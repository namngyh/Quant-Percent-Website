"""Print how many minute bars are stored for today, on the database PG_DSN names.

`daily-update.bat` gates the whole run on this number. No bars today means a
holiday, or a collector that did not run, and running the model on stale data
would overwrite a correct forecast with a worse one.

It is a script rather than an inline command because the gate used to be

    docker exec qp-timescaledb psql -U quant -d market -c "select count(*) ..."

which addressed the local container by name while every other step of the job
connected through PG_DSN. Once ingestion moved to the VPS over the VPN, the
gate was counting rows in a database nobody was writing to any more, so the
job logged "no bars today" and skipped — every day, silently, with exit code 0.
Reading the same connection string as the work it guards is the whole point.

Prints nothing on failure, which `daily-update.bat` reports as "cannot read
database" rather than mistaking it for a market holiday.
"""

from __future__ import annotations

import os
import sys

import psycopg

QUERY = """
SELECT count(*) FROM public.bars_1m
WHERE (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
    = (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
"""


def main() -> int:
    dsn = os.environ.get("PG_DSN")
    if not dsn:
        print("PG_DSN chua duoc dat", file=sys.stderr)
        return 2
    try:
        with psycopg.connect(dsn, connect_timeout=15) as conn, conn.cursor() as cur:
            cur.execute(QUERY)
            print(cur.fetchone()[0])
    except Exception as exc:  # noqa: BLE001 - the caller only needs "no answer"
        print(f"khong doc duoc database: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
