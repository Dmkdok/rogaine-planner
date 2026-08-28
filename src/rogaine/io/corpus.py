"""The real map corpus (T005).

Maps arrive from the owner over time and half of them are missing metadata at any given moment.
That is the normal state, not an error, so this module never refuses to list a corpus — it reports
per entry what is present and what is missing, and only refuses to *plan* on a map whose scale is
unknown. See ``data/README.md`` for the on-disk contract.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

#: Re-exported, not duplicated: T022 moved the real parsing to ``io/controls_csv`` (the canonical
#: home for the CSV contract), this module still exposes the name for anything that imports
#: ``read_controls`` from here.
from rogaine.io.controls_csv import read_controls as read_controls
from rogaine.io.scale import Calibration, mpp_from_dpi

#: Files a map directory may hold as its source raster, in the order they are preferred.
RASTER_SUFFIXES: tuple[str, ...] = (".ocd", ".pdf", ".png", ".tif", ".tiff", ".jpg", ".jpeg")

META_NAME = "meta.toml"
CONTROLS_NAME = "controls.csv"
REFERENCE_NAME = "reference.json"

#: ``Calibration`` here is the same type as ``rogaine.io.scale.Calibration`` (T011's canonical
#: home for the maths) — imported, not redefined, so the two never drift apart.


@dataclass(frozen=True)
class CorpusEntry:
    """One map directory, described by whatever it actually contains."""

    map_id: str
    path: Path
    raster: Path | None = None
    name: str | None = None
    scale_denominator: float | None = None
    dpi: float | None = None
    calibration: Calibration | None = None
    has_controls: bool = False
    has_reference: bool = False
    problems: tuple[str, ...] = field(default_factory=tuple)

    @property
    def meters_per_pixel(self) -> float | None:
        """Ground metres per pixel, or ``None`` when the map cannot say (SPEC F2)."""
        if self.calibration is not None:
            return self.calibration.meters_per_pixel
        if self.scale_denominator and self.dpi:
            return mpp_from_dpi(self.dpi, self.scale_denominator)
        return None

    @property
    def missing(self) -> tuple[str, ...]:
        """What this entry still needs, most blocking first."""
        gaps: list[str] = []
        if self.raster is None:
            gaps.append("raster")
        if self.meters_per_pixel is None:
            gaps.append("scale (need scale_denominator + dpi, or a [calibration] line)")
        if not self.has_controls:
            gaps.append("controls.csv (optional — detection runs instead)")
        if not self.has_reference:
            gaps.append("reference.json (optional — no acceptance comparison for this map)")
        return tuple(gaps)

    @property
    def is_plannable(self) -> bool:
        """True when this map has enough to route on: a raster and a known scale."""
        return self.raster is not None and self.meters_per_pixel is not None and not self.problems


def _read_meta(meta_path: Path) -> tuple[dict, tuple[str, ...]]:
    if not meta_path.is_file():
        return {}, (f"{META_NAME} is missing",)
    try:
        return tomllib.loads(meta_path.read_text(encoding="utf-8")), ()
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return {}, (f"{META_NAME} is unreadable: {exc}",)


def _find_raster(map_dir: Path) -> Path | None:
    for suffix in RASTER_SUFFIXES:
        for candidate in sorted(map_dir.glob(f"*{suffix}")):
            return candidate
    return None


def read_entry(map_dir: Path) -> CorpusEntry:
    """Describe one map directory. Never raises for a malformed map — it reports instead."""
    meta, problems = _read_meta(map_dir / META_NAME)

    calibration: Calibration | None = None
    raw_cal = meta.get("calibration")
    if isinstance(raw_cal, dict):
        try:
            calibration = Calibration(
                x1=float(raw_cal["x1"]),
                y1=float(raw_cal["y1"]),
                x2=float(raw_cal["x2"]),
                y2=float(raw_cal["y2"]),
                meters=float(raw_cal["meters"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            problems = (*problems, f"[calibration] is invalid: {exc}")

    def _positive(key: str) -> float | None:
        nonlocal problems
        value = meta.get(key)
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            problems = (*problems, f"{key} is not a number: {value!r}")
            return None
        if number <= 0:
            problems = (*problems, f"{key} must be positive, got {number}")
            return None
        return number

    return CorpusEntry(
        map_id=map_dir.name,
        path=map_dir,
        raster=_find_raster(map_dir),
        name=meta.get("name") if isinstance(meta.get("name"), str) else None,
        scale_denominator=_positive("scale_denominator"),
        dpi=_positive("dpi"),
        calibration=calibration,
        has_controls=(map_dir / CONTROLS_NAME).is_file(),
        has_reference=(map_dir / REFERENCE_NAME).is_file(),
        problems=problems,
    )


def list_corpus(root: Path) -> list[CorpusEntry]:
    """Every map directory under ``root``, sorted by id. An absent root is an empty corpus."""
    if not root.is_dir():
        return []
    return [read_entry(d) for d in sorted(root.iterdir()) if d.is_dir()]
