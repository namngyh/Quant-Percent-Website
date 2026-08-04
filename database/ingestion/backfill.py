"""Backfill lịch sử từ DataPro vào DB. Idempotent — chạy lại bao nhiêu lần
cũng được (upsert), dùng để nạp lần đầu hoặc vá lỗ hổng dữ liệu.

    docker compose stop ingestion            # tránh vượt rate limit 2 req/s
    docker compose run --rm --no-deps ingestion python backfill.py
    docker compose start ingestion

Nạp cho mọi mã trong SYMBOLS + STOCK_SYMBOLS:
- bars_1d : toàn bộ lịch sử ngày (OI, tự doanh, khối ngoại, adj_rate)
- bars_1m : bar phút chunk theo NĂM (response bị cap 500k dòng), is_final=true

TRADING_TIME là giờ VN encode dạng epoch — quy đổi như ingestion realtime.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone

import httpx
import psycopg

from config import load_config
from sources import _f, _i, now_vn_epoch, vn_epoch_to_utc

log = logging.getLogger("backfill")

SPACING = 1.3          # giây giữa 2 request (ingestion phải đang dừng)
MINUTE_START_YEAR = 2017   # dữ liệu phút DataPro không sớm hơn mốc này

BAR_1M_UPSERT = """
INSERT INTO bars_1m (symbol, ts, open, high, low, close, ref_px, volume, value,
                     buy_vol, buy_val, sell_vol, sell_val,
                     frn_buy_vol, frn_buy_val, frn_sell_vol, frn_sell_val,
                     adj_rate, is_final)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true)
ON CONFLICT (symbol, ts) DO UPDATE SET
    open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
    close = EXCLUDED.close, ref_px = EXCLUDED.ref_px,
    volume = EXCLUDED.volume, value = EXCLUDED.value,
    buy_vol = EXCLUDED.buy_vol, buy_val = EXCLUDED.buy_val,
    sell_vol = EXCLUDED.sell_vol, sell_val = EXCLUDED.sell_val,
    frn_buy_vol = EXCLUDED.frn_buy_vol, frn_buy_val = EXCLUDED.frn_buy_val,
    frn_sell_vol = EXCLUDED.frn_sell_vol, frn_sell_val = EXCLUDED.frn_sell_val,
    adj_rate = EXCLUDED.adj_rate, is_final = true, updated_at = now()
"""

BAR_1D_UPSERT = """
INSERT INTO bars_1d (symbol, trading_date, open, high, low, close, ref_px,
                     volume, value, oi, pt_vol, pt_val,
                     buy_vol, buy_val, sell_vol, sell_val,
                     port_buy_vol, port_buy_val, port_sell_vol, port_sell_val,
                     frn_buy_vol, frn_buy_val, frn_sell_vol, frn_sell_val, adj_rate)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (symbol, trading_date) DO UPDATE SET
    open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
    close = EXCLUDED.close, ref_px = EXCLUDED.ref_px,
    volume = EXCLUDED.volume, value = EXCLUDED.value, oi = EXCLUDED.oi,
    pt_vol = EXCLUDED.pt_vol, pt_val = EXCLUDED.pt_val,
    buy_vol = EXCLUDED.buy_vol, buy_val = EXCLUDED.buy_val,
    sell_vol = EXCLUDED.sell_vol, sell_val = EXCLUDED.sell_val,
    port_buy_vol = EXCLUDED.port_buy_vol, port_buy_val = EXCLUDED.port_buy_val,
    port_sell_vol = EXCLUDED.port_sell_vol, port_sell_val = EXCLUDED.port_sell_val,
    frn_buy_vol = EXCLUDED.frn_buy_vol, frn_buy_val = EXCLUDED.frn_buy_val,
    frn_sell_vol = EXCLUDED.frn_sell_vol, frn_sell_val = EXCLUDED.frn_sell_val,
    adj_rate = EXCLUDED.adj_rate
