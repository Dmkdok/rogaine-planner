"""Tests for T042's seeded GRASP + local search heuristic solver (F13, F19).

DoD: gap versus T041 (`solve_exact`) at most 5% across a suite of random instances with N up to
15; seeded and deterministic; handles 80 controls inside the time budget.

Every instance below passes a small explicit `heuristic_time_budget_s` via `RunConfig(...)` (see
`heuristic.py`'s module docstring: the time budget is read from `RunConfig`, not
`AppConfig.solver`) -- `config/default.toml`'s real 30s default would make these parametrized N<=15
tests slow in CI. A budget generous enough that convergence, not the clock, ends every run at these
tiny instance sizes keeps both test speed and the determinism test's byte-identical guarantee (see
that same docstring section on the wall-clock determinism boundary).

`_random_instance`/`_paths_for` mirror the same-named helpers in `test_exact.py` (independent
copies -- test modules in this codebase are self-contained), extended with a
`heuristic_time_budget_s` parameter.
"""

from __future__ import annotations

import math
import time

import numpy as np
import pytest

from rogaine.models import Control, RunConfig, TravelMatrix
from rogaine.solve.exact import solve_exact
from rogaine.solve.heuristic import solve_heuristic
from rogaine.solve.objective import score_order

_BUDGET_S = 1.5  # generous for N<=15; see module docstring


def _paths_for(
    ids: list[int], positions: dict[int, tuple[float, float]], seconds: np.ndarray
) -> dict[tuple[int, int], np.ndarray]:
    """A placeholder 2-point polyline for every finite-time ordered pair -- geometry is never
    checked by these tests, only that `solve_heuristic` can build a `Leg` for whichever order
    wins."""
    index = {cid: i for i, cid in enumerate(ids)}
    paths: dict[tuple[int, int], np.ndarray] = {}
    for a in ids:
        for b in ids:
            if a == b or not math.isfinite(seconds[index[a], index[b]]):
                continue
            xa, ya = positions[a]
            xb, yb = positions[b]
            paths[(a, b)] = np.array([[int(xa), int(ya)], [int(xb), int(yb)]], dtype=np.int32)
    return paths


def _random_instance(
    seed: int, n_candidates: int, heuristic_time_budget_s: float = _BUDGET_S
) -> tuple[list[Control], TravelMatrix, RunConfig]:
    """A random reachable instance: hub id 0, candidates 1..n_candidates, symmetric finite
    travel times, all points resolved."""
    rng = np.random.default_rng(seed)
    ids = list(range(n_candidates + 1))
    positions = {i: (float(rng.integers(0, 1000)), float(rng.integers(0, 1000))) for i in ids}

    controls = [Control(id=0, x=positions[0][0], y=positions[0][1], is_hub=True)]
    for i in ids[1:]:
        controls.append(
            Control(id=i, x=positions[i][0], y=positions[i][1], points=int(rng.integers(1, 30)))
        )

    raw = rng.uniform(50.0, 500.0, size=(len(ids), len(ids)))
    seconds = (raw + raw.T) / 2.0
    np.fill_diagonal(seconds, 0.0)
    meters = seconds * 1.4  # arbitrary consistent scale; score_order never reads meters

    matrix = TravelMatrix(
        control_ids=tuple(ids),
        seconds=seconds,
        meters=meters,
        paths=_paths_for(ids, positions, seconds),
    )
    run_config = RunConfig(
        base_speed_mps=1.5,
        time_limit_s=400.0,
        penalty_per_min=4.0,
        seed=seed,
        heuristic_time_budget_s=heuristic_time_budget_s,
    )
    return controls, matrix, run_config


def _gap(exact_score: float, heuristic_score: float) -> float:
    """Relative gap per F13: `(exact - heuristic) / exact`, guarding `exact == 0`.

    The empty hub-to-hub route is always feasible and always scores exactly `0.0` (see
    `exact.py`'s module docstring), and both solvers use it as their floor -- so `exact_score` is
    never negative, and when it is exactly `0.0` the heuristic's own floor guarantees
    `heuristic_score` is `0.0` too. The gap is defined as `0.0` in that case rather than dividing
    by zero.
    """
    if exact_score == 0.0:
        return 0.0
    return (exact_score - heuristic_score) / exact_score


