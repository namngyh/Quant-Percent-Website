"""Command line entry points: inspect the source, fit once, predict often.

    python -m raemf_mc.cli discover-source
    python -m raemf_mc.cli fit     --config configs/gpu_research.yaml
    python -m raemf_mc.cli predict --paths 2000 --horizon 20

`fit` is the expensive half (hours at research scale) and writes a bundle;
`predict` reloads that bundle and only runs the filter forward over whatever
sessions have appeared since, then simulates. Separating them is what the model
card's section 4.8 said was missing.

Output is JSON on stdout, written as UTF-8 explicitly: the documented deployment
is Windows Task Scheduler with stdout redirected to a file, which defaults to
cp1252 and would otherwise raise UnicodeEncodeError after the work is already
done.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import torch
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUNDLE_DIR = REPO_ROOT / "artifacts" / "models"
DEFAULT_FORECAST_DIR = REPO_ROOT / "artifacts" / "forecasts"


def emit(payload: dict[str, Any]) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        print(text)
        return
    sys.stdout.flush()
    buffer.write((text + "\n").encode("utf-8"))
    buffer.flush()


def load_ohlcv(source: str, path: Path | None, symbol: str) -> tuple[pd.DataFrame, str]:
    """Cleaned OHLCV from the database or from the static CSV.

    The two paths share the validation stage, so the same rows are rejected for
    the same reasons whichever one is used.
    """
    if source == "database":
        from raemf_mc.data.source import load_vnindex_from_database

        frame, _dropped, _total = load_vnindex_from_database(symbol=symbol)
        return frame, f"database:{symbol}"
    from raemf_mc.data.loader import load_vnindex_ohlcv

    return load_vnindex_ohlcv(path), f"csv:{path or 'default'}"


# ---------------------------------------------------------------------------
# discover-source
# ---------------------------------------------------------------------------
def command_discover_source(args: argparse.Namespace) -> dict[str, Any]:
    from raemf_mc.data.source import describe_source

    return describe_source(args.dsn)


# ---------------------------------------------------------------------------
# fit
# ---------------------------------------------------------------------------
def command_fit(args: argparse.Namespace) -> dict[str, Any]:
    from raemf_mc.bayesian.priors import HierarchicalPriorConfig
    from raemf_mc.bayesian.torch_backend import AdviConfig
    from raemf_mc.features.returns import compute_log_returns
    from raemf_mc.persistence import FittedBundle, SCHEMA_VERSION, build_provenance, save_bundle
    from raemf_mc.regime.ms_egarch import MSEGARCHParamLayout, default_recursion_init, fit_ms_egarch
    from raemf_mc.runtime.hardware import select_device
    from raemf_mc.scenario.mu_fit import fit_regime_mu

    started = time.perf_counter()
    with Path(args.config).open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    device = select_device(config.get("device_preference", "auto"))
    ohlcv, source_label = load_ohlcv(args.source, args.data, args.symbol)

    window = args.window or config.get("window_sessions")
    if window:
        ohlcv = ohlcv.iloc[-int(window) :]
    log_returns = compute_log_returns(ohlcv)

    # Centre on the estimation window's own mean and keep it: every simulated
    # path is produced in this centred space and has to be shifted back.
    centering_mean = float(log_returns.mean())
    centered = log_returns - centering_mean
    returns_tensor = torch.tensor(centered.to_numpy(), dtype=torch.float32).to(device)

    layout = MSEGARCHParamLayout()
    seeds = args.seeds if args.seeds else config["seeds"]
    advi_key = "ms_egarch_advi" if "ms_egarch_advi" in config else "advi"
    prior_key = "ms_egarch_prior" if "ms_egarch_prior" in config else "prior"
    advi = AdviConfig(**config[advi_key])
    prior = HierarchicalPriorConfig(**config[prior_key])

    log_directory = Path(args.out or DEFAULT_BUNDLE_DIR)
    log_directory.mkdir(parents=True, exist_ok=True)
    ms_egarch = fit_ms_egarch(
        returns_tensor, advi, prior, seeds, device, layout,
        fallback_log_path=log_directory / "ms_egarch_fallbacks.json",
    )

    mu_posterior = None
    if "mu_advi" in config:
        init_log_var, init_log_state_prob = default_recursion_init(layout, device=device)
        # `fit_regime_mu` compares `generator.device` to the tensor's device with
        # `!=`, and that comparison is index-sensitive: `torch.device("cuda")`
        # does not equal `torch.device("cuda:0")`. Build the generator from the
        # tensor's own device so the indices match, not from `select_device`'s
        # unindexed one. The failure only surfaces after the MS-EGARCH fit has
        # already burned an hour, so it is worth getting right here.
        mu_generator = torch.Generator(device=returns_tensor.device).manual_seed(int(seeds[0]))
        mu_posterior = fit_regime_mu(
            returns_tensor, ms_egarch, AdviConfig(**config["mu_advi"]), seeds, device,
            init_log_var, init_log_state_prob, layout=layout,
            n_draws=config["mu_n_draws"], mu_prior_scale=config["mu_prior_scale"],
            min_effective_observations=config["mu_min_effective_observations"],
            min_effective_fraction=config["mu_min_effective_fraction"],
            generator=mu_generator,
            fallback_log_path=log_directory / "mu_fallbacks.json",
        )

    bundle = FittedBundle(
        schema_version=SCHEMA_VERSION,
        ms_egarch=ms_egarch,
        mu=mu_posterior,
        layout=layout,
        centering_mean=centering_mean,
        window_sessions=int(window) if window else None,
        seeds=[int(s) for s in seeds],
        config={"path": str(args.config), **{k: v for k, v in config.items() if k != "seeds"}},
        provenance=build_provenance(ohlcv, source_label, {"device": str(device)}),
    )
    paths = save_bundle(log_directory, bundle)
    return {
        "status": "fitted",
        "source": source_label,
        "sessions": int(len(ohlcv)),
        "first_date": bundle.provenance["first_date"],
        "last_date": bundle.provenance["last_date"],
        "seeds": bundle.seeds,
        "fallback_summary": ms_egarch.fallback_summary(),
        "mu_fitted": mu_posterior is not None,
        "bundle_path": str(paths["bundle"]),
        "manifest_path": str(paths["manifest"]),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


# ---------------------------------------------------------------------------
# predict
# ---------------------------------------------------------------------------
def command_predict(args: argparse.Namespace) -> dict[str, Any]:
    from raemf_mc.features.returns import compute_log_returns
    from raemf_mc.persistence import assert_history_unchanged, load_bundle
    from raemf_mc.regime.ms_egarch import default_recursion_init
    from raemf_mc.regime.posterior_features import compute_posterior_volatility_features
    from raemf_mc.risk.metrics import summarize_risk
    from raemf_mc.scenario.simulate import simulate_mc_paths

    started = time.perf_counter()
    bundle = load_bundle(args.bundle or DEFAULT_BUNDLE_DIR)
    if bundle.mu is None:
        raise SystemExit(
            "Bundle khong co tang mu (regime-mean); Monte Carlo can no. "
            "Fit lai voi mot config co khoi `mu_advi`."
        )

    ohlcv, source_label = load_ohlcv(args.source, args.data, args.symbol)
    if bundle.window_sessions:
        ohlcv = ohlcv.iloc[-int(bundle.window_sessions) :]
    assert_history_unchanged(bundle, ohlcv)

    log_returns = compute_log_returns(ohlcv)
    # The bundle's own centring constant, not this series' mean: the posterior
    # was fitted in that space and recomputing the mean would shift it.
    centered = log_returns - bundle.centering_mean
    device = torch.device("cpu")
    returns_tensor = torch.tensor(centered.to_numpy(), dtype=torch.float32)
    init_log_var, init_log_state_prob = default_recursion_init(bundle.layout, device=device)

    volatility = compute_posterior_volatility_features(
        bundle.ms_egarch, centered, init_log_var, init_log_state_prob,
        layout=bundle.layout, n_draws=int(args.volatility_draws),
        generator=torch.Generator().manual_seed(int(args.seed)),
        device=device,
    )

    generator = torch.Generator().manual_seed(int(args.seed) + 1)
    forecast_directory = Path(args.out or DEFAULT_FORECAST_DIR)
    forecast_directory.mkdir(parents=True, exist_ok=True)
    paths_tensor = simulate_mc_paths(
        bundle.ms_egarch, bundle.mu, returns_tensor, init_log_var, init_log_state_prob,
        n_paths=int(args.paths), horizon=int(args.horizon), layout=bundle.layout,
        device=device, generator=generator,
        fallback_log_path=forecast_directory / "mc_fallbacks.json",
    )
    # simulate_mc_paths returns centred returns; add the fit's own mean back so
    # the reported tail carries the market's baseline drift.
    real_scale = paths_tensor.cpu().numpy() + bundle.centering_mean

    horizons = tuple(int(h) for h in args.report_horizons)
    risk = summarize_risk(real_scale, horizons=horizons, alphas=(0.95, 0.99))

    as_of = pd.Timestamp(ohlcv.index.max())
    latest_close = float(ohlcv["close"].iloc[-1])
    payload = {
        "model": "RAEMF-VB-MC",
        "as_of_date": str(as_of.date()),
        "source": source_label,
        "current_vnindex": latest_close,
        "sessions_used": int(len(ohlcv)),
        "posterior_sigma": {
            "latest": float(volatility["posterior_mean_sigma"].iloc[-1]),
            "latest_sd": float(volatility["posterior_sd_sigma"].iloc[-1]),
        },
        "monte_carlo": {"paths": int(args.paths), "horizon": int(args.horizon)},
        "risk": {
            str(h): {column: float(risk.loc[h, column]) for column in risk.columns}
            for h in horizons
        },
        "projected_index": {
            str(h): float(latest_close * float(pd.Series(real_scale[:, :h].sum(axis=1)).median()))
            for h in horizons
        },
        "fit_provenance": bundle.provenance,
        "caveats": [
            "VaR/CVaR chua dang tin: nu ~ 3 nen kurtosis van vo han (can nu > 4).",
            "Walk-forward OOS chua du suc manh thong ke; xem docs/model_card.md muc 4.",
        ],
    }

    written = _write_forecast(forecast_directory, payload, risk, volatility)
    payload_out = {
        "status": "predicted",
        "as_of_date": payload["as_of_date"],
        "artifacts": [str(path) for path in written],
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        **{k: payload[k] for k in ("current_vnindex", "posterior_sigma", "risk")},
    }
    return payload_out


def _write_forecast(directory: Path, payload, risk, volatility) -> list[Path]:
    written = []
    target = directory / "latest_forecast.json"
    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    written.append(target)
    risk_path = directory / "latest_risk.csv"
    risk.to_csv(risk_path)
    written.append(risk_path)
    volatility_path = directory / "latest_posterior_sigma.csv"
    volatility.tail(500).to_csv(volatility_path)
    written.append(volatility_path)
    return written


# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="raemf_mc.cli", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover-source", help="Read-only inventory of the daily table")
    discover.add_argument("--dsn", default=None)

    for name, helptext in (
        ("fit", "Fit MS-EGARCH (and the regime-mean layer) and save a bundle"),
        ("predict", "Reload a bundle and publish the latest risk/regime forecast"),
    ):
        sub = subparsers.add_parser(name, help=helptext)
        sub.add_argument("--source", choices=["database", "csv"], default="database")
        sub.add_argument("--data", type=Path, default=None, help="CSV path when --source csv")
        sub.add_argument("--symbol", default="VNINDEX")
        sub.add_argument("--out", type=Path, default=None)

    fit = subparsers.choices["fit"]
    fit.add_argument("--config", type=Path, required=True)
    fit.add_argument("--seeds", type=int, nargs="*", default=None)
    fit.add_argument("--window", type=int, default=None, help="Override window_sessions")

    predict = subparsers.choices["predict"]
    predict.add_argument("--bundle", type=Path, default=None)
    predict.add_argument("--paths", type=int, default=2000)
    predict.add_argument("--horizon", type=int, default=20)
    predict.add_argument("--report-horizons", type=int, nargs="*", default=[1, 5, 20])
    predict.add_argument("--volatility-draws", type=int, default=20)
    predict.add_argument("--seed", type=int, default=0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    handlers = {
        "discover-source": command_discover_source,
        "fit": command_fit,
        "predict": command_predict,
    }
    emit(handlers[args.command](args))


if __name__ == "__main__":
    main()
