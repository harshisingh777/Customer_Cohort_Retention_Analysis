"""Invite-only user management (admin). Every change is audited."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from apps.api.auth import AdminUser, invalidate_allowlist
from apps.api.db import db
from apps.api.errors import Problem, not_found
from apps.api.schemas import UserInvite, UserOut, UserPatch
from apps.api.tables import audit_t, users_t

router = APIRouter(prefix="/v1/users", tags=["users"])


async def _admins_left(conn, excluding: str) -> int:
    return int(
        (
            await conn.execute(
                select(func.count())
                .select_from(users_t)
                .where(users_t.c.role == "admin", ~users_t.c.disabled, users_t.c.email != excluding)
            )
        ).scalar_one()
    )


@router.get("", response_model=list[UserOut], summary="Everyone with access")
async def list_users(user: AdminUser) -> list[UserOut]:
    async with db.ro.connect() as conn:
        rows = (await conn.execute(select(users_t).order_by(users_t.c.role, users_t.c.email))).all()
    return [UserOut(**r._mapping) for r in rows]


@router.post(
    "",
    response_model=UserOut,
    status_code=201,
    summary="Invite someone (they sign in with that email)",
)
async def invite(body: UserInvite, user: AdminUser) -> UserOut:
    email = str(body.email).lower()
    try:
        async with db.ops.begin() as conn:
            row = (
                await conn.execute(
                    insert(users_t)
                    .values(email=email, role=body.role, name=body.name, invited_by=user.email)
                    .returning(*users_t.c)
                )
            ).one()
            await conn.execute(
                insert(audit_t).values(
                    actor=user.email,
                    action="user.invite",
                    detail={"email": email, "role": body.role},
                )
            )
    except IntegrityError:
        raise Problem(409, "exists", "Already invited", f"{email} already has access.") from None
    invalidate_allowlist()
    return UserOut(**row._mapping)


@router.patch("/{email}", response_model=UserOut, summary="Change role or disable")
async def patch_user(
    body: UserPatch, user: AdminUser, email: Annotated[str, Path(max_length=320)]
) -> UserOut:
    email = email.lower()
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise Problem(422, "invalid-request", "Nothing to change", "Send a role or disabled value.")
    async with db.ops.begin() as conn:
        demoting = changes.get("role") == "viewer" or changes.get("disabled") is True
        if demoting and await _admins_left(conn, email) == 0:
            raise Problem(
                409, "last-admin", "Last admin", "Invite another admin before removing this one."
            )
        row = (
            await conn.execute(
                update(users_t)
                .where(users_t.c.email == email)
                .values(**changes)
                .returning(*users_t.c)
            )
        ).first()
        if row is None:
            raise not_found("This user")
        await conn.execute(
            insert(audit_t).values(
                actor=user.email, action="user.update", detail={"email": email, **changes}
            )
        )
    invalidate_allowlist()
    return UserOut(**row._mapping)


@router.delete("/{email}", status_code=204, summary="Remove access")
async def remove_user(user: AdminUser, email: Annotated[str, Path(max_length=320)]) -> None:
    email = email.lower()
    async with db.ops.begin() as conn:
        if await _admins_left(conn, email) == 0:
            target = (
                await conn.execute(select(users_t.c.role).where(users_t.c.email == email))
            ).scalar()
            if target == "admin":
                raise Problem(
                    409,
                    "last-admin",
                    "Last admin",
                    "Invite another admin before removing this one.",
                )
        res = await conn.execute(delete(users_t).where(users_t.c.email == email))
        if res.rowcount == 0:
            raise not_found("This user")
        await conn.execute(
            insert(audit_t).values(actor=user.email, action="user.remove", detail={"email": email})
        )
    invalidate_allowlist()
