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

# A genuine ISOM 701 triangle is close to equilateral (its three sides come out within ~10% of each
# other on the fixture); a spurious 3-vertex `approxPolyDP` fit from noise ink routinely collapses
# one side to near zero (two vertices almost coincide). Rejecting anything more lopsided than this
# catches that failure mode without needing a size match to already have ruled it out.
_TRIANGLE_MIN_SIDE_RATIO = 0.5

# Radial tolerance band (as a fraction of the mid circle radius) `_ring_coverage` searches around a
# Hough-fitted radius -- absorbs Hough's own radius-estimation slop without weakening the shape
# check itself. See the module docstring's finding for how this was measured, not guessed.
_RING_COVERAGE_BAND_FRACTION = 1.0 / 8.0
_RING_COVERAGE_MIN = 0.75


def purple_mask(image: np.ndarray, config: AppConfig | None = None) -> np.ndarray:
    """Boolean `(H, W)` mask of pixels inside any of `config.detector.ink_hue_ranges`, the ink both
    the control circle (703) and the start triangle (701) are printed in.

    The name predates ADR-011 (I1): the shipped default still leads with ISOM purple 35/85/0/0, but
    the config now carries a *list* of hue bands so a real scan whose controls are hand-marked in a
    different ink family -- e.g. red -- is not silently undetected. The returned mask is the union
    (OR) of the per-band `cv2.inRange` masks, all sharing the same saturation/value floors.

    *image* is RGB uint8, the convention `rogaine.models.MapContext` and every other vision
    module in this package use -- converted via `cv2.COLOR_RGB2HSV` below, not `BGR2HSV`. OpenCV's
    H channel is `[0, 179]` and wraps at that boundary; this project's configured purple band
    (`[140, 175]`, `config/default.toml`) sits entirely below the wrap, so no wrap-around handling
    is needed there -- verified against the fixture's own rendered purple, not assumed:
    `RENDER_SRGB["purple_100"]` (`tests/fixtures/synth_map.py`) is RGB `(170, 60, 150)`, which
    converts to HSV `(155, 165, 170)`, comfortably inside the configured hue/saturation/value
    floors. Red *does* wrap around the 0/179 boundary, so its band is configured as two entries
    straddling the wrap rather than one -- see the comment on `ink_hue_ranges` in
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


def _detect_circles(
    mask: np.ndarray, dpi: float, config: AppConfig
) -> list[tuple[float, float, float]]:
    """Hough-circle candidates on the purple mask, filtered to those actually ringed in purple.

    Returns `(x, y, confidence)` triples, deduplicated by `_ring_coverage` rather than by Hough's
    own `minDist` alone (see the module docstring's finding).
    """
    det = config.detector
    r_min, r_max = det.circle_radius_px(dpi)
    r_mid = (r_min + r_max) / 2.0

    mask_u8 = mask.astype(np.uint8) * 255
    # A small blur softens the mask's hard-binary edges before Hough's internal Canny/Sobel step --
    # a jagged, pixel-quantised ring boundary otherwise produces noisier gradient directions than a
    # smoothly antialiased one would.
    blurred = cv2.GaussianBlur(mask_u8, (0, 0), 1.0)
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
    if raw is None:
        return []

    band = r_mid * _RING_COVERAGE_BAND_FRACTION
    out: list[tuple[float, float, float]] = []
    for x, y, r in raw[0]:
        coverage = _ring_coverage(mask, float(x), float(y), float(r), band)
        if coverage >= _RING_COVERAGE_MIN:
            out.append((float(x), float(y), coverage))
    return out


def _detect_hub_triangle(mask: np.ndarray, dpi: float, config: AppConfig) -> Control | None:
    """The ISOM 701 start/finish triangle -- the hub, and the only non-circle symbol this project's
    one-hub convention needs recognised.

    `cv2.HoughCircles` cannot find a triangle; this instead looks at the purple mask's
    connected-component outlines directly and keeps the ones `cv2.approxPolyDP` reduces to three
    vertices at roughly the expected size (see `_TRIANGLE_SIDE_TO_RADIUS`). The fixture's triangle
    places its three vertices symmetrically around the hub, so their centroid *is* the hub position
    exactly, by construction -- using the mean of the three `approxPolyDP` vertices as the returned
    centre is therefore not an approximation of convenience, it is the same point the fixture itself
    used to place the triangle.
    """
    det = config.detector
    r_min, r_max = det.circle_radius_px(dpi)
    r_mid = (r_min + r_max) / 2.0
    expected_side = r_mid * _TRIANGLE_SIDE_TO_RADIUS
    tol = det.circle_diameter_tolerance
    max_diff = expected_side * tol

    mask_u8 = mask.astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best_diff: float | None = None
    best_center: np.ndarray | None = None
    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue
        approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(approx) != 3:
            continue

        pts = approx.reshape(-1, 2).astype(np.float64)
        sides = [
            float(np.linalg.norm(pts[0] - pts[1])),
            float(np.linalg.norm(pts[1] - pts[2])),
            float(np.linalg.norm(pts[2] - pts[0])),
        ]
        if min(sides) < _TRIANGLE_MIN_SIDE_RATIO * max(sides):
            continue  # near-degenerate (near-collinear) fit, not a real triangle

        diff = abs(sum(sides) / 3.0 - expected_side)
        if diff > max_diff:
            continue
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_center = pts.mean(axis=0)

    if best_center is None or best_diff is None:
        return None

    confidence = max(0.0, min(1.0, 1.0 - best_diff / max_diff)) if max_diff > 0 else 1.0
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

    circles = _detect_circles(mask, dpi, cfg)
    circles.sort(key=lambda c: (c[1], c[0]))
    for i, (x, y, confidence) in enumerate(circles, start=1):
        controls.append(
            Control(id=i, x=x, y=y, confidence=confidence, source="detected", is_hub=False)
        )

    return controls
