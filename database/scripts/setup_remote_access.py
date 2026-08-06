"""Create a read-only database role for remote access.

Remote access is enabled by adding a restricted account, not by exposing the
existing one. `quant` owns every schema and can drop the lot; it is the account
the ingestion and the migrations run as, and its password is a development
placeholder. Handing that out to a laptop or a BI tool means handing out the
ability to delete 26 years of price history.

The role created here can read the `api` schema — the same twelve vetted views
the website is allowed to read — and nothing else. It cannot write, cannot see
`web.users`, and cannot reach the raw tables.

    python database/scripts/setup_remote_access.py --password '...'
    python database/scripts/setup_remote_access.py --password '...' --dry-run
    python database/scripts/setup_remote_access.py --revoke

The password is passed in, never generated here and never written to a file
this script controls: it belongs in `D:\\Database - QuantPercent\\.env`, which
is gitignored.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

import psycopg
from psycopg import sql

# Scripts here run under several different virtualenvs, so the shared
# helper is imported by path rather than as a package.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _db import dsn_from_env  # noqa: E402

DEFAULT_DSN = None  # resolved lazily by dsn_from_env()
ROLE = "qp_remote"


def grant(cur, password: str) -> None:
    cur.execute(
        "SELECT 1 FROM pg_roles WHERE rolname = %s",
        (ROLE,),
    )
    exists = cur.fetchone() is not None

    if exists:
        # CREATE/ALTER ROLE will not take a bound parameter for the
        # password, so it is escaped as a literal by psycopg rather than
        # interpolated by hand.
        cur.execute(
            sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                sql.Identifier(ROLE), sql.Literal(password)
            )
        )
        print(f"role {ROLE}: password rotated")
    else:
        cur.execute(
            sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD {}").format(
                sql.Identifier(ROLE), sql.Literal(password)
            )
        )
        print(f"role {ROLE}: created")

    # Explicitly deny everything first, then grant back only the api schema.
    cur.execute(
        sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(
            sql.Identifier("market"), sql.Identifier(ROLE)
        )
    )
    cur.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
            sql.Identifier("market"), sql.Identifier(ROLE)
        )
    )
    for schema in ("public", "web", "quant"):
        cur.execute(
            sql.SQL("REVOKE ALL ON SCHEMA {} FROM {}").format(
                sql.Identifier(schema), sql.Identifier(ROLE)
            )
        )

    cur.execute(
        sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
            sql.Identifier("api"), sql.Identifier(ROLE)
        )
    )
    cur.execute(
        sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(
            sql.Identifier("api"), sql.Identifier(ROLE)
        )
    )
    # Views added later are covered without rerunning this script.
    cur.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT SELECT ON TABLES TO {}"
        ).format(sql.Identifier("api"), sql.Identifier(ROLE))
    )

    # A runaway query from a remote client should not stall ingestion.
    cur.execute(
        sql.SQL("ALTER ROLE {} SET statement_timeout = '60s'").format(
            sql.Identifier(ROLE)
        )
    )
    cur.execute(
        sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '60s'").format(
            sql.Identifier(ROLE)
        )
    )
    print(f"role {ROLE}: read-only on schema api, 60s statement timeout")


def revoke(cur) -> None:
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (ROLE,))
    if cur.fetchone() is None:
        print(f"role {ROLE}: not present, nothing to do")
        return
    cur.execute(
        sql.SQL("ALTER ROLE {} WITH NOLOGIN").format(sql.Identifier(ROLE))
    )
    print(f"role {ROLE}: login disabled")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=None)
    parser.add_argument("--password", help=f"password for {ROLE}")
    parser.add_argument(
        "--revoke", action="store_true", help=f"disable login for {ROLE}"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Roll back instead of committing"
    )
    args = parser.parse_args()

    if not args.revoke and not args.password:
        parser.error("--password is required unless --revoke is given")
    if args.password and len(args.password) < 20:
        parser.error("use a password of at least 20 characters")

    with psycopg.connect(dsn_from_env(args.dsn)) as conn:
        with conn.cursor() as cur:
            if args.revoke:
                revoke(cur)
            else:
                grant(cur, args.password)

            cur.execute(
                """
                SELECT table_schema, count(*)
                FROM information_schema.table_privileges
                WHERE grantee = %s AND privilege_type = 'SELECT'
                GROUP BY table_schema ORDER BY table_schema
                """,
                (ROLE,),
            )
            rows = cur.fetchall()

        if args.dry_run:
            conn.rollback()
            print("dry run: rolled back")
        else:
            conn.commit()
            print("committed")

    print("readable objects by schema:")
    for schema, count in rows:
        print(f"  {schema}: {count}")


if __name__ == "__main__":
    main()
