"""Endpoints for the team's Vietnam market database.

Kept separate from ``/api/config`` on purpose: this data lives behind the team
VPN, and a failure here should mean "the VN list is unavailable", not "the app
would not load".
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException

from backend.data import market_vn, sources, team_models

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

# Coverage is a property of the last 45 sessions, so it barely moves within a
# working session; cached per symbol to keep symbol-flipping cheap.
_COVERAGE_CACHE_SECONDS = 300
_coverage_cache: dict[str, tuple[float, dict]] = {}

# The pipeline writes one risk snapshot a day at most, so a five-minute cache
# costs nothing and keeps tab-flipping off the VPN.
_RISK_CACHE_SECONDS = 300
_risk_cache: dict[str, tuple[float, dict]] = {}

# The forecast is written once a session and the network once a day, but the
# scoring walks the whole VNINDEX history to find each target session, so this
# is the one worth not repeating on every open.
_TEAM_CACHE_SECONDS = 300.0
_team_cache: dict[str, tuple[float, dict]] = {}


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


@router.get("/coverage")
def coverage(symbol: str) -> dict:
    """Whether a symbol's minute data is complete enough to work on.

    Answers three different questions that a bare "missing %" runs together:
    was there an outage, is the symbol too thin for intraday work at all, or
    was the market simply closed. See ``market_vn.data_coverage`` for why
    ``api.v_ingestion_gaps`` is the wrong source despite looking like the
    right one.
    """
    if not market_vn.configured():
        raise HTTPException(503, "Chưa cấu hình MARKET_DSN.")

    _, bare = sources.parse(symbol)
    now = time.monotonic()
    hit = _coverage_cache.get(bare)
    if hit and now - hit[0] < _COVERAGE_CACHE_SECONDS:
        return hit[1]

    try:
        report = market_vn.data_coverage(bare)
    except market_vn.MarketUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc

    _coverage_cache[bare] = (now, report)
    return report


@router.get("/risk")
def risk() -> dict:
    """The team's Monte Carlo risk read on VNINDEX.

    Offered next to the user's own backtested risk numbers as a second,
    independent opinion — the strategy tools measure a strategy, this measures
    the index. See ``market_vn.market_risk`` for the three limits that travel
    with it (uneven ``mc_paths``, a sparse series, VNINDEX only).
    """
    if not market_vn.configured():
        raise HTTPException(503, "Chưa cấu hình MARKET_DSN.")

    now = time.monotonic()
    hit = _risk_cache.get("vnindex")
    if hit and now - hit[0] < _RISK_CACHE_SECONDS:
        return hit[1]

    try:
        report = market_vn.market_risk()
    except market_vn.MarketUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc

    _risk_cache["vnindex"] = (now, report)
    return report


@router.get("/team-models")
def team_models_overview() -> dict:
    """What the team's own pipeline publishes: a forecast, its record, a
    correlation network, and the ingestion log.

    Four views that nothing here read until now. Each block carries either its
    content or its own error, so a missing network snapshot does not withhold
    the forecast beside it. The scoring is done against this platform's own
    closes, because the team's `actual_value` column is empty on every row —
    see backend/data/team_models.py.
    """
    if not market_vn.configured():
        raise HTTPException(503, "Chưa cấu hình MARKET_DSN.")

    now = time.monotonic()
    hit = _team_cache.get("all")
    if hit and now - hit[0] < _TEAM_CACHE_SECONDS:
        return hit[1]

    report = team_models.overview()
    _team_cache["all"] = (now, report)
    return report


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
