"""The real map corpus (T005).

Maps arrive from the owner over time and half of them are missing metadata at any given moment.
That is the normal state, not an error, so this module never refuses to list a corpus — it reports
per entry what is present and what is missing, and only refuses to *plan* on a map whose scale is
unknown. See ``data/README.md`` for the on-disk contract.
"""

from __future__ import annotations

import csv
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from rogaine.models import Control

#: Files a map directory may hold as its source raster, in the order they are preferred.
RASTER_SUFFIXES: tuple[str, ...] = (".ocd", ".pdf", ".png", ".tif", ".tiff", ".jpg", ".jpeg")

META_NAME = "meta.toml"
CONTROLS_NAME = "controls.csv"
REFERENCE_NAME = "reference.json"


@dataclass(frozen=True)
class Calibration:
    """Two points on the raster and the true ground distance between them (SPEC F3)."""

    x1: float
    y1: float
    x2: float
    y2: float
    meters: float

    def __post_init__(self) -> None:
        if self.meters <= 0:
            raise ValueError("calibration distance must be positive")
        if (self.x1, self.y1) == (self.x2, self.y2):
            raise ValueError("calibration points must be distinct")

    @property
    def meters_per_pixel(self) -> float:
        pixels = ((self.x2 - self.x1) ** 2 + (self.y2 - self.y1) ** 2) ** 0.5
        return self.meters / pixels


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
            return (25.4 / self.dpi) * self.scale_denominator / 1000.0
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


def read_controls(csv_path: Path) -> list[Control]:
    """Load ``controls.csv``. Raises — a controls file that is present must be correct."""
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"{csv_path} has a header but no controls")

    controls: list[Control] = []
    for line, row in enumerate(rows, start=2):
        try:
            number = int(row["number"]) if (row.get("number") or "").strip() else None
            points = int(row["points"]) if (row.get("points") or "").strip() else None
            controls.append(
                Control(
                    id=int(row["id"]),
                    x=float(row["x"]),
                    y=float(row["y"]),
                    number=number,
                    points=points,
                    confidence=1.0,
                    source="manual",
                    is_hub=(row.get("is_hub") or "").strip().lower() in {"true", "1", "yes"},
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{csv_path} line {line}: {exc}") from exc

    hubs = [c for c in controls if c.is_hub]
    if len(hubs) != 1:
        raise ValueError(f"{csv_path}: exactly one row must set is_hub, found {len(hubs)}")
    ids = [c.id for c in controls]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{csv_path}: control ids are not unique")
    # The hub is index 0 everywhere downstream (SPEC F14), so put it there once, here.
    controls.sort(key=lambda c: (not c.is_hub, c.id))
    return controls
