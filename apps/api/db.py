"""Database access for the API.

Two engines: `ro` (role api_ro: SELECT on analytics, read on ops) for every read, and `ops`
(role api_ops: INSERT on jobs/exports/audit_log, settings and users) for the few admin writes.
The current data version lives in memory, updated by LISTEN data_published on a direct
connection, with a 30-second poll as fallback.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import logging
import re
from dataclasses import dataclass

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from core.config import get_env, to_asyncpg_dsn, to_asyncpg_url

log = logging.getLogger(__name__)


@dataclass
class DataVersion:
    version: str
    data_through: dt.date
    published_at: dt.datetime


class Database:
    def __init__(self) -> None:
        env = get_env()
        if not env.api_database_url.startswith(("postgresql://", "postgres://", "postgresql+")):
            # Show what was set, minus anything that could be a password, so it can be fixed.
            seen = re.sub(r":[^:@/]*@", ":***@", env.api_database_url)[:40] or "empty"
            raise RuntimeError(
                f"API_DATABASE_URL must be a postgresql:// connection string; got: {seen}"
            )
        self.ro: AsyncEngine = create_async_engine(
            to_asyncpg_url(env.api_database_url),
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        self.ops: AsyncEngine = create_async_engine(
            to_asyncpg_url(env.api_ops_database_url or env.api_database_url),
            pool_size=2,
            max_overflow=2,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        self.current: DataVersion | None = None
        self._listener: asyncpg.Connection | None = None
        self._poller: asyncio.Task | None = None
        self.on_change: list = []

    async def refresh_version(self) -> DataVersion | None:
        async with self.ro.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "select version, data_through, published_at from ops.data_versions "
                        "order by published_at desc limit 1"
                    )
                )
            ).first()
        new = DataVersion(row.version, row.data_through, row.published_at) if row else None
        if new and (self.current is None or new.version != self.current.version):
            log.info("data version changed", extra={"data_version": new.version})
            for cb in self.on_change:
                cb(new)
        self.current = new
        return new

    async def start(self) -> None:
        try:
            await self.refresh_version()
        except Exception:
            log.exception("could not read data version at startup")
        self._poller = asyncio.create_task(self._poll())
        await self._listen()

    async def _listen(self) -> None:
        try:
            listener = await asyncpg.connect(to_asyncpg_dsn(get_env().api_database_url))
            await listener.add_listener("data_published", self._notified)
            self._listener = listener
        except Exception as e:  # The poll keeps things correct if LISTEN is unavailable.
            log.warning("LISTEN unavailable; relying on poll", extra={"error": str(e)})

    def _notified(self, *_: object) -> None:
        asyncio.get_running_loop().create_task(self.refresh_version())

    async def _poll(self) -> None:
        while True:
            await asyncio.sleep(30)
            try:
                await self.refresh_version()
                if self._listener is None or self._listener.is_closed():
                    await self._listen()
            except Exception as e:
                log.warning("data version poll failed", extra={"error": str(e)})

    async def stop(self) -> None:
        if self._poller:
            self._poller.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poller
        if self._listener and not self._listener.is_closed():
            await self._listener.close()
        await self.ro.dispose()
        await self.ops.dispose()


db = Database()
