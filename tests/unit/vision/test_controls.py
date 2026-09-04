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

import cv2
import numpy as np
import pytest
from PIL import Image

from fixtures.synth_map import CIRCLE_DIAMETER_MM, RENDER_SRGB
from rogaine.config import default_config
from rogaine.models import Control
from rogaine.vision.controls import _detect_circles, detect_controls, purple_mask

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


class TestOversizedRingsBeatABaseScaleDecoy:
    """T076, ADR-015 -- independent-review finding (C-1), fixed before landing: `_select_best_scale`
    must not let one base-scale false positive with a *perfect* mean coverage outrank many true,
    slightly-noisier rings at the map's real (larger) scale. A first version scored scales by raw
    mean coverage alone and handed every tie to the smallest multiplier (sweep order) -- but
    `_ring_coverage` saturates at exactly 1.0 for *any* candidate sitting inside a solid ink blob,
    not only a genuine ring, so a lone filled dot at the base scale ties a real scale's mean
    trivially. This is not a contrived edge case: it is what a single stray purple pixel-blob
    (unrelated debris, a printed legend swatch, anything solid and roughly round) would do to the
    old scoring on a real map. The fix scores `(coverage bucketed to _SCALE_TIE_EPS, candidate
    count)`, so a scale's *support* -- how many consistent circles it finds -- breaks ties between
    scales whose means are close enough to call equal.
    """

    def test_five_true_rings_at_2_5x_beat_one_perfect_base_scale_blob(self) -> None:
        dpi = 200.0
        config = default_config()
        det = config.detector
        r_min, r_max = det.circle_radius_px(dpi)
        r_mid = (r_min + r_max) / 2.0
        r_true = r_mid * 2.5  # a scale actually offered by the shipped circle_scale_multipliers

        gap = r_true * 3.0
        start_x = r_true * 2.0
        row_y = round(r_true * 2.0)
        true_centres = [(round(start_x + i * gap), row_y) for i in range(5)]

        width = round(true_centres[-1][0] + r_true * 2.0)
        decoy_centre = (round(r_mid * 2.0), round(row_y + r_true * 2.0 + r_mid * 2.0))
        height = round(decoy_centre[1] + r_mid * 2.0)

        image = np.full((height, width, 3), 255, dtype=np.uint8)
        ring_width = max(1, round(r_true * 0.15))
        for cx, cy in true_centres:
            cv2.circle(image, (cx, cy), round(r_true), RENDER_SRGB["purple_100"], ring_width)
        # A solid (filled, thickness=-1) blob at the base scale: ring-coverage samples its
        # circumference and finds ink all the way around, coverage 1.0, exactly as a genuine ring
        # would -- but it is one candidate against the true scale's five.
        cv2.circle(image, decoy_centre, round(r_mid), RENDER_SRGB["purple_100"], -1)

        mask = purple_mask(image, config)
        candidates = _detect_circles(mask, dpi, config)

        assert len(candidates) == len(true_centres), (
            f"expected the true scale's {len(true_centres)} rings, not the base-scale decoy; "
            f"got {len(candidates)}: {candidates}"
        )

        def _dist(ax: float, ay: float, bx: float, by: float) -> float:
            return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5

        for cx, cy in true_centres:
            assert any(_dist(cx, cy, x, y) <= r_true / 4.0 for x, y, _ in candidates), (
                f"no candidate near true ring centre ({cx}, {cy}): {candidates}"
            )


class TestSingleScaleSelected:
    """T076, ADR-015: one true ring must not be counted once per `circle_scale_multipliers` entry
    whose scaled window also passes `_ring_coverage` on it -- `_detect_circles` returns exactly one
    scale's candidates (`_select_best_scale`), so a ring cannot appear twice regardless of how many
    scales' windows it happens to fall inside.

    Adjacent multipliers' tolerance-widened windows overlap (`circle_diameter_tolerance=0.35`
    widens each scale's window to [0.65x, 1.35x] its own scaled radius, so e.g. multiplier 1.0's
    upper bound 1.35r and multiplier 1.5's lower bound 1.5r*0.65=0.975r overlap between 0.975r and
    1.35r). A ring whose true radius sits at the base scale's mid-radius therefore falls inside
    *both* the 1.0x and the 1.5x Hough search windows and can pass `_ring_coverage` at both --
    `_detect_circles` only ever returns one scale's candidates (`_select_best_scale`, T076,
    ADR-015), so this ring must not appear twice in the result regardless of how many scales it
    happens to clear the coverage bar at.
    """

    def test_one_true_ring_yields_exactly_one_candidate(self) -> None:
        dpi = 200.0
        config = default_config()
        det = config.detector
        r_min, r_max = det.circle_radius_px(dpi)
        r_mid = (r_min + r_max) / 2.0

        size = round(r_mid * 8)
        cx = cy = size // 2
        image = np.full((size, size, 3), 255, dtype=np.uint8)
        ring_width = max(1, round(r_mid * 0.15))
        cv2.circle(image, (cx, cy), round(r_mid), RENDER_SRGB["purple_100"], ring_width)

        mask = purple_mask(image, config)
        candidates = _detect_circles(mask, dpi, config)

        assert len(candidates) == 1, (
            f"expected exactly one candidate for the one true ring at multiplier 1.0's mid-radius "
            f"(which also falls inside multiplier 1.5's overlapping window), got "
            f"{len(candidates)}: {candidates}"
        )
        x, y, _ = candidates[0]
        dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
        assert dist <= r_mid / 4.0, (
            f"candidate at ({x:.1f}, {y:.1f}) is {dist:.2f}px from the true centre "
            f"({cx}, {cy}), tol={r_mid / 4.0:.2f}px"
        )


class TestRealScanRedInk:
    """I1, SPEC F7's second acceptance clause: on `data/maps/grid-lines-red-controls/map.jpeg`,
    whose controls and hub are hand-marked in red rather than ISOM purple, `purple_mask` (the
    pixel-level primitive `config/default.toml`'s `ink_hue_ranges` drives) must actually flag the
    real red ink. `test_purple_mask_flags_the_real_red_ink` below measures that directly and
    passes outright -- this is T073's genuine, narrow claim (widen the *colour* mask), independent
    of whatever the shape stage built on top of it does with that mask.

    That shape stage -- `cv2.HoughCircles` plus the ring-coverage gate -- did not turn that mask
    into correct detections on this file under T073 alone: `circle_radius_px(200)`'s predicted
    window ([15.4, 31.9]px from ISOM's 6mm circle spec) never contains a candidate near a true
    ~56px-radius ring, whatever ink colour the mask searches for, so every one of 16 raw detections
    was a false positive on the hand-written control *digits* (~43x67px components) instead
    (recall 0/13, precision 0/16, hub not found -- independently measured, see
    `docs/DECISIONS.md` ADR-015). Fixing it without loosening `_ring_coverage`/Hough's own
    parameters (non-negotiable per T073's own brief) is T076/ADR-015:
    `circle_scale_multipliers` sweeps the same, unmodified ring-coverage check across several
    scaled radius windows instead. `test_recall_and_hub_match_the_true_positions` below now
    asserts the real, fixed outcome (recall/precision >= 0.90, hub found) rather than documenting
    the prior failure.
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
