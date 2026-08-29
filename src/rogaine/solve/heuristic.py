"""Seeded GRASP + local search heuristic solver for the Orienteering Problem (T042, F13, F19).

**Same problem as T041, different regime.** ``solve_exact`` (``solve/exact.py``) proves optimality
for up to ``exact_max_controls`` (N<=15 in the DoD) via exhaustive bitmask DP; the owner's real maps
carry 30-80 controls, where ``2**N`` is intractable. This module never proves optimality -- it
returns the best route a bounded search finds and reports its score; ``bench`` (T044) is the one
that measures the gap against T041 where the exact answer is computable (ADR-003). Like T041, this
is the Orienteering Problem, not TSP: a route chooses a *subset* of non-hub controls to maximise
points, under a *soft* time penalty, never a hard deadline that excludes a route -- see
``objective.py``'s module docstring for the formula and why insert/remove moves (which change
*membership*, not just order) are essential here in a way they would not be for a must-visit-all
tour.

**Candidate controls**, filtered exactly as T041 does and for the same reason (ADR-009): the hub is
fixed as both endpoints and never a search variable; any other control with ``points is None`` is
excluded up front, since ``score_order`` would refuse to score it. ``N`` below means this filtered
count.

**GRASP construction** (the "greedy randomized" half). Starting from the empty hub-to-hub route,
each step considers every not-yet-visited *reachable* candidate (one with a finite-time insertion
somewhere -- an unreachable one is dropped for the rest of this construction, same as T041's
DP), finds its *cheapest-time* insertion position (a constant-time-per-position proxy: added
travel time only, ignoring points/penalty -- ``_cheapest_insertion``), and scores that one trial
order via ``score_order`` -- the actual objective, points and penalty included, is always what
*ranks* candidates, never the cheap-time proxy by itself; the proxy only decides *where* in the
order to test each candidate, keeping the number of ``score_order`` calls per step linear in the
candidate count rather than quadratic. Reachable candidates are ranked by score delta versus the
route-so-far (ties broken by ascending control id, for determinism on an exactly-tied random
matrix); the top ``config.solver.grasp_candidate_size`` form the restricted candidate list (RCL),
and one is drawn uniformly at random from it via a single seeded ``numpy.random.Generator``
threaded through the whole solve. Construction inserts every reachable candidate this way, one per
step, regardless of whether a given insertion's delta is positive -- it does **not** stop at the
first non-improving insertion. **This is a deliberate departure from a first, rejected design**
that gated each insertion on ``delta > 0`` ("stop growing the route once the next insertion looks
locally bad"): that version reliably trapped construction in tiny 1-3-control routes on instances
where the true optimum visits most or all candidates, because a control that looks like a net
loss to insert into whatever partial, poorly-ordered route greedy insertion has built so far can
still belong in the *globally* best route once 2-opt/or-opt have reordered the whole tour --
marginal-delta-right-now is not a reliable signal for OP control *selection* when the existing
partial order is arbitrary. Insert-everything-reachable instead guarantees the candidate pool each
local search pass starts from is a superset of any real optimum, and turns subset selection over to
local search's ``remove`` move (below) working against an order 2-opt/or-opt have already improved
-- a strictly easier problem (prune down a good-enough tour) than the rejected design's (guess the
right set to grow into, one locally-negative-looking step at a time). Construction stops only when
every remaining candidate is unreachable, or the time budget expires. This runs
``config.solver.grasp_restarts`` times; local search (below) refines *every* restart's
construction, not just the raw-best one, and the best refined result across all restarts wins --
textbook GRASP structure (construct, locally optimise, repeat, keep the best local optimum found).

**Local search**, applied to every constructed route: five move types, first-improvement within
each (apply the first move found that strictly improves the score, rather than scanning for the
single best one) --
  - ``insert``: add an unvisited control at whichever position improves the score.
  - ``remove``: drop a visited control whose presence is net-negative.
  - ``2-opt``: reverse a sub-segment of the visited order (untangles crossing legs).
  - ``or-opt``: relocate a run of 1-3 consecutive visited controls elsewhere in the order.
  - ``swap``: exchange the positions of two visited controls.
insert and remove run first each pass because OP's real lever is *which* controls are visited --
fixing a bad control selection is typically worth more than reordering a fixed set, and the three
reordering moves that follow only make sense once that pass has already been tried. A full pass
(all five move types, in that order) repeats until one pass improves nothing or the time budget
expires; the loop always returns a result at least as good as its input (worst case: no move ever
improves anything, and the constructed route is returned unchanged). Every move is evaluated via
``score_order`` -- this module never recomputes the score/penalty formula itself.

**Time budget.** Checked with ``time.monotonic()`` against a single deadline computed once at the
start of the solve; every loop (restarts, construction steps, each move-type scan) checks it near
the top of its own iteration, so a single slow scan can only overrun the deadline by roughly one
iteration's worth of work, never by a whole extra pass. On expiry the best route found so far is
returned -- this function never raises for running out of time and never returns nothing; the
worst-case floor is always the empty hub-to-hub route (``score_order([hub, hub], ...)``, always
feasible, always scores exactly ``0.0`` -- read ``exact.py``'s docstring for why), so the heuristic
never returns something worse than doing nothing, same invariant as T041.

**Design decision: the time budget and seed come from ``RunConfig``, not ``AppConfig.solver``.**
``config.solver.heuristic_time_budget_s`` and ``.seed`` exist too (they seed a *default*
``RunConfig`` elsewhere), but ``RunConfig`` -- "the parameters of a single planning run, everything
the user chooses per attempt" -- carries its own copies of both, and T041 already established the
precedent of reading ``run_config.seed`` rather than ``config.solver.seed`` for the same reason:
once a caller has resolved a ``RunConfig`` (e.g. from a ``--seed``/``--time-budget`` CLI flag,
T050), that resolved value is authoritative for *this* run, not the config file's default.
``grasp_restarts`` and ``grasp_candidate_size`` have no ``RunConfig`` equivalent, so those two come
from ``config.solver`` -- they tune *how hard* the search works, a property of the
installation/config, not a per-run choice the way the time budget and seed are.

**Determinism (F19) and its real boundary.** One ``numpy.random.Generator`` seeded from
``run_config.seed`` is threaded through every random draw in this module -- construction's RCL pick
is the *only* place randomness is consumed; local search is a pure function of its input order
(fixed iteration order over sorted candidate lists and fixed index ranges, no RNG calls at all), so
the same constructed route always locally optimises to the same result. Given the same inputs and
seed, and a time budget generous enough that every restart actually completes
construction-plus-convergence before the deadline (rather than being cut off mid-scan), two runs
are byte-identical because no wall-clock value ever enters a comparison or a branch. The boundary:
if the deadline *does* interrupt a run mid-scan or mid-restart, the exact point of interruption
depends on wall-clock progress, which depends on the host's speed and load -- a slower host or a
busier CPU can complete fewer restarts (or stop a move-type scan earlier) than a faster one given
the identical seed, and different restart counts can land on different best routes. This module
cannot remove that boundary without giving up the time budget itself; callers that need
byte-identical output across arbitrary hardware (T053) must size the budget generously enough, for
the instance at hand, that convergence -- not the clock -- is what ends every run.

**``_build_legs`` mirrors, rather than imports, ``exact.py``'s private helper of the same name** --
both solvers independently need the same order-to-``Leg``s translation (including the ``a == b``
special case for the empty baseline's self-loop, where ``TravelMatrix.paths`` holds no entry by
design), but a leading underscore marks a module-private helper not meant for cross-module import.
"""

