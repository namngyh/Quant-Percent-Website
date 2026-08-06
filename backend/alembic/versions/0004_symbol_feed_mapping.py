"""Map published symbols onto their ingestion feed names.

Revision ID: 0004
Revises: 0003

The website publishes the VN30 index as "VN30" (URLs, market filters, the
futures tab's spot quote), but DataPro delivers that series as "VN30INDEX".
Nothing translated between the two, so /api/v1/market/VN30/quote and
/history returned 404 and empty results against a live database.

web.symbols gains `feed_symbol`, the name the row carries in the ingestion
tables. It defaults to `symbol`, so every other ticker is unaffected. The
market views translate feed names to published names, and pass through feed
symbols that have no web.symbols row so collected-but-unpublished tickers
keep behaving as before.
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_WINDOW_DAYS = 45


def upgrade() -> None:
    op.execute(
        "ALTER TABLE web.symbols "
        "ADD COLUMN IF NOT EXISTS feed_symbol varchar(20)"
    )
    op.execute("UPDATE web.symbols SET feed_symbol = symbol "
               "WHERE feed_symbol IS NULL")
    op.execute("UPDATE web.symbols SET feed_symbol = 'VN30INDEX' "
               "WHERE symbol = 'VN30'")
    op.execute("ALTER TABLE web.symbols ALTER COLUMN feed_symbol SET NOT NULL")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_symbols_feed_symbol "
        "ON web.symbols (feed_symbol)"
    )

    op.execute(f"""
