from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import csrf_matches, decode_access_token
from app.db.models import User
from app.db.session import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user_optional(
    request: Request, session: SessionDep
) -> User | None:
    """Resolve the signed-in user, or None. Never raises — endpoints that
    are open to everyone use this to decide how much to return."""
    token = request.cookies.get(settings.access_cookie_name)
    if not token:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            token = header[7:]
    if not token:
        return None

    payload = decode_access_token(token)
    if not payload:
        return None
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        return None

    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None or user.status != "active":
        return None
    return user


async def get_current_user(
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "not_authenticated"},
        )
    return user


async def require_csrf(request: Request) -> None:
    """Double-submit CSRF check for cookie-authenticated state changes.

    Only enforced when the request actually carries the session cookie —
    anonymous form posts (contact, login) are protected by rate limiting
    instead, and would otherwise need a token round-trip.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    if settings.access_cookie_name not in request.cookies:
        return
    if not csrf_matches(
        request.headers.get("x-csrf-token"),
        request.cookies.get(settings.csrf_cookie_name),
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "csrf_failed"},
        )


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]
