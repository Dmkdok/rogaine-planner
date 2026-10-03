"""`rogaine evaluate` on the synthetic fixture and its generated truth (T118, F25)."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from typer.testing import CliRunner

from fixtures.synth_map import make_synthetic_map, make_truth
from rogaine.cli import app
from rogaine.config import default_config
from rogaine.eval.evaluate import (
    evaluate_map,
    load_bench_set,
    score_barrier_probes,
    score_class_probes,
)
from rogaine.eval.truth import dump_truth, load_truth
from rogaine.models import TerrainMap

runner = CliRunner()


@pytest.fixture(scope="module")
def fixture_truth(synthetic_map):
    return make_truth(synthetic_map)


def test_emitted_truth_has_every_section(synthetic_map, fixture_truth) -> None:
    assert len(fixture_truth.controls) == len(synthetic_map.controls) - 1
    assert fixture_truth.hub is not None
    assert len(fixture_truth.barrier_probes) == 1
    assert len(fixture_truth.class_probes) >= 10


def test_emitted_truth_survives_the_toml_round_trip(fixture_truth, tmp_path) -> None:
    p = tmp_path / "truth.toml"
    p.write_text(dump_truth(fixture_truth), encoding="utf-8")
    assert load_truth(p) == fixture_truth


def test_probes_are_exact_against_the_true_terrain(synthetic_map, fixture_truth) -> None:
    """With the fixture's own labels standing in for the segmenter: every class probe passes and
    the barrier probe has 0 crossings -- so any miss in the pipeline run below is the pipeline's."""
    assert score_class_probes(synthetic_map.labels, fixture_truth.class_probes) == (
        len(fixture_truth.class_probes),
        len(fixture_truth.class_probes),
    )
    terrain = TerrainMap(
        labels=synthetic_map.labels,
        contour_density=np.zeros(synthetic_map.shape, dtype=np.float32),
        meters_per_pixel=synthetic_map.meters_per_pixel,
    )
    m = score_barrier_probes(
        fixture_truth.barrier_probes, terrain, synthetic_map.meters_per_pixel, default_config()
    )
    assert (m.barrier_probes, m.barrier_unreachable, m.barrier_crossed, m.barrier_crossings) == (
        1,
        0,
        0,
        0,
    )


def test_pipeline_metrics_on_the_fixture(synthetic_map, fixture_truth) -> None:
    sm = synthetic_map
    m = evaluate_map(sm.image, sm.dpi, sm.meters_per_pixel, fixture_truth, default_config())
    n = len(fixture_truth.controls)
    # Detection is exact on the standard fixture (T020's own floor is only 0.95).
    assert (m.truth_circles, m.detected_circles, m.matched_circles) == (n, n, n)
    assert (m.recall, m.precision) == (1.0, 1.0)
    assert (m.hub_truth, m.hub_found) == (1, 1)
    # Every matched circle gets exactly one number outcome.
    assert m.numbers_correct + m.numbers_wrong + m.numbers_unread == n
    # Class accuracy is the plain fraction of probes the segmenter got right.
    assert m.class_probes == len(fixture_truth.class_probes)
    assert 0 < m.class_correct <= m.class_probes
    assert m.class_accuracy == m.class_correct / m.class_probes
    # The fixture's lake is not crossed.
    assert (m.barrier_probes, m.barrier_unreachable, m.barrier_crossed, m.barrier_crossings) == (
        1,
        0,
        0,
        0,
    )


def _write_png(path: Path, rgb: np.ndarray) -> None:
    ok, buf = cv2.imencode(".png", rgb[:, :, ::-1])
    assert ok
    path.write_bytes(buf.tobytes())


def _bench_dir(root: Path, sm, truth, with_truth: bool = True) -> Path:
    d = root / "maps" / "synth"
    d.mkdir(parents=True)
    _write_png(d / "map.png", sm.image)
    (d / "meta.toml").write_text(
        f"scale_denominator = {int(sm.scale_denominator)}\ndpi = {int(sm.dpi)}\n", encoding="utf-8"
    )
    if with_truth:
        (d / "truth.toml").write_text(dump_truth(truth), encoding="utf-8")
    (root / "bench.toml").write_text('maps = ["synth"]\n', encoding="utf-8")
    return root / "bench.toml"


def test_cli_prints_per_map_and_total_rows(synthetic_map, fixture_truth, tmp_path) -> None:
    bench = _bench_dir(tmp_path, synthetic_map, fixture_truth)
    result = runner.invoke(
        app, ["evaluate", "--set", str(bench), "--vlm", "off"], env={"COLUMNS": "250"}
    )
    assert result.exit_code == 0, result.output
    out = result.output
    assert "synth" in out and "TOTAL" in out
    assert "1.000 (12/12)" in out  # recall and precision, exact on the fixture
    assert "0/1" in out  # barrier probes crossed / probes


def test_cli_reports_a_map_without_truth_and_exits_non_zero(
    synthetic_map, fixture_truth, tmp_path
) -> None:
    bench = _bench_dir(tmp_path, synthetic_map, fixture_truth, with_truth=False)
    result = runner.invoke(app, ["evaluate", "--set", str(bench)])
    assert result.exit_code == 1
    assert "skipped synth" in result.output


def test_cli_rejects_a_bad_vlm_mode(tmp_path) -> None:
    (tmp_path / "bench.toml").write_text('maps = ["a"]\n', encoding="utf-8")
    result = runner.invoke(app, ["evaluate", "--set", str(tmp_path / "bench.toml"), "--vlm", "x"])
    assert result.exit_code == 1
    assert "--vlm" in result.output


def test_bench_set_root_defaults_to_maps_next_to_the_file(tmp_path) -> None:
    p = tmp_path / "bench.toml"
    p.write_text('maps = ["a", "b"]\n', encoding="utf-8")
    assert load_bench_set(p) == (tmp_path / "maps", ("a", "b"))
    p.write_text("maps = []\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_bench_set(p)


def test_fixture_truth_is_deterministic() -> None:
    a = make_truth(make_synthetic_map(seed=5, n_controls=4))
    b = make_truth(make_synthetic_map(seed=5, n_controls=4))
    assert a == b
