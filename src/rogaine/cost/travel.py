"""Travel matrix and path reconstruction (T032, F11).

**Algorithm (ADR-002).** One ``scipy.sparse.csgraph.dijkstra`` call with ``indices`` set to every
control's graph node -- scipy runs one sweep per index internally and returns a
``(n_controls, n_nodes)`` distance matrix plus, with ``return_predecessors=True``, a matching
``(n_controls, n_nodes)`` predecessors matrix -- rather than ``n_controls`` separate Python-level
calls. This module reads every pairwise time straight off that one distance matrix and reconstructs
every pairwise path from that one predecessors matrix; it never calls ``dijkstra`` more than once.

**The ``meters_per_pixel`` gap.** ``GridGraph`` (``cost/graph.py``) carries edge weights in
*seconds*, not pixels, and does not itself record the map's ground scale -- there is nothing in it
to convert a reconstructed path's pixel-space hop lengths into metres. Rather than add that field to
``GridGraph`` (T031, already landed, out of scope here) or to ``models.py`` (frozen contract), this
module takes ``meters_per_pixel`` as its own explicit parameter -- the same value the ``CostField``
that produced the graph already carries as ``CostField.meters_per_pixel``, so a caller holding both
just forwards it.

**Design decision 1: ``meters`` is the physical length of the reconstructed time-optimal path, not
an independently shortest *distance* path.** ``seconds[i, j]`` comes straight off scipy's
``dist_matrix``. ``meters[i, j]`` is the sum of the physical lengths of the hops on *that same*
path -- the one Dijkstra found while minimising time, which is not, in general, the geometrically
shortest route between the two points (a straighter line through slower terrain can lose to a longer
detour through faster terrain). Hop length is the Euclidean pixel distance between two adjacent
nodes' canonical pixels (``GridGraph.nodes_to_pixels``), converted via ``meters_per_pixel``; since
the graph only ever connects immediate 8-connected block neighbours (``cost/graph.py``), this
distance is always exactly ``downsample`` pixels for an orthogonal hop or ``downsample * sqrt(2)``
for a diagonal one -- the same geometry ``cost/graph.py``'s edge-weight docstring uses for its own
``spacing``, computed here via a plain Euclidean norm on each hop's endpoint coordinates rather than
a separate orthogonal/diagonal branch, since ``hypot(dx, dy)`` already gives that exact value for
either case (dx, dy in ``{-downsample, 0, downsample}`` by construction) without restating the
formula. Simplification (see decision 5) never touches this sum -- it is computed from the raw
reconstructed chain before any simplification runs.

**Design decision 2: self-pairs.** ``seconds[i, i]`` is ``0.0`` -- scipy's own Dijkstra reports
distance-to-self as ``0.0``, so this needs no special-casing, it just falls out of the distance
matrix. ``meters[i, i]`` is likewise ``0.0`` (a zero-hop path has zero length), set once via
``np.fill_diagonal`` rather than reconstructed. ``paths`` holds **no** ``(id, id)`` entry: a
self-visit needs no reconstructed geometry (a caller wanting a self-visit's position already has the
control's own ``(x, y)``), and omitting the diagonal keeps the reconstruction loop a plain
unordered-pair iteration (``i < j``) with no self-pair special case inside it.

**Design decision 3: symmetry is not forced.** ``seconds[i, j]`` and ``seconds[j, i]`` come from two
*independent* Dijkstra sweeps (source ``i`` and source ``j``), summing the same underlying symmetric
edge weights (``GridGraph.csr`` stores both directions explicitly, T031) but in a different order
-- so near-exact agreement is a real, testable property of a correctly-built graph, not one this
module manufactures. Averaging with the transpose, or otherwise post-hoc symmetrising, would hide a
real bug (e.g. an accidentally directed edge slipping into the graph) behind a matrix that always
looks correct; this module does neither, and the test suite asserts symmetry within a small
floating-point tolerance instead of exact equality.

**Design decision 4: one reconstruction per unordered pair, mirrored for the reverse direction.**
For each unordered pair ``{i, j}``, the path is reconstructed once, by walking source ``i``'s own
predecessor row backward from node ``j`` -- never independently reconstructed a second time from
source ``j``'s row. The reverse-direction ``paths[(id_j, id_i)]`` entry is the same array reversed.
This is cheaper (half the reconstruction work) and, unlike ``seconds``, guarantees ``(i, j)`` and
``(j, i)`` are exact geometric mirrors of each other -- which is not "artificially forcing symmetry"
in the sense decision 3 rules out (no independently-computed result is being overwritten or
averaged); it is simply never computing the second direction independently in the first place.
``meters[i, j]`` and ``meters[j, i]`` are set from that one computed length for the same reason.
The alternative -- reconstructing independently from each source's own sweep -- is simpler in that
it needs no reverse-mirroring step, but on a graph with tied-cost alternate routes the two
directions' polylines could theoretically differ in shape even though their total lengths must
match; mirroring sidesteps that without losing anything a downstream renderer needs.

**Design decision 5: polyline simplification is a plain pixel constant, not a config knob.**
``_SIMPLIFY_EPSILON_PX`` feeds ``cv2.approxPolyDP`` (open polyline, ``closed=False``) exactly as
``vision/controls.py`` already uses it for the start-triangle contour -- the same simplification
idiom, reused rather than reinvented. Unlike ``[linear]``'s or ``[detector]``'s mm-based geometric
tunables, this value carries no DoD floor and is purely cosmetic: it only ever shrinks the point
count of what gets *stored* in ``paths`` for rendering, never the reported ``seconds``/``meters``
(computed from the raw chain before simplification runs, decision 1). ``config/default.toml`` and
``config.py`` were checked and carry no existing ``[travel]`` section or epsilon-like field to
extend, so adding one here would be a new config surface for a single rendering nicety with no
correctness consequence -- not warranted by this codebase's own convention of reserving config for
tunables a DoD or a physical calibration depends on.

**``config`` parameter.** Accepted and resolved via ``default_config()`` like every sibling
``cost/`` builder (``compute_cost_field``, ``build_grid_graph``), for call-signature consistency
across the package and to fail fast if a caller's config fails to parse or validate -- but nothing
in this function currently reads a value *from* it, since decision 5 above keeps the one tunable
this module might otherwise need (the simplification epsilon) out of config entirely. A future
travel-specific setting would slot in here without a signature change for existing callers.

**Predecessor sentinel.** scipy's "no predecessor" marker is ``-9999``, hardcoded here as
``_PRED_NULL`` after checking the installed scipy (1.18.0 in this project's Docker image): it has no
``scipy.sparse.csgraph.NULL_IDX`` constant to import instead, and an empirical check
(``dijkstra`` on a small hand-built graph, unreachable and source nodes both) confirmed the sentinel
value directly rather than trusting it from memory.

**Unreachable pairs.** ``dist_matrix`` reports ``+inf`` for a node scipy's Dijkstra never reached;
this module reads that value for ``seconds`` without ever clipping or converting it, and never
attempts to reconstruct a path for a pair whose ``seconds`` entry is not finite -- ``meters`` for
that pair is also ``+inf`` (initialised there, never touched by the reconstruction loop, so it stays
``+inf`` rather than defaulting to ``0.0``), and ``paths`` holds **no** entry for that pair at all.
Absent, not an empty array: an empty ``(0, 2)`` array could be mistaken for a present-but-trivial
path, whereas a missing dict key makes "no path exists" unambiguous to a caller that checks
membership (or uses ``.get``) before touching ``paths``.
"""

