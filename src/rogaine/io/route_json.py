"""Route JSON schema, writer and reader (T051, SPEC F15).

"Route artefacts: JSON (order, per-leg time and distance, cumulative time, points, penalty,
polylines) ... | JSON validates against the documented schema" (SPEC F15, JSON half only — the PNG
half is T052, out of scope here).

**Why this isn't just `Route.model_dump()`.** `Route` (ADR-008, frozen — not edited by this task)
has no cumulative-time field and no embedded run config, both required by this task's DoD. Rather
than change the frozen contract, this module defines its own pydantic models — `LegRecord` and
`RouteFile` — built *from* a `Route` + `RunConfig` pair at write time:

- `LegRecord` is `Leg`'s own fields (`from_id`, `to_id`, `seconds`, `meters`, `polyline`) plus a
  computed `cumulative_seconds`: the running sum of `seconds` from the hub, i.e. the total
  elapsed time at the control this leg arrives at. This is exactly what `cli.py`'s `plan_cmd` table
  computes inline (running `cumulative += leg.seconds` over `route.legs`) — same arithmetic, just
  persisted instead of printed.
- `RouteFile` mirrors `Route`'s own top-level fields (`order`, `total_seconds`, `total_meters`,
  `points`, `penalty`, `score`, `solver`, `optimal`, `seed`) with `legs: list[LegRecord]` in place
  of `Route.legs`, plus a nested `run_config: RunConfig`. "The config that produced it" is
  `RunConfig` specifically — models.py's own docstring calls it "everything the user chooses per
  attempt" — not the larger `AppConfig` (terrain/palette tuning, not a per-run choice), so only
  `RunConfig` is embedded.
- `schema_version` (int, default 1) is included even though the DoD doesn't ask for it: it's the
  standard low-cost hook for evolving this file format without breaking old artefacts, and every
  other on-disk contract in this codebase (`Route`, `Control`) is itself a versioned pydantic model
  in spirit if not in name.

**Validated on write, and on read too.** Constructing `RouteFile` runs pydantic's own validation, so
`write_route_json` needs no hand-rolled checks (same principle `controls_csv.py` follows: let the
model raise). `RouteFile` also carries its own copy of `Route`'s order/legs invariant (order has at
least two entries, starts and ends on the hub, and each leg's `(from_id, to_id)` matches consecutive
`order` entries) rather than leaning on "it's built from an already-validated `Route`, so it can't
fail." That's true for `write_route_json` specifically, but `read_route_json` builds a `RouteFile`
from arbitrary bytes on disk — a hand-edited or corrupted `route.json` is not an already-validated
`Route` — so the invariant is checked again on read. This matches `controls_csv.py`'s own standing
precedent: "a controls file that is present must be correct" (SPEC F9) applies here too.

`write_route_json(path, route, run_config)` and `read_route_json(path)` are the round-trip pair;
`read_route_json` returns the `RouteFile`, not a `Route`, since the extra fields
(`cumulative_seconds`, `run_config`, `schema_version`) have no home on the frozen `Route` model.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rogaine.models import Route, RunConfig, SolverName

#: Current `RouteFile` schema version. Bump when the on-disk shape changes in a way old readers
#: could not tolerate.
SCHEMA_VERSION = 1


class LegRecord(BaseModel):
    """One leg of a route file: `Leg`'s own fields plus the running elapsed time at arrival."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_id: int = Field(ge=0)
    to_id: int = Field(ge=0)
    seconds: float = Field(ge=0.0)
    meters: float = Field(ge=0.0)
    polyline: list[tuple[int, int]] = Field(default_factory=list)
    cumulative_seconds: float = Field(
        ge=0.0, description="elapsed time from the hub through the end of this leg"
    )


class RouteFile(BaseModel):
    """The documented `route.json` schema (SPEC F15): a `Route` plus the `RunConfig` that produced
    it, with per-leg cumulative time filled in. See module docstring for the shape and validation
    rationale.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = SCHEMA_VERSION
    order: list[int]
    legs: list[LegRecord]
    total_seconds: float = Field(ge=0.0)
    total_meters: float = Field(ge=0.0)
    points: int = Field(ge=0)
    penalty: float = Field(ge=0.0)
    score: float
    solver: SolverName
    optimal: bool = False
    seed: int = 0
    run_config: RunConfig

    @model_validator(mode="after")
    def _legs_match_order(self) -> RouteFile:
        # Mirrors Route._legs_match_order (models.py, ADR-008) — see module docstring for why this
        # is re-checked here rather than trusted as unreachable.
        if len(self.order) < 2:
            raise ValueError("a route needs at least a departure from and a return to the hub")
        if self.order[0] != self.order[-1]:
            raise ValueError("a rogaine route starts and finishes at the hub (SPEC F14)")
        if len(self.legs) != len(self.order) - 1:
            raise ValueError(f"{len(self.order) - 1} legs expected, got {len(self.legs)}")
        pairs = zip(self.order, self.order[1:], strict=False)  # ragged on purpose: N-1 pairs
        for leg, (a, b) in zip(self.legs, pairs, strict=True):
            if (leg.from_id, leg.to_id) != (a, b):
                raise ValueError(f"leg {leg.from_id}->{leg.to_id} does not follow the visit order")
        return self


def _leg_records(route: Route) -> list[LegRecord]:
    records: list[LegRecord] = []
    cumulative = 0.0
    for leg in route.legs:
        cumulative += leg.seconds
        records.append(
            LegRecord(
                from_id=leg.from_id,
                to_id=leg.to_id,
                seconds=leg.seconds,
                meters=leg.meters,
                polyline=leg.polyline,
                cumulative_seconds=cumulative,
            )
        )
    return records


def write_route_json(path: Path, route: Route, run_config: RunConfig) -> None:
    """Write a `route.json`. Building `RouteFile` validates the whole document before any bytes
    hit disk — an invalid `route`/`run_config` pair raises instead of writing a broken file.
    """
    route_file = RouteFile(
        order=route.order,
        legs=_leg_records(route),
        total_seconds=route.total_seconds,
        total_meters=route.total_meters,
        points=route.points,
        penalty=route.penalty,
        score=route.score,
        solver=route.solver,
        optimal=route.optimal,
        seed=route.seed,
        run_config=run_config,
    )
    path.write_text(route_file.model_dump_json(indent=2) + "\n", encoding="utf-8")


def read_route_json(path: Path) -> RouteFile:
    """Load a `route.json`. Raises — a route file that is present must be correct, same standing
    rule as `controls_csv.read_controls` (SPEC F9's principle, applied here to SPEC F15).
    """
    return RouteFile.model_validate_json(path.read_text(encoding="utf-8"))
