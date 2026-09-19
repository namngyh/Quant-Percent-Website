"""Stop the quote view scanning every minute bar ever ingested

Revision ID: 0009
Revises: 0008

/api/v1/market/overview and /api/v1/market/{symbol}/quote have been returning
500 after 30.7 seconds — the statement timeout — on every call. The pages that
use them render, so nothing looked broken; their market panels were simply
empty.

api.v_quote has three CTEs over bars_1m. Two of them already bound the scan to
45 days. `last_minute` does not:

    SELECT DISTINCT ON (symbol) symbol, ts, close, volume
    FROM bars_1m ORDER BY symbol, ts DESC

That sorts the whole table — 2.4 million rows and growing — to return one row
per symbol. It is the only unbounded scan left in the view, and it is why the
cost rises with every session ingested rather than staying flat.

This machine has enough memory to sort it in 268 ms; the production database
does not, so it spills to disk and crosses the timeout. Measured here, adding
the same 45-day bound the sibling CTEs already use:

    unbounded   35 symbols   268.3 ms
    bounded     35 symbols    40.4 ms

and the two return the same 35 symbols, with none dropped. A symbol whose last
minute bar is older than 45 days is not a live quote anyway: COALESCE already
falls back to the daily close for it, which is what the bound now makes happen
explicitly.

The rest of the view is untouched. An earlier attempt to rewrite it around
LATERAL joins was both slower and wrong — it discarded the point of revision
0003, which derives prev_close from the minute feed rather than from the raw
daily bar.
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

BOUNDED = """CREATE OR REPLACE VIEW api.v_quote AS
WITH last_minute AS (
         SELECT DISTINCT ON (bars_1m.symbol) bars_1m.symbol,
            bars_1m.ts,
            bars_1m.close,
            bars_1m.volume
           FROM bars_1m
          WHERE bars_1m.ts >= (now() - '45 days'::interval)
          ORDER BY bars_1m.symbol, bars_1m.ts DESC
        ), minute_daily AS (
         SELECT bars_1m.symbol,
            (bars_1m.ts AT TIME ZONE 'Asia/Ho_Chi_Minh'::text)::date AS trading_date,
            (array_agg(bars_1m.close ORDER BY bars_1m.ts DESC))[1] AS close
           FROM bars_1m
          WHERE bars_1m.ts >= (now() - '45 days'::interval)
          GROUP BY bars_1m.symbol, ((bars_1m.ts AT TIME ZONE 'Asia/Ho_Chi_Minh'::text)::date)
        ), daily_union AS (
         SELECT minute_daily.symbol,
            minute_daily.trading_date,
            minute_daily.close
           FROM minute_daily
        UNION ALL
         SELECT d_1.symbol,
            d_1.trading_date,
            d_1.close
           FROM bars_1d d_1
          WHERE d_1.trading_date >= (CURRENT_DATE - 45) AND NOT (EXISTS ( SELECT 1
                   FROM minute_daily m_1
                  WHERE m_1.symbol = d_1.symbol AND m_1.trading_date = d_1.trading_date))
        ), ranked AS (
         SELECT daily_union.symbol,
            daily_union.trading_date,
            daily_union.close,
            row_number() OVER (PARTITION BY daily_union.symbol ORDER BY daily_union.trading_date DESC) AS rn
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
            WHEN d.prev_close > 0::numeric THEN round((COALESCE(m.close, d.close) - d.prev_close) / d.prev_close * 100::numeric, 2)
            ELSE 0::numeric
        END AS change_percent,
    COALESCE(m.volume, 0::bigint) AS volume,
    s.currency,
    COALESCE(m.ts, ((d.trading_date + '15:00:00'::time without time zone) AT TIME ZONE 'Asia/Ho_Chi_Minh'::text)) AS data_as_of
   FROM web.symbols s
     LEFT JOIN last_daily d ON d.symbol = s.feed_symbol::text
     LEFT JOIN last_minute m ON m.symbol = s.feed_symbol::text
  WHERE s.is_public
"""

UNBOUNDED = """CREATE OR REPLACE VIEW api.v_quote AS
WITH last_minute AS (
         SELECT DISTINCT ON (bars_1m.symbol) bars_1m.symbol,
            bars_1m.ts,
            bars_1m.close,
            bars_1m.volume
           FROM bars_1m
          ORDER BY bars_1m.symbol, bars_1m.ts DESC
        ), minute_daily AS (
         SELECT bars_1m.symbol,
            (bars_1m.ts AT TIME ZONE 'Asia/Ho_Chi_Minh'::text)::date AS trading_date,
            (array_agg(bars_1m.close ORDER BY bars_1m.ts DESC))[1] AS close
           FROM bars_1m
          WHERE bars_1m.ts >= (now() - '45 days'::interval)
          GROUP BY bars_1m.symbol, ((bars_1m.ts AT TIME ZONE 'Asia/Ho_Chi_Minh'::text)::date)
        ), daily_union AS (
         SELECT minute_daily.symbol,
            minute_daily.trading_date,
            minute_daily.close
           FROM minute_daily
        UNION ALL
         SELECT d_1.symbol,
            d_1.trading_date,
            d_1.close
           FROM bars_1d d_1
          WHERE d_1.trading_date >= (CURRENT_DATE - 45) AND NOT (EXISTS ( SELECT 1
                   FROM minute_daily m_1
                  WHERE m_1.symbol = d_1.symbol AND m_1.trading_date = d_1.trading_date))
        ), ranked AS (
         SELECT daily_union.symbol,
            daily_union.trading_date,
            daily_union.close,
            row_number() OVER (PARTITION BY daily_union.symbol ORDER BY daily_union.trading_date DESC) AS rn
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
            WHEN d.prev_close > 0::numeric THEN round((COALESCE(m.close, d.close) - d.prev_close) / d.prev_close * 100::numeric, 2)
            ELSE 0::numeric
        END AS change_percent,
    COALESCE(m.volume, 0::bigint) AS volume,
    s.currency,
    COALESCE(m.ts, ((d.trading_date + '15:00:00'::time without time zone) AT TIME ZONE 'Asia/Ho_Chi_Minh'::text)) AS data_as_of
   FROM web.symbols s
     LEFT JOIN last_daily d ON d.symbol = s.feed_symbol::text
     LEFT JOIN last_minute m ON m.symbol = s.feed_symbol::text
  WHERE s.is_public
"""


def upgrade() -> None:
    op.execute(BOUNDED)


def downgrade() -> None:
    op.execute(UNBOUNDED)
