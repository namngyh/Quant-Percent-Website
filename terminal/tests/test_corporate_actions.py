"""Splits and stock dividends, inferred from the prices themselves.

`api.v_history_1d` returns raw prices and the schema carries no corporate-action
history (§3.6). What it does carry is a ceiling band — 7% on HOSE, 10% on HNX,
15% on UPCOM — so a one-session move past 20% is not a market move: it is the
instrument being redenominated. That is enough to find the events and to make
the series continuous again.

The checks below are on synthetic frames, so they need no VPN. The live section
at the end runs only when the market database is reachable.

Run:  .venv\\Scripts\\python.exe tests/test_corporate_actions.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backend.data import corporate_actions as ca  # noqa: E402

CHECKS = []
DAY_MS = 86_400_000


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


def frame(closes: list[float], volumes: list[float] | None = None) -> pd.DataFrame:
    """A daily frame whose bars sit tightly around each close."""
    closes = [float(c) for c in closes]
    opens = [closes[0]] + closes[:-1]
    return pd.DataFrame({
        "open_time": [i * DAY_MS for i in range(len(closes))],
        "open": opens,
        "high": [max(o, c) * 1.001 for o, c in zip(opens, closes)],
        "low": [min(o, c) * 0.999 for o, c in zip(opens, closes)],
        "close": closes,
        "volume": volumes if volumes is not None else [1000.0] * len(closes),
    })


def walk(n: int, start: float = 100.0, step: float = 0.06, seed: int = 3) -> list[float]:
    """A series that moves as much as the band allows, and never more."""
    rng = np.random.default_rng(seed)
    closes = [start]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1.0 + rng.uniform(-step, step)))
    return closes


# --------------------------------------------------------------- detection

@check("a two-for-one split is found, with the ratio and the session it fell on")
def _():
    closes = walk(40)
    closes = closes[:20] + [c / 2 for c in closes[20:]]
    events = ca.detect(frame(closes))
    assert len(events) == 1, events
    event = events[0]
    assert abs(event.ratio - 2.0) < 0.15, event
    assert event.open_time == 20 * DAY_MS, event
    assert event.kind == "split", event


@check("a band-limited series raises nothing, however long it runs")
def _():
    # 4 000 sessions of the widest legal daily move: a false positive here
    # would accuse a fifth of the market of a split that never happened.
    assert ca.detect(frame(walk(4000, step=0.149, seed=11))) == []


@check("a consolidation — price up, shares down — is found too")
def _():
    closes = walk(30)
    closes = closes[:15] + [c * 5 for c in closes[15:]]
    events = ca.detect(frame(closes))
    assert len(events) == 1 and events[0].kind == "reverse_split", events
    assert abs(events[0].ratio - 0.2) < 0.02, events[0]


@check("two events in one window are both found")
def _():
    closes = walk(60)
    closes = closes[:20] + [c / 2 for c in closes[20:40]] + [c / 20 for c in closes[40:]]
    events = ca.detect(frame(closes))
    assert [e.open_time // DAY_MS for e in events] == [20, 40], events


@check("a simple ratio gets a name, an odd one is left unnamed")
def _():
    assert ca.ratio_label(2.0) == "2:1"
    assert ca.ratio_label(1.5) == "3:2"
    assert ca.ratio_label(0.2) == "1:5", ca.ratio_label(0.2)
    # Neither of these is a ratio a company announces. VIC's step of 1.8697
    # (2025-12-05) is a bonus issue, VNX's 44.33 (2026-04-13) a redenomination;
    # the correction uses the measured step either way, and the label stays
    # empty rather than inventing "28:15" or "133:3".
    assert ca.ratio_label(1.8697) is None, ca.ratio_label(1.8697)
    assert ca.ratio_label(44.33) is None, ca.ratio_label(44.33)


# -------------------------------------------------------------- adjustment

@check("adjusting makes the series continuous and leaves the newest prices alone")
def _():
    closes = walk(40)
    closes = closes[:20] + [c / 2 for c in closes[20:]]
    raw = frame(closes)
    fixed, events = ca.adjust(raw)
    assert len(events) == 1
    # The break is gone: nothing moves more than the band any more.
    moves = fixed["close"].pct_change().dropna().abs()
    assert moves.max() < 0.20, moves.max()
    # Back-adjusted: today's price is the price that was really traded today.
    assert fixed["close"].iloc[-1] == raw["close"].iloc[-1]
    assert fixed["open_time"].tolist() == raw["open_time"].tolist()
    # And the old prices moved onto today's scale, not the other way round.
    assert abs(fixed["close"].iloc[0] / raw["close"].iloc[0] - 0.5) < 0.02


@check("high, low and open travel with the close")
def _():
    # Flat either side of the event, so the inferred ratio is exactly 2 and the
    # check measures the rescaling rather than the fixture's own noise.
    closes = [100.0] * 10 + [50.0] * 10
    raw = frame(closes)
    fixed, _ = ca.adjust(raw)
    for column in ("open", "high", "low"):
        assert abs(fixed[column].iloc[0] / raw[column].iloc[0] - 0.5) < 1e-9, column
    # A bar still holds together after the rescale.
    assert (fixed["high"] >= fixed["low"]).all()
    assert (fixed["high"] >= fixed[["open", "close"]].max(axis=1) - 1e-9).all()


@check("volume moves the other way, because the shares did")
def _():
    raw = frame([100.0] * 10 + [50.0] * 10, volumes=[1000.0] * 20)
    fixed, _ = ca.adjust(raw)
    assert abs(fixed["volume"].iloc[0] - 2000.0) < 1e-6, fixed["volume"].iloc[0]
    assert fixed["volume"].iloc[-1] == 1000.0


@check("adjusting an adjusted series finds nothing left to do")
def _():
    closes = walk(40)
    closes = closes[:20] + [c / 2 for c in closes[20:]]
    once, _ = ca.adjust(frame(closes))
    twice, events = ca.adjust(once)
    assert events == [], events
    assert np.allclose(twice["close"].to_numpy(), once["close"].to_numpy())


@check("a frame with nothing to fix is returned as it came")
def _():
    raw = frame(walk(50, step=0.07, seed=5))
    fixed, events = ca.adjust(raw)
    assert events == []
    assert np.allclose(fixed["close"].to_numpy(), raw["close"].to_numpy())


@check("too few bars is not an opinion about splits")
def _():
    assert ca.detect(frame([100.0])) == []
    assert ca.detect(pd.DataFrame(columns=["open_time", "close"])) == []


# ------------------------------------------------------- which symbols

@check("only instruments with a price band are adjusted")
def _():
    # An equity and a fund trade inside a band, so a 20% session is an event.
    assert ca.applies_to("VN:VIC") is True
    assert ca.applies_to("VN:FUEVFVND") is True
    # Gold, crypto and FX have no band: a 20% day there is a 20% day.
    assert ca.applies_to("VN:G-XAUUSD") is False
    assert ca.applies_to("BTCUSDT") is False
    # An index is a computed level and a future is a contract; neither splits.
    assert ca.applies_to("VN:VNINDEX") is False
    assert ca.applies_to("VN:VN30F1M") is False


# ------------------------------------------------------------------ live

@check("[live] VIC's December 2025 split is found in the real series")
def _():
    from backend.data import market_vn

    if not market_vn.configured():
        print("        (skipped: no MARKET_DSN)")
        return
    try:
        df = market_vn.get_candles("VIC", "1d", limit=400, adjust=False)
    except market_vn.MarketUnavailable as exc:
        print(f"        (skipped: {exc})")
        return

    events = ca.detect(df)
    dates = {pd.to_datetime(e.open_time, unit="ms").date().isoformat(): e for e in events}
    assert "2025-12-05" in dates, sorted(dates)
    event = dates["2025-12-05"]
    assert 1.8 < event.ratio < 1.95, event

    fixed, applied = ca.adjust(df)
    assert len(applied) == len(events)
    moves = fixed["close"].pct_change().dropna().abs()
    assert moves.max() < 0.20, f"a break survived the adjustment: {moves.max():.3f}"
    print(f"        VIC: {len(events)} event(s), worst move {moves.max() * 100:.2f}% after adjusting")


def main() -> int:
    passed = failed = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as exc:
            print(f"  FAIL  {name}")
            print(f"          {exc}")
            failed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR {name}")
            print(f"          {type(exc).__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
