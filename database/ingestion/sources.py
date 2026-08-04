"""Nguồn dữ liệu. Mỗi source là async generator yield Tick hoặc Bar.

DataPro (app Windows chạy API server REST tại cổng 6789, auth Bearer,
rate limit ~2 req/s, response CSV):

- SnapshotSource  : poll /api/symbols (KHÔNG filter — 1 request trả toàn bộ
                    ~2100 mã) mỗi 1s, lọc theo watchlist -> pseudo-tick khi
                    (price, vol, bid, ask) của mã đó thay đổi. Nhờ bulk nên
                    theo dõi 1 hay 100 mã vẫn chỉ tốn 1 req/s.
- MinuteBarSource : poll /api/data/minute/{symbol} -> bar 1 phút chính thức.
                    Lịch quay vòng xen kẽ có ưu tiên, mỗi request cách nhau
                    bar_spacing giây: [VN30F1M, cp1, VN30F1M, cp2, ...]
                    -> VN30F1M refresh mỗi ~3s, mỗi cổ phiếu mỗi ~90s.
                    Tổng: 1 (bulk) + 0.67 (bar) ≈ 1.7 req/s < limit 2 req/s.

LƯU Ý ĐÃ KIỂM CHỨNG THỰC TẾ (2026-07-23): TRADING_TIME của DataPro là
GIỜ VN encode dạng epoch (bar "09:00" là 9h sáng VN chứ không phải UTC).
Tham số from/to trên URL cũng theo quy ước đó. Hai hàm chuyển đổi bên dưới
xử lý việc này; ts trong pipeline luôn là UTC thật.

MockTickSource / MockBarSource: giả lập để test pipeline không cần DataPro.
"""
from __future__ import annotations

import asyncio
import logging
import random
from csv import DictReader
from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import AsyncIterator
from zoneinfo import ZoneInfo

from config import Config
from records import Bar, Tick

log = logging.getLogger("source")

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


# ---------------------------------------------------------------- time utils
def vn_epoch_to_utc(tt: int | float) -> datetime:
    """TRADING_TIME (giờ VN encode dạng epoch) -> datetime UTC thật."""
    wall = datetime.fromtimestamp(float(tt), tz=timezone.utc).replace(tzinfo=None)
    return wall.replace(tzinfo=VN_TZ).astimezone(timezone.utc)


def now_vn_epoch() -> int:
    """Thời điểm hiện tại theo quy ước epoch-giờ-VN của DataPro."""
    wall = datetime.now(VN_TZ).replace(tzinfo=None)
    return int(wall.replace(tzinfo=timezone.utc).timestamp())


def _f(row: dict, key: str) -> float | None:
    v = row.get(key)
    if v is None or v == "":
        return None
    return float(v)


def _i(row: dict, key: str) -> int | None:
    v = _f(row, key)
    return int(v) if v is not None else None


# ------------------------------------------------------------ DataPro client
class _DataProBase:
    def __init__(self, cfg: Config):
        if not cfg.datapro_rest_url:
            raise RuntimeError("DATAPRO_REST_URL chua duoc dien trong .env")
        self.cfg = cfg
        self.base = cfg.datapro_rest_url
        self.headers = {"Authorization": f"Bearer {cfg.datapro_api_key}"}

    async def _get_csv(self, client, path: str) -> list[dict]:
        resp = await client.get(f"{self.base}{path}")
        if resp.status_code == 429:
            log.warning("DataPro 429 rate limit — cho 3s")
            await asyncio.sleep(3)
            return []
        resp.raise_for_status()
        text = resp.text.strip()
        if not text:
            return []
        return list(DictReader(StringIO(text)))


