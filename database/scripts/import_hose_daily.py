"""Load every HOSE stock's daily history from the local DataPro store.

Quant Portfolio can only measure a holding the database has prices for, and
until now that was 30 VN30 names. The DataPro file already on this machine
carries 406 HOSE tickers with a median of about fifteen years of sessions
each, so the limit was never the data — it was that nothing had loaded it.

Two things make this a bulk import rather than a feed change. Daily bars come
from a local SQLite file, so there is no rate limit to respect: the live
minute feed polls one symbol every 1.5 seconds and could not cover 400 names
inside a session, but it does not need to. And the portfolio endpoint values
positions from the last daily close, which this table already provides.

    python database/scripts/import_hose_daily.py
    python database/scripts/import_hose_daily.py --dry-run
    python database/scripts/import_hose_daily.py --since 2016-01-01

`HIST` is keyed by an opaque `EID` with no foreign key to `QUOTES_INFO`. The
link is reconstructed by fingerprinting, the same approach the DynamicGraph
connector documents: `QUOTES_INFO` holds the latest session's OHLCV per
symbol and the identical tuple appears in `HIST` under that symbol's EID.
Only tuples unique on both sides are accepted, so an ambiguous match is
dropped rather than guessed.
"""

from __future__ import annotations

import argparse
import os
import sys
import sqlite3
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import psycopg

# Scripts here run under several different virtualenvs, so the shared
# helper is imported by path rather than as a package.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _db import dsn_from_env  # noqa: E402

DEFAULT_DAT = r"C:\DataPro\D.dat"
DEFAULT_DSN = None  # resolved lazily by dsn_from_env()

# DataPro labels the Ho Chi Minh exchange HSX; the site calls it HOSE.
FEED_EXCHANGE = "HSX"
EXCHANGE = "HOSE"

# TRADING_KEY counts days since the Unix epoch.
EPOCH = date(1970, 1, 1)

# ICB supersector code (first four digits of ICB_ID) -> the label already used
# on the site, so a HOSE stock and a VN30 stock report the same sector name.
ICB_SUPERSECTOR = {
    "1030": "Chemicals",
    "1070": "Basic Resources",
    "1150": "Oil & Gas",
    "2030": "Construction & Materials",
    "2070": "Industrial Goods & Services",
    "3030": "Automobiles & Parts",
    "3050": "Food & Beverage",
    "3070": "Personal & Household Goods",
    "4050": "Health Care",
    "5030": "Retail",
    "5050": "Media",
    "5070": "Travel & Leisure",
    "6050": "Telecommunications",
    "7050": "Utilities",
    "8030": "Banks",
    "8050": "Insurance",
    "8060": "Real Estate",
    "8070": "Financial Services",
    "8090": "Equity Investment Instruments",
    "9050": "Technology",
}

FINGERPRINT_COLUMNS = ("OPEN_PX", "HIGH_PX", "LOW_PX", "CLOSE_PX", "VOL")
# How many recent sessions to try when fingerprinting. A symbol that did not
# trade on the very last session still matches on an earlier one.
FINGERPRINT_SESSIONS = 8


def open_readonly(path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)


def resolve_eids(con: sqlite3.Connection) -> dict[str, int]:
    """Reconstruct symbol -> EID by fingerprinting recent OHLCV tuples."""
    keys = [
        r[0]
        for r in con.execute(
            "SELECT DISTINCT TRADING_KEY FROM HIST "
            "ORDER BY TRADING_KEY DESC LIMIT ?",
            (FINGERPRINT_SESSIONS,),
        )
    ]

    quote_rows = con.execute(
        f"SELECT SYMBOL, {', '.join(FINGERPRINT_COLUMNS)} FROM QUOTES_INFO"
    ).fetchall()
    quote_fp: dict[tuple, list[str]] = {}
    for row in quote_rows:
        quote_fp.setdefault(tuple(row[1:]), []).append(row[0])

    mapping: dict[str, int] = {}
    for key in keys:
        hist_fp: dict[tuple, list[int]] = {}
        for row in con.execute(
            f"SELECT EID, {', '.join(FINGERPRINT_COLUMNS)} "
            "FROM HIST WHERE TRADING_KEY = ?",
            (key,),
        ):
            hist_fp.setdefault(tuple(row[1:]), []).append(row[0])

        for fingerprint, symbols in quote_fp.items():
            # Ambiguous on either side: skip rather than pick one.
            if len(symbols) != 1:
                continue
            eids = hist_fp.get(fingerprint)
            if not eids or len(eids) != 1:
                continue
            mapping.setdefault(symbols[0], eids[0])

    return mapping


