from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field, field_validator

from app.schemas.common import ApiModel

Locale = Literal["vi", "en"]


class RegisterRequest(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    locale: Locale = "vi"
    consent: Literal[True]
    # Honeypot — humans never fill this
    website: str | None = Field(default=None, max_length=0)


class LoginRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class ForgotPasswordRequest(ApiModel):
    email: EmailStr
    locale: Locale = "vi"


class ResetPasswordRequest(ApiModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class VerifyEmailRequest(ApiModel):
    token: str = Field(min_length=10, max_length=200)


class UserOut(ApiModel):
    id: str
    email: str
    name: str
    locale: str
    email_verified: bool
    created_at: datetime


class AuthResponse(ApiModel):
    user: UserOut


class ContactRequest(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    organization: str | None = Field(default=None, max_length=200)
    inquiryType: Literal[
        "investor_interest",
        "research_collaboration",
        "data_partnership",
        "technology_partnership",
        "general",
    ]
    message: str = Field(min_length=10, max_length=5000)
    locale: Locale
    consent: Literal[True]
    website: str | None = Field(default=None, max_length=0)

    @field_validator("phone", "organization", mode="before")
    @classmethod
    def _empty_to_none(cls, v: object) -> object:
        return None if v == "" else v


class InvestorInterestRequest(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    organization: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=2000)
    locale: Locale
    consent: Literal[True]
    website: str | None = Field(default=None, max_length=0)


class SuccessResponse(ApiModel):
    success: bool = True
