from __future__ import annotations

from datetime import datetime
from typing import Literal

import re

from pydantic import EmailStr, Field, field_validator

from app.schemas.common import ApiModel

Locale = Literal["vi", "en"]
# Named UserRole, not Role: JoinRequest.role further down this file is the
# "what do you do" field on the careers form and means something else entirely.
UserRole = Literal["user", "author", "admin"]
AccountStatus = Literal["active", "disabled"]


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


# Letters in any script (so Vietnamese diacritics), digits, and a few joiners.
# No leading/trailing separator and no runs of spaces, so two nicknames
# cannot differ only in whitespace a reader cannot see.
NICKNAME_PATTERN = re.compile(r"^[^\W_](?:[\w.\- ]*[^\W_])?$")


class UpdateProfileRequest(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    # Only written when the client sends the field, so an older client that
    # knows nothing about nicknames cannot clear one by saving its form.
    nickname: str | None = Field(default=None, max_length=40)

    @field_validator("phone", "nickname", mode="before")
    @classmethod
    def _empty_to_none(cls, v: object) -> object:
        # A cleared field arrives as "" from the form; store absence as NULL
        # rather than as an empty string that reads like a real answer.
        if isinstance(v, str):
            v = v.strip()
        return None if v == "" else v

    @field_validator("nickname")
    @classmethod
    def _nickname_shape(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = re.sub(r"\s+", " ", v)
        if len(v) < 2 or not NICKNAME_PATTERN.match(v):
            raise ValueError("nickname_invalid")
        return v


class UpdateAvatarRequest(ApiModel):
    """A Cloudinary delivery URL, or null to go back to initials. The router
    checks it points at our own cloud; the shape is checked here."""

    avatar_url: str | None = Field(default=None, max_length=500)


class AvatarSignatureOut(ApiModel):
    """Everything the browser needs for one signed upload to Cloudinary.

    Every field except ``api_key`` and ``cloud_name`` went into the
    signature, so the browser must send them back unchanged."""

    cloud_name: str
    api_key: str
    timestamp: int
    signature: str
    public_id: str
    overwrite: bool
    allowed_formats: str


class AdminUserOut(ApiModel):
    """One row of the admin user list. Deliberately not UserOut: this carries
    sign-in and account-management fields no member ever needs about anyone."""

    id: str
    email: str
    name: str
    role: UserRole
    status: AccountStatus
    email_verified: bool
    author_request_status: Literal["pending", "rejected"] | None = None
    author_request_at: datetime | None = None
    created_at: datetime
    # "last password sign-in", not "last seen" — refresh-token rotation does
    # not touch it. See services.auth.authenticate.
    last_login_at: datetime | None = None


class AdminUserList(ApiModel):
    users: list[AdminUserOut]


class AdminUserUpdate(ApiModel):
    """Every field optional; only what is sent gets changed."""

    role: UserRole | None = None
    status: AccountStatus | None = None
    author_request: Literal["approve", "reject"] | None = None


class ChangePasswordRequest(ApiModel):
    # min_length=1 on the current one, matching LoginRequest: the rules that
    # applied when it was set are not this endpoint's business to re-litigate.
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class UserOut(ApiModel):
    id: str
    email: str
    name: str
    # Defaulted, not required: every existing _user_out call site predates the
    # column, and members who registered before it have nothing to report.
    phone: str | None = None
    nickname: str | None = None
    avatar_url: str | None = None
    # nickname if set, else name — what everyone else sees.
    display_name: str = ""
    role: UserRole = "user"
    author_request_status: Literal["pending", "rejected"] | None = None
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


class FeedbackRequest(ApiModel):
    """Feedback from a signed-in member.

    Deliberately carries no name or email: the sender is read from the
    session on the server, so it cannot be put in somebody else's name.
    """

    category: Literal["ui", "data_model", "content", "bug", "other"]
    message: str = Field(min_length=10, max_length=5000)
    locale: Locale
    website: str | None = Field(default=None, max_length=0)


class JoinRequest(ApiModel):
    """An open application to build with the team."""

    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    role: Literal["ai_ml_engineer", "mathematician", "developer", "other"]
    roleOther: str | None = Field(default=None, max_length=200)
    about: str | None = Field(default=None, max_length=2000)
    link: str | None = Field(default=None, max_length=300)
    locale: Locale
    consent: Literal[True]
    website: str | None = Field(default=None, max_length=0)

    @field_validator("phone", "roleOther", "about", "link", mode="before")
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
