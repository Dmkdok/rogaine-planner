"""8-connected CSR grid graph over a CostField (T031), consumed by T032's multi-source Dijkstra.

**Edge weight formula.** ``CostField.seconds_per_pixel`` is a *rate* -- seconds needed to cross
one pixel-width, not an absolute time (see ``cost/field.py``'s module docstring). For a straight
segment of length ``L`` pixel-widths at a constant rate ``r``, travel time is ``L * r`` (the rate
integrated over distance is trivial when constant). Where the rate differs at the two ends of a
hop, this module uses the standard trapezoidal approximation ``L * (r_u + r_v) / 2`` -- the same
discretisation used by raster cost-distance / friction-surface analyses in GIS. An edge's ``L`` is
the Euclidean pixel distance between the centres of the two blocks it connects: ``downsample`` for
an orthogonal edge, ``downsample * sqrt(2)`` for a diagonal one (the diagonal of a ``downsample x
downsample`` step). Both factors are in compatible units (seconds/pixel times pixels = seconds),
so summing these edge weights along a path approximates the same physical travel time ``t = mpp /
(v_base * k_terrain * k_slope)`` would give integrated along that path, piecewise between block
centres, with the same kind of bounded discretisation error any coarse-grid cost-distance method
has. At ``downsample == 1`` a block *is* a pixel, so this reduces exactly to the finest per-pixel
8-connected grid (the two endpoints' own per-pixel rates, spacing 1 or sqrt(2)) -- there is no
separate "downsample == 1 case" in the code, only in this reasoning.

**Downsample aggregation.** With ``downsample > 1`` each graph node represents an ``N x N`` block
of original pixels. A block is passable if it contains *at least one* passable original pixel, and
its rate is the mean of ``seconds_per_pixel`` over only that block's passable pixels (the ``+inf``
at impassable pixels is excluded from the mean, never averaged in). Two alternatives were
rejected: (a) including impassable pixels' ``+inf`` in a plain mean would make any block with even
a single impassable pixel evaluate to ``+inf``, i.e. fully impassable -- since ``downsample``
exists purely as a performance knob (ADR-002), that would make thin barriers propagate far more
aggressively than the source data warrants, closing off large areas the fine-grained map never
actually blocked; (b) stride-sampling every Nth pixel and ignoring the rest could step clean over
a one-pixel-wide impassable barrier that never lands on a sampled pixel, silently reporting a
passable block with a plausible rate. The mean-over-passable-pixels rule still inspects every
constituent pixel (via a vectorised reshape + sum, not a Python loop), so a barrier is only
invisible to it when it fills an *entire* block -- exactly the resolution ``downsample`` is
allowed to give up.

**`strict_impassable` / `impassable_cost_multiplier`.** When ``strict_impassable`` is true (the
config default), no edge is created if either endpoint block is impassable -- the node index still
exists (node numbering must stay stable regardless of this flag, since a `Control`'s node index
must not shift when the flag changes), but it has degree zero, so Dijkstra can never route through
or into it. When false, impassable blocks get a real finite "effective rate" instead of ``+inf``:
``impassable_cost_multiplier`` (> 1.0, config-validated) times the mean rate of every *passable*
block on the map, and edges use that effective rate exactly like a normal block rate. That
reference is a single global scalar rather than each edge's own locally-adjacent passable rate,
deliberately: a literal per-edge "nearest passable neighbour" rule is ill-defined for an edge
between two impassable blocks (interior of a lake, say) and for an impassable region with no
passable neighbour at all, while "the typical passable rate on this map" is well-defined for every
node uniformly, simple, and deterministic. Because the multiplier is a strict ``> 1.0``, the
effective rate is always strictly greater than an ordinary passable rate, so any edge touching an
impassable block is always finite, never zero, and never coincides with a normal
passable-passable edge weight, exactly as the `impassable_cost_multiplier` config comment intends
("high enough that the solver never routes through it unless there is no alternative at all").
Degenerate case: if the map has *no* passable block at all, there is no "typical passable rate" to
scale, so the reference falls back to a nominal ``1.0`` -- this only matters for a pathological
all-impassable input, never a real map.

**Node/pixel mapping, exact both ways.** Nodes are numbered row-major over the block grid:
``node = block_row * n_block_cols + block_col``. ``pixel_to_node(x, y)`` takes pixel coordinates
in this codebase's ``(x=column, y=row)`` convention (``Control.x``/``Control.y``), floors
sub-pixel input to its containing pixel, then floor-divides by ``downsample`` -- a many-to-one map
when ``downsample > 1``, since every pixel in a block shares one node. ``node_to_pixel(node)`` is
its declared inverse and returns the block's top-left original pixel as ``(x, y)`` (matching
``Leg.polyline``'s and ``TravelMatrix.paths``' own ``(x, y)`` pixel convention) -- top-left, not
centre, because it is always a real in-bounds pixel even for a partial block at the grid's bottom
or right edge, whereas a centre would need separate rounding rules there. "Exact both ways"
therefore means: ``node -> pixel -> node`` always returns the same node (this is what T032 relies
on to place a `Control` at a node and read a path's node sequence back out as pixels), while
``pixel -> node -> pixel`` only reproduces the original pixel when ``downsample == 1``; for
`downsample > 1` it canonicalises to the containing block's top-left, which is the documented and
intended behaviour, not a bug. ``nodes_to_pixels`` is the vectorised form of ``node_to_pixel``,
for turning a whole Dijkstra predecessor chain into a ``(K, 2)`` int32 pixel polyline in one call.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix

from rogaine.config import AppConfig, default_config
from rogaine.models import CostField

_SQRT2 = math.sqrt(2.0)


@dataclass(frozen=True)
class GridGraph:
    """An 8-connected CSR grid graph over a `CostField`, plus its node<->pixel mapping.

    One node per `downsample x downsample` block of original `CostField` pixels; see the module
    docstring for the edge weight formula, the aggregation rule and the mapping's exact semantics.
    """

    csr: csr_matrix  # (N, N) float64 seconds, symmetric (both directions stored explicitly)
    shape: tuple[int, int]  # original (H, W) pixel grid the graph was built from
    downsample: int
    block_shape: tuple[int, int]  # (n_block_rows, n_block_cols); N == n_block_rows * n_block_cols
    block_passable: np.ndarray  # (n_block_rows, n_block_cols) bool
    block_seconds_per_pixel: np.ndarray  # (n_block_rows, n_block_cols) float32; +inf if impassable

    @property
    def n_nodes(self) -> int:
        return self.block_shape[0] * self.block_shape[1]

    def pixel_to_node(self, x: float, y: float) -> int:
        """Pixel `(x, y)` (Control convention: x=column, y=row) -> the node of its containing
        block. Many-to-one when `downsample > 1` -- see the module docstring."""
        h, w = self.shape
        px, py = math.floor(x), math.floor(y)
        if not (0 <= px < w and 0 <= py < h):
            raise ValueError(f"pixel ({x}, {y}) is outside the {w}x{h} grid")
        block_row = py // self.downsample
        block_col = px // self.downsample
        return int(block_row * self.block_shape[1] + block_col)

    def node_to_pixel(self, node: int) -> tuple[int, int]:
        """Node -> its block's canonical top-left pixel, as `(x, y)`. See the module docstring for
        why top-left and for the exact-both-ways guarantee this provides."""
        n = self.n_nodes
        if not (0 <= node < n):
            raise ValueError(f"node {node} is outside [0, {n})")
        block_row, block_col = divmod(node, self.block_shape[1])
        return (block_col * self.downsample, block_row * self.downsample)

    def nodes_to_pixels(self, nodes: np.ndarray) -> np.ndarray:
        """Vectorised `node_to_pixel`: node indices -> `(K, 2)` int32 array of `(x, y)` points."""
        nodes_arr = np.asarray(nodes, dtype=np.int64)
        block_row, block_col = np.divmod(nodes_arr, self.block_shape[1])
        x = block_col * self.downsample
        y = block_row * self.downsample
        return np.stack([x, y], axis=1).astype(np.int32)


def _aggregate_blocks(
    seconds_per_pixel: np.ndarray, passable: np.ndarray, downsample: int
) -> tuple[np.ndarray, np.ndarray]:
    """Vectorised block aggregation: mean rate over each block's passable pixels; a block is
    passable iff it has at least one passable pixel. Returns `(block_passable, block_rate)`."""
    h, w = passable.shape
    n_rows = -(-h // downsample)  # ceil division: a partial trailing block still gets a node
    n_cols = -(-w // downsample)
    pad_h, pad_w = n_rows * downsample - h, n_cols * downsample - w

    count = passable.astype(np.float64)
    total = np.where(passable, seconds_per_pixel, 0.0).astype(np.float64)
    if pad_h or pad_w:
        count = np.pad(count, ((0, pad_h), (0, pad_w)))
        total = np.pad(total, ((0, pad_h), (0, pad_w)))

    count = count.reshape(n_rows, downsample, n_cols, downsample).sum(axis=(1, 3))
    total = total.reshape(n_rows, downsample, n_cols, downsample).sum(axis=(1, 3))

    block_passable = count > 0
    block_rate = np.full((n_rows, n_cols), np.inf, dtype=np.float64)
    np.divide(total, count, out=block_rate, where=block_passable)
    return block_passable, block_rate.astype(np.float32)


def _effective_rate(
    block_rate: np.ndarray, block_passable: np.ndarray, strict_impassable: bool, multiplier: float
) -> np.ndarray:
    """float64 per-node rate used for edge weights. Under strict mode, impassable entries stay
    `+inf` -- harmless, because those edges are dropped before a weight is ever read. Otherwise
    they are replaced by `multiplier * (mean rate of every passable block)` -- see module
    docstring."""
    eff = block_rate.astype(np.float64)
    if strict_impassable:
        return eff
    passable_rates = eff[block_passable]
    reference = float(passable_rates.mean()) if passable_rates.size else 1.0
    return np.where(block_passable, eff, multiplier * reference)


def _build_edges(
    eff_rate: np.ndarray, block_passable: np.ndarray, downsample: int, strict_impassable: bool
) -> csr_matrix:
    """Vectorised 8-connected edge construction over the block grid: one slice pair per direction
    (right, down, both diagonals), no Python loop over nodes or edges."""
    n_rows, n_cols = eff_rate.shape
    node_id = np.arange(n_rows * n_cols, dtype=np.int64).reshape(n_rows, n_cols)

    us: list[np.ndarray] = []
    vs: list[np.ndarray] = []
    ws: list[np.ndarray] = []

    def add(u_idx: tuple, v_idx: tuple, spacing: float) -> None:
        u, v = node_id[u_idx].ravel(), node_id[v_idx].ravel()
        weight = spacing * (eff_rate[u_idx] + eff_rate[v_idx]) / 2.0
        weight = weight.ravel()
        if strict_impassable:
            valid = (block_passable[u_idx] & block_passable[v_idx]).ravel()
            u, v, weight = u[valid], v[valid], weight[valid]
        us.append(u)
        vs.append(v)
        ws.append(weight)

    if n_cols > 1:
        add(np.s_[:, :-1], np.s_[:, 1:], float(downsample))  # right
    if n_rows > 1:
        add(np.s_[:-1, :], np.s_[1:, :], float(downsample))  # down
    if n_rows > 1 and n_cols > 1:
        add(np.s_[:-1, :-1], np.s_[1:, 1:], downsample * _SQRT2)  # down-right
        add(np.s_[:-1, 1:], np.s_[1:, :-1], downsample * _SQRT2)  # down-left

    n = n_rows * n_cols
    if not us:
        return csr_matrix((n, n))

    u_all, v_all, w_all = np.concatenate(us), np.concatenate(vs), np.concatenate(ws)
    rows = np.concatenate([u_all, v_all])
    cols = np.concatenate([v_all, u_all])
    data = np.concatenate([w_all, w_all])
    return coo_matrix((data, (rows, cols)), shape=(n, n)).tocsr()


def build_grid_graph(cost_field: CostField, config: AppConfig | None = None) -> GridGraph:
    """Build the 8-connected CSR grid graph a `CostField` describes (F11 setup for T032)."""
    cfg = config or default_config()
    graph_cfg = cfg.graph

    block_passable, block_rate = _aggregate_blocks(
        cost_field.seconds_per_pixel, cost_field.passable, graph_cfg.downsample
    )
    eff_rate = _effective_rate(
        block_rate,
        block_passable,
        graph_cfg.strict_impassable,
        graph_cfg.impassable_cost_multiplier,
    )
    csr = _build_edges(
        eff_rate, block_passable, graph_cfg.downsample, graph_cfg.strict_impassable
    )

    return GridGraph(
        csr=csr,
        shape=cost_field.seconds_per_pixel.shape,
        downsample=graph_cfg.downsample,
        block_shape=block_rate.shape,
        block_passable=block_passable,
        block_seconds_per_pixel=block_rate,
    )
