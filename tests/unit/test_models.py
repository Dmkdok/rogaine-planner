"""The frozen contract (T002). These tests are what "frozen" means in practice."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from rogaine.models import (
    TERRAIN_ORDER,
    Control,
    CostField,
    Leg,
    MapContext,
    Route,
    RunConfig,
    TerrainClass,
    TerrainMap,
    TravelMatrix,
    terrain_class,
    terrain_label,
)


def _leg(a: int, b: int, seconds: float = 60.0) -> Leg:
    return Leg(from_id=a, to_id=b, seconds=seconds, meters=100.0, polyline=[(0, 0), (1, 1)])


class TestTerrainLabels:
    def test_label_and_class_are_inverse(self) -> None:
        for cls in TerrainClass:
            assert terrain_class(terrain_label(cls)) is cls

    def test_order_covers_every_class_exactly_once(self) -> None:
        assert len(TERRAIN_ORDER) == len(set(TERRAIN_ORDER)) == len(list(TerrainClass))

    def test_labels_fit_in_uint8(self) -> None:
        # Mask rasters are uint8; a 257th class would silently wrap.
        assert len(TERRAIN_ORDER) <= 255


class TestControl:
    def test_round_trips(self) -> None:
        c = Control(id=3, x=10.5, y=20.25, number=47, points=4, confidence=0.9)
        assert Control.model_validate_json(c.model_dump_json()) == c

    def test_missing_points_is_representable(self) -> None:
        # ADR-009: an unreadable number must survive as "unknown", never as a guess.
        c = Control(id=1, x=0.0, y=0.0, number=None, points=None, confidence=0.1)
        assert c.points is None

    def test_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            Control(id=1, x=0.0, y=0.0, elevation=100)  # type: ignore[call-arg]

    def test_rejects_negative_coordinates(self) -> None:
        with pytest.raises(ValidationError):
            Control(id=1, x=-1.0, y=0.0)


class TestRoute:
    def test_valid_loop_round_trips(self) -> None:
        route = Route(
            order=[0, 1, 2, 0],
            legs=[_leg(0, 1), _leg(1, 2), _leg(2, 0)],
            total_seconds=180.0,
            total_meters=300.0,
            points=7,
            penalty=0.0,
            score=7.0,
            solver="exact",
            optimal=True,
        )
        assert Route.model_validate_json(route.model_dump_json()) == route

    def test_route_must_return_to_the_hub(self) -> None:
        with pytest.raises(ValidationError, match="starts and finishes at the hub"):
            Route(
                order=[0, 1, 2],
                legs=[_leg(0, 1), _leg(1, 2)],
                total_seconds=120.0,
                total_meters=200.0,
                points=5,
                penalty=0.0,
                score=5.0,
                solver="heuristic",
            )

    def test_legs_must_follow_the_visit_order(self) -> None:
        with pytest.raises(ValidationError, match="does not follow the visit order"):
            Route(
                order=[0, 1, 2, 0],
                legs=[_leg(0, 1), _leg(2, 1), _leg(2, 0)],
                total_seconds=180.0,
                total_meters=300.0,
                points=7,
                penalty=0.0,
                score=7.0,
                solver="heuristic",
            )

    def test_leg_count_must_match_the_order(self) -> None:
        with pytest.raises(ValidationError, match="legs expected"):
            Route(
                order=[0, 1, 2, 0],
                legs=[_leg(0, 1), _leg(1, 2)],
                total_seconds=120.0,
                total_meters=200.0,
                points=7,
                penalty=0.0,
                score=7.0,
                solver="heuristic",
            )


class TestRunConfig:
    def test_round_trips(self) -> None:
        cfg = RunConfig(base_speed_mps=2.5, time_limit_s=4 * 3600, penalty_per_min=2.0, seed=7)
        assert RunConfig.model_validate_json(cfg.model_dump_json()) == cfg

    def test_speed_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            RunConfig(base_speed_mps=0.0, time_limit_s=3600)

    # ADR-017 / S-001: upper bounds keep a single run's resource use bounded.

    def test_time_limit_above_bound_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RunConfig(base_speed_mps=2.0, time_limit_s=86400.1)

    def test_heuristic_time_budget_above_bound_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RunConfig(base_speed_mps=2.0, time_limit_s=3600, heuristic_time_budget_s=600.1)

    def test_alternatives_above_bound_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RunConfig(base_speed_mps=2.0, time_limit_s=3600, alternatives=21)


class TestRasterStructures:
    def test_map_context_accepts_an_rgb_image(self) -> None:
        ctx = MapContext(
            image=np.zeros((4, 6, 3), dtype=np.uint8),
            meters_per_pixel=2.54,
            source=Path("m.png"),
        )
        assert (ctx.height, ctx.width) == (4, 6)

    def test_map_context_rejects_greyscale(self) -> None:
        with pytest.raises(ValueError, match="RGB image"):
            MapContext(
                image=np.zeros((4, 6), dtype=np.uint8),
                meters_per_pixel=1.0,
                source=Path("m.png"),
            )

    def test_map_context_rejects_nonpositive_scale(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            MapContext(
                image=np.zeros((4, 6, 3), dtype=np.uint8),
                meters_per_pixel=0.0,
                source=Path("m.png"),
            )

    def test_terrain_map_rejects_out_of_range_labels(self) -> None:
        labels = np.full((3, 3), len(TERRAIN_ORDER), dtype=np.uint8)
        with pytest.raises(ValueError, match="outside TERRAIN_ORDER"):
            TerrainMap(
                labels=labels,
                contour_density=np.zeros((3, 3), np.float32),
                meters_per_pixel=1.0,
            )

    def test_cost_field_rejects_infinite_cost_on_passable_ground(self) -> None:
        cost = np.full((2, 2), np.inf, dtype=np.float32)
        with pytest.raises(ValueError, match="finite cost"):
            CostField(
                seconds_per_pixel=cost,
                passable=np.ones((2, 2), dtype=bool),
                meters_per_pixel=1.0,
                base_speed_mps=2.0,
            )

    def test_travel_matrix_lookups(self) -> None:
        seconds = np.array([[0.0, 30.0], [30.0, 0.0]])
        tm = TravelMatrix(
            control_ids=(0, 5), seconds=seconds, meters=seconds * 2.0, paths={}
        )
        assert tm.index_of(5) == 1
        assert tm.time_between(0, 5) == 30.0

    def test_travel_matrix_rejects_a_shape_mismatch(self) -> None:
        with pytest.raises(ValueError, match="matrices for"):
            TravelMatrix(
                control_ids=(0, 1, 2),
                seconds=np.zeros((2, 2)),
                meters=np.zeros((2, 2)),
                paths={},
            )
