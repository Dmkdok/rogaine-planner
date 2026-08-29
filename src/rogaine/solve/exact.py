"""Exact Held-Karp solver for the Orienteering Problem (T041, F12).

**This is the Orienteering Problem, not TSP.** Classic Held-Karp solves the Travelling Salesman
Problem: visit every city exactly once and minimise total tour length -- a hard must-visit-all
constraint. SPEC F12 and ADR-003 ask for something structurally different: choose a *subset* of
non-hub controls (to maximise collected points) and an order to visit them in, subject only to a
*soft* time penalty (``rogaine.solve.objective``'s ``score = points - penalty_per_min * overrun``),
never a hard deadline that rules a route out. Reusing textbook Held-Karp unmodified -- forcing every
control into the tour -- would solve a different problem than the one this codebase scores routes
against. This module instead runs Held-Karp's bitmask-DP *machinery* to solve a different problem:
minimum travel *time* per subset, then lets that drive an exhaustive search over every subset for
the one that maximises ``score_order``'s score.

**Candidate controls.** The hub (``Control.is_hub``) is fixed as both start and end and is never a
DP variable. Every other control with ``points is None`` (ADR-009: unread, no points rule resolved
it) is excluded from the search space before the DP runs -- such a control can never be scored by
``score_order``, so it can never be selected; this is not a rejection of the whole call, just one
control removed from consideration, per ``score_order``'s own module-docstring contract that a
caller filters unresolved-points controls out of its search space once, up front. ``N`` -- the count
the DoD's "N up to 15" and "configured cap" both refer to -- is the size of what remains after that
filter, never a count that includes the hub.

**Why minimising time per subset is provably sufficient to solve the OP exactly.** Fix a subset
``S`` of candidate controls and a control ``j in S`` as the last one visited before returning to the
hub. Every visit order of ``S`` ending at ``j`` collects exactly the same ``points(S)`` -- order
changes only how long the route takes, never which points it earns. ``penalty_per_min * max(0, T -
limit) / 60`` (``objective.py``) is monotonic non-decreasing in ``T`` since ``penalty_per_min >= 0``
(``RunConfig`` validates this), so among all orders of ``S`` ending at ``j``, the one with the
smallest total travel time ``T`` has the smallest penalty and therefore the highest possible score
for that ``(S, j)``. So: solve a plain minimum-time bitmask DP (Held-Karp's classic transition, just
for time rather than a forced Hamiltonian tour), and only ever score the time-minimal order of each
``(S, j)`` -- a slower order of the same ``(S, j)`` provably cannot win and is never generated.

**DP.** States are ``(mask, j)`` where ``mask`` is a bitmask over the ``N`` candidates and ``j in
mask`` is the last one visited. ``dp_time[mask][j]`` = minimum travel time hub -> ... -> ``j``
visiting exactly the candidates in ``mask``. Base case: ``dp_time[{j}][j] = seconds(hub, j)``.
Transition: ``dp_time[mask][j] = min over k in mask \\ {j} of dp_time[mask \\ {j}][k] + seconds(k,
j)``. A parent array alongside ``dp_time`` records which ``k`` achieved the minimum (or a ``-1``
sentinel for the base case), used to reconstruct each winning order afterwards. ``seconds(a, b)``
comes straight from ``TravelMatrix.seconds`` and can be ``+inf`` for an unreachable pair (T032);
``+inf`` propagates through the plain float ``min``/``+`` exactly as intended -- an unreachable
subset/order naturally never wins against a finite alternative, no special-casing required. This
module still skips calling ``score_order`` for a ``(mask, j)`` whose ``dp_time`` is already ``inf``
before adding the return leg: that candidate's outbound time is unreachable regardless of what the
return leg does, so ``score_order`` would only re-derive ``feasible=False`` / ``score=-inf`` at real
cost (rebuilding ``order``, walking every leg) for a result already known -- a performance-only
skip, never a correctness one, since a ``(mask, j)`` whose *return* leg alone is unreachable
(``dp_time`` finite, ``seconds(j, hub) == inf``) is not skipped and still goes through
``score_order`` to be marked infeasible correctly.

**Enumeration and scoring.** For every non-empty ``mask`` (``2**N - 1`` of them) and every ``j`` in
it, the order is reconstructed via parent pointers (hub, ..., j, hub) and scored by T040's
``score_order`` -- this module never reimplements the score/penalty formula. The trivial
empty-subset route ``order = [hub, hub]`` (visit nothing) is also scored the same way rather than
hand-built, so it picks up ``score_order``'s own formula and stays correct if that formula ever
changes; it is always feasible (a self-pair's travel time is ``0.0``, never ``inf`` --
``TravelMatrix``'s own invariant, see ``cost/travel.py``), scores exactly ``0.0`` under any valid
config, and is therefore never beaten by an infeasible candidate (``score = -inf``) or a feasible
one that nets negative (large penalty, few points) -- it is the guaranteed floor, "the solver never
returns something worse than doing nothing." The winner is whichever candidate has the strictly
highest score encountered, with the empty baseline as the running start -- so a run where every
non-trivial subset is infeasible or nets negative correctly returns the empty route rather than
crashing or returning a losing one.

**Memory guard (the DoD's actual ask).** Time ``O(2**N * N**2)``, space ``O(2**N * N)`` for
``dp_time`` (plus a same-shape ``parent`` array). At ``N=15``: ``2**15 * 15 = 491_520`` entries per
array -- trivial. At the config's validated ceiling ``N=24``: ``2**24 * 24 ~= 4*10**8`` entries per
array -- multi-GB, exactly why the DoD requires refusing above the cap rather than attempting it.
Before allocating anything, this module checks ``N > config.solver.exact_max_controls`` (after the
``points is None`` filter, so the check is against the real candidate count the DP would run on) and
raises ``ValueError`` naming both numbers, never letting a ``2**N``-sized allocation start.
``SolverSettings.exact_max_controls`` is itself only validated up to 24 in ``config.py``; this
module's job is only to honour whatever cap the config gives it, not to second-guess a user who sets
that cap unreasonably high themselves -- an accepted scope boundary, not a second hardcoded ceiling.
"""

