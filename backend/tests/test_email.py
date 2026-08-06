"""Provider selection and the Gmail From rule.

Delivery itself is network work and is not exercised here; what is pinned is
which transport gets chosen and the header rewrite that stops Gmail from
silently dropping mail.
"""

from email.utils import parseaddr

import pytest

from app.core.config import Settings
from app.services import email as email_service


@pytest.fixture
def settings(monkeypatch):
    """Swap in a Settings instance the tests can mutate freely.

    Every provider field is cleared first. Settings reads the developer's
    .env, so without this a machine with a real mailbox configured would
    change which transport these tests observe.
    """

    def _apply(**overrides) -> Settings:
        blank = {
            "resend_api_key": None,
            "smtp_host": None,
            "smtp_user": None,
            "smtp_password": None,
        }
        value = Settings(**{**blank, **overrides})
        monkeypatch.setattr(email_service, "settings", value)
        return value

    return _apply


async def test_no_provider_configured_skips_quietly(settings) -> None:
    settings()
    assert await email_service.send_email("a@b.com", "s", "t") is False


async def test_smtp_used_when_only_smtp_configured(settings, monkeypatch) -> None:
    settings(
        smtp_host="smtp.gmail.com",
        smtp_user="quantpercent@gmail.com",
        smtp_password="app-password",
    )
    sent: list[tuple] = []

    def fake_send(to, subject, text):
        sent.append((to, subject, text))

    monkeypatch.setattr(email_service, "_smtp_send", fake_send)
    assert await email_service.send_email("a@b.com", "s", "t") is True
    assert sent == [("a@b.com", "s", "t")]


async def test_resend_wins_when_both_configured(settings, monkeypatch) -> None:
    settings(
        resend_api_key="re_key",
        smtp_host="smtp.gmail.com",
        smtp_user="quantpercent@gmail.com",
        smtp_password="app-password",
    )
    calls: list[str] = []

    async def fake_resend(to, subject, text):
        calls.append("resend")
        return True

    monkeypatch.setattr(email_service, "_send_via_resend", fake_resend)
    assert await email_service.send_email("a@b.com", "s", "t") is True
    assert calls == ["resend"]


async def test_send_failure_returns_false(settings, monkeypatch) -> None:
    """A dead mail server must not lose the stored submission."""
    settings(
        smtp_host="smtp.gmail.com",
        smtp_user="quantpercent@gmail.com",
        smtp_password="app-password",
    )

    def boom(to, subject, text):
        raise OSError("connection refused")

    monkeypatch.setattr(email_service, "_smtp_send", boom)
    assert await email_service.send_email("a@b.com", "s", "t") is False


def test_from_is_rewritten_to_the_authenticated_mailbox(
    settings, monkeypatch
) -> None:
    """Gmail rejects a From it did not authenticate.

    EMAIL_FROM defaults to noreply@quantpercent.com, which an ordinary Gmail
    account cannot send as. The display name is kept; the address is not.
    """
    settings(
        smtp_host="smtp.gmail.com",
        smtp_user="quantpercent@gmail.com",
        smtp_password="app-password",
        email_from="Quant Percent <noreply@quantpercent.com>",
    )
    captured = {}

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, **kwargs):
            pass

        def login(self, user, password):
            pass

        def send_message(self, message):
            captured["from"] = message["From"]

    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    email_service._smtp_send("a@b.com", "s", "t")

    display, address = parseaddr(captured["from"])
    assert address == "quantpercent@gmail.com"
    assert display == "Quant Percent"
