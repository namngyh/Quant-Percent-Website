"""Keep the read views usable now that bars_1m holds the whole DataPro universe

Revision ID: 0010
Revises: 0009

bars_1m went from 35 symbols and 2.5 million rows to 2,055 symbols and 37.7
million, because the backfill now takes its universe from /api/symbols instead
of the ingestion watchlist. Two views that were comfortable at the old size
stopped being usable at the new one. Both regressions were reported by a
teammate reading through the qp_remote role, and both are measured below
against the production database.

**api.v_history_1m — 69.6s, past the 60s statement timeout, for one symbol.**

Revision 0004 renames one symbol for display, VN30INDEX to VN30, with a join:

    SELECT COALESCE(s.symbol::text, b.symbol) AS symbol, ...
    FROM bars_1m b LEFT JOIN web.symbols s ON s.feed_symbol::text = b.symbol

A caller's `WHERE symbol = 'FPT'` therefore lands on `COALESCE(...)`, not on
`b.symbol`. bars_1m is compressed with `segmentby = symbol`, and segment
pruning needs a bare equality on that column — an expression over it defeats
the pruning entirely, so the plan is a sequential scan of every chunk:

    Filter: (COALESCE((s.symbol)::text, b.symbol) = 'FPT'::text)
      ->  Parallel Append -> Seq Scan on <every chunk>

A CASE expression instead of the join does not help; it is still an expression
over the column. Measured on FPT:

    bare  WHERE symbol = 'FPT'                    2.3 s
    CASE  WHEN symbol='VN30INDEX' THEN 'VN30' ..  69.6 s

Splitting the rename into a UNION ALL restores it. Postgres pushes the caller's
predicate into both branches, where it becomes a bare equality in one and a
constant-false in the other, so the second branch is eliminated outright:

    FPT   2.2 s      VN30 (the renamed one)   2.4 s

The output is unchanged — same columns, same rows, same names. Exactly one
public symbol is renamed today, which is what makes the two-branch form
tractable; add a second mapping to web.symbols and this view will silently stop
applying it, so a mapping added later needs a revision here too.

**api.v_quote — 13.9s for 389 rows, was 1.9s.**

Revision 0009 bounded the CTEs to 45 days, which fixed an unbounded sort when
35 symbols lived in bars_1m. 45 days across 2,055 symbols is 4.5 million rows,
and the view discards four fifths of them: it ends at
`FROM web.symbols s ... WHERE s.is_public`, 389 symbols. The CTEs now also
restrict themselves to those symbols. Nothing is dropped that the final join
was not already dropping, so the result is identical:

    last_minute  CTE   4.9 s -> 0.9 s
    minute_daily CTE   2.7 s -> 2.0 s
    whole view        13.9 s -> 3.2 s

That is short of the original 1.9s. The remaining cost is minute_daily
aggregating 45 days of minute bars for 389 symbols; narrowing that CTE alone
would help, but the window is what lets prev_close survive a holiday, so it is
left as 0009 set it.
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


HISTORY_1M_SPLIT = """CREATE OR REPLACE VIEW api.v_history_1m AS
  SELECT b.symbol, b.ts, b.open, b.high, b.low, b.close, b.volume
  FROM bars_1m b
  WHERE b.is_final AND b.symbol <> 'VN30INDEX'
UNION ALL
  SELECT 'VN30'::text, b.ts, b.open, b.high, b.low, b.close, b.volume
  FROM bars_1m b
  WHERE b.is_final AND b.symbol = 'VN30INDEX'
"""

HISTORY_1M_JOIN = """CREATE OR REPLACE VIEW api.v_history_1m AS
SELECT COALESCE(s.symbol::text, b.symbol) AS symbol,
       b.ts, b.open, b.high, b.low, b.close, b.volume
FROM bars_1m b
  LEFT JOIN web.symbols s ON s.feed_symbol::text = b.symbol AND s.is_public
