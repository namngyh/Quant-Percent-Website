"""Device handling in `raemf_mc.cli fit`.

`fit_regime_mu` compares `generator.device` to the returns tensor's device with
`!=`, and that comparison is index-sensitive: `torch.device("cuda")` does not
equal `torch.device("cuda:0")`. Building the generator from `select_device()`
therefore passes on CPU and fails on GPU -- after the MS-EGARCH fit has already
run, which at research scale is an hour of wasted compute.

The CPU test below asserts the invariant that makes both work; the CUDA test
runs the real thing and is skipped where there is no GPU.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import torch
import yaml

from raemf_mc import cli

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "vnindex_sample.csv"
REAL_DATA = Path(__file__).resolve().parents[1] / "data" / "raw" / "VNINDEX_Daily.csv"


def _config(steps: int = 5, window: int = 150, device: str = "auto") -> dict:
    block = {
        "n_steps": steps,
        "learning_rate": 0.05,
        "warmup_steps": 2,
        "grad_clip_norm": 10.0,
        "elbo_ma_window": 3,
        "early_stop_patience": 100,
        "min_delta": 0.001,
        "retry_lr_factor": 0.5,
        "max_retries": 1,
        "n_mc_samples": 2,
    }
    return {
        "device_preference": device,
        "window_sessions": window,
        "seeds": [0],
        "ms_egarch_advi": dict(block),
        "ms_egarch_prior": {
            "hyper_mean_scale": 1.0,
            "min_effective_observations": 30.0,
            "min_effective_fraction": 0.05,
        },
        "mu_advi": dict(block),
        "mu_n_draws": 2,
        "mu_prior_scale": 0.01,
        "mu_min_effective_observations": 30.0,
        "mu_min_effective_fraction": 0.05,
    }


def _args(tmp_path: Path, config: dict, device: str = "auto") -> argparse.Namespace:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return argparse.Namespace(
        config=config_path,
        source="csv",
        data=REAL_DATA,
        symbol="VNINDEX",
        out=tmp_path / "bundle",
        seeds=None,
        window=None,
    )


def test_the_mu_generator_matches_the_returns_tensor_device(tmp_path, monkeypatch):
    """The invariant, asserted without needing a GPU: whatever device the
    returns tensor ends up on, the generator is built from *that* device object,
    indices included."""
    captured: dict = {}

    import raemf_mc.scenario.mu_fit as mu_fit

    real = mu_fit.fit_regime_mu

    def spy(returns_tensor, *args, **kwargs):
        captured["tensor_device"] = returns_tensor.device
        captured["generator_device"] = kwargs["generator"].device
        return real(returns_tensor, *args, **kwargs)

    monkeypatch.setattr(mu_fit, "fit_regime_mu", spy)

    cli.command_fit(_args(tmp_path, _config(device="cpu")))

    assert captured["generator_device"] == captured["tensor_device"]


@pytest.mark.skipif(not torch.cuda.is_available(), reason="no CUDA device")
def test_fit_runs_end_to_end_on_cuda(tmp_path):
    """The regression itself. `torch.Generator()` defaults to CPU and
    `torch.Generator(device=torch.device('cuda'))` reports an unindexed device;
    only the tensor's own device object satisfies `fit_regime_mu`."""
    result = cli.command_fit(_args(tmp_path, _config(device="cuda")))
    assert result["status"] == "fitted"
    assert result["mu_fitted"] is True
    assert (tmp_path / "bundle" / "raemf_bundle.pt").exists()


@pytest.mark.skipif(not torch.cuda.is_available(), reason="no CUDA device")
def test_a_cuda_bundle_predicts_on_cpu(tmp_path):
    """`predict` pins itself to CPU, so a GPU-fitted bundle has to reload there."""
    cli.command_fit(_args(tmp_path, _config(device="cuda")))
    forecast_dir = tmp_path / "forecasts"
    payload = cli.command_predict(
        argparse.Namespace(
            source="csv",
            data=REAL_DATA,
            symbol="VNINDEX",
            out=forecast_dir,
            bundle=tmp_path / "bundle",
            paths=200,
            horizon=5,
            report_horizons=[1, 5],
            volatility_draws=2,
            seed=0,
        )
    )
    assert payload["status"] == "predicted"
    assert (forecast_dir / "latest_forecast.json").exists()
