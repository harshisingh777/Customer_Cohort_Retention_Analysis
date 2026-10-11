"""Exports (spec §9.7). CSV streams straight from the API for any table view, honouring the
current filters (emails masked for viewers). PDF is an async job for admins: the worker
renders the print route and the result is downloaded through a signed URL valid for 24 hours."""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import hmac
import io
import time
import uuid
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import func, insert, select

from apps.api.auth import CurrentUser, User
from apps.api.cache import require_version
from apps.api.db import db
from apps.api.errors import Problem, forbidden, not_found
from apps.api.filters import Dims, Range, cohort_range, month_range
from apps.api.filters import dims as parse_dims
from apps.api.schemas import ExportOut, ExportRequest
from apps.api.services.channels import compute_channels
from apps.api.services.cohorts import cohort_rows
from apps.api.services.customers import customer_page
from apps.api.services.repeat import first_product
from apps.api.services.store import clv_status
from apps.api.tables import audit_t, export_files_t, exports_t, jobs_t, rfm_cells
from core.config import get_env

router = APIRouter(prefix="/v1/exports", tags=["exports"])
LINK_TTL = dt.timedelta(hours=24)
_recent: dict[str, deque] = defaultdict(deque)


def _rate_limit(user: User, limit: int = 20, window: float = 600) -> None:
    q = _recent[user.email]
    now = time.monotonic()
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        raise Problem(
            429,
            "rate-limited",
            "Too many exports",
            "You've started a lot of exports in the last 10 minutes. Wait a few minutes and retry.",
        )
    q.append(now)


def _list(params: dict, key: str) -> list[str]:
    v = params.get(key)
    if v is None:
        return []
    return [v] if isinstance(v, str) else list(v)


def _one(params: dict, key: str, default: str | None = None) -> str | None:
    v = params.get(key, default)
    return v[0] if isinstance(v, list) else v


async def _filters(params: dict, granularity: str = "month") -> tuple[Range, Dims]:
    d = await parse_dims(
        _list(params, "channel") or None,
        _list(params, "country") or None,
        _list(params, "category") or None,
    )
    if granularity == "month":
        r = await month_range(_one(params, "from"), _one(params, "to"))
    else:
        r = await cohort_range(granularity, _one(params, "from"), _one(params, "to"))  # type: ignore[arg-type]
    return r, d


def _csv_line(values: list) -> str:
    buf = io.StringIO()
    csv.writer(buf).writerow(["" if v is None else v for v in values])
    return buf.getvalue()


