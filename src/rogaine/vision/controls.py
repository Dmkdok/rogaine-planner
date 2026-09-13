"""Control circle and start/finish triangle detection (T020, SPEC F7).

Two ISOM symbols carry the purple ink this module looks for, and they are not the same shape, so
this is two detectors sharing one mask, not one detector doing both:

- **703, the control circle** -- a purple ring of a fixed printed diameter
  (`config.detector.circle_diameter_mm`). `cv2.HoughCircles` finds circles; it will not reliably
  find a triangle, so it is the right tool for this half and only this half.
- **701, the start triangle** -- a purple triangle outline at the hub. This project's one-hub
  convention (start = finish, `docs/BRIEF.md`/`docs/SPEC.md`) means there is exactly one of these
  per map, never a second "finish" symbol to recognise (`tests/fixtures/synth_map.py`'s
  `_place_controls` draws only this one marker at the hub). Found instead via connected-component
  contours and `cv2.approxPolyDP`, the same way T014's `vision/linear.py` tells a real corridor from
  noise ink by shape rather than by colour alone.

*dpi* is taken explicitly everywhere a printed size needs converting to pixels, the same
convention `vision/linear.py` (T014), `vision/contours.py` (T015) and
`config.DetectorSettings.circle_radius_px` itself already establish: printed sizes are fixed in
millimetres, never a hardcoded pixel count. The map's scale (`meters_per_pixel`) never enters into
this module at all -- ISOM symbol sizes are fixed on paper, not on the ground
(`circle_radius_px`'s own docstring).

**A real finding from tuning against the fixture (T020).** The config's Hough parameters as
shipped (`hough_dp=1.2`, `hough_param1=100`, `hough_param2=30`) find every real control circle on
the fixture (recall 1.0) but also fit spurious circles inside the purple out-of-bounds hatching --
diagonal hatch lines happen to cross in locally circular patterns at a radius inside the configured
tolerance band. Measured on the standard (degraded) fixture: 14 raw Hough detections for 12 true
controls, 2 of them sitting 100+ px from any real control or the hub, dragging precision to 0.857
against the 0.90 floor. Retuning `hough_param1`/`hough_param2` blindly was not the fix (SPEC
review: don't silently repick Hough numbers without saying so) -- the actual defect is that
`cv2.HoughCircles` alone cannot tell a genuine drawn ring from a coincidental circular alignment of
unrelated ink. `_ring_coverage` below adds that missing check: a real ISOM ring has purple ink all
the way around its fitted circumference; a spurious fit through hatch-line crossings only touches
purple ink at a handful of sampled points.
Filtering on it (threshold 0.75, tuned against the measured true/false separation: true detections
scored 0.822-1.000, false ones 0.500-0.682) brings precision to 1.0 on both the degraded and clean
fixture without touching a single config value. It doubles as this module's per-circle `confidence`
-- literally "how well this component matches the expected circle shape", the same grounding this
task's own instructions ask for rather than a uniform placeholder.
"""

from __future__ import annotations

import cv2
import numpy as np

from rogaine.config import AppConfig, default_config
from rogaine.models import Control

# ISOM 701's real printed size is not yet in `config/default.toml` (only the 703 circle's is) --
# T017's corpus validation is where that gap gets closed, same as the circle diameter's own config
# comment already flags for T020. Until then this project's own fixture is the only grounded source:
# `tests/fixtures/synth_map.py`'s `_place_controls` draws the triangle at `side = radius * 2.2`
# around the hub, so anchoring the expected size to `circle_radius_px(dpi)` through that ratio is a
# real, cited constant, not one pulled from nowhere.
_TRIANGLE_SIDE_TO_RADIUS = 2.2

# A genuine ISOM 701 triangle is close to equilateral. Originally 0.5 (T020's fixture-only floor);
# T081 tightened it to 0.85 once the epsilon sweep below could widen far enough to make an
# unrelated blob's `approxPolyDP` fit collapse to 3 vertices too. Measured real ISOM 701 triangles
# (the equilateral spec shape, printed not hand-drawn) hold side ratio >=0.97 even through a
# scan/JPEG pass: 0.980 (`data/maps/grid-lines-red-controls`, already-passing case, untouched by
# this change since its fit is found at the original eps=0.02), 0.970 (`ozero-shchuche`), 0.977
# (`kkm-toksovo`). The false-positive this guards against, measured on the same scan: a course
# logo's overlapping running-figure glyphs on `data/maps/ozero-shchuche/map.jpg` also eventually
# collapses to 3 vertices under the widened sweep, but only at ratio 0.604-0.634 -- 0.85 sits with
# wide margin on both sides of that gap.
_TRIANGLE_MIN_SIDE_RATIO = 0.85

