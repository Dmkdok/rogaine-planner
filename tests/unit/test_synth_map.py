"""The synthetic fixture (T004). Everything M1-M4 measures is measured against this map, so its
own guarantees — determinism, exact labels, honest ground truth — are worth asserting directly.
"""

from __future__ import annotations

import numpy as np
import pytest

from fixtures.synth_map import (
    FULL_SIZE,
    RENDER_SRGB,
    SHADE_OF,
    SyntheticMap,
    make_synthetic_map,
    meters_per_pixel,
)
from rogaine.models import TERRAIN_ORDER, TerrainClass, terrain_class, terrain_label


class TestDeterminism:
    def test_the_same_seed_gives_the_same_map(self) -> None:
        a = make_synthetic_map(400, 320, seed=11, dpi=100.0, n_controls=3)
        b = make_synthetic_map(400, 320, seed=11, dpi=100.0, n_controls=3)
        assert np.array_equal(a.image, b.image)
        assert np.array_equal(a.labels, b.labels)
        assert np.array_equal(a.contour_mask, b.contour_mask)
        assert a.controls == b.controls

    def test_a_different_seed_gives_a_different_map(self) -> None:
        a = make_synthetic_map(400, 320, seed=11, dpi=100.0, n_controls=3)
        b = make_synthetic_map(400, 320, seed=12, dpi=100.0, n_controls=3)
        assert not np.array_equal(a.image, b.image)

    def test_degradation_changes_the_render_but_never_the_truth(self) -> None:
        noisy = make_synthetic_map(400, 320, seed=11, dpi=100.0, n_controls=3, degrade=True)
        clean = make_synthetic_map(400, 320, seed=11, dpi=100.0, n_controls=3, degrade=False)
        assert not np.array_equal(noisy.image, clean.image)
        assert np.array_equal(noisy.labels, clean.labels)
        assert noisy.controls == clean.controls


class TestGeometry:
    def test_meters_per_pixel_is_the_spec_formula(self) -> None:
        # SPEC F2: mpp = (25.4 / dpi) * N / 1000. 1:30000 at 300 dpi is 2.54 m per pixel.
        assert meters_per_pixel(30000, 300) == pytest.approx(2.54, abs=1e-9)
        assert meters_per_pixel(15000, 600) == pytest.approx(0.635, abs=1e-9)

    def test_the_map_reports_its_own_scale(self, synthetic_map: SyntheticMap) -> None:
        assert synthetic_map.meters_per_pixel == pytest.approx(
            meters_per_pixel(synthetic_map.scale_denominator, synthetic_map.dpi)
        )

    def test_the_standard_fixture_covers_a_real_rogaine_area(
        self, synthetic_map: SyntheticMap
    ) -> None:
        h, w = synthetic_map.shape
        km_x = w * synthetic_map.meters_per_pixel / 1000.0
        km_y = h * synthetic_map.meters_per_pixel / 1000.0
        assert (km_x, km_y) == pytest.approx((4.064, 3.048), abs=1e-3)

    def test_image_and_labels_are_the_same_raster(self, synthetic_map: SyntheticMap) -> None:
        assert synthetic_map.image.shape[:2] == synthetic_map.labels.shape
        assert synthetic_map.image.shape[2] == 3
        assert synthetic_map.image.dtype == np.uint8
        assert synthetic_map.labels.dtype == np.uint8
        assert synthetic_map.contour_mask.dtype == np.bool_


class TestLabels:
    def test_every_label_is_a_real_terrain_class(self, synthetic_map: SyntheticMap) -> None:
        assert int(synthetic_map.labels.max()) < len(TERRAIN_ORDER)

    def test_the_map_is_not_one_flat_colour(self, synthetic_map: SyntheticMap) -> None:
        present = {terrain_class(int(v)) for v in np.unique(synthetic_map.labels)}
        # Every class the generator paints must actually survive being overpainted by the next one.
        expected = set(SHADE_OF) - {
            TerrainClass.CONTOUR,  # overprint only — see below
            TerrainClass.UNKNOWN,  # a classifier output, never ground truth
        }
        assert present == expected

    def test_contour_is_never_a_ground_truth_label(self, synthetic_map: SyntheticMap) -> None:
        # Contours are printed over terrain; the ground under them is still whatever it was. A
        # pipeline reporting "brown" there has misread the map.
        assert terrain_label(TerrainClass.CONTOUR) not in set(np.unique(synthetic_map.labels))
        assert synthetic_map.contour_mask.any()

    def test_forest_dominates_as_it_does_on_a_real_map(self, synthetic_map: SyntheticMap) -> None:
        forest = float(
            (synthetic_map.labels == terrain_label(TerrainClass.FOREST_RUNNABLE)).mean()
        )
        assert 0.5 < forest < 0.9

    def test_out_of_bounds_is_the_whole_area_not_just_the_hatching(
        self, clean_synthetic_map: SyntheticMap
    ) -> None:
        # The purple hatch covers a fraction of the enclosed region, but the region as a whole is
        # forbidden — so the label must be filled while the ink is not.
        oob = clean_synthetic_map.labels == terrain_label(TerrainClass.OUT_OF_BOUNDS)
        assert oob.any()
        purple = np.all(
            clean_synthetic_map.image == np.array(RENDER_SRGB["purple_100"], dtype=np.uint8),
            axis=2,
        )
        inked = float((purple & oob).sum()) / float(oob.sum())
        assert 0.05 < inked < 0.6, f"hatch covers {inked:.0%} of the out-of-bounds area"


