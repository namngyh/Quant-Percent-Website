"""Backfill candles from Binance into the local store.

    python scripts/backfill.py                       # everything in config.yaml
    python scripts/backfill.py -t 1h 4h 1d           # only these timeframes
    python scripts/backfill.py -t 1m --start 2024-01-01

Safe to re-run: it resumes from the newest candle already stored, so a second
run only fetches what is missing.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import settings  # noqa: E402
from backend.data import service, store  # noqa: E402


def _format(count: int) -> str:
    return f"{count:,}".replace(",", " ")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill Binance candles")
    parser.add_argument("-s", "--symbols", nargs="+", default=None)
    parser.add_argument("-t", "--timeframes", nargs="+", default=None)
    parser.add_argument("--start", default=None, help="ISO date, e.g. 2017-01-01")
    args = parser.parse_args()

    symbols = args.symbols or settings.data.symbols
    timeframes = args.timeframes or settings.data.timeframes

    print(f"Symbols    : {', '.join(symbols)}")
    print(f"Timeframes : {', '.join(timeframes)}")
    print(f"From       : {args.start or settings.data.start_date}")
    print(f"Store      : {store.db_path()}\n")

    started = time.time()
    last_line = {"len": 0}

    def on_progress(progress) -> None:
        line = (
            f"  {progress.symbol} {progress.timeframe:>3s}  "
            f"{_format(progress.rows_written):>12s} rows  "
            f"({progress.pages} pages)"
        )
        pad = " " * max(0, last_line["len"] - len(line))
        print(line + pad, end="\r", flush=True)
        last_line["len"] = len(line)

    from backend.data.binance import BinanceClient, to_ms

    start_ms = to_ms(args.start) if args.start else None
    total = 0

    async with BinanceClient() as client:
        for symbol in symbols:
            for timeframe in timeframes:
                result = await service.backfill_series(
                    client, symbol, timeframe, start_ms=start_ms, progress_cb=on_progress
                )
                print()  # keep the finished line
                if result.error:
                    print(f"    ERROR: {result.error}")
                total += result.rows_written

    elapsed = time.time() - started
    print(f"\nDone: {_format(total)} rows in {elapsed:.1f}s\n")

    print(f"{'SERIES':<22}{'CANDLES':>12}")
    for row in store.list_coverage():
        label = f"{row['symbol']} {row['timeframe']}"
        print(f"{label:<22}{_format(row['count']):>12}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
