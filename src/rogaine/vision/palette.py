"""ISOM palette classifier: nearest-colour terrain classification in CIELAB (T013).

Takes an already-normalised RGB image — the architecture diagram in ``docs/PLAN.md`` draws
``norm --> seg``, so :func:`rogaine.vision.normalize.normalize` is the caller's job, run once,
before this module ever sees a pixel — and produces an ``(H, W)`` uint8 labels array indexed by
:data:`rogaine.models.TERRAIN_ORDER`, the same convention :class:`rogaine.models.TerrainMap.labels`
uses.

Algorithm: convert both the image and every configured shade to CIELAB (``skimage.color.rgb2lab``),
then give every pixel the shade with the smallest CIE76 (plain Euclidean Lab) distance — that is
what ``config/default.toml`` itself says ``palette.lab_distance_threshold`` measures, and it is what
``tests/unit/vision/test_normalize.py`` already measures distances with, so the whole pipeline
agrees on one notion of colour distance. A pixel farther than ``lab_distance_threshold`` from every
shade becomes ``unknown`` rather than a forced, wrong guess.

**Shared-shade classes (design decision).** ``road``, ``vehicle_track`` and ``footpath`` are all
printed in ``black_100`` (``config/default.toml``); colour alone cannot tell them apart, and it is
not supposed to — T014 separates them geometrically (width, elongation, skeleton length).
:func:`shade_to_terrain` resolves every ``black_100`` pixel to ``road``: the first of the three in
``TERRAIN_ORDER``, which also happens to be the widest of the three on the fixture (0.60 mm vs.
0.35/0.25 mm) and the class that defines the whole speed table (``speed_factor = 1.0`` by
definition). T014 overwrites this placeholder with the real sub-class downstream; this module's own
IoU test measures the union of the three ("any linear black class") against SPEC F4's 0.80 linear
bar, not each sub-class separately — the palette genuinely cannot support a finer split by colour,
so the test says so rather than faking one.

**``unknown`` neighbourhood fill.** :func:`fill_unknown` repeats a majority-vote pass to a fixed
point: each pass counts already-classified (non-``unknown``) neighbours within
``unknown_fill_radius`` pixels via an O(1)-per-pixel box filter (``cv2.boxFilter``, with
``BORDER_CONSTANT`` so the count never picks up a phantom pixel past the image edge), and every
``unknown`` pixel reachable this pass takes the class with the most votes. A single pass only
reaches pixels within ``unknown_fill_radius`` of an originally-known pixel; repeating lets the fill
grow outward a ring at a time from the known border, so a region wider than ``2 * radius`` still
fills completely, not just its rim. A pixel with zero known neighbours in range on the pass that
just ran (deep inside a very large unclassified region, or ``unknown_fill_radius = 0``) is left
``unknown`` rather than handed an arbitrary label, and the loop stops as soon as a pass changes
nothing.

**``out_of_bounds`` and ``contour`` are not scored against SPEC F4's 0.95 "area class" bar.**

* ``contour`` never appears in the fixture's own ground truth ``labels`` at all — contour lines are
  overprint, and ``tests/fixtures/synth_map.py``'s docstring is explicit that the terrain underneath
  is unaffected. A colour classifier legitimately reports ``contour`` wherever it sees contour ink,
  which necessarily disagrees with the pre-overprint ``labels`` value at exactly those pixels. Every
  IoU measurement in ``tests/unit/vision/test_palette.py`` therefore excludes ``contour_mask``
  pixels — the same ``sampleable = ~contour_mask`` convention ``test_normalize.py`` already uses.
* ``out_of_bounds`` is filled ground truth (the *whole* enclosed polygon is
  ``labels == OUT_OF_BOUNDS``) but only *drawn* as purple hatching over the terrain that was there
  before — the fixture's own docstring says a correct pipeline "has to fill the hatch, not just
  trace it". :func:`classify_labels` alone has no notion of "enclosed": it correctly classifies
  the hatch lines themselves and, just as correctly by its own lights, classifies the ground
  between them as whatever colour is actually there — that is this function working as specified,
  not a bug. :func:`classify_palette` closes the gap one step later, via
  :func:`_close_out_of_bounds_regions` (T109, ADR-036); the synthetic fixture has no hatched region
  wide enough to exercise it (real-scan-only coverage, ``tests/unit/vision/test_segment.py``), so
  this IoU test still measures and reports ``out_of_bounds`` without asserting a floor on it.

**Performance.** No per-pixel Python loop. ``rgb2lab`` runs once on the whole image and once on the
~14 configured shades; distance-to-each-shade is a Python loop of ~14 broadcasted ``(H, W)`` array
subtractions, not a stacked ``(H, W, K)`` tensor — kept that way so a 4000x3000 image costs 14
``(H, W)`` float32 arrays rather than one multi-gigabyte one. The unknown fill is 16
``cv2.boxFilter`` calls per pass, each O(H*W) regardless of ``unknown_fill_radius``, repeated until
a pass changes nothing — bounded by how many ``radius``-sized rings the widest unknown region
needs, not by image size.

**``contour``'s ``speed_factor = 0.0`` despite ``passable = true``** (``config/default.toml``) is a
real, deliberate config quirk, not a bug for this module to "fix": contour only feeds the slope
penalty (T015), never the speed table — config's own note says so, and this classifier's logic
never looks at ``speed_factor`` at all.
"""

