"""Báo cáo tiếng Việt dựa hoàn toàn trên artifact của thử nghiệm Risk-off CPU."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from raemf_mc.reporting.tables import markdown_table


COLORS = {
    "multiclass_probability_sum": "#0072B2",
    "candidate_risk_off": "#D55E00",
}
WALL_CPU_INTERRUPTION_RATIO = 4.0


def _read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def _interrupted_runtime_rows(runtime: pd.DataFrame) -> pd.DataFrame:
    required = {"wall_time", "cpu_time"}
    if not required.issubset(runtime.columns):
        return pd.DataFrame()
    return runtime.loc[
        runtime["wall_time"]
        > WALL_CPU_INTERRUPTION_RATIO * runtime["cpu_time"].clip(lower=1),
        ["stage", "horizon", "fold", "wall_time", "cpu_time"],
    ]


def _style() -> None:
    plt.rcParams.update(
        {
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.23,
            "legend.frameon": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )


def _save(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _plot_threshold_curves(curve: pd.DataFrame, figures: Path) -> None:
    if curve.empty:
        return
    horizons = sorted(curve["horizon"].unique())
    fig, axes = plt.subplots(
        1,
        len(horizons),
        figsize=(4.3 * len(horizons), 3.8),
        squeeze=False,
    )
    for column, horizon in enumerate(horizons):
        ax = axes[0, column]
        for model, frame in curve[curve["horizon"] == horizon].groupby("model"):
            aggregate = frame.groupby("threshold", as_index=False)["expected_cost"].mean()
            ax.plot(
                aggregate["threshold"],
                aggregate["expected_cost"],
                label=model,
                color=COLORS.get(model, "#777777"),
            )
        ax.set(title=f"h{horizon}", xlabel="Ngưỡng", ylabel="Chi phí downside kỳ vọng")
    axes[0, -1].legend()
    fig.suptitle(
        "Chi phí trên validation; outer test không dùng để chọn ngưỡng",
        fontweight="bold",
    )
    _save(fig, figures / "risk_off_cost_curve.png")

    fig, axes = plt.subplots(
        1,
        len(horizons),
        figsize=(4.3 * len(horizons), 3.8),
        squeeze=False,
    )
    for column, horizon in enumerate(horizons):
        ax = axes[0, column]
        for model, frame in curve[curve["horizon"] == horizon].groupby("model"):
            aggregate = frame.groupby("threshold", as_index=False)[["precision", "recall"]].mean()
            ax.plot(
                aggregate["recall"],
                aggregate["precision"],
                label=model,
                color=COLORS.get(model, "#777777"),
            )
        ax.set(
            title=f"h{horizon}",
            xlabel="Recall Risk-off",
            ylabel="Precision Risk-off",
            xlim=(0, 1),
            ylim=(0, 1),
        )
    axes[0, -1].legend()
    fig.suptitle("Đánh đổi precision–recall trên validation", fontweight="bold")
    _save(fig, figures / "risk_off_precision_recall_curve.png")


def _plot_reliability(events: pd.DataFrame, figures: Path) -> None:
    if events.empty:
        return
    horizons = sorted(events["horizon"].unique())
    fig, axes = plt.subplots(
        1,
        len(horizons),
        figsize=(4.3 * len(horizons), 3.8),
        squeeze=False,
    )
    bins = np.linspace(0, 1, 11)
    for column, horizon in enumerate(horizons):
        ax = axes[0, column]
        ax.plot([0, 1], [0, 1], "--", color="#555555", label="Lý tưởng")
        for model, frame in events[events["horizon"] == horizon].groupby("model"):
            probability = frame["probability"].to_numpy(dtype=float)
            actual = frame["actual_risk_off"].to_numpy(dtype=float)
            centers: list[float] = []
            observed: list[float] = []
            for index in range(len(bins) - 1):
                mask = (probability >= bins[index]) & (
                    probability < bins[index + 1]
                    if index < len(bins) - 2
                    else probability <= bins[index + 1]
                )
                if mask.any():
                    centers.append(float(probability[mask].mean()))
                    observed.append(float(actual[mask].mean()))
            ax.plot(
                centers,
                observed,
                marker="o",
                color=COLORS.get(model, "#777777"),
                label=model,
            )
        ax.set(
            title=f"h{horizon}",
            xlabel="Xác suất dự báo",
            ylabel="Tỷ lệ Risk-off quan sát",
            xlim=(0, 1),
            ylim=(0, 1),
        )
    axes[0, -1].legend()
    fig.suptitle("Reliability trên nested development OOS", fontweight="bold")
    _save(fig, figures / "risk_off_reliability.png")


def _plot_fold_metrics(metrics: pd.DataFrame, figures: Path) -> None:
    if metrics.empty:
        return
    aggregate = metrics.groupby(["model", "horizon"], as_index=False)[
        ["recall", "precision", "pr_auc", "expected_cost"]
    ].mean()
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for model, frame in aggregate.groupby("model"):
        axes[0].plot(
            frame["horizon"],
            frame["recall"],
            marker="o",
            color=COLORS.get(model, "#777777"),
            label=model,
        )
        axes[1].plot(
            frame["horizon"],
            frame["expected_cost"],
            marker="o",
            color=COLORS.get(model, "#777777"),
            label=model,
        )
    axes[0].set(title="Recall Risk-off OOS", xlabel="Horizon", ylabel="Recall", ylim=(0, 1))
    axes[1].set(
        title="Chi phí downside kỳ vọng OOS",
        xlabel="Horizon",
        ylabel="Chi phí/quan sát",
    )
    axes[0].legend()
    _save(fig, figures / "risk_off_oos_comparison.png")


def _plot_bear_bootstrap(bootstrap: pd.DataFrame, figures: Path) -> None:
    if bootstrap.empty:
        return
    bear = bootstrap[
        (bootstrap["class"] == "Bear")
        & (bootstrap["metric"].isin(["recall", "precision", "pr_auc"]))
    ]
    if bear.empty:
        return
    metrics = ["recall", "precision", "pr_auc"]
    titles = {
        "recall": "Recall Bear",
        "precision": "Precision Bear",
        "pr_auc": "PR-AUC Bear one-vs-rest",
    }
    fig, axes = plt.subplots(1, len(metrics), figsize=(12, 3.8))
    for axis, metric in zip(axes, metrics, strict=True):
        frame = bear[bear["metric"] == metric].sort_values("horizon")
        estimate = frame["estimate"].to_numpy(dtype=float)
        lower = estimate - frame["ci_low"].to_numpy(dtype=float)
        upper = frame["ci_high"].to_numpy(dtype=float) - estimate
        axis.errorbar(
            frame["horizon"],
            estimate,
            yerr=np.vstack([lower, upper]),
            color="#E69F00",
            marker="o",
            capsize=4,
        )
        axis.set(
            title=titles[metric],
            xlabel="Horizon",
            ylabel="Ước lượng OOS",
            ylim=(0, 1),
        )
    fig.suptitle("Bear-specific nested OOS với moving-block CI 95%", fontweight="bold")
    _save(fig, figures / "bear_oos_diagnostics.png")


def _bear_confusion_summary(probabilities: pd.DataFrame) -> pd.DataFrame:
    required = {"horizon", "actual_class", "predicted_class"}
    if probabilities.empty or not required.issubset(probabilities.columns):
        return pd.DataFrame()
    bear = probabilities[probabilities["actual_class"] == "Bear"]
    if bear.empty:
        return pd.DataFrame()
    classes = ["Bull", "Sideway", "Bear", "Stress"]
    counts = (
        pd.crosstab(bear["horizon"], bear["predicted_class"])
        .reindex(columns=classes, fill_value=0)
        .rename(columns=lambda value: f"predicted_{str(value).lower()}")
    )
    counts.insert(0, "actual_bear", counts.sum(axis=1))
    counts["recall_bear"] = (
        counts["predicted_bear"] / counts["actual_bear"].clip(lower=1)
    )
    return counts.reset_index()


def _bear_interpretation(confusion: pd.DataFrame) -> str:
    if confusion.empty:
        return (
            "**Nhận xét:** Không đủ quan sát Bear OOS để mô tả confusion. "
            "Không dùng legacy audit để tuning hoặc khẳng định cải thiện."
        )
    ratios = "; ".join(
        f"h{int(row.horizon)}: {int(row.predicted_bear)}/{int(row.actual_bear)}"
        for row in confusion.itertuples(index=False)
    )
    uniformly_low = bool((confusion["recall_bear"] < 0.25).all())
    assessment = (
        "Recall Bear thấp ở mọi horizon trong run này."
        if uniformly_low
        else "Recall Bear không đồng đều giữa các horizon trong run này."
    )
    return (
        f"**Nhận xét:** Số Bear nhận đúng/số Bear thực tế là {ratios}. "
        f"{assessment} Các quan sát còn lại bị chuyển sang Bull, Sideway hoặc Stress. "
        "Binary Risk-off head chỉ ước lượng `P(Bear hoặc Stress)`, không xuất riêng "
        "`P(Bear)` nên không chứng minh Bear đã cải thiện. Khoảng tin cậy dùng "
        "moving-block bootstrap trên development OOS; legacy audit không tham gia "
        "tuning hay kết luận cải thiện."
    )


def _acceptance_text(risk: dict[str, object]) -> str:
    acceptance = risk.get("acceptance", {})
    if not isinstance(acceptance, dict):
        return "Không đủ artifact để đánh giá acceptance criteria."
    checks = acceptance.get("checks", {})
    if not isinstance(checks, dict):
        return f"Trạng thái: `{acceptance.get('status', 'inconclusive')}`."
    passed = sum(bool(value) for value in checks.values())
    return (
        f"Trạng thái: `{acceptance.get('status', 'inconclusive')}`; "
        f"đạt {passed}/{len(checks)} kiểm tra đã đăng ký trước. "
        "Candidate không tự động thay production classifier hoặc scenario mode."
    )


def build_downside_report(run_dir: str | Path) -> Path:
    """Tạo lại hình và báo cáo trung lập từ artifact đã lưu."""
    run_dir = Path(run_dir)
    figures = run_dir / "figures"
    figures.mkdir(exist_ok=True)
    _style()
    metrics = _read_csv(run_dir / "risk_off_metrics_by_fold.csv")
    summary = _read_csv(run_dir / "risk_off_metrics_summary.csv")
    curve = _read_csv(run_dir / "risk_off_threshold_curve.csv")
    events = _read_csv(run_dir / "risk_off_oos_events.csv")
    bootstrap = _read_csv(run_dir / "risk_off_bootstrap_differences.csv")
    multiclass_probabilities = _read_csv(
        run_dir / "multiclass_oos_probabilities.csv"
    )
    multiclass_metrics = _read_csv(run_dir / "multiclass_metrics_by_fold.csv")
    multiclass_bootstrap = _read_csv(run_dir / "multiclass_class_bootstrap.csv")
    ablation = _read_csv(run_dir / "downside_feature_ablation.csv")
    missed = _read_csv(run_dir / "missed_downside_events.csv")
    false_positive = _read_csv(run_dir / "false_positive_events.csv")
    overlay = _read_csv(run_dir / "risk_overlay_backtest.csv")
    runtime = _read_csv(run_dir / "runtime_benchmark.csv")
    legacy = _read_csv(run_dir / "legacy_audit_metrics.csv")
    risk = json.loads((run_dir / "experiment_risk_summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
    thresholds = json.loads(
        (run_dir / "risk_off_selected_thresholds.json").read_text(encoding="utf-8")
    )
    interrupted_runtime = _interrupted_runtime_rows(runtime)
    runtime_note = (
        f"Có stage có wall time lớn hơn {WALL_CPU_INTERRUPTION_RATIO:g} lần CPU time; "
        "số đo này có thể bao gồm "
        "thời gian máy sleep/suspend hoặc idle kéo dài, nên không phải benchmark wall sạch."
        if not interrupted_runtime.empty
        else (
            "Không phát hiện stage có wall time lớn hơn "
            f"{WALL_CPU_INTERRUPTION_RATIO:g} lần CPU time."
        )
    )

    _plot_threshold_curves(curve, figures)
    _plot_reliability(events, figures)
    _plot_fold_metrics(metrics, figures)
    _plot_bear_bootstrap(multiclass_bootstrap, figures)

    multiclass_summary = pd.DataFrame()
    if not multiclass_metrics.empty:
        multiclass_summary = multiclass_metrics.groupby(
            ["model", "horizon"],
            as_index=False,
        )[
            [
                "macro_f1",
                "balanced_accuracy",
                "recall_bear",
                "recall_stress",
                "brier",
                "ece",
            ]
        ].mean()
    bear_bootstrap = (
        multiclass_bootstrap[
            (multiclass_bootstrap["class"] == "Bear")
            & (
                multiclass_bootstrap["metric"].isin(
                    ["recall", "precision", "f1", "pr_auc", "brier"]
                )
            )
        ]
        if not multiclass_bootstrap.empty
        else pd.DataFrame()
    )
    bear_confusion = _bear_confusion_summary(multiclass_probabilities)

    summary_columns = [
        column
        for column in [
            "model",
            "horizon",
            "recall",
            "precision",
            "pr_auc",
            "brier",
            "ece",
            "expected_cost",
            "alert_fraction",
        ]
        if column in summary
    ]
    lines = [
        "# CPU downside experiment — experimental, not production",
        "",
        "Báo cáo nghiên cứu trung lập. Kết quả không phải khuyến nghị đầu tư và "
        "không được dùng để tự động thay mô hình production.",
        "",
        "## 1. Thiết kế thử nghiệm",
        "",
        f"Evaluation scope: `{metadata.get('evaluation_scope')}`. Mọi target development "
        "phải kết thúc trước 2021-04-02. Outer test không tham gia feature selection, "
        "calibration hoặc threshold selection.",
        "",
        "## 2. Tình trạng baseline",
        "",
        "Baseline Risk-off được giữ nguyên là `P(Bear) + P(Stress)` từ EBM bốn lớp. "
        "Giai đoạn từ 2021-04-02 chỉ là `legacy_audit_test`, không phải untouched holdout mới.",
        "",
        markdown_table(summary[summary_columns], max_rows=30)
        if not summary.empty
        else "_not_available_",
        "",
        "### Xác suất đầy đủ và nhận diện Bear",
        "",
        f"Artifact `multiclass_oos_probabilities.csv` có {len(multiclass_probabilities)} "
        "dòng OOS. Mỗi dòng lưu đủ xác suất raw và temperature-calibrated cho "
        "`Bull/Sideway/Bear/Stress`, actual/predicted class, xác suất Risk-off "
        "baseline/candidate, threshold và alert. Các target downside còn lại là nhãn "
        "nghiên cứu, không được trình bày như xác suất nếu chưa fit head riêng.",
        "",
        markdown_table(multiclass_summary, max_rows=20)
        if not multiclass_summary.empty
        else "_not_available_",
        "",
        markdown_table(bear_confusion, max_rows=20)
        if not bear_confusion.empty
        else "_not_available_",
        "",
        markdown_table(bear_bootstrap, max_rows=20)
        if not bear_bootstrap.empty
        else "_not_available_",
        "",
        "![Bear-specific OOS](figures/bear_oos_diagnostics.png)",
        "",
        _bear_interpretation(bear_confusion),
        "",
        "## 3. Tác động của Risk-off head",
        "",
        "![So sánh Risk-off OOS](figures/risk_off_oos_comparison.png)",
        "",
        "**Nhận xét:** Bảng là nguồn số chính; hình chỉ trực quan hóa recall và expected "
        "cost. Không kết luận cải thiện nếu bootstrap hoặc consistency theo fold không đạt.",
        "",
        "## 4. Threshold được chọn và lý do",
        "",
        f"Có {len(thresholds)} quyết định fold/horizon. Mỗi threshold được chọn trên outer "
        "validation. Khi ràng buộc precision/recall thất bại, artifact ghi rõ "
        "`constraint_failure_minimum_expected_cost`.",
        "",
        "![Chi phí theo threshold](figures/risk_off_cost_curve.png)",
        "",
        "Điểm cực tiểu trên curve chỉ là validation estimate; outer-test metrics không dùng "
        "để dịch chuyển threshold.",
        "",
        "## 5. Precision–recall trade-off",
        "",
        "![Precision–recall trade-off](figures/risk_off_precision_recall_curve.png)",
        "",
        "Threshold thấp có thể tăng recall nhưng cũng tăng false-positive exposure. "
        "Acceptance criteria yêu cầu precision tối thiểu 25%.",
        "",
        "## 6. Expected cost",
        "",
        "Expected cost dùng độ lớn `abs(min(future_mae, 0))` cho false negative và "
        "`max(forward_return, 0)` cho false positive, không chỉ đếm lỗi.",
        "",
        "## 7. False negative nguy hiểm nhất",
        "",
        markdown_table(missed.head(15), max_rows=15)
        if not missed.empty
        else "_not_available: không có false negative trong artifact này._",
        "",
        "## 8. False positive tốn kém nhất",
        "",
        markdown_table(false_positive.head(15), max_rows=15)
        if not false_positive.empty
        else "_not_available: không có false positive trong artifact này._",
        "",
        "## 9. Feature ablation",
        "",
        markdown_table(ablation.sort_values("objective").head(20), max_rows=20)
        if not ablation.empty
        else "_not_available_",
        "",
        "Ablation chạy theo nhóm feature trong inner purged folds; outer test không chọn feature.",
        "",
        "## 10. Calibration",
        "",
        "![Reliability Risk-off](figures/risk_off_reliability.png)",
        "",
        "Calibration được fit trên validation của từng outer fold. Reliability trong hình "
        "dùng outer development OOS.",
        "",
        "## 11. Backtest risk overlay",
        "",
        markdown_table(overlay, max_rows=10) if not overlay.empty else "_not_available_",
        "",
        "Overlay chỉ là paper overlay, dùng vị thế trễ một phiên và notional exposure. "
        "Không được thay notional bằng tiền ký quỹ futures.",
        "",
        "## 12. Runtime và RAM trên CPU",
        "",
        markdown_table(runtime, max_rows=30) if not runtime.empty else "_not_available_",
        "",
        runtime_note,
        "",
        markdown_table(interrupted_runtime, max_rows=10)
        if not interrupted_runtime.empty
        else "",
        "",
        "Runner downside không gọi CUDA. `peak_rss=not_available` nghĩa là môi trường thiếu "
        "psutil; `peak_python_bytes` vẫn được ghi và giới hạn này phải được nêu rõ.",
        "",
        "## 13. Giới hạn nghiên cứu",
        "",
        "- Legacy audit đã được quan sát trước và không thể khôi phục thành holdout unbiased.",
        "- Nhãn Risk-off phụ thuộc target bốn lớp hiện tại; binary target không đổi nghĩa bốn lớp.",
        "- OHLCV không bao phủ vĩ mô, breadth, tin tức hoặc đổi thành phần chỉ số.",
        "- Candidate tăng recall nhưng vi phạm precision, cost, calibration hoặc fold consistency "
        "vẫn phải bị loại.",
        "",
        "### Post-selection legacy audit",
        "",
        markdown_table(legacy, max_rows=20)
        if not legacy.empty
        else "_not_available: profile này không chạy legacy audit._",
        "",
        "Legacy audit không tham gia chọn model, calibration, threshold hoặc acceptance.",
        "",
        "## 14. Điều kiện được phép chạy shadow test",
        "",
        _acceptance_text(risk),
        "",
        "Chỉ forecast mới, đăng ký bất biến và chấm sau maturity mới tạo bằng chứng prospective.",
        "",
        "## 15. Điều kiện chưa được phép dùng tiền thật",
        "",
        "Không dùng tiền thật khi acceptance chưa đạt, bootstrap còn inconclusive, registry "
        "chưa có đủ forecast matured hoặc distribution calibration/VaR production chưa đạt. "
        "Repository không tự động cấp quyền production.",
        "",
        "## Phụ lục bootstrap",
        "",
        markdown_table(bootstrap, max_rows=30) if not bootstrap.empty else "_not_available_",
    ]
    destination = run_dir / "report.md"
    destination.write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return destination
