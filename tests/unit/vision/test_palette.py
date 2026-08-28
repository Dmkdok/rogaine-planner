"""ISOM palette classifier (T013): CIELAB nearest-colour with a distance threshold.

DoD (F4): per-class IoU at least 0.95 for area classes on the fixture, 0.80 for linear classes;
``unknown`` filled by neighbourhood majority; a 4000x3000 map classifies in under 30 s on CPU.

Two scoping decisions carried over from ``rogaine.vision.palette``'s own module docstring — read
that first if either of the following looks like an omission:

* ``road``/``vehicle_track``/``footpath`` share one printed shade (``black_100``); colour cannot
  separate them (T014 does, geometrically), so the linear-class IoU here is measured as the union
  of the three against the SPEC F4 0.80 bar, not three separate numbers.
* ``contour`` and ``out_of_bounds`` are excluded from the 0.95 area-class bar for reasons specific
  to how the fixture encodes their ground truth (overprint for the former, an unfilled hatch for the
  latter) — see the module docstring. Both are still measured and reported, just not asserted.
"""

from __future__ import annotations

import time

import numpy as np
import pytest
from skimage.color import lab2rgb, rgb2lab

from rogaine.config import default_config
from rogaine.models import TerrainClass, terrain_label
from rogaine.vision.normalize import normalize
from rogaine.vision.palette import classify_labels, classify_palette, fill_unknown, shade_to_terrain

# The 11 ISOM area classes with a unique shade — identical to test_normalize.py's `_AREA_CLASSES`,
# on purpose: it is the same "on the fixture" bar, so it should be the same list.
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
LINEAR_CLASSES: tuple[TerrainClass, ...] = (
    TerrainClass.ROAD,
    TerrainClass.VEHICLE_TRACK,
    TerrainClass.FOOTPATH,
)


def _iou(pred_mask: np.ndarray, truth_mask: np.ndarray) -> float:
    union = pred_mask | truth_mask
    if not union.any():
        return 1.0  # neither predicted nor present: vacuously agree, never asserted on its own
    return float((pred_mask & truth_mask).sum()) / float(union.sum())


class TestShadeToTerrain:
    """The shared-shade design decision (module docstring, point 1)."""

    def test_the_shared_black_shade_resolves_to_road(self) -> None:
        mapping = shade_to_terrain(default_config())
        assert mapping["black_100"] is TerrainClass.ROAD

    def test_every_configured_shade_maps_to_the_class_that_declares_it(self) -> None:
        cfg = default_config()
        mapping = shade_to_terrain(cfg)
        for cls in (*AREA_CLASSES, TerrainClass.OUT_OF_BOUNDS, TerrainClass.CONTOUR):
            shade = cfg.terrain_of(cls).shade
            assert mapping[shade] is cls

    def test_unknown_is_never_a_value(self) -> None:
        mapping = shade_to_terrain(default_config())
        assert TerrainClass.UNKNOWN not in mapping.values()


class TestClassifyLabelsRoundTrip:
    """A pixel painted exactly the classifier's own shade classifies as that shade's class."""

    @pytest.mark.parametrize(
        "cls",
        [*AREA_CLASSES, *LINEAR_CLASSES, TerrainClass.OUT_OF_BOUNDS, TerrainClass.CONTOUR],
    )
    def test_exact_shade_colour_round_trips(self, cls: TerrainClass) -> None:
        cfg = default_config()
        mapping = shade_to_terrain(cfg)
        shade = cfg.terrain_of(cls).shade
        expected = mapping[shade]  # for the shared shade this is `road`, not `cls` itself
        srgb = cfg.palette.srgb_of(shade)
        image = np.full((8, 8, 3), srgb, dtype=np.uint8)

        labels = classify_labels(image, cfg)

        assert (labels == terrain_label(expected)).all()

    def test_white_shade_round_trips_to_forest_runnable(self) -> None:
        # `forest_runnable` is the only class the "white" shade declares -- a separate check since
        # the parametrized case above only walks classes, and "white" is otherwise easy to conflate
        # with the `unknown` sentinel shade "none" (also rendered white but not a real shade entry).
        cfg = default_config()
        image = np.full((8, 8, 3), cfg.palette.srgb_of("white"), dtype=np.uint8)
        labels = classify_labels(image, cfg)
        assert (labels == terrain_label(TerrainClass.FOREST_RUNNABLE)).all()


