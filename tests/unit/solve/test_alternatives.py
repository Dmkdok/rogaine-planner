"""Tests for T043's top-K structurally distinct alternative routes and interestingness (F16).

DoD: top-K routes differing by at least one control, each with its score; K configurable; the score
spread is reported as the map's interestingness measure.

`_paths_for`/`_random_instance` mirror the same-named helpers in `test_heuristic.py` (independent
copies -- test modules in this codebase are self-contained), extended with an `alternatives`
parameter so `RunConfig.alternatives` (K) can vary per test.
"""

from __future__ import annotations

import math
from itertools import combinations, permutations

import numpy as np
import pytest

from rogaine.models import Control, RunConfig, TravelMatrix
from rogaine.solve.alternatives import solve_alternatives
from rogaine.solve.heuristic import solve_heuristic
from rogaine.solve.objective import score_order

_BUDGET_S = 1.5  # generous for the small instances below; see test_heuristic.py's rationale


def _paths_for(
    ids: list[int], positions: dict[int, tuple[float, float]], seconds: np.ndarray
) -> dict[tuple[int, int], np.ndarray]:
    """A placeholder 2-point polyline for every finite-time ordered pair -- geometry is never
    checked by these tests, only that `solve_alternatives` can build a `Leg` for every route it
    returns."""
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
    seed: int,
    n_candidates: int,
    heuristic_time_budget_s: float = _BUDGET_S,
    alternatives: int = 3,
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
        alternatives=alternatives,
    )
    return controls, matrix, run_config


def _best_score_per_subset(
    controls: list[Control],
    matrix: TravelMatrix,
    run_config: RunConfig,
    candidate_ids: list[int],
) -> dict[frozenset[int], float]:
    """Independent ground truth, computed by brute force (not via any solver): the best achievable
    `score_order` score for every subset of `candidate_ids`, trying every permutation of each. An
    upper bound `solve_alternatives`'s local-search-based entries must never exceed for a matching
    subset -- local search finds *a* local optimum for a subset, never guaranteed to be its global
    best ordering.
    """
    hub_id = next(c.id for c in controls if c.is_hub)
    best: dict[frozenset[int], float] = {
        frozenset(): score_order([hub_id, hub_id], controls, matrix, run_config).score
    }
    for size in range(1, len(candidate_ids) + 1):
        for subset in combinations(candidate_ids, size):
            best_score = -math.inf
            for perm in permutations(subset):
                scored = score_order([hub_id, *perm, hub_id], controls, matrix, run_config)
                if scored.feasible and scored.score > best_score:
                    best_score = scored.score
            best[frozenset(subset)] = best_score
    return best


class TestHandComputedTwoCandidates:
    """Same fixture as `test_heuristic.py::TestHandComputedOptimum`: hub=0, A(id=1, points=10),
    B(id=2, points=100), asymmetric A<->B cost. Only 2 candidates -> only 2 distinct visited-control
    sets are ever reachable from GRASP construction here ({} and {A, B}; see the analysis in this
    task's design notes -- construction always inserts both candidates for a 2-candidate instance,
    and `{A}`/`{B}` alone never beats `{A, B}` so `remove` never fires) -- exact scores
    hand-computed independently below.
    """

    def _instance(self, alternatives: int = 3) -> tuple[list[Control], TravelMatrix, RunConfig]:
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
            alternatives=alternatives,
        )
        return controls, matrix, run_config

    def test_two_distinct_alternatives_ranked_with_correct_interestingness(self):
        controls, matrix, run_config = self._instance(alternatives=3)
        result = solve_alternatives(controls, matrix, run_config)

        assert len(result.routes) == 2

        best, second = result.routes
        assert best.order == [0, 1, 2, 0]
        assert best.total_seconds == 25.0
        assert best.points == 110
        assert best.penalty == pytest.approx(0.5)
        assert best.score == pytest.approx(109.5)
        assert best.solver == "heuristic"
        assert best.optimal is False
        assert best.seed == run_config.seed
        assert len(best.legs) == 3

        assert second.order == [0, 0]
        assert second.score == pytest.approx(0.0)
        assert len(second.legs) == 1

        assert result.interestingness == pytest.approx(109.5)

    def test_k_zero_returns_no_alternatives_and_zero_interestingness(self):
        controls, matrix, run_config = self._instance(alternatives=0)
        result = solve_alternatives(controls, matrix, run_config)

        assert result.routes == []
        assert result.interestingness == 0.0

    def test_k_one_returns_only_the_best_and_zero_interestingness(self):
        controls, matrix, run_config = self._instance(alternatives=1)
        result = solve_alternatives(controls, matrix, run_config)

        assert len(result.routes) == 1
        assert result.routes[0].order == [0, 1, 2, 0]
        assert result.interestingness == 0.0

    def test_k_larger_than_available_returns_only_the_distinct_ones_found(self):
        controls, matrix, run_config = self._instance(alternatives=50)
        result = solve_alternatives(controls, matrix, run_config)

        assert len(result.routes) == 2  # never padded, never an error


class TestHubValidation:
    def test_wrong_hub_count_raises_even_when_k_is_zero(self):
        controls = [
            Control(id=0, x=0.0, y=0.0, is_hub=True),
            Control(id=1, x=1.0, y=0.0, is_hub=True),
        ]
        matrix = TravelMatrix(
            control_ids=(0, 1),
            seconds=np.zeros((2, 2)),
            meters=np.zeros((2, 2)),
            paths={},
        )
        run_config = RunConfig(
            base_speed_mps=1.0,
            time_limit_s=100.0,
            alternatives=0,
            heuristic_time_budget_s=_BUDGET_S,
        )

        with pytest.raises(ValueError, match="exactly one hub"):
            solve_alternatives(controls, matrix, run_config)


