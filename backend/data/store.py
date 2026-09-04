"""DuckDB-backed OHLCV store.

One table holds every (symbol, timeframe) series. DuckDB handles the millions
of 1m candles we backfill from 2017 without a server process, and unlike raw
Parquet it supports the incremental upserts that live streaming needs.

The module keeps a single write connection behind a lock: DuckDB allows only
one process to hold the database file in write mode, and FastAPI serves
requests from a thread pool.
"""

from __future__ import annotations

import threading
from pathlib import Path

import duckdb
import pandas as pd

from backend.config import settings

_DB_LOCK = threading.RLock()
_CONN: duckdb.DuckDBPyConnection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (
    symbol     VARCHAR NOT NULL,
    timeframe  VARCHAR NOT NULL,
    open_time  BIGINT  NOT NULL,   -- epoch milliseconds, candle open
    open       DOUBLE  NOT NULL,
    high       DOUBLE  NOT NULL,
    low        DOUBLE  NOT NULL,
    close      DOUBLE  NOT NULL,
    volume     DOUBLE  NOT NULL,
    PRIMARY KEY (symbol, timeframe, open_time)
);
"""

OHLCV_COLUMNS = ["open_time", "open", "high", "low", "close", "volume"]


def db_path() -> Path:
    return settings.data.store_path / "qp.duckdb"


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return the shared write connection, creating the schema on first use."""
    global _CONN
    with _DB_LOCK:
        if _CONN is None:
            _CONN = duckdb.connect(str(db_path()))
            _CONN.execute(SCHEMA)
        return _CONN


def close_connection() -> None:
    global _CONN
    with _DB_LOCK:
        if _CONN is not None:
            _CONN.close()
            _CONN = None


def upsert_candles(symbol: str, timeframe: str, df: pd.DataFrame) -> int:
    """Insert candles, replacing any that already exist at the same open_time.

    Replacing rather than ignoring matters for live data: the most recent
    candle is still forming and gets rewritten on every update.

    Returns the number of rows written.
    """
    if df is None or df.empty:
        return 0

    missing = set(OHLCV_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"candle frame missing columns: {sorted(missing)}")

    payload = df[OHLCV_COLUMNS].copy()
    payload.insert(0, "timeframe", timeframe)
    payload.insert(0, "symbol", symbol)
    payload = payload.drop_duplicates(subset=["symbol", "timeframe", "open_time"], keep="last")

    conn = get_connection()
    with _DB_LOCK:
        conn.register("_incoming", payload)
        try:
            # DELETE-then-INSERT: DuckDB has no UPSERT on a plain primary key
            # that also works when the incoming batch overlaps stored rows.
            conn.execute(
                """
                DELETE FROM candles
                WHERE (symbol, timeframe, open_time) IN (
                    SELECT symbol, timeframe, open_time FROM _incoming
                )
                """
            )
            conn.execute("INSERT INTO candles SELECT * FROM _incoming")
        finally:
            conn.unregister("_incoming")

    return len(payload)


def get_candles(
    symbol: str,
    timeframe: str,
    start_ms: int | None = None,
    end_ms: int | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    """Fetch candles ordered oldest-first.

    When ``limit`` is set the *most recent* ``limit`` candles in range are
    returned — a chart wants the latest window, not the first one.
    """
    clauses = ["symbol = ?", "timeframe = ?"]
    params: list = [symbol, timeframe]
    if start_ms is not None:
        clauses.append("open_time >= ?")
        params.append(start_ms)
    if end_ms is not None:
        clauses.append("open_time <= ?")
        params.append(end_ms)

    where = " AND ".join(clauses)

    if limit:
        sql = f"""
            SELECT * FROM (
                SELECT {', '.join(OHLCV_COLUMNS)}
                FROM candles WHERE {where}
                ORDER BY open_time DESC LIMIT ?
            ) ORDER BY open_time ASC
        """
        params.append(limit)
    else:
        sql = f"""
            SELECT {', '.join(OHLCV_COLUMNS)}
            FROM candles WHERE {where} ORDER BY open_time ASC
        """

    conn = get_connection()
    with _DB_LOCK:
        return conn.execute(sql, params).df()


def get_coverage(symbol: str, timeframe: str) -> dict | None:
    """Return {first, last, count} in epoch ms, or None if nothing stored."""
    conn = get_connection()
    with _DB_LOCK:
        row = conn.execute(
            """
            SELECT MIN(open_time), MAX(open_time), COUNT(*)
            FROM candles WHERE symbol = ? AND timeframe = ?
            """,
            [symbol, timeframe],
        ).fetchone()

    if not row or row[2] == 0:
        return None
    return {"first": int(row[0]), "last": int(row[1]), "count": int(row[2])}


def list_coverage() -> list[dict]:
    """Coverage summary for every stored (symbol, timeframe) pair."""
    conn = get_connection()
    with _DB_LOCK:
        rows = conn.execute(
            """
            SELECT symbol, timeframe, MIN(open_time), MAX(open_time), COUNT(*)
            FROM candles GROUP BY symbol, timeframe
            ORDER BY symbol, COUNT(*) DESC
            """
        ).fetchall()

    return [
        {
            "symbol": r[0],
            "timeframe": r[1],
            "first": int(r[2]),
            "last": int(r[3]),
            "count": int(r[4]),
        }
        for r in rows
    ]
