"""RFC 9457 problem details. `detail` is written for people: the UI shows it verbatim."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

BASE = "https://retention.app/problems/"


class Problem(Exception):
    def __init__(self, status: int, type_: str, title: str, detail: str, **extra: Any) -> None:
        self.status = status
        self.type = type_
        self.title = title
        self.detail = detail
        self.extra = extra


def not_published() -> Problem:
    return Problem(
        503,
        "no-data",
        "No data published",
        "No data has been published yet. An admin can run a refresh from the Data page.",
    )


def forbidden(detail: str = "Your role can't do this. Ask an admin.") -> Problem:
    return Problem(403, "forbidden", "Forbidden", detail)


def not_found(what: str) -> Problem:
    return Problem(
        404, "not-found", "Not found", f"{what} doesn't exist or is no longer available."
    )


def _body(
    request: Request, status: int, type_: str, title: str, detail: str, extra: dict | None = None
) -> JSONResponse:
    payload = {
        "type": BASE + type_,
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "request_id": getattr(request.state, "request_id", None),
        **(extra or {}),
    }
    return JSONResponse(payload, status_code=status, media_type="application/problem+json")


async def problem_handler(request: Request, exc: Problem) -> JSONResponse:
    return _body(request, exc.status, exc.type, exc.title, exc.detail, exc.extra)


async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {"loc": [str(p) for p in e.get("loc", [])], "msg": e.get("msg")} for e in exc.errors()
    ]
    first = errors[0] if errors else {"loc": [], "msg": "invalid request"}
    field = ".".join(x for x in first["loc"] if x not in ("query", "body", "path"))
    detail = (
        f"Invalid value for {field}: {first['msg']}."
        if field
        else f"Invalid request: {first['msg']}."
    )
    return _body(request, 422, "invalid-request", "Invalid request", detail, {"errors": errors})


async def http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    titles = {
        401: "Unauthorized",
        404: "Not found",
        405: "Method not allowed",
        429: "Too many requests",
    }
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return _body(
        request,
        exc.status_code,
        f"http-{exc.status_code}",
        titles.get(exc.status_code, "Error"),
        detail,
    )


async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    return _body(
        request,
        500,
        "internal",
        "Internal error",
        "The server hit an unexpected error. Retry; if it keeps happening, share the request id with your admin.",
    )
