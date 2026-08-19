"""Config loading and the ISOM colour derivation (T003)."""

from __future__ import annotations

import numpy as np
import pytest

from fixtures.synth_map import RENDER_SRGB, SHADE_OF
from rogaine.config import DEFAULT_CONFIG_PATH, cmyk_to_srgb, default_config, load_config
from rogaine.models import TERRAIN_ORDER, TerrainClass, terrain_label


class TestCmykConversion:
    @pytest.mark.parametrize(
        ("cmyk", "expected"),
        [
            ((0, 0, 0, 0), (255, 255, 255)),
            ((0, 0, 0, 100), (0, 0, 0)),
            ((100, 0, 0, 0), (0, 174, 239)),  # process cyan
            ((0, 100, 0, 0), (236, 0, 140)),  # process magenta
            ((0, 0, 100, 0), (255, 241, 0)),  # process yellow
        ],
    )
    def test_primaries(self, cmyk: tuple[float, ...], expected: tuple[int, int, int]) -> None:
        assert cmyk_to_srgb(*cmyk) == expected

    def test_isom_yellow_is_a_warm_orange_yellow(self) -> None:
        # ISOM yellow is 0/27/79/0 [IOF Appendix 1 section 4].
        r, g, b = cmyk_to_srgb(0, 27, 79, 0)
        assert (r, g, b) == pytest.approx((250, 178, 47), abs=1)

    def test_isom_purple_is_purple_not_blue(self) -> None:
        # The textbook conversion renders 35/85/0/0 with a blue channel of 255, which would put the
        # control circles nearer to blue than to purple. This is the regression guard for that.
        r, g, b = cmyk_to_srgb(35, 85, 0, 0)
        assert (r, g, b) == pytest.approx((155, 34, 154), abs=1)
        assert b < 200

    def test_rejects_values_outside_the_percentage_range(self) -> None:
        with pytest.raises(ValueError, match="percentage"):
            cmyk_to_srgb(0, 0, 0, 120)


class TestDefaultConfig:
    def test_ships_and_loads(self) -> None:
        assert DEFAULT_CONFIG_PATH.is_file()
        assert default_config() is default_config()  # cached

    def test_covers_every_terrain_class(self) -> None:
        cfg = load_config()
        assert {t.name for t in cfg.terrain} == set(TerrainClass)

    def test_impassable_terrain_has_no_speed(self) -> None:
        cfg = load_config()
        for cls in (TerrainClass.WATER_UNCROSSABLE, TerrainClass.OUT_OF_BOUNDS):
            spec = cfg.terrain_of(cls)
            assert not spec.passable and spec.speed_factor == 0.0

    def test_road_is_the_speed_baseline(self) -> None:
        # v_base is defined as road speed, so the road factor must be exactly 1.
        assert load_config().terrain_of(TerrainClass.ROAD).speed_factor == 1.0

    def test_vegetation_ordering_follows_isom_runnability(self) -> None:
        # ISOM 406 60-80%, 408 20-60%, 410 under 20% — of forest speed, in that order.
        cfg = load_config()
        forest = cfg.terrain_of(TerrainClass.FOREST_RUNNABLE).speed_factor
        slow = cfg.terrain_of(TerrainClass.VEG_SLOW_RUN).speed_factor
        walk = cfg.terrain_of(TerrainClass.VEG_WALK).speed_factor
        fight = cfg.terrain_of(TerrainClass.VEG_FIGHT).speed_factor
        assert forest > slow > walk > fight > 0.0

    def test_arrays_are_indexed_by_terrain_label(self) -> None:
        cfg = load_config()
        speeds = cfg.speed_factors()
        passable = cfg.passability()
        assert speeds.shape == passable.shape == (len(TERRAIN_ORDER),)
        assert speeds[terrain_label(TerrainClass.ROAD)] == np.float32(1.0)
        assert not passable[terrain_label(TerrainClass.WATER_UNCROSSABLE)]


class TestOverrides:
    def test_overrides_merge_without_restating_the_file(self, tmp_path) -> None:
        user = tmp_path / "user.toml"
        user.write_text('[solver]\nheuristic_time_budget_s = 5.0\n', encoding="utf-8")
        cfg = load_config(user)
        assert cfg.solver.heuristic_time_budget_s == 5.0
        assert cfg.solver.grasp_restarts == load_config().solver.grasp_restarts

    def test_dict_overrides_win_over_the_file(self, tmp_path) -> None:
        user = tmp_path / "user.toml"
        user.write_text('[rules]\npenalty_per_min = 2.0\n', encoding="utf-8")
        cfg = load_config(user, overrides={"rules": {"penalty_per_min": 9.0}})
        assert cfg.rules.penalty_per_min == 9.0

    def test_missing_file_is_an_error_not_a_silent_default(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nope.toml")


class TestDetectorGeometry:
    def test_circle_radius_comes_from_dpi_alone(self) -> None:
        # ISOM 703 is 6 mm on paper; at 300 dpi that is 35.4 px radius, whatever the map scale.
        det = load_config().detector
        lo, hi = det.circle_radius_px(300.0)
        assert lo < 35.43 < hi
        # Doubling the resolution doubles the circle.
        lo2, hi2 = det.circle_radius_px(600.0)
        assert lo2 == pytest.approx(lo * 2) and hi2 == pytest.approx(hi * 2)


class TestPaletteSeparation:
    """The palette must be able to tell the fixture's colours apart.

    This runs in M0, before the classifier exists, because it is the assumption T013 is built on:
    the shades derived from published CMYK must each be the nearest match for the corresponding
    real printed colour. If this fails, no amount of classifier code will fix it — the palette is
    wrong.
    """

    def test_every_rendered_shade_matches_its_own_nominal_shade(self) -> None:
        table = load_config().palette.srgb_table()
        names = list(table)
        nominal = np.array([table[n] for n in names], dtype=np.float64)

        mismatches = []
        for shade_name, rendered in RENDER_SRGB.items():
            d = np.linalg.norm(nominal - np.array(rendered, dtype=np.float64), axis=1)
            nearest = names[int(np.argmin(d))]
            if nearest != shade_name:
                mismatches.append(f"{shade_name} rendered as {rendered} matched {nearest}")
        assert not mismatches, "; ".join(mismatches)

    def test_fixture_and_config_agree_on_which_shade_each_terrain_uses(self) -> None:
        cfg = load_config()
        for cls, shade in SHADE_OF.items():
            if cls is TerrainClass.UNKNOWN:
                continue  # the fixture paints unknown as forest white; the config declares no shade
            assert cfg.terrain_of(cls).shade == shade, f"{cls} disagrees"
