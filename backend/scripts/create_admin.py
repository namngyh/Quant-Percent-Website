"""Create the first admin account, or promote an existing one.

    QP_ADMIN_PASSWORD='...' python -m scripts.create_admin \
        --email admin@quantpercent.com --create

On the server, inside the api service so it inherits DATABASE_URL:

    docker compose --env-file .env.production \
      -f compose.production.yml -f compose.override.yml \
      run --rm -e QP_ADMIN_PASSWORD api \
      python -m scripts.create_admin --email admin@quantpercent.com --create

The password comes from the environment and never from a command-line flag:
argv is visible to every other process on the box through `ps`, and it lands
in the shell history besides.

Idempotent, the same way scripts/create_role.sql is: run it twice and the
second run promotes rather than fails. Creating requires --create so a typo in
the address cannot quietly produce a second admin nobody knows about.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import User
from app.db.session import SessionLocal

MIN_PASSWORD = 12


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument(
        "--name", default="Administrator", help="Display name for a new account"
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="Create the account if it does not exist yet",
    )
    args = parser.parse_args()
    email = args.email.strip().lower()

    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))

        if user is None:
            if not args.create:
                print(
                    f"No account for {email}. Pass --create to make one.",
                    file=sys.stderr,
                )
                return 1

            password = os.environ.get("QP_ADMIN_PASSWORD", "")
            if len(password) < MIN_PASSWORD:
                print(
                    f"Set QP_ADMIN_PASSWORD to at least {MIN_PASSWORD} "
                    "characters before running. It is read from the "
                    "environment, never from a flag, because argv is public.",
                    file=sys.stderr,
                )
                return 2

            user = User(
                email=email,
                password_hash=hash_password(password),
                full_name=args.name,
                locale="vi",
                status="active",
                role="admin",
                # Stamped on purpose: this account has no real inbox to click a
                # link in, and members-only content is gated on verification.
                email_verified_at=datetime.now(UTC),
            )
            session.add(user)
            await session.commit()
            print(f"Created admin account {email}.")
            print("Sign in and change this password on first use.")
            return 0

        if user.role == "admin":
            print(f"{email} is already an admin. Nothing changed.")
            return 0

        was = user.role
        user.role = "admin"
        user.author_request_status = None
        user.updated_at = datetime.now(UTC)
        await session.commit()
        print(f"Promoted {email} from '{was}' to admin.")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
