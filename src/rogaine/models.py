"""Shared data contract for the rogaine route planner.

Frozen after M0 — changing anything here requires a new ADR and a coordinated update across the
three workstreams (ADR-008).

Two kinds of type live here, and the split is deliberate:

* **pydantic models** for everything that crosses a serialisation boundary — the route JSON, the
  controls CSV, the run parameters. These validate, and they round-trip.
* **frozen dataclasses** for everything that carries a numpy raster. Rasters are megabytes and are
  never serialised as JSON, so wrapping them in pydantic would buy validation overhead and nothing
  else. They validate their own shapes in ``__post_init__`` instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

# --------------------------------------------------------------------------------------------
# Terrain
# --------------------------------------------------------------------------------------------


class TerrainClass(StrEnum):
    """The terrain classes the segmenter can emit (SPEC F4).

    The names are the contract; their parameters (speed factor, passability, printed shade) live in
    ``config/default.toml`` and are loaded by :mod:`rogaine.config`, which asserts that the config
    covers exactly this enum.
    """

    OPEN_LAND = "open_land"
    ROUGH_OPEN = "rough_open"
    FOREST_RUNNABLE = "forest_runnable"
    VEG_SLOW_RUN = "veg_slow_run"
    VEG_WALK = "veg_walk"
    VEG_FIGHT = "veg_fight"
    MARSH = "marsh"
    WATER_SHALLOW = "water_shallow"
    WATER_UNCROSSABLE = "water_uncrossable"
    BARE_ROCK = "bare_rock"
    PAVED_AREA = "paved_area"
    ROAD = "road"
    VEHICLE_TRACK = "vehicle_track"
    FOOTPATH = "footpath"
    OUT_OF_BOUNDS = "out_of_bounds"
    CONTOUR = "contour"
    UNKNOWN = "unknown"


#: Label order for the ``uint8`` mask rasters. Append-only — the integer values are baked into
#: saved ``terrain.npz`` files and into the golden route fixtures, so reordering silently
#: invalidates both (SPEC F19).
TERRAIN_ORDER: tuple[TerrainClass, ...] = tuple(TerrainClass)

_LABEL_BY_CLASS = {cls: i for i, cls in enumerate(TERRAIN_ORDER)}


def terrain_label(cls: TerrainClass) -> int:
    """Integer label used for *cls* in mask rasters."""
    return _LABEL_BY_CLASS[cls]


def terrain_class(label: int) -> TerrainClass:
    """Inverse of :func:`terrain_label`."""
    return TERRAIN_ORDER[label]


# --------------------------------------------------------------------------------------------
# Serialisable models
# --------------------------------------------------------------------------------------------

ControlSource = Literal["detected", "manual"]
SolverName = Literal["exact", "heuristic"]


class Control(BaseModel):
    """One control point, in map pixel coordinates.

    ``points`` is ``None`` when the number could not be read and no rule supplied a value. That is
    a state the pipeline carries forward and reports, never one it papers over with a guess
    (ADR-009).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int = Field(ge=0)
    x: float = Field(ge=0.0, description="pixel column, sub-pixel precision allowed")
    y: float = Field(ge=0.0, description="pixel row, sub-pixel precision allowed")
    number: int | None = Field(default=None, ge=0)
    points: int | None = Field(default=None, ge=0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: ControlSource = "detected"
    is_hub: bool = Field(default=False, description="start and finish; exactly one per run")


class Leg(BaseModel):
    """One leg of a route: control to control, along the actual walked path."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_id: int = Field(ge=0)
    to_id: int = Field(ge=0)
    seconds: float = Field(ge=0.0)
    meters: float = Field(ge=0.0)
    polyline: list[tuple[int, int]] = Field(
        default_factory=list, description="pixel (x, y) points from `from_id` to `to_id`"
    )


class RunConfig(BaseModel):
    """The parameters of a single planning run — everything the user chooses per attempt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_speed_mps: float = Field(
        gt=0.0, description="speed on a road; every terrain scales off it"
    )
    time_limit_s: float = Field(gt=0.0)
    penalty_per_min: float = Field(default=1.0, ge=0.0)
    strategy: Literal["auto", "exact", "heuristic"] = "auto"
    heuristic_time_budget_s: float = Field(default=30.0, gt=0.0)
    alternatives: int = Field(default=3, ge=0)
    seed: int = 0


class Route(BaseModel):
    """A planned route and everything needed to judge it.

    ``optimal`` is only ever true when the exact solver proved it. The heuristic reports its score
    and lets ``bench`` measure the gap; it never claims optimality (ADR-003).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    order: list[int] = Field(
        description="control ids in visit order, starting and ending at the hub"
    )
    legs: list[Leg]
    total_seconds: float = Field(ge=0.0)
    total_meters: float = Field(ge=0.0)
    points: int = Field(ge=0)
    penalty: float = Field(ge=0.0)
    score: float
    solver: SolverName
    optimal: bool = False
    seed: int = 0

    @model_validator(mode="after")
    def _legs_match_order(self) -> Route:
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


# --------------------------------------------------------------------------------------------
# Raster-carrying structures
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class MapContext:
    """A loaded map raster together with the scale that gives it meaning."""

    image: np.ndarray  # (H, W, 3) uint8, RGB
    meters_per_pixel: float
    source: Path
    page: int = 0

    def __post_init__(self) -> None:
        if self.image.ndim != 3 or self.image.shape[2] != 3:
            raise ValueError(f"expected an (H, W, 3) RGB image, got shape {self.image.shape}")
        if self.image.dtype != np.uint8:
            raise ValueError(f"expected uint8 pixels, got {self.image.dtype}")
        if not self.meters_per_pixel > 0:
            raise ValueError(f"meters_per_pixel must be positive, got {self.meters_per_pixel}")

    @property
    def height(self) -> int:
        return int(self.image.shape[0])

    @property
    def width(self) -> int:
        return int(self.image.shape[1])


@dataclass(frozen=True)
class TerrainMap:
    """Per-pixel terrain classification plus the contour density that stands in for slope."""

    labels: np.ndarray  # (H, W) uint8, values index TERRAIN_ORDER
    contour_density: np.ndarray  # (H, W) float32 in [0, 1]
    meters_per_pixel: float

    def __post_init__(self) -> None:
        if self.labels.ndim != 2:
            raise ValueError(f"labels must be 2-D, got shape {self.labels.shape}")
        if self.labels.dtype != np.uint8:
            raise ValueError(f"labels must be uint8, got {self.labels.dtype}")
        if self.labels.max(initial=0) >= len(TERRAIN_ORDER):
            raise ValueError("labels contain a value outside TERRAIN_ORDER")
        if self.contour_density.shape != self.labels.shape:
            raise ValueError("contour_density must have the same shape as labels")

    @property
    def shape(self) -> tuple[int, int]:
        return (int(self.labels.shape[0]), int(self.labels.shape[1]))


@dataclass(frozen=True)
class CostField:
    """Seconds needed to cross one pixel, for one runner at one speed."""

    seconds_per_pixel: np.ndarray  # (H, W) float32
    passable: np.ndarray  # (H, W) bool
    meters_per_pixel: float
    base_speed_mps: float

    def __post_init__(self) -> None:
        if self.seconds_per_pixel.shape != self.passable.shape:
            raise ValueError("seconds_per_pixel and passable must have the same shape")
        if not np.isfinite(self.seconds_per_pixel[self.passable]).all():
            raise ValueError("passable pixels must have a finite cost")


@dataclass(frozen=True)
class TravelMatrix:
    """Travel time and distance between every pair of controls, plus the paths behind them.

    Unreachable pairs hold ``inf``, never zero — a zero would read as "free" and the solver would
    happily route through it.
    """

    control_ids: tuple[int, ...]
    seconds: np.ndarray  # (N, N) float64
    meters: np.ndarray  # (N, N) float64
    paths: dict[tuple[int, int], np.ndarray]  # (from_id, to_id) -> (K, 2) int32 pixel polyline

    def __post_init__(self) -> None:
        n = len(self.control_ids)
        if self.seconds.shape != (n, n) or self.meters.shape != (n, n):
            raise ValueError(f"expected {n}x{n} matrices for {n} controls")
        if len(set(self.control_ids)) != n:
            raise ValueError("control_ids must be unique")

    def index_of(self, control_id: int) -> int:
        return self.control_ids.index(control_id)

    def time_between(self, from_id: int, to_id: int) -> float:
        return float(self.seconds[self.index_of(from_id), self.index_of(to_id)])
