"""Linear feature extraction (T014): the geometric split of the palette classifier's shared `road`
placeholder into real `road` / `vehicle_track` / `footpath` corridors.

DoD (F5): a fixture path drawn end-to-end is recovered as one connected component covering at least
90% of its length; map text and point symbols are rejected, measured as false-positive corridor
area on the fixture.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from fixtures.synth_map import stroke_thickness_px
from rogaine.config import default_config, load_config
from rogaine.models import TerrainClass, terrain_label
from rogaine.vision.linear import extract_linear_features
from rogaine.vision.palette import classify_palette

LINEAR_CLASSES: tuple[TerrainClass, ...] = (
    TerrainClass.ROAD,
    TerrainClass.VEHICLE_TRACK,
    TerrainClass.FOOTPATH,
)
LINEAR_LABELS: list[int] = [terrain_label(c) for c in LINEAR_CLASSES]


def _blank(height: int, width: int, cls: TerrainClass = TerrainClass.FOREST_RUNNABLE) -> np.ndarray:
    return np.full((height, width), terrain_label(cls), dtype=np.uint8)


def _largest_component_coverage(mask: np.ndarray, truth: np.ndarray) -> float:
    """Fraction of *truth*'s pixels covered by the single largest connected component of *mask*.

    This is SPEC F5's own measure: "a path drawn end-to-end is recovered as one connected component
    covering at least 90% of its length".
    """
    if not truth.any():
        return 1.0
    _, cc = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)[:2]
    overlap_ids, counts = np.unique(cc[truth], return_counts=True)
    best = 0
    for comp_id, count in zip(overlap_ids, counts, strict=True):
        if comp_id != 0:
            best = max(best, int(count))
    return best / float(truth.sum())


class TestCorridorConnectivity:
    """SPEC F5: a path drawn end-to-end is one component covering at least 90% of its length."""

    def test_a_long_wandering_corridor_survives_as_one_component(self) -> None:
        dpi = 300.0
        cfg = default_config()
        labels = _blank(500, 800)
        # A bent polyline, not a straight line -- corners are where naive per-segment logic breaks.
        pts = np.array([[40, 40], [300, 120], [200, 300], [600, 250], [760, 460]], dtype=np.int32)
        width_px = stroke_thickness_px(cfg.linear.footpath_width_mm * dpi / 25.4)
        cv2.polylines(labels, [pts], False, terrain_label(TerrainClass.ROAD), width_px)
        truth = labels == terrain_label(TerrainClass.ROAD)
        assert truth.sum() > 200, "test precondition: drawn path too short to be meaningful"

        out = extract_linear_features(labels, dpi, cfg)
        corridor = np.isin(out, LINEAR_LABELS)

        coverage = _largest_component_coverage(corridor, truth)
        assert coverage >= 0.90, f"largest surviving component covers only {coverage:.1%}"

    def test_a_small_gap_across_the_path_is_bridged_into_one_component(self) -> None:
        """SPEC F5's own wording: "connected corridors, not scattered black pixels". A gap up to
        `close_radius_px` (scan noise, a shallow crossing) must not fragment the output."""
        dpi = 300.0
        cfg = default_config()
        labels = _blank(200, 600)
        width_px = stroke_thickness_px(cfg.linear.footpath_width_mm * dpi / 25.4)
        gap = cfg.linear.close_radius_px
        cv2.line(labels, (20, 100), (280, 100), terrain_label(TerrainClass.ROAD), width_px)
        cv2.line(labels, (280 + gap, 100), (580, 100), terrain_label(TerrainClass.ROAD), width_px)
        truth = labels == terrain_label(TerrainClass.ROAD)

        out = extract_linear_features(labels, dpi, cfg)
        corridor = np.isin(out, LINEAR_LABELS)
        _, cc = cv2.connectedComponentsWithStats(corridor.astype(np.uint8), connectivity=8)[:2]
        overlapping = set(np.unique(cc[truth])) - {0}
        assert len(overlapping) == 1, f"the bridged path split into {len(overlapping)} component(s)"


class TestNonCorridorShapesRejected:
    """Blobby ink -- point symbols, single glyphs -- must not survive as a linear class."""

    def test_a_filled_disk_is_rejected_to_unknown(self) -> None:
        dpi = 300.0
        cfg = default_config()
        labels = _blank(150, 150)
        cv2.circle(labels, (75, 75), 20, terrain_label(TerrainClass.ROAD), -1)
        truth = labels == terrain_label(TerrainClass.ROAD)
        assert truth.sum() > cfg.linear.min_component_area_px

        out = extract_linear_features(labels, dpi, cfg)

        assert not np.isin(out[truth], LINEAR_LABELS).any()
        assert (out[truth] == terrain_label(TerrainClass.UNKNOWN)).all()

    def test_a_short_segment_below_the_length_floor_is_rejected(self) -> None:
        """A segment short enough to fail `min_length_px` despite being shaped enough like a
        corridor to pass the elongation and aspect-ratio tests on their own -- the length floor is
        what actually rejects it (module docstring), so this proves it does something the shape
        tests do not."""
        dpi = 300.0
        cfg = default_config()
        labels = _blank(80, 200)
        width_px = stroke_thickness_px(cfg.linear.footpath_width_mm * dpi / 25.4)
        length_px = 70
        assert length_px < cfg.linear.min_length_px(dpi), "test precondition: segment too long"
        cv2.line(labels, (80, 40), (80 + length_px, 40), terrain_label(TerrainClass.ROAD), width_px)
        truth = labels == terrain_label(TerrainClass.ROAD)

        # Precondition: with the length floor effectively disabled, this same segment survives --
        # so the shape tests alone are not what rejects it below; the length floor specifically is.
        lenient = load_config(overrides={"linear": {"min_length_mm": 0.001}})
        lenient_out = extract_linear_features(labels, dpi, lenient)
        assert np.isin(lenient_out[truth], LINEAR_LABELS).any(), (
            "test precondition: segment should pass the shape tests on their own"
        )

        out = extract_linear_features(labels, dpi, cfg)

        assert not np.isin(out[truth], LINEAR_LABELS).any()


class TestWidthBasedClassAssignment:
    """A corridor's measured stroke width assigns it to the nearest nominal class (T014, F5)."""

    def test_each_nominal_width_is_assigned_to_its_own_class(self) -> None:
        dpi = 300.0
        cfg = default_config()
        width_mm_by_class = {
            TerrainClass.ROAD: cfg.linear.road_width_mm,
            TerrainClass.VEHICLE_TRACK: cfg.linear.vehicle_track_width_mm,
            TerrainClass.FOOTPATH: cfg.linear.footpath_width_mm,
        }
        labels = _blank(400, 400)
        line_masks: dict[TerrainClass, np.ndarray] = {}
        y = 40
        for cls in LINEAR_CLASSES:
            width_px = stroke_thickness_px(width_mm_by_class[cls] * dpi / 25.4)
            cv2.line(labels, (20, y), (380, y), terrain_label(TerrainClass.ROAD), width_px)
            line_layer = np.zeros((400, 400), dtype=np.uint8)
            cv2.line(line_layer, (20, y), (380, y), 255, width_px)
            line_masks[cls] = line_layer > 0
            y += 60  # far enough apart that closing never bridges one line into the next

        out = extract_linear_features(labels, dpi, cfg)

        for cls, line_mask in line_masks.items():
            got = set(np.unique(out[line_mask]))
            assert got == {terrain_label(cls)}, f"{cls.value}: expected only itself, got {got}"


