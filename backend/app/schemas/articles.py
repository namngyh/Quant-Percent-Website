from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.schemas.auth import UserRole
from app.schemas.common import ApiModel

ArticleSort = Literal["new", "old", "top", "comments"]

COMMENT_MAX_WORDS = 100


def count_words(text: str) -> int:
    """Whitespace-separated words. The website counts the same way, so the
    counter under the box and this check can never disagree by one."""
    return len(text.split())


# ------------------------------------------------------------------ requests


def _strip(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip()


class ArticleCreate(ApiModel):
    title: str = Field(min_length=5, max_length=200)
    summary: str | None = Field(default=None, max_length=400)
    body: str = Field(min_length=50, max_length=100_000)

    _strip_fields = field_validator("title", "summary", mode="before")(_strip)

    @field_validator("summary")
    @classmethod
    def _empty_summary_is_none(cls, value: str | None) -> str | None:
        return value or None


class ArticleUpdate(ApiModel):
    title: str | None = Field(default=None, min_length=5, max_length=200)
    summary: str | None = Field(default=None, max_length=400)
    body: str | None = Field(default=None, min_length=50, max_length=100_000)

    _strip_fields = field_validator("title", "summary", mode="before")(_strip)


class VoteIn(ApiModel):
    # 0 takes the vote back
    value: Literal[-1, 0, 1]


class CommentCreate(ApiModel):
    body: str = Field(min_length=1, max_length=1000)

    @field_validator("body")
    @classmethod
    def _word_limit(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("empty")
        if count_words(value) > COMMENT_MAX_WORDS:
            raise ValueError("too_many_words")
        return value


# ----------------------------------------------------------------- responses


class ArticleAuthor(ApiModel):
    id: str
    name: str
    role: UserRole


class ArticleSummary(ApiModel):
    slug: str
    title: str
    summary: str | None
    author: ArticleAuthor
    created_at: datetime
    updated_at: datetime
    upvotes: int
    downvotes: int
    score: int
    comment_count: int


class ArticleList(ApiModel):
    items: list[ArticleSummary]
    total: int
    page: int
    page_size: int


class ArticleDetail(ArticleSummary):
    body: str
    # Per viewer. Null for somebody signed out or who has not voted.
    my_vote: Literal[-1, 1] | None = None
    can_edit: bool = False
    can_delete: bool = False
    can_vote: bool = False


class ArticleCreated(ApiModel):
    slug: str


class VoteOut(ApiModel):
    upvotes: int
    downvotes: int
    score: int
    my_vote: Literal[-1, 1] | None


class CommentOut(ApiModel):
    id: str
    body: str
    author: ArticleAuthor
    created_at: datetime
    can_delete: bool = False


class CommentList(ApiModel):
    items: list[CommentOut]
    total: int
    page: int
    page_size: int


class ImageUploaded(ApiModel):
    id: str
    url: str