CREATE OR REPLACE VIEW api.v_quote AS
WITH last_minute AS (
    SELECT DISTINCT ON (symbol) symbol, ts, close, volume
    FROM bars_1m
    ORDER BY symbol, ts DESC
), minute_daily AS (
    SELECT symbol,
           (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS trading_date,
           (array_agg(close ORDER BY ts DESC))[1] AS close
    FROM bars_1m
    WHERE ts >= now() - interval '{_WINDOW_DAYS} days'
    GROUP BY 1, 2
), daily_union AS (
    SELECT symbol, trading_date, close FROM minute_daily
    UNION ALL
    SELECT d.symbol, d.trading_date, d.close
    FROM bars_1d d
    WHERE d.trading_date >= (current_date - {_WINDOW_DAYS})
      AND NOT EXISTS (
          SELECT 1 FROM minute_daily m
          WHERE m.symbol = d.symbol AND m.trading_date = d.trading_date
      )
), ranked AS (
    SELECT symbol, trading_date, close,
           row_number() OVER (
               PARTITION BY symbol ORDER BY trading_date DESC
           ) AS rn
    FROM daily_union
), last_daily AS (
    SELECT c.symbol, c.trading_date, c.close, p.close AS prev_close
    FROM ranked c
    LEFT JOIN ranked p ON p.symbol = c.symbol AND p.rn = 2
    WHERE c.rn = 1
)
SELECT s.symbol,
       s.name,
       COALESCE(m.close, d.close) AS price,
       COALESCE(m.close, d.close) - d.prev_close AS change,
       CASE
           WHEN d.prev_close > 0::numeric
           THEN round(
               (COALESCE(m.close, d.close) - d.prev_close)
               / d.prev_close * 100::numeric, 2)
           ELSE 0::numeric
       END AS change_percent,
       COALESCE(m.volume, 0::bigint) AS volume,
       s.currency,
       COALESCE(
           m.ts,
           ((d.trading_date + '15:00:00'::time)
               AT TIME ZONE 'Asia/Ho_Chi_Minh'::text)
       ) AS data_as_of
FROM web.symbols s
    LEFT JOIN last_daily d ON d.symbol = s.feed_symbol::text
    LEFT JOIN last_minute m ON m.symbol = s.feed_symbol::text
WHERE s.is_public;
""")

    op.execute("""
CREATE OR REPLACE VIEW api.v_history_1d AS
SELECT COALESCE(s.symbol::text, b.symbol) AS symbol,
       b.trading_date, b.open, b.high, b.low, b.close, b.volume
FROM bars_1d b
    LEFT JOIN web.symbols s
        ON s.feed_symbol::text = b.symbol AND s.is_public;
""")

    op.execute("""
CREATE OR REPLACE VIEW api.v_history_1m AS
SELECT COALESCE(s.symbol::text, b.symbol) AS symbol,
       b.ts, b.open, b.high, b.low, b.close, b.volume
FROM bars_1m b
    LEFT JOIN web.symbols s
        ON s.feed_symbol::text = b.symbol AND s.is_public
WHERE b.is_final;
""")

    op.execute("""
CREATE OR REPLACE VIEW api.v_data_freshness AS
SELECT COALESCE(s.symbol::text, b.symbol) AS symbol,
       max(b.ts) AS data_as_of
FROM bars_1m b
    LEFT JOIN web.symbols s
        ON s.feed_symbol::text = b.symbol AND s.is_public
GROUP BY 1;
""")


def downgrade() -> None:
    op.execute("""
CREATE OR REPLACE VIEW api.v_data_freshness AS
SELECT symbol, max(ts) AS data_as_of FROM bars_1m GROUP BY symbol;
""")
    op.execute("""
CREATE OR REPLACE VIEW api.v_history_1m AS
SELECT symbol, ts, open, high, low, close, volume
FROM bars_1m WHERE is_final;
""")
    op.execute("""
CREATE OR REPLACE VIEW api.v_history_1d AS
SELECT symbol, trading_date, open, high, low, close, volume FROM bars_1d;
""")
    # api.v_quote reverts to the 0003 definition, which joins on symbol.
    op.execute(f"""
CREATE OR REPLACE VIEW api.v_quote AS
WITH last_minute AS (
    SELECT DISTINCT ON (symbol) symbol, ts, close, volume
    FROM bars_1m
    ORDER BY symbol, ts DESC
), minute_daily AS (
    SELECT symbol,
           (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS trading_date,
           (array_agg(close ORDER BY ts DESC))[1] AS close
    FROM bars_1m
    WHERE ts >= now() - interval '{_WINDOW_DAYS} days'
    GROUP BY 1, 2
), daily_union AS (
    SELECT symbol, trading_date, close FROM minute_daily
    UNION ALL
    SELECT d.symbol, d.trading_date, d.close
    FROM bars_1d d
    WHERE d.trading_date >= (current_date - {_WINDOW_DAYS})
      AND NOT EXISTS (
          SELECT 1 FROM minute_daily m
          WHERE m.symbol = d.symbol AND m.trading_date = d.trading_date
      )
), ranked AS (
    SELECT symbol, trading_date, close,
           row_number() OVER (
               PARTITION BY symbol ORDER BY trading_date DESC
           ) AS rn
    FROM daily_union
), last_daily AS (
    SELECT c.symbol, c.trading_date, c.close, p.close AS prev_close
    FROM ranked c
    LEFT JOIN ranked p ON p.symbol = c.symbol AND p.rn = 2
    WHERE c.rn = 1
)
SELECT s.symbol,
       s.name,
       COALESCE(m.close, d.close) AS price,
       COALESCE(m.close, d.close) - d.prev_close AS change,
       CASE
           WHEN d.prev_close > 0::numeric
           THEN round(
               (COALESCE(m.close, d.close) - d.prev_close)
               / d.prev_close * 100::numeric, 2)
           ELSE 0::numeric
       END AS change_percent,
       COALESCE(m.volume, 0::bigint) AS volume,
       s.currency,
       COALESCE(
           m.ts,
           ((d.trading_date + '15:00:00'::time)
               AT TIME ZONE 'Asia/Ho_Chi_Minh'::text)
       ) AS data_as_of
FROM web.symbols s
    LEFT JOIN last_daily d ON d.symbol = s.symbol::text
    LEFT JOIN last_minute m ON m.symbol = s.symbol::text
WHERE s.is_public;
""")
    op.execute("DROP INDEX IF EXISTS web.ix_symbols_feed_symbol")
    op.execute("ALTER TABLE web.symbols DROP COLUMN IF EXISTS feed_symbol")
