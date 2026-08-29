"""Command line entry point.

M0 shipped the corpus commands. T044 adds `bench`, a synthetic solver-comparison smoke check
that depends only on T041/T042's solver contracts. T050 (WS-C) still adds `segment`, `plan` and
`serve` to this same app.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import typer
from rich.console import Console
from rich.table import Table

from rogaine import __version__
from rogaine.config import default_config
from rogaine.io.corpus import list_corpus, read_entry
from rogaine.models import Control, RunConfig, TravelMatrix
from rogaine.solve.exact import solve_exact
from rogaine.solve.heuristic import solve_heuristic

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
    table.add_column("missing / problems")

    for entry in entries:
        mpp = f"{entry.meters_per_pixel:.3f}" if entry.meters_per_pixel else "-"
        notes = [*entry.problems, *entry.missing]
        table.add_row(
            entry.map_id,
            mpp,
            "[green]yes[/]" if entry.is_plannable else "[red]no[/]",
            "; ".join(notes) if notes else "[green]complete[/]",
        )
    console.print(table)


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


if __name__ == "__main__":  # pragma: no cover
    app()
