"""DynamicGraph command line interface.

    python -m dynamicgraph.cli discover-data
    python -m dynamicgraph.cli audit-data       --config config/local.yaml
    python -m dynamicgraph.cli build-features   --config config/local.yaml
    python -m dynamicgraph.cli build-graphs     --config config/local.yaml
    python -m dynamicgraph.cli train-baselines  --config config/local.yaml
    python -m dynamicgraph.cli train-gnn        --config config/full.yaml
    python -m dynamicgraph.cli walk-forward     --config config/local.yaml
    python -m dynamicgraph.cli generate-latest  --config config/local.yaml
    python -m dynamicgraph.cli export-website   --config config/local.yaml
    python -m dynamicgraph.cli run-all          --config config/local.yaml
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

try:
    import typer

    _HAS_TYPER = True
except Exception:  # pragma: no cover
    _HAS_TYPER = False

from dynamicgraph.config import CONFIG_DIR, REPO_ROOT, load_config
from dynamicgraph.logging_config import get_logger, setup_logging

logger = get_logger(__name__)

if _HAS_TYPER:
    app = typer.Typer(
        add_completion=False,
        help="DynamicGraph - dynamic financial network model for VN30.",
        no_args_is_help=True,
    )
else:  # pragma: no cover
    app = None


def _bootstrap(
    config_path: str | None,
    fast: bool = False,
    full: bool = False,
    start_date: str | None = None,
    end_date: str | None = None,
    log_level: str | None = None,
    seed: int | None = None,
) -> Any:
    """Load config, apply CLI overrides, configure logging and seed RNGs."""
    from dynamicgraph.training.reproducibility import set_global_seed

    if fast and full:
        raise ValueError("--fast and --full are mutually exclusive.")

    path = config_path
    if path is None:
        if fast:
            path = str(CONFIG_DIR / "fast.yaml")
        elif full:
            path = str(CONFIG_DIR / "full.yaml")

    overrides: dict[str, Any] = {}
    if fast and config_path is not None:
        overrides.setdefault("project", {})["mode"] = "fast"
        overrides.setdefault("graph", {}).update(
            {"windows": [60, 120], "bootstrap_iterations": 0, "snapshot_stride": 5,
             "build_raw_and_residual": False}
        )
        overrides.setdefault("models", {}).update({"run_random_forest": False, "run_temporal_gnn": False})
        overrides.setdefault("evaluation", {})["bootstrap_iterations"] = 200
    if full and config_path is not None:
        overrides.setdefault("project", {})["mode"] = "full"
        overrides.setdefault("graph", {}).update(
            {"edge_filter_method": "stability", "bootstrap_iterations": 100, "snapshot_stride": 1}
        )
    if start_date:
        overrides.setdefault("data", {})["start_date"] = start_date
    if end_date:
        overrides.setdefault("data", {})["end_date"] = end_date
    if seed is not None:
        overrides.setdefault("project", {})["seed"] = seed
        overrides.setdefault("training", {})["random_seed"] = seed
    if log_level:
        overrides.setdefault("logging", {})["level"] = log_level

    config = load_config(path, overrides or None)
    setup_logging(
        level=str(config.logging.level),
        log_file=config.resolve_path(config.logging.file),
        use_rich=bool(config.logging.rich),
    )
    set_global_seed(int(config.project.seed))
    logger.info(
        "DynamicGraph %s | mode=%s | seed=%d | config=%s",
        config.project.version, config.project.mode, config.project.seed, path or "default",
    )
    return config


def _load_state(config: Any, need: str = "network", force: bool = False) -> Any:
    """Run the stages required to reach `need`."""
    from dynamicgraph import pipeline as P

    state = P.PipelineState(config=config)
    state = P.stage_data(state, force=force)
    if need == "data":
        return state
    state = P.stage_features(state, force=force)
    if need == "features":
        return state
    state = P.stage_graphs(state, force=force)
    if need == "graphs":
        return state
    state = P.stage_network(state)
    return state


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def _cmd_discover_data(
    root: str | None = None, max_depth: int = 6, log_level: str = "INFO"
) -> int:
    from dynamicgraph.data.discovery import discover_data_sources, write_inventory

    setup_logging(log_level, None, True)
    roots = [Path(root)] if root else None
    inventory = discover_data_sources(roots=roots, project_root=REPO_ROOT, max_depth=max_depth)
    out_dir = REPO_ROOT / "artifacts" / "data_audit"
    json_path, md_path = write_inventory(inventory, out_dir)

    recommended = inventory.get("recommended")
    print("\n" + "=" * 78)
    print("DynamicGraph - data discovery")
    print("=" * 78)
    print(f"Candidates scanned : {inventory['n_candidates']}")
    print(f"Inventory JSON     : {json_path}")
    print(f"Inventory Markdown : {md_path}")
    if recommended:
        print("\nRecommended source:")
        print(f"  path     : {recommended['path']}")
        print(f"  backend  : {recommended.get('backend')}")
        print(f"  tickers  : {recommended.get('n_tickers')}")
        print(f"  range    : {recommended.get('date_min')} .. {recommended.get('date_max')}")
        print(f"  adjusted : {recommended.get('has_adjusted_price')}")
        print("\nSet this in config/local.yaml under `data.database_path`.")
    else:
        print("\nNo usable data source found.")
        print("Copy config/local.example.yaml to config/local.yaml and set `data.database_path`,")
        print("or export DYNAMICGRAPH_DATABASE_URL.")
    print("=" * 78 + "\n")
    return 0


def _cmd_audit_data(config: Any, force: bool = False) -> int:
    from dynamicgraph.outputs.reports import write_data_audit_report

    state = _load_state(config, need="data", force=force)
    bundle = state.bundle
    path = write_data_audit_report(
        config.artifact_path("reports", "data_audit_report.md"), bundle
    )
    import json

    config.artifact_path("data_audit", "panel_audit.json").write_text(
        json.dumps(bundle.to_dict(), indent=2, default=str), encoding="utf-8"
    )

    print("\n" + "=" * 78)
    print("DynamicGraph - data audit")
    print("=" * 78)
    print(f"Rows        : {len(bundle.panel):,}")
    print(f"Tickers     : {bundle.panel['ticker'].nunique()} (index: {bundle.index_ticker})")
    print(f"Date range  : {bundle.panel['date'].min().date()} .. {bundle.panel['date'].max().date()}")
    print(f"Adjusted    : {bundle.source_metadata.get('has_adjusted_price')}")
    print(f"Survivorship: {bundle.universe.survivorship_bias}")
    print(f"Errors      : {len(bundle.validation.errors)}   Warnings: {len(bundle.validation.warnings)}")
    print(f"Report      : {path}")
    print("=" * 78 + "\n")
    return 1 if bundle.validation.errors else 0


def _cmd_build_features(config: Any, force: bool = False) -> int:
    state = _load_state(config, need="features", force=force)
    print(f"\nNode features : {len(state.node_features.frames)}")
    print(f"Market features: {state.market_features.shape[1]}")
    print(f"Targets        : {list(state.targets.labels.columns)}")
    print(f"Cached under   : {config.artifacts_dir / 'processed'}\n")
    return 0


def _cmd_build_graphs(config: Any, force: bool = False) -> int:
    from dynamicgraph import pipeline as P

    state = _load_state(config, need="graphs", force=force)
    state = P.stage_network(state)
    print("\nGraph layers built:")
    for key, series in state.series_by_key.items():
        print(f"  {key:48s} {len(series):5d} snapshots")
    print(f"\nStress score history: {config.artifacts_dir / 'metrics' / 'stress_score_history.csv'}\n")
    return 0


def _cmd_walk_forward(config: Any, force: bool = False) -> int:
    from dynamicgraph import pipeline as P

    state = _load_state(config, need="network", force=force)
    state = P.stage_predictive(state)
    if state.experiment is None or state.experiment.metrics.empty:
        print("\nNo out-of-sample results were produced.\n")
        return 1

    metrics = state.experiment.metrics
    columns = [c for c in ("horizon", "feature_set", "model", "n", "base_rate", "brier",
                           "brier_skill_score", "auprc", "mcc") if c in metrics.columns]
    print("\n" + "=" * 78)
    print("Walk-forward out-of-sample results")
    print("=" * 78)
    print(metrics[columns].sort_values(["horizon", "brier"]).to_string(index=False))
    print(f"\nIncremental-value verdict: {state.verdict.get('verdict')}")
    print(state.verdict.get("interpretation", ""))
    print("=" * 78 + "\n")
    return 0


def _cmd_train_baselines(config: Any, force: bool = False) -> int:
    return _cmd_walk_forward(config, force=force)


def _cmd_train_gnn(config: Any, force: bool = False) -> int:
    from dynamicgraph import pipeline as P

    state = _load_state(config, need="network", force=force)
    state = P.stage_predictive(state)
    state = P.stage_gnn(state)
    if state.gnn_result is None:
        print("\nTemporal GNN did not run (disabled or dependencies unavailable).")
        for note in state.skipped_modules:
            print(f"  - {note}")
        print()
        return 1
    print("\nTemporal GNN result:")
    for key, value in state.gnn_result.items():
        print(f"  {key}: {value}")
    print()
    return 0


def _cmd_allocate(config: Any, force: bool = False) -> int:
    """Run the allocation experiment on its own and print the headline table."""
    from dynamicgraph import pipeline as P

    state = _load_state(config, need="network", force=force)
    state = P.stage_allocation(state)
    if not state.allocation:
        print("\nAllocation produced no results; see the log for the reason.\n")
        return 1

    summary = state.allocation["summary"]
    verdict = state.allocation_verdict
    columns = [
        c
        for c in ("key", "annual_volatility", "annual_return", "sharpe", "max_drawdown",
                  "mean_effective_n_bets", "mean_turnover_traded")
        if c in summary.columns
    ]
    print("\n" + "=" * 92)
    print("DynamicGraph - capital allocation, walk-forward out of sample")
    print("=" * 92)
    print(summary[columns].to_string(index=False, float_format=lambda v: f"{v:,.4f}"))
    print("-" * 92)
    print(f"Verdict : {verdict.get('verdict')}")
    print(f"          {verdict.get('interpretation')}")
    print(f"Caveat  : {verdict.get('caveat')}")
    print(f"Artifacts: {config.artifacts_dir / 'allocation'}")
    print("=" * 92 + "\n")
    return 0


def _cmd_generate_latest(config: Any, force: bool = False) -> int:
    from dynamicgraph import pipeline as P
    from dynamicgraph.latest import generate_latest

    state = _load_state(config, need="network", force=force)
    state = P.stage_directed(state)
    state = P.stage_observatory(state)
    state = P.stage_predictive(state)
    state = P.stage_graph_validation(state)
    payload = generate_latest(state)
    P.write_state_summary(state)

    print("\n" + "=" * 78)
    print("DynamicGraph - latest state")
    print("=" * 78)
    print(f"As of        : {payload['model']['as_of_date']}")
    print(f"Network state: {payload['network_state']['label']}")
    print(f"Stress score : {payload['network_state']['stress_score']}")
    print(f"Nodes/edges  : {payload['universe']['node_count']} / {len(payload['top_edges'])} published")
    print(f"Artifacts    : {config.artifacts_dir / 'latest'}")
    print("=" * 78 + "\n")
    return 0


def _cmd_init_online_state(config: Any, force: bool = False) -> int:
    from dynamicgraph.online.runner import initialize_online_state

    _print_online(initialize_online_state(config))
    return 0


def _cmd_update_latest(config: Any, force: bool = False) -> int:
    from dynamicgraph.online.runner import update_latest_online

    _print_online(update_latest_online(config))
    return 0


def _print_online(result: dict) -> None:
    """Emit the result as UTF-8 whatever the console code page is.

    The documented deployment is Task Scheduler/cron with stdout redirected to
    a file, which defaults to cp1252 on Windows and cannot encode the Vietnamese
    strings these payloads carry.
    """
    import json
    import sys

    text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        print(text)
        return
    sys.stdout.flush()
    buffer.write((text + "\n").encode("utf-8"))
    buffer.flush()


def _cmd_export_website(config: Any, force: bool = False) -> int:
    return _cmd_generate_latest(config, force=force)


def _cmd_run_all(config: Any, force: bool = False) -> int:
    from dynamicgraph import pipeline as P
    from dynamicgraph.latest import generate_latest

    state = P.PipelineState(config=config)
    state = P.stage_data(state, force=force)
    state = P.stage_features(state, force=force)
    state = P.stage_graphs(state, force=force)
    state = P.stage_network(state)
    state = P.stage_directed(state)
    state = P.stage_observatory(state)
    state = P.stage_predictive(state)
    state = P.stage_graph_validation(state)
    state = P.stage_allocation(state)
    state = P.stage_gnn(state)
    payload = generate_latest(state)
    summary_path = P.write_state_summary(state)

    print("\n" + "=" * 78)
    print("DynamicGraph - full pipeline complete")
    print("=" * 78)
    print(f"Data          : {state.bundle.panel['date'].min().date()} .. "
          f"{state.bundle.panel['date'].max().date()} "
          f"({state.bundle.panel['ticker'].nunique()} tickers)")
    print(f"Graph layers  : {len(state.series_by_key)}")
    print(f"Snapshots     : {sum(len(s) for s in state.series_by_key.values())}")
    print(f"Folds         : {len(state.folds)}")
    print(f"Network state : {payload['network_state']['label']} "
          f"(score {payload['network_state']['stress_score']})")
    print(f"Graph value   : {state.verdict.get('verdict')}")
    print(f"Artifacts     : {config.artifacts_dir}")
    print(f"Run summary   : {summary_path}")
    print("=" * 78 + "\n")
    return 0


# ---------------------------------------------------------------------------
# Typer wiring
# ---------------------------------------------------------------------------
if _HAS_TYPER:
    ConfigOption = typer.Option(None, "--config", "-c", help="Path to a YAML config file.")
    FastOption = typer.Option(False, "--fast", help="Fast mode: fewer scales, no bootstrap, no GNN.")
    FullOption = typer.Option(False, "--full", help="Full mode: multi-scale, stability, tuning, GNN.")
    StartOption = typer.Option(None, "--start-date", help="Override data.start_date (YYYY-MM-DD).")
    EndOption = typer.Option(None, "--end-date", help="Override data.end_date (YYYY-MM-DD).")
    AsOfOption = typer.Option(None, "--as-of-date", help="Publish the state as of this date.")
    ForceOption = typer.Option(False, "--force", help="Ignore caches and recompute.")
    LogOption = typer.Option(None, "--log-level", help="DEBUG|INFO|WARNING|ERROR.")
    SeedOption = typer.Option(None, "--seed", help="Override the random seed.")

    @app.command("discover-data")
    def discover_data(
        root: Optional[str] = typer.Option(None, "--root", help="Restrict the scan to this directory."),
        max_depth: int = typer.Option(6, "--max-depth"),
        log_level: str = typer.Option("INFO", "--log-level"),
    ) -> None:
        """Scan the machine for candidate VN30 data sources (read-only)."""
        raise typer.Exit(_cmd_discover_data(root, max_depth, log_level))

    @app.command("audit-data")
    def audit_data(
        config: Optional[str] = ConfigOption, fast: bool = FastOption, full: bool = FullOption,
        start_date: Optional[str] = StartOption, end_date: Optional[str] = EndOption,
        force: bool = ForceOption, log_level: Optional[str] = LogOption,
        seed: Optional[int] = SeedOption,
    ) -> None:
        """Load, normalise and validate the panel; write the data-audit report."""
        cfg = _bootstrap(config, fast, full, start_date, end_date, log_level, seed)
        raise typer.Exit(_cmd_audit_data(cfg, force))

    @app.command("build-features")
    def build_features(
        config: Optional[str] = ConfigOption, fast: bool = FastOption, full: bool = FullOption,
        start_date: Optional[str] = StartOption, end_date: Optional[str] = EndOption,
        force: bool = ForceOption, log_level: Optional[str] = LogOption,
        seed: Optional[int] = SeedOption,
    ) -> None:
        """Build node features, market features and forward targets."""
        cfg = _bootstrap(config, fast, full, start_date, end_date, log_level, seed)
        raise typer.Exit(_cmd_build_features(cfg, force))

    @app.command("build-graphs")
    def build_graphs(
        config: Optional[str] = ConfigOption, fast: bool = FastOption, full: bool = FullOption,
        start_date: Optional[str] = StartOption, end_date: Optional[str] = EndOption,
        force: bool = ForceOption, log_level: Optional[str] = LogOption,
        seed: Optional[int] = SeedOption,
    ) -> None:
        """Build the dynamic graph snapshots and the network metric history."""
        cfg = _bootstrap(config, fast, full, start_date, end_date, log_level, seed)
        raise typer.Exit(_cmd_build_graphs(cfg, force))

    @app.command("train-baselines")
    def train_baselines(
        config: Optional[str] = ConfigOption, fast: bool = FastOption, full: bool = FullOption,
        start_date: Optional[str] = StartOption, end_date: Optional[str] = EndOption,
        force: bool = ForceOption, log_level: Optional[str] = LogOption,
        seed: Optional[int] = SeedOption,
    ) -> None:
        """Train the tabular baselines with purged walk-forward evaluation."""
        cfg = _bootstrap(config, fast, full, start_date, end_date, log_level, seed)
        raise typer.Exit(_cmd_train_baselines(cfg, force))

    @app.command("walk-forward")
    def walk_forward(
        config: Optional[str] = ConfigOption, fast: bool = FastOption, full: bool = FullOption,
        start_date: Optional[str] = StartOption, end_date: Optional[str] = EndOption,
        force: bool = ForceOption, log_level: Optional[str] = LogOption,
        seed: Optional[int] = SeedOption,
    ) -> None:
        """Run the full out-of-sample walk-forward experiment."""
        cfg = _bootstrap(config, fast, full, start_date, end_date, log_level, seed)
        raise typer.Exit(_cmd_walk_forward(cfg, force))

    @app.command("allocate")
    def allocate(
        config: Optional[str] = ConfigOption, fast: bool = FastOption, full: bool = FullOption,
        start_date: Optional[str] = StartOption, end_date: Optional[str] = EndOption,
        force: bool = ForceOption, log_level: Optional[str] = LogOption,
        seed: Optional[int] = SeedOption,
    ) -> None:
        """Backtest the covariance estimators and weight rules out of sample."""
        cfg = _bootstrap(config, fast, full, start_date, end_date, log_level, seed)
        raise typer.Exit(_cmd_allocate(cfg, force))

    @app.command("train-gnn")
    def train_gnn(
        config: Optional[str] = ConfigOption, fast: bool = FastOption, full: bool = FullOption,
        start_date: Optional[str] = StartOption, end_date: Optional[str] = EndOption,
        force: bool = ForceOption, log_level: Optional[str] = LogOption,
        seed: Optional[int] = SeedOption,
    ) -> None:
        """Train the Temporal GNN and compare it against the baselines."""
        cfg = _bootstrap(config, fast, full, start_date, end_date, log_level, seed)
        raise typer.Exit(_cmd_train_gnn(cfg, force))

    @app.command("generate-latest")
    def generate_latest_cmd(
        config: Optional[str] = ConfigOption, fast: bool = FastOption, full: bool = FullOption,
        start_date: Optional[str] = StartOption, end_date: Optional[str] = EndOption,
        as_of_date: Optional[str] = AsOfOption, force: bool = ForceOption,
        log_level: Optional[str] = LogOption, seed: Optional[int] = SeedOption,
    ) -> None:
        """Produce artifacts/latest/, the figures and the markdown reports."""
        cfg = _bootstrap(config, fast, full, start_date, as_of_date or end_date, log_level, seed)
        raise typer.Exit(_cmd_generate_latest(cfg, force))

    @app.command("export-website")
    def export_website(
        config: Optional[str] = ConfigOption, fast: bool = FastOption, full: bool = FullOption,
        start_date: Optional[str] = StartOption, end_date: Optional[str] = EndOption,
        as_of_date: Optional[str] = AsOfOption, force: bool = ForceOption,
        log_level: Optional[str] = LogOption, seed: Optional[int] = SeedOption,
    ) -> None:
        """Alias of generate-latest: write every website-facing artifact."""
        cfg = _bootstrap(config, fast, full, start_date, as_of_date or end_date, log_level, seed)
        raise typer.Exit(_cmd_export_website(cfg, force))

    @app.command("init-online-state")
    def init_online_state(
        config: Optional[str] = ConfigOption, fast: bool = FastOption, full: bool = FullOption,
        start_date: Optional[str] = StartOption, end_date: Optional[str] = EndOption,
        as_of_date: Optional[str] = AsOfOption, force: bool = ForceOption,
        log_level: Optional[str] = LogOption, seed: Optional[int] = SeedOption,
    ) -> None:
        """Seed the per-session online state from the latest batch run."""
        cfg = _bootstrap(config, fast, full, start_date, as_of_date or end_date, log_level, seed)
        raise typer.Exit(_cmd_init_online_state(cfg, force))

    @app.command("update-latest")
    def update_latest(
        config: Optional[str] = ConfigOption, fast: bool = FastOption, full: bool = FullOption,
        start_date: Optional[str] = StartOption, end_date: Optional[str] = EndOption,
        as_of_date: Optional[str] = AsOfOption, force: bool = ForceOption,
        log_level: Optional[str] = LogOption, seed: Optional[int] = SeedOption,
    ) -> None:
        """Apply every new trading session without refitting any model."""
        cfg = _bootstrap(config, fast, full, start_date, as_of_date or end_date, log_level, seed)
        raise typer.Exit(_cmd_update_latest(cfg, force))

    @app.command("run-all")
    def run_all(
        config: Optional[str] = ConfigOption, fast: bool = FastOption, full: bool = FullOption,
        start_date: Optional[str] = StartOption, end_date: Optional[str] = EndOption,
        as_of_date: Optional[str] = AsOfOption, force: bool = ForceOption,
        log_level: Optional[str] = LogOption, seed: Optional[int] = SeedOption,
    ) -> None:
        """Run every phase end to end: data -> graphs -> OOS -> website."""
        cfg = _bootstrap(config, fast, full, start_date, as_of_date or end_date, log_level, seed)
        raise typer.Exit(_cmd_run_all(cfg, force))


def main(argv: list[str] | None = None) -> int:
    """Programmatic entry point, used by `scripts/*.py` and by `-m dynamicgraph.cli`.

    Typer reads `sys.argv` directly, so an explicit `argv` has to be installed
    before handing over; otherwise the command injected by the script wrappers
    would be silently dropped.
    """
    if _HAS_TYPER:
        if argv is not None:
            original = sys.argv
            sys.argv = [original[0], *argv]
            try:
                app()
            finally:
                sys.argv = original
        else:
            app()
        return 0

    import argparse

    parser = argparse.ArgumentParser(prog="dynamicgraph")
    parser.add_argument("command", choices=[
        "discover-data", "audit-data", "build-features", "build-graphs", "train-baselines",
        "train-gnn", "walk-forward", "allocate", "generate-latest", "export-website", "run-all",
        "init-online-state", "update-latest",
    ])
    parser.add_argument("--config", "-c", default=None)
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--as-of-date", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--log-level", default=None)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args(argv)

    if args.command == "discover-data":
        return _cmd_discover_data(None, 6, args.log_level or "INFO")

    config = _bootstrap(
        args.config, args.fast, args.full, args.start_date,
        args.as_of_date or args.end_date, args.log_level, args.seed,
    )
    dispatch = {
        "audit-data": _cmd_audit_data,
        "build-features": _cmd_build_features,
        "build-graphs": _cmd_build_graphs,
        "train-baselines": _cmd_train_baselines,
        "train-gnn": _cmd_train_gnn,
        "walk-forward": _cmd_walk_forward,
        "allocate": _cmd_allocate,
        "generate-latest": _cmd_generate_latest,
        "export-website": _cmd_export_website,
        "init-online-state": _cmd_init_online_state,
        "update-latest": _cmd_update_latest,
        "run-all": _cmd_run_all,
    }
    return dispatch[args.command](config, args.force)


if __name__ == "__main__":
    sys.exit(main())
