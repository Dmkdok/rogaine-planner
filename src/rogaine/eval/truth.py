"""The `truth.toml` schema (ADR-042, F25): what a labeller says is on a map.

Lives at `data/maps/<map>/truth.toml` (gitignored, ADR-010). All coordinates are map pixels,
`x` = column, `y` = row, the same convention as `rogaine.models.Control`.

```toml
[hub]
x = 812.0
y = 640.5

[[controls]]
number = 41
x = 300.0
y = 220.0

[[barrier_probes]]            # a -> b must not cross the polyline `barrier`
a = [100.0, 400.0]
b = [500.0, 400.0]
barrier = [[300.0, 350.0], [300.0, 450.0]]

[[class_probes]]
x = 120.0
y = 90.0
expected = "marsh"            # a key of FAMILIES
```

Class families map onto `rogaine.models.TerrainClass`; a probe passes when the segmenter's class
at the point is in the expected family. The coarse family `linear` accepts any of road / track /
footpath. Fences, banks and walls are not `TerrainClass` members yet (ADR-048), so there is no
family for them; add one here when the enum grows.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from rogaine.models import TerrainClass

T = TerrainClass

FAMILIES: dict[str, frozenset[TerrainClass]] = {
    "open": frozenset({T.OPEN_LAND, T.ROUGH_OPEN}),
    "forest": frozenset({T.FOREST_RUNNABLE}),
    "vegetation": frozenset({T.VEG_SLOW_RUN, T.VEG_WALK, T.VEG_FIGHT}),
    "marsh": frozenset({T.MARSH}),
    "water": frozenset({T.WATER_SHALLOW}),
    "impassable": frozenset({T.WATER_UNCROSSABLE}),
    "rock": frozenset({T.BARE_ROCK}),
    "paved": frozenset({T.PAVED_AREA}),
    "road": frozenset({T.ROAD}),
    "track": frozenset({T.VEHICLE_TRACK}),
    "footpath": frozenset({T.FOOTPATH}),
    "linear": frozenset({T.ROAD, T.VEHICLE_TRACK, T.FOOTPATH}),
    "out_of_bounds": frozenset({T.OUT_OF_BOUNDS}),
}

Point = tuple[float, float]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TruthPoint(_Frozen):
    x: float = Field(ge=0.0)
    y: float = Field(ge=0.0)


class TruthControl(TruthPoint):
    number: int | None = Field(default=None, ge=0, description="None = number not legible")


class BarrierProbe(_Frozen):
    a: Point
    b: Point
    barrier: tuple[Point, ...] = Field(min_length=2)


class ClassProbe(TruthPoint):
    expected: str

    @field_validator("expected")
    @classmethod
    def _known_family(cls, v: str) -> str:
        if v not in FAMILIES:
            raise ValueError(f"unknown class family {v!r}; expected one of {sorted(FAMILIES)}")
        return v


class Truth(_Frozen):
    hub: TruthPoint | None = None
    controls: tuple[TruthControl, ...] = ()
    barrier_probes: tuple[BarrierProbe, ...] = ()
    class_probes: tuple[ClassProbe, ...] = ()


def load_truth(path: Path) -> Truth:
    """Parse and validate a `truth.toml`. Raises `ValueError` (incl. pydantic's) on bad input."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{path}: invalid TOML: {exc}") from exc
    return Truth.model_validate(data)


def _num(v: float) -> str:
    return repr(float(v))


def _pt(p: Point) -> str:
    return f"[{_num(p[0])}, {_num(p[1])}]"


def dump_truth(truth: Truth) -> str:
    """Serialise *truth* to `truth.toml` text; `load_truth(dump)` round-trips."""
    out: list[str] = []
    if truth.hub is not None:
        out += ["[hub]", f"x = {_num(truth.hub.x)}", f"y = {_num(truth.hub.y)}", ""]
    for c in truth.controls:
        out += ["[[controls]]"]
        if c.number is not None:
            out += [f"number = {c.number}"]
        out += [f"x = {_num(c.x)}", f"y = {_num(c.y)}", ""]
    for p in truth.barrier_probes:
        out += [
            "[[barrier_probes]]",
            f"a = {_pt(p.a)}",
            f"b = {_pt(p.b)}",
            "barrier = [" + ", ".join(_pt(q) for q in p.barrier) + "]",
            "",
        ]
    for q in truth.class_probes:
        out += [
            "[[class_probes]]",
            f"x = {_num(q.x)}",
            f"y = {_num(q.y)}",
            f'expected = "{q.expected}"',
            "",
        ]
    return "\n".join(out)
