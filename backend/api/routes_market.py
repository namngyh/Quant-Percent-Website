"""Endpoints for the team's Vietnam market database.

Kept separate from ``/api/config`` on purpose: this data lives behind the team
VPN, and a failure here should mean "the VN list is unavailable", not "the app
would not load".
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException

from backend.data import market_vn, sources

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/markets/vn", tags=["market-vn"])

# ``api.v_quote`` itself has gotten slow as the database has grown — measured
# at 13-20s for even a bare `count(*)`, independent of anything this endpoint
# adds on top. That is the team's view, not something fixable from here, but a
# symbol list does not need to pay that cost on every dropdown open: it is
# cached for a minute, which a picker list can be that stale without anyone
# noticing.
_SYMBOLS_CACHE_SECONDS = 60
_symbols_cache: dict | None = None
_symbols_cache_at: float = 0.0


@router.get("/symbols")
def symbols() -> dict:
    """Every symbol with its latest quote, and which have minute bars.

    ``api.v_quote`` is a curated live-price feed, not the full catalogue — it
    covers 389 names while the daily-history table alone has 2,100, roughly
    1,150 of them still trading with real volume and simply never added to
    the quote feed. ``market_vn.list_symbols`` folds those in, priced off
    their own last two closes since there is no live quote for them.
    """
    global _symbols_cache, _symbols_cache_at

    if not market_vn.configured():
        raise HTTPException(
            503,
            "Chưa cấu hình MARKET_DSN. Copy .env.example thành .env và điền mật khẩu.",
        )

    now = time.monotonic()
    if _symbols_cache is not None and now - _symbols_cache_at < _SYMBOLS_CACHE_SECONDS:
        return _symbols_cache

    try:
        quotes = market_vn.list_symbols()
        intraday = market_vn.intraday_symbols()
    except market_vn.MarketUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc

    for quote in quotes:
        quote["id"] = sources.qualify(sources.VIETNAM, quote["symbol"])
        quote["has_intraday"] = quote["symbol"] in intraday

    payload = {
        "count": len(quotes),
        "intraday_count": len(intraday),
        "symbols": quotes,
        "timeframes": market_vn.SUPPORTED_TIMEFRAMES,
        "daily_only_note": (
            "Chỉ các mã có nến 1 phút mới dùng được khung intraday; "
            "các mã còn lại chỉ có khung ngày. Mã không có báo giá trực tiếp "
            "được định giá theo phiên đóng cửa gần nhất, có thể trễ tới một phiên."
        ),
    }
    _symbols_cache, _symbols_cache_at = payload, now
    return payload


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
