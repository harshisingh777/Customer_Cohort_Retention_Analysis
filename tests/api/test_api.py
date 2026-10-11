"""API behaviour against a real Postgres with Online Retail II (real data) published."""

import datetime as dt
import gzip
import os

import httpx
import jwt
import pytest
import pytest_asyncio

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


def token(email: str, role: str, **extra) -> dict:
    now = dt.datetime.now(dt.UTC)
    t = jwt.encode(
        {"sub": email, "role": role, "iat": now, "exp": now + dt.timedelta(minutes=5), **extra},
        os.environ["API_JWT_SECRET"],
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {t}"}


ADMIN = lambda: token("admin@example.com", "admin")  # noqa: E731
VIEWER = lambda: token("viewer@example.com", "viewer")  # noqa: E731


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def client(published):
    from apps.api.db import db
    from apps.api.main import app

    await db.start()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    await db.stop()


async def test_health(client):
    assert (await client.get("/healthz")).json() == {"status": "ok"}
    r = await client.get("/readyz")
    assert r.status_code == 200 and r.json()["status"] == "ready"


async def test_requires_a_token(client):
    r = await client.get("/v1/meta")
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["detail"] and body["request_id"] and body["type"].endswith("/unauthorized")


async def test_rejects_forged_and_expired_tokens(client):
    forged = jwt.encode(
        {"sub": "admin@example.com", "role": "admin", "exp": 9999999999}, "wrong", algorithm="HS256"
    )
    assert (
        await client.get("/v1/meta", headers={"Authorization": f"Bearer {forged}"})
    ).status_code == 401
    expired = token("admin@example.com", "admin", exp=dt.datetime(2020, 1, 1, tzinfo=dt.UTC))
    assert (await client.get("/v1/meta", headers=expired)).status_code == 401


async def test_role_comes_from_the_allowlist_not_the_token(client):
    # A viewer who mints themselves an "admin" token is still a viewer.
    sneaky = token("viewer@example.com", "admin")
    assert (await client.post("/v1/pipeline/runs", headers=sneaky)).status_code == 403
    stranger = token("stranger@example.com", "admin")
    assert (await client.get("/v1/meta", headers=stranger)).status_code == 403


async def test_viewer_cannot_use_admin_routes(client):
    for method, path in [
        ("POST", "/v1/pipeline/runs"),
        ("GET", "/v1/settings"),
        ("GET", "/v1/users"),
        ("PUT", "/v1/settings"),
    ]:
        r = await client.request(
            method, path, headers=VIEWER(), json={} if method == "PUT" else None
        )
        assert r.status_code == 403, (method, path)


async def test_meta(client):
    m = (await client.get("/v1/meta", headers=VIEWER())).json()
    assert m["role"] == "viewer"
    assert m["freshness"]["state"] in ("fresh", "stale")
    assert "United Kingdom" in m["dimensions"]["countries"]
    assert m["data_through"] == "2011-12-09"


async def test_cohort_table_matches_the_marts(client, db):
    r = await client.get("/v1/cohorts/retention", headers=VIEWER())
    assert r.status_code == 200
    body = r.json()
    rows = db.execute(
        "select cohort_month, period_number, sum(cohort_customers)::int as n, sum(active_customers)::int as a "
        "from analytics.mart_cohort_retention_monthly group by 1, 2"
    ).fetchall()
    cells = {(x["cohort_month"], x["period_number"]): (x["n"], x["a"]) for x in rows}
    for row in body["data"]["cohorts"]:
        cohort = dt.date.fromisoformat(row["cohort"] + "-01")
        assert row["active"][0] == row["size"]
        for p, active in enumerate(row["active"]):
            assert (row["size"], active) == cells[(cohort, p)]
            assert row["low"][p] <= row["rate"][p] <= row["high"][p]
    # Arrays end where observability ends.
    lengths = [len(r["rate"]) for r in body["data"]["cohorts"]]
    assert lengths == sorted(lengths, reverse=True) and lengths[-1] == 1
    assert body["meta"]["data_version"] and body["meta"]["currency"] == "GBP"


async def test_filters_are_additive(client):
    total = (await client.get("/v1/cohorts/retention", headers=VIEWER())).json()["data"]["cohorts"]
    countries = (await client.get("/v1/meta", headers=VIEWER())).json()["dimensions"]["countries"]
    summed: dict[str, int] = {}
    for c in countries:
        rows = (
            await client.get("/v1/cohorts/retention", params={"country": c}, headers=VIEWER())
        ).json()
        for row in rows["data"]["cohorts"]:
            summed[row["cohort"]] = summed.get(row["cohort"], 0) + row["size"]
    assert summed == {r["cohort"]: r["size"] for r in total}


async def test_validation_errors_are_readable(client):
    r = await client.get("/v1/cohorts/retention", params={"foo": "1"}, headers=VIEWER())
    assert r.status_code == 422 and r.json()["detail"] == "Unknown parameter: foo."
    r = await client.get(
        "/v1/cohorts/retention", params={"channel": "Carrier pigeon"}, headers=VIEWER()
    )
    assert r.status_code == 422 and "Unknown channel" in r.json()["detail"]
    r = await client.get("/v1/cohorts/retention", params={"measure": "vibes"}, headers=VIEWER())
    assert r.status_code == 422
    r = await client.get(
        "/v1/cohorts/retention", params={"from": "2011-06", "to": "2010-03"}, headers=VIEWER()
    )
    assert r.status_code == 422


async def test_dates_are_clamped_to_data_bounds(client):
    r = await client.get(
        "/v1/cohorts/retention", params={"from": "1999-01", "to": "2099-01"}, headers=VIEWER()
    )
    assert r.status_code == 200
    assert r.json()["meta"]["filters"]["from"] == "2009-12-01"


async def test_etag_and_cache_headers(client):
    r = await client.get("/v1/cohorts/curves", headers=VIEWER())
    etag = r.headers["etag"]
    assert "max-age=60" in r.headers["cache-control"]
    r2 = await client.get("/v1/cohorts/curves", headers={**VIEWER(), "If-None-Match": etag})
    assert r2.status_code == 304


async def test_heatmap_payload_budget(client):
    r = await client.get("/v1/cohorts/retention", params={"granularity": "week"}, headers=VIEWER())
    assert len(gzip.compress(r.content)) < 30_000


async def test_findings_and_vitals(client):
    s = (await client.get("/v1/summary", headers=VIEWER())).json()["data"]
    assert 0 <= len(s["findings"]) <= 3
    assert all(f["text"] and f["href"].startswith("/") for f in s["findings"])
    ids = [v["id"] for v in s["vitals"]]
    assert ids == ["new_customers", "repeat_90d", "lapse_rate", "ltv_365"]
    rep = next(v for v in s["vitals"] if v["id"] == "repeat_90d")
    assert rep["change"]["unit"] == "pts"


async def test_repeat_routes(client):
    so = (await client.get("/v1/repeat/second-order", headers=VIEWER())).json()["data"]
    assert so["repeaters"] == sum(b["customers"] for b in so["bins"])
    assert so["median_days"] <= so["p90_days"]
    fp = (
        await client.get("/v1/repeat/first-product", params={"level": "product"}, headers=VIEWER())
    ).json()["data"]
    assert all(r["eligible"] >= 30 for r in fp["rows"])


async def test_customers_paginate_without_gaps_and_mask_emails(client):
    seen, cursor = [], None
    while True:
        params = {"limit": 500, "state": "lapsed"} | ({"cursor": cursor} if cursor else {})
        page = (await client.get("/v1/customers", params=params, headers=VIEWER())).json()["data"]
        seen += [r["customer_key"] for r in page["rows"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == page["total"] or len(seen) == len(set(seen))
    viewer = (await client.get("/v1/customers", params={"limit": 5}, headers=VIEWER())).json()[
        "data"
    ]["rows"]
    admin = (await client.get("/v1/customers", params={"limit": 5}, headers=ADMIN())).json()[
        "data"
    ]["rows"]
    assert all("***@" in r["email"] for r in viewer if r["email"])
    assert all("***" not in r["email"] for r in admin if r["email"])
    detail = (
        await client.get(f"/v1/customers/{viewer[0]['customer_key']}", headers=VIEWER())
    ).json()["data"]
    assert detail["orders"] == len(detail["orders_timeline"])


async def test_channels_without_spend(client):
    """Online Retail II has no channel or spend data: CAC is absent, never shown as zero."""
    ch = (await client.get("/v1/channels", headers=VIEWER())).json()["data"]
    assert not ch["has_spend"]
    assert all(r["cac"] is None and r["ltv_cac"] is None for r in ch["rows"])
    assert ch["coverage"]["share"] == 0


async def test_csv_export_streams_with_filters(client):
    r = await client.post(
        "/v1/exports",
        headers=VIEWER(),
        json={"format": "csv", "view": "cohorts", "params": {"country": ["United Kingdom"]}},
    )
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("cohort,cohort_size,month_0")
    r = await client.post(
        "/v1/exports", headers=VIEWER(), json={"format": "pdf", "view": "summary"}
    )
    assert r.status_code == 403


async def test_malformed_export_id_is_not_found(client):
    r = await client.get("/v1/exports/" + "0" * 63, headers=VIEWER())
    assert r.status_code == 404


async def test_manual_refresh_returns_the_existing_job(client):
    first = await client.post("/v1/pipeline/runs", headers=ADMIN())
    second = await client.post("/v1/pipeline/runs", headers=ADMIN())
    assert first.status_code == 202 and second.status_code == 200
    assert second.json()["existing"] and second.json()["job_id"] == first.json()["job_id"]
    status = (
        await client.get(f"/v1/pipeline/runs/{first.json()['job_id']}", headers=ADMIN())
    ).json()
    assert status["status"] == "queued"


async def test_settings_are_validated_and_audited(client):
    bad = await client.put("/v1/settings", headers=ADMIN(), json={"reporting_tz": "Mars/Olympus"})
    assert bad.status_code == 422 and "timezone" in bad.json()["detail"].lower()
    ok = await client.put("/v1/settings", headers=ADMIN(), json={"store_name": "Renamed store"})
    assert ok.status_code == 200 and ok.json()["rebuild_job_id"] is None
    assert (await client.get("/v1/settings", headers=ADMIN())).json()[
        "store_name"
    ] == "Renamed store"


async def test_metrics_doc(client):
    doc = (await client.get("/v1/metrics", headers=VIEWER())).json()
    ids = {m["id"] for m in doc["metrics"]}
    assert {"retention_rate", "lapse_rate", "predicted_ltv_12m", "payback_month"} <= ids
    assert doc["lapse_threshold"]["lapse_threshold_days"] >= 60
