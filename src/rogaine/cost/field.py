"""Per-pixel travel-time cost field (T030, F10).

``t = mpp / (v_base * k_terrain * k_slope * k_proximity)`` per pixel: ``mpp`` is
``TerrainMap.meters_per_pixel``, ``v_base`` is the caller's ``base_speed_mps`` (a per-run
parameter -- see ``RunConfig.base_speed_mps`` -- passed explicitly rather than read from
``AppConfig``, since the same terrain classification is reused across a runner's different
attempts at different speeds), ``k_terrain`` is ``config.speed_factors()`` gathered by
``TerrainMap.labels``, ``k_slope`` is :func:`rogaine.vision.contours.k_slope` applied to
``TerrainMap.contour_density``, and ``k_proximity`` is
:func:`rogaine.cost.proximity.k_proximity` (T095, ADR-029) -- a distance-decay speed bonus near
any linear feature (``road``/``vehicle_track``/``footpath``), off by default (see its own module
docstring). This module does not recompute any of the three factors, only combines them.

**Impassable pixels store ``+inf``, never ``nan``.** ``TerrainSpec`` (``config.py``) enforces
``speed_factor == 0.0`` for every impassable class, so the raw formula divides by zero exactly
where ``passable`` is ``False``. ``mpp`` is always a positive finite float, ``k_slope`` is always
strictly positive for a valid, finite, non-negative ``penalty`` (``SlopeSettings.penalty`` is
``ge=0.0``; ``k_slope`` itself requires ``density`` in ``[0, 1]``, so
``1 + penalty * density ** density_exponent >= 1`` always), and ``k_proximity`` is always ``>= 1.0``
by construction (``1.0`` plus a non-negative bonus term, ``ProximitySettings.bonus_magnitude`` is
``ge=0.0``) -- so the only factor that can ever be zero is ``k_terrain``, meaning the division is
always a positive number over zero, i.e. ``+inf``, never the ``0 / 0`` that would produce ``nan``.
``CostField.__post_init__`` only requires *passable* pixels to carry a finite cost, so ``+inf`` at
impassable pixels satisfies that contract by construction. SPEC F10's "impassable classes are
excluded from the graph" is T031's job (it reads ``passable``, not this numeric value, to decide
graph membership); storing ``+inf`` here rather than an arbitrary finite placeholder means any
future code that touches these cells without checking ``passable`` first fails loudly
(``np.isfinite``, comparisons, arithmetic warnings) instead of silently computing a
plausible-looking wrong answer. The division itself never executes at impassable cells at all
(``np.divide(..., where=passable)`` on a pre-filled ``+inf`` array), so this is a deliberate fill
value, not an uncaught floating-point exception.

**``contour`` is passable with ``speed_factor == 0.0`` by design, not by omission.**
``config/default.toml``'s own comment on the ``contour`` terrain row: "not an area class: contours
only feed the slope penalty (T015), never the speed table" -- and ``TerrainSpec``'s validator
carves out exactly this one exception to its own "passable implies positive speed_factor" rule.
Applying the raw formula literally at those pixels would divide by zero at a *passable* cell and
raise inside ``CostField.__post_init__`` on any real map (contour ink is common, not an edge case).
Any pixel that is ``passable`` yet whose gathered ``k_terrain`` is ``0.0`` can, by that same
validator, only be this contour-ink case -- no other passable class has a zero speed factor -- so
this module neutralises ``k_terrain`` to ``1.0`` there: no extra terrain penalty from the line-ink
pixel itself, leaving only ``k_slope``'s density-driven penalty, exactly as the config comment
prescribes.
"""

from __future__ import annotations

import numpy as np

from rogaine.config import AppConfig, default_config
from rogaine.cost.proximity import k_proximity
from rogaine.models import CostField, TerrainMap
from rogaine.vision.contours import k_slope


def compute_cost_field(
    terrain: TerrainMap,
    base_speed_mps: float,
    config: AppConfig | None = None,
) -> CostField:
    """Build the per-pixel travel-time field ``t = mpp / (v_base * k_terrain * k_slope *
    k_proximity)`` (F10).

    *base_speed_mps* is the runner's road speed for this run, taken as an explicit argument (not
    read from *config*) because it is a per-run choice, not an install-wide constant -- see the
    module docstring and ``RunConfig.base_speed_mps``.
    """
    if not base_speed_mps > 0.0:
        raise ValueError(f"base_speed_mps must be positive, got {base_speed_mps}")

    cfg = config or default_config()
    labels = terrain.labels

    k_terrain = cfg.speed_factors()[labels]  # fresh copy from fancy indexing -- safe to mutate
    passable = cfg.passability()[labels]
    slope_factor = k_slope(terrain.contour_density, cfg)
    proximity_factor = k_proximity(labels, terrain.meters_per_pixel, cfg)

    # See module docstring: the only passable class with a zero speed factor is `contour`, by
    # `TerrainSpec`'s own validator -- neutralise it instead of dividing by zero at a passable cell.
    passable_zero_speed = passable & (k_terrain == 0.0)
    if passable_zero_speed.any():
        k_terrain[passable_zero_speed] = np.float32(1.0)

    denom = np.float32(base_speed_mps) * k_terrain * slope_factor * proximity_factor
    seconds_per_pixel = np.full(labels.shape, np.float32(np.inf), dtype=np.float32)
    np.divide(
        np.float32(terrain.meters_per_pixel),
        denom,
        out=seconds_per_pixel,
        where=passable,
    )

    return CostField(
        seconds_per_pixel=seconds_per_pixel,
        passable=passable,
        meters_per_pixel=terrain.meters_per_pixel,
        base_speed_mps=base_speed_mps,
    )
