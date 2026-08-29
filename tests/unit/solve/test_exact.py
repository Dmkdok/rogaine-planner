"""Tests for T041's exact Held-Karp Orienteering Problem solver (F12).

DoD: optimal for N up to 15 within memory; agrees with brute force for N up to 9 on random
matrices; refuses N above the configured cap with a clear message instead of exhausting RAM.

The brute-force reference in `TestBruteForceAgreement` is deliberately independent of
`solve_exact`'s own DP: it enumerates every subset and every permutation within each subset
directly (never calling `solve_exact`), scoring each with the same `score_order` both solvers are
required to reuse, and takes the max. Ties across differently-shaped orders are possible on a
symmetric random matrix (see the class docstring) -- `solve_exact` and the brute force need not
pick the same *order* in that case, only the same *score*.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import pytest

from rogaine.config import load_config
from rogaine.models import Control, RunConfig, TravelMatrix
from rogaine.solve.exact import solve_exact
from rogaine.solve.objective import score_order


def _paths_for(
    ids: list[int], positions: dict[int, tuple[float, float]], seconds: np.ndarray
) -> dict[tuple[int, int], np.ndarray]:
    """A placeholder 2-point polyline for every finite-time ordered pair -- geometry is never
    checked by these tests, only that `solve_exact` can build a `Leg` for whichever order wins."""
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
    seed: int, n_candidates: int
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
        base_speed_mps=1.5, time_limit_s=400.0, penalty_per_min=4.0, seed=seed
    )
    return controls, matrix, run_config


def _brute_force_best_score(
    controls: list[Control], matrix: TravelMatrix, run_config: RunConfig
) -> float:
    hub_id = next(c.id for c in controls if c.is_hub)
    candidate_ids = [c.id for c in controls if not c.is_hub and c.points is not None]
    best = score_order([hub_id, hub_id], controls, matrix, run_config).score
    for k in range(1, len(candidate_ids) + 1):
        for subset in itertools.combinations(candidate_ids, k):
            for perm in itertools.permutations(subset):
                scored = score_order([hub_id, *perm, hub_id], controls, matrix, run_config)
                if scored.score > best:
                    best = scored.score
    return best


class TestHandComputedOptimum:
    """hub=0, A(id=1, points=10), B(id=2, points=100). A<->B costs 5s forward / 50s reverse on
    purpose, so the two visit orders of {A, B} take different total times (and therefore incur
    different penalties) -- the DP must find the cheaper one (hub->A->B->hub, 25s) rather than
    the more expensive mirror (hub->B->A->hub, 70s) to reach the true optimum.

    time_limit_s=20, penalty_per_min=6:
      {}       -> score 0
      {A}      -> 20s, overrun 0            -> score 10
      {B}      -> 20s, overrun 0            -> score 100
      {A,B} best order hub->A->B->hub = 25s, overrun 5s = 5/60 min, penalty = 6*5/60 = 0.5
               -> score 110 - 0.5 = 109.5   (the global optimum)
      {A,B} worse order hub->B->A->hub = 70s, overrun 50s, penalty = 6*50/60 = 5.0
               -> score 110 - 5.0 = 105.0   (feasible, but not chosen)
    """

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
        run_config = RunConfig(base_speed_mps=1.0, time_limit_s=20.0, penalty_per_min=6.0)
        return controls, matrix, run_config

    def test_finds_the_provable_optimum(self):
        controls, matrix, run_config = self._instance()
        route = solve_exact(controls, matrix, run_config)

        assert route.order == [0, 1, 2, 0]
        assert route.total_seconds == 25.0
        assert route.points == 110
        assert route.penalty == pytest.approx(0.5)
        assert route.score == pytest.approx(109.5)
        assert route.solver == "exact"
        assert route.optimal is True

        assert len(route.legs) == len(route.order) - 1
        for leg, (a, b) in zip(route.legs, itertools.pairwise(route.order), strict=True):
            assert (leg.from_id, leg.to_id) == (a, b)


class TestBruteForceAgreement:
    @pytest.mark.parametrize("n_candidates", [4, 6, 9])
    def test_agrees_with_brute_force(self, n_candidates):
        controls, matrix, run_config = _random_instance(
            seed=1000 + n_candidates, n_candidates=n_candidates
        )
        route = solve_exact(controls, matrix, run_config)
        expected = _brute_force_best_score(controls, matrix, run_config)
        # Exact score agreement per the DoD; a tiny tolerance only guards against floating-point
        # summation-order noise on a *tied* optimum reached via a differently-shaped order.
        assert route.score == pytest.approx(expected, rel=1e-9, abs=1e-9)


class TestUnresolvedPointsExcluded:
    def test_none_points_control_left_out_of_the_search_space(self):
        # C (id=3) is by far the cheapest to reach and would dominate if it could be scored --
        # but points=None means it can never enter `order`, only A and B can.
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
        run_config = RunConfig(base_speed_mps=1.0, time_limit_s=1000.0, penalty_per_min=5.0)

        route = solve_exact(controls, matrix, run_config)

        assert 3 not in route.order
        assert set(route.order[1:-1]) == {1, 2}
        assert route.points == 60
        assert route.optimal is True


class TestEmptySubsetBaseline:
    def test_returns_empty_route_when_every_subset_loses(self):
        # A single reachable control, but the round trip is ruinously slow against a tiny time
        # limit and a huge penalty rate -- visiting it nets deeply negative, so the solver must
        # fall back to the empty hub-to-hub route rather than return a losing one.
        controls = [
            Control(id=0, x=0.0, y=0.0, is_hub=True),
            Control(id=1, x=1000.0, y=0.0, points=5),
        ]
        seconds = np.array([[0.0, 1000.0], [1000.0, 0.0]])
        meters = seconds.copy()
        positions = {0: (0.0, 0.0), 1: (1000.0, 0.0)}
        paths = _paths_for([0, 1], positions, seconds)
        matrix = TravelMatrix(control_ids=(0, 1), seconds=seconds, meters=meters, paths=paths)
        run_config = RunConfig(base_speed_mps=1.0, time_limit_s=10.0, penalty_per_min=1_000_000.0)

        route = solve_exact(controls, matrix, run_config)

        assert route.order == [0, 0]
        assert route.total_seconds == 0.0
        assert route.points == 0
        assert route.penalty == 0.0
        assert route.score == 0.0
        assert route.optimal is True
        assert route.solver == "exact"
        assert len(route.legs) == 1
        assert route.legs[0].from_id == 0
        assert route.legs[0].to_id == 0
        assert route.legs[0].polyline == []


class TestExactMaxControlsCap:
    def test_at_cap_succeeds(self):
        cfg = load_config(overrides={"solver": {"exact_max_controls": 2}})
        controls, matrix, run_config = _random_instance(seed=55, n_candidates=2)
        route = solve_exact(controls, matrix, run_config, config=cfg)
        assert route.optimal is True

    def test_above_cap_refused_with_clear_message(self):
        cfg = load_config(overrides={"solver": {"exact_max_controls": 2}})
        controls, matrix, run_config = _random_instance(seed=55, n_candidates=3)
        with pytest.raises(ValueError, match="exceed"):
            solve_exact(controls, matrix, run_config, config=cfg)
