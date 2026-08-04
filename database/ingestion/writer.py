"""Ghi Tick/Bar ra 3 nhánh, theo đúng thứ tự ưu tiên:

1. PUBLISH Redis NGAY khi nhận (`ticks:{symbol}` / `bars:{symbol}`)
   — độ trễ tới model là ưu tiên số 1
2. TimescaleDB: ticks batch INSERT ON CONFLICT DO NOTHING (100 tick/500ms);
   bars_1m upsert ngay (tần suất thấp)
3. Parquet rolling theo ngày VN: data/raw/ticks/ (mọi tick),
   data/raw/bars_1m/ (chỉ bar final)

Cùng MỘT object đã chuẩn hóa đi qua cả 3 nhánh → model thấy gì, DB lưu đó.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
import pyarrow as pa
import pyarrow.parquet as pq
import redis.asyncio as aioredis

from config import Config
from records import Bar, Tick

log = logging.getLogger("writer")

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

TICK_INSERT_SQL = """
INSERT INTO ticks (symbol, ts, price, volume, bid_px, bid_vol, ask_px, ask_vol,
                   total_vol, ref_px, seq)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING
"""

BAR_UPSERT_SQL = """
INSERT INTO bars_1m (symbol, ts, open, high, low, close, ref_px, volume, value,
                     buy_vol, buy_val, sell_vol, sell_val,
                     frn_buy_vol, frn_buy_val, frn_sell_vol, frn_sell_val,
                     adj_rate, is_final)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (symbol, ts) DO UPDATE SET
    open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
    close = EXCLUDED.close, ref_px = EXCLUDED.ref_px,
    volume = EXCLUDED.volume, value = EXCLUDED.value,
    buy_vol = EXCLUDED.buy_vol, buy_val = EXCLUDED.buy_val,
    sell_vol = EXCLUDED.sell_vol, sell_val = EXCLUDED.sell_val,
    frn_buy_vol = EXCLUDED.frn_buy_vol, frn_buy_val = EXCLUDED.frn_buy_val,
    frn_sell_vol = EXCLUDED.frn_sell_vol, frn_sell_val = EXCLUDED.frn_sell_val,
    adj_rate = EXCLUDED.adj_rate,
    is_final = bars_1m.is_final OR EXCLUDED.is_final,
    updated_at = now()
