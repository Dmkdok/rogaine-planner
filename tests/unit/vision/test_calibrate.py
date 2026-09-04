"""Per-map best-effort auto-calibration for the M7 training corpus (T078, ADR-016)."""

from __future__ import annotations

import tomllib

import cv2
import numpy as np
import pytest

from rogaine.config import default_config
from rogaine.io.corpus import read_entry
from rogaine.io.scale import Calibration
from rogaine.vision import calibrate


def _blank(h: int = 400, w: int = 400, value: int = 255) -> np.ndarray:
    return np.full((h, w, 3), value, dtype=np.uint8)


class TestCalibrationResultValidation:
    def test_scale_bar_requires_calibration(self) -> None:
        with pytest.raises(ValueError, match=r"scale_bar.*must carry"):
            calibrate.CalibrationResult(source="scale_bar", scale_denominator=15000.0, dpi=300.0)

    def test_grid_requires_calibration(self) -> None:
        with pytest.raises(ValueError, match=r"grid.*must carry"):
            calibrate.CalibrationResult(source="grid", scale_denominator=15000.0, dpi=300.0)

    def test_circle_does_not_require_calibration(self) -> None:
        calibrate.CalibrationResult(source="circle", scale_denominator=15000.0, dpi=300.0)

    def test_scale_bar_with_calibration_is_valid(self) -> None:
        cal = Calibration(x1=0, y1=0, x2=10, y2=0, meters=5)
        calibrate.CalibrationResult(
            source="scale_bar", scale_denominator=15000.0, dpi=300.0, calibration=cal
        )


class TestImpliedDpi:
    def test_is_the_algebraic_inverse_of_mpp_from_dpi(self) -> None:
        # dpi=300, scale_denominator=15000 -> mpp = (25.4/300)*15000/1000 = 1.27
        dpi = calibrate._implied_dpi(meters_per_pixel=1.27, scale_denominator=15000.0)
        assert dpi == pytest.approx(300.0, rel=1e-3)

    def test_zero_or_negative_mpp_is_rejected(self) -> None:
        assert calibrate._implied_dpi(0.0, 15000.0) is None
        assert calibrate._implied_dpi(-1.0, 15000.0) is None


class TestAccept:
    """The shared plausibility guard (C1) -- the single gate every tier's candidate result must
    clear, replacing the first version's `_PLAUSIBLE_MPP`, which checked only a per-pixel ratio and
    rejected nothing physically real (module docstring).
    """

    def test_a_sane_result_is_accepted(self) -> None:
        # width 3000px @ mpp=2.0 -> 6km extent; dpi=300 -- all comfortably in range
        assert calibrate._accept(3000.0, 2.0, 300.0) is True

    def test_dpi_out_of_range_is_rejected(self) -> None:
        assert calibrate._accept(3000.0, 2.0, 5000.0) is False
        assert calibrate._accept(3000.0, 2.0, 10.0) is False

    def test_extent_too_small_is_rejected(self) -> None:
        # the real ogps-7212... bug: a "180m" bar reading implying well under a km course
        assert calibrate._accept(600.0, 1.0, 300.0) is False  # 0.6km extent

    def test_extent_too_large_is_rejected(self) -> None:
        assert calibrate._accept(3000.0, 200.0, 300.0) is False  # 600km extent

    def test_paper_check_is_skipped_unless_requested(self) -> None:
        # dpi=1790.7-equivalent paper size would fail the paper check, but check_paper defaults
        # to False (tiers 1/2, an implied not measured dpi) -- module docstring's own rationale.
        assert calibrate._accept(3000.0, 2.0, 1000.0) is True

    def test_paper_check_rejects_an_implausible_printed_sheet(self) -> None:
        # the real ogps-8043... bug: dpi=1790.7 implies a 71x50mm printed sheet for a 5000px map
        assert calibrate._accept(5000.0, 2.0, 1790.7, check_paper=True) is False

    def test_paper_check_accepts_a_plausible_printed_sheet(self) -> None:
        # 3000px @ 300dpi -> 254mm, a plausible printed sheet
        assert calibrate._accept(3000.0, 2.0, 300.0, check_paper=True) is True