async def _csv_rows(view: str, params: dict, user: User) -> AsyncIterator[str]:
    if view == "cohorts":
        granularity = _one(params, "granularity", "month") or "month"
        measure = _one(params, "measure", "customers") or "customers"
        if granularity not in ("month", "week") or measure not in (
            "customers",
            "revenue",
            "cumulative",
        ):
            raise Problem(
                422, "invalid-request", "Invalid request", "Unknown granularity or measure."
            )
        rng, d = await _filters(params, granularity)
        async with db.ro.connect() as conn:
            rows = await cohort_rows(conn, granularity, measure, rng, d)
        n = max((len(r.rate) for r in rows), default=0)
        yield _csv_line(["cohort", "cohort_size", *[f"{granularity}_{i}" for i in range(n)]])
        for r in rows:
            yield _csv_line([r.cohort, r.size, *r.rate])
    elif view == "first_product":
        level_raw = _one(params, "level", "category") or "category"
        if level_raw not in ("category", "product"):
            raise Problem(
                422, "invalid-request", "Invalid request", "level must be category or product."
            )
        level = cast(Literal["category", "product"], level_raw)
        rng, d = await _filters(params)
        async with db.ro.connect() as conn:
            fp = await first_product(conn, level, rng, d, 30)
        yield _csv_line(
            [
                level,
                "first_time_buyers",
                "eligible_90d",
                "repeat_90d",
                "rate",
                "low",
                "high",
                "diff_pts",
            ]
        )
        for r in fp.rows:
            yield _csv_line(
                [
                    r.label,
                    r.first_buyers,
                    r.eligible,
                    r.repeaters,
                    r.rate,
                    r.low,
                    r.high,
                    r.diff_pts,
                ]
            )
    elif view in ("customers", "segments"):
        rng, d = await _filters(params)
        segment = _one(params, "segment")
        state = _one(params, "state", "all") or "all"
        cursor = None
        yield _csv_line(
            [
                "customer",
                "email",
                "cohort",
                "channel",
                "country",
                "first_category",
                "orders",
                "net_revenue",
                "last_order",
                "days_since_last",
                "lapsed",
                "segment",
                "p_alive",
                "pred_ltv_12m_p10",
                "pred_ltv_12m_p50",
                "pred_ltv_12m_p90",
            ]
        )
        async with db.ro.connect() as conn:
            _, visible, _, _ = await clv_status(conn)
            while True:
                page = await customer_page(
                    conn,
                    rng=rng,
                    dims=d,
                    segment=segment,
                    state=state,  # type: ignore[arg-type]
                    sort="value",
                    cursor=cursor,
                    limit=500,
                    reveal=user.is_admin,
                    clv_visible=visible,
                    with_total=False,
                )
                for r in page.rows:
                    yield _csv_line(
                        [
                            r.customer_key,
                            r.email,
                            r.cohort,
                            r.channel,
                            r.country,
                            r.first_category,
                            r.orders,
                            r.net_revenue,
                            r.last_order_date,
                            r.days_since_last,
                            r.is_lapsed,
                            r.segment,
                            r.p_alive,
                            r.pred_ltv_p10,
                            r.pred_ltv_p50,
                            r.pred_ltv_p90,
                        ]
                    )
                if not page.next_cursor:
                    break
                cursor = page.next_cursor
    elif view == "channels":
        rng = await month_range(_one(params, "from"), _one(params, "to"))
        async with db.ro.connect() as conn:
            ch = await compute_channels(conn, rng)
        yield _csv_line(
            [
                "channel",
                "new_customers",
                "spend",
                "cac",
                "ltv_365",
                "ltv_basis",
                "pred_ltv_12m_p10",
                "pred_ltv_12m_p50",
                "pred_ltv_12m_p90",
                "ltv_cac",
                "payback_month",
            ]
        )
        for r in ch.rows:
            yield _csv_line(
                [
                    r.channel,
                    r.new_customers,
                    r.spend,
                    r.cac,
                    r.ltv_365,
                    r.ltv_basis,
                    r.pred_ltv_p10,
                    r.pred_ltv_p50,
                    r.pred_ltv_p90,
                    r.ltv_cac,
                    r.payback_month,
                ]
            )
    elif view == "rfm":
        rng, d = await _filters(params)
        t = rfm_cells
        stmt = (
            select(
                t.c.rfm_r,
                t.c.rfm_f,
                t.c.rfm_segment,
                func.sum(t.c.customers).label("n"),
                func.sum(t.c.net_revenue).label("rev"),
            )
            .group_by(t.c.rfm_r, t.c.rfm_f, t.c.rfm_segment)
            .order_by(t.c.rfm_r.desc(), t.c.rfm_f.desc())
        )
        async with db.ro.connect() as conn:
            rows = (await conn.execute(rng.apply(d.apply(stmt, t), t.c.cohort_month))).all()
        yield _csv_line(["recency", "frequency", "segment", "customers", "net_revenue"])
        for r in rows:
            yield _csv_line([r.rfm_r, r.rfm_f, r.rfm_segment, int(r.n), float(r.rev)])
    else:
        raise Problem(
            422, "unsupported", "Not supported", f"CSV export isn't available for {view}."
        )


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def _sign(export_id: str, expires: int) -> str:
    key = get_env().export_signing_key.encode()
    return hmac.new(key, f"{export_id}:{expires}".encode(), hashlib.sha256).hexdigest()


