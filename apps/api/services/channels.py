"""Channel performance from additive marts plus spend. Shared by the route and CSV export."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection

from apps.api import metrics_math as mm
from apps.api.filters import Range
from apps.api.schemas import ChannelRow, Channels, Coverage
from apps.api.services.store import clv_status, read_settings
from apps.api.tables import channel_month, channel_spend, clv_group_draws, ltv_cohort

UNATTRIBUTED = "unattributed"


async def compute_channels(conn: AsyncConnection, rng: Range) -> Channels:
    cm, sp, lt = channel_month, channel_spend, ltv_cohort
    settings = await read_settings(conn)
    _, clv_visible, hidden_reason, _ = await clv_status(conn)
    cells = (
        await conn.execute(
            rng.apply(
                select(
                    cm.c.acquisition_channel,
                    cm.c.cohort_month,
                    cm.c.period_number,
                    cm.c.new_customers,
                    cm.c.net_revenue,
                ),
                cm.c.cohort_month,
            )
        )
    ).all()
    spend_rows = (
        await conn.execute(
            rng.apply(
                select(sp.c.channel, func.sum(sp.c.spend).label("spend")).group_by(sp.c.channel),
                sp.c.month,
            )
        )
    ).all()
    any_spend = bool((await conn.execute(select(func.count()).select_from(sp))).scalar())
    ltv_rows = (
        await conn.execute(
            rng.apply(
                select(
                    lt.c.acquisition_channel,
                    func.sum(lt.c.eligible_365d).label("elig"),
                    func.sum(lt.c.ltv_365d_sum).label("ltv"),
                ).group_by(lt.c.acquisition_channel),
                lt.c.cohort_month,
            )
        )
    ).all()
    pred: dict[str, tuple[float, float, float]] = {}
    if clv_visible:
        g = clv_group_draws
        draws: dict[str, list] = {}
        for row in (
            await conn.execute(
                rng.apply(
                    select(g.c.acquisition_channel, g.c.customers, g.c.draw_sums), g.c.cohort_month
                )
            )
        ).all():
            acc = draws.setdefault(row.acquisition_channel, [0, None])
            acc[0] += int(row.customers)
            acc[1] = (
                list(row.draw_sums)
                if acc[1] is None
                else [a + b for a, b in zip(acc[1], row.draw_sums, strict=True)]
            )
        # Average predicted value per customer, per posterior draw; its spread is the range.
        for ch, (n, sums) in draws.items():
            if n and sums:
                means = [x / n for x in sums]
                pred[ch] = (
                    mm.quantile(means, 0.1),
                    mm.quantile(means, 0.5),
                    mm.quantile(means, 0.9),
                )

    new: dict[str, int] = defaultdict(int)
    rev: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    size_at: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for r in cells:
        if r.period_number == 0:
            new[r.acquisition_channel] += int(r.new_customers)
        rev[r.acquisition_channel][r.period_number] += float(r.net_revenue)
        size_at[r.acquisition_channel][r.period_number] += int(r.new_customers)
    spend = {r.channel: float(r.spend) for r in spend_rows}
    ltv = {r.acquisition_channel: (int(r.elig), float(r.ltv)) for r in ltv_rows}

    rows: list[ChannelRow] = []
    for ch in sorted(set(new) | set(spend), key=lambda k: (-new.get(k, 0), k)):
        n = new.get(ch, 0)
        ch_spend = spend.get(ch) if any_spend else None
        cac = (ch_spend / n) if ch_spend is not None and n else None
        elig, ltv_sum = ltv.get(ch, (0, 0.0))
        p = pred.get(ch)
        if elig >= mm.SMALL_N:
            ltv_value, basis = ltv_sum / elig, "historical"
        elif p is not None:
            ltv_value, basis = p[1], "predicted"
        else:
            ltv_value, basis = None, None
        # Cumulative revenue per acquired customer: each period averages over the cohorts
        # that have reached it, then accumulates.
        cum, running = [], 0.0
        for period in sorted(rev.get(ch, {})):
            size = size_at[ch][period]
            running += rev[ch][period] / size if size else 0.0
            cum.append(running)
        rows.append(
            ChannelRow(
                channel=ch,
                new_customers=n,
                spend=ch_spend,
                cac=cac,
                ltv_365=ltv_value,
                ltv_365_eligible=elig,
                ltv_basis=basis,  # type: ignore[arg-type]
                pred_ltv_p10=p[0] if p is not None else None,
                pred_ltv_p50=p[1] if p is not None else None,
                pred_ltv_p90=p[2] if p is not None else None,
                ltv_cac=(ltv_value / cac) if ltv_value is not None and cac else None,
                payback_month=mm.payback_month(cum, settings.gross_margin, cac)
                if ch != UNATTRIBUTED
                else None,
            )
        )
    total_new = sum(new.values())
    attributed = total_new - new.get(UNATTRIBUTED, 0)
    data = Channels(
        coverage=Coverage(
            new_customers=total_new,
            attributed=attributed,
            share=attributed / total_new if total_new else None,
        ),
        has_spend=any_spend,
        gross_margin=settings.gross_margin,
        clv_visible=clv_visible,
        clv_hidden_reason=None if clv_visible else hidden_reason,
        rows=rows,
    )
    return data
