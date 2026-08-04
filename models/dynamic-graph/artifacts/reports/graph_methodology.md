# DynamicGraph - Graph Methodology

_Generated 2026-07-26T03:32:26+07:00_

## 1. Construction

For every trading day `t` with a complete trailing window of length `W`:

1. **Node validity** - a ticker enters the snapshot only if at most 10% of its returns inside the window are missing.
2. **Covariance** - Ledoit-Wolf shrinkage `Sigma = (1-d) S + d F`, with `d` estimated from the window. With ~30 assets and windows as short as 20 days the sample covariance is ill-conditioned, so shrinkage is the default rather than an option.
3. **Layer**:
   - correlation: `A_ij = rho_ij`
   - partial correlation (core): graphical lasso on the **correlation** matrix, then `rho^partial_ij = -Theta_ij / sqrt(Theta_ii Theta_jj)`. Fitting on the correlation rather than the covariance makes the penalty scale-free; partial correlation is scale invariant so the result is unchanged.
4. **Edge filtering** - method `quantile` (absolute threshold 0.1, top-quantile 0.25, stability threshold 0.6), then a density cap of 0.6.
5. **Edge stability** - bootstrap stability selection was DISABLED in this run (`graph.bootstrap_iterations: 0`), so per-edge selection frequencies are not available and edges were filtered by weight quantile alone. Run with `--full` to enable it.

## 2. Return type

Core layer uses **residual** returns. Market residualization:

```
r_it = alpha_it + beta_it * r_mt + eps_it
```

estimated on a 60-day rolling window ending at `t`. Raw correlation between VN30 stocks is dominated by the market mode; residualizing lets the graph describe relationships that are not simply "everything follows the index".

## 3. Scales built

|   window |   n_snapshots |   mean_density |   std_density |   mean_node_strength | first_date   | last_date   |
|---------:|--------------:|---------------:|--------------:|---------------------:|:-------------|:------------|
|       20 |           718 |         0.1911 |        0.0128 |               0.6396 | 2012-03-02   | 2026-07-20  |
|       60 |           710 |         0.1903 |        0.0127 |               0.6685 | 2012-05-02   | 2026-07-20  |
|      120 |           698 |         0.186  |        0.0145 |               0.6342 | 2012-07-25   | 2026-07-20  |
|      252 |           672 |         0.1806 |        0.0172 |               0.5837 | 2013-01-30   | 2026-07-22  |

Scales are kept separate rather than merged, because a 20-day edge (current co-movement) and a 252-day edge (structural relationship) are different objects.

## 4. Layers produced

- `partial_correlation__residual__w20`: 712 snapshot(s)
- `partial_correlation__residual__w60`: 3526 snapshot(s)
- `partial_correlation__residual__w120`: 694 snapshot(s)
- `partial_correlation__residual__w252`: 671 snapshot(s)
- `partial_correlation__raw__w20`: 718 snapshot(s)
- `partial_correlation__raw__w60`: 710 snapshot(s)
- `partial_correlation__raw__w120`: 698 snapshot(s)
- `partial_correlation__raw__w252`: 672 snapshot(s)
- `correlation__residual__w60`: 705 snapshot(s)
- `correlation__raw__w60`: 710 snapshot(s)

## 5. Graph validation

### Edge Stability

Distribution over all 3525 observation(s):

| metric                   |   count | mean    | std    | min     | 10%     | 50%     | 90%     | max     |
|:-------------------------|--------:|:--------|:-------|:--------|:--------|:--------|:--------|:--------|
| edge_survival            |    3525 | 0.9075  | 0.0508 | 0.5789  | 0.8438  | 0.9136  | 0.9583  | 1.0000  |
| edge_turnover            |    3525 | 0.1662  | 0.0787 | 0.0000  | 0.0791  | 0.1585  | 0.2635  | 0.5926  |
| n_shared_nodes           |    3525 | 23.7677 | 6.8463 | 13.0000 | 14.0000 | 29.0000 | 30.0000 | 30.0000 |
| bootstrap_mean_stability |       0 | -       | -      | -       | -       | -       | -       | -       |

Most recent 12 observation(s):

