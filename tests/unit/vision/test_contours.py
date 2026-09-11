"""Contour density and slope factor (T015): F6's slope proxy, without elevation reconstruction.

DoD (F6): brown contour mask, density by Gaussian blur, `k_slope` from config; a contour-dense
fixture region yields a strictly higher cost than a flat region of the same class; the coefficient
is documented as direction-blind (ADR-006).
"""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pytest

from rogaine.config import default_config, load_config
from rogaine.models import TerrainClass, terrain_label
from rogaine.vision.contours import contour_density, contour_mask, k_slope
from rogaine.vision.palette import classify_palette


def _blank(height: int, width: int, cls: TerrainClass = TerrainClass.FOREST_RUNNABLE) -> np.ndarray:
    return np.full((height, width), terrain_label(cls), dtype=np.uint8)


class TestContourMask:
    def test_extracts_exactly_the_contour_labelled_pixels(self) -> None:
        labels = _blank(10, 10)
        labels[3, 4] = terrain_label(TerrainClass.CONTOUR)
        labels[7, 2] = terrain_label(TerrainClass.CONTOUR)

        mask = contour_mask(labels)

        assert mask.dtype == np.bool_
        assert mask.shape == labels.shape
        expected = np.zeros((10, 10), dtype=bool)
        expected[3, 4] = True
        expected[7, 2] = True
        assert np.array_equal(mask, expected)

    def test_no_contour_pixels_gives_an_all_false_mask(self) -> None:
        labels = _blank(10, 10)
        mask = contour_mask(labels)
        assert not mask.any()


class TestContourDensityRange:
    def test_zero_where_there_is_no_contour_ink(self) -> None:
        labels = _blank(60, 60)
        density = contour_density(labels, 300.0)
        assert density.dtype == np.float32
        assert density.shape == labels.shape
        assert np.array_equal(density, np.zeros((60, 60), dtype=np.float32))

    def test_stays_within_zero_one_even_with_solid_contour_ink(self) -> None:
        labels = _blank(80, 80, cls=TerrainClass.CONTOUR)
        density = contour_density(labels, 300.0)
        assert density.min() >= 0.0
        assert density.max() <= 1.0

    def test_density_rises_with_local_contour_line_spacing(self) -> None:
        """More contour lines packed into the same area -> higher local density (F6's premise)."""
        cfg = default_config()
        height, width = 300, 300
        sparse = _blank(height, width)
        dense = _blank(height, width)
        for y in range(20, height - 20, 60):
            sparse[y, :] = terrain_label(TerrainClass.CONTOUR)
        for y in range(20, height - 20, 10):
            dense[y, :] = terrain_label(TerrainClass.CONTOUR)

        sparse_density = contour_density(sparse, 300.0, cfg)
        dense_density = contour_density(dense, 300.0, cfg)

        # Compare away from the top/bottom edges, where the sigma-scale blur radius has full room
        # to build up its plateau on both sides.
        band = slice(80, height - 80)
        assert dense_density[band].mean() > sparse_density[band].mean()


class TestKSlope:
    def test_density_zero_gives_factor_one(self) -> None:
        density = np.zeros((5, 5), dtype=np.float32)
        factor = k_slope(density)
        assert np.allclose(factor, 1.0)

    def test_matches_the_configured_formula_on_a_hand_computed_case(self) -> None:
        # This test only exercises `k_slope`, which never touches `density_sigma_mm` -- overriding
        # just `penalty`/`density_exponent` keeps the override minimal and honest about what the
        # test depends on. Exponent 2.0 here (not the shipped default) to hand-verify the exponent
        # itself is actually applied, separately from `test_matches_the_shipped_default_config`.
        cfg = load_config(overrides={"slope": {"penalty": 3.0, "density_exponent": 2.0}})
        density = np.array([[0.0, 0.25, 0.5, 1.0]], dtype=np.float32)
        expected = 1.0 / (1.0 + 3.0 * density**2.0)
        factor = k_slope(density, cfg)
        assert factor.dtype == np.float32
        np.testing.assert_allclose(factor, expected, rtol=1e-6)

    def test_matches_the_shipped_default_config(self) -> None:
        """T095/ADR-029's retuned defaults (`config/default.toml`): penalty 6.0, exponent 2.0."""
        cfg = default_config()
        assert cfg.slope.penalty == pytest.approx(6.0)
        assert cfg.slope.density_exponent == pytest.approx(2.0)
        density = np.array([[0.0, 1 / 3, 0.5, 1.0]], dtype=np.float32)
        expected = 1.0 / (1.0 + 6.0 * density**2.0)
        factor = k_slope(density, cfg)
        np.testing.assert_allclose(factor, expected, rtol=1e-6)

    def test_convex_exponent_crosses_the_old_linear_formula_at_the_documented_point(self) -> None:
        """At the shipped penalty/exponent, the new convex curve costs the same as the original
        linear `1 + 2 * density` formula at density = 1/3, less below it, and more above it (the
        crossing point `config/default.toml`'s own comment derives and hand-checks)."""
        cfg = default_config()
        below, at, above = 0.2, 1 / 3, 0.6
        old_linear = lambda d: 1.0 + 2.0 * d  # noqa: E731 - the pre-T095 formula, for comparison
        new_convex = lambda d: 1.0 + cfg.slope.penalty * d**cfg.slope.density_exponent  # noqa: E731

        assert new_convex(below) < old_linear(below)
        assert new_convex(at) == pytest.approx(old_linear(at), rel=1e-6)
        assert new_convex(above) > old_linear(above)

    def test_decreases_monotonically_as_density_rises(self) -> None:
        density = np.linspace(0.0, 1.0, 11, dtype=np.float32).reshape(1, -1)
        factor = k_slope(density).reshape(-1)
        assert all(a > b for a, b in pairwise(factor))

    def test_density_exponent_one_recovers_the_original_linear_formula(self) -> None:
        cfg = load_config(overrides={"slope": {"penalty": 2.5, "density_exponent": 1.0}})
        density = np.array([[0.0, 0.3, 0.7, 1.0]], dtype=np.float32)
        expected = 1.0 / (1.0 + 2.5 * density)
        factor = k_slope(density, cfg)
        np.testing.assert_allclose(factor, expected, rtol=1e-6)