from __future__ import annotations

import cv2
import numpy as np
from scipy.sparse.csgraph import dijkstra

from rogaine.config import AppConfig, default_config
from rogaine.cost.graph import GridGraph
from rogaine.models import Control, TravelMatrix

# scipy's sentinel for "no predecessor" (source node itself, or unreached). Verified empirically
# against the installed scipy (1.18.0) rather than assumed -- see the module docstring.
_PRED_NULL = -9999

# cv2.approxPolyDP tolerance, in pixels, for the polylines stored in `TravelMatrix.paths`. Rendering
# only -- see the module docstring's design decision 5.
_SIMPLIFY_EPSILON_PX = 1.5


def build_travel_matrix(
    controls: list[Control],
    graph: GridGraph,
    meters_per_pixel: float,
    config: AppConfig | None = None,
) -> TravelMatrix:
    """Multi-source Dijkstra over `graph` from every control, reconstructed into a `TravelMatrix`.

    `control_ids` preserves `controls`' own order -- no hub-first sort is applied here.
    """
    if meters_per_pixel <= 0:
        raise ValueError(f"meters_per_pixel must be positive, got {meters_per_pixel}")
    _ = config or default_config()

    n = len(controls)
    control_ids = tuple(c.id for c in controls)
    nodes = np.array([graph.pixel_to_node(c.x, c.y) for c in controls], dtype=np.int64)

    dist_matrix, predecessors = dijkstra(
        graph.csr, directed=False, indices=nodes, return_predecessors=True
    )
    seconds = dist_matrix[:, nodes]  # (n, n): seconds[i, j] = time from control i to control j

    meters = np.full((n, n), np.inf, dtype=np.float64)
    np.fill_diagonal(meters, 0.0)
    paths: dict[tuple[int, int], np.ndarray] = {}

    for i in range(n):
        for j in range(i + 1, n):
            if not np.isfinite(seconds[i, j]):
                continue
            chain = _reconstruct_chain(predecessors[i], nodes[i], nodes[j])
            pixels = graph.nodes_to_pixels(chain)
            total_meters = float(_hop_lengths_px(pixels).sum()) * meters_per_pixel
            meters[i, j] = meters[j, i] = total_meters
            simplified = _simplify_polyline(pixels)
            paths[(control_ids[i], control_ids[j])] = simplified
            paths[(control_ids[j], control_ids[i])] = simplified[::-1].copy()

    return TravelMatrix(control_ids=control_ids, seconds=seconds, meters=meters, paths=paths)


