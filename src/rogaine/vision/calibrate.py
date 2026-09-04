"""Per-map best-effort auto-calibration for the M7 training corpus (T078, ADR-016).

`data/maps/` exists to improve *content* recognition for M7's SegFormer corpus (T070), not to
produce distance-accurate output -- a real end user's own map is still calibrated through the
existing manual path (SPEC F3, `io/scale.py::Calibration`), completely unaffected by this module.
ADR-016's own corpus survey found that a detector chasing only trustworthy, cross-validated scale
signals calibrates roughly a quarter to a third of the corpus at best, so this is one lightweight,
best-effort layered detector -- no new maths, `io/scale.py::Calibration`/`mpp_from_dpi` do all the
arithmetic -- tried in priority order per map, first hit wins:

1. :func:`detect_scale_bar` -- a printed graphical scale bar.
2. :func:`detect_grid_calibration` -- coordinate/magnetic-north grid spacing.
3. :func:`detect_circle_dpi` -- control-circle diameter (`config.detector.circle_diameter_mm`), a
   fallback/cross-check only (ADR-016).

**Every tier requires `ocr_scale_denominator` to have read a "1:N" ratio on the same map before it
is trusted** -- this was not true of tier 1 in this module's first version, and an independent
review of that version's real-corpus run found the gap live: a scale-bar-shaped row whose "label"
was actually a legend/contour number (`ogps-7212...`, `meters=180`) passed unchecked. Tiers 1/2 use
the OCR'd ratio to derive an *implied* dpi (`_implied_dpi`); tier 3 measures its own dpi directly
and uses the ratio only to reach a ground distance at all (it has no ground-distance signal of its
own). Every tier's candidate, regardless of how its dpi was obtained, passes through one shared
guard (:func:`_accept`, C1 of that review) before being trusted: the raster's own implied physical
course extent must be a plausible rogaine-map size (`_PLAUSIBLE_EXTENT_KM`), the implied dpi must be
a plausible scan resolution (`_PLAUSIBLE_DPI`), and -- tier 3 only, since it is the one tier with an
independently *measured* dpi rather than one merely implied by a raw ground measurement -- the
implied printed-paper size must be plausible too (`_PLAUSIBLE_PAPER_MM`). The version that shipped
without this guard had `_PLAUSIBLE_MPP`, a per-pixel ratio check that rejected nothing real: it
passed both the `ogps-7212...` false positive above and `dpi=1790.7` circle-tier results implying a
71x50mm printed sheet (`ogps-8043...`) -- neither wrong per-pixel ratio, both wrong at any real
physical scale.

When none of the three fire (the expected majority, per the survey), the map is not excluded --
:func:`calibrate_corpus` still writes a real `meta.toml`, with `dpi`/`scale_denominator` set to the
median of this run's own successful measurements *from all three tiers* (a data-informed default,
not an arbitrary pick) and `calibration_source = "assumed_default"`, versus `"measured"` (plus a
`calibration_tier` key naming which one) for the maps this module actually measured -- both
machine-distinguishable downstream exactly as ADR-016 requires.

**Scope**: `calibrate_corpus` only ever touches directories whose name starts with `name_prefix`
(default `"ogps-"`, the M7 scraped-map naming convention, ADR-014). ADR-016's fabrication exception
is scoped explicitly to "this internal M7 training corpus" -- never the owner's own T017 validation
scans, which happen to live in the same `data/maps/` root. The review above also found this
module's first version had no way to redo a corpus it had already written to (`calibrate_corpus`
unconditionally skips any directory with a `meta.toml`, including its own past output) -- `refresh`
opts a re-run into overwriting exactly the directories carrying this module's own
`calibration_source` key, and nothing else.

**Explicit judgement calls, flagged here rather than silently decided elsewhere (T078's own
instructions invite this)**:

- Tier 2's real-world grid interval (`_GRID_INTERVAL_METERS`) is assumed to be 1000m -- the
  standard interval a printed coordinate/kilometre grid represents on a topographic-base map,
  regardless of the map's own print scale. ADR-016 discusses grid spacing being "at a known
  interval" but never states the number; this is this module's own reading of that phrase.
- :func:`detect_grid_calibration` only ever looks for near-*vertical* lines (the corpus-survey
  script it is adapted from, `data/maps/_survey_grid_color.py`, did the same). A grid drawn as
  horizontal-only lines is invisible to it -- not exercised on the real corpus this session
  (ADR-016's survey sample had no such map), so unconfirmed either way.
- :func:`ocr_scale_denominator` reads English only (`pytesseract`'s default), not the
  `lang="rus+eng"` this session's own survey script used (`data/maps/_survey_calibration.py`) --
  the Docker image (`Dockerfile`) installs only the base `tesseract-ocr` package, no
  `tesseract-ocr-rus` language data, and a "1:N" ratio is digits and a colon, language-independent.
- The assumed-default fallback's `scale_denominator`, when this run's own OCR pool is empty (should
  not happen at corpus scale -- the survey found scale-ratio text on 20% of a 40-map sample), falls
  back further to a literal constant (`_FALLBACK_SCALE_DENOMINATOR`, a plausible round rogaine
  scale) -- never exercised in the real T078 corpus run, per its own landing note in
  `docs/TASKS.md`.
- `_PLAUSIBLE_EXTENT_KM`/`_PLAUSIBLE_DPI`/`_PLAUSIBLE_PAPER_MM`'s own bounds are this module's
  judgement, not a cited standard -- wide enough to admit any real rogaine map (from a short urban
  score event to a multi-day wilderness one), tight enough to reject the two concrete false
  positives the independent review found. Worth the owner's own sanity check against a wider real
  sample than this session's.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
import pytesseract

from rogaine.config import AppConfig, default_config
from rogaine.io.corpus import META_NAME, list_corpus
from rogaine.io.raster import load_raster
from rogaine.io.scale import Calibration, mpp_from_dpi
from rogaine.vision.controls import purple_mask

# --- OCR: scale-ratio text (every tier needs this) --------------------------------------------
_OCR_MAX_DIM = 1600  # matches this session's corpus-survey scripts' own downscale (ADR-016)
# Bounded (~2000-100000, a real independent-review finding: unbounded, "1.500" inside unrelated
# text read as a 1:500 ratio) and anchored with a left/right digit boundary so a larger number
# ("21:50000") cannot be misread as a smaller one ("1:50000") by matching only its tail/head.
# ":" only, not "." -- a decimal point is not this project's printed scale-ratio convention and
# matched too much unrelated text in the same review.
_SCALE_RATIO_RE = re.compile(r"(?<!\d)1\s*:\s*(\d{4,6})(?!\d)")
_SCALE_DENOMINATOR_RANGE = (2000.0, 100_000.0)

# --- Tier 1: printed graphical scale bar -----------------------------------------------------
_BAR_DARK_THRESHOLD = 110  # gray value below this counts as ink for run detection
_BAR_MIN_SEGMENTS = 3  # at least this many alternating ticks make a ruler, not a stray dashed line
_BAR_REGULARITY_MAX = 0.35  # tick-width std/mean
_BAR_WIDTH_FRACTION = (0.06, 0.5)  # a scale bar spans a modest slice of the map's width, unlike a
# near-full-width border rule (ADR-012's own grid/border finding)
_DISTANCE_LABEL_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(km|км|m|м)\b", re.IGNORECASE)
# A scale-bar label crop is small and sparse (a few digits, mostly white) -- Tesseract's default
# psm 3 ("fully automatic page segmentation") found no text at all on such a crop in testing; psm 6
# ("assume a single uniform block of text") reads it reliably.
_DISTANCE_LABEL_OCR_CONFIG = "--psm 6"

# --- Tier 2: coordinate/magnetic-north grid ---------------------------------------------------
# HSV band and regularity threshold from this session's corpus-survey script
# (`data/maps/_survey_grid_color.py`, ADR-016), which measured this heuristic catching more real
# grid lines than a grayscale-Hough pass (15% vs 10% of a 40-map sample).
_GRID_HSV_LOWER = (90, 40, 120)
_GRID_HSV_UPPER = (140, 255, 255)
_GRID_LINE_CLUSTER_GAP_PX = 5
_GRID_MIN_GAP_PX = 10
_GRID_MIN_LINES = 3
_GRID_MAX_REGULARITY = 0.2
_GRID_INTERVAL_METERS = 1000.0  # explicit assumption -- see module docstring

# --- Tier 3: control-circle diameter fallback -------------------------------------------------
_CIRCLE_MIN_RADIUS_PX = 3
_CIRCLE_MAX_RADIUS_FRACTION = 0.125  # of min(height, width) -- generous, dpi-independent
_CIRCLE_MIN_CANDIDATES = 3  # ADR-015's "one map, one hand-drawn circle scale throughout"
_CIRCLE_RING_COVERAGE_MIN = 0.5

# --- Shared plausibility guard for every tier's candidate result (C1) --------------------------
# All three come from an independent review of this module's first real-corpus run, which found
# the previous single per-pixel-ratio guard (`_PLAUSIBLE_MPP`) rejected nothing real: it passed a
# scale-bar reading a legend number as "180m" (implying a 0.44 x 0.59 km course) and a circle-tier
# dpi of 1790.7 (implying a 71x50mm printed sheet). None of the three bounds is a cited standard --
# see the module docstring's own judgement-call note.
_PLAUSIBLE_DPI = (72.0, 1200.0)  # a plausible scan/print resolution
_PLAUSIBLE_EXTENT_KM = (1.5, 40.0)  # a plausible rogaine course's physical width on the ground
_PLAUSIBLE_PAPER_MM = (100.0, 2000.0)  # a plausible printed-sheet width (tier 3 only -- see below)

# --- Assumed-default fallback (ADR-016: "the median of this run's successful measurements") ----
_FALLBACK_SCALE_DENOMINATOR = 15000.0  # last resort only -- see module docstring

#: Directories this module is allowed to write to (ADR-016's fabrication exception is scoped to
#: the M7 scraped-map corpus specifically, never the owner's own T017 validation scans that share
#: the same `data/maps/` root -- module docstring's own "Scope" note).
DEFAULT_NAME_PREFIX = "ogps-"


@dataclass(frozen=True)
class CalibrationResult:
    """One map's auto-calibration outcome (ADR-016). *scale_denominator* and *dpi* are always
    populated -- every tier now requires an OCR'd scale ratio to fire at all (module docstring), so
    every result has one, and *dpi* is either directly measured (tier 3) or implied by combining a
    raw ground-distance measurement with that ratio (tiers 1/2, `_implied_dpi`) -- either way a real
    number `calibrate_corpus` can pool for the assumed-default fallback (all three tiers, not tier 3
    alone). *calibration* is the real two-point ground measurement, set only for tiers 1/2 --
    `_write_meta_toml` prefers it (a `[calibration]` block, zero information lost) over the
    (*dpi*, *scale_denominator*) pair tier 3 is limited to.
    """

    source: Literal["scale_bar", "grid", "circle"]
    scale_denominator: float
    dpi: float
    calibration: Calibration | None = None

    def __post_init__(self) -> None:
        if self.source in ("scale_bar", "grid") and self.calibration is None:
            raise ValueError(f"a {self.source!r} result must carry `calibration`")


@dataclass(frozen=True)
class CorpusCalibrationReport:
    """Counts from one `calibrate_corpus` run (T078's DoD: "report counts... at the end")."""

    measured: int
    assumed_default: int
    skipped_existing: int
    out_of_scope: int
    errors: int
    total: int


def _true_runs(flags: np.ndarray) -> list[tuple[int, int]]:
    """Inclusive ``(start, end)`` index pairs of every contiguous ``True`` run in a 1-D boolean
    array (the same vectorised idiom `vision/segment.py`'s own private `_true_runs` uses --
    duplicated rather than imported, to keep this module decoupled from segmentation's private API).
    """
    padded = np.concatenate(([False], flags, [False]))
    edges = np.diff(padded.astype(np.int8))
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1) - 1
    return list(zip(starts.tolist(), ends.tolist(), strict=True))


