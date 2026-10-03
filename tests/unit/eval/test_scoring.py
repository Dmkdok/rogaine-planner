"""The pure scorers behind `rogaine evaluate` (T118, F25): exact counts on hand-built input."""

from __future__ import annotations

import numpy as np

from rogaine.config import default_config
from rogaine.eval.evaluate import (
    Metrics,
    count_crossings,
    match_circles,
    score_class_probes,
    score_controls,
    segments_intersect,
    with_vlm,
)
from rogaine.eval.truth import ClassProbe, Truth, TruthControl, TruthPoint
from rogaine.models import Control, TerrainClass, terrain_label

R = 20.0


def _det(i: int, x: float, y: float, number: int | None, hub: bool = False) -> Control:
    return Control(id=i, x=x, y=y, number=number, is_hub=hub)


TRUTH = Truth(
    hub=TruthPoint(x=5.0, y=5.0),
    controls=(
        TruthControl(number=31, x=100.0, y=100.0),
        TruthControl(number=42, x=200.0, y=100.0),
        TruthControl(number=53, x=300.0, y=100.0),
        TruthControl(number=64, x=400.0, y=100.0),
    ),
)


def test_perfect_detection_scores_exactly_one() -> None:
    det = [_det(0, 5, 5, None, hub=True)] + [
        _det(i + 1, c.x, c.y, c.number) for i, c in enumerate(TRUTH.controls)
    ]
    m = score_controls(det, TRUTH, R)
    assert (m.recall, m.precision) == (1.0, 1.0)
    assert (m.numbers_correct, m.numbers_wrong, m.numbers_unread) == (4, 0, 0)
    assert (m.hub_truth, m.hub_found) == (1, 1)


def test_miss_false_positive_wrong_and_unread_are_counted() -> None:
    det = [
        _det(1, 103, 100, 31),  # within 0.5 R = 10 px, correct
        _det(2, 200, 108, 99),  # wrong number
        _det(3, 300, 100, None),  # unread
        _det(4, 400, 125, 64),  # 25 px off -> no match (a miss plus a false positive)
        _det(5, 700, 700, 7),  # false positive
    ]
    m = score_controls(det, TRUTH, R)
    assert (m.matched_circles, m.truth_circles, m.detected_circles) == (3, 4, 5)
    assert (m.numbers_correct, m.numbers_wrong, m.numbers_unread) == (1, 1, 1)
    assert m.recall == 0.75 and m.precision == 0.6
    assert m.hub_found == 0


def test_matching_is_one_to_one_nearest_first() -> None:
    truth = (TruthControl(number=1, x=100, y=100),)
    pairs = match_circles([_det(1, 104, 100, 1), _det(2, 101, 100, 2)], truth, R)
    assert [d.id for d, _ in pairs] == [2]


def test_class_probes_use_families() -> None:
    labels = np.full((10, 10), terrain_label(TerrainClass.FOREST_RUNNABLE), dtype=np.uint8)
    labels[2, 3] = terrain_label(TerrainClass.VEHICLE_TRACK)
    probes = (
        ClassProbe(x=3, y=2, expected="linear"),  # track is in 'linear'
        ClassProbe(x=3, y=2, expected="road"),  # ...but not in 'road'
        ClassProbe(x=0, y=0, expected="forest"),
        ClassProbe(x=50, y=0, expected="forest"),  # off the raster -> wrong
    )
    assert score_class_probes(labels, probes) == (2, 4)


def test_segment_intersection() -> None:
    assert segments_intersect((0, 0), (10, 10), (0, 10), (10, 0))
    assert not segments_intersect((0, 0), (4, 4), (0, 10), (10, 0))
    assert segments_intersect((0, 0), (10, 0), (5, 0), (5, 5))  # touching counts
    assert segments_intersect((0, 0), (10, 0), (5, 0), (15, 0))  # collinear overlap


def test_count_crossings() -> None:
    barrier = ((50.0, 0.0), (50.0, 100.0))
    assert count_crossings([(0, 50), (100, 50)], barrier) == 1
    assert count_crossings([(0, 50), (40, 50), (40, 200), (60, 200), (60, 50)], barrier) == 0
    assert count_crossings([(0, 10), (100, 10), (0, 20)], barrier) == 2


def test_metrics_add_sums_counts() -> None:
    a, b = Metrics(truth_circles=2, matched_circles=1), Metrics(truth_circles=2, matched_circles=2)
    t = a + b
    assert (t.truth_circles, t.matched_circles, t.recall) == (4, 3, 0.75)
    assert Metrics().recall is None


def test_with_vlm_toggles_only_the_fallback() -> None:
    base = default_config()
    assert with_vlm(base, "off").ocr_fallback.enabled is False
    on = with_vlm(base, "auto")
    assert on.ocr_fallback.enabled is True
    assert on.detector == base.detector
