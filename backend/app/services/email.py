from __future__ import annotations

import asyncio
import html as html_lib
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)


FACEBOOK_URL = "https://www.facebook.com/QuantPercent"


async def _send_via_resend(
    to: str, subject: str, text: str, html: str | None = None
) -> bool:
    payload = {
        "from": settings.email_from,
        "to": [to],
        "subject": subject,
        "text": text,
    }
    if html:
        payload["html"] = html
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json=payload,
        )
    if resp.status_code >= 400:
        log.error("email provider rejected: %s %s", resp.status_code, resp.text)
        return False
    return True


def _smtp_send(to: str, subject: str, text: str, html: str | None = None) -> None:
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
    if html:
        # multipart/alternative: clients that render HTML show the designed
        # version, the rest — and spam filters, which distrust HTML-only
        # mail — still get a complete plain-text copy.
        message.add_alternative(html, subtype="html")

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


async def _send_via_smtp(
    to: str, subject: str, text: str, html: str | None = None
) -> bool:
    # smtplib blocks; a slow or unreachable mail server would otherwise stall
    # every request served by this worker.
    await asyncio.to_thread(_smtp_send, to, subject, text, html)
    return True


async def send_email(
    to: str, subject: str, text: str, html: str | None = None
) -> bool:
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
        return await send(to, subject, text, html)
    except Exception as exc:  # pragma: no cover - network dependent
        log.error("email send failed: %s", exc)
        return False


