"""Colour normalisation (T012): grey-world white balance plus illumination flattening.

DoD: "a synthetically tinted and vignetted fixture classifies at least as well as the clean
one." T013 (the palette classifier) does not exist yet, so this is measured with a proxy — see
the docstring on ``TestNormalizeRecoversTheCleanRender`` for what it compares against and why.
"""

from __future__ import annotations

import numpy as np
from skimage.color import rgb2lab

from rogaine.models import TerrainClass, terrain_label
from rogaine.vision.normalize import flatten_illumination, normalize, white_balance_grey_world

# Every ISOM area class the fixture paints a substantial region of (line features and the hub
# markers are excluded — too little area per pixel to give a stable mean colour).
_AREA_CLASSES: tuple[TerrainClass, ...] = (
    TerrainClass.OPEN_LAND,
    TerrainClass.ROUGH_OPEN,
    TerrainClass.FOREST_RUNNABLE,
    TerrainClass.VEG_SLOW_RUN,
    TerrainClass.VEG_WALK,
    TerrainClass.VEG_FIGHT,
    TerrainClass.MARSH,
    TerrainClass.WATER_SHALLOW,
    TerrainClass.WATER_UNCROSSABLE,
    TerrainClass.BARE_ROCK,
    TerrainClass.PAVED_AREA,
)


class TestWhiteBalanceGreyWorld:
    def test_equalises_channel_means(self) -> None:
        # Large enough (480,000 px) that a naive float32 accumulator would lose several units of
        # precision summing it — this is a direct regression guard for that bug, not just a
        # description of the algorithm.
        rng = np.random.default_rng(0)
        base = rng.integers(40, 220, size=(600, 800, 3)).astype(np.uint8)
        cast = np.clip(base.astype(np.float32) * np.array([1.2, 1.0, 0.8]), 0, 255).astype(
            np.uint8
        )

        balanced = white_balance_grey_world(cast)

        means = balanced.reshape(-1, 3).astype(np.float64).mean(axis=0)
        assert means.max() - means.min() < 1.0

    def test_a_near_neutral_image_is_left_close_to_alone(self) -> None:
        rng = np.random.default_rng(1)
        flat = np.clip(
            120 + rng.integers(-10, 10, size=(40, 40, 3)), 0, 255
        ).astype(np.uint8)

        balanced = white_balance_grey_world(flat)

        assert abs(int(balanced.mean()) - int(flat.mean())) <= 2


class TestFlattenIllumination:
    def test_reduces_vignette_brightness_spread(self) -> None:
        rng = np.random.default_rng(2)
        base = np.clip(
            180 + rng.integers(-15, 15, size=(300, 400, 3)), 0, 255
        ).astype(np.uint8)
        h, w = base.shape[:2]
        yy, xx = np.mgrid[0:h, 0:w]
        r = np.sqrt(((yy - h / 2) / (h / 2)) ** 2 + ((xx - w / 2) / (w / 2)) ** 2)
        vignette = (1.0 - 0.4 * np.clip(r, 0, 1.0))[..., None]
        vignetted = np.clip(base.astype(np.float32) * vignette, 0, 255).astype(np.uint8)

        flattened = flatten_illumination(vignetted)

        std_before = vignetted.astype(np.float64).mean(axis=2).std()
        std_after = flattened.astype(np.float64).mean(axis=2).std()
        assert std_after < std_before * 0.4


