from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings

_hasher = PasswordHasher()


# --- Passwords -------------------------------------------------------------


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
        return True
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, ValueError):
        return True


# --- Opaque tokens (refresh, password reset, email verification) -----------


def generate_token() -> str:
    """URL-safe secret handed to the user. Only its hash is stored."""
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """SHA-256 is right here: the token already has full entropy, so the
    slow hashing that passwords need would only add latency."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- Access token ----------------------------------------------------------


def create_access_token(user_id: uuid.UUID, email: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int(
            (now + timedelta(minutes=settings.access_token_minutes)).timestamp()
        ),
        "typ": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != "access":
        return None
    return payload


def refresh_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.refresh_token_days)


# --- CSRF ------------------------------------------------------------------


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_matches(header_value: str | None, cookie_value: str | None) -> bool:
    if not header_value or not cookie_value:
        return False
    return secrets.compare_digest(header_value, cookie_value)
