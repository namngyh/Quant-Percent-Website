"""Save and reload a fitted model, so predicting does not mean refitting.

Until now every run refit from scratch: `run_research_fit.py` spends about 9.5
hours on eight seeds and then throws the posterior away. That is why the model
card lists "a daily update costs ~4 seconds in theory but ~9 minutes in
practice" -- there was no way to separate fitting from predicting.

What is stored is the variational posterior itself: for each seed, the mean and
log-sigma of the mean-field approximation over the MS-EGARCH parameter vector,
plus the same for the regime-mean layer. Those are small tensors. The data are
not stored; the fingerprint of the data is, so a reload against a series that
has been restated is refused rather than silently accepted.

`torch.load(..., weights_only=False)` is required because the payload is a
dataclass graph, not a bare state dict. That is safe here and only here: the
file is written by this module on the same machine. Never point `load_bundle` at
a file from an untrusted source.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import torch

from raemf_mc.bayesian.torch_backend import PooledPosterior
from raemf_mc.regime.ms_egarch import MSEGARCHParamLayout

SCHEMA_VERSION = 1
BUNDLE_NAME = "raemf_bundle.pt"


class BundleError(RuntimeError):
    """Raised when a stored bundle cannot be trusted as-is."""


def data_fingerprint(ohlcv: pd.DataFrame) -> str:
    """SHA-256 over the session dates and closes actually used for the fit.

    Dates and closes only: those are what the likelihood sees. A fingerprint
    over every column would change whenever the vendor restated a volume figure,
    which would force needless refits.
    """
    digest = hashlib.sha256()
    digest.update(pd.DatetimeIndex(ohlcv.index).asi8.tobytes())
    digest.update(ohlcv["close"].to_numpy(dtype="float64").tobytes())
    return digest.hexdigest()


@dataclass
class FittedBundle:
    """Everything needed to predict without refitting."""

    schema_version: int
    ms_egarch: PooledPosterior
    mu: PooledPosterior | None
    layout: MSEGARCHParamLayout
    #: Subtracted from log returns before fitting; must be re-applied at predict
    #: time or every simulated path is centred on the wrong drift.
    centering_mean: float
    #: Number of trailing sessions the fit used, or None for the whole series.
    window_sessions: int | None
    seeds: list[int]
    config: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def manifest(self) -> dict[str, Any]:
        """Human-readable audit record, written alongside the tensors."""
        return {
            "schema_version": self.schema_version,
            "created_at": self.provenance.get("created_at"),
            "seeds": list(self.seeds),
            "n_states": int(self.layout.n_states),
            "centering_mean": float(self.centering_mean),
            "window_sessions": self.window_sessions,
            "fallback_summary": self.ms_egarch.fallback_summary(),
            "mu_fitted": self.mu is not None,
            "provenance": dict(self.provenance),
            "config": dict(self.config),
        }


def bundle_paths(root: str | Path) -> dict[str, Path]:
    directory = Path(root)
    return {
        "directory": directory,
        "bundle": directory / BUNDLE_NAME,
        "manifest": directory / "raemf_bundle_manifest.json",
    }


def save_bundle(root: str | Path, bundle: FittedBundle) -> dict[str, Path]:
    """Write the bundle and its manifest atomically."""
    paths = bundle_paths(root)
    paths["directory"].mkdir(parents=True, exist_ok=True)

    temporary = paths["bundle"].with_suffix(".pt.tmp")
    torch.save(
        {
            "schema_version": bundle.schema_version,
            "ms_egarch": bundle.ms_egarch,
            "mu": bundle.mu,
            "layout": asdict(bundle.layout),
            "centering_mean": float(bundle.centering_mean),
            "window_sessions": bundle.window_sessions,
            "seeds": list(bundle.seeds),
            "config": dict(bundle.config),
            "provenance": dict(bundle.provenance),
        },
        temporary,
    )
    temporary.replace(paths["bundle"])

    manifest_temporary = paths["manifest"].with_suffix(".json.tmp")
    manifest_temporary.write_text(
        json.dumps(bundle.manifest(), indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    manifest_temporary.replace(paths["manifest"])
    return paths


def load_bundle(root: str | Path) -> FittedBundle:
    paths = bundle_paths(root)
    if not paths["bundle"].exists():
        raise BundleError(f"Chua co bundle tai {paths['bundle']}; chay `fit` truoc.")
    payload = torch.load(paths["bundle"], map_location="cpu", weights_only=False)
    if int(payload.get("schema_version", -1)) != SCHEMA_VERSION:
        raise BundleError(
            f"Bundle dung schema {payload.get('schema_version')}, code hien tai la "
            f"{SCHEMA_VERSION}; chay lai `fit`."
        )
    return FittedBundle(
        schema_version=SCHEMA_VERSION,
        ms_egarch=payload["ms_egarch"],
        mu=payload.get("mu"),
        layout=MSEGARCHParamLayout(**payload["layout"]),
        centering_mean=float(payload["centering_mean"]),
        window_sessions=payload.get("window_sessions"),
        seeds=list(payload.get("seeds", [])),
        config=dict(payload.get("config", {})),
        provenance=dict(payload.get("provenance", {})),
    )


def build_provenance(ohlcv: pd.DataFrame, source: str, extra: dict[str, Any] | None = None):
    """Record where the fit's data came from and exactly which rows they were."""
    provenance = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": str(source),
        "n_sessions": int(len(ohlcv)),
        "first_date": str(pd.Timestamp(ohlcv.index.min()).date()),
        "last_date": str(pd.Timestamp(ohlcv.index.max()).date()),
        "data_fingerprint": data_fingerprint(ohlcv),
    }
    provenance.update(extra or {})
    return provenance


def assert_history_unchanged(bundle: FittedBundle, ohlcv: pd.DataFrame) -> None:
    """Refuse to predict if the sessions the fit saw have since been restated.

    The bundle's posterior conditions on a specific history. If that history is
    edited, the posterior is conditioning on data that no longer exists and the
    right response is a refit, not a prediction. Extra sessions appended at the
    end are the normal case and are fine -- only the overlap is checked.
    """
    fitted_last = bundle.provenance.get("last_date")
    fitted_count = bundle.provenance.get("n_sessions")
    if not fitted_last or not fitted_count:
        return
    overlap = ohlcv.loc[ohlcv.index <= pd.Timestamp(fitted_last)]
    if len(overlap) != int(fitted_count):
        raise BundleError(
            f"Nguon co {len(overlap)} phien toi {fitted_last} nhung bundle duoc fit tren "
            f"{fitted_count}; lich su da doi, can chay lai `fit`."
        )
    if data_fingerprint(overlap) != bundle.provenance.get("data_fingerprint"):
        raise BundleError(
            "Gia dong cua lich su da bi sua so voi luc fit; can chay lai `fit` thay vi du bao tiep."
        )
