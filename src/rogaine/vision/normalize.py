"""Colour normalisation: grey-world white balance plus illumination flattening (T012).

Real scans carry two lighting errors the palette classifier (T013) cannot see through on its
own: a global colour cast (a scanner lamp, or a phone camera's auto white balance) and an
uneven brightness across the page (vignetting, or a flatbed lit unevenly from one side). This
module corrects both before classification. Neither correction references any specific
palette — they only assume a real map is not one colour, and that its illumination varies
smoothly rather than in hard steps.
"""

from __future__ import annotations

import cv2
import numpy as np


def white_balance_grey_world(image: np.ndarray) -> np.ndarray:
    """Grey-world white balance: scale each channel so the three channel means agree.

    Assumes the *average* colour of a real map, over its whole area, is close to neutral grey —
    true for an ISOM map, whose area is mostly white/yellow/green ground cover in no single
    dominant hue, false for a swatch of one colour. A uniform colour cast multiplies each
    channel by a constant, which is exactly what dividing by the channel means undoes.
    """
    img = image.astype(np.float32)
    # dtype=float64 for the reduction only: a plain float32 accumulator loses several units of
    # precision summing millions of pixels (mantissa exhaustion at a ~1e8-1e9 running total),
    # which is the same order of magnitude as the cast this function exists to correct.
    channel_means = img.reshape(-1, 3).mean(axis=0, dtype=np.float64)
    gray = float(channel_means.mean())
    scale = (gray / np.clip(channel_means, 1.0, None)).astype(np.float32)
    balanced = img * scale
    return np.clip(balanced, 0, 255).astype(np.uint8)


def flatten_illumination(image: np.ndarray, *, sigma_frac: float = 0.1) -> np.ndarray:
    """Divide out large-scale brightness variation (vignetting, uneven scan lighting).

    Estimates the illumination field as a heavily blurred copy of the image's luminance — wide
    enough to smear out every terrain feature but not the slow brightness gradient underneath —
    then rescales each pixel by the ratio between the field's own mean and its local value.
    *sigma_frac* is the blur radius as a fraction of the image's longer side, so the correction
    scales with map size the way no real ISOM feature would.
    """
    img = image.astype(np.float32)
    luminance = img.mean(axis=2)  # 3-term mean per pixel: no precision concern here
    sigma = max(image.shape[0], image.shape[1]) * sigma_frac
    illumination = cv2.GaussianBlur(luminance, (0, 0), sigma)
    illumination = np.clip(illumination, 1.0, None)
    # dtype=float64 for the same reason as white_balance_grey_world's channel means.
    target = illumination.mean(dtype=np.float64)
    correction = (target / illumination).astype(np.float32)
    flattened = img * correction[..., None]
    return np.clip(flattened, 0, 255).astype(np.uint8)


def normalize(image: np.ndarray, *, illumination_sigma_frac: float = 0.1) -> np.ndarray:
    """Grey-world white balance, then illumination flattening (T012).

    White balance runs first: it removes the *global* per-channel cast, so the ratio between
    channels that illumination flattening preserves (it scales R, G and B together, by the same
    per-pixel factor) is already the corrected one rather than the tinted one.
    """
    balanced = white_balance_grey_world(image)
    return flatten_illumination(balanced, sigma_frac=illumination_sigma_frac)
