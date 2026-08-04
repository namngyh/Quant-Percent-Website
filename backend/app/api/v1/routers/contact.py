from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.deps import SessionDep
from app.core.ratelimit import CONTACT, client_ip, enforce
from app.db.models import Contact, InvestorInterest
from app.schemas.auth import (
    ContactRequest,
    InvestorInterestRequest,
    SuccessResponse,
)
from app.services import email as email_service

router = APIRouter(tags=["contact"])


@router.post("/contact", response_model=SuccessResponse)
async def submit_contact(
    payload: ContactRequest, request: Request, session: SessionDep
) -> SuccessResponse:
    ip = client_ip(request)
    await enforce(f"contact:{ip}", CONTACT)

    # Honeypot filled means a bot: answer normally, store nothing
    if payload.website:
        return SuccessResponse()

    record = Contact(
        name=payload.name,
        email=payload.email.lower(),
        phone=payload.phone,
        organization=payload.organization,
        inquiry_type=payload.inquiryType,
        message=payload.message,
        locale=payload.locale,
        consent=payload.consent,
        ip=ip if ip != "unknown" else None,
        user_agent=(request.headers.get("user-agent") or "")[:400] or None,
    )
    session.add(record)
    await session.commit()

    # Notification failure must not lose the submission
    await email_service.notify_contact(
        {
            "name": record.name,
            "email": record.email,
            "phone": record.phone,
            "organization": record.organization,
            "inquiry_type": record.inquiry_type,
            "locale": record.locale,
            "message": record.message,
        }
    )
    return SuccessResponse()


@router.post("/investor-interest", response_model=SuccessResponse)
async def register_interest(
    payload: InvestorInterestRequest, request: Request, session: SessionDep
) -> SuccessResponse:
    ip = client_ip(request)
    await enforce(f"interest:{ip}", CONTACT)

    if payload.website:
        return SuccessResponse()

    session.add(
        InvestorInterest(
            name=payload.name,
            email=payload.email.lower(),
            organization=payload.organization,
            note=payload.note,
            locale=payload.locale,
            consent=payload.consent,
            ip=ip if ip != "unknown" else None,
        )
    )
    await session.commit()
    return SuccessResponse()