def _downscale(image: np.ndarray, max_dim: int = _OCR_MAX_DIM) -> tuple[np.ndarray, float]:
    """*image* resized so its longer side is at most *max_dim* -- faster OCR/Hough passes over 200+
    maps, matching this session's corpus-survey scripts' own downscale (ADR-016). Returns the
    (possibly unchanged) image and the scale factor applied, so pixel measurements can be projected
    back to the original raster's coordinates.
    """
    h, w = image.shape[:2]
    scale = min(1.0, max_dim / max(h, w))
    if scale >= 1.0:
        return image, 1.0
    small = cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return small, scale


def _implied_dpi(meters_per_pixel: float, scale_denominator: float) -> float | None:
    """dpi implied by a raw two-point ground-distance measurement plus an OCR'd scale ratio -- the
    algebraic inverse of `io/scale.py::mpp_from_dpi`. Tiers 1/2 have no dpi of their own (a scale
    bar or a grid measures ground distance directly, never a paper size); this is how their
    candidate result is cross-validated against the map's own printed scale (C1/H1, module
    docstring) and how they get a poolable dpi for the assumed-default fallback (H3).
    """
    if meters_per_pixel <= 0:
        return None
    return 25.4 * scale_denominator / (1000.0 * meters_per_pixel)


def _accept(
    width_px: float, meters_per_pixel: float, dpi: float, *, check_paper: bool = False
) -> bool:
    """The one shared plausibility guard applied to every tier's candidate result (C1) --
    superseding the first version's `_PLAUSIBLE_MPP`, a per-pixel ratio that rejected nothing real
    (module docstring). *dpi* must already be a real number here (measured, tier 3, or implied,
    tiers 1/2 via `_implied_dpi`) -- a candidate whose own `_implied_dpi` came back `None` never
    reaches this function.

    *check_paper* -- tier 3 only (its caller passes it): the printed-sheet-size check only makes
    sense against a dpi that was *measured* (a real circle's real ink), not one merely implied by
    combining an unrelated raw ground measurement with the OCR'd ratio (tiers 1/2) -- for those,
    the same information is already covered by the extent check in different units.
    """
    dpi_lo, dpi_hi = _PLAUSIBLE_DPI
    if not (dpi_lo <= dpi <= dpi_hi):
        return False

    extent_km = width_px * meters_per_pixel / 1000.0
    ext_lo, ext_hi = _PLAUSIBLE_EXTENT_KM
    if not (ext_lo <= extent_km <= ext_hi):
        return False

    if check_paper:
        paper_mm = width_px * 25.4 / dpi
        pap_lo, pap_hi = _PLAUSIBLE_PAPER_MM
        if not (pap_lo <= paper_mm <= pap_hi):
            return False

    return True


