# Capital allocation - out-of-sample evaluation

_Generated 2026-07-27 15:26._

## The question this answers

The predictive evaluation established that this data does not support
forecasting market stress: no configuration beat a naive frequency
baseline. That is a statement about **first** moments. Allocation depends
on **second** moments, which are a different and considerably easier
estimation problem -- realised correlation structure persists across
months, whereas the signal-to-noise ratio of expected returns is near
zero. So the failure of the predictive layer does not settle whether the
graph is useful, and this report tests the remaining claim separately.

Three claims are kept apart on purpose:

1. does *any* covariance-aware rule beat naive equal weighting?
2. does the *graphical-lasso* covariance beat the *sample* covariance at
   the same weight rule?
3. does the *community partition* beat a covariance-free risk split?

Answering (1) yes and (2) no would mean dependence modelling helped but
the network layer specifically did not -- a distinction that is easy to
blur and that changes what the project is worth.

## Method

- Estimation window: **60 trading days**, trailing, ending at the rebalance date inclusive.
- Rebalance frequency: every **20 trading days**.
- Weight cap: **20%** per name, long only, fully invested.
- Transaction cost: **15 bps per side**, charged on traded notional against the drifted book.
- Graphical-lasso penalty: **0.02**, frozen from the training-period selection.

Weights formed on date `t` are applied to returns of `t+1 ... t+h`. No
date is ever used both to estimate and to evaluate. Nothing in the
backtest is fitted globally, so the whole series is out of sample.

Every estimator keeps the **sample standard deviations on the diagonal**
and differs only in the correlation matrix. Without that constraint a
lower backtested volatility could come from an estimator quietly
understating the risk level rather than from a better dependence estimate.

The primary metric is **realised annualised volatility**, because every
rule here is a function of the covariance matrix alone and can only be
held responsible for the risk it produced. Return and Sharpe are reported
alongside so that a risk reduction bought by giving up more return is
visible rather than hidden.

## Results

Sorted by realised volatility, lowest first.

| key                           | rule                  | estimator   |   annual_volatility |   annual_return |   sharpe |   max_drawdown |   mean_effective_n_bets |   mean_diversification_ratio |   mean_turnover_traded |   annual_cost_drag |   realized_over_ex_ante_volatility |   n_days |
|:------------------------------|:----------------------|:------------|--------------------:|----------------:|---------:|---------------:|------------------------:|-----------------------------:|-----------------------:|-------------------:|-----------------------------------:|---------:|
| minimum_variance__ledoit_wolf | minimum_variance      | ledoit_wolf |              0.1644 |          0.1441 |   0.8762 |        -0.4131 |                  5.9627 |                       2.1058 |                 0.5147 |             0.0097 |                             1.41   |     3549 |
| minimum_variance__glasso      | minimum_variance      | glasso      |              0.1646 |          0.142  |   0.8631 |        -0.4223 |                  5.3476 |                       1.9836 |                 0.5405 |             0.0102 |                             1.338  |     3549 |
| minimum_variance__sample      | minimum_variance      | sample      |              0.165  |          0.1445 |   0.8761 |        -0.4172 |                  5.1468 |                       1.9922 |                 0.5552 |             0.0105 |                             1.3406 |     3549 |
| minimum_variance__diagonal    | minimum_variance      | diagonal    |              0.185  |          0.1626 |   0.8791 |        -0.4376 |                 20.4279 |                       4.6419 |                 0.2434 |             0.0046 |                             3.2185 |     3549 |
| risk_parity__sample           | risk_parity           | sample      |              0.1853 |          0.1619 |   0.8738 |        -0.4148 |                  1.7563 |                       1.8594 |                 0.1989 |             0.0038 |                             1.143  |     3549 |
| risk_parity__glasso           | risk_parity           | glasso      |              0.1854 |          0.1615 |   0.8711 |        -0.4157 |                  1.7595 |                       1.8693 |                 0.1978 |             0.0037 |                             1.1495 |     3549 |
| risk_parity__ledoit_wolf      | risk_parity           | ledoit_wolf |              0.1859 |          0.1613 |   0.8677 |        -0.4158 |                  1.9763 |                       2.045  |                 0.1877 |             0.0035 |                             1.2453 |     3549 |
| inverse_volatility__sample    | inverse_volatility    | sample      |              0.1934 |          0.1615 |   0.8353 |        -0.4358 |                  1.4395 |                       1.7084 |                 0.144  |             0.0027 |                             1.1029 |     3549 |
| risk_parity__diagonal         | risk_parity           | diagonal    |              0.1934 |          0.1615 |   0.8353 |        -0.4358 |                 23.8315 |                       4.8259 |                 0.144  |             0.0027 |                             3.2291 |     3549 |
| community_risk_parity__sample | community_risk_parity | sample      |              0.1953 |          0.1554 |   0.7956 |        -0.4797 |                  1.6246 |                       1.6826 |                 0.4639 |             0.0088 |                             1.0966 |     3549 |
| equal_weight__sample          | equal_weight          | sample      |              0.2034 |          0.1612 |   0.7924 |        -0.4256 |                  1.2415 |                       1.7049 |                 0.0647 |             0.0012 |                             1.0692 |     3549 |

