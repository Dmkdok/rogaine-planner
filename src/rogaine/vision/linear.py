"""Linear feature extraction: roads, tracks and footpaths as connected corridors (T014, F5).

:mod:`rogaine.vision.palette` collapses `road`, `vehicle_track` and `footpath` into a single `ROAD`
label, because all three print in `black_100` and colour alone cannot separate them (its own module
docstring says so explicitly). This module takes that placeholder and does the geometric split: it
finds connected components of the `road` mask, rejects the ones that are not shaped like a corridor,
and assigns the survivors to `road` / `vehicle_track` / `footpath` by measured stroke width.

**Elongation.** For a connected component of area ``A`` and skeleton length ``S`` (pixel count of
``skimage.morphology.skeletonize``'s output), define ``elongation = S / sqrt(A)``. A straight
corridor of width ``w`` and length ``L`` has ``A ~= w*L`` and ``S ~= L``, so
``elongation ~= sqrt(L/w)``: it grows with how much longer the shape is than it is wide, and does
not depend on absolute size. A blob -- a point symbol, a single glyph's dot or bowl -- has
``A ~= S**2``, so its elongation sits near a small constant. ``config.linear.elongation_ratio_min``
is the cutoff. Components smaller than ``config.linear.min_component_area_px`` are rejected before
this test even runs; the ratio is not stable on a handful of pixels.

**Absolute length floor.** Elongation alone is not enough: a single tall, narrow glyph (a capital
"I" or "L", a digit "1") at a typical map-text font size can score an elongation ratio comparable to
a real corridor's, purely because the font's cap-height-to-stroke-width ratio is itself a few units.
What actually separates them is size on paper: text and point symbols are bounded by a font's cap
height or a symbol's diameter -- a few millimetres -- while a road, track or footpath is a
through-route and is, on any real map, far longer than that. ``config.linear.min_length_mm``
(converted to pixels via the map's own DPI, never hardcoded) is that floor, checked against the same
skeleton length used for elongation.

**Bounding-box aspect ratio.** Neither test above is safe alone against a cluster of touching or
closing-bridged glyphs (several letters of a word, close enough to merge into one component): a
branchy skeleton -- several short strokes meeting at junctions -- can rack up enough total pixel
count to pass both the elongation ratio and the length floor even though the component is not
shaped like a corridor at all. What it does not have is a long *straight-line* extent: the smallest
rotated rectangle enclosing it (``cv2.minAreaRect``) is close to square. A real corridor, even a
wandering one, is long in some direction over its whole run, so its ``minAreaRect`` is not.
``config.linear.aspect_ratio_min`` (the rectangle's long side over its short side) is the cutoff --
measured against real fixture components: touching-glyph clusters top out near 1.6, the shortest
real corridor fragments start near 2.8. A component must pass the elongation ratio, the length
floor *and* this aspect ratio to be accepted; failing any one of the three is enough to reject it.

**Gap bridging.** ``config.linear.close_radius_px`` morphologically closes the `road` mask before
components are found and skeletonized, so a corridor interrupted by a few pixels of scan noise, or
by crossing another feature at a shallow angle, still comes back as one component -- SPEC F5's own
wording, "connected corridors, not scattered black pixels". Kept small on purpose: enough to bridge
scan noise, too little to merge a corridor with unrelated ink placed nearby (e.g. a text label close
to a path).

**Width assignment.** For an accepted component, ``cv2.distanceTransform`` gives, at every pixel,
the distance between that pixel's *centre* and the nearest non-mask pixel's *centre*; along the
component's own skeleton pixels (away from endpoints and junctions, which is what the median
discounts), ``2 * median(distance) - 1`` estimates the stroke's width in pixels. The ``- 1``
matters: for a centreline distance ``d``, the true width is ``2d`` (even) or ``2d - 1`` (odd) -- the
pixel grid cannot tell which -- and every width this pipeline draws or measures is a whole number of
pixels, so treating it as odd is exact whenever it is, and off by only one pixel otherwise, which
the class widths are always spaced apart by more than. The component is assigned whichever of
`road` / `vehicle_track` / `footpath` has the nearest nominal printed width at the map's DPI
(``config.linear.nominal_width_px``) -- one class for the whole component, matching "connected
corridor" rather than a per-pixel patchwork.

**Rejected components become `unknown`, not left as `road`.** A component that fails any shape test
is stripped of its `road` label and set to `TerrainClass.UNKNOWN`, at exactly the pixels the
palette classifier originally called `road` -- not at the small filler pixels a morphological close
may have added, which were never black ink and already carry whatever label they had. This is the
same "do not force a wrong guess" position :mod:`rogaine.vision.palette` takes for `unknown`, and it
composes with :func:`rogaine.vision.palette.fill_unknown` if a caller wants the neighbourhood to
reclaim that area.

**Accepted components keep the closing-bridged pixels.** Once a component is judged a real
corridor, its whole bridged footprint -- ink plus the small gaps :func:`extract_linear_features`
just closed -- is labelled with the assigned class: that is what "recovered as a connected
corridor" means.
"""

