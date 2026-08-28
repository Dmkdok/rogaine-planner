"""Tests for T040's objective and feasibility (F14).

DoD: `score = sum(points) - penalty_per_min * max(0, T - limit)`; hub start and end enforced;
unit-tested on hand-computed cases including exactly-on-limit.

Every expected number below is computed by hand in the test itself (never by calling
`score_order` to produce its own oracle). The fixture matrix is deliberately uniform -- every
off-diagonal pair is 300s / 500m apart -- so a route's totals are always `n_legs * 300` /
`n_legs * 500`, keeping the hand arithmetic trivial and unambiguous.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from rogaine.models import Control, RunConfig, TravelMatrix
from rogaine.solve.objective import score_order

_HUB = Control(id=0, x=0.0, y=0.0, is_hub=True, points=None)
_C1 = Control(id=1, x=10.0, y=0.0, points=10)
_C2 = Control(id=2, x=20.0, y=0.0, points=20)
_C3_UNRESOLVED = Control(id=3, x=30.0, y=0.0, points=None)


def _controls() -> list[Control]:
    return [_HUB, _C1, _C2, _C3_UNRESOLVED]


def _matrix() -> TravelMatrix:
    # Uniform complete graph over ids (0, 1, 2, 3): every off-diagonal pair is 300s / 500m.
    seconds = np.full((4, 4), 300.0, dtype=np.float64)
    meters = np.full((4, 4), 500.0, dtype=np.float64)
    np.fill_diagonal(seconds, 0.0)
    np.fill_diagonal(meters, 0.0)
    return TravelMatrix(control_ids=(0, 1, 2, 3), seconds=seconds, meters=meters, paths={})


def _matrix_unreachable() -> TravelMatrix:
    # Same as _matrix(), but controls 1 and 2 have no path between them at all.
    matrix = _matrix()
    seconds = matrix.seconds.copy()
    meters = matrix.meters.copy()
    seconds[1, 2] = seconds[2, 1] = math.inf
    meters[1, 2] = meters[2, 1] = math.inf
    return TravelMatrix(control_ids=matrix.control_ids, seconds=seconds, meters=meters, paths={})


def _config(time_limit_s: float, penalty_per_min: float) -> RunConfig:
    return RunConfig(
        base_speed_mps=1.5, time_limit_s=time_limit_s, penalty_per_min=penalty_per_min
    )


class TestHandComputedScore:
    """order=[0, 1, 2, 0]: 3 legs -> total_seconds=900, total_meters=1500, points=10+20=30."""

    def test_exactly_on_limit(self):
        # overrun = max(0, 900 - 900) = 0 -> penalty = 0 exactly, regardless of the rate.
        result = score_order([0, 1, 2, 0], _controls(), _matrix(), _config(900.0, 5.0))
        assert result.total_seconds == 900.0
        assert result.total_meters == 1500.0
        assert result.points == 30
        assert result.penalty == 0.0
        assert result.score == 30.0
        assert result.feasible is True

    def test_just_over_limit(self):
        # overrun = 900 - 840 = 60s = 1 min -> penalty = 6.0 * 1 = 6.0.
        result = score_order([0, 1, 2, 0], _controls(), _matrix(), _config(840.0, 6.0))
        assert result.penalty == 6.0
        assert result.score == 30.0 - 6.0

    def test_well_under_limit(self):
        # overrun = max(0, 900 - 3600) = 0 -> penalty = 0 no matter how large the rate is.
        result = score_order([0, 1, 2, 0], _controls(), _matrix(), _config(3600.0, 999.0))
        assert result.penalty == 0.0
        assert result.score == 30.0

    def test_zero_penalty_per_min_lets_solver_overrun(self):
        # SPEC F14: "zero lets the solver overrun" -- overrun is 840s here, but penalty stays 0.
        result = score_order([0, 1, 2, 0], _controls(), _matrix(), _config(60.0, 0.0))
        assert result.feasible is True
        assert result.penalty == 0.0
        assert result.score == 30.0


class TestInfeasibility:
    """order=[0, 1, 2, 0] against a matrix where the 1<->2 leg has no path at all."""

    def test_unreachable_leg_marks_infeasible_not_raised(self):
        result = score_order(
            [0, 1, 2, 0], _controls(), _matrix_unreachable(), _config(900.0, 5.0)
        )
        assert result.feasible is False
        assert math.isinf(result.total_seconds)
        assert math.isinf(result.total_meters)
        assert result.penalty == math.inf
        assert result.score == -math.inf

    def test_unreachable_leg_with_zero_penalty_per_min_is_still_negative_infinite(self):
        # Regression for the 0 * inf = nan trap: feasibility must be decided before the
        # per-minute formula runs, so a zero rate never turns an infeasible route into nan.
        result = score_order(
            [0, 1, 2, 0], _controls(), _matrix_unreachable(), _config(900.0, 0.0)
        )
        assert result.feasible is False
        assert not math.isnan(result.score)
        assert result.score == -math.inf


class TestHubEnforcement:
    def test_rejects_order_not_starting_or_ending_at_hub(self):
        # order[0] == order[-1] == 1, satisfying Route's own bare loop check, but 1 is not the
        # hub (id 0) -- this module must catch that Route's validator alone would miss.
        with pytest.raises(ValueError, match="hub"):
            score_order([1, 2, 1], _controls(), _matrix(), _config(900.0, 5.0))


class TestUnresolvedPoints:
    def test_visited_control_with_none_points_rejected(self):
        # order=[0, 1, 3, 0] visits control 3, whose points were never resolved (ADR-009).
        with pytest.raises(ValueError, match="unresolved points"):
            score_order([0, 1, 3, 0], _controls(), _matrix(), _config(900.0, 5.0))

    def test_hub_own_none_points_is_not_flagged(self):
        # The hub (id 0) also has points=None, but it is a waypoint, not a scored control --
        # already exercised by every TestHandComputedScore case succeeding at all.
        result = score_order([0, 1, 0], _controls(), _matrix(), _config(900.0, 5.0))
        assert result.points == 10


class TestStructuralValidation:
    def test_rejects_when_no_control_is_hub(self):
        controls = [
            Control(id=0, x=0.0, y=0.0, points=None),
            Control(id=1, x=1.0, y=0.0, points=10),
        ]
        with pytest.raises(ValueError, match="exactly one hub"):
            score_order([0, 1, 0], controls, _matrix(), _config(900.0, 5.0))

    def test_rejects_order_referencing_unknown_control_id(self):
        with pytest.raises(ValueError, match="unknown control id"):
            score_order([0, 1, 99, 0], _controls(), _matrix(), _config(900.0, 5.0))
