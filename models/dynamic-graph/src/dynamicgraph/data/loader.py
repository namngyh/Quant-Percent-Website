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


def _universe_coverage(
    panel: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    universe: UniverseResolution,
    index_ticker: str,
) -> pd.DataFrame:
    """Daily active-universe and usable-price coverage.

    `n_observed` counts active members with a usable adjusted close after the
    configured, membership-bounded fill policy. The benchmark is deliberately
    excluded from both numerator and denominator.
    """
    membership = universe.membership.loc[:, ["date", "ticker"]].drop_duplicates().copy()
    membership["date"] = pd.to_datetime(membership["date"])
    active = membership.groupby("date")["ticker"].agg(lambda values: sorted(set(values)))

    stocks = panel[panel["ticker"] != index_ticker]
    price_column = "adjusted_close" if "adjusted_close" in stocks.columns else "close"
    usable = stocks[stocks[price_column].notna()]
    observed = usable.groupby("date")["ticker"].agg(lambda values: sorted(set(values)))

    rows = []
    for date in calendar:
        active_tickers = list(active.get(date, []))
        observed_tickers = sorted(set(observed.get(date, [])) & set(active_tickers))
        n_universe = len(active_tickers)
        n_observed = len(observed_tickers)
        rows.append(
            {
                "date": pd.Timestamp(date),
                "n_universe": n_universe,
                "n_observed": n_observed,
                "coverage_ratio": n_observed / n_universe if n_universe else float("nan"),
                "active_tickers": active_tickers,
                "observed_tickers": observed_tickers,
            }
        )
    return pd.DataFrame(rows)


def apply_point_in_time_membership(
    panel: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    universe: UniverseResolution,
    index_ticker: str,
    max_forward_fill_days: int = 1,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply daily `(date, ticker)` membership and align within active spells.

    The market benchmark is aligned separately and is never treated as a
    constituent. Stock prices can only be forward-filled inside one contiguous
    active-membership spell.
    """
    membership = universe.membership.loc[:, ["date", "ticker"]].drop_duplicates().copy()
    membership["date"] = pd.to_datetime(membership["date"])
    membership = membership[
        membership["date"].isin(calendar) & membership["ticker"].isin(universe.tickers)
    ]

    benchmark_raw = panel[panel["ticker"] == index_ticker]
    benchmark = align_to_calendar(
        benchmark_raw,
        calendar,
        max_forward_fill_days=max_forward_fill_days,
    )
    stocks = align_to_calendar(
        panel[panel["ticker"] != index_ticker],
        calendar,
        max_forward_fill_days=max_forward_fill_days,
        active_membership=membership,
    )
    selected = pd.concat([stocks, benchmark], ignore_index=True)
    selected = selected.sort_values(["ticker", "date"], kind="stable").reset_index(drop=True)

    # Runtime invariant: every stock row must be backed by an exact daily
    # membership pair. The benchmark is the only permitted exception.
    stock_pairs = selected.loc[selected["ticker"] != index_ticker, ["date", "ticker"]]
    check = stock_pairs.merge(membership, on=["date", "ticker"], how="left", indicator=True)
    if not check.empty and not check["_merge"].eq("both").all():
        raise AssertionError("Panel contains stock rows outside point-in-time membership.")

    coverage = _universe_coverage(selected, calendar, universe, index_ticker)
    universe.daily_coverage = coverage
    return selected, coverage


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
    ordered = panel.copy()
    sort_columns = [
        column for column in ("ticker", "date") if column in ordered.columns
    ]
    if sort_columns:
        ordered = ordered.sort_values(sort_columns, kind="mergesort")
    ordered = ordered.reindex(sorted(ordered.columns), axis=1).reset_index(drop=True)

    digest = hashlib.sha256()
    digest.update(json.dumps(list(ordered.columns)).encode())
    digest.update(json.dumps([str(dtype) for dtype in ordered.dtypes]).encode())
    digest.update(
        pd.util.hash_pandas_object(ordered, index=False).values.tobytes()
    )
    return digest.hexdigest()[:16]


def _file_content_fingerprint(path_value: Any) -> str | None:
    """Hash a complete local source file and its SQLite WAL, when present."""
    if not path_value:
        return None
    path = Path(str(path_value))
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    for candidate in (path, Path(f"{path}-wal")):
        if not candidate.is_file():
            continue
        digest.update(candidate.name.encode())
        with candidate.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _cache_key(config: Any) -> str:
    # Full effective config is intentional: residualization, feature and graph
    # changes all alter the semantics of downstream cached artifacts.
    config_payload = config.to_dict()
    payload = {
        "cache_schema_version": 2,
        "effective_config": config_payload,
        "source_content": _file_content_fingerprint(config.data.database_path),
        "universe_content": _file_content_fingerprint(
            config.resolve_path(config.data.universe_file)
        ),
        "sector_map_content": _file_content_fingerprint(
            config.resolve_path(config.data.sector_map_file)
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()[:12]


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
        universe = resolve_universe(config, panel, calendar, canonical_index)
        panel, _ = apply_point_in_time_membership(
            panel,
            calendar,
            universe,
            canonical_index,
            max_forward_fill_days=int(config.data.max_forward_fill_days),
        )

        validation = validate_panel(panel, config, index_ticker=canonical_index, calendar=calendar)
        panel = apply_exclusions(panel, validation, canonical_index, enforce=True)
        universe.daily_coverage = _universe_coverage(panel, calendar, universe, canonical_index)
        calendar = infer_trading_calendar(
            panel, canonical_index if canonical_index in set(panel["ticker"]) else None
        )

        if not cache_file.exists() or force:
            try:
                panel.to_parquet(cache_file, index=False)
            except Exception as exc:  # pragma: no cover - pyarrow optional
                logger.warning("Could not write the panel cache (%s); continuing without it.", exc)
            try:
                universe.daily_coverage.to_parquet(
                    cache_dir / f"universe_coverage_{key}.parquet", index=False
                )
            except Exception as exc:  # pragma: no cover - pyarrow optional
                logger.warning("Could not write universe coverage cache (%s).", exc)

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
