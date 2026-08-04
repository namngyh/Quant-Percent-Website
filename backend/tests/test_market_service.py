"""A registered symbol with no bars yet must read as "no data", not 500.

This is the first state the API is in on a fresh install: the catalogue
seeds `web.symbols` before the ingestion pipeline has written any bar.
"""

from datetime import UTC, datetime

import pytest

from app.services import market


class _FakeResult:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class _FakeSession:
    """Returns one canned result per execute() call, in order."""

    def __init__(self, *results: list[dict]):
        self._results = list(results)

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(self._results.pop(0) if self._results else [])


async def test_quote_returns_none_when_price_missing() -> None:
    session = _FakeSession(
        [
            {
                "symbol": "VN30F1M",
                "name": "VN30F1M",
                "price": None,  # no bar ingested yet
                "change": None,
                "change_percent": None,
                "volume": None,
                "currency": "VND",
                "data_as_of": None,
            }
        ]
    )
    assert await market.get_quote(session, "VN30F1M") is None


async def test_quote_returns_none_for_unknown_symbol() -> None:
    assert await market.get_quote(_FakeSession([]), "NOPE") is None


async def test_quote_maps_a_real_row() -> None:
    session = _FakeSession(
        [
            {
                "symbol": "VN30F1M",
                "name": "VN30F1M",
                "price": 1308.5,
                "change": 4.2,
                "change_percent": 0.32,
                "volume": 12345,
                "currency": "VND",
                "data_as_of": datetime.now(UTC),
            }
        ]
    )
    quote = await market.get_quote(session, "vn30f1m")
    assert quote is not None
    assert quote.symbol == "VN30F1M"
    assert quote.price == pytest.approx(1308.5)
    assert quote.is_stale is False


async def test_overview_without_model_output_is_honest() -> None:
    """No market_state row yet: report what we have and flag low
    conviction rather than inventing a regime."""
    # three quote lookups (all empty), then the market_state query
    session = _FakeSession([], [], [], [])
    overview = await market.get_overview(session)
    assert overview.quotes == []
    assert overview.public_signal == "low_conviction"
    assert overview.regime_probability == 0.0
    # An empty payload must never be presented as fresh
    assert overview.is_stale is True
    assert overview.source_status == "unavailable"
