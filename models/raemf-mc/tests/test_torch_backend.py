"""Tests for the GPU-first PyTorch ADVI backend (run on CPU for portability)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch")

from raemf_mc.bayesian import torch_backend  # noqa: E402
from raemf_mc.bayesian.model import TorchVariationalScenarioModel  # noqa: E402
from raemf_mc.bayesian.priors import ScenarioPriors  # noqa: E402
from raemf_mc.bayesian.torch_backend import (  # noqa: E402
    TorchScenarioELBO,
    fit_torch_advi,
    pool_seed_results,
    seed_stability_metrics,
)


def _synthetic(n=900, seed=3):
    rng = np.random.default_rng(seed)
    states = rng.choice(2, size=n, p=[0.6, 0.4])
    probabilities = np.full((n, 2), 0.05)
    probabilities[np.arange(n), states] = 0.95
    sigma = 0.01 * np.exp(rng.normal(0, 0.05, n))
    mu = np.array([0.002, -0.003])
    c = np.array([0.8, 1.6])
    nu = 6.0
    z = rng.standard_t(nu, size=n) * np.sqrt((nu - 2) / nu)
    returns = mu[states] + c[states] * sigma * z
    return returns, probabilities, sigma


def _config(**overrides):
    base = {
        "enabled": True,
        "backend": "pytorch_cuda",
        "method": "fullrank_advi",
        "hierarchical": True,
        "shared_nu": True,
        "seeds": [11, 42],
        "advi_steps": 700,
        "min_steps": 300,
        "posterior_draws": 400,
        "learning_rate": 0.02,
        "vi_samples_per_step": 4,
        "convergence_window": 100,
        "convergence_tolerance": 0.01,
        "min_effective_observations": 20,
        "device": "cpu",
    }
    base.update(overrides)
    return base


def test_prior_dimensions_and_validation():
    priors = ScenarioPriors.from_config({"hierarchical": True, "shared_nu": True})
    assert priors.n_parameters(4) == 2 + 4 + 2 + 4 + 1
    priors = ScenarioPriors.from_config({"hierarchical": False, "shared_nu": False})
    assert priors.n_parameters(4) == 4 + 4 + 4
    bad = ScenarioPriors.from_config({"priors": {"nu_rate": -1}})
    with pytest.raises(ValueError):
        bad.validate()


def test_torch_advi_recovers_relative_structure_and_constraints():
    returns, probabilities, sigma = _synthetic()
    model = TorchVariationalScenarioModel(_config())
    result = model.fit(
        pd.Series(returns),
        pd.DataFrame(probabilities, columns=["hmm_prob_state_0", "hmm_prob_state_1"]),
        pd.Series(sigma),
        np.arange(len(returns)),
    )
    assert result.fitted
    samples = result.posterior_samples
    assert samples["mu"].shape == samples["c"].shape == samples["nu"].shape
    assert np.isfinite(samples["mu"]).all()
    assert np.all(samples["c"] > 0)
    assert np.all(samples["nu"] > 2)
    # relative structure: calm regime has higher drift and lower multiplier
    assert result.posterior_means["mu"][0] > result.posterior_means["mu"][1]
    assert result.posterior_means["c"][0] < result.posterior_means["c"][1]
    # shared nu must be identical across regimes in every draw
    assert np.allclose(samples["nu"][:, 0], samples["nu"][:, 1])


def test_multi_seed_outputs_and_stability_frame():
    returns, probabilities, sigma = _synthetic()
    model = TorchVariationalScenarioModel(_config())
    model.fit(
        pd.Series(returns),
        pd.DataFrame(probabilities, columns=["s0", "s1"]),
        pd.Series(sigma),
        np.arange(len(returns)),
    )
    by_seed = model.posterior_by_seed
    assert list(by_seed["seed"]) == [11, 42]
    stability = seed_stability_metrics(by_seed)
    assert stability["n_seeds"] == 2
    assert all(np.isfinite(v) for v in stability.values())


def test_posterior_uses_only_train_rows():
    returns, probabilities, sigma = _synthetic(n=1000)
    train = np.arange(700)
    model = TorchVariationalScenarioModel(_config(seeds=[11], advi_steps=350))
    result = model.fit(
        pd.Series(returns),
        pd.DataFrame(probabilities, columns=["s0", "s1"]),
        pd.Series(sigma),
        train,
    )
    # fingerprint must be identical when test-period rows change
    perturbed = returns.copy()
    perturbed[700:] += 1.0
    model2 = TorchVariationalScenarioModel(_config(seeds=[11], advi_steps=350))
    result2 = model2.fit(
        pd.Series(perturbed),
        pd.DataFrame(probabilities, columns=["s0", "s1"]),
        pd.Series(sigma),
        train,
    )
    assert result.data_fingerprint == result2.data_fingerprint
    assert np.allclose(result.posterior_means["mu"], result2.posterior_means["mu"])


def test_same_seed_is_reproducible():
    returns, probabilities, sigma = _synthetic(n=600)
    outputs = []
    for _ in range(2):
        model = TorchVariationalScenarioModel(_config(seeds=[42], advi_steps=300))
        result = model.fit(
            pd.Series(returns),
            pd.DataFrame(probabilities, columns=["s0", "s1"]),
            pd.Series(sigma),
            np.arange(len(returns)),
        )
        outputs.append(result.posterior_means["mu"])
    assert np.allclose(outputs[0], outputs[1], atol=1e-6)


def test_shared_nu_fallback_when_regime_is_thin():
    returns, probabilities, sigma = _synthetic(n=900)
    # add a third regime with almost no mass
    third = np.full((len(returns), 1), 1e-4)
    probabilities = np.hstack([probabilities * (1 - 1e-4), third])
    model = TorchVariationalScenarioModel(
        _config(shared_nu=False, min_effective_observations=50, seeds=[11], advi_steps=300)
    )
    result = model.fit(
        pd.Series(returns),
        pd.DataFrame(probabilities, columns=["s0", "s1", "s2"]),
        pd.Series(sigma),
        np.arange(len(returns)),
    )
    assert any("shared" in w.lower() for w in result.warnings)
    nu = result.posterior_samples["nu"]
    assert np.allclose(nu[:, 0], nu[:, 2])


def test_fallback_chain_is_recorded(monkeypatch):
    returns, probabilities, sigma = _synthetic(n=400)
    elbo = TorchScenarioELBO(
        returns / returns.std(),
        probabilities,
        sigma / returns.std(),
        ScenarioPriors.from_config({"hierarchical": False, "shared_nu": True}),
        device="cpu",
    )
    original = torch_backend._fit_single_attempt
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # simulate a NaN failure on the first attempt
        return original(*args, **kwargs)

    monkeypatch.setattr(torch_backend, "_fit_single_attempt", flaky)
    outcome = fit_torch_advi(
        elbo,
        seed=7,
        max_steps=300,
        min_steps=100,
        retry_learning_rates=(0.001,),
        posterior_draws=100,
    )
    assert calls["n"] == 2
    assert len(outcome.fallbacks) == 1
    assert outcome.fallbacks[0]["reason"] == "non_finite_elbo"


def test_pooling_gives_equal_seed_weight():
    rng = np.random.default_rng(0)
    results = []
    for seed, offset in ((1, 0.0), (2, 10.0)):
        samples = {
            "mu": rng.normal(offset, 0.01, size=(200, 2)),
            "c": np.abs(rng.normal(1, 0.01, size=(200, 2))) + 0.5,
            "nu": np.full((200, 2), 5.0),
        }
        results.append(
            torch_backend.SeedFitResult(
                seed=seed,
                method="fullrank_advi",
                learning_rate=0.01,
                converged=True,
                final_elbo=-1.0,
                n_steps=100,
                elbo_history=np.zeros(100),
                samples=samples,
            )
        )
    pooled, by_seed = pool_seed_results(results, 400)
    assert len(pooled["mu"]) == 400
    # equal-weight mixture: pooled mean sits midway between the two seed means
    assert abs(pooled["mu"].mean() - 5.0) < 0.5
    assert len(by_seed) == 2
