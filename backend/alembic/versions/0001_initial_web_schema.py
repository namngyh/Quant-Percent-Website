"""Initial web/quant schemas, vetted api views and grants

Creates only the schemas this service owns. The ingestion pipeline keeps
full ownership of `public` (ticks, bars_1m, bars_1d, gap_log) — nothing
here alters or drops those tables, so this migration is safe to run on a
database that already holds live market data.

Revision ID: 0001
Revises:
"""
from __future__ import annotations

from alembic import op
from app.db import models  # noqa: F401  (registers the mappings)
from app.db.base import QUANT_SCHEMA, WEB_SCHEMA, Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

MANAGED = (WEB_SCHEMA, QUANT_SCHEMA)

# The API role reads market data only through these views. Each one lists
# its columns explicitly so a future column on an ingestion table cannot
# silently become public (spec §18 forbidden fields, §21 vetted views).
VIEWS_SQL = """
CREATE OR REPLACE VIEW api.v_quote AS
WITH daily AS (
    SELECT symbol,
           trading_date,
           close,
           lag(close) OVER (PARTITION BY symbol ORDER BY trading_date) AS prev_close,
           row_number() OVER (PARTITION BY symbol ORDER BY trading_date DESC) AS rn
    FROM public.bars_1d
),
last_daily AS (
    SELECT symbol, trading_date, close, prev_close FROM daily WHERE rn = 1
),
last_minute AS (
    SELECT DISTINCT ON (symbol) symbol, ts, close, volume
    FROM public.bars_1m
    ORDER BY symbol, ts DESC
)
SELECT s.symbol,
       s.name,
       COALESCE(m.close, d.close)                             AS price,
       COALESCE(m.close, d.close) - d.prev_close              AS change,
       CASE WHEN d.prev_close > 0
            THEN round(((COALESCE(m.close, d.close) - d.prev_close)
                        / d.prev_close * 100)::numeric, 2)
            ELSE 0 END                                        AS change_percent,
       COALESCE(m.volume, 0)                                  AS volume,
       s.currency,
       COALESCE(m.ts, (d.trading_date + time '15:00') AT TIME ZONE 'Asia/Ho_Chi_Minh')
                                                              AS data_as_of
FROM web.symbols s
LEFT JOIN last_daily  d ON d.symbol = s.symbol
LEFT JOIN last_minute m ON m.symbol = s.symbol
WHERE s.is_public;

CREATE OR REPLACE VIEW api.v_history_1d AS
SELECT symbol, trading_date, open, high, low, close, volume
FROM public.bars_1d;

CREATE OR REPLACE VIEW api.v_history_1m AS
SELECT symbol, ts, open, high, low, close, volume
FROM public.bars_1m
WHERE is_final;

CREATE OR REPLACE VIEW api.v_data_freshness AS
SELECT symbol, max(ts) AS data_as_of
FROM public.bars_1m
GROUP BY symbol;

CREATE OR REPLACE VIEW api.v_ingestion_gaps AS
SELECT id, symbol, disconnect_ts, reconnect_ts
FROM public.gap_log;

CREATE OR REPLACE VIEW api.v_market_state AS
SELECT ts, regime, regime_probability, probability_up, probability_down,
       volatility, risk_state, risk_score, model_consensus, public_signal,
       generated_at
FROM quant.market_state
WHERE scope = 'market';

CREATE OR REPLACE VIEW api.v_risk_metrics AS
SELECT ts, current_drawdown, rolling_drawdown_60d, volatility, var_95, es_95,
       downside_probability, risk_state, mc_paths, generated_at
FROM quant.risk_metrics
WHERE scope = 'market';

CREATE OR REPLACE VIEW api.v_risk_distribution AS
SELECT ts, bucket, probability
FROM quant.risk_mc_distribution
WHERE scope = 'market';

CREATE OR REPLACE VIEW api.v_risk_scenarios AS
SELECT ts, scenario_id, impact_percent
FROM quant.risk_scenarios
WHERE scope = 'market';

CREATE OR REPLACE VIEW api.v_vn30_constituents AS
WITH members AS (
    SELECT member_symbol
    FROM web.index_constituents
    WHERE index_symbol = 'VN30'
      AND valid_from <= CURRENT_DATE
      AND (valid_to IS NULL OR valid_to >= CURRENT_DATE)
),
latest_rank_ts AS (
    SELECT max(ts) AS ts FROM quant.stock_rankings
),
daily AS (
    SELECT symbol,
           close,
           lag(close) OVER (PARTITION BY symbol ORDER BY trading_date) AS prev_close,
           row_number() OVER (PARTITION BY symbol ORDER BY trading_date DESC) AS rn
    FROM public.bars_1d
)
SELECT r.ticker,
       d.close                                        AS price,
       CASE WHEN d.prev_close > 0
            THEN round(((d.close - d.prev_close) / d.prev_close * 100)::numeric, 2)
            ELSE 0 END                                AS change_percent,
       r.regime,
       r.probability_up,
       r.volatility,
       r.risk_state,
       r.rank,
       r.ts
FROM quant.stock_rankings r
JOIN latest_rank_ts l ON r.ts = l.ts
JOIN members m ON m.member_symbol = r.ticker
LEFT JOIN daily d ON d.symbol = r.ticker AND d.rn = 1;

CREATE OR REPLACE VIEW api.v_model_forecast_latest AS
SELECT DISTINCT ON (model_id, symbol, horizon)
       model_id, symbol, horizon, model_version, timeframe, horizon_unit,
       data_as_of, generated_at, forecast_value, forecast_return,
       probability_up, probability_down, regime, regime_probability,
       volatility, interval_level, interval_lower, interval_upper,
       risk_score, risk_state, status
FROM quant.model_forecasts
ORDER BY model_id, symbol, horizon, data_as_of DESC;

CREATE OR REPLACE VIEW api.v_forecast_history AS
SELECT model_id, symbol, horizon, data_as_of, generated_at, forecast_value,
       interval_level, interval_lower, interval_upper, actual_value
FROM quant.model_forecasts;
"""

