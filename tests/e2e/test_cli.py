"""T053's end-to-end guards, both driven through the real `plan` Typer command (F15, F19).

PLAN.md's test strategy section (verbatim): "Golden end-to-end. Fixture map through the whole CLI
produces a `route.json` compared against a stored golden with numeric tolerance; also the F19
determinism check (same seed, byte-identical)." Two distinct checks, kept as two distinct test
classes below rather than folded into one:

* `TestGoldenRegression` -- one `plan` run compared against `golden_route.json` (this directory)
  with numeric tolerance (`pytest.approx` on parsed JSON, not a byte comparison).
* `TestDeterminism` -- two `plan` runs with byte-for-byte identical arguments compared with
  `Path.read_bytes()` equality (no tolerance at all -- F19's own wording is "byte-identical").

Both drive `plan` via `--controls <written controls.csv>` rather than `--strategy auto` through
detection: ADR-008/ADR-009 both state OCR is explicitly non-load-bearing/best-effort, so coupling
either check to real Tesseract output would risk environment-dependent flakiness for no benefit.
`tests/unit/test_cli.py::TestPlan::test_end_to_end_via_controls_csv_skips_detection` already
establishes this `write_controls` + `--controls` pattern; both classes below reuse it.

Both classes use the ordinary small `make_synthetic_map` scale (1600x1200 default preset, not the
`full_size_synthetic_map` 4000x3000 preset reserved for `tests/perf/test_budgets.py` and the three
existing `@pytest.mark.perf` tests it documents) -- neither check needs "full size", and running
the whole pipeline at that size on every ordinary suite run would be wasteful.

Every `plan` invocation below passes an explicit `--out-dir` inside `tmp_path`.  `plan_cmd`'s
default `--out-dir` is `.` (the process cwd) and this project has already hit that exact mistake
twice (see `docs/STATUS.md`'s "Blocked on the owner" section, and the near-miss fixed alongside
T052's own landing) -- never invoke `plan` without `--out-dir` in a test.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from typer.testing import CliRunner

from fixtures.synth_map import make_synthetic_map
from rogaine.cli import app
from rogaine.io.controls_csv import write_controls

pytestmark = pytest.mark.e2e

runner = CliRunner()

#: This directory's own golden fixture (T053's call on where to put it -- see module docstring).
_GOLDEN_PATH = Path(__file__).parent / "golden_route.json"


def _write_png(path: Path, image_rgb: np.ndarray) -> None:
    """Write an RGB array to *path* as a PNG (cv2 wants BGR) -- matches
    `tests/unit/test_cli.py`'s own helper of the same name."""
    ok, buf = cv2.imencode(".png", image_rgb[:, :, ::-1])
    assert ok
    path.write_bytes(buf.tobytes())


def _assert_json_approx(expected: object, actual: object, *, path: str = "$") -> None:
    """Recursively compare parsed JSON, tolerating float drift with `pytest.approx` while
    requiring exact equality everywhere else (ints, strings, bools, null, structure, key set).
    """
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected an object, got {type(actual).__name__}"
        assert expected.keys() == actual.keys(), f"{path}: key set differs"
        for key in expected:
            _assert_json_approx(expected[key], actual[key], path=f"{path}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list), f"{path}: expected an array, got {type(actual).__name__}"
        assert len(expected) == len(actual), f"{path}: length {len(expected)} != {len(actual)}"
        for i, (e, a) in enumerate(zip(expected, actual, strict=True)):
            _assert_json_approx(e, a, path=f"{path}[{i}]")
    elif isinstance(expected, float):
        assert actual == pytest.approx(expected, rel=1e-6, abs=1e-9), (
            f"{path}: {actual} != {expected}"
        )
    else:
        assert expected == actual, f"{path}: {actual!r} != {expected!r}"


def _run_plan(out_dir: Path, *, map_path: Path, dpi: float, scale: float, controls_csv: Path,
              strategy: str, seed: int, extra: list[str] | None = None):
    args = [
        "plan",
        "--map", str(map_path),
        "--dpi", str(dpi),
        "--scale", str(scale),
        "--controls", str(controls_csv),
        "--strategy", strategy,
        "--seed", str(seed),
        "--alternatives", "0",
        "--out-dir", str(out_dir),
    ]
    if extra:
        args.extend(extra)
    return runner.invoke(app, args)


class TestGoldenRegression:
    """`route.json` from a fixed small instance, compared against a stored golden.

    `--strategy exact` removes GRASP's RNG-driven search order as a source of drift, leaving only
    genuine float/library-version differences as what `pytest.approx` needs to absorb -- 6
    candidate controls (well under `exact_max_controls=15`, `config/default.toml`) keeps Held-Karp
    fast.
    """

    def test_route_json_matches_golden(self, tmp_path: Path) -> None:
        sm = make_synthetic_map(seed=8, n_controls=6)
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)
        controls_csv = tmp_path / "controls.csv"
        write_controls(controls_csv, sm.controls)
        out_dir = tmp_path / "out"

        result = _run_plan(
            out_dir,
            map_path=map_path,
            dpi=sm.dpi,
            scale=sm.scale_denominator,
            controls_csv=controls_csv,
            strategy="exact",
            seed=0,
        )

        assert result.exit_code == 0, result.stdout
        route_json_path = out_dir / "route.json"
        assert route_json_path.is_file()
        actual = json.loads(route_json_path.read_text(encoding="utf-8"))

        if not _GOLDEN_PATH.is_file():
            pytest.fail(
                f"{_GOLDEN_PATH} does not exist -- see this test module's docstring / T053's "
                "landing notes for how it was generated and hand-verified before being committed."
            )
        expected = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
        _assert_json_approx(expected, actual)


class TestDeterminism:
    """F19: "Same inputs and same seed produce byte-identical JSON."

    `--strategy heuristic` specifically (not `exact` or `auto`): exact has no RNG at all, so it
    would not meaningfully exercise the seeding contract F19 is actually about -- heuristic's
    GRASP construction is the one path where a seeding bug could silently produce two
    different-but-both-valid routes.
    """

    def test_same_seed_gives_byte_identical_route_json(self, tmp_path: Path) -> None:
        sm = make_synthetic_map(seed=9, n_controls=6)
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)
        controls_csv = tmp_path / "controls.csv"
        write_controls(controls_csv, sm.controls)

        out_dir_a = tmp_path / "out_a"
        out_dir_b = tmp_path / "out_b"
        extra = ["--heuristic-time-budget", "2.0"]

        result_a = _run_plan(
            out_dir_a,
            map_path=map_path,
            dpi=sm.dpi,
            scale=sm.scale_denominator,
            controls_csv=controls_csv,
            strategy="heuristic",
            seed=123,
            extra=extra,
        )
        assert result_a.exit_code == 0, result_a.stdout

        result_b = _run_plan(
            out_dir_b,
            map_path=map_path,
            dpi=sm.dpi,
            scale=sm.scale_denominator,
            controls_csv=controls_csv,
            strategy="heuristic",
            seed=123,
            extra=extra,
        )
        assert result_b.exit_code == 0, result_b.stdout

        bytes_a = (out_dir_a / "route.json").read_bytes()
        bytes_b = (out_dir_b / "route.json").read_bytes()
        assert bytes_a == bytes_b, "same inputs and seed produced different route.json bytes"
