"""Controls CSV round-trip (T022, SPEC F9)."""

from __future__ import annotations

import pytest

from rogaine.io.controls_csv import read_controls, write_controls
from rogaine.models import Control


class TestRoundTrip:
    def test_every_field_survives_write_then_read_exactly(self, tmp_path) -> None:
        # Mixes detected (real, non-trivial confidence) and manual controls, a readable and an
        # unreadable number, to exercise every field the DoD calls out plus the two this module
        # added (source, is_hub) for the reasons its own docstring gives.
        controls = [
            Control(id=0, x=1600.0, y=1200.0, confidence=1.0, source="manual", is_hub=True),
            Control(
                id=1,
                x=842.25,
                y=410.75,
                number=73,
                points=7,
                confidence=0.8220000000000001,
                source="detected",
                is_hub=False,
            ),
            Control(
                id=2,
                x=2150.0,
                y=980.0,
                number=None,
                points=None,
                confidence=0.6543,
                source="detected",
                is_hub=False,
            ),
            Control(
                id=3,
                x=333.0,
                y=222.0,
                number=45,
                points=None,
                confidence=1.0,
                source="manual",
                is_hub=False,
            ),
        ]
        csv_path = tmp_path / "controls.csv"
        write_controls(csv_path, controls)
        loaded = {c.id: c for c in read_controls(csv_path)}

        assert loaded.keys() == {c.id for c in controls}
        for original in controls:
            assert loaded[original.id] == original

    def test_hub_not_first_on_write_still_reads_hub_first(self, tmp_path) -> None:
        controls = [
            Control(id=1, x=842.0, y=410.0, number=73, points=7, source="manual"),
            Control(id=0, x=1600.0, y=1200.0, source="manual", is_hub=True),
            Control(id=2, x=2150.0, y=980.0, number=45, source="manual"),
        ]
        csv_path = tmp_path / "controls.csv"
        write_controls(csv_path, controls)
        loaded = read_controls(csv_path)
        assert loaded[0].id == 0 and loaded[0].is_hub
        assert [c.id for c in loaded] == [0, 1, 2]


class TestReadLeniency:
    """A hand-edited file following data/README.md's documented example (no confidence/source
    columns at all) must still load, matching the values the old hardcoded behaviour always
    produced.
    """

    def test_bare_dod_header_defaults_confidence_and_source(self, tmp_path) -> None:
        csv_path = tmp_path / "controls.csv"
        csv_path.write_text(
            "id,x,y,number,points,is_hub\n"
            "1,842,410,73,7,false\n"
            "0,1600,1200,,0,true\n"
            "2,2150,980,45,,false\n",
            encoding="utf-8",
        )
        controls = read_controls(csv_path)
        assert controls[0].id == 0 and controls[0].is_hub
        assert [c.id for c in controls] == [0, 1, 2]
        assert controls[1].points == 7
        assert controls[2].points is None  # blank means "apply the config's points rule"
        assert all(c.source == "manual" for c in controls)
        assert all(c.confidence == 1.0 for c in controls)


class TestMalformedRows:
    HEADER = "id,x,y,number,points,confidence,source,is_hub\n"

    def test_exactly_one_hub_is_required(self, tmp_path) -> None:
        csv_path = tmp_path / "controls.csv"
        rows = "0,10,10,,0,1.0,manual,false\n1,20,20,45,4,1.0,manual,false\n"
        csv_path.write_text(self.HEADER + rows, encoding="utf-8")
        with pytest.raises(ValueError, match="exactly one row must set is_hub"):
            read_controls(csv_path)

    def test_duplicate_ids_are_rejected(self, tmp_path) -> None:
        csv_path = tmp_path / "controls.csv"
        rows = "0,10,10,,0,1.0,manual,true\n0,20,20,45,4,1.0,manual,false\n"
        csv_path.write_text(self.HEADER + rows, encoding="utf-8")
        with pytest.raises(ValueError, match="not unique"):
            read_controls(csv_path)

    def test_a_non_numeric_field_names_its_line(self, tmp_path) -> None:
        csv_path = tmp_path / "controls.csv"
        rows = "0,10,10,,0,1.0,manual,true\n1,x,20,45,4,1.0,manual,false\n"
        csv_path.write_text(self.HEADER + rows, encoding="utf-8")
        with pytest.raises(ValueError, match="line 3"):
            read_controls(csv_path)

    def test_confidence_out_of_range_raises_with_line_number(self, tmp_path) -> None:
        csv_path = tmp_path / "controls.csv"
        rows = "0,10,10,,0,1.0,manual,true\n1,20,20,45,4,1.5,detected,false\n"
        csv_path.write_text(self.HEADER + rows, encoding="utf-8")
        with pytest.raises(ValueError, match="line 3"):
            read_controls(csv_path)

    def test_invalid_source_raises_with_line_number(self, tmp_path) -> None:
        csv_path = tmp_path / "controls.csv"
        rows = "0,10,10,,0,1.0,manual,true\n1,20,20,45,4,0.9,auto,false\n"
        csv_path.write_text(self.HEADER + rows, encoding="utf-8")
        with pytest.raises(ValueError, match="line 3"):
            read_controls(csv_path)

    def test_missing_required_column_raises_with_line_number(self, tmp_path) -> None:
        csv_path = tmp_path / "controls.csv"
        # No "x" column at all — id/x/y are never defaulted, unlike the optional columns.
        csv_path.write_text(
            "id,y,number,points,confidence,source,is_hub\n0,10,,0,1.0,manual,true\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="line 2"):
            read_controls(csv_path)

    def test_empty_file_after_header_is_rejected(self, tmp_path) -> None:
        csv_path = tmp_path / "controls.csv"
        csv_path.write_text(self.HEADER, encoding="utf-8")
        with pytest.raises(ValueError, match="no controls"):
            read_controls(csv_path)
