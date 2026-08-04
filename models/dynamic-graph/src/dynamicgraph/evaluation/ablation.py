"""Ablation study.

Each variant is a restriction of the feature space; everything else (folds,
model, calibration, thresholds) is held fixed so the difference is attributable
to the removed feature family. Results are reported as deltas against the
market-only baseline.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.logging_config import get_logger
from dynamicgraph.models.baselines import build_model_zoo
from dynamicgraph.models.registry import ABLATION_VARIANTS, FeatureSetBuilder, apply_variant_filters
from dynamicgraph.training.splits import Fold
from dynamicgraph.training.walk_forward import run_walk_forward

logger = get_logger(__name__)


class _StaticFrameBuilder:
    """Adapter so a pre-filtered frame can be fed to `run_walk_forward`."""

    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def build(self, *_: Any, **__: Any) -> pd.DataFrame:
        return self.frame


def run_ablation(
    builder: FeatureSetBuilder,
    forward_values: pd.DataFrame,
    folds: list[Fold],
    config: Any,
    horizon: int | None = None,
    model_name: str | None = None,
    variants: list[str] | None = None,
) -> pd.DataFrame:
    """Run the configured ablation variants for one horizon and one model."""
    horizon = horizon or int(config.targets.horizons[len(config.targets.horizons) // 2])
    variants = variants or list(config.ablation.variants)
    zoo = build_model_zoo(config, "classification")

    if model_name is None:
        for candidate in ("hist_gradient_boosting", "logistic_elasticnet", "logistic_l2"):
            if candidate in zoo:
                model_name = candidate
                break
    if model_name not in zoo:
        logger.warning("Ablation model `%s` unavailable; skipping ablation.", model_name)
        return pd.DataFrame()
    spec = zoo[model_name]

    forward_column = f"future_drawdown_{horizon}d"
    if forward_column not in forward_values.columns:
        logger.warning("Ablation skipped: %s missing.", forward_column)
        return pd.DataFrame()
    target_values = forward_values[forward_column]
    quantile = float(config.targets.stress_quantile)

    rows: list[dict[str, Any]] = []
    skipped: list[str] = []
    for variant in variants:
        spec_dict = ABLATION_VARIANTS.get(variant)
        if spec_dict is None:
            logger.warning("Unknown ablation variant `%s`; skipping.", variant)
            continue
        try:
            base_set = spec_dict["feature_set"]
            kwargs: dict[str, Any] = {}
            if "exclude_groups" in spec_dict:
                kwargs["exclude_groups"] = spec_dict["exclude_groups"]
            frame = builder.build(base_set, **kwargs) if base_set != "market" else builder.build("market")
            frame = apply_variant_filters(frame, spec_dict)
        except Exception as exc:
            logger.warning("Ablation variant `%s` failed to build features: %s", variant, exc)
            continue

        if frame.empty or frame.shape[1] == 0:
            logger.info(
                "Ablation variant `%s` produced no usable features (the required layer or scale "
                "was not built in this run); skipping rather than reporting a fallback result.",
                variant,
            )
            skipped.append(variant)
            continue

        result = run_walk_forward(
            features=frame,
            target_values=target_values,
            folds=folds,
            model_spec=spec,
            config=config,
            horizon=horizon,
            target_name=f"ablation_{variant}",
            feature_set=variant,
            quantile=quantile,
        )
        if result.predictions.empty:
            continue
        metrics = result.oos_metrics()
        metrics.update(
            {
                "variant": variant,
                # Candidate space vs what the fold-local selector actually kept.
                "n_features_candidate": frame.shape[1],
                "n_features": result.n_features_selected,
                "model": model_name,
            }
        )
        rows.append(metrics)

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    baseline = frame[frame["variant"] == "market_only"]
    if not baseline.empty:
        base_brier = float(baseline["brier"].iloc[0])
        base_auprc = float(baseline["auprc"].iloc[0])
        frame["brier_vs_market_only"] = frame["brier"] - base_brier
        frame["auprc_vs_market_only"] = frame["auprc"] - base_auprc
        frame["improves_brier"] = frame["brier_vs_market_only"] < 0

    frame = frame.sort_values("brier").reset_index(drop=True)
    frame.attrs["skipped_variants"] = skipped
    logger.info(
        "Ablation complete: %d variant(s) evaluated at horizon %d.%s",
        len(frame),
        horizon,
        f" Skipped as unavailable: {skipped}." if skipped else "",
    )
    return frame


def feature_group_contributions(ablation: pd.DataFrame) -> pd.DataFrame:
    """Marginal cost of removing each feature family, from the `no_*` variants."""
    if ablation.empty or "variant" not in ablation.columns:
        return pd.DataFrame()

    full = ablation[ablation["variant"] == "market_plus_graph"]
    if full.empty:
        return pd.DataFrame()
    full_brier = float(full["brier"].iloc[0])
    full_auprc = float(full["auprc"].iloc[0])

    rows = []
    for _, row in ablation.iterrows():
        variant = str(row["variant"])
        if not variant.startswith("no_"):
            continue
        rows.append(
            {
                "removed_group": variant.replace("no_", "").replace("_features", ""),
                "brier_without": row["brier"],
                "brier_with_all": full_brier,
                # Positive = removing the group made things worse = the group helped.
                "brier_degradation": row["brier"] - full_brier,
                "auprc_without": row["auprc"],
                "auprc_with_all": full_auprc,
                "auprc_degradation": full_auprc - row["auprc"],
                "n_features": row.get("n_features"),
            }
        )
    frame = pd.DataFrame(rows)
    return frame.sort_values("brier_degradation", ascending=False).reset_index(drop=True) if not frame.empty else frame
