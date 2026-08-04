"""Data schema constants."""

from __future__ import annotations

CANONICAL_COLUMNS = ["date", "open", "high", "low", "close", "volume"]
REQUIRED_COLUMNS = ["date", "close"]
OPTIONAL_COLUMNS = ["open", "high", "low", "volume"]

COLUMN_ALIASES = {
    "date": {"date", "tradingdate", "trading_date", "ngay"},
    "open": {"open", "openprice", "open_price"},
    "high": {"high", "highprice", "high_price"},
    "low": {"low", "lowprice", "low_price"},
    "close": {"close", "closeprice", "close_price", "adjclose", "adj_close"},
    "volume": {"volume", "vol", "khoiluong", "khoi_luong"},
}
