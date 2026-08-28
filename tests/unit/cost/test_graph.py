"""8-connected CSR grid graph over a CostField (T031, F11 setup for T032).

DoD: 8-connected CSR graph with sqrt(2) diagonals and configurable `graph_downsample`; node/pixel
mapping is exact both ways; a 4000x3000 map at downsample 4 builds in under 15 s and stays under
1 GB.
"""

from __future__ import annotations

import time
import tracemalloc

import numpy as np
import pytest

from rogaine.config import load_config
from rogaine.cost.graph import build_grid_graph
from rogaine.models import CostField

_SQRT2 = 2.0**0.5


def _cost_field(seconds_per_pixel: np.ndarray, passable: np.ndarray, mpp: float = 1.0) -> CostField:
    return CostField(
        seconds_per_pixel=seconds_per_pixel.astype(np.float32),
        passable=passable.astype(bool),
        meters_per_pixel=mpp,
        base_speed_mps=1.0,
    )


class TestDownsampleOneConnectivity:
    """A uniform 3x3 field, downsample=1, so node == pixel and edge weights can be checked
    directly against the formula in the module docstring: `spacing * avg(rate_u, rate_v)`."""

    RATE = 2.0

    @pytest.fixture()
    def graph(self):
        sp = np.full((3, 3), self.RATE, dtype=np.float32)
        passable = np.ones((3, 3), dtype=bool)
        cfg = load_config(overrides={"graph": {"downsample": 1, "strict_impassable": True}})
        return build_grid_graph(_cost_field(sp, passable), cfg)

    def test_node_count_and_shape(self, graph) -> None:
        assert graph.n_nodes == 9
        assert graph.shape == (3, 3)
        assert graph.block_shape == (3, 3)

    def test_orthogonal_weight_equals_downsample_times_average_rate(self, graph) -> None:
        dense = graph.csr.toarray()
        # node 0 = (row0,col0), node 1 = (row0,col1): orthogonal right neighbour.
        assert dense[0, 1] == pytest.approx(1.0 * self.RATE)
        assert dense[1, 0] == pytest.approx(1.0 * self.RATE)  # symmetric

    def test_diagonal_weight_is_sqrt2_times_orthogonal(self, graph) -> None:
        dense = graph.csr.toarray()
        # node 0 = (row0,col0), node 4 = (row1,col1): diagonal neighbour.
        orthogonal = dense[0, 1]
        diagonal = dense[0, 4]
        assert diagonal == pytest.approx(orthogonal * _SQRT2)

    def test_corner_has_three_neighbours_interior_has_eight(self, graph) -> None:
        dense = graph.csr.toarray()
        corner_degree = (dense[0] != 0).sum()
        center_degree = (dense[4] != 0).sum()  # node 4 = (row1,col1), the interior pixel
        assert corner_degree == 3
        assert center_degree == 8

    def test_graph_is_symmetric(self, graph) -> None:
        dense = graph.csr.toarray()
        np.testing.assert_allclose(dense, dense.T)

    def test_heterogeneous_rates_average_correctly(self) -> None:
        sp = np.array([[1.0, 1.0], [3.0, 3.0]], dtype=np.float32)
        passable = np.ones((2, 2), dtype=bool)
        cfg = load_config(overrides={"graph": {"downsample": 1, "strict_impassable": True}})
        graph = build_grid_graph(_cost_field(sp, passable), cfg)
        dense = graph.csr.toarray()

        right = dense[graph.pixel_to_node(0, 0), graph.pixel_to_node(1, 0)]
        down = dense[graph.pixel_to_node(0, 0), graph.pixel_to_node(0, 1)]
        diag = dense[graph.pixel_to_node(0, 0), graph.pixel_to_node(1, 1)]

        assert right == pytest.approx(1.0 * (1.0 + 1.0) / 2)
        assert down == pytest.approx(1.0 * (1.0 + 3.0) / 2)
        assert diag == pytest.approx(_SQRT2 * (1.0 + 3.0) / 2)


