"""Segmentation orchestration, `terrain.npz` round-trip, and per-class IoU (T016).

DoD: `segment()` produces a `TerrainMap`; `terrain.npz` round-trips; `iou_report` is printed per
class (this module tests the string-returning `format_iou_report`, not a live `print()`).
"""

from __future__ import annotations

import numpy as np
import pytest

from rogaine.config import default_config
from rogaine.models import TERRAIN_ORDER, TerrainClass, TerrainMap, terrain_label
from rogaine.vision.segment import (
    format_iou_report,
    iou_report,
    load_terrain_map,
    save_terrain_map,
    segment,
)

# Same list, same reason as `test_palette.py`'s `AREA_CLASSES`: the 11 ISOM area classes with a
# unique shade -- the ones a colour classifier alone should nail on the clean fixture render.
AREA_CLASSES: tuple[TerrainClass, ...] = (
    TerrainClass.OPEN_LAND,
    TerrainClass.ROUGH_OPEN,
    TerrainClass.FOREST_RUNNABLE,
    TerrainClass.VEG_SLOW_RUN,
    TerrainClass.VEG_WALK,
    TerrainClass.VEG_FIGHT,
    TerrainClass.MARSH,
    TerrainClass.WATER_SHALLOW,
    TerrainClass.WATER_UNCROSSABLE,
    TerrainClass.BARE_ROCK,
    TerrainClass.PAVED_AREA,
)


class TestSegmentEndToEnd:
    def test_produces_a_valid_terrain_map(self, clean_synthetic_map) -> None:
        sm = clean_synthetic_map
        cfg = default_config()

        terrain_map = segment(sm.image, sm.dpi, sm.meters_per_pixel, cfg)

        assert isinstance(terrain_map, TerrainMap)
        assert terrain_map.shape == sm.shape
        assert terrain_map.labels.dtype == np.uint8
        assert terrain_map.labels.max() < len(TERRAIN_ORDER)
        assert terrain_map.contour_density.dtype == np.float32
        assert terrain_map.contour_density.shape == terrain_map.labels.shape
        assert terrain_map.contour_density.min() >= 0.0
        assert terrain_map.contour_density.max() <= 1.0
        assert terrain_map.meters_per_pixel == sm.meters_per_pixel


class TestSegmentInputValidation:
    def test_rejects_non_positive_dpi(self) -> None:
        image = np.zeros((10, 10, 3), dtype=np.uint8)
        with pytest.raises(ValueError, match="dpi"):
            segment(image, 0.0, 2.5)


class TestIouReportOnFixture:
    """`iou_report` measured on the same fixture and with the same sampleable exclusions
    `test_palette.py`'s `TestPaletteIoUAgainstFixture` and `test_linear.py`'s
    `TestSubClassAccuracyOnFixture` already establish: contour overprint, black text/point-symbol
    noise, and out-of-bounds hatching are excluded from every class's sampled pixels.

    Measured on the *degraded* fixture (`synthetic_map`, not `clean_synthetic_map`), on purpose:
    `segment()` always runs `normalize()` (module docstring), and `test_normalize.py`'s own
    `TestNormalizeRecoversTheCleanRender` docstring records that grey-world white balance run on
    an already-clean, zero-tint render makes area classes match the classifier's true CMYK
    palette *worse*, not better -- confirmed here too (measured min area-class IoU on the clean
    render via `segment()`: 0.16, well under `test_palette.py`'s 0.95, which is measured
    *without* `normalize()` in the loop). The degraded render is the realistic case `segment()`
    exists for, and is the same fixture/floor style `test_palette.py`'s own
    `test_area_classes_after_normalize_on_the_degraded_render` already uses for a
    normalize+classify pipeline: a mean, not a per-class min (that test's own reasoning: a couple
    of small-area classes swing a lot on JPEG blockiness alone, so a `min` bound really bounds
    whichever class the degradation hit hardest, not the pipeline). Floor set to that same 0.60,
    not a fresh number -- same fixture, same normalize+classify composition for the area classes
    (measured here: 0.63).
    """

    def test_area_class_mean_iou_floor_on_the_degraded_render(self, synthetic_map) -> None:
        sm = synthetic_map
        cfg = default_config()
        oob_lbl = terrain_label(TerrainClass.OUT_OF_BOUNDS)
        sampleable = ~sm.contour_mask & (sm.labels != oob_lbl) & ~sm.noise_mask

        terrain_map = segment(sm.image, sm.dpi, sm.meters_per_pixel, cfg)
        report = iou_report(terrain_map.labels, sm.labels, sampleable=sampleable)

        area_ious = [report[cls] for cls in AREA_CLASSES]
        mean_iou = sum(area_ious) / len(area_ious)
        formatted = format_iou_report(report)
        assert mean_iou >= 0.60, f"mean area-class IoU below floor:\n{formatted}"