class TestScaleRatioRegex:
    """`_SCALE_RATIO_RE`'s own boundary/format rules (M3) -- the numeric range bound lives in
    `ocr_scale_denominator`, exercised via OCR in `TestOcrScaleDenominator` below.
    """

    def test_matches_a_colon_ratio(self) -> None:
        m = calibrate._SCALE_RATIO_RE.search("map scale 1:20000 approx")
        assert m is not None
        assert m.group(1) == "20000"

    def test_rejects_a_decimal_point(self) -> None:
        assert calibrate._SCALE_RATIO_RE.search("version 1.500 released") is None

    def test_left_boundary_prevents_misreading_a_larger_number(self) -> None:
        # "21:50000" must not be read as the ratio "1:50000" via its own trailing "1"
        assert calibrate._SCALE_RATIO_RE.search("21:50000") is None

    def test_right_boundary_prevents_truncating_a_larger_number(self) -> None:
        # "1:500001" (7 digits) must not be read as "1:50000" (its own first 5 digits)
        assert calibrate._SCALE_RATIO_RE.search("1:5000012") is None


class TestOcrScaleDenominator:
    def test_reads_a_printed_ratio(self) -> None:
        image = _blank(200, 500)
        cv2.putText(image, "1:20000", (30, 110), cv2.FONT_HERSHEY_SIMPLEX, 2.2, (0, 0, 0), 4)
        assert calibrate.ocr_scale_denominator(image) == pytest.approx(20000.0)

    def test_no_text_reads_nothing(self) -> None:
        assert calibrate.ocr_scale_denominator(_blank()) is None

    def test_unrelated_text_reads_nothing(self) -> None:
        image = _blank(200, 500)
        cv2.putText(image, "ROGAINE 2024", (30, 110), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 0, 0), 3)
        assert calibrate.ocr_scale_denominator(image) is None

    def test_a_ratio_below_the_plausible_range_reads_nothing(self) -> None:
        image = _blank(200, 500)
        cv2.putText(image, "1:1500", (30, 110), cv2.FONT_HERSHEY_SIMPLEX, 2.2, (0, 0, 0), 4)
        assert calibrate.ocr_scale_denominator(image) is None


class TestDetectScaleBar:
    def _bar_image(self, *, label: str = "1000m") -> np.ndarray:
        image = _blank(400, 600)
        # 5 alternating dark ticks, equal width, at y=350 -- within the bottom-half scan and evenly
        # spaced (regularity ~0).
        y0, y1 = 344, 356
        x = 100
        for _ in range(5):
            cv2.rectangle(image, (x, y0), (x + 20, y1), (0, 0, 0), -1)
            x += 40
        cv2.putText(image, label, (70, 390), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 3)
        return image

    def test_reads_a_labelled_bar_cross_validated_by_the_ratio(self) -> None:
        # bar spans x=100..280 (180px) -> mpp = 1000/180 ~= 5.56; width_px=600 -> ~3.3km extent;
        # implied dpi = 25.4*20000/(1000*5.56) ~= 91 -- all within the plausible bounds.
        cal = calibrate.detect_scale_bar(self._bar_image(), 20000.0)
        assert cal is not None
        assert cal.meters == pytest.approx(1000.0)
        assert cal.meters_per_pixel == pytest.approx(1000.0 / 180.0, rel=0.05)

    def test_blank_map_has_no_bar(self) -> None:
        assert calibrate.detect_scale_bar(_blank(), 20000.0) is None

    def test_ticks_without_a_label_are_not_trusted(self) -> None:
        image = _blank(400, 600)
        y0, y1 = 344, 356
        x = 100
        for _ in range(5):
            cv2.rectangle(image, (x, y0), (x + 20, y1), (0, 0, 0), -1)
            x += 40
        assert calibrate.detect_scale_bar(image, 20000.0) is None

    def test_a_legend_number_masquerading_as_a_label_is_rejected(self) -> None:
        # the real ogps-7212... bug this session's independent review found: a syntactically-valid
        # "<number>m" label near a tick-shaped run, but not a real scale bar -- meters=180 against
        # this same 180px-wide tick pattern implies mpp=1.0, a ~0.6km course extent, well outside
        # _PLAUSIBLE_EXTENT_KM. Cross-validation must reject it, regardless of any scale ratio.
        cal = calibrate.detect_scale_bar(self._bar_image(label="180m"), 20000.0)
        assert cal is None