class TestStrictImpassable:
    """One impassable pixel in the middle of an otherwise uniform passable field."""

    def _fields(self):
        sp = np.full((3, 3), 2.0, dtype=np.float32)
        passable = np.ones((3, 3), dtype=bool)
        sp[1, 1] = np.inf
        passable[1, 1] = False
        return sp, passable

    def test_strict_true_gives_impassable_node_zero_degree(self) -> None:
        sp, passable = self._fields()
        cfg = load_config(overrides={"graph": {"downsample": 1, "strict_impassable": True}})
        graph = build_grid_graph(_cost_field(sp, passable), cfg)

        center = graph.pixel_to_node(1, 1)
        dense = graph.csr.toarray()
        assert (dense[center] != 0).sum() == 0
        assert (dense[:, center] != 0).sum() == 0
        # the node still exists -- node numbering doesn't shift with strict_impassable.
        assert graph.n_nodes == 9

    def test_strict_false_gives_finite_high_edges_never_zero_never_ordinary(self) -> None:
        sp, passable = self._fields()
        cfg = load_config(
            overrides={
                "graph": {
                    "downsample": 1,
                    "strict_impassable": False,
                    "impassable_cost_multiplier": 5.0,
                }
            }
        )
        graph = build_grid_graph(_cost_field(sp, passable), cfg)

        center = graph.pixel_to_node(1, 1)
        neighbour = graph.pixel_to_node(0, 1)  # an ordinary passable neighbour, rate 2.0
        dense = graph.csr.toarray()

        edge = dense[neighbour, center]
        ordinary_edge = dense[graph.pixel_to_node(0, 0), graph.pixel_to_node(1, 0)]

        assert np.isfinite(edge)
        assert edge != 0.0
        assert edge != pytest.approx(ordinary_edge)
        # reference passable rate is 2.0 everywhere else; effective impassable rate is 5*2=10;
        # edge weight = 1 * (2 + 10) / 2 = 6.0, per the module docstring's formula.
        assert edge == pytest.approx(6.0)
        assert (dense[center] != 0).sum() == 8  # now reachable from every neighbour


class TestDownsampleAggregation:
    """downsample=2 over a 4x4 field: block (0,0) is 3 passable pixels (rates 2, 4, 6) and one
    impassable pixel; block (0,1) is fully impassable."""

    @pytest.fixture()
    def graph(self):
        sp = np.zeros((4, 4), dtype=np.float32)
        passable = np.zeros((4, 4), dtype=bool)

        sp[0, 0], passable[0, 0] = 2.0, True
        sp[0, 1], passable[0, 1] = 4.0, True
        sp[1, 0], passable[1, 0] = 6.0, True
        sp[1, 1], passable[1, 1] = np.inf, False  # block (0,0)'s one impassable pixel

        sp[0, 2:4] = np.inf
        sp[1, 2:4] = np.inf  # block (0,1): fully impassable

        sp[2:, :] = 1.0
        passable[2:, :] = True

        cfg = load_config(overrides={"graph": {"downsample": 2, "strict_impassable": True}})
        return build_grid_graph(_cost_field(sp, passable), cfg)

    def test_block_shape(self, graph) -> None:
        assert graph.block_shape == (2, 2)
        assert graph.n_nodes == 4

    def test_partially_impassable_block_is_passable_with_mean_rate_over_passable_pixels(
        self, graph
    ) -> None:
        assert graph.block_passable[0, 0]
        assert graph.block_seconds_per_pixel[0, 0] == pytest.approx((2.0 + 4.0 + 6.0) / 3)

    def test_fully_impassable_block_is_impassable(self, graph) -> None:
        assert not graph.block_passable[0, 1]
        assert np.isinf(graph.block_seconds_per_pixel[0, 1])

    def test_edge_spacing_uses_downsample_as_pixel_distance(self, graph) -> None:
        # block (0,0) and block (1,0) (rate 1.0) are orthogonal neighbours in the block grid;
        # spacing between block centres is `downsample` = 2 pixels.
        dense = graph.csr.toarray()
        node00 = 0 * graph.block_shape[1] + 0
        node10 = 1 * graph.block_shape[1] + 0
        expected = 2.0 * (((2.0 + 4.0 + 6.0) / 3) + 1.0) / 2
        assert dense[node00, node10] == pytest.approx(expected)