def _render_email(
    locale: str,
    *,
    preheader: str,
    heading: str,
    greeting: str,
    paragraphs: list[str],
    cta_label: str,
    link: str,
    footnotes: list[str],
) -> str:
    """The one HTML layout every member-facing message uses.

    Tables and inline styles, because that is what Gmail, Outlook and phone
    mail apps agree on; no remote images, because most clients block them
    until the reader opts in and a broken logo looks worse than none. Every
    value is escaped — the greeting carries a name the member typed.
    """
    e = html_lib.escape
    vi = locale == "vi"
    site = settings.public_site_url.rstrip("/")
    site_label = site.split("://", 1)[-1]
    support = settings.support_email
    fallback = (
        "Nếu nút không hoạt động, hãy sao chép liên kết dưới đây và dán vào trình duyệt:"
        if vi
        else "If the button does not work, copy this link into your browser:"
    )
    automated = (
        "Đây là email tự động, vui lòng không trả lời trực tiếp."
        if vi
        else "This is an automated message; please do not reply to it."
    )
    body = "".join(
        '<p style="margin:0 0 16px;font-size:15px;line-height:24px;'
        f'color:#334155;">{e(p)}</p>'
        for p in paragraphs
    )
    notes = "".join(
        '<p style="margin:0 0 8px;font-size:13px;line-height:20px;'
        f'color:#64748b;">{e(n)}</p>'
        for n in footnotes
    )
    link_style = "color:#1e4a72;text-decoration:none;"
    return f"""<!DOCTYPE html>
<html lang="{e(locale)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<title>{e(heading)}</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{e(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f1f5f9;">
<tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;background:#ffffff;border:1px solid #e6ebf3;border-radius:12px;overflow:hidden;">
<tr><td style="background:#1e4a72;padding:22px 32px;">
<span style="font-size:20px;font-weight:700;color:#ffffff;">Quant&nbsp;Percent</span>
</td></tr>
<tr><td style="padding:36px 32px 12px;">
<h1 style="margin:0 0 20px;font-size:22px;line-height:30px;font-weight:700;color:#0f1b2a;">{e(heading)}</h1>
<p style="margin:0 0 16px;font-size:15px;line-height:24px;color:#0f1b2a;">{e(greeting)}</p>
{body}
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:28px 0;">
<tr><td style="border-radius:999px;background:#1e4a72;">
<a href="{e(link)}" target="_blank" style="display:inline-block;padding:14px 32px;font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:999px;">{e(cta_label)}</a>
</td></tr>
</table>
<p style="margin:0 0 6px;font-size:13px;line-height:20px;color:#64748b;">{e(fallback)}</p>
<p style="margin:0 0 24px;font-size:13px;line-height:20px;word-break:break-all;"><a href="{e(link)}" style="color:#1e4a72;">{e(link)}</a></p>
<div style="border-top:1px solid #e6ebf3;padding-top:20px;">{notes}</div>
</td></tr>
<tr><td style="background:#f7f9fc;border-top:1px solid #e6ebf3;padding:20px 32px;">
<p style="margin:0 0 6px;font-size:12px;line-height:18px;color:#64748b;">
<a href="{e(site)}" style="{link_style}">{e(site_label)}</a>
&nbsp;·&nbsp;<a href="{FACEBOOK_URL}" style="{link_style}">Facebook</a>
&nbsp;·&nbsp;<a href="mailto:{e(support)}" style="{link_style}">{e(support)}</a>
</p>
<p style="margin:0;font-size:12px;line-height:18px;color:#94a3b8;">{e(automated)}</p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def _plain_email(
    greeting: str,
    paragraphs: list[str],
    cta_label: str,
    link: str,
    footnotes: list[str],
) -> str:
    """The text/plain twin of ``_render_email``: same words, same order."""
    site = settings.public_site_url.rstrip("/")
    return "\n\n".join(
        [
            greeting,
            *paragraphs,
            f"{cta_label}:\n{link}",
            *footnotes,
            f"— Quant Percent\n{site}\n{FACEBOOK_URL}",
        ]
    )


def _greeting(name: str | None, locale: str) -> str:
    name = (name or "").strip()
    if locale == "vi":
        return f"Xin chào {name}," if name else "Xin chào,"
    return f"Hi {name}," if name else "Hi,"


async def _send_action_email(
    email: str,
    locale: str,
    name: str | None,
    *,
    subject: str,
    heading: str,
    paragraphs: list[str],
    cta_label: str,
    link: str,
    footnotes: list[str],
) -> None:
    greeting = _greeting(name, locale)
    await send_email(
        email,
        subject,
        _plain_email(greeting, paragraphs, cta_label, link, footnotes),
        _render_email(
            locale,
            preheader=paragraphs[-1],
            heading=heading,
            greeting=greeting,
            paragraphs=paragraphs,
            cta_label=cta_label,
            link=link,
            footnotes=footnotes,
        ),
    )


async def send_password_reset(
    email: str, token: str, locale: str, name: str | None = None
) -> None:
    link = f"{settings.public_site_url}/{locale}/reset-password?token={token}"
    if locale == "vi":
        await _send_action_email(
            email,
            locale,
            name,
            subject="Yêu cầu đặt lại mật khẩu – Quant Percent",
            heading="Đặt lại mật khẩu",
            paragraphs=[
                "Chúng tôi nhận được yêu cầu đặt lại mật khẩu cho tài khoản "
                f"Quant Percent gắn với địa chỉ {email}.",
                "Bấm nút bên dưới để tạo mật khẩu mới.",
            ],
            cta_label="Đặt lại mật khẩu",
            link=link,
            footnotes=[
                "Liên kết có hiệu lực trong 1 giờ và chỉ dùng được một lần.",
                "Nếu bạn không yêu cầu đặt lại mật khẩu, hãy bỏ qua email này. "
                "Mật khẩu hiện tại của bạn vẫn giữ nguyên.",
            ],
        )
    else:
        await _send_action_email(
            email,
            locale,
            name,
            subject="Reset your password – Quant Percent",
            heading="Reset your password",
            paragraphs=[
                "We received a request to reset the password for the Quant "
                f"Percent account registered to {email}.",
                "Use the button below to choose a new password.",
            ],
            cta_label="Reset password",
            link=link,
            footnotes=[
                "This link expires in 1 hour and can be used once.",
                "If you did not ask to reset your password, ignore this email. "
                "Your current password stays as it is.",
            ],
        )


async def send_email_verification(
    email: str, token: str, locale: str, name: str | None = None
) -> None:
    link = f"{settings.public_site_url}/{locale}/verify-email?token={token}"
    if locale == "vi":
        await _send_action_email(
            email,
            locale,
            name,
            subject="Xác nhận địa chỉ email của bạn – Quant Percent",
            heading="Xác nhận địa chỉ email",
            paragraphs=[
                "Cảm ơn bạn đã tạo tài khoản Quant Percent.",
                "Bấm nút bên dưới để xác nhận đây là email của bạn. Sau khi xác "
                "nhận, bạn có thể xem kết quả mô hình dành cho thành viên, mở "
                "QP Terminal và tham gia bình luận, bình chọn trong cộng đồng.",
            ],
            cta_label="Xác nhận email",
            link=link,
            footnotes=[
                "Liên kết có hiệu lực trong 3 ngày. Khi hết hạn, bạn có thể gửi "
                "lại liên kết mới từ trang Tài khoản.",
                "Nếu bạn không tạo tài khoản này, hãy bỏ qua email này.",
            ],
        )
    else:
        await _send_action_email(
            email,
            locale,
            name,
            subject="Confirm your email address – Quant Percent",
            heading="Confirm your email address",
            paragraphs=[
                "Thank you for creating a Quant Percent account.",
                "Use the button below to confirm this address is yours. Once it "
                "is confirmed you can see members-only model output, open QP "
                "Terminal, and comment and vote in the community.",
            ],
            cta_label="Confirm email",
            link=link,
            footnotes=[
                "This link expires in 3 days. After that you can send a new one "
                "from your Account page.",
                "If you did not create this account, ignore this email.",
            ],
        )


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