`mean_effective_n_bets` is the exponential entropy of risk across principal
components -- the number of *independent* risk sources, not the number of
positions. `realized_over_ex_ante_volatility` above 1 means the estimator
understated risk in advance.

### Against equal weighting

Paired moving-block bootstrap, same blocks drawn from both series so the
shared market variation cancels.

| portfolio                     | benchmark            | metric            |   portfolio_value |   benchmark_value |   difference |   ci_lower |   ci_upper |   p_value | significant   |    n |
|:------------------------------|:---------------------|:------------------|------------------:|------------------:|-------------:|-----------:|-----------:|----------:|:--------------|-----:|
| minimum_variance__ledoit_wolf | equal_weight__sample | annual_volatility |            0.1644 |            0.2034 |      -0.039  |    -0.0447 |    -0.0319 |         0 | True          | 3549 |
| minimum_variance__glasso      | equal_weight__sample | annual_volatility |            0.1646 |            0.2034 |      -0.0389 |    -0.0448 |    -0.0314 |         0 | True          | 3549 |
| minimum_variance__sample      | equal_weight__sample | annual_volatility |            0.165  |            0.2034 |      -0.0385 |    -0.0444 |    -0.0311 |         0 | True          | 3549 |
| minimum_variance__diagonal    | equal_weight__sample | annual_volatility |            0.185  |            0.2034 |      -0.0185 |    -0.0209 |    -0.0155 |         0 | True          | 3549 |
| risk_parity__sample           | equal_weight__sample | annual_volatility |            0.1853 |            0.2034 |      -0.0181 |    -0.0205 |    -0.0156 |         0 | True          | 3549 |
| risk_parity__glasso           | equal_weight__sample | annual_volatility |            0.1854 |            0.2034 |      -0.0181 |    -0.0204 |    -0.0155 |         0 | True          | 3549 |
| risk_parity__ledoit_wolf      | equal_weight__sample | annual_volatility |            0.1859 |            0.2034 |      -0.0176 |    -0.0199 |    -0.0151 |         0 | True          | 3549 |
| inverse_volatility__sample    | equal_weight__sample | annual_volatility |            0.1934 |            0.2034 |      -0.0101 |    -0.0113 |    -0.0086 |         0 | True          | 3549 |
| risk_parity__diagonal         | equal_weight__sample | annual_volatility |            0.1934 |            0.2034 |      -0.0101 |    -0.0113 |    -0.0086 |         0 | True          | 3549 |
| community_risk_parity__sample | equal_weight__sample | annual_volatility |            0.1953 |            0.2034 |      -0.0082 |    -0.0101 |    -0.0054 |         0 | True          | 3549 |

### Graphical lasso against the sample covariance

The isolated test of the project's own claim: same weight rule, same
window, same cap -- only the covariance estimator changes.

| rule             | estimator   | baseline_estimator   |   volatility |   baseline_volatility |   volatility_difference |   ci_lower |   ci_upper |   p_value | significant_reduction   |    n |
|:-----------------|:------------|:---------------------|-------------:|----------------------:|------------------------:|-----------:|-----------:|----------:|:------------------------|-----:|
| minimum_variance | ledoit_wolf | sample               |       0.1644 |                0.165  |                 -0.0005 |    -0.0012 |     0.0001 |     0.066 | False                   | 3549 |
| minimum_variance | glasso      | sample               |       0.1646 |                0.165  |                 -0.0004 |    -0.0008 |     0.0001 |     0.042 | False                   | 3549 |
| minimum_variance | diagonal    | sample               |       0.185  |                0.165  |                  0.02   |     0.0148 |     0.0247 |     1     | False                   | 3549 |
| risk_parity      | ledoit_wolf | sample               |       0.1859 |                0.1853 |                  0.0006 |     0.0004 |     0.0008 |     1     | False                   | 3549 |
| risk_parity      | glasso      | sample               |       0.1854 |                0.1853 |                  0.0001 |     0      |     0.0001 |     0.982 | False                   | 3549 |
| risk_parity      | diagonal    | sample               |       0.1934 |                0.1853 |                  0.0081 |     0.0063 |     0.0098 |     1     | False                   | 3549 |

## Verdict

**`covariance_helps_graph_does_not`**

Covariance-aware allocation beat equal weighting, but the sparse graphical-lasso estimate did not beat the sample covariance at the same weight rule. The gain came from modelling dependence at all, not from the network layer specifically.

- Lowest-volatility portfolio: `minimum_variance__ledoit_wolf`
- Its realised volatility: `0.1644`
- Equal-weight volatility: `0.2034`
- Significant volatility reductions vs equal weight: `10`
- Comparisons run: `10`
- Rules where glasso beat the sample covariance: `[]`
- Community risk parity minus inverse volatility (vol): `0.0019`

## What this does not establish

> Backtested weights ignore market impact, borrow availability, foreign ownership limits and the VN30 constituent changes over the period. These are risk-model comparisons, not a tradable strategy.

Specifically:

- The universe is the **current** VN30 held fixed over the whole period.
  Names that left the index are absent, which flatters every rule here
  equally but flatters them all.
- Costs are linear in traded notional. Real impact is convex, so the
  high-turnover rules are treated more kindly than they deserve.
- Foreign ownership limits, lot sizes and borrow availability are ignored.
- A volatility reduction is not a return improvement. Where the two
  disagree, the table above shows both.