from __future__ import annotations

import math
from itertools import pairwise

import numpy as np

from rogaine.config import AppConfig, default_config
from rogaine.models import Control, Leg, Route, RunConfig, TravelMatrix
from rogaine.solve.objective import score_order


def solve_exact(
    controls: list[Control],
    matrix: TravelMatrix,
    run_config: RunConfig,
    config: AppConfig | None = None,
) -> Route:
    """Solve the Orienteering Problem exactly via bitmask DP over subsets (F12).

    Returns a ``Route`` with ``solver="exact"`` and ``optimal=True`` -- Held-Karp is exact by
    construction whenever it runs at all. Raises ``ValueError`` if *controls* does not carry exactly
    one hub, or if the number of candidate (non-hub, resolved-points) controls exceeds
    ``config.solver.exact_max_controls`` -- see the module docstring for both the OP-vs-TSP framing
    and the memory guard this check exists for.
    """
    cfg = config or default_config()

    hub_candidates = [c for c in controls if c.is_hub]
    if len(hub_candidates) != 1:
        raise ValueError(f"expected exactly one hub control, found {len(hub_candidates)}")
    hub = hub_candidates[0]

    candidates = [c for c in controls if not c.is_hub and c.points is not None]
    n = len(candidates)
    cap = cfg.solver.exact_max_controls
    if n > cap:
        raise ValueError(
            f"solve_exact: {n} candidate controls (hub excluded, unresolved-points controls "
            f"excluded) exceed config.solver.exact_max_controls={cap}; use the heuristic solver "
            "(T042) for larger instances, or raise the cap in config"
        )

    best = score_order([hub.id, hub.id], controls, matrix, run_config)

    if n > 0:
        hub_idx = matrix.index_of(hub.id)
        cand_indices = [matrix.index_of(c.id) for c in candidates]
        cand_ids = [c.id for c in candidates]
        hub_to_cand = matrix.seconds[hub_idx, cand_indices]
        sub = matrix.seconds[np.ix_(cand_indices, cand_indices)]

        size = 1 << n
        dp_time = np.full((size, n), math.inf, dtype=np.float64)
        parent = np.full((size, n), -1, dtype=np.int64)

        for mask in range(1, size):
            bits = _set_bits(mask)
            for j in bits:
                prev_mask = mask ^ (1 << j)
                if prev_mask == 0:
                    dp_time[mask, j] = hub_to_cand[j]
                    continue
                best_time = math.inf
                best_k = -1
                for k in bits:
                    if k == j:
                        continue
                    t = dp_time[prev_mask, k] + sub[k, j]
                    if t < best_time:
                        best_time = t
                        best_k = k
                dp_time[mask, j] = best_time
                parent[mask, j] = best_k

        for mask in range(1, size):
            for j in _set_bits(mask):
                if not math.isfinite(dp_time[mask, j]):
                    continue  # unreachable outbound leg -- see module docstring's DP section
                order = _reconstruct_order(mask, j, parent, cand_ids, hub.id)
                scored = score_order(order, controls, matrix, run_config)
                if scored.score > best.score:
                    best = scored

    legs = _build_legs(best.order, matrix)
    return Route(
        order=list(best.order),
        legs=legs,
        total_seconds=best.total_seconds,
        total_meters=best.total_meters,
        points=best.points,
        penalty=best.penalty,
        score=best.score,
        solver="exact",
        optimal=True,
        seed=run_config.seed,
    )


def _set_bits(mask: int) -> list[int]:
    """Ascending 0-based positions of the set bits in ``mask``."""
    bits = []
    i = 0
    while mask:
        if mask & 1:
            bits.append(i)
        mask >>= 1
        i += 1
    return bits


def _reconstruct_order(
    mask: int, j: int, parent: np.ndarray, cand_ids: list[int], hub_id: int
) -> list[int]:
    """Walk ``parent`` pointers backward from ``(mask, j)`` to the hub-to-hub visit order."""
    visited: list[int] = []
    cur_mask, cur_j = mask, j
    while True:
        visited.append(cand_ids[cur_j])
        k = int(parent[cur_mask, cur_j])
        if k == -1:
            break
        cur_mask ^= 1 << cur_j
        cur_j = k
    visited.reverse()
    return [hub_id, *visited, hub_id]


def _build_legs(order: tuple[int, ...], matrix: TravelMatrix) -> list[Leg]:
    """Pull real ``Leg``s (with polylines) from ``matrix`` for consecutive pairs in ``order``.

    ``a == b`` only ever happens for the empty-subset baseline's single hub-to-hub leg (a
    non-trivial winning order never repeats a control) -- ``TravelMatrix.paths`` holds no
    self-pair entry by design (``cost/travel.py``), so that case is built directly rather than
    looked up.
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
