"""One-line pipeline outcome to a Slack-compatible webhook. Failures alert immediately."""

from __future__ import annotations

import logging

import httpx

from core.config import get_env

log = logging.getLogger(__name__)


def post(text: str) -> None:
    url = get_env().pipeline_webhook_url
    if not url:
        return
    try:
        httpx.post(url, json={"text": text}, timeout=10).raise_for_status()
    except httpx.HTTPError as e:
        log.warning("webhook failed", extra={"error": str(e)})
