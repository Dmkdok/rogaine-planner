"""Control number OCR and the points rule (T021, SPEC F8).

Reads each non-hub `Control`'s printed number (ISOM 704: Arial, 4.0 mm) from a crop of the map
raster and derives `points` from it. This is explicitly the most fragile step in the pipeline
(ADR-009: "reading two digits from a map is the most fragile step in the pipeline") -- Tesseract
was chosen over EasyOCR (drags in torch) or a VLM (cost, determinism) *because* it is allowed to be
weak: ADR-009's whole point is that OCR quality never gates a route. Concretely that means:

- A number that cannot be read confidently never becomes a guess. It comes back `number=None`, and
  the batch function below reports a human-readable flag for it -- the same "report, don't silently
  drop" shape `rogaine.io.corpus.CorpusEntry.problems`/`missing` already use for gaps elsewhere in
  the pipeline.
- A `pytesseract`/Tesseract failure anywhere in one control's read (a malformed crop, a missing
  binary, a timeout) is caught and folded into the same "unreadable" path, never propagated. One
  bad control must not take down a batch of otherwise-good ones -- see `read_control_number`'s
  `try`.

**Resolving the DoD's own ambiguity (T021 task notes).** The DoD says "unreadable numbers emit
`points: null` and a flag, never a guess", stated as a blanket rule. But ADR-009's decision text
already carves out an exception in the same breath it states the rule: "Unread numbers produce
`points: null` plus a flag; **the points rule can fall back to a constant**". A constant-points
control's score does not depend on the printed number at all -- assigning it is not "a guess", it
is exactly the deterministic value the config says every control is worth, computed from the
*rule*, not the *reading*. Treating an unreadable number as a hard block on `points` under
`points_rule == "constant"` would mean a single smudged digit gates an entire route's scoring,
which is precisely what ADR-009's "OCR quality never gates a route" consequence exists to prevent.
This module therefore reads the DoD's blanket wording as describing the default (`first_digit`)
case, where `points` is genuinely derived from the number and an unreadable number leaves it
`None`, while `constant` still assigns `points_constant` regardless of whether the number was read.
In every case -- readable or not, whichever rule is active -- an unreadable number still emits its
flag and leaves `number=None`; only `points` under `constant` diverges from the blanket rule, and
only because the DoD's own justification (ADR-009) says it should. `csv` is unaffected either way:
see below.

**Crop geometry and two real findings from measuring against the fixture (T021).**
`config.detector.number_search_radius` is "how far from the circle edge to look for the number, in
circle radii" -- a size, not a direction. The synthetic fixture happens to place every number
upper-right of its circle (`tests/fixtures/synth_map.py`'s `_place_controls`), but nothing in ISOM
704 fixes that placement on a real map, so `_ocr_crop` below takes a square window centred on the
control, reaching past the circle's edge by the configured radius on every side -- a generous
superset, not a re-derivation of the fixture's one specific offset. The circle's own radius is
never taken from the incoming `Control` (T020 does not carry it, only centre and detection
confidence) -- it is re-derived from `dpi` via `config.detector.circle_radius_px`, the same
fixed-on-paper convention `vision/controls.py` documents at length.

Two things about the raw crop measurably defeat Tesseract, found by running the pipeline end to
end against `clean_synthetic_map` and checking what actually came back (not by guessing and
re-tuning blind -- the same discipline T020's own docstring insists on):

1. **The control circle (ISOM 703) is printed in the same purple ink as the number (704).** Left
   in the crop, Tesseract's line segmentation reads the ring itself as text (`"O*"`-shaped
   garbage) or merges it with the real digits, and recognises nothing useful. `purple_mask`
   (already built for T020) isolates the ink; `_CIRCLE_MASK_RADIUS_FACTOR` then blanks a disk
   around the crop's known centre wide enough to erase the ring's own stroke width and rendering
   slop -- measured against the fixture: smaller multipliers left a visible crescent of ring in
   the mask that Tesseract still choked on.
2. **A bare `number_search_radius` crop clips the second digit.** At the config's own reach
   (radius x (1 + `number_search_radius`), no headroom), Tesseract's recognised-word bounding box
   for a typical ISOM two-digit number sat flush against the crop's right edge, and only one digit
   came back: 1 of 12 controls read correctly on the clean fixture. `_CROP_MARGIN_FACTOR` adds
   headroom (again in circle radii, so it scales with `dpi` the same way every other size in this
   module does) purely for this segmentation slack -- it does not change what "how far to search"
   means, the way a larger `number_search_radius` in config would. Measured against the fixture: 0
   extra reach -> 1/12 correct; this module's `_CROP_MARGIN_FACTOR` -> 11/12 (a wider margin
   still, e.g. twice this, scores *worse*: a bigger crop has more chance of catching a
   neighbouring control's number or the purple out-of-bounds hatching -- both the same ink again;
   see `test_ocr.py` for the one fixture control this still does not resolve, close enough to the
   course boundary that its hatching lands inside even this margin).

**Confidence.** `pytesseract.image_to_data` gives a per-word confidence, 0-100, or -1 where
Tesseract has nothing to say (e.g. block/paragraph/line-level rows with no recognised text).
`_read_digits` normalises that to this project's `[0, 1]` convention and averages across every
non-empty word in the crop (ordinarily exactly one -- the whole control number). The `Control` this
module returns combines that OCR confidence with the *detection* confidence already on the
incoming `Control` (T020's "how well this matched a circle shape", nothing to do with reading
digits) by taking the **minimum** of the two. Overall trust in a control is only as strong as its
weakest evidence -- a beautifully detected circle whose number could not be read is not a control
we are confident about, even though the shape match alone was perfect.

**`points_rule == "csv"` is a no-op placeholder here, on purpose.** Reading `controls.csv` is
T022's job (`rogaine.io.controls_csv`, not built yet). Under this rule `points` always comes back
`None` from this module regardless of OCR success -- T022's future merge step is what fills it in.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytesseract

from rogaine.config import AppConfig, DetectorSettings, default_config
from rogaine.models import Control
from rogaine.vision.controls import purple_mask

# A number crop holds one short line of digits, not a page -- psm 7 ("treat the image as a single
# text line") measured meaningfully more confident than psm 8 ("single word") on this project's own
# Hershey-font synthetic numbers (96 vs 45 average confidence on a sample "45" crop), likely because
# Tesseract's word-level segmentation second-guesses a single isolated word more than a single line.
# The whitelist restricts recognition to the only characters a control number can contain.
_TESSERACT_CONFIG = "--psm 7 -c tessedit_char_whitelist=0123456789"

# See the module docstring's two measured findings for where these numbers come from.
_CIRCLE_MASK_RADIUS_FACTOR = 1.25
_CROP_MARGIN_FACTOR = 0.6


def _ocr_crop(image: np.ndarray, control: Control, dpi: float, cfg: AppConfig) -> np.ndarray:
    """The black-ink-on-white crop `pytesseract` reads from: a generous square around *control*,
    purple ink only, with the control's own circle ring erased (module docstring)."""
    det = cfg.detector
    r_min, r_max = det.circle_radius_px(dpi)
    r_mid = (r_min + r_max) / 2.0
    half = r_mid * (1.0 + det.number_search_radius + _CROP_MARGIN_FACTOR)

    h_img, w_img = image.shape[:2]
    x0 = max(0, round(control.x - half))
    x1 = min(w_img, round(control.x + half))
    y0 = max(0, round(control.y - half))
    y1 = min(h_img, round(control.y + half))
    crop = image[y0:y1, x0:x1]

    mask = purple_mask(crop, cfg)
    h, w = mask.shape
    cx, cy = control.x - x0, control.y - y0
    yy, xx = np.ogrid[:h, :w]
    ring = (xx - cx) ** 2 + (yy - cy) ** 2 <= (r_mid * _CIRCLE_MASK_RADIUS_FACTOR) ** 2
    ink = mask & ~ring
    return np.where(ink, 0, 255).astype(np.uint8)


