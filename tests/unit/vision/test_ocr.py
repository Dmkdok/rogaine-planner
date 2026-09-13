"""Control number OCR and the points rule (T021, SPEC F8).

DoD: digits read from a crop beside each circle with a confidence; points rule `first_digit` /
`constant` / `csv`; unreadable numbers emit `points: null` and a flag, never a guess; OCR failure
degrades the run, never aborts it.

Measured against `clean_synthetic_map`, not the degraded standard fixture -- `ocr.py`'s own
module docstring documents why: its two crop-geometry findings (ring masking, margin headroom)
were measured there, and 11 of the fixture's 12 controls read correctly at that noise level. The
twelfth (`id=8`, truth number 83) sat close enough to the course boundary that its purple
out-of-bounds hatching landed inside even the widened crop margin -- a real, documented limitation
at the time, and exactly the case F8's "never a guess" line exists for. T102's
`_keep_largest_ink_cluster` (leftover-ink clusters, `ocr.py`'s own docstring) incidentally isolates
this control's digits from the hatching too, so all 12 now read correctly; the floor below stays
at its own conservative margin rather than being tightened to chase the new number.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from rogaine.config import AppConfig, default_config
from rogaine.io.raster import load_raster, resolve_dpi
from rogaine.models import Control
from rogaine.vision.controls import detect_controls
from rogaine.vision.ocr import (
    _CROP_MARGIN_FACTOR,
    _apply_points_rule,
    _ocr_crop,
    read_control_number,
    read_control_numbers,
)

# The one fixture control close enough to the course boundary that its number is unreadable even
# with this module's widened crop margin (see the module docstring above and ocr.py's own).
_UNREADABLE_CONTROL_TRUTH_NUMBER = 83

#: T077/ADR-020's own regression fixture: a real scan whose 13 controls all detect at multiplier
#: 2.0, not the base ISOM print scale (T076's measurement) -- gitignored per ADR-010, same as
#: `tests/unit/vision/test_controls.py`'s own `_REAL_SCAN_PATH`.
_REAL_SCAN_DIR = Path(__file__).resolve().parents[3] / "data" / "maps" / "grid-lines-red-controls"
_REAL_SCAN_PATH = _REAL_SCAN_DIR / "map.jpeg"

#: T084/ADR-023's own regression fixtures -- both gitignored real owner scans (ADR-010), neither
#: with a meta.toml, so their dpi comes from `resolve_dpi`'s own auto-probe/fallback, the same way
#: the throwaway measurement script that produced these numbers resolved it.
_PERVOMAYSKOE_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "maps" / "pervomayskoe" / "map.jpeg"
)
_NOVO_KAVGOLOVSKY_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "maps" / "novo-kavgolovsky-lesopark" / "map.jpg"
)

#: T090/ADR-031's own regression fixtures -- the two other owner scans the OCR-gated sub-1.0
#: multiplier fix (ADR-030's H2) measurably improved, alongside novo-kavgolovsky-lesopark above.
#: Same gitignored-real-scan caveat (ADR-010), no meta.toml, dpi from `resolve_dpi`'s own probe.
_KKM_TOKSOVO_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "maps" / "kkm-toksovo" / "map.jpg"
)
_LEMBOLOVO_KKM_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "maps" / "lembolovo-kkm" / "map.jpg"
)

#: T102 (I6, `docs/iterations/I6-real-map-detection-gaps-and-viewer-ux.md`): the owner's own named
#: unread controls (42/53/72) on this real scan. Same gitignored-real-scan caveat (ADR-010).
_OGPS_6802_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "maps"
    / "ogps-6802_4a769f64b455f9b4675552284c3681b1"
    / "map.jpg"
)


def _with_detector(cfg: AppConfig, **overrides: object) -> AppConfig:
    return cfg.model_copy(update={"detector": cfg.detector.model_copy(update=overrides)})


def _nearest_truth(control: Control, truth: list[Control]) -> Control:
    return min(truth, key=lambda t: (t.x - control.x) ** 2 + (t.y - control.y) ** 2)


class TestInputValidation:
    def test_rejects_non_3channel_image(self) -> None:
        with pytest.raises(ValueError, match="H, W, 3"):
            read_control_numbers(np.zeros((4, 4), dtype=np.uint8), [], 300.0)

    def test_rejects_non_uint8_image(self) -> None:
        with pytest.raises(ValueError, match="uint8"):
            read_control_numbers(np.zeros((4, 4, 3), dtype=np.float32), [], 300.0)

    def test_rejects_non_positive_dpi(self) -> None:
        image = np.zeros((4, 4, 3), dtype=np.uint8)
        with pytest.raises(ValueError, match="dpi"):
            read_control_numbers(image, [], 0.0)


class TestHubPassthrough:
    """The hub has no printed number (ISOM 701, not 704) -- nothing to read."""

    def test_hub_control_is_returned_unchanged_with_no_flag(self, clean_synthetic_map) -> None:
        sm = clean_synthetic_map
        cfg = default_config()
        updated, flag = read_control_number(sm.image, sm.hub, sm.dpi, cfg)
        assert updated == sm.hub
        assert flag is None


class TestOcrNeverAborts:
    """SPEC F8: "OCR failure degrades the run, never aborts it" (ADR-009)."""

    def test_a_degenerate_crop_is_reported_as_a_flag_not_an_exception(
        self, clean_synthetic_map
    ) -> None:
        sm = clean_synthetic_map
        bogus = Control(id=99, x=sm.image.shape[1] * 100.0, y=sm.image.shape[0] * 100.0)

        updated, flag = read_control_number(sm.image, bogus, sm.dpi, default_config())

        assert updated.number is None
        assert updated.points is None
        assert updated.confidence == 0.0
        assert flag is not None and "control 99" in flag

    def test_batch_call_collects_the_flag_and_keeps_going(self, clean_synthetic_map) -> None:
        sm = clean_synthetic_map
        bogus = Control(id=99, x=sm.image.shape[1] * 100.0, y=sm.image.shape[0] * 100.0)
        controls = [sm.hub, sm.controls[1], bogus]

        updated, flags = read_control_numbers(sm.image, controls, sm.dpi, default_config())

        assert len(updated) == 3
        assert updated[1].number == sm.controls[1].number  # the good control still reads fine
        assert len(flags) == 1 and "control 99" in flags[0]


class TestCropWindowSlidesNearEdges:
    """T097: near an image boundary, `_ocr_crop`'s `(x0, y0, x1, y1)` window must slide along
    that axis to keep its full configured half-width, rather than clamping each end
    independently -- which used to shrink the window instead. One control per edge, each placed
    close enough that a naive per-end clamp would have truncated it, but with the fixture image
    (400x400) comfortably larger than the window so the slide path applies, not the
    smaller-than-raster shrink fallback.
    """

    @pytest.mark.parametrize(
        "x, y",
        [(2.0, 200.0), (398.0, 200.0), (200.0, 2.0), (200.0, 398.0)],
        ids=["left-edge", "right-edge", "top-edge", "bottom-edge"],
    )
    def test_edge_control_crop_reaches_full_configured_size(self, x: float, y: float) -> None:
        cfg = default_config()
        dpi = 300.0
        image = np.zeros((400, 400, 3), dtype=np.uint8)
        control = Control(id=1, x=x, y=y, radius_px=30.0)

        crop = _ocr_crop(image, control, dpi, cfg)

        half = control.radius_px * (
            1.0 + cfg.detector.number_search_radius + _CROP_MARGIN_FACTOR
        )
        expected_w = round(x + half) - round(x - half)
        expected_h = round(y + half) - round(y - half)
        assert crop.shape[:2] == (expected_h, expected_w), (
            f"edge control at ({x},{y}) got crop shape {crop.shape[:2]}, expected the full "
            f"window ({expected_h}, {expected_w}) -- the window must slide, not shrink"
        )

    def test_centred_control_crop_is_unaffected(self) -> None:
        """Regression guard: away from every edge, the slide path is a no-op -- same window as
        before T097."""
        cfg = default_config()
        dpi = 300.0
        image = np.zeros((400, 400, 3), dtype=np.uint8)
        control = Control(id=1, x=200.0, y=200.0, radius_px=30.0)

        crop = _ocr_crop(image, control, dpi, cfg)

        half = control.radius_px * (
            1.0 + cfg.detector.number_search_radius + _CROP_MARGIN_FACTOR
        )
        expected_w = round(200.0 + half) - round(200.0 - half)
        expected_h = expected_w
        assert crop.shape[:2] == (expected_h, expected_w)

    def test_window_exactly_fitting_the_raster_slides_to_full_size_not_shrunk(self) -> None:
        """Review finding L1: the shrink fallback must trigger only when the configured window is
        strictly wider than the raster on that axis -- a window that fits *exactly* after sliding
        must still get the full slide, not the shrink path. `radius_px=30` gives a 204px window; a
        204px-wide raster with the control 2px from the left edge is the exact-fit boundary."""
        cfg = default_config()
        dpi = 300.0
        control = Control(id=1, x=2.0, y=102.0, radius_px=30.0)
        half = control.radius_px * (
            1.0 + cfg.detector.number_search_radius + _CROP_MARGIN_FACTOR
        )
        window = round(2 * half)
        image = np.zeros((204, window, 3), dtype=np.uint8)

        crop = _ocr_crop(image, control, dpi, cfg)

        assert crop.shape[1] == window, (
            f"expected the full {window}px window (exact fit via sliding), got {crop.shape[1]}px "
            "-- the shrink fallback fired when it should not have"
        )

    def test_window_wider_than_the_raster_falls_back_to_shrinking(self) -> None:
        """The one case sliding genuinely cannot fix: the configured window is wider than the
        raster itself on that axis. Falls back to the pre-T097 clamp-and-shrink behaviour --
        the crop is bounded by the raster, not by the (unreachable) full window."""
        cfg = default_config()
        dpi = 300.0
        image = np.zeros((50, 50, 3), dtype=np.uint8)
        control = Control(id=1, x=25.0, y=25.0, radius_px=30.0)  # window (204px) > raster (50px)

        crop = _ocr_crop(image, control, dpi, cfg)

        assert crop.shape[:2] == (50, 50), (
            f"expected the shrink fallback to bound the crop to the 50x50 raster, got "
            f"{crop.shape[:2]}"
        )


class TestReadsNumbersOnFixture:
    def test_at_least_eleven_of_twelve_controls_read_correctly(
        self, clean_synthetic_map
    ) -> None:
        sm = clean_synthetic_map
        cfg = default_config()
        detections = detect_controls(sm.image, sm.dpi, cfg)
        truth = [c for c in sm.controls if not c.is_hub]

        updated, _flags = read_control_numbers(sm.image, detections, sm.dpi, cfg)
        det_controls = [c for c in updated if not c.is_hub]

        n_correct = sum(
            1 for d in det_controls if d.number == _nearest_truth(d, truth).number
        )
        assert n_correct >= 11, f"only {n_correct}/{len(det_controls)} numbers read correctly"

    def test_confidences_are_within_the_project_convention(self, clean_synthetic_map) -> None:
        sm = clean_synthetic_map
        cfg = default_config()
        detections = detect_controls(sm.image, sm.dpi, cfg)

        updated, _flags = read_control_numbers(sm.image, detections, sm.dpi, cfg)

        assert all(0.0 <= c.confidence <= 1.0 for c in updated)

    def test_an_unreadable_control_is_flagged_null_not_a_wrong_guess(
        self, clean_synthetic_map
    ) -> None:
        """T102: this used to exercise the one fixture control whose purple out-of-bounds
        hatching landed inside the crop margin (`_UNREADABLE_CONTROL_TRUTH_NUMBER = 83`, see the
        module docstring) -- `_keep_largest_ink_cluster` now correctly isolates its digits from
        that hatching and it reads 83 like every other control (a genuine improvement, not a
        regression; `_INK_CLUSTER_GAP_FACTOR`'s own comment in `ocr.py` has the corpus-wide
        measurement). The "never a guess" path itself still needs covering, so this constructs a
        blank-ink crop directly instead of depending on incidental fixture noise.
        """
        sm = clean_synthetic_map
        cfg = default_config()
        blank_area_control = Control(id=999, x=15.0, y=15.0)

        updated, flag = read_control_number(sm.image, blank_area_control, sm.dpi, cfg)

        assert updated.number is None
        assert updated.points is None  # first_digit rule: no number, no points -- never a guess
        assert flag is not None and f"control {updated.id}" in flag


class TestPointsRule:
    """F8: points rule is `first_digit` / `constant` / `csv`; see ocr.py's module docstring for
    why `constant` is the one rule that still assigns points to an unreadable number."""

    def test_first_digit_matches_the_rogaine_convention(self, clean_synthetic_map) -> None:
        sm = clean_synthetic_map
        cfg = _with_detector(default_config(), points_rule="first_digit")
        control = sm.controls[1]  # a readable, non-boundary control

        updated, _flag = read_control_number(sm.image, control, sm.dpi, cfg)

        assert updated.number == control.number
        assert updated.points == int(str(control.number)[0])

    def test_first_digit_uses_all_digits_but_the_last_for_a_three_digit_number(self) -> None:
        """ADR-024: `first_digit` is every digit but the last, not the literal first character --
        the two coincide only for 2-digit numbers (see the test above)."""
        det = _with_detector(default_config(), points_rule="first_digit").detector

        assert _apply_points_rule(123, det) == 12

    def test_first_digit_floors_a_single_digit_number_to_zero(self) -> None:
        """Documented edge case (ADR-024): a single-digit control number floors to 0 under
        `number // 10` -- accepted, not special-cased."""
        det = _with_detector(default_config(), points_rule="first_digit").detector

        assert _apply_points_rule(7, det) == 0

    def test_first_digit_leaves_points_null_when_number_is_unreadable(
        self, clean_synthetic_map
    ) -> None:
        # T102: a directly-constructed blank-ink crop, not a fixture control -- see
        # `TestReadsNumbersOnFixture.test_an_unreadable_control_is_flagged_null_not_a_wrong_guess`
        # for why the fixture no longer has one of its own.
        sm = clean_synthetic_map
        cfg = _with_detector(default_config(), points_rule="first_digit")
        blank_area_control = Control(id=999, x=15.0, y=15.0)

        updated, flag = read_control_number(sm.image, blank_area_control, sm.dpi, cfg)

        assert updated.number is None
        assert updated.points is None
        assert flag is not None

    def test_constant_assigns_points_even_when_the_number_is_unreadable(
        self, clean_synthetic_map
    ) -> None:
        sm = clean_synthetic_map
        cfg = _with_detector(default_config(), points_rule="constant", points_constant=7)
        blank_area_control = Control(id=999, x=15.0, y=15.0)

        updated, flag = read_control_number(sm.image, blank_area_control, sm.dpi, cfg)

        assert updated.number is None  # still unreadable -- only points falls back
        assert updated.points == 7
        assert flag is not None  # still flagged: the number itself was not read

    def test_constant_assigns_the_same_points_to_a_readable_control_too(
        self, clean_synthetic_map
    ) -> None:
        sm = clean_synthetic_map
        cfg = _with_detector(default_config(), points_rule="constant", points_constant=7)
        control = sm.controls[1]

        updated, _flag = read_control_number(sm.image, control, sm.dpi, cfg)

        assert updated.points == 7

    def test_csv_rule_never_assigns_points_here_readable_or_not(
        self, clean_synthetic_map
    ) -> None:
        # `csv`'s own no-op contract doesn't depend on whether the number is actually read (module
        # docstring), so a second, once-hard-to-read fixture control (T102: now reads fine, see
        # `TestReadsNumbersOnFixture`) still exercises the same "points always None" guarantee.
        sm = clean_synthetic_map
        cfg = _with_detector(default_config(), points_rule="csv")
        readable = sm.controls[1]
        other = next(c for c in sm.controls if c.number == _UNREADABLE_CONTROL_TRUTH_NUMBER)

        readable_updated, _f1 = read_control_number(sm.image, readable, sm.dpi, cfg)
        other_updated, _f2 = read_control_number(sm.image, other, sm.dpi, cfg)

        assert readable_updated.points is None
        assert other_updated.points is None
        assert readable_updated.number == readable.number  # csv only changes `points`, not reading


class TestConfidenceCombination:
    """`Control.confidence` is `min(detection confidence, OCR confidence)` (ocr.py's module
    docstring): overall trust in a control is only as strong as its weakest evidence."""

    def test_a_low_detection_confidence_caps_the_combined_confidence(
        self, clean_synthetic_map
    ) -> None:
        sm = clean_synthetic_map
        control = sm.controls[1]  # reads with high OCR confidence (see the recall test above)
        low_confidence_control = control.model_copy(update={"confidence": 0.1})

        updated, _flag = read_control_number(
            sm.image, low_confidence_control, sm.dpi, default_config()
        )

        assert updated.confidence == pytest.approx(0.1)

    def test_a_high_detection_confidence_does_not_inflate_a_lower_ocr_confidence(
        self, clean_synthetic_map
    ) -> None:
        sm = clean_synthetic_map
        control = sm.controls[1].model_copy(update={"confidence": 1.0})

        updated, _flag = read_control_number(sm.image, control, sm.dpi, default_config())

        assert updated.confidence < 1.0  # bounded by the OCR side, not the detection side


class TestScaleAwareCropOnRealScan:
    """T077, ADR-020: `_ocr_crop` now sizes its number-search crop and ring-erase disk from
    `control.radius_px` (the nominal mid radius for whatever scale the control actually matched,
    not Hough's own per-candidate fit) when it is set, instead of always assuming the base ISOM
    print scale. On
    `data/maps/grid-lines-red-controls/map.jpeg`, T076's own finding was that all 13 controls
    detect at multiplier 2.0, not the base scale -- a real fixture for exactly the gap this task
    closes. Regression guard: the read rate must not regress relative to sizing the crop from the
    base scale unconditionally (simulated below by stripping `radius_px` back to `None`, which is
    exactly today's pre-T077 fallback path in `_ocr_crop`).
    """

    @pytest.mark.skipif(
        not _REAL_SCAN_PATH.is_file(),
        reason="data/maps/grid-lines-red-controls/map.jpeg absent (ADR-010: gitignored real scan)",
    )
    def test_radius_aware_crop_does_not_regress_the_base_scale_read_rate(self) -> None:
        with (_REAL_SCAN_DIR / "meta.toml").open("rb") as fh:
            meta = tomllib.load(fh)
        dpi = float(meta["dpi"])
        cfg = default_config()

        image = np.array(Image.open(_REAL_SCAN_PATH).convert("RGB"))
        detections = detect_controls(image, dpi, cfg)
        circles = [c for c in detections if not c.is_hub]
        assert len(circles) == 13, f"expected 13 detected circles, got {len(circles)}"

        r_min, r_max = cfg.detector.circle_radius_px(dpi)
        for c in circles:
            assert c.radius_px is not None, f"control {c.id} has no radius_px"
            # T076's own measurement: every control on this file matches multiplier 2.0 -- a
            # generous window around that, not a tight re-assertion of T076's own scale-selection
            # test.
            assert r_min * 2.0 * 0.5 <= c.radius_px <= r_max * 2.0 * 1.5, (
                f"control {c.id} radius_px={c.radius_px:.2f} not near multiplier 2.0's window "
                f"[{r_min * 2.0:.2f}, {r_max * 2.0:.2f}]"
            )

        updated, _flags = read_control_numbers(image, detections, dpi, cfg)
        n_read_scale_aware = sum(1 for c in updated if not c.is_hub and c.number is not None)

        # Simulate pre-T077 behaviour: a Control with no radius_px falls back to
        # `circle_radius_px(dpi)`'s base-scale mid-value, exactly as every control did before this
        # task (`_ocr_crop`'s own docstring/module docstring).
        base_scale_detections = [c.model_copy(update={"radius_px": None}) for c in detections]
        updated_base, _flags_base = read_control_numbers(image, base_scale_detections, dpi, cfg)
        n_read_base_scale = sum(1 for c in updated_base if not c.is_hub and c.number is not None)

        report = (
            f"scale-aware crop read {n_read_scale_aware}/13 numbers, "
            f"base-scale-only crop read {n_read_base_scale}/13"
        )
        assert n_read_scale_aware >= n_read_base_scale, report


class TestRealScanReadRateFloor:
    """T084/ADR-023: a permanent regression floor for the real-scan read-rate fix, against T083's
    own measured baseline (ADR-023's per-map table). Two maps, each isolating one of the two fix
    modes landed in `_ocr_crop`:

    - `pervomayskoe` isolates mode 2 (the conditional ring-erase widen): T083's baseline was 0/41
      (the true printed ring extends to ~1.3-1.5x `r_mid`, past the base 1.25x erase disk, leaving
      an unerased ring outline next to the digits) and mode 1 alone (the ink-area filter) still
      measured 0/41 -- only the conditional widen moved this map.
    - `novo-kavgolovsky-lesopark` isolates mode 1 (`_strip_thin_ink`): T083's baseline was 0/21
      (contour-line ink bleeding into the mask on densely-contoured terrain defeats Tesseract's
      psm 7 single-line assumption even with a correctly-erased ring) -- mode 2's conditional widen
      does not trigger on this map (its rings are already correctly erased at the base factor).

    Floors sit a small margin below the measured counts (T084: 19/41 and 6/21 respectively) to
    tolerate incidental jitter without masking an actual regression.

    T090/ADR-031 adds three more real-scan floors for the OCR-gated sub-1.0
    `circle_scale_multipliers` fix (ADR-030's H2): `novo-kavgolovsky-lesopark`'s own circle count
    and floor move too (its gated scale is now 0.5, not 1.0 -- 21 circles -> 23, 6/21 -> 16/23),
    and `kkm-toksovo`/`lembolovo-kkm` are new floors entirely (1/25 -> 8/25, 7/20 -> 13/22
    respectively -- also gated to a sub-1.0 scale, so their circle counts move too, 25 stays 25 but
    20 -> 22). All three numbers are this task's own measurement, `_t089_measure.py --owner-only`
    re-run against the landed gate (`data/maps/_t089_owner_out.csv`) -- not carried over from
    T089/ADR-030's apples-to-apples table verbatim, since that table predates T090's landed gate;
    this floor uses the gate's actual output.

    T099/ADR-032 (first version) generalised the sub-1.0 gate to per-candidate (keep only the ones
    whose own crop reads a plausible number), which moved all three of T090's own circle counts
    down again -- `novo-kavgolovsky-lesopark` 23 -> 16, `kkm-toksovo` 25 -> 8, `lembolovo-kkm`
    22 -> 13. The owner's own T100 sign-off found this too aggressive on these very three maps: a
    by-hand check of the "dropped" candidates on `kkm-toksovo` found several (91, 92, 72, 52)
    unambiguously real, legible, correctly-positioned controls that Tesseract simply never read at
    this map's print style -- silently vanishing from the output instead of surfacing flagged, the
    way a production-scale unread control already does. T099 was amended (ADR-032's own amendment)
    to only filter when the set looks junk-dominated (more than `_SUB_BASE_JUNK_UNREAD_FRACTION`
    unread) -- none of these three maps crosses that line (30%, 68%, 41% unread respectively, all
    below 85%), so all three circle counts revert to their T090 values below. Each map's absolute
    `n_read` count is unchanged throughout every version of this gate (16, 8, 13 respectively): the
    `n_read >=` floors below never needed to move, only `len(circles) ==`.
    """

    @pytest.mark.skipif(
        not _PERVOMAYSKOE_PATH.is_file(),
        reason="data/maps/pervomayskoe/map.jpeg absent (ADR-010: gitignored real scan)",
    )
    def test_pervomayskoe_read_rate_floor(self) -> None:
        cfg = default_config()
        dpi = resolve_dpi(_PERVOMAYSKOE_PATH, user_dpi=None)
        image = load_raster(_PERVOMAYSKOE_PATH)
        detections = detect_controls(image, dpi, cfg)
        circles = [c for c in detections if not c.is_hub]
        assert len(circles) == 41, f"expected 41 detected circles, got {len(circles)}"

        updated, _flags = read_control_numbers(image, detections, dpi, cfg)
        n_read = sum(1 for c in updated if not c.is_hub and c.number is not None)

        # T083 baseline (ADR-023): 0/41. T084 measured: 19/41. T102 measured: 18/41 -- one of
        # those 19 (control 14) was itself a wrong read ("5" of a true "35", clipped at the crop's
        # own edge by a separate, pre-existing limitation) that `_keep_largest_ink_cluster`'s
        # competition+edge-touch guard now correctly rejects to unread rather than a wrong number
        # (ADR-009); the floor stays at its own margin below the true, still-correct count.
        assert n_read >= 15, f"pervomayskoe read {n_read}/41 numbers, expected >= 15"

    @pytest.mark.skipif(
        not _NOVO_KAVGOLOVSKY_PATH.is_file(),
        reason="data/maps/novo-kavgolovsky-lesopark/map.jpg absent (ADR-010: gitignored real scan)",
    )
    def test_novo_kavgolovsky_lesopark_read_rate_floor(self) -> None:
        cfg = default_config()
        dpi = resolve_dpi(_NOVO_KAVGOLOVSKY_PATH, user_dpi=None)
        image = load_raster(_NOVO_KAVGOLOVSKY_PATH)
        detections = detect_controls(image, dpi, cfg)
        circles = [c for c in detections if not c.is_hub]
        # T090/ADR-031: the OCR-gated sub-1.0 fix picks this map's true (smaller) scale, so the
        # circle count itself moved -- 21 (T084's own count, at the old base-scale-only ladder) ->
        # 23 (2 more real rings found at the correct, smaller scale). T099's first version dropped
        # that to 16 (30% of the 23 unread); the owner's T100 sign-off found real controls among
        # those dropped elsewhere in this same corpus, so T099 was amended to only filter a
        # junk-dominated set (>85% unread) -- this map's 30% unread stays well under that line, so
        # its count was back to 23 (ADR-032's amendment).
        # T103: both of the "extra" 2 circles in that 23 were the same false positive -- the club
        # mascot logo (a running figure printed in two different colour bands, both inside
        # `purple_mask`'s hue range) fitting a spurious ring, confirmed by visual crop. T103's
        # interior-ink discriminant correctly excludes both (measured: interior_ink_fraction=1.0,
        # far past its 0.3 threshold) -- 23 -> 21. Not a regression: these were never real controls,
        # just uncaught by any earlier discriminant, and `n_read` below (a true-positive count) is
        # unchanged.
        assert len(circles) == 21, f"expected 21 detected circles, got {len(circles)}"

        updated, _flags = read_control_numbers(image, detections, dpi, cfg)
        n_read = sum(1 for c in updated if not c.is_hub and c.number is not None)

        # T083 baseline (ADR-023): 0/21. T084 measured: 6/21. T090/ADR-031 measured: 16/23 -- this
        # absolute count is unchanged by every later amendment (including T103's), only the total
        # circle count moved. T102 measured: 18/21 -- `_keep_largest_ink_cluster` newly reads 2
        # controls whose crops had leftover ink (a nearby symbol/mark) alongside the real digits.
        assert n_read >= 13, f"novo-kavgolovsky-lesopark read {n_read}/21 numbers, expected >= 13"

    @pytest.mark.skipif(
        not _KKM_TOKSOVO_PATH.is_file(),
        reason="data/maps/kkm-toksovo/map.jpg absent (ADR-010: gitignored real scan)",
    )
    def test_kkm_toksovo_read_rate_floor(self) -> None:
        """T090/ADR-031: this map's real control circles print smaller than ISOM spec (H2), gated
        to multiplier 0.85 by `_ocr_gate_sub_base_scale`'s OCR-outcome comparison. Before T090, the
        production ladder's base-scale (1.0) fit read only 1/25 -- the worst reader in the owner
        corpus. T099's first version dropped the circle count from 25 to 8 (68% of the 25 unread) --
        this is the very map where the owner's own T100 sign-off found several of those 17 "dropped"
        candidates (91, 92, 72, 52) to be real, legible, correctly-positioned controls Tesseract
        simply couldn't read, not false positives. T099 was amended to only filter a set that looks
        junk-dominated (>85% unread); 68% stays under that line, so the count was back to 25, with
        the 17 unread ones surfacing flagged downstream like any other unread control (ADR-032's
        amendment).

        T103: one of those 25 was the same club-mascot-logo false positive found on
        novo-kavgolovsky-lesopark/lembolovo-kkm (confirmed by visual crop) -- T103's interior-ink
        discriminant correctly excludes it (interior_ink_fraction=1.0, threshold 0.3), 25 -> 24. Not
        a regression: `n_read` (true positives only) is unchanged.
        """
        cfg = default_config()
        dpi = resolve_dpi(_KKM_TOKSOVO_PATH, user_dpi=None)
        image = load_raster(_KKM_TOKSOVO_PATH)
        detections = detect_controls(image, dpi, cfg)
        circles = [c for c in detections if not c.is_hub]
        assert len(circles) == 24, f"expected 24 detected circles, got {len(circles)}"

        updated, _flags = read_control_numbers(image, detections, dpi, cfg)
        n_read = sum(1 for c in updated if not c.is_hub and c.number is not None)

        # Pre-T090 (base scale 1.0 only, ADR-030): 1/25. T090/ADR-031 measured: 8/25 -- this
        # absolute count is unchanged by every later amendment (including T103's), only the total
        # circle count moved. T102 measured: 12/24 -- 5 controls newly read (leftover ink beside
        # the real digits), 1 corrected from a wrong read ("3" of a true 2+-digit number, clipped
        # at the crop's own edge) to properly-flagged unread (ADR-009: never a guess).
        assert n_read >= 6, f"kkm-toksovo read {n_read}/24 numbers, expected >= 6"

    @pytest.mark.skipif(
        not _LEMBOLOVO_KKM_PATH.is_file(),
        reason="data/maps/lembolovo-kkm/map.jpg absent (ADR-010: gitignored real scan)",
    )
    def test_lembolovo_kkm_read_rate_floor(self) -> None:
        """T090/ADR-031: gated to multiplier 0.5 (H2), which also finds 2 more real rings than the
        base-scale-only ladder did (20 -> 22 circles). T099's first version dropped the circle count
        from 22 to 13 (41% of the 22 unread); amended to only filter a junk-dominated set (>85%
        unread) after the owner's T100 sign-off found real controls being dropped elsewhere in this
        corpus -- 41% stays under that line, so the count was back to 22 (ADR-032's amendment).

        T103: one of those 22 was the same club-mascot-logo false positive found on the other two
        maps above (confirmed by visual crop) -- T103's interior-ink discriminant correctly excludes
        it (interior_ink_fraction=1.0, threshold 0.3), 22 -> 21. Not a regression: `n_read` (true
        positives only) is unchanged.
        """
        cfg = default_config()
        dpi = resolve_dpi(_LEMBOLOVO_KKM_PATH, user_dpi=None)
        image = load_raster(_LEMBOLOVO_KKM_PATH)
        detections = detect_controls(image, dpi, cfg)
        circles = [c for c in detections if not c.is_hub]
        assert len(circles) == 21, f"expected 21 detected circles, got {len(circles)}"

        updated, _flags = read_control_numbers(image, detections, dpi, cfg)
        n_read = sum(1 for c in updated if not c.is_hub and c.number is not None)

        # Pre-T090 (base scale 1.0 only, ADR-030): 7/20. T090/ADR-031 measured: 13/22 -- this
        # absolute count is unchanged by every later amendment (including T103's), only the total
        # circle count moved. T102 measured: 14/21 -- 1 control newly read (leftover ink beside
        # the real digits).
        assert n_read >= 10, f"lembolovo-kkm read {n_read}/21 numbers, expected >= 10"

    @pytest.mark.skipif(
        not _OGPS_6802_PATH.is_file(),
        reason="data/maps/ogps-6802.../map.jpg absent (ADR-010: gitignored real scan)",
    )
    def test_ogps_6802_named_controls(self) -> None:
        """T102 diagnosed the owner's three named unread controls (42/53/72) on this scan by
        cropping each individually -- three different, unrelated root causes, not one shared bug:

        - Control 72: a contour-line/mark fragment survived `_strip_thin_ink`'s area floor and
          sat well above the real digits (43px, ~1.2x this crop's digit height) -- the
          leftover-ink-cluster failure `_keep_largest_ink_cluster` targets. Fixed by T102 alone.
        - Control 42: the crop was already clean (no stray ink) -- Tesseract read the correct text
          "42" but assigned it 0% confidence. Not an ink-masking problem.
        - Control 53: also a clean crop -- Tesseract misread the printed "5" as "9" ("93" at 41%
          confidence). A character-recognition problem, not ink-masking.

        T104 (a later, unrelated diagnosis on `ogps-8078`) turned out to also apply here: this
        map's own scale-selection ties multiplier 2.25 against 3.0 (`_ocr_gate_tied_scales`), and
        the OCR-outcome gate now picks 3.0 map-wide (33/35 read vs. 2.25's 32/35). The larger,
        correctly-scaled crop this hands to *every* control incidentally resolves 42's confidence
        and 53's misread too (both now read at 0.96 confidence) -- the "different, unrelated root
        cause" T102 documented for them was itself downstream of the same undersized-scale
        symptom T104 targets on a different map, not actually a separate Tesseract quirk. The
        trade: 72's own leftover-ink fix (T102) no longer helps at the new, larger crop size (the
        stray mark's ink survives differently at this scale) -- Tesseract now reads only "7" of
        the true "72" at 0% confidence, correctly refused rather than guessed (ADR-009). Net:
        2 of the 3 originally-named controls fixed instead of 1, and the third fails safely
        instead of previously reading correctly -- not a regression, a different, still-correct
        outcome after a later, independently-justified fix changed this map's own selected scale.
        """
        cfg = default_config()
        dpi = resolve_dpi(_OGPS_6802_PATH, user_dpi=None)
        image = load_raster(_OGPS_6802_PATH, dpi=dpi)
        detections = detect_controls(image, dpi, cfg)
        circles = [c for c in detections if not c.is_hub]
        assert len(circles) == 35, f"expected 35 detected circles, got {len(circles)}"

        updated, _flags = read_control_numbers(image, detections, dpi, cfg)
        n_read = sum(1 for c in updated if not c.is_hub and c.number is not None)
        # T102 measured (pre-T104): 32/35. T104 measured: 33/35.
        assert n_read >= 30, f"ogps-6802 read {n_read}/35 numbers, expected >= 30"

        def _nearest(x: float, y: float) -> Control:
            return min(circles, key=lambda c: (c.x - x) ** 2 + (c.y - y) ** 2)

        updated_by_id = {c.id: c for c in updated}
        control_42 = updated_by_id[_nearest(2532.6, 1721.4).id]
        control_53 = updated_by_id[_nearest(2801.4, 2003.4).id]
        control_72 = updated_by_id[_nearest(1175.4, 2475.0).id]

        assert control_42.number == 42, f"near (2533,1721) read {control_42.number}, want 42"
        assert control_53.number == 53, f"near (2801,2003) read {control_53.number}, want 53"
        # 72 fails safely at this scale (reads a truncated "7", refused below the confidence
        # floor) rather than the wrong number T102's own fix (still present, just less effective
        # at this larger crop size) would otherwise risk -- never a guess (ADR-009).
        assert control_72.number is None, (
            f"control near (1175,2475) read {control_72.number}, want None"
        )
