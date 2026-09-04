"""Live-stream checks.

Run directly:  .venv\\Scripts\\python.exe tests/test_stream.py

Covers the parts that can be tested without a network: message parsing and the
subscription bookkeeping that decides when an upstream connection opens and
closes. The upstream itself is stubbed — what matters here is that a series
nobody is watching does not keep a socket open.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.data.stream import Series, StreamManager, parse_kline  # noqa: E402

CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


def kline(**overrides) -> dict:
    k = {
        "t": 1700000000000, "T": 1700000059999, "s": "BTCUSDT", "i": "1m",
        "o": "42000.10", "c": "42010.50", "h": "42020.00", "l": "41990.00",
        "v": "12.345", "x": False,
    }
    k.update(overrides)
    return {"e": "kline", "E": 1700000000001, "s": "BTCUSDT", "k": k}


class StubManager(StreamManager):
    """StreamManager whose upstream never touches the network."""

    def __init__(self):
        super().__init__(broadcast=self._collect)
        self.messages = []
        self.running: list[Series] = []

    async def _collect(self, message: dict) -> None:
        self.messages.append(message)

    async def _run(self, series: Series) -> None:
        self.running.append(series)
        try:
            await asyncio.Event().wait()   # stand in for a live connection
        except asyncio.CancelledError:
            self.running.remove(series)
            raise


# --------------------------------------------------------------------------

@check("a well-formed kline parses into typed fields")
def _():
    c = parse_kline(kline())
    assert c["symbol"] == "BTCUSDT" and c["timeframe"] == "1m", c
    assert c["open_time"] == 1700000000000 and isinstance(c["open_time"], int), c
    assert c["open"] == 42000.10 and c["close"] == 42010.50, c
    assert c["high"] == 42020.00 and c["low"] == 41990.00, c
    assert c["volume"] == 12.345 and c["closed"] is False, c


@check("the closed flag is carried through")
def _():
    assert parse_kline(kline(x=True))["closed"] is True


@check("malformed payloads return None instead of raising")
def _():
    for bad in ({}, {"k": None}, {"k": {}}, {"k": {"t": "not-a-number"}}, {"k": []}):
        assert parse_kline(bad) is None, bad


@check("a stream name matches Binance's channel format")
def _():
    assert Series("BTCUSDT", "1m").stream_name == "btcusdt@kline_1m"
    assert Series("BTCUSDT", "4h").stream_name == "btcusdt@kline_4h"


@check("subscribing opens exactly one upstream per series")
def _():
    async def run():
        m = StubManager()
        await m.subscribe("clientA", "BTCUSDT", "1m")
        await m.subscribe("clientB", "BTCUSDT", "1m")
        await asyncio.sleep(0)

        assert len(m.running) == 1, m.running
        assert m.watched() == [{"symbol": "BTCUSDT", "timeframe": "1m", "viewers": 2}], m.watched()
        await m.close()

    asyncio.run(run())


@check("the upstream stays open while any viewer remains")
def _():
    async def run():
        m = StubManager()
        await m.subscribe("clientA", "BTCUSDT", "1m")
        await m.subscribe("clientB", "BTCUSDT", "1m")
        await asyncio.sleep(0)

        await m.unsubscribe("clientA")
        assert len(m.running) == 1, "closed while clientB was still watching"
        assert m.watched()[0]["viewers"] == 1, m.watched()

        await m.unsubscribe("clientB")
        assert m.running == [], "should have closed with nobody watching"
        assert m.watched() == [], m.watched()
        await m.close()

    asyncio.run(run())


@check("switching timeframe closes the old upstream and opens the new one")
def _():
    async def run():
        m = StubManager()
        await m.subscribe("client", "BTCUSDT", "1m")
        await asyncio.sleep(0)
        await m.subscribe("client", "BTCUSDT", "1h")
        await asyncio.sleep(0)

        assert len(m.running) == 1, m.running
        assert m.running[0].timeframe == "1h", m.running
        assert len(m.watched()) == 1 and m.watched()[0]["timeframe"] == "1h", m.watched()
        await m.close()

    asyncio.run(run())


@check("an unsupported timeframe is rejected before any socket opens")
def _():
    async def run():
        m = StubManager()
        try:
            await m.subscribe("client", "BTCUSDT", "7s")
        except ValueError as exc:
            assert "unsupported timeframe" in str(exc), exc
        else:
            raise AssertionError("expected a rejection")
        assert m.running == [], m.running
        await m.close()

    asyncio.run(run())


@check("closing the manager tears down every upstream")
def _():
    async def run():
        m = StubManager()
        await m.subscribe("a", "BTCUSDT", "1m")
        await m.subscribe("b", "BTCUSDT", "1h")
        await asyncio.sleep(0)
        assert len(m.running) == 2, m.running

        await m.close()
        assert m.running == [], m.running
        assert m.watched() == [], m.watched()

    asyncio.run(run())


# --------------------------------------------------------------------------

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
        except Exception as exc:
            print(f"  ERROR {name}")
            print(f"          {type(exc).__name__}: {exc}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
