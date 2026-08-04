"""Reproducibility: seeds, fingerprints and secret hygiene."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dynamicgraph.config import config_fingerprint, load_config, redact
from dynamicgraph.graphs.snapshots import SnapshotBuildConfig, build_snapshot_series
from dynamicgraph.training.reproducibility import (
    ReproducibilityRecord,
    detect_device,
    package_versions,
    set_global_seed,
)


def test_seeding_makes_numpy_deterministic():
    set_global_seed(123)
    first = np.random.random(5)
    set_global_seed(123)
    np.testing.assert_array_equal(first, np.random.random(5))


def test_graph_construction_is_deterministic(synthetic_returns, base_config):
    build = SnapshotBuildConfig.from_config(base_config, "partial_correlation", 60, "residual")
    build.stride = 100
    a = build_snapshot_series(synthetic_returns, build, progress_every=0)
    b = build_snapshot_series(synthetic_returns, build, progress_every=0)
    assert len(a) == len(b)
    for x, y in zip(a, b):
        np.testing.assert_allclose(x.adjacency, y.adjacency, rtol=1e-12, atol=1e-14)


def test_bootstrap_stability_is_seed_deterministic(synthetic_returns, base_config):
    build = SnapshotBuildConfig.from_config(base_config, "partial_correlation", 60, "residual")
    build.stride = 400
    build.bootstrap_iterations = 8
    build.seed = 999
    a = build_snapshot_series(synthetic_returns, build, progress_every=0)
    b = build_snapshot_series(synthetic_returns, build, progress_every=0)
    for x, y in zip(a, b):
        np.testing.assert_allclose(x.stability, y.stability, rtol=1e-12)


def test_community_detection_is_seed_deterministic():
    from dynamicgraph.network.communities import detect_communities

    rng = np.random.default_rng(5)
    n = 14
    adjacency = np.abs(rng.normal(0, 1, (n, n)))
    adjacency = (adjacency + adjacency.T) / 2
    np.fill_diagonal(adjacency, 0.0)
    nodes = [f"N{i}" for i in range(n)]
    a = detect_communities(adjacency, nodes, seed=7)
    b = detect_communities(adjacency, nodes, seed=7)
    assert a.labels == b.labels


def test_config_fingerprint_is_stable_and_changes_with_content():
    config = load_config("config/default.yaml")
    first = config_fingerprint(config)
    assert first == config_fingerprint(load_config("config/default.yaml"))
    config.graph.graphical_lasso_alpha = 0.987
    assert config_fingerprint(config) != first


def test_config_fingerprint_redacts_the_database_path():
    config = load_config("config/default.yaml")
    config.data.database_path = "postgresql://user:hunter2@db.internal:5432/prices"
    payload = config.to_dict()
    _ = config_fingerprint(config)
    # `to_dict()` itself is not redacted, but the record and the fingerprint are.
    record = ReproducibilityRecord.build(config, data_fingerprint="abc")
    dumped = json.dumps(record.to_dict())
    assert "hunter2" not in dumped
    assert "<redacted>" in dumped


def test_redact_hides_credentials():
    assert "hunter2" not in redact("postgresql://user:hunter2@host/db")
    assert redact("C:/DataPro/D.dat") == "C:/DataPro/D.dat"


def test_reproducibility_record_captures_provenance():
    config = load_config("config/default.yaml")
    record = ReproducibilityRecord.build(
        config, data_fingerprint="deadbeef", date_min="2012-01-01", date_max="2026-07-24", n_tickers=30
    )
    payload = record.to_dict()
    for key in (
        "model_version", "run_id", "generated_at", "seed", "config_fingerprint",
        "data_fingerprint", "package_versions", "platform_info", "training_date",
    ):
        assert key in payload
    assert payload["data_fingerprint"] == "deadbeef"
    assert payload["n_tickers"] == 30


def test_package_versions_include_the_core_stack():
    versions = package_versions()
    for package in ("python", "numpy", "pandas", "scikit-learn"):
        assert package in versions
        assert versions[package] != "not installed"


def test_detect_device_returns_something_usable():
    assert detect_device("auto") in {"cpu", "cuda", "mps"}
    assert detect_device("cpu") == "cpu"


def test_no_secrets_committed_in_source():
    """Guard against credentials being pasted into the package."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    pattern = re.compile(
        r"(?i)(password|passwd|api[_-]?key|secret|token)\s*[=:]\s*['\"][^'\"]{6,}['\"]"
    )
    offenders = []
    for path in list((root / "src").rglob("*.py")) + list((root / "config").rglob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            snippet = match.group(0)
            if any(token in snippet.lower() for token in ("env", "none", "null", "<", "example")):
                continue
            offenders.append(f"{path.name}: {snippet[:40]}")
    assert not offenders, f"Possible secrets in source: {offenders}"


def test_run_summary_redacts_the_database_location():
    """`run_summary.json` is committed, so the source path must not survive it.

    `ReproducibilityRecord` already hashes `database_path`. The run summary was
    writing the same value in the clear, which made the hashing elsewhere
    pointless -- the repository would have published the absolute location of
    the vendor database on the operating machine.
    """
    from dynamicgraph.pipeline import _redact_source_paths

    # The connector nests its metadata under `source`, so a top-level-only
    # redaction would silently do nothing -- which is what the bug was.
    payload = {
        "n_rows": 90023,
        "source": {"path": r"C:\SomeVendor\Daily.dat", "backend": "sqlite"},
        "warnings": [{"path": r"D:\Other\feed.dat"}],
    }
    out = _redact_source_paths(payload)
    dumped = json.dumps(out)
    assert "SomeVendor" not in dumped and "Other" not in dumped
    assert out["source"]["path"].startswith("<redacted:sha256:")
    assert out["source"]["path_name"] == "Daily.dat", "the file name identifies the feed safely"
    assert out["source"]["backend"] == "sqlite", "unrelated fields must pass through"
    assert out["n_rows"] == 90023
    assert out["warnings"][0]["path"].startswith("<redacted:sha256:")

    # The digest is stable, so two runs on the same source still match.
    again = _redact_source_paths({"path": r"C:\SomeVendor\Daily.dat"})
    other = _redact_source_paths({"path": r"C:\SomeVendor\Other.dat"})
    assert again["path"] == out["source"]["path"]
    assert other["path"] != again["path"]


def test_manifest_paths_are_repo_relative():
    """Absolute paths in the manifest publish the operator's directory layout."""
    from dynamicgraph.config import REPO_ROOT
    from dynamicgraph.outputs.exporters import _relative_to_repo

    inside = REPO_ROOT / "artifacts" / "latest" / "nodes.json"
    assert _relative_to_repo(inside) == "artifacts/latest/nodes.json"
    assert _relative_to_repo(str(inside)) == "artifacts/latest/nodes.json"

    # Anything outside the repository keeps its name and loses its parents.
    outside = _relative_to_repo(Path("/somewhere/else/private/report.json"))
    assert outside == "report.json"
    assert _relative_to_repo(None) is None


def test_committed_artifacts_carry_no_absolute_paths():
    """Scan what is actually on disk, not just the functions that write it."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    artifacts = root / "artifacts"
    if not artifacts.exists():
        pytest.skip("no artifacts directory in this checkout")

    # Directories excluded from the repository may legitimately hold paths.
    skip_dirs = {"processed", "graphs", "data_audit"}
    absolute = re.compile(r"(?i)([a-z]:[\\/]{1,2}users|/home/[a-z0-9_.-]+/|/Users/)")
    offenders = []
    for path in artifacts.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".json", ".md", ".csv"}:
            continue
        if skip_dirs & set(p.name for p in path.parents):
            continue
        if path.suffix == ".log":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if absolute.search(text):
            offenders.append(str(path.relative_to(root)))
    assert not offenders, f"Absolute machine paths in committed artifacts: {offenders}"


def test_load_config_extends_chain():
    fast = load_config("config/fast.yaml")
    assert fast.project.mode == "fast"
    # Inherited from default.yaml, not restated in fast.yaml.
    assert fast.data.minimum_history_days == 252
    assert fast.graph.bootstrap_iterations == 0
