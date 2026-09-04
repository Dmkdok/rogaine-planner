"""The corpus loader (T005). Its job is to be honest about half-configured maps, not to reject
them — files arrive from the owner over time.
"""

from __future__ import annotations

import pytest

from rogaine.io.corpus import Calibration, list_corpus, read_entry


def _map_dir(root, map_id: str, meta: str = "", *, raster: str = "map.png"):
    d = root / map_id
    d.mkdir(parents=True)
    if raster:
        (d / raster).write_bytes(b"\x89PNG\r\n\x1a\n")
    if meta:
        (d / "meta.toml").write_text(meta, encoding="utf-8")
    return d


class TestScale:
    def test_scale_and_dpi_give_meters_per_pixel(self, tmp_path) -> None:
        _map_dir(tmp_path, "ivanovo", "scale_denominator = 30000\ndpi = 300\n")
        entry = read_entry(tmp_path / "ivanovo")
        assert entry.meters_per_pixel == pytest.approx(2.54)
        assert entry.is_plannable

    def test_calibration_overrides_the_nominal_dpi(self, tmp_path) -> None:
        # A cropped or resampled scan: the nominal 300 dpi no longer describes the file.
        _map_dir(
            tmp_path,
            "cropped",
            "scale_denominator = 30000\ndpi = 300\n"
            "[calibration]\nx1 = 100\ny1 = 500\nx2 = 600\ny2 = 500\nmeters = 1000\n",
        )
        entry = read_entry(tmp_path / "cropped")
        assert entry.meters_per_pixel == pytest.approx(2.0)

    def test_a_map_without_scale_is_listed_but_not_plannable(self, tmp_path) -> None:
        _map_dir(tmp_path, "nameless", 'name = "no scale here"\n')
        entry = read_entry(tmp_path / "nameless")
        assert entry.meters_per_pixel is None
        assert not entry.is_plannable
        assert any("scale" in m for m in entry.missing)

    def test_calibration_rejects_coincident_points(self) -> None:
        with pytest.raises(ValueError, match="distinct"):
            Calibration(x1=1, y1=1, x2=1, y2=1, meters=100)


class TestCalibrationSource:
    """T078/ADR-016: the M7 auto-calibrator's own provenance flag -- informational only, never read
    by `is_plannable`/`meters_per_pixel`.
    """

    def test_present_when_written(self, tmp_path) -> None:
        _map_dir(
            tmp_path,
            "auto",
            'scale_denominator = 30000\ndpi = 300\ncalibration_source = "assumed_default"\n',
        )
        entry = read_entry(tmp_path / "auto")
        assert entry.calibration_source == "assumed_default"
        assert entry.is_plannable

    def test_absent_on_a_hand_authored_map(self, tmp_path) -> None:
        _map_dir(tmp_path, "manual", "scale_denominator = 30000\ndpi = 300\n")
        entry = read_entry(tmp_path / "manual")
        assert entry.calibration_source is None


class TestReporting:
    def test_a_broken_meta_is_reported_not_raised(self, tmp_path) -> None:
        _map_dir(tmp_path, "broken", "scale_denominator = = 30000\n")
        entry = read_entry(tmp_path / "broken")
        assert entry.problems and "unreadable" in entry.problems[0]
        assert not entry.is_plannable

    def test_a_nonpositive_dpi_is_a_problem_not_a_silent_zero(self, tmp_path) -> None:
        _map_dir(tmp_path, "zero", "scale_denominator = 30000\ndpi = 0\n")
        entry = read_entry(tmp_path / "zero")
        assert entry.dpi is None
        assert any("dpi must be positive" in p for p in entry.problems)

    def test_missing_lists_the_optional_extras_too(self, tmp_path) -> None:
        _map_dir(tmp_path, "bare", "scale_denominator = 30000\ndpi = 300\n")
        missing = read_entry(tmp_path / "bare").missing
        assert any("controls.csv" in m for m in missing)
        assert any("reference.json" in m for m in missing)

    def test_a_directory_without_a_raster_says_so(self, tmp_path) -> None:
        _map_dir(tmp_path, "empty", "scale_denominator = 30000\ndpi = 300\n", raster="")
        entry = read_entry(tmp_path / "empty")
        assert entry.raster is None
        assert "raster" in entry.missing

    def test_ocd_is_preferred_over_a_derived_raster(self, tmp_path) -> None:
        d = _map_dir(tmp_path, "both", "scale_denominator = 30000\ndpi = 300\n")
        (d / "map.ocd").write_bytes(b"OCAD")
        assert read_entry(d).raster.name == "map.ocd"


class TestListing:
    def test_an_absent_corpus_is_empty_not_an_error(self, tmp_path) -> None:
        assert list_corpus(tmp_path / "nope") == []

    def test_one_broken_map_does_not_hide_the_others(self, tmp_path) -> None:
        _map_dir(tmp_path, "good", "scale_denominator = 30000\ndpi = 300\n")
        _map_dir(tmp_path, "bad", "dpi = oops\n")
        entries = list_corpus(tmp_path)
        assert [e.map_id for e in entries] == ["bad", "good"]
        assert [e.is_plannable for e in entries] == [False, True]
