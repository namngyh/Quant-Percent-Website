"""Endpoints for the team's Vietnam market database.

Kept separate from ``/api/config`` on purpose: this data lives behind the team
VPN, and a failure here should mean "the VN list is unavailable", not "the app
would not load".
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.data import market_vn, sources

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/markets/vn", tags=["market-vn"])


@router.get("/symbols")
def symbols() -> dict:
    """Every HOSE symbol with its latest quote, and which have minute bars.

    Only 35 of the 389 carry 1m data. Saying which lets the UI grey out the
    intraday timeframes instead of showing an empty chart with no reason given.
    """
    if not market_vn.configured():
        raise HTTPException(
            503,
            "Chưa cấu hình MARKET_DSN. Copy .env.example thành .env và điền mật khẩu.",
        )

    try:
        quotes = market_vn.list_symbols()
        intraday = market_vn.intraday_symbols()
    except market_vn.MarketUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc

    for quote in quotes:
        quote["id"] = sources.qualify(sources.VIETNAM, quote["symbol"])
        quote["has_intraday"] = quote["symbol"] in intraday

    return {
        "count": len(quotes),
        "intraday_count": len(intraday),
        "symbols": quotes,
        "timeframes": market_vn.SUPPORTED_TIMEFRAMES,
        "daily_only_note": (
            "Chỉ các mã có nến 1 phút mới dùng được khung intraday; "
            "các mã còn lại chỉ có khung ngày."
        ),
    }


@router.get("/freshness")
def freshness() -> dict:
    """How recent each symbol's data is, straight from the pipeline's own view."""
    if not market_vn.configured():
        raise HTTPException(503, "Chưa cấu hình MARKET_DSN.")
    try:
        return {"series": market_vn.freshness()}
    except market_vn.MarketUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/status")
def status() -> dict:
    """Whether the database is reachable right now, for the UI to show plainly."""
    if not market_vn.configured():
        return {"configured": False, "reachable": False, "message": "Chưa cấu hình MARKET_DSN."}

    try:
        rows = market_vn.query("SELECT current_user, now()")
        return {
            "configured": True,
            "reachable": True,
            "user": rows[0][0],
            "server_time": rows[0][1].isoformat(),
        }
    except market_vn.MarketUnavailable as exc:
        return {"configured": True, "reachable": False, "message": str(exc)}