from __future__ import annotations

import math
import time
from itertools import pairwise

import numpy as np

from rogaine.config import AppConfig, default_config
from rogaine.models import Control, Leg, Route, RunConfig, TravelMatrix
from rogaine.solve.objective import ScoredOrder, score_order

_Move = tuple[list[int], ScoredOrder]


def solve_heuristic(
    controls: list[Control],
    matrix: TravelMatrix,
    run_config: RunConfig,
    config: AppConfig | None = None,
) -> Route:
    """Solve the Orienteering Problem heuristically via seeded GRASP + local search (F13, F19).

    Returns a ``Route`` with ``solver="heuristic"`` and ``optimal=False`` -- this solver never
    proves optimality, only reports the best score it found within the time budget. Raises
    ``ValueError`` if *controls* does not carry exactly one hub (same contract as ``solve_exact``
    and ``score_order``); never raises for running out of time or for finding no improving route.
    """
    cfg = config or default_config()

    hub_candidates = [c for c in controls if c.is_hub]
    if len(hub_candidates) != 1:
        raise ValueError(f"expected exactly one hub control, found {len(hub_candidates)}")
    hub = hub_candidates[0]

    candidate_ids = sorted(c.id for c in controls if not c.is_hub and c.points is not None)

    best = score_order([hub.id, hub.id], controls, matrix, run_config)

    if candidate_ids:
        rng = np.random.default_rng(run_config.seed)
        deadline = time.monotonic() + run_config.heuristic_time_budget_s

        for _ in range(cfg.solver.grasp_restarts):
            if time.monotonic() >= deadline:
                break
            constructed = _construct(
                hub.id,
                candidate_ids,
                controls,
                matrix,
                run_config,
                rng,
                cfg.solver.grasp_candidate_size,
                deadline,
            )
            refined = _local_search(
                constructed, candidate_ids, controls, matrix, run_config, deadline
            )
            if refined.score > best.score:
                best = refined

    legs = _build_legs(best.order, matrix)
    return Route(
        order=list(best.order),
        legs=legs,
        total_seconds=best.total_seconds,
        total_meters=best.total_meters,
        points=best.points,
        penalty=best.penalty,
        score=best.score,
        solver="heuristic",
        optimal=False,
        seed=run_config.seed,
    )


