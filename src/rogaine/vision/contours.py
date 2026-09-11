"""Contour density and the slope factor derived from it (T015, F6, ADR-006).

The article this project is modelled on penalises a route for crossing contour lines -- a slope
proxy: dense contours mean steep ground. Reconstructing an actual DEM from contour lines (line
tracing, height assignment, interpolation) is a project of its own and fragile on a raster where
contours are broken by overprinted symbols and text (ADR-006's own wording). This module takes the
cheaper path the ADR chose instead: extract the brown ``contour`` mask that
:mod:`rogaine.vision.palette` already produces, blur it into a local density field, and derive a
multiplicative speed penalty from that density directly -- no elevation, no line tracing.

**Why a Gaussian blur.** A single contour crossing is a thin, discrete event; what actually
correlates with slope is how *many* of them sit near a given point, i.e. local line spacing.
Blurring the binary contour mask with a Gaussian of standard deviation
``config.slope.density_sigma_px(dpi)`` turns a sparse set of thin lines into a smooth, local
estimate of that spacing: tightly packed contours (a steep flank) blur into a high plateau, widely
spaced ones stay low. The sigma is configured in millimetres on paper and converted to pixels via
the map's own DPI -- the same convention every other geometric tunable in this config follows
(``LinearSettings.nominal_width_px``, ``DetectorSettings.circle_radius_px``), never a hardcoded
pixel constant. It is a tunable, not a physical constant, because it trades off two failure
modes -- too small and density is noisy pixel-to-pixel (an artefact of stroke width, not slope);
too large and a genuinely steep, narrow feature gets smeared into its flat surroundings.

**Direction-blindness (ADR-006, F6).** :func:`k_slope` is a function of local contour density
alone -- it never receives a "from" pixel and a "to" pixel, only the density field, so by
construction it cannot tell uphill from downhill: a leg between two points costs the same in both
directions. This is a known, accepted limitation (SPEC risk 3, ADR-006's own "Consequences"), not an
oversight -- ADR-006 records it as a limitation to be stated in the README and the route output once
those exist (M5/M6), rather than hidden.
"""

from __future__ import annotations

import cv2
import numpy as np

from rogaine.config import AppConfig, default_config
from rogaine.models import TerrainClass, terrain_label


def contour_mask(labels: np.ndarray) -> np.ndarray:
    """Pixels the palette classifier called ``contour`` (T013's ``brown_100`` shade).

    *labels* is an ``(H, W)`` uint8 array as produced by
    :func:`rogaine.vision.palette.classify_palette` (or
    :func:`rogaine.vision.palette.classify_labels`), indexed by
    :data:`rogaine.models.TERRAIN_ORDER`. Returns a boolean array of the same shape.
    """
    if labels.ndim != 2:
        raise ValueError(f"expected an (H, W) labels array, got shape {labels.shape}")
    if labels.dtype != np.uint8:
        raise ValueError(f"expected uint8 labels, got {labels.dtype}")
    return labels == terrain_label(TerrainClass.CONTOUR)


