"""The API trusts nobody: every request carries a short-lived JWT minted by the web server
(HS256, shared key), and roles are enforced here, not in the frontend.
The allowlist is re-checked (cached 60 s) so revoking a user takes effect within a minute."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Annotated, Literal

import jwt
from fastapi import Depends, Request
from sqlalchemy import text

from apps.api.db import db
from apps.api.errors import Problem, forbidden
from core.config import get_env

Role = Literal["admin", "viewer"]


@dataclass(frozen=True)
class User:
    email: str
    role: Role
    scope: str = "app"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


_allow: dict[str, tuple[str, bool]] = {}
_allow_loaded = 0.0


async def _allowlist() -> dict[str, tuple[str, bool]]:
    global _allow, _allow_loaded
    if time.monotonic() - _allow_loaded > 60:
        async with db.ro.connect() as conn:
            rows = (await conn.execute(text("select email, role, disabled from ops.users"))).all()
        _allow = {r.email: (r.role, r.disabled) for r in rows}
        _allow_loaded = time.monotonic()
    return _allow


def invalidate_allowlist() -> None:
    global _allow_loaded
    _allow_loaded = 0.0


def _unauthorized(detail: str) -> Problem:
    return Problem(401, "unauthorized", "Unauthorized", detail)


async def current_user(request: Request) -> User:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise _unauthorized("Sign in to see this. Your session token is missing.")
    try:
        claims = jwt.decode(
            header[7:],
            get_env().api_jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "sub", "role"]},
            leeway=5,
        )
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Your session token expired. Reload the page.") from None
    except jwt.InvalidTokenError:
        raise _unauthorized("Your session token isn't valid. Sign in again.") from None
    email = str(claims["sub"]).lower()
    allowed = (await _allowlist()).get(email)
    if allowed is None or allowed[1]:
        raise forbidden("This account no longer has access. Ask an admin to invite you.")
    role: Role = "admin" if allowed[0] == "admin" else "viewer"
    scope = str(claims.get("scope", "app"))
    if scope == "print" and request.method != "GET":
        raise forbidden("Print tokens are read-only.")
    user = User(email=email, role=role, scope=scope)
    request.state.user_id = email
    return user


async def require_admin(user: Annotated[User, Depends(current_user)]) -> User:
    if not user.is_admin:
        raise forbidden("Only admins can do this.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