| date                |   edge_survival |   edge_turnover |   n_shared_nodes | bootstrap_mean_stability   |
|:--------------------|----------------:|----------------:|-----------------:|:---------------------------|
| 2026-07-09 00:00:00 |          0.9634 |          0.092  |               30 | -                          |
| 2026-07-10 00:00:00 |          0.9405 |          0.092  |               30 | -                          |
| 2026-07-13 00:00:00 |          0.9024 |          0.1778 |               30 | -                          |
| 2026-07-14 00:00:00 |          0.9634 |          0.0814 |               30 | -                          |
| 2026-07-15 00:00:00 |          0.8795 |          0.2234 |               30 | -                          |
| 2026-07-16 00:00:00 |          0.869  |          0.2151 |               30 | -                          |
| 2026-07-17 00:00:00 |          0.9268 |          0.1364 |               30 | -                          |
| 2026-07-20 00:00:00 |          0.878  |          0.2174 |               30 | -                          |
| 2026-07-21 00:00:00 |          0.9024 |          0.1591 |               30 | -                          |
| 2026-07-22 00:00:00 |          0.825  |          0.2826 |               30 | -                          |
| 2026-07-23 00:00:00 |          0.9359 |          0.1205 |               30 | -                          |
| 2026-07-24 00:00:00 |          0.8846 |          0.2333 |               30 | -                          |

### Centrality Stability

Distribution over all 705 observation(s):

| metric         |   count |   mean |    std |    min |    10% |    50% |   90% |    max |
|:---------------|--------:|-------:|-------:|-------:|-------:|-------:|------:|-------:|
| rank_stability |     705 | 0.8481 | 0.0927 | 0.3802 | 0.7284 | 0.8706 | 0.943 | 0.9911 |

Most recent 12 observation(s):

| date                | previous_date       | metric   |   rank_stability |
|:--------------------|:--------------------|:---------|-----------------:|
| 2026-05-08 00:00:00 | 2026-04-29 00:00:00 | strength |           0.7686 |
| 2026-05-15 00:00:00 | 2026-05-08 00:00:00 | strength |           0.7904 |
| 2026-05-22 00:00:00 | 2026-05-15 00:00:00 | strength |           0.8616 |
| 2026-05-29 00:00:00 | 2026-05-22 00:00:00 | strength |           0.8625 |
| 2026-06-05 00:00:00 | 2026-05-29 00:00:00 | strength |           0.8385 |
| 2026-06-12 00:00:00 | 2026-06-05 00:00:00 | strength |           0.9106 |
| 2026-06-19 00:00:00 | 2026-06-12 00:00:00 | strength |           0.8812 |
| 2026-06-26 00:00:00 | 2026-06-19 00:00:00 | strength |           0.7851 |
| 2026-07-03 00:00:00 | 2026-06-26 00:00:00 | strength |           0.8336 |
| 2026-07-10 00:00:00 | 2026-07-03 00:00:00 | strength |           0.9008 |
| 2026-07-17 00:00:00 | 2026-07-10 00:00:00 | strength |           0.8968 |
| 2026-07-24 00:00:00 | 2026-07-17 00:00:00 | strength |           0.7566 |

### Community Persistence

Distribution over all 3526 observation(s):

| metric        |   count |   mean |    std |    min |    10% |    50% |    90% |    max |
|:--------------|--------:|-------:|-------:|-------:|-------:|-------:|-------:|-------:|
| n_communities |    3526 | 4.8576 | 0.9158 | 2      | 4      | 5      | 6      | 9      |
| modularity    |    3526 | 0.3295 | 0.0437 | 0.1593 | 0.2806 | 0.3246 | 0.3881 | 0.5398 |
| sector_purity |    3526 | 0.5029 | 0.0495 | 0.4    | 0.4444 | 0.5    | 0.5667 | 0.6875 |
| ari           |    3525 | 0.6087 | 0.2249 | 0.0527 | 0.3209 | 0.5955 | 1      | 1      |
| nmi           |    3525 | 0.7561 | 0.1528 | 0.256  | 0.5492 | 0.7607 | 1      | 1      |
| jaccard       |    3525 | 0.7161 | 0.1687 | 0.2875 | 0.4957 | 0.7123 | 1      | 1      |

Most recent 12 observation(s):

| date                |   n_communities |   modularity |   sector_purity | method   |    ari |    nmi |   jaccard |
|:--------------------|----------------:|-------------:|----------------:|:---------|-------:|-------:|----------:|
| 2026-07-09 00:00:00 |               5 |       0.3625 |          0.5667 | greedy   | 1      | 1      |    1      |
| 2026-07-10 00:00:00 |               6 |       0.3632 |          0.5333 | greedy   | 0.8279 | 0.8883 |    0.8778 |
| 2026-07-13 00:00:00 |               5 |       0.3657 |          0.5333 | greedy   | 0.4403 | 0.6804 |    0.6313 |
| 2026-07-14 00:00:00 |               5 |       0.3733 |          0.5667 | greedy   | 0.7657 | 0.8378 |    0.85   |
| 2026-07-15 00:00:00 |               5 |       0.3886 |          0.5667 | greedy   | 0.8085 | 0.864  |    0.9028 |
| 2026-07-16 00:00:00 |               6 |       0.4076 |          0.5333 | greedy   | 0.833  | 0.891  |    0.8917 |
| 2026-07-17 00:00:00 |               5 |       0.4146 |          0.5    | greedy   | 0.7703 | 0.8539 |    0.754  |
| 2026-07-20 00:00:00 |               5 |       0.3879 |          0.5    | greedy   | 0.7207 | 0.8429 |    0.8543 |
| 2026-07-21 00:00:00 |               5 |       0.3788 |          0.4667 | greedy   | 0.5492 | 0.7104 |    0.6686 |
| 2026-07-22 00:00:00 |               5 |       0.3911 |          0.5    | greedy   | 0.4065 | 0.6118 |    0.6356 |
| 2026-07-23 00:00:00 |               5 |       0.3866 |          0.4667 | greedy   | 0.6266 | 0.7118 |    0.7113 |
| 2026-07-24 00:00:00 |               6 |       0.3812 |          0.5333 | greedy   | 0.6242 | 0.7763 |    0.785  |

