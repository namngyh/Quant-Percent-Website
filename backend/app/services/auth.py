from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    generate_csrf_token,
    generate_token,
    hash_password,
    hash_token,
    needs_rehash,
    refresh_expiry,
    verify_password,
)
from app.db.models import AuditLog, OneTimeToken, RefreshToken, User

RESET_TTL = timedelta(hours=1)
VERIFY_TTL = timedelta(days=3)


# --- Cookies ---------------------------------------------------------------


def _cookie_kwargs() -> dict:
    return {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "domain": settings.cookie_domain,
        "path": "/",
    }


def set_session_cookies(response: Response, user: User, refresh_token: str) -> None:
    """Session lives in httpOnly cookies so a script injection cannot read
    it; the CSRF cookie is deliberately readable for double-submit."""
    response.set_cookie(
        settings.access_cookie_name,
        create_access_token(user.id, user.email),
        max_age=settings.access_token_minutes * 60,
        **_cookie_kwargs(),
    )
    response.set_cookie(
        settings.refresh_cookie_name,
        refresh_token,
        max_age=settings.refresh_token_days * 24 * 3600,
        **_cookie_kwargs(),
    )
    csrf_kwargs = _cookie_kwargs()
    csrf_kwargs["httponly"] = False
    response.set_cookie(
        settings.csrf_cookie_name,
        generate_csrf_token(),
        max_age=settings.refresh_token_days * 24 * 3600,
        **csrf_kwargs,
    )


def clear_session_cookies(response: Response) -> None:
    for name in (
        settings.access_cookie_name,
        settings.refresh_cookie_name,
        settings.csrf_cookie_name,
    ):
        response.delete_cookie(
            name, domain=settings.cookie_domain, path="/"
        )


# --- Audit -----------------------------------------------------------------


async def record_audit(
    session: AsyncSession,
    action: str,
    *,
    actor_id: uuid.UUID | None = None,
    entity: str | None = None,
    entity_id: str | None = None,
    ip: str | None = None,
    meta: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            ip=ip if ip and ip != "unknown" else None,
            meta=meta,
        )
    )


# --- Registration / login --------------------------------------------------


async def register_user(
    session: AsyncSession,
    *,
    name: str,
    email: str,
    password: str,
    locale: str,
    ip: str | None,
) -> tuple[User, str | None]:
    """Create an account. Returns the user and an email-verification token.

    An already-registered address raises 409 — the sign-up form is a
    deliberate action by the person owning the address, so telling them
    the account exists is more useful than hiding it. (Password reset,
    which anyone can trigger for any address, stays non-committal.)
    """
    normalized = email.strip().lower()
    existing = await session.scalar(select(User).where(User.email == normalized))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "email_taken"},
        )

    user = User(
        email=normalized,
        password_hash=hash_password(password),
        full_name=name.strip(),
        locale=locale,
    )
    session.add(user)
    await session.flush()

    token = generate_token()
    session.add(
        OneTimeToken(
            user_id=user.id,
            purpose="email_verification",
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + VERIFY_TTL,
        )
    )
    await record_audit(
        session, "user.register", actor_id=user.id, entity="user",
        entity_id=str(user.id), ip=ip,
    )
    return user, token


async def authenticate(
    session: AsyncSession, *, email: str, password: str
) -> User:
    normalized = email.strip().lower()
    user = await session.scalar(select(User).where(User.email == normalized))
    # Same error and roughly the same work whether the account exists or
    # the password is wrong, so the response cannot enumerate accounts.
    if user is None:
        hash_password(password)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_credentials"},
        )
    if not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_credentials"},
        )
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "account_disabled"},
        )
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = datetime.now(UTC)
    return user


# --- Refresh tokens --------------------------------------------------------


async def issue_refresh_token(
    session: AsyncSession,
    user: User,
    *,
    family_id: uuid.UUID | None = None,
    user_agent: str | None = None,
    ip: str | None = None,
) -> str:
    token = generate_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(token),
            family_id=family_id or uuid.uuid4(),
            expires_at=refresh_expiry(),
            user_agent=(user_agent or "")[:400] or None,
            ip=ip if ip and ip != "unknown" else None,
        )
    )
    return token


async def rotate_refresh_token(
    session: AsyncSession,
    raw_token: str,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
) -> tuple[User, str]:
    """Exchange a refresh token for a new one.

    Replaying a token that was already rotated means it leaked, so the
    whole family is revoked and the holder must sign in again.
    """
    record = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_refresh_token"},
        )

    now = datetime.now(UTC)
    if record.revoked_at is not None:
        await session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == record.family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now, revoked_reason="reuse_detected")
        )
        await record_audit(
            session, "auth.refresh_reuse", actor_id=record.user_id, ip=ip,
            meta={"family_id": str(record.family_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "refresh_token_reused"},
        )

    if record.expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "refresh_token_expired"},
        )

    user = await session.scalar(select(User).where(User.id == record.user_id))
    if user is None or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_refresh_token"},
        )

    record.revoked_at = now
    record.revoked_reason = "rotated"
    new_token = await issue_refresh_token(
        session, user, family_id=record.family_id, user_agent=user_agent, ip=ip
    )
    return user, new_token


async def revoke_refresh_token(session: AsyncSession, raw_token: str) -> None:
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == hash_token(raw_token),
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC), revoked_reason="logout")
    )


# --- One-time tokens -------------------------------------------------------


async def create_one_time_token(
    session: AsyncSession, user: User, purpose: str, ttl: timedelta
) -> str:
    token = generate_token()
    session.add(
        OneTimeToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + ttl,
        )
    )
    return token


async def consume_one_time_token(
    session: AsyncSession, raw_token: str, purpose: str
) -> User:
    record = await session.scalar(
        select(OneTimeToken).where(
            OneTimeToken.token_hash == hash_token(raw_token),
            OneTimeToken.purpose == purpose,
        )
    )
    now = datetime.now(UTC)
    if record is None or record.used_at is not None or record.expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_or_expired_token"},
        )
    record.used_at = now
    user = await session.scalar(select(User).where(User.id == record.user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_or_expired_token"},
        )
    return user


async def set_password(session: AsyncSession, user: User, password: str) -> None:
    user.password_hash = hash_password(password)
    # A password change invalidates every existing session
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
        )
        .values(
            revoked_at=datetime.now(UTC),
            revoked_reason="password_changed",
        )
    )