# T081: ISOM's combined start/finish overlaps the 701 triangle with the 706 finish double-circle,
# and that circle ink bulges one edge of the triangle's contour outward, adding an extra vertex --
# a single fixed `approxPolyDP` epsilon (this project shipped 0.02 before T081) reduces the fused
# shape to 4+ vertices, never exactly 3, so the hub was silently dropped. Measured on real scans:
# `data/maps/ozero-shchuche/map.jpg`'s hub (single ring overlap) first collapses to exactly 3
# vertices at eps=0.03; `data/maps/kkm-toksovo/map.jpg`'s (a full double-ring overlap, bulging more)
# needs eps=0.08. Trying eps=0.02 first keeps the already-passing `grid-lines-red-controls` and
# synthetic-fixture triangles (both fit at eps=0.02, an isolated triangle with no circle to fuse
# with) matching at the exact same epsilon as before -- this list is a strict superset of the old
# single-value behaviour, not a replacement of it. A plain, isolated control ring never reaches
# exactly 3 vertices anywhere in this range on any real scan measured (it plateaus at 4 by
# eps=0.05-0.06 and stays there through eps=0.10), so widening the search this far does not risk
# mistaking a circle for a triangle -- `_TRIANGLE_MIN_SIDE_RATIO` above guards the remaining risk
# (an unrelated blob that does eventually reach 3 vertices, but lopsided).
_TRIANGLE_APPROX_EPS_FRACTIONS = (0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10)

# Radial tolerance band (as a fraction of the mid circle radius) `_ring_coverage` searches around a
# Hough-fitted radius -- absorbs Hough's own radius-estimation slop without weakening the shape
# check itself. See the module docstring's finding for how this was measured, not guessed.
_RING_COVERAGE_BAND_FRACTION = 1.0 / 8.0
_RING_COVERAGE_MIN = 0.75

# `_select_best_scale`'s (T076, ADR-015) mean-coverage bucket width. Coarse enough that the real
# scan's two false-prone scales (mean 0.8806, 0.9394) fall in different buckets from the true
# scale (0.9943) and so still lose outright on coverage alone, but coarse enough that scales whose
# means are close by CV noise (the real scan's true scale itself splits 0.9943/0.9907/0.9307 across
# three multipliers) don't spuriously out-rank each other on the mean term before the candidate-
# count tie-break gets a say.
_SCALE_TIE_EPS = 0.02

# `_ocr_gate_sub_base_scale`'s (T099, amended per the owner's T100 sign-off, ADR-032) junk-fraction
# line: a sub-1.0 candidate set with more than this fraction reading no plausible number is assumed
# junk-dominated and filtered down to only the candidates that do read; below it, the whole set is
# kept (flagged unread, as any production-scale detection already would be). Provisional, measured
# against only 2 real points -- `kkm-toksovo` (0.68, real controls Tesseract couldn't read, must NOT
# filter) and `ogps-3771_0da0ae4ad426ed5d03089615dbe38a1f` (0.93, a pink-hatched "no-crossing zone"
# ink texture, must filter) -- comfortably between the two but not corpus-validated; a wider sweep
# is flagged as follow-up, not silently assumed solid (ADR-032's amendment says so explicitly).
_SUB_BASE_JUNK_UNREAD_FRACTION = 0.85


