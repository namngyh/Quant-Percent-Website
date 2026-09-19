"""Give a member somewhere to keep their phone number.

Revision ID: 0006
Revises: 0005

The account page lets a member edit their own name and phone number, but
web.users only ever stored a name. A phone existed solely on web.contacts,
filled in by whoever submitted the contact form — which is a record of one
message, not of a person, and is never read back when that person signs in.

Nullable on purpose: a phone number is not needed to hold an account, and
requiring one would lock out every member who registered before this column
existed. varchar(40) matches web.contacts.phone so both tables agree on what
a phone number is; the API validates length and little else, because a
number that is merely unusual is not a number that is wrong.

IF NOT EXISTS is required, not decorative. Migration 0001 builds the schema
with Base.metadata.create_all from the live SQLAlchemy models, so the moment
User gains this attribute a brand-new database already has the column by the
time this migration runs. Existing databases do not. Both must pass.

No GRANT is needed: 0001 grants SELECT/INSERT/UPDATE/DELETE on ALL TABLES in
schema web to qp_web, and a table-level privilege in Postgres covers columns
added later.
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE web.users ADD COLUMN IF NOT EXISTS phone varchar(40)")


def downgrade() -> None:
    op.execute("ALTER TABLE web.users DROP COLUMN IF EXISTS phone")
