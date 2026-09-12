"""Linear-feature proximity bonus (T095, ADR-029, Rules 2+7): `k_proximity` in isolation.

DoD: off (all-ones, no distance transform even attempted) when `config.proximity.enabled` is
`False`; a synthetic case where distance to a linear feature (`road`/`vehicle_track`/`footpath`)
decays the bonus exactly per the configured exponential-decay formula once enabled.

ADR-029 amendment (owner sign-off, 2026-09-12): the shipped default is now `enabled=True`, not
`False` -- `TestEnabledByDefault` below covers that; `TestDisabledExplicitly` still covers the
off-path, forced via an explicit override rather than relying on the default.
"""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pytest

from rogaine.config import default_config, load_config
from rogaine.cost.proximity import k_proximity
from rogaine.models import TerrainClass, terrain_label


def _labels_with_road_at(shape: tuple[int, int], road_col: int) -> np.ndarray:
    labels = np.full(shape, terrain_label(TerrainClass.FOREST_RUNNABLE), dtype=np.uint8)
    labels[:, road_col] = terrain_label(TerrainClass.ROAD)
    return labels


class TestEnabledByDefault:
    """ADR-029 amendment (owner sign-off, 2026-09-12): the shipped default is now enabled."""

    def test_shipped_default_config_has_it_enabled(self) -> None:
        assert default_config().proximity.enabled is True

    def test_returns_a_real_bonus_with_default_config(self) -> None:
        labels = _labels_with_road_at((5, 5), road_col=2)
        factor = k_proximity(labels, meters_per_pixel=1.0)
        assert factor.dtype == np.float32
        assert factor[0, 2] > 1.0, "no bonus at all on the linear-feature pixel itself"
        assert not np.array_equal(factor, np.ones((5, 5), dtype=np.float32))


class TestDisabledExplicitly:
    def test_returns_all_ones_when_forced_off(self) -> None:
        cfg = load_config(overrides={"proximity": {"enabled": False}})
        labels = _labels_with_road_at((5, 5), road_col=2)
        factor = k_proximity(labels, meters_per_pixel=1.0, config=cfg)
        assert factor.dtype == np.float32
        assert np.array_equal(factor, np.ones((5, 5), dtype=np.float32))

    def test_returns_all_ones_when_no_linear_features_present_even_if_enabled(self) -> None:
        cfg = load_config(
            overrides={
                "proximity": {"enabled": True, "decay_distance_m": 10.0, "bonus_magnitude": 0.5}
            }
        )
        labels = np.full((4, 4), terrain_label(TerrainClass.FOREST_RUNNABLE), dtype=np.uint8)
        factor = k_proximity(labels, meters_per_pixel=1.0, config=cfg)
        assert np.array_equal(factor, np.ones((4, 4), dtype=np.float32))


class TestEnabledHandComputed:
    def test_matches_the_exponential_decay_formula_on_a_1d_case(self) -> None:
        cfg = load_config(
            overrides={
                "proximity": {"enabled": True, "decay_distance_m": 2.0, "bonus_magnitude": 1.0}
            }
        )
        labels = _labels_with_road_at((1, 5), road_col=2)

        factor = k_proximity(labels, meters_per_pixel=2.0, config=cfg)

        dist_px = np.array([2.0, 1.0, 0.0, 1.0, 2.0])
        dist_m = dist_px * 2.0
        expected = 1.0 + 1.0 * np.exp(-dist_m / 2.0)
        assert factor.dtype == np.float32
        np.testing.assert_allclose(factor[0], expected, rtol=1e-5)

    def test_peak_bonus_is_exactly_on_the_linear_feature_pixel(self) -> None:
        cfg = load_config(
            overrides={
                "proximity": {"enabled": True, "decay_distance_m": 5.0, "bonus_magnitude": 0.3}
            }
        )
        labels = _labels_with_road_at((6, 6), road_col=3)

        factor = k_proximity(labels, meters_per_pixel=1.0, config=cfg)

        np.testing.assert_allclose(factor[:, 3], 1.3, rtol=1e-6)

    def test_decays_strictly_monotonically_with_distance(self) -> None:
        cfg = load_config(
            overrides={
                "proximity": {"enabled": True, "decay_distance_m": 3.0, "bonus_magnitude": 0.8}
            }
        )
        labels = _labels_with_road_at((1, 10), road_col=0)

        factor = k_proximity(labels, meters_per_pixel=1.0, config=cfg)[0]

        assert all(a > b for a, b in pairwise(factor))


class TestInputValidation:
    def test_rejects_non_2d_labels(self) -> None:
        with pytest.raises(ValueError, match="H, W"):
            k_proximity(np.zeros((2, 2, 2), dtype=np.uint8), meters_per_pixel=1.0)

    def test_rejects_wrong_dtype(self) -> None:
        with pytest.raises(ValueError, match="uint8"):
            k_proximity(np.zeros((2, 2), dtype=np.int32), meters_per_pixel=1.0)

    def test_rejects_non_positive_meters_per_pixel(self) -> None:
        labels = np.zeros((2, 2), dtype=np.uint8)
        with pytest.raises(ValueError, match="meters_per_pixel"):
            k_proximity(labels, meters_per_pixel=0.0)
        with pytest.raises(ValueError, match="meters_per_pixel"):
            k_proximity(labels, meters_per_pixel=-1.0)
