"""Score the pipeline against a `Truth` (ADR-042, F25). A thin scorer: run the existing
detection / OCR / segmentation / graph entry points, compare to truth, report counts.

The scoring functions are pure (they take detections, labels or paths) so they can be tested
without a raster; `evaluate_map` is the only place that runs the pipeline.
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, fields
from itertools import pairwise
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from rogaine.config import AppConfig
from rogaine.cost.field import compute_cost_field
from rogaine.cost.graph import build_grid_graph
from rogaine.cost.travel import build_travel_matrix
from rogaine.eval.truth import FAMILIES, BarrierProbe, ClassProbe, Point, Truth, TruthControl
from rogaine.models import TERRAIN_ORDER, Control, TerrainMap
from rogaine.vision.controls import detect_controls
from rogaine.vision.ocr import read_control_numbers
from rogaine.vision.segment import segment

#: A detection matches a truth circle when its centre is within this fraction of the radius.
MATCH_RADIUS_FRACTION = 0.5
#: Runner speed for the barrier-probe cost field, m/s (same default as `rogaine plan`).
PROBE_SPEED_MPS = 2.0


@dataclass
class Metrics:
    """Raw counts; ratios are derived so per-map rows sum exactly into the total."""

    truth_circles: int = 0
    detected_circles: int = 0
    matched_circles: int = 0
    numbers_correct: int = 0
    numbers_wrong: int = 0
    numbers_unread: int = 0
    hub_truth: int = 0
    hub_found: int = 0
    class_probes: int = 0
    class_correct: int = 0
    barrier_probes: int = 0
    barrier_unreachable: int = 0
    barrier_crossed: int = 0  # probes with at least one crossing
    barrier_crossings: int = 0  # total path segments that cross a barrier

    @property
    def recall(self) -> float | None:
        return self.matched_circles / self.truth_circles if self.truth_circles else None

    @property
    def precision(self) -> float | None:
        return self.matched_circles / self.detected_circles if self.detected_circles else None

    @property
    def class_accuracy(self) -> float | None:
        return self.class_correct / self.class_probes if self.class_probes else None

    def __add__(self, other: Metrics) -> Metrics:
        return Metrics(
            **{f.name: getattr(self, f.name) + getattr(other, f.name) for f in fields(self)}
        )


def match_circles(
    detected: list[Control], truth: tuple[TruthControl, ...], radius_px: float
) -> list[tuple[Control, TruthControl]]:
    """Greedy one-to-one matching, nearest pairs first, within `MATCH_RADIUS_FRACTION * radius`."""
    tol = MATCH_RADIUS_FRACTION * radius_px
    pairs = sorted(
        (math.hypot(d.x - t.x, d.y - t.y), i, j)
        for i, d in enumerate(detected)
        for j, t in enumerate(truth)
    )
    used_d: set[int] = set()
    used_t: set[int] = set()
    out: list[tuple[Control, TruthControl]] = []
    for dist, i, j in pairs:
        if dist > tol:
            break
        if i in used_d or j in used_t:
            continue
        used_d.add(i)
        used_t.add(j)
        out.append((detected[i], truth[j]))
    return out


def score_controls(detected: list[Control], truth: Truth, radius_px: float) -> Metrics:
    """Circle recall/precision, number outcomes and the hub hit (hub is not a circle)."""
    circles = [c for c in detected if not c.is_hub]
    m = Metrics(truth_circles=len(truth.controls), detected_circles=len(circles))
    for det, tru in match_circles(circles, truth.controls, radius_px):
        m.matched_circles += 1
        if tru.number is None:
            continue
        if det.number is None:
            m.numbers_unread += 1
        elif det.number == tru.number:
            m.numbers_correct += 1
        else:
            m.numbers_wrong += 1
    if truth.hub is not None:
        hub = truth.hub
        m.hub_truth = 1
        m.hub_found = int(
            any(c.is_hub and math.hypot(c.x - hub.x, c.y - hub.y) <= radius_px for c in detected)
        )
    return m


def score_class_probes(labels: np.ndarray, probes: tuple[ClassProbe, ...]) -> tuple[int, int]:
    """(correct, total). A probe outside the raster counts as wrong."""
    h, w = labels.shape
    correct = 0
    for p in probes:
        x, y = math.floor(p.x), math.floor(p.y)
        if 0 <= x < w and 0 <= y < h and TERRAIN_ORDER[int(labels[y, x])] in FAMILIES[p.expected]:
            correct += 1
    return correct, len(probes)


def _ccw(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: Point, b: Point, c: Point) -> bool:
    return min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= c[1] <= max(a[1], b[1])


def segments_intersect(p1: Point, p2: Point, q1: Point, q2: Point) -> bool:
    """Closed-segment intersection (touching counts)."""
    d1, d2 = _ccw(q1, q2, p1), _ccw(q1, q2, p2)
    d3, d4 = _ccw(p1, p2, q1), _ccw(p1, p2, q2)
    if ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4)):
        return True
    return (
        (d1 == 0 and _on_segment(q1, q2, p1))
        or (d2 == 0 and _on_segment(q1, q2, p2))
        or (d3 == 0 and _on_segment(p1, p2, q1))
        or (d4 == 0 and _on_segment(p1, p2, q2))
    )


def count_crossings(path: list[Point], barrier: tuple[Point, ...]) -> int:
    """Number of path segments that intersect the barrier polyline."""
    return sum(
        any(segments_intersect(p, q, barrier[k], barrier[k + 1]) for k in range(len(barrier) - 1))
        for p, q in pairwise(path)
    )


def score_barrier_probes(
    probes: tuple[BarrierProbe, ...], terrain: TerrainMap, mpp: float, config: AppConfig
) -> Metrics:
    """Shortest path a->b on the real cost graph, intersected with each barrier polyline."""
    m = Metrics(barrier_probes=len(probes))
    if not probes:
        return m
    graph = build_grid_graph(compute_cost_field(terrain, PROBE_SPEED_MPS, config), config)
    for p in probes:
        ends = [Control(id=0, x=p.a[0], y=p.a[1]), Control(id=1, x=p.b[0], y=p.b[1])]
        try:
            matrix = build_travel_matrix(ends, graph, mpp, config)
        except ValueError:  # endpoint outside the raster
            m.barrier_unreachable += 1
            continue
        path = matrix.paths.get((0, 1))
        if path is None:
            m.barrier_unreachable += 1
            continue
        pts: list[Point] = [p.a, *((float(x), float(y)) for x, y in path), p.b]
        n = count_crossings(pts, p.barrier)
        m.barrier_crossings += n
        m.barrier_crossed += int(n > 0)
    return m


def evaluate_map(
    image: np.ndarray, dpi: float, mpp: float, truth: Truth, config: AppConfig
) -> Metrics:
    """Run detection, number reading and (if probes exist) segmentation + routing, then score."""
    controls = detect_controls(image, dpi, config)
    controls, _flags = read_control_numbers(image, controls, dpi, config)
    r_lo, r_hi = config.detector.circle_radius_px(dpi)
    m = score_controls(controls, truth, (r_lo + r_hi) / 2.0)
    if truth.class_probes or truth.barrier_probes:
        terrain = segment(image, dpi, mpp, config)
        m.class_correct, m.class_probes = score_class_probes(terrain.labels, truth.class_probes)
        b = score_barrier_probes(truth.barrier_probes, terrain, mpp, config)
        m.barrier_probes = b.barrier_probes
        m.barrier_unreachable = b.barrier_unreachable
        m.barrier_crossed = b.barrier_crossed
        m.barrier_crossings = b.barrier_crossings
    return m


def with_vlm(config: AppConfig, mode: str) -> AppConfig:
    """`off` forces the OCR VLM fallback off; `auto` enables it (it still stays inert without a
    key / reachable local server, see `OcrFallbackSettings`)."""
    if mode not in ("off", "auto"):
        raise ValueError(f"--vlm must be 'off' or 'auto', got {mode!r}")
    fallback = config.ocr_fallback.model_copy(update={"enabled": mode == "auto"})
    return config.model_copy(update={"ocr_fallback": fallback})


class BenchSet(BaseModel):
    """`data/bench.toml`: `maps = ["id", ...]`, plus an optional `root` (default: `maps/` next to
    the file)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    maps: tuple[str, ...] = Field(min_length=1)
    root: Path | None = None


def load_bench_set(path: Path) -> tuple[Path, tuple[str, ...]]:
    """Return `(maps_root, map_ids)` for a bench set file."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{path}: invalid TOML: {exc}") from exc
    bench = BenchSet.model_validate(data)
    root = bench.root if bench.root is not None else Path("maps")
    return (root if root.is_absolute() else path.parent / root), bench.maps