def _construct(
    hub_id: int,
    candidate_ids: list[int],
    controls: list[Control],
    matrix: TravelMatrix,
    run_config: RunConfig,
    rng: np.random.Generator,
    rcl_size: int,
    deadline: float,
) -> ScoredOrder:
    """One GRASP construction: greedy-randomized insertion until nothing left can improve the
    score or the deadline arrives. See the module docstring for the cheapest-insertion proxy vs.
    ``score_order`` ranking split.
    """
    order = [hub_id, hub_id]
    current = score_order(order, controls, matrix, run_config)
    remaining = list(candidate_ids)

    while remaining and time.monotonic() < deadline:
        ranked: list[tuple[float, int, int, ScoredOrder]] = []
        for cid in remaining:
            if time.monotonic() >= deadline:
                break
            pos, extra = _cheapest_insertion(order, cid, matrix)
            if pos is None or not math.isfinite(extra):
                continue  # unreachable at every position -- never inserted, this instance only
            trial = [*order[:pos], cid, *order[pos:]]
            scored = score_order(trial, controls, matrix, run_config)
            if not scored.feasible:
                continue
            delta = scored.score - current.score
            ranked.append((delta, cid, pos, scored))

        if not ranked:
            break  # every remaining candidate is unreachable from every position

        ranked.sort(key=lambda t: (-t[0], t[1]))
        rcl = ranked[: min(rcl_size, len(ranked))]
        _, cid, pos, scored = rcl[int(rng.integers(len(rcl)))]
        order = [*order[:pos], cid, *order[pos:]]
        current = scored
        remaining.remove(cid)

    return current


def _cheapest_insertion(
    order: list[int], cid: int, matrix: TravelMatrix
) -> tuple[int | None, float]:
    """The position (and its added travel time) where inserting ``cid`` into ``order`` costs the
    least travel time -- a proxy used only to pick one trial per candidate per construction step;
    see the module docstring for why this is not what ranks candidates.
    """
    best_pos: int | None = None
    best_extra = math.inf
    for pos in range(1, len(order)):
        a, b = order[pos - 1], order[pos]
        cost = matrix.time_between(a, cid) + matrix.time_between(cid, b)
        extra = cost - matrix.time_between(a, b)
        if extra < best_extra:
            best_extra = extra
            best_pos = pos
    return best_pos, best_extra


def _local_search(
    start: ScoredOrder,
    candidate_ids: list[int],
    controls: list[Control],
    matrix: TravelMatrix,
    run_config: RunConfig,
    deadline: float,
) -> ScoredOrder:
    """Refine one constructed route to a local optimum under the five move types (module
    docstring), insert/remove before the three reordering moves, first-improvement within each.
    """
    current = start
    order = list(current.order)
    improved = True
    while improved and time.monotonic() < deadline:
        improved = False
        for try_move in _MOVE_FNS:
            if time.monotonic() >= deadline:
                break
            result = try_move(order, current, candidate_ids, controls, matrix, run_config, deadline)
            if result is not None:
                order, current = result
                improved = True
    return current


