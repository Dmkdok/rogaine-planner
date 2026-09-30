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
from rogaine.io.raster import resolve_dpi
from rogaine.models import Control
from rogaine.vision.controls import (
    _detect_circles,
    _select_best_scale,
    detect_controls,
    purple_mask,
)

#: I1 (docs/iterations/I1-real-scan-vision.md): a real scan whose controls and hub are hand-marked
#: in red, not ISOM purple. Gitignored per ADR-010 -- present only on machines the owner handed it
#: to -- so tests using it skip rather than fail where it is absent.
_REAL_SCAN_DIR = Path(__file__).resolve().parents[3] / "data" / "maps" / "grid-lines-red-controls"
_REAL_SCAN_PATH = _REAL_SCAN_DIR / "map.jpeg"

#: ADR-018 (I2): a second real scan whose controls are ISOM purple, not red -- used only to check
#: `purple_mask`'s false-positive *rate* (brown contour ink leaking into the red band), never
#: recall/precision (no `meta.toml`/dpi ships with it, so `detect_controls` cannot be run against
#: it). Gitignored per ADR-010, same as `_REAL_SCAN_PATH` above.
_OZERO_SCAN_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "maps" / "ozero-shchuche" / "map.jpg"
)


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
        candidates = _detect_circles(image, mask, dpi, config)

        assert len(candidates) == len(true_centres), (
            f"expected the true scale's {len(true_centres)} rings, not the base-scale decoy; "
            f"got {len(candidates)}: {candidates}"
        )

        def _dist(ax: float, ay: float, bx: float, by: float) -> float:
            return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5

        for cx, cy in true_centres:
            assert any(_dist(cx, cy, x, y) <= r_true / 4.0 for x, y, _r, _ in candidates), (
                f"no candidate near true ring centre ({cx}, {cy}): {candidates}"
            )


