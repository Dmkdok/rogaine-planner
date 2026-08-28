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

import numpy as np
import pytest

from rogaine.config import AppConfig, default_config
from rogaine.models import Control
from rogaine.vision.controls import detect_controls
from rogaine.vision.ocr import read_control_number, read_control_numbers

# The one fixture control close enough to the course boundary that its number is unreadable even
# with this module's widened crop margin (see the module docstring above and ocr.py's own).
_UNREADABLE_CONTROL_TRUTH_NUMBER = 83


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