def ocr_scale_denominator(image: np.ndarray) -> float | None:
    """Best-effort OCR read of a printed "1:N" scale-ratio somewhere on the map -- every tier now
    needs this before it can fire at all (module docstring).

    Mirrors this session's corpus-survey script (`data/maps/_survey_calibration.py`, ADR-016) that
    measured this pattern's real hit rate (8/40, 20%) -- same downscale -- with two deliberate
    differences from it, both from real findings against the actual corpus (module docstring/M3):
    English only, not `lang="rus+eng"`; and a bounded, digit-anchored regex, not an unbounded one.
    """
    small, _ = _downscale(image)
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    try:
        text = pytesseract.image_to_string(gray)
    except pytesseract.TesseractNotFoundError:
        # Systemic (the binary itself is missing/misconfigured), not a per-map read failure --
        # let this propagate so `calibrate_corpus`'s own error counter (H4) sees it, rather than
        # silently reading as "no scale text found" on every single map in the corpus.
        raise
    except Exception:  # a genuine per-crop OCR failure -- never abort (ADR-009)
        return None
    match = _SCALE_RATIO_RE.search(text)
    if match is None:
        return None
    try:
        denominator = float(match.group(1))
    except ValueError:
        return None
    lo, hi = _SCALE_DENOMINATOR_RANGE
    return denominator if lo <= denominator <= hi else None


