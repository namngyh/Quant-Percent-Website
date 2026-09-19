from __future__ import annotations

import re
import secrets
import unicodedata
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Article, ArticleComment, ArticleImage, ArticleVote
from app.schemas.articles import ArticleSort

PAGE_SIZE = 20
COMMENT_PAGE_SIZE = 30
IMAGE_MAX_BYTES = 2 * 1024 * 1024

# ------------------------------------------------------------------- slugs

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def make_slug(title: str) -> str:
    """ASCII slug from a Vietnamese title, with a random tail.

    NFKD strips the tone marks but leaves đ alone — it is a separate letter,
    not d with a combining mark — so it is mapped by hand. The tail keeps two
    articles with the same title apart without a uniqueness retry loop, and
    means no slug can ever equal a static route segment such as `new`.
    """
    text = title.lower().replace("đ", "d")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    base = _NON_SLUG.sub("-", text).strip("-")[:80].strip("-") or "bai-viet"
    return f"{base}-{secrets.token_hex(3)}"


# ------------------------------------------------------------------ images

_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def sniff_image(data: bytes) -> str | None:
    """The real type from the first bytes, ignoring what the client claimed.

    Only raster formats. SVG is deliberately absent: it is a document that can
    carry script, and serving one from our own origin would hand an author a
    way to run code in every reader's session.
    """
    for magic, content_type in _SIGNATURES:
        if data.startswith(magic):
            return content_type
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


# ---------------------------------------------------------------- articles


def _live():
    return Article.deleted_at.is_(None)


_ORDER = {
    "new": (Article.created_at.desc(),),
    "old": (Article.created_at.asc(),),
    "top": (Article.score.desc(), Article.created_at.desc()),
    "comments": (Article.comment_count.desc(), Article.created_at.desc()),
}


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_articles(
    session: AsyncSession, *, sort: ArticleSort, q: str | None, page: int
) -> tuple[list[Article], int]:
    where = [_live()]
    if q:
        where.append(Article.title.ilike(f"%{_escape_like(q)}%", escape="\\"))

    total = await session.scalar(
        select(func.count()).select_from(Article).where(*where)
    )
    rows = await session.scalars(
        select(Article)
        .where(*where)
        .order_by(*_ORDER[sort], Article.id)
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
    )
    return list(rows), int(total or 0)


async def get_article(session: AsyncSession, slug: str) -> Article | None:
    return await session.scalar(
        select(Article).where(Article.slug == slug, _live())
    )


async def get_vote(
    session: AsyncSession, article_id: uuid.UUID, user_id: uuid.UUID
) -> int | None:
    return await session.scalar(
        select(ArticleVote.value).where(
            ArticleVote.article_id == article_id, ArticleVote.user_id == user_id
        )
    )


async def set_vote(
    session: AsyncSession, article: Article, user_id: uuid.UUID, value: int
) -> None:
    """Record, change or withdraw a vote, then recount.

    The totals are recounted from article_votes rather than nudged by a delta.
    A delta needs to know the previous vote, and two tabs voting at once would
    both read the same previous value and apply it twice; a recount inside the
    transaction is right whatever order the writes land in.
    """
    now = datetime.now(UTC)
    if value == 0:
        await session.execute(
            delete(ArticleVote).where(
                ArticleVote.article_id == article.id,
                ArticleVote.user_id == user_id,
            )
        )
    else:
        stmt = insert(ArticleVote).values(
            article_id=article.id, user_id=user_id, value=value
        )
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[ArticleVote.article_id, ArticleVote.user_id],
                set_={"value": value, "updated_at": now},
            )
        )

    up = (
        select(func.count())
        .where(ArticleVote.article_id == article.id, ArticleVote.value == 1)
        .scalar_subquery()
    )
    down = (
        select(func.count())
        .where(ArticleVote.article_id == article.id, ArticleVote.value == -1)
        .scalar_subquery()
    )
    result = await session.execute(
        update(Article)
        .where(Article.id == article.id)
        .values(upvotes=up, downvotes=down, score=up - down)
        .execution_options(synchronize_session=False)
        .returning(Article.upvotes, Article.downvotes, Article.score)
    )
    article.upvotes, article.downvotes, article.score = result.one()


# ---------------------------------------------------------------- comments


async def list_comments(
    session: AsyncSession, article: Article, *, page: int
) -> tuple[list[ArticleComment], int]:
    where = (
        ArticleComment.article_id == article.id,
        ArticleComment.deleted_at.is_(None),
    )
    total = await session.scalar(
        select(func.count()).select_from(ArticleComment).where(*where)
    )
    rows = await session.scalars(
        select(ArticleComment)
        .where(*where)
        .order_by(ArticleComment.created_at.desc(), ArticleComment.id)
        .offset((page - 1) * COMMENT_PAGE_SIZE)
        .limit(COMMENT_PAGE_SIZE)
    )
    return list(rows), int(total or 0)


async def recount_comments(session: AsyncSession, article: Article) -> None:
    live = (
        select(func.count())
        .where(
            ArticleComment.article_id == article.id,
            ArticleComment.deleted_at.is_(None),
        )
        .scalar_subquery()
    )
    result = await session.execute(
        update(Article)
        .where(Article.id == article.id)
        .values(comment_count=live)
        .execution_options(synchronize_session=False)
        .returning(Article.comment_count)
    )
    article.comment_count = result.scalar_one()


async def get_comment(
    session: AsyncSession, article: Article, comment_id: uuid.UUID
) -> ArticleComment | None:
    return await session.scalar(
        select(ArticleComment).where(
            ArticleComment.id == comment_id,
            ArticleComment.article_id == article.id,
            ArticleComment.deleted_at.is_(None),
        )
    )


async def get_image(session: AsyncSession, image_id: uuid.UUID) -> ArticleImage | None:
    return await session.scalar(select(ArticleImage).where(ArticleImage.id == image_id))