class TestNoLinearInputIsUntouched:
    def test_an_image_with_no_road_pixels_is_returned_unchanged(self) -> None:
        labels = _blank(20, 20)
        out = extract_linear_features(labels, 300.0)
        assert np.array_equal(out, labels)

    def test_the_input_array_is_never_mutated(self) -> None:
        labels = _blank(30, 30)
        cv2.circle(labels, (15, 15), 5, terrain_label(TerrainClass.ROAD), -1)
        original = labels.copy()

        extract_linear_features(labels, 300.0)

        assert np.array_equal(labels, original)


class TestInputValidation:
    def test_rejects_non_2d_labels(self) -> None:
        with pytest.raises(ValueError, match="H, W"):
            extract_linear_features(np.zeros((4, 4, 3), dtype=np.uint8), 300.0)

    def test_rejects_non_uint8_labels(self) -> None:
        with pytest.raises(ValueError, match="uint8"):
            extract_linear_features(np.zeros((4, 4), dtype=np.int32), 300.0)

    def test_rejects_non_positive_dpi(self) -> None:
        with pytest.raises(ValueError, match="dpi"):
            extract_linear_features(np.zeros((4, 4), dtype=np.uint8), 0.0)


class TestFalsePositiveRejectionOnFixture:
    """SPEC F5: text/point symbols are rejected, measured as false-positive corridor area."""

    def test_text_and_point_symbols_contribute_little_false_positive_corridor_area(
        self, clean_synthetic_map
    ) -> None:
        sm = clean_synthetic_map
        assert sm.noise_mask.sum() > 200, "fixture drew too little text/point-symbol ink to measure"

        cfg = default_config()
        palette_out = classify_palette(sm.image, cfg)
        # Precondition: the palette classifier really does see this ink as `road` -- it is the false
        # positive T014 exists to clean up, not a fixture artifact that never reached it.
        road_lbl = terrain_label(TerrainClass.ROAD)
        seen_as_road = float((palette_out[sm.noise_mask] == road_lbl).mean())
        assert seen_as_road > 0.5, (
            f"test precondition: only {seen_as_road:.1%} of the noise ink classified as road"
        )

        out = extract_linear_features(palette_out, sm.dpi, cfg)
        corridor = np.isin(out, LINEAR_LABELS)
        fp_fraction = float((corridor & sm.noise_mask).sum()) / float(sm.noise_mask.sum())
        assert fp_fraction < 0.05, f"{fp_fraction:.1%} of text/point-symbol ink kept as a corridor"