def purple_mask(image: np.ndarray, config: AppConfig | None = None) -> np.ndarray:
    """Boolean `(H, W)` mask of pixels inside any of `config.detector`'s configured ink bands, the
    ink both the control circle (703) and the start triangle (701) are printed in.

    The name predates ADR-011 (I1): the shipped default still leads with ISOM purple 35/85/0/0, but
    the config now carries a *list* of hue bands (`ink_hue_ranges`) so a real scan whose controls
    are hand-marked in a different ink family -- e.g. red -- is not silently undetected. Red is
    handled by a second, separate band list, `red_hue_ranges` (ADR-018): a real scan
    (`data/maps/ozero-shchuche`) showed brown contour ink passing the shared purple/value floor
    that `ink_hue_ranges` bands use, because brown is saturated but dimmer than real red control
    ink (mean RGB (161, 106, 90) vs (234, 66, 221) for that file's true purple ink) -- so red gets
    its own, measured-tighter saturation/value floor plus a red-vs-brown minimum channel-gap check
    (`min(R-G, R-B) >= red_min_channel_gap`), which the true red ink easily clears but brown does
    not. The returned mask is the union (OR) of every band's own `cv2.inRange` mask.

    *image* is RGB uint8, the convention `rogaine.models.MapContext` and every other vision
    module in this package use -- converted via `cv2.COLOR_RGB2HSV` below, not `BGR2HSV`. OpenCV's
    H channel is `[0, 179]` and wraps at that boundary; this project's configured purple band
    (`[140, 175]`, `config/default.toml`) sits entirely below the wrap, so no wrap-around handling
    is needed there -- verified against the fixture's own rendered purple, not assumed:
    `RENDER_SRGB["purple_100"]` (`tests/fixtures/synth_map.py`) is RGB `(170, 60, 150)`, which
    converts to HSV `(155, 165, 170)`, comfortably inside the configured hue/saturation/value
    floors. Red *does* wrap around the 0/179 boundary, so its band is configured as two entries
    straddling the wrap rather than one -- see the comments on `ink_hue_ranges`/`red_hue_ranges` in
    `config/default.toml`.
    """
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"expected an (H, W, 3) RGB image, got shape {image.shape}")
    if image.dtype != np.uint8:
        raise ValueError(f"expected uint8 pixels, got {image.dtype}")

    cfg = config or default_config()
    det = cfg.detector
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    mask = np.zeros(image.shape[:2], dtype=bool)
    for hue_lo, hue_hi in det.ink_hue_ranges:
        lower = np.array([hue_lo, det.purple_min_saturation, det.purple_min_value], dtype=np.uint8)
        upper = np.array([hue_hi, 255, 255], dtype=np.uint8)
        mask |= cv2.inRange(hsv, lower, upper) > 0

    red = np.zeros(image.shape[:2], dtype=bool)
    for hue_lo, hue_hi in det.red_hue_ranges:
        lower = np.array([hue_lo, det.red_min_saturation, det.red_min_value], dtype=np.uint8)
        upper = np.array([hue_hi, 255, 255], dtype=np.uint8)
        red |= cv2.inRange(hsv, lower, upper) > 0
    if det.red_min_channel_gap > 0:
        r = image[..., 0].astype(np.int16)
        g = image[..., 1].astype(np.int16)
        b = image[..., 2].astype(np.int16)
        red &= np.minimum(r - g, r - b) >= det.red_min_channel_gap
    mask |= red

    return mask


def _ring_coverage(mask: np.ndarray, cx: float, cy: float, r: float, band: float) -> float:
    """Fraction of a sampled circle's circumference that actually sits on purple ink.

    Samples points evenly around the circle at radius *r*, and at four more radii spread across
    `[r - band, r + band]`, so a Hough radius that is a few pixels off a real ring's true radius is
    not penalised for imprecision that has nothing to do with whether the ring is really there. See
    the module docstring for why this check exists and how its threshold was measured.
    """
    n = max(16, round(2 * np.pi * r / 3))
    theta = np.linspace(0, 2 * np.pi, n, endpoint=False)
    h, w = mask.shape
    hit = np.zeros(n, dtype=bool)
    for offset in np.linspace(-band, band, 5):
        rr = r + offset
        xs = np.round(cx + rr * np.cos(theta)).astype(int)
        ys = np.round(cy + rr * np.sin(theta)).astype(int)
        valid = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
        hit[valid] |= mask[ys[valid], xs[valid]]
    return float(hit.sum()) / n


