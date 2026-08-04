# DynamicGraph - Limitations

_Generated 2026-07-26T03:32:26+07:00_

## 1. Data

- **Survivorship bias (material).** The universe is a current-membership snapshot applied to the whole history. Constituents removed from the VN30 are absent, and current members appear before they joined. Network density, centrality persistence and model performance are all optimistically biased. Mitigation: set `data.universe_method: liquidity_proxy`, or add effective dates to `config/vn30_universe.csv`.
- History starts 2012-02-06, giving 3,609 trading days. Stress episodes are rare, so the effective number of independent events behind any performance claim is small.
- Vietnamese equities have a +/-7% daily price band and periodic foreign-ownership constraints. Both compress observed return distributions and can distort correlation estimates during stress.
- Non-synchronous trading across constituents biases short-window correlations downward.

## 2. Graph estimation

- Partial correlation conditions only on the other VN30 members. Omitted common factors (global risk sentiment, FX, commodities) can still generate edges.
- The graphical-lasso penalty is a modelling choice, not an identified parameter. The alpha-sensitivity analysis quantifies how much conclusions depend on it.
- Edge weights are associations. No edge in this system is a causal channel.
- Centrality on an undirected graph carries no direction of propagation. That is why the system emits `high_influence_node`, never `transmitter`, unless a directed layer exists.

## 3. Directed layers

- Lead-lag edges are lagged correlations subject to multiple testing (BH-FDR is applied) and to non-synchronous trading. Daily sampling gives limited power to detect genuine lead-lag structure.
- VAR spillover uses regularised estimation because a 30-dimensional unrestricted VAR is not estimable on a 120-day window. Generalised FEVD shares are predictive attributions under an assumed model.

## 4. Prediction

- **No configuration achieved positive out-of-sample forecasting skill.** The best Brier skill score across 48 configuration(s) was -0.122, i.e. no better than quoting the historical frequency of stress. The predictive layer of DynamicGraph is not currently usable for decisions; the structural layer is what this system delivers today.
- Graph incremental value verdict: **mixed**. Some settings improved significantly and others did not. The evidence does not support a general claim that graph features help.
- Labels overlap across adjacent dates, so nominal sample sizes overstate information content. Confidence intervals use block bootstrap for this reason.
- Calibration is fitted per fold on a limited validation block; with few positives it falls back from isotonic to Platt scaling, which is reported per fold.
- Performance is evaluated on one market over one historical period. There is no out-of-market or live forward validation.

## 5. Interpretation

- Association, predictive importance and causal effect are distinct. DynamicGraph establishes the first two at most.
- Portfolio spreads reported in the ranking evaluation are an evaluation device, not a tradable strategy and not evidence of causality.
- Attention weights from the optional Temporal GNN are a model diagnostic only.

## 6. Operational

- The pipeline reads a local database that a third-party client updates. If that client stops updating, `data_freshness_days` grows and outputs become stale; consumers should check that field.
- Optional dependencies (torch, torch-geometric, shap, interpret, leidenalg, xgboost) are not required; when absent the corresponding analysis is skipped and recorded rather than silently replaced.