def _read_digits(crop: np.ndarray) -> tuple[str, float]:
    """Run Tesseract on *crop* (as built by `_ocr_crop`). Returns `(digits, confidence in [0, 1])`;
    `("", 0.0)` covers both "Tesseract found nothing" and the caller's own caught exception -- from
    the outside, an OCR call that raised and one that ran and saw no text are the same "unreadable"
    outcome (SPEC F8, ADR-009)."""
    rgb = cv2.cvtColor(crop, cv2.COLOR_GRAY2RGB)
    data = pytesseract.image_to_data(
        rgb, config=_TESSERACT_CONFIG, output_type=pytesseract.Output.DICT
    )
    words = [
        (text, conf)
        for text, conf in zip(data["text"], data["conf"], strict=True)
        if text.strip()
    ]
    if not words:
        return "", 0.0

    digits = "".join(text for text, _ in words)
    confidences = [conf / 100.0 for _, conf in words if conf >= 0]
    confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return digits, confidence


def _apply_points_rule(number: int | None, det: DetectorSettings) -> int | None:
    """Points for one control, given its (possibly unreadable) number. See module docstring for the
    `constant`-vs-unreadable resolution and the `csv` no-op."""
    if det.points_rule == "csv":
        return None
    if det.points_rule == "constant":
        return det.points_constant
    # first_digit: the general form -- the first character of the number's decimal string, not a
    # hardcoded `// 10` -- so a 1- or 3-digit control number is handled correctly too, even though
    # this project's fixture only ever generates 2-digit ones.
    if number is None:
        return None
    return int(str(number)[0])


