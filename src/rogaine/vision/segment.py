"""Segmentation orchestration and the `terrain.npz` round-trip (T016, SPEC F4-F6, F19).

`vision/normalize.py`, `vision/palette.py`, `vision/linear.py` and `vision/contours.py` each do one
job and take their own `dpi`/`config` explicitly (T012-T015); nothing before this module chains them
end to end into the :class:`~rogaine.models.TerrainMap` that T030's cost field actually consumes.
:func:`segment` is that chain, in the one order that makes each stage's assumptions hold:
:func:`~rogaine.vision.normalize.normalize` runs first (its own docstring: white balance before
illumination flattening preserves the *corrected* channel ratio, not the tinted one);
:func:`~rogaine.vision.palette.classify_palette` needs that normalised image
(:func:`~rogaine.vision.palette.classify_labels`'s own docstring: "*image* must already be
normalised RGB"); :func:`~rogaine.vision.linear.extract_linear_features` needs
``classify_palette``'s shared `road` placeholder to exist before it can split it into
`road`/`vehicle_track`/`footpath`/`unknown`; :func:`~rogaine.vision.contours.contour_density` reads
whatever `contour`-labelled pixels remain, which the road split never touches (linear features only
ever rewrite pixels the palette called `road`) -- running it last simply matches the pipeline order
in `docs/PLAN.md`'s architecture diagram.

`dpi` and `meters_per_pixel` are both required here, independently, because neither derives from
the other: `dpi` is scan resolution, needed to convert this config's millimetre-based tunables
(stroke widths, blur sigma) into pixels for `extract_linear_features` and `contour_density`;
`meters_per_pixel` is ground distance per pixel, computed either from `dpi` + printed scale or from
two-point calibration that never touches `dpi` at all (`io/scale.py`).
:class:`~rogaine.models.MapContext` (T011) deliberately carries `meters_per_pixel` only, never
`dpi` (see `io/raster.py`'s `load_map_context`), so a caller building a `TerrainMap` from a loaded
map must resolve `dpi` itself (`io/raster.py`'s `resolve_dpi`) and pass both here rather than
expect one from the other.

Also home to the `terrain.npz` round-trip (:func:`save_terrain_map` / :func:`load_terrain_map`)
and :func:`iou_report`, a per-class IoU helper promoted from the ad hoc version every T013-T015
fixture test already wrote inline (e.g. `tests/unit/vision/test_linear.py`'s
`TestSubClassAccuracyOnFixture`), so `tools/palette_report.py` (T017) and any future caller share
one implementation instead of a fourth copy.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from rogaine.config import AppConfig, default_config
from rogaine.models import TERRAIN_ORDER, TerrainClass, TerrainMap, terrain_label
from rogaine.vision.contours import contour_density
from rogaine.vision.linear import extract_linear_features
from rogaine.vision.normalize import normalize
from rogaine.vision.palette import classify_palette


def segment(
    image: np.ndarray,
    dpi: float,
    meters_per_pixel: float,
    config: AppConfig | None = None,
) -> TerrainMap:
    """Run the full pipeline -- normalize, classify, split roads, measure contour density.

    *image* is an ``(H, W, 3)`` uint8 RGB raster (validation of that shape happens downstream, in
    :func:`~rogaine.vision.palette.classify_labels`, the first stage that actually requires it).
    *dpi* is the raster's scan resolution and *meters_per_pixel* is ground distance per pixel; see
    the module docstring for why both are required and neither substitutes for the other. Returns a
    :class:`~rogaine.models.TerrainMap` ready for `terrain.npz` (:func:`save_terrain_map`) or a
    preview (:mod:`rogaine.render.preview`).
    """
    if not dpi > 0:
        raise ValueError(f"dpi must be positive, got {dpi}")

    cfg = config or default_config()
    normalized = normalize(image)
    labels = classify_palette(normalized, cfg)
    labels = extract_linear_features(labels, dpi, cfg)
    density = contour_density(labels, dpi, cfg)
    return TerrainMap(labels=labels, contour_density=density, meters_per_pixel=meters_per_pixel)


def save_terrain_map(path: Path, terrain_map: TerrainMap) -> None:
    """Write *terrain_map* to *path* as a compressed ``.npz`` (SPEC F19's `terrain.npz`).

    ``np.savez_compressed`` -- these are large, sparse-ish label rasters, worth the compression.
    `labels` is stored exactly as `TerrainMap` already holds it (uint8): the module comment on
    :data:`rogaine.models.TERRAIN_ORDER` states the integer values are baked into saved
    `terrain.npz` files, so this function must never re-encode them.
    """
    np.savez_compressed(
        path,
        labels=terrain_map.labels,
        contour_density=terrain_map.contour_density,
        meters_per_pixel=terrain_map.meters_per_pixel,
    )


def load_terrain_map(path: Path) -> TerrainMap:
    """Inverse of :func:`save_terrain_map`.

    ``np.load`` hands back an ``NpzFile``, and the scalar `meters_per_pixel` comes back as a 0-D
    array (``np.savez`` wraps every array it stores, scalars included) -- ``.item()`` unwraps it to
    a plain Python ``float``, matching :class:`~rogaine.models.TerrainMap`'s field type exactly.
    """
    with np.load(path) as npz:
        return TerrainMap(
            labels=npz["labels"],
            contour_density=npz["contour_density"],
            meters_per_pixel=float(npz["meters_per_pixel"].item()),
        )


def iou_report(
    pred_labels: np.ndarray,
    truth_labels: np.ndarray,
    *,
    sampleable: np.ndarray | None = None,
) -> dict[TerrainClass, float]:
    """Per-class IoU between two label rasters, one entry per :data:`~rogaine.models.TERRAIN_ORDER`
    class.

    Promotes the pattern every T013-T015 fixture test already wrote by hand (e.g.
    `tests/unit/vision/test_linear.py`'s `TestSubClassAccuracyOnFixture`,
    `tests/unit/vision/test_palette.py`'s `_iou`) into one shared function for
    `tools/palette_report.py` (T017) and any other caller.

    Reports every class in `TERRAIN_ORDER`, not only the ones present in *truth_labels*: a class
    absent from both prediction and truth is a legitimate "nothing to disagree about" result (see
    the vacuous-agreement rule below); inferring the class list from *truth_labels* alone would
    instead silently drop information about a class the predictor hallucinated pixels for.

    *sampleable*, if given, is a boolean mask the same shape as *pred_labels*/*truth_labels*: only
    ``True`` pixels count towards any class's IoU. This project's existing fixture tests already
    use this to exclude pixels whose ground truth is not what a classifier sees there --
    overprinted contour ink, black map-text/point-symbol noise, out-of-bounds hatching (see
    `test_palette.py`'s `TestPaletteIoUAgainstFixture` module docstring for why each is excluded).

    Vacuous agreement: a class with an empty union (absent from both rasters, after masking)
    scores ``1.0``, not ``NaN`` or a division error -- the same convention `test_palette.py`'s
    `_iou` helper uses.
    """
    if pred_labels.shape != truth_labels.shape:
        raise ValueError(
            f"pred_labels and truth_labels must have the same shape, "
            f"got {pred_labels.shape} and {truth_labels.shape}"
        )
    mask = sampleable if sampleable is not None else np.ones(pred_labels.shape, dtype=bool)

    report: dict[TerrainClass, float] = {}
    for cls in TERRAIN_ORDER:
        lbl = terrain_label(cls)
        pred_mask = (pred_labels == lbl) & mask
        truth_mask = (truth_labels == lbl) & mask
        union = pred_mask | truth_mask
        iou = 1.0 if not union.any() else float((pred_mask & truth_mask).sum() / union.sum())
        report[cls] = iou
    return report


def format_iou_report(report: dict[TerrainClass, float]) -> str:
    """One line per class, in *report*'s own order, e.g. ``open_land: 0.9821``.

    Pure string formatting -- the DoD's "printed per class" is a caller's job (T050's CLI calls
    ``print()`` on this), not this function's.
    """
    return "\n".join(f"{cls.value}: {iou:.4f}" for cls, iou in report.items())
