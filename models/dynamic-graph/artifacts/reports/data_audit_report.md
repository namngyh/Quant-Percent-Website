# DynamicGraph - Data Audit Report

_Generated 2026-07-26T03:32:26+07:00_

## 1. Source

- **Backend**: `datapro_sqlite`
- **Tables**: HIST, QUOTES_INFO
- **Symbols in source**: 31
- **Date range**: 2012-02-06 .. 2026-07-24
- **Adjusted price available**: True
- **Adjustment method**: adjusted_close = close * (1 - ADJUST_RATE/1e6); cumulative vendor factor, latest session factor = 1.0
- **Volume available**: True
- **Turnover available**: True
- **Sector classification available**: True
- **Data fingerprint**: `cf4f63b6856693b2`

The database is opened strictly read-only (SQLite `mode=ro` plus a write-denying authorizer). No pipeline stage writes to it.

## 2. Loaded panel

- Rows: 90,023
- Tickers: 31 (index `VN30` + 30 constituents)
- Date range: 2012-02-06 .. 2026-07-24
- Trading days: 3,609

## 3. Universe

- Method: `static_list`
- Constituents: 30
- Survivorship bias present: **True**

### Universe warnings

- SURVIVORSHIP BIAS: the universe file has no effective dates, so today's VN30 membership is applied to the whole history. Stocks that were removed from the index are absent and current members are present before they joined. Network statistics and any model trained on them are optimistically biased. Use `data.universe_method: liquidity_proxy` for a point-in-time alternative, or add effective dates to config/vn30_universe.csv.

## 4. Source assumptions

- HIST.TRADING_KEY is days since 1970-01-01. Validated by decoding the maximum key and matching it to the session represented by the QUOTES_INFO snapshot.
- HIST.EID <-> QUOTES_INFO.SYMBOL is reconstructed by unique OHLCV fingerprint on the latest session, because the vendor schema carries no foreign key between the two tables. Symbols whose OHLCV tuple is not unique on that session remain unmapped and are reported rather than guessed.
- adjusted_close = close * (1 - ADJUST_RATE/1e6). The scale and functional form were verified against 12 HPG corporate-action boundaries: the implied factor ratio matched the observed reference-price-to-previous-close ratio to 5 decimal places at every one.
- Prices are quoted in thousand VND and turnover (VAL) in VND. Only ratios and log differences are used downstream, so the unit mismatch does not propagate.
- ICB_ID decodes as <industry:2><supersector:2><sector:2>. Validated against ~40 known tickers (banks -> 8030, real estate -> 8060, securities -> 8070, steel -> 1070).
- Rows with TRADING_KEY before 1990 belong to global reference series (equity indices, metals, FX), not Vietnamese listings; they do not enter a VN30 universe.

## 5. Validation checks

| Check | Result | Severity | Message |
|---|---|---|---|
| `duplicate_ticker_date` | PASS | error | No duplicates. |
| `missing_trading_dates` | PASS | warning | All tickers cover their in-range trading days. |
| `non_positive_prices` | PASS | error | All prices positive. |
| `negative_volume` | PASS | error | No negative volume. |
| `ohlc_coherence` | FAIL | warning | 4 row(s) violate low <= {open, close} <= high. |
| `abnormal_price_jumps` | PASS | warning | No abnormal price jumps. |
| `corporate_action_like_jumps` | PASS | warning | No corporate-action-like jumps beyond the daily price band. |
| `minimum_history` | PASS | warning | All tickers meet the minimum history requirement. |
| `stale_prices` | FAIL | warning | 19 ticker(s) have a run of >= 5 identical consecutive closes. |
| `zero_return_ratio` | PASS | warning | Zero-return ratios are within a normal range. |
| `excess_forward_fill` | PASS | warning | Forward-fill usage is minimal. |
| `calendar_alignment` | FAIL | warning | 496 date(s) have fewer than half of the tickers reporting - sources may not share a trading calendar. |
| `calendar_gaps` | FAIL | info | 1 calendar gap(s) longer than 10 days (holidays or data outages). |
| `timestamp_normalisation` | PASS | warning | All timestamps are dates. |
| `constituent_count` | PASS | info | Ticker count per date ranges 14..31 (median 30). |
| `index_present` | PASS | error | Index `VN30` present. |

**0 error(s), 3 warning(s).**

## 7. Normalisation

- Rows in / out: 90,035 -> 90,035
- Duplicate (ticker, date) rows dropped: 0
- Adjusted price available: True
- Used unadjusted close as a substitute: False
- Sector source: database_classification
- Tickers with UNKNOWN sector: 1

### Normalisation warnings

- 1 ticker(s) have sector = UNKNOWN. Sectors are never guessed from the company name; add them to config/sector_map.csv if you need sector features.