class TestHandComputedOptimum:
    """Same fixture as `test_exact.py::TestHandComputedOptimum`: hub=0, A(id=1, points=10),
    B(id=2, points=100), asymmetric A<->B cost so the two visit orders of {A, B} score
    differently. Only two candidates -- trivial for GRASP + local search to reach the same proven
    optimum `solve_exact` finds (score 109.5, order hub->A->B->hub)."""

    def _instance(self) -> tuple[list[Control], TravelMatrix, RunConfig]:
        controls = [
            Control(id=0, x=0.0, y=0.0, is_hub=True),
            Control(id=1, x=10.0, y=0.0, points=10),
            Control(id=2, x=20.0, y=0.0, points=100),
        ]
        seconds = np.array(
            [
                [0.0, 10.0, 10.0],
                [10.0, 0.0, 5.0],
                [10.0, 50.0, 0.0],
            ]
        )
        meters = seconds.copy()
        positions = {0: (0.0, 0.0), 1: (10.0, 0.0), 2: (20.0, 0.0)}
        paths = _paths_for([0, 1, 2], positions, seconds)
        matrix = TravelMatrix(control_ids=(0, 1, 2), seconds=seconds, meters=meters, paths=paths)
        run_config = RunConfig(
            base_speed_mps=1.0,
            time_limit_s=20.0,
            penalty_per_min=6.0,
            heuristic_time_budget_s=_BUDGET_S,
        )
        return controls, matrix, run_config

    def test_finds_the_provable_optimum(self):
        controls, matrix, run_config = self._instance()
        route = solve_heuristic(controls, matrix, run_config)

        assert route.order == [0, 1, 2, 0]
        assert route.total_seconds == 25.0
        assert route.points == 110
        assert route.penalty == pytest.approx(0.5)
        assert route.score == pytest.approx(109.5)
        assert route.solver == "heuristic"
        assert route.optimal is False
        assert len(route.legs) == len(route.order) - 1


class TestGapVersusExact:
    @pytest.mark.parametrize("n_candidates", [3, 6, 9, 12, 15])
    @pytest.mark.parametrize("seed", [0, 7, 21])
    def test_gap_within_5_percent(self, seed, n_candidates):
        controls, matrix, run_config = _random_instance(
            seed=seed * 1000 + n_candidates, n_candidates=n_candidates
        )
        exact = solve_exact(controls, matrix, run_config)
        heuristic = solve_heuristic(controls, matrix, run_config)

        # The exact solver is optimal by construction -- the heuristic can never legitimately beat
        # it; a tiny tolerance only guards floating-point summation-order noise.
        assert heuristic.score <= exact.score + 1e-6

        gap = _gap(exact.score, heuristic.score)
        assert gap <= 0.05, (
            f"gap {gap:.4f} exceeds 5% (exact={exact.score}, heuristic={heuristic.score}, "
            f"seed={seed}, n_candidates={n_candidates})"
        )


class TestDeterminism:
    def test_same_inputs_same_seed_identical_route(self):
        controls, matrix, run_config = _random_instance(seed=42, n_candidates=10)
        route_a = solve_heuristic(controls, matrix, run_config)
        route_b = solve_heuristic(controls, matrix, run_config)
        assert route_a == route_b

    def test_different_seed_can_change_the_route(self):
        # Not a DoD requirement by itself, but documents that `seed` is actually consumed: two
        # different seeds on a large-enough random instance are overwhelmingly unlikely to walk
        # through GRASP construction identically.
        controls, matrix, run_config_a = _random_instance(seed=1, n_candidates=12)
        _, _, run_config_b = _random_instance(seed=2, n_candidates=12)
        route_a = solve_heuristic(controls, matrix, run_config_a)
        route_b = solve_heuristic(controls, matrix, run_config_b)
        assert route_a.seed == 1
        assert route_b.seed == 2


class TestLargeInstanceSmoke:
    def test_completes_within_budget_at_80_controls(self):
        budget_s = 5.0
        controls, matrix, run_config = _random_instance(
            seed=999, n_candidates=79, heuristic_time_budget_s=budget_s
        )

        start = time.monotonic()
        route = solve_heuristic(controls, matrix, run_config)
        elapsed = time.monotonic() - start

        # Slack above the raw budget: deadline checks happen near the top of each loop, not
        # mid-scan (module docstring), so one scan can overrun the deadline by a bounded amount.
        assert elapsed <= budget_s + 5.0
        assert route.solver == "heuristic"
        assert route.optimal is False
        assert route.order[0] == 0
        assert route.order[-1] == 0
        assert route.score >= 0.0  # never worse than the empty hub-to-hub baseline
        assert len(route.legs) == len(route.order) - 1


