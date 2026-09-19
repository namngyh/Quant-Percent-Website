from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select

from app.core.deps import AdminUser, SessionDep, require_csrf
from app.core.ratelimit import client_ip
from app.db.models import User
from app.schemas.auth import AdminUserList, AdminUserOut, AdminUserUpdate
from app.services import auth as auth_service

router = APIRouter(prefix="/admin", tags=["admin"])


def _row(user: User) -> AdminUserOut:
    return AdminUserOut(
        id=str(user.id),
        email=user.email,
        name=user.full_name,
        role=user.role,
        status=user.status,
        email_verified=user.email_verified_at is not None,
        author_request_status=user.author_request_status,
        author_request_at=user.author_request_at,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@router.get("/users", response_model=AdminUserList)
async def list_users(
    session: SessionDep,
    admin: AdminUser,
    count: int = Query(50, ge=1, le=200),
) -> AdminUserList:
    """Newest first, so a fresh registration is the first thing on screen.

    `count` rather than real paging: there is no pagination anywhere in this
    API yet, and inventing one for a list of this size would be the larger
    mistake. It will need revisiting once the ceiling is a real constraint.
    """
    rows = await session.scalars(
        select(User).order_by(User.created_at.desc()).limit(count)
    )
    return AdminUserList(users=[_row(u) for u in rows])


async def _count_admins(session) -> int:
    return await session.scalar(
        select(func.count()).select_from(User).where(User.role == "admin")
    )


@router.patch(
    "/users/{user_id}",
    response_model=AdminUserOut,
    dependencies=[Depends(require_csrf)],
)
async def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
) -> AdminUserOut:
    target = await session.scalar(select(User).where(User.id == user_id))
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"}
        )

    role = payload.role
    if payload.author_request == "approve":
        role = "author"

    losing_admin = target.role == "admin" and role is not None and role != "admin"
    being_disabled = payload.status == "disabled"

    # An admin must not be able to lock themselves out: without this, one
    # careless click on your own row leaves the site with no way back in short
    # of editing the database by hand.
    if target.id == admin.id and (losing_admin or being_disabled):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "cannot_modify_self"},
        )

    # Unreachable while the rail above stands, and deliberately kept anyway.
    # Reaching it needs the sole remaining admin to be somebody other than the
    # caller, but only an admin gets this far — so when the count is one, that
    # one is the caller and the self-check already fired. It is here so that
    # relaxing the self-check later cannot quietly delete the last admin.
    if (losing_admin or being_disabled) and target.role == "admin":
        if await _count_admins(session) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "last_admin"},
            )

    ip = client_ip(request)
    before = target.role

    if payload.author_request == "approve":
        target.role = "author"
        # Approval lives in role from here on; leaving the flag set would give
        # the same fact two homes that can drift apart.
        target.author_request_status = None
        await auth_service.record_audit(
            session, "user.role_grant", actor_id=admin.id, entity="user",
            entity_id=str(target.id), ip=ip,
            meta={"from": before, "to": "author", "via": "request"},
        )
    elif payload.author_request == "reject":
        target.author_request_status = "rejected"
        await auth_service.record_audit(
            session, "user.role_request_reject", actor_id=admin.id,
            entity="user", entity_id=str(target.id), ip=ip,
        )
    elif role is not None and role != target.role:
        target.role = role
        target.author_request_status = None
        await auth_service.record_audit(
            session,
            "user.role_grant" if role != "user" else "user.role_revoke",
            actor_id=admin.id, entity="user", entity_id=str(target.id), ip=ip,
            meta={"from": before, "to": role, "via": "direct"},
        )

    if payload.status is not None and payload.status != target.status:
        was = target.status
        target.status = payload.status
        await auth_service.record_audit(
            session, "user.status_change", actor_id=admin.id, entity="user",
            entity_id=str(target.id), ip=ip,
            meta={"from": was, "to": payload.status},
        )

    # utcnow_column has no onupdate, so nothing bumps this on its own.
    target.updated_at = datetime.now(UTC)
    await session.commit()
    return _row(target)
