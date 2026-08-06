"""Let a forecast omit the regime call and the risk grade.

Revision ID: 0005
Revises: 0004

quant.model_forecasts required regime, regime_probability, risk_score and
risk_state on every row. Only some models produce those. MSDP forecasts a
return distribution — quantiles, a calibrated interval and a volatility — and
makes no regime call at all, so publishing its output meant inventing one.

A made-up regime is indistinguishable from a real one on the model page, which
is the same failure already fixed in /api/v1/market/overview. Making the four
columns nullable lets a distributional model publish exactly what it computed
and nothing more; models that do call regimes keep filling them in.

The forecast itself stays required: value, return, both directional
probabilities, volatility and the interval are what makes a row a forecast.
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

COLUMNS = ("regime", "regime_probability", "risk_score", "risk_state")


def upgrade() -> None:
    for column in COLUMNS:
        op.execute(
            f"ALTER TABLE quant.model_forecasts ALTER COLUMN {column} DROP NOT NULL"
        )


def downgrade() -> None:
    # Rows written by a distributional model have no regime to restore, so
    # they would block the NOT NULL. Drop them rather than backfill a guess.
    op.execute(
        "DELETE FROM quant.model_forecasts "
        "WHERE regime IS NULL OR regime_probability IS NULL "
        "   OR risk_score IS NULL OR risk_state IS NULL"
    )
    for column in COLUMNS:
        op.execute(
            f"ALTER TABLE quant.model_forecasts ALTER COLUMN {column} SET NOT NULL"
        )