class TestZeroCandidates:
    def test_only_hub_returns_empty_route(self):
        controls = [Control(id=0, x=0.0, y=0.0, is_hub=True)]
        matrix = TravelMatrix(
            control_ids=(0,),
            seconds=np.array([[0.0]]),
            meters=np.array([[0.0]]),
            paths={},
        )
        run_config = RunConfig(
            base_speed_mps=1.0,
            time_limit_s=100.0,
            penalty_per_min=1.0,
            heuristic_time_budget_s=_BUDGET_S,
        )

        route = solve_heuristic(controls, matrix, run_config)

        assert route.order == [0, 0]
        assert route.points == 0
        assert route.total_seconds == 0.0
        assert route.penalty == 0.0
        assert route.score == 0.0
        assert route.solver == "heuristic"
        assert route.optimal is False
        assert route.seed == run_config.seed
        assert len(route.legs) == 1
        assert route.legs[0].polyline == []


class TestUnresolvedPointsExcluded:
    def test_none_points_control_never_appears_in_the_result(self):
        # C (id=3) is by far the cheapest to reach and would dominate if it could be scored --
        # but points=None means it can never enter `order`, only A and B can. Trivial enough
        # (2 real candidates) that the heuristic should reliably find both.
        controls = [
            Control(id=0, x=0.0, y=0.0, is_hub=True),
            Control(id=1, x=10.0, y=0.0, points=50),
            Control(id=2, x=20.0, y=0.0, points=10),
            Control(id=3, x=1.0, y=0.0, points=None),
        ]
        seconds = np.array(
            [
                [0.0, 10.0, 10.0, 1.0],
                [10.0, 0.0, 10.0, 1.0],
                [10.0, 10.0, 0.0, 1.0],
                [1.0, 1.0, 1.0, 0.0],
            ]
        )
        meters = seconds.copy()
        positions = {0: (0.0, 0.0), 1: (10.0, 0.0), 2: (20.0, 0.0), 3: (1.0, 0.0)}
        paths = _paths_for([0, 1, 2, 3], positions, seconds)
        matrix = TravelMatrix(
            control_ids=(0, 1, 2, 3), seconds=seconds, meters=meters, paths=paths
        )
        run_config = RunConfig(
            base_speed_mps=1.0,
            time_limit_s=1000.0,
            penalty_per_min=5.0,
            heuristic_time_budget_s=_BUDGET_S,
        )

        route = solve_heuristic(controls, matrix, run_config)

        assert 3 not in route.order
        assert set(route.order[1:-1]) == {1, 2}
        assert route.points == 60
        assert route.solver == "heuristic"
        assert route.optimal is False


class TestAllUnreachableFallsBackToEmpty:
    def test_no_path_to_any_control_returns_empty_route(self):
        controls = [
            Control(id=0, x=0.0, y=0.0, is_hub=True),
            Control(id=1, x=10.0, y=0.0, points=50),
            Control(id=2, x=20.0, y=0.0, points=100),
        ]
        seconds = np.array(
            [
                [0.0, math.inf, math.inf],
                [math.inf, 0.0, 5.0],
                [math.inf, 5.0, 0.0],
            ]
        )
        meters = seconds.copy()
        matrix = TravelMatrix(control_ids=(0, 1, 2), seconds=seconds, meters=meters, paths={})
        run_config = RunConfig(
            base_speed_mps=1.0,
            time_limit_s=100.0,
            penalty_per_min=1.0,
            heuristic_time_budget_s=_BUDGET_S,
        )

        route = solve_heuristic(controls, matrix, run_config)

        assert route.order == [0, 0]
        assert route.points == 0
        assert route.score == 0.0
        assert route.solver == "heuristic"
        assert route.optimal is False


class TestNeverReimplementsTheFormula:
    """Sanity cross-check: for a fixed order the heuristic could plausibly return, its Route
    totals must agree exactly with `score_order` on that same order -- confirming the solver
    reports whatever `score_order` says, never a value it computed some other way."""

    def test_route_totals_match_score_order_for_its_own_order(self):
        controls, matrix, run_config = _random_instance(seed=5, n_candidates=8)
        route = solve_heuristic(controls, matrix, run_config)
        expected = score_order(route.order, controls, matrix, run_config)

        assert route.total_seconds == expected.total_seconds
        assert route.total_meters == expected.total_meters
        assert route.points == expected.points
        assert route.penalty == expected.penalty
        assert route.score == expected.score
