from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)


async def _send_via_resend(to: str, subject: str, text: str) -> bool:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.email_from,
                "to": [to],
                "subject": subject,
                "text": text,
            },
        )
    if resp.status_code >= 400:
        log.error("email provider rejected: %s %s", resp.status_code, resp.text)
        return False
    return True


def _smtp_send(to: str, subject: str, text: str) -> None:
    """Blocking send. Called through a worker thread, never on the loop.

    Uses the standard library so mail costs the project no new dependency to
    audit and pin.
    """
    message = EmailMessage()
    display, address = parseaddr(settings.email_from)
    if address.lower() != (settings.smtp_user or "").lower():
        # Gmail — and most mailbox providers — only accept a From that matches
        # the authenticated mailbox. Anything else is silently rewritten or
        # rejected, which looks like mail vanishing. Keep the display name and
        # send from the real mailbox.
        log.info(
            "SMTP From %r does not match the authenticated mailbox; "
            "sending as %s",
            settings.email_from,
            settings.smtp_user,
        )
        message["From"] = formataddr(
            (display or "Quant Percent", settings.smtp_user)
        )
    else:
        message["From"] = settings.email_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)

    context = ssl.create_default_context()
    if settings.smtp_use_ssl:
        client = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=15, context=context
        )
    else:
        client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
    with client:
        if not settings.smtp_use_ssl:
            client.starttls(context=context)
        client.login(settings.smtp_user, settings.smtp_password)
        client.send_message(message)


async def _send_via_smtp(to: str, subject: str, text: str) -> bool:
    # smtplib blocks; a slow or unreachable mail server would otherwise stall
    # every request served by this worker.
    await asyncio.to_thread(_smtp_send, to, subject, text)
    return True


async def send_email(to: str, subject: str, text: str) -> bool:
    """Best-effort delivery.

    Returns False instead of raising: a failed notification must never
    lose a stored contact submission or block a password reset.

    Resend is preferred when configured; SMTP is the fallback for setups
    without a verified sending domain.
    """
    if settings.resend_api_key:
        send = _send_via_resend
    elif settings.smtp_configured:
        send = _send_via_smtp
    else:
        log.info("email skipped (no provider configured): %s -> %s", subject, to)
        return False
    try:
        return await send(to, subject, text)
    except Exception as exc:  # pragma: no cover - network dependent
        log.error("email send failed: %s", exc)
        return False


async def send_password_reset(email: str, token: str, locale: str) -> None:
    link = f"{settings.public_site_url}/{locale}/reset-password?token={token}"
    subject = (
        "Đặt lại mật khẩu Quant Percent"
        if locale == "vi"
        else "Reset your Quant Percent password"
    )
    body = (
        f"Liên kết đặt lại mật khẩu (hết hạn sau 1 giờ):\n{link}\n\n"
        "Nếu bạn không yêu cầu, hãy bỏ qua email này."
        if locale == "vi"
        else f"Password reset link (expires in 1 hour):\n{link}\n\n"
        "If you did not request this, ignore this email."
    )
    await send_email(email, subject, body)


async def send_email_verification(email: str, token: str, locale: str) -> None:
    link = f"{settings.public_site_url}/{locale}/verify-email?token={token}"
    subject = (
        "Xác thực email Quant Percent"
        if locale == "vi"
        else "Verify your Quant Percent email"
    )
    body = (
        f"Xác thực email của bạn:\n{link}"
        if locale == "vi"
        else f"Verify your email address:\n{link}"
    )
    await send_email(email, subject, body)


async def _notify(subject: str, lines: list[str]) -> bool:
    """Send an inbound-message notification, and make a failure recoverable.

    Feedback and applications are not written to the database — mail is the
    only copy. ``send_email`` swallows failures by design, so the body is
    logged when it does not go out; otherwise a provider outage would lose
    what somebody took the trouble to write.
    """
    if not settings.contact_notify_email:
        log.error(
            "no CONTACT_NOTIFY_EMAIL set, dropping: %s\n%s",
            subject,
            "\n".join(lines),
        )
        return False
    body = "\n".join(lines)
    sent = await send_email(settings.contact_notify_email, subject, body)
    if not sent:
        log.error("notification not delivered: %s\n%s", subject, body)
    return sent


async def notify_contact(record: dict) -> bool:
    if not settings.contact_notify_email:
        return False
    lines = [
        f"Name: {record.get('name')}",
        f"Email: {record.get('email')}",
        f"Phone: {record.get('phone') or '-'}",
        f"Organization: {record.get('organization') or '-'}",
        f"Type: {record.get('inquiry_type')}",
        f"Locale: {record.get('locale')}",
        "",
        str(record.get("message", "")),
    ]
    return await send_email(
        settings.contact_notify_email,
        f"[quantpercent.com] {record.get('inquiry_type')} — {record.get('name')}",
        "\n".join(lines),
    )


async def notify_feedback(record: dict) -> bool:
    """Member feedback. The sender comes from the session, not the form."""
    return await _notify(
        "[quantpercent.com] feedback "
        f"{record.get('category')} — {record.get('name')}",
        [
            f"From: {record.get('name')} <{record.get('email')}>",
            f"Category: {record.get('category')}",
            f"Locale: {record.get('locale')}",
            "",
            str(record.get("message", "")),
        ],
    )


async def notify_join(record: dict) -> bool:
    """An application to join the team."""
    role = record.get("role")
    if role == "other":
        role = f"other ({record.get('role_other') or '-'})"
    return await _notify(
        f"[quantpercent.com] join {role} — {record.get('name')}",
        [
            f"Name: {record.get('name')}",
            f"Email: {record.get('email')}",
            f"Phone: {record.get('phone') or '-'}",
            f"Role: {role}",
            f"Link: {record.get('link') or '-'}",
            f"Locale: {record.get('locale')}",
            "",
            str(record.get("about") or "-"),
        ],
    )
