# DynamicGraph - Recorded Assumptions

_Generated 2026-07-26T03:32:26+07:00_

Every non-obvious decision taken automatically by the pipeline, recorded so it can be challenged.

1. HIST.TRADING_KEY is days since 1970-01-01. Validated by decoding the maximum key and matching it to the session represented by the QUOTES_INFO snapshot.
2. HIST.EID <-> QUOTES_INFO.SYMBOL is reconstructed by unique OHLCV fingerprint on the latest session, because the vendor schema carries no foreign key between the two tables. Symbols whose OHLCV tuple is not unique on that session remain unmapped and are reported rather than guessed.
3. adjusted_close = close * (1 - ADJUST_RATE/1e6). The scale and functional form were verified against 12 HPG corporate-action boundaries: the implied factor ratio matched the observed reference-price-to-previous-close ratio to 5 decimal places at every one.
4. Prices are quoted in thousand VND and turnover (VAL) in VND. Only ratios and log differences are used downstream, so the unit mismatch does not propagate.
5. ICB_ID decodes as <industry:2><supersector:2><sector:2>. Validated against ~40 known tickers (banks -> 8030, real estate -> 8060, securities -> 8070, steel -> 1070).
6. Rows with TRADING_KEY before 1990 belong to global reference series (equity indices, metals, FX), not Vietnamese listings; they do not enter a VN30 universe.
7. Residual returns come from a 60-day rolling market regression; residual at t uses coefficients fitted on [t-W+1, t] only.
8. The graphical lasso is fitted on the CORRELATION matrix rather than the covariance. Daily return covariances are ~1e-4, so a penalty on the covariance scale would zero every off-diagonal term; partial correlation is scale invariant, so the estimate is unchanged while alpha becomes comparable across windows and regimes.
9. Centrality measures that are undefined on negative weights (eigenvector, PageRank, closeness, harmonic, betweenness, clustering, coreness) are computed on |A|. Sign information is preserved separately as positive/negative strength and edge sign ratio.
10. The universe is the static VN30 list in config/vn30_universe.csv applied to all of history, because the database carries no index-membership table. This is survivorship-biased; `data.universe_method: liquidity_proxy` builds a point-in-time alternative from trailing market cap x turnover.
