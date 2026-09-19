"""Articles: what the author role was granted for.

Revision ID: 0010
Revises: 0009

0007 gave accounts an author role and said the publishing feature would hang
from it. This is that feature: authors publish research articles, anyone can
read them, and confirmed members vote on them and leave short comments.

Four tables, all in `web` because this service writes them:

  articles          the article, with its vote and comment totals stored on
                    the row so the list can sort by them without counting
  article_votes     one row per member per article; no row means no vote
  article_comments  short comments, soft-deleted like the articles
  article_images    uploaded figures, as bytea

Images live in the database rather than on a volume because pg_dump is the
only backup this deployment runs. A volume would need a second backup path,
and restoring articles without their charts would be a quiet kind of loss.

checkfirst=True for the reason spelled out in 0006: 0001 builds a brand-new
database with create_all from the live models, so these tables already exist
there by the time this runs. Existing databases do not have them. Both pass.

No GRANT — 0001's default privileges give qp_web read/write on every new
table in `web`.
"""

from alembic import op
from app.db import models  # noqa: F401  (registers the mappings)
from app.db.base import WEB_SCHEMA, Base

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

# Parents before children; downgrade walks it backwards.
TABLES = (
    f"{WEB_SCHEMA}.articles",
    f"{WEB_SCHEMA}.article_votes",
    f"{WEB_SCHEMA}.article_comments",
    f"{WEB_SCHEMA}.article_images",
)


def upgrade() -> None:
    Base.metadata.create_all(
        op.get_bind(),
        tables=[Base.metadata.tables[name] for name in TABLES],
        checkfirst=True,
    )


def downgrade() -> None:
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(op.get_bind(), checkfirst=True)