class TestDistanceThreshold:
    """A colour just inside/outside `lab_distance_threshold` from every shade."""

    def test_just_inside_classifies_just_outside_is_unknown(self) -> None:
        cfg = default_config()
        threshold = cfg.palette.lab_distance_threshold
        table = cfg.palette.srgb_table()
        names = list(table.keys())
        srgb = np.array([table[n] for n in names], dtype=np.uint8)
        lab = rgb2lab(srgb.reshape(1, -1, 3)).reshape(-1, 3)

        # Pick the shade whose nearest neighbour in Lab is farthest away, so a shift of
        # `threshold +/- 3` along L stays in "closest to this shade or unknown" territory and can
        # never accidentally land closer to some other shade instead.
        dists = np.linalg.norm(lab[:, None, :] - lab[None, :, :], axis=-1)
        np.fill_diagonal(dists, np.inf)
        nearest_neighbour = dists.min(axis=1)
        pick = int(np.argmax(nearest_neighbour))
        margin = 3.0
        assert nearest_neighbour[pick] > threshold + margin, (
            "fixture precondition: every configured shade has a neighbour closer than "
            f"threshold+{margin}; the isolation this test relies on no longer holds"
        )
        l0, a0, b0 = lab[pick]

        def _pixel(delta_l: float) -> np.ndarray:
            lab_pixel = np.array([[[l0 + delta_l, a0, b0]]], dtype=np.float64)
            rgb = np.clip(lab2rgb(lab_pixel) * 255.0, 0, 255).astype(np.uint8)
            return np.full((4, 4, 3), rgb[0, 0], dtype=np.uint8)

        expected_cls = shade_to_terrain(cfg)[names[pick]]

        inside = classify_labels(_pixel(threshold - margin), cfg)
        outside = classify_labels(_pixel(threshold + margin), cfg)

        assert (inside == terrain_label(expected_cls)).all()
        assert (outside == terrain_label(TerrainClass.UNKNOWN)).all()


class TestFillUnknown:
    """`unknown` fill: neighbourhood majority over already-classified labels, repeated to a fixed
    point so a region wider than `2 * radius` still fills completely (see palette.py docstring)."""

    def test_a_patch_of_unknown_surrounded_by_one_class_fills_to_that_class(self) -> None:
        labels = np.full((40, 40), terrain_label(TerrainClass.OPEN_LAND), dtype=np.uint8)
        labels[15:25, 15:25] = terrain_label(TerrainClass.UNKNOWN)

        filled = fill_unknown(labels, radius=3)

        assert (filled == terrain_label(TerrainClass.OPEN_LAND)).all()

    def test_only_unknown_pixels_are_overwritten(self) -> None:
        labels = np.full((30, 30), terrain_label(TerrainClass.OPEN_LAND), dtype=np.uint8)
        labels[10:20, 10:20] = terrain_label(TerrainClass.WATER_UNCROSSABLE)
        labels[12:14, 12:14] = terrain_label(TerrainClass.UNKNOWN)
        original = labels.copy()

        filled = fill_unknown(labels, radius=2)

        # every pixel that was not `unknown` keeps its original label exactly
        untouched = original != terrain_label(TerrainClass.UNKNOWN)
        assert (filled[untouched] == original[untouched]).all()

    def test_unknown_patch_touching_the_border_does_not_crash(self) -> None:
        labels = np.full((20, 20), terrain_label(TerrainClass.MARSH), dtype=np.uint8)
        labels[0:5, 0:5] = terrain_label(TerrainClass.UNKNOWN)  # top-left corner

        filled = fill_unknown(labels, radius=3)

        assert (filled == terrain_label(TerrainClass.MARSH)).all()

    def test_a_fully_unknown_image_stays_unknown(self) -> None:
        labels = np.full((10, 10), terrain_label(TerrainClass.UNKNOWN), dtype=np.uint8)

        filled = fill_unknown(labels, radius=3)

        assert (filled == terrain_label(TerrainClass.UNKNOWN)).all()

    def test_radius_zero_is_a_no_op(self) -> None:
        labels = np.full((10, 10), terrain_label(TerrainClass.OPEN_LAND), dtype=np.uint8)
        labels[3:6, 3:6] = terrain_label(TerrainClass.UNKNOWN)

        filled = fill_unknown(labels, radius=0)

        assert np.array_equal(filled, labels)


