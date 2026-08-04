import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from raemf_mc.bayesian.variational import VariationalPosteriorResult, VariationalScenarioModel
from raemf_mc.config import bayesian_config
from raemf_mc.simulation.structural_mc import simulate_paths_detailed


def _model_with_result(draws: int = 50) -> VariationalScenarioModel:
    rng = np.random.default_rng(12)
    samples = {
        "mu": rng.normal([0.002, -0.003], [0.0005, 0.0005], size=(draws, 2)),
        "c": np.exp(rng.normal([-.1, .2], 0.05, size=(draws, 2))),
        "nu": 2 + rng.exponential(6, size=(draws, 2)),
    }
    model = VariationalScenarioModel({"min_effective_observations": 1})
    model.result = VariationalPosteriorResult(
        fitted=True,
        inference_method="meanfield_advi",
        elbo_history=np.arange(20, dtype=float),
        posterior_samples=samples,
        posterior_means={key: value.mean(axis=0) for key, value in samples.items()},
        posterior_standard_deviations={key: value.std(axis=0, ddof=1) for key, value in samples.items()},
        credible_intervals=pd.DataFrame(
            [{"parameter": key, "regime": regime, "q025": 0.0, "q50": 0.0, "q975": 1.0} for key in samples for regime in range(2)]
        ),
        regime_labels=["calm", "stress"],
        scaling_metadata={"return_scale": 0.01},
        train_date_range=("2020-01-01", "2020-12-31"),
        data_fingerprint="abc",
        random_seed=42,
        convergence_status="converged",
        effective_observations=np.array([100.0, 80.0]),
    )
    model._training_data = {
        "returns": rng.normal(0, 0.01, size=40),
        "probabilities": np.tile([0.6, 0.4], (40, 1)),
        "volatility": np.full(40, 0.01),
    }
    return model


def _simulation(**kwargs):
    return simulate_paths_detailed(
        100.0,
        np.array([0.5, 0.5]),
        np.array([[0.9, 0.1], [0.1, 0.9]]),
        np.array([0.001, -0.001]),
        0.01,
        8,
        20,
        7,
        state_volatility=np.array([0.01, 0.02]),
        egarch_params={"omega": -0.1, "alpha[1]": 0.1, "gamma[1]": -0.05, "beta[1]": 0.9},
        **kwargs,
    )


def test_bayesian_defaults_and_validation():
    config = bayesian_config({})
    assert config["enabled"] is False
    assert config["method"] == "fullrank_advi"
    with pytest.raises(ValueError, match="method"):
        bayesian_config({"method": "invalid"})


def test_input_alignment_and_probability_simplex_errors_are_clear():
    model = VariationalScenarioModel({"min_effective_observations": 1})
    dates = pd.date_range("2020-01-01", periods=5)
    returns = pd.Series(np.linspace(-0.01, 0.01, 5), index=dates)
    probabilities = pd.DataFrame([[0.7, 0.4]] * 5, index=dates)
    volatility = pd.Series(0.01, index=dates)
    with pytest.raises(ValueError, match="sum to 1"):
        model.fit(returns, probabilities, volatility, np.arange(5))
    with pytest.raises(ValueError, match="Index mismatch"):
        model.fit(returns, probabilities.set_axis(dates + pd.Timedelta(days=1)), volatility, np.arange(5))


def test_parameter_sampling_is_reproducible_and_save_load_round_trip(tmp_path):
    model = _model_with_result()
    first = model.sample_parameters(12, 99)
    second = model.sample_parameters(12, 99)
    assert all(np.array_equal(first[key], second[key]) for key in first)
    model.save(tmp_path)
    loaded = VariationalScenarioModel.load(tmp_path)
    assert all(np.array_equal(model.result.posterior_samples[key], loaded.result.posterior_samples[key]) for key in first)
    assert loaded.result.train_date_range == model.result.train_date_range


def test_invalid_saved_posterior_is_rejected_for_pipeline_fallback(tmp_path):
    model = _model_with_result()
    model.save(tmp_path)
    stored = np.load(tmp_path / "posterior_samples.npz")
    invalid_nu = stored["nu"].copy()
    invalid_nu[0, 0] = 2.0
    np.savez_compressed(tmp_path / "posterior_samples.npz", mu=stored["mu"], c=stored["c"], nu=invalid_nu)
    with pytest.raises(ValueError, match="violates"):
        VariationalScenarioModel.load(tmp_path)


def test_posterior_predictive_is_finite_and_recovers_relative_parameter_order():
    model = _model_with_result()
    check = model.posterior_predictive_check(12)
    assert np.isfinite(model.result.elbo_history).all()
    assert np.isfinite(check["draws"]).all()
    assert model.result.posterior_means["mu"][0] > 0 > model.result.posterior_means["mu"][1]
    assert model.result.posterior_means["c"][1] > model.result.posterior_means["c"][0]


def test_variational_mc_uses_exactly_one_joint_draw_per_path():
    parameters = _model_with_result(20).sample_parameters(20, 3)
    result = _simulation(scenario_mode="variational_posterior", parameter_draws=parameters)
    assert np.array_equal(result.parameter_draw_indices, np.arange(20))
    assert result.summary.loc[0, "scenario_mode"] == "variational_posterior"
    assert np.isfinite(result.paths).all()


def test_point_estimate_default_is_identical_to_explicit_mode():
    implicit = _simulation()
    explicit = _simulation(scenario_mode="point_estimate")
    assert np.array_equal(implicit.paths, explicit.paths)
    assert implicit.summary.equals(explicit.summary)


def test_invalid_posterior_constraints_are_rejected():
    parameters = _model_with_result(20).sample_parameters(20, 3)
    parameters["nu"][0, 0] = 2.0
    with pytest.raises(ValueError, match="greater than 2"):
        _simulation(scenario_mode="variational_posterior", parameter_draws=parameters)


def test_importing_cli_does_not_import_pymc_when_bayesian_is_disabled():
    command = [sys.executable, "-c", "import sys, raemf_mc.cli; assert 'pymc' not in sys.modules"]
    subprocess.run(command, check=True)


def test_cli_exposes_variational_commands_and_options():
    from raemf_mc.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(
        [
            "fit-variational",
            "--data",
            "data.csv",
            "--config",
            "configs/laptop.yaml",
            "--advi-steps",
            "100",
            "--posterior-draws",
            "20",
        ]
    )
    assert args.cmd == "fit-variational"
    assert args.advi_steps == 100