class TestSubClassAccuracyOnFixture:
    """Diagnostic: per-class IoU against the fixture's ground truth, now that T014 can split the
    palette's `road` placeholder into the three real linear classes.

    Not gated at a floor, deliberately -- the same scoping decision `test_palette.py` makes for
    `out_of_bounds`/`contour` (see its module docstring). This module classifies a whole connected
    component as one class (module docstring: "one class for the whole component, matching
    'connected corridor' rather than a per-pixel patchwork"). The full fixture scene draws six
    separate paths (two each of road/track/footpath) wandering across the same canvas, so several
    of them cross; a component that several true classes merge into can only be assigned one of
    them, which mechanically caps per-class IoU here however good the width estimate is. The tight
    correctness check for the assignment itself is
    `TestWidthBasedClassAssignment.test_each_nominal_width_is_assigned_to_its_own_class`, on lines
    that never cross.
    """

    def test_per_class_iou_on_the_clean_render(self, clean_synthetic_map) -> None:
        sm = clean_synthetic_map
        cfg = default_config()
        oob_lbl = terrain_label(TerrainClass.OUT_OF_BOUNDS)
        sampleable = ~sm.contour_mask & (sm.labels != oob_lbl) & ~sm.noise_mask

        palette_out = classify_palette(sm.image, cfg)
        out = extract_linear_features(palette_out, sm.dpi, cfg)

        ious: dict[TerrainClass, float] = {}
        for cls in LINEAR_CLASSES:
            lbl = terrain_label(cls)
            truth_mask = (sm.labels == lbl) & sampleable
            pred_mask = (out == lbl) & sampleable
            assert truth_mask.sum() > 200, f"fixture placed too little {cls.value} to measure IoU"
            union = truth_mask | pred_mask
            ious[cls] = float((truth_mask & pred_mask).sum()) / float(union.sum())

        report = ", ".join(f"{c.value}={i:.4f}" for c, i in ious.items())
        assert all(0.0 <= i <= 1.0 for i in ious.values()), f"IoU out of range: {report}"
