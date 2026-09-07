"""Command line entry point.

M0 shipped the corpus commands. T044 added `bench`, a synthetic solver-comparison smoke check
that depends only on T041/T042's solver contracts. T050 (WS-C) adds `segment`, `detect`, `plan`
and a deliberate `serve` stub to this same app -- see each command's own docstring for the scope
cuts that are documented judgement calls, not oversights: `serve` prints where the real FastAPI
backend lands (T060) and exits non-zero. `plan` originally ended at the terminal summary (SPEC
F15's `route.json`/`route.png` writers were T051/T052, not landed at the time); both have since
landed and `plan` now writes both artefacts to `--out-dir`.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Literal

import numpy as np
import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from rogaine import __version__
from rogaine.config import AppConfig, default_config, load_config
from rogaine.cost.field import compute_cost_field
from rogaine.cost.graph import build_grid_graph
from rogaine.cost.travel import build_travel_matrix
from rogaine.io.controls_csv import read_controls, write_controls
from rogaine.io.corpus import CorpusEntry, list_corpus, read_entry
from rogaine.io.raster import load_raster, resolve_dpi
from rogaine.io.route_json import write_route_json
from rogaine.io.scale import Calibration, mpp_from_dpi
from rogaine.models import TERRAIN_ORDER, Control, RunConfig, TravelMatrix
from rogaine.render.overlay import write_overlay
from rogaine.render.preview import write_preview
from rogaine.solve.alternatives import solve_alternatives
from rogaine.solve.exact import solve_exact
from rogaine.solve.heuristic import solve_heuristic
from rogaine.vision.calibrate import calibrate_map
from rogaine.vision.controls import detect_controls
from rogaine.vision.ocr import read_control_numbers
from rogaine.vision.segment import save_terrain_map
from rogaine.vision.segment import segment as run_segmentation

DEFAULT_CORPUS = Path("data/maps")

app = typer.Typer(
    help="Plan rogaine routes from orienteering map rasters.",
    no_args_is_help=True,
    add_completion=False,
)
corpus_app = typer.Typer(help="Inspect the map corpus under data/maps/.", no_args_is_help=True)
app.add_typer(corpus_app, name="corpus")

console = Console()


# invoke_without_command lets `--version` run without a subcommand; no_args_is_help still turns a
# bare `rogaine` into the help screen.
@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="Print the version and exit."),
) -> None:
    if version:
        console.print(__version__)
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()


@corpus_app.command("list")
def corpus_list(
    root: Path = typer.Option(DEFAULT_CORPUS, "--root", help="Corpus directory."),
) -> None:
    """List every map and what metadata it is still missing.

    Never fails on an incomplete map: a half-set-up corpus is the normal state while files are
    still arriving.
    """
    entries = list_corpus(root)
    if not entries:
        console.print(f"[yellow]No maps under {root}[/]. See data/README.md for the layout.")
        raise typer.Exit()

    table = Table(title=f"{len(entries)} map(s) under {root}")
    table.add_column("id")
    table.add_column("m/px", justify="right")
    table.add_column("plannable", justify="center")
    table.add_column("scale source")
    table.add_column("missing / problems")

    for entry in entries:
        mpp = f"{entry.meters_per_pixel:.3f}" if entry.meters_per_pixel else "-"
        notes = [*entry.problems, *entry.missing]
        table.add_row(
            entry.map_id,
            mpp,
            "[green]yes[/]" if entry.is_plannable else "[red]no[/]",
            _scale_source(entry),
            "; ".join(notes) if notes else "[green]complete[/]",
        )
    console.print(table)


def _scale_source(entry: CorpusEntry) -> str:
    """How an entry's scale was obtained -- surfaces T078/ADR-016's `calibration_source` (and, for
    a "measured" one, which tier) so a human looking at the CLI sees when a map's scale is a
    fabricated corpus default rather than a real measurement, instead of a plannable map with no
    visible hint either way.
    """
    if entry.calibration_source == "assumed_default":
        return "[yellow]assumed default[/]"
    if entry.calibration_source == "measured":
        tier = entry.calibration_tier or "?"
        return f"measured ({tier})"
    return "-"


@corpus_app.command("check")
def corpus_check(
    map_id: str = typer.Argument(..., help="Directory name under the corpus root."),
    root: Path = typer.Option(DEFAULT_CORPUS, "--root", help="Corpus directory."),
) -> None:
    """Report one map in full. Exits non-zero when the map cannot be planned on."""
    map_dir = root / map_id
    if not map_dir.is_dir():
        console.print(f"[red]{map_dir} does not exist[/]")
        raise typer.Exit(code=2)

    entry = read_entry(map_dir)
    console.print(f"[bold]{entry.map_id}[/]" + (f" — {entry.name}" if entry.name else ""))
    console.print(f"  raster:     {entry.raster or '[red]missing[/]'}")
    console.print(f"  scale:      {entry.scale_denominator or '-'} at {entry.dpi or '-'} dpi")
    console.print(f"  calibrated: {'yes' if entry.calibration else 'no'}")
    console.print(f"  scale src:  {_scale_source(entry)}")
    mpp = entry.meters_per_pixel
    console.print(f"  m/px:       {f'{mpp:.4f}' if mpp else '[red]unknown[/]'}")
    console.print(f"  controls:   {'controls.csv' if entry.has_controls else 'none (detect)'}")
    console.print(f"  reference:  {'reference.json' if entry.has_reference else 'none'}")
    for problem in entry.problems:
        console.print(f"  [red]problem:[/]  {problem}")
    for gap in entry.missing:
        console.print(f"  [yellow]missing:[/]  {gap}")

    if not entry.is_plannable:
        raise typer.Exit(code=1)


_DURATION_RE = re.compile(
    r"^(?:(?P<h>\d+(?:\.\d+)?)h)?(?:(?P<m>\d+(?:\.\d+)?)m)?(?:(?P<s>\d+(?:\.\d+)?)s)?$"
)


def _parse_duration(text: str) -> float:
    """Parse a human time budget: '4h', '2h30m', '90s', or a bare number of seconds.

    Backs `plan`'s `--limit` (SPEC's flows call for something simple here, not a new dependency).
    """
    text = text.strip()
    try:
        return float(text)
    except ValueError:
        pass
    match = _DURATION_RE.match(text)
    if not match or not any(match.groups()):
        raise ValueError(f"cannot parse --limit {text!r}; use e.g. '4h', '2h30m', or seconds")
    hours = float(match.group("h") or 0.0)
    minutes = float(match.group("m") or 0.0)
    seconds = float(match.group("s") or 0.0)
    total = hours * 3600.0 + minutes * 60.0 + seconds
    if total <= 0:
        raise ValueError(f"--limit must be positive, got {text!r}")
    return total


def _fmt_duration(seconds: float) -> str:
    """Render seconds as `H:MM:SS`, or `M:SS` under an hour."""
    total = max(0, round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _parse_calibration(text: str) -> Calibration:
    parts = text.split(",")
    if len(parts) != 5:
        raise ValueError(f"--calibrate expects 'x1,y1,x2,y2,meters', got {text!r}")
    try:
        x1, y1, x2, y2, meters = (float(p) for p in parts)
    except ValueError as exc:
        raise ValueError(f"--calibrate values must all be numbers, got {text!r}") from exc
    return Calibration(x1, y1, x2, y2, meters)


def _resolve_mpp(
    dpi: float,
    scale: float | None,
    calibrate: str | None,
    auto_scale: bool,
    image: np.ndarray,
    config: AppConfig,
) -> tuple[float, float, str | None]:
    """Meters-per-pixel from exactly one of `--scale` (+ dpi), `--calibrate`, or `--auto-scale` --
    never zero, never more than one (ADR-022 extends the original --scale/--calibrate contract
    with a third, opt-in option). Returns `(mpp, dpi, tier)`: *dpi* passes through unchanged for
    the two manual paths, or becomes the detector's own measured/implied dpi when `--auto-scale`
    fires (mirrors `calibrate_corpus`'s use of `CalibrationResult.dpi`, ADR-016) so downstream
    mm-to-px conversions (segmentation, detection) use the detected value, not a stale probe;
    *tier* is `None` for the two manual paths, else whichever tier fired (`scale_bar`/`grid`/
    `circle`, F21). Shared by `segment` and `plan` (`detect` never needs mpp, only dpi).
    """
    if scale is not None and calibrate is not None:
        raise ValueError("pass either --scale or --calibrate, not both")
    if auto_scale and (scale is not None or calibrate is not None):
        raise ValueError("pass --auto-scale on its own, not together with --scale or --calibrate")
    if scale is not None:
        return mpp_from_dpi(dpi, scale), dpi, None
    if calibrate is not None:
        return _parse_calibration(calibrate).meters_per_pixel, dpi, None
    if auto_scale:
        result, _ = calibrate_map(image, config)
        if result is None:
            raise ValueError(
                "auto-scale: no calibration signal found on this map -- pass --scale or "
                "--calibrate instead"
            )
        return mpp_from_dpi(result.dpi, result.scale_denominator), result.dpi, result.source
    raise ValueError(
        "pass --scale (with --dpi), --calibrate, or --auto-scale to resolve meters-per-pixel"
    )


@app.command("segment")
def segment_cmd(
    map_path: Path = typer.Option(..., "--map", help="Map raster (or PDF) to segment."),
    dpi: float | None = typer.Option(
        None, "--dpi", help="Scan resolution; probed from the file or config default if omitted."
    ),
    scale: float | None = typer.Option(
        None, "--scale", help="Map scale denominator (1:N); combined with dpi (SPEC F2)."
    ),
    calibrate: str | None = typer.Option(
        None,
        "--calibrate",
        help="Two-point calibration 'x1,y1,x2,y2,meters' in place of --scale (SPEC F3).",
    ),
    auto_scale: bool = typer.Option(
        False,
        "--auto-scale",
        help=(
            "Best-effort automatic scale detection (SPEC F21, ADR-022) in place of --scale/"
            "--calibrate; reports which tier fired or fails with a clear message."
        ),
    ),
    page: int = typer.Option(0, "--page", help="PDF page, 0-based; ignored for other formats."),
    out_dir: Path = typer.Option(
        Path("."), "--out-dir", help="Directory for terrain.npz and terrain_preview.png."
    ),
    config: Path | None = typer.Option(None, "--config", help="Config TOML overriding defaults."),
) -> None:
    """Segment a map raster into a terrain map: writes `terrain.npz` + `terrain_preview.png`.

    No `--seed`: normalize/classify/contour-density is deterministic given the same image and
    config, so a decorative seed flag here would promise a guarantee this command doesn't need.
    """
    try:
        cfg = load_config(config)
        dpi_resolved = resolve_dpi(map_path, user_dpi=dpi)
        image = load_raster(map_path, page=page, dpi=dpi_resolved)
        mpp, dpi_resolved, tier = _resolve_mpp(
            dpi_resolved, scale, calibrate, auto_scale, image, cfg
        )
        if tier is not None:
            console.print(
                f"[green]auto-scale:[/] {tier} tier -> {mpp:.4f} m/px, {dpi_resolved:.0f} dpi"
            )
        terrain_map = run_segmentation(image, dpi_resolved, mpp, cfg)
    except (ValueError, OSError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from exc

    out_dir.mkdir(parents=True, exist_ok=True)
    save_terrain_map(out_dir / "terrain.npz", terrain_map)
    write_preview(out_dir / "terrain_preview.png", terrain_map, cfg)

    h, w = terrain_map.shape
    counts = np.bincount(terrain_map.labels.ravel(), minlength=len(TERRAIN_ORDER))
    total = int(counts.sum())
    table = Table(
        title=f"segment: {map_path.name} ({w}x{h}, {mpp:.4f} m/px, {dpi_resolved:.0f} dpi)"
    )
    table.add_column("terrain class")
    table.add_column("pixels", justify="right")
    table.add_column("%", justify="right")
    for cls, count in zip(TERRAIN_ORDER, counts, strict=True):
        if count == 0:
            continue
        table.add_row(cls.value, f"{int(count):,}", f"{100.0 * count / total:.1f}")
    console.print(table)
    console.print(f"wrote {out_dir / 'terrain.npz'} and {out_dir / 'terrain_preview.png'}")


@app.command("detect")
def detect_cmd(
    map_path: Path = typer.Option(..., "--map", help="Map raster (or PDF) to detect controls on."),
    dpi: float | None = typer.Option(
        None, "--dpi", help="Scan resolution; probed from the file or config default if omitted."
    ),
    out: Path = typer.Option(
        Path("controls.csv"), "--out", help="Where to write the controls CSV."
    ),
    config: Path | None = typer.Option(None, "--config", help="Config TOML overriding defaults."),
) -> None:
    """Detect the hub and control circles, read their numbers, and write an editable CSV (F7-F9).

    No `--seed`: detection and OCR are deterministic given the same image and config.
    """
    try:
        cfg = load_config(config)
        dpi_resolved = resolve_dpi(map_path, user_dpi=dpi)
        image = load_raster(map_path, dpi=dpi_resolved)
        controls = detect_controls(image, dpi_resolved, cfg)
        controls, flags = read_control_numbers(image, controls, dpi_resolved, cfg)
        write_controls(out, controls)
    except (ValueError, OSError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from exc

    hub_found = any(c.is_hub for c in controls)
    n_circles = sum(1 for c in controls if not c.is_hub)
    console.print(f"hub: {'[green]found[/]' if hub_found else '[red]not found[/]'}")
    console.print(f"circles detected: {n_circles}")
    console.print(f"unreadable numbers: {len(flags)}")
    for flag in flags:
        console.print(f"  [yellow]{flag}[/]")
    console.print(f"wrote {out}")

    if not hub_found:
        console.print(
            "[red]no hub detected[/] -- a route needs a start/finish; add one by hand to the "
            "CSV or improve the scan."
        )
        raise typer.Exit(code=1)


@app.command("plan")
def plan_cmd(
    map_path: Path = typer.Option(..., "--map", help="Map raster (or PDF) to plan on."),
    dpi: float | None = typer.Option(
        None, "--dpi", help="Scan resolution; probed from the file or config default if omitted."
    ),
    scale: float | None = typer.Option(
        None, "--scale", help="Map scale denominator (1:N); combined with dpi (SPEC F2)."
    ),
    calibrate: str | None = typer.Option(
        None,
        "--calibrate",
        help="Two-point calibration 'x1,y1,x2,y2,meters' in place of --scale (SPEC F3).",
    ),
    auto_scale: bool = typer.Option(
        False,
        "--auto-scale",
        help=(
            "Best-effort automatic scale detection (SPEC F21, ADR-022) in place of --scale/"
            "--calibrate; reports which tier fired or fails with a clear message."
        ),
    ),
    controls_path: Path | None = typer.Option(
        None,
        "--controls",
        help="Hand-edited controls.csv; overrides detection entirely when given (SPEC F9).",
    ),
    speed: float = typer.Option(2.0, "--speed", min=0.0, help="Runner base speed, m/s."),
    limit: str = typer.Option(
        "4h", "--limit", help="Time budget: '4h', '2h30m', or a plain number of seconds."
    ),
    penalty_per_min: float = typer.Option(
        1.0, "--penalty-per-min", min=0.0, help="Score penalty per minute over the time limit."
    ),
    strategy: Literal["auto", "exact", "heuristic"] = typer.Option(
        "auto", "--strategy", help="Solver dispatch; 'auto' picks exact under the control cap."
    ),
    heuristic_time_budget: float = typer.Option(
        30.0, "--heuristic-time-budget", min=0.0, help="Heuristic solver time budget, seconds."
    ),
    alternatives: int = typer.Option(
        3, "--alternatives", min=0, help="Top-K structurally distinct alternative routes (F16)."
    ),
    seed: int = typer.Option(
        0, "--seed", help="Seeds the heuristic solver and the alternatives search (F19)."
    ),
    out_dir: Path = typer.Option(
        Path("."), "--out-dir", help="Directory for route.json and route.png (SPEC F15)."
    ),
    config: Path | None = typer.Option(None, "--config", help="Config TOML overriding defaults."),
) -> None:
    """Plan a route: resolve controls, build the cost field and travel matrix, solve, print
    a summary of legs, time, points and penalty plus the top-K alternatives (F1-F3, F7-F14, F16),
    and write `route.json` / `route.png` to `--out-dir` (F15, `io/route_json.py` +
    `render/overlay.py`). Nothing is written for a run that exits non-zero (bad input, over the
    exact-solver cap, or no reachable route) -- only a successfully solved route reaches disk.
    """
    try:
        cfg = load_config(config)
        dpi_resolved = resolve_dpi(map_path, user_dpi=dpi)
        image = load_raster(map_path, dpi=dpi_resolved)
        mpp, dpi_resolved, tier = _resolve_mpp(
            dpi_resolved, scale, calibrate, auto_scale, image, cfg
        )
        if tier is not None:
            console.print(
                f"[green]auto-scale:[/] {tier} tier -> {mpp:.4f} m/px, {dpi_resolved:.0f} dpi"
            )

        if controls_path is not None:
            controls = read_controls(controls_path)
        else:
            controls = detect_controls(image, dpi_resolved, cfg)
            controls, _flags = read_control_numbers(image, controls, dpi_resolved, cfg)

        if not any(c.is_hub for c in controls):
            console.print("[red]no hub[/] -- pass --controls with a hub row, or improve the scan.")
            raise typer.Exit(code=1)

        limit_s = _parse_duration(limit)
        run_config = RunConfig(
            base_speed_mps=speed,
            time_limit_s=limit_s,
            penalty_per_min=penalty_per_min,
            strategy=strategy,
            heuristic_time_budget_s=heuristic_time_budget,
            alternatives=alternatives,
            seed=seed,
        )

        terrain_map = run_segmentation(image, dpi_resolved, mpp, cfg)
        cost_field = compute_cost_field(terrain_map, speed, cfg)
        graph = build_grid_graph(cost_field, cfg)
        matrix = build_travel_matrix(controls, graph, mpp, cfg)

        n_candidates = sum(1 for c in controls if not c.is_hub and c.points is not None)
        if strategy == "exact":
            route = solve_exact(controls, matrix, run_config, cfg)
        elif strategy == "heuristic":
            route = solve_heuristic(controls, matrix, run_config, cfg)
        elif n_candidates <= cfg.solver.exact_max_controls:
            route = solve_exact(controls, matrix, run_config, cfg)
        else:
            route = solve_heuristic(controls, matrix, run_config, cfg)

        if len(route.order) <= 2:
            console.print(
                "[red]no reachable route[/] -- no candidate control could be reached within "
                "the time limit."
            )
            raise typer.Exit(code=1)

        alt_result = solve_alternatives(controls, matrix, run_config, cfg)

        out_dir.mkdir(parents=True, exist_ok=True)
        write_route_json(out_dir / "route.json", route, run_config)
        write_overlay(out_dir / "route.png", image, route, controls)
    except (ValueError, OSError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from exc

    by_id = {c.id: c for c in controls}
    table = Table(
        title=f"route: {len(route.order) - 2} control(s), {route.solver} solver"
        + (" (optimal)" if route.optimal else "")
    )
    table.add_column("#", justify="right")
    table.add_column("control")
    table.add_column("leg time", justify="right")
    table.add_column("leg dist (m)", justify="right")
    table.add_column("cumulative", justify="right")
    table.add_column("points", justify="right")
    table.add_row("0", "hub", "-", "-", "0:00", "-")
    cumulative = 0.0
    for i, leg in enumerate(route.legs, start=1):
        cumulative += leg.seconds
        control = by_id[leg.to_id]
        if control.is_hub:
            label, points = "hub", "-"
        else:
            label = f"#{control.number if control.number is not None else control.id}"
            points = str(control.points or 0)
        table.add_row(
            str(i),
            label,
            _fmt_duration(leg.seconds),
            f"{leg.meters:.0f}",
            _fmt_duration(cumulative),
            points,
        )
    console.print(table)

    console.print(
        f"total: {_fmt_duration(route.total_seconds)} / limit "
        f"{_fmt_duration(run_config.time_limit_s)}, {route.total_meters:.0f} m, "
        f"{route.points} points, penalty {route.penalty:.2f}, score {route.score:.2f}"
    )

    if alt_result.routes:
        alt_table = Table(
            title=f"alternatives: top {len(alt_result.routes)} "
            f"(interestingness {alt_result.interestingness:.2f})"
        )
        alt_table.add_column("rank", justify="right")
        alt_table.add_column("controls visited", justify="right")
        alt_table.add_column("score", justify="right")
        for rank, alt_route in enumerate(alt_result.routes, start=1):
            alt_table.add_row(str(rank), str(len(alt_route.order) - 2), f"{alt_route.score:.2f}")
        console.print(alt_table)
    else:
        console.print("alternatives: none requested (--alternatives 0)")

    console.print(f"wrote {out_dir / 'route.json'} and {out_dir / 'route.png'}")


def _bench_instance(
    n_candidates: int, seed: int, heuristic_time_budget_s: float
) -> tuple[list[Control], TravelMatrix, RunConfig]:
    """Build a small, self-contained, seeded synthetic Orienteering Problem instance.

    Mirrors (does not import -- this module is application code, the tests are deliberately
    self-contained) the pattern established by `tests/unit/solve/test_heuristic.py`'s
    `_random_instance`: hub id 0 plus `n_candidates` candidates at random pixel positions, a
    random symmetric finite travel-time matrix (every pair reachable, so neither solver ever
    hits an unreachable leg), every control's points resolved (never `None`), and a placeholder
    2-point polyline per reachable ordered pair -- geometry itself is never scored by either
    solver, only `seconds`/`meters` and `points` are.
    """
    rng = np.random.default_rng(seed)
    ids = list(range(n_candidates + 1))
    positions = {i: (float(rng.integers(0, 1000)), float(rng.integers(0, 1000))) for i in ids}

    controls = [Control(id=0, x=positions[0][0], y=positions[0][1], is_hub=True)]
    for i in ids[1:]:
        controls.append(
            Control(id=i, x=positions[i][0], y=positions[i][1], points=int(rng.integers(1, 30)))
        )

    raw = rng.uniform(50.0, 500.0, size=(len(ids), len(ids)))
    seconds = (raw + raw.T) / 2.0
    np.fill_diagonal(seconds, 0.0)
    meters = seconds * 1.4  # arbitrary consistent scale; neither solver reads meters

    paths: dict[tuple[int, int], np.ndarray] = {}
    for a in ids:
        for b in ids:
            if a == b:
                continue
            xa, ya = positions[a]
            xb, yb = positions[b]
            paths[(a, b)] = np.array([[int(xa), int(ya)], [int(xb), int(yb)]], dtype=np.int32)

    matrix = TravelMatrix(control_ids=tuple(ids), seconds=seconds, meters=meters, paths=paths)
    run_config = RunConfig(
        base_speed_mps=1.5,
        time_limit_s=400.0,
        penalty_per_min=4.0,
        seed=seed,
        heuristic_time_budget_s=heuristic_time_budget_s,
    )
    return controls, matrix, run_config


@app.command("bench")
def bench(
    n_candidates: int = typer.Option(
        10,
        "--n-candidates",
        min=0,
        help="Candidate controls in the synthetic instance (hub excluded).",
    ),
    seed: int = typer.Option(
        0, "--seed", help="Seeds instance generation and the heuristic solver's RNG (F19)."
    ),
    time_budget: float = typer.Option(
        2.0,
        "--time-budget",
        min=0.0,
        help="Heuristic solver time budget, in seconds.",
    ),
) -> None:
    """Run both solvers on a reduced synthetic instance and report the exact-vs-heuristic gap.

    Builds its own small synthetic Orienteering Problem instance (`_bench_instance`) rather than
    driving the real vision/cost pipeline -- that pipeline's `plan` command is M5/T050's job, not
    this one's; `bench` needs nothing beyond T041 (`solve_exact`) and T042 (`solve_heuristic`).

    Exits 0 regardless of the measured gap. `bench` reports; it does not gate: T042's own test
    suite (`tests/unit/solve/test_heuristic.py`) already exhaustively verifies the heuristic's
    quality across many seeds and sizes, so a bad gap here would mean this command's own synthetic
    instance or defaults are unrepresentative, not a newly broken solver -- that is a bug to fix in
    `bench`, not a build to fail. The gap is still printed with a clear pass/fail colour against
    the F13 5% bar so a human glancing at the output can tell at a glance.
    """
    cfg = default_config()
    cap = cfg.solver.exact_max_controls
    if n_candidates > cap:
        console.print(
            f"[red]--n-candidates={n_candidates} exceeds "
            f"config.solver.exact_max_controls={cap}[/]"
        )
        raise typer.Exit(code=1)

    controls, matrix, run_config = _bench_instance(n_candidates, seed, time_budget)

    t0 = time.perf_counter()
    exact_route = solve_exact(controls, matrix, run_config)
    exact_elapsed = time.perf_counter() - t0

    t0 = time.perf_counter()
    heuristic_route = solve_heuristic(controls, matrix, run_config)
    heuristic_elapsed = time.perf_counter() - t0

    gap = (
        0.0
        if exact_route.score == 0.0
        else (exact_route.score - heuristic_route.score) / exact_route.score
    )

    table = Table(title=f"bench: {n_candidates} candidate(s), seed={seed}")
    table.add_column("solver")
    table.add_column("points", justify="right")
    table.add_column("time (s)", justify="right")
    table.add_column("score", justify="right")
    table.add_row(
        "exact", str(exact_route.points), f"{exact_elapsed:.3f}", f"{exact_route.score:.2f}"
    )
    table.add_row(
        "heuristic",
        str(heuristic_route.points),
        f"{heuristic_elapsed:.3f}",
        f"{heuristic_route.score:.2f}",
    )
    console.print(table)

    verdict = "green" if gap <= 0.05 else "red"
    console.print(f"gap: [{verdict}]{gap:.2%}[/] (F13 bar: <= 5.00%)")


@app.command("serve")
def serve_cmd(
    host: str = typer.Option(
        "127.0.0.1", "--host", help="Bind address -- never 0.0.0.0 (SPEC security)."
    ),
    port: int = typer.Option(8000, "--port", help="Bind port."),
) -> None:
    """Launch the FastAPI web viewer backend (T060, `src/rogaine/web/app.py`) via uvicorn."""
    uvicorn.run("rogaine.web.app:app", host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    app()
