"""Command-line interface for RAEMF-MC."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

from raemf_mc.config import load_config
from raemf_mc.data.validation import validate_data_file
from raemf_mc.ops.ingest import IngestError, ingest_latest
from raemf_mc.pipeline import run_pipeline
from raemf_mc.reporting.current_monitor import generate_current_monitor
from raemf_mc.reporting.plots import generate_all_plots
from raemf_mc.reporting.report_builder import build_docs_and_readme, build_run_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="raemf-mc")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("validate-data")
    p.add_argument("--data", required=True)
    p.add_argument("--output-dir", default="outputs/data_validation")

    def add_bayesian_options(command: argparse.ArgumentParser) -> None:
        command.add_argument("--bayesian", action="store_true", help="Enable the Variational Bayesian scenario layer")
        command.add_argument(
            "--bayesian-method",
            choices=["fullrank_advi", "meanfield_advi"],
            help="Variational family; default is read from config",
        )
        command.add_argument("--posterior-draws", type=int, help="Number of retained posterior draws")
        command.add_argument("--advi-steps", type=int, help="Number of ADVI optimization steps")
        command.add_argument("--use-saved-posterior", help="Load this posterior directory without refitting deployment")
        command.add_argument(
            "--compare-vb-baseline",
            action="store_true",
            help="Write original, posterior-mean and posterior-draw MC comparison",
        )
        command.add_argument("--seed", type=int, help="Deterministic posterior and Monte Carlo seed")

    p = sub.add_parser("run")
    p.add_argument("--data", required=True)
    p.add_argument("--config", required=True)
    add_bayesian_options(p)

    p = sub.add_parser("report")
    p.add_argument("--run-dir", required=True)

    p = sub.add_parser("plots")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--data", default="data.csv")

    p = sub.add_parser("forecast-latest")
    p.add_argument("--data", required=True)
    p.add_argument("--config", required=True)
    add_bayesian_options(p)

    p = sub.add_parser("current-report")
    p.add_argument("--data", default="VNINDEX_Daily.csv")
    p.add_argument("--baseline-run", default="outputs/latest")
    p.add_argument("--config", default="configs/laptop.yaml")
    p.add_argument("--output-dir", default="outputs/current_monitor")
    p.add_argument("--readme", default="README.md")

    p = sub.add_parser("reproduce")
    p.add_argument("--data", default="data.csv")
    p.add_argument("--config", default="configs/laptop.yaml")
    add_bayesian_options(p)

    p = sub.add_parser("fit-variational", help="Fit and save a causal scenario posterior")
    p.add_argument("--data", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--output-dir", default="outputs/bayesian")
    add_bayesian_options(p)

    p = sub.add_parser("forecast-vb", help="Run forecast with posterior-draw Monte Carlo")
    p.add_argument("--data", required=True)
    p.add_argument("--config", required=True)
    add_bayesian_options(p)

    p = sub.add_parser("compare-vb", help="Compare original, posterior-mean and posterior-draw Monte Carlo")
    p.add_argument("--data", required=True)
    p.add_argument("--config", required=True)
    add_bayesian_options(p)

    p = sub.add_parser("posterior-report", help="Read a saved posterior and write its summary")
    p.add_argument("--posterior-dir", required=True)
    p.add_argument("--output", help="CSV đích; mặc định posterior_summary.csv trong artifact")

    p = sub.add_parser(
        "benchmark-distribution",
        help="Run checkpointed leakage-safe OOS distribution benchmark",
    )
    p.add_argument("--data", default="data.csv")
    p.add_argument("--config", default="configs/benchmark_distribution_laptop.yaml")
    p.add_argument("--output-dir", default="outputs/distribution_oos_laptop")
    p.add_argument("--no-resume", action="store_true", help="Ignore completed fold checkpoints")

    p = sub.add_parser(
        "benchmark-plots",
        help="Generate detailed plots from saved OOS distribution artifacts",
    )
    p.add_argument("--run-dir", default="outputs/distribution_oos_laptop")

    p = sub.add_parser(
        "benchmark-regime-head",
        help="So sánh OOS: EBM vs Bayesian regime head vs XGBoost vs RF vs MACD",
    )
    p.add_argument("--data", default="data.csv")
    p.add_argument("--config", default="configs/laptop_vb.yaml")
    p.add_argument("--output-dir", default="outputs/regime_head_benchmark")

    p = sub.add_parser("merge-data", help="Hợp nhất data.csv và VNINDEX_Daily.csv thành chuỗi chuẩn")
    p.add_argument("--primary", default="VNINDEX_Daily.csv")
    p.add_argument("--secondary", default="data.csv")
    p.add_argument("--output-dir", default="outputs/latest")

    p = sub.add_parser("hardware-report", help="Kiểm tra GPU/CUDA và benchmark CPU-vs-GPU")
    p.add_argument("--output-dir", default="outputs/latest")

    p = sub.add_parser("ingest-data", help="Nạp file DataPro mới nhất từ incoming/ vào lịch sử chính")
    p.add_argument("--data", default="VNINDEX_Daily.csv")
    p.add_argument("--incoming-dir", default="incoming")
    p.add_argument("--backup-dir", default="backups")

    p = sub.add_parser("daily", help="Chu trình hằng ngày: ingest -> validate -> current-report")
    p.add_argument("--data", default="VNINDEX_Daily.csv")
    p.add_argument("--incoming-dir", default="incoming")
    p.add_argument("--backup-dir", default="backups")
    p.add_argument("--baseline-run", default="outputs/latest")
    p.add_argument("--config", default="configs/laptop.yaml")
    p.add_argument("--output-dir", default="outputs/current_monitor")
    p.add_argument("--readme", default="README.md")
    p = sub.add_parser(
        "downside-experiment",
        help="Chạy benchmark CPU nested-purged cho binary Risk-off head",
    )
    p.add_argument("--data", default="VNINDEX_Daily.csv")
    p.add_argument("--config", default="configs/cpu_smoke.yaml")

    p = sub.add_parser(
        "downside-report",
        help="Tạo lại báo cáo và biểu đồ từ artifact downside đã lưu",
    )
    p.add_argument("--run-dir", required=True)

    p = sub.add_parser(
        "shadow-update",
        help="Ghi dự báo Risk-off bất biến và chấm các origin đã đủ horizon",
    )
    p.add_argument("--data", default="VNINDEX_Daily.csv")
    p.add_argument("--config", default="configs/cpu_final.yaml")
    p.add_argument("--registry", default="outputs/shadow_registry/forecast_registry.csv")
    return parser


def _apply_bayesian_overrides(config: dict[str, object], args: argparse.Namespace, *, force: bool = False) -> dict[str, object]:
    updated = copy.deepcopy(config)
    section = updated.setdefault("bayesian", {})
    if not isinstance(section, dict):
        raise ValueError("Config key 'bayesian' must be a mapping")
    if force or getattr(args, "bayesian", False) or getattr(args, "compare_vb_baseline", False):
        section["enabled"] = True
    if getattr(args, "bayesian_method", None):
        section["method"] = args.bayesian_method
    if getattr(args, "posterior_draws", None) is not None:
        if args.posterior_draws <= 0:
            raise ValueError("--posterior-draws must be positive")
        section["posterior_draws"] = args.posterior_draws
    if getattr(args, "advi_steps", None) is not None:
        if args.advi_steps <= 0:
            raise ValueError("--advi-steps must be positive")
        section["advi_steps"] = args.advi_steps
    if getattr(args, "use_saved_posterior", None):
        section["use_saved_posterior"] = args.use_saved_posterior
        section["enabled"] = True
    if getattr(args, "seed", None) is not None:
        section["random_seed"] = args.seed
        runtime = updated.setdefault("runtime", {})
        if isinstance(runtime, dict):
            runtime["seed"] = args.seed
    return updated


def _run_ingest(args: argparse.Namespace) -> dict[str, object]:
    result = ingest_latest(target_csv=args.data, incoming_dir=args.incoming_dir, backup_dir=args.backup_dir)
    summary = result.to_dict()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "validate-data":
        profile = validate_data_file(args.data, args.output_dir)
        print(json.dumps(profile, indent=2, ensure_ascii=False))
    elif args.cmd in {"run", "forecast-latest", "forecast-vb", "compare-vb"}:
        config = _apply_bayesian_overrides(
            load_config(args.config),
            args,
            force=args.cmd in {"forecast-vb", "compare-vb"},
        )
        run_dir = run_pipeline(args.data, config)
        print(run_dir)
    elif args.cmd == "report":
        build_run_report(args.run_dir)
        build_docs_and_readme(args.run_dir)
        print(Path(args.run_dir) / "report.md")
    elif args.cmd == "current-report":
        config = load_config(args.config)
        output_dir = generate_current_monitor(args.data, args.baseline_run, config, args.output_dir, args.readme)
        print(output_dir / "report_for_nonspecialists.md")
    elif args.cmd == "plots":
        figures = generate_all_plots(args.run_dir, args.data)
        print(f"Generated {len(figures)} figures in {Path(args.run_dir) / 'figures'}")
    elif args.cmd == "reproduce":
        config = _apply_bayesian_overrides(load_config(args.config), args)
        run_dir = run_pipeline(args.data, config)
        print(run_dir)
    elif args.cmd == "fit-variational":
        from raemf_mc.bayesian.workflow import fit_variational_from_data

        config = _apply_bayesian_overrides(load_config(args.config), args, force=True)
        output_dir = fit_variational_from_data(args.data, config, args.output_dir)
        print(output_dir)
    elif args.cmd == "posterior-report":
        from raemf_mc.bayesian.variational import VariationalScenarioModel

        model = VariationalScenarioModel.load(args.posterior_dir)
        output = Path(args.output) if args.output else Path(args.posterior_dir) / "posterior_summary.csv"
        model.posterior_summary().to_csv(output, index=False)
        print(output)
    elif args.cmd == "benchmark-distribution":
        from raemf_mc.evaluation.oos_distribution_benchmark import run_oos_distribution_benchmark

        config = load_config(args.config)
        output = run_oos_distribution_benchmark(
            args.data,
            config,
            args.output_dir,
            resume=not args.no_resume,
        )
        print(output)
    elif args.cmd == "benchmark-plots":
        from raemf_mc.reporting.oos_distribution_plots import generate_oos_distribution_plots

        figures = generate_oos_distribution_plots(args.run_dir)
        print(f"Generated {len(figures)} figures in {Path(args.run_dir) / 'figures'}")
    elif args.cmd == "benchmark-regime-head":
        from raemf_mc.evaluation.regime_head_benchmark import run_regime_head_benchmark

        config = load_config(args.config)
        output = run_regime_head_benchmark(args.data, config, args.output_dir)
        print(output)
    elif args.cmd == "merge-data":
        from raemf_mc.data.merge import merge_price_histories, write_merge_artifacts

        result = merge_price_histories(args.primary, args.secondary)
        destination = write_merge_artifacts(result, args.output_dir)
        print(json.dumps({k: v for k, v in result.report.items() if not k.endswith("_meta")}, indent=2, ensure_ascii=False, default=str))
        print(destination / "canonical_vnindex.csv")
    elif args.cmd == "hardware-report":
        from raemf_mc.runtime.hardware import write_hardware_artifacts

        report = write_hardware_artifacts(args.output_dir)
        print(json.dumps(report["torch"], indent=2, ensure_ascii=False))
    elif args.cmd == "ingest-data":
        try:
            _run_ingest(args)
        except IngestError as exc:
            raise SystemExit(f"INGEST TỪ CHỐI: {exc}") from exc
    elif args.cmd == "daily":
        try:
            summary = _run_ingest(args)
        except IngestError as exc:
            raise SystemExit(f"INGEST TỪ CHỐI: {exc}") from exc
        if summary["status"] == "no_new_file":
            print(f"Không có file mới trong {args.incoming_dir}/ — chạy với dữ liệu hiện có.")
        validate_data_file(args.data, "outputs/data_validation")
        config = load_config(args.config)
        output_dir = generate_current_monitor(args.data, args.baseline_run, config, args.output_dir, args.readme)
        try:
            figures = generate_all_plots(args.baseline_run, args.data)
            print(f"Đã vẽ lại {len(figures)} hình nghiên cứu theo dữ liệu mới trong {Path(args.baseline_run) / 'figures'}")
        except Exception as exc:  # noqa: BLE001 - báo cáo chính đã xong, hình nghiên cứu không được chặn kết quả
            print(f"[CẢNH BÁO] Không vẽ lại được hình nghiên cứu: {exc}")
        print(output_dir / "report_for_nonspecialists.md")
    elif args.cmd == "downside-experiment":
        from raemf_mc.evaluation.downside_experiment import run_downside_experiment

        output = run_downside_experiment(args.data, load_config(args.config))
        print(output)
    elif args.cmd == "downside-report":
        from raemf_mc.reporting.downside_report import build_downside_report

        output = build_downside_report(args.run_dir)
        print(output)
    elif args.cmd == "shadow-update":
        from raemf_mc.evaluation.shadow_update import update_shadow_registry

        output = update_shadow_registry(
            args.data,
            load_config(args.config),
            registry_path=args.registry,
        )
        print(output)


if __name__ == "__main__":
    main()
