"""Control number OCR and the points rule (T021, SPEC F8).

DoD: digits read from a crop beside each circle with a confidence; points rule `first_digit` /
`constant` / `csv`; unreadable numbers emit `points: null` and a flag, never a guess; OCR failure
degrades the run, never aborts it.

Measured against `clean_synthetic_map`, not the degraded standard fixture -- `ocr.py`'s own
module docstring documents why: its two crop-geometry findings (ring masking, margin headroom)
were measured there, and 11 of the fixture's 12 controls read correctly at that noise level. The
twelfth (`id=8`, truth number 83) sits close enough to the course boundary that its purple
out-of-bounds hatching lands inside even the widened crop margin -- a real, documented limitation,
not a bug, and exactly the case F8's "never a guess" line exists for.
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
from rogaine.vision.ocr import _apply_points_rule, read_control_number, read_control_numbers

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

    def test_the_boundary_control_is_flagged_null_not_a_wrong_guess(
        self, clean_synthetic_map
    ) -> None:
        sm = clean_synthetic_map
        cfg = default_config()
        detections = detect_controls(sm.image, sm.dpi, cfg)
        truth = [c for c in sm.controls if not c.is_hub]

        updated, flags = read_control_numbers(sm.image, detections, sm.dpi, cfg)
        det = next(
            d
            for d in updated
            if not d.is_hub
            and _nearest_truth(d, truth).number == _UNREADABLE_CONTROL_TRUTH_NUMBER
        )

        assert det.number is None
        assert det.points is None  # first_digit rule: no number, no points -- never a guess
        assert any(f"control {det.id}" in f for f in flags)


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
        sm = clean_synthetic_map
        cfg = _with_detector(default_config(), points_rule="first_digit")
        truth = next(c for c in sm.controls if c.number == _UNREADABLE_CONTROL_TRUTH_NUMBER)

        updated, flag = read_control_number(sm.image, truth, sm.dpi, cfg)

        assert updated.number is None
        assert updated.points is None
        assert flag is not None

    def test_constant_assigns_points_even_when_the_number_is_unreadable(
        self, clean_synthetic_map
    ) -> None:
        sm = clean_synthetic_map
        cfg = _with_detector(default_config(), points_rule="constant", points_constant=7)
        truth = next(c for c in sm.controls if c.number == _UNREADABLE_CONTROL_TRUTH_NUMBER)

        updated, flag = read_control_number(sm.image, truth, sm.dpi, cfg)

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
        sm = clean_synthetic_map
        cfg = _with_detector(default_config(), points_rule="csv")
        readable = sm.controls[1]
        unreadable = next(c for c in sm.controls if c.number == _UNREADABLE_CONTROL_TRUTH_NUMBER)

        readable_updated, _f1 = read_control_number(sm.image, readable, sm.dpi, cfg)
        unreadable_updated, _f2 = read_control_number(sm.image, unreadable, sm.dpi, cfg)

        assert readable_updated.points is None
        assert unreadable_updated.points is None
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

        # T083 baseline (ADR-023): 0/41. T084 measured: 19/41.
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
        # T090/ADR-031: the OCR-gated sub-1.0 fix now picks this map's true (smaller) scale, so the
        # circle count itself moves too -- 21 (T084's own count, at the old base-scale-only ladder)
        # -> 23 (2 more real rings found at the correct, smaller scale).
        assert len(circles) == 23, f"expected 23 detected circles, got {len(circles)}"

        updated, _flags = read_control_numbers(image, detections, dpi, cfg)
        n_read = sum(1 for c in updated if not c.is_hub and c.number is not None)

        # T083 baseline (ADR-023): 0/21. T084 measured: 6/21. T090/ADR-031 measured: 16/23.
        assert n_read >= 13, f"novo-kavgolovsky-lesopark read {n_read}/23 numbers, expected >= 13"

    @pytest.mark.skipif(
        not _KKM_TOKSOVO_PATH.is_file(),
        reason="data/maps/kkm-toksovo/map.jpg absent (ADR-010: gitignored real scan)",
    )
    def test_kkm_toksovo_read_rate_floor(self) -> None:
        """T090/ADR-031: this map's real control circles print smaller than ISOM spec (H2), gated
        to multiplier 0.85 by `_ocr_gate_sub_base_scale`'s OCR-outcome comparison. Before T090, the
        production ladder's base-scale (1.0) fit read only 1/25 -- the worst reader in the owner
        corpus.
        """
        cfg = default_config()
        dpi = resolve_dpi(_KKM_TOKSOVO_PATH, user_dpi=None)
        image = load_raster(_KKM_TOKSOVO_PATH)
        detections = detect_controls(image, dpi, cfg)
        circles = [c for c in detections if not c.is_hub]
        assert len(circles) == 25, f"expected 25 detected circles, got {len(circles)}"

        updated, _flags = read_control_numbers(image, detections, dpi, cfg)
        n_read = sum(1 for c in updated if not c.is_hub and c.number is not None)

        # Pre-T090 (base scale 1.0 only, ADR-030): 1/25. T090/ADR-031 measured: 8/25.
        assert n_read >= 6, f"kkm-toksovo read {n_read}/25 numbers, expected >= 6"

    @pytest.mark.skipif(
        not _LEMBOLOVO_KKM_PATH.is_file(),
        reason="data/maps/lembolovo-kkm/map.jpg absent (ADR-010: gitignored real scan)",
    )
    def test_lembolovo_kkm_read_rate_floor(self) -> None:
        """T090/ADR-031: gated to multiplier 0.5 (H2), which also finds 2 more real rings than the
        base-scale-only ladder did (20 -> 22 circles).
        """
        cfg = default_config()
        dpi = resolve_dpi(_LEMBOLOVO_KKM_PATH, user_dpi=None)
        image = load_raster(_LEMBOLOVO_KKM_PATH)
        detections = detect_controls(image, dpi, cfg)
        circles = [c for c in detections if not c.is_hub]
        assert len(circles) == 22, f"expected 22 detected circles, got {len(circles)}"

        updated, _flags = read_control_numbers(image, detections, dpi, cfg)
        n_read = sum(1 for c in updated if not c.is_hub and c.number is not None)

        # Pre-T090 (base scale 1.0 only, ADR-030): 7/20. T090/ADR-031 measured: 13/22.
        assert n_read >= 10, f"lembolovo-kkm read {n_read}/22 numbers, expected >= 10"
