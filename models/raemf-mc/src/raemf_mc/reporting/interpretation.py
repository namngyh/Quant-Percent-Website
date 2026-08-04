"""Data-driven Vietnamese interpretation for tables and figures."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd


METRIC_NAMES_VI = {
    "brier": "Brier score",
    "log_loss": "log loss",
    "ece": "ECE",
    "macro_f1": "macro F1",
    "balanced_accuracy": "balanced accuracy",
    "mcc": "MCC",
    "recall_bear": "recall Bear",
    "recall_stress": "recall Stress",
}


def _load(run_dir: Path, name: str) -> pd.DataFrame:
    path = run_dir / name
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _macd_probability_caveat(metrics: pd.DataFrame) -> str:
    """Explain why a low probability score for MACD probabilistic is not superiority."""
    macd = metrics[metrics["model"] == "MACD probabilistic"]
    if macd.empty or not {"recall_bear", "recall_stress"}.issubset(macd.columns):
        return ""
    if not bool(((macd["recall_bear"].fillna(0) == 0) & (macd["recall_stress"].fillna(0) == 0)).all()):
        return ""
    return (
        " Lưu ý: MACD probabilistic đạt điểm xác suất thấp vì phát xác suất gần tần suất lớp học trên validation, "
        "trong khi không nhận diện được quan sát Bear hay Stress nào (recall đều bằng 0); "
        "điểm Brier/log loss thấp của baseline này không đồng nghĩa dự báo phân loại tốt hơn."
    )


def metric_interpretation(run_dir: Path, metric: str) -> str:
    metrics = _load(run_dir, "metrics_by_model_horizon.csv")
    if metrics.empty or metric not in metrics:
        return "Chưa có đủ dữ liệu để diễn giải metric này."
    lower = metric in {"brier", "log_loss", "ece"}
    observations = []
    best_models: list[str] = []
    for horizon, frame in metrics.groupby("horizon"):
        best = frame.loc[frame[metric].idxmin() if lower else frame[metric].idxmax()]
        raemf = frame[frame["model"] == "RAEMF-MC"].iloc[0]
        delta = float(raemf[metric] - best[metric])
        best_models.append(str(best["model"]))
        observations.append(
            f"{int(horizon)} phiên: tốt nhất là {best['model']} ({best[metric]:.4f}); "
            f"RAEMF-MC đạt {raemf[metric]:.4f}, chênh {delta:+.4f}"
        )
    direction = "thấp hơn" if lower else "cao hơn"
    name = METRIC_NAMES_VI.get(metric, metric)
    caveat = _macd_probability_caveat(metrics) if lower and "MACD probabilistic" in best_models else ""
    return (
        f"{name.capitalize()} được đọc theo hướng {direction} là tốt hơn. "
        + "; ".join(observations)
        + ". So sánh điểm không tự nó chứng minh ưu thế ổn định theo thời gian."
        + caveat
    )


def overall_metric_interpretation(run_dir: Path) -> str:
    """Balanced summary across discrimination and probability quality for the main table."""
    metrics = _load(run_dir, "metrics_by_model_horizon.csv")
    if metrics.empty or not {"macro_f1", "brier"}.issubset(metrics.columns):
        return "Chưa có đủ dữ liệu để diễn giải bảng kết quả."
    observations = []
    for horizon, frame in metrics.groupby("horizon"):
        best_f1 = frame.loc[frame["macro_f1"].idxmax()]
        best_brier = frame.loc[frame["brier"].idxmin()]
        observations.append(
            f"{int(horizon)} phiên: macro F1 cao nhất là {best_f1['model']} ({best_f1['macro_f1']:.4f}), "
            f"Brier thấp nhất là {best_brier['model']} ({best_brier['brier']:.4f})"
        )
    return (
        "Bảng gồm nhiều metric với hướng đọc khác nhau: macro F1, balanced accuracy, MCC và recall đọc theo hướng cao hơn là tốt hơn; "
        "Brier, log loss và ECE đọc theo hướng thấp hơn là tốt hơn. "
        + "; ".join(observations)
        + "."
        + _macd_probability_caveat(metrics)
        + " So sánh điểm không tự nó chứng minh ưu thế ổn định theo thời gian."
    )


def bootstrap_interpretation(run_dir: Path, metric: str) -> str:
    frame = _load(run_dir, "bootstrap_differences.csv")
    frame = frame[frame["metric"] == metric]
    if frame.empty:
        return "Không có bootstrap phù hợp để diễn giải."
    excludes_zero = int(((frame["ci_low"] > 0) | (frame["ci_high"] < 0)).sum())
    total = len(frame)
    direction = "chênh lệch âm có lợi cho RAEMF-MC" if metric in {"brier", "log_loss"} else "chênh lệch dương có lợi cho RAEMF-MC"
    return (
        f"Forest plot dùng định nghĩa RAEMF-MC trừ benchmark; {direction}. "
        f"Có {excludes_zero}/{total} khoảng tin cậy 95% không chứa 0. Các khoảng còn chứa 0 chưa cung cấp bằng chứng ổn định về khác biệt."
    )


def calibration_interpretation(run_dir: Path, horizon: int) -> str:
    frame = _load(run_dir, "calibration_comparison.csv")
    frame = frame[(frame["horizon"] == horizon) & (frame["model"] == "RAEMF-MC")]
    if frame.empty:
        return "Không có dữ liệu calibration cho chân trời này."
    row = frame.iloc[0]
    return (
        f"Trên validation {horizon} phiên, temperature scaling làm Brier thay đổi từ {row['brier_before']:.4f} xuống {row['brier_after']:.4f}, "
        f"log loss từ {row['log_loss_before']:.4f} xuống {row['log_loss_after']:.4f}, và ECE từ {row['ece_before']:.4f} xuống {row['ece_after']:.4f}. "
        "Reliability trên test vẫn có thể lệch do drift và số mẫu trong các bin không đồng đều."
    )


def monte_carlo_interpretation(run_dir: Path, horizon: int) -> str:
    frame = _load(run_dir, "monte_carlo_summary.csv")
    frame = frame[frame["horizon"] == horizon]
    if frame.empty:
        return "Không có kết quả Monte Carlo cho chân trời này."
    row = frame.iloc[0]
    return (
        f"Tại {horizon} phiên, phân phối tái trọng số có xác suất lợi suất dương {row['prob_positive']:.1%}, "
        f"VaR 95% {row['var_95']:.1%}, CVaR 95% {row['cvar_95']:.1%}, và xác suất drawdown vượt 10% {row['prob_drawdown_gt_10pct']:.1%}. "
        f"ESS đạt {row['ess']:.0f} ({row['ess_fraction']:.1%} số quỹ đạo), với bậc tự do Student-t {row['student_t_nu']:.2f}. "
        "Đây là phân phối kịch bản có điều kiện, không phải khoảng đảm bảo cho mức chỉ số tương lai."
    )


def backtest_interpretation(run_dir: Path) -> str:
    frame = _load(run_dir, "backtest_metrics.csv")
    if frame.empty:
        return "Không có kết quả backtest."
    best = frame.loc[frame["sharpe"].idxmax()]
    raemf = frame[frame["model"] == "RAEMF-MC"].iloc[0]
    return (
        f"Trên cùng final-test OOS, Sharpe cao nhất thuộc {best['model']} ({best['sharpe']:.3f}). "
        f"RAEMF-MC có lợi suất tích lũy {raemf['cumulative_return']:.1%}, Sharpe {raemf['sharpe']:.3f}, "
        f"drawdown cực đại {raemf['max_drawdown']:.1%}, turnover {raemf['turnover']:.2f} và chi phí {raemf['total_transaction_cost']:.2%}. "
        "Backtest là proxy trên VN-Index, chưa phản ánh tracking error, thanh khoản hay khả năng giao dịch chỉ số trực tiếp."
    )


def ablation_interpretation(run_dir: Path) -> str:
    frame = _load(run_dir, "ablation_metrics.csv")
    if frame.empty:
        return "Không có kết quả ablation."
    observations = []
    for horizon, part in frame.groupby("horizon"):
        best = part.loc[part["brier"].idxmin()]
        observations.append(f"{int(horizon)} phiên: {best['configuration']} có Brier thấp nhất ({best['brier']:.4f})")
    return "; ".join(observations) + ". Tác động của HMM, EGARCH và calibration không được giả định là nhất quán nếu thứ hạng đổi giữa các chân trời."


def feature_interpretation(run_dir: Path, horizon: int) -> str:
    frame = _load(run_dir, f"feature_importance_RAEMF-MC_{horizon}.csv")
    frame = frame.dropna(subset=["importance"]).head(5)
    if frame.empty:
        return "Mô hình fallback không cung cấp độ quan trọng EBM có thể diễn giải."
    pairs = ", ".join(f"{row.feature} ({row.importance:.3f})" for row in frame.itertuples())
    return f"Năm term quan trọng nhất ở {horizon} phiên là {pairs}. Độ quan trọng toàn cục không biểu thị quan hệ nhân quả và interaction term có thể chia sẻ tín hiệu với đặc trưng tương quan."


def latest_interpretation(run_dir: Path) -> str:
    path = run_dir / "latest_outlook.json"
    if not path.exists():
        return "Không có dự báo triển khai mới nhất."
    latest = json.loads(path.read_text(encoding="utf-8"))
    values = []
    for horizon, item in latest["horizons"].items():
        values.append(
            f"{horizon} phiên: {item['predicted_class']} ({max(item['probabilities'].values()):.1%}), "
            f"confidence={item['confidence']}, entropy={item['entropy']:.2f}, margin={item['margin']:.2f}"
        )
    return f"Dự báo deployment tại {latest['as_of_date']}: " + "; ".join(values) + ". Xác suất phản ánh bất định của mô hình trên dữ liệu hiện có, không phải khuyến nghị đầu tư."


def state_interpretation(run_dir: Path) -> str:
    frame = _load(run_dir, "hmm_state_mapping.csv")
    if frame.empty:
        return "Không có bảng căn chỉnh trạng thái HMM."
    values = ", ".join(
        f"{row.economic_label}: mean={row.mean_return:.3%}, sigma={row.std_return:.3%}, tần suất={row.frequency:.1%}"
        for row in frame.itertuples()
    )
    return f"Căn chỉnh train-only cho thấy {values}. Tên state là diễn giải tương đối theo quy tắc định lượng, không đồng nhất trực tiếp với nhãn dự báo."


def figure_interpretation(run_dir: Path, filename: str) -> str:
    """Return an artifact-specific observation without embedding old values."""
    if filename.startswith("so_sanh_"):
        return metric_interpretation(run_dir, filename.removeprefix("so_sanh_").removesuffix(".png"))
    if filename.startswith("bootstrap_forest_"):
        return bootstrap_interpretation(run_dir, filename.removeprefix("bootstrap_forest_").removesuffix(".png"))
    if filename.startswith("reliability_diagram_"):
        return calibration_interpretation(run_dir, int(re.findall(r"\d+", filename)[-1]))
    if filename.startswith("fan_chart_monte_carlo_"):
        return monte_carlo_interpretation(run_dir, int(re.findall(r"\d+", filename)[-1]))
    if filename.startswith("feature_importance_raemf_mc_") or filename.startswith("ebm_shape_plot_") or filename.startswith("local_explanation_latest_"):
        return feature_interpretation(run_dir, int(re.findall(r"\d+", filename)[-1]))
    if filename.startswith("backtest_"):
        return backtest_interpretation(run_dir)
    if filename == "ablation_study.png":
        return ablation_interpretation(run_dir)
    if filename == "du_bao_moi_nhat_theo_horizon.png":
        return latest_interpretation(run_dir)
    if "hmm" in filename:
        return state_interpretation(run_dir)
    if filename == "egarch_conditional_volatility.png":
        risk = _load(run_dir, "egarch_features.csv")
        if risk.empty or "egarch_sigma" not in risk:
            return "Không có artifact EGARCH để diễn giải."
        return f"Sigma EGARCH trung vị là {risk['egarch_sigma'].median():.3%} và cực đại {risk['egarch_sigma'].max():.3%}. Tham số được fit trên train cho evaluation; các đỉnh volatility là ước lượng mô hình, không phải volatility quan sát trực tiếp."
    if filename == "metric_theo_fold_walk_forward.png":
        folds = _load(run_dir, "walk_forward_metrics.csv")
        best = folds[folds["is_best_trial"]]
        spread = best.groupby("horizon")["brier"].std().fillna(0)
        return "Độ lệch chuẩn Brier giữa các fold là " + ", ".join(f"{int(h)} phiên={v:.4f}" for h, v in spread.items()) + ". Số fold nhỏ nên đây là kiểm tra ổn định, không phải bằng chứng bất biến theo chế độ thị trường."
    if filename.startswith("confusion_matrix_") or filename.startswith("precision_recall_"):
        return "Hình tập trung vào sai số phân loại ngoài mẫu và các lớp rủi ro hiếm. Kết quả phải được đọc cùng support lớp; một đường cong hoặc ô recall cao trên ít quan sát có độ bất định lớn."
    if filename == "phan_phoi_lop_theo_horizon.png":
        return "Tỷ trọng lớp thay đổi theo chân trời do lợi suất và maximum adverse excursion tích lũy khác nhau. Mất cân bằng này là lý do báo cáo macro F1, balanced accuracy và recall Bear/Stress thay cho chỉ accuracy."
    if filename == "vnindex_va_phan_chia_du_lieu.png":
        split = json.loads((run_dir / "split_boundaries.json").read_text(encoding="utf-8"))
        return f"Validation bắt đầu {split['validation_start']} và final test bắt đầu {split['test_start']}. Mọi metric chính và backtest chỉ dùng final test; ranh giới được xác định theo thời gian, không xáo trộn quan sát."
    if filename in {"loi_suat_theo_thoi_gian.png", "phan_phoi_loi_suat.png"}:
        return "Lợi suất có cụm biến động và đuôi dày, tạo động cơ cho EGARCH Student-t và bootstrap theo khối. Quan sát lịch sử không bảo đảm phân phối tương lai giữ nguyên."
    return "Hình được tạo trực tiếp từ artifact của lần chạy hiện tại. Diễn giải chỉ áp dụng cho dữ liệu, split và cấu hình đã ghi trong metadata của run."
