"""Raster loading (T010): PNG/JPG/BMP/TIFF/PDF -> RGB array, corrupt/oversized files fail
clearly (SPEC F1).
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from PIL import Image

from rogaine.io import raster
from rogaine.io.raster import RasterLoadError, load_map_context, load_raster, resolve_dpi


def _mean_abs_diff(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a.astype(np.int32) - b.astype(np.int32)).mean())


class TestLosslessRoundTrip:
    """PNG/BMP/TIFF are lossless — the DoD's "within 1 LSB" is exact equality here."""

    @pytest.mark.parametrize("suffix", [".png", ".bmp", ".tif"])
    def test_round_trips_exactly(self, tmp_path, clean_synthetic_map, suffix) -> None:
        source = clean_synthetic_map.image  # BGR-encode/decode below, RGB in and out
        path = tmp_path / f"map{suffix}"
        ok, buf = cv2.imencode(suffix, source[:, :, ::-1])
        assert ok
        path.write_bytes(buf.tobytes())

        loaded = load_raster(path)

        assert loaded.shape == source.shape
        assert loaded.dtype == np.uint8
        assert np.array_equal(loaded, source)


class TestLossyRoundTrip:
    """JPEG has no lossless mode, and Pillow's PDF writer always JPEG-encodes RGB content (no
    lossless filter is available there either — see ``PIL.PdfImagePlugin._write_image``, which
    routes every ``RGB`` image through ``DCTDecode``). Both tests are relaxed to a mean
    per-pixel error bound rather than exact equality; measured on the standard 1600x1200 clean
    fixture at quality 95, direct JPEG and PDF-embedded JPEG both land a mean abs diff around
    1.7 (the two paths converge because they hit the same JPEG codec at the same quality) — 5.0
    leaves comfortable headroom without being able to hide a real regression such as a
    channel-order bug (measured mean abs diff ~16-19 for a R/B channel swap on this fixture).
    """

    def test_jpeg_round_trip_stays_close(self, tmp_path, clean_synthetic_map) -> None:
        source = clean_synthetic_map.image
        path = tmp_path / "map.jpg"
        ok, buf = cv2.imencode(".jpg", source[:, :, ::-1], [cv2.IMWRITE_JPEG_QUALITY, 95])
        assert ok
        path.write_bytes(buf.tobytes())

        loaded = load_raster(path)

        assert loaded.shape == source.shape
        assert _mean_abs_diff(loaded, source) < 5.0

    def test_pdf_round_trip_stays_close(self, tmp_path, clean_synthetic_map) -> None:
        source = clean_synthetic_map.image
        dpi = clean_synthetic_map.dpi
        path = tmp_path / "map.pdf"
        Image.fromarray(source, mode="RGB").save(
            path, format="PDF", resolution=dpi, quality=95
        )

        loaded = load_raster(path, dpi=dpi)

        assert loaded.shape == source.shape
        assert _mean_abs_diff(loaded, source) < 5.0