class TestNodePixelRoundTrip:
    def test_exact_round_trip_every_node_downsample_one(self) -> None:
        sp = np.ones((5, 4), dtype=np.float32)
        passable = np.ones((5, 4), dtype=bool)
        cfg = load_config(overrides={"graph": {"downsample": 1, "strict_impassable": True}})
        graph = build_grid_graph(_cost_field(sp, passable), cfg)

        for node in range(graph.n_nodes):
            x, y = graph.node_to_pixel(node)
            assert graph.pixel_to_node(x, y) == node
        # at downsample=1 pixel -> node -> pixel also round-trips exactly (node == pixel).
        for y in range(5):
            for x in range(4):
                node = graph.pixel_to_node(x, y)
                assert graph.node_to_pixel(node) == (x, y)

    def test_exact_round_trip_every_node_downsample_greater_than_one_irregular_size(self) -> None:
        # 7x5 doesn't divide evenly by downsample=3 -- exercises the partial trailing block.
        h, w, ds = 7, 5, 3
        sp = np.ones((h, w), dtype=np.float32)
        passable = np.ones((h, w), dtype=bool)
        cfg = load_config(overrides={"graph": {"downsample": ds, "strict_impassable": True}})
        graph = build_grid_graph(_cost_field(sp, passable), cfg)

        assert graph.block_shape == (3, 2)  # ceil(7/3)=3, ceil(5/3)=2
        for node in range(graph.n_nodes):
            x, y = graph.node_to_pixel(node)
            assert graph.pixel_to_node(x, y) == node

    def test_node_to_pixel_returns_block_top_left(self) -> None:
        h, w, ds = 6, 6, 2
        sp = np.ones((h, w), dtype=np.float32)
        passable = np.ones((h, w), dtype=bool)
        cfg = load_config(overrides={"graph": {"downsample": ds, "strict_impassable": True}})
        graph = build_grid_graph(_cost_field(sp, passable), cfg)

        # node for block row=1, col=2 -> pixel (x=4, y=2)
        node = 1 * graph.block_shape[1] + 2
        assert graph.node_to_pixel(node) == (4, 2)

    def test_pixel_to_node_floors_subpixel_coordinates(self) -> None:
        h, w, ds = 6, 6, 2
        sp = np.ones((h, w), dtype=np.float32)
        passable = np.ones((h, w), dtype=bool)
        cfg = load_config(overrides={"graph": {"downsample": ds, "strict_impassable": True}})
        graph = build_grid_graph(_cost_field(sp, passable), cfg)

        # 1.9 floors to pixel 1 (block 0), not round()'s 2 (block 1) -- floor is the documented
        # rule.
        assert graph.pixel_to_node(1.9, 1.9) == graph.pixel_to_node(1, 1)
        assert graph.pixel_to_node(1.9, 1.9) != graph.pixel_to_node(2, 2)

    def test_pixel_to_node_rejects_out_of_bounds(self) -> None:
        sp = np.ones((3, 3), dtype=np.float32)
        passable = np.ones((3, 3), dtype=bool)
        cfg = load_config(overrides={"graph": {"downsample": 1, "strict_impassable": True}})
        graph = build_grid_graph(_cost_field(sp, passable), cfg)

        with pytest.raises(ValueError, match="outside"):
            graph.pixel_to_node(3, 0)
        with pytest.raises(ValueError, match="outside"):
            graph.pixel_to_node(0, -1)

    def test_node_to_pixel_rejects_out_of_range_node(self) -> None:
        sp = np.ones((3, 3), dtype=np.float32)
        passable = np.ones((3, 3), dtype=bool)
        cfg = load_config(overrides={"graph": {"downsample": 1, "strict_impassable": True}})
        graph = build_grid_graph(_cost_field(sp, passable), cfg)

        with pytest.raises(ValueError, match="outside"):
            graph.node_to_pixel(graph.n_nodes)

    def test_nodes_to_pixels_matches_scalar_node_to_pixel(self) -> None:
        h, w, ds = 7, 5, 3
        sp = np.ones((h, w), dtype=np.float32)
        passable = np.ones((h, w), dtype=bool)
        cfg = load_config(overrides={"graph": {"downsample": ds, "strict_impassable": True}})
        graph = build_grid_graph(_cost_field(sp, passable), cfg)

        nodes = np.arange(graph.n_nodes)
        pixels = graph.nodes_to_pixels(nodes)
        assert pixels.dtype == np.int32
        assert pixels.shape == (graph.n_nodes, 2)
        for node in nodes:
            assert tuple(pixels[node]) == graph.node_to_pixel(int(node))


@pytest.mark.perf
class TestPerformance:
    """SPEC F11 / ADR-002's budget: a 4000x3000 map at downsample=4 builds under 15 s / 1 GB.

    Builds an equivalent-size synthetic `CostField` directly with numpy rather than running the
    full segmentation + T030 pipeline on `full_size_synthetic_map`: the budget here is for graph
    construction alone, and running segmentation first (its own ~30 s budget, see
    `test_palette.py::TestPerformance`) would conflate the two and slow this test down for no
    reason -- this is the "equivalent-size synthetic CostField" option the task explicitly allows.
    """

    def test_full_size_builds_under_15s_and_1gb(self) -> None:
        rng = np.random.default_rng(20260828)
        h, w = 3000, 4000
        sp = rng.uniform(0.1, 5.0, size=(h, w)).astype(np.float32)
        passable = rng.random((h, w)) > 0.1  # ~90% passable, ~10% impassable islands
        sp[~passable] = np.inf
        cost_field = _cost_field(sp, passable, mpp=2.54)
        cfg = load_config(overrides={"graph": {"downsample": 4}})

        tracemalloc.start()
        start = time.perf_counter()
        graph = build_grid_graph(cost_field, cfg)
        elapsed = time.perf_counter() - start
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        assert graph.n_nodes == 750 * 1000  # ceil(3000/4) * ceil(4000/4), matches ADR-002's ~750k
        assert elapsed < 15.0, f"build_grid_graph took {elapsed:.1f}s on a 4000x3000 map"
        # tracemalloc only tracks Python-heap allocations; numpy/scipy normally allocate through
        # the same allocator so this is representative, but if this assertion is ever the one that
        # fails while the process's actual RSS looks fine, that undercount is the likely reason --
        # trust a wall-clock/RSS profiler over this number before concluding the budget is blown.
        assert peak < 1024**3, f"build_grid_graph peaked at {peak / 1024**2:.0f} MiB"
