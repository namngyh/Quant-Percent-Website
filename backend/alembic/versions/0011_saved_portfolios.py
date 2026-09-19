"""Saved portfolios for signed-in members.

Revision ID: 0011
Revises: 0010

Quant Portfolio never stored anything: a reader typed their holdings, got
the analysis, and the request was discarded. That is still the behaviour for
anyone not signed in. A member can now press Save, and only then is the
input kept — the holdings, cash, loan and horizon, as one JSON document per
named portfolio. No analysis is stored; it is recomputed on every open
because a stored result would go stale the next session.

Rows are cascaded with the account. Ten portfolios per member is enforced in
the endpoint, not here, so the limit can change without a migration.

Written as IF NOT EXISTS: the table is also created by hand on development
databases that run ahead of the migration chain, and this must not fail on
them.
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

CREATE = """
CREATE TABLE IF NOT EXISTS web.portfolios (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    name varchar(80) NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_portfolios PRIMARY KEY (id),
    CONSTRAINT fk_portfolios_user_id_users
        FOREIGN KEY (user_id) REFERENCES web.users (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_portfolios_user
    ON web.portfolios (user_id, updated_at);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'qp_web') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON web.portfolios TO qp_web;
    END IF;
END $$;
"""


def upgrade() -> None:
    op.execute(CREATE)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS web.portfolios")
