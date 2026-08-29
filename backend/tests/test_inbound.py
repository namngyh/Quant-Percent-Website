"""Feedback and join applications.

Neither endpoint writes to the database — mail is the only copy — so what
is worth pinning is who is allowed through, that a bot sends nothing, and
that the notification carries the fields somebody needs in order to reply.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core import ratelimit
from app.core.deps import get_current_user
from app.db.models import User
from app.main import app
from app.services import email as email_service


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    """No Redis, and a clean window per test.

    The in-memory fallback is process-global; without the clear, the sixth
    request of the whole file would 429 in whichever test happened to run
    after the rate-limit ones.
    """

    def boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(ratelimit, "get_redis", boom)
    ratelimit._local_hits.clear()
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def sent(monkeypatch):
    """Capture notifications instead of sending them."""
    calls: list[tuple[str, str, str]] = []

    async def fake_send(to, subject, text):
        calls.append((to, subject, text))
        return True

    monkeypatch.setattr(email_service, "send_email", fake_send)
    monkeypatch.setattr(
        email_service.settings, "contact_notify_email", "inbox@quantpercent.com"
    )
    return calls


@pytest.fixture
def member():
    """Sign the request in without touching the database."""
    user = User(
        id=uuid.uuid4(),
        email="member@example.com",
        full_name="Nguyen Van A",
        locale="vi",
        status="active",
    )
    app.dependency_overrides[get_current_user] = lambda: user
    return user


@pytest.fixture
def client():
    return TestClient(app)


FEEDBACK = {
    "category": "ui",
    "message": "Bieu do hieu suat kho doc tren dien thoai.",
    "locale": "vi",
}

JOIN = {
    "name": "Tran Thi B",
    "email": "B@Example.com",
    "phone": "0900000000",
    "role": "ai_ml_engineer",
    "about": "Ba nam lam viec voi mo hinh chuoi thoi gian.",
    "link": "https://github.com/example",
    "locale": "vi",
    "consent": True,
}


# --------------------------------------------------------------- feedback


def test_feedback_rejects_anonymous(client) -> None:
    """The sign-in panel on the website is presentation; this is the lock."""
    res = client.post("/api/v1/feedback", json=FEEDBACK)
    assert res.status_code == 401
    assert res.json()["detail"] == {"error": "not_authenticated"}


def test_feedback_accepted_from_a_member(client, member, sent) -> None:
    res = client.post("/api/v1/feedback", json=FEEDBACK)
    assert res.status_code == 200
    assert res.json() == {"success": True}

    to, subject, body = sent[0]
    assert to == "inbox@quantpercent.com"
    assert "feedback" in subject
    # The sender is read from the session, so the mail can be replied to
    # even though the form never asked for an address.
    assert member.email in body
    assert FEEDBACK["message"] in body


def test_feedback_honeypot_sends_nothing(client, member, sent) -> None:
    """A filled honeypot never reaches the mailbox.

    It is the `max_length=0` on the field that stops it, so the answer is
    the ordinary 400 validation shape rather than the fake success the
    router's own honeypot branch would return — same as /contact.
    """
    res = client.post("/api/v1/feedback", json={**FEEDBACK, "website": "x"})
    assert res.status_code == 400
    assert res.json()["error"] == "validation"
    assert sent == []


def test_feedback_rate_limited_per_account(client, member, sent) -> None:
    for _ in range(5):
        assert client.post("/api/v1/feedback", json=FEEDBACK).status_code == 200
    res = client.post("/api/v1/feedback", json=FEEDBACK)
    assert res.status_code == 429
    assert res.json()["detail"] == {"error": "rate_limited"}


# ------------------------------------------------------------------- join


def test_join_is_open_to_anyone(client, sent) -> None:
    res = client.post("/api/v1/join", json=JOIN)
    assert res.status_code == 200
    assert res.json() == {"success": True}

    _, subject, body = sent[0]
    assert "join" in subject
    assert "ai_ml_engineer" in subject
    # Lowercased, so the same person twice is not two different addresses
    assert "b@example.com" in body
    assert JOIN["link"] in body


def test_join_other_role_carries_the_free_text(client, sent) -> None:
    res = client.post(
        "/api/v1/join",
        json={**JOIN, "role": "other", "roleOther": "Data engineer"},
    )
    assert res.status_code == 200
    _, subject, body = sent[0]
    assert "Data engineer" in subject
    assert "Data engineer" in body


def test_join_requires_consent(client, sent) -> None:
    res = client.post("/api/v1/join", json={**JOIN, "consent": False})
    assert res.status_code == 400
    assert "consent" in res.json()["issues"]
    assert sent == []


def test_join_rate_limited_per_ip(client, sent) -> None:
    for _ in range(5):
        assert client.post("/api/v1/join", json=JOIN).status_code == 200
    assert client.post("/api/v1/join", json=JOIN).status_code == 429