class SnapshotSource(_DataProBase):
    """Poll bulk snapshot -> pseudo-tick cho mọi mã trong watchlist.
    Chỉ emit khi thị trường thay đổi, nên ngoài giờ giao dịch sẽ im lặng."""

    def __init__(self, cfg: Config):
        super().__init__(cfg)
        self.watch = set(cfg.symbols) | set(cfg.stock_symbols)
        self._state: dict[str, tuple] = {}       # symbol -> key so sánh thay đổi
        self._total_vol: dict[str, int] = {}     # symbol -> VOL lũy kế lần trước

    async def stream(self) -> AsyncIterator[Tick]:
        import httpx
        async with httpx.AsyncClient(headers=self.headers, timeout=10) as client:
            log.info("SnapshotSource start: bulk poll moi %.1fs, watch %d ma",
                     self.cfg.snapshot_interval, len(self.watch))
            while True:
                rows = await self._get_csv(client, "/api/symbols")
                for row in rows:
                    sym = row.get("SYMBOL")
                    if sym not in self.watch:
                        continue
                    tick = self._diff(sym, row)
                    if tick is not None:
                        yield tick
                await asyncio.sleep(self.cfg.snapshot_interval)

    def _diff(self, sym: str, row: dict) -> Tick | None:
        price = _f(row, "CLOSE_PX")
        vol = _i(row, "VOL") or 0
        key = (price, vol, _f(row, "BID_PX"), _i(row, "BID_VOL"),
               _f(row, "ASK_PX"), _i(row, "ASK_VOL"))
        prev_key = self._state.get(sym)
        self._state[sym] = key
        if prev_key is None:
            # Lần quan sát đầu sau khởi động: chỉ seed state, không emit
            # (tránh ghi tick giả ngoài giờ từ snapshot cũ).
            self._total_vol[sym] = vol
            return None
        if key == prev_key:
            return None
        prev_vol = self._total_vol.get(sym, 0)
        delta = vol - prev_vol if vol >= prev_vol else vol  # vol giảm = phiên mới
        self._total_vol[sym] = vol
        return Tick(
            symbol=sym,
            ts=datetime.now(timezone.utc),
            price=price,
            volume=delta,
            bid_px=_f(row, "BID_PX"), bid_vol=_i(row, "BID_VOL"),
            ask_px=_f(row, "ASK_PX"), ask_vol=_i(row, "ASK_VOL"),
            total_vol=vol,
            ref_px=_f(row, "REF_PX"),
        )


class MinuteBarSource(_DataProBase):
    """Poll bar phút cả ngày hiện tại (241 bar/ngày — nhẹ), so với cache,
    yield bar thay đổi. Bar final khi: có bar muộn hơn trong response,
    hoặc đã quá cuối bar 30s.

    Lịch quay vòng xen kẽ ưu tiên: [uu_tien..., cp1, uu_tien..., cp2, ...]
    mỗi request cách bar_spacing giây -> mã ưu tiên luôn tươi, cổ phiếu
    quay hết vòng trong n_stock * 2 * bar_spacing giây."""

    FINAL_GRACE = 30  # giây sau khi bar kết thúc thì coi là đóng

    def __init__(self, cfg: Config):
        super().__init__(cfg)
        self._cache: dict[tuple[str, int], tuple] = {}   # (sym, tt) -> nội dung
        self._final: set[tuple[str, int]] = set()

    def _slot_iter(self):
        """Sinh vô hạn thứ tự mã cần poll, xen kẽ ưu tiên/cổ phiếu."""
        prio = self.cfg.symbols
        stocks = self.cfg.stock_symbols
        while True:
            if not stocks:
                yield from prio
                continue
            for s in stocks:
                yield from prio
                yield s

    async def stream(self) -> AsyncIterator[Bar]:
        import httpx
        async with httpx.AsyncClient(headers=self.headers, timeout=15) as client:
            log.info("MinuteBarSource start: uu_tien=%s + %d co phieu, "
                     "1 request moi %.1fs",
                     self.cfg.symbols, len(self.cfg.stock_symbols),
                     self.cfg.bar_spacing)
            # Lệch pha với SnapshotSource để dàn đều request
            await asyncio.sleep(0.5)
            for sym in self._slot_iter():
                async for bar in self._poll_symbol(client, sym):
                    yield bar
                await asyncio.sleep(self.cfg.bar_spacing)

    async def _poll_symbol(self, client, sym: str) -> AsyncIterator[Bar]:
        now_vn = now_vn_epoch()
        day_start = now_vn - (now_vn % 86400)            # 00:00 giờ VN hôm nay
        rows = await self._get_csv(
            client, f"/api/data/minute/{sym}/{day_start}/{now_vn + 300}/0")
        if not rows:
            return
        max_tt = max(int(float(r["TRADING_TIME"])) for r in rows)
        for row in rows:
            tt = int(float(row["TRADING_TIME"]))
            content = tuple(row.get(k) for k in (
                "OPEN_PX", "HIGH_PX", "LOW_PX", "CLOSE_PX", "VOL", "VAL",
                "BUY_VOL", "BUY_VAL", "SELL_VOL", "SELL_VAL"))
            is_final = (tt < max_tt) or (now_vn >= tt + 60 + self.FINAL_GRACE)
            ck = (sym, tt)
            changed = self._cache.get(ck) != content
            newly_final = is_final and ck not in self._final
            if not changed and not newly_final:
                continue
            self._cache[ck] = content
            if is_final:
                self._final.add(ck)
            yield Bar(
                symbol=sym,
                ts=vn_epoch_to_utc(tt),
                open=_f(row, "OPEN_PX"), high=_f(row, "HIGH_PX"),
                low=_f(row, "LOW_PX"), close=_f(row, "CLOSE_PX"),
                ref_px=_f(row, "REF_PX"),
                volume=_i(row, "VOL"), value=_f(row, "VAL"),
                buy_vol=_i(row, "BUY_VOL"), buy_val=_f(row, "BUY_VAL"),
                sell_vol=_i(row, "SELL_VOL"), sell_val=_f(row, "SELL_VAL"),
                frn_buy_vol=_i(row, "FRN_BUY_VOL"), frn_buy_val=_f(row, "FRN_BUY_VAL"),
                frn_sell_vol=_i(row, "FRN_SELL_VOL"), frn_sell_val=_f(row, "FRN_SELL_VAL"),
                adj_rate=_f(row, "ADJ_RATE"),
                final=is_final,
            )
        # Gọn cache: bỏ ngày cũ
        for ck in [k for k in self._cache if k[1] < day_start]:
            self._cache.pop(ck, None)
            self._final.discard(ck)


