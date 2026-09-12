"""Linear-feature proximity bonus (T095, ADR-029, Rules 2+7).

The literature's "prefer running near a handrail" (Rule 2) and "prefer a leg with an obvious
catching feature beyond the control" (Rule 7) reduce to the same mechanism once translated into
this codebase's per-pixel cost model: reward proximity to any linear feature -- ``road``,
``vehicle_track``, ``footpath`` (:class:`rogaine.models.TerrainClass`, ADR-008's frozen contract) --
the same three classes :mod:`rogaine.vision.linear` (T014) extracts, folded straight into
``TerrainMap.labels`` by the palette classifier rather than kept as a separate mask. A control near
a linear feature gets the same treatment as any other nearby pixel for free: the bonus is a
property of the terrain grid, not of the route or the solve, so a leg ending near a trail is
naturally cheaper to approach without any control-specific "attack point" logic (this codebase has
none, see ADR-029's own deferred list).

**Mechanism.** A one-time Euclidean distance transform (``scipy.ndimage.distance_transform_edt``,
already an indirect dependency via ``cost/graph.py``'s ``scipy.sparse``) gives every pixel its
distance to the nearest linear-feature pixel, in pixels, converted to metres via the caller's
``meters_per_pixel``. That distance feeds an exponential decay,
``k_proximity = 1 + bonus_magnitude * exp(-distance_m / decay_distance_m)`` -- 1.0 in the limit of
large distance (no bonus), rising smoothly to ``1 + bonus_magnitude`` right on the feature itself,
with the classic e-folding shape (~37% of the peak bonus remains one ``decay_distance_m`` away).
:mod:`rogaine.cost.field` multiplies this factor into the same per-pixel rate ``k_terrain``/
``k_slope`` already occupy, so a higher ``k_proximity`` means a *lower* ``seconds_per_pixel`` -- a
genuine speed bonus, not a separate additive term that could break ``CostField``'s ``+inf``/finite
invariants (see ``cost/field.py``'s own module docstring).

**Enabled by default (``ProximitySettings.enabled``).** ADR-029 shipped this off, pending an owner
review of a before/after example on a real map (T095); the owner signed off 2026-09-12 and the
shipped default is now ``True`` (see ADR-029's amendment paragraph). When disabled -- still
available as an explicit override -- this returns an all-ones array with no distance transform
computed at all, so ``k_terrain * k_slope * 1.0`` in ``cost/field.py`` is bit-for-bit identical to
the pre-T095 formula.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import distance_transform_edt

from rogaine.config import AppConfig, default_config
from rogaine.models import TerrainClass, terrain_label

_LINEAR_CLASSES = (TerrainClass.ROAD, TerrainClass.VEHICLE_TRACK, TerrainClass.FOOTPATH)


def k_proximity(
    labels: np.ndarray, meters_per_pixel: float, config: AppConfig | None = None
) -> np.ndarray:
    """The multiplicative proximity-bonus factor :mod:`rogaine.cost.field` folds into its
    per-pixel rate.

    *labels* is ``TerrainMap.labels`` -- an ``(H, W)`` uint8 array indexed by
    :data:`rogaine.models.TERRAIN_ORDER` (same contract as
    :func:`rogaine.vision.contours.contour_mask`). Returns an ``(H, W)`` float32 array, always
    exactly ``1.0`` everywhere when ``config.proximity.enabled`` is ``False`` (an explicit
    override -- the shipped default is now ``True``, ADR-029's amendment) or when the map has no
    linear-feature pixels at all -- both cases skip the distance transform entirely rather than
    compute-and-discard it.
    """
    if labels.ndim != 2:
        raise ValueError(f"expected an (H, W) labels array, got shape {labels.shape}")
    if labels.dtype != np.uint8:
        raise ValueError(f"expected uint8 labels, got {labels.dtype}")
    if not meters_per_pixel > 0:
        raise ValueError(f"meters_per_pixel must be positive, got {meters_per_pixel}")

    cfg = config or default_config()
    settings = cfg.proximity
    if not settings.enabled:
        return np.ones(labels.shape, dtype=np.float32)

    mask = np.zeros(labels.shape, dtype=bool)
    for cls in _LINEAR_CLASSES:
        mask |= labels == terrain_label(cls)
    if not mask.any():
        return np.ones(labels.shape, dtype=np.float32)

    dist_px = distance_transform_edt(~mask)
    dist_m = dist_px.astype(np.float32) * np.float32(meters_per_pixel)
    decay = np.exp(-dist_m / np.float32(settings.decay_distance_m))
    return (1.0 + np.float32(settings.bonus_magnitude) * decay).astype(np.float32)