def _select_best_scale(
    per_multiplier: list[tuple[float, list[tuple[float, float, float, float]]]],
) -> list[tuple[float, float, float, float]]:
    """Pick the single scale (multiplier) whose ring-coverage-passing candidates fit most
    convincingly, and return only that scale's candidates (T076, ADR-015).

    *per_multiplier* is `(multiplier, candidates)` for every configured multiplier, in sweep
    order; *candidates* are `(x, y, r, coverage)` tuples that already cleared `_ring_coverage`'s
    unmodified threshold at that multiplier's own scaled window (`r` is that multiplier's nominal
    mid radius, not Hough's own per-candidate fit -- see `_detect_circles`'s inline comment for why
    -- threaded through since T077/ADR-020 purely for `Control.radius_px`; the scoring below never
    reads it).

    A real map draws every control circle at one consistent hand size, so the *correct* scale is
    the one whose fits clear the (unmodified) ring-coverage bar most convincingly on average --
    measured directly against the real scan (`data/maps/grid-lines-red-controls/map.jpeg`): the
    true scale's 13 candidates average >=0.99 ring coverage, while the too-small base scale's 16
    false fits on hand-written control-number digits average only ~0.88, even though every one of
    them still individually clears the same 0.75 floor a true fit does. This is why pooling every
    scale's passing candidates (this task's first design, replaced after that measurement) cannot
    be fixed by retuning any per-candidate threshold: a false fit clearing the identical bar a true
    fit clears is not separable candidate-by-candidate, only scale-by-scale.

    Scoring by raw mean coverage alone is not enough, though (found by independent review, before
    this shipped): `_ring_coverage` saturates at exactly `1.0` for *any* candidate sitting inside a
    solid ink blob, not only a true ring, so two scales tying at a perfect mean is the normal case,
    not a rare edge case -- and a bare `mean_a > mean_b` comparison hands every such tie to
    whichever multiplier is checked first (the smallest, by sweep order), which can be the wrong
    one: a single lucky solid-blob false positive at the base scale scores an unbeatable `1.0`
    mean just as easily as many genuine, slightly-noisier true rings at the correct scale.  The
    score is therefore `(coverage bucketed to _SCALE_TIE_EPS, candidate count)`: only scales whose
    mean coverage is *meaningfully* higher win outright; among scales close enough to call a tie,
    the one with more corroborating candidates wins, since a real map's true scale finds many
    consistent circles, a lucky false positive finds one. `TestOversizedRingsBeatABaseScaleDecoy`
    is the regression test for exactly this failure mode.

    Known limitation, not fixed here: this still assumes one map uses one hand-drawn scale
    throughout, and the count-based tie-break only protects against a tie against *few* false
    candidates -- a wrong scale producing *many* same-bucket false fits (more than the true scale's
    real candidate count) would still win. No evidence of either case exists in this project's
    corpus to design or test against further (same "measured, not guessed" bound ADR-011/ADR-014
    already apply elsewhere). `_detect_hub_triangle` picks its single best match across scales by
    per-candidate normalised error rather than this set-level rule -- consistent so far (no
    real-scan or adversarial-test failure found), but a genuine design asymmetry worth noting: a
    hub is a single expected symbol, so there is no "many corroborating candidates" signal to
    weigh in the first place, which is why the two functions do not share one selection rule.

    T090/ADR-031 addendum (independent review finding, tried and reverted): a third tie-break tier
    biasing exact (bucketed coverage, count) ties toward the multiplier nearest `1.0` was proposed
    to avoid `_ocr_gate_sub_base_scale` firing "needlessly" on a tie -- reverted after measurement
    disproved its premise. `kkm-toksovo` ties in exactly this way (mult `0.85` and `1.0` both score
    `n=25` at the same bucketed coverage) yet the two scales' OCR outcomes are *not* equivalent:
    `1.0` reads 1/25, `0.85` reads 8/25 (the ADR-030/ADR-031 "same ring, differently-sized crop"
    mechanism -- same physical rings, but `_ocr_crop` sizes its crop from the *matched* radius, and
    `0.85`'s smaller crop happens to frame the digits better on this map). A tie-break that resolves
    this tie toward `1.0` skips the gate entirely (since `_detect_circles` only invokes it when the
    winner is itself sub-1.0) and silently reverts a real, measured win back to a 4% read rate.
    Ring-coverage ties are therefore not proof of OCR-outcome ties, and this rule is unsafe to
    apply -- left as the original two-tier score below; the "extra OCR pass on a genuine tie" cost
    this addendum tried to avoid is the gate's own intended price for catching cases like this one.
    """
    best: list[tuple[float, float, float, float]] = []
    best_score: tuple[int, int] = (-1, -1)
    for _mult, candidates in per_multiplier:
        if not candidates:
            continue
        mean_coverage = sum(c for _, _, _, c in candidates) / len(candidates)
        score = (round(mean_coverage / _SCALE_TIE_EPS), len(candidates))
        if score > best_score:
            best_score = score
            best = candidates
    return best