@router.post(
    "",
    status_code=202,
    response_model=ExportOut,
    responses={200: {"content": {"text/csv": {}}, "description": "CSV, streamed"}},
    summary="CSV: streamed now (viewer). PDF: queued job (admin).",
)
async def create_export(body: ExportRequest, user: CurrentUser):
    require_version()
    _rate_limit(user)
    if body.format == "csv":
        gen = _csv_rows(body.view, body.params, user)
        first = await gen.__anext__()  # validate before streaming headers go out

        async def stream() -> AsyncIterator[bytes]:
            yield first.encode()
            async for line in gen:
                yield line.encode()

        async with db.ops.begin() as conn:
            await conn.execute(
                insert(audit_t).values(
                    actor=user.email,
                    action="export.csv",
                    detail={"view": body.view, "params": body.params},
                )
            )
        stamp = dt.date.today().isoformat()
        return StreamingResponse(
            stream(),
            status_code=200,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{body.view}-{stamp}.csv"'},
        )

    if not user.is_admin:
        raise forbidden("Only admins can export PDFs. You can export this view as CSV.")
    if body.view in ("customers", "first_product"):
        raise Problem(
            422, "unsupported", "Not supported", "PDF export covers page views; use CSV for tables."
        )
    async with db.ops.begin() as conn:
        row = (
            await conn.execute(
                insert(exports_t)
                .values(owner=user.email, format="pdf", view=body.view, params=body.params)
                .returning(exports_t.c.id, exports_t.c.created_at)
            )
        ).one()
        job_id = (
            await conn.execute(
                insert(jobs_t)
                .values(
                    kind="pdf_export", payload={"export_id": str(row.id)}, created_by=user.email
                )
                .returning(jobs_t.c.id)
            )
        ).scalar_one()
        await conn.execute(
            insert(audit_t).values(
                actor=user.email,
                action="export.pdf",
                detail={"export_id": str(row.id), "job_id": job_id, "view": body.view},
            )
        )
    return ExportOut(
        id=str(row.id),
        status="queued",
        view=body.view,
        created_at=row.created_at,
        download_url=None,
        expires_at=None,
        error=None,
    )


@router.get(
    "/{export_id}", response_model=ExportOut, summary="Export status and a 24-hour download link"
)
async def export_status(
    request: Request, user: CurrentUser, export_id: Annotated[str, Path(max_length=64)]
) -> ExportOut:
    # Export ids are uuids; anything else can't exist, and would make Postgres reject the query.
    if not _is_uuid(export_id):
        raise not_found("This export")
    async with db.ro.connect() as conn:
        e = (await conn.execute(select(exports_t).where(exports_t.c.id == export_id))).first()
    if e is None or (e.owner != user.email and not user.is_admin):
        raise not_found("This export")
    url = expires_at = None
    if e.status == "succeeded":
        expires_at = dt.datetime.now(dt.UTC) + LINK_TTL
        if e.storage == "s3":
            import boto3

            env = get_env()
            url = boto3.client(
                "s3", endpoint_url=env.s3_endpoint_url or None, region_name=env.s3_region or None
            ).generate_presigned_url(
                "get_object",
                Params={"Bucket": env.s3_bucket, "Key": e.storage_key},
                ExpiresIn=int(LINK_TTL.total_seconds()),
            )
        else:
            exp = int(expires_at.timestamp())
            url = str(
                request.url_for("export_file", export_id=export_id).include_query_params(
                    expires=exp, sig=_sign(export_id, exp)
                )
            )
    return ExportOut(
        id=str(e.id),
        status=e.status,
        view=e.view,
        created_at=e.created_at,
        download_url=url,
        expires_at=expires_at,
        error=e.error,
    )


@router.get("/{export_id}/file", name="export_file", include_in_schema=False)
async def export_file(
    export_id: Annotated[str, Path(max_length=64)],
    expires: Annotated[int, Query()],
    sig: Annotated[str, Query(max_length=128)],
) -> Response:
    if expires < time.time() or not hmac.compare_digest(sig, _sign(export_id, expires)):
        raise Problem(
            403,
            "link-expired",
            "Link expired",
            "This download link has expired. Open the export again.",
        )
    if not _is_uuid(export_id):
        raise not_found("This export file")
    async with db.ro.connect() as conn:
        f = (
            await conn.execute(
                select(export_files_t.c.content, export_files_t.c.content_type).where(
                    export_files_t.c.export_id == export_id
                )
            )
        ).first()
    if f is None:
        raise not_found("This export file")
    return Response(
        bytes(f.content),
        media_type=f.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="export-{export_id[:8]}.pdf"',
            "Cache-Control": "private, max-age=3600",
        },
    )
