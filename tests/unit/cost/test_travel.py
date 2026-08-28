"""Tests for T032's travel matrix and path reconstruction (F11).

DoD: `scipy.sparse.csgraph.dijkstra` from each control; matrix symmetric within tolerance; per-pair
polylines reconstructed from predecessors and simplified for rendering; unreachable pairs marked
infinite, not zero; 60 controls on a full-size map in under 60 s.
"""

from __future__ import annotations

import math
import time

import numpy as np
import pytest

from rogaine.config import load_config
from rogaine.cost.graph import GridGraph, build_grid_graph
from rogaine.cost.travel import build_travel_matrix
from rogaine.models import Control, CostField

_SQRT2 = math.sqrt(2.0)


def _cost_field(seconds_per_pixel: np.ndarray, passable: np.ndarray, mpp: float = 1.0) -> CostField:
    return CostField(
        seconds_per_pixel=seconds_per_pixel.astype(np.float32),
        passable=passable.astype(bool),
        meters_per_pixel=mpp,
        base_speed_mps=1.0,
    )


def _uniform_graph(
    shape: tuple[int, int], rate: float, mpp: float, downsample: int = 1
) -> GridGraph:
    sp = np.full(shape, rate, dtype=np.float32)
    passable = np.ones(shape, dtype=bool)
    cfg = load_config(overrides={"graph": {"downsample": downsample}})
    return build_grid_graph(_cost_field(sp, passable, mpp=mpp), cfg)


class TestHandCheckedDiagonal:
    """3x3 uniform grid, downsample=1: two controls at opposite corners. The time-optimal path is
    the two-hop diagonal (0,0)->(1,1)->(2,2) -- cheaper than any four-hop orthogonal route -- so
    both `seconds` and `meters` can be hand-computed exactly from the edge-weight formula
    (`cost/graph.py`'s module docstring: `spacing * avg(rate_u, rate_v)`, spacing `sqrt(2)` for a
    diagonal hop between uniform-rate blocks).
    """

    RATE = 2.0
    MPP = 0.5

    @pytest.fixture()
    def matrix(self):
        graph = _uniform_graph((3, 3), self.RATE, self.MPP, downsample=1)
        controls = [Control(id=0, x=0, y=0), Control(id=1, x=2, y=2)]
        return build_travel_matrix(controls, graph, meters_per_pixel=self.MPP)

    def test_seconds_matches_two_hop_diagonal(self, matrix):
        expected = 2 * _SQRT2 * self.RATE
        assert matrix.seconds[0, 1] == pytest.approx(expected)
        assert matrix.seconds[1, 0] == pytest.approx(expected)

    def test_meters_matches_two_hop_diagonal_pixel_length(self, matrix):
        expected = 2 * _SQRT2 * self.MPP
        assert matrix.meters[0, 1] == pytest.approx(expected)
        assert matrix.meters[1, 0] == pytest.approx(expected)

    def test_self_pairs_are_zero_and_absent_from_paths(self, matrix):
        assert matrix.seconds[0, 0] == 0.0
        assert matrix.meters[0, 0] == 0.0
        assert matrix.seconds[1, 1] == 0.0
        assert matrix.meters[1, 1] == 0.0
        assert (0, 0) not in matrix.paths
        assert (1, 1) not in matrix.paths

    def test_path_endpoints_and_mirrored_reverse(self, matrix):
        path = matrix.paths[(0, 1)]
        assert tuple(int(v) for v in path[0]) == (0, 0)
        assert tuple(int(v) for v in path[-1]) == (2, 2)
        reverse = matrix.paths[(1, 0)]
        assert np.array_equal(reverse, path[::-1])


class TestPolylineSimplification:
    """A perfectly straight 21-pixel corridor: the raw reconstructed chain has 21 points (one per
    pixel at downsample=1), but a straight line simplifies to just its two endpoints."""

    @pytest.fixture()
    def matrix(self):
        graph = _uniform_graph((1, 21), rate=1.0, mpp=1.0, downsample=1)
        controls = [Control(id=5, x=0, y=0), Control(id=9, x=20, y=0)]
        return build_travel_matrix(controls, graph, meters_per_pixel=1.0)

    def test_simplified_polyline_has_fewer_points_than_raw_chain(self, matrix):
        path = matrix.paths[(5, 9)]
        assert len(path) < 21
        assert len(path) == 2  # collinear chain simplifies to exactly its two endpoints

    def test_endpoints_preserved(self, matrix):
        path = matrix.paths[(5, 9)]
        assert tuple(int(v) for v in path[0]) == (0, 0)
        assert tuple(int(v) for v in path[-1]) == (20, 0)

    def test_seconds_and_meters_reflect_raw_chain_not_simplified(self, matrix):
        # 20 orthogonal hops at rate 1.0 -> 20.0s; mpp=1.0 -> 20.0m. Simplification never touches
        # these numbers, even though the stored polyline collapses from 21 points to 2.
        assert matrix.seconds[0, 1] == pytest.approx(20.0)
        assert matrix.meters[0, 1] == pytest.approx(20.0)


