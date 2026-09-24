"""Nickname, avatar and the member-facing mail that greets them by name.

The endpoints themselves need a database; what is pinned here is everything
that decides what a member is allowed to store and what they are sent.
"""

import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.v1.routers import auth as auth_router
from app.core.config import Settings
from app.schemas.auth import UpdateProfileRequest
from app.services import email as email_service


# --- nickname -------------------------------------------------------------


@pytest.mark.parametrize(
    "value, stored",
    [
        ("Minh", "Minh"),
        ("  Nguyễn  Văn   An ", "Nguyễn Văn An"),
        ("quant.percent-01", "quant.percent-01"),
        ("", None),
        (None, None),
    ],
)
def test_nickname_accepted(value, stored) -> None:
    req = UpdateProfileRequest(name="A", nickname=value)
    assert req.nickname == stored


@pytest.mark.parametrize("value", ["x", "_hidden", "trailing-", "<b>hi</b>", "😀😀"])
def test_nickname_rejected(value) -> None:
    with pytest.raises(ValidationError):
        UpdateProfileRequest(name="A", nickname=value)


def test_nickname_untouched_when_not_sent() -> None:
    # An older client saving name and phone must not wipe a nickname.
    req = UpdateProfileRequest(name="A", phone="")
    assert "nickname" not in req.model_fields_set


# --- avatar ---------------------------------------------------------------


def test_cloudinary_signature_matches_documented_example() -> None:
    # The worked example from Cloudinary's "Generating authentication
    # signatures" page.
    params = {
        "eager": "w_400,h_300,c_pad|w_260,h_200,c_crop",
        "public_id": "sample_image",
        "timestamp": 1315060510,
    }
    assert (
        auth_router.cloudinary_signature(params, "abcd")
        == "bfd09f95f331f558cbd1320e67aa8d488770583e"
    )


@pytest.fixture
def cloud(monkeypatch):
    value = Settings(
        cloudinary_cloud_name="qp-cloud",
        cloudinary_api_key="123",
        cloudinary_api_secret="secret",
    )
    monkeypatch.setattr(auth_router, "settings", value)
    return value


def test_avatar_url_must_be_this_members_upload(cloud) -> None:
    me = SimpleNamespace(id=uuid.uuid4())
    other = SimpleNamespace(id=uuid.uuid4())
    pattern = auth_router._avatar_pattern(me)
    base = "https://res.cloudinary.com/qp-cloud/image/upload"

    assert pattern.match(f"{base}/v1712/qp/avatars/{me.id}.jpg")
    assert pattern.match(f"{base}/v1712/qp/avatars/{me.id}.webp")
    # Someone else's face.
    assert not pattern.match(f"{base}/v1712/qp/avatars/{other.id}.jpg")
    # Another cloud, another host, or a smuggled transform.
    assert not pattern.match(
        f"https://res.cloudinary.com/evil/image/upload/v1/qp/avatars/{me.id}.jpg"
    )
    assert not pattern.match(f"https://example.com/qp/avatars/{me.id}.jpg")
    assert not pattern.match(
        f"{base}/e_pixelate/v1712/qp/avatars/{me.id}.jpg"
    )
    assert not pattern.match(f"{base}/v1712/qp/avatars/{me.id}.svg")


# --- mail -----------------------------------------------------------------


@pytest.fixture
def outbox(monkeypatch):
    sent: list[dict] = []

    async def fake_send(to, subject, text, html=None):
        sent.append({"to": to, "subject": subject, "text": text, "html": html})
        return True

    monkeypatch.setattr(email_service, "send_email", fake_send)
    return sent


async def test_verification_mail_is_html_and_text(outbox) -> None:
    await email_service.send_email_verification(
        "a@b.com", "tok123", "vi", "Minh <script>"
    )
    [mail] = outbox
    assert "Xác nhận" in mail["subject"]
    assert "/vi/verify-email?token=tok123" in mail["text"]
    assert "/vi/verify-email?token=tok123" in mail["html"]
    assert "3 ngày" in mail["html"]
    # The name is member input and must not become markup.
    assert "<script>" not in mail["html"]
    assert "Minh &lt;script&gt;" in mail["html"]
    assert "facebook.com/QuantPercent" in mail["html"]


async def test_reset_mail_follows_locale(outbox) -> None:
    await email_service.send_password_reset("a@b.com", "tok", "en", None)
    [mail] = outbox
    assert mail["subject"].startswith("Reset your password")
    assert "1 hour" in mail["html"]
    assert mail["text"].startswith("Hi,")
