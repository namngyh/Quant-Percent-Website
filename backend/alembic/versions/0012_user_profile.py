"""A public face for a member: a nickname and an avatar.

Revision ID: 0012
Revises: 0011

Articles and comments printed web.users.full_name — the legal-looking name a
member typed at registration, shown to everyone. A member can now choose a
nickname that is shown instead, and a portrait hosted on Cloudinary. Both are
optional; with no nickname the full name is still what appears.

The nickname is unique regardless of case, so two members cannot look the
same in a comment thread. A unique index on lower(nickname) rather than a
constraint on the column, because "Minh" and "minh" must collide. NULLs do
not collide in Postgres, which is what lets every member without one coexist.

avatar_url is text, not varchar: Cloudinary delivery URLs carry a transform
segment and a version, and nothing is gained by guessing their longest form.

IF NOT EXISTS for the reason 0006 gives: 0001 builds the schema from the live
models, so a fresh database already has these by the time this runs.
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

# One statement per execute: asyncpg refuses several commands in one.


def upgrade() -> None:
    op.execute(
        "ALTER TABLE web.users ADD COLUMN IF NOT EXISTS nickname varchar(40)"
    )
    op.execute("ALTER TABLE web.users ADD COLUMN IF NOT EXISTS avatar_url text")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_nickname_lower "
        "ON web.users (lower(nickname))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS web.uq_users_nickname_lower")
    op.execute("ALTER TABLE web.users DROP COLUMN IF EXISTS avatar_url")
    op.execute("ALTER TABLE web.users DROP COLUMN IF EXISTS nickname")
