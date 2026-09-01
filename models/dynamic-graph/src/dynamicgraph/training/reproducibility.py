"""Seeding and the reproducibility record.

Everything needed to reproduce a run -- config snapshot, package versions, data
fingerprint, git commit, feature list, hyperparameters, calibration method and
decision threshold -- is captured here and written next to the model artifacts.
"""

from __future__ import annotations

import json
import os
import platform
import random
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)


def set_global_seed(seed: int = 42) -> dict[str, Any]:
    """Seed every RNG the pipeline can reach. Returns what was actually seeded."""
    seeded: dict[str, Any] = {"seed": seed}

    random.seed(seed)
    seeded["python_random"] = True

    os.environ["PYTHONHASHSEED"] = str(seed)

    try:
        import numpy as np

        np.random.seed(seed)
        seeded["numpy"] = True
    except Exception:
        seeded["numpy"] = False

    try:
        import torch

        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.use_deterministic_algorithms(True, warn_only=True)
        if hasattr(torch, "backends") and hasattr(torch.backends, "cudnn"):
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
        seeded["torch"] = True
    except Exception:
        seeded["torch"] = False

    try:
        import optuna

        seeded["optuna_sampler_seed"] = seed
        _ = optuna  # sampler seeding happens where the study is created
    except Exception:
        seeded["optuna_sampler_seed"] = None

    logger.debug("Seeded RNGs: %s", seeded)
    return seeded


def package_versions() -> dict[str, str]:
    packages = [
        "numpy", "pandas", "scipy", "scikit-learn", "statsmodels", "networkx",
        "pyyaml", "pydantic", "matplotlib", "optuna", "torch", "torch_geometric",
        "shap", "xgboost", "lightgbm", "interpret", "python-louvain", "igraph",
    ]
    versions: dict[str, str] = {"python": sys.version.split()[0]}
    for name in packages:
        try:
            from importlib.metadata import version

            versions[name] = version(name)
        except Exception:
            try:
                module = __import__(name.replace("-", "_"))
                versions[name] = getattr(module, "__version__", "unknown")
            except Exception:
                versions[name] = "not installed"
    return versions


def git_commit(repo_root: Path | None = None) -> str | None:
    """Short git commit hash, or None when the tree is not a repository."""
    try:
        from dynamicgraph.config import REPO_ROOT

        root = repo_root or REPO_ROOT
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            commit = result.stdout.strip()
            dirty = subprocess.run(
                ["git", "status", "--porcelain"], cwd=str(root),
                capture_output=True, text=True, timeout=10,
            )
            return f"{commit}{'-dirty' if dirty.stdout.strip() else ''}"
    except Exception:
        pass
    return None


def code_fingerprint(repo_root: Path | None = None) -> str:
    """Hash executable project inputs, including uncommitted source changes."""
    import hashlib

    from dynamicgraph.config import REPO_ROOT

    root = (repo_root or REPO_ROOT).resolve()
    candidates: list[Path] = []
    for directory, patterns in (
        ("src", ("*.py",)),
        ("scripts", ("*.py",)),
        ("tests", ("*.py",)),
        ("config", ("*.yaml", "*.yml", "*.csv")),
    ):
        base = root / directory
        if base.exists():
            for pattern in patterns:
                candidates.extend(base.rglob(pattern))
    candidates.extend(
        path
        for path in (root / "pyproject.toml", root / "README.md")
        if path.exists()
    )

    digest = hashlib.sha256()
    for path in sorted(set(candidates), key=lambda item: item.as_posix()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


@dataclass
class ReproducibilityRecord:
    """Serialisable provenance for one pipeline run."""

    model_name: str = "DynamicGraph"
    model_version: str = "0.1.0"
    run_id: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    seed: int = 42
    config_fingerprint: str = ""
    config_snapshot: dict[str, Any] = field(default_factory=dict)
    data_fingerprint: str = ""
    data_date_min: str | None = None
    data_date_max: str | None = None
    n_tickers: int = 0
    git_commit: str | None = None
    code_fingerprint: str = ""
    platform_info: str = field(default_factory=lambda: f"{platform.system()} {platform.release()}")
    package_versions: dict[str, str] = field(default_factory=package_versions)
    feature_list: list[str] = field(default_factory=list)
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    calibration_method: str | None = None
    decision_thresholds: dict[str, float] = field(default_factory=dict)
    training_date: str | None = None
    optional_modules_skipped: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        data = payload.get("config_snapshot", {}).get("data", {})
        if isinstance(data, dict) and data.get("database_path"):
            data["database_path"] = "<redacted>"
        return payload

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, default=str), encoding="utf-8")
        logger.info("Reproducibility record written to %s", path)
        return path

    @classmethod
    def build(
        cls,
        config: Any,
        data_fingerprint: str = "",
        date_min: str | None = None,
        date_max: str | None = None,
        n_tickers: int = 0,
        run_id: str | None = None,
    ) -> "ReproducibilityRecord":
        from dynamicgraph.config import config_fingerprint

        return cls(
            model_version=str(config.project.version),
            run_id=run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            seed=int(config.project.seed),
            config_fingerprint=config_fingerprint(config),
            config_snapshot=config.to_dict(),
            data_fingerprint=data_fingerprint,
            data_date_min=date_min,
            data_date_max=date_max,
            n_tickers=n_tickers,
            git_commit=git_commit(),
            code_fingerprint=code_fingerprint(),
            training_date=datetime.now(timezone.utc).date().isoformat(),
        )


def detect_device(preference: str = "auto") -> str:
    """Resolve `auto` to cuda/mps/cpu. Never required for the statistical core."""
    if preference != "auto":
        return preference
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"