class TestPdfPageSelection:
    def _two_page_pdf(self, tmp_path):
        red = Image.fromarray(np.full((80, 120, 3), (200, 20, 20), dtype=np.uint8), "RGB")
        blue = Image.fromarray(np.full((80, 120, 3), (20, 20, 200), dtype=np.uint8), "RGB")
        path = tmp_path / "two_page.pdf"
        red.save(path, format="PDF", save_all=True, append_images=[blue], resolution=150.0)
        return path

    def test_page_zero_is_the_default(self, tmp_path) -> None:
        loaded = load_raster(self._two_page_pdf(tmp_path), dpi=150.0)
        assert loaded[loaded.shape[0] // 2, loaded.shape[1] // 2, 0] > 150  # red page

    def test_page_one_selects_the_second_page(self, tmp_path) -> None:
        loaded = load_raster(self._two_page_pdf(tmp_path), page=1, dpi=150.0)
        assert loaded[loaded.shape[0] // 2, loaded.shape[1] // 2, 2] > 150  # blue page

    def test_out_of_range_page_is_a_clear_error(self, tmp_path) -> None:
        with pytest.raises(RasterLoadError, match="out of range"):
            load_raster(self._two_page_pdf(tmp_path), page=5, dpi=150.0)


class TestErrors:
    def test_missing_file_is_a_clear_error(self, tmp_path) -> None:
        with pytest.raises(RasterLoadError, match="no such file"):
            load_raster(tmp_path / "nope.png")

    def test_unsupported_suffix_is_a_clear_error(self, tmp_path) -> None:
        path = tmp_path / "map.gif"
        path.write_bytes(b"GIF89a")
        with pytest.raises(RasterLoadError, match="unsupported map format"):
            load_raster(path)

    def test_corrupt_raster_is_a_clear_error_not_a_traceback(self, tmp_path) -> None:
        path = tmp_path / "map.png"
        path.write_bytes(b"this is not a png file at all")
        with pytest.raises(RasterLoadError, match="could not decode"):
            load_raster(path)

    def test_corrupt_pdf_is_a_clear_error_not_a_traceback(self, tmp_path) -> None:
        path = tmp_path / "map.pdf"
        path.write_bytes(b"%PDF-1.4 this is not a real pdf")
        with pytest.raises(RasterLoadError, match="could not open PDF"):
            load_raster(path)

    def test_oversized_file_is_rejected(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(raster, "MAX_DECODED_PIXELS", 100)
        path = tmp_path / "map.png"
        small = np.zeros((50, 50, 3), dtype=np.uint8)  # 2500 px > the 100 px test cap
        ok, buf = cv2.imencode(".png", small)
        assert ok
        path.write_bytes(buf.tobytes())
        with pytest.raises(RasterLoadError, match="pixel cap"):
            load_raster(path)


class TestResolveDpi:
    def test_user_dpi_wins(self, tmp_path) -> None:
        path = tmp_path / "map.png"
        Image.fromarray(np.zeros((10, 10, 3), dtype=np.uint8)).save(path, dpi=(300, 300))
        assert resolve_dpi(path, user_dpi=150.0) == 150.0

    def test_nonpositive_user_dpi_is_rejected(self, tmp_path) -> None:
        path = tmp_path / "map.png"
        Image.fromarray(np.zeros((10, 10, 3), dtype=np.uint8)).save(path)
        with pytest.raises(RasterLoadError, match="dpi must be positive"):
            resolve_dpi(path, user_dpi=0.0)

    def test_falls_back_to_embedded_dpi(self, tmp_path) -> None:
        path = tmp_path / "map.tiff"
        Image.fromarray(np.zeros((10, 10, 3), dtype=np.uint8)).save(path, dpi=(600, 600))
        assert resolve_dpi(path) == pytest.approx(600.0, rel=1e-3)

    def test_falls_back_to_config_default_when_nothing_else_says(self, tmp_path) -> None:
        # No embedded dpi, no user dpi — config/default.toml [map] default_dpi (F1/F2).
        path = tmp_path / "map.png"
        Image.fromarray(np.zeros((10, 10, 3), dtype=np.uint8)).save(path)
        from rogaine.config import default_config

        assert resolve_dpi(path) == default_config().map.default_dpi

    def test_pdf_pages_never_claim_an_embedded_dpi(self, tmp_path) -> None:
        path = tmp_path / "map.pdf"
        Image.fromarray(np.zeros((10, 10, 3), dtype=np.uint8)).save(
            path, format="PDF", resolution=300.0
        )
        assert raster.probe_dpi(path) is None


class TestLoadMapContext:
    def test_builds_a_valid_map_context(self, tmp_path, clean_synthetic_map) -> None:
        source = clean_synthetic_map.image
        path = tmp_path / "map.png"
        ok, buf = cv2.imencode(".png", source[:, :, ::-1])
        assert ok
        path.write_bytes(buf.tobytes())

        ctx = load_map_context(path, meters_per_pixel=2.54, page=0)

        assert ctx.meters_per_pixel == 2.54
        assert ctx.source == path
        assert ctx.page == 0
        assert np.array_equal(ctx.image, source)