from __future__ import annotations

import cv2
import numpy as np
from scipy import ndimage
from skimage.color import rgb2lab

from rogaine.config import AppConfig, default_config
from rogaine.models import TERRAIN_ORDER, TerrainClass, terrain_label


def shade_to_terrain(config: AppConfig) -> dict[str, TerrainClass]:
    """The terrain class each configured shade resolves to.

    One-to-one for every shade except ``black_100`` (``road``, ``vehicle_track``, ``footpath``):
    the first class to claim a shade in ``TERRAIN_ORDER`` wins it, which is ``road`` for the shared
    one — see the module docstring for why that default is reasonable. ``unknown`` is never a value
    here: its configured shade is the ``"none"`` sentinel, not a real printed colour.
    """
    mapping: dict[str, TerrainClass] = {}
    for cls in TERRAIN_ORDER:
        if cls is TerrainClass.UNKNOWN:
            continue
        mapping.setdefault(config.terrain_of(cls).shade, cls)
    return mapping


def classify_labels(image: np.ndarray, config: AppConfig | None = None) -> np.ndarray:
    """Nearest-shade CIELAB classification, no neighbourhood fill.

    *image* must already be normalised RGB (see the module docstring). Returns an ``(H, W)`` uint8
    array indexed by ``TERRAIN_ORDER``; pixels farther than
    ``config.palette.lab_distance_threshold`` from every shade get ``TerrainClass.UNKNOWN``'s label.
    """
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"expected an (H, W, 3) RGB image, got shape {image.shape}")
    if image.dtype != np.uint8:
        raise ValueError(f"expected uint8 pixels, got {image.dtype}")

    cfg = config or default_config()
    mapping = shade_to_terrain(cfg)
    shade_names = list(mapping.keys())
    shade_srgb = np.array([cfg.palette.srgb_of(name) for name in shade_names], dtype=np.uint8)
    shade_lab = rgb2lab(shade_srgb.reshape(1, -1, 3)).astype(np.float32).reshape(-1, 3)
    class_labels = np.array(
        [terrain_label(mapping[name]) for name in shade_names], dtype=np.uint8
    )

    image_lab = rgb2lab(image).astype(np.float32)
    best_dist2: np.ndarray | None = None
    best_idx: np.ndarray | None = None
    for k in range(len(shade_names)):
        diff = image_lab - shade_lab[k]
        dist2 = np.sum(diff * diff, axis=-1)
        if best_dist2 is None:
            best_dist2 = dist2
            best_idx = np.zeros(dist2.shape, dtype=np.intp)
        else:
            better = dist2 < best_dist2
            best_idx = np.where(better, k, best_idx)
            best_dist2 = np.where(better, dist2, best_dist2)

    assert best_dist2 is not None and best_idx is not None  # shade_names is never empty

    labels = class_labels[best_idx]
    unknown = np.sqrt(best_dist2) > cfg.palette.lab_distance_threshold
    labels[unknown] = terrain_label(TerrainClass.UNKNOWN)
    return labels


