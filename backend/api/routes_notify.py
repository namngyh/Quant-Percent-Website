"""Notification settings and a manual test.

The credentials can be set from the browser rather than only from ``.env``.
That is a deliberate trade: the token is written to ``.env`` on this machine,
which is gitignored, and the server binds to localhost only — so the exposure
is the same as the file already was. What it buys is that the settings can be
fixed without leaving the app, and that a wrong token is caught by ``getMe``
at the moment it is entered instead of silently producing no notifications
hours later during a paper session.

The token is never sent back to the browser in full. ``GET /status`` returns a
masked form, which is enough to tell two bots apart and not enough to use.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.notify import telegram

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notify", tags=["notify"])


class TelegramSettings(BaseModel):
    bot_token: str = Field(min_length=10, max_length=200)
    chat_id: str = Field(min_length=1, max_length=64)

    @field_validator("bot_token", "chat_id")
    @classmethod
    def _trim(cls, value: str) -> str:
        return value.strip()

    @field_validator("bot_token")
    @classmethod
    def _shape(cls, value: str) -> str:
        # A bot token is "<bot id>:<secret>". Catching the shape here turns the
        # commonest mistake — pasting the chat id into the token box — into a
        # clear message instead of a Telegram 404.
        if ":" not in value:
            raise ValueError(
                "Token phải có dạng 123456789:AA... — có vẻ bạn đang dán nhầm chat id."
            )
        return value


@router.get("/status")
async def status() -> dict:
    """Whether Telegram is configured and the token works."""
    return await telegram.check()


@router.put("/settings")
async def save_settings(settings: TelegramSettings) -> dict:
    """Verify a token, then store it in ``.env`` and apply it immediately.

    Verification comes first on purpose. Saving an invalid token and reporting
    the failure afterwards leaves the file holding something that does not
    work, and the next paper-trading event fails silently.
    """
    result = await telegram.verify(settings.bot_token, settings.chat_id)
    if not result.get("reachable"):
        raise HTTPException(400, result.get("message", "Token không dùng được."))

    try:
        telegram.save_credentials(settings.bot_token, settings.chat_id)
    except OSError as exc:
        log.exception("could not write .env")
        raise HTTPException(500, f"Không ghi được file .env: {exc}") from exc

    return await telegram.check()


@router.delete("/settings")
async def clear_settings() -> dict:
    """Forget the token. Notifications stop; nothing else changes."""
    try:
        telegram.clear_credentials()
    except OSError as exc:
        log.exception("could not write .env")
        raise HTTPException(500, f"Không ghi được file .env: {exc}") from exc
    return await telegram.check()


@router.post("/test")
async def test() -> dict:
    """Send one message, on the user's explicit request.

    Nothing is ever sent without configuration, and nothing else in the app
    sends on a button press — only paper-trading events do, and only once a
    session is running.

    This is also the only check that can prove the *chat id* is right: a valid
    token with the wrong chat id passes ``getMe`` and still delivers nothing.
    """
    if not telegram.configured():
        raise HTTPException(
            400,
            "Chưa cấu hình. Nhập token và chat id ở khung Thông báo Telegram.",
        )

    result = await telegram.send(
        "✅ <b>Quant Percent</b>\nKết nối Telegram hoạt động."
    )
    if not result["sent"]:
        raise HTTPException(502, f"Không gửi được: {result.get('reason')}")
    return result