def _read_distance_label(
    gray: np.ndarray, x0: int, x1: int, y: int, h: int, w: int
) -> float | None:
    """OCR the strip around a candidate scale-bar row for a "<number> m/km" style label, returning
    the largest parsed ground distance -- a ruler's far end is conventionally labelled with its
    total length.
    """
    margin = max(10, (x1 - x0) // 4)
    top, bottom = max(0, y - 3 * margin), min(h, y + 3 * margin)
    left, right = max(0, x0 - margin), min(w, x1 + margin)
    crop = gray[top:bottom, left:right]
    try:
        text = pytesseract.image_to_string(crop, config=_DISTANCE_LABEL_OCR_CONFIG)
    except pytesseract.TesseractNotFoundError:
        raise  # systemic -- see ocr_scale_denominator's own comment
    except Exception:  # a genuine per-crop OCR failure -- never abort (ADR-009)
        return None

    best: float | None = None
    for number, unit in _DISTANCE_LABEL_RE.findall(text):
        try:
            value = float(number.replace(",", "."))
        except ValueError:
            continue
        if unit.lower() in ("km", "км"):
            value *= 1000.0
        if best is None or value > best:
            best = value
    return best


def detect_scale_bar(image: np.ndarray, scale_denominator: float) -> Calibration | None:
    """Tier 1 (ADR-016): a printed graphical scale bar -- a short horizontal ruler with alternating
    dark/light ticks, labelled at at least one end with a real ground distance.

    *scale_denominator* (already OCR'd by the caller) is required: an independent review of this
    module's first version found it accepted the *first* syntactically-parseable "<number> m/km"
    label near a tick pattern with no further check, including a legend/contour number that
    happened to sit near a run of dark pixels (`ogps-7212...`, module docstring). Every row
    candidate is now cross-validated (`_accept`) before being returned; a candidate that fails is
    not trusted, but does not stop the scan either -- a later, real scale bar elsewhere in the
    image still gets a chance.

    Best-effort and, per ADR-016's own corpus survey, essentially unvalidated against a real
    positive: none of the 40 sampled maps had a confirmed graphical scale bar.
    """
    small, scale = _downscale(image)
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    dark = gray < _BAR_DARK_THRESHOLD
    width_px = float(image.shape[1])

    for y in range(h // 2, h, 2):  # scale bars conventionally sit in the bottom margin
        runs = _true_runs(dark[y])
        if len(runs) < _BAR_MIN_SEGMENTS:
            continue
        widths = np.array([end - start + 1 for start, end in runs], dtype=np.float64)
        if widths.mean() == 0 or widths.std() / widths.mean() > _BAR_REGULARITY_MAX:
            continue
        span = runs[-1][1] - runs[0][0] + 1
        if not (_BAR_WIDTH_FRACTION[0] * w <= span <= _BAR_WIDTH_FRACTION[1] * w):
            continue

        x0, x1 = runs[0][0], runs[-1][1]
        meters = _read_distance_label(gray, x0, x1, y, h, w)
        if meters is None:
            continue
        cal = Calibration(x1=x0 / scale, y1=y / scale, x2=x1 / scale, y2=y / scale, meters=meters)
        dpi = _implied_dpi(cal.meters_per_pixel, scale_denominator)
        if dpi is not None and _accept(width_px, cal.meters_per_pixel, dpi):
            return cal

    return None


def detect_grid_calibration(image: np.ndarray) -> Calibration | None:
    """Tier 2's raw grid signal (ADR-016): regularly-spaced near-vertical blue/cyan-ish lines, the
    fingerprint of a coordinate or magnetic-north grid. Purely geometric -- the caller
    (:func:`calibrate_map`) cross-validates the result against an OCR'd scale ratio via
    `_implied_dpi`/`_accept` before trusting it (H1: this used to be a presence check only, "a
    scale ratio exists somewhere on this map", never actually checked against the measured
    spacing).

    Assumes the spacing between adjacent lines means `_GRID_INTERVAL_METERS` (module docstring's
    explicit-assumptions note), and only ever looks for vertical lines (also noted there).
    """
    small, scale = _downscale(image)
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, _GRID_HSV_LOWER, _GRID_HSV_UPPER)
    h = mask.shape[0]
    col_frac = mask.sum(axis=0) / 255.0 / h
    candidate_cols = np.flatnonzero(col_frac > 0.5)
    if candidate_cols.size == 0:
        return None

    lines: list[float] = []
    start = prev = candidate_cols[0]
    for col in candidate_cols[1:]:
        if col - prev > _GRID_LINE_CLUSTER_GAP_PX:
            lines.append((start + prev) / 2.0)
            start = col
        prev = col
    lines.append((start + prev) / 2.0)
    if len(lines) < _GRID_MIN_LINES:
        return None

    diffs = np.diff(lines)
    diffs = diffs[diffs > _GRID_MIN_GAP_PX]
    if diffs.size < 2 or (diffs.std() / diffs.mean()) >= _GRID_MAX_REGULARITY:
        return None

    x0 = lines[0] / scale
    x1 = (lines[0] + float(diffs.mean())) / scale
    y_mid = image.shape[0] / 2.0
    return Calibration(x1=x0, y1=y_mid, x2=x1, y2=y_mid, meters=_GRID_INTERVAL_METERS)


def _ring_coverage(mask: np.ndarray, x: float, y: float, r: float, samples: int = 36) -> float:
    """Fraction of *samples* angles, evenly spaced around a circle of radius *r* centred at (x, y),
    that hit *mask* somewhere within a tolerance band of *r* -- a lightweight stand-in for
    `vision/controls.py`'s own private `_ring_coverage` (not imported: this task does not touch that
    module, per its own scope). Checking a band rather than the single exact radius matters here:
    `cv2.HoughCircles`'s own radius estimate for a *ring* (not a filled disc) routinely lands a few
    px off the ink's true radius -- measured against this module's own synthetic test fixture, up to
    ~15% high -- so sampling only at the reported `r` undercounts a real, well-formed ring.
    """
    h, w = mask.shape
    band = max(2.0, 0.2 * r)
    radii = np.linspace(max(1.0, r - band), r + band, 5)
    hits = 0
    for angle in np.linspace(0.0, 2.0 * np.pi, samples, endpoint=False):
        xs = np.clip((x + radii * np.cos(angle)).astype(int), 0, w - 1)
        ys = np.clip((y + radii * np.sin(angle)).astype(int), 0, h - 1)
        if mask[ys, xs].any():
            hits += 1
    return hits / samples


def detect_circle_dpi(image: np.ndarray, config: AppConfig) -> float | None:
    """Tier 3's raw signal (ADR-016): the scan's dpi implied by a control circle's own observed
    pixel diameter against its fixed printed size (`config.detector.circle_diameter_mm`, ISOM 703).
    Purely geometric -- no scale ratio needed here at all; the caller (:func:`calibrate_map`)
    combines this dpi with an OCR'd scale ratio to reach a ground distance, and cross-validates the
    combination (`_accept` with `check_paper=True`) before trusting it. (This function used to do a
    weaker version of that check itself, against `_PLAUSIBLE_MPP` alone -- module docstring.)

    Deliberately not `vision/controls.py`'s `_detect_circles`/`detect_controls`: those need *dpi* as
    an input (to seed their search window) -- calibration cannot supply what it is trying to
    measure. This runs its own single, generously wide Hough pass over the same `purple_mask` ink
    classifier those functions already use (T020/ADR-011), then reads back each candidate's own
    radius (which `_detect_circles` computes internally but never returns -- not a public contract
    this task can lean on). Requires at least `_CIRCLE_MIN_CANDIDATES` consistent hits before
    trusting their median radius -- the same "one map, one hand-drawn circle scale throughout"
    assumption ADR-015 already documents for the primary control detector.

    Runs against a downscaled copy, like every other detector/OCR pass in this module -- the real
    corpus has scans up to ~90 megapixels (`load_raster`'s own 150-megapixel cap), and
    `cv2.HoughCircles` over a mask that size is not worth paying for on a fallback/cross-check-only
    tier. The measured radius is projected back to full-resolution pixels before it becomes a dpi.
    """
    small, scale = _downscale(image)
    mask = purple_mask(small, config)
    mask_u8 = mask.astype(np.uint8) * 255
    blurred = cv2.GaussianBlur(mask_u8, (0, 0), 1.0)
    h, w = mask.shape
    min_r = _CIRCLE_MIN_RADIUS_PX
    max_r = max(min_r + 1, int(min(h, w) * _CIRCLE_MAX_RADIUS_FRACTION))

    det = config.detector
    raw = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=det.hough_dp,
        # A wide-open, dpi-independent radius window (unlike `_detect_circles`'s own dpi-scaled
        # one) lets Hough fit the same real ring at several nearby radii -- measured on this
        # module's own synthetic fixture, up to 4-5 near-duplicate detections per true circle.
        # `minDist` scaled off `max_r` (not `min_r`, `_detect_circles`'s own choice) keeps at most
        # one accepted detection per real circle regardless of where in the window its true radius
        # actually falls.
        minDist=max_r * 1.5,
        param1=det.hough_param1,
        param2=det.hough_param2,
        minRadius=min_r,
        maxRadius=max_r,
    )
    if raw is None:
        return None

    radii = [
        float(r)
        for x, y, r in raw[0]
        if _ring_coverage(mask, float(x), float(y), float(r)) >= _CIRCLE_RING_COVERAGE_MIN
    ]
    if len(radii) < _CIRCLE_MIN_CANDIDATES:
        return None

    median_r = statistics.median(radii) / scale
    return 25.4 * 2.0 * median_r / det.circle_diameter_mm


