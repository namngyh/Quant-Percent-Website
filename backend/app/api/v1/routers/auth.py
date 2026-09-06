from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.config import settings
from app.core.deps import (
    CurrentUser,
    OptionalUser,
    SessionDep,
    VerifiedUser,
    require_csrf,
)
from app.core.security import verify_password
from app.core.ratelimit import (
    LOGIN,
    PASSWORD_CHANGE,
    PASSWORD_RESET,
    REGISTER,
    RESEND_VERIFICATION,
    client_ip,
    enforce,
)
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SuccessResponse,
    UpdateProfileRequest,
    UserOut,
    VerifyEmailRequest,
)
from app.services import auth as auth_service
from app.services import email as email_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(user) -> UserOut:
    return UserOut(
        id=str(user.id),
        email=user.email,
        name=user.full_name,
        phone=user.phone,
        role=user.role,
        author_request_status=user.author_request_status,
        locale=user.locale,
        email_verified=user.email_verified_at is not None,
        created_at=user.created_at,
    )


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    session: SessionDep,
) -> AuthResponse:
    ip = client_ip(request)
    await enforce(f"register:{ip}", REGISTER)

    user, verify_token = await auth_service.register_user(
        session,
        name=payload.name,
        email=payload.email,
        password=payload.password,
        locale=payload.locale,
        ip=ip,
    )
    refresh = await auth_service.issue_refresh_token(
        session,
        user,
        user_agent=request.headers.get("user-agent"),
        ip=ip,
    )
    await session.commit()

    if verify_token:
        await email_service.send_email_verification(
            user.email, verify_token, user.locale
        )
    auth_service.set_session_cookies(response, user, refresh)
    return AuthResponse(user=_user_out(user))


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
) -> AuthResponse:
    ip = client_ip(request)
    # Limit by IP and by account so one attacker cannot lock out everyone,
    # and one account cannot be sprayed from many IPs unnoticed
    await enforce(f"login:ip:{ip}", LOGIN)
    await enforce(f"login:email:{payload.email.lower()}", LOGIN)

    user = await auth_service.authenticate(
        session, email=payload.email, password=payload.password
    )
    refresh = await auth_service.issue_refresh_token(
        session, user, user_agent=request.headers.get("user-agent"), ip=ip
    )
    await auth_service.record_audit(
        session, "auth.login", actor_id=user.id, ip=ip
    )
    await session.commit()

    auth_service.set_session_cookies(response, user, refresh)
    return AuthResponse(user=_user_out(user))


@router.post("/refresh", response_model=AuthResponse)
async def refresh_session(
    request: Request, response: Response, session: SessionDep
) -> AuthResponse:
    raw = request.cookies.get(settings.refresh_cookie_name)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "missing_refresh_token"},
        )
    user, new_token = await auth_service.rotate_refresh_token(
        session,
        raw,
        user_agent=request.headers.get("user-agent"),
        ip=client_ip(request),
    )
    await session.commit()
    auth_service.set_session_cookies(response, user, new_token)
    return AuthResponse(user=_user_out(user))


@router.post(
    "/logout",
    response_model=SuccessResponse,
    dependencies=[Depends(require_csrf)],
)
async def logout(
    request: Request, response: Response, session: SessionDep
) -> SuccessResponse:
    raw = request.cookies.get(settings.refresh_cookie_name)
    if raw:
        await auth_service.revoke_refresh_token(session, raw)
        await session.commit()
    auth_service.clear_session_cookies(response)
    return SuccessResponse()


@router.get("/me", response_model=AuthResponse)
async def me(user: CurrentUser) -> AuthResponse:
    return AuthResponse(user=_user_out(user))


@router.patch(
    "/me",
    response_model=AuthResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_profile(
    payload: UpdateProfileRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUser,
) -> AuthResponse:
    user.full_name = payload.name.strip()
    user.phone = payload.phone
    # utcnow_column has no onupdate, so nothing bumps this on its own.
    user.updated_at = datetime.now(UTC)
    await auth_service.record_audit(
        session,
        "user.profile_update",
        actor_id=user.id,
        entity="user",
        entity_id=str(user.id),
        ip=client_ip(request),
    )
    await session.commit()
    # Returning the whole user lets the client update its cached copy without
    # a follow-up GET /me, the same way login and register already do.
    return AuthResponse(user=_user_out(user))


@router.post(
    "/change-password",
    response_model=SuccessResponse,
    dependencies=[Depends(require_csrf)],
)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    user: CurrentUser,
) -> SuccessResponse:
    await enforce(f"password-change:{user.id}", PASSWORD_CHANGE)

    # verify_password directly rather than authenticate(): that one looks the
    # user up by email and stamps last_login_at, neither of which belongs here.
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_current_password"},
        )

    await auth_service.set_password(session, user, payload.new_password)
    await auth_service.record_audit(
        session,
        "auth.password_change",
        actor_id=user.id,
        ip=client_ip(request),
    )
    # set_password revoked every refresh token, including this browser's. Issue
    # a fresh one so the device doing the change stays signed in; every other
    # device is signed out, which is the point of changing a password.
    refresh = await auth_service.issue_refresh_token(
        session,
        user,
        user_agent=request.headers.get("user-agent"),
        ip=client_ip(request),
    )
    await session.commit()
    auth_service.set_session_cookies(response, user, refresh)
    return SuccessResponse()