class TestInputValidation:
    def test_contour_mask_rejects_non_2d_labels(self) -> None:
        with pytest.raises(ValueError, match="H, W"):
            contour_mask(np.zeros((4, 4, 3), dtype=np.uint8))

    def test_contour_mask_rejects_non_uint8_labels(self) -> None:
        with pytest.raises(ValueError, match="uint8"):
            contour_mask(np.zeros((4, 4), dtype=np.int32))

    def test_contour_density_rejects_non_2d_labels(self) -> None:
        with pytest.raises(ValueError, match="H, W"):
            contour_density(np.zeros((4, 4, 3), dtype=np.uint8), 300.0)

    def test_contour_density_rejects_non_uint8_labels(self) -> None:
        with pytest.raises(ValueError, match="uint8"):
            contour_density(np.zeros((4, 4), dtype=np.int32), 300.0)

    def test_contour_density_rejects_non_positive_dpi(self) -> None:
        with pytest.raises(ValueError, match="dpi"):
            contour_density(np.zeros((4, 4), dtype=np.uint8), 0.0)

    def test_k_slope_rejects_non_2d_density(self) -> None:
        with pytest.raises(ValueError, match="H, W"):
            k_slope(np.zeros((4, 4, 3), dtype=np.float32))

    def test_k_slope_rejects_non_floating_density(self) -> None:
        with pytest.raises(ValueError, match="floating"):
            k_slope(np.zeros((4, 4), dtype=np.int32))

    def test_k_slope_rejects_density_outside_zero_one(self) -> None:
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            k_slope(np.array([[0.0, 1.5]], dtype=np.float32))

    def test_k_slope_rejects_negative_density(self) -> None:
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            k_slope(np.array([[-0.1, 0.5]], dtype=np.float32))


class TestSlopeCostOnFixture:
    """SPEC F6's literal DoD line, measured on the fixture's dense-to-sparse contour gradient
    (`tests/fixtures/synth_map.py`'s own T015 comment): the same terrain class costs strictly more
    to traverse in the contour-dense top quarter of the map than in the flat bottom quarter."""

    def test_dense_region_costs_strictly_more_than_flat_region_of_the_same_class(
        self, clean_synthetic_map
    ) -> None:
        sm = clean_synthetic_map
        cfg = default_config()
        pred_labels = classify_palette(sm.image, cfg)
        density = contour_density(pred_labels, sm.dpi, cfg)
        factor = k_slope(density, cfg)

        forest_lbl = terrain_label(TerrainClass.FOREST_RUNNABLE)
        h = pred_labels.shape[0]
        top = slice(0, h // 4)
        bottom = slice(3 * h // 4, h)

        dense_forest = pred_labels[top] == forest_lbl
        flat_forest = pred_labels[bottom] == forest_lbl
        assert dense_forest.sum() > 200, "fixture precondition: too little forest in the dense band"
        assert flat_forest.sum() > 200, "fixture precondition: too little forest in the flat band"

        dense_cost = 1.0 / factor[top][dense_forest]
        flat_cost = 1.0 / factor[bottom][flat_forest]
        # A margin, not a bare `>`: a regression collapsing the gap to a fraction of a percent would
        # still pass a bare inequality. The real measured margin is ~4.4%; 2% leaves headroom.
        assert dense_cost.mean() > flat_cost.mean() * 1.02, (
            f"dense-region mean cost {dense_cost.mean():.4f} not >2% above "
            f"flat-region mean cost {flat_cost.mean():.4f}"
        )
