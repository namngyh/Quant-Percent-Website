"""Notification settings and a manual test."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.notify import telegram

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notify", tags=["notify"])


@router.get("/status")
async def status() -> dict:
    """Whether Telegram is configured and the token works."""
    return await telegram.check()


@router.post("/test")
async def test() -> dict:
    """Send one message, on the user's explicit request.

    Nothing is ever sent without configuration, and nothing else in the app
    sends on a button press — only paper-trading events do, and only once a
    session is running.
    """
    if not telegram.configured():
        raise HTTPException(
            400,
            "Chưa cấu hình. Thêm TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID vào .env.",
        )

    result = await telegram.send(
        "✅ <b>Quant Percent</b>\nKết nối Telegram hoạt động."
    )
    if not result["sent"]:
        raise HTTPException(502, f"Không gửi được: {result.get('reason')}")
    return result