class TestUnreachablePair:
    """Two controls in disconnected regions under `strict_impassable=True`: `seconds`/`meters`
    read `+inf`, never `0`, with no crash; the pair gets no `paths` entry at all."""

    @pytest.fixture()
    def matrix(self):
        # 1x5 row with an impassable cell at column 2, splitting it into two islands; in a
        # single-row 8-connected grid a gap of one cell severs every edge across it.
        sp = np.full((1, 5), 1.0, dtype=np.float32)
        passable = np.ones((1, 5), dtype=bool)
        passable[0, 2] = False
        cfg = load_config(overrides={"graph": {"downsample": 1, "strict_impassable": True}})
        graph = build_grid_graph(_cost_field(sp, passable, mpp=1.0), cfg)
        controls = [Control(id=1, x=0, y=0), Control(id=2, x=4, y=0)]
        return build_travel_matrix(controls, graph, meters_per_pixel=1.0)

    def test_seconds_is_infinite_not_zero(self, matrix):
        assert math.isinf(matrix.seconds[0, 1])
        assert matrix.seconds[0, 1] > 0

    def test_meters_is_infinite_not_zero(self, matrix):
        assert math.isinf(matrix.meters[0, 1])
        assert matrix.meters[0, 1] > 0

    def test_no_paths_entry_for_unreachable_pair(self, matrix):
        assert (1, 2) not in matrix.paths
        assert (2, 1) not in matrix.paths


class TestSymmetryWithinTolerance:
    """Several controls on a nontrivial random passable grid: `seconds` comes from independent
    per-source Dijkstra sweeps, so it should match its own transpose within floating-point
    tolerance, not exactly -- see the module's design-decision-3 discussion for why this is not
    forced. `meters` is symmetric by construction (design decision 4: reconstructed once per
    unordered pair, mirrored for the reverse direction) but is checked the same way for
    consistency.
    """

    @pytest.fixture()
    def matrix(self):
        rng = np.random.default_rng(20260829)
        h, w = 30, 30
        sp = rng.uniform(0.5, 3.0, size=(h, w)).astype(np.float32)
        passable = np.ones((h, w), dtype=bool)
        cfg = load_config(overrides={"graph": {"downsample": 1}})
        graph = build_grid_graph(_cost_field(sp, passable, mpp=0.75), cfg)
        rng2 = np.random.default_rng(7)
        controls = [
            Control(id=i, x=float(rng2.integers(0, w)), y=float(rng2.integers(0, h)))
            for i in range(6)
        ]
        return build_travel_matrix(controls, graph, meters_per_pixel=0.75)

    def test_seconds_symmetric_within_tolerance(self, matrix):
        # float64 sums of independently-ordered edge traversals differ only at the level of
        # summation-order rounding; rtol=1e-7 comfortably covers that while still catching a
        # genuinely asymmetric (e.g. accidentally directed) edge, which would show up orders of
        # magnitude larger.
        np.testing.assert_allclose(matrix.seconds, matrix.seconds.T, rtol=1e-7, atol=1e-6)

    def test_meters_symmetric_within_tolerance(self, matrix):
        np.testing.assert_allclose(matrix.meters, matrix.meters.T, rtol=1e-7, atol=1e-6)


class TestInputValidation:
    def test_non_positive_meters_per_pixel_rejected(self):
        graph = _uniform_graph((2, 2), rate=1.0, mpp=1.0, downsample=1)
        controls = [Control(id=0, x=0, y=0), Control(id=1, x=1, y=1)]
        with pytest.raises(ValueError):
            build_travel_matrix(controls, graph, meters_per_pixel=0.0)


@pytest.mark.perf
class TestPerformance:
    """SPEC F11's budget: 60 controls (+ the hub = 61) on a full-size 4000x3000 map at
    downsample=4, under 60 s -- for `build_travel_matrix` alone, not the vision + T030 pipeline.
    Mirrors `test_graph.py::TestPerformance`'s own precedent for isolating one stage's budget: an
    equivalent-size synthetic `CostField` built directly with numpy, then `build_grid_graph`, then
    this module's own function timed in isolation.
    """

    def test_61_controls_full_size_under_60s(self) -> None:
        rng = np.random.default_rng(20260829)
        h, w = 3000, 4000
        sp = rng.uniform(0.1, 5.0, size=(h, w)).astype(np.float32)
        passable = rng.random((h, w)) > 0.1  # ~90% passable, ~10% impassable islands
        sp[~passable] = np.inf
        cost_field = _cost_field(sp, passable, mpp=2.54)
        cfg = load_config(overrides={"graph": {"downsample": 4}})
        graph = build_grid_graph(cost_field, cfg)

        # 61 distinct random in-bounds pixel positions -- not guaranteed passable, matching
        # T031's own precedent; some legitimately unreachable pairs in this timing run are fine,
        # this budget is about wall time, not connectivity.
        controls = [
            Control(
                id=i,
                x=float(rng.uniform(0, w - 1)),
                y=float(rng.uniform(0, h - 1)),
                is_hub=(i == 0),
            )
            for i in range(61)
        ]

        start = time.perf_counter()
        matrix = build_travel_matrix(controls, graph, meters_per_pixel=2.54, config=cfg)
        elapsed = time.perf_counter() - start

        assert len(matrix.control_ids) == 61
        assert elapsed < 60.0, f"build_travel_matrix took {elapsed:.1f}s for 61 controls"
