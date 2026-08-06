"""Export VNINDEX daily bars from TimescaleDB to the CSV the models read.

Three of the four research models (rarf-fhe, msdp, raemf-mc) load their input
from a `VNINDEX_Daily.csv` shipped inside each repository. Those files are
snapshots: at 2026-08-04 every one of them still ended at 2026-07-13, which is
why the published artifacts were three weeks stale. The database has the same
series and keeps growing, so regenerate the CSV from it instead of exporting
by hand from the vendor app.

    python scripts/export_vnindex_daily.py --repo-root ..
    python scripts/export_vnindex_daily.py --out "D:/some/VNINDEX_Daily.csv"

Format: a plain six-column CSV. The vendor's own export writes thousands
separators unquoted, which splits one number across several CSV fields, and
both model parsers carry recovery code for it. That recovery only kicks in
when the header has more than six columns, so writing exactly six clean
columns takes the ordinary `pd.read_csv` path in every model. Dates are
ISO-8601; the parsers pass `dayfirst=True`, which pandas ignores for
unambiguous ISO input.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

# Scripts here run under several different virtualenvs, so the shared
# helper is imported by path rather than as a package.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _db import dsn_from_env  # noqa: E402

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover - dependency hint
    sys.exit('Missing dependency. Install with: pip install "psycopg[binary]"')

DEFAULT_DSN = None  # resolved lazily by dsn_from_env()

QUERY = """
SELECT trading_date, open, high, low, close, volume
FROM bars_1d
WHERE symbol = %s
  AND close IS NOT NULL
ORDER BY trading_date
"""

# Where each model keeps its copy, relative to the monorepo root.
MODEL_TARGETS = (
    "models/rarf-fhe/VNINDEX_Daily.csv",
    "models/rarf-fhe/data/raw/VNINDEX_Daily.csv",
    "models/msdp/data/raw/VNINDEX_Daily.csv",
    "models/raemf-mc/VNINDEX_Daily.csv",
)


def fetch_rows(dsn: str, symbol: str) -> list[tuple]:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(QUERY, (symbol,))
        return cur.fetchall()


def write_csv(path: Path, rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="" keeps csv from doubling line endings on Windows.
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
        for trading_date, open_, high, low, close, volume in rows:
            writer.writerow([
                trading_date.isoformat(),
                open_, high, low, close,
                int(volume or 0),
            ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=None, help="PostgreSQL DSN")
    parser.add_argument("--symbol", default="VNINDEX")
    parser.add_argument(
        "--repo-root",
        help="Monorepo root; refreshes every model's copy of the CSV.",
    )
    parser.add_argument("--out", help="Write a single file to this path instead.")
    args = parser.parse_args()

    if not args.repo_root and not args.out:
        parser.error("give --repo-root or --out")

    rows = fetch_rows(dsn_from_env(args.dsn), args.symbol)
    if not rows:
        print(f"No rows for {args.symbol}; is the database seeded?", file=sys.stderr)
        return 1

    targets: list[Path] = []
    if args.out:
        targets.append(Path(args.out))
    if args.repo_root:
        root = Path(args.repo_root).resolve()
        for relative in MODEL_TARGETS:
            target = root / relative
            # Only refresh copies that already exist: a missing file means
            # that model keeps its data somewhere else, and inventing one
            # would quietly shadow the real input.
            if target.exists():
                targets.append(target)
            else:
                print(f"skip (not present): {target}")

    for target in targets:
        write_csv(target, rows)
        print(f"wrote {len(rows):,} rows -> {target}")

    print(f"range {rows[0][0]} .. {rows[-1][0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
