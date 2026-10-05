"""Tests for ``contam.stats.wilson_interval`` (D-014)."""

from __future__ import annotations

import pytest

from contam.stats import wilson_interval


def test_known_value_half_of_ten() -> None:
    low, high = wilson_interval(5, 10)
    assert low == pytest.approx(0.2366, abs=1e-3)
    assert high == pytest.approx(0.7634, abs=1e-3)


def test_known_value_zero_of_ten_has_upper_bound_near_28_percent() -> None:
    low, high = wilson_interval(0, 10)
    assert low == 0.0
    assert high == pytest.approx(0.2775, abs=1e-3)


def test_known_value_all_of_ten() -> None:
    low, high = wilson_interval(10, 10)
    assert low == pytest.approx(0.7225, abs=1e-3)
    assert high == 1.0


def test_no_observations_means_total_uncertainty() -> None:
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_more_data_gives_a_narrower_interval() -> None:
    small_low, small_high = wilson_interval(8, 10)
    large_low, large_high = wilson_interval(800, 1000)
    assert (large_high - large_low) < (small_high - small_low)


@pytest.mark.parametrize(("successes", "total"), [(-1, 5), (6, 5), (0, -1)])
def test_inconsistent_counts_are_rejected(successes: int, total: int) -> None:
    with pytest.raises(ValueError, match="invalid counts"):
        wilson_interval(successes, total)
