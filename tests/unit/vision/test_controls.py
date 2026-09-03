"""Control circle and start-triangle detection (T020): SPEC F7's HSV-mask + Hough pipeline.

DoD (F7): HSV purple mask plus HoughCircles with the radius range derived from `dpi` (ISOM 5-6 mm);
the start triangle (ISOM 701) is recognised at the hub; on the fixture recall at least 0.95,
precision at least 0.90, centre error at most a quarter radius. `docs/TASKS.md`'s T020 entry also
names a "finish double-circle" symbol -- `tests/fixtures/synth_map.py`'s `_place_controls` draws no
such second marker (this project's start = finish, one-hub convention,
`docs/BRIEF.md`/`docs/SPEC.md`), so there is nothing to test for it here.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from fixtures.synth_map import CIRCLE_DIAMETER_MM
from rogaine.config import default_config
from rogaine.models import Control
from rogaine.vision.controls import detect_controls, purple_mask

#: I1 (docs/iterations/I1-real-scan-vision.md): a real scan whose controls and hub are hand-marked
#: in red, not ISOM purple. Gitignored per ADR-010 -- present only on machines the owner handed it
#: to -- so tests using it skip rather than fail where it is absent.
_REAL_SCAN_DIR = Path(__file__).resolve().parents[3] / "data" / "maps" / "grid-lines-red-controls"
_REAL_SCAN_PATH = _REAL_SCAN_DIR / "map.jpeg"


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

    def test_rejects_a_saturated_colour_outside_every_configured_band(self) -> None:
        # Red is no longer a safe "outside every band" colour to test with (I1/ADR-011: it is now
        # one of the shipped ink_hue_ranges, alongside purple). Saturated green (hue ~60) sits in
        # the gap between the configured bands -- purple [140, 175], red [0, 9] and [167, 179]
        # (config/default.toml) -- so it is still a genuine negative case.
        image = np.full((20, 20, 3), 255, dtype=np.uint8)
        image[:] = (40, 200, 40)  # saturated green

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


class TestRealScanRedInk:
    """I1, SPEC F7's second acceptance clause: on `data/maps/grid-lines-red-controls/map.jpeg`,
    whose controls and hub are hand-marked in red rather than ISOM purple, `purple_mask` (the
    pixel-level primitive `config/default.toml`'s `ink_hue_ranges` drives) must actually flag the
    real red ink. `test_purple_mask_flags_the_real_red_ink` below measures that directly and
    passes outright -- this is T073's genuine, narrow claim (widen the *colour* mask), independent
    of whatever the shape stage built on top of it does with that mask.

    That shape stage -- `cv2.HoughCircles` plus the ring-coverage gate -- does NOT currently turn
    that mask into correct detections on this file, and does not just fall short of a high bar: it
    is wrong. Independently re-measured this session (`test_recall_and_hub_match_the_true_positions`
    below, `xfail(strict=True)`): `detect_controls` returns 16 "circles" and no hub, and **every
    one of the 16 is a false positive** -- nearest true ring 97.7-466.9px away, recall 0/13 =
    0.000, hub not found. Connected-component analysis of the real scan's strict red-ink mask
    (`R>150, R-G>60, R-B>60`) identifies what the 16 actually are: the hand-written control
    *digits* (~43x67px components), not the ~111-113x110-113px (~56px radius) ring components the
    detector is supposed to find. The digits happen to fall inside `circle_radius_px(200)`'s
    predicted window ([15.4, 31.9]px from ISOM's 6mm circle spec); the true rings, at ~56px
    radius, do not -- `cv2.HoughCircles`' `minRadius`/`maxRadius` (from that same window) can
    therefore never return a candidate anywhere near a true ring, whatever ink colour the mask
    searches for. This is a radius/geometry defect, orthogonal to ink colour, and fixing it means
    changing the Hough radius derivation or `circle_diameter_mm`/`circle_diameter_tolerance` --
    exactly what T073's task brief calls non-negotiable not to touch ("No change to
    _ring_coverage/Hough parameters or any other false-positive guard"). Left for a follow-up
    task (not yet filed as of this session); flagged here rather than silently passed over, and
    **SPEC F7's acceptance clause "finds the map's red-circled controls (shape-filtered, not 'any
    red pixel')" does not hold on this file** until it lands -- see `docs/STATUS.md`.
    """

    @pytest.mark.skipif(
        not _REAL_SCAN_PATH.is_file(),
        reason="data/maps/grid-lines-red-controls/map.jpeg absent (ADR-010: gitignored real scan)",
    )
    def test_purple_mask_flags_the_real_red_ink(self) -> None:
        """T073's actual, narrow claim: the widened hue mask covers the real red ink at the pixel
        level. Measured against the same strict red-pixel criterion this file's other tests use
        for ground truth (`R>150, R-G>60, R-B>60`, 54,061 matching pixels): `purple_mask` overlaps
        98.99% of them. Deliberately does not touch `detect_controls`/Hough at all -- see this
        class's own docstring for why that stage is a separate, still-broken concern on this file.
        """
        image = np.array(Image.open(_REAL_SCAN_PATH).convert("RGB"))
        mask = purple_mask(image, default_config())

        r, g, b = (image[..., i].astype(int) for i in range(3))
        strict_red = (r > 150) & (r - g > 60) & (r - b > 60)

        overlap = float((mask & strict_red).sum())
        coverage = overlap / float(strict_red.sum())
        assert coverage >= 0.95, f"purple_mask covers only {coverage:.3f} of the real red ink"

    @pytest.mark.skipif(
        not _REAL_SCAN_PATH.is_file(),
        reason="data/maps/grid-lines-red-controls/map.jpeg absent (ADR-010: gitignored real scan)",
    )
    @pytest.mark.xfail(
        reason=(
            "measured this session: recall 0/13 = 0.000, precision 0/16 = 0.000, hub not found. "
            "known, out-of-T073-scope radius/geometry mismatch: this file's true control rings "
            "measure ~56px radius and its hub triangle ~125px side, versus the "
            "[15.4, 31.9]px / [33.8, 70.2]px windows DetectorSettings.circle_radius_px(200) "
            "predicts -- see TestRealScanRedInk's class docstring for the full measurement."
        ),
        strict=True,
    )
    def test_recall_and_hub_match_the_true_positions(self) -> None:
        with (_REAL_SCAN_DIR / "meta.toml").open("rb") as fh:
            meta = tomllib.load(fh)
        dpi = float(meta["dpi"])

        image = np.array(Image.open(_REAL_SCAN_PATH).convert("RGB"))
        detections = detect_controls(image, dpi, default_config())
        circles = [d for d in detections if not d.is_hub]
        hub = next((d for d in detections if d.is_hub), None)

        # True positions, measured once offline via connected-component analysis of a strict
        # red-pixel mask (R > 150, R-G > 60, R-B > 60) over the full scan: 13 ring components (each
        # an ~111-113 x 110-113 px bbox) plus the hub triangle (~127x111 px bbox, its contour
        # reduced to 3 vertices by cv2.approxPolyDP).
        true_ring_centres = [
            (1276.1, 294.1), (411.1, 297.6), (618.9, 606.9), (1444.8, 633.9),
            (1769.4, 801.7), (323.1, 844.3), (796.0, 1026.5), (1871.6, 1090.4),
            (218.8, 1246.2), (1113.7, 1329.5), (1515.3, 1413.3), (1899.7, 1571.3),
            (213.0, 1597.7),
        ]
        true_hub_centre = (808.7, 302.3)
        match_tol = 56.0  # one true ring radius

        def _dist(ax: float, ay: float, bx: float, by: float) -> float:
            return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5

        matched = sum(
            1
            for tx, ty in true_ring_centres
            if any(_dist(tx, ty, d.x, d.y) <= match_tol for d in circles)
        )
        recall = matched / len(true_ring_centres)
        n_matched_det = sum(
            1
            for d in circles
            if any(_dist(tx, ty, d.x, d.y) <= match_tol for tx, ty in true_ring_centres)
        )
        precision = n_matched_det / len(circles) if circles else 0.0
        hub_ok = hub is not None and _dist(*true_hub_centre, hub.x, hub.y) <= match_tol

        report = (
            f"recall={recall:.3f} ({matched}/{len(true_ring_centres)} true rings matched), "
            f"precision={precision:.3f} ({len(circles)} detections)"
        )
        assert recall >= 0.90, report
        assert precision >= 0.90, report
        assert hub_ok, f"hub not found within {match_tol}px of the true centre"