### Window Sensitivity

|   window |   n_snapshots |   mean_density |   std_density |   mean_strength | top5_nodes              |   top5_overlap_with_shortest_window |
|---------:|--------------:|---------------:|--------------:|----------------:|:------------------------|------------------------------------:|
|       20 |            25 |         0.1756 |        0.0172 |          0.6851 | LPB, PLX, VIC, VHM, VRE |                                 1   |
|       60 |            24 |         0.1844 |        0.0079 |          0.8425 | VIC, VHM, PLX, MWG, LPB |                                 0.8 |
|      120 |            23 |         0.1857 |        0.0063 |          0.8453 | VIC, VHM, FPT, PLX, GVR |                                 0.6 |
|      252 |            19 |         0.1891 |        0.0045 |          0.8004 | VIC, FPT, VHM, PLX, VJC |                                 0.6 |

### Alpha Sensitivity

|   alpha |   n_snapshots |   mean_density |   mean_edges | top5_nodes              |   top5_overlap_with_smallest_alpha |
|--------:|--------------:|---------------:|-------------:|:------------------------|-----------------------------------:|
|   0.002 |            16 |         0.6    |     261      | VIC, VHM, VRE, STB, MWG |                                1   |
|   0.005 |            16 |         0.6    |     261      | VIC, VHM, VRE, STB, MWG |                                1   |
|   0.01  |            16 |         0.6    |     261      | VIC, VHM, VRE, STB, MWG |                                1   |
|   0.02  |            16 |         0.6    |     261      | VIC, VHM, STB, VRE, MWG |                                1   |
|   0.05  |            16 |         0.4816 |     209.5    | VIC, VHM, GVR, PLX, BCM |                                0.4 |
|   0.1   |            16 |         0.2408 |     104.75   | VIC, VHM, PLX, GAS, MBB |                                0.4 |
|   0.2   |            16 |         0.0634 |      27.5625 | VHM, VIC, PLX, GAS, BID |                                0.4 |

### Missing Data Robustness

|   missing_rate |   n_snapshots | mean_density   | mean_nodes   | density_correlation_with_clean   |
|---------------:|--------------:|:---------------|:-------------|:---------------------------------|
|           0    |            16 | 0.1862         | 30.0000      | 1.0000                           |
|           0.05 |             2 | 0.1724         | 29.0000      | -                                |
|           0.1  |             1 | 0.2051         | 13.0000      | -                                |
|           0.2  |             0 | -              | -            | -                                |

### Sector Removal Robustness

| metric                   |   baseline_mean |   reduced_mean |   relative_change |   correlation | removed                                                              |
|:-------------------------|----------------:|---------------:|------------------:|--------------:|:---------------------------------------------------------------------|
| graph_density            |          0.1862 |         0.1938 |            0.0405 |        0.5346 | ACB, BID, CTG, HDB, LPB, MBB, SHB, SSB, STB, TCB, TPB, VCB, VIB, VPB |
| spectral_radius          |          0.7754 |         0.5805 |           -0.2514 |        0.9358 | ACB, BID, CTG, HDB, LPB, MBB, SHB, SSB, STB, TCB, TPB, VCB, VIB, VPB |
| modularity               |          0.3076 |         0.3654 |            0.1878 |        0.3509 | ACB, BID, CTG, HDB, LPB, MBB, SHB, SSB, STB, TCB, TPB, VCB, VIB, VPB |
| centrality_concentration |          0.0432 |         0.0859 |            0.9893 |        0.7334 | ACB, BID, CTG, HDB, LPB, MBB, SHB, SSB, STB, TCB, TPB, VCB, VIB, VPB |
| average_strength         |          0.5986 |         0.4203 |           -0.2979 |        0.9431 | ACB, BID, CTG, HDB, LPB, MBB, SHB, SSB, STB, TCB, TPB, VCB, VIB, VPB |
| number_of_communities    |          4.9375 |         4.625  |           -0.0633 |        0.4944 | ACB, BID, CTG, HDB, LPB, MBB, SHB, SSB, STB, TCB, TPB, VCB, VIB, VPB |

