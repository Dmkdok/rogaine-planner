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

:func:`reclassify_grid_ink` (T074, F20, ADR-012) runs between those last two: it must see
`classify_palette`'s water classes before anything downstream treats them as real water.
`extract_linear_features` only ever rewrites pixels the palette called `road`, never `road`'s own
water-class siblings, so the two passes are independent in practice -- but this is the order
ADR-012 states.

Review finding M-4 (I6 milestone review): this docstring used to promise `reclassify_grid_ink` the
palette's classification "untouched by any later stage" -- no longer true. `classify_palette`
itself is not just `classify_labels` + `fill_unknown`: T101 (F4, `docs/TASKS.md`) inserted
:func:`~rogaine.vision.palette._consolidate_banked_water` between them, so what
`reclassify_grid_ink` actually sees already has bank-lined water blobs bulk-promoted to
`water_uncrossable`. This still doesn't collide with `reclassify_grid_ink`'s own column/row
water-fraction test, which sums across *both* water classes and so cannot see a
`water_shallow -> water_uncrossable` promotion within that sum. What it can collide with is
`_consolidate_banked_water`'s own whole-component promotion: a real shallow watercourse that is
8-connected to a genuinely bank-lined body (e.g. a ditch draining into a river) is promoted along
with it, since the two share one connected component. This is outside T101's own diagnosed case
(`ogps-6802`'s marsh, a disjoint blob) and not yet measured against a real instance of that
specific shape -- a named, not yet corpus-tested, follow-up risk rather than a fix landed here.

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
    labels = classify_palette(normalized, cfg, dpi)
    labels = reclassify_grid_ink(labels, dpi, cfg)
    labels = extract_linear_features(labels, dpi, cfg)
    density = contour_density(labels, dpi, cfg)
    return TerrainMap(labels=labels, contour_density=density, meters_per_pixel=meters_per_pixel)


def _true_runs(flags: np.ndarray) -> list[tuple[int, int]]:
    """Inclusive ``(start, end)`` index pairs of every contiguous ``True`` run in a 1-D boolean
    array, vectorised (no Python loop over indices).
    """
    padded = np.concatenate(([False], flags, [False]))
    edges = np.diff(padded.astype(np.int8))
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1) - 1
    return list(zip(starts.tolist(), ends.tolist(), strict=True))


def reclassify_grid_ink(
    labels: np.ndarray, dpi: float, config: AppConfig | None = None
) -> np.ndarray:
    """Reclassify grid/magnetic-north/border-rule ink misread as water to `unknown` (T074, F20,
    ADR-012).

    Real orienteering maps print thin solid lines (a UTM/magnetic-north grid, the map's own border
    rule) that can sit close enough to the water reference colour to be classified
    `water_shallow`/`water_uncrossable` (confirmed on a real scan, `docs/STATUS.md`, I1). Left
    alone, a full-height column of `speed_factor 0.0` slices the routable graph into disconnected
    strips.

    Rather than a per-connected-component shape test (`vision/linear.py`'s precedent),
    this looks at whole-column and whole-row coverage: for each column, what fraction of its
    pixels (over the image's full height) are one of the two water classes, and symmetrically for
    each row over the full width. A real grid/border line is solid enough, and near enough the full
    height or width, to spike this fraction (measured 0.338-0.898 across 9 columns of the real
    scan named above); real water bodies never come close on the synthetic fixture used to floor
    this pipeline's other tests (measured max 0.145) -- see `config/default.toml`'s `[grid]`
    section for the exact numbers this threshold is picked from. Two narrower checks then reject a
    run that clears the fraction but is not actually line-shaped: `GridSettings.max_line_width_mm`
    rejects a run *wider* than any real printed line (a lake or marsh large enough to clear the
    fraction threshold is, at any real map scale, far wider than that); `min_elongation_ratio`
    independently requires the run to be many times longer (the image's own height or width) than
    it is wide -- `max_line_width_mm` alone is an *absolute* size, so on a small or heavily-cropped
    raster it stops discriminating a line from a squarish blob (see `GridSettings`'s own docstring
    for the measured numbers). Together these are what keep a compact water body's own columns from
    being caught by the fraction check alone (the non-negotiable this task's own DoD states).

    Only pixels the palette actually called `water_shallow`/`water_uncrossable` are ever touched --
    a column or row flagged as a line does not drag its non-water neighbours along, the same
    "rejected components become `unknown`, not the whole bounding box" discipline
    `extract_linear_features` already follows.

    The column pass and the row pass both test against the *same* original water mask, not against
    each other's output -- deliberately: reading an already-partially-reclassified array would make
    the result depend on which pass happens to run first, for no benefit (a pixel either passage
    would flag is flagged either way; nothing here depends on running both to convergence).
    """
    if labels.ndim != 2:
        raise ValueError(f"expected an (H, W) labels array, got shape {labels.shape}")
    if labels.dtype != np.uint8:
        raise ValueError(f"expected uint8 labels, got {labels.dtype}")
    if not dpi > 0:
        raise ValueError(f"dpi must be positive, got {dpi}")

    cfg = config or default_config()
    grid = cfg.grid

    water_lbls = (
        terrain_label(TerrainClass.WATER_SHALLOW),
        terrain_label(TerrainClass.WATER_UNCROSSABLE),
    )
    mask = np.isin(labels, water_lbls)
    out = labels.copy()
    if not mask.any():
        return out

    unknown_lbl = terrain_label(TerrainClass.UNKNOWN)
    height, width = mask.shape
    max_width_px = grid.max_line_width_px(dpi)

    col_frac = mask.sum(axis=0) / height
    for start, end in _true_runs(col_frac >= grid.span_fraction_min):
        run_width = end - start + 1
        if run_width <= max_width_px and height / run_width >= grid.min_elongation_ratio:
            band = mask[:, start : end + 1]
            out[:, start : end + 1][band] = unknown_lbl

    row_frac = mask.sum(axis=1) / width
    for start, end in _true_runs(row_frac >= grid.span_fraction_min):
        run_width = end - start + 1
        if run_width <= max_width_px and width / run_width >= grid.min_elongation_ratio:
            band = mask[start : end + 1, :]
            out[start : end + 1, :][band] = unknown_lbl

    return out


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
