"""Who may use QP Terminal (terminal.quantpercent.com).

The Terminal is a separate app with no accounts of its own. Caddy asks
`GET /api/v1/auth/terminal-gate` before every request to it — page loads, API
calls and the WebSocket upgrade alike — and only a 2xx lets the request
through. Anything else is returned to the browser exactly as this module
builds it, which is why the answer depends on what kind of request it was:

* a page load gets a redirect to the website, where the visitor can sign in
  or confirm their address and then be sent back;
* a fetch or WebSocket gets a JSON error, since a redirect to an HTML page
  would only surface in the Terminal as an unreadable parse failure. The body
  is in the Terminal's own error shape — `{code, message: {vi, en}}` — so its
  existing error display shows it in the right language.

The decision is a pure function of the user and the request so the whole
matrix can be tested without a database.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Response
from fastapi.responses import JSONResponse, RedirectResponse

from app.core.deps import is_admin, is_verified_member
from app.db.models import User

Level = Literal["member", "admin"]

# Where a blocked page load is sent. The website page decides what to show
# (sign in, confirm email, or straight back to the Terminal), and `from`
# lets it notice when it is being bounced back and forth instead of looping.
LANDING_PATH = "/vi/terminal?from=terminal"

_MESSAGES = {
    "terminal_login_required": {
        "vi": "Phiên đăng nhập đã hết. Tải lại trang để đăng nhập lại.",
        "en": "Your session has ended. Reload the page to sign in again.",
    },
    "email_not_verified": {
        "vi": "Xác thực email tài khoản Quant Percent để dùng QP Terminal.",
        "en": "Confirm your Quant Percent account's email to use QP Terminal.",
    },
    "admin_only": {
        "vi": "Chỉ quản trị viên được làm thao tác này.",
        "en": "Only administrators can do this.",
    },
}


def _refuse(code: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": {"code": code, "message": _MESSAGES[code]}},
    )


def gate_response(
    user: User | None,
    *,
    level: Level,
    navigate: bool,
    site_url: str,
) -> Response:
    """The answer Caddy should act on.

    `navigate` is true for a top-level page load (`Sec-Fetch-Mode: navigate`).
    """
    if user is None or not is_verified_member(user):
        if navigate:
            return RedirectResponse(
                f"{site_url.rstrip('/')}{LANDING_PATH}", status_code=302
            )
        if user is None:
            return _refuse("terminal_login_required", 401)
        return _refuse("email_not_verified", 403)

    # Admin-only paths are API calls (plugin upload, Telegram token, backfill),
    # never page loads, so there is no redirect branch to take here.
    if level == "admin" and not is_admin(user):
        return _refuse("admin_only", 403)

    return Response(status_code=204)
