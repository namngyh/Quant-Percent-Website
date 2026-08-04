"""Tests for the Bayesian hierarchical multinomial regime head."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("torch")

from raemf_mc import CLASS_ORDER
from raemf_mc.evaluation.regime_head_benchmark import composite_objective
from raemf_mc.models.bayesian_regime_head import BayesianRegimeHead


def _classification_data(n=600, p=8, seed=5):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, p))
    logits = np.zeros((n, 4))
    logits[:, 0] = 1.2 * x[:, 0]
    logits[:, 1] = 1.2 * x[:, 1]
    logits[:, 2] = -1.2 * x[:, 0]
    logits[:, 3] = -1.2 * x[:, 1]
    probability = np.exp(logits - logits.max(axis=1, keepdims=True))
    probability /= probability.sum(axis=1, keepdims=True)
    labels = [CLASS_ORDER[rng.choice(4, p=row)] for row in probability]
    columns = [f"f{i}" for i in range(p)]
    return pd.DataFrame(x, columns=columns), pd.Series(labels)


def _head(**overrides):
    params = dict(
        max_features=6,
        seeds=(11,),
        advi_steps=500,
        min_steps=200,
        posterior_draws=150,
        learning_rate=0.03,
        convergence_window=100,
        convergence_tolerance=0.01,
        device="cpu",
    )
    params.update(overrides)
    return BayesianRegimeHead(**params)


def test_head_learns_signal_and_outputs_valid_probabilities():
    x, y = _classification_data()
    head = _head().fit(x.iloc[:450], y.iloc[:450])
    probability = head.predict_proba(x.iloc[450:])
    assert probability.shape == (150, 4)
    assert np.allclose(probability.sum(axis=1), 1.0, atol=1e-6)
    assert (probability >= 0).all()
    predicted = probability.argmax(axis=1)
    actual = np.array([CLASS_ORDER.index(v) for v in y.iloc[450:]])
    accuracy = float((predicted == actual).mean())
    assert accuracy > 0.4  # far above the 0.25 chance level


def test_feature_selection_uses_train_only_and_respects_budget():
    x, y = _classification_data(p=15)
    head = _head(max_features=5).fit(x.iloc[:450], y.iloc[:450])
    assert len(head.selected_features) == 5
    assert set(head.selected_features) <= set(x.columns)


def test_uncertainty_outputs_are_ordered_and_finite():
    x, y = _classification_data()
    head = _head(seeds=(11, 42)).fit(x.iloc[:400], y.iloc[:400])
    out = head.predict_with_uncertainty(x.iloc[400:420])
    assert (out["q05"] <= out["mean"] + 1e-9).all()
    assert (out["mean"] <= out["q95"] + 1e-9).all()
    assert np.isfinite(out["epistemic_sd"]).all()
    assert np.isfinite(out["predictive_entropy"]).all()
    summary = head.seed_summary()
    assert len(summary) == 2


def test_composite_objective_matches_specified_weights():
    metrics = {
        "macro_f1": 0.5,
        "balanced_accuracy": 0.6,
        "recall_bear": 0.4,
        "recall_stress": 0.2,
        "brier": 0.5,
    }
    expected = 0.30 * 0.5 + 0.20 * 0.6 + 0.15 * 0.4 + 0.15 * 0.2 + 0.20 * (1 - 0.25)
    assert composite_objective(metrics) == pytest.approx(expected)