@router.post("/forgot-password", response_model=SuccessResponse)
async def forgot_password(
    payload: ForgotPasswordRequest, request: Request, session: SessionDep
) -> SuccessResponse:
    ip = client_ip(request)
    await enforce(f"forgot:{ip}", PASSWORD_RESET)

    from sqlalchemy import select

    from app.db.models import User

    user = await session.scalar(
        select(User).where(User.email == payload.email.strip().lower())
    )
    if user is not None:
        token = await auth_service.create_one_time_token(
            session, user, "password_reset", auth_service.RESET_TTL
        )
        await session.commit()
        await email_service.send_password_reset(
            user.email, token, payload.locale
        )
    # Always the same answer, so the endpoint cannot be used to discover
    # which addresses have accounts
    return SuccessResponse()


@router.post("/reset-password", response_model=SuccessResponse)
async def reset_password(
    payload: ResetPasswordRequest, request: Request, session: SessionDep
) -> SuccessResponse:
    await enforce(f"reset:{client_ip(request)}", PASSWORD_RESET)
    user = await auth_service.consume_one_time_token(
        session, payload.token, "password_reset"
    )
    await auth_service.set_password(session, user, payload.password)
    await auth_service.record_audit(
        session, "auth.password_reset", actor_id=user.id, ip=client_ip(request)
    )
    await session.commit()
    return SuccessResponse()


@router.post(
    "/request-author",
    response_model=AuthResponse,
    dependencies=[Depends(require_csrf)],
)
async def request_author(
    request: Request, session: SessionDep, user: VerifiedUser
) -> AuthResponse:
    """Ask an admin for permission to publish articles.

    VerifiedUser, not CurrentUser: an unconfirmed address is already blocked
    from members-only output, so letting it queue up for a stronger role would
    be a hole in the same wall.

    Idempotent — asking twice while a request is open changes nothing rather
    than raising, because from the caller's point of view the outcome they
    wanted is already true.
    """
    if user.role != "user":
        # Already an author or an admin. Nothing to ask for.
        return AuthResponse(user=_user_out(user))

    if user.author_request_status != "pending":
        user.author_request_status = "pending"
        user.author_request_at = datetime.now(UTC)
        user.updated_at = datetime.now(UTC)
        await auth_service.record_audit(
            session,
            "user.role_request",
            actor_id=user.id,
            entity="user",
            entity_id=str(user.id),
            ip=client_ip(request),
            meta={"requested": "author"},
        )
        await session.commit()
    return AuthResponse(user=_user_out(user))


@router.post(
    "/resend-verification",
    response_model=SuccessResponse,
    dependencies=[Depends(require_csrf)],
)
async def resend_verification(
    request: Request, session: SessionDep, user: CurrentUser
) -> SuccessResponse:
    """Send a fresh confirmation link to the signed-in member.

    Without this the three-day VERIFY_TTL is a trapdoor: the only link a
    member ever received is the one from registration, so letting it lapse
    used to mean the address could never be confirmed at all. That was
    tolerable while verification gated nothing. It is not now that it gates
    members-only output.
    """
    await enforce(f"resend-verify:{user.id}", RESEND_VERIFICATION)

    if user.email_verified_at is not None:
        # Not an error worth alarming anyone with — the address is confirmed,
        # which is the outcome the caller wanted.
        return SuccessResponse()

    token = await auth_service.create_one_time_token(
        session, user, "email_verification", auth_service.VERIFY_TTL
    )
    await session.commit()
    await email_service.send_email_verification(user.email, token, user.locale)
    return SuccessResponse()


@router.post("/verify-email", response_model=SuccessResponse)
async def verify_email(
    payload: VerifyEmailRequest, session: SessionDep, user: OptionalUser
) -> SuccessResponse:
    verified = await auth_service.consume_one_time_token(
        session, payload.token, "email_verification"
    )
    verified.email_verified_at = datetime.now(UTC)
    await session.commit()
    return SuccessResponse()
