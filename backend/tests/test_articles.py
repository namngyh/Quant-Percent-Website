"""Articles: who may do what, and the rules a request body must meet.

None of this touches the database. Every gate here fires in a dependency or
in request validation, before the handler runs its first query — which is
also the point: a refused caller should cost nothing.
"""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core import ratelimit
from app.core.deps import get_author_user, get_current_user
from app.db.models import User
from app.main import app
from app.schemas.articles import ArticleCreate, CommentCreate, count_words
from app.services.articles import make_slug, sniff_image


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    def boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(ratelimit, "get_redis", boom)
    ratelimit._local_hits.clear()
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


def _user(role: str = "user", *, verified: bool = True) -> User:
    return User(
        id=uuid.uuid4(),
        email="member@example.com",
        full_name="Nguyen Van A",
        locale="vi",
        status="active",
        role=role,
        email_verified_at=datetime.now(UTC) if verified else None,
    )


def _sign_in(user: User) -> User:
    app.dependency_overrides[get_current_user] = lambda: user
    return user


ARTICLE = {
    "title": "Đánh giá mô hình MSDP",
    "summary": "Tóm tắt",
    "body": "Nội dung đủ dài để vượt qua giới hạn năm mươi ký tự tối thiểu $E=mc^2$.",
}


# ------------------------------------------------------------------- gates


async def test_author_gate_refuses_plain_members() -> None:
    with pytest.raises(HTTPException) as exc:
        await get_author_user(_user("user"))
    assert exc.value.status_code == 403
    assert exc.value.detail == {"error": "author_only"}


@pytest.mark.parametrize("role", ["author", "admin"])
async def test_author_gate_admits_authors_and_admins(role) -> None:
    user = _user(role)
    assert await get_author_user(user) is user


def test_publishing_requires_a_session(client) -> None:
    res = client.post("/api/v1/articles", json=ARTICLE)
    assert res.status_code == 401
    assert res.json()["detail"] == {"error": "not_authenticated"}


def test_publishing_refuses_a_plain_member(client) -> None:
    _sign_in(_user("user"))
    res = client.post("/api/v1/articles", json=ARTICLE)
    assert res.status_code == 403
    assert res.json()["detail"] == {"error": "author_only"}


def test_image_upload_refuses_a_plain_member(client) -> None:
    _sign_in(_user("user"))
    res = client.post(
        "/api/v1/articles/images",
        content=b"\x89PNG\r\n\x1a\n0000",
        headers={"content-type": "image/png"},
    )
    assert res.status_code == 403


def test_voting_requires_a_confirmed_address(client) -> None:
    _sign_in(_user(verified=False))
    res = client.put("/api/v1/articles/some-slug/vote", json={"value": 1})
    assert res.status_code == 403
    assert res.json()["detail"] == {"error": "email_not_verified"}


def test_commenting_requires_a_confirmed_address(client) -> None:
    _sign_in(_user(verified=False))
    res = client.post("/api/v1/articles/some-slug/comments", json={"body": "Hay"})
    assert res.status_code == 403
    assert res.json()["detail"] == {"error": "email_not_verified"}


def test_anonymous_cannot_vote(client) -> None:
    res = client.put("/api/v1/articles/some-slug/vote", json={"value": 1})
    assert res.status_code == 401


def test_vote_value_is_restricted(client) -> None:
    _sign_in(_user())
    res = client.put("/api/v1/articles/some-slug/vote", json={"value": 5})
    assert res.status_code == 400
    assert res.json()["error"] == "validation"


# ---------------------------------------------------------------- comments


def test_hundred_words_is_allowed() -> None:
    body = " ".join(["từ"] * 100)
    assert CommentCreate(body=body).body == body


def test_hundred_and_one_words_is_refused() -> None:
    with pytest.raises(ValidationError, match="too_many_words"):
        CommentCreate(body=" ".join(["từ"] * 101))


def test_whitespace_only_comment_is_refused() -> None:
    with pytest.raises(ValidationError):
        CommentCreate(body="   \n  ")


def test_word_count_ignores_runs_of_whitespace() -> None:
    """Line breaks and double spaces are not words; the website's counter
    splits on the same thing."""
    assert count_words("  một\n\nhai   ba\t bốn ") == 4


def test_long_comment_is_refused_over_http(client) -> None:
    _sign_in(_user())
    res = client.post(
        "/api/v1/articles/some-slug/comments",
        json={"body": " ".join(["a"] * 101)},
    )
    assert res.status_code == 400
    assert res.json()["error"] == "validation"


# ---------------------------------------------------------------- articles


def test_article_body_has_a_floor() -> None:
    with pytest.raises(ValidationError):
        ArticleCreate(title="Tiêu đề hợp lệ", body="ngắn")


def test_blank_summary_becomes_null() -> None:
    assert ArticleCreate(**{**ARTICLE, "summary": "   "}).summary is None


def test_slug_strips_vietnamese_marks() -> None:
    slug = make_slug("Đánh giá mô hình: VN30 & rủi ro!")
    base, _, tail = slug.rpartition("-")
    assert base == "danh-gia-mo-hinh-vn30-rui-ro"
    assert len(tail) == 6


def test_slug_of_symbols_only_still_has_a_base() -> None:
    assert make_slug("!!!").startswith("bai-viet-")


def test_two_identical_titles_get_different_slugs() -> None:
    assert make_slug("Cùng tiêu đề") != make_slug("Cùng tiêu đề")


# ------------------------------------------------------------------ images


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"\x89PNG\r\n\x1a\n rest", "image/png"),
        (b"\xff\xd8\xff\xe0 rest", "image/jpeg"),
        (b"GIF89a rest", "image/gif"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
    ],
)
def test_raster_images_are_recognised(data, expected) -> None:
    assert sniff_image(data) == expected


@pytest.mark.parametrize(
    "data",
    [
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        b"<html><body>not an image</body></html>",
        b"",
    ],
)
def test_anything_else_is_refused(data) -> None:
    """The client's Content-Type is never trusted — only the bytes."""
    assert sniff_image(data) is None