"""


def _vn_year_epoch(year: int) -> int:
    """Epoch-giờ-VN của 00:00 ngày 1/1 (quy ước TRADING_TIME của DataPro)."""
    return int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp())


async def _get_csv(client: httpx.AsyncClient, base: str, path: str) -> list[dict]:
    from csv import DictReader
    from io import StringIO
    for attempt in range(3):
        resp = await client.get(f"{base}{path}")
        if resp.status_code == 429:
            log.warning("429 rate limit, cho 5s (lan %d)", attempt + 1)
            await asyncio.sleep(5)
            continue
        resp.raise_for_status()
        text = resp.text.strip()
        return list(DictReader(StringIO(text))) if text else []
    return []


async def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"   # all | daily | minute
    cfg = load_config()
    symbols = cfg.symbols + cfg.stock_symbols
    now_vn = now_vn_epoch()
    this_year = datetime.now(timezone.utc).year
    log.info("Backfill %d ma: %s...", len(symbols), ", ".join(symbols[:5]))

    total_1d = total_1m = 0
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {cfg.datapro_api_key}"}, timeout=120,
    ) as client:
        pg = await psycopg.AsyncConnection.connect(cfg.pg_dsn, autocommit=True)
        for i, sym in enumerate(symbols, 1):
            # ---- 1) Daily: toàn bộ lịch sử trong 1 request
            rows = []
            if mode in ("all", "daily"):
                rows = await _get_csv(client, cfg.datapro_rest_url,
                                      f"/api/data/daily/{sym}/0/{now_vn}/0")
            if rows:
                data = [(
                    sym,
                    # TRADING_TIME daily = 00:00 GIỜ VN encode dạng epoch ->
                    # lấy thẳng ngày wall-clock, KHÔNG trừ 7h (trừ sẽ lùi 1 ngày)
                    datetime.fromtimestamp(
                        int(float(r["TRADING_TIME"])), tz=timezone.utc).date(),
                    _f(r, "OPEN_PX"), _f(r, "HIGH_PX"), _f(r, "LOW_PX"),
                    _f(r, "CLOSE_PX"), _f(r, "REF_PX"),
                    _i(r, "VOL"), _f(r, "VAL"), _i(r, "OI"),
                    _i(r, "PT_VOL"), _f(r, "PT_VAL"),
                    _i(r, "BUY_VOL"), _f(r, "BUY_VAL"),
                    _i(r, "SELL_VOL"), _f(r, "SELL_VAL"),
                    _i(r, "PORT_BUY_VOL"), _f(r, "PORT_BUY_VAL"),
                    _i(r, "PORT_SELL_VOL"), _f(r, "PORT_SELL_VAL"),
                    _i(r, "FRN_BUY_VOL"), _f(r, "FRN_BUY_VAL"),
                    _i(r, "FRN_SELL_VOL"), _f(r, "FRN_SELL_VAL"),
                    _f(r, "ADJ_RATE"),
                ) for r in rows]
                async with pg.cursor() as cur:
                    await cur.executemany(BAR_1D_UPSERT, data)
                total_1d += len(data)
            log.info("[%2d/%d] %s: daily %d phien", i, len(symbols), sym, len(rows))
            await asyncio.sleep(SPACING)

            # ---- 2) Minute: chunk theo năm
            sym_1m = 0
            years = range(MINUTE_START_YEAR, this_year + 1) \
                if mode in ("all", "minute") else []
            for year in years:
                y0, y1 = _vn_year_epoch(year), min(_vn_year_epoch(year + 1), now_vn)
                rows = await _get_csv(client, cfg.datapro_rest_url,
                                      f"/api/data/minute/{sym}/{y0}/{y1}/0")
                if rows:
                    data = [(
                        sym, vn_epoch_to_utc(int(float(r["TRADING_TIME"]))),
                        _f(r, "OPEN_PX"), _f(r, "HIGH_PX"), _f(r, "LOW_PX"),
                        _f(r, "CLOSE_PX"), _f(r, "REF_PX"),
                        _i(r, "VOL"), _f(r, "VAL"),
                        _i(r, "BUY_VOL"), _f(r, "BUY_VAL"),
                        _i(r, "SELL_VOL"), _f(r, "SELL_VAL"),
                        _i(r, "FRN_BUY_VOL"), _f(r, "FRN_BUY_VAL"),
                        _i(r, "FRN_SELL_VOL"), _f(r, "FRN_SELL_VAL"),
                        _f(r, "ADJ_RATE"),
                    ) for r in rows]
                    async with pg.cursor() as cur:
                        await cur.executemany(BAR_1M_UPSERT, data)
                    sym_1m += len(data)
                await asyncio.sleep(SPACING)
            total_1m += sym_1m
            log.info("[%2d/%d] %s: minute %d bar", i, len(symbols), sym, sym_1m)
        await pg.close()
    log.info("XONG: %d bar ngay + %d bar phut da vao DB", total_1d, total_1m)


if __name__ == "__main__":
    asyncio.run(main())
