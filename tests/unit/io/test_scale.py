"""Scale and calibration (T011): DPI + map scale, and two-point calibration, to metres per
pixel (SPEC F2, F3).
"""

from __future__ import annotations

import pytest

from fixtures.synth_map import meters_per_pixel as fixture_meters_per_pixel
from rogaine.io.corpus import Calibration as CorpusCalibration
from rogaine.io.scale import Calibration, mpp_from_dpi


class TestMppFromDpi:
    def test_matches_the_exact_formula(self) -> None:
        # mpp = (25.4 / dpi) * N / 1000 — worked by hand: (25.4/300)*30000/1000 = 2.54
        assert mpp_from_dpi(dpi=300.0, scale_denominator=30000.0) == pytest.approx(
            2.54, abs=1e-6
        )

    def test_agrees_with_the_fixture_oracle_across_several_scales(self) -> None:
        for dpi, scale_denominator in [(300.0, 30000.0), (150.0, 15000.0), (600.0, 50000.0)]:
            assert mpp_from_dpi(dpi, scale_denominator) == pytest.approx(
                fixture_meters_per_pixel(scale_denominator, dpi), abs=1e-6
            )

    def test_zero_dpi_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="dpi must be positive"):
            mpp_from_dpi(dpi=0.0, scale_denominator=30000.0)

    def test_negative_dpi_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="dpi must be positive"):
            mpp_from_dpi(dpi=-300.0, scale_denominator=30000.0)

    def test_zero_scale_denominator_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="scale_denominator must be positive"):
            mpp_from_dpi(dpi=300.0, scale_denominator=0.0)


class TestCalibration:
    def test_two_point_calibration_matches_the_fixture_scale_within_one_percent(
        self, clean_synthetic_map
    ) -> None:
        true_mpp = clean_synthetic_map.meters_per_pixel
        x1, y1, x2, y2 = 100.0, 500.0, 900.0, 500.0
        true_meters = (x2 - x1) * true_mpp
        # A person pacing this off on the ground rounds to the nearest 10 m — the calibration
        # should still recover the fixture's true scale to within 1%, not bit-for-bit.
        rounded_meters = round(true_meters / 10.0) * 10.0
        cal = Calibration(x1=x1, y1=y1, x2=x2, y2=y2, meters=rounded_meters)
        assert cal.meters_per_pixel == pytest.approx(true_mpp, rel=0.01)

    def test_diagonal_points_use_euclidean_distance(self) -> None:
        cal = Calibration(x1=0.0, y1=0.0, x2=3.0, y2=4.0, meters=10.0)
        assert cal.meters_per_pixel == pytest.approx(2.0)  # 10 m / hypot(3, 4) = 10 / 5

    def test_coincident_points_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="distinct"):
            Calibration(x1=1.0, y1=1.0, x2=1.0, y2=1.0, meters=100.0)

    def test_nonpositive_distance_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            Calibration(x1=0.0, y1=0.0, x2=1.0, y2=0.0, meters=0.0)

    def test_corpus_reuses_this_calibration_not_a_copy(self) -> None:
        # Guards against the two modules drifting into independent implementations of the
        # same physics (see corpus.py's comment above its Calibration import).
        assert CorpusCalibration is Calibration