def _try_insert(
    order: list[int],
    current: ScoredOrder,
    candidate_ids: list[int],
    controls: list[Control],
    matrix: TravelMatrix,
    run_config: RunConfig,
    deadline: float,
) -> _Move | None:
    """First unvisited candidate, first position, that strictly improves the score."""
    visited = set(order[1:-1])
    for cid in candidate_ids:
        if cid in visited:
            continue
        if time.monotonic() >= deadline:
            return None
        for pos in range(1, len(order)):
            trial = [*order[:pos], cid, *order[pos:]]
            scored = score_order(trial, controls, matrix, run_config)
            if scored.feasible and scored.score > current.score:
                return trial, scored
    return None


def _try_remove(
    order: list[int],
    current: ScoredOrder,
    candidate_ids: list[int],
    controls: list[Control],
    matrix: TravelMatrix,
    run_config: RunConfig,
    deadline: float,
) -> _Move | None:
    """First visited control whose removal strictly improves the score."""
    for i in range(1, len(order) - 1):
        if time.monotonic() >= deadline:
            return None
        trial = order[:i] + order[i + 1 :]
        scored = score_order(trial, controls, matrix, run_config)
        if scored.feasible and scored.score > current.score:
            return trial, scored
    return None


def _try_2opt(
    order: list[int],
    current: ScoredOrder,
    candidate_ids: list[int],
    controls: list[Control],
    matrix: TravelMatrix,
    run_config: RunConfig,
    deadline: float,
) -> _Move | None:
    """First sub-segment reversal (endpoints excluded) that strictly improves the score."""
    n = len(order)
    for i in range(1, n - 2):
        if time.monotonic() >= deadline:
            return None
        for j in range(i + 1, n - 1):
            trial = order[:i] + list(reversed(order[i : j + 1])) + order[j + 1 :]
            scored = score_order(trial, controls, matrix, run_config)
            if scored.feasible and scored.score > current.score:
                return trial, scored
    return None


def _try_or_opt(
    order: list[int],
    current: ScoredOrder,
    candidate_ids: list[int],
    controls: list[Control],
    matrix: TravelMatrix,
    run_config: RunConfig,
    deadline: float,
    max_chunk: int = 3,
) -> _Move | None:
    """First relocation of a 1-3 length run of visited controls that strictly improves the score."""
    n = len(order)
    visited_len = n - 2
    for chunk_len in range(1, min(max_chunk, visited_len) + 1):
        for start in range(1, n - chunk_len):
            if time.monotonic() >= deadline:
                return None
            chunk = order[start : start + chunk_len]
            remainder = order[:start] + order[start + chunk_len :]
            for pos in range(1, len(remainder)):
                trial = remainder[:pos] + chunk + remainder[pos:]
                if trial == order:
                    continue
                scored = score_order(trial, controls, matrix, run_config)
                if scored.feasible and scored.score > current.score:
                    return trial, scored
    return None


def _try_swap(
    order: list[int],
    current: ScoredOrder,
    candidate_ids: list[int],
    controls: list[Control],
    matrix: TravelMatrix,
    run_config: RunConfig,
    deadline: float,
) -> _Move | None:
    """First pairwise exchange of two visited controls that strictly improves the score."""
    n = len(order)
    for i in range(1, n - 1):
        if time.monotonic() >= deadline:
            return None
        for j in range(i + 1, n - 1):
            trial = list(order)
            trial[i], trial[j] = trial[j], trial[i]
            scored = score_order(trial, controls, matrix, run_config)
            if scored.feasible and scored.score > current.score:
                return trial, scored
    return None


_MOVE_FNS = (_try_insert, _try_remove, _try_2opt, _try_or_opt, _try_swap)


def _build_legs(order: tuple[int, ...], matrix: TravelMatrix) -> list[Leg]:
    """Pull real ``Leg``s (with polylines) from ``matrix`` for consecutive pairs in ``order``.

    Mirrors ``solve.exact._build_legs`` -- see the module docstring for why this is a mirror, not
    an import. ``a == b`` only ever happens for the empty-baseline single hub-to-hub leg.
    """
    legs = []
    for a, b in pairwise(order):
        if a == b:
            legs.append(Leg(from_id=a, to_id=b, seconds=0.0, meters=0.0, polyline=[]))
            continue
        seconds = matrix.time_between(a, b)
        meters = float(matrix.meters[matrix.index_of(a), matrix.index_of(b)])
        polyline = [(int(x), int(y)) for x, y in matrix.paths[(a, b)]]
        legs.append(Leg(from_id=a, to_id=b, seconds=seconds, meters=meters, polyline=polyline))
    return legs