# ------------------------------------------------------------------- mocks
class MockTickSource:
    """Pseudo-tick giả lập: random walk quanh 1840, kèm bid/ask, 2 tick/s."""

    def __init__(self, cfg: Config):
        self.symbols = cfg.symbols
        self._price: dict[str, float] = {}
        self._total: dict[str, int] = {}

    async def stream(self) -> AsyncIterator[Tick]:
        log.info("MockTickSource start: %s", self.symbols)
        while True:
            for sym in self.symbols:
                p = round(self._price.get(sym, 1840.0) + random.gauss(0, 0.2), 1)
                self._price[sym] = p
                dv = random.randint(1, 30)
                self._total[sym] = self._total.get(sym, 0) + dv
                yield Tick(
                    symbol=sym, ts=datetime.now(timezone.utc), price=p,
                    volume=dv,
                    bid_px=round(p - 0.1, 1), bid_vol=random.randint(1, 200),
                    ask_px=round(p + 0.1, 1), ask_vol=random.randint(1, 200),
                    total_vol=self._total[sym], ref_px=1837.6,
                )
            await asyncio.sleep(0.5)


class MockBarSource:
    """Bar phút giả lập: cập nhật bar phút hiện tại mỗi 2s, phút trước
    được phát lại với final=True khi sang phút mới."""

    def __init__(self, cfg: Config):
        self.symbols = cfg.symbols
        self._state: dict[str, dict] = {}

    def _bar(self, sym: str, minute: datetime, final: bool) -> Bar:
        st = self._state[sym]
        return Bar(
            symbol=sym, ts=minute,
            open=st["open"], high=st["high"], low=st["low"], close=st["close"],
            ref_px=1837.6, volume=st["vol"], value=round(st["val"], 1),
            buy_vol=st["bvol"], buy_val=round(st["bval"], 1),
            sell_vol=st["svol"], sell_val=round(st["sval"], 1),
            frn_buy_vol=0, frn_buy_val=0.0, frn_sell_vol=0, frn_sell_val=0.0,
            adj_rate=1.0,
            final=final,
        )

    async def stream(self) -> AsyncIterator[Bar]:
        log.info("MockBarSource start: %s", self.symbols)
        cur_minute: datetime | None = None
        price: dict[str, float] = {}
        while True:
            minute = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            for sym in self.symbols:
                p = round(price.get(sym, 1840.0) + random.gauss(0, 0.3), 1)
                price[sym] = p
                if minute != cur_minute:
                    if cur_minute is not None and sym in self._state:
                        yield self._bar(sym, cur_minute, final=True)
                    self._state[sym] = {"open": p, "high": p, "low": p, "close": p,
                                        "vol": 0, "val": 0.0, "bvol": 0, "bval": 0.0,
                                        "svol": 0, "sval": 0.0}
                st = self._state[sym]
                dv = random.randint(20, 200)
                is_buy = random.random() < 0.5
                st.update(high=max(st["high"], p), low=min(st["low"], p), close=p)
                st["vol"] += dv
                st["val"] += p * dv
                if is_buy:
                    st["bvol"] += dv
                    st["bval"] += p * dv
                else:
                    st["svol"] += dv
                    st["sval"] += p * dv
                yield self._bar(sym, minute, final=False)
            cur_minute = minute
            await asyncio.sleep(2)


# ------------------------------------------------------------------ factory
def make_sources(cfg: Config) -> list[tuple[str, object]]:
    """Trả về [(tên, source), ...] — mỗi source chạy trong 1 runner riêng
    với reconnect backoff + gap_log độc lập."""
    if cfg.mode == "mock":
        return [("mock-tick", MockTickSource(cfg)), ("mock-bar", MockBarSource(cfg))]
    if cfg.mode == "datapro":
        return [("snapshot", SnapshotSource(cfg)), ("minute", MinuteBarSource(cfg))]
    raise ValueError(f"DATAPRO_MODE khong hop le: {cfg.mode} (mock | datapro)")
