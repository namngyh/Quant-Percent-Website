"""Project-wide constants: the data contract, canonical column names and
classification lookup tables.

Nothing here depends on configuration; everything is a fixed vocabulary that
the rest of the pipeline agrees on.
"""

from __future__ import annotations

from typing import Final

# --------------------------------------------------------------------------
# Data contract (long format). `loader` + `normalizer` must produce exactly
# these columns, in this order, before anything downstream touches the data.
# --------------------------------------------------------------------------
DATA_CONTRACT_COLUMNS: Final[list[str]] = [
    "date",
    "ticker",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
    "turnover",
    "sector",
    "is_index",
]

#: Columns that must be present and non-null for a row to be usable at all.
REQUIRED_COLUMNS: Final[list[str]] = ["date", "ticker", "close"]

#: Optional columns filled with NaN when the source does not provide them.
OPTIONAL_NUMERIC_COLUMNS: Final[list[str]] = [
    "open",
    "high",
    "low",
    "adjusted_close",
    "volume",
    "turnover",
]

#: Extra columns that some backends can supply; carried through when present.
EXTENDED_COLUMNS: Final[list[str]] = [
    "shares_outstanding",
    "market_cap",
    "foreign_buy_value",
    "foreign_sell_value",
    "reference_price",
]

TRADING_DAYS_PER_YEAR: Final[int] = 252
EPS: Final[float] = 1e-12

#: Canonical internal name of the market index node.
INDEX_TICKER: Final[str] = "VN30"

UNKNOWN_SECTOR: Final[str] = "UNKNOWN"

# --------------------------------------------------------------------------
# Column-name synonyms used by `schema_inference` to recognise unknown schemas.
# Matching is case-insensitive and ignores separators.
# --------------------------------------------------------------------------
COLUMN_SYNONYMS: Final[dict[str, list[str]]] = {
    "date": [
        "date", "trade_date", "tradingdate", "trading_date", "time", "timestamp",
        "datetime", "dt", "day", "ngay", "tradingday", "bar_date", "trading_key",
    ],
    "ticker": [
        "ticker", "symbol", "code", "stock", "stock_code", "sym", "instrument",
        "security", "ma", "macp", "seccode", "name",
    ],
    "open": ["open", "open_px", "openprice", "open_price", "o", "gia_mo_cua"],
    "high": ["high", "high_px", "highprice", "high_price", "h", "gia_cao_nhat"],
    "low": ["low", "low_px", "lowprice", "low_price", "l", "gia_thap_nhat"],
    "close": [
        "close", "close_px", "closeprice", "close_price", "c", "last", "px_last",
        "gia_dong_cua",
    ],
    "adjusted_close": [
        "adjusted_close", "adj_close", "adjclose", "adjusted", "adj_px",
        "close_adjusted", "adjusted_price", "gia_dieu_chinh",
    ],
    "volume": [
        "volume", "vol", "qty", "quantity", "shares", "matched_vol", "khoi_luong",
        "total_volume", "nmvolume",
    ],
    "turnover": [
        "turnover", "value", "val", "amount", "traded_value", "notional",
        "gia_tri", "total_value", "nmvalue",
    ],
    "market_cap": ["market_cap", "marketcap", "mcap", "cap", "von_hoa"],
    "sector": ["sector", "industry", "icb", "icb_id", "icb_code", "nganh", "gics"],
    "shares_outstanding": [
        "shares_outstanding", "outstanding_vol", "listed_vol", "shares_out",
        "outstanding", "listed_shares",
    ],
}

# --------------------------------------------------------------------------
# ICB classification lookups.
#
# ASSUMPTION (recorded in artifacts/reports/assumptions.md): the 6-digit ICB
# code stored by the data vendor decomposes as <industry:2><supersector:2>
# <sector:2>. This was validated against ~40 known VN tickers (banks -> 8030,
# real estate -> 8060, securities -> 8070, steel -> 1070, ...). Codes that are
# not in the table fall back to the industry level, then to UNKNOWN.
# --------------------------------------------------------------------------
ICB_INDUSTRY_NAMES: Final[dict[str, str]] = {
    "10": "Basic Materials",
    "11": "Oil & Gas",
    "20": "Industrials",
    "30": "Consumer Goods",
    "40": "Health Care",
    "50": "Consumer Services",
    "60": "Telecommunications",
    "70": "Utilities",
    "80": "Financials",
    "90": "Technology",
}