class TestAutoPlacementConfidenceFloor:
    """T105, ADR-033 (I6 item 7): a candidate whose own `_ring_coverage` clears the base
    `_RING_COVERAGE_MIN` (0.75) but not `_AUTO_PLACEMENT_CONFIDENCE_FLOOR` (0.80) must not be
    auto-placed as a `Control` -- the owner's own cross-cutting policy request, "skip auto-placing
    a control the system isn't confident about, rather than risk a false one."
    """

    def test_a_broken_ring_below_the_floor_is_dropped_not_placed(self) -> None:
        dpi = 200.0
        config = default_config()
        det = config.detector
        r_min, r_max = det.circle_radius_px(dpi)
        r_true = (r_min + r_max) / 2.0  # base scale (multiplier 1.0)

        gap = r_true * 4.0
        full_centres = [(round(r_true * 2.0 + i * gap), round(r_true * 2.0)) for i in range(2)]
        broken_centre = (round(full_centres[-1][0] + gap), round(r_true * 2.0))

        width = round(broken_centre[0] + r_true * 2.0)
        height = round(r_true * 4.0)
        image = np.full((height, width, 3), 255, dtype=np.uint8)
        ring_width = max(1, round(r_true * 0.15))
        for cx, cy in full_centres:
            cv2.circle(image, (cx, cy), round(r_true), RENDER_SRGB["purple_100"], ring_width)
        # A ring missing 80 of its 360 degrees: real ink over the remaining 280 degrees, so
        # `_ring_coverage` measures ~280/360 = 0.778 -- comfortably between the base 0.75 floor
        # (so it is still a candidate at all) and this task's own 0.80 floor (so it must be
        # dropped by it).
        cv2.ellipse(
            image,
            broken_centre,
            (round(r_true), round(r_true)),
            0,
            0,
            280,
            RENDER_SRGB["purple_100"],
            ring_width,
        )

        mask = purple_mask(image, config)
        candidates = _detect_circles(image, mask, dpi, config)

        assert len(candidates) == len(full_centres), (
            f"expected only the {len(full_centres)} full rings, not the broken one; "
            f"got {len(candidates)}: {candidates}"
        )

        def _dist(ax: float, ay: float, bx: float, by: float) -> float:
            return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5

        assert not any(
            _dist(broken_centre[0], broken_centre[1], x, y) <= r_true / 4.0
            for x, y, _r, _ in candidates
        ), f"broken ring at {broken_centre} was auto-placed despite its own low confidence"
        for cx, cy in full_centres:
            assert any(_dist(cx, cy, x, y) <= r_true / 4.0 for x, y, _r, _ in candidates), (
                f"no candidate near full ring centre ({cx}, {cy}): {candidates}"
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
        candidates = _detect_circles(image, mask, dpi, config)

        assert len(candidates) == 1, (
            f"expected exactly one candidate for the one true ring at multiplier 1.0's mid-radius "
            f"(which also falls inside multiplier 1.5's overlapping window), got "
            f"{len(candidates)}: {candidates}"
        )
        x, y, _r, _ = candidates[0]
        dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
        assert dist <= r_mid / 4.0, (
            f"candidate at ({x:.1f}, {y:.1f}) is {dist:.2f}px from the true centre "
            f"({cx}, {cy}), tol={r_mid / 4.0:.2f}px"
        )


class TestOutOfBoundsHatchExcluded:
    """T103, SPEC F7's ISOM 709 exclusion clause. ISOM 709 (out of bounds) is printed in the same
    purple ink as the 703 control circle, as a dense diagonal cross-hatch rather than a ring.
    `_ring_coverage` alone does not reject it: measured directly on a real scan
    (`data/maps/ogps-7302_5d8c290224a04f49e2c95484d2fbaf92`), the hatch's own crossing density let
    dozens of spurious Hough fits saturate `_ring_coverage` to as high as 1.000, dragging that map's
    raw circle count from its true ~35 controls up to 65. The hatch block below reproduces that
    same failure mode synthetically rather than merely asserting the fix in the abstract: its line
    spacing/thickness (as a fraction of `r_mid`) is set from that same real scan's own measured
    hatch pitch (a horizontal scanline through its out-of-bounds polygon), and with
    `_INTERIOR_INK_MAX` neutralised this exact synthetic block reproduces the real failure (7
    spurious in-block candidates) -- so a regression that silences `_interior_ink_fraction` again
    would fail this test, not just the real scan nobody runs in CI (ADR-010: gitignored).
    """

    def test_hatch_block_yields_no_candidates_while_real_circles_still_found(self) -> None:
        dpi = 200.0
        config = default_config()
        det = config.detector
        r_min, r_max = det.circle_radius_px(dpi)
        r_mid = (r_min + r_max) / 2.0

        block_side = round(r_mid * 4.5)
        margin = round(r_mid * 2.0)
        size = block_side + margin * 2 + round(r_mid * 10)
        block_x0, block_y0 = margin, margin
        block_x1, block_y1 = block_x0 + block_side, block_y0 + block_side

        # Spacing/thickness ratios measured against the real out-of-bounds hatch on
        # `ogps-7302_5d8c290224a04f49e2c95484d2fbaf92` (a horizontal scanline through it: ~6-7px
        # ink runs separated by ~2-3px gaps, at that map's own r_mid of ~34.5px).
        hatch_thickness = max(1, round(r_mid * 0.19))
        hatch_spacing = max(2, round(r_mid * 0.28))
        purple = RENDER_SRGB["purple_100"]

        # Drawn on a separate canvas and copied in only within the block's own bounding box --
        # `cv2.line` does not clip to an arbitrary rectangle, and an uncropped diagonal hatch would
        # bleed well past the intended block and contaminate the true circles placed just outside
        # it below.
        hatch_canvas = np.full((size, size, 3), 255, dtype=np.uint8)
        for offset in range(-block_side, block_side, hatch_spacing):
            cv2.line(
                hatch_canvas,
                (block_x0 + offset, block_y0),
                (block_x0 + offset + block_side, block_y1),
                purple,
                hatch_thickness,
            )
            cv2.line(
                hatch_canvas,
                (block_x1 - offset, block_y0),
                (block_x1 - offset - block_side, block_y1),
                purple,
                hatch_thickness,
            )
        image = np.full((size, size, 3), 255, dtype=np.uint8)
        image[block_y0:block_y1, block_x0:block_x1] = hatch_canvas[
            block_y0:block_y1, block_x0:block_x1
        ]

        true_centres = [
            (block_x1 + round(r_mid * 3.0), block_y0 + round(r_mid * 1.5)),
            (block_x0 + round(r_mid * 1.5), block_y1 + round(r_mid * 3.0)),
        ]
        ring_width = max(1, round(r_mid * 0.15))
        for cx, cy in true_centres:
            cv2.circle(image, (cx, cy), round(r_mid), purple, ring_width)

        mask = purple_mask(image, config)
        candidates = _detect_circles(image, mask, dpi, config)

        in_block = [
            (x, y)
            for x, y, _r, _conf in candidates
            if block_x0 <= x <= block_x1 and block_y0 <= y <= block_y1
        ]
        assert in_block == [], f"spurious candidate(s) inside the out-of-bounds block: {in_block}"

        assert len(candidates) == len(true_centres), (
            f"expected exactly the {len(true_centres)} real circles, got {len(candidates)}: "
            f"{candidates}"
        )
        for cx, cy in true_centres:
            assert any(
                ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 <= r_mid / 4.0
                for x, y, _r, _conf in candidates
            ), f"no candidate near true ring centre ({cx}, {cy}): {candidates}"


class TestRadiusThreadedThroughDetection:
    """T077, ADR-020: `_detect_circles` widened its candidate tuples from `(x, y, coverage)` to
    `(x, y, r, coverage)` so `detect_controls` can carry the matched scale's nominal radius into
    `Control.radius_px` instead of discarding it -- OCR (`vision/ocr.py::_ocr_crop`) then sizes its
    crop from the control's own matched scale rather than always assuming the base ISOM print size.
    `r` is that scale's nominal mid radius, not Hough's own per-candidate fit -- see
    `_detect_circles`'s inline comment for why (raw per-candidate jitter regressed OCR on the
    clean fixture when this was first tried).
    """

    def test_detect_circles_candidates_are_four_tuples_with_a_plausible_radius(self) -> None:
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
        candidates = _detect_circles(image, mask, dpi, config)

        assert len(candidates) == 1
        _x, _y, r, coverage = candidates[0]
        assert r_min * 0.5 <= r <= r_max * 1.5, (
            f"nominal radius {r:.2f}px is implausible for a true radius of {r_mid:.2f}px"
        )
        assert 0.0 <= coverage <= 1.0

    def test_select_best_scale_passes_the_winning_scales_tuples_through_unchanged(self) -> None:
        losing = [(1.0, 2.0, 3.0, 0.80)]
        winning = [(10.0, 20.0, 5.0, 0.99), (11.0, 21.0, 5.5, 0.98)]

        result = _select_best_scale([(1.0, losing), (2.0, winning)])

        assert result == winning

    def test_detect_controls_sets_radius_px_on_every_non_hub_control(self, synthetic_map) -> None:
        sm = synthetic_map
        detections = detect_controls(sm.image, sm.dpi, default_config())
        circles = [d for d in detections if not d.is_hub]
        assert circles, "expected at least one detected control circle"

        r_min, r_max = default_config().detector.circle_radius_px(sm.dpi)
        for c in circles:
            assert c.radius_px is not None, f"control {c.id} has no radius_px"
            assert r_min * 0.5 <= c.radius_px <= r_max * 1.5, (
                f"control {c.id} radius_px={c.radius_px:.2f} outside plausible window "
                f"[{r_min:.2f}, {r_max:.2f}]"
            )

    def test_hub_still_has_no_radius(self, synthetic_map) -> None:
        sm = synthetic_map
        detections = detect_controls(sm.image, sm.dpi, default_config())
        hub = next(d for d in detections if d.is_hub)
        assert hub.radius_px is None


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


class TestInkHueFalsePositiveRateOnOzeroShchuche:
    """ADR-018 (I2): `purple_mask` flagged 6.82% of this file (measured once, T079's own baseline
    session), 3.5x `grid-lines-red-controls`' 1.93% (`TestRecallPrecisionOnFixture` and
    `TestRealScanRedInk` above hold that file's own floor). 88% of the flagged pixels were brown
    contour ink (mean RGB (161, 106, 90)) passing the red band's then-shared 60/60
    saturation/value floor, not real control ink (only 12% were true purple, mean RGB
    (234, 66, 221)). This file carries no `meta.toml`/dpi, so only the pixel-level `purple_mask`
    primitive is testable here -- the same constraint `TestRealScanRedInk` documents for its own
    file's `test_purple_mask_flags_the_real_red_ink`.
    """

    @pytest.mark.skipif(
        not _OZERO_SCAN_PATH.is_file(),
        reason="data/maps/ozero-shchuche/map.jpg absent (ADR-010: gitignored real scan)",
    )
    def test_density_dropped_towards_the_red_controls_files_order_of_magnitude(self) -> None:
        image = np.array(Image.open(_OZERO_SCAN_PATH).convert("RGB"))
        mask = purple_mask(image, default_config())
        density = float(mask.sum()) / mask.size

        baseline_density = 0.0682  # measured pre-ADR-018, this file, T079's own baseline session
        report = (
            f"purple_mask density on ozero-shchuche is {density:.4f} "
            f"(pre-fix: {baseline_density:.4f})"
        )
        # A regression guard (density must actually have dropped, substantially) plus an absolute
        # cap keeping it in the same order of magnitude as grid-lines-red-controls' own 1.93%
        # floor, without hard-coding that file's exact, independently-tuned number here.
        assert density < baseline_density * 0.5, report
        assert density < 0.02, report


class TestHubFoundOnOzeroShchuche:
    """T081 regression guard. `_detect_hub_triangle` found no hub on this file even under T079's
    clean purple mask, for two independent, measured reasons -- both fixed by T081, neither
    touching `purple_mask`/`_select_best_scale`:

    - This file's start/finish is ISOM's *combined* symbol: the 701 triangle overlapping the 706
      finish double-circle. The circle's ink bulges one edge of the triangle's contour outward,
      adding a vertex `cv2.approxPolyDP`'s original fixed epsilon (0.02) could not absorb --
      `_detect_hub_triangle` never saw a 3-vertex fit at all. `_TRIANGLE_APPROX_EPS_FRACTIONS`
      widens the search; this file's own triangle first collapses to exactly 3 vertices at
      eps=0.03 (measured this session).
    - Independently, `cv2.RETR_EXTERNAL` (the pre-T081 retrieval mode) only returns a contour's
      outermost nesting level; a shape entirely inside another contour's hole is invisible to it
      even without touching that contour. `cv2.RETR_LIST` (T081) returns every contour regardless
      of nesting.

    True hub location measured this session by visual inspection (crop of the mask around the
    triangle+circle icon, `data/maps/ozero-shchuche/map.jpg`): centre approx (2042, 2000) at this
    file's own probed DPI (300, read from its JFIF header -- no `meta.toml` ships with this file,
    same as `TestInkHueFalsePositiveRateOnOzeroShchuche` above, so `resolve_dpi` falls back to the
    probe exactly as the CLI does with no `--dpi` flag).
    """

    @pytest.mark.skipif(
        not _OZERO_SCAN_PATH.is_file(),
        reason="data/maps/ozero-shchuche/map.jpg absent (ADR-010: gitignored real scan)",
    )
    def test_hub_is_found_near_the_true_location(self) -> None:
        image = np.array(Image.open(_OZERO_SCAN_PATH).convert("RGB"))
        dpi = resolve_dpi(_OZERO_SCAN_PATH)
        detections = detect_controls(image, dpi, default_config())
        hub = next((d for d in detections if d.is_hub), None)

        assert hub is not None, "hub not found on ozero-shchuche"
        true_x, true_y = 2042.0, 2000.0
        dist = ((hub.x - true_x) ** 2 + (hub.y - true_y) ** 2) ** 0.5
        # One true ring diameter's worth of slack (measured ring radius ~53px at this file's
        # matched scale multiplier 1.5) -- generous, this test only guards existence/rough
        # position, not the sub-pixel accuracy `TestRealScanRedInk` already covers elsewhere.
        assert dist <= 106.0, (
            f"hub detected at ({hub.x:.1f}, {hub.y:.1f}), {dist:.1f}px from truth "
            f"({true_x}, {true_y})"
        )


class TestOcrGatesDisableVlmFallback:
    """T117/H-1: the scale-selection gates must never let the opt-in VLM fallback run -- circle
    detection stays classical CV, and these gates probe known-junk candidate sets."""

    @staticmethod
    def _capturing_stub(seen: list):
        def stub(image, controls, dpi, config):
            seen.append(config.ocr_fallback.enabled)
            return [c.model_copy(update={"number": 1}) for c in controls], []

        return stub

    @staticmethod
    def _enabled_config(provider: str):
        cfg = default_config()
        return cfg.model_copy(
            update={
                "ocr_fallback": cfg.ocr_fallback.model_copy(
                    update={"enabled": True, "provider": provider}
                )
            }
        )

    @pytest.mark.parametrize("provider", ["anthropic", "ollama"])
    def test_sub_base_gate_probes_with_fallback_disabled(
        self, monkeypatch: pytest.MonkeyPatch, provider: str
    ) -> None:
        import rogaine.vision.ocr as ocr_module
        from rogaine.vision.controls import _ocr_gate_sub_base_scale

        seen: list[bool] = []
        monkeypatch.setattr(ocr_module, "read_control_numbers", self._capturing_stub(seen))
        cfg = self._enabled_config(provider)
        sub_base = [(10.0, 10.0, 5.0, 0.9)]
        production = [(30.0, 30.0, 5.0, 0.9)]

        _ocr_gate_sub_base_scale(
            np.zeros((10, 10, 3), dtype=np.uint8),
            200.0,
            cfg,
            [(0.5, sub_base), (1.0, production)],
            sub_base,
        )

        assert len(seen) == 2 and not any(seen)  # sub-1.0 probe and production probe
        assert cfg.ocr_fallback.enabled is True  # caller's config not mutated

    @pytest.mark.parametrize("provider", ["anthropic", "ollama"])
    def test_tied_scales_gate_probes_with_fallback_disabled(
        self, monkeypatch: pytest.MonkeyPatch, provider: str
    ) -> None:
        import rogaine.vision.ocr as ocr_module
        from rogaine.vision.controls import _ocr_gate_tied_scales

        seen: list[bool] = []
        monkeypatch.setattr(ocr_module, "read_control_numbers", self._capturing_stub(seen))
        cfg = self._enabled_config(provider)
        cands = [(10.0, 10.0, 5.0, 0.9)]

        _ocr_gate_tied_scales(
            np.zeros((10, 10, 3), dtype=np.uint8),
            200.0,
            cfg,
            [(2.0, cands), (2.5, list(cands))],
            cands,
        )

        assert len(seen) == 2 and not any(seen)

    @pytest.mark.parametrize("provider", ["anthropic", "ollama"])
    def test_no_backend_fires_during_detect_controls(
        self, synthetic_map, monkeypatch: pytest.MonkeyPatch, provider: str
    ) -> None:
        """End to end: with the fallback enabled, neither backend is ever called by detection."""
        from unittest.mock import MagicMock

        from rogaine.vision import ocr_vlm, ocr_vlm_ollama

        anthropic_spy, ollama_spy = MagicMock(), MagicMock()
        monkeypatch.setattr(ocr_vlm, "read_control_number", anthropic_spy)
        monkeypatch.setattr(ocr_vlm_ollama, "read_control_number", ollama_spy)
        sm = synthetic_map

        detect_controls(sm.image, sm.dpi, self._enabled_config(provider))

        anthropic_spy.assert_not_called()
        ollama_spy.assert_not_called()


class TestOcrGateSubBaseScale:
    """T090/ADR-031 (independent review finding H2): `_ocr_gate_sub_base_scale`'s branches,
    driven directly with a stubbed `read_control_numbers` -- its only prior coverage was three
    real-scan floor tests in `test_ocr.py`, all `skipif`-guarded on gitignored files (ADR-010), so
    the gate ran unexercised on any machine without the owner's own corpus (CI included). The
    deferred `from rogaine.vision.ocr import read_control_numbers` inside the function under test
    (see its own comment on why the import is deferred) re-resolves `rogaine.vision.ocr`'s module
    attribute on every call, so `monkeypatch.setattr` on that module reaches it with no need to
    patch `rogaine.vision.controls` itself.

    Each stub is keyed by the exact x-coordinates of the `Control`s it's asked to score -- a plain,
    deterministic stand-in for "how many of these controls read a number" that needs no real image
    or OCR call; `_stub_reading` marks the first *n_read* controls (in the order passed in) as read,
    the rest as unread.

    T099/ADR-032 generalised the sub-1.0 side from a whole-set comparison to a per-candidate one,
    then this same amendment (after the owner's own T100 sign-off found the first version too
    aggressive -- see the function's own docstring) narrowed that to a junk-fraction condition:
    at or below `_SUB_BASE_JUNK_UNREAD_FRACTION` unread, the whole set is kept (T090's original
    behaviour); strictly above it, only the reading candidates survive (T099's original behaviour).
    The first four tests below happen to keep the same overall pass/fail outcome under either rule
    (every sub-1.0 candidate in them either all reads or all doesn't, so which rule applies changes
    nothing about which side wins) -- itself the regression proof that neither amendment disturbed
    T090's own already-covered branches. The remaining tests cover the junk-fraction line itself,
    on both sides of it, with and without a production side to compare against.
    """

    @staticmethod
    def _stub_reading(read_counts_by_xs: dict[tuple[float, ...], int]):
        def stub(image, controls, dpi, config):
            xs = tuple(c.x for c in controls)
            n_read = read_counts_by_xs[xs]
            updated = [
                c.model_copy(update={"number": (i + 1) if i < n_read else None})
                for i, c in enumerate(controls)
            ]
            return updated, []

        return stub

    def test_sub_base_wins_when_it_reads_strictly_more(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sub_base = [(10.0, 10.0, 5.0, 0.9), (20.0, 20.0, 5.0, 0.9)]
        production = [(30.0, 30.0, 5.0, 0.9)]
        per_multiplier = [(0.5, []), (1.0, production)]

        import rogaine.vision.ocr as ocr_module
        from rogaine.vision.controls import _ocr_gate_sub_base_scale

        monkeypatch.setattr(
            ocr_module,
            "read_control_numbers",
            self._stub_reading({(30.0,): 0, (10.0, 20.0): 2}),
        )

        result = _ocr_gate_sub_base_scale(
            np.zeros((10, 10, 3), dtype=np.uint8), 200.0, default_config(), per_multiplier, sub_base
        )
        assert result == sub_base

    def test_production_wins_when_it_reads_strictly_more(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sub_base = [(10.0, 10.0, 5.0, 0.9), (20.0, 20.0, 5.0, 0.9)]
        production = [(30.0, 30.0, 5.0, 0.9)]
        per_multiplier = [(0.5, []), (1.0, production)]

        import rogaine.vision.ocr as ocr_module
        from rogaine.vision.controls import _ocr_gate_sub_base_scale

        monkeypatch.setattr(
            ocr_module,
            "read_control_numbers",
            self._stub_reading({(30.0,): 1, (10.0, 20.0): 0}),
        )

        result = _ocr_gate_sub_base_scale(
            np.zeros((10, 10, 3), dtype=np.uint8), 200.0, default_config(), per_multiplier, sub_base
        )
        assert result == production

    def test_tie_falls_back_to_production_both_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Docstring's own degenerate case: a purely geometric image with no digit ink reads zero
        on both sides -- must not hand the tie to the unvalidated sub-1.0 set."""
        sub_base = [(10.0, 10.0, 5.0, 0.9)]
        production = [(30.0, 30.0, 5.0, 0.9)]
        per_multiplier = [(0.5, []), (1.0, production)]

        import rogaine.vision.ocr as ocr_module
        from rogaine.vision.controls import _ocr_gate_sub_base_scale

        monkeypatch.setattr(
            ocr_module, "read_control_numbers", self._stub_reading({(30.0,): 0, (10.0,): 0})
        )

        result = _ocr_gate_sub_base_scale(
            np.zeros((10, 10, 3), dtype=np.uint8), 200.0, default_config(), per_multiplier, sub_base
        )
        assert result == production

    def test_tie_falls_back_to_production_equal_nonzero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sub_base = [(10.0, 10.0, 5.0, 0.9)]
        production = [(30.0, 30.0, 5.0, 0.9)]
        per_multiplier = [(0.5, []), (1.0, production)]

        import rogaine.vision.ocr as ocr_module
        from rogaine.vision.controls import _ocr_gate_sub_base_scale

        monkeypatch.setattr(
            ocr_module, "read_control_numbers", self._stub_reading({(30.0,): 1, (10.0,): 1})
        )

        result = _ocr_gate_sub_base_scale(
            np.zeros((10, 10, 3), dtype=np.uint8), 200.0, default_config(), per_multiplier, sub_base
        )
        assert result == production

    def test_no_production_candidates_below_junk_fraction_keeps_whole_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No `>=1.0` entry has any candidate at all -- nothing to compare against -- but the
        per-candidate probe still runs (needed for the junk-fraction check regardless). Here only
        1 of 2 candidates reads (50% unread, below `_SUB_BASE_JUNK_UNREAD_FRACTION`), so the set is
        not junk-dominated and the whole thing is kept -- T090's original "nothing to compare
        against, sub-1.0 stands" behaviour, now reached via the fraction check rather than
        unconditionally.
        """
        sub_base = [(10.0, 10.0, 5.0, 0.9), (20.0, 20.0, 5.0, 0.9)]
        per_multiplier = [(0.5, sub_base), (1.0, [])]

        import rogaine.vision.ocr as ocr_module
        from rogaine.vision.controls import _ocr_gate_sub_base_scale

        monkeypatch.setattr(
            ocr_module, "read_control_numbers", self._stub_reading({(10.0, 20.0): 1})
        )

        result = _ocr_gate_sub_base_scale(
            np.zeros((10, 10, 3), dtype=np.uint8), 200.0, default_config(), per_multiplier, sub_base
        )
        assert result == sub_base

    def test_no_production_candidates_above_junk_fraction_filters_to_the_reads(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same "nothing to compare against" shape, but with 9 of 10 candidates unread (90%,
        above `_SUB_BASE_JUNK_UNREAD_FRACTION`) -- a map whose only Hough hits are sub-1.0 junk
        (e.g. a cover page with no real controls, only small round glyph loops) is exactly the case
        this must not leave unguarded even with no production alternative, so only the one reading
        candidate survives.
        """
        sub_base = [(float(i * 10), float(i * 10), 5.0, 0.9) for i in range(10)]
        per_multiplier = [(0.5, sub_base), (1.0, [])]

        import rogaine.vision.ocr as ocr_module
        from rogaine.vision.controls import _ocr_gate_sub_base_scale

        monkeypatch.setattr(
            ocr_module,
            "read_control_numbers",
            self._stub_reading({tuple(c[0] for c in sub_base): 1}),
        )

        result = _ocr_gate_sub_base_scale(
            np.zeros((10, 10, 3), dtype=np.uint8), 200.0, default_config(), per_multiplier, sub_base
        )
        assert result == [sub_base[0]]

    def test_below_junk_fraction_keeps_the_illegible_ones_flagged_not_dropped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """T100's own real finding on `kkm-toksovo` (ADR-032's amendment): a genuine control whose
        specific number Tesseract can't read must not silently vanish from the output the way T099's
        first version made it -- it stays in the returned set (flagged unread downstream, exactly
        like a production-scale detection would be) as long as the set as a whole doesn't look
        junk-dominated. Two of three candidates unread (67%, below the 85% line) plus a weaker
        production side: the whole 3-candidate set wins and is returned unfiltered.
        """
        sub_base = [(10.0, 10.0, 5.0, 0.9), (20.0, 20.0, 5.0, 0.9), (30.0, 30.0, 5.0, 0.9)]
        production = [(40.0, 40.0, 5.0, 0.9)]
        per_multiplier = [(0.5, []), (1.0, production)]

        import rogaine.vision.ocr as ocr_module
        from rogaine.vision.controls import _ocr_gate_sub_base_scale

        monkeypatch.setattr(
            ocr_module,
            "read_control_numbers",
            self._stub_reading({(10.0, 20.0, 30.0): 1, (40.0,): 0}),
        )

        result = _ocr_gate_sub_base_scale(
            np.zeros((10, 10, 3), dtype=np.uint8), 200.0, default_config(), per_multiplier, sub_base
        )
        assert result == sub_base

    def test_above_junk_fraction_drops_the_non_reading_candidates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """T100's own real finding on `ogps-3771` (ADR-032's amendment): a set overwhelmingly
        dominated by coincidental ink-texture false positives (a pink-hatched "no-crossing zone",
        in the real case) should still be filtered down to its few genuine reads, not returned
        whole. 9 of 10 candidates unread (90%, above the 85% line) plus a weaker production side:
        only the reading candidate survives, and that filtered result still beats production.
        """
        sub_base = [(float(i * 10), float(i * 10), 5.0, 0.9) for i in range(10)]
        production = [(999.0, 999.0, 5.0, 0.9)]
        per_multiplier = [(0.5, []), (1.0, production)]

        import rogaine.vision.ocr as ocr_module
        from rogaine.vision.controls import _ocr_gate_sub_base_scale

        monkeypatch.setattr(
            ocr_module,
            "read_control_numbers",
            self._stub_reading({tuple(c[0] for c in sub_base): 1, (999.0,): 0}),
        )

        result = _ocr_gate_sub_base_scale(
            np.zeros((10, 10, 3), dtype=np.uint8), 200.0, default_config(), per_multiplier, sub_base
        )
        assert result == [sub_base[0]]

    def test_above_junk_fraction_still_falls_back_to_production_if_filtered_reads_no_better(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Junk-dominated (90% unread) does not override the production comparison itself -- if the
        few surviving sub-1.0 reads don't actually beat production, production still wins, same as
        the non-junk-fraction tie-break above.
        """
        sub_base = [(float(i * 10), float(i * 10), 5.0, 0.9) for i in range(10)]
        production = [(999.0, 999.0, 5.0, 0.9)]
        per_multiplier = [(0.5, []), (1.0, production)]

        import rogaine.vision.ocr as ocr_module
        from rogaine.vision.controls import _ocr_gate_sub_base_scale

        monkeypatch.setattr(
            ocr_module,
            "read_control_numbers",
            self._stub_reading({tuple(c[0] for c in sub_base): 1, (999.0,): 1}),
        )

        result = _ocr_gate_sub_base_scale(
            np.zeros((10, 10, 3), dtype=np.uint8), 200.0, default_config(), per_multiplier, sub_base
        )
        assert result == production

    def test_exactly_at_the_junk_fraction_line_is_not_junk_dominated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Boundary case (review finding M2): 17 of 20 candidates unread is exactly 85% --
        `_SUB_BASE_JUNK_UNREAD_FRACTION` itself -- which must land on the "keep whole" side, per
        the constant's own "more than this fraction" wording (`_ocr_gate_sub_base_scale`'s
        docstring: "strictly more than that fraction unread ... assumed junk-dominated"). A set
        landing exactly on the line is treated as not-yet-junk.
        """
        sub_base = [(float(i * 10), float(i * 10), 5.0, 0.9) for i in range(20)]
        production = [(999.0, 999.0, 5.0, 0.9)]
        per_multiplier = [(0.5, []), (1.0, production)]

        import rogaine.vision.ocr as ocr_module
        from rogaine.vision.controls import _ocr_gate_sub_base_scale

        monkeypatch.setattr(
            ocr_module,
            "read_control_numbers",
            # 3 of 20 read -> 17/20 = 0.85 exactly unread.
            self._stub_reading({tuple(c[0] for c in sub_base): 3, (999.0,): 0}),
        )

        result = _ocr_gate_sub_base_scale(
            np.zeros((10, 10, 3), dtype=np.uint8), 200.0, default_config(), per_multiplier, sub_base
        )
        assert result == sub_base

    def test_no_production_all_unread_and_junk_dominated_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Review finding M4: with no production side to fall back to and every sub-1.0 candidate
        unread (100%, above the junk line), the deliberate result is an empty list -- a map whose
        only Hough hits are entirely unread junk (e.g. a cover page with no real controls at all)
        contributes nothing, rather than surfacing a whole page of unread false positives.
        """
        sub_base = [(float(i * 10), float(i * 10), 5.0, 0.9) for i in range(10)]
        per_multiplier = [(0.5, sub_base), (1.0, [])]

        import rogaine.vision.ocr as ocr_module
        from rogaine.vision.controls import _ocr_gate_sub_base_scale

        monkeypatch.setattr(
            ocr_module,
            "read_control_numbers",
            self._stub_reading({tuple(c[0] for c in sub_base): 0}),
        )

        result = _ocr_gate_sub_base_scale(
            np.zeros((10, 10, 3), dtype=np.uint8), 200.0, default_config(), per_multiplier, sub_base
        )
        assert result == []


class TestHubTriangleIgnoresSubBaseScaleRungs:
    """T090/ADR-031 (independent review finding H1): `_detect_hub_triangle` must not sweep the
    sub-1.0 rungs (`0.5`/`0.85`) T090 added to `circle_scale_multipliers` for circle detection --
    there is no measured evidence anywhere in this project's corpus of an undersized hub triangle,
    and sweeping them anyway shrinks `max_diff`'s absolute tolerance band, which measurably turned a
    correct "no hub found" into a spurious low-confidence match on a real scan
    (`history-race-primorsk`, found during independent review). Regression-tested here with a
    synthetic adversarial contour sized to match only a sub-1.0 window, never a real hub.
    """

    def test_a_contour_matching_only_a_sub_base_scale_window_is_not_picked_up_as_the_hub(
        self,
    ) -> None:
        from rogaine.vision.controls import _TRIANGLE_SIDE_TO_RADIUS, _detect_hub_triangle

        dpi = 200.0
        config = default_config()
        det = config.detector
        base_r_min, base_r_max = det.circle_radius_px(dpi)
        base_r_mid = (base_r_min + base_r_max) / 2.0

        # A triangle whose side length matches the *0.5* window's expected_side exactly (diff=0,
        # the best possible fit at that rung). With tol=0.35, 0.5's own band is
        # [0.715, 1.485] * base_r_mid, while 1.0's band is [1.43, 2.97] * base_r_mid -- this side
        # (1.1 * base_r_mid) sits well outside every `>=1.0` rung's band, no overlap.
        side = base_r_mid * 0.5 * _TRIANGLE_SIDE_TO_RADIUS
        size = round(side * 6)
        cx = cy = size // 2
        half = side / (3**0.5)
        pts = np.array(
            [
                [cx, cy - half],
                [cx - side / 2, cy + half / 2],
                [cx + side / 2, cy + half / 2],
            ],
            dtype=np.int32,
        )
        image = np.full((size, size, 3), 255, dtype=np.uint8)
        cv2.fillPoly(image, [pts], RENDER_SRGB["purple_100"])

        mask = purple_mask(image, config)
        hub = _detect_hub_triangle(mask, dpi, config)

        assert hub is None, (
            f"a contour sized for a sub-1.0-only window should not be picked up as the hub, "
            f"got {hub}"
        )