def _detect_circles(
    image: np.ndarray, mask: np.ndarray, dpi: float, config: AppConfig
) -> list[tuple[float, float, float, float]]:
    """Hough-circle candidates on the purple mask, filtered to those actually ringed in purple.

    Runs once per `config.detector.circle_scale_multipliers` entry, each pass against that
    multiplier's own scaled `(r_min, r_max)` window, gated through the same unmodified
    `_ring_coverage` check every pass uses (T076, ADR-015) -- a real ring drawn larger than the
    ISOM print size is found by a larger-multiplier pass without loosening the check that rejects
    spurious fits at the base scale. `_select_best_scale` then picks the single multiplier whose
    passing candidates fit most convincingly *on average* and returns only that scale's
    candidates -- see its own docstring for why comparing scales as sets, not pooling every
    scale's individually-passing candidates, is what actually separates a real ring from a
    same-threshold-clearing false fit at the wrong scale.

    T090/ADR-031: when the winner sits below multiplier `1.0` (a real, measured gap for some
    hand-drawn scans, T089's H2 finding -- see `config/default.toml`'s own comment on
    `circle_scale_multipliers`), it is not trusted on ring-coverage alone -- `_ring_coverage`
    cannot tell a genuinely undersized ring from the *same* correctly-matched >=1.0 ring winning a
    sweep-order tie against its own sub-1.0 window, or from a small false-positive ink cluster
    (ADR-030 measured both failure modes on real scans: naive widening was a net -24 reads across
    7 owner maps). `_ocr_gate_sub_base_scale` below probes the real OCR outcome of each sub-1.0
    candidate individually and compares the surviving count against the >=1.0 (production) side's
    own aggregate read count, defaulting to production otherwise -- see its own docstring for why
    the set is only *filtered* down to the reading candidates when it looks junk-dominated (T099,
    then amended per the owner's own T100 sign-off, ADR-032), and kept whole (flagged unread) when
    it doesn't. Bounded to at most two `read_control_numbers` passes (one per candidate set), only
    paid when a sub-1.0 candidate would otherwise be chosen blind, on top of the pipeline's own
    later OCR pass over whichever set is finally returned.
    """
    det = config.detector
    base_r_min, base_r_max = det.circle_radius_px(dpi)

    mask_u8 = mask.astype(np.uint8) * 255
    # A small blur softens the mask's hard-binary edges before Hough's internal Canny/Sobel step --
    # a jagged, pixel-quantised ring boundary otherwise produces noisier gradient directions than a
    # smoothly antialiased one would.
    blurred = cv2.GaussianBlur(mask_u8, (0, 0), 1.0)

    per_multiplier: list[tuple[float, list[tuple[float, float, float, float]]]] = []
    for mult in det.circle_scale_multipliers:
        r_min = base_r_min * mult
        r_max = base_r_max * mult
        r_mid = (r_min + r_max) / 2.0
        raw = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=det.hough_dp,
            minDist=r_min * 1.5,
            param1=det.hough_param1,
            param2=det.hough_param2,
            minRadius=round(r_min),
            maxRadius=round(r_max),
        )
        candidates: list[tuple[float, float, float, float]] = []
        if raw is not None:
            band = r_mid * _RING_COVERAGE_BAND_FRACTION
            for x, y, r in raw[0]:
                coverage = _ring_coverage(mask, float(x), float(y), float(r), band)
                if coverage >= _RING_COVERAGE_MIN:
                    # r_mid (this multiplier's nominal radius), not Hough's own per-candidate `r`:
                    # measured against the clean fixture (T077/ADR-020), Hough's raw fit jitters
                    # +-10% around r_mid even at the base scale, and `_ocr_crop`'s crop-margin
                    # constants (`_CROP_MARGIN_FACTOR`/`_CIRCLE_MASK_RADIUS_FACTOR`) were tuned
                    # against the noiseless r_mid, not that jitter -- feeding the raw fit through
                    # regressed 2 of 12 already-passing fixture reads (11/12 -> 9/12) for zero
                    # benefit, since every candidate at one scale shares the same nominal radius
                    # anyway. Using r_mid keeps a base-scale (multiplier 1.0) `Control.radius_px`
                    # bit-identical to `_ocr_crop`'s own pre-T077 fallback value, so base-scale
                    # controls see no behaviour change at all -- only a control actually matched at
                    # a non-base multiplier gets a different (correctly larger) crop.
                    candidates.append((float(x), float(y), r_mid, coverage))
        per_multiplier.append((mult, candidates))

    selected = _select_best_scale(per_multiplier)
    base_r_mid = (base_r_min + base_r_max) / 2.0
    selected_mult = selected[0][2] / base_r_mid if selected and base_r_mid > 0 else None
    if selected_mult is not None and selected_mult < 1.0:
        selected = _ocr_gate_sub_base_scale(image, dpi, config, per_multiplier, selected)

    return selected


