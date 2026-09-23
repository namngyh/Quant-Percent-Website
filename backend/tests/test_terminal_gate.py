"""The QP Terminal gate.

Caddy lets a request through to the Terminal only on a 2xx from
`/api/v1/auth/terminal-gate`, and hands every other answer to the browser as
it is. So both the decision and the *shape* of each refusal matter: a page
load has to be sent somewhere the visitor can act, and an API call has to get
JSON the Terminal can display.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Response
from starlette.responses import JSONResponse

from app.db.models import RefreshToken, User
from app.services.auth import refresh_record_usable
from app.services.terminal_gate import gate_response

SITE = "https://quantpercent.com"


def _user(*, verified: bool = True, role: str = "user") -> User:
    return User(
        email="member@example.com",
        full_name="Nguyen Van A",
        locale="vi",
        status="active",
        role=role,
        email_verified_at=datetime.now(UTC) if verified else None,
    )


def _code(response: Response) -> str:
    assert isinstance(response, JSONResponse)
    return json.loads(response.body)["detail"]["code"]


def test_verified_member_passes() -> None:
    response = gate_response(_user(), level="member", navigate=False, site_url=SITE)
    assert response.status_code == 204


def test_anonymous_page_load_is_sent_to_the_website() -> None:
    response = gate_response(None, level="member", navigate=True, site_url=SITE)
    assert response.status_code == 302
    assert response.headers["location"] == f"{SITE}/vi/terminal?from=terminal"


def test_anonymous_api_call_gets_readable_json() -> None:
    """A redirect here would reach the Terminal's fetch as an HTML page."""
    response = gate_response(None, level="member", navigate=False, site_url=SITE)
    assert response.status_code == 401
    assert _code(response) == "terminal_login_required"


def test_unverified_member_is_refused() -> None:
    user = _user(verified=False)
    page = gate_response(user, level="member", navigate=True, site_url=SITE)
    api = gate_response(user, level="member", navigate=False, site_url=SITE)
    assert page.status_code == 302
    assert api.status_code == 403
    assert _code(api) == "email_not_verified"


@pytest.mark.parametrize("role", ["user", "author"])
def test_admin_paths_refuse_non_admins(role) -> None:
    """Plugin upload runs Python on the server; it stays with admins."""
    response = gate_response(_user(role=role), level="admin", navigate=False, site_url=SITE)
    assert response.status_code == 403
    assert _code(response) == "admin_only"


def test_admin_paths_admit_admins() -> None:
    response = gate_response(_user(role="admin"), level="admin", navigate=False, site_url=SITE)
    assert response.status_code == 204


def test_trailing_slash_in_site_url_does_not_double() -> None:
    response = gate_response(None, level="member", navigate=True, site_url=SITE + "/")
    assert response.headers["location"] == f"{SITE}/vi/terminal?from=terminal"


def _record(*, revoked: bool = False, expires_in: timedelta = timedelta(days=1)):
    now = datetime.now(UTC)
    return RefreshToken(
        token_hash="x",
        expires_at=now + expires_in,
        revoked_at=now if revoked else None,
    )


def test_refresh_token_usability() -> None:
    """Logout revokes the refresh token, so it must stop passing at once."""
    now = datetime.now(UTC)
    assert refresh_record_usable(_record(), now) is True
    assert refresh_record_usable(_record(revoked=True), now) is False
    assert refresh_record_usable(_record(expires_in=timedelta(seconds=-1)), now) is False
    assert refresh_record_usable(None, now) is False


def test_shared_cookie_domain_expires_host_only_copies(monkeypatch) -> None:
    """Once COOKIE_DOMAIN is set, a browser from before still holds the old
    host-only session cookies. Left alone, the old rotated qp_refresh can be
    replayed and trip reuse detection, so every cookie write expires them."""
    from app.core.config import settings
    from app.services.auth import clear_session_cookies

    monkeypatch.setattr(settings, "cookie_domain", ".quantpercent.com")
    response = Response()
    clear_session_cookies(response)
    headers = [v for k, v in response.raw_headers if k == b"set-cookie"]
    refresh = [h.decode() for h in headers if h.startswith(b"qp_refresh=")]
    assert len(refresh) == 2
    assert sum("Domain=.quantpercent.com" in h for h in refresh) == 1


def test_no_cookie_domain_writes_nothing_extra(monkeypatch) -> None:
    from app.core.config import settings
    from app.services.auth import clear_session_cookies

    monkeypatch.setattr(settings, "cookie_domain", None)
    response = Response()
    clear_session_cookies(response)
    headers = [v for k, v in response.raw_headers if k == b"set-cookie"]
    assert len(headers) == 3
