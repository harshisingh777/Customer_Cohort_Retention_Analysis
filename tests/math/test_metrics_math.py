"""The API's only arithmetic: intervals, percentiles, change, finding thresholds, payback."""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from apps.api import metrics_math as mm


def test_wilson_matches_spec_example():
    # Spec §8.5 example: "318 of 1,204 ... (26.4%, 24.0-28.9%)". The exact Wilson interval is
    # 24.00%-28.97%, so the illustration's upper bound is truncated; we check the exact values.
    lo, hi = mm.wilson(318, 1204)
    assert lo == pytest.approx(0.23999, abs=1e-4)
    assert hi == pytest.approx(0.28974, abs=1e-4)


def test_wilson_edges():
    assert mm.wilson(0, 0) is None
    lo, hi = mm.wilson(0, 10)
    assert lo == 0.0 and 0 < hi < 0.35
    lo, hi = mm.wilson(10, 10)
    assert hi == 1.0 and 0.65 < lo < 1


@given(st.integers(min_value=1, max_value=100_000), st.data())
def test_wilson_contains_the_rate(n, data):
    k = data.draw(st.integers(min_value=0, max_value=n))
    lo, hi = mm.wilson(k, n)
    assert 0 <= lo <= k / n <= hi <= 1


def test_rate():
    assert mm.rate(1, 4) == 0.25
    assert mm.rate(1, 0) is None


def test_median():
    assert mm.median([3, 1, 2]) == 2
    assert mm.median([4, 1, 2, 3]) == 2.5
    assert mm.median([]) is None


def test_hist_percentile_nearest_rank():
    hist = [(10, 1), (20, 1), (30, 1), (40, 1)]
    assert mm.hist_percentile(hist, 0.5) == 20
    assert mm.hist_percentile(hist, 0.9) == 40
    assert mm.hist_percentile([(5, 0)], 0.5) is None
    # Order of input doesn't matter.
    assert mm.hist_percentile(list(reversed(hist)), 0.5) == 20


def test_quantile_matches_numpy_linear():
    vals = [3, 1, 4, 1, 5, 9, 2, 6]
    assert mm.quantile(vals, 0.5) == 3.5
    assert mm.quantile(vals, 0.0) == 1
    assert mm.quantile(vals, 1.0) == 9
    assert math.isclose(mm.quantile(vals, 0.1), 1.0)


def test_change_points_vs_percent():
    assert mm.change(0.27, 0.29, "rate") == {"value": -2.0, "unit": "pts"}
    assert mm.change(1204, 1311, "count") == {"value": -8.2, "unit": "pct"}
    assert mm.change(84, 81, "currency") == {"value": 3.7, "unit": "pct"}
    assert mm.change(1, 0, "count") is None
    assert mm.change(None, 1, "rate") is None


def test_finding_bar_requires_30_on_both_sides():
    base = mm.baseline_interval([0.27, 0.28, 0.26, 0.27, 0.29, 0.27], [200] * 6)
    assert base is not None
    assert mm.clears_bar(0.21, 400, base, 1200)
    assert not mm.clears_bar(0.21, 29, base, 1200)
    assert not mm.clears_bar(0.21, 400, base, 29)
    assert not mm.clears_bar(0.27, 400, base, 1200)


def test_category_vs_store():
    assert mm.outside_own_interval(127, 412, 0.15, 5000)  # 31% vs 15%
    assert not mm.outside_own_interval(64, 412, 0.15, 5000)  # 15.5% vs 15%
    assert not mm.outside_own_interval(10, 20, 0.15, 5000)  # too few


@pytest.mark.parametrize(
    ("cum", "margin", "cac", "expected"),
    [
        ([10, 20, 30, 40], 0.5, 12, 2),
        ([10, 20, 30, 40], 0.5, 25, None),
        ([10, 20], None, 5, None),
        ([10, 20], 0.5, None, None),
        ([60], 0.5, 30, 0),
    ],
)
def test_payback_month(cum, margin, cac, expected):
    assert mm.payback_month(cum, margin, cac) == expected


@pytest.mark.parametrize(
    ("ratio", "phrase"),
    [(2.0, "twice"), (3.0, "three times"), (0.5, "half"), (1.4, "1.4 times"), (0.71, "71% of")],
)
def test_ratio_phrase(ratio, phrase):
    assert mm.ratio_phrase(ratio) == phrase