class TestTerrainNpzRoundTrip:
    def test_labels_density_and_scale_survive_exactly(self, tmp_path) -> None:
        rng = np.random.default_rng(0)
        labels = rng.integers(0, len(TERRAIN_ORDER), size=(37, 53), dtype=np.uint8)
        density = rng.random((37, 53)).astype(np.float32)
        terrain_map = TerrainMap(labels=labels, contour_density=density, meters_per_pixel=2.54321)

        path = tmp_path / "terrain.npz"
        save_terrain_map(path, terrain_map)
        loaded = load_terrain_map(path)

        assert np.array_equal(loaded.labels, terrain_map.labels)
        assert loaded.labels.dtype == np.uint8
        assert np.array_equal(loaded.contour_density, terrain_map.contour_density)
        assert loaded.contour_density.dtype == np.float32
        assert loaded.meters_per_pixel == terrain_map.meters_per_pixel
        assert isinstance(loaded.meters_per_pixel, float)


class TestIouReport:
    def test_perfect_match_scores_one_for_every_class(self) -> None:
        labels = np.array([[0, 1], [2, 3]], dtype=np.uint8)
        report = iou_report(labels, labels)
        assert set(report.keys()) == set(TERRAIN_ORDER)
        assert all(v == 1.0 for v in report.values())

    def test_disjoint_prediction_and_truth_scores_zero_only_for_the_involved_classes(self) -> None:
        pred = np.full((4, 4), terrain_label(TerrainClass.OPEN_LAND), dtype=np.uint8)
        truth = np.full((4, 4), terrain_label(TerrainClass.WATER_SHALLOW), dtype=np.uint8)

        report = iou_report(pred, truth)

        assert report[TerrainClass.OPEN_LAND] == 0.0
        assert report[TerrainClass.WATER_SHALLOW] == 0.0
        assert report[TerrainClass.MARSH] == 1.0  # absent from both: vacuous agreement

    def test_sampleable_mask_excludes_pixels_from_every_class(self) -> None:
        pred = np.full((4, 4), terrain_label(TerrainClass.OPEN_LAND), dtype=np.uint8)
        truth = pred.copy()
        truth[0, 0] = terrain_label(TerrainClass.MARSH)  # a disagreement...
        sampleable = np.ones((4, 4), dtype=bool)
        sampleable[0, 0] = False  # ...excluded from sampling

        report = iou_report(pred, truth, sampleable=sampleable)

        assert report[TerrainClass.OPEN_LAND] == 1.0
        assert report[TerrainClass.MARSH] == 1.0  # no sampled pixel is MARSH in either raster

    def test_rejects_mismatched_shapes(self) -> None:
        with pytest.raises(ValueError, match="shape"):
            iou_report(np.zeros((4, 4), dtype=np.uint8), np.zeros((5, 5), dtype=np.uint8))


class TestFormatIouReport:
    def test_one_line_per_class_with_four_decimal_places(self) -> None:
        report = {TerrainClass.OPEN_LAND: 0.98, TerrainClass.MARSH: 1.0}
        assert format_iou_report(report).splitlines() == ["open_land: 0.9800", "marsh: 1.0000"]
