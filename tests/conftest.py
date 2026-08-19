"""Shared test fixtures.

``tests/`` goes on ``sys.path`` so that every test module can say ``from fixtures.synth_map import
...`` regardless of which subdirectory it lives in.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from fixtures.synth_map import FULL_SIZE, SyntheticMap, make_synthetic_map


@pytest.fixture(scope="session")
def synthetic_map() -> SyntheticMap:
    """The standard fixture map: 1:30000 at 300 dpi, 1600x1200 px, about 4 x 3 km."""
    return make_synthetic_map(seed=20260819)


@pytest.fixture(scope="session")
def clean_synthetic_map() -> SyntheticMap:
    """The same map without scan degradation — for telling a classifier bug from a noise bug."""
    return make_synthetic_map(seed=20260819, degrade=False)


@pytest.fixture(scope="session")
def full_size_synthetic_map() -> SyntheticMap:
    """The 4000x3000 preset the performance budgets are stated against — slow, so session-scoped."""
    return make_synthetic_map(*FULL_SIZE, seed=20260819, n_controls=60)
