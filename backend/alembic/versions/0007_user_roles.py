"""Give an account a role, and a way to ask for the author one.

Revision ID: 0007
Revises: 0006

Every account was equal apart from web.models.access, which only ever asked
"is this visitor a confirmed member". That was enough while the only thing
worth gating was model output. It is not enough now: somebody has to be able
to see who registered and who signed in, and somebody has to decide who may
publish an article.

Three roles, on the row rather than in a join table:

  user    the default, and what every existing account becomes
  author  may publish articles once an admin approves. The publishing feature
          does not exist yet — this is the hook it will hang from
  admin   manages the rest

The request to become an author is two more columns rather than a
role_requests table, matching how this schema already stores email_verified_at
and last_login_at: current state on the row, history in web.audit_log. NULL in
author_request_status means never asked; approval clears it and sets
role = 'author', so approved state has exactly one home and the two columns
cannot contradict each other.

status also picks up a CHECK it never had. It has only ever held 'active', but
the admin screen can now write 'disabled', and get_current_user_optional
already treats anything but 'active' as signed out — so a typo there would
silently lock somebody out rather than fail loudly.

IF NOT EXISTS on the columns, and a guarded DO block for the constraints, for
the reason spelled out in 0006: migration 0001 builds the schema with
Base.metadata.create_all from the live models, so a brand-new database already
has all of this by the time this migration runs. Existing databases do not.
Both must pass.

No GRANT is needed — 0001 grants table-level rights on every web table to
qp_web, and in Postgres that covers columns added later.
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


CONSTRAINTS = (
    ("ck_users_role_valid", "role IN ('user', 'author', 'admin')"),
    ("ck_users_status_valid", "status IN ('active', 'disabled')"),
    (
        "ck_users_author_request_status_valid",
        "author_request_status IN ('pending', 'rejected')",
    ),
)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE web.users "
        "ADD COLUMN IF NOT EXISTS role varchar(20) NOT NULL DEFAULT 'user', "
        "ADD COLUMN IF NOT EXISTS author_request_status varchar(20), "
        "ADD COLUMN IF NOT EXISTS author_request_at timestamptz"
    )
    for name, check in CONSTRAINTS:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = '{name}'
                ) THEN
                    ALTER TABLE web.users ADD CONSTRAINT {name} CHECK ({check});
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    for name, _ in CONSTRAINTS:
        op.execute(f"ALTER TABLE web.users DROP CONSTRAINT IF EXISTS {name}")
    op.execute(
        "ALTER TABLE web.users "
        "DROP COLUMN IF EXISTS author_request_at, "
        "DROP COLUMN IF EXISTS author_request_status, "
        "DROP COLUMN IF EXISTS role"
    )
