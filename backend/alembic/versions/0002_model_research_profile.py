"""Store published research evidence in the database.

Revision ID: 0002
Revises: 0001

The initial migration builds tables from current SQLAlchemy metadata.  The
IF NOT EXISTS clauses therefore support both existing databases (created by
the old 0001) and fresh databases (where current 0001 already sees columns).
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE web.models "
        "ADD COLUMN IF NOT EXISTS sparkline jsonb, "
        "ADD COLUMN IF NOT EXISTS sparkline_label jsonb, "
        "ADD COLUMN IF NOT EXISTS research_profile jsonb"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE web.models "
        "DROP COLUMN IF EXISTS research_profile, "
        "DROP COLUMN IF EXISTS sparkline_label, "
        "DROP COLUMN IF EXISTS sparkline"
    )
