"""Route overlay rendering (T052, F15): a solved :class:`~rogaine.models.Route` drawn over the map.

Complements `render/preview.py` (which recolours `TerrainMap.labels`, never touching the original
raster) and `io/route_json.py` (T051, which serialises the very same `Route`): this module draws
directly over the *original* map raster -- the ``(H, W, 3)`` uint8 RGB array `io/raster.py`'s
``load_raster`` returns -- using `route.legs[i].polyline` unchanged.

**"Rendered legs match the JSON polylines pixel for pixel" holds by construction, not by anything
this module does.** `io/route_json.py`'s ``LegRecord.polyline`` is `Leg.polyline` copied verbatim
(no transform); this module draws from the same `Leg.polyline` list, so the two are the same points
by definition. What this module *does* control is not corrupting that guarantee with anti-aliasing:
every stroke below uses ``cv2.LINE_8`` (OpenCV's default, non-antialiased rasterizer) rather than
``cv2.LINE_AA``, so a pixel sitting exactly on a polyline coordinate is deterministically painted
the solid core colour, never a blended edge tone -- a property the test suite checks directly, not
just "the image changed somewhere".

**Legibility over both dark and light terrain: halo + core, drawn twice.** Every stroke, marker and
label is drawn twice with the same points -- first thicker in a near-black halo colour, then thinner
in a bright, high-saturation core colour on top (`cv2.polylines` / `cv2.circle` / `cv2.fillPoly` /
`cv2.putText` all take a plain ``thickness`` and are called twice). The halo keeps the core colour
readable against light open-land yellows and whites; the core keeps the line visible against dark
forest greens and blacks where a halo alone would vanish.

**Colour choice: bright magenta, not red, purple, or blue/cyan.** T073 widened
`config/default.toml`'s `[detector].ink_hue_ranges` to recognise red-pen control marks alongside
ISOM purple, so this module's original choice (bright red) stopped being a colour the map never
prints -- it broke the very invariant this section exists to argue for. `_CORE_COLOR` is now a
pure, fully-saturated magenta, picked by measurement rather than by eye: its CIELAB distance (the
same nearest-colour space `vision/palette.py`'s classifier already uses) to every one of the six
ISOM inks' nominal sRGB (`config.cmyk_to_srgb` on `[palette.ink]`'s CMYK) plus a representative red
sampled from a real hand-marked scan (`data/maps/grid-lines-red-controls/map.jpeg`, I1) is at
least ~48.3 -- comfortably above `PaletteSettings.lab_distance_threshold` (35.0), this project's
own bar for "clearly a different colour, not the same ink". See
``TestCoreColorDistinctFromForbiddenInks`` in this module's test file for the exact numbers. Blue
and cyan were still avoided, for the reason this section already gave for ruling out cyan before
red became an issue: blue is the water-body ink family, and a blue-hued route line over a lake
would read as "more water", not "route".

The guarantee this section states is a CIELAB distance, not hue exclusivity: `_CORE_COLOR`'s
OpenCV hue (150) happens to fall inside `config/default.toml`'s widened purple band (140-175), so
`vision/controls.py::purple_mask` on a magenta patch returns true. This has no effect on this
product's actual data flow -- `render_overlay` only ever draws onto a raster that has already been
through `detect_controls`, never the other way round -- but it means a rendered `route.png` is not
literally colour-disjoint from the control-ink mask, only Lab-distinguishable to any comparison
that measures colour difference the way this project's own classifier does (a human eye included).

**Numbered visit order, not `Control.number`.** Each intermediate stop is labelled with its 1-based
position in `route.order` (1st control visited, 2nd, ...) -- the DoD asks for visit order, and
`Control.number` is a different, physical-map-facing identifier that can also be ``None`` (unread).
This module deliberately does not also print `Control.number`: doing so risks a cluttered label at
small map scale for a value the DoD does not ask for, and visit order alone already satisfies the
literal requirement.

**The hub is drawn once, not as stop `1` and stop `N+1`.** `Route`'s own validator guarantees
``order[0] == order[-1]`` (`models.py::Route._legs_match_order`); this module takes that
structurally -- the hub id is `route.order[0]`, the visit-order loop runs over
``route.order[1:-1]`` only, and the hub gets a separate call with a distinct shape (a filled
triangle, echoing the ISOM 701 start/finish symbol `vision/controls.py` already looks for) and a
distinct label (``"H"``) rather than a numbered circle.

**Missing controls raise, they are not silently skipped.** If `route.order` names a control id
absent from the given ``controls`` list, `render_overlay` raises `ValueError` rather than drawing a
route with an unlabelled gap. This matches this project's standing convention that a present input
must be internally consistent (`io/controls_csv.py`, `io/route_json.py`) -- a route referencing a
control nobody can see is a rendering defect a caller needs to know about immediately, not a corner
case to paper over.

**Geometry scales off the image's own size, not a flat pixel constant.** `vision/controls.py` scales
its detection geometry from DPI in millimetres; this module is given no DPI (out of scope for T052),
and a full-size map (commonly 4000x3000px) next to a tiny test fixture (tens of pixels) differ by
roughly two orders of magnitude, so one fixed stroke width would be invisible on one and absurd on
the other. Every stroke width, marker radius and font scale here is instead a fraction of
``max(image.shape[:2])``, clamped to a sane pixel range -- see `_geometry`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from rogaine.models import Control, Leg, Route

# --------------------------------------------------------------------------------------------
# Colour -- see the module docstring for why magenta, and why not red, purple, blue or cyan.
# --------------------------------------------------------------------------------------------
_HALO_COLOR: tuple[int, int, int] = (15, 15, 15)  # near-black RGB, the halo/outline pass
_CORE_COLOR: tuple[int, int, int] = (255, 0, 255)  # bright magenta RGB, the legible pass on top
_FONT = cv2.FONT_HERSHEY_SIMPLEX
_LINE_TYPE = cv2.LINE_8  # not LINE_AA -- see module docstring, pixel-for-pixel reproducibility

# --------------------------------------------------------------------------------------------
# Image-size-relative geometry -- see `_geometry` and the module docstring.
# --------------------------------------------------------------------------------------------
_CORE_LINE_FRACTION = 0.0015
_MIN_CORE_LINE = 1
_MAX_CORE_LINE = 6
_HALO_EXTRA_FRACTION = 0.0025
_MIN_HALO_EXTRA = 2
_MAX_HALO_EXTRA = 10
_MARKER_RADIUS_FRACTION = 0.006
_MIN_MARKER_RADIUS = 3
_MAX_MARKER_RADIUS = 22
_FONT_SCALE_FRACTION = 0.00045
_MIN_FONT_SCALE = 0.3
_MAX_FONT_SCALE = 1.6
_FONT_THICKNESS_FRACTION = 0.0006
_MIN_FONT_THICKNESS = 1
_MAX_FONT_THICKNESS = 4


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


@dataclass(frozen=True)
class _Geometry:
    """Every pixel size this module draws with, derived once per image by `_geometry`."""

    core_line: int
    halo_line: int
    marker_radius: int
    halo_extra: int
    font_scale: float
    font_core: int
    font_halo: int
    label_offset: int


def _geometry(image: np.ndarray) -> _Geometry:
    """Derive stroke widths, marker radius and font scale from `image`'s largest dimension.

    Each quantity is ``dim * fraction``, clamped to a ``[min, max]`` pixel range so a tiny test
    fixture still gets a visible (if minimal) line/marker/label and a full-size map does not get an
    absurdly thick one. See the module docstring for why this scales off image size rather than a
    flat constant or a DPI input.
    """
    dim = max(image.shape[:2])
    core_line = round(_clamp(dim * _CORE_LINE_FRACTION, _MIN_CORE_LINE, _MAX_CORE_LINE))
    halo_extra = round(_clamp(dim * _HALO_EXTRA_FRACTION, _MIN_HALO_EXTRA, _MAX_HALO_EXTRA))
    marker_radius = round(
        _clamp(dim * _MARKER_RADIUS_FRACTION, _MIN_MARKER_RADIUS, _MAX_MARKER_RADIUS)
    )
    font_scale = _clamp(dim * _FONT_SCALE_FRACTION, _MIN_FONT_SCALE, _MAX_FONT_SCALE)
    font_core = round(
        _clamp(dim * _FONT_THICKNESS_FRACTION, _MIN_FONT_THICKNESS, _MAX_FONT_THICKNESS)
    )
    return _Geometry(
        core_line=core_line,
        halo_line=core_line + halo_extra,
        marker_radius=marker_radius,
        halo_extra=halo_extra,
        font_scale=font_scale,
        font_core=font_core,
        font_halo=font_core + halo_extra,
        label_offset=marker_radius + halo_extra,
    )


def _fmt_duration(seconds: float) -> str:
    """Render seconds as `H:MM:SS`, or `M:SS` under an hour.

    Mirrors `cli.py`'s own `_fmt_duration` rather than importing it -- this project's established
    convention for small presentation helpers crossing a module boundary (`solve/heuristic.py`'s
    `_build_legs` docstring makes the same call); `cli.py` is presentation layer, not a shared
    utility module.
    """
    total = max(0, round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _point(control: Control) -> tuple[int, int]:
    return (round(control.x), round(control.y))


def _triangle_vertices(center: tuple[int, int], radius: int) -> np.ndarray:
    """Three vertices of an upward-pointing equilateral triangle, circumradius `radius`."""
    cx, cy = center
    angles_deg = (-90.0, 30.0, 150.0)  # top, lower-right, lower-left
    pts = [
        (
            round(cx + radius * math.cos(math.radians(a))),
            round(cy + radius * math.sin(math.radians(a))),
        )
        for a in angles_deg
    ]
    return np.array(pts, dtype=np.int32)


def _draw_halo_polyline(img: np.ndarray, points: list[tuple[int, int]], geo: _Geometry) -> None:
    pts = np.asarray(points, dtype=np.int32).reshape((-1, 1, 2))
    cv2.polylines(img, [pts], False, _HALO_COLOR, thickness=geo.halo_line, lineType=_LINE_TYPE)
    cv2.polylines(img, [pts], False, _CORE_COLOR, thickness=geo.core_line, lineType=_LINE_TYPE)


def _draw_halo_text(
    img: np.ndarray, text: str, org: tuple[int, int], geo: _Geometry
) -> None:
    cv2.putText(
        img, text, org, _FONT, geo.font_scale, _HALO_COLOR, geo.font_halo, lineType=_LINE_TYPE
    )
    cv2.putText(
        img, text, org, _FONT, geo.font_scale, _CORE_COLOR, geo.font_core, lineType=_LINE_TYPE
    )


def _label_origin(center: tuple[int, int], geo: _Geometry) -> tuple[int, int]:
    return (center[0] + geo.label_offset, center[1] - geo.label_offset)


def _draw_stop(img: np.ndarray, control: Control, position: int, geo: _Geometry) -> None:
    """A numbered visit-order stop: a filled circle marker plus its 1-based position label."""
    center = _point(control)
    cv2.circle(img, center, geo.marker_radius + geo.halo_extra, _HALO_COLOR, -1, _LINE_TYPE)
    cv2.circle(img, center, geo.marker_radius, _CORE_COLOR, -1, _LINE_TYPE)
    _draw_halo_text(img, str(position), _label_origin(center, geo), geo)


def _draw_hub(img: np.ndarray, control: Control, geo: _Geometry) -> None:
    """The hub (start and finish, drawn once): a filled triangle plus an "H" label -- distinct in
    shape from the numbered circle stops, echoing the ISOM 701 start/finish symbol."""
    center = _point(control)
    halo_tri = _triangle_vertices(center, geo.marker_radius + geo.halo_extra).reshape((-1, 1, 2))
    core_tri = _triangle_vertices(center, geo.marker_radius).reshape((-1, 1, 2))
    cv2.fillPoly(img, [halo_tri], _HALO_COLOR, lineType=_LINE_TYPE)
    cv2.fillPoly(img, [core_tri], _CORE_COLOR, lineType=_LINE_TYPE)
    _draw_halo_text(img, "H", _label_origin(center, geo), geo)


def _leg_midpoint(leg: Leg, by_id: dict[int, Control]) -> tuple[int, int]:
    pts = leg.polyline
    if len(pts) >= 2:
        mid_idx = (len(pts) - 1) / 2
        lo, hi = pts[math.floor(mid_idx)], pts[math.ceil(mid_idx)]
        return (round((lo[0] + hi[0]) / 2), round((lo[1] + hi[1]) / 2))
    if pts:
        return pts[0]
    frm, to = by_id[leg.from_id], by_id[leg.to_id]
    return (round((frm.x + to.x) / 2), round((frm.y + to.y) / 2))


def _draw_leg(img: np.ndarray, leg: Leg, by_id: dict[int, Control], geo: _Geometry) -> None:
    if len(leg.polyline) >= 2:
        _draw_halo_polyline(img, leg.polyline, geo)
    mid = _leg_midpoint(leg, by_id)
    _draw_halo_text(img, _fmt_duration(leg.seconds), _label_origin(mid, geo), geo)


def render_overlay(image: np.ndarray, route: Route, controls: list[Control]) -> np.ndarray:
    """Draw `route` over `image`: each leg's polyline, a numbered marker per visited stop, the
    hub drawn once, and each leg's time near its polyline. Returns a new ``(H, W, 3)`` uint8 RGB
    array -- `image` itself is never mutated, matching `render_preview`'s own contract (a caller
    reasonably expects its own array back unchanged).

    Raises `ValueError` if `route.order` names a control id not present in `controls` -- see the
    module docstring's "Missing controls raise" note.
    """
    by_id = {control.id: control for control in controls}
    missing = sorted({control_id for control_id in route.order if control_id not in by_id})
    if missing:
        raise ValueError(
            f"route references control id(s) {missing} not present in the given controls list"
        )

    out = image.copy()
    geo = _geometry(out)

    for leg in route.legs:
        _draw_leg(out, leg, by_id, geo)

    for position, control_id in enumerate(route.order[1:-1], start=1):
        _draw_stop(out, by_id[control_id], position, geo)

    _draw_hub(out, by_id[route.order[0]], geo)

    return out


def write_overlay(path: Path, image: np.ndarray, route: Route, controls: list[Control]) -> None:
    """Write :func:`render_overlay`'s output to *path* as a PNG.

    ``cv2.imwrite`` expects BGR, so the RGB output of `render_overlay` is channel-swapped first --
    skipping that step ships a colour-swapped PNG, not an error. ``cv2.imwrite`` also fails
    silently (returns ``False``, raises nothing) on a bad path such as a missing parent directory;
    that return value is checked here so a bad *path* raises clearly instead of leaving no file and
    no error. Mirrors `write_preview` exactly (same failure mode, same fix).
    """
    overlay = render_overlay(image, route, controls)
    bgr = cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR)
    if not cv2.imwrite(str(path), bgr):
        raise OSError(f"failed to write overlay PNG to {path}")