ICB_SUPERSECTOR_NAMES: Final[dict[str, str]] = {
    "1030": "Chemicals",
    "1070": "Basic Resources",
    "1150": "Oil & Gas",
    "2030": "Construction & Materials",
    "2070": "Industrial Goods & Services",
    "3030": "Automobiles & Parts",
    "3050": "Food & Beverage",
    "3070": "Personal & Household Goods",
    "4050": "Health Care",
    "5030": "Retail",
    "5050": "Media",
    "5070": "Travel & Leisure",
    "6050": "Telecommunications",
    "7050": "Utilities",
    "8030": "Banks",
    "8050": "Insurance",
    "8060": "Real Estate",
    "8070": "Financial Services",
    "8090": "Equity Investment Instruments",
    "9050": "Technology",
}

# --------------------------------------------------------------------------
# Graph / network vocabulary
# --------------------------------------------------------------------------
GRAPH_LAYERS: Final[list[str]] = [
    "correlation",
    "partial_correlation",
    "lead_lag",
    "spillover",
]

RETURN_TYPES: Final[list[str]] = ["raw", "residual"]

#: Centrality measures that cannot consume negative edge weights and therefore
#: must be run on the absolute-weight graph.
ABS_WEIGHT_REQUIRED_METRICS: Final[list[str]] = [
    "eigenvector_centrality",
    "pagerank",
    "closeness_centrality",
    "harmonic_centrality",
    "betweenness_centrality",
    "clustering",
    "coreness",
]

NODE_METRIC_COLUMNS: Final[list[str]] = [
    "degree",
    "degree_centrality",
    "strength",
    "positive_strength",
    "negative_strength",
    "edge_sign_ratio",
    "eigenvector_centrality",
    "pagerank",
    "betweenness_centrality",
    "closeness_centrality",
    "harmonic_centrality",
    "clustering",
    "coreness",
    "community",
    "participation_coefficient",
    "within_community_degree_z",
    "avg_neighbor_strength",
    "avg_neighbor_risk",
    "avg_neighbor_volatility",
    "neighbor_downside_exposure",
]

GRAPH_METRIC_COLUMNS: Final[list[str]] = [
    "number_of_nodes",
    "number_of_edges",
    "graph_density",
    "average_degree",
    "average_strength",
    "median_strength",
    "maximum_strength",
    "average_clustering",
    "global_transitivity",
    "assortativity",
    "modularity",
    "number_of_communities",
    "largest_community_share",
    "largest_cc_share",
    "spectral_radius",
    "algebraic_connectivity",
    "laplacian_entropy",
    "edge_weight_mean",
    "edge_weight_std",
    "average_absolute_correlation",
    "average_partial_correlation",
    "avg_abs_partial_correlation",
    "positive_edge_ratio",
    "negative_edge_ratio",
    "edge_turnover",
    "community_turnover",
    "centrality_concentration",
    "eigenvalue_concentration",
    "market_mode_share",
    "mst_length",
    "network_fragility",
    "negative_diversification",
    "community_compression",
    "total_connectedness",
]

#: Network-state labels exposed to the website, ordered from calm to stressed.
NETWORK_STATE_LABELS: Final[list[str]] = [
    "low_connectivity",
    "normal",
    "elevated",
    "high_stress",
]

# --------------------------------------------------------------------------
# Wording discipline. Undirected centrality never justifies causal language.
# --------------------------------------------------------------------------
INFLUENCE_LABEL: Final[str] = "high_influence_node"
TRANSMITTER_LABEL: Final[str] = "directed_risk_transmitter"
RECEIVER_LABEL: Final[str] = "directed_risk_receiver"
VULNERABLE_LABEL: Final[str] = "vulnerable_node"
