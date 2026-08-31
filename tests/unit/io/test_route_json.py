"""route.json schema, writer and reader (T051, SPEC F15).

Golden expectations below are plain Python dicts compared against `json.loads(path.read_text())`,
not a raw stored string: `model_dump_json`'s exact whitespace/indentation is an implementation
detail, not part of the documented schema (SPEC F15 is about field values and structure). Field
values — `cumulative_seconds` in particular — are checked against hand arithmetic, not against
whatever the code happens to produce.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from rogaine.io.route_json import LegRecord, RouteFile, read_route_json, write_route_json
from rogaine.models import Leg, Route, RunConfig

# A small, fully hand-computed route: hub(0) -> control(1) -> control(2) -> hub(0).
# leg seconds: 300, 200, 250 -> cumulative: 300, 500, 750 -> total_seconds 750.
ROUTE = Route(
    order=[0, 1, 2, 0],
    legs=[
        Leg(from_id=0, to_id=1, seconds=300.0, meters=450.0, polyline=[(10, 10), (20, 20)]),
        Leg(from_id=1, to_id=2, seconds=200.0, meters=300.0, polyline=[(20, 20), (30, 25)]),
        Leg(from_id=2, to_id=0, seconds=250.0, meters=400.0, polyline=[(30, 25), (10, 10)]),
    ],
    total_seconds=750.0,
    total_meters=1150.0,
    points=15,
    penalty=0.0,
    score=15.0,
    solver="exact",
    optimal=True,
    seed=0,
)
RUN_CONFIG = RunConfig(
    base_speed_mps=1.4,
    time_limit_s=3600.0,
    penalty_per_min=2.0,
    strategy="exact",
    heuristic_time_budget_s=30.0,
    alternatives=3,
    seed=0,
)

EXPECTED_JSON = {
    "schema_version": 1,
    "order": [0, 1, 2, 0],
    "legs": [
        {
            "from_id": 0,
            "to_id": 1,
            "seconds": 300.0,
            "meters": 450.0,
            "polyline": [[10, 10], [20, 20]],
            "cumulative_seconds": 300.0,
        },
        {
            "from_id": 1,
            "to_id": 2,
            "seconds": 200.0,
            "meters": 300.0,
            "polyline": [[20, 20], [30, 25]],
            "cumulative_seconds": 500.0,
        },
        {
            "from_id": 2,
            "to_id": 0,
            "seconds": 250.0,
            "meters": 400.0,
            "polyline": [[30, 25], [10, 10]],
            "cumulative_seconds": 750.0,
        },
    ],
    "total_seconds": 750.0,
    "total_meters": 1150.0,
    "points": 15,
    "penalty": 0.0,
    "score": 15.0,
    "solver": "exact",
    "optimal": True,
    "seed": 0,
    "run_config": {
        "base_speed_mps": 1.4,
        "time_limit_s": 3600.0,
        "penalty_per_min": 2.0,
        "strategy": "exact",
        "heuristic_time_budget_s": 30.0,
        "alternatives": 3,
        "seed": 0,
    },
}


class TestGolden:
    def test_write_matches_hand_computed_schema(self, tmp_path) -> None:
        path = tmp_path / "route.json"
        write_route_json(path, ROUTE, RUN_CONFIG)
        assert json.loads(path.read_text(encoding="utf-8")) == EXPECTED_JSON


class TestRoundTrip:
    def test_every_field_survives_write_then_read(self, tmp_path) -> None:
        path = tmp_path / "route.json"
        write_route_json(path, ROUTE, RUN_CONFIG)
        loaded = read_route_json(path)

        expected = RouteFile(
            order=ROUTE.order,
            legs=[
                LegRecord(from_id=0, to_id=1, seconds=300.0, meters=450.0,
                          polyline=[(10, 10), (20, 20)], cumulative_seconds=300.0),
                LegRecord(from_id=1, to_id=2, seconds=200.0, meters=300.0,
                          polyline=[(20, 20), (30, 25)], cumulative_seconds=500.0),
                LegRecord(from_id=2, to_id=0, seconds=250.0, meters=400.0,
                          polyline=[(30, 25), (10, 10)], cumulative_seconds=750.0),
            ],
            total_seconds=ROUTE.total_seconds,
            total_meters=ROUTE.total_meters,
            points=ROUTE.points,
            penalty=ROUTE.penalty,
            score=ROUTE.score,
            solver=ROUTE.solver,
            optimal=ROUTE.optimal,
            seed=ROUTE.seed,
            run_config=RUN_CONFIG,
        )
        assert loaded == expected

    def test_read_missing_file_raises(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            read_route_json(tmp_path / "does-not-exist.json")


class TestOrderLegsInvariant:
    """RouteFile carries its own copy of Route's order/legs validator (see route_json.py's module
    docstring for why): write_route_json can never trip it, since it is always built from an
    already-validated Route, but read_route_json builds a RouteFile from arbitrary disk bytes, so
    the same corrupted-file case is reachable there too. Both are exercised directly here.
    """

    def test_direct_construction_rejects_a_legs_order_mismatch(self) -> None:
        with pytest.raises(ValidationError, match="does not follow the visit order"):
            RouteFile(
                order=[0, 1, 2, 0],
                legs=[
                    LegRecord(from_id=0, to_id=1, seconds=1.0, meters=1.0, cumulative_seconds=1.0),
                    # wrong: should be 1->2, not 1->9
                    LegRecord(from_id=1, to_id=9, seconds=1.0, meters=1.0, cumulative_seconds=2.0),
                    LegRecord(from_id=2, to_id=0, seconds=1.0, meters=1.0, cumulative_seconds=3.0),
                ],
                total_seconds=3.0,
                total_meters=3.0,
                points=0,
                penalty=0.0,
                score=0.0,
                solver="exact",
                run_config=RUN_CONFIG,
            )

    def test_hand_corrupted_file_is_rejected_on_read(self, tmp_path) -> None:
        path = tmp_path / "route.json"
        write_route_json(path, ROUTE, RUN_CONFIG)
        broken = json.loads(path.read_text(encoding="utf-8"))
        broken["order"] = [0, 1, 0]  # now shorter than legs
        path.write_text(json.dumps(broken), encoding="utf-8")
        with pytest.raises(ValidationError, match="legs expected"):
            read_route_json(path)

    def test_route_itself_rejects_the_same_mismatch(self) -> None:
        # Confirms write_route_json's input side is unreachable for this defect: Route (ADR-008)
        # already refuses to construct with a legs/order mismatch, before route_json ever sees it.
        with pytest.raises(ValidationError, match="does not follow the visit order"):
            Route(
                order=[0, 1, 2, 0],
                legs=[
                    Leg(from_id=0, to_id=1, seconds=1.0, meters=1.0),
                    Leg(from_id=1, to_id=9, seconds=1.0, meters=1.0),
                    Leg(from_id=2, to_id=0, seconds=1.0, meters=1.0),
                ],
                total_seconds=3.0,
                total_meters=3.0,
                points=0,
                penalty=0.0,
                score=0.0,
                solver="exact",
            )
