"""Articles, their votes and their comments.

Reading is open to everyone, signed in or not. Publishing needs the author
role, voting and commenting need a confirmed address, and removing something
needs to be its owner or an admin. The website hides the buttons a visitor
cannot use, but that is presentation; the dependencies here are the lock.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.core.config import settings
from app.core.deps import (
    AuthorUser,
    CurrentUser,
    OptionalUser,
    SessionDep,
    VerifiedUser,
    is_admin,
    is_verified_member,
    require_csrf,
)
from app.core.ratelimit import (
    ARTICLE_COMMENT,
    ARTICLE_IMAGE,
    ARTICLE_VOTE,
    ARTICLE_WRITE,
    client_ip,
    enforce,
)
from app.db.models import Article, ArticleComment, ArticleImage, User
from app.schemas.articles import (
    ArticleAuthor,
    ArticleCreate,
    ArticleCreated,
    ArticleDetail,
    ArticleList,
    ArticleSort,
    ArticleSummary,
    ArticleUpdate,
    CommentCreate,
    CommentList,
    CommentOut,
    ImageUploaded,
    VoteIn,
    VoteOut,
)
from app.services import articles as svc
from app.services import auth as auth_service

router = APIRouter(prefix="/articles", tags=["articles"])


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"}
    )


def _forbidden() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail={"error": "forbidden"}
    )


def _author(user: User) -> ArticleAuthor:
    return ArticleAuthor(id=str(user.id), name=user.full_name, role=user.role)


def _summary_fields(article: Article) -> dict:
    return {
        "slug": article.slug,
        "title": article.title,
        "summary": article.summary,
        "author": _author(article.author),
        "created_at": article.created_at,
        "updated_at": article.updated_at,
        "upvotes": article.upvotes,
        "downvotes": article.downvotes,
        "score": article.score,
        "comment_count": article.comment_count,
    }


async def _article_or_404(session, slug: str) -> Article:
    article = await svc.get_article(session, slug)
    if article is None:
        raise _not_found()
    return article


# ------------------------------------------------------------------ images
# Declared before /{slug} so "images" is never read as an article slug.


@router.post(
    "/images",
    response_model=ImageUploaded,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def upload_image(
    request: Request, session: SessionDep, user: AuthorUser
) -> ImageUploaded:
    """The raw file as the request body, not multipart: one file per request is
    all the editor sends, and it saves a dependency for the form parser."""
    await enforce(f"article-image:{user.id}", ARTICLE_IMAGE)

    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > svc.IMAGE_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"error": "image_too_large"},
        )
    data = await request.body()
    if len(data) > svc.IMAGE_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"error": "image_too_large"},
        )
    content_type = svc.sniff_image(data)
    if content_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"error": "unsupported_image"},
        )

    image = ArticleImage(
        uploader_id=user.id,
        content_type=content_type,
        byte_size=len(data),
        data=data,
    )
    session.add(image)
    await session.commit()
    return ImageUploaded(
        id=str(image.id),
        url=f"{settings.api_prefix}/articles/images/{image.id}",
    )


@router.get("/images/{image_id}")
async def get_image(image_id: uuid.UUID, session: SessionDep) -> Response:
    image = await svc.get_image(session, image_id)
    if image is None:
        raise _not_found()
    return Response(
        content=image.data,
        media_type=image.content_type,
        headers={
            # An image never changes under its id; a new upload gets a new one.
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'",
        },
    )


# ---------------------------------------------------------------- articles


@router.get("", response_model=ArticleList)
async def list_articles(
    session: SessionDep,
    sort: ArticleSort = "new",
    q: str | None = Query(None, max_length=100),
    page: int = Query(1, ge=1, le=10_000),
) -> ArticleList:
    term = q.strip() if q else None
    rows, total = await svc.list_articles(session, sort=sort, q=term, page=page)
    return ArticleList(
        items=[ArticleSummary(**_summary_fields(a)) for a in rows],
        total=total,
        page=page,
        page_size=svc.PAGE_SIZE,
    )


@router.post(
    "",
    response_model=ArticleCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_article(
    payload: ArticleCreate, session: SessionDep, user: AuthorUser
) -> ArticleCreated:
    await enforce(f"article:{user.id}", ARTICLE_WRITE)
    article = Article(
        slug=svc.make_slug(payload.title),
        author_id=user.id,
        title=payload.title,
        summary=payload.summary,
        body=payload.body,
    )
    session.add(article)
    await session.commit()
    return ArticleCreated(slug=article.slug)


@router.get("/{slug}", response_model=ArticleDetail)
async def get_article(
    slug: str, session: SessionDep, user: OptionalUser
) -> ArticleDetail:
    article = await _article_or_404(session, slug)
    owner = user is not None and user.id == article.author_id
    my_vote = await svc.get_vote(session, article.id, user.id) if user else None
    return ArticleDetail(
        **_summary_fields(article),
        body=article.body,
        my_vote=my_vote,
        # Editing needs the role still held: an author whose role was revoked
        # keeps their old articles but cannot keep rewriting them.
        can_edit=owner and user is not None and user.role in ("author", "admin"),
        can_delete=owner or is_admin(user),
        can_vote=is_verified_member(user) and not owner,
    )


@router.patch(
    "/{slug}",
    response_model=ArticleCreated,
    dependencies=[Depends(require_csrf)],
)
async def update_article(
    slug: str, payload: ArticleUpdate, session: SessionDep, user: AuthorUser
) -> ArticleCreated:
    article = await _article_or_404(session, slug)
    if article.author_id != user.id:
        raise _forbidden()
    await enforce(f"article:{user.id}", ARTICLE_WRITE)

    fields = payload.model_fields_set
    if "title" in fields and payload.title:
        article.title = payload.title
    if "summary" in fields:
        article.summary = payload.summary or None
    if "body" in fields and payload.body:
        article.body = payload.body

    # The slug stays put when the title changes, so links already shared keep
    # working. utcnow_column has no onupdate, so this is set by hand.
    article.updated_at = datetime.now(UTC)
    await session.commit()
    return ArticleCreated(slug=article.slug)


@router.delete(
    "/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def delete_article(
    slug: str, request: Request, session: SessionDep, user: CurrentUser
) -> Response:
    article = await _article_or_404(session, slug)
    owner = article.author_id == user.id
    if not owner and not is_admin(user):
        raise _forbidden()

    article.deleted_at = datetime.now(UTC)
    article.updated_at = article.deleted_at
    if not owner:
        # Removing somebody else's writing is moderation, and moderation is
        # what the audit log is for.
        await auth_service.record_audit(
            session, "article.delete", actor_id=user.id, entity="article",
            entity_id=str(article.id), ip=client_ip(request),
            meta={"slug": article.slug, "author_id": str(article.author_id)},
        )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------- votes


@router.put(
    "/{slug}/vote",
    response_model=VoteOut,
    dependencies=[Depends(require_csrf)],
)
async def vote(
    slug: str, payload: VoteIn, session: SessionDep, user: VerifiedUser
) -> VoteOut:
    article = await _article_or_404(session, slug)
    if article.author_id == user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "cannot_vote_own"},
        )
    await enforce(f"article-vote:{user.id}", ARTICLE_VOTE)

    await svc.set_vote(session, article, user.id, payload.value)
    await session.commit()
    return VoteOut(
        upvotes=article.upvotes,
        downvotes=article.downvotes,
        score=article.score,
        my_vote=payload.value or None,
    )


# ---------------------------------------------------------------- comments


def _comment(comment: ArticleComment, viewer: User | None) -> CommentOut:
    return CommentOut(
        id=str(comment.id),
        body=comment.body,
        author=_author(comment.author),
        created_at=comment.created_at,
        can_delete=viewer is not None
        and (viewer.id == comment.user_id or is_admin(viewer)),
    )


@router.get("/{slug}/comments", response_model=CommentList)
async def list_comments(
    slug: str,
    session: SessionDep,
    user: OptionalUser,
    page: int = Query(1, ge=1, le=10_000),
) -> CommentList:
    article = await _article_or_404(session, slug)
    rows, total = await svc.list_comments(session, article, page=page)
    return CommentList(
        items=[_comment(c, user) for c in rows],
        total=total,
        page=page,
        page_size=svc.COMMENT_PAGE_SIZE,
    )


@router.post(
    "/{slug}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_comment(
    slug: str, payload: CommentCreate, session: SessionDep, user: VerifiedUser
) -> CommentOut:
    article = await _article_or_404(session, slug)
    await enforce(f"article-comment:{user.id}", ARTICLE_COMMENT)

    comment = ArticleComment(article_id=article.id, user_id=user.id, body=payload.body)
    session.add(comment)
    await session.flush()
    await svc.recount_comments(session, article)
    await session.commit()
    await session.refresh(comment, attribute_names=["created_at", "author"])
    return _comment(comment, user)


@router.delete(
    "/{slug}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def delete_comment(
    slug: str,
    comment_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    user: CurrentUser,
) -> Response:
    article = await _article_or_404(session, slug)
    comment = await svc.get_comment(session, article, comment_id)
    if comment is None:
        raise _not_found()
    owner = comment.user_id == user.id
    if not owner and not is_admin(user):
        raise _forbidden()

    comment.deleted_at = datetime.now(UTC)
    await session.flush()
    await svc.recount_comments(session, article)
    if not owner:
        await auth_service.record_audit(
            session, "article.comment_delete", actor_id=user.id,
            entity="article_comment", entity_id=str(comment.id),
            ip=client_ip(request),
            meta={"slug": article.slug, "author_id": str(comment.user_id)},
        )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
