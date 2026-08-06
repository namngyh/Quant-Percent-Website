"""Derive quote prev_close from the live minute feed.

Revision ID: 0003
Revises: 0002

The original api.v_quote took `price` from bars_1m but `prev_close` from
bars_1d. Only bars_1m is maintained by the ingestion service; bars_1d is
written exclusively by the manual `backfill.py` script. Whenever that script
had not been run for a few sessions the view compared a live price against a
days-old close, so `change` and `change_percent` were wrong on every page that
shows a quote.

Observed on 2026-08-04: VNINDEX reported +72.55 (+4.26%) because bars_1d
stopped at 2026-07-30 and prev_close resolved to the 2026-07-29 close of
1704.68. The correct figures against the 2026-08-03 close of 1762.84 were
+14.39 (+0.82%).

The rebuilt view builds its daily series from bars_1m first and only falls
back to bars_1d for recent days the minute feed does not cover, so price and
prev_close always come from the same continuously updated source. Both
branches stay windowed so the view does not scan full history per request.
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


# Days of daily closes to consider. Only the two most recent sessions per
# symbol are used; the window just has to outlast holidays and trading halts.
_WINDOW_DAYS = 45

NEW_VIEW = f"""
CREATE OR REPLACE VIEW api.v_quote AS
WITH last_minute AS (
    SELECT DISTINCT ON (symbol) symbol, ts, close, volume
    FROM bars_1m
    ORDER BY symbol, ts DESC
), minute_daily AS (
    -- Session close per trading day, in exchange local time, from the feed
    -- the ingestion service keeps current.
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
    SELECT c.symbol,
           c.trading_date,
           c.close,
           p.close AS prev_close
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
"""

OLD_VIEW = """
CREATE OR REPLACE VIEW api.v_quote AS
WITH daily AS (
    SELECT symbol,
           trading_date,
           close,
           lag(close) OVER (PARTITION BY symbol ORDER BY trading_date)
               AS prev_close,
           row_number() OVER (
               PARTITION BY symbol ORDER BY trading_date DESC
           ) AS rn
    FROM bars_1d
), last_daily AS (
    SELECT symbol, trading_date, close, prev_close
    FROM daily WHERE rn = 1
), last_minute AS (
    SELECT DISTINCT ON (symbol) symbol, ts, close, volume
    FROM bars_1m
    ORDER BY symbol, ts DESC
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
"""


def upgrade() -> None:
    op.execute(NEW_VIEW)


def downgrade() -> None:
    op.execute(OLD_VIEW)
