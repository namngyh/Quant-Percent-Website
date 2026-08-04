r"""Network Stress Score (0-100).

Two versions, kept strictly separate:

**Descriptive** (`DescriptiveStressScore`)
    Robust-standardised aggregation of network metrics. Location and scale come
    from the TRAINING period only:

        z_{k,t} = clip((m_{k,t} - median_k^train) / (1.4826 MAD_k^train + eps), -3, 3)
        S_t^raw = sum_k w_k z_{k,t}
        Score_t = 100 * sigmoid(S_t^raw)

    Signs are aligned so that larger always means more stressed, and metrics
    that are near-duplicates (|corr| > threshold on training data) are dropped
    before equal-weighting so the score is not silently dominated by whichever
    quantity happens to be measured five different ways.

**Predictive** (`models.combined_model`)
    Weights learned by a calibrated classifier against a *future* stress target.
    That lives in the models package because it needs the walk-forward
    machinery; this module only produces the descriptive score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from dynamicgraph.constants import EPS, NETWORK_STATE_LABELS
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


def sigmoid(x: np.ndarray | pd.Series) -> np.ndarray | pd.Series:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50, 50)))


@dataclass
class DescriptiveStressScore:
    """Fit-on-train / apply-everywhere descriptive stress score."""

    metrics: list[str]
    signs: dict[str, int] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    clip_z: float = 3.0
    redundancy_threshold: float = 0.95
    center: dict[str, float] = field(default_factory=dict)
    scale: dict[str, float] = field(default_factory=dict)
    dropped_metrics: list[str] = field(default_factory=list)
    used_metrics: list[str] = field(default_factory=list)
    raw_quantiles: dict[str, float] = field(default_factory=dict)
    fitted: bool = False

    # -- fitting ---------------------------------------------------------
    def fit(self, metric_frame: pd.DataFrame, train_mask: pd.Series | None = None) -> "DescriptiveStressScore":
        """Estimate robust location/scale and prune redundant metrics.

        `train_mask` MUST be supplied for any evaluation that will be reported
        out-of-sample; without it the whole sample is used and the score is
        in-sample only (a warning is logged).
        """
        available = [m for m in self.metrics if m in metric_frame.columns]
        missing = [m for m in self.metrics if m not in metric_frame.columns]
        if missing:
            logger.warning("Stress-score metrics absent from the graph metrics: %s", missing)

        if train_mask is None:
            logger.warning(
                "DescriptiveStressScore.fit called without a training mask; the score will be "
                "standardised in-sample and must not be presented as an OOS quantity."
            )
            train = metric_frame[available]
        else:
            train = metric_frame.loc[train_mask.reindex(metric_frame.index, fill_value=False), available]

        train = train.replace([np.inf, -np.inf], np.nan)
        usable = [m for m in available if train[m].notna().sum() >= 30]
        if len(usable) < len(available):
            logger.warning(
                "Dropping stress metrics with <30 training observations: %s",
                sorted(set(available) - set(usable)),
            )

        # Prune near-duplicates, keeping the first occurrence in config order.
        signed_train = pd.DataFrame(
            {m: train[m] * float(self.signs.get(m, 1)) for m in usable}, index=train.index
        )
        correlation = signed_train.corr(method="spearman").abs()
        keep: list[str] = []
        dropped: list[str] = []
        for metric in usable:
            if any(
                correlation.loc[metric, existing] > self.redundancy_threshold
                for existing in keep
                if pd.notna(correlation.loc[metric, existing])
            ):
                dropped.append(metric)
            else:
                keep.append(metric)
        if dropped:
            logger.info(
                "Stress score: dropped %d redundant metric(s) (|rho| > %.2f): %s",
                len(dropped),
                self.redundancy_threshold,
                dropped,
            )

        self.used_metrics = keep
        self.dropped_metrics = dropped
        self.center = {m: float(train[m].median()) for m in keep}
        self.scale = {
            m: float(1.4826 * (train[m] - train[m].median()).abs().median() + EPS) for m in keep
        }
        for metric, scale in self.scale.items():
            if scale <= 10 * EPS:
                self.scale[metric] = float(train[metric].std(ddof=1) + EPS)

        if not self.weights or self.weights == "equal":
            self.weights = {m: 1.0 / max(len(keep), 1) for m in keep}
        else:
            total = sum(abs(self.weights.get(m, 0.0)) for m in keep)
            self.weights = (
                {m: self.weights.get(m, 0.0) / total for m in keep}
                if total > 0
                else {m: 1.0 / max(len(keep), 1) for m in keep}
            )

        raw_train = self._raw(metric_frame.loc[train.index])
        self.raw_quantiles = {
            f"q{int(q * 100)}": float(raw_train.quantile(q))
            for q in (0.05, 0.25, 0.50, 0.75, 0.80, 0.95, 0.99)
        }
        self.fitted = True
        logger.info("Descriptive stress score fitted on %d training rows, %d metric(s).", len(train), len(keep))
        return self

    # -- application -------------------------------------------------------
    def _z(self, metric_frame: pd.DataFrame) -> pd.DataFrame:
        parts = {}
        for metric in self.used_metrics:
            sign = float(self.signs.get(metric, 1))
            z = (metric_frame[metric] - self.center[metric]) / self.scale[metric]
            parts[metric] = (sign * z).clip(-self.clip_z, self.clip_z)
        return pd.DataFrame(parts, index=metric_frame.index)

    def _raw(self, metric_frame: pd.DataFrame) -> pd.Series:
        z = self._z(metric_frame)
        weights = pd.Series({m: self.weights[m] for m in self.used_metrics})
        # Renormalise per row over the metrics actually observed at that date.
        mask = z.notna()
        effective = mask.mul(weights, axis=1)
        denominator = effective.sum(axis=1).replace(0.0, np.nan)
        return (z.fillna(0.0) * effective).sum(axis=1) / denominator

    def transform(self, metric_frame: pd.DataFrame) -> pd.DataFrame:
        """Return raw score, 0-100 score, historical percentile and contributions."""
        if not self.fitted:
            raise RuntimeError("DescriptiveStressScore must be fitted before transform().")

        z = self._z(metric_frame)
        raw = self._raw(metric_frame)
        # sigmoid(raw) saturates for |raw| > 4; scale so that a +-3 sigma
        # composite maps to roughly 5..95 rather than 0..100.
        score = 100.0 * sigmoid(2.0 * raw)

        out = pd.DataFrame(
            {
                "stress_raw": raw,
                "stress_score": score,
                "stress_percentile": raw.expanding(min_periods=60).rank(pct=True),
            },
            index=metric_frame.index,
        )
        for window in (1, 5, 20):
            out[f"stress_change_{window}d"] = out["stress_score"].diff(window)

        weights = pd.Series({m: self.weights[m] for m in self.used_metrics})
        contributions = z.mul(weights, axis=1)
        for metric in self.used_metrics:
            out[f"contrib_{metric}"] = contributions[metric]
        return out

    def classify_state(
        self,
        scores: pd.DataFrame,
        percentiles: Iterable[float] = (0.50, 0.80, 0.95),
        labels: Iterable[str] = tuple(NETWORK_STATE_LABELS),
        train_mask: pd.Series | None = None,
    ) -> pd.Series:
        """Map the raw score onto discrete network states using TRAINING quantiles."""
        percentiles = list(percentiles)
        labels = list(labels)
        if len(labels) != len(percentiles) + 1:
            raise ValueError("`labels` must have exactly one more entry than `percentiles`.")

        reference = (
            scores.loc[train_mask.reindex(scores.index, fill_value=False), "stress_raw"]
            if train_mask is not None
            else scores["stress_raw"]
        )
        cutoffs = [float(reference.quantile(p)) for p in percentiles]
        bins = [-np.inf] + cutoffs + [np.inf]
        return pd.cut(scores["stress_raw"], bins=bins, labels=labels, include_lowest=True).astype(str)

    def contribution_table(self, scores: pd.DataFrame, date: pd.Timestamp) -> pd.DataFrame:
        """Per-metric contribution to the score on one date, largest first."""
        columns = [c for c in scores.columns if c.startswith("contrib_")]
        row = scores.loc[date, columns]
        frame = pd.DataFrame(
            {
                "metric": [c.replace("contrib_", "") for c in columns],
                "contribution": row.to_numpy(dtype=float),
            }
        )
        frame["abs_contribution"] = frame["contribution"].abs()
        total = frame["abs_contribution"].sum()
        frame["share"] = frame["abs_contribution"] / total if total > 0 else np.nan
        return frame.sort_values("abs_contribution", ascending=False).reset_index(drop=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "used_metrics": self.used_metrics,
            "dropped_metrics": self.dropped_metrics,
            "signs": {m: int(self.signs.get(m, 1)) for m in self.used_metrics},
            "weights": {m: float(self.weights[m]) for m in self.used_metrics},
            "center": self.center,
            "scale": self.scale,
            "clip_z": self.clip_z,
            "raw_quantiles": self.raw_quantiles,
            "note": (
                "Descriptive score: robust z-scores of network metrics, standardised on the "
                "training period only, equal-weighted after removing near-duplicates. It is a "
                "description of current network structure, NOT a forecast."
            ),
        }


def build_descriptive_stress_score(
    metric_frame: pd.DataFrame,
    config: Any,
    train_mask: pd.Series | None = None,
) -> tuple[DescriptiveStressScore, pd.DataFrame, pd.Series]:
    """Fit and apply the descriptive score. Returns (model, scores, states)."""
    cfg = config.stress_score
    weights = cfg.weights if isinstance(cfg.weights, Mapping) else {}
    model = DescriptiveStressScore(
        metrics=list(cfg.metrics),
        signs={k: int(v) for k, v in (cfg.signs or {}).items()},
        weights=dict(weights),
        clip_z=float(cfg.clip_z),
        redundancy_threshold=float(cfg.redundancy_corr_threshold),
    )
    model.fit(metric_frame, train_mask)
    scores = model.transform(metric_frame)
    states = model.classify_state(
        scores,
        percentiles=cfg.state_percentiles,
        labels=cfg.state_labels,
        train_mask=train_mask,
    )
    scores["network_state"] = states
    return model, scores, states
