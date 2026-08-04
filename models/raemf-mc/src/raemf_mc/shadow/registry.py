"""Immutable forecast fields with maturity-gated prospective scoring."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


IMMUTABLE_COLUMNS = [
    "forecast_origin",
    "origin_close",
    "horizon",
    "model_version",
    "git_sha",
    "data_checksum",
    "config_checksum",
    "prob_bull",
    "prob_sideway",
    "prob_bear",
    "prob_stress",
    "risk_off_probability",
    "threshold",
    "alert_state",
    "prob_drawdown_5",
    "prob_drawdown_10",
    "prob_drawdown_15",
    "prob_drawdown_20",
    "var_95",
    "cvar_95",
    "maturity_date",
]

REGISTRY_COLUMNS = IMMUTABLE_COLUMNS + [
    "forecast_hash",
    "status",
    "realized_return",
    "realized_mae",
    "realized_max_drawdown",
    "scoring_timestamp",
]


def _forecast_hash(row: pd.Series) -> str:
    payload = {
        column: (
            pd.Timestamp(row[column]).isoformat()
            if column in {"forecast_origin", "maturity_date"}
            else row[column]
        )
        for column in IMMUTABLE_COLUMNS
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(IMMUTABLE_COLUMNS) - set(frame.columns))
    if missing:
        raise ValueError(f"Forecast registry rows missing immutable fields: {missing}")
    output = frame.copy()
    output["forecast_origin"] = pd.to_datetime(output["forecast_origin"])
    output["maturity_date"] = pd.to_datetime(output["maturity_date"])
    probability_columns = ["prob_bull", "prob_sideway", "prob_bear", "prob_stress"]
    if not np.allclose(output[probability_columns].sum(axis=1), 1.0, atol=1e-6):
        raise ValueError("Four-class probabilities must sum to one")
    for column in probability_columns + [
        "risk_off_probability",
        "prob_drawdown_5",
        "prob_drawdown_10",
        "prob_drawdown_15",
        "prob_drawdown_20",
    ]:
        if not output[column].astype(float).between(0, 1).all():
            raise ValueError(f"{column} must be inside [0, 1]")
    output["forecast_hash"] = output.apply(_forecast_hash, axis=1)
    output["status"] = "pending"
    output["realized_return"] = np.nan
    output["realized_mae"] = np.nan
    output["realized_max_drawdown"] = np.nan
    output["scoring_timestamp"] = ""
    return output[REGISTRY_COLUMNS]


def append_forecasts(path: str | Path, forecasts: pd.DataFrame) -> pd.DataFrame:
    """Append new origins; reject any attempt to rewrite an existing forecast."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    incoming = _normalize(forecasts)
    if destination.exists():
        existing = pd.read_csv(destination, parse_dates=["forecast_origin", "maturity_date"])
        for _, row in existing.iterrows():
            if _forecast_hash(row) != row["forecast_hash"]:
                raise ValueError("Existing registry failed immutable forecast hash verification")
        key_columns = ["forecast_origin", "horizon", "model_version"]
        merged_keys = existing[key_columns].merge(incoming[key_columns], on=key_columns)
        if not merged_keys.empty:
            existing_map = existing.set_index(key_columns)["forecast_hash"]
            incoming_map = incoming.set_index(key_columns)["forecast_hash"]
            for key in merged_keys.itertuples(index=False, name=None):
                if existing_map.loc[key] != incoming_map.loc[key]:
                    raise ValueError(f"Attempted mutation of existing forecast key={key}")
            incoming = incoming.loc[
                ~pd.MultiIndex.from_frame(incoming[key_columns]).isin(pd.MultiIndex.from_frame(existing[key_columns]))
            ]
        combined = pd.concat([existing, incoming], ignore_index=True)
    else:
        combined = incoming
    combined = combined.sort_values(["forecast_origin", "horizon", "model_version"]).reset_index(drop=True)
    combined.to_csv(destination, index=False)
    return combined


def mature_forecasts(
    path: str | Path,
    prices: pd.DataFrame,
    *,
    scoring_timestamp: str | None = None,
) -> pd.DataFrame:
    """Fill realized fields only after h strictly future market sessions exist."""
    destination = Path(path)
    if not destination.exists():
        raise FileNotFoundError(destination)
    registry = pd.read_csv(destination, parse_dates=["forecast_origin", "maturity_date"])
    registry["scoring_timestamp"] = registry["scoring_timestamp"].fillna("").astype(str)
    price_frame = prices[["date", "close"]].copy()
    price_frame["date"] = pd.to_datetime(price_frame["date"])
    price_frame = price_frame.sort_values("date").drop_duplicates("date", keep="last")
    timestamp = scoring_timestamp or datetime.now(timezone.utc).isoformat()
    for index, row in registry.loc[registry["status"] == "pending"].iterrows():
        future = price_frame.loc[price_frame["date"] > row["forecast_origin"]].head(int(row["horizon"]))
        if len(future) < int(row["horizon"]):
            continue
        origin_close = float(row["origin_close"])
        levels = np.r_[origin_close, future["close"].to_numpy(dtype=float)]
        log_path = np.log(levels[1:] / origin_close)
        running_peak = np.maximum.accumulate(levels)
        drawdown = levels / running_peak - 1.0
        registry.loc[index, "status"] = "matured"
        registry.loc[index, "realized_return"] = float(np.log(levels[-1] / origin_close))
        registry.loc[index, "realized_mae"] = float(log_path.min())
        registry.loc[index, "realized_max_drawdown"] = float(drawdown.min())
        registry.loc[index, "scoring_timestamp"] = timestamp
    for _, row in registry.iterrows():
        if _forecast_hash(row) != row["forecast_hash"]:
            raise AssertionError("Maturity scoring modified immutable forecast fields")
    registry.to_csv(destination, index=False)
    return registry