def sector_for(icb_id) -> str | None:
    if icb_id is None:
        return None
    code = str(icb_id).strip()
    return ICB_SUPERSECTOR.get(code[:4])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dat", default=DEFAULT_DAT)
    parser.add_argument("--dsn", default=None)
    parser.add_argument(
        "--since",
        default="2015-01-01",
        help="earliest trading date to import (default 2015-01-01)",
    )
    parser.add_argument(
        "--min-sessions",
        type=int,
        default=60,
        help="skip symbols with fewer sessions than this (default 60)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Roll back instead of committing"
    )
    args = parser.parse_args()

    since = date.fromisoformat(args.since)
    since_key = (since - EPOCH).days

    con = open_readonly(args.dat)
    print(f"reading {args.dat}")

    mapping = resolve_eids(con)
    print(f"resolved symbol -> EID for {len(mapping)} instrument(s)")

    listed = con.execute(
        "SELECT SYMBOL, NAME, ICB_ID FROM QUOTES_INFO "
        "WHERE EXCHANGE = ? AND TYPE = 'STOCK'",
        (FEED_EXCHANGE,),
    ).fetchall()
    print(f"{FEED_EXCHANGE} stocks listed: {len(listed)}")

    stats = Counter()
    symbol_rows: list[tuple] = []
    bar_rows: list[tuple] = []

    for symbol, name, icb_id in listed:
        eid = mapping.get(symbol)
        if eid is None:
            stats["unmapped"] += 1
            continue

        history = con.execute(
            "SELECT TRADING_KEY, OPEN_PX, HIGH_PX, LOW_PX, CLOSE_PX, "
            "       REF_PX, VOL, VAL "
            "FROM HIST WHERE EID = ? AND TRADING_KEY >= ? "
            "ORDER BY TRADING_KEY",
            (eid, since_key),
        ).fetchall()

        usable = [r for r in history if r[4] is not None and float(r[4]) > 0]
        if len(usable) < args.min_sessions:
            stats["too_short"] += 1
            continue

        stats["imported"] += 1
        symbol_rows.append(
            (
                symbol,
                (name or symbol).strip()[:120],
                "stock",
                EXCHANGE,
                "VND",
                sector_for(icb_id),
                True,
                symbol,
            )
        )
        for key, o, h, low, c, ref, vol, val in usable:
            bar_rows.append(
                (
                    symbol,
                    EPOCH + timedelta(days=int(key)),
                    o,
                    h,
                    low,
                    c,
                    ref,
                    int(vol or 0),
                    val,
                )
            )

    con.close()

    print(f"  imported : {stats['imported']}")
    print(f"  unmapped : {stats['unmapped']}")
    print(f"  too short: {stats['too_short']} (< {args.min_sessions} sessions)")
    print(f"  bar rows : {len(bar_rows):,}")

    if not bar_rows:
        raise SystemExit("nothing to import")

    with psycopg.connect(dsn_from_env(args.dsn)) as pg:
        with pg.cursor() as cur:
            # Existing rows are left alone on conflict: the live feed owns the
            # sessions it has already written, and its intraday-derived close
            # is the one the rest of the site reads.
            cur.executemany(
                """
                INSERT INTO web.symbols
                    (symbol, name, kind, exchange, currency, sector,
                     is_public, feed_symbol)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol) DO UPDATE SET
                    name = EXCLUDED.name,
                    exchange = EXCLUDED.exchange,
                    sector = COALESCE(EXCLUDED.sector, web.symbols.sector),
                    is_public = EXCLUDED.is_public
                """,
                symbol_rows,
            )
            print(f"web.symbols upserted: {len(symbol_rows)}")

            # Staged through a temp table so the whole load is one COPY plus
            # one INSERT..SELECT, rather than 400k individual statements.
            cur.execute(
                "CREATE TEMP TABLE bars_1d_import "
                "(LIKE bars_1d INCLUDING DEFAULTS) ON COMMIT DROP"
            )
            with cur.copy(
                "COPY bars_1d_import (symbol, trading_date, open, high, low, "
                "close, ref_px, volume, value) FROM STDIN"
            ) as copy:
                for row in bar_rows:
                    copy.write_row(row)

            cur.execute(
                """
                INSERT INTO bars_1d
                    (symbol, trading_date, open, high, low, close,
                     ref_px, volume, value)
                SELECT symbol, trading_date, open, high, low, close,
                       ref_px, volume, value
                FROM bars_1d_import
                ON CONFLICT (symbol, trading_date) DO NOTHING
                """
            )
            inserted = cur.rowcount
            print(f"bars_1d inserted: {inserted:,} (existing rows untouched)")

        if args.dry_run:
            pg.rollback()
            print("dry run: rolled back")
        else:
            pg.commit()
            print("committed")


if __name__ == "__main__":
    main()
