# DynamicGraph - Investor Summary

**As of 2026-07-24**

## What this is

DynamicGraph maps how the 30 VN30 constituents move in relation to one another, and how that structure changes over time. It answers structural questions - which stocks sit at the centre of the market, which groups move together, whether diversification is working - rather than forecasting a price level.

## Current network state

- **State**: `high_stress`
- **Network Stress Score**: 84.62 / 100
- **Historical percentile**: 0.9282
- **Change over 20 sessions**: -0.25

The network is highly synchronised: connectivity and concentration are near the top of their historical range. Historically, periods like this have coincided with weaker index-level diversification, though they do not determine what happens next.

### What is driving the score

- `market_mode_share` is raising the score (share 0.1807)
- `spectral_radius` is raising the score (share 0.1807)
- `centrality_concentration` is lowering the score (share 0.1807)
- `negative_diversification` is raising the score (share 0.1807)
- `community_compression` is raising the score (share 0.0838)

## Most central stocks

These sit at the centre of the estimated dependence structure. **This is not a view on their future returns.** A central stock is one whose movements are most connected to the rest of the index.

| Ticker | Sector | Strength | Eigenvector centrality |
|---|---|---|---|
| VIC | Real Estate | 1.8312 | 0.4057 |
| FPT | Technology | 1.467 | 0.319 |
| VHM | Real Estate | 1.2239 | 0.2716 |
| LPB | Banks | 1.3719 | 0.2736 |
| VRE | Real Estate | 1.1831 | 0.2647 |
| PLX | Oil & Gas | 1.3246 | 0.2158 |
| GVR | Chemicals | 1.0721 | 0.2375 |
| HPG | Basic Resources | 1.0589 | 0.2474 |

## Stocks under structural strain

Deeper drawdowns and higher downside volatility, with stressed neighbours in the network. This is a description of current condition, not a forecast.

| Ticker | Sector | Drawdown | Downside volatility |
|---|---|---|---|
| HDB | Banks | -0.1296 | 0.1872 |
| ACB | Banks | -0.114 | 0.1604 |
| LPB | Banks | -0.0643 | 0.2134 |
| STB | Banks | -0.043 | 0.1626 |
| VCB | Banks | -0.2829 | 0.2256 |
| VPB | Banks | -0.343 | 0.1977 |
| CTG | Banks | -0.2905 | 0.2451 |
| VNM | Food & Beverage | -0.4075 | 0.1473 |

## Groups moving together

- **Group 0** (8 stocks, mixed; largest sector Banks at 38%): FPT, HDB, HPG, MBB, MSN, MWG, STB, VIC
- **Group 1** (6 stocks, mostly Banks, 83%): ACB, LPB, TPB, VIB, VJC, VPB
- **Group 2** (5 stocks, mixed; largest sector Real Estate at 20%): BCM, GAS, GVR, PLX, SSB
- **Group 3** (4 stocks, mostly Banks, 75%): BID, BVH, CTG, VCB
- **Group 4** (4 stocks, mixed; largest sector Food & Beverage at 50%): SAB, SHB, SSI, VNM
- **Group 5** (3 stocks, mostly Real Estate, 67%): TCB, VHM, VRE

Groups are detected from the data, not imposed from sector labels. When they line up with sectors, sector exposure is the dominant structure; when they do not, something else is driving co-movement.

## Stress probabilities

| Horizon | Probability | Calibrated | OOS Brier | Sample |
|---|---|---|---|---|
| 5d | 0.18205 | True | 0.1141 | 1323 |
| 10d | 0.13183 | True | 0.1354 | 1323 |
| 20d | 0.08426 | True | 0.1563 | 1323 |
| 40d | 0.25397 | True | 0.2147 | 1323 |

These are estimated probabilities of a drawdown-defined stress state, evaluated out-of-sample. They carry material uncertainty.

**Warning.** Horizon(s) 5d, 10d, 20d, 40d did not beat a constant base-rate forecast out of sample. Those probabilities should be treated as uninformative and are published only for transparency.

## How much to trust this

- Out-of-sample assessment of whether network features improve stress prediction over a market-only baseline: **mixed**.
- Some settings improved significantly and others did not. The evidence does not support a general claim that graph features help.

- **The stress probabilities have no demonstrated forecasting skill.** Measured out of sample, the best model scored no better than simply quoting the historical frequency of stress periods. Read the network state and its drivers; do not act on the probability numbers.

- **Survivorship bias**: the constituent list is today's VN30 applied backwards. Stocks removed from the index over the period are absent. Historical statistics are flattering as a result.

## What this does not say

- It does not say the market will fall. A rising stress score says stocks are moving together more and that diversification within the index may be providing less protection.
- Connections between stocks are statistical associations, not causal links.
- Central stocks are not recommendations.

_Not investment advice._
