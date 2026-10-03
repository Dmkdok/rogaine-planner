"""`truth.toml` schema (T118, F25)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rogaine.eval.truth import FAMILIES, Truth, dump_truth, load_truth
from rogaine.models import TerrainClass

EXAMPLE = """
[hub]
x = 812.0
y = 640.5

[[controls]]
number = 41
x = 300.0
y = 220.0

[[controls]]
x = 10.0
y = 20.0

[[barrier_probes]]
a = [100.0, 400.0]
b = [500.0, 400.0]
barrier = [[300.0, 350.0], [300.0, 450.0]]

[[class_probes]]
x = 120.0
y = 90.0
expected = "marsh"
"""


def test_example_parses_and_round_trips(tmp_path) -> None:
    p = tmp_path / "truth.toml"
    p.write_text(EXAMPLE, encoding="utf-8")
    truth = load_truth(p)
    assert truth.hub is not None and truth.hub.y == 640.5
    assert [c.number for c in truth.controls] == [41, None]
    assert truth.barrier_probes[0].barrier[1] == (300.0, 450.0)
    p.write_text(dump_truth(truth), encoding="utf-8")
    assert load_truth(p) == truth


def test_every_terrain_class_is_reachable_from_some_family_or_deliberately_not() -> None:
    covered = set().union(*FAMILIES.values())
    assert covered == set(TerrainClass) - {TerrainClass.CONTOUR, TerrainClass.UNKNOWN}


@pytest.mark.parametrize(
    "bad",
    [
        '[[class_probes]]\nx = 1.0\ny = 1.0\nexpected = "lava"\n',
        "[[controls]]\nx = -1.0\ny = 1.0\n",
        "[[barrier_probes]]\na = [0.0, 0.0]\nb = [1.0, 1.0]\nbarrier = [[0.0, 0.0]]\n",
        "[[controls]]\nx = 1.0\ny = 1.0\ncolour = 'red'\n",
    ],
)
def test_invalid_truth_is_rejected(bad: str, tmp_path) -> None:
    p = tmp_path / "truth.toml"
    p.write_text(bad, encoding="utf-8")
    with pytest.raises(ValidationError):
        load_truth(p)


def test_malformed_toml_is_a_value_error(tmp_path) -> None:
    p = tmp_path / "truth.toml"
    p.write_text("[hub\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid TOML"):
        load_truth(p)


def test_empty_truth_is_valid() -> None:
    assert Truth.model_validate({}) == Truth()