from __future__ import annotations

import cv2
import numpy as np
from skimage.morphology import skeletonize

from rogaine.config import AppConfig, default_config
from rogaine.models import TerrainClass, terrain_label


def _aspect_ratio(mask: np.ndarray, x: int, y: int, w: int, h: int) -> float:
    """``minAreaRect``'s long side over its short side, for the True pixels of *mask* in the
    ``[y:y+h, x:x+w]`` box. 1.0 for a compact blob, large for a component that is genuinely much
    longer than it is wide in *some* direction -- unlike the skeleton-length elongation ratio, this
    is not fooled by a branchy skeleton (see :func:`extract_linear_features`'s module docstring).
    """
    pts = cv2.findNonZero(mask[y : y + h, x : x + w].astype(np.uint8))
    if pts is None or len(pts) < 2:
        return 0.0
    (_, _), (rw, rh), _ = cv2.minAreaRect(pts)
    lo, hi = sorted((rw, rh))
    return hi / max(lo, 1e-6)


def extract_linear_features(
    labels: np.ndarray, dpi: float, config: AppConfig | None = None
) -> np.ndarray:
    """Split the palette classifier's `road` placeholder into real linear corridors (T014, F5).

    *labels* is an ``(H, W)`` uint8 array as produced by
    :func:`rogaine.vision.palette.classify_palette` (or
    :func:`rogaine.vision.palette.classify_labels`), indexed by
    :data:`rogaine.models.TERRAIN_ORDER`. *dpi* is the raster's scan resolution -- the same value
    :class:`rogaine.config.DetectorSettings.circle_radius_px` takes explicitly, for the same reason:
    printed sizes are fixed in millimetres, not pixels.

    Returns an array of the same shape and convention: every pixel the palette classified `road`
    becomes `road`, `vehicle_track`, `footpath` (a real corridor) or `unknown` (rejected as
    non-corridor ink); every other pixel is returned unchanged.
    """
    if labels.ndim != 2:
        raise ValueError(f"expected an (H, W) labels array, got shape {labels.shape}")
    if labels.dtype != np.uint8:
        raise ValueError(f"expected uint8 labels, got {labels.dtype}")
    if not dpi > 0:
        raise ValueError(f"dpi must be positive, got {dpi}")

    cfg = config or default_config()
    lin = cfg.linear

    road_lbl = terrain_label(TerrainClass.ROAD)
    unknown_lbl = terrain_label(TerrainClass.UNKNOWN)
    mask = labels == road_lbl

    out = labels.copy()
    if not mask.any():
        return out

    if lin.close_radius_px > 0:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (2 * lin.close_radius_px + 1, 2 * lin.close_radius_px + 1)
        )
        closed = cv2.morphologyEx(mask.astype(np.uint8) * 255, cv2.MORPH_CLOSE, kernel)
    else:
        closed = mask.astype(np.uint8) * 255

    skeleton = skeletonize(closed > 0)
    dist = cv2.distanceTransform(closed, cv2.DIST_L2, 5)
    n_components, cc, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)

    nominal_px = lin.nominal_width_px(dpi).items()
    min_length_px = lin.min_length_px(dpi)

    for comp_id in range(1, n_components):
        comp_mask = cc == comp_id
        area = int(stats[comp_id, cv2.CC_STAT_AREA])
        if area < lin.min_component_area_px:
            out[comp_mask & mask] = unknown_lbl
            continue

        skeleton_len = int(np.count_nonzero(skeleton & comp_mask))
        elongation = skeleton_len / np.sqrt(area)
        if elongation < lin.elongation_ratio_min or skeleton_len < min_length_px:
            out[comp_mask & mask] = unknown_lbl
            continue

        x, y, w, h = (int(v) for v in stats[comp_id, cv2.CC_STAT_LEFT : cv2.CC_STAT_HEIGHT + 1])
        if _aspect_ratio(comp_mask, x, y, w, h) < lin.aspect_ratio_min:
            out[comp_mask & mask] = unknown_lbl
            continue

        # `cv2.distanceTransform` gives the distance between a foreground pixel's *centre* and the
        # nearest background pixel's *centre*. For a stroke of true width W that centreline distance
        # is ceil(W/2), so 2*distance overestimates an odd W by exactly 1 (and matches an even W
        # exactly) -- subtracting 1 makes this exact for a stroke drawn at any odd width, which is
        # every width this pipeline ever draws or measures (widths are always >= 1 whole pixel).
        skeleton_widths = dist[skeleton & comp_mask] * 2.0 - 1.0
        if skeleton_widths.size > 0:
            estimated_width = float(np.median(skeleton_widths))
        else:  # pragma: no cover -- a component passing the length floor always has skeleton pixels
            estimated_width = float(dist[comp_mask].max()) * 2.0 - 1.0

        assigned = min(nominal_px, key=lambda kv: abs(kv[1] - estimated_width))[0]
        out[comp_mask] = terrain_label(assigned)

    return out
