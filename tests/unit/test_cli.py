"""The CLI surface that exists in M0 (T005). T050 extends both the app and this file."""

from __future__ import annotations

import re

import pytest
from typer.testing import CliRunner

from rogaine import __version__
from rogaine.cli import app
from rogaine.config import default_config

runner = CliRunner()


def _map_dir(root, map_id: str, meta: str):
    d = root / map_id
    d.mkdir(parents=True)
    (d / "map.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (d / "meta.toml").write_text(meta, encoding="utf-8")
    return d


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


@pytest.mark.parametrize(
    "command",
    [["corpus", "list", "--help"], ["corpus", "check", "--help"], ["bench", "--help"]],
)
def test_help_is_available_for_every_command(command: list[str]) -> None:
    assert runner.invoke(app, command).exit_code == 0
