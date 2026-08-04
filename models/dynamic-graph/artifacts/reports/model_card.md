# DynamicGraph - Model Card

**Version** 0.1.0 | **Run** `20260725T174740Z` | **Generated** 2026-07-25T17:47:40.950596+00:00

## Intended use

DynamicGraph describes how the dependence structure among VN30 constituents evolves, and estimates the probability that the VN30 enters a drawdown-defined stress state over a 5-40 day horizon. It is a **risk-monitoring and structural-description tool**.

**Out of scope**: forecasting the VN30 index level, single-stock price prediction, identifying causal relationships between companies, and any use as standalone investment advice.

## Data

- Source backend: `datapro_sqlite` (read-only)
- Period: 2012-02-06 .. 2026-07-24
- Universe: 30 constituents plus the `VN30` index, method `static_list`
- Data fingerprint: `cf4f63b6856693b2`
- Adjusted prices: True
- Survivorship bias: **True**

## Method

- Core graph: partial_correlation on residual returns, 60-day window, Ledoit-Wolf covariance, graphical lasso alpha=0.02
- Edge filter: quantile
- Evaluation: purged_walk_forward, purge 40d, embargo 5d
- Calibration: isotonic (fitted on validation blocks only)

## Performance

- Best out-of-sample model: `random_forest` on feature set `combined` at horizon 5d - Brier 0.1141, Brier skill score -0.1216, AUPRC 0.1582 (base rate 0.115)
- **No model achieved a positive Brier skill score.** Every configuration scored worse than a constant forecast at the realised base rate, so the probabilities carry no demonstrated forecasting skill at these horizons. They are published for transparency, not because they are actionable. Use DynamicGraph for structural description; do not act on the probabilities.
- Graph incremental value: **mixed** - Some settings improved significantly and others did not. The evidence does not support a general claim that graph features help.

The Brier skill score is measured against a constant forecast at the *realised* test-set base rate, which is a hindsight benchmark and therefore a demanding one. A small negative value does not by itself mean a model is useless, but a model that cannot approach zero has no demonstrated forecasting value.

## Reproducibility

- Seed: 42
- Config fingerprint: `5a6468edfbd1b8d7`
- Git commit: `not a git repository`
- Platform: Windows 11
- Key package versions: python=3.13.14, numpy=2.4.4, pandas=3.0.3, scipy=1.17.1, scikit-learn=1.8.0, networkx=3.6.1

## Ethical and practical considerations

- The published probability is an estimate with material uncertainty. It must be presented with its calibration quality and sample size, never as a bare number.
- Network centrality identifies structural position, not attractiveness as an investment.
- The model is fitted on a single market over a limited history; it has not been validated on other markets or on a live forward period.

## Maintenance

- Last training date: 2026-07-25
- Retrain when the walk-forward window advances materially, when the VN30 constituent list changes, or when data-quality warnings change.
