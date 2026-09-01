"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import sys

from .online import initialize_online_state, update_latest
from .pipeline import run_pipeline, validate_data_only


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VN-Index regime-aware forecasting pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-data", help="Validate and profile the source data")
    validate.add_argument("--config", default="configs/default.yaml")
    discover = subparsers.add_parser(
        "discover-source",
        help="Read a database read-only and report the data.source block it needs",
    )
    discover.add_argument("path", help="Path to a CSV/parquet file, SQLite store, or DuckDB file")
    sync = subparsers.add_parser(
        "sync-source",
        help="Export data.source to project.data_path so the batch tier reads the same numbers",
    )
    sync.add_argument("--config", default="configs/default.yaml")
    sync.add_argument(
        "--destination",
        default=None,
        help="Override project.data_path (.csv or .parquet)",
    )
    for command in ["train", "backtest", "forecast", "report", "run-all"]:
        sub = subparsers.add_parser(command)
        sub.add_argument("--config", default="configs/default.yaml")
    initialize = subparsers.add_parser(
        "init-online-state", help="Seed the online update state from the latest batch run"
    )
    initialize.add_argument("--config", default="configs/default.yaml")
    update = subparsers.add_parser(
        "update-latest", help="Apply every new trading session without refitting any model"
    )
    update.add_argument("--config", default="configs/default.yaml")
    return parser


def emit_text(text: str) -> None:
    """Write text as UTF-8 whatever the console code page is."""
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        print(text)
        return
    sys.stdout.flush()
    buffer.write((text + "\n").encode("utf-8"))
    buffer.flush()


def emit_result(payload: dict) -> None:
    """Write the result as UTF-8 regardless of the console code page.

    The payloads carry Vietnamese text, and the documented deployment is
    Windows Task Scheduler/cron calling the CLI with stdout redirected to a
    file - which defaults to cp1252 on Windows and would otherwise raise
    UnicodeEncodeError after the whole run has already succeeded.
    """
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        print(text)
        return
    sys.stdout.flush()
    buffer.write((text + "\n").encode("utf-8"))
    buffer.flush()


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "discover-source":
        from .source_discovery import report

        emit_text(report(args.path))
        return
    if args.command == "sync-source":
        from .data_sync import sync_source

        result = sync_source(args.config, destination=args.destination)
    elif args.command == "validate-data":
        result = validate_data_only(args.config)
    elif args.command == "init-online-state":
        result = initialize_online_state(args.config)
    elif args.command == "update-latest":
        result = update_latest(args.config)
    else:
        # Each research command is reproducible and materializes dependent stages.
        # Existing artifacts are overwritten atomically by their producing stage.
        result = run_pipeline(args.config)
    emit_result(result)


if __name__ == "__main__":
    main()