class TestDetectGridCalibration:
    def _grid_image(self, xs: list[int], *, w: int = 400, h: int = 400) -> np.ndarray:
        image = _blank(h, w)
        for x in xs:
            cv2.line(image, (x, 0), (x, h - 1), (0, 80, 200), 4)  # RGB -> HSV hue ~108, in-band
        return image

    def test_regular_lines_yield_a_1km_calibration(self) -> None:
        cal = calibrate.detect_grid_calibration(self._grid_image([50, 100, 150, 200, 250]))
        assert cal is not None
        assert cal.meters == pytest.approx(1000.0)
        assert abs(cal.x2 - cal.x1) == pytest.approx(50.0, abs=2.0)

    def test_too_few_lines_reads_nothing(self) -> None:
        assert calibrate.detect_grid_calibration(self._grid_image([50, 100])) is None

    def test_irregular_spacing_reads_nothing(self) -> None:
        cal = calibrate.detect_grid_calibration(self._grid_image([50, 60, 200, 260, 340]))
        assert cal is None

    def test_blank_map_has_no_grid(self) -> None:
        assert calibrate.detect_grid_calibration(_blank()) is None


class TestDetectCircleDpi:
    """Purely geometric now (H1/C1's architecture change): no scale ratio in scope here at all --
    `calibrate_map` combines this dpi with an OCR'd ratio and cross-validates the combination via
    `_accept(..., check_paper=True)`, covered in `TestAccept` and `TestCalibrateMapPriority`.
    """

    _PURPLE_RGB = (170, 60, 150)  # tests/fixtures/synth_map.py's own validated ink (T020/ADR-011)

    def _circles_image(self, n: int, radius: int = 24) -> np.ndarray:
        image = _blank(500, 500)
        positions = [(80, 80), (400, 80), (80, 400), (400, 400), (240, 240)][:n]
        for x, y in positions:
            cv2.circle(image, (x, y), radius, self._PURPLE_RGB, 3)
        return image

    def test_measures_dpi_from_a_known_radius(self) -> None:
        # rel=0.2, not the tighter tolerance a "measurement" test would usually want: Hough's own
        # radius estimate for a *ring* (not a filled disc) measurably skews toward the ink's outer
        # edge rather than its drawn centre -- a known effect, confirmed against this fixture (the
        # drawn radius is 24px, Hough's own estimate lands close to 26-27px) -- exactly the kind of
        # slop ADR-016 already accepts for this fallback/cross-check-only tier.
        cfg = default_config()
        dpi = calibrate.detect_circle_dpi(self._circles_image(4, radius=24), cfg)
        assert dpi is not None
        expected = 25.4 * 2.0 * 24 / cfg.detector.circle_diameter_mm
        assert dpi == pytest.approx(expected, rel=0.2)

    def test_too_few_circles_is_not_trusted(self) -> None:
        cfg = default_config()
        assert calibrate.detect_circle_dpi(self._circles_image(2), cfg) is None

    def test_blank_map_has_no_circles(self) -> None:
        cfg = default_config()
        assert calibrate.detect_circle_dpi(_blank(), cfg) is None


