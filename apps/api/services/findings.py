"""Plain-language findings from deterministic templates (spec §8.8). No LLM.

A comparison finding is shown only when it clears the bar in metrics.yml (rules.findings):
outside the 95% interval of its baseline, with at least 30 customers on both sides. Every
sentence links to the view that proves it. At most three per page, largest effect first.
"""

from __future__ import annotations

import datetime as dt
from urllib.parse import urlencode

from apps.api import metrics_math as mm
from apps.api.filters import Dims
from apps.api.schemas import CohortRow, Finding, FirstProduct, SecondOrder
from apps.api.services.cohorts import human_cohort

MAX_FINDINGS = 3


def pct(x: float) -> str:
    v = x * 100
    return f"{v:.0f}%" if v >= 10 or v == 0 else f"{v:.1f}%"


def _qs(dims: Dims, **extra: str) -> str:
    params: list[tuple[str, str]] = [(k, v) for k, v in extra.items() if v]
    for name, values in (
        ("channel", dims.channel),
        ("country", dims.country),
        ("category", dims.category),
    ):
        params += [(name, v) for v in values]
    return urlencode(params)


def cohort_findings(rows: list[CohortRow], granularity: str, dims: Dims) -> list[Finding]:
    """Each of the three latest cohorts against the six before it, on cumulative repeat at the
    latest period they can all be compared on. `rows` must use the cumulative measure."""
    out: list[Finding] = []
    unit = "month" if granularity == "month" else "week"
    for idx in range(max(0, len(rows) - 3), len(rows)):
        cohort = rows[idx]
        previous = rows[max(0, idx - 6) : idx]
        if len(previous) < 3:
            continue
        n_period = len(cohort.rate) - 1
        if n_period < 1:
            continue
        value = cohort.rate[n_period]
        base_rates = [
            r.rate[n_period]
            for r in previous
            if len(r.rate) > n_period and r.rate[n_period] is not None
        ]
        base_sizes = [r.size for r in previous if len(r.rate) > n_period]
        if value is None or len(base_rates) < 3:
            continue
        base = mm.baseline_interval(base_rates, base_sizes)  # type: ignore[arg-type]
        if not mm.clears_bar(value, cohort.size, base, sum(base_sizes)):
            continue
        med = base[0]  # type: ignore[index]
        direction = "less" if value < med else "more"
        d = dt.date.fromisoformat(cohort.cohort + ("-01" if granularity == "month" else ""))
        out.append(
            Finding(
                id=f"cohort:{cohort.cohort}",
                kind="cohort",
                text=(
                    f"Customers acquired in {human_cohort(d, granularity)} bought again {direction} often than usual: "
                    f"{pct(value)} by {unit} {n_period}, against {pct(med)} for the previous six cohorts."
                ),
                href=f"/cohorts?{_qs(dims, granularity=granularity, measure='cumulative', select=cohort.cohort)}",
                effect=abs(value - med) / med if med else abs(value),
                metric_ids=["cumulative_repeat", "cohort"],
            )
        )
    return out


def timing_finding(so: SecondOrder, dims: Dims) -> Finding | None:
    if so.repeaters < mm.SMALL_N or so.median_days is None:
        return None
    text = f"Half of returning customers place their second order within {so.median_days} days."
    if so.share_after_90 is not None:
        if so.share_after_90 < 0.1:
            text += " After 90 days, fewer than 1 in 10 still do."
        else:
            text += f" {pct(so.share_after_90)} of second orders come after day 90."
    return Finding(
        id="timing",
        kind="timing",
        text=text,
        href=f"/repeat?{_qs(dims)}",
        effect=0.0,
        metric_ids=["time_to_second_order"],
    )


def first_purchase_findings(fp: FirstProduct, dims: Dims) -> list[Finding]:
    store = fp.store
    if store.rate is None or store.rate == 0:
        return []
    out = []
    for row in fp.rows:
        if row.rate is None:
            continue
        if not mm.outside_own_interval(row.repeaters, row.eligible, store.rate, store.eligible):
            continue
        ratio = row.rate / store.rate
        out.append(
            Finding(
                id=f"first:{fp.level}:{row.item_id}",
                kind="first_purchase",
                text=(
                    f"Customers whose first order was in {row.label} came back within 90 days at "
                    f"{mm.ratio_phrase(ratio)} the store average ({pct(row.rate)} vs {pct(store.rate)}, "
                    f"{row.eligible:,} customers)."
                ),
                href=f"/repeat?{_qs(dims, level=fp.level, highlight=row.item_id)}",
                effect=abs(ratio - 1),
                metric_ids=["repeat_90d"],
            )
        )
    out.sort(key=lambda f: -f.effect)
    return out[:MAX_FINDINGS]


def pick(findings: list[Finding], *, low_repeat: bool = False) -> list[Finding]:
    """Largest effect first; the descriptive timing sentence fills a remaining slot. For a
    low-repeat store the heatmap is mostly pale, so timing and first purchase lead."""
    timing = [f for f in findings if f.kind == "timing"]
    first = sorted((f for f in findings if f.kind == "first_purchase"), key=lambda f: -f.effect)
    cohort = sorted((f for f in findings if f.kind == "cohort"), key=lambda f: -f.effect)
    if low_repeat:
        ordered = timing + first + cohort
    else:
        ordered = sorted(first + cohort, key=lambda f: -f.effect) + timing
    return ordered[:MAX_FINDINGS]
