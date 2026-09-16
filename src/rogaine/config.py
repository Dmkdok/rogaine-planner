"""Configuration loading, and the ISOM colour table it carries.

One TOML file holds every tunable in the product (SPEC F18). This module loads it, validates that
it covers exactly the terrain contract in :mod:`rogaine.models`, and derives the sRGB palette that
the segmenter matches pixels against.

The colour derivation is deliberately explicit rather than a table of hand-typed RGB values: the
authoritative numbers published by the IOF are CMYK, so those are what the config stores, and
:func:`cmyk_to_srgb` turns them into screen colours in one auditable place.
"""

from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from rogaine.models import TERRAIN_ORDER, TerrainClass

#: Repo-root config, the one shipped default.
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "default.toml"

#: Environment override, mostly for tests and for Docker mounts.
CONFIG_ENV_VAR = "ROGAINE_CONFIG"


#: sRGB appearance of each process ink at full strength. These are the standard screen renderings
#: of process cyan, magenta and yellow — the same anchors print-preview conversions use. They matter
#: because the textbook conversion (``255 * (1 - c)``) renders 100% cyan as pure ``#00FFFF``, which
#: is nowhere near the blue on a real orienteering map, and ISOM purple as ``#A626FF``, which would
#: put the control circles closer to blue than to purple.
_INK_PRIMARIES: dict[str, tuple[float, float, float]] = {
    "c": (0.0, 174 / 255, 239 / 255),
    "m": (236 / 255, 0.0, 140 / 255),
    "y": (1.0, 241 / 255, 0.0),
}


def cmyk_to_srgb(c: float, m: float, y: float, k: float) -> tuple[int, int, int]:
    """Convert CMYK percentages to an 8-bit sRGB triple.

    Each ink is modelled as a filter: at fraction *f* it interpolates the channel between white and
    that ink's primary, and the three filters multiply. Black then scales the result. This is not
    colour management — no ICC profile, no ink limit, no dot gain — but it lands close enough to
    real map colours that nearest-palette classification is unambiguous, which is all the segmenter
    asks of it. T017 measures the residual offset against the owner's corpus and adds per-profile
    entries if any of it turns out to matter.
    """
    for name, value in (("c", c), ("m", m), ("y", y), ("k", k)):
        if not 0.0 <= value <= 100.0:
            raise ValueError(f"{name} must be a percentage in [0, 100], got {value}")

    rgb = [1.0, 1.0, 1.0]
    for ink, pct in (("c", c), ("m", m), ("y", y)):
        f = pct / 100.0
        primary = _INK_PRIMARIES[ink]
        for i in range(3):
            rgb[i] *= (1.0 - f) + f * primary[i]

    kf = 1.0 - k / 100.0
    return tuple(round(255.0 * ch * kf) for ch in rgb)  # type: ignore[return-value]


class MapSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    default_dpi: float = Field(gt=0.0)


class Shade(BaseModel):
    """One printed colour on the map: an ink at a screen percentage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    ink: str
    tint: float = Field(ge=0.0, le=100.0)


class PaletteSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lab_distance_threshold: float = Field(gt=0.0)
    unknown_fill_radius: int = Field(ge=0)
    ink: dict[str, tuple[float, float, float, float]]
    shade: list[Shade]

    @model_validator(mode="after")
    def _shades_reference_known_inks(self) -> PaletteSettings:
        names = [s.name for s in self.shade]
        if len(set(names)) != len(names):
            raise ValueError("shade names must be unique")
        for s in self.shade:
            if s.ink != "none" and s.ink not in self.ink:
                raise ValueError(f"shade {s.name!r} references unknown ink {s.ink!r}")
        return self

    def srgb_of(self, shade_name: str) -> tuple[int, int, int]:
        """The screen colour of a named shade.

        A tint is a screen percentage of the ink, so it scales the ink's CMYK values before
        conversion — 50% yellow is 0/13.5/39.5/0, not "yellow at half brightness".
        """
        if shade_name == "none":
            return (255, 255, 255)
        for s in self.shade:
            if s.name == shade_name:
                if s.ink == "none":
                    return (255, 255, 255)
                c, m, y, k = self.ink[s.ink]
                f = s.tint / 100.0
                return cmyk_to_srgb(c * f, m * f, y * f, k * f)
        raise KeyError(f"unknown shade {shade_name!r}")

    def srgb_table(self) -> dict[str, tuple[int, int, int]]:
        """Every shade's screen colour, keyed by shade name."""
        return {s.name: self.srgb_of(s.name) for s in self.shade}


class TerrainSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: TerrainClass
    isom: str = ""
    shade: str
    speed_factor: float = Field(ge=0.0, description="fraction of the runner's road speed")
    passable: bool
    note: str = ""

    @model_validator(mode="after")
    def _impassable_has_no_speed(self) -> TerrainSpec:
        if not self.passable and self.speed_factor != 0.0:
            raise ValueError(f"{self.name}: impassable terrain must have speed_factor 0")
        if self.passable and self.speed_factor == 0.0 and self.name is not TerrainClass.CONTOUR:
            raise ValueError(f"{self.name}: passable terrain needs a positive speed_factor")
        return self


class LinearSettings(BaseModel):
    """Tunables for splitting the palette's shared `road` placeholder (T014, F5).

    `road`, `vehicle_track` and `footpath` all print in `black_100`; the palette classifier cannot
    tell them apart by colour (see `vision/palette.py`'s module docstring), so this module does it
    geometrically. `*_width_mm` are the ISOM nominal printed widths (symbols 502/503, 504, 505) that
    a corridor's measured stroke width is matched against, nearest wins.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    road_width_mm: float = Field(gt=0.0)
    vehicle_track_width_mm: float = Field(gt=0.0)
    footpath_width_mm: float = Field(gt=0.0)
    min_component_area_px: int = Field(gt=0)
    elongation_ratio_min: float = Field(gt=0.0)
    aspect_ratio_min: float = Field(gt=0.0)
    min_length_mm: float = Field(gt=0.0)
    close_radius_px: int = Field(ge=0)

    def nominal_width_px(self, dpi: float) -> dict[TerrainClass, float]:
        """Nominal printed stroke width per linear class, in pixels at *dpi*."""
        px_per_mm = dpi / 25.4
        return {
            TerrainClass.ROAD: self.road_width_mm * px_per_mm,
            TerrainClass.VEHICLE_TRACK: self.vehicle_track_width_mm * px_per_mm,
            TerrainClass.FOOTPATH: self.footpath_width_mm * px_per_mm,
        }

    def min_length_px(self, dpi: float) -> float:
        """Shortest skeleton length (px, at *dpi*) a component must have to count as a corridor.

        Text and point symbols are bounded in physical size (a font's cap height, a symbol's
        diameter -- a few mm); a road/track/footpath is a through-route and is, on any real map,
        much longer than that. This floor is what actually separates a single tall glyph (which can
        have `elongation_ratio` comparable to a real corridor's) from the real thing -- see
        `vision/linear.py`'s module docstring.
        """
        return self.min_length_mm * dpi / 25.4


class GridSettings(BaseModel):
    """Shape-based carve-out for grid/magnetic-north/border lines misread as water (T074, F20,
    ADR-012) -- see `vision/segment.py::reclassify_grid_ink`'s module docstring for the shape
    reasoning and the real-scan measurements these numbers come from.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    span_fraction_min: float = Field(gt=0.0, le=1.0)
    max_line_width_mm: float = Field(gt=0.0)
    min_elongation_ratio: float = Field(gt=0.0)

    def max_line_width_px(self, dpi: float) -> float:
        """Widest a candidate grid/border run may be (px, at *dpi*) and still count as a line
        rather than real terrain -- the same mm-on-paper convention as every sibling geometric
        tunable (`LinearSettings.nominal_width_px`, `DetectorSettings.circle_radius_px`).
        """
        return self.max_line_width_mm * dpi / 25.4


class SlopeSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    density_sigma_mm: float = Field(gt=0.0)
    penalty: float = Field(ge=0.0)
    # Exponent applied to density before the penalty multiplier (T095, ADR-029): `1.0` is the
    # original linear formula; `> 1.0` makes the density -> penalty curve convex, so a small
    # increase in density near the low end barely changes the cost while the same-sized increase
    # near the high end (genuinely steep/dense terrain) changes it a lot -- the literature's own
    # "2-storey vs 10-storey climb" framing (`docs/research/route-choice-heuristics.md`, Rule 6),
    # rather than every unit of density costing the same regardless of how steep the ground
    # already is. See `config/default.toml`'s own comment for the tuned default and its rationale.
    density_exponent: float = Field(ge=1.0)

    def density_sigma_px(self, dpi: float) -> float:
        """Gaussian blur sigma in pixels, for a raster at *dpi*.

        The blur radius is a fixed size *on paper*, like every other geometric tunable in this
        config (``LinearSettings.nominal_width_px``, ``DetectorSettings.circle_radius_px``) -- so
        its pixel size follows from the scan resolution alone, never a hardcoded pixel constant.
        """
        return self.density_sigma_mm * dpi / 25.4


class ProximitySettings(BaseModel):
    """Distance-decay speed bonus near a linear feature -- `road`/`vehicle_track`/`footpath`
    (T095, ADR-029's Rules 2+7: "prefer running near a handrail" and "prefer a leg with a catching
    feature beyond the control" collapse to the same mechanism once expressed as a per-pixel cost
    term -- a control near a linear feature gets the same treatment as any other nearby pixel, no
    separate "attack point" concept needed).

    **Enabled by default (`enabled = true`)** -- shipped off pending an owner review of a
    before/after example on a real map (ADR-029, T095); the owner signed off 2026-09-12 and this
    group's own two other numbers (`decay_distance_m`, `bonus_magnitude`) are that session's
    real-map best-effort starting point, not yet a corpus-validated final tuning (ADR-029's
    amendment paragraph).

    **Ground metres, not paper millimetres.** Unlike this file's `_mm` tunables (`LinearSettings`,
    `SlopeSettings.density_sigma_mm`) -- fixed *printed* sizes converted to pixels via DPI, because
    an ISOM stroke width or a blur radius is chosen in terms of ink on the sheet -- how far a
    runner can still benefit from a nearby trail is a real-world distance on the ground, unrelated
    to how the map happens to be printed. `cost/field.py` already carries
    `TerrainMap.meters_per_pixel` for exactly this kind of conversion (it is how
    `seconds_per_pixel` itself turns a pixel count into real time), so this group converts through
    that instead of a DPI it has no reason to need.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool
    decay_distance_m: float = Field(gt=0.0)
    bonus_magnitude: float = Field(ge=0.0)


class DetectorSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    circle_diameter_mm: float = Field(gt=0.0)
    circle_diameter_tolerance: float = Field(ge=0.0, lt=1.0)
    ink_hue_ranges: list[tuple[int, int]] = Field(min_length=1)
    purple_min_saturation: int = Field(ge=0, le=255)
    purple_min_value: int = Field(ge=0, le=255)
    # Red is split out from ink_hue_ranges (ADR-018): on a real scan (data/maps/ozero-shchuche),
    # the shared purple_min_saturation/value floor above let brown contour ink pass the red hue
    # band, because brown is saturated but dimmer than real red control ink. Red gets its own,
    # measured floor plus a red-vs-brown channel-gap check; every other configured ink colour
    # (purple today) keeps using the shared floor above.
    red_hue_ranges: list[tuple[int, int]] = Field(min_length=1)
    red_min_saturation: int = Field(ge=0, le=255)
    red_min_value: int = Field(ge=0, le=255)
    red_min_channel_gap: int = Field(ge=0, le=255)
    hough_dp: float = Field(gt=0.0)
    hough_param1: float = Field(gt=0.0)
    hough_param2: float = Field(gt=0.0)
    circle_scale_multipliers: list[float] = Field(min_length=1)
    number_font_height_mm: float = Field(gt=0.0)
    number_search_radius: float = Field(gt=0.0)
    points_rule: Literal["first_digit", "constant", "csv"]
    points_constant: int = Field(ge=0)
    min_ocr_confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _hue_ranges_are_valid_opencv_bands(self) -> DetectorSettings:
        for lo, hi in [*self.ink_hue_ranges, *self.red_hue_ranges]:
            if not (0 <= lo <= hi <= 179):
                raise ValueError(
                    f"ink_hue_ranges/red_hue_ranges band ({lo}, {hi}) must satisfy "
                    "0 <= lo <= hi <= 179 (OpenCV's 0-179 H scale) -- a hue above 179 overflows "
                    "the uint8 HSV frame purple_mask builds, and lo > hi would silently match "
                    "nothing"
                )
        return self

    @model_validator(mode="after")
    def _scale_multipliers_are_positive(self) -> DetectorSettings:
        if any(m <= 0.0 for m in self.circle_scale_multipliers):
            raise ValueError(
                f"circle_scale_multipliers must all be > 0, got {self.circle_scale_multipliers} "
                "-- a zero or negative multiplier collapses or inverts the scaled Hough radius "
                "window _detect_circles/_detect_hub_triangle derive from it"
            )
        return self

    def circle_radius_px(self, dpi: float) -> tuple[float, float]:
        """Expected control-circle radius range in pixels, for a raster at *dpi*.

        The circle is a fixed size *on paper* (ISOM 703), so its pixel size follows from the scan
        resolution alone — the map scale never enters into it.
        """
        mm_per_px = 25.4 / dpi
        r = self.circle_diameter_mm / 2.0 / mm_per_px
        tol = self.circle_diameter_tolerance
        return (r * (1.0 - tol), r * (1.0 + tol))


class OcrFallbackSettings(BaseModel):
    """Opt-in VLM OCR fallback for control-*number* reading only (T114, SPEC F23, ADR-039) --
    circle/position detection stays 100% classical CV, untouched by this section. Disabled by
    shipped default; wiring and the trigger condition live in `vision/ocr.py`, this class is only
    the config surface. Both `enabled` AND a configured `ANTHROPIC_API_KEY` (never stored here or
    in any committed file) are required before `vision/ocr_vlm.py` makes any network call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool
    #: A control's Tesseract read below this floor (or empty) is what triggers the fallback
    #: attempt -- deliberately its own value, not reused from `DetectorSettings.min_ocr_confidence`
    #: above: that one gates Tesseract's own accept/reject decision, this one gates whether a
    #: second, network-costing attempt is worth making at all.
    trigger_confidence: float = Field(ge=0.0, le=1.0)
    model: str = Field(min_length=1)


class GraphSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    downsample: int = Field(ge=1)
    impassable_cost_multiplier: float = Field(gt=1.0)
    strict_impassable: bool


class SolverSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy: Literal["auto", "exact", "heuristic"]
    exact_max_controls: int = Field(ge=1, le=24)
    heuristic_time_budget_s: float = Field(gt=0.0)
    grasp_restarts: int = Field(ge=1)
    grasp_candidate_size: int = Field(ge=1)
    seed: int
    alternatives: int = Field(ge=0)


class RuleSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    penalty_per_min: float = Field(ge=0.0)


class AppConfig(BaseModel):
    """The whole configuration file, validated."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    map: MapSettings
    palette: PaletteSettings
    terrain: list[TerrainSpec]
    grid: GridSettings
    linear: LinearSettings
    slope: SlopeSettings
    proximity: ProximitySettings
    detector: DetectorSettings
    ocr_fallback: OcrFallbackSettings
    graph: GraphSettings
    solver: SolverSettings
    rules: RuleSettings

    @model_validator(mode="after")
    def _terrain_covers_the_contract(self) -> AppConfig:
        configured = [t.name for t in self.terrain]
        if len(set(configured)) != len(configured):
            raise ValueError("terrain classes must not be repeated")
        missing = set(TERRAIN_ORDER) - set(configured)
        if missing:
            names = sorted(m.value for m in missing)
            raise ValueError(f"config is missing terrain classes: {names}")
        known_shades = {s.name for s in self.palette.shade} | {"none"}
        for t in self.terrain:
            if t.shade not in known_shades:
                raise ValueError(f"terrain {t.name}: unknown shade {t.shade!r}")
        return self

    def terrain_of(self, cls: TerrainClass) -> TerrainSpec:
        for t in self.terrain:
            if t.name is cls:
                return t
        raise KeyError(cls)  # unreachable: the validator guarantees coverage

    def speed_factors(self) -> np.ndarray:
        """Speed factor per terrain label, indexed by ``TERRAIN_ORDER`` position."""
        return np.array([self.terrain_of(c).speed_factor for c in TERRAIN_ORDER], dtype=np.float32)

    def passability(self) -> np.ndarray:
        """Passability per terrain label, indexed by ``TERRAIN_ORDER`` position."""
        return np.array([self.terrain_of(c).passable for c in TERRAIN_ORDER], dtype=bool)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(
    path: Path | str | None = None, overrides: dict[str, Any] | None = None
) -> AppConfig:
    """Load the configuration.

    Precedence, lowest first: the shipped ``config/default.toml``, then *path* (or
    ``$ROGAINE_CONFIG``) merged over it, then *overrides* merged over that. A user file therefore
    only has to name the keys it changes.
    """
    with DEFAULT_CONFIG_PATH.open("rb") as fh:
        data = tomllib.load(fh)

    chosen = path if path is not None else os.environ.get(CONFIG_ENV_VAR)
    if chosen:
        chosen_path = Path(chosen)
        if not chosen_path.is_file():
            raise FileNotFoundError(f"config file not found: {chosen_path}")
        if chosen_path.resolve() != DEFAULT_CONFIG_PATH.resolve():
            with chosen_path.open("rb") as fh:
                data = _deep_merge(data, tomllib.load(fh))

    if overrides:
        data = _deep_merge(data, overrides)

    return AppConfig.model_validate(data)


@lru_cache(maxsize=1)
def default_config() -> AppConfig:
    """The shipped configuration, loaded once. Use :func:`load_config` when overriding."""
    return load_config()
