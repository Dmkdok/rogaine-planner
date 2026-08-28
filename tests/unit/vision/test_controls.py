"""Control circle and start-triangle detection (T020): SPEC F7's HSV-mask + Hough pipeline.

DoD (F7): HSV purple mask plus HoughCircles with the radius range derived from `dpi` (ISOM 5-6 mm);
the start triangle (ISOM 701) is recognised at the hub; on the fixture recall at least 0.95,
precision at least 0.90, centre error at most a quarter radius. `docs/TASKS.md`'s T020 entry also
names a "finish double-circle" symbol -- `tests/fixtures/synth_map.py`'s `_place_controls` draws no
such second marker (this project's start = finish, one-hub convention,
`docs/BRIEF.md`/`docs/SPEC.md`), so there is nothing to test for it here.
"""

from __future__ import annotations

import numpy as np
import pytest

from fixtures.synth_map import CIRCLE_DIAMETER_MM
from rogaine.config import default_config
from rogaine.models import Control
from rogaine.vision.controls import detect_controls, purple_mask


def _match_detections(
    truth: list[Control], detections: list[Control], tol: float
) -> tuple[int, int, list[float]]:
    """Greedy nearest-neighbour one-to-one matching within *tol* px.

    Pairs are resolved in order of increasing distance, so a detection equidistant between two
    truth controls never steals the farther truth's match out from under the closer detection.
    Returns (matched truth count, matched detection count, per-match centre-error distances).
    """
    candidates = []
    for i, t in enumerate(truth):
        for j, d in enumerate(detections):
            dist = ((t.x - d.x) ** 2 + (t.y - d.y) ** 2) ** 0.5
            if dist <= tol:
                candidates.append((dist, i, j))
    candidates.sort(key=lambda c: c[0])

    matched_t: set[int] = set()
    matched_d: set[int] = set()
    errors: list[float] = []
    for dist, i, j in candidates:
        if i in matched_t or j in matched_d:
            continue
        matched_t.add(i)
        matched_d.add(j)
        errors.append(dist)
    return len(matched_t), len(matched_d), errors


def _circle_radius_px(dpi: float) -> float:
    """The fixture's own known control-circle radius, in pixels, at *dpi* (T020's DoD wording)."""
    return CIRCLE_DIAMETER_MM / 2.0 * (dpi / 25.4)


class TestPurpleMask:
    """Faster/more diagnosable than only testing through the full detector (T013's precedent)."""

    def test_isolates_a_known_purple_region(self) -> None:
        image = np.full((40, 40, 3), 255, dtype=np.uint8)
        purple = (170, 60, 150)  # tests/fixtures/synth_map.py's RENDER_SRGB["purple_100"]
        image[10:20, 10:20] = purple

        mask = purple_mask(image)

        assert mask[10:20, 10:20].all(), "the drawn purple square was not fully masked in"
        assert not mask[:10, :].any()
        assert not mask[20:, :].any()
        assert not mask[:, :10].any()
        assert not mask[:, 20:].any()

    def test_rejects_a_saturated_non_purple_colour(self) -> None:
        image = np.full((20, 20, 3), 255, dtype=np.uint8)
        image[:] = (200, 40, 40)  # saturated red -- nowhere near the configured purple hue range

        mask = purple_mask(image)

        assert not mask.any()


class TestInputValidation:
    def test_purple_mask_rejects_non_3channel_image(self) -> None:
        with pytest.raises(ValueError, match="H, W, 3"):
            purple_mask(np.zeros((4, 4), dtype=np.uint8))

    def test_purple_mask_rejects_non_uint8_image(self) -> None:
        with pytest.raises(ValueError, match="uint8"):
            purple_mask(np.zeros((4, 4, 3), dtype=np.float32))

    def test_detect_controls_rejects_non_3channel_image(self) -> None:
        with pytest.raises(ValueError, match="H, W, 3"):
            detect_controls(np.zeros((4, 4), dtype=np.uint8), 300.0)

    def test_detect_controls_rejects_non_uint8_image(self) -> None:
        with pytest.raises(ValueError, match="uint8"):
            detect_controls(np.zeros((4, 4, 3), dtype=np.float32), 300.0)

    def test_detect_controls_rejects_non_positive_dpi(self) -> None:
        image = np.zeros((4, 4, 3), dtype=np.uint8)
        with pytest.raises(ValueError, match="dpi"):
            detect_controls(image, 0.0)


class TestHubTriangleDetection:
    """SPEC F7: the ISOM 701 start triangle, recognised at the hub."""

    def test_hub_is_found_as_a_triangle_near_the_true_location(self, synthetic_map) -> None:
        sm = synthetic_map
        detections = detect_controls(sm.image, sm.dpi, default_config())

        hubs = [d for d in detections if d.is_hub]
        assert len(hubs) == 1, f"expected exactly one hub triangle, found {len(hubs)}"
        hub = hubs[0]
        assert hub.id == 0

        tol = _circle_radius_px(sm.dpi) / 4.0
        dist = ((hub.x - sm.hub.x) ** 2 + (hub.y - sm.hub.y) ** 2) ** 0.5
        assert dist <= tol, (
            f"hub detected at ({hub.x:.1f}, {hub.y:.1f}), "
            f"{dist:.2f}px from truth ({sm.hub.x:.1f}, {sm.hub.y:.1f}), tol={tol:.2f}px"
        )


class TestRecallPrecisionOnFixture:
    """SPEC F7's own numbers, measured against the standard (degraded) fixture."""

    def test_control_circles_meet_the_dod_floor(self, synthetic_map) -> None:
        sm = synthetic_map
        radius_px = _circle_radius_px(sm.dpi)
        centre_error_tol = radius_px / 4.0
        # Matching tolerance for pairing detections to truth is deliberately looser than the
        # centre-error floor itself (one full circle radius, not a quarter) -- otherwise a poorly
        # centred detector could never be caught by the separate centre-error assertion below, since
        # anything matched would already be within tolerance by construction.
        match_tol = radius_px

        detections = detect_controls(sm.image, sm.dpi, default_config())
        det_circles = [d for d in detections if not d.is_hub]
        truth_circles = [c for c in sm.controls if not c.is_hub]

        n_matched_truth, n_matched_det, errors = _match_detections(
            truth_circles, det_circles, match_tol
        )
        recall = n_matched_truth / len(truth_circles)
        precision = n_matched_det / len(det_circles) if det_circles else 0.0
        max_error = max(errors) if errors else float("nan")

        report = (
            f"recall={recall:.3f} ({n_matched_truth}/{len(truth_circles)} truth matched), "
            f"precision={precision:.3f} ({n_matched_det}/{len(det_circles)} detections matched), "
            f"max centre error={max_error:.2f}px (floor: <= {centre_error_tol:.2f}px)"
        )
        assert recall >= 0.95, report
        assert precision >= 0.90, report
        assert all(e <= centre_error_tol for e in errors), report
