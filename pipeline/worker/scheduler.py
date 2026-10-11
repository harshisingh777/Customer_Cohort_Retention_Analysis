"""Internal schedule: one refresh per day at the configured local time, one CLV fit per week.
The (kind, scheduled_for) unique key makes restarts and double-schedules harmless."""

from __future__ import annotations

import datetime as dt

from core.db import Conn, read_store_settings
from pipeline.worker.jobs import enqueue


def schedule_due(conn: Conn, now: dt.datetime | None = None) -> list[int]:
    s = read_store_settings(conn)
    now_local = (now or dt.datetime.now(dt.UTC)).astimezone(s.tz)
    hh, mm = (int(x) for x in s.refresh_time_local.split(":"))
    slot = now_local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    created: list[int] = []
    if now_local >= slot:
        job = enqueue(
            conn, "refresh", {"trigger": "schedule"}, scheduled_for=slot, created_by="scheduler"
        )
        if job:
            created.append(job)
    clv_slot = slot + dt.timedelta(minutes=30)
    if now_local.weekday() == s.clv_weekday and now_local >= clv_slot:
        job = enqueue(
            conn, "clv_fit", {"trigger": "schedule"}, scheduled_for=clv_slot, created_by="scheduler"
        )
        if job:
            created.append(job)
    return created