"""

TICK_SCHEMA = pa.schema([
    ("symbol", pa.string()), ("ts", pa.timestamp("us", tz="UTC")),
    ("price", pa.float64()), ("volume", pa.int64()),
    ("bid_px", pa.float64()), ("bid_vol", pa.int64()),
    ("ask_px", pa.float64()), ("ask_vol", pa.int64()),
    ("total_vol", pa.int64()), ("ref_px", pa.float64()), ("seq", pa.int64()),
])

BAR_SCHEMA = pa.schema([
    ("symbol", pa.string()), ("ts", pa.timestamp("us", tz="UTC")),
    ("open", pa.float64()), ("high", pa.float64()),
    ("low", pa.float64()), ("close", pa.float64()),
    ("ref_px", pa.float64()), ("volume", pa.int64()), ("value", pa.float64()),
    ("buy_vol", pa.int64()), ("buy_val", pa.float64()),
    ("sell_vol", pa.int64()), ("sell_val", pa.float64()),
    ("frn_buy_vol", pa.int64()), ("frn_buy_val", pa.float64()),
    ("frn_sell_vol", pa.int64()), ("frn_sell_val", pa.float64()),
    ("adj_rate", pa.float64()),
])


class ParquetSink:
    """Ghi rolling theo ngày VN. Restart giữa ngày -> file .partN mới
    (không append được vào file parquet đã đóng, không đè dữ liệu cũ)."""

    def __init__(self, root: Path, schema: pa.Schema,
                 batch_rows: int, flush_interval: float):
        self.root = root
        self.schema = schema
        self.batch_rows = batch_rows
        self.flush_interval = flush_interval
        self.buf: list[dict] = []
        self.writer: pq.ParquetWriter | None = None
        self.day: str | None = None
        self.last_flush = 0.0
        root.mkdir(parents=True, exist_ok=True)

    def add(self, row: dict) -> None:
        self.buf.append(row)

    def maybe_flush(self, now: float, force: bool = False) -> None:
        due = force or len(self.buf) >= self.batch_rows or (
            self.buf and now - self.last_flush >= self.flush_interval)
        if not due or not self.buf:
            return
        rows, self.buf = self.buf, []
        self.last_flush = now

        day = datetime.now(timezone.utc).astimezone(VN_TZ).strftime("%Y-%m-%d")
        if self.writer is not None and day != self.day:
            self.writer.close()
            self.writer = None
        if self.writer is None:
            path = self.root / f"{day}.parquet"
            if path.exists():
                n = 1
                while (p2 := self.root / f"{day}.part{n}.parquet").exists():
                    n += 1
                path = p2
            self.writer = pq.ParquetWriter(path, self.schema)
            self.day = day
            log.info("Mo parquet: %s", path)
        self.writer.write_table(pa.Table.from_pylist(rows, schema=self.schema))

    def close(self) -> None:
        if self.writer is not None:
            self.writer.close()
            self.writer = None


class PipelineWriter:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.redis: aioredis.Redis | None = None
        self.pg: psycopg.AsyncConnection | None = None
        self._tick_buf: list[Tick] = []
        self._tick_pq = ParquetSink(Path(cfg.parquet_dir) / "ticks", TICK_SCHEMA,
                                    cfg.parquet_batch_rows, cfg.parquet_flush_interval)
        self._bar_pq = ParquetSink(Path(cfg.parquet_dir) / "bars_1m", BAR_SCHEMA,
                                   batch_rows=200, flush_interval=60.0)
        self._flush_task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    # ------------------------------------------------------------------ setup
    async def start(self) -> None:
        self.redis = aioredis.from_url(self.cfg.redis_url, decode_responses=True)
        await self.redis.ping()
        log.info("Redis connected: %s", self.cfg.redis_url)
        await self._connect_pg()
        self._flush_task = asyncio.create_task(self._flush_loop())

    async def _connect_pg(self) -> None:
        self.pg = await psycopg.AsyncConnection.connect(
            self.cfg.pg_dsn, autocommit=True)
        log.info("PostgreSQL connected")

    async def _pg_exec(self, sql: str, rows: list[tuple], many: bool) -> None:
        if self.pg is None or self.pg.closed:
            await self._connect_pg()
        async with self.pg.cursor() as cur:
            if many:
                await cur.executemany(sql, rows)
            else:
                await cur.execute(sql, rows[0])

    # ----------------------------------------------------------------- handle
    async def handle(self, event: Tick | Bar) -> None:
        """1 record đã validate: Redis trước, DB/Parquet sau."""
        if isinstance(event, Tick):
            await self._handle_tick(event)
        else:
            await self._handle_bar(event)

    async def _handle_tick(self, tick: Tick) -> None:
        try:
            await self.redis.publish(f"ticks:{tick.symbol}", tick.to_json())
        except Exception as e:
            log.warning("Redis publish tick loi (tick van vao DB): %s", e)
        self._tick_buf.append(tick)
        if len(self._tick_buf) >= self.cfg.batch_size:
            try:
                await self._flush_ticks()
            except Exception as e:
                log.error("flush ticks loi (giu buffer): %s", e)
        self._tick_pq.add(tick.parquet_row())

    async def _handle_bar(self, bar: Bar) -> None:
        try:
            await self.redis.publish(f"bars:{bar.symbol}", bar.to_json())
        except Exception as e:
            log.warning("Redis publish bar loi (bar van vao DB): %s", e)
        try:
            await self._pg_exec(BAR_UPSERT_SQL, [bar.db_row()], many=False)
        except Exception as e:
            log.error("upsert bar loi %s %s: %s", bar.symbol, bar.ts, e)
        if bar.final:
            self._bar_pq.add(bar.parquet_row())

    # ------------------------------------------------------------------ flush
    async def _flush_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=self.cfg.flush_interval)
            except asyncio.TimeoutError:
                pass
            try:
                await self._flush_ticks()
            except Exception as e:
                log.error("flush DB loi (giu buffer, thu lai): %s", e)
            now = asyncio.get_event_loop().time()
            for sink in (self._tick_pq, self._bar_pq):
                try:
                    sink.maybe_flush(now)
                except Exception as e:
                    log.error("flush parquet loi: %s", e)

    async def _flush_ticks(self) -> None:
        if not self._tick_buf:
            return
        batch, self._tick_buf = self._tick_buf, []
        try:
            await self._pg_exec(TICK_INSERT_SQL, [t.db_row() for t in batch], many=True)
            log.debug("DB flush %d tick", len(batch))
        except Exception:
            self._tick_buf = batch + self._tick_buf
            if len(self._tick_buf) > 100_000:
                dropped = len(self._tick_buf) - 100_000
                self._tick_buf = self._tick_buf[-100_000:]
                log.error("DB buffer qua lon, bo %d tick cu nhat", dropped)
            raise

    # ---------------------------------------------------------------- gap log
    async def log_disconnect(self, note: str) -> int | None:
        try:
            if self.pg is None or self.pg.closed:
                await self._connect_pg()
            async with self.pg.cursor() as cur:
                await cur.execute(
                    "INSERT INTO gap_log (symbol, disconnect_ts, note) "
                    "VALUES (%s, now(), %s) RETURNING id",
                    (",".join(self.cfg.symbols), note[:500]))
                row = await cur.fetchone()
                return row[0]
        except Exception as e:
            log.error("khong ghi duoc gap_log: %s", e)
            return None

    async def log_reconnect(self, gap_id: int | None) -> None:
        if gap_id is None:
            return
        try:
            async with self.pg.cursor() as cur:
                await cur.execute(
                    "UPDATE gap_log SET reconnect_ts = now() WHERE id = %s",
                    (gap_id,))
        except Exception as e:
            log.error("khong cap nhat duoc gap_log: %s", e)

    # --------------------------------------------------------------- shutdown
    async def close(self) -> None:
        self._stop.set()
        if self._flush_task:
            await self._flush_task
        try:
            await self._flush_ticks()
        except Exception as e:
            log.error("flush cuoi loi: %s", e)
        now = asyncio.get_event_loop().time()
        for sink in (self._tick_pq, self._bar_pq):
            try:
                sink.maybe_flush(now, force=True)
            except Exception as e:
                log.error("parquet cuoi loi: %s", e)
            sink.close()
        if self.pg is not None and not self.pg.closed:
            await self.pg.close()
        if self.redis is not None:
            await self.redis.aclose()
        log.info("Writer closed")
