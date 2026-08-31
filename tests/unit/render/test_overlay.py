"""Route overlay rendering (T052): Route drawn over the map raster."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from rogaine.models import Control, Leg, Route
from rogaine.render.overlay import _CORE_COLOR, _geometry, render_overlay, write_overlay

_BACKGROUND = 120  # a flat mid-grey, distinct from both _HALO_COLOR and _CORE_COLOR


def _image(height: int, width: int) -> np.ndarray:
    return np.full((height, width, 3), _BACKGROUND, dtype=np.uint8)


def _axis_aligned_route() -> tuple[Route, list[Control]]:
    """A hub-to-hub route with three axis-aligned legs, chosen so every polyline pixel lands
    exactly on a single, predictable output pixel (no diagonal anti-aliasing ambiguity)."""
    controls = [
        Control(id=0, x=10, y=10, is_hub=True),
        Control(id=1, x=50, y=10),
        Control(id=2, x=50, y=60),
    ]
    legs = [
        Leg(from_id=0, to_id=1, seconds=90, meters=40, polyline=[(10, 10), (50, 10)]),
        Leg(from_id=1, to_id=2, seconds=150, meters=50, polyline=[(50, 10), (50, 60)]),
        Leg(
            from_id=2,
            to_id=0,
            seconds=200,
            meters=90,
            polyline=[(50, 60), (10, 60), (10, 10)],
        ),
    ]
    route = Route(
        order=[0, 1, 2, 0],
        legs=legs,
        total_seconds=440,
        total_meters=180,
        points=0,
        penalty=0.0,
        score=0.0,
        solver="exact",
    )
    return route, controls


def _widely_spaced_route() -> tuple[Route, list[Control]]:
    """A hub-to-hub route whose three control positions are far enough apart (relative to marker
    size at this image scale) that each marker's footprint cannot overlap another's."""
    controls = [
        Control(id=0, x=200, y=200, is_hub=True),
        Control(id=1, x=700, y=200),
        Control(id=2, x=700, y=600),
    ]
    legs = [
        Leg(from_id=0, to_id=1, seconds=60, meters=100, polyline=[(200, 200), (700, 200)]),
        Leg(from_id=1, to_id=2, seconds=60, meters=100, polyline=[(700, 200), (700, 600)]),
        Leg(from_id=2, to_id=0, seconds=60, meters=100, polyline=[(700, 600), (200, 200)]),
    ]
    route = Route(
        order=[0, 1, 2, 0],
        legs=legs,
        total_seconds=180,
        total_meters=300,
        points=0,
        penalty=0.0,
        score=0.0,
        solver="exact",
    )
    return route, controls


class TestRenderOverlay:
    def test_shape_dtype_and_no_mutation(self) -> None:
        image = _image(100, 140)
        original = image.copy()
        route, controls = _axis_aligned_route()

        out = render_overlay(image, route, controls)

        assert out.shape == image.shape
        assert out.dtype == np.uint8
        assert np.array_equal(image, original)

    def test_leg_polylines_are_drawn_pixel_for_pixel(self) -> None:
        """Sample points taken directly from `Leg.polyline`, away from any marker or label, must
        be the exact core route colour -- not merely "different from the background somewhere"."""
        image = _image(100, 140)
        route, controls = _axis_aligned_route()

        out = render_overlay(image, route, controls)

        # leg0: horizontal segment y=10, x in [10, 50] -- sample (x=30, y=10)
        assert tuple(int(c) for c in out[10, 30]) == _CORE_COLOR
        # leg1: vertical segment x=50, y in [10, 60] -- sample (x=50, y=35)
        assert tuple(int(c) for c in out[35, 50]) == _CORE_COLOR
        # leg2 first segment: horizontal y=60, x in [10, 50] -- sample (x=30, y=60)
        assert tuple(int(c) for c in out[60, 30]) == _CORE_COLOR
        # leg2 second segment: vertical x=10, y in [10, 60] -- sample (x=10, y=40)
        assert tuple(int(c) for c in out[40, 10]) == _CORE_COLOR

    def test_missing_control_raises_value_error(self) -> None:
        image = _image(100, 140)
        route, controls = _axis_aligned_route()
        controls_missing_one = [c for c in controls if c.id != 1]

        with pytest.raises(ValueError, match=r"\[1\]"):
            render_overlay(image, route, controls_missing_one)


class TestHubDrawnOnceAndDistinctly:
    def test_hub_marker_is_a_triangle_stops_are_circles(self) -> None:
        """A point straight below a marker's centre, just inside a filled circle of the marker
        radius but below an equilateral triangle's flat base (same circumradius, apex up), tells
        the two marker shapes apart with a single pixel read: coloured at every numbered stop,
        untouched at the hub. That confirms the hub is drawn once, with a shape distinct from the
        stop markers -- not as an extra, indistinguishable numbered circle."""
        image = _image(800, 1000)
        route, controls = _widely_spaced_route()

        out = render_overlay(image, route, controls)
        geo = _geometry(image)
        below = geo.marker_radius - 1  # inside the circle; below the triangle's base

        for control in controls:
            cx, cy = int(control.x), int(control.y)
            sample = tuple(int(c) for c in out[cy + below, cx])
            if control.is_hub:
                assert sample == (_BACKGROUND, _BACKGROUND, _BACKGROUND)
            else:
                assert sample == _CORE_COLOR


class TestWriteOverlay:
    def test_writes_a_readable_png_of_the_right_shape(self, tmp_path) -> None:
        image = _image(100, 140)
        route, controls = _axis_aligned_route()
        path = tmp_path / "overlay.png"

        write_overlay(path, image, route, controls)

        assert path.exists()
        read_back = cv2.imread(str(path), cv2.IMREAD_COLOR)
        assert read_back.shape == (100, 140, 3)

    def test_raises_clearly_on_a_missing_parent_directory(self, tmp_path) -> None:
        image = _image(100, 140)
        route, controls = _axis_aligned_route()
        path = tmp_path / "missing_dir" / "overlay.png"

        with pytest.raises(OSError):
            write_overlay(path, image, route, controls)
