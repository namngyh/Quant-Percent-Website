from __future__ import annotations

import logging

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)


async def send_email(to: str, subject: str, text: str) -> bool:
    """Best-effort delivery.

    Returns False instead of raising: a failed notification must never
    lose a stored contact submission or block a password reset.
    """
    if not settings.resend_api_key:
        log.info("email skipped (no provider configured): %s -> %s", subject, to)
        return False
    try:
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
