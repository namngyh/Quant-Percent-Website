from __future__ import annotations

from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.config import settings
from app.core.deps import CurrentUser, OptionalUser, SessionDep, require_csrf
from app.core.ratelimit import (
    LOGIN,
    PASSWORD_RESET,
    REGISTER,
    client_ip,
    enforce,
)
from app.schemas.auth import (
    AuthResponse,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SuccessResponse,
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


@router.post("/verify-email", response_model=SuccessResponse)
async def verify_email(
    payload: VerifyEmailRequest, session: SessionDep, user: OptionalUser
) -> SuccessResponse:
    from datetime import datetime

    verified = await auth_service.consume_one_time_token(
        session, payload.token, "email_verification"
    )
    verified.email_verified_at = datetime.now(UTC)
    await session.commit()
    return SuccessResponse()
