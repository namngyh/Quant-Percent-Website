"""API route handlers. Every handler reads a file; none computes anything."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


class ArtifactStore:
    """Cached, read-only access to `artifacts/`.

    Files are re-read when their mtime changes, so a pipeline run is picked up
    without restarting the service.
    """

    def __init__(self, artifacts_dir: Path) -> None:
        self.artifacts_dir = Path(artifacts_dir)
        self.latest_dir = self.artifacts_dir / "latest"
        self._cache: dict[str, tuple[float, Any]] = {}

    # -- primitives ------------------------------------------------------
    def _read_json(self, path: Path) -> Any:
        if not path.exists():
            return None
        key = str(path)
        mtime = path.stat().st_mtime
        cached = self._cache.get(key)
        if cached and cached[0] == mtime:
            return cached[1]
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not read %s: %s", path, exc)
            return None
        self._cache[key] = (mtime, payload)
        return payload

    def _read_csv(self, path: Path) -> Any:
        if not path.exists():
            return None
        import pandas as pd

        key = str(path)
        mtime = path.stat().st_mtime
        cached = self._cache.get(key)
        if cached and cached[0] == mtime:
            return cached[1]
        try:
            frame = pd.read_csv(path)
        except Exception as exc:
            logger.warning("Could not read %s: %s", path, exc)
            return None
        self._cache[key] = (mtime, frame)
        return frame

    # -- documents --------------------------------------------------------
    def latest(self) -> dict[str, Any] | None:
        return self._read_json(self.latest_dir / "latest_dynamicgraph.json")

    def nodes(self) -> list[dict[str, Any]]:
        return self._read_json(self.latest_dir / "nodes.json") or []

    def edges(self) -> list[dict[str, Any]]:
        return self._read_json(self.latest_dir / "edges.json") or []

    def communities(self) -> list[dict[str, Any]]:
        return self._read_json(self.latest_dir / "communities.json") or []

    def network_history(self) -> list[dict[str, Any]]:
        payload = self._read_json(self.latest_dir / "network_history.json")
        if payload is not None:
            return payload
        frame = self._read_csv(self.latest_dir / "network_history.csv")
        return frame.to_dict(orient="records") if frame is not None else []

    def stress_forecasts(self) -> list[dict[str, Any]]:
        frame = self._read_csv(self.latest_dir / "stress_forecasts.csv")
        return frame.to_dict(orient="records") if frame is not None else []

    def oos_metrics(self) -> list[dict[str, Any]]:
        frame = self._read_csv(self.artifacts_dir / "predictions" / "oos_metrics.csv")
        return frame.to_dict(orient="records") if frame is not None else []

    def comparisons(self) -> list[dict[str, Any]]:
        frame = self._read_csv(self.artifacts_dir / "predictions" / "model_comparisons.csv")
        return frame.to_dict(orient="records") if frame is not None else []

    def run_summary(self) -> dict[str, Any]:
        return self._read_json(self.artifacts_dir / "reports" / "run_summary.json") or {}

    def available(self) -> bool:
        return (self.latest_dir / "latest_dynamicgraph.json").exists()


def ticker_detail(store: ArtifactStore, ticker: str) -> dict[str, Any]:
    """Node record plus its strongest neighbours."""
    ticker = str(ticker).upper()
    nodes = {n["id"]: n for n in store.nodes()}
    if ticker not in nodes:
        return {"ticker": ticker, "found": False, "node": {}, "neighbours": []}

    neighbours = []
    for edge in store.edges():
        if edge.get("source") == ticker:
            neighbours.append({"ticker": edge["target"], **_edge_view(edge)})
        elif edge.get("target") == ticker:
            neighbours.append({"ticker": edge["source"], **_edge_view(edge)})
    neighbours.sort(key=lambda e: abs(e.get("weight", 0.0)), reverse=True)

    latest = store.latest() or {}
    role = None
    for key, label in (
        ("leading_influence_nodes", "high_influence_node"),
        ("vulnerable_nodes", "vulnerable_node"),
        ("risk_transmitters", "directed_risk_transmitter"),
        ("risk_receivers", "directed_risk_receiver"),
    ):
        if any(entry.get("id") == ticker for entry in latest.get(key, [])):
            role = label
            break

    return {
        "ticker": ticker,
        "found": True,
        "node": nodes[ticker],
        "neighbours": neighbours[:15],
        "role": role,
    }


def _edge_view(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        "weight": edge.get("weight"),
        "signed_weight": edge.get("signed_weight"),
        "edge_type": edge.get("edge_type"),
        "window": edge.get("window"),
        "stability": edge.get("stability"),
        "direction": edge.get("direction"),
    }


def stress_latest(store: ArtifactStore) -> dict[str, Any]:
    latest = store.latest()
    if not latest:
        return {"as_of_date": None, "disclaimers": []}
    state = latest.get("network_state", {})
    return {
        "as_of_date": latest.get("model", {}).get("as_of_date"),
        "network_state": state.get("label"),
        "stress_score": state.get("stress_score"),
        "historical_percentile": state.get("historical_percentile"),
        "change_1d": state.get("change_1d"),
        "change_5d": state.get("change_5d"),
        "change_20d": state.get("change_20d"),
        "probabilities": latest.get("stress_probabilities", {}),
        "main_contributors": state.get("main_contributors", []),
        "warning_flags": state.get("warning_flags", []),
        "disclaimers": latest.get("disclaimers", []),
        "warnings": latest.get("warnings", []),
    }


def stress_history(store: ArtifactStore, limit: int = 750) -> list[dict[str, Any]]:
    history = store.network_history()
    keep = (
        "date", "stress_score", "stress_raw", "stress_percentile", "network_state",
        "graph_density", "spectral_radius", "market_mode_share", "centrality_concentration",
        "number_of_communities", "edge_turnover",
    )
    return [{k: row.get(k) for k in keep if k in row} for row in history[-limit:]]


def model_status(store: ArtifactStore, version: str) -> dict[str, Any]:
    latest = store.latest()
    if not latest:
        return {
            "model_name": "DynamicGraph",
            "version": version,
            "warnings": ["No artifacts found. Run `python -m dynamicgraph.cli run-all` first."],
        }
    model = latest.get("model", {})
    quality = latest.get("model_quality", {})
    return {
        "model_name": model.get("name", "DynamicGraph"),
        "version": model.get("version", version),
        "as_of_date": model.get("as_of_date"),
        "generated_at": model.get("generated_at"),
        "data_freshness_days": model.get("data_freshness_days"),
        "run_id": model.get("run_id"),
        "git_commit": model.get("git_commit"),
        "evaluation_type": quality.get("evaluation_type"),
        "graph_incremental_value": quality.get("graph_incremental_value"),
        "model_quality": quality,
        "warnings": latest.get("warnings", []),
    }
