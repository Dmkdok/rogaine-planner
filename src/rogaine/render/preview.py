"""Terrain preview rendering (T016).

:mod:`rogaine.vision.segment` turns a map raster into a :class:`~rogaine.models.TerrainMap` of
per-pixel labels; this module turns that back into something legible without decoding label
integers. Every pixel is coloured by its class's nominal printed colour --
``config.palette.srgb_of`` on the shade ``config.terrain_of(cls).shade`` names for that class -- so
the preview uses the same colour vocabulary the map itself was printed in (ADR-001), not a palette
invented for this tool. `render/overlay.py` (later, F15) draws a route over the *original* map
raster; this module never touches that raster, only `TerrainMap.labels`.

**Vectorised lookup, not a per-pixel loop.** :data:`~rogaine.models.TERRAIN_ORDER` fixes a small
(under 32) integer alphabet for `labels`, so a ``(len(TERRAIN_ORDER), 3)`` lookup table built once
and indexed with ``lut[terrain_map.labels]`` recolours the whole raster in a single fancy-index --
the full-size fixture preset is 4000x3000, and a Python-level per-pixel loop over 12M pixels would
dominate any real run.

**A known colour collision.** `unknown`'s shade is literally the string ``"none"``
(`config/default.toml`), which `PaletteSettings.srgb_of` resolves to white -- the same white
`forest_runnable` renders as via its own shade `white` (ink `"none"`, tint 0). Both are legitimate,
config-driven choices (`forest_runnable` = white is the correct ISOM convention for unmarked
runnable forest; `unknown` = white is this project's own convention for "no classification"), not a
bug in this module, so it does not invent an unrequested colour to tell them apart. A caller that
needs to distinguish them can still test ``labels == terrain_label(TerrainClass.UNKNOWN)`` directly.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from rogaine.config import AppConfig, default_config
from rogaine.models import TERRAIN_ORDER, TerrainMap


def render_preview(terrain_map: TerrainMap, config: AppConfig | None = None) -> np.ndarray:
    """Colour `terrain_map.labels` by each class's nominal printed colour.

    Returns an ``(H, W, 3)`` uint8 RGB array. See the module docstring for the colour source and the
    one known collision (`unknown` vs `forest_runnable`, both white). Pure and vectorised -- no
    per-pixel Python loop.
    """
    cfg = config or default_config()
    lut = np.array(
        [cfg.palette.srgb_of(cfg.terrain_of(cls).shade) for cls in TERRAIN_ORDER],
        dtype=np.uint8,
    )
    return lut[terrain_map.labels]


def write_preview(path: Path, terrain_map: TerrainMap, config: AppConfig | None = None) -> None:
    """Write :func:`render_preview`'s output to *path* as a PNG.

    ``cv2.imwrite`` expects BGR, so the RGB output of `render_preview` is channel-swapped first --
    skipping that step ships a colour-swapped PNG, not an error. ``cv2.imwrite`` also fails
    silently (returns ``False``, raises nothing) on a bad path such as a missing parent directory;
    that return value is checked here so a bad *path* raises clearly instead of leaving no file and
    no error.
    """
    preview = render_preview(terrain_map, config)
    bgr = cv2.cvtColor(preview, cv2.COLOR_RGB2BGR)
    if not cv2.imwrite(str(path), bgr):
        raise OSError(f"failed to write preview PNG to {path}")