def fill_unknown(labels: np.ndarray, radius: int) -> np.ndarray:
    """Overwrite ``unknown`` pixels with the majority class among their known neighbours.

    Each ``unknown`` pixel takes whichever class has the most votes among non-``unknown`` pixels
    within a ``radius``-pixel box. One pass is not always enough to reach every pixel of a large
    unknown region -- a pixel deeper than ``radius`` from any originally-known pixel has no vote to
    count on the first pass -- so this repeats until a pass makes no further change: each pass can
    only ever recruit pixels adjacent (within ``radius``) to the *previous* pass's newly-filled
    pixels, so the fill grows outward from the known border a ``radius``-sized ring at a time,
    the same way a majority-vote fill would if it were computed one ring at a time by hand. A
    region with no known pixels anywhere near it (nothing to vote) reaches a fixed point unfilled
    and stays ``unknown``, which is the last pass detects via "no pixel changed" and stops on.
    """
    unknown_label = terrain_label(TerrainClass.UNKNOWN)
    if radius <= 0 or not (labels == unknown_label).any():
        return labels

    ksize = 2 * radius + 1
    filled = labels.copy()
    while True:
        still_unknown = filled == unknown_label
        if not still_unknown.any():
            break

        best_count = np.full(filled.shape, -1.0, dtype=np.float32)
        best_label = np.zeros(filled.shape, dtype=np.uint8)
        for cls in TERRAIN_ORDER:
            if cls is TerrainClass.UNKNOWN:
                continue
            lbl = terrain_label(cls)
            mask = (filled == lbl).astype(np.float32)
            count = cv2.boxFilter(
                mask, ddepth=-1, ksize=(ksize, ksize), normalize=False,
                borderType=cv2.BORDER_CONSTANT,
            )
            better = count > best_count
            best_count = np.where(better, count, best_count)
            best_label = np.where(better, lbl, best_label)

        fill_here = still_unknown & (best_count > 0)
        if not fill_here.any():
            break  # no known pixel is reachable from any remaining `unknown` pixel; stop here
        filled[fill_here] = best_label[fill_here]

    return filled


