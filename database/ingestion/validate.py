"""Validate cơ bản: bỏ record lỗi, log warning, không bao giờ crash."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from records import Bar, Tick

log = logging.getLogger("validate")

TICK_FUTURE_TOLERANCE = timedelta(seconds=5)
BAR_FUTURE_TOLERANCE = timedelta(seconds=65)   # ts là ĐẦU bar nên có thể sớm tới 60s


def _ensure_utc(ts: datetime, label: str) -> datetime:
    if ts.tzinfo is None:
        log.warning("%s ts thieu timezone, gia dinh UTC: %s", label, ts)
        return ts.replace(tzinfo=timezone.utc)
    return ts


def validate_tick(tick: Tick) -> Tick | None:
    if tick.price is None or tick.price <= 0:
        log.warning("drop tick: price khong hop le %s %s price=%s",
                    tick.symbol, tick.ts, tick.price)
        return None
    tick.ts = _ensure_utc(tick.ts, "tick")
    if tick.ts - datetime.now(timezone.utc) > TICK_FUTURE_TOLERANCE:
        log.warning("drop tick: ts lech tuong lai >5s %s ts=%s", tick.symbol, tick.ts)
        return None
    return tick


def validate_bar(bar: Bar) -> Bar | None:
    if bar.close is None or bar.close <= 0:
        log.warning("drop bar: close khong hop le %s %s close=%s",
                    bar.symbol, bar.ts, bar.close)
        return None
    bar.ts = _ensure_utc(bar.ts, "bar")
    if bar.ts - datetime.now(timezone.utc) > BAR_FUTURE_TOLERANCE:
        log.warning("drop bar: ts lech tuong lai %s ts=%s", bar.symbol, bar.ts)
        return None
    return bar