DROP_VIEWS_SQL = """
DROP VIEW IF EXISTS api.v_forecast_history;
DROP VIEW IF EXISTS api.v_model_forecast_latest;
DROP VIEW IF EXISTS api.v_vn30_constituents;
DROP VIEW IF EXISTS api.v_risk_scenarios;
DROP VIEW IF EXISTS api.v_risk_distribution;
DROP VIEW IF EXISTS api.v_risk_metrics;
DROP VIEW IF EXISTS api.v_market_state;
DROP VIEW IF EXISTS api.v_ingestion_gaps;
DROP VIEW IF EXISTS api.v_data_freshness;
DROP VIEW IF EXISTS api.v_history_1m;
DROP VIEW IF EXISTS api.v_history_1d;
DROP VIEW IF EXISTS api.v_quote;
"""

# Applied only when the role already exists, so the migration works on a
# developer database where nobody created it. See scripts/create_role.sql.
GRANTS_SQL = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'qp_web') THEN
        GRANT USAGE ON SCHEMA api, web, quant TO qp_web;
        GRANT SELECT ON ALL TABLES IN SCHEMA api TO qp_web;
        GRANT SELECT ON ALL TABLES IN SCHEMA quant TO qp_web;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA web TO qp_web;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA web TO qp_web;
        ALTER DEFAULT PRIVILEGES IN SCHEMA api GRANT SELECT ON TABLES TO qp_web;
        ALTER DEFAULT PRIVILEGES IN SCHEMA quant GRANT SELECT ON TABLES TO qp_web;
        ALTER DEFAULT PRIVILEGES IN SCHEMA web
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO qp_web;
        ALTER DEFAULT PRIVILEGES IN SCHEMA web
            GRANT USAGE, SELECT ON SEQUENCES TO qp_web;
        -- Deliberately no rights on `public`: the API must reach market
        -- data through the vetted api.* views only.
        REVOKE ALL ON SCHEMA public FROM qp_web;
    END IF;
END $$;
"""

# model_forecasts grows per model/symbol/horizon/day — worth partitioning
# by time. Skipped silently when the extension is absent (plain Postgres).
TIMESCALE_SQL = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable('quant.model_forecasts', 'data_as_of',
                                  if_not_exists => TRUE, migrate_data => TRUE);
    END IF;
END $$;
"""

def _exec_many(sql: str) -> None:
    parts, buf, in_dollar = [], [], False
    for line in sql.splitlines():
        if line.count("$$") % 2 == 1:
            in_dollar = not in_dollar
        buf.append(line)
        if not in_dollar and line.rstrip().endswith(";"):
            parts.append("\n".join(buf))
            buf = []
    if buf:
        parts.append("\n".join(buf))
    for part in parts:
        if part.strip():
            op.execute(part)


def upgrade() -> None:
    conn = op.get_bind()
    for schema in (*MANAGED, "api"):
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')

    # The initial revision builds straight from the mappings so the schema
    # cannot drift from app/db/models.py. Later revisions are ordinary
    # autogenerated diffs.
    tables = [
        t for t in Base.metadata.sorted_tables if t.schema in MANAGED
    ]
    Base.metadata.create_all(bind=conn, tables=tables, checkfirst=True)

    _exec_many(TIMESCALE_SQL)
    _exec_many(VIEWS_SQL)
    _exec_many(GRANTS_SQL)


def downgrade() -> None:
    conn = op.get_bind()
    _exec_many(DROP_VIEWS_SQL)
    tables = [t for t in Base.metadata.sorted_tables if t.schema in MANAGED]
    Base.metadata.drop_all(bind=conn, tables=tables, checkfirst=True)
    op.execute('DROP SCHEMA IF EXISTS "api" CASCADE')
    # `public` is never touched — it belongs to the ingestion pipeline.
