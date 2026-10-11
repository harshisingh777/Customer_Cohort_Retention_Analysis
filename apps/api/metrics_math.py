"""The only arithmetic the API does on mart numbers (spec §3, ownership rules): divide summed
additive counts, compute intervals, read percentiles off histograms, and decide whether a
difference clears the findings bar. No metric is defined here; metrics.yml and dbt own that.
Tested against dbt rollups in tests/math and tests/pipeline."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

Z95 = 1.959963984540054
SMALL_N = 30


def rate(k: float, n: float) -> float | None:
    return k / n if n else None


def wilson(k: float, n: float, z: float = Z95) -> tuple[float, float] | None:
    """Wilson score interval for k successes in n trials."""
    if n <= 0:
        return None
    p = min(max(k / n, 0.0), 1.0)
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    # Exact endpoints at the extremes (floating point would otherwise leave 1.0 just outside).
    lo = 0.0 if k <= 0 else max(0.0, centre - half)
    hi = 1.0 if k >= n else min(1.0, centre + half)
    return lo, hi


def median(values: Sequence[float]) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2


def quantile(values: Sequence[float], q: float) -> float:
    """Linear-interpolated quantile (numpy's default method)."""
    vals = sorted(values)
    if not vals:
        raise ValueError("quantile of empty sequence")
    pos = (len(vals) - 1) * q
    lo = math.floor(pos)
    hi = min(lo + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)


def hist_percentile(hist: Iterable[tuple[int, int]], q: float) -> int | None:
    """Nearest-rank percentile from (value, count) pairs."""
    pairs = sorted((v, c) for v, c in hist if c > 0)
    total = sum(c for _, c in pairs)
    if total == 0:
        return None
    target = max(1, math.ceil(q * total))
    running = 0
    for v, c in pairs:
        running += c
        if running >= target:
            return v
    return pairs[-1][0]


def change(current: float | None, previous: float | None, kind: str) -> dict | None:
    """Rates change in percentage points; counts and money in percent."""
    if current is None or previous is None:
        return None
    if kind == "rate":
        return {"value": round((current - previous) * 100, 1), "unit": "pts"}
    if previous == 0:
        return None
    return {"value": round((current - previous) / previous * 100, 1), "unit": "pct"}


def baseline_interval(
    rates: Sequence[float], sizes: Sequence[int]
) -> tuple[float, float, float] | None:
    """Median of the comparison cohorts and the Wilson interval at that rate for their
    average size (metrics.yml: rules.findings)."""
    if not rates:
        return None
    med = median(rates)
    avg_n = sum(sizes) / len(sizes)
    if med is None or avg_n <= 0:
        return None
    lo, hi = wilson(med * avg_n, avg_n)  # type: ignore[misc]
    return med, lo, hi


def clears_bar(value: float, n: int, base: tuple[float, float, float] | None, base_n: int) -> bool:
    if base is None or n < SMALL_N or base_n < SMALL_N:
        return False
    _, lo, hi = base
    return value < lo or value > hi


def outside_own_interval(k: int, n: int, reference: float, reference_n: int) -> bool:
    """Category-vs-store comparisons: is the store rate outside the category's interval?"""
    if n < SMALL_N or reference_n < SMALL_N:
        return False
    ci = wilson(k, n)
    return ci is not None and (reference < ci[0] or reference > ci[1])


def payback_month(
    cum_revenue_per_customer: Sequence[float], gross_margin: float | None, cac: float | None
) -> int | None:
    if not gross_margin or not cac or cac <= 0:
        return None
    for month, cum in enumerate(cum_revenue_per_customer):
        if cum * gross_margin >= cac:
            return month
    return None


def ratio_phrase(r: float) -> str:
    if 1.9 <= r <= 2.1:
        return "twice"
    if 2.9 <= r <= 3.1:
        return "three times"
    if 0.45 <= r <= 0.55:
        return "half"
    if r >= 1:
        return f"{r:.1f} times"
    return f"{round(r * 100)}% of"