def _ocr_gate_sub_base_scale(
    image: np.ndarray,
    dpi: float,
    config: AppConfig,
    per_multiplier: list[tuple[float, list[tuple[float, float, float, float]]]],
    sub_base_candidates: list[tuple[float, float, float, float]],
) -> list[tuple[float, float, float, float]]:
    """T090/ADR-031 H2 gate; per-candidate probing added by T099, then narrowed to a junk-fraction
    condition by this same amendment after the owner's own T100 sign-off found T099's first version
    too aggressive (ADR-032's amendment). `_select_best_scale`'s ring-coverage-only score is not
    enough to trust a sub-1.0 winner: `_ring_coverage` saturates at 1.0 for any solid ink blob, not
    only a genuine ring, and a smaller sub-1.0 search window is exactly the size a round loop inside
    a coincidental ink texture (a bold glyph, a hatching crossing) can also fill.

    T090's original version compared two whole candidate *sets* by aggregate valid-read count and
    kept one entirely. T099 (first version) instead probed each sub-1.0 candidate's own crop and
    kept only the ones that read a plausible number -- but a candidate that is a genuine control
    whose specific number is illegible reads exactly the same `None` a coincidental ink blob does,
    so that filter cannot tell them apart. Measured on real scans (T100): on
    `ogps-3771_0da0ae4ad426ed5d03089615dbe38a1f` this was a clean win (a pink-hatched "no-crossing
    zone" ink texture generates hundreds of false positives, 213/230 unread, filtering them out
    cost nothing real). On the owner's own `kkm-toksovo` it was not: 17/25 unread, but several of
    those 17 are confirmed-by-eye real, legible, correctly-positioned controls (91, 92, 72, 52) that
    Tesseract simply never read at this map's print style -- filtering silently dropped them from
    the output entirely, instead of surfacing them flagged-unread the way every production-scale
    (`>=1.0`) detection already does.

    Resolution, the owner's own choice: gate the *filtering itself* on how unread-dominated the
    sub-1.0 set looks, rather than always filtering or never filtering. Below
    `_SUB_BASE_JUNK_UNREAD_FRACTION` unread, the set is assumed mostly real and returned whole
    (T090's original behaviour: real controls stay visible even when illegible, flagged downstream
    like any other unread control) if it beats production's own read count. Strictly more than that
    fraction unread, the set is assumed junk-dominated and only the candidates that actually read
    survive (T099's original behaviour) -- `ogps-3771` (93% unread) crosses this line, `kkm-toksovo`
    (68% unread) does not; a set landing exactly on the line is treated as not-yet-junk (kept
    whole), matching `_SUB_BASE_JUNK_UNREAD_FRACTION`'s own "more than" wording. The threshold is
    provisional, calibrated against only these 2 measured points (ADR-032's amendment says so
    explicitly) -- a corpus-wide validation is flagged as follow-up, not silently assumed solid.

    Comparison against production is otherwise unchanged in shape from T090: same tie-break (ties,
    including both sides at zero, fall back to production, never to a sub-1.0 result that reads no
    better), same "no `>=1.0` candidate at all -> nothing to compare against" fallback (still probed
    per-candidate first, since the junk-fraction check needs the per-candidate outcome regardless of
    whether a comparison side exists -- a map whose only Hough hits are sub-1.0 junk is exactly the
    case this must not leave unguarded even with no production alternative; if every candidate is
    unread and the fraction crosses the junk line, this returns an empty list rather than a whole
    set of unread candidates -- deliberate, see `TestOcrGateSubBaseScale`'s own coverage of this
    exact case).
    """
    # Deferred import: `vision.ocr` imports `purple_mask` from this module at load time, so a
    # module-level import here would be circular.
    from rogaine.vision.ocr import read_control_numbers

    def _controls_for(
        candidates: list[tuple[float, float, float, float]],
    ) -> list[Control]:
        return [
            Control(
                id=i, x=x, y=y, confidence=coverage, radius_px=r, source="detected", is_hub=False
            )
            for i, (x, y, r, coverage) in enumerate(candidates, start=1)
        ]

    sub_updated, _flags = read_control_numbers(
        image, _controls_for(sub_base_candidates), dpi, config
    )
    filtered_sub = [
        cand
        for cand, updated_control in zip(sub_base_candidates, sub_updated, strict=True)
        if updated_control.number is not None
    ]
    sub_read_count = len(filtered_sub)
    n_sub = len(sub_base_candidates)
    unread_fraction = (n_sub - sub_read_count) / n_sub if n_sub else 0.0
    junk_dominated = unread_fraction > _SUB_BASE_JUNK_UNREAD_FRACTION

    production_candidates = _select_best_scale(
        [(mult, candidates) for mult, candidates in per_multiplier if mult >= 1.0]
    )
    if not production_candidates:
        return filtered_sub if junk_dominated else sub_base_candidates

    prod_updated, _flags = read_control_numbers(
        image, _controls_for(production_candidates), dpi, config
    )
    prod_ok = sum(1 for c in prod_updated if c.number is not None)

    if sub_read_count <= prod_ok:
        return production_candidates
    return filtered_sub if junk_dominated else sub_base_candidates