WHERE b.is_final
"""

QUOTE_PUBLIC_ONLY = """CREATE OR REPLACE VIEW api.v_quote AS
WITH pub AS (SELECT feed_symbol::text AS fs FROM web.symbols WHERE is_public),
last_minute AS (
  SELECT DISTINCT ON (b.symbol) b.symbol, b.ts, b.close, b.volume
  FROM bars_1m b
  WHERE b.ts >= now() - interval '45 days' AND b.symbol IN (SELECT fs FROM pub)
  ORDER BY b.symbol, b.ts DESC
),
minute_daily AS (
  SELECT b.symbol, (b.ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS trading_date,
         (array_agg(b.close ORDER BY b.ts DESC))[1] AS close
  FROM bars_1m b
  WHERE b.ts >= now() - interval '45 days' AND b.symbol IN (SELECT fs FROM pub)
  GROUP BY b.symbol, ((b.ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date)
),
daily_union AS (
  SELECT symbol, trading_date, close FROM minute_daily
  UNION ALL
  SELECT d.symbol, d.trading_date, d.close FROM bars_1d d
  WHERE d.trading_date >= CURRENT_DATE - 45 AND d.symbol IN (SELECT fs FROM pub)
    AND NOT EXISTS (SELECT 1 FROM minute_daily m
                    WHERE m.symbol = d.symbol AND m.trading_date = d.trading_date)
),
ranked AS (
  SELECT symbol, trading_date, close,
         row_number() OVER (PARTITION BY symbol ORDER BY trading_date DESC) AS rn
  FROM daily_union
),
last_daily AS (
  SELECT c.symbol, c.trading_date, c.close, p.close AS prev_close
  FROM ranked c LEFT JOIN ranked p ON p.symbol = c.symbol AND p.rn = 2
  WHERE c.rn = 1
)
SELECT s.symbol, s.name,
       COALESCE(m.close, d.close) AS price,
       COALESCE(m.close, d.close) - d.prev_close AS change,
       CASE WHEN d.prev_close > 0::numeric
            THEN round((COALESCE(m.close, d.close) - d.prev_close)
                       / d.prev_close * 100::numeric, 2)
            ELSE 0::numeric END AS change_percent,
       COALESCE(m.volume, 0::bigint) AS volume,
       s.currency,
       COALESCE(m.ts, ((d.trading_date + '15:00:00'::time)
                       AT TIME ZONE 'Asia/Ho_Chi_Minh')) AS data_as_of
FROM web.symbols s
  LEFT JOIN last_daily d ON d.symbol = s.feed_symbol::text
  LEFT JOIN last_minute m ON m.symbol = s.feed_symbol::text
WHERE s.is_public
"""

QUOTE_ALL_SYMBOLS = """CREATE OR REPLACE VIEW api.v_quote AS
WITH last_minute AS (
  SELECT DISTINCT ON (bars_1m.symbol) bars_1m.symbol, bars_1m.ts,
         bars_1m.close, bars_1m.volume
  FROM bars_1m
  WHERE bars_1m.ts >= (now() - '45 days'::interval)
  ORDER BY bars_1m.symbol, bars_1m.ts DESC
),
minute_daily AS (
  SELECT bars_1m.symbol,
         (bars_1m.ts AT TIME ZONE 'Asia/Ho_Chi_Minh'::text)::date AS trading_date,
         (array_agg(bars_1m.close ORDER BY bars_1m.ts DESC))[1] AS close
  FROM bars_1m
  WHERE bars_1m.ts >= (now() - '45 days'::interval)
  GROUP BY bars_1m.symbol, ((bars_1m.ts AT TIME ZONE 'Asia/Ho_Chi_Minh'::text)::date)
),
daily_union AS (
  SELECT minute_daily.symbol, minute_daily.trading_date, minute_daily.close
  FROM minute_daily
  UNION ALL
  SELECT d_1.symbol, d_1.trading_date, d_1.close
  FROM bars_1d d_1
  WHERE d_1.trading_date >= (CURRENT_DATE - 45)
    AND NOT (EXISTS (SELECT 1 FROM minute_daily m_1
                     WHERE m_1.symbol = d_1.symbol
                       AND m_1.trading_date = d_1.trading_date))
),
ranked AS (
  SELECT daily_union.symbol, daily_union.trading_date, daily_union.close,
         row_number() OVER (PARTITION BY daily_union.symbol
                            ORDER BY daily_union.trading_date DESC) AS rn
  FROM daily_union
),
last_daily AS (
  SELECT c.symbol, c.trading_date, c.close, p.close AS prev_close
  FROM ranked c LEFT JOIN ranked p ON p.symbol = c.symbol AND p.rn = 2
  WHERE c.rn = 1
)
SELECT s.symbol, s.name,
       COALESCE(m.close, d.close) AS price,
       COALESCE(m.close, d.close) - d.prev_close AS change,
       CASE WHEN d.prev_close > 0::numeric
            THEN round((COALESCE(m.close, d.close) - d.prev_close)
                       / d.prev_close * 100::numeric, 2)
            ELSE 0::numeric END AS change_percent,
       COALESCE(m.volume, 0::bigint) AS volume,
       s.currency,
       COALESCE(m.ts, ((d.trading_date + '15:00:00'::time without time zone)
                       AT TIME ZONE 'Asia/Ho_Chi_Minh'::text)) AS data_as_of
FROM web.symbols s
  LEFT JOIN last_daily d ON d.symbol = s.feed_symbol::text
  LEFT JOIN last_minute m ON m.symbol = s.feed_symbol::text
WHERE s.is_public
"""


def upgrade() -> None:
    # The two-branch form of v_history_1m is only correct while exactly one
    # public symbol is renamed. Fail the migration rather than ship a view
    # that quietly ignores a mapping somebody added.
    op.execute("""
    DO $$
    DECLARE n int;
    BEGIN
        SELECT count(*) INTO n FROM web.symbols
        WHERE is_public AND symbol::text IS DISTINCT FROM feed_symbol::text;
        IF n <> 1 THEN
            RAISE EXCEPTION
              'v_history_1m assumes exactly one renamed public symbol, found %', n;
        END IF;
    END $$;
    """)
    op.execute(HISTORY_1M_SPLIT)
    op.execute(QUOTE_PUBLIC_ONLY)


def downgrade() -> None:
    op.execute(QUOTE_ALL_SYMBOLS)
    op.execute(HISTORY_1M_JOIN)
