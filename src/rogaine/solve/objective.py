"""Route objective: score, penalty, feasibility (T040, F14).

``score = sum(points) - penalty_per_min * max(0, T - limit) / 60`` for one candidate visit
``order`` -- the formula every solver (T041 exact, T042 heuristic) optimises against. This module
owns only the arithmetic and its edge cases; it never searches for an order itself.

**Design decision 1: units.** SPEC F14's formula reads ``penalty_per_min * max(0, T - limit)``
literally, but ``penalty_per_min`` is named (and, per ``RunConfig``, documented) as a *per-minute*
rate while every duration in this codebase -- ``RunConfig.time_limit_s``, ``TravelMatrix.seconds``,
``Leg.seconds`` -- is in *seconds*. Transcribing the DoD's formula verbatim against a
seconds-denominated ``T - limit`` would overcharge the penalty by a factor of 60. This module
divides the seconds-denominated overrun by 60 before multiplying by ``penalty_per_min``:
``penalty = penalty_per_min * max(0.0, T_seconds - limit_seconds) / 60.0``.

**Design decision 2: a visited control with ``points is None`` is refused, not scored as zero.**
``Control.points`` is ``None`` when OCR could not read the number *and* no points rule (constant,
CSV) supplied a value (ADR-009). Scoring such a control as ``0`` would silently absorb a genuinely
missing number into the objective -- the exact kind of guess ADR-009 refuses to make for the
*reading* itself, and doing it one layer downstream, in the score, does not make it less of a
guess. ``score_order`` instead raises ``ValueError`` naming the offending control id(s) when
``order`` visits one whose points are unresolved. ADR-009's own stated escape hatch -- CSV or
viewer editing -- is a designed flow the caller runs *before* handing controls to the solver, not
something this module papers over. The hub is exempt from both this check and the points sum
below: it is a waypoint, not a scored control, and its ``points`` is almost always ``None`` (OCR
never reads a number off the start/finish marker), so counting it here would make every route
unscoreable.

**Design decision 3: feasibility is a cheap field, never an exception.** A candidate ``order`` can
place two controls back to back with no path between them at all (``TravelMatrix.seconds == inf``,
never ``0`` -- see that class's own docstring). Unlike decision 2's ``points is None`` (a static,
order-independent property of one control that a well-behaved caller filters out of its search
space *once*, before generating any candidates), an unreachable leg is a dynamic property of a
*specific pair in a specific order* -- the heuristic solver (T042) evaluates many candidate orders
per second, and different orders hit different unreachable pairs. Raising and catching an exception
per candidate in that hot loop is a real cost, not a style choice, so infeasibility surfaces as a
plain ``ScoredOrder.feasible: bool`` the caller checks with an ``if``, plus ``score = -inf`` (and
``penalty = +inf``) so an infeasible order never accidentally wins a max-score comparison even if a
caller forgets to check ``feasible`` explicitly. Getting there needs one more piece of care: with
``T`` infinite, the literal formula's ``penalty_per_min * max(0, T - limit)`` hits IEEE-754's
``0 * inf = nan`` whenever ``penalty_per_min == 0.0`` (SPEC's own "zero lets the solver overrun"
case) -- so this module never lets ``T`` reach that multiplication un-branched; infeasibility is
decided first, from the finite-sum-of-non-negative-legs property of ``total_seconds``, and
short-circuits straight to ``penalty = inf`` / ``score = -inf`` before the per-minute formula ever
runs.

**Design decision 4: only the cheap scoring path is built here.** The DoD asks for a score formula,
hub enforcement, and hand-computed unit tests -- not full ``Route``/``Leg`` construction. Building
simplified polylines for every candidate a solver's inner loop touches would be wasted work the DoD
never asked for, and ``Route`` also needs a ``solver`` name, an ``optimal`` flag, and a ``seed`` --
all solver-specific concerns T041/T042 own, not this module. ``score_order`` therefore returns a
``ScoredOrder`` (totals, points, penalty, score, feasibility) computed straight off
``TravelMatrix.seconds``/``meters`` and each ``Control.points``, with no polyline work at all.
Turning a winning ``ScoredOrder`` into a full ``Route`` (pulling real ``Leg``s from
``TravelMatrix.paths``, then round-tripping through ``Route``'s own validator) is left to
T041/T042, which already have to walk ``order`` pairwise to assemble legs and are the ones who know
``solver``/``optimal``/``seed`` for the ``Route`` they are about to build.

**Design decision 5: hub enforcement checks the actual hub, not just that both ends match.**
``Route``'s own validator only checks ``order[0] == order[-1]`` -- true for *any* control looped
back on itself, hub or not. This module additionally resolves the one ``Control`` with
``is_hub=True`` (a structural invariant enforced upstream, e.g. ``io/controls_csv.py``'s "exactly
one row must set is_hub") and checks both ends equal *that* control's id specifically, raising a
clear error naming the mismatch otherwise. This is the cheapest possible check -- no matrix lookup,
no arithmetic -- so it runs first, before anything else in this module touches ``TravelMatrix``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from rogaine.models import Control, RunConfig, TravelMatrix


@dataclass(frozen=True)
class ScoredOrder:
    """The cheap-path result of scoring one candidate visit order.

    Field names mirror ``Route``'s (``total_seconds``, ``total_meters``, ``points``, ``penalty``,
    ``score``) so a solver can lift them straight into a ``Route`` once it also has ``legs``,
    ``solver``, ``optimal`` and ``seed`` to supply. ``feasible`` is ``False`` exactly when
    ``order`` includes a leg with no path at all (``TravelMatrix.seconds == inf``); when it is
    ``False``, ``total_seconds``/``total_meters`` are ``inf``, ``penalty`` is ``inf`` and ``score``
    is ``-inf``, regardless of ``RunConfig.penalty_per_min``.
    """

    order: tuple[int, ...]
    total_seconds: float
    total_meters: float
    points: int
    penalty: float
    score: float
    feasible: bool


def score_order(
    order: Sequence[int],
    controls: Sequence[Control],
    matrix: TravelMatrix,
    config: RunConfig,
) -> ScoredOrder:
    """Score one candidate visit ``order`` against a travel ``matrix`` and run ``config``.

    ``order`` is a sequence of control ids starting and ending at the hub. Raises ``ValueError`` if
    ``controls`` does not carry exactly one hub, if ``order`` does not start and end at that hub's
    id, if ``order`` references a control id absent from ``controls``, or if a non-hub control
    ``order`` visits has ``points is None`` (see module docstring, decision 2). See decision 3 for
    how an unreachable leg is reported instead of raised.
    """
    hub_ids = [c.id for c in controls if c.is_hub]
    if len(hub_ids) != 1:
        raise ValueError(f"expected exactly one hub control, found {len(hub_ids)}")
    hub_id = hub_ids[0]

    if len(order) < 2:
        raise ValueError("a route needs at least a departure from and a return to the hub")
    if order[0] != hub_id or order[-1] != hub_id:
        raise ValueError(
            f"route must start and end at hub control {hub_id}, "
            f"got order[0]={order[0]}, order[-1]={order[-1]}"
        )

    controls_by_id = {c.id: c for c in controls}
    unknown = sorted({cid for cid in order if cid not in controls_by_id})
    if unknown:
        raise ValueError(f"order references unknown control id(s): {unknown}")

    unresolved = sorted({cid for cid in order[1:-1] if controls_by_id[cid].points is None})
    if unresolved:
        raise ValueError(
            f"order visits control(s) with unresolved points (ADR-009): {unresolved} -- "
            "resolve via the points rule, CSV, or viewer editing before scoring"
        )
    points = sum(controls_by_id[cid].points for cid in order[1:-1])

    total_seconds = 0.0
    total_meters = 0.0
    for a, b in pairwise(order):
        total_seconds += matrix.time_between(a, b)
        total_meters += matrix.meters[matrix.index_of(a), matrix.index_of(b)]

    if not math.isfinite(total_seconds):
        return ScoredOrder(
            order=tuple(order),
            total_seconds=total_seconds,
            total_meters=total_meters,
            points=points,
            penalty=math.inf,
            score=-math.inf,
            feasible=False,
        )

    overrun_s = max(0.0, total_seconds - config.time_limit_s)
    penalty = 0.0 if config.penalty_per_min == 0.0 else config.penalty_per_min * overrun_s / 60.0
    score = points - penalty
    return ScoredOrder(
        order=tuple(order),
        total_seconds=total_seconds,
        total_meters=total_meters,
        points=points,
        penalty=penalty,
        score=score,
        feasible=True,
    )
