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
superset, not a re-derivation of the fixture's one specific offset. The circle's own radius comes
from `control.radius_px` when it is set (T077/ADR-020: the *nominal* mid radius for whatever scale
`vision/controls.py`'s `circle_scale_multipliers` sweep actually matched -- not necessarily the
base ISOM print size, and deliberately not Hough's own noisier per-candidate fit; see
`_detect_circles`'s inline comment for the measured reason). It is re-derived from `dpi` via
`config.detector.circle_radius_px`'s own mid-value only when `radius_px` is `None` -- the hub (a
triangle has no radius) and any `Control` built another way (a CSV round-trip, a hand-built
fixture, a manual edit), keeping this module's behaviour on those unchanged. A base-scale
(multiplier 1.0) control's `radius_px` is bit-identical to that fallback value, so this change is
strictly additive for any control matched at the base scale -- only a non-base-scale match sees a
different (correctly larger) crop.

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

# T084/ADR-023 mode 1: minimum connected-component area to survive `_strip_thin_ink`, computed as
# this fraction of the expected digit height (`number_font_height_mm` converted to px), squared:
# `(digit_height_px * _MIN_INK_AREA_FACTOR) ** 2` -- squared because area, not a linear kernel
# size, is what a connected-component filter tests against a
# stroke that is thin in one dimension but spans nearly the full digit height in the other. Swept
# in 0.02 steps from 0.0 to 0.40 against both the synthetic fixture and the full real corpus (a
# throwaway script under data/maps/, same pattern as T083's): the synthetic fixture's 11/12 floor
# held everywhere from 0.0 to 0.30 (only breaking down at 0.40+, where the filter starts eating
# genuine digit strokes on some real maps too), while the real corpus total climbed from the
# unfiltered 80/416 to a broad plateau of 169-179/416 across 0.16-0.24 -- 0.20 sits mid-plateau
# (176/416) rather than chasing the single noisiest point (0.21's 179/416).
_MIN_INK_AREA_FACTOR = 0.20

# T084/ADR-023 mode 2: on some real scans the ring-erase disk above (r_mid *
# _CIRCLE_MASK_RADIUS_FACTOR) undershoots the real printed ring -- measured directly on
# `pervomayskoe` (radial ink-density profile around the detected centre): the true ring band sits
# at ~1.3-1.5x r_mid, well past the disk's 1.25x edge. A *global* widen was tried and rejected: it
# helps the undershoot maps but measurably hurts maps whose ring was already correctly erased at
# 1.25x (e.g. `toksovo-1` 19/21 -> 13/21 at a global 1.50x -- the wider disk starts eating into
# nearby digit ink instead). Widening only when a residual ring is actually still detectable past
# the base disk avoids that: swept against the full real corpus, every threshold/widened-factor
# combination in {0.3, 0.4, 0.5} x {1.50, 1.55, 1.60} left every already-correct map's count
# unchanged while `pervomayskoe` (0/41 at every mode-1-only factor) jumped to 19/41 and
# `history-race-2024-michurinskoe` (an undershoot case T083 did not separately flag) climbed from
# 2/37 to 5-14/37. 0.4/1.55 sits mid-range rather than the single best point.
_RING_CHECK_OUTER_RATIO = 1.2
_RING_DENSITY_WIDEN_THRESHOLD = 0.4
_WIDENED_CIRCLE_MASK_RADIUS_FACTOR = 1.55


def _strip_thin_ink(ink: np.ndarray, min_area: float) -> np.ndarray:
    """Drop every connected component of *ink* whose pixel area is under *min_area*.

    T084/ADR-023 mode 1: real scans leave behind ink `purple_mask`/the ring erasure above do not
    catch -- a squiggly shoreline or contour-line edge that happens to clear the hue/saturation/
    value floor, or contour ink bleeding in on densely-contoured terrain. Left in, it defeats
    Tesseract's psm 7 single-line assumption even when the crop is otherwise correctly framed and
    the ring correctly erased (measured: `novo-kavgolovsky-lesopark` control 1, `kkm-toksovo`
    controls 1/5). A morphological opening was tried first and rejected: even its smallest
    non-trivial kernel shaved corners off the *surviving* ink and cost the synthetic fixture's
    11/12 floor at every kernel size that helped the real corpus. A connected-component area
    filter never touches a surviving component's own pixels -- it only removes components too
    small in total area to be a digit stroke, which stays gentle on the synthetic fixture's own
    (thin but full-height) Hershey strokes while still dropping small isolated real-scan noise
    blobs.
    """
    if min_area <= 0:
        return ink
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        ink.astype(np.uint8), connectivity=8
    )
    keep = np.zeros_like(ink)
    for label in range(1, n_labels):  # label 0 is the background
        if stats[label, cv2.CC_STAT_AREA] >= min_area:
            keep |= labels == label
    return keep


def _annulus_ink_density(
    mask: np.ndarray, cx: float, cy: float, r_inner: float, r_outer: float
) -> float:
    """Fraction of the annulus `[r_inner, r_outer)` around `(cx, cy)` that *mask* covers.

    Close to 1 for a mostly-closed printed ring surviving in that band, much lower for scattered
    digit or noise ink -- the residual-ring signal `_ocr_crop` uses to decide whether to widen its
    erase disk (T084/ADR-023 mode 2)."""
    h, w = mask.shape
    yy, xx = np.ogrid[:h, :w]
    r2 = (xx - cx) ** 2 + (yy - cy) ** 2
    annulus = (r2 >= r_inner**2) & (r2 < r_outer**2)
    total = annulus.sum()
    if total == 0:
        return 0.0
    return float(mask[annulus].sum()) / float(total)


def _ocr_crop(image: np.ndarray, control: Control, dpi: float, cfg: AppConfig) -> np.ndarray:
    """The black-ink-on-white crop `pytesseract` reads from: a generous square around *control*,
    purple ink only, with the control's own circle ring erased and any remaining ink too small to
    be a digit stroke stripped out too (module docstring, T084/ADR-023)."""
    det = cfg.detector
    r_min, r_max = det.circle_radius_px(dpi)
    base_r_mid = (r_min + r_max) / 2.0
    r_mid = control.radius_px if control.radius_px is not None else base_r_mid
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

    # T084/ADR-023 mode 2: widen the ring-erase disk only when a residual ring survives just past
    # the base disk's edge (see the constants' own comment for the measured reasoning).
    density = _annulus_ink_density(
        mask,
        cx,
        cy,
        r_mid * _CIRCLE_MASK_RADIUS_FACTOR,
        r_mid * _CIRCLE_MASK_RADIUS_FACTOR * _RING_CHECK_OUTER_RATIO,
    )
    erase_factor = (
        _WIDENED_CIRCLE_MASK_RADIUS_FACTOR
        if density > _RING_DENSITY_WIDEN_THRESHOLD
        else _CIRCLE_MASK_RADIUS_FACTOR
    )
    yy, xx = np.ogrid[:h, :w]
    ring = (xx - cx) ** 2 + (yy - cy) ** 2 <= (r_mid * erase_factor) ** 2
    ink = mask & ~ring

    # T084/ADR-023 mode 1: a control matched at a non-base circle_scale_multiplier (T077/ADR-020)
    # was printed bigger by the same ratio its circle was, so the expected digit size scales with
    # r_mid the same way the ring-erase disk above already does.
    scale = r_mid / base_r_mid if base_r_mid > 0 else 1.0
    digit_height_px = det.number_font_height_mm * (dpi / 25.4) * scale
    ink = _strip_thin_ink(ink, (digit_height_px * _MIN_INK_AREA_FACTOR) ** 2)

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