def read_control_number(
    image: np.ndarray, control: Control, dpi: float, config: AppConfig | None = None
) -> tuple[Control, str | None]:
    """Read one control's printed number and derive its points.

    Returns the updated `Control` (same `id`, same detection `x`/`y`/`source`/`is_hub`) plus a
    human-readable flag string when the number could not be read, or `None` when it was. The hub is
    passed through completely unchanged -- it has no number to read. Building the crop and running
    Tesseract both happen inside one `try`: any failure in either step (a malformed crop, a
    missing Tesseract binary, a timeout) is treated exactly like a clean "no text found" result,
    never raised -- "OCR failure degrades the run, never aborts it" (SPEC F8, ADR-009).
    """
    if control.is_hub:
        return control, None

    cfg = config or default_config()
    det = cfg.detector
    try:
        digits, ocr_confidence = _read_digits(_ocr_crop(image, control, dpi, cfg))
        exc: Exception | None = None
    except Exception as caught:  # pytesseract.TesseractNotFoundError, TesseractError, a bad crop
        digits, ocr_confidence, exc = "", 0.0, caught

    number: int | None = None
    flag: str | None = None
    if exc is not None:
        flag = f"control {control.id}: OCR raised {type(exc).__name__}: {exc}"
    elif not digits:
        flag = f"control {control.id}: OCR found no digits"
    elif ocr_confidence < det.min_ocr_confidence:
        flag = (
            f"control {control.id}: OCR confidence {ocr_confidence:.2f} below floor "
            f"{det.min_ocr_confidence:.2f} (read '{digits}')"
        )
    else:
        number = int(digits)

    overall_confidence = min(control.confidence, ocr_confidence)
    points = _apply_points_rule(number, det)
    updated = control.model_copy(
        update={"number": number, "points": points, "confidence": overall_confidence}
    )
    return updated, flag


def read_control_numbers(
    image: np.ndarray, controls: list[Control], dpi: float, config: AppConfig | None = None
) -> tuple[list[Control], list[str]]:
    """Read every non-hub control's number in *controls* (T020's `detect_controls` output) and apply
    the configured points rule (SPEC F8).

    *image* is RGB uint8 (`rogaine.models.MapContext`'s convention). Returns the updated controls in
    the same order (the hub, if present, passed through unchanged) plus a flag for every control
    whose number came back unreadable -- never a raised exception, matching ADR-009's "OCR quality
    never gates a route".
    """
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"expected an (H, W, 3) RGB image, got shape {image.shape}")
    if image.dtype != np.uint8:
        raise ValueError(f"expected uint8 pixels, got {image.dtype}")
    if not dpi > 0:
        raise ValueError(f"dpi must be positive, got {dpi}")

    cfg = config or default_config()
    updated: list[Control] = []
    flags: list[str] = []
    for control in controls:
        new_control, flag = read_control_number(image, control, dpi, cfg)
        updated.append(new_control)
        if flag is not None:
            flags.append(flag)
    return updated, flags