class TestCalibrateMapPriority:
    """`calibrate_map`'s own orchestration (ADR-016's tier order, and the OCR-first requirement
    every tier now shares), isolated from the sub-detectors' real CV/OCR and from `_accept`'s own
    plausibility maths (each covered separately above) via monkeypatching. What is under test here
    is priority, short-circuiting, and that OCR gates every tier, not just tiers 2/3.
    """

    _IMAGE = np.zeros((4, 4, 3), dtype=np.uint8)
    _CAL = Calibration(x1=0, y1=0, x2=100, y2=0, meters=50)

    def _accept_everything(self, monkeypatch) -> None:
        monkeypatch.setattr(calibrate, "_implied_dpi", lambda mpp, sd: 300.0)
        monkeypatch.setattr(calibrate, "_accept", lambda *a, **k: True)

    def test_nothing_is_tried_without_ocr(self, monkeypatch) -> None:
        calls: list[str] = []
        monkeypatch.setattr(calibrate, "ocr_scale_denominator", lambda image: None)
        monkeypatch.setattr(
            calibrate, "detect_scale_bar", lambda image, sd: calls.append("bar") or None
        )
        monkeypatch.setattr(
            calibrate, "detect_grid_calibration", lambda image: calls.append("grid") or None
        )
        monkeypatch.setattr(
            calibrate, "detect_circle_dpi", lambda image, cfg: calls.append("circle") or None
        )
        result, pooled = calibrate.calibrate_map(self._IMAGE)
        assert result is None
        assert pooled is None
        assert calls == []

    def test_scale_bar_wins_and_short_circuits_grid_and_circle(self, monkeypatch) -> None:
        self._accept_everything(monkeypatch)
        calls: list[str] = []
        monkeypatch.setattr(calibrate, "ocr_scale_denominator", lambda image: 20000.0)
        monkeypatch.setattr(calibrate, "detect_scale_bar", lambda image, sd: self._CAL)
        monkeypatch.setattr(
            calibrate, "detect_grid_calibration", lambda image: calls.append("grid") or None
        )
        monkeypatch.setattr(
            calibrate, "detect_circle_dpi", lambda image, cfg: calls.append("circle") or None
        )
        result, pooled = calibrate.calibrate_map(self._IMAGE)
        assert result == calibrate.CalibrationResult(
            source="scale_bar", scale_denominator=20000.0, dpi=300.0, calibration=self._CAL
        )
        assert pooled == 20000.0
        assert calls == []

    def test_grid_wins_over_circle(self, monkeypatch) -> None:
        self._accept_everything(monkeypatch)
        calls: list[str] = []
        monkeypatch.setattr(calibrate, "ocr_scale_denominator", lambda image: 20000.0)
        monkeypatch.setattr(calibrate, "detect_scale_bar", lambda image, sd: None)
        monkeypatch.setattr(calibrate, "detect_grid_calibration", lambda image: self._CAL)
        monkeypatch.setattr(
            calibrate, "detect_circle_dpi", lambda image, cfg: calls.append("circle") or 300.0
        )
        result, pooled = calibrate.calibrate_map(self._IMAGE)
        assert result == calibrate.CalibrationResult(
            source="grid", scale_denominator=20000.0, dpi=300.0, calibration=self._CAL
        )
        assert pooled == 20000.0
        assert calls == []

    def test_circle_fires_when_bar_and_grid_do_not(self, monkeypatch) -> None:
        self._accept_everything(monkeypatch)
        monkeypatch.setattr(calibrate, "ocr_scale_denominator", lambda image: 20000.0)
        monkeypatch.setattr(calibrate, "detect_scale_bar", lambda image, sd: None)
        monkeypatch.setattr(calibrate, "detect_grid_calibration", lambda image: None)
        monkeypatch.setattr(calibrate, "detect_circle_dpi", lambda image, cfg: 300.0)
        result, pooled = calibrate.calibrate_map(self._IMAGE)
        assert result == calibrate.CalibrationResult(
            source="circle", scale_denominator=20000.0, dpi=300.0
        )
        assert pooled == 20000.0

    def test_a_candidate_that_fails_the_shared_guard_falls_through_to_no_signal(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(calibrate, "_implied_dpi", lambda mpp, sd: 300.0)
        monkeypatch.setattr(calibrate, "_accept", lambda *a, **k: False)
        monkeypatch.setattr(calibrate, "ocr_scale_denominator", lambda image: 20000.0)
        monkeypatch.setattr(calibrate, "detect_scale_bar", lambda image, sd: self._CAL)
        monkeypatch.setattr(calibrate, "detect_grid_calibration", lambda image: self._CAL)
        monkeypatch.setattr(calibrate, "detect_circle_dpi", lambda image, cfg: 300.0)
        result, pooled = calibrate.calibrate_map(self._IMAGE)
        assert result is None
        assert pooled == 20000.0  # the OCR read is still pooled even though nothing was accepted

    def test_no_signal_still_pools_the_ocr_read(self, monkeypatch) -> None:
        monkeypatch.setattr(calibrate, "ocr_scale_denominator", lambda image: 20000.0)
        monkeypatch.setattr(calibrate, "detect_scale_bar", lambda image, sd: None)
        monkeypatch.setattr(calibrate, "detect_grid_calibration", lambda image: None)
        monkeypatch.setattr(calibrate, "detect_circle_dpi", lambda image, cfg: None)
        result, pooled = calibrate.calibrate_map(self._IMAGE)
        assert result is None
        assert pooled == 20000.0


def _write_png(path, *, value: int = 255, size: int = 40) -> None:
    cv2.imwrite(str(path), np.full((size, size, 3), value, dtype=np.uint8))


class TestCalibrateCorpus:
    """The corpus-level orchestrator: skip-existing, the two-pass median-of-all-tiers fallback
    (H3), and one bad file never aborting the run (ADR-009, H4). `calibrate_map` itself is stubbed
    (tagged by each map's own pixel value) so this exercises orchestration, not detection. Scoping
    (M5) and refresh (C1's compounding finding) get their own test classes below.
    """

    def _fake_calibrate_map(self, image: np.ndarray, config) -> tuple:
        tag = int(image[0, 0, 0])
        if tag == 10:
            cal = Calibration(x1=0, y1=0, x2=50, y2=0, meters=1000)
            result = calibrate.CalibrationResult(
                source="grid", scale_denominator=20000.0, dpi=250.0, calibration=cal
            )
            return result, 20000.0
        if tag == 20:
            result = calibrate.CalibrationResult(
                source="circle", scale_denominator=18000.0, dpi=250.0
            )
            return result, 18000.0
        if tag == 40:
            return None, 22000.0
        return None, None

    def test_full_run(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(calibrate, "calibrate_map", self._fake_calibrate_map)

        existing = tmp_path / "already-has-meta"
        existing.mkdir()
        _write_png(existing / "map.png", value=99)
        (existing / "meta.toml").write_text('name = "owner map"\n', encoding="utf-8")

        measured_grid = tmp_path / "measured-grid"
        measured_grid.mkdir()
        _write_png(measured_grid / "map.png", value=10)

        measured_circle = tmp_path / "measured-circle"
        measured_circle.mkdir()
        _write_png(measured_circle / "map.png", value=20)

        no_signal = tmp_path / "no-signal"
        no_signal.mkdir()
        _write_png(no_signal / "map.png", value=30)

        no_signal_with_ocr = tmp_path / "no-signal-with-ocr"
        no_signal_with_ocr.mkdir()
        _write_png(no_signal_with_ocr / "map.png", value=40)

        report = calibrate.calibrate_corpus(tmp_path, name_prefix="")

        assert report.total == 5
        assert report.out_of_scope == 0
        assert report.skipped_existing == 1
        assert report.measured == 2
        assert report.assumed_default == 2
        assert report.errors == 0

        # the owner's own meta.toml is untouched
        assert (existing / "meta.toml").read_text(encoding="utf-8") == 'name = "owner map"\n'

        grid_meta = tomllib.loads((measured_grid / "meta.toml").read_text(encoding="utf-8"))
        assert grid_meta["calibration_source"] == "measured"
        assert grid_meta["calibration_tier"] == "grid"
        assert grid_meta["calibration"]["meters"] == 1000

        circle_meta = tomllib.loads((measured_circle / "meta.toml").read_text(encoding="utf-8"))
        assert circle_meta["calibration_source"] == "measured"
        assert circle_meta["calibration_tier"] == "circle"
        assert circle_meta["dpi"] == pytest.approx(250.0)
        assert circle_meta["scale_denominator"] == pytest.approx(18000.0)

        # fallback dpi: median of this run's measured dpis from ALL tiers, {250.0, 250.0} -> 250.0
        # (H3 -- the grid hit now contributes too, not just the circle one)
        # fallback scale_denominator: median of the pooled OCR reads {20000, 18000, 22000} -> 20000
        for d in (no_signal, no_signal_with_ocr):
            meta = tomllib.loads((d / "meta.toml").read_text(encoding="utf-8"))
            assert meta["calibration_source"] == "assumed_default"
            assert "calibration_tier" not in meta
            assert meta["dpi"] == pytest.approx(250.0)
            assert meta["scale_denominator"] == pytest.approx(20000.0)

    def test_no_measurements_at_all_falls_back_to_config_defaults(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setattr(calibrate, "calibrate_map", lambda image, config: (None, None))
        d = tmp_path / "lonely-map"
        d.mkdir()
        _write_png(d / "map.png", value=30)

        cfg = default_config()
        report = calibrate.calibrate_corpus(tmp_path, cfg, name_prefix="")

        assert report.measured == 0
        assert report.assumed_default == 1
        assert report.errors == 0
        meta = tomllib.loads((d / "meta.toml").read_text(encoding="utf-8"))
        assert meta["calibration_source"] == "assumed_default"
        assert meta["dpi"] == pytest.approx(cfg.map.default_dpi)
        assert meta["scale_denominator"] == pytest.approx(calibrate._FALLBACK_SCALE_DENOMINATOR)

    def test_a_bad_raster_degrades_to_assumed_default_and_is_counted_as_an_error(
        self, tmp_path
    ) -> None:
        d = tmp_path / "corrupt"
        d.mkdir()
        (d / "map.jpg").write_bytes(b"not actually a jpeg")

        report = calibrate.calibrate_corpus(tmp_path, name_prefix="")

        assert report.measured == 0
        assert report.assumed_default == 1
        assert report.errors == 1  # H4: a corrupt raster is now visible, not silently swallowed
        meta = tomllib.loads((d / "meta.toml").read_text(encoding="utf-8"))
        assert meta["calibration_source"] == "assumed_default"

    def test_empty_corpus_root_is_a_no_op(self, tmp_path) -> None:
        report = calibrate.calibrate_corpus(tmp_path / "does-not-exist", name_prefix="")
        assert report == calibrate.CorpusCalibrationReport(
            measured=0, assumed_default=0, skipped_existing=0, out_of_scope=0, errors=0, total=0
        )


class TestScopingToNamePrefix:
    """M5: the owner's own T017 validation scans share `data/maps/` with the M7 scraped corpus
    ADR-016's fabrication exception is actually scoped to -- `calibrate_corpus` must never write a
    fabricated `meta.toml` for the former, regardless of directory-layout accident.
    """

    def test_out_of_scope_directories_are_never_touched(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(calibrate, "calibrate_map", lambda image, config: (None, None))
        in_scope = tmp_path / "ogps-1234_deadbeef"
        in_scope.mkdir()
        _write_png(in_scope / "map.png")
        out_of_scope = tmp_path / "some-owner-scan"
        out_of_scope.mkdir()
        _write_png(out_of_scope / "map.png")

        report = calibrate.calibrate_corpus(tmp_path)  # default name_prefix="ogps-"

        assert report.total == 2
        assert report.out_of_scope == 1
        assert report.assumed_default == 1
        assert not (out_of_scope / "meta.toml").exists()
        assert (in_scope / "meta.toml").exists()

    def test_an_owner_scan_that_already_has_meta_is_also_left_alone(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setattr(calibrate, "calibrate_map", lambda image, config: (None, None))
        owner = tmp_path / "owner-scan"
        owner.mkdir()
        _write_png(owner / "map.png")
        (owner / "meta.toml").write_text("dpi = 200\nscale_denominator = 15000\n", encoding="utf-8")

        report = calibrate.calibrate_corpus(tmp_path)

        assert report.out_of_scope == 1
        assert report.skipped_existing == 0  # never even considered, not "skipped"
        assert (owner / "meta.toml").read_text(encoding="utf-8") == (
            "dpi = 200\nscale_denominator = 15000\n"
        )


class TestRefresh:
    """C1's compounding finding: the first version could never redo a corpus it had already
    written to. `refresh=True` must overwrite exactly this module's own past output and nothing
    else.
    """

    def test_refresh_overwrites_only_this_modules_own_output(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(calibrate, "calibrate_map", lambda image, config: (None, None))

        owner_authored = tmp_path / "ogps-owner"
        owner_authored.mkdir()
        _write_png(owner_authored / "map.png")
        (owner_authored / "meta.toml").write_text('name = "hand entered"\n', encoding="utf-8")

        auto_written = tmp_path / "ogps-auto"
        auto_written.mkdir()
        _write_png(auto_written / "map.png")
        (auto_written / "meta.toml").write_text(
            'calibration_source = "assumed_default"\ndpi = 300\nscale_denominator = 15000\n',
            encoding="utf-8",
        )

        report = calibrate.calibrate_corpus(tmp_path, name_prefix="ogps-", refresh=True)

        assert report.skipped_existing == 1  # the owner-authored one, never touched
        assert report.measured + report.assumed_default == 1  # the auto-written one, redone
        assert (
            owner_authored / "meta.toml"
        ).read_text(encoding="utf-8") == 'name = "hand entered"\n'

    def test_without_refresh_this_modules_own_output_is_also_left_alone(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setattr(calibrate, "calibrate_map", lambda image, config: (None, None))
        auto_written = tmp_path / "ogps-auto"
        auto_written.mkdir()
        _write_png(auto_written / "map.png")
        original = 'calibration_source = "assumed_default"\ndpi = 300\nscale_denominator = 15000\n'
        (auto_written / "meta.toml").write_text(original, encoding="utf-8")

        report = calibrate.calibrate_corpus(tmp_path, name_prefix="ogps-")

        assert report.skipped_existing == 1
        assert (auto_written / "meta.toml").read_text(encoding="utf-8") == original


class TestWrittenMetaRoundTripsThroughCorpusEntry:
    """The writer's output is exactly what `io/corpus.py::read_entry` expects (ADR-016's own
    "machine-distinguishable downstream" requirement) -- not just valid TOML in isolation.
    """

    def test_measured_calibration_block_roundtrips(self, tmp_path) -> None:
        d = tmp_path / "m"
        d.mkdir()
        cal = Calibration(x1=10, y1=20, x2=210, y2=20, meters=1000)
        calibrate._write_meta_toml(d, calibration_source="measured", tier="grid", calibration=cal)
        entry = read_entry(d)
        assert entry.calibration_source == "measured"
        assert entry.calibration_tier == "grid"
        assert entry.meters_per_pixel == pytest.approx(5.0)

    def test_assumed_default_dpi_pair_roundtrips(self, tmp_path) -> None:
        d = tmp_path / "m"
        d.mkdir()
        calibrate._write_meta_toml(
            d, calibration_source="assumed_default", dpi=300.0, scale_denominator=15000.0
        )
        entry = read_entry(d)
        assert entry.calibration_source == "assumed_default"
        assert entry.calibration_tier is None
        assert entry.meters_per_pixel == pytest.approx(1.27)
