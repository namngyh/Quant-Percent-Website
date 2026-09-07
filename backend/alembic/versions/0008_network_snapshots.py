"""Publish DynamicGraph's network through the database, not through git.

Revision ID: 0008
Revises: 0007

The relationship map and the ranking table reached the site as two JSON files
copied into `frontend/public/research/` and committed. The model runs every
trading session, but the page could only change when someone deployed, so it
sat on a 6 August snapshot for a month while the model kept producing newer
ones — and nothing on the page said which it was showing.

MSDP and RARF-FHE already publish through `quant`, and the website reads them
the same day they run. This gives DynamicGraph the same route.

`quant.stock_rankings` was not reused. It expects a regime and an up-probability
per ticker; DynamicGraph produces network centrality and per-ticker risk
measures, which are different quantities, and mapping one onto the other would
invent data. This table stores what the model actually computes.

Nodes and edges live in JSONB because they are read as one whole graph and
never filtered by field — about thirty kilobytes for a thirty-stock basket.
"""

from alembic import op
from app.db import models  # noqa: F401  (registers the mappings)
from app.db.base import QUANT_SCHEMA, Base

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

TABLE = f"{QUANT_SCHEMA}.network_snapshots"

# One row per session; the view hands the site the newest one per index.
# Columns are listed explicitly, like every other api view, so a column added
# later cannot become public by accident.
VIEW_SQL = """
CREATE OR REPLACE VIEW api.v_network_latest AS
SELECT DISTINCT ON (index_name)
       index_name,
       as_of_date,
       generated_at,
       model_version,
       graph_layer,
       graph_window,
       node_count,
       stress_score,
       stress_label,
       stress_percentile,
       nodes,
       edges,
       communities
FROM quant.network_snapshots
ORDER BY index_name, as_of_date DESC;
"""


def upgrade() -> None:
    Base.metadata.create_all(
        op.get_bind(),
        tables=[Base.metadata.tables[TABLE]],
    )
    op.execute(VIEW_SQL)
    op.execute("GRANT SELECT ON api.v_network_latest TO qp_web")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS api.v_network_latest")
    Base.metadata.tables[TABLE].drop(op.get_bind(), checkfirst=True)
