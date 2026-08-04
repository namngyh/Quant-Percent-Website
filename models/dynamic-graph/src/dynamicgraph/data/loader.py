"""End-to-end data loading: connector -> universe -> calendar -> normalise ->
validate, with a Parquet/CSV cache so repeated runs do not re-query the source.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from dynamicgraph.data.calendar import align_to_calendar, infer_trading_calendar
from dynamicgraph.data.connectors import BaseConnector, build_connector
from dynamicgraph.data.constituent_manager import UniverseResolution, resolve_universe
from dynamicgraph.data.normalizer import NormalizationReport, normalize_panel
from dynamicgraph.data.validator import ValidationReport, apply_exclusions, validate_panel
from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class PanelBundle:
    """Everything downstream stages need from the data layer."""

    panel: pd.DataFrame
    calendar: pd.DatetimeIndex
    universe: UniverseResolution
    index_ticker: str
    source_metadata: dict[str, Any]
    normalization: NormalizationReport
    validation: ValidationReport
    fingerprint: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def tickers(self) -> list[str]:
        return [t for t in sorted(self.panel["ticker"].unique()) if t != self.index_ticker]

    def wide(self, column: str = "adjusted_close", include_index: bool = True) -> pd.DataFrame:
        frame = self.panel if include_index else self.panel[self.panel["ticker"] != self.index_ticker]
        return frame.pivot_table(index="date", columns="ticker", values=column, aggfunc="last").sort_index()

    def sectors(self) -> dict[str, str]:
        latest = self.panel.sort_values("date").drop_duplicates("ticker", keep="last")
        return dict(zip(latest["ticker"], latest["sector"]))

    def to_dict(self) -> dict[str, Any]:
        return {
            "index_ticker": self.index_ticker,
            "n_rows": len(self.panel),
            "n_tickers": int(self.panel["ticker"].nunique()),
            "date_min": str(self.panel["date"].min().date()),
            "date_max": str(self.panel["date"].max().date()),
            "fingerprint": self.fingerprint,
            "source": self.source_metadata,
            "universe": self.universe.to_dict(),
            "normalization": self.normalization.to_dict(),
            "validation": self.validation.to_dict(),
            "warnings": self.warnings,
        }


def _fingerprint(panel: pd.DataFrame) -> str:
    """Content hash of the loaded data, for the reproducibility record."""
    digest = hashlib.sha256()
    digest.update(str(len(panel)).encode())
    digest.update(str(panel["date"].min()).encode())
    digest.update(str(panel["date"].max()).encode())
    digest.update(",".join(sorted(panel["ticker"].unique())).encode())
    tail = panel.sort_values(["ticker", "date"]).tail(500)
    digest.update(pd.util.hash_pandas_object(tail, index=False).values.tobytes())
    return digest.hexdigest()[:16]


def _cache_key(config: Any) -> str:
    payload = {
        "path": str(config.data.database_path),
        "start": config.data.start_date,
        "end": config.data.end_date,
        "universe_method": config.data.universe_method,
        "universe_size": config.data.universe_size,
        "ffill": config.data.max_forward_fill_days,
        "min_history": config.data.minimum_history_days,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]


def load_panel(
    config: Any,
    force: bool = False,
    connector: BaseConnector | None = None,
) -> PanelBundle:
    """Load, normalise and validate the VN30 panel."""
    cache_dir = config.artifacts_dir / "processed"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _cache_key(config)
    cache_file = cache_dir / f"panel_{key}.parquet"
    meta_file = cache_dir / f"panel_{key}.meta.json"

    owns_connector = connector is None
    connector = connector or build_connector(config, cache_dir=config.artifacts_dir / "data_audit")

    try:
        index_source = None
        if hasattr(connector, "detect_index_symbol"):
            index_source = connector.detect_index_symbol(config.data.index_source_symbol)
        canonical_index = str(config.data.index_symbol or "VN30").upper()
        if index_source is None:
            logger.warning(
                "No index symbol detected in the source; market residualization will be skipped."
            )

        # ---- universe selection (needs a first pass over symbols) -------
        symbols = connector.list_symbols()
        available = {str(t).upper() for t in symbols["ticker"]}

        requested: list[str] | None
        if str(config.data.universe_method).lower() == "liquidity_proxy":
            # Load every ordinary HSX/HNX stock, then rank point-in-time.
            candidates = symbols
            if "instrument_type" in candidates.columns:
                candidates = candidates[candidates["instrument_type"].astype(str).str.upper() == "STOCK"]
            if "exchange" in candidates.columns:
                candidates = candidates[candidates["exchange"].astype(str).str.upper().isin({"HSX", "HNX"})]
            requested = sorted(candidates["ticker"].astype(str).str.upper().unique().tolist())
            if index_source:
                requested = [index_source] + [t for t in requested if t != index_source]
            logger.info("Liquidity-proxy universe: screening %d listed stocks.", len(requested))
        else:
            from dynamicgraph.config import REPO_ROOT
            from dynamicgraph.data.constituent_manager import read_static_universe

            universe_path = Path(config.data.universe_file)
            if not universe_path.is_absolute():
                universe_path = REPO_ROOT / universe_path
            static = read_static_universe(universe_path)
            requested = sorted(set(static["ticker"]) & available)
            if index_source:
                requested = [index_source] + [t for t in requested if t != index_source]

        # ---- cached fast path -------------------------------------------
        if cache_file.exists() and not force:
            logger.info("Loading cached panel from %s", cache_file)
            panel = pd.read_parquet(cache_file)
            panel["date"] = pd.to_datetime(panel["date"])
            # The connector normally fills its metadata during `.load()`; on the
            # cached path restore it from the sidecar so the audit report does
            # not silently claim "no adjusted price".
            if meta_file.exists():
                try:
                    cached_meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    for key, value in (cached_meta.get("source") or {}).items():
                        setattr(connector.metadata, key, value)
                except Exception as exc:
                    logger.debug("Could not restore cached source metadata: %s", exc)
        else:
            panel = connector.load(
                tickers=requested,
                start=config.data.start_date,
                end=config.data.end_date,
            )

        panel, norm_report = normalize_panel(
            panel,
            config,
            index_source_symbol=index_source,
            sector_map_path=config.resolve_path(config.data.sector_map_file),
        )

        calendar = infer_trading_calendar(
            panel, canonical_index if canonical_index in set(panel["ticker"]) else None
        )
        panel = align_to_calendar(
            panel, calendar, max_forward_fill_days=int(config.data.max_forward_fill_days)
        )

        validation = validate_panel(panel, config, index_ticker=canonical_index, calendar=calendar)
        panel = apply_exclusions(panel, validation, canonical_index, enforce=True)

        universe = resolve_universe(config, panel, calendar, canonical_index)

        keep = set(universe.tickers) | {canonical_index}
        panel = panel[panel["ticker"].isin(keep)].reset_index(drop=True)
        calendar = infer_trading_calendar(
            panel, canonical_index if canonical_index in set(panel["ticker"]) else None
        )

        if not cache_file.exists() or force:
            try:
                panel.to_parquet(cache_file, index=False)
            except Exception as exc:  # pragma: no cover - pyarrow optional
                logger.warning("Could not write the panel cache (%s); continuing without it.", exc)

        bundle = PanelBundle(
            panel=panel,
            calendar=calendar,
            universe=universe,
            index_ticker=canonical_index,
            source_metadata=connector.metadata.to_dict(),
            normalization=norm_report,
            validation=validation,
            fingerprint=_fingerprint(panel),
            warnings=list(norm_report.warnings) + list(universe.warnings)
            + [c.message for c in validation.warnings],
        )
        meta_file.write_text(json.dumps(bundle.to_dict(), indent=2, default=str), encoding="utf-8")

        logger.info(
            "Panel ready: %d rows, %d tickers, %s .. %s (fingerprint %s)",
            len(panel),
            panel["ticker"].nunique(),
            panel["date"].min().date(),
            panel["date"].max().date(),
            bundle.fingerprint,
        )
        return bundle
    finally:
        if owns_connector:
            connector.close()
