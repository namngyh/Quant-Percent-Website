"""Cấu trúc dữ liệu chuẩn hóa. MỘT object duy nhất đi qua cả 3 nhánh
(Redis publish / DB / Parquet) để đảm bảo dữ liệu model thấy khớp 1:1 với DB.

- Tick : pseudo-tick từ snapshot /api/symbols (giá khớp + bid/ask, ts = lúc quan sát)
- Bar  : bar 1 phút chính thức từ /api/data/minute (OHLC + buy/sell + khối ngoại)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass(slots=True)
class Tick:
    symbol: str
    ts: datetime                    # timezone-aware UTC, thời điểm quan sát
    price: float                    # CLOSE_PX
    volume: int | None = None       # delta VOL giữa 2 lần poll
    bid_px: float | None = None
    bid_vol: int | None = None
    ask_px: float | None = None
    ask_vol: int | None = None
    total_vol: int | None = None    # VOL lũy kế phiên
    ref_px: float | None = None
    seq: int = 0

    def to_json(self) -> str:
        d = asdict(self)
        d["ts"] = self.ts.astimezone(timezone.utc).isoformat()
        return json.dumps(d, separators=(",", ":"))

    def db_row(self) -> tuple:
        return (self.symbol, self.ts, self.price, self.volume,
                self.bid_px, self.bid_vol, self.ask_px, self.ask_vol,
                self.total_vol, self.ref_px, self.seq)

    def parquet_row(self) -> dict:
        d = asdict(self)
        d["ts"] = self.ts.astimezone(timezone.utc)
        return d


@dataclass(slots=True)
class Bar:
    symbol: str
    ts: datetime                    # bar start, timezone-aware UTC
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    ref_px: float | None = None
    volume: int | None = None
    value: float | None = None
    buy_vol: int | None = None
    buy_val: float | None = None
    sell_vol: int | None = None
    sell_val: float | None = None
    frn_buy_vol: int | None = None
    frn_buy_val: float | None = None
    frn_sell_vol: int | None = None
    frn_sell_val: float | None = None
    adj_rate: float | None = None   # hệ số điều chỉnh giá (cổ phiếu)
    final: bool = False             # bar đã đóng, không đổi nữa

    def to_json(self) -> str:
        d = asdict(self)
        d["ts"] = self.ts.astimezone(timezone.utc).isoformat()
        return json.dumps(d, separators=(",", ":"))

    def db_row(self) -> tuple:
        return (self.symbol, self.ts, self.open, self.high, self.low, self.close,
                self.ref_px, self.volume, self.value,
                self.buy_vol, self.buy_val, self.sell_vol, self.sell_val,
                self.frn_buy_vol, self.frn_buy_val,
                self.frn_sell_vol, self.frn_sell_val, self.adj_rate, self.final)

    def parquet_row(self) -> dict:
        d = asdict(self)
        d.pop("final")
        d["ts"] = self.ts.astimezone(timezone.utc)
        return d
