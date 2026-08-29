"""Top-K structurally distinct alternative routes and the interestingness measure (T043, F16).

**Scope boundary: built on T042 (the heuristic solver), not T041 (the exact solver).** SPEC's F16
row asks for "top-K structurally distinct solutions with their scores." The owner's real corpora
run 30-80 controls, where the exact Held-Karp DP (``solve/exact.py``) is intractable by
construction (``2**N`` subsets) -- exactly the regime T042 exists for (see ``heuristic.py``'s
module docstring). This module is deliberately not wired to ``solve_exact`` at all; a caller
wanting alternatives over a small enough instance to run exactly would need to enumerate
near-optimal subsets itself, which is out of scope here.

**Where the K candidate routes come from.** ``heuristic.py``'s GRASP restart loop already
constructs-then-locally-optimises ``config.solver.grasp_restarts`` candidate routes per solve and
(pre-T043) discarded every one but the single best. T043 promotes that restart loop to a public
function, ``search_heuristic_candidates`` (see its docstring and ``heuristic.py``'s module
docstring's "T043 split" paragraph), which returns the whole pool -- one ``ScoredOrder`` per
completed restart, plus the baseline empty hub-to-hub route at index 0. This module runs that search
exactly once per call (never once per K) and reduces the pool itself; ``solve_heuristic`` and this
module are siblings over the same pool, not one built on top of the other.

**"Structurally distinct" (dedup rule).** Per SPEC F16 and the T043 DoD, two routes are the same
alternative unless they differ by at least one *visited control* -- so this module dedupes the pool
by ``frozenset(order[1:-1])`` (the set of non-hub control ids visited), not by the order/permutation
of a fixed set: two routes visiting the same controls in a different sequence collapse into one
entry, keeping whichever of the two scores higher. This mirrors ``score_order``'s own indifference
to anything but membership, timing and points -- order only matters through the travel time it
produces, which ``score_order`` already folds into the score being compared.

**Ranking and K-handling.** Deduped candidates are ranked by score descending; ties (an exact score
tie between two different control sets) are broken by the tie's own visited-control-id tuple
ascending, purely for deterministic output, since score is otherwise the only ranking criterion.
The top ``run_config.alternatives`` (K) are returned. ``RunConfig.alternatives`` always carries a
default (``ge=0``, see ``models.py``), so this module reads only ``run_config``, never
``config.solver.alternatives`` -- same precedent ``heuristic.py`` already established for
``seed``/``heuristic_time_budget_s`` (a resolved run's ``RunConfig`` is authoritative). ``K=0`` is a
valid, meaningful input ("no alternatives requested"): handled by returning an empty result without
running the search at all, since nothing downstream needs it. If fewer than K structurally distinct
candidates exist (e.g. very few reachable non-hub controls), every distinct one found is returned --
never padded with duplicates, never an error.

**Interestingness (F16's other half).** SPEC does not pin down the exact statistic beyond "the
score spread." This module defines it as the max-minus-min score *across the alternatives actually
returned* (``top[0].score - top[-1].score``, since ``top`` is already sorted descending) -- a wide
spread means the map rewards route choice, a spread near zero means most reasonable subsets score
about the same. It is computed only over the K returned, not over the full internal pool, since
SPEC's DoD phrasing ties it to "top-K routes ... each with its score." A direct consequence: with
``K<2`` the spread is trivially ``0.0`` (nothing to compare), even if the underlying pool contains
routes with very different scores -- a caller wanting the map's full interestingness signal needs
``K>=2``. Degenerate cases (no reachable non-hub candidates, an all-unreachable hub) yield exactly
one distinct alternative -- the empty hub-to-hub route, score ``0.0`` -- and thus interestingness
``0.0``, never a crash.

**Determinism (F19)**, same boundary ``heuristic.py`` documents: given the same inputs, seed, and a
time budget generous enough that every restart converges before the deadline rather than being cut
off mid-scan, this module's output is byte-identical across runs, because it is a deterministic
reduction (dedup + sort) over ``search_heuristic_candidates``'s already-deterministic pool. If the
deadline interrupts a run mid-restart, the same wall-clock-dependent boundary applies here as there.

**Each alternative is a full ``Route``**, built the same way ``solve_exact``/``solve_heuristic``
build theirs -- ``order``, ``legs`` with real polylines pulled from ``matrix.paths``, totals, and
``solver="heuristic"``, ``optimal=False`` (honest: every alternative is a heuristic-search result,
never proven optimal), ``seed=run_config.seed``. ``_build_legs`` below mirrors (does not import)
``exact.py``/``heuristic.py``'s private helper of the same name, for the same reason those two
mirror each other: a leading underscore marks a helper as not meant for cross-module import.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from rogaine.config import AppConfig
from rogaine.models import Control, Leg, Route, RunConfig, TravelMatrix
from rogaine.solve.heuristic import search_heuristic_candidates
from rogaine.solve.objective import ScoredOrder


@dataclass(frozen=True)
class AlternativesResult:
    """Top-K structurally distinct routes plus the map's interestingness measure (F16).

    ``routes`` holds at most ``run_config.alternatives`` entries, best score first; fewer if the
    instance has fewer than K structurally distinct feasible candidates (never padded), and exactly
    zero if ``run_config.alternatives == 0``. ``interestingness`` is ``routes[0].score -
    routes[-1].score`` (``0.0`` if ``routes`` has fewer than two entries) -- see the module
    docstring for why it is computed only over the returned routes.
    """

    routes: list[Route]
    interestingness: float


def solve_alternatives(
    controls: list[Control],
    matrix: TravelMatrix,
    run_config: RunConfig,
    config: AppConfig | None = None,
) -> AlternativesResult:
    """Find up to ``run_config.alternatives`` structurally distinct routes and their score spread.

    Raises ``ValueError`` if *controls* does not carry exactly one hub (same contract as
    ``solve_exact``/``solve_heuristic``/``score_order``) -- checked before the ``K=0`` short
    circuit, so a malformed instance is never silently accepted just because no alternatives were
    requested. Never raises for running out of time or for finding no improving route (see
    ``search_heuristic_candidates``).
    """
    hub_candidates = [c for c in controls if c.is_hub]
    if len(hub_candidates) != 1:
        raise ValueError(f"expected exactly one hub control, found {len(hub_candidates)}")

    k = run_config.alternatives
    if k == 0:
        return AlternativesResult(routes=[], interestingness=0.0)

    pool = search_heuristic_candidates(controls, matrix, run_config, config)

    best_by_controls: dict[frozenset[int], ScoredOrder] = {}
    for scored in pool:
        key = frozenset(scored.order[1:-1])
        current = best_by_controls.get(key)
        if current is None or scored.score > current.score:
            best_by_controls[key] = scored

    ranked = sorted(
        best_by_controls.values(),
        key=lambda so: (-so.score, tuple(sorted(so.order[1:-1]))),
    )
    top = ranked[:k]

    routes = [
        Route(
            order=list(so.order),
            legs=_build_legs(so.order, matrix),
            total_seconds=so.total_seconds,
            total_meters=so.total_meters,
            points=so.points,
            penalty=so.penalty,
            score=so.score,
            solver="heuristic",
            optimal=False,
            seed=run_config.seed,
        )
        for so in top
    ]

    interestingness = routes[0].score - routes[-1].score if routes else 0.0
    return AlternativesResult(routes=routes, interestingness=interestingness)


def _build_legs(order: tuple[int, ...], matrix: TravelMatrix) -> list[Leg]:
    """Pull real ``Leg``s (with polylines) from ``matrix`` for consecutive pairs in ``order``.

    Mirrors ``solve.exact``/``solve.heuristic``'s private helper of the same name -- see the module
    docstring for why this is a mirror, not an import. ``a == b`` only ever happens for the
    empty-baseline single hub-to-hub leg.
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
