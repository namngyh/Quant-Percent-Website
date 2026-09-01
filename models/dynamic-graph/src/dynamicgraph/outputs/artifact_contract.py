"""Run-manifest and publication-integrity checks."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dynamicgraph.config import config_fingerprint
from dynamicgraph.training.reproducibility import code_fingerprint, git_commit


def load_invalidation_manifest(artifacts_dir: Path) -> dict[str, Any]:
    path = artifacts_dir / "invalidation_manifest.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def invalidation_for_path(path: Path, artifacts_dir: Path) -> list[str]:
    """Return active invalidation IDs whose concrete scope covers ``path``."""
    manifest = load_invalidation_manifest(artifacts_dir)
    relative = path.resolve().relative_to(artifacts_dir.resolve()).as_posix()
    candidate = f"artifacts/{relative}"
    matches: list[str] = []
    for item in manifest.get("invalidations", []):
        if item.get("status") not in {"stale", "invalid"}:
            continue
        for scope in item.get("scope", []):
            normalized = str(scope).replace("\\", "/").rstrip("/")
            if not normalized.startswith("artifacts/"):
                continue
            if candidate == normalized or candidate.startswith(f"{normalized}/"):
                matches.append(str(item.get("id")))
                break
    return matches


def validate_publication_state(state: Any) -> None:
    """Refuse a primary publication from mismatched or failed fitted state."""
    if state.record is None or state.bundle is None:
        raise RuntimeError("Publication requires an in-memory reproducibility record.")
    if state.record.data_fingerprint != state.bundle.fingerprint:
        raise RuntimeError("Data fingerprint mismatch; refusing to publish stale state.")
    if state.record.config_fingerprint != config_fingerprint(state.config):
        raise RuntimeError("Config fingerprint mismatch; refusing to publish stale state.")
    current_commit = git_commit()
    if (
        state.record.git_commit is not None
        and current_commit is not None
        and state.record.git_commit != current_commit
    ):
        raise RuntimeError("Code version mismatch; refusing to publish stale state.")
    if (
        getattr(state.record, "code_fingerprint", "")
        and state.record.code_fingerprint != code_fingerprint()
    ):
        raise RuntimeError(
            "Working-tree code fingerprint mismatch; refusing to publish stale state."
        )
    core_key = (
        state.core_key
        if state.core_key in state.series_by_key
        else next(iter(state.series_by_key), None)
    )
    if core_key is None or not len(state.series_by_key[core_key]):
        raise RuntimeError("No current graph snapshot is available for publication.")
    failed = [
        f"{key}@{snapshot.date}"
        for key, series in state.series_by_key.items()
        for snapshot in series
        if snapshot.metadata.get("glasso_converged") is False
    ]
    if failed:
        raise RuntimeError(
            "At least one fitted graph failed convergence; it may be audited but "
            f"not published. First failures: {failed[:5]}"
        )


def artifact_status_row(
    path: Path,
    artifacts_dir: Path,
    run_started_at: float | None = None,
) -> dict[str, Any]:
    """Classify one artifact without confusing regenerated files with stale ones."""
    invalidations = invalidation_for_path(path, artifacts_dir)
    regenerated = (
        run_started_at is not None
        and path.stat().st_mtime >= run_started_at - 1.0
    )
    if invalidations and not regenerated:
        status = "invalidated"
    elif regenerated:
        status = "current_run"
    else:
        status = "present"
    return {
        "path": path.relative_to(artifacts_dir).as_posix(),
        "status": status,
        "invalidation_ids": invalidations if status == "invalidated" else [],
        "historical_invalidation_ids": invalidations if regenerated else [],
    }


def write_run_manifest(state: Any) -> Path:
    """Write the machine-readable contract for the current run."""
    artifacts_dir = state.config.artifacts_dir
    invalidation = load_invalidation_manifest(artifacts_dir)
    convergence = []
    for key, series in state.series_by_key.items():
        for snapshot in series:
            convergence.append(
                {
                    "configuration": key,
                    "date": str(snapshot.date.date()),
                    "converged": snapshot.metadata.get("glasso_converged", True),
                    "n_iter": snapshot.metadata.get("glasso_n_iter"),
                    "dual_gap": snapshot.metadata.get("glasso_dual_gap"),
                    "warning": snapshot.metadata.get("glasso_warning"),
                    "retry_count": snapshot.metadata.get("glasso_retry_count", 0),
                    "fallback_reason": snapshot.metadata.get("glasso_fallback_reason"),
                }
            )

    try:
        run_started_at = datetime.fromisoformat(
            state.record.generated_at
        ).timestamp()
    except (AttributeError, TypeError, ValueError):
        run_started_at = None
    artifact_rows = []
    for path in artifacts_dir.rglob("*"):
        if not path.is_file() or path.name == "run_manifest.json":
            continue
        artifact_rows.append(
            artifact_status_row(path, artifacts_dir, run_started_at)
        )

    test_status_path = artifacts_dir / "test_status.json"
    test_status = (
        json.loads(test_status_path.read_text(encoding="utf-8"))
        if test_status_path.exists()
        else {"status": "unknown", "note": "test status was not attached to this run"}
    )
    fitted = (
        state.fitted_graph_spec.to_dict()
        if state.fitted_graph_spec is not None
        else {}
    )
    payload = {
        "schema_version": 1,
        "git_commit": getattr(state.record, "git_commit", None),
        "code_fingerprint": getattr(state.record, "code_fingerprint", None),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": getattr(state.record, "run_id", None),
        "data_fingerprint": state.bundle.fingerprint,
        "config_hash": config_fingerprint(state.config),
        "universe_definition": state.bundle.universe.to_dict(),
        "date_ranges": {
            "data_start": str(state.bundle.panel["date"].min().date()),
            "data_end": str(state.bundle.panel["date"].max().date()),
            "graph_start": (
                str(min(series.dates.min() for series in state.series_by_key.values()).date())
                if state.series_by_key
                else None
            ),
            "graph_end": (
                str(max(series.dates.max() for series in state.series_by_key.values()).date())
                if state.series_by_key
                else None
            ),
        },
        "feature_schema": {
            "market": list(state.market_features.columns)
            if state.market_features is not None
            else [],
            "node": list(state.node_features.names)
            if state.node_features is not None
            else [],
        },
        "selected_parameters": fitted,
        "warnings": list(state.bundle.warnings) + list(state.assumptions),
        "convergence_diagnostics": convergence,
        "test_status": test_status,
        "artifact_status": artifact_rows,
        "invalidation_policy": invalidation.get("publication_policy", {}),
    }
    path = artifacts_dir / "run_manifest.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path