def _close_out_of_bounds_regions(
    labels: np.ndarray,
    dpi: float,
    hatch_close_mm: float = 2.4,
    min_density_fraction: float = 0.25,
    min_closed_fraction: float = 0.70,
    min_solidity_fraction: float = 0.70,
) -> np.ndarray:
    """Fill a hatched ``out_of_bounds`` polygon's whole enclosed interior (T109, ADR-036, F4).

    :func:`classify_labels` is a per-pixel nearest-shade classifier with no notion of "enclosed":
    it correctly labels the ISOM 709 hatch lines themselves ``out_of_bounds`` and, just as
    correctly by its own lights, labels the paper showing through the gaps between them as
    whatever terrain colour is actually printed there. T108's measurement on
    ``data/maps/ogps-8620_502cda4f6c774e8ecb86d063a71895f6`` (three real out-of-bounds polygons,
    not one -- this map's own control circles print red, not purple) found the largest polygon's
    raw hatch-ink density inside its own interior only 56.75%: :func:`fill_unknown`'s radius-3
    majority vote closes most of the ambiguous ``unknown`` remainder as a side effect (56.75% ->
    81.06% ``out_of_bounds`` after the full pipeline), but not the 15.94% where a wide gap lands a
    *confident* nearest-shade match on real terrain (``forest_runnable``, mostly) -- that residual
    then leaks through `cost/graph.py`'s any-passable-pixel block rule as routable ground.

    Run this *before* :func:`_consolidate_banked_water`/:func:`fill_unknown` so the region is
    already closed by the time either runs, rather than have `fill_unknown` do a partial,
    order-sensitive job on whatever gaps happen to be within its own radius of known ink.

    Mirrors :func:`_consolidate_banked_water`'s shape: close the raw hatch mask with a kernel sized
    to the hatch's own line pitch, fill each closed component's external contour, and promote every
    pixel inside a fill to ``out_of_bounds`` -- but only if that filled interior passes *two*
    "don't swallow unrelated terrain" guards (the same role ``_consolidate_banked_water``'s
    ``min_bank_fraction`` plays there):

    * ``min_density_fraction`` -- the filled interior's own raw hatch-ink density. Calibration
      (T108, ``ogps-8620``): the three real polygons measured 36-57% density; one small unrelated
      purple symbol (a start-triangle fragment, same ``purple_100`` ink) measured only 15%.
    * ``min_closed_fraction`` -- the fraction of the filled interior *already* covered by the
      closed mask itself, before this function's own contour fill adds anything. A real hatch
      pattern, once its own pitch is bridged by ``hatch_close_mm``'s kernel, is already
      near-solid throughout its interior (closing alone does most of the work); a purple ring
      symbol (an ISOM control circle, or this project's own synthetic fixture's course-overprint
      circles, sharing ``purple_100`` ink per ``config/default.toml``'s ``out_of_bounds`` note) is
      a thin loop closing into a mostly-*empty* disk -- the disk only gets covered by this
      function's own contour fill, not by closing. Needed because ``min_density_fraction`` alone
      cannot separate the two here: closing bridges a control circle's ring to its own adjacent
      purple control-number digits (a few px apart, well within any kernel that also bridges a
      real hatch's own, much coarser, pitch), and that ring+digit density (measured on this
      project's synthetic fixture, ``tests/conftest.py``'s ``clean_synthetic_map``: 0.296-0.387)
      overlaps the real polygon's own density there (0.319) -- but the two are cleanly separable
      on ``min_closed_fraction`` alone (real polygon 0.847 vs. every ring+digit false positive
      0.537-0.608), so this second guard is load-bearing, not redundant.
    * ``min_solidity_fraction`` -- ``filled_area / convex_hull_area`` of the same filled contour.
      Added after the synthetic fixture's own IoU floor caught a case the two guards above cannot
      separate: a course-overprint control that happens to land close enough to the real polygon's
      own hatch to bridge directly into it (closing's kernel does not require them to touch, only
      to come within its own radius) rather than sitting elsewhere on the map as its own isolated
      component. That merged "dumbbell" measured density 0.319 and closed_fraction 0.847 --
      statistically indistinguishable from a genuine large polygon (ogps-8620's own largest measured
      0.567/1.0) -- because the control's own solid ink pulls both figures up to par. What it cannot
      fake is shape: bridging two separate blobs across a real (if narrow) gap leaves a concave
      waist between them, so the filled area covers noticeably less of its own convex hull than a
      single chunky polygon does. Measured on ``ogps-8620``: the three real polygons (component
      density 0.36-0.57) solidity 0.786-0.893, and even the rejected purple fragment (component
      density 0.15, already excluded above) solidity 0.904; the bridged fixture false positive
      0.598. 0.70 sits with comfortable margin on every side of that gap.

    ``hatch_close_mm`` is a paper distance, converted to pixels via *dpi* like every sibling
    geometric tunable in this project (never a hardcoded pixel count) -- calibration point:
    25px closed this map's hatch cleanly at 265.991 dpi, i.e. ``25 * 25.4 / 265.991 ~= 2.39mm``.
    """
    oob = terrain_label(TerrainClass.OUT_OF_BOUNDS)
    raw = labels == oob
    if not raw.any():
        return labels

    ksize = max(1, round(hatch_close_mm * dpi / 25.4))
    kernel = np.ones((ksize, ksize), np.uint8)
    closed = cv2.morphologyEx(raw.astype(np.uint8), cv2.MORPH_CLOSE, kernel) > 0

    contours, _ = cv2.findContours(
        closed.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return labels

    out = labels.copy()
    for contour in contours:
        filled = np.zeros(labels.shape[:2], dtype=np.uint8)
        cv2.drawContours(filled, [contour], -1, color=1, thickness=cv2.FILLED)
        filled_mask = filled > 0
        area = int(filled_mask.sum())
        if area == 0:
            continue
        density = float(np.count_nonzero(raw & filled_mask)) / area
        closed_fraction = float(np.count_nonzero(closed & filled_mask)) / area
        hull_area = cv2.contourArea(cv2.convexHull(contour))
        solidity = area / hull_area if hull_area > 0 else 0.0
        if (
            density >= min_density_fraction
            and closed_fraction >= min_closed_fraction
            and solidity >= min_solidity_fraction
        ):
            out[filled_mask] = oob
    return out


def _consolidate_banked_water(
    labels: np.ndarray, border_radius: int = 2, min_bank_fraction: float = 0.3
) -> np.ndarray:
    """Promote a whole connected water blob to ``water_uncrossable`` when its own boundary is
    substantially bank-lined (T101, F4).

    On a real scan, printed ``blue_70`` (``water_shallow``) and ``blue_100`` (``water_uncrossable``)
    ink can land close enough together in CIELAB -- and close enough to real halftone/JPEG noise --
    that :func:`classify_labels`'s per-pixel nearest-shade choice flips almost at random along a
    river's own width, fragmenting one continuous uncrossable body of water into thousands of tiny
    ``water_uncrossable`` islands inside an otherwise ``water_shallow`` (passable) blob: measured on
    ``data/maps/ogps-6802_4a769f64b455f9b4675552284c3681b1``, individual core-fill pixels of the
    river sit only 5-10 CIELAB units from *both* shades (the two shades are themselves just ~14
    apart), and the river's largest single ``water_uncrossable`` fragment was 341 px against a
    river thousands of pixels long -- nowhere near enough to block a route.

    Rather than move the ``blue_70``/``blue_100`` decision boundary itself (which this same scan's
    other, legitimately shallow, hatched/screened water shows would just as readily swallow a real
    ``water_shallow`` feature -- its core ink sits in the very same ambiguous neighbourhood), this
    uses the one signal ``config/default.toml`` already documents as what actually distinguishes
    them on a real map: ``water_uncrossable``'s own note that it is "emphasised by a black bank
    line". For each connected component of ``water_shallow | water_uncrossable``, if at least
    ``min_bank_fraction`` of *its own boundary ring* (not its interior) lies within
    ``border_radius`` px of ``black_100``-shaded ink (the ``road`` label, per the shared-shade
    convention above) -- i.e. the component is actually bank-lined, not just incidentally near a
    stray bit of black ink -- the whole component becomes ``water_uncrossable``; every pixel of a
    component that fails this check keeps whatever :func:`classify_labels` already gave it. A
    hatched/screened shallow pond or marsh with no such border is untouched by construction: its
    boundary simply has no adjacent bank-line ink to measure.

    Vectorised with :func:`scipy.ndimage.sum` keyed by component id rather than a Python loop over
    components -- a real scan can fragment into several thousand of them, and a per-component
    Python loop measured ~120s on one 3107x3278 scan alone versus ~0.4s vectorised.
    """
    wu = terrain_label(TerrainClass.WATER_UNCROSSABLE)
    ws = terrain_label(TerrainClass.WATER_SHALLOW)
    road = terrain_label(TerrainClass.ROAD)

    water = (labels == wu) | (labels == ws)
    if not water.any():
        return labels

    eroded = cv2.erode(water.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    boundary = water & ~eroded

    ksize = 2 * border_radius + 1
    bank_nearby = (
        cv2.dilate((labels == road).astype(np.uint8), np.ones((ksize, ksize), np.uint8)) > 0
    )

    components, n = ndimage.label(water, structure=np.ones((3, 3)))
    if n == 0:
        return labels

    index = np.arange(1, n + 1)
    boundary_count = ndimage.sum(boundary, components, index=index)
    banked_count = ndimage.sum(boundary & bank_nearby, components, index=index)
    fraction = np.divide(
        banked_count, boundary_count, out=np.zeros_like(banked_count), where=boundary_count > 0
    )

    promote = np.zeros(n + 1, dtype=bool)
    promote[index] = fraction >= min_bank_fraction

    out = labels.copy()
    out[promote[components] & (labels == ws)] = wu
    return out


def classify_palette(
    image: np.ndarray, config: AppConfig | None = None, dpi: float | None = None
) -> np.ndarray:
    """Classify *image* into ISOM terrain classes and fill in ``unknown`` (T013, F4).

    :func:`classify_labels`, then :func:`_close_out_of_bounds_regions` (T109) to close a hatched
    ``out_of_bounds`` polygon's whole interior before either of the next two steps can leak part of
    it through as real terrain, then :func:`_consolidate_banked_water` (T101) to make a genuinely
    bank-lined water body solidly ``water_uncrossable``, then :func:`fill_unknown` using
    ``config.palette.unknown_fill_radius``. Returns an ``(H, W)`` uint8 array indexed by
    ``TERRAIN_ORDER`` — directly usable as :class:`rogaine.models.TerrainMap`'s ``labels``.

    *dpi* sizes the out-of-bounds closure's morphological kernel to the hatch's own line pitch on
    paper (see :func:`_close_out_of_bounds_regions`); it defaults to ``config.map.default_dpi``
    when the caller has no better estimate, the same fallback :func:`~rogaine.io.raster.resolve_dpi`
    uses when a scan carries no DPI metadata of its own.
    """
    cfg = config or default_config()
    labels = classify_labels(image, cfg)
    labels = _close_out_of_bounds_regions(labels, dpi if dpi is not None else cfg.map.default_dpi)
    labels = _consolidate_banked_water(labels)
    return fill_unknown(labels, cfg.palette.unknown_fill_radius)