def _reconstruct_chain(
    predecessors_row: np.ndarray, source_node: int, target_node: int
) -> np.ndarray:
    """Walk one Dijkstra sweep's predecessor row backward from `target_node` to `source_node`,
    then reverse -- the node sequence `source -> ... -> target`."""
    if target_node == source_node:
        return np.array([source_node], dtype=np.int64)
    chain = [target_node]
    node = target_node
    while node != source_node:
        prev = int(predecessors_row[node])
        if prev == _PRED_NULL:
            raise RuntimeError(
                f"predecessor chain broke before reaching source {source_node} (stuck at node "
                f"{node}) despite a finite reported distance -- scipy/graph inconsistency, not "
                "expected to happen in practice"
            )
        chain.append(prev)
        node = prev
    chain.reverse()
    return np.array(chain, dtype=np.int64)


def _hop_lengths_px(pixels: np.ndarray) -> np.ndarray:
    """Euclidean length of each hop in a `(K, 2)` pixel chain, as a `(K-1,)` float64 array (empty
    for a single-point chain, so the caller's `.sum()` is `0.0` with no special case)."""
    diffs = np.diff(pixels.astype(np.float64), axis=0)
    return np.hypot(diffs[:, 0], diffs[:, 1])


def _simplify_polyline(pixels: np.ndarray) -> np.ndarray:
    """Reduce a reconstructed `(K, 2)` pixel chain via `cv2.approxPolyDP`, for the polyline stored
    in `TravelMatrix.paths` only -- `seconds`/`meters` are computed from `pixels` before this runs.
    """
    if len(pixels) < 3:
        return pixels.astype(np.int32)
    contour = pixels.reshape(-1, 1, 2).astype(np.float32)
    simplified = cv2.approxPolyDP(contour, _SIMPLIFY_EPSILON_PX, False)
    return simplified.reshape(-1, 2).astype(np.int32)
