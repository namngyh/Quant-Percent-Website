"""Tests for saving and reloading a fitted model.

Before this existed every run refit from scratch, which is why the model card
put a daily update at "~9 minutes minimum" against a theoretical ~4 seconds. The
properties that make a reload trustworthy are the ones asserted here: the
posterior comes back identical, the centring constant survives, and a series
whose history has been restated is refused rather than predicted from.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import torch

from raemf_mc.bayesian.torch_backend import FitResult, PooledPosterior
from raemf_mc.persistence import (
    SCHEMA_VERSION,
    BundleError,
    FittedBundle,
    assert_history_unchanged,
    build_provenance,
    data_fingerprint,
    load_bundle,
    save_bundle,
)
from raemf_mc.regime.ms_egarch import MSEGARCHParamLayout


def _ohlcv(rows: int = 30, close_offset: float = 0.0) -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-01", periods=rows)
    # Each session's value must not depend on how many sessions were asked for,
    # or "append 5 more rows" would also restate all the earlier ones and the
    # history guard would be tested against the wrong thing.
    close = 1000.0 + np.arange(rows) * 3.4 + close_offset
    return pd.DataFrame(
        {
            "open": close - 1,
            "high": close + 2,
            "low": close - 3,
            "close": close,
            "volume": np.arange(rows) + 1000,
        },
        index=pd.DatetimeIndex(dates, name="date"),
    )


def _posterior(seed: int = 0, scale: float = 1.0) -> PooledPosterior:
    layout = MSEGARCHParamLayout()
    size = layout.n_egarch_params + layout.n_transition_params + layout.n_nu_params
    return PooledPosterior(
        seed_results=[
            FitResult(
                mu=torch.arange(size, dtype=torch.float32) * scale,
                log_sigma=torch.full((size,), -1.5),
                elbo_trace=[1.0, 2.0, 3.0],
                completed_without_divergence=True,
                fallback_used=False,
                fallback_reason=None,
                n_retries=0,
                seed=seed,
            )
        ]
    )


def _bundle(ohlcv: pd.DataFrame, **overrides) -> FittedBundle:
    defaults = dict(
        schema_version=SCHEMA_VERSION,
        ms_egarch=_posterior(),
        mu=_posterior(seed=1, scale=0.5),
        layout=MSEGARCHParamLayout(),
        centering_mean=0.000123,
        window_sessions=400,
        seeds=[0],
        config={"path": "configs/tiny.yaml"},
        provenance=build_provenance(ohlcv, "database:VNINDEX"),
    )
    defaults.update(overrides)
    return FittedBundle(**defaults)


# ---------------------------------------------------------------------------
# Round trip
# ---------------------------------------------------------------------------
def test_posterior_survives_the_round_trip_exactly(tmp_path):
    """An approximate reload would silently change every forecast the bundle
    produces, with nothing to compare against."""
    original = _bundle(_ohlcv())
    save_bundle(tmp_path, original)
    reloaded = load_bundle(tmp_path)
    for left, right in zip(original.ms_egarch.seed_results, reloaded.ms_egarch.seed_results):
        assert torch.equal(left.mu, right.mu)
        assert torch.equal(left.log_sigma, right.log_sigma)
        assert left.seed == right.seed


def test_centering_mean_survives_the_round_trip(tmp_path):
    """Every simulated path is produced in centred space; losing this constant
    would shift the whole distribution by the market's drift."""
    save_bundle(tmp_path, _bundle(_ohlcv()))
    assert load_bundle(tmp_path).centering_mean == pytest.approx(0.000123)


def test_layout_and_window_survive_the_round_trip(tmp_path):
    save_bundle(tmp_path, _bundle(_ohlcv()))
    reloaded = load_bundle(tmp_path)
    assert reloaded.layout.n_states == MSEGARCHParamLayout().n_states
    assert reloaded.window_sessions == 400
    assert reloaded.seeds == [0]


def test_a_bundle_without_the_mu_layer_reloads(tmp_path):
    """`fit` on a config with no `mu_advi` block produces one of these; predict
    then refuses explicitly rather than crashing on a None."""
    save_bundle(tmp_path, _bundle(_ohlcv(), mu=None))
    assert load_bundle(tmp_path).mu is None


def test_manifest_is_readable_without_torch(tmp_path):
    """The manifest is the audit record; a human debugging a bad session should
    not need to unpickle tensors to see what was fitted."""
    import json

    paths = save_bundle(tmp_path, _bundle(_ohlcv()))
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["seeds"] == [0]
    assert manifest["mu_fitted"] is True
    assert manifest["fallback_summary"]["n_fallback_seeds"] == 0
    assert manifest["provenance"]["source"] == "database:VNINDEX"


def test_loading_a_missing_bundle_says_to_fit_first(tmp_path):
    with pytest.raises(BundleError, match="chay `fit` truoc"):
        load_bundle(tmp_path)


def test_a_bundle_from_another_schema_is_refused(tmp_path):
    save_bundle(tmp_path, _bundle(_ohlcv()))
    payload = torch.load(tmp_path / "raemf_bundle.pt", map_location="cpu", weights_only=False)
    payload["schema_version"] = SCHEMA_VERSION + 1
    torch.save(payload, tmp_path / "raemf_bundle.pt")
    with pytest.raises(BundleError, match="schema"):
        load_bundle(tmp_path)


# ---------------------------------------------------------------------------
# History guard
# ---------------------------------------------------------------------------
def test_fingerprint_ignores_columns_the_likelihood_never_sees():
    """A restated volume figure must not force a refit; the likelihood only
    sees dates and closes."""
    base = _ohlcv()
    volume_changed = base.copy()
    volume_changed["volume"] = volume_changed["volume"] * 2
    assert data_fingerprint(base) == data_fingerprint(volume_changed)


def test_fingerprint_changes_when_a_close_changes():
    base = _ohlcv()
    restated = base.copy()
    restated.iloc[5, restated.columns.get_loc("close")] += 0.01
    assert data_fingerprint(base) != data_fingerprint(restated)


def test_appending_new_sessions_is_allowed():
    """The normal case: yesterday's fit, today's sessions."""
    fitted = _ohlcv(rows=30)
    bundle = _bundle(fitted)
    assert_history_unchanged(bundle, _ohlcv(rows=35))


def test_restated_history_is_refused():
    """The posterior conditions on a specific history. If that history is
    edited, the right answer is a refit, not a prediction."""
    bundle = _bundle(_ohlcv(rows=30))
    restated = _ohlcv(rows=35)
    restated.iloc[3, restated.columns.get_loc("close")] += 5.0
    with pytest.raises(BundleError, match="da bi sua"):
        assert_history_unchanged(bundle, restated)


def test_a_shortened_history_is_refused():
    bundle = _bundle(_ohlcv(rows=30))
    with pytest.raises(BundleError, match="lich su da doi"):
        assert_history_unchanged(bundle, _ohlcv(rows=25))


def test_a_bundle_without_provenance_skips_the_check():
    """Older bundles carry no provenance; refusing them outright would be worse
    than letting them through with the check simply unavailable."""
    bundle = _bundle(_ohlcv(), provenance={})
    assert_history_unchanged(bundle, _ohlcv(rows=35))
