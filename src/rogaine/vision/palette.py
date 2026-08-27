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
  trace it". A per-pixel nearest-colour classifier has no notion of "enclosed": it correctly
  classifies the hatch lines themselves and, just as correctly by its own lights, classifies the
  ground between them as whatever colour is actually there. That is this module working as
  specified, not a bug — filling the interior is a flood-fill/morphological step nobody in
  ``docs/TASKS.md`` M1 owns yet. The test measures and reports its IoU without asserting a floor.

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


def classify_palette(image: np.ndarray, config: AppConfig | None = None) -> np.ndarray:
    """Classify *image* into ISOM terrain classes and fill in ``unknown`` (T013, F4).

    :func:`classify_labels` then :func:`fill_unknown`, using ``config.palette.unknown_fill_radius``.
    Returns an ``(H, W)`` uint8 array indexed by ``TERRAIN_ORDER`` — directly usable as
    :class:`rogaine.models.TerrainMap`'s ``labels``.
    """
    cfg = config or default_config()
    labels = classify_labels(image, cfg)
    return fill_unknown(labels, cfg.palette.unknown_fill_radius)