def contour_density(labels: np.ndarray, dpi: float, config: AppConfig | None = None) -> np.ndarray:
    """Local contour density: a Gaussian-blurred version of :func:`contour_mask`, clipped to
    ``[0, 1]``.

    Directly usable as :class:`rogaine.models.TerrainMap`'s ``contour_density`` field. *dpi* is the
    raster's scan resolution -- the same value :func:`rogaine.vision.linear.extract_linear_features`
    takes explicitly, for the same reason: the blur radius is a fixed size *on paper*
    (``config.slope.density_sigma_mm``), not a hardcoded pixel count.

    **Range.** ``cv2.GaussianBlur`` normalises its kernel to sum to 1 (``cv2.getGaussianKernel``
    always returns non-negative weights summing to 1), so mathematically every output pixel is a
    convex combination of the input 0/1 values and is guaranteed to land in ``[0, 1]`` -- border
    reflection (the default ``BORDER_REFLECT_101``) only ever reflects existing 0/1 pixels, it
    never invents a value outside that range either. In practice, though, floating-point summation
    of many small kernel weights does not associate exactly: blurring an all-ones ``float32`` array
    (verified empirically) comes back as ``1.0000001``, a few ULPs over 1.0. The ``np.clip`` below
    is therefore not defensive boilerplate -- it corrects a real, observed rounding overshoot, not
    a hypothetical one. On a real map density never gets close to 1.0 in the first place: gaps
    between contour lines are most of any real area (see ``config/default.toml``'s own comment).
    """
    if not dpi > 0:
        raise ValueError(f"dpi must be positive, got {dpi}")

    mask = contour_mask(labels)  # also validates labels' shape/dtype
    if not mask.any():
        return np.zeros(labels.shape, dtype=np.float32)

    cfg = config or default_config()
    sigma_px = cfg.slope.density_sigma_px(dpi)
    # `cv2.GaussianBlur` on a float32 input returns float32, so clipping in place (rather than
    # `np.clip(...).astype(np.float32)`) avoids a third full-size temporary on a large raster.
    blurred = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), sigma_px)
    return np.clip(blurred, 0.0, 1.0, out=blurred)


def k_slope(density: np.ndarray, config: AppConfig | None = None) -> np.ndarray:
    """The multiplicative slope factor T030's cost field multiplies into ``k_terrain``.

    ``config/default.toml``'s own comment states the model: "speed is divided by
    ``(1 + penalty * density ** density_exponent)``". ``k_slope`` is the reciprocal of that
    divisor, so that ``t = mpp / (v_base * k_terrain * k_slope)`` (T030) applies it by
    multiplication like every other factor in the cost field, rather than needing a separate
    division step there. At ``density = 0`` this is exactly 1.0 (no penalty) regardless of
    ``density_exponent``; it decreases monotonically as ``density`` rises. ``1 / (1 + penalty)`` is
    the theoretical floor, reached only at ``density = 1.0`` -- wall-to-wall contour ink -- which
    does not happen on a real map: gaps between contour lines are most of any real area, so a map's
    actual steepest terrain sits well short of that floor (see ``config/default.toml``'s own
    comment for a measured range).

    **Convex by default (T095, ADR-029).** ``density_exponent > 1.0`` (the shipped default is
    ``2.0``) makes the divisor grow convexly with density rather than linearly: since
    ``density ** density_exponent <= density`` everywhere on ``[0, 1]``, a *sparse* contour
    crossing costs the same or less than the original linear formula would, while a *dense* one
    costs disproportionately more -- the literature's own "2-storey vs 10-storey climb" framing
    (Rule 6), where a small climb barely registers but a big one costs far more than proportionally.
    ``density_exponent = 1.0`` recovers the original linear formula exactly.

    **Direction-blind by construction (ADR-006, F6).** The signature takes only a density field --
    no "from" pixel, no "to" pixel, no travel direction -- so this function has no way of knowing
    whether a route crosses dense contours going uphill or downhill; the same density value always
    produces the same factor, so a leg costs the same in both directions. This is a deliberate,
    accepted limitation (SPEC risk 3), not an omission: telling the directions apart would need
    actual elevation, which is exactly what ADR-006 chose not to reconstruct.
    """
    if density.ndim != 2:
        raise ValueError(f"expected an (H, W) density array, got shape {density.shape}")
    if not np.issubdtype(density.dtype, np.floating):
        raise ValueError(f"expected a floating density array, got {density.dtype}")
    if density.size and (density.min() < 0.0 or density.max() > 1.0):
        raise ValueError(f"density must be in [0, 1], got [{density.min()}, {density.max()}]")

    cfg = config or default_config()
    return (1.0 / (1.0 + cfg.slope.penalty * density**cfg.slope.density_exponent)).astype(
        np.float32
    )
