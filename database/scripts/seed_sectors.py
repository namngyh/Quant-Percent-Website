"""Fill web.symbols.sector from the network model's per-stock export.

The column has been empty since the schema was created, which meant the
portfolio endpoint reported every holding as "Unclassified" and its sector
concentration was uniformly useless. The DynamicGraph node export already
carries an industry label for each VN30 member, so that is the source rather
than a hand-typed table that would drift.

Symbols the export does not cover are left NULL. A missing sector shows as
missing; it is never guessed.

    python database/scripts/seed_sectors.py
    python database/scripts/seed_sectors.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg

# Scripts here run under several different virtualenvs, so the shared
# helper is imported by path rather than as a package.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _db import dsn_from_env  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_NODES = ROOT / "frontend" / "public" / "research" / "dynamic-graph-nodes.json"
DEFAULT_DSN = None  # resolved lazily by dsn_from_env()


def load_sectors(path: Path) -> dict[str, str]:
    nodes = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for node in nodes:
        symbol = (node.get("id") or "").strip().upper()
        sector = (node.get("sector") or "").strip()
        if symbol and sector:
            out[symbol] = sector
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=None)
    parser.add_argument("--nodes", default=str(DEFAULT_NODES))
    parser.add_argument(
        "--dry-run", action="store_true", help="Roll back instead of committing"
    )
    args = parser.parse_args()

    path = Path(args.nodes)
    if not path.exists():
        raise SystemExit(
            f"{path} not found. Run `npm run research:sync` in frontend/ first."
        )

    sectors = load_sectors(path)
    if not sectors:
        raise SystemExit(f"{path} carries no sector labels.")

    with psycopg.connect(dsn_from_env(args.dsn)) as conn:
        with conn.cursor() as cur:
            updated = 0
            for symbol, sector in sectors.items():
                cur.execute(
                    "UPDATE web.symbols SET sector = %s WHERE symbol = %s",
                    (sector, symbol),
                )
                updated += cur.rowcount
            cur.execute(
                "SELECT count(*) FILTER (WHERE sector IS NULL) FROM web.symbols"
            )
            still_null = cur.fetchone()[0]

        if args.dry_run:
            conn.rollback()
            print("dry run: rolled back")
        else:
            conn.commit()
            print("committed")

    print(f"labels in export : {len(sectors)}")
    print(f"rows updated     : {updated}")
    print(f"symbols still without a sector: {still_null}")


if __name__ == "__main__":
    main()
