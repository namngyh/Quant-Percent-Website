"""The members-only lock must live on the server.

On the website the lock is a blur plus an icon — presentation only. What
actually protects the data is `is_locked` and the 403 the router raises,
so those are tested directly.
"""

import pytest

from app.db.models import Model
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


@pytest.mark.parametrize(
    ("access", "authenticated", "expected"),
    [
        ("members", False, True),
        ("members", True, False),
        ("public", False, False),
        ("public", True, False),
    ],
)
def test_lock_matrix(access, authenticated, expected) -> None:
    assert is_locked(_model(access), authenticated) is expected


def test_guard_raises_403_for_anonymous_members_model() -> None:
    from fastapi import HTTPException

    from app.api.v1.routers.models import _guard

    with pytest.raises(HTTPException) as exc:
        _guard(_model("members"), None)
    assert exc.value.status_code == 403
    assert exc.value.detail == {"error": "members_only"}


def test_guard_allows_signed_in_visitor() -> None:
    from app.api.v1.routers.models import _guard

    _guard(_model("members"), object())  # must not raise


def test_guard_allows_public_model_anonymously() -> None:
    from app.api.v1.routers.models import _guard

    _guard(_model("public"), None)  # must not raise