class TestPaletteIoUAgainstFixture:
    """SPEC F4's per-class IoU bar, measured on ``tests/fixtures/synth_map.py``.

    ``contour_mask`` pixels are excluded from every measurement here — the same
    ``sampleable = ~contour_mask`` convention ``test_normalize.py`` uses — because the fixture's
    ground truth for a contour-overprinted pixel is the terrain *underneath*, while a colour
    classifier correctly reports the contour ink actually printed there. See the module docstring.
    """

    def test_area_classes_on_the_clean_render(self, clean_synthetic_map) -> None:
        # The clean render isolates T013's own algorithm from T012's residual normalisation error
        # (that pairing is `TestPaletteIoUAgainstFixture.test_area_classes_after_normalize` below).
        cfg = default_config()
        labels = clean_synthetic_map.labels
        # Also excludes `out_of_bounds` truth pixels: the fixture only hatches that area rather
        # than filling it (module docstring), so a correctly-classified underlying colour there is
        # not counted as contamination of the class it visually matches. And `noise_mask` (T014,
        # F5): black map-text/point-symbol overprint classifies as `road`, same reasoning as
        # `contour_mask` -- it is not the area class underneath, so it is not sampled as one.
        oob_lbl = terrain_label(TerrainClass.OUT_OF_BOUNDS)
        sampleable = (
            ~clean_synthetic_map.contour_mask
            & (labels != oob_lbl)
            & ~clean_synthetic_map.noise_mask
        )
        predicted = classify_palette(clean_synthetic_map.image, cfg)

        ious: dict[TerrainClass, float] = {}
        for cls in AREA_CLASSES:
            lbl = terrain_label(cls)
            truth_mask = (labels == lbl) & sampleable
            assert truth_mask.sum() > 500, f"fixture placed too little {cls} to measure IoU"
            pred_mask = (predicted == lbl) & sampleable
            ious[cls] = _iou(pred_mask, truth_mask)

        report = ", ".join(f"{cls.value}={iou:.4f}" for cls, iou in ious.items())
        assert min(ious.values()) >= 0.95, f"area-class IoU below 0.95: {report}"

    def test_linear_union_on_the_clean_render(self, clean_synthetic_map) -> None:
        cfg = default_config()
        labels = clean_synthetic_map.labels
        # See `test_area_classes_on_the_clean_render` above for why `out_of_bounds` and `noise_mask`
        # are excluded too.
        oob_lbl = terrain_label(TerrainClass.OUT_OF_BOUNDS)
        sampleable = (
            ~clean_synthetic_map.contour_mask
            & (labels != oob_lbl)
            & ~clean_synthetic_map.noise_mask
        )
        predicted = classify_palette(clean_synthetic_map.image, cfg)

        linear_labels = {terrain_label(c) for c in LINEAR_CLASSES}
        truth_mask = np.isin(labels, list(linear_labels)) & sampleable
        pred_mask = np.isin(predicted, list(linear_labels)) & sampleable
        assert truth_mask.sum() > 500, "fixture placed too little linear track to measure IoU"

        iou = _iou(pred_mask, truth_mask)
        assert iou >= 0.80, f"linear-class (union) IoU below 0.80: {iou:.4f}"

    def test_area_classes_after_normalize_on_the_degraded_render(self, synthetic_map) -> None:
        """The realistic pipeline: degraded scan -> `normalize()` -> `classify_palette()`.

        Reported, not gated at the same 0.95 as the clean-render test above: this map carries a
        colour cast, vignette, sensor noise and a JPEG round-trip (`make_synthetic_map`'s
        ``degrade=True`` default), and `normalize()` (T012) is not required to undo that perfectly
        -- `lab_distance_threshold` exists to absorb what it leaves behind. A regression guard
        against this getting *worse*, not the strict F4 acceptance number (that is
        ``test_area_classes_on_the_clean_render``, above).
        """
        cfg = default_config()
        labels = synthetic_map.labels
        # See `test_area_classes_on_the_clean_render` above for why `out_of_bounds` and `noise_mask`
        # are excluded too.
        oob_lbl = terrain_label(TerrainClass.OUT_OF_BOUNDS)
        sampleable = (
            ~synthetic_map.contour_mask & (labels != oob_lbl) & ~synthetic_map.noise_mask
        )
        normalized = normalize(synthetic_map.image)
        predicted = classify_palette(normalized, cfg)

        ious: dict[TerrainClass, float] = {}
        for cls in AREA_CLASSES:
            lbl = terrain_label(cls)
            truth_mask = (labels == lbl) & sampleable
            pred_mask = (predicted == lbl) & sampleable
            ious[cls] = _iou(pred_mask, truth_mask)

        report = ", ".join(f"{cls.value}={iou:.4f}" for cls, iou in ious.items())
        # Mean, not min: `water_shallow` and `paved_area` are small enough on this fixture (a few
        # hundred to a couple of thousand pixels) that JPEG blockiness alone swings their individual
        # IoU by a large fraction from one seed to the next -- a `min` bound is really a bound on
        # whichever rare class the degradation happened to hit hardest, not on the classifier. The
        # mean still catches a genuine collapse: the pre-fix regression this guards against (two
        # classes pinned at ~0.0 IoU from a green-tier palette bug) failed this same 0.60 bound even
        # averaged across all eleven classes.
        mean_iou = sum(ious.values()) / len(ious)
        assert mean_iou >= 0.60, f"mean area-class IoU collapsed on the degraded render: {report}"

    def test_out_of_bounds_and_contour_are_measured_not_gated(self, clean_synthetic_map) -> None:
        """Diagnostic only -- see the module docstring for why neither is scored against 0.95."""
        cfg = default_config()
        labels = clean_synthetic_map.labels
        sampleable = ~clean_synthetic_map.contour_mask
        predicted = classify_palette(clean_synthetic_map.image, cfg)

        oob_lbl = terrain_label(TerrainClass.OUT_OF_BOUNDS)
        oob_truth = (labels == oob_lbl) & sampleable
        oob_pred = (predicted == oob_lbl) & sampleable
        oob_iou = _iou(oob_pred, oob_truth)

        # `contour` has no ground-truth pixels in `labels` at all (see module docstring) -- IoU
        # against `labels` is meaningless, so this checks the thing that *is* meaningful: every
        # pixel actually painted with contour ink is reachable from `contour_mask`, and enough of
        # it classifies as `contour` to show the palette table entry itself works.
        contour_lbl = terrain_label(TerrainClass.CONTOUR)
        contour_recall = float(
            (predicted[clean_synthetic_map.contour_mask] == contour_lbl).mean()
        )

        # No floor asserted on either -- see module docstring. Structural sanity only: both are
        # real numbers in [0, 1], not NaN/empty from a broken mask.
        assert 0.0 <= oob_iou <= 1.0
        assert 0.0 <= contour_recall <= 1.0


@pytest.mark.perf
class TestPerformance:
    """SPEC F4's non-functional budget: a 4000x3000 map classifies in under 30 s on CPU."""

    def test_full_size_preset_under_30_seconds(self, full_size_synthetic_map) -> None:
        cfg = default_config()
        image = full_size_synthetic_map.image

        start = time.perf_counter()
        classify_palette(image, cfg)
        elapsed = time.perf_counter() - start

        assert elapsed < 30.0, f"classify_palette took {elapsed:.1f}s on a 4000x3000 image"