def _detect_hub_triangle(mask: np.ndarray, dpi: float, config: AppConfig) -> Control | None:
    """The ISOM 701 start/finish triangle -- the hub, and the only non-circle symbol this project's
    one-hub convention needs recognised.

    `cv2.HoughCircles` cannot find a triangle; this instead looks at the purple mask's contour
    outlines directly and keeps the ones `cv2.approxPolyDP` reduces to three vertices at roughly
    the expected size (see `_TRIANGLE_SIDE_TO_RADIUS`). The fixture's triangle places its three
    vertices symmetrically around the hub, so their centroid *is* the hub position exactly, by
    construction -- using the mean of the three `approxPolyDP` vertices as the returned centre is
    therefore not an approximation of convenience, it is the same point the fixture itself used to
    place the triangle.

    Two contour-extraction choices were tightened by T081, both measured against real scans that
    the original (fixture-only-tuned) version silently returned no hub for:

    - `cv2.RETR_LIST`, not `cv2.RETR_EXTERNAL`: on a real scan whose terrain-contour ink forms a
      dense mesh of closed loops across most of the page, the hub commonly ends up geometrically
      *inside* one of those loops without ever touching it. `RETR_EXTERNAL` only returns the
      outermost contour of each nesting chain, so the enclosing loop wins and the triangle nested
      inside it is silently discarded. Measured on `data/maps/kkm-toksovo/map.jpg`:
      `RETR_EXTERNAL` finds exactly one contour system-wide (the terrain mesh swallows everything
      else); `RETR_LIST` recovers 64,366, among which the real hub is the sole match once the
      approximation and side-ratio checks below are applied.
    - A widened, ordered `approxPolyDP` epsilon sweep (`_TRIANGLE_APPROX_EPS_FRACTIONS`): ISOM's
      combined start/finish overlaps the 701 triangle with the 706 finish double-circle, whose ink
      bulges one edge of the triangle's contour outward, adding an extra vertex that a single fixed
      epsilon (this project's original 0.02) cannot always absorb. See that constant's own comment
      for the measurements.

    Sweeps `config.detector.circle_scale_multipliers` the same way `_detect_circles` scales its
    radius window (T076, ADR-015), since a hand-drawn triangle at a hub scales with whatever size
    its ring counterparts were drawn at. Contour extraction and the polygon fit don't depend on
    scale, so those run once; only `expected_side` (and thus `max_diff`) is recomputed per
    multiplier. The best match across scales is chosen by *normalised* relative error
    (`diff / max_diff`), not raw pixel `diff` -- `max_diff` itself grows with the multiplier, so
    comparing raw `diff` across scales would bias the choice toward larger scales merely because
    their tolerance band is wider in absolute pixels.

    T090/ADR-031 addendum (independent review finding): only the `>=1.0` entries of
    `circle_scale_multipliers` are swept here, not the full list. T090 added measured sub-1.0 rungs
    (`0.5`/`0.85`) for *circles* (ADR-030's H2), gated behind an OCR-outcome check before a
    sub-base-scale circle candidate is ever trusted (`_ocr_gate_sub_base_scale`) -- but this
    function has no OCR signal to gate against (a hub carries no digits) and no measured evidence
    exists anywhere in this project's corpus of a hub triangle drawn smaller than ISOM spec.
    Sweeping the sub-1.0 rungs here anyway shrinks `max_diff`'s absolute tolerance band, which
    measurably turned a correct "no hub found" into a spurious low-confidence false match on a real
    scan (`history-race-primorsk`: no hub -> a hub at confidence 0.298, the lowest in the owner
    corpus) -- silently starting/finishing a route at an unverified point is worse than the existing
    "hub not found, add manually" fallback the viewer already handles. Filtering to `>=1.0` here is
    unconditional, not itself gated, since (unlike circles) there is no cheap post-hoc signal to
    gate a hub match against.
    """
    det = config.detector
    hub_multipliers = [m for m in det.circle_scale_multipliers if m >= 1.0]
    base_r_min, base_r_max = det.circle_radius_px(dpi)
    base_r_mid = (base_r_min + base_r_max) / 2.0
    tol = det.circle_diameter_tolerance

    mask_u8 = mask.astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask_u8, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    triangles: list[tuple[np.ndarray, float]] = []  # (centre, mean side length)
    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue
        approx = None
        for eps_frac in _TRIANGLE_APPROX_EPS_FRACTIONS:
            candidate = cv2.approxPolyDP(contour, eps_frac * perimeter, True)
            if len(candidate) == 3:
                approx = candidate
                break
        if approx is None:
            continue

        pts = approx.reshape(-1, 2).astype(np.float64)
        sides = [
            float(np.linalg.norm(pts[0] - pts[1])),
            float(np.linalg.norm(pts[1] - pts[2])),
            float(np.linalg.norm(pts[2] - pts[0])),
        ]
        if min(sides) < _TRIANGLE_MIN_SIDE_RATIO * max(sides):
            continue  # near-degenerate (near-collinear) fit, not a real triangle
        triangles.append((pts.mean(axis=0), sum(sides) / 3.0))

    best_rel_error: float | None = None
    best_center: np.ndarray | None = None
    for mult in hub_multipliers:
        expected_side = base_r_mid * mult * _TRIANGLE_SIDE_TO_RADIUS
        max_diff = expected_side * tol
        if max_diff <= 0:
            continue
        for center, mean_side in triangles:
            diff = abs(mean_side - expected_side)
            if diff > max_diff:
                continue
            rel_error = diff / max_diff
            if best_rel_error is None or rel_error < best_rel_error:
                best_rel_error = rel_error
                best_center = center

    if best_center is None or best_rel_error is None:
        return None

    confidence = max(0.0, min(1.0, 1.0 - best_rel_error))
    return Control(
        id=0,
        x=float(best_center[0]),
        y=float(best_center[1]),
        confidence=confidence,
        source="detected",
        is_hub=True,
    )


