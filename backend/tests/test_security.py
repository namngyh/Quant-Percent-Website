import uuid

import pytest

from app.core.security import (
    create_access_token,
    csrf_matches,
    decode_access_token,
    generate_token,
    hash_password,
    hash_token,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_password_hash_is_salted() -> None:
    # Two users with the same password must not share a hash
    assert hash_password("same") != hash_password("same")


def test_verify_rejects_garbage_hash() -> None:
    assert not verify_password("anything", "not-a-hash")


def test_access_token_roundtrip() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "a@b.com")
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == str(user_id)
    assert payload["email"] == "a@b.com"


def test_tampered_token_rejected() -> None:
    token = create_access_token(uuid.uuid4(), "a@b.com")
    assert decode_access_token(token[:-2] + "xx") is None


def test_refresh_token_is_stored_hashed() -> None:
    raw = generate_token()
    digest = hash_token(raw)
    assert raw not in digest
    assert len(digest) == 64
    assert hash_token(raw) == digest


@pytest.mark.parametrize(
    ("header", "cookie", "expected"),
    [("abc", "abc", True), ("abc", "abd", False), (None, "abc", False),
     ("abc", None, False), (None, None, False)],
)
def test_csrf_double_submit(header, cookie, expected) -> None:
    assert csrf_matches(header, cookie) is expected