def _tint_and_vignette(
    image: np.ndarray, *, tint: np.ndarray, vignette_strength: float
) -> np.ndarray:
    """A colour cast whose channel factors sum to 3 (shifts colour *ratio*, not overall
    brightness — grey-world cannot recover a brightness change, only a ratio one, which is a
    property of the technique, not a bug) plus a radial vignette that only ever darkens, never
    brightens (as a real lens/scan vignette does).
    """
    out = image.astype(np.float32) * tint
    h, w = image.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((yy - h / 2) / (h / 2)) ** 2 + ((xx - w / 2) / (w / 2)) ** 2)
    out *= (1.0 - vignette_strength * np.clip(r, 0, 1.0))[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


def _aggregate_distance_to_clean(
    lab_candidate: np.ndarray, lab_clean: np.ndarray, labels: np.ndarray, sampleable: np.ndarray
) -> tuple[float, int]:
    """Summed per-class Lab distance from *lab_candidate* to the clean render's own ground-truth
    region colours, and how many of the sampled classes are closer than the worst case.
    """
    total = 0.0
    n_classes = 0
    for cls in _AREA_CLASSES:
        mask = (labels == terrain_label(cls)) & sampleable
        assert mask.sum() > 500, f"fixture placed too little {cls} to sample reliably"
        ref = lab_clean[mask].mean(axis=0)
        total += float(np.linalg.norm(lab_candidate[mask].mean(axis=0) - ref))
        n_classes += 1
    return total, n_classes


class TestNormalizeRecoversTheCleanRender:
    """Proxy for "classifies at least as well as the clean one" (T013 does not exist yet).

    The T012 brief suggested comparing directly to the *true* CMYK-derived ISOM shade
    (``AppConfig.palette.srgb_of``). Measured empirically, that comparison is dominated by a
    confound unrelated to normalisation: ``RENDER_SRGB`` (what this fixture actually paints) is
    deliberately *not* the classifier's own CMYK-derived palette — the fixture module's own
    docstring says so, and ``docs/STATUS.md`` records the residual as "largest for green".
    Grey-world's estimate of "neutral" is thrown off by that same non-neutral colour mix: run it
    on the *zero-tint* clean render and every area class's distance to the true CMYK shade gets
    *worse*, not better (e.g. bare_rock 0.008 -> 4.0 Lab units, with no injected degradation at
    all) — that gap is T013's distance threshold to absorb, not something a colour-cast
    correction can close.

    So this compares against each region's own colour in the *clean render* instead — available
    independently from the fixture's ground-truth labels, computed once, before any degradation.
    That isolates exactly what T012 owns: does ``normalize()`` undo an injected tint and vignette
    well enough that the degraded map's regions read like the clean map's regions again?
    ``normalize()`` is never given the clean image, so this stays non-tautological.
    """

    def test_a_brightness_neutral_tint_and_mild_vignette(self, clean_synthetic_map) -> None:
        image = clean_synthetic_map.image
        labels = clean_synthetic_map.labels
        sampleable = ~clean_synthetic_map.contour_mask
        lab_clean = rgb2lab(image)

        degraded = _tint_and_vignette(
            image, tint=np.array([1.08, 1.0, 0.92], dtype=np.float32), vignette_strength=0.15
        )
        normalized = normalize(degraded)
        lab_degraded = rgb2lab(degraded)
        lab_normalized = rgb2lab(normalized)

        improved = 0
        for cls in _AREA_CLASSES:
            mask = (labels == terrain_label(cls)) & sampleable
            ref = lab_clean[mask].mean(axis=0)
            d_before = np.linalg.norm(lab_degraded[mask].mean(axis=0) - ref)
            d_after = np.linalg.norm(lab_normalized[mask].mean(axis=0) - ref)
            improved += d_after < d_before
        total_before, n = _aggregate_distance_to_clean(lab_degraded, lab_clean, labels, sampleable)
        total_after, _ = _aggregate_distance_to_clean(lab_normalized, lab_clean, labels, sampleable)

        # Most individual regions improve; a couple of low-contrast ones can land a near-tie —
        # the aggregate is what "classifies at least as well" actually needs.
        assert improved >= 7, f"only {improved}/{n} regions moved closer to the clean render"
        assert total_after < total_before * 0.90, (
            f"normalize() only took the aggregate Lab distance from {total_before:.1f} to "
            f"{total_after:.1f} (want at least a 10% reduction)"
        )

    def test_a_second_independent_degradation_also_improves(self, clean_synthetic_map) -> None:
        """A stronger, differently-shaped tint+vignette — guards against the first test's margin
        being a fluke of one parameter choice.
        """
        image = clean_synthetic_map.image
        labels = clean_synthetic_map.labels
        sampleable = ~clean_synthetic_map.contour_mask
        lab_clean = rgb2lab(image)

        degraded = _tint_and_vignette(
            image, tint=np.array([1.15, 0.95, 0.80], dtype=np.float32), vignette_strength=0.35
        )
        normalized = normalize(degraded)
        lab_degraded = rgb2lab(degraded)
        lab_normalized = rgb2lab(normalized)

        total_before, _ = _aggregate_distance_to_clean(lab_degraded, lab_clean, labels, sampleable)
        total_after, _ = _aggregate_distance_to_clean(lab_normalized, lab_clean, labels, sampleable)

        assert total_after < total_before * 0.90, (
            f"normalize() only took the aggregate Lab distance from {total_before:.1f} to "
            f"{total_after:.1f} (want at least a 10% reduction)"
        )
