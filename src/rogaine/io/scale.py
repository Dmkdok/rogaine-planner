"""Scale and calibration: turning DPI + map scale, or two picked points, into ground
metres per pixel (SPEC F2, F3).

This is the canonical home for the physics. ``rogaine.io.corpus.Calibration`` re-exports the
:class:`Calibration` defined here rather than keeping a second, independently-drifting copy of
the same formula.
"""

from __future__ import annotations

from dataclasses import dataclass


def mpp_from_dpi(dpi: float, scale_denominator: float) -> float:
    """Ground metres covered by one pixel, from scan resolution and map scale (SPEC F2).

    ``mpp = (25.4 / dpi) * scale_denominator / 1000``: 25.4 mm/inch turns dpi into
    millimetres per pixel on paper, and the scale denominator (a map printed at 1:N) blows
    that up from paper millimetres to ground metres.
    """
    if not dpi > 0:
        raise ValueError(f"dpi must be positive, got {dpi}")
    if not scale_denominator > 0:
        raise ValueError(f"scale_denominator must be positive, got {scale_denominator}")
    return (25.4 / dpi) * scale_denominator / 1000.0


@dataclass(frozen=True)
class Calibration:
    """Two points on the raster and the true ground distance between them (SPEC F3).

    Use this instead of ``mpp_from_dpi`` when a scan has been cropped or resampled and the
    nominal DPI no longer describes the file.
    """

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
