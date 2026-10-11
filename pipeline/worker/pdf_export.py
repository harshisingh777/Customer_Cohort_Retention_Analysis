"""PDF export (spec §9.7): open the web app's print route in headless Chromium with a one-time
token, wait for `data-ready`, print, store, and mark the export done. The print route reuses the
screen components, so there is no second template."""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from urllib.parse import urlencode

import jwt

from core.config import get_env
from core.db import Conn
from pipeline.worker.storage import store

log = logging.getLogger(__name__)
PRINT_VIEWS = {"summary", "cohorts", "repeat", "segments", "channels", "data"}


def mint_print_token(owner: str, role: str) -> str:
    env = get_env()
    now = dt.datetime.now(dt.UTC)
    return jwt.encode(
        {
            "sub": owner,
            "role": role,
            "scope": "print",
            "jti": uuid.uuid4().hex,
            "iat": now,
            "exp": now + dt.timedelta(minutes=5),
        },
        env.api_jwt_secret,
        algorithm="HS256",
    )


def render_pdf(url: str, timeout_ms: int = 60_000) -> bytes:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1240, "height": 1754})
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            page.wait_for_selector("[data-ready='true']", timeout=timeout_ms)
            return page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "14mm", "bottom": "14mm", "left": "12mm", "right": "12mm"},
            )
        finally:
            browser.close()


def run_pdf_export(conn: Conn, export_id: str) -> None:
    exp = conn.execute(
        "select e.*, coalesce(u.role, 'viewer') as role from ops.exports e "
        "left join ops.users u on u.email = e.owner where e.id = %s",
        (export_id,),
    ).fetchone()
    if not exp:
        raise ValueError(f"export {export_id} not found")
    if exp["view"] not in PRINT_VIEWS:  # type: ignore[index]
        raise ValueError(f"unknown print view {exp['view']!r}")  # type: ignore[index]
    conn.execute("update ops.exports set status = 'running' where id = %s", (export_id,))
    conn.commit()
    try:
        token = mint_print_token(exp["owner"], exp["role"])  # type: ignore[index]
        params = {k: v for k, v in (exp["params"] or {}).items() if v not in (None, "")}  # type: ignore[index]
        qs = urlencode({**params, "token": token}, doseq=True)
        url = f"{get_env().web_base_url.rstrip('/')}/print/{exp['view']}?{qs}"  # type: ignore[index]
        pdf = render_pdf(url)
        kind, key = store(conn, export_id, pdf, "application/pdf")
        conn.execute(
            "update ops.exports set status = 'succeeded', storage = %s, storage_key = %s, finished_at = now() "
            "where id = %s",
            (kind, key, export_id),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.execute(
            "update ops.exports set status = 'failed', error = %s, finished_at = now() where id = %s",
            (str(e)[:2000], export_id),
        )
        conn.commit()
        raise