def calibrate_map(
    image: np.ndarray, config: AppConfig | None = None
) -> tuple[CalibrationResult | None, float | None]:
    """Try scale bar -> grid -> circle, first hit wins (ADR-016, T078's DoD).

    `ocr_scale_denominator` now runs first, unconditionally -- every tier requires it (module
    docstring); tier 1 used to run before it and return on its own first candidate, which is
    exactly the gap an independent review of the real-corpus run found live (C1). Returns the
    result (`None` when nothing fires) plus whatever `ocr_scale_denominator` read on this map, even
    when it went unused by whichever tier fired first (e.g. tier 1 fired, tier 2's own denominator
    reading is moot) -- callers pool this second value across a whole corpus run to seed the
    assumed-default fallback (:func:`calibrate_corpus`), without paying for a second OCR pass.
    """
    cfg = config or default_config()

    scale_denominator = ocr_scale_denominator(image)
    if scale_denominator is None:
        return None, None

    width_px = float(image.shape[1])

    bar = detect_scale_bar(image, scale_denominator)
    if bar is not None:
        dpi = _implied_dpi(bar.meters_per_pixel, scale_denominator)
        if dpi is not None and _accept(width_px, bar.meters_per_pixel, dpi):
            result = CalibrationResult(
                source="scale_bar", scale_denominator=scale_denominator, dpi=dpi, calibration=bar
            )
            return result, scale_denominator

    grid = detect_grid_calibration(image)
    if grid is not None:
        dpi = _implied_dpi(grid.meters_per_pixel, scale_denominator)
        if dpi is not None and _accept(width_px, grid.meters_per_pixel, dpi):
            result = CalibrationResult(
                source="grid", scale_denominator=scale_denominator, dpi=dpi, calibration=grid
            )
            return result, scale_denominator

    dpi = detect_circle_dpi(image, cfg)
    if dpi is not None:
        mpp = mpp_from_dpi(dpi, scale_denominator)
        if _accept(width_px, mpp, dpi, check_paper=True):
            result = CalibrationResult(
                source="circle", scale_denominator=scale_denominator, dpi=dpi
            )
            return result, scale_denominator

    return None, scale_denominator