class TestZeroCandidates:
    def test_only_hub_returns_single_baseline_alternative(self):
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
            alternatives=3,
        )

        result = solve_alternatives(controls, matrix, run_config)

        assert len(result.routes) == 1
        assert result.routes[0].order == [0, 0]
        assert result.routes[0].score == 0.0
        assert result.routes[0].solver == "heuristic"
        assert result.routes[0].optimal is False
        assert result.interestingness == 0.0


class TestAllUnreachableFallsBackToBaseline:
    def test_no_path_to_any_control_returns_single_baseline_alternative(self):
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
            alternatives=3,
        )

        result = solve_alternatives(controls, matrix, run_config)

        assert len(result.routes) == 1
        assert result.routes[0].order == [0, 0]
        assert result.routes[0].score == 0.0
        assert result.interestingness == 0.0


class TestUnresolvedPointsExcluded:
    def test_none_points_control_never_appears_in_any_alternative(self):
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
            alternatives=5,
        )

        result = solve_alternatives(controls, matrix, run_config)

        assert result.routes  # at least the baseline
        for route in result.routes:
            assert 3 not in route.order


class TestStructurallyDistinctAndRanking:
    """Invariants that must hold regardless of exactly which subsets GRASP happens to surface."""

    def test_invariants_on_a_random_instance(self):
        controls, matrix, run_config = _random_instance(seed=13, n_candidates=6, alternatives=4)
        result = solve_alternatives(controls, matrix, run_config)

        assert 1 <= len(result.routes) <= run_config.alternatives

        # Every route starts/ends at the hub and differs from every other by at least one control.
        keys = [frozenset(r.order[1:-1]) for r in result.routes]
        assert len(keys) == len(set(keys))
        for route in result.routes:
            assert route.order[0] == 0
            assert route.order[-1] == 0
            assert route.solver == "heuristic"
            assert route.optimal is False
            assert route.seed == run_config.seed
            assert len(route.legs) == len(route.order) - 1

        # Ranked best score first.
        scores = [r.score for r in result.routes]
        assert scores == sorted(scores, reverse=True)

        # Interestingness is exactly the reported max-minus-min across the returned routes.
        expected_interestingness = (
            scores[0] - scores[-1] if len(scores) >= 2 else 0.0
        )
        assert result.interestingness == pytest.approx(expected_interestingness)

    def test_no_route_beats_the_brute_force_best_for_its_own_subset(self):
        # Small enough (4 candidates, 16 subsets, <=4! permutations each) to brute-force directly.
        controls, matrix, run_config = _random_instance(seed=3, n_candidates=4, alternatives=16)
        candidate_ids = [c.id for c in controls if not c.is_hub]
        ground_truth = _best_score_per_subset(controls, matrix, run_config, candidate_ids)

        result = solve_alternatives(controls, matrix, run_config)

        for route in result.routes:
            key = frozenset(route.order[1:-1])
            assert route.score <= ground_truth[key] + 1e-6

    def test_route_totals_match_score_order_for_their_own_order(self):
        # Cross-check: every returned Route's totals must agree exactly with an independent
        # `score_order` call on that same order -- never a value computed some other way.
        controls, matrix, run_config = _random_instance(seed=21, n_candidates=8, alternatives=5)
        result = solve_alternatives(controls, matrix, run_config)

        for route in result.routes:
            expected = score_order(route.order, controls, matrix, run_config)
            assert route.total_seconds == expected.total_seconds
            assert route.total_meters == expected.total_meters
            assert route.points == expected.points
            assert route.penalty == expected.penalty
            assert route.score == expected.score

    def test_top_alternative_matches_solve_heuristic_on_the_same_instance(self):
        # Both reduce the identical search pool to its single best entry (see heuristic.py's
        # module docstring, "T043 split"); on a generic random instance an exact cross-subset score
        # tie is vanishingly unlikely, so the two should agree exactly.
        controls, matrix, run_config = _random_instance(seed=55, n_candidates=7, alternatives=3)
        heuristic_route = solve_heuristic(controls, matrix, run_config)
        result = solve_alternatives(controls, matrix, run_config)

        assert result.routes[0].order == heuristic_route.order
        assert result.routes[0].score == heuristic_route.score


class TestKConfigurable:
    def test_smaller_k_is_a_prefix_of_larger_k_on_the_same_instance(self):
        controls, matrix, run_config_small = _random_instance(
            seed=77, n_candidates=6, alternatives=1
        )
        run_config_big = run_config_small.model_copy(update={"alternatives": 4})

        small = solve_alternatives(controls, matrix, run_config_small)
        big = solve_alternatives(controls, matrix, run_config_big)

        assert len(small.routes) == 1
        assert len(big.routes) <= 4
        assert small.routes == big.routes[:1]
        assert small.interestingness == 0.0


class TestDeterminism:
    def test_same_inputs_same_seed_identical_result(self):
        controls, matrix, run_config = _random_instance(seed=42, n_candidates=10, alternatives=4)
        result_a = solve_alternatives(controls, matrix, run_config)
        result_b = solve_alternatives(controls, matrix, run_config)

        assert result_a.routes == result_b.routes
        assert result_a.interestingness == result_b.interestingness
