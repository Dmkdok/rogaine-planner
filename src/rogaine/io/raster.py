"""Raster loading: PNG/JPG/BMP/TIFF and PDF pages to RGB arrays (SPEC F1).

This module deals only in pixels and DPI metadata. Turning pixels into a :class:`MapContext`
needs a metres-per-pixel value, and computing *that* from DPI + map scale (or a two-point
calibration) is ``rogaine.io.scale``'s job (T011) — see :func:`load_map_context` for where the
two compose: the caller resolves ``meters_per_pixel`` first (via ``rogaine.io.scale`` and
whatever the map's ``meta.toml``/CLI flags say), then hands it here.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pypdfium2 as pdfium
from PIL import Image

from rogaine.config import default_config
from rogaine.models import MapContext

#: Suffixes decoded directly by OpenCV; every other supported suffix (``.pdf``) has its own path.
_OPENCV_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}

#: Hard cap on decoded pixel count (width * height), checked after decode. The SPEC
#: performance-budget "full size" preset is 4000x3000 = 12,000,000 px; the owner's real scan
#: corpus tops out around 28,700,000 px (5768x4969). 150,000,000 px (e.g. ~17300x8700) gives
#: over 5x headroom above the largest real file while still refusing a file whose decoded size
#: would start eating gigabytes of RAM before anything downstream gets a chance to say no.
#: A module attribute, not a function default, so tests can lower it without touching real data.
MAX_DECODED_PIXELS = 150_000_000


class RasterLoadError(ValueError):
    """A map file could not be loaded — a clear, catchable error, never a raw decoder traceback."""


def load_raster(path: Path, *, page: int = 0, dpi: float | None = None) -> np.ndarray:
    """Load *path* to an ``(H, W, 3)`` uint8 RGB array.

    PDF pages are rasterised via pypdfium2 at :func:`resolve_dpi`'s resolution (*page* selects
    which page, 0-based). Every other supported suffix is decoded via OpenCV, which is
    resolution-independent — *dpi* is ignored for those. Corrupt files and files whose decoded
    size would exceed :data:`MAX_DECODED_PIXELS` raise :class:`RasterLoadError`.
    """
    if not path.is_file():
        raise RasterLoadError(f"no such file: {path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        image = _load_pdf_page(path, page, resolve_dpi(path, user_dpi=dpi))
    elif suffix in _OPENCV_SUFFIXES:
        image = _load_opencv_image(path)
    else:
        raise RasterLoadError(f"unsupported map format {suffix!r}: {path}")

    h, w = image.shape[:2]
    if h * w > MAX_DECODED_PIXELS:
        raise RasterLoadError(
            f"{path} decodes to {w}x{h} = {w * h:,} pixels, over the {MAX_DECODED_PIXELS:,} "
            f"pixel cap"
        )
    return image


def _load_opencv_image(path: Path) -> np.ndarray:
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise RasterLoadError(f"could not decode image: {path}")
    return np.ascontiguousarray(bgr[:, :, ::-1])  # BGR -> RGB


def _load_pdf_page(path: Path, page: int, dpi: float) -> np.ndarray:
    try:
        pdf = pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as exc:
        raise RasterLoadError(f"could not open PDF: {path} ({exc})") from exc
    try:
        if not 0 <= page < len(pdf):
            raise RasterLoadError(
                f"PDF page {page} out of range for {path} ({len(pdf)} page(s))"
            )
        bitmap = pdf[page].render(scale=dpi / 72.0)
        return np.array(bitmap.to_pil().convert("RGB"), dtype=np.uint8)
    except pdfium.PdfiumError as exc:
        raise RasterLoadError(f"could not render page {page} of {path}: {exc}") from exc
    finally:
        pdf.close()


def probe_dpi(path: Path) -> float | None:
    """The DPI embedded in *path*'s own metadata (PNG ``pHYs``, TIFF/JPEG resolution tags), or
    ``None`` when it carries none. PDF pages always return ``None`` — they are rasterised at a
    caller-chosen resolution, not scanned at a fixed one.
    """
    if path.suffix.lower() == ".pdf":
        return None
    try:
        with Image.open(path) as img:
            dpi = img.info.get("dpi")
    except (OSError, ValueError):
        return None
    if not dpi or not dpi[0] > 0:
        return None
    return float(dpi[0])


def resolve_dpi(path: Path, *, user_dpi: float | None = None) -> float:
    """The DPI to use for *path*: an explicit *user_dpi*, else the file's own metadata, else the
    configured fallback (``config/default.toml [map] default_dpi``, SPEC F1/F2).
    """
    if user_dpi is not None:
        if not user_dpi > 0:
            raise RasterLoadError(f"dpi must be positive, got {user_dpi}")
        return user_dpi
    probed = probe_dpi(path)
    if probed is not None:
        return probed
    return default_config().map.default_dpi


def load_map_context(path: Path, meters_per_pixel: float, *, page: int = 0) -> MapContext:
    """Load *path* and wrap it in a :class:`MapContext` at the given scale.

    *meters_per_pixel* is computed by the caller (``rogaine.io.scale``) — this function only
    ever fills the pixel side of the contract.
    """
    image = load_raster(path, page=page)
    return MapContext(image=image, meters_per_pixel=meters_per_pixel, source=path, page=page)
