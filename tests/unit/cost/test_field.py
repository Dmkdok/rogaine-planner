"""Per-pixel cost field (T030, F10): `t = mpp / (v_base * k_terrain * k_slope)`.

DoD (F10): float32 seconds-per-pixel plus a passability mask; impassable classes excluded; a
hand-checked 5x5 case matches the formula exactly.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np
import pytest

from rogaine.config import default_config, load_config
from rogaine.cost.field import compute_cost_field
from rogaine.cost.proximity import k_proximity
from rogaine.models import CostField, TerrainClass, TerrainMap, terrain_label
from rogaine.vision.contours import k_slope


def _terrain_map(labels: np.ndarray, density: np.ndarray, mpp: float) -> TerrainMap:
    return TerrainMap(
        labels=labels.astype(np.uint8),
        contour_density=density.astype(np.float32),
        meters_per_pixel=mpp,
    )


class TestHandCheckedFormula:
    """A 5x5 map, one homogeneous terrain class and contour density per row, computed against the
    formula directly in this test -- never by calling `compute_cost_field` to produce its own
    oracle."""

    MPP = 2.0
    V_BASE = 5.0
    PENALTY = 1.0  # overridden below; k_slope = 1 / (1 + PENALTY * density ** EXPONENT)
    EXPONENT = 1.0  # forced to the pre-T095 linear formula -- this class hand-checks that, not
    # T095/ADR-029's retuned convex default (covered separately in test_contours.py).

    # Row layout: (terrain class, row's contour density). `forest_runnable` and `road` are
    # ordinary passable classes; `water_uncrossable` is impassable; `contour` is the one passable
    # class with speed_factor 0.0 by design (config/default.toml's own "not an area class" note).
    ROWS: ClassVar[list[tuple[TerrainClass, float]]] = [
        (TerrainClass.FOREST_RUNNABLE, 0.0),
        (TerrainClass.ROAD, 0.25),
        (TerrainClass.WATER_UNCROSSABLE, 0.5),
        (TerrainClass.CONTOUR, 0.75),
        (TerrainClass.ROAD, 1.0),
    ]

    @pytest.fixture()
    def cfg(self):
        # `proximity.enabled` explicitly forced off (T095/ADR-029's default flipped `true` on
        # 2026-09-12, sign-off): this class hand-checks the base two-factor `k_terrain * k_slope`
        # formula in isolation, independent of whatever the shipped proximity default happens to
        # be -- the proximity bonus itself is covered separately by `TestProximityBonusIntegration`
        # below and by `tests/unit/cost/test_proximity.py`.
        return load_config(
            overrides={
                "slope": {"penalty": self.PENALTY, "density_exponent": self.EXPONENT},
                "proximity": {"enabled": False},
            }
        )

    @pytest.fixture()
    def cost_field(self, cfg) -> CostField:
        labels = np.zeros((5, 5), dtype=np.uint8)
        density = np.zeros((5, 5), dtype=np.float32)
        for row, (cls, row_density) in enumerate(self.ROWS):
            labels[row, :] = terrain_label(cls)
            density[row, :] = row_density
        terrain = _terrain_map(labels, density, self.MPP)
        return compute_cost_field(terrain, self.V_BASE, cfg)

    def test_seconds_per_pixel_matches_the_formula_row_by_row(self, cfg, cost_field) -> None:
        for row, (cls, row_density) in enumerate(self.ROWS):
            spec = cfg.terrain_of(cls)
            if not spec.passable:
                expected = float("inf")
            else:
                # `contour` is the documented exception: passable with speed_factor 0.0, which
                # this module neutralises to 1.0 rather than dividing by zero (see field.py's
                # module docstring).
                k_terrain = 1.0 if spec.speed_factor == 0.0 else spec.speed_factor
                k_slope = 1.0 / (1.0 + self.PENALTY * row_density)
                expected = self.MPP / (self.V_BASE * k_terrain * k_slope)

            actual_row = cost_field.seconds_per_pixel[row]
            if np.isinf(expected):
                assert np.all(np.isinf(actual_row)), f"row {row} ({cls}): expected all +inf"
            else:
                np.testing.assert_allclose(
                    actual_row, expected, rtol=1e-6, err_msg=f"row {row} ({cls})"
                )

    def test_passable_mask_matches_config_passability(self, cfg, cost_field) -> None:
        for row, (cls, _density) in enumerate(self.ROWS):
            expected_passable = cfg.terrain_of(cls).passable
            assert np.all(cost_field.passable[row] == expected_passable), cls

    def test_meters_per_pixel_and_base_speed_are_recorded_as_given(self, cost_field) -> None:
        assert cost_field.meters_per_pixel == self.MPP
        assert cost_field.base_speed_mps == self.V_BASE


class TestImpassableExclusion:
    def test_impassable_pixels_are_not_passable(self) -> None:
        labels = np.full((4, 4), terrain_label(TerrainClass.WATER_UNCROSSABLE), dtype=np.uint8)
        density = np.zeros((4, 4), dtype=np.float32)
        terrain = _terrain_map(labels, density, mpp=1.0)

        result = compute_cost_field(terrain, base_speed_mps=3.0)

        assert not result.passable.any()

    def test_finiteness_exactly_tracks_passability_no_nan_anywhere(self) -> None:
        """Every passable pixel is finite (CostField's own invariant) and every impassable pixel
        is exactly the documented `+inf` sentinel -- never `nan`, and never a finite value that
        could silently corrupt a downstream sum over the whole array."""
        labels = np.array(
            [
                [terrain_label(TerrainClass.FOREST_RUNNABLE), terrain_label(TerrainClass.ROAD)],
                [
                    terrain_label(TerrainClass.WATER_UNCROSSABLE),
                    terrain_label(TerrainClass.OUT_OF_BOUNDS),
                ],
            ],
            dtype=np.uint8,
        )
        density = np.array([[0.0, 0.3], [0.6, 0.9]], dtype=np.float32)
        terrain = _terrain_map(labels, density, mpp=1.5)

        result = compute_cost_field(terrain, base_speed_mps=4.0)

        assert not np.isnan(result.seconds_per_pixel).any()
        assert np.array_equal(np.isfinite(result.seconds_per_pixel), result.passable)
        assert np.all(np.isinf(result.seconds_per_pixel[~result.passable]))
        # A naive sum over the whole array is visibly +inf, not a silently-wrong finite number.
        assert np.isinf(result.seconds_per_pixel.sum())
        # ...while summing only the passable pixels, as downstream code must, stays finite.
        assert np.isfinite(result.seconds_per_pixel[result.passable].sum())


class TestDtype:
    def test_seconds_per_pixel_and_passable_are_float32_and_bool(self) -> None:
        labels = np.full((3, 3), terrain_label(TerrainClass.ROAD), dtype=np.uint8)
        density = np.full((3, 3), 0.2, dtype=np.float32)
        terrain = _terrain_map(labels, density, mpp=0.5)

        result = compute_cost_field(terrain, base_speed_mps=2.5)

        assert result.seconds_per_pixel.dtype == np.float32
        assert result.passable.dtype == np.bool_


class TestInputValidation:
    def test_rejects_non_positive_base_speed(self) -> None:
        labels = np.full((2, 2), terrain_label(TerrainClass.ROAD), dtype=np.uint8)
        density = np.zeros((2, 2), dtype=np.float32)
        terrain = _terrain_map(labels, density, mpp=1.0)

        with pytest.raises(ValueError, match="base_speed_mps"):
            compute_cost_field(terrain, base_speed_mps=0.0)

        with pytest.raises(ValueError, match="base_speed_mps"):
            compute_cost_field(terrain, base_speed_mps=-1.0)


class TestProximityBonusIntegration:
    """T095/ADR-029: the linear-feature proximity bonus (`cost/proximity.k_proximity`), folded
    into `compute_cost_field`'s per-pixel rate alongside `k_terrain`/`k_slope`."""

    def test_default_config_applies_the_proximity_bonus(self) -> None:
        """Enabled by default (ADR-029 amendment, owner sign-off 2026-09-12) -- with defaults
        untouched, `compute_cost_field` must fold in `k_proximity` alongside `k_terrain`/
        `k_slope`, exactly matching the three-factor formula computed independently here.
        `TestHandCheckedFormula` above covers the plain two-factor formula in isolation, with
        `proximity.enabled` explicitly forced off."""
        cfg = default_config()
        assert cfg.proximity.enabled is True
        labels = np.array(
            [[terrain_label(TerrainClass.FOOTPATH), terrain_label(TerrainClass.FOREST_RUNNABLE)]],
            dtype=np.uint8,
        )
        density = np.array([[0.1, 0.2]], dtype=np.float32)
        terrain = _terrain_map(labels, density, mpp=1.5)

        result = compute_cost_field(terrain, base_speed_mps=3.0, config=cfg)

        k_terrain = cfg.speed_factors()[labels]
        slope = k_slope(density, cfg)
        proximity = k_proximity(labels, meters_per_pixel=terrain.meters_per_pixel, config=cfg)
        expected = terrain.meters_per_pixel / (np.float32(3.0) * k_terrain * slope * proximity)
        np.testing.assert_allclose(result.seconds_per_pixel, expected.astype(np.float32), rtol=1e-6)

    def test_enabled_bonus_makes_a_pixel_near_a_linear_feature_strictly_cheaper(self) -> None:
        """Synthetic case (DoD): a footpath at one end of an otherwise-uniform forest row. With
        the bonus enabled at a concrete non-default value, the forest pixel next to the footpath
        must cost strictly less than an identical-terrain pixel further away."""
        cfg = load_config(
            overrides={
                "proximity": {"enabled": True, "decay_distance_m": 10.0, "bonus_magnitude": 0.5}
            }
        )
        labels = np.full((1, 6), terrain_label(TerrainClass.FOREST_RUNNABLE), dtype=np.uint8)
        labels[0, 0] = terrain_label(TerrainClass.FOOTPATH)
        density = np.zeros((1, 6), dtype=np.float32)
        terrain = _terrain_map(labels, density, mpp=1.0)

        result = compute_cost_field(terrain, base_speed_mps=3.0, config=cfg)

        near = result.seconds_per_pixel[0, 1]
        far = result.seconds_per_pixel[0, 5]
        assert near < far, f"near-footpath cost {near} not below far cost {far}"
