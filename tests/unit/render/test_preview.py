"""Terrain preview rendering (T016): TerrainMap -> a legible, colour-vectorised PNG."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from rogaine.config import default_config
from rogaine.models import TerrainClass, TerrainMap, terrain_label
from rogaine.render.preview import render_preview, write_preview


def _terrain_map(labels: np.ndarray) -> TerrainMap:
    density = np.zeros(labels.shape, dtype=np.float32)
    return TerrainMap(labels=labels, contour_density=density, meters_per_pixel=2.5)


class TestRenderPreview:
    def test_shape_and_dtype(self) -> None:
        labels = np.zeros((6, 8), dtype=np.uint8)
        preview = render_preview(_terrain_map(labels))
        assert preview.shape == (6, 8, 3)
        assert preview.dtype == np.uint8

    def test_each_pixel_gets_its_class_nominal_colour(self) -> None:
        cfg = default_config()
        labels = np.full((4, 4), terrain_label(TerrainClass.OPEN_LAND), dtype=np.uint8)
        labels[1, 2] = terrain_label(TerrainClass.WATER_UNCROSSABLE)

        preview = render_preview(_terrain_map(labels), cfg)

        expected_open = cfg.palette.srgb_of(cfg.terrain_of(TerrainClass.OPEN_LAND).shade)
        expected_water = cfg.palette.srgb_of(cfg.terrain_of(TerrainClass.WATER_UNCROSSABLE).shade)
        assert tuple(int(c) for c in preview[0, 0]) == expected_open
        assert tuple(int(c) for c in preview[1, 2]) == expected_water

    def test_unknown_and_forest_runnable_both_render_white(self) -> None:
        """Documents the known collision from the module docstring: both classes render
        identically because their configured shades both resolve to white -- not a bug in this
        module, so this locks the observed behaviour in rather than silently diverging from it."""
        cfg = default_config()
        labels = np.array(
            [[terrain_label(TerrainClass.UNKNOWN), terrain_label(TerrainClass.FOREST_RUNNABLE)]],
            dtype=np.uint8,
        )

        preview = render_preview(_terrain_map(labels), cfg)

        assert tuple(int(c) for c in preview[0, 0]) == (255, 255, 255)
        assert tuple(int(c) for c in preview[0, 1]) == (255, 255, 255)


class TestWritePreview:
    def test_writes_a_readable_png_of_the_right_shape(self, tmp_path) -> None:
        labels = np.full((5, 7), terrain_label(TerrainClass.OPEN_LAND), dtype=np.uint8)
        path = tmp_path / "preview.png"

        write_preview(path, _terrain_map(labels))

        assert path.exists()
        read_back = cv2.imread(str(path), cv2.IMREAD_COLOR)
        assert read_back.shape == (5, 7, 3)

    def test_raises_clearly_on_a_missing_parent_directory(self, tmp_path) -> None:
        labels = np.zeros((3, 3), dtype=np.uint8)
        path = tmp_path / "missing_dir" / "preview.png"

        with pytest.raises(OSError):
            write_preview(path, _terrain_map(labels))
