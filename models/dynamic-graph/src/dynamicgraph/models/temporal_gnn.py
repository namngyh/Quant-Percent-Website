r"""Temporal Graph Neural Network (advanced module, evaluated only after the
statistical baselines).

Architecture, deliberately small because there are 30 nodes and a few thousand
daily snapshots:

    h_i^(0)   = MLP(X_i,t)
    e_ij      = LeakyReLU(a^T [W h_i || W h_j || phi(A_ij)])
    alpha_ij  = softmax_j(e_ij)
    h_i^graph = sigma( sum_j alpha_ij W h_j )
    z_i,t     = GRU(h_i^graph, z_i,t-1)
    g_t       = sum_i gamma_i,t z_i,t                     (attention pooling)
    p_t       = sigmoid(W_g g_t + b_g)                    (graph-level stress)
    p_i,t     = sigmoid(W_n [z_i,t || g_t] + b_n)         (node-level downside)

Edge weights enter the attention through `phi`, so a strong partial correlation
can raise attention directly rather than only through connectivity.

torch-geometric is NOT required: the attention layer is implemented with dense
adjacency masking, which is efficient at N=30 and removes a heavy optional
dependency. If torch itself is missing, importing this module raises ImportError
and the pipeline records the skip.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except ImportError as exc:  # pragma: no cover - optional dependency
    raise ImportError(
        "Temporal GNN requires PyTorch. Install with `pip install -e .[gnn]`. "
        "The statistical pipeline and all baselines run without it."
    ) from exc

from dynamicgraph.models.losses import build_loss  # noqa: E402


class WeightedGraphAttention(nn.Module):
    """Dense masked graph attention that consumes edge weights."""

    def __init__(self, in_dim: int, out_dim: int, dropout: float = 0.2, negative_slope: float = 0.2) -> None:
        super().__init__()
        self.linear = nn.Linear(in_dim, out_dim, bias=False)
        self.attention_source = nn.Parameter(torch.empty(out_dim))
        self.attention_target = nn.Parameter(torch.empty(out_dim))
        self.edge_projection = nn.Linear(1, 1, bias=True)
        self.dropout = nn.Dropout(dropout)
        self.negative_slope = negative_slope
        nn.init.xavier_uniform_(self.linear.weight)
        nn.init.normal_(self.attention_source, std=0.1)
        nn.init.normal_(self.attention_target, std=0.1)

    def forward(self, x: torch.Tensor, adjacency: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """x: (B, N, F), adjacency: (B, N, N) -> ((B, N, out), attention)."""
        h = self.linear(x)                                     # (B, N, out)
        source = (h * self.attention_source).sum(-1)           # (B, N)
        target = (h * self.attention_target).sum(-1)           # (B, N)
        scores = source.unsqueeze(-1) + target.unsqueeze(-2)   # (B, N, N)
        scores = scores + self.edge_projection(adjacency.unsqueeze(-1)).squeeze(-1)
        scores = F.leaky_relu(scores, self.negative_slope)

        # Self-loops keep isolated nodes from producing NaN attention.
        eye = torch.eye(adjacency.size(-1), device=adjacency.device).unsqueeze(0)
        mask = (adjacency.abs() > 0) | (eye > 0)
        scores = scores.masked_fill(~mask, float("-inf"))
        attention = torch.softmax(scores, dim=-1)
        attention = torch.nan_to_num(attention, nan=0.0)
        attention = self.dropout(attention)
        return torch.bmm(attention, h), attention


class TemporalGNN(nn.Module):
    """Node encoder -> graph attention -> GRU -> attention pooling -> two heads."""

    def __init__(
        self,
        n_features: int,
        hidden_dim: int = 32,
        n_graph_layers: int = 1,
        dropout: float = 0.25,
        temporal_model: str = "GRU",
    ) -> None:
        super().__init__()
        self.hidden_dim = hidden_dim
        self.encoder = nn.Sequential(
            nn.Linear(n_features, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        self.graph_layers = nn.ModuleList(
            [WeightedGraphAttention(hidden_dim, hidden_dim, dropout) for _ in range(n_graph_layers)]
        )
        self.graph_norm = nn.LayerNorm(hidden_dim)
        if temporal_model.upper() == "GRU":
            self.temporal = nn.GRU(hidden_dim, hidden_dim, num_layers=1, batch_first=True)
        else:
            self.temporal = nn.LSTM(hidden_dim, hidden_dim, num_layers=1, batch_first=True)
        self.pool_attention = nn.Linear(hidden_dim, 1)
        self.dropout = nn.Dropout(dropout)
        self.graph_head = nn.Linear(hidden_dim, 1)
        self.node_head = nn.Linear(2 * hidden_dim, 1)
        self.last_attention: torch.Tensor | None = None

    def forward(
        self, x: torch.Tensor, adjacency: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """x: (B, T, N, F), adjacency: (B, T, N, N).

        Returns (graph logits (B,), node logits (B, N), graph embedding (B, H)).
        """
        B, T, N, _ = x.shape
        states = []
        for t in range(T):
            h = self.encoder(x[:, t])
            attention = None
            for layer in self.graph_layers:
                h_new, attention = layer(h, adjacency[:, t])
                h = F.elu(self.graph_norm(h_new)) + h        # residual
            states.append(h)
            self.last_attention = attention

        sequence = torch.stack(states, dim=1)                # (B, T, N, H)
        flat = sequence.permute(0, 2, 1, 3).reshape(B * N, T, self.hidden_dim)
        output, _ = self.temporal(flat)
        z = output[:, -1, :].reshape(B, N, self.hidden_dim)  # (B, N, H)
        z = self.dropout(z)

        gamma = torch.softmax(self.pool_attention(z).squeeze(-1), dim=-1)   # (B, N)
        g = torch.bmm(gamma.unsqueeze(1), z).squeeze(1)                     # (B, H)

        graph_logits = self.graph_head(g).squeeze(-1)
        node_logits = self.node_head(
            torch.cat([z, g.unsqueeze(1).expand(-1, N, -1)], dim=-1)
        ).squeeze(-1)
        return graph_logits, node_logits, g


@dataclass
class GNNDataset:
    """Aligned sequences of (features, adjacency) with graph-level labels."""

    features: np.ndarray       # (S, T, N, F)
    adjacency: np.ndarray      # (S, T, N, N)
    labels: np.ndarray         # (S,)
    dates: pd.DatetimeIndex
    nodes: list[str]
    feature_names: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.labels)


def build_gnn_dataset(
    series: Any,
    node_features: Any,
    labels: pd.Series,
    sequence_length: int = 20,
    feature_names: list[str] | None = None,
    max_features: int = 24,
) -> GNNDataset | None:
    """Assemble sequences from a snapshot series.

    Only nodes present in every snapshot of a sequence are used, so the tensor
    shape is constant. Features are the node-feature matrix at each snapshot
    date; missing values are filled with the cross-sectional median at that date
    (a within-date operation, so no look-ahead).
    """
    snapshots = list(series)
    if len(snapshots) < sequence_length + 10:
        logger.warning(
            "Not enough snapshots (%d) for sequence length %d.", len(snapshots), sequence_length
        )
        return None

    shared = set(snapshots[0].nodes)
    for snapshot in snapshots:
        shared &= set(snapshot.nodes)
    nodes = sorted(shared)
    if len(nodes) < 5:
        logger.warning("Too few nodes shared across snapshots (%d).", len(nodes))
        return None

    if feature_names is None:
        preferred = [
            "return_5d", "return_20d", "return_60d", "momentum_20d", "volatility_5d",
            "volatility_20d", "volatility_60d", "downside_volatility_20d", "current_drawdown",
            "max_drawdown_60d", "idiosyncratic_volatility", "rolling_beta_60d",
            "market_relative_strength_20d", "amihud_illiquidity", "log_turnover",
            "volume_zscore_20d", "skewness_60d", "excess_kurtosis_60d",
            "volatility_ratio_5_20", "recovery_ratio_60d", "short_term_reversal",
            "residual_return_5d", "days_since_peak", "zero_return_ratio_20d",
        ]
        feature_names = [f for f in preferred if f in node_features.frames][:max_features]
    if not feature_names:
        logger.warning("No usable node features for the GNN.")
        return None

    per_date: dict[pd.Timestamp, np.ndarray] = {}
    for snapshot in snapshots:
        matrix = node_features.matrix_at(snapshot.date, nodes, feature_names)
        matrix = matrix.fillna(matrix.median(numeric_only=True)).fillna(0.0)
        per_date[snapshot.date] = matrix.to_numpy(dtype=np.float32)

    adjacency_by_date: dict[pd.Timestamp, np.ndarray] = {}
    for snapshot in snapshots:
        frame = pd.DataFrame(snapshot.adjacency, index=snapshot.nodes, columns=snapshot.nodes)
        adjacency_by_date[snapshot.date] = frame.loc[nodes, nodes].to_numpy(dtype=np.float32)

    dates = [s.date for s in snapshots]
    features_out, adjacency_out, labels_out, dates_out = [], [], [], []
    for i in range(sequence_length - 1, len(dates)):
        window = dates[i - sequence_length + 1 : i + 1]
        target_date = dates[i]
        if target_date not in labels.index or pd.isna(labels.loc[target_date]):
            continue
        features_out.append(np.stack([per_date[d] for d in window]))
        adjacency_out.append(np.stack([adjacency_by_date[d] for d in window]))
        labels_out.append(float(labels.loc[target_date]))
        dates_out.append(target_date)

    if len(labels_out) < 50:
        logger.warning("Only %d GNN sequences could be built; skipping.", len(labels_out))
        return None

    logger.info(
        "GNN dataset: %d sequences, %d nodes, %d features, T=%d.",
        len(labels_out), len(nodes), len(feature_names), sequence_length,
    )
    return GNNDataset(
        features=np.stack(features_out),
        adjacency=np.stack(adjacency_out),
        labels=np.asarray(labels_out, dtype=np.float32),
        dates=pd.DatetimeIndex(dates_out),
        nodes=nodes,
        feature_names=feature_names,
    )


def _standardize(train: np.ndarray, *others: np.ndarray) -> list[np.ndarray]:
    """Standardise features using TRAINING statistics only."""
    mean = train.reshape(-1, train.shape[-1]).mean(axis=0)
    std = train.reshape(-1, train.shape[-1]).std(axis=0) + 1e-8
    return [((array - mean) / std).astype(np.float32) for array in (train, *others)]


def train_temporal_gnn(
    dataset: GNNDataset,
    train_idx: np.ndarray,
    validation_idx: np.ndarray,
    test_idx: np.ndarray,
    config: Any,
) -> dict[str, Any]:
    """Train one model on one fold and return the calibrated test predictions."""
    from dynamicgraph.models.calibration import calibrate, optimize_threshold
    from dynamicgraph.training.reproducibility import detect_device

    gnn = config.gnn
    seed = int(config.project.seed)
    torch.manual_seed(seed)
    np.random.seed(seed)
    device = torch.device(detect_device(str(gnn.device)))

    X_train, X_validation, X_test = _standardize(
        dataset.features[train_idx], dataset.features[validation_idx], dataset.features[test_idx]
    )
    to_tensor = lambda a: torch.from_numpy(np.asarray(a)).to(device)  # noqa: E731

    train_x, validation_x, test_x = to_tensor(X_train), to_tensor(X_validation), to_tensor(X_test)
    train_a = to_tensor(dataset.adjacency[train_idx])
    validation_a = to_tensor(dataset.adjacency[validation_idx])
    test_a = to_tensor(dataset.adjacency[test_idx])
    train_y = to_tensor(dataset.labels[train_idx])
    validation_y = dataset.labels[validation_idx]

    positives = float(train_y.sum().item())
    if positives < 5 or positives == len(train_y):
        return {"status": "skipped", "reason": "degenerate training labels"}
    pos_weight = (len(train_y) - positives) / max(positives, 1.0)

    model = TemporalGNN(
        n_features=dataset.features.shape[-1],
        hidden_dim=int(gnn.hidden_dimension),
        n_graph_layers=int(gnn.n_graph_layers),
        dropout=float(gnn.dropout),
        temporal_model=str(gnn.temporal_model),
    ).to(device)

    optimizer = torch.optim.AdamW(
        model.parameters(), lr=float(gnn.learning_rate), weight_decay=float(gnn.weight_decay)
    )
    loss_fn = build_loss(str(gnn.loss), gamma=float(gnn.focal_gamma), pos_weight=pos_weight)

    batch_size = int(gnn.batch_size)
    best_loss, best_state, patience = float("inf"), None, 0
    n_train = len(train_idx)

    for epoch in range(int(gnn.max_epochs)):
        model.train()
        permutation = torch.randperm(n_train, device=device)
        for start in range(0, n_train, batch_size):
            batch = permutation[start : start + batch_size]
            optimizer.zero_grad()
            logits, _, _ = model(train_x[batch], train_a[batch])
            loss = loss_fn(logits, train_y[batch])
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), float(gnn.gradient_clip_norm))
            optimizer.step()

        model.eval()
        with torch.no_grad():
            validation_logits, _, _ = model(validation_x, validation_a)
            validation_loss = float(
                F.binary_cross_entropy_with_logits(
                    validation_logits, torch.from_numpy(validation_y).to(device)
                ).item()
            )
        if validation_loss < best_loss - 1e-5:
            best_loss, patience = validation_loss, 0
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        else:
            patience += 1
            if patience >= int(gnn.early_stopping_patience):
                logger.info("GNN early stopping at epoch %d (val loss %.5f).", epoch, best_loss)
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        validation_probabilities = torch.sigmoid(model(validation_x, validation_a)[0]).cpu().numpy()
        test_probabilities = torch.sigmoid(model(test_x, test_a)[0]).cpu().numpy()
        attention = model.last_attention.cpu().numpy() if model.last_attention is not None else None

    # Calibrate on validation, exactly like the tabular baselines.
    class _Wrapper:
        def __init__(self, probabilities: np.ndarray) -> None:
            self.probabilities = probabilities

        def predict_proba(self, X: Any) -> np.ndarray:
            return np.column_stack([1 - self.probabilities, self.probabilities])

    calibrated = calibrate(
        _Wrapper(validation_probabilities),
        np.zeros((len(validation_probabilities), 1)),
        validation_y,
        method=str(config.models.calibration_method),
    )
    if calibrated.calibrator is not None:
        if calibrated.method == "isotonic":
            test_calibrated = np.clip(calibrated.calibrator.predict(test_probabilities), 1e-6, 1 - 1e-6)
        else:
            test_calibrated = calibrated.calibrator.predict_proba(test_probabilities.reshape(-1, 1))[:, 1]
    else:
        test_calibrated = test_probabilities

    threshold, _ = optimize_threshold(
        validation_probabilities, validation_y,
        objective=str(config.evaluation.decision_threshold_objective),
        fixed=float(config.evaluation.fixed_threshold),
    )

    return {
        "status": "ok",
        "test_probabilities": test_calibrated,
        "test_dates": dataset.dates[test_idx],
        "test_labels": dataset.labels[test_idx],
        "threshold": float(threshold),
        "calibration_method": calibrated.method,
        "best_validation_loss": best_loss,
        "n_parameters": int(sum(p.numel() for p in model.parameters())),
        "attention": attention,
        "device": str(device),
    }


def run_temporal_gnn_experiment(state: Any) -> dict[str, Any]:
    """Walk-forward the GNN on the core graph and compare it to the best baseline."""
    from dynamicgraph.evaluation.bootstrap import paired_bootstrap_difference
    from dynamicgraph.evaluation.classification import classification_metrics
    from dynamicgraph.features.targets import label_by_train_quantile

    config = state.config
    core_key = state.core_key if state.core_key in state.series_by_key else next(iter(state.series_by_key))
    series = state.series_by_key[core_key]

    horizon = int(config.targets.horizons[len(config.targets.horizons) // 2])
    forward_column = f"future_drawdown_{horizon}d"
    if forward_column not in state.targets.forward.columns:
        return {"status": "skipped", "reason": f"{forward_column} unavailable"}

    if not state.folds:
        return {"status": "skipped", "reason": "no walk-forward folds"}

    sequence_length = int(config.gnn.sequence_length)
    forward_values = state.targets.forward[forward_column]

    # Labels use the first fold's training block for the quantile, so the label
    # definition itself is fixed on training data before any GNN sees it.
    first_train_mask = state.folds[0].mask("train").reindex(forward_values.index, fill_value=False)
    labels, label_threshold = label_by_train_quantile(
        forward_values, first_train_mask, float(config.targets.stress_quantile), "lower"
    )

    dataset = build_gnn_dataset(series, state.node_features, labels, sequence_length)
    if dataset is None:
        return {"status": "skipped", "reason": "insufficient data to build GNN sequences"}

    date_to_position = {d: i for i, d in enumerate(dataset.dates)}
    all_probabilities, all_labels, all_dates = [], [], []
    fold_reports = []

    for fold in state.folds:
        train_idx = np.array([date_to_position[d] for d in fold.train_dates if d in date_to_position])
        validation_idx = np.array([date_to_position[d] for d in fold.validation_dates if d in date_to_position])
        test_idx = np.array([date_to_position[d] for d in fold.test_dates if d in date_to_position])
        if len(train_idx) < 100 or len(validation_idx) < 20 or len(test_idx) < 5:
            continue
        try:
            result = train_temporal_gnn(dataset, train_idx, validation_idx, test_idx, config)
        except Exception as exc:
            logger.warning("GNN fold %d failed: %s", fold.fold_id, exc)
            continue
        if result.get("status") != "ok":
            continue
        all_probabilities.append(result["test_probabilities"])
        all_labels.append(result["test_labels"])
        all_dates.append(result["test_dates"])
        fold_reports.append(
            {
                "fold": fold.fold_id,
                "n_test": len(test_idx),
                "best_validation_loss": result["best_validation_loss"],
                "calibration_method": result["calibration_method"],
                "n_parameters": result["n_parameters"],
            }
        )

    if not all_probabilities:
        return {"status": "skipped", "reason": "no fold produced GNN predictions"}

    probabilities = np.concatenate(all_probabilities)
    y = np.concatenate(all_labels)
    dates = pd.DatetimeIndex(np.concatenate([d.to_numpy() for d in all_dates]))
    metrics = classification_metrics(y, probabilities, threshold=0.5, n_days=len(y))

    predictions = pd.DataFrame(
        {"date": dates, "probability": probabilities, "y_true": y, "model": "temporal_gnn",
         "horizon": horizon}
    ).sort_values("date")
    predictions.to_csv(config.artifact_path("predictions", "gnn_predictions.csv"), index=False)

    # Fair comparison against the best baseline on the SAME dates.
    comparison: dict[str, Any] = {}
    experiment = state.experiment
    if experiment is not None and not experiment.metrics.empty:
        subset = experiment.metrics[
            (experiment.metrics["horizon"] == horizon)
            & (experiment.metrics["model"] != "naive_frequency")
        ].dropna(subset=["brier"])
        if not subset.empty:
            best = subset.loc[subset["brier"].idxmin()]
            key = f"{best['target']}__{best['feature_set']}__{best['model']}"
            baseline = experiment.results.get(key)
            if baseline is not None and not baseline.predictions.empty:
                from sklearn.metrics import brier_score_loss

                merged = predictions.merge(baseline.predictions, on="date", suffixes=("_gnn", "_base"))
                if len(merged) >= 50:
                    test = paired_bootstrap_difference(
                        merged["y_true_gnn"].to_numpy(),
                        merged["probability_base"].to_numpy(),
                        merged["probability_gnn"].to_numpy(),
                        metric_fn=brier_score_loss,
                        n_bootstrap=int(config.evaluation.bootstrap_iterations),
                        block_length=int(config.evaluation.bootstrap_block_length),
                        seed=int(config.project.seed),
                        higher_is_better=False,
                    )
                    # `difference` = baseline Brier - GNN Brier; positive means
                    # the GNN is better (lower Brier).
                    gnn_better = test["difference"] > 0 and test["significant"]
                    comparison = {
                        "baseline_key": key,
                        "baseline_brier": test["metric_a"],
                        "gnn_brier": test["metric_b"],
                        "difference": test["difference"],
                        "ci_lower": test["lower"],
                        "ci_upper": test["upper"],
                        "n_shared": len(merged),
                        "gnn_beats_baseline": bool(gnn_better),
                        "verdict": (
                            "Temporal GNN significantly outperformed the best tabular baseline."
                            if gnn_better else
                            "Temporal GNN did NOT significantly outperform the best tabular "
                            "baseline. The baseline remains the reference model and the GNN output "
                            "must not be published as an improvement."
                        ),
                    }

    logger.info(
        "Temporal GNN: %d OOS predictions, Brier %.4f, AUPRC %.4f. %s",
        len(y), metrics.get("brier", float("nan")), metrics.get("auprc", float("nan")),
        comparison.get("verdict", "No baseline comparison was possible."),
    )
    return {
        "status": "ok",
        "horizon": horizon,
        "sequence_length": sequence_length,
        "label_threshold": float(label_threshold),
        "n_predictions": int(len(y)),
        "metrics": metrics,
        "folds": fold_reports,
        "comparison_vs_baseline": comparison,
        "attention_disclaimer": (
            "Attention weights are a model diagnostic. They do not measure influence between "
            "companies and are not a causal explanation."
        ),
    }
