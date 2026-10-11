"""Data-version keyed response cache and ETags (spec §9.2).

Data changes once a day. Responses are cached in-process, keyed by
(data_version, route, normalised params, role); a publish changes the version, so
invalidation is automatic. Repeat requests with a matching ETag get 304.
"""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request, Response
from pydantic import BaseModel

from apps.api.db import DataVersion, db
from apps.api.errors import not_published

CACHE_CONTROL = "private, max-age=60, stale-while-revalidate=600"
IGNORED_PARAMS = {"_"}


class LRU:
    def __init__(self, max_entries: int = 1024) -> None:
        self.max = max_entries
        self._d: OrderedDict[tuple, bytes] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: tuple) -> bytes | None:
        v = self._d.get(key)
        if v is None:
            self.misses += 1
            return None
        self._d.move_to_end(key)
        self.hits += 1
        return v

    def set(self, key: tuple, value: bytes) -> None:
        self._d[key] = value
        self._d.move_to_end(key)
        while len(self._d) > self.max:
            self._d.popitem(last=False)

    def clear(self) -> None:
        self._d.clear()


cache = LRU()
db.on_change.append(lambda _v: cache.clear())


def require_version() -> DataVersion:
    if db.current is None:
        raise not_published()
    return db.current


def normalized_params(request: Request) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted((k, v) for k, v in request.query_params.multi_items() if k not in IGNORED_PARAMS)
    )


def make_etag(*parts: Any) -> str:
    digest = hashlib.sha256(json.dumps(parts, default=str, sort_keys=True).encode()).hexdigest()[
        :24
    ]
    return f'W/"{digest}"'


def _headers(etag: str, version: DataVersion | None) -> dict[str, str]:
    h = {"ETag": etag, "Cache-Control": CACHE_CONTROL}
    if version:
        h["X-Data-Version"] = version.version
    return h


def serialize(payload: BaseModel | dict) -> bytes:
    if isinstance(payload, BaseModel):
        return payload.model_dump_json(by_alias=True).encode()
    return json.dumps(payload, default=str, separators=(",", ":")).encode()


async def cached(
    request: Request,
    compute: Callable[[DataVersion], Awaitable[BaseModel | dict]],
    *,
    vary: tuple = (),
) -> Response:
    version = require_version()
    request.state.data_version = version.version
    key = (version.version, request.url.path, normalized_params(request), *vary)
    etag = make_etag(*key)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=_headers(etag, version))
    body = cache.get(key)
    if body is None:
        body = serialize(await compute(version))
        cache.set(key, body)
    return Response(body, media_type="application/json", headers=_headers(etag, version))


async def uncached(
    request: Request, payload: BaseModel | dict, version: DataVersion | None = None
) -> Response:
    """Content-hashed ETag for responses that change without a publish (runs, settings)."""
    body = serialize(payload)
    etag = make_etag(hashlib.sha256(body).hexdigest())
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=_headers(etag, version))
    headers = _headers(etag, version)
    headers["Cache-Control"] = "private, no-cache"
    return Response(body, media_type="application/json", headers=headers)
