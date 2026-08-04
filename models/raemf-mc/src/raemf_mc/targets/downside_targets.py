"""Non-exclusive downside targets derived from the frozen four-class labels."""

from __future__ import annotations

import numpy as np
import pandas as pd

from raemf_mc import HORIZONS


DOWNSIDE_TARGET_PREFIXES = (
    "risk_off_",
    "negative_terminal_",
    "stress_path_",
    "drawdown_5_",
    "drawdown_10_",
)


def create_downside_targets(
    targeted: pd.DataFrame,
    horizons: list[int] | None = None,
    *,
    bear_threshold: float = 0.5,
    stress_threshold: float = 1.5,
) -> pd.DataFrame:
    """Add binary downside events without changing the four-class target.

    The input must already contain the causal scale and forward quantities made
    by :func:`create_multihorizon_targets`. The binary events are intentionally
    non-exclusive: a row can be both ``negative_terminal`` and ``stress_path``.
    """
    horizons = horizons or HORIZONS
    out = targeted.copy()
    for horizon in horizons:
        required = {
            "target_sigma",
            f"target_{horizon}",
            f"forward_return_{horizon}",
            f"future_mae_{horizon}",
            f"target_end_date_{horizon}",
        }
        missing = sorted(required - set(out.columns))
        if missing:
            raise KeyError(f"Missing multiclass target columns for h={horizon}: {missing}")
        denom = out["target_sigma"].astype(float) * np.sqrt(horizon) + 1e-9
        forward_return = out[f"forward_return_{horizon}"].astype(float)
        future_mae = out[f"future_mae_{horizon}"].astype(float)
        valid = (
            forward_return.notna()
            & future_mae.notna()
            & out[f"target_end_date_{horizon}"].notna()
        )
        values = {
            f"risk_off_{horizon}": out[f"target_{horizon}"].astype("string").isin(["Bear", "Stress"]),
            f"negative_terminal_{horizon}": forward_return < (-bear_threshold * denom),
            f"stress_path_{horizon}": future_mae < (-stress_threshold * denom),
            f"drawdown_5_{horizon}": future_mae <= np.log(0.95),
            f"drawdown_10_{horizon}": future_mae <= np.log(0.90),
        }
        for column, event in values.items():
            series = pd.Series(pd.NA, index=out.index, dtype="Int8")
            series.loc[valid] = event.loc[valid].astype("int8")
            out[column] = series
    return out


def downside_target_columns(horizons: list[int] | None = None) -> list[str]:
    """Return target columns that must never enter any feature matrix."""
    horizons = horizons or HORIZONS
    return [f"{prefix}{horizon}" for horizon in horizons for prefix in DOWNSIDE_TARGET_PREFIXES]