class TestContourDensity:
    def test_density_is_asymmetric_so_a_slope_penalty_has_something_to_bite_on(
        self, synthetic_map: SyntheticMap
    ) -> None:
        # T015 / ADR-006: the slope factor comes from contour density. A uniformly contoured map
        # would let a broken penalty pass unnoticed.
        mask = synthetic_map.contour_mask
        h = mask.shape[0]
        steep = mask[: h // 4].mean()
        flat = mask[3 * h // 4 :].mean()
        assert steep > 1.3 * flat, f"top {steep:.4f} vs bottom {flat:.4f}"

    def test_contours_cover_a_plausible_fraction_of_the_map(
        self, synthetic_map: SyntheticMap
    ) -> None:
        assert 0.01 < synthetic_map.contour_mask.mean() < 0.20


class TestControls:
    def test_the_hub_comes_first_and_is_the_only_hub(self, synthetic_map: SyntheticMap) -> None:
        controls = synthetic_map.controls
        assert controls[0] is synthetic_map.hub
        assert synthetic_map.hub.is_hub
        assert [c.is_hub for c in controls].count(True) == 1

    def test_the_requested_number_of_scoring_controls_is_placed(self) -> None:
        sm = make_synthetic_map(seed=5, n_controls=9)
        assert len(sm.controls) == 10  # hub plus nine scoring controls

    def test_ids_are_dense_and_numbers_unique(self, synthetic_map: SyntheticMap) -> None:
        controls = synthetic_map.controls
        assert [c.id for c in controls] == list(range(len(controls)))
        numbers = [c.number for c in controls[1:]]
        assert len(set(numbers)) == len(numbers)

    def test_points_follow_the_first_digit_convention(self, synthetic_map: SyntheticMap) -> None:
        # config/default.toml sets points_rule = "first_digit": control 73 is worth 7.
        for c in synthetic_map.controls[1:]:
            assert c.number is not None and c.points == c.number // 10
            assert 2 <= c.points <= 9

    def test_the_hub_scores_nothing(self, synthetic_map: SyntheticMap) -> None:
        assert synthetic_map.hub.points == 0

    def test_controls_sit_inside_the_map_and_off_forbidden_ground(
        self, synthetic_map: SyntheticMap
    ) -> None:
        h, w = synthetic_map.shape
        forbidden = {
            terrain_label(TerrainClass.WATER_UNCROSSABLE),
            terrain_label(TerrainClass.OUT_OF_BOUNDS),
        }
        for c in synthetic_map.controls:
            assert 0 <= c.x < w and 0 <= c.y < h
            assert int(synthetic_map.labels[int(c.y), int(c.x)]) not in forbidden

    def test_an_impossible_course_is_an_error_not_an_empty_map(self) -> None:
        # A map too small for the minimum gap used to come back with a hub and nothing else, which
        # made every downstream control assertion pass by vacuum.
        with pytest.raises(ValueError, match="minimum gap does not fit"):
            make_synthetic_map(400, 300, seed=3, n_controls=6)


@pytest.mark.perf
class TestFullSizePreset:
    """The preset the performance budgets in SPEC are stated against. Slow by construction."""

    def test_it_is_the_size_the_budgets_assume(
        self, full_size_synthetic_map: SyntheticMap
    ) -> None:
        assert full_size_synthetic_map.shape == (FULL_SIZE[1], FULL_SIZE[0])

    def test_it_carries_a_rogaine_sized_course(
        self, full_size_synthetic_map: SyntheticMap
    ) -> None:
        # 60 scoring controls is the top of the range the owner asked for (30-80).
        assert len(full_size_synthetic_map.controls) == 61
