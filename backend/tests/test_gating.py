"""The members-only lock must live on the server.

On the website the lock is a blur plus an icon — presentation only. What
actually protects the data is `is_locked` and the 403 the router raises,
so those are tested directly.
"""

from datetime import UTC, datetime

import pytest

from app.db.models import Model, User
from app.services.models import is_locked


def _model(access: str) -> Model:
    return Model(
        slug="regime-hmm",
        code="QP-S01",
        name="Regime HMM",
        markets=["VNINDEX"],
        category="regime",
        status="active",
        visibility="public",
        access=access,
        featured=False,
        version="1.4.1",
        horizons=[1],
        show_forecast=True,
        show_performance=False,
        tagline={},
        key_output={},
        description={},
    )


def _user(*, verified: bool, role: str = "user") -> User:
    """A detached user; only email_verified_at and role are read by the gates."""
    return User(
        email="member@example.com",
        full_name="Nguyen Van A",
        locale="vi",
        status="active",
        role=role,
        email_verified_at=datetime.now(UTC) if verified else None,
    )


@pytest.mark.parametrize(
    ("access", "verified", "expected"),
    [
        ("members", False, True),
        ("members", True, False),
        ("public", False, False),
        ("public", True, False),
    ],
)
def test_lock_matrix(access, verified, expected) -> None:
    assert is_locked(_model(access), verified) is expected


def test_guard_raises_403_for_anonymous_members_model() -> None:
    from fastapi import HTTPException

    from app.api.v1.routers.models import _guard

    with pytest.raises(HTTPException) as exc:
        _guard(_model("members"), None)
    assert exc.value.status_code == 403
    assert exc.value.detail == {"error": "members_only"}


def test_guard_raises_403_for_unverified_member() -> None:
    """Signing in is no longer enough, and the error has to say which wall
    the visitor hit — "sign in" would send them round a loop they are in."""
    from fastapi import HTTPException

    from app.api.v1.routers.models import _guard

    with pytest.raises(HTTPException) as exc:
        _guard(_model("members"), _user(verified=False))
    assert exc.value.status_code == 403
    assert exc.value.detail == {"error": "email_not_verified"}


def test_guard_allows_verified_member() -> None:
    from app.api.v1.routers.models import _guard

    _guard(_model("members"), _user(verified=True))  # must not raise


def test_guard_allows_public_model_anonymously() -> None:
    from app.api.v1.routers.models import _guard

    _guard(_model("public"), None)  # must not raise


# ------------------------------------------------------------------ roles


@pytest.mark.parametrize(
    ("role", "expected"),
    [("user", False), ("author", False), ("admin", True)],
)
def test_is_admin_matrix(role, expected) -> None:
    from app.core.deps import is_admin

    assert is_admin(_user(verified=True, role=role)) is expected


def test_is_admin_rejects_anonymous() -> None:
    from app.core.deps import is_admin

    assert is_admin(None) is False


@pytest.mark.parametrize("role", ["user", "author"])
async def test_admin_dependency_refuses_non_admin(role) -> None:
    """403, not 401: the caller is signed in, they are simply not an admin."""
    from fastapi import HTTPException

    from app.core.deps import get_admin_user

    with pytest.raises(HTTPException) as exc:
        await get_admin_user(_user(verified=True, role=role))
    assert exc.value.status_code == 403
    assert exc.value.detail == {"error": "admin_only"}


async def test_admin_dependency_allows_admin() -> None:
    from app.core.deps import get_admin_user

    user = _user(verified=True, role="admin")
    assert await get_admin_user(user) is user


async def test_admin_does_not_need_a_confirmed_email() -> None:
    """AdminUser is built on CurrentUser, not VerifiedUser, so an admin whose
    address is unconfirmed is still an admin rather than getting the
    email_not_verified answer to a question about roles."""
    from app.core.deps import get_admin_user

    user = _user(verified=False, role="admin")
    assert await get_admin_user(user) is user