### Hub Removal Robustness

| metric                   |   baseline_mean |   reduced_mean |   relative_change |   correlation | removed   |
|:-------------------------|----------------:|---------------:|------------------:|--------------:|:----------|
| graph_density            |          0.1862 |         0.1846 |           -0.0088 |        0.8523 | VIC       |
| spectral_radius          |          0.7754 |         0.7178 |           -0.0743 |        0.9365 | VIC       |
| modularity               |          0.3076 |         0.3151 |            0.0242 |        0.8021 | VIC       |
| centrality_concentration |          0.0432 |         0.0445 |            0.0297 |        0.9295 | VIC       |
| average_strength         |          0.5986 |         0.553  |           -0.0762 |        0.9576 | VIC       |
| number_of_communities    |          4.9375 |         5      |            0.0127 |        0.7103 | VIC       |

### Threshold Sensitivity

|   threshold |   mean_density |   mean_top5_overlap |
|------------:|---------------:|--------------------:|
|        0.02 |         0.1906 |              0.257  |
|        0.05 |         0.1901 |              0.2568 |
|        0.1  |         0.1157 |              0.2677 |
|        0.15 |         0.0383 |              0.2525 |
|        0.2  |         0.0117 |              0.3615 |

### Variant Comparison

| variant_a                           | variant_b                           |   spearman_centrality |   top5_overlap |   n_shared_nodes |
|:------------------------------------|:------------------------------------|----------------------:|---------------:|-----------------:|
| partial_correlation__residual__w20  | partial_correlation__residual__w60  |                0.3824 |            0.4 |               30 |
| partial_correlation__residual__w20  | partial_correlation__residual__w120 |                0.2231 |            0.4 |               30 |
| partial_correlation__residual__w20  | partial_correlation__residual__w252 |                0.026  |            0.4 |               30 |
| partial_correlation__residual__w20  | partial_correlation__raw__w20       |                0.8038 |            0.4 |               30 |
| partial_correlation__residual__w20  | partial_correlation__raw__w60       |                0.0385 |            0.4 |               30 |
| partial_correlation__residual__w20  | partial_correlation__raw__w120      |               -0.0972 |            0.4 |               30 |
| partial_correlation__residual__w20  | partial_correlation__raw__w252      |               -0.2747 |            0.2 |               30 |
| partial_correlation__residual__w20  | correlation__residual__w60          |               -0.0646 |            0   |               30 |
| partial_correlation__residual__w20  | correlation__raw__w60               |               -0.4194 |            0   |               30 |
| partial_correlation__residual__w60  | partial_correlation__residual__w120 |                0.5488 |            0.8 |               30 |
| partial_correlation__residual__w60  | partial_correlation__residual__w252 |                0.3802 |            0.8 |               30 |
| partial_correlation__residual__w60  | partial_correlation__raw__w20       |                0.2734 |            0.2 |               30 |
| partial_correlation__residual__w60  | partial_correlation__raw__w60       |                0.5012 |            0.4 |               30 |
| partial_correlation__residual__w60  | partial_correlation__raw__w120      |                0.2601 |            0.6 |               30 |
| partial_correlation__residual__w60  | partial_correlation__raw__w252      |                0.1181 |            0.4 |               30 |
| partial_correlation__residual__w60  | correlation__residual__w60          |                0.3612 |            0.4 |               30 |
| partial_correlation__residual__w60  | correlation__raw__w60               |               -0.0283 |            0   |               30 |
| partial_correlation__residual__w120 | partial_correlation__residual__w252 |                0.6418 |            1   |               30 |
| partial_correlation__residual__w120 | partial_correlation__raw__w20       |                0.0518 |            0.4 |               30 |
| partial_correlation__residual__w120 | partial_correlation__raw__w60       |                0.2672 |            0.6 |               30 |

## 6. Signed-graph handling

Partial correlations can be negative. Eigenvector centrality, PageRank, closeness, harmonic centrality, clustering and coreness are undefined or meaningless on negative weights, so they are computed on `|A|`. Sign information is preserved separately as `positive_strength`, `negative_strength` and `edge_sign_ratio`. Every node-metric row carries a `weights_used` column recording the transformation.

## 7. Known limitations

- Partial correlation conditions only on the other VN30 members; omitted common factors (global risk appetite, FX, commodity prices) can still induce edges.
- Non-synchronous trading across the constituents biases short-window correlations downward.
- The graphical-lasso penalty controls sparsity but is not itself identified; the alpha sensitivity table above shows how much the conclusions depend on it.
- Edges are associations. Nothing here identifies a causal channel.
