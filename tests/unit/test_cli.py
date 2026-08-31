"""The CLI surface that exists in M0 (T005). T050 extends both the app and this file."""

from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np
import pytest
from typer.testing import CliRunner

from fixtures.synth_map import make_synthetic_map
from rogaine import __version__
from rogaine.cli import app
from rogaine.config import default_config
from rogaine.io.controls_csv import write_controls
from rogaine.models import Control

runner = CliRunner()


def _map_dir(root, map_id: str, meta: str):
    d = root / map_id
    d.mkdir(parents=True)
    (d / "map.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (d / "meta.toml").write_text(meta, encoding="utf-8")
    return d


def _write_png(path: Path, image_rgb: np.ndarray) -> None:
    """Write an RGB array to *path* as a PNG (cv2 wants BGR); matches `test_raster.py`'s pattern."""
    ok, buf = cv2.imencode(".png", image_rgb[:, :, ::-1])
    assert ok
    path.write_bytes(buf.tobytes())


class TestRoot:
    def test_version(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.stdout

    def test_bare_invocation_shows_help_rather_than_failing(self) -> None:
        assert "corpus" in runner.invoke(app, []).stdout


class TestCorpusList:
    def test_an_empty_corpus_is_reported_not_an_error(self, tmp_path) -> None:
        result = runner.invoke(app, ["corpus", "list", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "No maps under" in result.stdout

    def test_lists_good_and_broken_maps_together(self, tmp_path) -> None:
        _map_dir(tmp_path, "good", "scale_denominator = 30000\ndpi = 300\n")
        _map_dir(tmp_path, "noscale", 'name = "n"\n')
        result = runner.invoke(app, ["corpus", "list", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "good" in result.stdout and "noscale" in result.stdout


class TestCorpusCheck:
    def test_a_complete_map_exits_zero(self, tmp_path) -> None:
        _map_dir(tmp_path, "good", "scale_denominator = 30000\ndpi = 300\n")
        result = runner.invoke(app, ["corpus", "check", "good", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "2.5400" in result.stdout

    def test_an_unplannable_map_exits_nonzero(self, tmp_path) -> None:
        _map_dir(tmp_path, "noscale", 'name = "n"\n')
        result = runner.invoke(app, ["corpus", "check", "noscale", "--root", str(tmp_path)])
        assert result.exit_code == 1

    def test_an_unknown_map_exits_two(self, tmp_path) -> None:
        result = runner.invoke(app, ["corpus", "check", "nope", "--root", str(tmp_path)])
        assert result.exit_code == 2


class TestBench:
    def test_reports_a_gap_within_the_f13_bar(self) -> None:
        result = runner.invoke(
            app, ["bench", "--n-candidates", "10", "--seed", "0", "--time-budget", "1.5"]
        )
        assert result.exit_code == 0
        assert "exact" in result.stdout and "heuristic" in result.stdout

        match = re.search(r"gap:\s*(-?\d+(?:\.\d+)?)%", result.stdout)
        assert match, f"no gap percentage found in output:\n{result.stdout}"
        gap = float(match.group(1)) / 100.0
        assert gap <= 0.05, f"gap {gap:.4f} exceeds the F13 5% bar:\n{result.stdout}"

    def test_n_candidates_above_the_exact_cap_fails_cleanly(self) -> None:
        cap = default_config().solver.exact_max_controls
        result = runner.invoke(app, ["bench", "--n-candidates", str(cap + 1)])
        assert result.exit_code != 0
        assert "exact_max_controls" in result.stdout


class TestSegment:
    def test_writes_terrain_artifacts_and_prints_a_summary(self, tmp_path) -> None:
        sm = make_synthetic_map(seed=1)
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)
        out_dir = tmp_path / "out"

        result = runner.invoke(
            app,
            [
                "segment",
                "--map",
                str(map_path),
                "--dpi",
                str(sm.dpi),
                "--scale",
                str(sm.scale_denominator),
                "--out-dir",
                str(out_dir),
            ],
        )
        assert result.exit_code == 0, result.stdout
        assert (out_dir / "terrain.npz").is_file()
        assert (out_dir / "terrain_preview.png").is_file()
        assert "forest_runnable" in result.stdout

    def test_rejects_both_scale_and_calibrate(self, tmp_path) -> None:
        sm = make_synthetic_map(seed=1)
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)

        result = runner.invoke(
            app,
            [
                "segment",
                "--map",
                str(map_path),
                "--dpi",
                str(sm.dpi),
                "--scale",
                str(sm.scale_denominator),
                "--calibrate",
                "0,0,100,0,50",
            ],
        )
        assert result.exit_code != 0
        assert "not both" in result.stdout

    def test_rejects_neither_scale_nor_calibrate(self, tmp_path) -> None:
        sm = make_synthetic_map(seed=1)
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)

        result = runner.invoke(app, ["segment", "--map", str(map_path), "--dpi", str(sm.dpi)])
        assert result.exit_code != 0
        assert "--scale" in result.stdout


class TestDetect:
    def test_detects_hub_and_writes_a_controls_csv(self, tmp_path) -> None:
        sm = make_synthetic_map(seed=2)
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)
        out_csv = tmp_path / "controls.csv"

        result = runner.invoke(
            app,
            ["detect", "--map", str(map_path), "--dpi", str(sm.dpi), "--out", str(out_csv)],
        )
        assert result.exit_code == 0, result.stdout
        assert out_csv.is_file()
        assert "found" in result.stdout

    def test_exits_nonzero_when_no_hub_is_present(self, tmp_path) -> None:
        blank = np.full((200, 200, 3), 255, dtype=np.uint8)
        map_path = tmp_path / "map.png"
        _write_png(map_path, blank)
        out_csv = tmp_path / "controls.csv"

        result = runner.invoke(
            app, ["detect", "--map", str(map_path), "--dpi", "300", "--out", str(out_csv)]
        )
        assert result.exit_code != 0
        assert "no hub" in result.stdout


class TestPlan:
    def test_end_to_end_via_detection(self, tmp_path) -> None:
        sm = make_synthetic_map(seed=3, n_controls=6)
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)
        out_dir = tmp_path / "out"

        result = runner.invoke(
            app,
            [
                "plan",
                "--map",
                str(map_path),
                "--dpi",
                str(sm.dpi),
                "--scale",
                str(sm.scale_denominator),
                "--heuristic-time-budget",
                "0.5",
                "--alternatives",
                "2",
                "--out-dir",
                str(out_dir),
            ],
        )
        assert result.exit_code == 0, result.stdout
        assert "score" in result.stdout
        assert "alternatives" in result.stdout
        assert (out_dir / "route.json").is_file()
        assert (out_dir / "route.png").is_file()

    def test_end_to_end_via_controls_csv_skips_detection(self, tmp_path) -> None:
        sm = make_synthetic_map(seed=3, n_controls=6)
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)
        controls_csv = tmp_path / "controls.csv"
        write_controls(controls_csv, sm.controls)
        out_dir = tmp_path / "out"

        result = runner.invoke(
            app,
            [
                "plan",
                "--map",
                str(map_path),
                "--dpi",
                str(sm.dpi),
                "--scale",
                str(sm.scale_denominator),
                "--controls",
                str(controls_csv),
                "--heuristic-time-budget",
                "0.5",
                "--alternatives",
                "0",
                "--out-dir",
                str(out_dir),
            ],
        )
        assert result.exit_code == 0, result.stdout
        assert "alternatives: none requested" in result.stdout
        assert (out_dir / "route.json").is_file()
        assert (out_dir / "route.png").is_file()

    def test_rejects_scale_and_calibrate_together(self, tmp_path) -> None:
        sm = make_synthetic_map(seed=3, n_controls=1)
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)

        result = runner.invoke(
            app,
            [
                "plan",
                "--map",
                str(map_path),
                "--dpi",
                str(sm.dpi),
                "--scale",
                str(sm.scale_denominator),
                "--calibrate",
                "0,0,100,0,50",
            ],
        )
        assert result.exit_code != 0
        assert "not both" in result.stdout

    def test_strategy_exact_above_the_cap_exits_nonzero(self, tmp_path) -> None:
        sm = make_synthetic_map(seed=4, n_controls=1)
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)

        cap = default_config().solver.exact_max_controls
        controls = [Control(id=0, x=800.0, y=600.0, is_hub=True)]
        for i in range(1, cap + 5):
            controls.append(
                Control(
                    id=i,
                    x=float(100 + (i * 60) % 1400),
                    y=float(100 + (i * 37) % 1000),
                    points=5,
                )
            )
        controls_csv = tmp_path / "controls.csv"
        write_controls(controls_csv, controls)

        result = runner.invoke(
            app,
            [
                "plan",
                "--map",
                str(map_path),
                "--dpi",
                str(sm.dpi),
                "--scale",
                str(sm.scale_denominator),
                "--controls",
                str(controls_csv),
                "--strategy",
                "exact",
            ],
        )
        assert result.exit_code != 0
        assert "exact_max_controls" in result.stdout

    def test_no_reachable_route_exits_nonzero(self, tmp_path) -> None:
        sm = make_synthetic_map(seed=5, n_controls=6)
        map_path = tmp_path / "map.png"
        _write_png(map_path, sm.image)

        result = runner.invoke(
            app,
            [
                "plan",
                "--map",
                str(map_path),
                "--dpi",
                str(sm.dpi),
                "--scale",
                str(sm.scale_denominator),
                "--limit",
                "1s",
                "--penalty-per-min",
                "1000000",
                "--heuristic-time-budget",
                "0.5",
            ],
        )
        assert result.exit_code != 0
        assert "no reachable route" in result.stdout


class TestServe:
    def test_is_a_documented_stub_that_exits_nonzero(self) -> None:
        result = runner.invoke(app, ["serve"])
        assert result.exit_code != 0
        assert "T060" in result.stdout


@pytest.mark.parametrize(
    "command",
    [
        ["corpus", "list", "--help"],
        ["corpus", "check", "--help"],
        ["bench", "--help"],
        ["segment", "--help"],
        ["detect", "--help"],
        ["plan", "--help"],
        ["serve", "--help"],
    ],
)
def test_help_is_available_for_every_command(command: list[str]) -> None:
    assert runner.invoke(app, command).exit_code == 0
