"""Checksum-keyed cache for model-independent causal artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, TypeVar


T = TypeVar("T")
CACHE_VERSION = "downside-causal-v1"


def cache_key(
    *,
    data_checksum: str,
    feature_config: dict[str, Any],
    artifact: str,
    horizon: int | None = None,
    split_boundaries: dict[str, Any] | None = None,
    model_config: dict[str, Any] | None = None,
) -> str:
    """Hash every dependency that can change one cached causal object."""
    payload = {
        "version": CACHE_VERSION,
        "data_checksum": data_checksum,
        "feature_config": feature_config,
        "artifact": artifact,
        "horizon": horizon,
        "split_boundaries": split_boundaries,
        "model_config": model_config,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


class ArtifactCache:
    def __init__(self, root: str | Path, enabled: bool = True) -> None:
        self.root = Path(root)
        self.enabled = bool(enabled)
        if self.enabled:
            self.root.mkdir(parents=True, exist_ok=True)

    def get_or_compute(self, key: str, compute: Callable[[], T]) -> tuple[T, str]:
        """Load a pickle by exact hash or compute and atomically replace it."""
        if not self.enabled:
            return compute(), "disabled"
        import joblib

        path = self.root / f"{key}.joblib"
        if path.exists():
            return joblib.load(path), "hit"
        value = compute()
        temporary = path.with_suffix(".tmp")
        joblib.dump(value, temporary)
        temporary.replace(path)
        return value, "miss"
