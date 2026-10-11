from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from apps.api.db import db

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness")
async def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness: database reachable and data published")
async def readyz() -> JSONResponse:
    try:
        async with db.ro.connect() as conn:
            await conn.execute(text("select 1"))
    except Exception:
        return JSONResponse(
            {"status": "unavailable", "reason": "database unreachable"}, status_code=503
        )
    if db.current is None:
        return JSONResponse(
            {"status": "unavailable", "reason": "no data version published"}, status_code=503
        )
    return JSONResponse(
        {
            "status": "ready",
            "data_version": db.current.version,
            "data_through": db.current.data_through.isoformat(),
        }
    )
