"""Segmentation orchestration, `terrain.npz` round-trip, and per-class IoU (T016).

DoD: `segment()` produces a `TerrainMap`; `terrain.npz` round-trips; `iou_report` is printed per
class (this module tests the string-returning `format_iou_report`, not a live `print()`).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from scipy.sparse.csgraph import connected_components

from rogaine.config import default_config
from rogaine.cost.field import compute_cost_field
from rogaine.cost.graph import build_grid_graph
from rogaine.io.raster import load_raster, resolve_dpi
from rogaine.io.scale import mpp_from_dpi
from rogaine.models import TERRAIN_ORDER, TerrainClass, TerrainMap, terrain_label
from rogaine.vision.contours import contour_density
from rogaine.vision.linear import extract_linear_features
from rogaine.vision.normalize import normalize
from rogaine.vision.palette import classify_palette
from rogaine.vision.segment import (
    format_iou_report,
    iou_report,
    load_terrain_map,
    reclassify_grid_ink,
    save_terrain_map,
    segment,
)

#: I1 (docs/iterations/I1-real-scan-vision.md): same real scan and skip-if-absent convention as
#: `test_controls.py` -- gitignored per ADR-010, present only on machines the owner handed it to.
_REAL_SCAN_DIR = Path(__file__).resolve().parents[3] / "data" / "maps" / "grid-lines-red-controls"
_REAL_SCAN_PATH = _REAL_SCAN_DIR / "map.jpeg"

#: T101 (I6, `docs/iterations/I6-real-map-detection-gaps-and-viewer-ux.md`): same skip-if-absent
#: convention, a different real scan whose river fragments into thousands of tiny
#: `water_uncrossable` islands inside an otherwise `water_shallow` blob (see
#: `_consolidate_banked_water`'s own docstring in `vision/palette.py` for the measured mechanism).
_OGPS_6802_DIR = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "maps"
    / "ogps-6802_4a769f64b455f9b4675552284c3681b1"
)
_OGPS_6802_PATH = _OGPS_6802_DIR / "map.jpg"

#: T109 (I7, ADR-036): a third real scan carrying three genuine ISOM 709 out-of-bounds polygons
#: (this map's own control circles print red, not purple) whose hatched interiors leaked through
#: as whatever terrain prints in the gaps between hatch lines -- see
#: `_close_out_of_bounds_regions`'s own docstring in `vision/palette.py` for the measured mechanism.
_OGPS_8620_DIR = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "maps"
    / "ogps-8620_502cda4f6c774e8ecb86d063a71895f6"
)
_OGPS_8620_PATH = _OGPS_8620_DIR / "map.jpg"

# Same list, same reason as `test_palette.py`'s `AREA_CLASSES`: the 11 ISOM area classes with a
# unique shade -- the ones a colour classifier alone should nail on the clean fixture render.
AREA_CLASSES: tuple[TerrainClass, ...] = (
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


class TestSegmentEndToEnd:
    def test_produces_a_valid_terrain_map(self, clean_synthetic_map) -> None:
        sm = clean_synthetic_map
        cfg = default_config()

        terrain_map = segment(sm.image, sm.dpi, sm.meters_per_pixel, cfg)

        assert isinstance(terrain_map, TerrainMap)
        assert terrain_map.shape == sm.shape
        assert terrain_map.labels.dtype == np.uint8
        assert terrain_map.labels.max() < len(TERRAIN_ORDER)
        assert terrain_map.contour_density.dtype == np.float32
        assert terrain_map.contour_density.shape == terrain_map.labels.shape
        assert terrain_map.contour_density.min() >= 0.0
        assert terrain_map.contour_density.max() <= 1.0
        assert terrain_map.meters_per_pixel == sm.meters_per_pixel


class TestSegmentInputValidation:
    def test_rejects_non_positive_dpi(self) -> None:
        image = np.zeros((10, 10, 3), dtype=np.uint8)
        with pytest.raises(ValueError, match="dpi"):
            segment(image, 0.0, 2.5)


class TestReclassifyGridInk:
    """T074, F20, ADR-012: a shape-based carve-out for grid/border ink misread as water. Uses
    small hand-built label arrays (not the fixture, which has no grid lines at all -- see
    `TestIouReportOnFixture` for the fixture-level non-regression check) at ``dpi=100.0``, so
    ``GridSettings.max_line_width_px(100.0)`` (``config/default.toml``'s ``max_line_width_mm =
    6.0``) is ``6.0 * 100 / 25.4`` ~= 23.6px, and ``min_elongation_ratio`` is ``10.0``.
    """

    _H, _W = 100, 60
    _OPEN = terrain_label(TerrainClass.OPEN_LAND)
    _ROAD = terrain_label(TerrainClass.ROAD)
    _WU = terrain_label(TerrainClass.WATER_UNCROSSABLE)
    _WS = terrain_label(TerrainClass.WATER_SHALLOW)
    _UNKNOWN = terrain_label(TerrainClass.UNKNOWN)

    def _blank(self) -> np.ndarray:
        return np.full((self._H, self._W), self._OPEN, dtype=np.uint8)

    def test_thin_full_height_column_becomes_unknown(self) -> None:
        labels = self._blank()
        labels[:, 10] = self._WU  # 100% of height, 1px wide -- a grid/magnetic-north line

        out = reclassify_grid_ink(labels, dpi=100.0)

        assert np.all(out[:, 10] == self._UNKNOWN)
        assert np.array_equal(np.delete(out, 10, axis=1), np.delete(labels, 10, axis=1))

    def test_thin_full_width_row_becomes_unknown(self) -> None:
        labels = self._blank()
        labels[50, :] = self._WS  # 100% of width, 1px tall -- a border rule

        out = reclassify_grid_ink(labels, dpi=100.0)

        assert np.all(out[50, :] == self._UNKNOWN)
        assert np.array_equal(np.delete(out, 50, axis=0), np.delete(labels, 50, axis=0))

    def test_compact_water_body_below_the_span_threshold_is_untouched(self) -> None:
        labels = self._blank()
        labels[40:61, 5:16] = self._WU  # 21/100 = 0.21 of height, well under span_fraction_min

        out = reclassify_grid_ink(labels, dpi=100.0)

        assert np.array_equal(out, labels)

    def test_wide_span_clearing_run_is_rejected_by_the_width_cap(self) -> None:
        """A lake wide enough to also clear `span_fraction_min` in every one of its columns must
        not be caught -- `max_line_width_mm` is exactly the guard the DoD's non-negotiable
        ("a real water body must still classify as water_uncrossable") needs. 50px is chosen to be
        both well over `max_line_width_px(100.0)` (~23.6px) and, unlike a real 1-3px grid line,
        obviously not a printed line.
        """
        labels = self._blank()
        labels[0:30, 0:50] = self._WU  # 30/100 = 0.30 of height (clears 0.25), 50px wide (> cap)

        out = reclassify_grid_ink(labels, dpi=100.0)

        assert np.array_equal(out, labels)

    def test_narrower_than_the_width_cap_but_not_elongated_is_untouched(self) -> None:
        """`max_line_width_mm` alone is an *absolute* size: on this 100px-tall array it would
        accept anything under ~23.6px wide even though a 20px-wide run is nowhere near
        line-shaped (elongation 100/20 = 5.0, under `min_elongation_ratio`'s 10.0). This is the
        gap `min_elongation_ratio` closes -- a run this squarish must stay real terrain regardless
        of the image's absolute size.
        """
        labels = self._blank()
        labels[0:30, 0:20] = self._WU  # 30% of height (clears 0.25), 20px wide (under the mm cap)

        out = reclassify_grid_ink(labels, dpi=100.0)

        assert np.array_equal(out, labels)

    def test_only_water_pixels_in_a_flagged_column_are_touched(self) -> None:
        """A non-water pixel sitting inside an otherwise-water grid column keeps its own label --
        the reclassification follows the water mask, not the column's bounding box (the same
        "rejected components become `unknown` at exactly their own pixels" discipline
        `extract_linear_features` already follows).
        """
        labels = self._blank()
        labels[:, 10] = self._WU
        labels[7, 10] = self._ROAD  # one foreign pixel inside the flagged column

        out = reclassify_grid_ink(labels, dpi=100.0)

        assert out[7, 10] == self._ROAD
        assert np.all(np.delete(out[:, 10], 7) == self._UNKNOWN)

    def test_rejects_non_2d_labels(self) -> None:
        with pytest.raises(ValueError, match="H, W"):
            reclassify_grid_ink(np.zeros((4, 4, 3), dtype=np.uint8), 100.0)

    def test_rejects_non_uint8_labels(self) -> None:
        with pytest.raises(ValueError, match="uint8"):
            reclassify_grid_ink(np.zeros((4, 4), dtype=np.int32), 100.0)

    def test_rejects_non_positive_dpi(self) -> None:
        with pytest.raises(ValueError, match="dpi"):
            reclassify_grid_ink(np.zeros((4, 4), dtype=np.uint8), 0.0)


class TestGridInkOnRealScan:
    """I1, F20's acceptance clause: on `data/maps/grid-lines-red-controls/map.jpeg`, whose 8 grid
    columns measured >30% `water_uncrossable`/`water_shallow` over their height before this task
    (`docs/STATUS.md`), each must drop to ~0% once `segment()` runs `reclassify_grid_ink`.
    """

    @pytest.mark.skipif(
        not _REAL_SCAN_PATH.is_file(),
        reason="data/maps/grid-lines-red-controls/map.jpeg absent (ADR-010: gitignored real scan)",
    )
    def test_known_grid_columns_drop_to_near_zero_water_fraction(self) -> None:
        with (_REAL_SCAN_DIR / "meta.toml").open("rb") as fh:
            meta = tomllib.load(fh)
        dpi = float(meta["dpi"])

        image = np.array(Image.open(_REAL_SCAN_PATH).convert("RGB"))
        cfg = default_config()
        terrain_map = segment(image, dpi, meters_per_pixel=1.0, config=cfg)

        wu = terrain_label(TerrainClass.WATER_UNCROSSABLE)
        ws = terrain_label(TerrainClass.WATER_SHALLOW)
        height = terrain_map.labels.shape[0]

        # Measured pre-fix (docs/STATUS.md, ADR-012): these 8 columns ranged 0.338-0.898.
        known_grid_columns = [142, 339, 535, 928, 1128, 1520, 1716, 2112]
        for x in known_grid_columns:
            column = terrain_map.labels[:, x]
            frac = float(((column == wu) | (column == ws)).sum() / height)
            assert frac < 0.05, f"column x={x}: water fraction {frac:.3f}, expected ~0"

    @pytest.mark.skipif(
        not _REAL_SCAN_PATH.is_file(),
        reason="data/maps/grid-lines-red-controls/map.jpeg absent (ADR-010: gitignored real scan)",
    )
    def test_routable_graph_is_far_less_fragmented(self) -> None:
        """I1's exit criterion 3 ("a plan across one of those columns no longer fails with 'no
        reachable route'") in the terms the graph solver actually reasons in: connected components
        of the routable graph, not one hand-picked hub/control pair -- at `graph.downsample`'s
        default block size, `_aggregate_blocks`' own "passable iff at least one passable pixel"
        rule (T031) already bridges most individual gaps in a partially-fragmented column, so a
        pair straddling any one column may or may not disconnect depending on exactly where it
        sits; the graph-wide component count is what the misclassification actually damages, and
        what this fix actually repairs, regardless of which two points a route happens to use.
        Measured on this scan (`docker compose run --rm tests`, this session): 9463 components pre-
        fix (largest 244595/254065 nodes, 96.3%) vs 580 post-fix (largest 253486/254065, 99.8%).
        """
        with (_REAL_SCAN_DIR / "meta.toml").open("rb") as fh:
            meta = tomllib.load(fh)
        dpi = float(meta["dpi"])
        image = np.array(Image.open(_REAL_SCAN_PATH).convert("RGB"))
        cfg = default_config()

        normalized = normalize(image)
        palette_labels = classify_palette(normalized, cfg)
        pre_labels = extract_linear_features(palette_labels, dpi, cfg)
        pre_terrain = TerrainMap(
            labels=pre_labels,
            contour_density=contour_density(pre_labels, dpi, cfg),
            meters_per_pixel=1.0,
        )
        post_terrain = segment(image, dpi, meters_per_pixel=1.0, config=cfg)

        def _n_components_and_giant_fraction(terrain: TerrainMap) -> tuple[int, float]:
            cost_field = compute_cost_field(terrain, base_speed_mps=2.0, config=cfg)
            graph = build_grid_graph(cost_field, config=cfg)
            n_components, comp_labels = connected_components(graph.csr, directed=False)
            giant_fraction = float(np.bincount(comp_labels).max() / graph.csr.shape[0])
            return n_components, giant_fraction

        pre_n, _pre_giant = _n_components_and_giant_fraction(pre_terrain)
        post_n, post_giant = _n_components_and_giant_fraction(post_terrain)

        assert post_n < pre_n / 5, f"post-fix components {post_n} not far below pre-fix {pre_n}"
        assert post_giant >= 0.99, f"post-fix giant component only {post_giant:.3f} of all nodes"


class TestBankedWaterConsolidationOnRealScan:
    """T101, SPEC F4 (I6): on `ogps-6802`, the printed river's ink sits close enough to both
    `water_shallow`/`water_uncrossable` shades (and to real scan noise) that `classify_labels`'s
    per-pixel nearest-shade choice fragments one continuous, bank-lined river into thousands of
    tiny `water_uncrossable` islands inside an otherwise `water_shallow` (passable) blob -- not
    nearly enough of it to block a route (`docs/TASKS.md` T101's own landed account measured this
    directly: the river's largest single fragment was 341px against a river thousands of pixels
    long).
    `_consolidate_banked_water` promotes a whole water blob once its own boundary is
    substantially bank-lined; this pins that it does so for the real river without swallowing a
    real hatched/screened marsh nearby that has no such bank line.
    """

    @pytest.mark.skipif(
        not _OGPS_6802_PATH.is_file(),
        reason="data/maps/ogps-6802.../map.jpg absent (ADR-010: gitignored real scan)",
    )
    def test_river_core_uncrossable_marsh_stays_shallow(self) -> None:
        # No meta.toml dpi trusted here (`calibration_source = "assumed_default"`, ADR-016) --
        # `resolve_dpi`'s own probe/fallback, matching what a real `rogaine plan` invocation
        # without `--dpi` actually resolves (same convention as `test_ocr.py`'s own maps without a
        # measured meta.toml).
        dpi = resolve_dpi(_OGPS_6802_PATH, user_dpi=None)
        image = load_raster(_OGPS_6802_PATH, dpi=dpi)
        cfg = default_config()
        labels = classify_palette(normalize(image), cfg)

        wu = terrain_label(TerrainClass.WATER_UNCROSSABLE)
        ws = terrain_label(TerrainClass.WATER_SHALLOW)

        # Measured: (948, 1597) is the fragmented river's own deepest interior point (max
        # distance from its pre-fix boundary, `cv2.distanceTransform`) -- a small box centred on
        # it sits entirely inside the river's true width, clear of the bank on every side.
        river_core = labels[1592:1602, 943:953]
        assert (river_core == wu).all(), (
            f"river core not fully water_uncrossable: "
            f"wu={int((river_core == wu).sum())}/{river_core.size}"
        )

        # Measured: this bbox holds a hatched/screened marsh with no adjacent black bank line
        # (visually confirmed crop) -- `_consolidate_banked_water` must not bulk-promote it just
        # because it is a water-shaded blob near other bank-lined water elsewhere on the map.
        marsh = labels[1950:2200, 2350:2700]
        marsh_wu = int((marsh == wu).sum())
        marsh_ws = int((marsh == ws).sum())
        assert marsh_ws > 10 * marsh_wu, (
            f"marsh over-promoted: wu={marsh_wu} ws={marsh_ws}, expected mostly shallow"
        )

    @pytest.mark.skipif(
        not _OGPS_6802_PATH.is_file(),
        reason="data/maps/ogps-6802.../map.jpg absent (ADR-010: gitignored real scan)",
    )
    def test_river_core_is_impassable_in_the_routing_graph(self) -> None:
        """DoD: `rogaine plan` on this map no longer routes through the river -- checked at the
        actual mechanism the solver relies on (same precedent as T103's own out-of-bounds
        confirmation) rather than by solving a full route: `solve_heuristic`'s GRASP search has a
        real wall-clock time budget (`RunConfig.heuristic_time_budget_s`), so which specific tour
        it returns is not itself deterministic run-to-run (measured: 3 identical runs produced
        89px/59px/162px of incidental route-line overlap with unrelated map ink even before this
        distinction, an unusable regression signal). `GridGraph.block_passable` is the
        deterministic ground truth `_build_edges` actually reads: a block with no passable pixel
        gets no edge at all under `strict_impassable` (the config default), so no route -- of any
        quality, found by any solver -- can ever cross it. The DoD's own fallback text agrees
        ("confirm ... no code change expected") once the terrain is classified correctly.
        """
        dpi = resolve_dpi(_OGPS_6802_PATH, user_dpi=None)
        image = load_raster(_OGPS_6802_PATH, dpi=dpi)
        cfg = default_config()
        assert cfg.graph.strict_impassable, "test assumes the strict_impassable default"

        terrain_map = segment(image, dpi, meters_per_pixel=mpp_from_dpi(dpi, 20000), config=cfg)
        cost_field = compute_cost_field(terrain_map, base_speed_mps=2.0, config=cfg)
        graph = build_grid_graph(cost_field, cfg)

        # Measured: (948, 1597) is the fragmented river's own deepest interior point (max
        # distance from its pre-fix boundary) -- solidly inside the river's true width on every
        # side, so its containing block cannot pick up a passable neighbour pixel.
        block_row, block_col = 1597 // graph.downsample, 948 // graph.downsample
        assert not graph.block_passable[block_row, block_col], (
            "river core block is passable in the routing graph -- a route could still cross it"
        )


class TestOutOfBoundsClosureOnRealScan:
    """T109, SPEC F4, ADR-036 (I7): on `ogps-8620`, `classify_labels`'s raw hatch-ink density
    inside the largest of this map's three real ISOM 709 out-of-bounds polygons is only 56.75% --
    the rest is `unknown`/`forest_runnable`/etc., whatever colour prints between the hatch lines
    (T108's own measured breakdown; confirmed unchanged here as the RAW figure below). Pre-fix,
    `cost/graph.py`'s any-passable-pixel block rule then made 84.26% of the graph blocks
    overlapping this interior block-passable -- a route could cross straight through. This pins
    that `_close_out_of_bounds_regions` (wired into `classify_palette` ahead of
    `_consolidate_banked_water`/`fill_unknown`) makes the whole interior classify consistently
    `out_of_bounds` and impassable, both at the pixel level and in the routing graph.
    """

    @pytest.mark.skipif(
        not _OGPS_8620_PATH.is_file(),
        reason="data/maps/ogps-8620.../map.jpg absent (ADR-010: gitignored real scan)",
    )
    def test_polygon_interior_probe_point_is_out_of_bounds(self) -> None:
        dpi = resolve_dpi(_OGPS_8620_PATH, user_dpi=None)
        image = load_raster(_OGPS_8620_PATH, dpi=dpi)
        cfg = default_config()
        labels = classify_palette(normalize(image), cfg, dpi)

        oob = terrain_label(TerrainClass.OUT_OF_BOUNDS)

        # Measured (`data/maps/_t109_measure_oob.py`): (2357, 1761) is the largest polygon's own
        # deepest interior point (max distance from its boundary, ~118px in) -- a small box
        # centred on it sits entirely inside the polygon, clear of the hatch/paper edge on every
        # side, and clear of the residual `forest_runnable` gaps RAW classification leaves there.
        probe = labels[1756:1766, 2352:2362]
        assert (probe == oob).all(), (
            f"interior probe not fully out_of_bounds: "
            f"oob={int((probe == oob).sum())}/{probe.size}"
        )

    @pytest.mark.skipif(
        not _OGPS_8620_PATH.is_file(),
        reason="data/maps/ogps-8620.../map.jpg absent (ADR-010: gitignored real scan)",
    )
    def test_polygon_interior_is_impassable_in_the_routing_graph(self) -> None:
        """DoD: `rogaine plan`/`detect` on this map no longer routes through the polygon --
        checked at `GridGraph.block_passable`, the deterministic ground truth `_build_edges`
        actually reads (same precedent as T101's and T103's own real-scan graph confirmations),
        rather than by solving a full route and hoping its non-deterministic GRASP search happens
        to avoid the polygon.
        """
        dpi = resolve_dpi(_OGPS_8620_PATH, user_dpi=None)
        image = load_raster(_OGPS_8620_PATH, dpi=dpi)
        cfg = default_config()
        assert cfg.graph.strict_impassable, "test assumes the strict_impassable default"

        terrain_map = segment(image, dpi, meters_per_pixel=mpp_from_dpi(dpi, 24000), config=cfg)
        cost_field = compute_cost_field(terrain_map, base_speed_mps=2.0, config=cfg)
        graph = build_grid_graph(cost_field, cfg)

        # Same deepest-interior-point measurement as the pixel-level test above, reduced to its
        # containing block.
        block_row, block_col = 1761 // graph.downsample, 2357 // graph.downsample
        assert not graph.block_passable[block_row, block_col], (
            "polygon interior block is passable in the routing graph -- a route could still "
            "cross it"
        )


class TestIouReportOnFixture:
    """`iou_report` measured on the same fixture and with the same sampleable exclusions
    `test_palette.py`'s `TestPaletteIoUAgainstFixture` and `test_linear.py`'s
    `TestSubClassAccuracyOnFixture` already establish: contour overprint, black text/point-symbol
    noise, and out-of-bounds hatching are excluded from every class's sampled pixels.

    Measured on the *degraded* fixture (`synthetic_map`, not `clean_synthetic_map`), on purpose:
    `segment()` always runs `normalize()` (module docstring), and `test_normalize.py`'s own
    `TestNormalizeRecoversTheCleanRender` docstring records that grey-world white balance run on
    an already-clean, zero-tint render makes area classes match the classifier's true CMYK
    palette *worse*, not better -- confirmed here too (measured min area-class IoU on the clean
    render via `segment()`: 0.16, well under `test_palette.py`'s 0.95, which is measured
    *without* `normalize()` in the loop). The degraded render is the realistic case `segment()`
    exists for, and is the same fixture/floor style `test_palette.py`'s own
    `test_area_classes_after_normalize_on_the_degraded_render` already uses for a
    normalize+classify pipeline: a mean, not a per-class min (that test's own reasoning: a couple
    of small-area classes swing a lot on JPEG blockiness alone, so a `min` bound really bounds
    whichever class the degradation hit hardest, not the pipeline). Floor set to that same 0.60,
    not a fresh number -- same fixture, same normalize+classify composition for the area classes
    (measured here: 0.63).
    """

    def test_area_class_mean_iou_floor_on_the_degraded_render(self, synthetic_map) -> None:
        sm = synthetic_map
        cfg = default_config()
        oob_lbl = terrain_label(TerrainClass.OUT_OF_BOUNDS)
        sampleable = ~sm.contour_mask & (sm.labels != oob_lbl) & ~sm.noise_mask

        terrain_map = segment(sm.image, sm.dpi, sm.meters_per_pixel, cfg)
        report = iou_report(terrain_map.labels, sm.labels, sampleable=sampleable)

        area_ious = [report[cls] for cls in AREA_CLASSES]
        mean_iou = sum(area_ious) / len(area_ious)
        formatted = format_iou_report(report)
        assert mean_iou >= 0.60, f"mean area-class IoU below floor:\n{formatted}"


class TestTerrainNpzRoundTrip:
    def test_labels_density_and_scale_survive_exactly(self, tmp_path) -> None:
        rng = np.random.default_rng(0)
        labels = rng.integers(0, len(TERRAIN_ORDER), size=(37, 53), dtype=np.uint8)
        density = rng.random((37, 53)).astype(np.float32)
        terrain_map = TerrainMap(labels=labels, contour_density=density, meters_per_pixel=2.54321)

        path = tmp_path / "terrain.npz"
        save_terrain_map(path, terrain_map)
        loaded = load_terrain_map(path)

        assert np.array_equal(loaded.labels, terrain_map.labels)
        assert loaded.labels.dtype == np.uint8
        assert np.array_equal(loaded.contour_density, terrain_map.contour_density)
        assert loaded.contour_density.dtype == np.float32
        assert loaded.meters_per_pixel == terrain_map.meters_per_pixel
        assert isinstance(loaded.meters_per_pixel, float)


class TestIouReport:
    def test_perfect_match_scores_one_for_every_class(self) -> None:
        labels = np.array([[0, 1], [2, 3]], dtype=np.uint8)
        report = iou_report(labels, labels)
        assert set(report.keys()) == set(TERRAIN_ORDER)
        assert all(v == 1.0 for v in report.values())

    def test_disjoint_prediction_and_truth_scores_zero_only_for_the_involved_classes(self) -> None:
        pred = np.full((4, 4), terrain_label(TerrainClass.OPEN_LAND), dtype=np.uint8)
        truth = np.full((4, 4), terrain_label(TerrainClass.WATER_SHALLOW), dtype=np.uint8)

        report = iou_report(pred, truth)

        assert report[TerrainClass.OPEN_LAND] == 0.0
        assert report[TerrainClass.WATER_SHALLOW] == 0.0
        assert report[TerrainClass.MARSH] == 1.0  # absent from both: vacuous agreement

    def test_sampleable_mask_excludes_pixels_from_every_class(self) -> None:
        pred = np.full((4, 4), terrain_label(TerrainClass.OPEN_LAND), dtype=np.uint8)
        truth = pred.copy()
        truth[0, 0] = terrain_label(TerrainClass.MARSH)  # a disagreement...
        sampleable = np.ones((4, 4), dtype=bool)
        sampleable[0, 0] = False  # ...excluded from sampling

        report = iou_report(pred, truth, sampleable=sampleable)

        assert report[TerrainClass.OPEN_LAND] == 1.0
        assert report[TerrainClass.MARSH] == 1.0  # no sampled pixel is MARSH in either raster

    def test_rejects_mismatched_shapes(self) -> None:
        with pytest.raises(ValueError, match="shape"):
            iou_report(np.zeros((4, 4), dtype=np.uint8), np.zeros((5, 5), dtype=np.uint8))


class TestFormatIouReport:
    def test_one_line_per_class_with_four_decimal_places(self) -> None:
        report = {TerrainClass.OPEN_LAND: 0.98, TerrainClass.MARSH: 1.0}
        assert format_iou_report(report).splitlines() == ["open_land: 0.9800", "marsh: 1.0000"]