def _fmt(value: float) -> str:
    """A clean TOML-safe number literal: rounded to a sane precision, without a pointless trailing
    ``.0``.
    """
    rounded = round(value, 3)
    return str(int(rounded)) if rounded == int(rounded) else str(rounded)


def _write_meta_toml(
    map_dir: Path,
    *,
    calibration_source: Literal["measured", "assumed_default"],
    tier: str | None = None,
    calibration: Calibration | None = None,
    dpi: float | None = None,
    scale_denominator: float | None = None,
) -> None:
    """Write `meta.toml` for one map directory (T078's DoD; `data/README.md`'s on-disk contract).
    Exactly one of *calibration* or (*dpi*, *scale_denominator*) must be given -- the same either/or
    `io/corpus.py::CorpusEntry.meters_per_pixel` already reads. *tier* (H2: a real, parseable key
    now, `calibration_tier` -- a TOML comment alone, this module's first version, is invisible to
    `tomllib` and everything downstream) is written only alongside `calibration_source="measured"`.
    """
    lines: list[str] = [f'calibration_source = "{calibration_source}"']
    if tier is not None:
        lines.append(f'calibration_tier = "{tier}"')

    if calibration is not None:
        lines += [
            "",
            "[calibration]",
            f"x1 = {_fmt(calibration.x1)}",
            f"y1 = {_fmt(calibration.y1)}",
            f"x2 = {_fmt(calibration.x2)}",
            f"y2 = {_fmt(calibration.y2)}",
            f"meters = {_fmt(calibration.meters)}",
        ]
    elif dpi is not None and scale_denominator is not None:
        lines.append(f"dpi = {_fmt(dpi)}")
        lines.append(f"scale_denominator = {_fmt(scale_denominator)}")
    else:
        raise ValueError("need either `calibration` or both `dpi` and `scale_denominator`")

    (map_dir / META_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")


def calibrate_corpus(
    root: Path,
    config: AppConfig | None = None,
    *,
    name_prefix: str = DEFAULT_NAME_PREFIX,
    refresh: bool = False,
) -> CorpusCalibrationReport:
    """Write `meta.toml` for every in-scope map under *root* that does not already have one (T078's
    DoD).

    **Scope** (M5): only directories whose name starts with *name_prefix* are ever touched or even
    counted toward `measured`/`assumed_default`/`skipped_existing` -- everything else (the owner's
    own T017 validation scans, which share this same root) is counted in `out_of_scope` and left
    completely untouched, never written to, regardless of whether it already has a `meta.toml`.

    **Refresh** (C1's compounding finding): a directory with an existing `meta.toml` is normally
    left alone and counted in `skipped_existing` -- owner-authored or not. Pass `refresh=True` to
    instead overwrite exactly the in-scope directories whose existing `meta.toml` carries this
    module's own `calibration_source` key (i.e. this module's own past output, safe to redo); a
    directory whose `meta.toml` has no such key is never overwritten by `refresh`, on the same
    "never touch an owner-authored file" rule as always.

    Two passes: detection first, across the whole in-scope corpus, then writing -- the
    assumed-default fallback's own numbers (ADR-016: "the median of this run's successful
    measurements") can only be known once the run is complete, so no map's `meta.toml` is written
    until every map has been tried once.

    A single bad file (corrupt raster, an unsupported format like the corpus's one `.ocd`-only
    directory, or a systemic OCR failure) degrades that one map to "no signal" rather than aborting
    the run (ADR-009) -- and is counted in `errors` (H4), so a systemic failure (e.g. Tesseract
    missing) is visible in the report rather than reading as an unusually hard corpus.
    """
    cfg = config or default_config()
    all_entries = list_corpus(root)
    entries = [e for e in all_entries if e.map_id.startswith(name_prefix)]
    out_of_scope = len(all_entries) - len(entries)

    pending: list[tuple[Path, CalibrationResult | None]] = []
    scale_pool: list[float] = []
    skipped = 0
    errors = 0

    for entry in entries:
        meta_path = entry.path / META_NAME
        if meta_path.is_file() and not (refresh and entry.calibration_source is not None):
            skipped += 1
            continue

        result: CalibrationResult | None = None
        scale_denominator: float | None = None
        if entry.raster is not None:
            try:
                image = load_raster(entry.raster)
                result, scale_denominator = calibrate_map(image, cfg)
            except Exception:  # RasterLoadError, a corrupt/unsupported file, a systemic OCR
                errors += 1  # failure, an unexpected cv2 failure -- one bad map must not abort a
                # 200+ map run (ADR-009), but is now counted rather than silently swallowed (H4)

        if scale_denominator is not None:
            scale_pool.append(scale_denominator)
        pending.append((entry.path, result))

    measured_dpis = [r.dpi for _, r in pending if r is not None]  # all 3 tiers now (H3)
    fallback_dpi = statistics.median(measured_dpis) if measured_dpis else cfg.map.default_dpi
    fallback_scale = statistics.median(scale_pool) if scale_pool else _FALLBACK_SCALE_DENOMINATOR

    measured = 0
    assumed = 0
    for map_dir, result in pending:
        try:
            if result is not None:
                _write_meta_toml(
                    map_dir,
                    calibration_source="measured",
                    tier=result.source,
                    calibration=result.calibration,
                    dpi=result.dpi,
                    scale_denominator=result.scale_denominator,
                )
                measured += 1
            else:
                _write_meta_toml(
                    map_dir,
                    calibration_source="assumed_default",
                    dpi=fallback_dpi,
                    scale_denominator=fallback_scale,
                )
                assumed += 1
        except OSError:  # one unwritable directory must not abort/half-write the corpus (M6)
            errors += 1

    return CorpusCalibrationReport(
        measured=measured,
        assumed_default=assumed,
        skipped_existing=skipped,
        out_of_scope=out_of_scope,
        errors=errors,
        total=len(all_entries),
    )
