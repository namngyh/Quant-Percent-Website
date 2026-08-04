"""Shared fixtures.

A synthetic market is generated with a known factor structure so that tests can
assert on properties the estimator *should* recover (block correlation, market
mode, stress episodes) without depending on the real database.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dynamicgraph.config import load_config  # noqa: E402


N_DAYS = 1400
N_STOCKS = 12
SECTORS = {
    **{f"BNK{i}": "Banks" for i in range(1, 5)},
    **{f"RES{i}": "Real Estate" for i in range(1, 5)},
    **{f"TEC{i}": "Technology" for i in range(1, 5)},
}
TICKERS = list(SECTORS)


@pytest.fixture(scope="session")
def synthetic_panel() -> pd.DataFrame:
    """Long-format panel with a market factor, three sector factors and a
    deliberate stress regime in the middle of the sample."""
    rng = np.random.default_rng(20240101)
    dates = pd.bdate_range("2019-01-01", periods=N_DAYS)

    market = rng.normal(0.0003, 0.010, N_DAYS)
    # Stress regime: higher volatility and stronger common movement.
    stress = slice(700, 820)
    market[stress] = rng.normal(-0.003, 0.026, 120)

    sector_factors = {
        sector: rng.normal(0.0, 0.007, N_DAYS) for sector in {"Banks", "Real Estate", "Technology"}
    }
    for factor in sector_factors.values():
        factor[stress] *= 2.0

    rows = []
    for ticker in TICKERS:
        sector = SECTORS[ticker]
        beta = rng.uniform(0.7, 1.3)
        sector_loading = rng.uniform(0.5, 1.1)
        idiosyncratic = rng.normal(0.0, 0.011, N_DAYS)
        idiosyncratic[stress] *= 1.6
        returns = beta * market + sector_loading * sector_factors[sector] + idiosyncratic
        price = 20.0 * np.exp(np.cumsum(returns))
        volume = rng.lognormal(13.0, 0.6, N_DAYS)
        rows.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "ticker": ticker,
                    "open": price * (1 + rng.normal(0, 0.002, N_DAYS)),
                    "high": price * (1 + np.abs(rng.normal(0, 0.004, N_DAYS))),
                    "low": price * (1 - np.abs(rng.normal(0, 0.004, N_DAYS))),
                    "close": price,
                    "adjusted_close": price,
                    "volume": volume,
                    "turnover": volume * price,
                    "sector": sector,
                    "is_index": False,
                }
            )
        )

    index_price = 1000.0 * np.exp(np.cumsum(market))
    rows.append(
        pd.DataFrame(
            {
                "date": dates,
                "ticker": "VN30",
                "open": index_price,
                "high": index_price * 1.003,
                "low": index_price * 0.997,
                "close": index_price,
                "adjusted_close": index_price,
                "volume": rng.lognormal(18.0, 0.4, N_DAYS),
                "turnover": rng.lognormal(20.0, 0.4, N_DAYS),
                "sector": "UNKNOWN",
                "is_index": True,
            }
        )
    )
    panel = pd.concat(rows, ignore_index=True)
    return panel.sort_values(["ticker", "date"]).reset_index(drop=True)


@pytest.fixture(scope="session")
def synthetic_returns(synthetic_panel: pd.DataFrame) -> pd.DataFrame:
    wide = synthetic_panel[synthetic_panel["ticker"] != "VN30"].pivot_table(
        index="date", columns="ticker", values="adjusted_close"
    )
    return np.log(wide / wide.shift(1)).dropna()


@pytest.fixture(scope="session")
def base_config():
    """Default config with the sizes reduced so tests stay fast."""
    config = load_config("config/default.yaml")
    config.graph.windows = [60]
    config.graph.core_window = 60
    config.graph.bootstrap_iterations = 0
    config.graph.snapshot_stride = 20
    config.graph.build_raw_and_residual = False
    config.graph.build_correlation_and_partial = False
    config.graph.enable_lead_lag = False
    config.training.initial_train_days = 400
    config.training.validation_days = 100
    config.training.test_days = 100
    config.data.minimum_history_days = 100
    config.output.create_figures = False
    return config


@pytest.fixture(scope="session")
def sector_map() -> dict[str, str]:
    return dict(SECTORS)
