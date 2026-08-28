"""A synthetic ISOM map with exact ground truth (T004).

Why this exists: the owner's real maps carry no labels, so nothing measurable can be asserted
against them. This generator draws a map whose every pixel's true class is known by construction,
which is what lets SPEC F4-F7 be numbers rather than opinions. The real corpus validates; this
fixture tests (ADR-010).

Two design points worth knowing before changing anything here:

**The colours are deliberately not the classifier's colours.** :data:`RENDER_SRGB` holds values
typical of real rendered and scanned orienteering maps. The classifier derives its palette
independently, from the IOF CMYK definitions via :func:`rogaine.config.cmyk_to_srgb`. If this
fixture rendered with the classifier's own table, a passing IoU would prove only that a lookup
table equals itself.

**Overprint does not change the ground truth.** Contour lines, control circles and course symbols
are printed *over* terrain; the ground underneath is still forest or marsh or whatever it was. So
``labels`` records the terrain, and contours come back separately in ``contour_mask``. A pipeline
that reports "brown" where a contour crosses a marsh has misread the map, and this fixture says so.
The one exception is the out-of-bounds area: purple hatching means the whole enclosed region is
forbidden, so the enclosed region is labelled ``OUT_OF_BOUNDS`` and a correct pipeline has to fill
the hatch, not just trace it.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from rogaine.models import Control, TerrainClass, terrain_label

#: How a real render or scan of an ISOM map actually looks, per shade. Independent of the
#: classifier's own palette on purpose — see the module docstring.
RENDER_SRGB: dict[str, tuple[int, int, int]] = {
    "white": (255, 255, 255),
    "yellow_100": (253, 187, 63),
    "yellow_50": (254, 221, 160),
    "green_100": (75, 175, 40),
    "green_60": (150, 205, 128),
    "green_30": (194, 229, 208),
    "blue_100": (0, 158, 224),
    "blue_70": (77, 184, 233),
    "blue_50": (128, 207, 240),
    "brown_100": (190, 105, 40),
    "brown_50": (219, 170, 133),
    "black_100": (0, 0, 0),
    "black_30": (179, 179, 179),
    "purple_100": (170, 60, 150),
}

#: Which shade each terrain class is printed in. Mirrors ``config/default.toml`` — the mapping is
#: the map standard, not a tunable, so both files state it and a test asserts they agree.
SHADE_OF: dict[TerrainClass, str] = {
    TerrainClass.OPEN_LAND: "yellow_100",
    TerrainClass.ROUGH_OPEN: "yellow_50",
    TerrainClass.FOREST_RUNNABLE: "white",
    TerrainClass.VEG_SLOW_RUN: "green_30",
    TerrainClass.VEG_WALK: "green_60",
    TerrainClass.VEG_FIGHT: "green_100",
    TerrainClass.MARSH: "blue_50",
    TerrainClass.WATER_SHALLOW: "blue_70",
    TerrainClass.WATER_UNCROSSABLE: "blue_100",
    TerrainClass.BARE_ROCK: "black_30",
    TerrainClass.PAVED_AREA: "brown_50",
    TerrainClass.ROAD: "black_100",
    TerrainClass.VEHICLE_TRACK: "black_100",
    TerrainClass.FOOTPATH: "black_100",
    TerrainClass.OUT_OF_BOUNDS: "purple_100",
    TerrainClass.CONTOUR: "brown_100",
    TerrainClass.UNKNOWN: "white",
}

#: Printed widths in millimetres, from ISOM 2017-2. Converted to pixels through the DPI, so the
#: fixture's geometry is right at any resolution -- via `stroke_thickness_px`, not a bare
#: `round(mm * ppm)`, so the three classes stay distinguishable by actual rendered width (T014).
LINE_WIDTH_MM: dict[TerrainClass, float] = {
    TerrainClass.ROAD: 0.60,
    TerrainClass.VEHICLE_TRACK: 0.35,
    TerrainClass.FOOTPATH: 0.25,
}
#: The "full size" preset the performance budgets are stated against (SPEC non-functional
#: section): 4000x3000 at 1:30000 and 300 dpi is about 10 x 7.6 km of real ground.
FULL_SIZE: tuple[int, int] = (4000, 3000)

CONTOUR_WIDTH_MM = 0.14
CIRCLE_WIDTH_MM = 0.35
CIRCLE_DIAMETER_MM = 6.0
NUMBER_HEIGHT_MM = 4.0

#: Black map-text labels (T014, F5): overprint like the control numbers below, so `labels` is
#: untouched -- these exist to give T014's false-positive rejection something real to be measured
#: against (see its landing note in ``docs/TASKS.md`` for why the fixture drew none before).
MAP_TEXT_LABELS: tuple[str, ...] = ("SUMMIT RIDGE", "OLD QUARRY", "PINE HOLLOW")
TEXT_HEIGHT_MM = 3.0
#: Black ISOM point symbols (e.g. 201 boulder) -- small filled blobs, also overprint only.
POINT_SYMBOL_DIAMETER_MM = 1.2
N_POINT_SYMBOLS = 6


@dataclass(frozen=True)
class SyntheticMap:
    """A rendered map and the truth behind it."""

    image: np.ndarray  # (H, W, 3) uint8 RGB — what a segmenter is allowed to see
    labels: np.ndarray  # (H, W) uint8 — true terrain class per pixel
    contour_mask: np.ndarray  # (H, W) bool — where contour lines were drawn
    noise_mask: np.ndarray  # (H, W) bool — black map-text/point-symbol ink (T014, F5); never a real
    # linear feature, so it is what a correct pipeline must reject from the corridor output
    controls: list[Control]  # hub first, then controls; numbers and points are exact
    meters_per_pixel: float
    dpi: float
    scale_denominator: float

    @property
    def hub(self) -> Control:
        return self.controls[0]

    @property
    def shape(self) -> tuple[int, int]:
        return (int(self.labels.shape[0]), int(self.labels.shape[1]))


def _px_per_mm(dpi: float) -> float:
    return dpi / 25.4


def meters_per_pixel(scale_denominator: float, dpi: float) -> float:
    """Ground metres covered by one pixel (SPEC F2)."""
    return (25.4 / dpi) * scale_denominator / 1000.0


def _blob(rng: np.random.Generator, w: int, h: int, radius: float) -> np.ndarray:
    """A closed irregular polygon — terrain boundaries are never ellipses."""
    cx = rng.uniform(radius, w - radius)
    cy = rng.uniform(radius, h - radius)
    n = int(rng.integers(7, 12))
    angles = np.sort(rng.uniform(0, 2 * np.pi, n))
    radii = radius * rng.uniform(0.55, 1.0, n)
    pts = np.stack([cx + radii * np.cos(angles), cy + radii * np.sin(angles)], axis=1)
    return pts.astype(np.int32)


def _draw_area(
    image: np.ndarray, labels: np.ndarray, poly: np.ndarray, cls: TerrainClass
) -> None:
    cv2.fillPoly(image, [poly], RENDER_SRGB[SHADE_OF[cls]])
    cv2.fillPoly(labels, [poly], terrain_label(cls))


def _actual_stroke_width(thickness: int) -> int:
    """The width (px) `cv2.line`/`cv2.polylines` actually draws for an axis-aligned stroke asked
    to be `thickness` px -- not the same number for `thickness >= 2` (see `stroke_thickness_px`)."""
    if thickness <= 1:
        return 1
    return thickness + 1 if thickness % 2 == 0 else thickness + 2


def stroke_thickness_px(target_width_px: float) -> int:
    """The `thickness` to pass to `cv2.line`/`cv2.polylines` so the stroke it actually draws is as
    close as possible to `target_width_px` (T014, F5).

    OpenCV's thick-line rasterizer does not draw `thickness` pixels wide: measured directly, an
    axis-aligned stroke is 1 px for `thickness=1` and jumps in steps of 2 from there (3, 5, 7, ...),
    with two adjacent `thickness` values (one even, the odd one above it) landing on the same
    actual width. Left uncorrected, `round(0.35mm * ppm)=4` and `round(0.25mm * ppm)=3` --
    vehicle_track and footpath at the standard 300 dpi fixture -- both draw a 5 px stroke:
    indistinguishable by width, which defeats the one thing T014 measures against this fixture.
    This searches the achievable widths for the `thickness` that lands nearest the request.
    """
    target = max(1.0, target_width_px)
    candidates = range(1, int(target) + 4)
    return min(candidates, key=lambda t: abs(_actual_stroke_width(t) - target))


def _wandering_path(
    rng: np.random.Generator, w: int, h: int, steps: int = 9
) -> np.ndarray:
    """A polyline crossing the map — paths connect edges, they do not wander in circles."""
    vertical = bool(rng.integers(0, 2))
    t = np.linspace(0, 1, steps)
    drift = np.cumsum(rng.normal(0, 0.06, steps))
    drift = np.clip(0.5 + drift - drift[0], 0.08, 0.92)
    # A vertical path drifts in x as it runs down the map; a horizontal one drifts in y.
    xs, ys = (drift * w, t * h) if vertical else (t * w, drift * h)
    return np.stack([xs, ys], axis=1).astype(np.int32)


_LINEAR_CLASSES = (TerrainClass.ROAD, TerrainClass.VEHICLE_TRACK, TerrainClass.FOOTPATH)
_LINEAR_LABELS: set[int] = {terrain_label(c) for c in _LINEAR_CLASSES}


def _avoid_linear(
    labels: np.ndarray, y0: int, y1: int, x0: int, x1: int, linear_lbls: set[int]
) -> bool:
    """True if the label patch ``labels[y0:y1, x0:x1]`` contains no linear-class pixel.

    Keeps map-text and point-symbol noise (T014, F5) from touching a real road/track/footpath, so
    the two never merge into one connected component and contaminate the false-positive measurement
    the noise exists to support.
    """
    patch = labels[max(0, y0) : max(0, y1), max(0, x0) : max(0, x1)]
    return not np.isin(patch, list(linear_lbls)).any()


def _draw_map_text(
    image: np.ndarray,
    labels: np.ndarray,
    rng: np.random.Generator,
    ppm: float,
    width: int,
    height: int,
) -> np.ndarray:
    """Black map-text labels. Overprint only, like the control numbers -- `labels` is untouched."""
    noise = np.zeros((height, width), dtype=bool)
    black = RENDER_SRGB["black_100"]
    font_scale = (TEXT_HEIGHT_MM * ppm) / 22.0
    thickness = max(1, round(0.12 * ppm))

    for text in MAP_TEXT_LABELS:
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
        x, y = int(tw * 0.6), int(th * 1.5)  # fallback if every retry below stays on a road
        for _ in range(200):
            lo_x, hi_x = tw * 0.6, max(tw * 0.6 + 1.0, width - tw * 1.1)
            lo_y, hi_y = th * 1.5, max(th * 1.5 + 1.0, height - th * 0.5)
            x, y = int(rng.uniform(lo_x, hi_x)), int(rng.uniform(lo_y, hi_y))
            if _avoid_linear(labels, y - th - 4, y + 4, x - 4, x + tw + 4, _LINEAR_LABELS):
                break
        # `cv2.putText` antialiases Hershey glyphs regardless of `lineType` (the T013 landing note
        # in docs/TASKS.md names this exact OpenCV quirk for the control numbers) -- render into a
        # scratch layer and threshold it instead of writing straight onto `image`.
        layer = np.zeros((height, width), dtype=np.uint8)
        cv2.putText(layer, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, 255, thickness)
        hit = layer > 40
        image[hit] = black
        noise |= hit
    return noise


def _draw_point_symbols(
    image: np.ndarray,
    labels: np.ndarray,
    rng: np.random.Generator,
    ppm: float,
    width: int,
    height: int,
) -> np.ndarray:
    """Small filled black point symbols (e.g. ISOM 201 boulder). Overprint only, ditto."""
    noise = np.zeros((height, width), dtype=bool)
    black = RENDER_SRGB["black_100"]
    radius = max(1, round(POINT_SYMBOL_DIAMETER_MM / 2.0 * ppm))
    margin = radius * 3

    placed = 0
    for _ in range(400):
        if placed >= N_POINT_SYMBOLS:
            break
        lo, hi_w, hi_h = margin, max(margin + 1, width - margin), max(margin + 1, height - margin)
        x, y = int(rng.uniform(lo, hi_w)), int(rng.uniform(lo, hi_h))
        patch_ok = _avoid_linear(
            labels, y - radius - 2, y + radius + 2, x - radius - 2, x + radius + 2, _LINEAR_LABELS
        )
        if not patch_ok:
            continue
        cv2.circle(image, (x, y), radius, black, -1)  # filled, no LINE_AA -- see module docstring
        layer = np.zeros((height, width), dtype=np.uint8)
        cv2.circle(layer, (x, y), radius, 255, -1)
        noise |= layer > 0
        placed += 1
    return noise


def make_synthetic_map(
    width: int = 1600,
    height: int = 1200,
    *,
    seed: int = 0,
    dpi: float = 300.0,
    scale_denominator: float = 30000.0,
    n_controls: int = 12,
    degrade: bool = True,
) -> SyntheticMap:
    """Render a synthetic ISOM map with exact ground truth.

    Defaults describe a 1:30000 rogaine map scanned at 300 dpi — 2.54 m per pixel, so the standard
    1600x1200 fixture covers about 4 x 3 km and the 4000x3000 preset about 10 x 7.6 km. Those are
    real rogaine areas, which keeps the performance guards honest about the sizes they claim.

    With ``degrade=True`` the render picks up the things that make a scan a scan: a slight colour
    cast, sensor noise and JPEG ringing. Turn it off to isolate a classifier bug from a noise bug.
    """
    rng = np.random.default_rng(seed)
    ppm = _px_per_mm(dpi)
    mpp = meters_per_pixel(scale_denominator, dpi)

    image = np.full((height, width, 3), RENDER_SRGB["white"], dtype=np.uint8)
    labels = np.full((height, width), terrain_label(TerrainClass.FOREST_RUNNABLE), dtype=np.uint8)

    # Area features, painted in the order a cartographer would: broad ground cover first, then the
    # things that sit inside it.
    area_plan: list[tuple[TerrainClass, int, float]] = [
        (TerrainClass.OPEN_LAND, 3, 0.14),
        (TerrainClass.ROUGH_OPEN, 3, 0.11),
        (TerrainClass.VEG_SLOW_RUN, 4, 0.10),
        (TerrainClass.VEG_WALK, 3, 0.08),
        (TerrainClass.VEG_FIGHT, 3, 0.06),
        (TerrainClass.BARE_ROCK, 2, 0.05),
        (TerrainClass.MARSH, 2, 0.07),
        (TerrainClass.WATER_SHALLOW, 1, 0.06),
        (TerrainClass.WATER_UNCROSSABLE, 2, 0.08),
        (TerrainClass.PAVED_AREA, 1, 0.04),
    ]
    span = min(width, height)
    for cls, count, rel_radius in area_plan:
        for _ in range(count):
            _draw_area(image, labels, _blob(rng, width, height, span * rel_radius), cls)

    # Linear features. Roads and paths are drawn last among the ground features because on a real
    # map they are on top of everything they cross.
    for cls in (TerrainClass.ROAD, TerrainClass.VEHICLE_TRACK, TerrainClass.FOOTPATH):
        for _ in range(2):
            pts = _wandering_path(rng, width, height)
            thickness = stroke_thickness_px(LINE_WIDTH_MM[cls] * ppm)
            # No LINE_AA: an antialiased blend against the white background would put edge pixels
            # at intermediate colours that match no real shade (or, worse, one that coincidentally
            # does -- see the module docstring). `labels` is drawn hard-edged at the same thickness;
            # matching that here keeps every drawn pixel's colour and ground truth consistent.
            cv2.polylines(image, [pts], False, RENDER_SRGB[SHADE_OF[cls]], thickness)
            cv2.polylines(labels, [pts], False, terrain_label(cls), thickness)

    # Out-of-bounds: purple hatching over ground that stays forbidden underneath (see docstring).
    oob = _blob(rng, width, height, span * 0.09)
    cv2.fillPoly(labels, [oob], terrain_label(TerrainClass.OUT_OF_BOUNDS))
    hatch = np.zeros((height, width), dtype=np.uint8)
    step = max(4, round(1.5 * ppm))
    for offset in range(-height, width, step):
        cv2.line(hatch, (offset, 0), (offset + height, height), 255, max(1, int(0.4 * ppm)))
    oob_area = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(oob_area, [oob], 255)
    image[(hatch > 0) & (oob_area > 0)] = RENDER_SRGB["purple_100"]

    # Contours: dense towards the top edge, sparse towards the bottom, so a slope penalty has
    # something to bite on (T015). They overprint the terrain, so `labels` is untouched.
    contour_mask = np.zeros((height, width), dtype=bool)
    contour_layer = np.zeros((height, width), dtype=np.uint8)
    thickness = max(1, round(CONTOUR_WIDTH_MM * ppm))
    xs = np.arange(width)
    # Scaled to the map, not fixed: at a constant count a small fixture comes out almost solid
    # brown. 1200 px, the standard fixture, keeps its 26 lines.
    n_contours = max(8, round(height / 46.0))
    for i in range(n_contours):
        # Spacing tightens towards the top edge: the north of the map is the steep flank.
        base = (i / n_contours) ** 1.6 * height * 1.4 - height * 0.2
        amplitude = height * 0.05 * (0.5 + rng.random())
        phase = rng.uniform(0, 2 * np.pi)
        ys = base + amplitude * np.sin(2 * np.pi * xs / (width * rng.uniform(0.4, 0.9)) + phase)
        pts = np.stack([xs, ys], axis=1).astype(np.int32)
        cv2.polylines(contour_layer, [pts], False, 255, thickness, cv2.LINE_AA)
    contour_mask = contour_layer > 40
    image[contour_mask] = RENDER_SRGB["brown_100"]

    controls = _place_controls(
        image, labels, rng, n_controls=n_controls, ppm=ppm, width=width, height=height
    )

    # Black map-text and point-symbol noise (T014, F5): overprint only, `labels` untouched, kept
    # clear of the linear features above so it never merges into their connected components. Drawn
    # last, after every other rng-consuming step, so adding it here never reshuffles the geometry
    # (out-of-bounds blob, contour waviness, control placement) any seeded fixture already produced.
    noise_mask = _draw_map_text(image, labels, rng, ppm, width, height)
    noise_mask |= _draw_point_symbols(image, labels, rng, ppm, width, height)

    if degrade:
        image = _degrade(image, rng)

    return SyntheticMap(
        image=image,
        labels=labels,
        contour_mask=contour_mask,
        noise_mask=noise_mask,
        controls=controls,
        meters_per_pixel=mpp,
        dpi=dpi,
        scale_denominator=scale_denominator,
    )


def _place_controls(
    image: np.ndarray,
    labels: np.ndarray,
    rng: np.random.Generator,
    *,
    n_controls: int,
    ppm: float,
    width: int,
    height: int,
) -> list[Control]:
    """Draw the course overprint and return the truth about it.

    ``n_controls`` counts scoring controls; the hub is extra, so the returned list has
    ``n_controls + 1`` entries with the hub first.

    Numbers follow the rogaine convention the detector assumes: a two-digit code whose first digit
    is the control's value.
    """
    radius = CIRCLE_DIAMETER_MM / 2.0 * ppm
    ring = max(1, round(CIRCLE_WIDTH_MM * ppm))
    purple = RENDER_SRGB["purple_100"]
    forbidden = {
        terrain_label(TerrainClass.WATER_UNCROSSABLE),
        terrain_label(TerrainClass.OUT_OF_BOUNDS),
    }
    margin = radius * 3
    min_gap = radius * 5

    placed: list[tuple[float, float]] = []
    hub = (width / 2.0, height / 2.0)
    placed.append(hub)

    for _ in range(4000):
        if len(placed) > n_controls:
            break
        x = float(rng.uniform(margin, width - margin))
        y = float(rng.uniform(margin, height - margin))
        if int(labels[int(y), int(x)]) in forbidden:
            continue
        if any((x - px) ** 2 + (y - py) ** 2 < min_gap**2 for px, py in placed):
            continue
        placed.append((x, y))

    # A map too small for the requested course would otherwise come back with a hub and nothing
    # else, and every downstream assertion about controls would pass by vacuum. Fail instead.
    if len(placed) <= n_controls:
        raise ValueError(
            f"placed {len(placed) - 1} of {n_controls} controls on a {width}x{height} map at "
            f"{ppm * 25.4:.0f} dpi: the {min_gap:.0f} px minimum gap does not fit that many. "
            f"Ask for fewer controls, a bigger map, or a lower dpi."
        )

    # Start triangle (ISOM 701) at the hub, pointing north.
    side = radius * 2.2
    tri = np.array(
        [
            [hub[0], hub[1] - side * 0.62],
            [hub[0] - side * 0.54, hub[1] + side * 0.31],
            [hub[0] + side * 0.54, hub[1] + side * 0.31],
        ],
        dtype=np.int32,
    )
    cv2.polylines(image, [tri], True, purple, ring)  # no LINE_AA -- see the roads/tracks comment

    controls = [
        Control(id=0, x=hub[0], y=hub[1], number=None, points=0, source="detected", is_hub=True)
    ]

    font_scale = (NUMBER_HEIGHT_MM * ppm) / 22.0  # cv2's HERSHEY cap height at scale 1.0
    used_numbers: set[int] = set()
    for i, (x, y) in enumerate(placed[1:], start=1):
        number = int(rng.integers(2, 10)) * 10 + int(rng.integers(0, 10))
        while number in used_numbers:
            number = int(rng.integers(2, 10)) * 10 + int(rng.integers(0, 10))
        used_numbers.add(number)

        cv2.circle(image, (round(x), round(y)), round(radius), purple, ring)  # no LINE_AA, ditto
        # `cv2.putText` antialiases Hershey glyphs regardless of `lineType` (an OpenCV quirk, unlike
        # `line`/`circle`/`polylines`), so it can't write hard-edged purple directly onto `image`
        # the way the other overprint symbols above do. Render into a scratch layer and threshold
        # it instead, the same mask-then-hard-set pattern the contour lines below already use.
        number_layer = np.zeros((height, width), dtype=np.uint8)
        cv2.putText(
            number_layer,
            str(number),
            (round(x + radius * 1.15), round(y - radius * 0.6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            255,
            max(1, round(0.3 * ppm)),
        )
        image[number_layer > 40] = purple
        controls.append(
            Control(id=i, x=x, y=y, number=number, points=number // 10, source="detected")
        )

    return controls


def _degrade(image: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Make a clean render look like something that came off a scanner."""
    out = image.astype(np.float32)
    # Warm-ish cast and a gentle vignette, the two things every flatbed adds.
    cast = np.array([1.02, 1.0, 0.97], dtype=np.float32)
    out *= cast
    h, w = out.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((yy - h / 2) / (h / 2)) ** 2 + ((xx - w / 2) / (w / 2)) ** 2)
    out *= (1.0 - 0.06 * np.clip(r, 0, 1.4))[..., None]
    out += rng.normal(0.0, 2.0, out.shape).astype(np.float32)
    out = np.clip(out, 0, 255).astype(np.uint8)
    # A JPEG round-trip, because that is what the owner's files will have been through.
    ok, buf = cv2.imencode(".jpg", out[:, :, ::-1], [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    if not ok:  # pragma: no cover — cv2 does not fail at this without a broken build
        return out
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)[:, :, ::-1].copy()
