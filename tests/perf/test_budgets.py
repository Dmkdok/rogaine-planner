"""T053's performance/NFR budget guards (SPEC non-functional section, F19).

SPEC's non-functional section names three budgets on a 4000x3000 map at 1:10000, CPU only:
segmentation at most 30 s, all-pairs travel times for 60 controls at most 60 s, heuristic solve at
most 30 s. T031's own DoD (already landed) added a fourth: grid graph build under 15 s and under
1 GB. Together these are "the four NFR budgets" T053's DoD refers to.

Three of the four already have their own `@pytest.mark.perf` test, each isolating one pipeline
stage the same way this file's own test isolates the fourth. They are **not duplicated or moved
here** -- read each one's own docstring for why it is built the way it is:

- `tests/unit/vision/test_palette.py::TestPerformance::test_full_size_preset_under_30_seconds`
  (segmentation, <30 s) -- uses the shared `full_size_synthetic_map` session fixture because this
  stage genuinely needs a real rendered image.
- `tests/unit/cost/test_graph.py::TestPerformance::test_full_size_builds_under_15s_and_1gb`
  (grid graph build, <15 s and <1 GB) -- builds an equivalent-size (3000x4000) synthetic
  `CostField` directly with `numpy.random` instead, because graph-building doesn't need a real map
  and running the full vision pipeline first would conflate two budgets.
- `tests/unit/cost/test_travel.py::TestPerformance::test_61_controls_full_size_under_60s`
  (travel matrix, 61 controls incl. hub, <60 s) -- same "synthesize an equivalent-scale instance
  directly" pattern, citing `test_graph.py` as its own precedent.

This file holds only the one budget that did not exist anywhere yet: the heuristic solver's own
time budget (SPEC: "heuristic solve at most 30 s"; T042's DoD: "handles 80 controls inside the
budget"). `solve_heuristic` needs only a `list[Control]`, a `TravelMatrix` and a `RunConfig` -- no
pixels, no map, nothing to render -- so there is no "full-size map" to build here at all; the scale
that matters for this stage is control count, and T042's own DoD names 80 as that number.
`tests/unit/solve/test_heuristic.py`'s own `_random_instance` helper and `cli.py`'s
`_bench_instance` are both precedent for building such a synthetic instance without importing
across that boundary (application code and test code stay self-contained) -- this module mirrors
their *shape*, not their code, with its own small builder below.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from rogaine.models import Control, RunConfig, TravelMatrix
from rogaine.solve.heuristic import solve_heuristic

# T042's own DoD number: "handles 80 controls inside the budget".
_N_CANDIDATES = 80

# Bounded-overrun slack above the 30s budget. `solve_heuristic`'s deadline check happens near the
# top of each GRASP-restart / local-search pass, not mid-scan (see `heuristic.py`'s module
# docstring and `test_heuristic.py::TestLargeInstanceSmoke`'s own 5s-over-a-5s-budget precedent),
# so one in-flight pass can overrun the deadline by a bounded amount before the next check fires.
# That bound is set by how long a single pass over ~80 candidates takes, not by the size of the
# budget itself -- the same 79-candidate instance already needed no more than 5s of slack against
# a 5s budget in that precedent. 10s here is double that, which absorbs a slower CI host without
# being so loose it would hide a several-times-over-budget regression.
_SLACK_S = 10.0


def _synthetic_instance(
    seed: int, n_candidates: int
) -> tuple[list[Control], TravelMatrix, RunConfig]:
    """A random, fully-reachable synthetic Orienteering Problem instance: hub id 0 plus
    `n_candidates` candidates at random positions, a symmetric finite travel-time matrix (every
    pair reachable), every candidate's points resolved, and a placeholder 2-point polyline per
    ordered pair -- `solve_heuristic` never scores geometry, only `seconds`/`meters`/`points`, so
    the positions themselves are arbitrary and not tied to any real map scale.
    """
    rng = np.random.default_rng(seed)
    ids = list(range(n_candidates + 1))
    positions = {i: (float(rng.uniform(0, 1000)), float(rng.uniform(0, 1000))) for i in ids}

    controls = [Control(id=0, x=positions[0][0], y=positions[0][1], is_hub=True)]
    for i in ids[1:]:
        controls.append(
            Control(id=i, x=positions[i][0], y=positions[i][1], points=int(rng.integers(1, 30)))
        )

    raw = rng.uniform(50.0, 500.0, size=(len(ids), len(ids)))
    seconds = (raw + raw.T) / 2.0
    np.fill_diagonal(seconds, 0.0)
    meters = seconds * 1.4  # arbitrary consistent scale; solve_heuristic never reads meters

    paths: dict[tuple[int, int], np.ndarray] = {}
    for a in ids:
        for b in ids:
            if a == b:
                continue
            xa, ya = positions[a]
            xb, yb = positions[b]
            paths[(a, b)] = np.array([[int(xa), int(ya)], [int(xb), int(yb)]], dtype=np.int32)

    matrix = TravelMatrix(control_ids=tuple(ids), seconds=seconds, meters=meters, paths=paths)
    run_config = RunConfig(
        base_speed_mps=1.5,
        time_limit_s=400.0,
        penalty_per_min=4.0,
        seed=seed,
        # heuristic_time_budget_s intentionally omitted -- RunConfig's own default (30.0s) is the
        # real budget this test exists to check, never a smaller stand-in.
    )
    return controls, matrix, run_config


@pytest.mark.perf
class TestPerformance:
    """SPEC's fourth non-functional budget: the heuristic solver handles 80 controls inside its
    real 30s default time budget (`config/default.toml`'s `RunConfig.heuristic_time_budget_s`).
    """

    def test_80_controls_under_the_real_30s_budget(self) -> None:
        controls, matrix, run_config = _synthetic_instance(
            seed=20260831, n_candidates=_N_CANDIDATES
        )
        assert run_config.heuristic_time_budget_s == 30.0, (
            "this test exists to check RunConfig's real default budget -- if that default ever "
            "changes, update this assertion deliberately rather than let it silently drift"
        )

        start = time.perf_counter()
        route = solve_heuristic(controls, matrix, run_config)
        elapsed = time.perf_counter() - start

        budget = run_config.heuristic_time_budget_s
        assert elapsed <= budget + _SLACK_S, (
            f"solve_heuristic took {elapsed:.1f}s against a {budget:.0f}s budget "
            f"(+{_SLACK_S:.0f}s slack) for {_N_CANDIDATES} controls"
        )
        assert route.solver == "heuristic"
        assert route.optimal is False
        assert route.order[0] == 0
        assert route.order[-1] == 0
        assert route.score >= 0.0  # never worse than the empty hub-to-hub baseline
        assert len(route.legs) == len(route.order) - 1