def detect_controls(
    image: np.ndarray, dpi: float, config: AppConfig | None = None
) -> list[Control]:
    """Detect the hub (start/finish triangle, ISOM 701) and every control circle (ISOM 703) on a
    map raster (T020, SPEC F7).

    *image* is RGB uint8 (`rogaine.models.MapContext`'s convention). *dpi* is the raster's scan
    resolution, the same value `config.detector.circle_radius_px` and every sibling `vision/` module
    take explicitly (see the module docstring). Numbers and points are left `None` here -- reading a
    control's number is T021's job, not this one's.

    Returns the hub first (`id=0`, `is_hub=True`) when the triangle is found, followed by every
    accepted circle (`is_hub=False`) with `id` assigned sequentially from 1, in `(y, x)` order.
    Detection order carries no meaning on its own; a deterministic order just keeps output
    reproducible run to run, matching this project's convention elsewhere (e.g.
    `vision/linear.py`'s connected-component processing order).
    """
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"expected an (H, W, 3) RGB image, got shape {image.shape}")
    if image.dtype != np.uint8:
        raise ValueError(f"expected uint8 pixels, got {image.dtype}")
    if not dpi > 0:
        raise ValueError(f"dpi must be positive, got {dpi}")

    cfg = config or default_config()
    mask = purple_mask(image, cfg)

    controls: list[Control] = []
    hub = _detect_hub_triangle(mask, dpi, cfg)
    if hub is not None:
        controls.append(hub)

    circles = _detect_circles(image, mask, dpi, cfg)
    circles.sort(key=lambda c: (c[1], c[0]))
    for i, (x, y, r, confidence) in enumerate(circles, start=1):
        controls.append(
            Control(
                id=i,
                x=x,
                y=y,
                confidence=confidence,
                radius_px=r,
                source="detected",
                is_hub=False,
            )
        )

    return controls
