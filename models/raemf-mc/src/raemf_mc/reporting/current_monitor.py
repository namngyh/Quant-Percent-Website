"""Current-data monitoring and plain-language RAEMF-MC forecast reporting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from raemf_mc import CLASS_ORDER, HORIZONS
from raemf_mc.calibration.temperature_scaling import apply_temperature
from raemf_mc.data.loader import load_price_data, sha256_file
from raemf_mc.features.selection import select_features
from raemf_mc.features.technical import build_features
from raemf_mc.models.base import fill_features
from raemf_mc.models.ebm_forecaster import EBMForecaster
from raemf_mc.regime.filtered_hmm import fit_filtered_hmm
from raemf_mc.reporting.plots import _THOUSANDS, _apply_style
from raemf_mc.risk.egarch_t import fit_egarch_features
from raemf_mc.simulation.structural_mc import simulate_paths_detailed
from raemf_mc.targets.regime_targets import create_multihorizon_targets
from raemf_mc.uncertainty.confidence import confidence_label, market_filter


MONITOR_START = "<!-- CURRENT_MONITOR_START -->"
MONITOR_END = "<!-- CURRENT_MONITOR_END -->"
QUANTILE_COLUMNS = ["q025", "q050", "q100", "q250", "q500", "q750", "q900", "q950", "q975"]
CLASS_VI = {
    "Bull": "tăng",
    "Sideway": "đi ngang",
    "Bear": "giảm",
    "Stress": "căng thẳng/giảm sâu",
}
CONFIDENCE_VI = {"High": "Cao", "Medium": "Trung bình", "Low": "Thấp", "Uncertain": "Không chắc chắn"}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")


def _band_label(row: pd.Series) -> str:
    actual = float(row["actual_close"])
    if float(row["q250"]) <= actual <= float(row["q750"]):
        return "Trong vùng trung tâm 50%"
    if float(row["q100"]) <= actual <= float(row["q900"]):
        return "Trong vùng 80%"
    if float(row["q025"]) <= actual < float(row["q100"]):
        return "Đuôi thấp của vùng 95%"
    if float(row["q900"]) < actual <= float(row["q975"]):
        return "Đuôi cao của vùng 95%"
    if float(row["q025"]) <= actual <= float(row["q975"]):
        return "Trong vùng 95%"
    return "Ngoài vùng 95%"


def _estimated_percentile(row: pd.Series) -> float:
    values = np.asarray([row[column] for column in QUANTILE_COLUMNS], dtype=float)
    levels = np.asarray([0.025, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.975])
    values = np.maximum.accumulate(values)
    return float(np.interp(float(row["actual_close"]), values, levels, left=0.0, right=1.0))


def _build_monitoring_path(
    prices: pd.DataFrame,
    baseline_run: Path,
    baseline_outlook: dict[str, Any],
    config: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Overlay post-forecast closes on the immutable baseline MC distributions."""
    origin = pd.Timestamp(baseline_outlook["as_of_date"])
    baseline_close = float(baseline_outlook["last_close"])
    post = prices.loc[prices["date"] > origin, ["date", "close"]].reset_index(drop=True)
    targeted = create_multihorizon_targets(
        prices,
        bull_threshold=float(config["target"]["bull_threshold"]),
        bear_threshold=float(config["target"]["bear_threshold"]),
        stress_threshold=float(config["target"]["stress_threshold"]),
        volatility_window=int(config["target"]["volatility_window"]),
    )
    origin_target = targeted.loc[targeted["date"] == origin]
    path_rows: list[pd.DataFrame] = []
    summary_rows: list[dict[str, object]] = []
    for horizon in HORIZONS:
        quantiles = pd.read_csv(baseline_run / f"monte_carlo_quantiles_{horizon}.csv")
        observed = min(len(post), horizon, int(quantiles["step"].max()))
        actual = post.iloc[:observed].copy()
        actual.insert(0, "step", np.arange(1, observed + 1))
        merged = actual.merge(quantiles, on="step", how="left")
        merged.insert(0, "horizon", horizon)
        if not merged.empty:
            merged["actual_return_from_forecast_origin"] = merged["close"] / baseline_close - 1.0
            merged["median_error_pct"] = merged["close"] / merged["q500"] - 1.0
            merged = merged.rename(columns={"close": "actual_close"})
            merged["band"] = merged.apply(_band_label, axis=1)
            merged["estimated_percentile"] = merged.apply(_estimated_percentile, axis=1)
            endpoint = merged.iloc[-1]
            path_rows.append(merged)
            actual_close = float(endpoint["actual_close"])
            partial_return = float(endpoint["actual_return_from_forecast_origin"])
            band = str(endpoint["band"])
            percentile = float(endpoint["estimated_percentile"])
            median_error = float(endpoint["median_error_pct"])
            observed_date = pd.Timestamp(endpoint["date"]).strftime("%Y-%m-%d")
        else:
            actual_close = np.nan
            partial_return = np.nan
            band = "Chưa có phiên mới"
            percentile = np.nan
            median_error = np.nan
            observed_date = baseline_outlook["as_of_date"]
        actual_class: str | None = None
        if not origin_target.empty:
            value = origin_target.iloc[0][f"target_{horizon}"]
            if pd.notna(value):
                actual_class = str(value)
        predicted = str(baseline_outlook["horizons"][str(horizon)]["predicted_class"])
        summary_rows.append(
            {
                "horizon": horizon,
                "forecast_origin": baseline_outlook["as_of_date"],
                "observed_through": observed_date,
                "sessions_observed": observed,
                "sessions_remaining": max(horizon - observed, 0),
                "status": "Đã đủ phiên để chấm cuối kỳ" if actual_class is not None else "Đang theo dõi, chưa đủ phiên",
                "forecast_class": predicted,
                "forecast_confidence": baseline_outlook["horizons"][str(horizon)]["confidence"],
                "actual_class": actual_class,
                "class_correct": bool(actual_class == predicted) if actual_class is not None else None,
                "actual_close": actual_close,
                "partial_return": partial_return,
                "median_error_pct": median_error,
                "estimated_percentile": percentile,
                "forecast_band": band,
            }
        )
    path = pd.concat(path_rows, ignore_index=True) if path_rows else pd.DataFrame()
    return path, pd.DataFrame(summary_rows)


def _fit_current_deployment(
    prices: pd.DataFrame,
    baseline_run: Path,
    config: dict[str, Any],
) -> tuple[dict[str, Any], dict[int, pd.DataFrame], pd.DataFrame, dict[str, Any]]:
    """Refit only the deployment RAEMF-MC using locked baseline parameters."""
    seed = int(config.get("runtime", {}).get("seed", 42))
    targeted = create_multihorizon_targets(
        prices,
        bull_threshold=float(config["target"]["bull_threshold"]),
        bear_threshold=float(config["target"]["bear_threshold"]),
        stress_threshold=float(config["target"]["stress_threshold"]),
        volatility_window=int(config["target"]["volatility_window"]),
    )
    technical, _ = build_features(targeted)
    returns = np.log(targeted["close"] / targeted["close"].shift(1))
    deployment_idx = np.arange(len(targeted), dtype=int)
    hmm = fit_filtered_hmm(
        technical,
        returns,
        deployment_idx,
        int(config["hmm"]["n_states"]),
        list(config["hmm"]["seeds"]),
    )
    risk = fit_egarch_features(returns, deployment_idx)
    numeric_hmm = hmm.probabilities.select_dtypes(include=[np.number])
    full_features = pd.concat([technical, numeric_hmm, risk.features], axis=1)
    best_parameters = _load_json(baseline_run / "best_parameters.json")
    calibration = pd.read_csv(baseline_run / "calibration_comparison.csv")
    temperatures = {
        int(row.horizon): float(row.temperature)
        for row in calibration[calibration["model"] == "RAEMF-MC"].itertuples()
    }
    outlook: dict[str, Any] = {
        "as_of_date": targeted["date"].iloc[-1].strftime("%Y-%m-%d"),
        "last_close": float(targeted["close"].iloc[-1]),
        "scope": "Deployment refit with locked baseline hyperparameters and calibration",
        "horizons": {},
        "note": "Không phải lời khuyên đầu tư.",
    }
    fit_metadata: dict[str, Any] = {
        "hmm_warnings": hmm.diagnostics.get("warnings", []),
        "egarch_warnings": risk.diagnostics.get("warnings", []),
        "horizons": {},
    }
    for horizon in HORIZONS:
        valid = targeted[f"target_{horizon}"].notna()
        sub = targeted.loc[valid].reset_index()
        model_features = full_features.loc[sub["index"]].reset_index(drop=True)
        selected, _ = select_features(
            model_features,
            np.arange(len(model_features)),
            float(config["features"]["missing_threshold"]),
            float(config["features"]["correlation_threshold"]),
        )
        training, latest = fill_features(
            model_features[selected],
            full_features.loc[[targeted.index[-1]], selected],
        )
        params = dict(best_parameters[str(horizon)]["parameters"])
        model = EBMForecaster(seed, **params).fit(training, sub[f"target_{horizon}"].astype(str))
        raw_probability = model.predict_proba(latest)
        temperature = temperatures.get(horizon, 1.0)
        probability = apply_temperature(raw_probability, temperature)[0]
        entropy = float(-(probability * np.log(np.clip(probability, 1e-12, 1.0))).sum())
        ordered = np.sort(probability)
        hmm_entropy = float(hmm.probabilities["hmm_entropy"].iloc[-1])
        confidence = confidence_label(probability, hmm_entropy)
        outlook["horizons"][str(horizon)] = {
            "probabilities": {target_class: float(probability[index]) for index, target_class in enumerate(CLASS_ORDER)},
            "predicted_class": CLASS_ORDER[int(probability.argmax())],
            "confidence": confidence,
            "entropy": entropy,
            "margin": float(ordered[-1] - ordered[-2]),
            "market_filter": market_filter(probability, confidence, config["market_filter"]),
        }
        fit_metadata["horizons"][str(horizon)] = {
            "labeled_observations": len(sub),
            "last_labeled_date": sub["date"].iloc[-1].strftime("%Y-%m-%d"),
            "selected_feature_count": len(selected),
            "temperature_from_baseline_validation": temperature,
            "model_warning": model.warning,
        }

    transition = np.asarray(hmm.diagnostics["transition_matrix"], dtype=float)
    probability_columns = [column for column in hmm.probabilities if column.startswith("hmm_prob_state_")]
    state_probability = hmm.probabilities[probability_columns].iloc[-1].to_numpy(dtype=float)
    state_mean = np.asarray(hmm.diagnostics["state_mean"], dtype=float)
    state_volatility = np.asarray(hmm.diagnostics["state_volatility"], dtype=float)
    quantiles: dict[int, pd.DataFrame] = {}
    summary_rows: list[pd.DataFrame] = []
    for horizon in HORIZONS:
        target_probability = np.asarray(
            [outlook["horizons"][str(horizon)]["probabilities"][target_class] for target_class in CLASS_ORDER],
            dtype=float,
        )
        simulation = simulate_paths_detailed(
            float(targeted["close"].iloc[-1]),
            state_probability,
            transition,
            state_mean,
            float(risk.features["egarch_sigma"].iloc[-1]),
            horizon,
            int(config["monte_carlo"]["paths"]),
            seed,
            state_volatility=state_volatility,
            egarch_params=dict(risk.diagnostics.get("params", {})),
            nu=float(risk.diagnostics.get("nu", 8.0)),
            target_class_probabilities=target_probability,
            state_to_class=np.arange(len(state_probability)) % len(CLASS_ORDER),
        )
        quantiles[horizon] = simulation.quantiles
        summary_rows.append(simulation.summary)
    return outlook, quantiles, pd.concat(summary_rows, ignore_index=True), fit_metadata


def _save_figure(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=190, bbox_inches="tight")
    plt.close(fig)


def _plot_baseline_forecast(
    prices: pd.DataFrame,
    baseline_outlook: dict[str, Any],
    path: pd.DataFrame,
    baseline_run: Path,
    horizon: int,
    output_path: Path,
) -> None:
    origin = pd.Timestamp(baseline_outlook["as_of_date"])
    baseline_close = float(baseline_outlook["last_close"])
    history = prices.loc[prices["date"] <= origin, ["date", "close"]].tail(100).copy()
    history.loc[history.index[-1], "close"] = baseline_close
    history_x = np.arange(-len(history) + 1, 1)
    quantiles = pd.read_csv(baseline_run / f"monte_carlo_quantiles_{horizon}.csv")
    actual = path[path["horizon"] == horizon]
    fig, ax = plt.subplots(figsize=(10.2, 5.4))
    ax.plot(history_x, history["close"], color="#4B5563", linewidth=1.25, label="VN-Index trước mốc dự báo")
    ax.fill_between(quantiles["step"], quantiles["q025"], quantiles["q975"], color="#56B4E9", alpha=0.13, label="RAEMF-MC 95%")
    ax.fill_between(quantiles["step"], quantiles["q100"], quantiles["q900"], color="#0072B2", alpha=0.20, label="RAEMF-MC 80%")
    ax.fill_between(quantiles["step"], quantiles["q250"], quantiles["q750"], color="#009E73", alpha=0.27, label="RAEMF-MC 50%")
    ax.plot(quantiles["step"], quantiles["q500"], color="#1F2937", linestyle="--", linewidth=1.4, label="Trung vị RAEMF-MC")
    if not actual.empty:
        ax.plot(actual["step"], actual["actual_close"], color="#D55E00", marker="o", markersize=4, linewidth=2.0, label="VN-Index thực tế")
        endpoint = actual.iloc[-1]
        ax.annotate(
            f"{endpoint['actual_close']:,.2f}\n{endpoint['band']}",
            (endpoint["step"], endpoint["actual_close"]),
            xytext=(8, -34),
            textcoords="offset points",
            fontsize=8,
            arrowprops={"arrowstyle": "->", "color": "#555555"},
        )
        actual_through = pd.Timestamp(actual["date"].max()).strftime("%d/%m/%Y")
    else:
        actual_through = baseline_outlook["as_of_date"]
    ax.axvline(0, color="#111827", linewidth=1.0)
    ax.yaxis.set_major_formatter(_THOUSANDS)
    ax.margins(x=0)
    ax.set(
        title=f"Dự báo RAEMF-MC {horizon} phiên từ {baseline_outlook['as_of_date']} và VN-Index thực tế đến {actual_through}",
        xlabel="Số phiên so với mốc phát hành dự báo",
        ylabel="Điểm VN-Index",
    )
    ax.legend(fontsize=8, ncol=2)
    _save_figure(fig, output_path)


def _plot_current_outlook(
    prices: pd.DataFrame,
    outlook: dict[str, Any],
    quantiles: dict[int, pd.DataFrame],
    output_path: Path,
) -> None:
    history = prices[["date", "close"]].tail(90)
    history_x = np.arange(-len(history) + 1, 1)
    fig, axes = plt.subplots(3, 1, figsize=(10.5, 12.0), sharey=False)
    for ax, horizon in zip(axes, HORIZONS, strict=True):
        frame = quantiles[horizon]
        item = outlook["horizons"][str(horizon)]
        probabilities = item["probabilities"]
        ax.plot(history_x, history["close"], color="#4B5563", linewidth=1.2, label="VN-Index thực tế")
        ax.fill_between(frame["step"], frame["q025"], frame["q975"], color="#56B4E9", alpha=0.13, label="RAEMF-MC 95%")
        ax.fill_between(frame["step"], frame["q100"], frame["q900"], color="#0072B2", alpha=0.20, label="RAEMF-MC 80%")
        ax.fill_between(frame["step"], frame["q250"], frame["q750"], color="#009E73", alpha=0.27, label="RAEMF-MC 50%")
        ax.plot(frame["step"], frame["q500"], color="#1F2937", linestyle="--", linewidth=1.4, label="Trung vị RAEMF-MC")
        probability_note = ", ".join(f"{name} {probabilities[name]:.0%}" for name in CLASS_ORDER)
        ax.text(
            0.01,
            0.03,
            f"Lớp cao nhất: {item['predicted_class']} ({CLASS_VI[item['predicted_class']]}); "
            f"{CONFIDENCE_VI.get(item['confidence'], item['confidence'])}\n{probability_note}",
            transform=ax.transAxes,
            fontsize=8,
            va="bottom",
            bbox={"facecolor": "white", "alpha": 0.84, "edgecolor": "#CCCCCC"},
        )
        ax.axvline(0, color="#111827", linewidth=1.0)
        ax.yaxis.set_major_formatter(_THOUSANDS)
        ax.margins(x=0)
        ax.set(title=f"Outlook RAEMF-MC tại {outlook['as_of_date']}: {horizon} phiên", xlabel="Số phiên so với hiện tại", ylabel="Điểm VN-Index")
    axes[0].legend(fontsize=8, ncol=3)
    _save_figure(fig, output_path)


def _display_monitor_table(summary: pd.DataFrame) -> str:
    lines = [
        "| Horizon | Đã quan sát | Còn lại | Dự báo 01/07 | Trạng thái chấm | Lợi suất tạm thời | Vị trí trong dải |",
        "| --- | ---: | ---: | --- | --- | ---: | --- |",
    ]
    for row in summary.itertuples():
        partial = "chưa có" if pd.isna(row.partial_return) else f"{row.partial_return:.2%}"
        lines.append(
            f"| {int(row.horizon)} phiên | {int(row.sessions_observed)} | {int(row.sessions_remaining)} | "
            f"{row.forecast_class} ({CLASS_VI[row.forecast_class]}) | {row.status} | {partial} | {row.forecast_band} |"
        )
    return "\n".join(lines)


def _display_current_table(outlook: dict[str, Any], mc_summary: pd.DataFrame) -> str:
    summary = mc_summary.set_index("horizon")
    class_lines = [
        "| Horizon | Bull | Sideway | Bear | Stress | Lớp xác suất cao nhất | Độ tin cậy |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    risk_lines = [
        "| Horizon | Trung vị cuối kỳ | Dải 90% cuối kỳ | P(lợi suất dương) | P(drawdown >10%) | VaR 95% |",
        "| --- | ---: | --- | ---: | ---: | ---: |",
    ]
    for horizon in HORIZONS:
        item = outlook["horizons"][str(horizon)]
        p = item["probabilities"]
        row = summary.loc[horizon]
        median_level = outlook["last_close"] * np.exp(float(row["q50"]))
        low = outlook["last_close"] * np.exp(float(row["q05"]))
        high = outlook["last_close"] * np.exp(float(row["q95"]))
        class_lines.append(
            f"| {horizon} phiên | {p['Bull']:.1%} | {p['Sideway']:.1%} | {p['Bear']:.1%} | {p['Stress']:.1%} | "
            f"{item['predicted_class']} ({CLASS_VI[item['predicted_class']]}) | "
            f"{CONFIDENCE_VI.get(item['confidence'], item['confidence'])} |"
        )
        risk_lines.append(
            f"| {horizon} phiên | {median_level:,.0f} | {low:,.0f} - {high:,.0f} | {row['prob_positive']:.1%} | "
            f"{row['prob_drawdown_gt_10pct']:.1%} | {row['var_95']:.1%} |"
        )
    return "\n".join(["**Xác suất trạng thái**", "", *class_lines, "", "**Phân phối mức điểm và rủi ro**", "", *risk_lines])


def _plain_language_section(
    baseline_outlook: dict[str, Any],
    outlook: dict[str, Any],
    summary: pd.DataFrame,
    mc_summary: pd.DataFrame,
    source_revision: float | None,
    exact_duplicate_records: int,
    conflicting_duplicate_records: int,
) -> str:
    observed = int(summary["sessions_observed"].max())
    current_close = float(outlook["last_close"])
    baseline_close = float(baseline_outlook["last_close"])
    partial_return = current_close / baseline_close - 1.0
    revision_text = (
        f"Dữ liệu mới sửa mức đóng cửa 01/07 thêm {source_revision:+.2%} so với file dùng khi phát hành dự báo. "
        "Đánh giá vẫn neo tại mức cũ để không sửa dự báo sau khi đã biết dữ liệu mới."
        if source_revision is not None and abs(source_revision) > 1e-12
        else "Không phát hiện thay đổi mức đóng cửa tại mốc phát hành dự báo."
    )
    quality_notes = []
    if exact_duplicate_records:
        quality_notes.append(f"loại {exact_duplicate_records} bản ghi trùng hoàn toàn")
    if conflicting_duplicate_records:
        quality_notes.append(f"tổng hợp {conflicting_duplicate_records} bản ghi cùng ngày nhưng khác nội dung")
    duplicate_text = f" Loader đã {' và '.join(quality_notes)} trước khi tính toán." if quality_notes else ""
    highest_probabilities = [
        max(outlook["horizons"][str(horizon)]["probabilities"].values())
        for horizon in HORIZONS
    ]
    top_classes = [str(outlook["horizons"][str(horizon)]["predicted_class"]) for horizon in HORIZONS]
    confidences = {str(outlook["horizons"][str(horizon)]["confidence"]) for horizon in HORIZONS}
    if len(set(top_classes)) == 1:
        top_text = f"Tại cả ba horizon, `{top_classes[0]}` là lớp có xác suất cao nhất"
    else:
        pairs = ", ".join(f"{horizon} phiên: `{cls}`" for horizon, cls in zip(HORIZONS, top_classes, strict=True))
        top_text = f"Lớp có xác suất cao nhất khác nhau giữa các horizon ({pairs})"
    majority_note = "" if min(highest_probabilities) > 0.5 else ", chưa phải xác suất đa số"
    confidence_note = (
        f", và độ tin cậy đều là `{next(iter(confidences))}`"
        if len(confidences) == 1
        else ""
    )
    median_returns = mc_summary.set_index("horizon")["q50"]
    disagreement_text = (
        f"{top_text} nhưng chỉ ở mức "
        f"{min(highest_probabilities):.1%}-{max(highest_probabilities):.1%}{majority_note}{confidence_note}. "
        f"Trong khi đó trung vị Monte Carlo tương ứng là {median_returns.loc[20]:+.1%}, {median_returns.loc[40]:+.1%} và {median_returns.loc[60]:+.1%}. "
        "Bộ phân loại trạng thái và bộ mô phỏng đường giá là hai thành phần khác nhau; mọi sự lệch giữa hai đầu ra phải được đọc là dấu hiệu bất định, không phải dự báo chắc chắn theo một hướng."
    )
    return "\n".join(
        [
            "## Theo dõi dự báo RAEMF-MC đến dữ liệu hiện tại",
            "",
            f"Dự báo gốc được phát hành sau phiên **{baseline_outlook['as_of_date']}** tại VN-Index **{baseline_close:,.2f}**. "
            f"File mới có dữ liệu đến **{outlook['as_of_date']}**, tương đương **{observed} phiên mới**; VN-Index hiện ở **{current_close:,.2f}**, thay đổi **{partial_return:.2%}** so với mức neo dự báo.",
            "",
            f"> **Trạng thái đánh giá:** horizon ngắn nhất là 20 phiên nên hiện chưa có horizon nào đủ ngày để kết luận dự báo lớp đúng hay sai. Các số dưới đây là theo dõi giữa kỳ, không phải điểm accuracy mới. {revision_text}{duplicate_text}",
            "",
            "### Dự báo ngày 01/07 đang diễn biến thế nào?",
            "",
            _display_monitor_table(summary),
            "",
            "![RAEMF-MC 20 phiên và VN-Index thực tế](outputs/current_monitor/figures/raemf_forecast_vs_actual_20.png)",
            "",
            "![RAEMF-MC 40 phiên và VN-Index thực tế](outputs/current_monitor/figures/raemf_forecast_vs_actual_40.png)",
            "",
            "![RAEMF-MC 60 phiên và VN-Index thực tế](outputs/current_monitor/figures/raemf_forecast_vs_actual_60.png)",
            "",
            "Ba hình chỉ trả lời một câu hỏi giữa kỳ: đường VN-Index thực tế đang nằm ở đâu trong phân phối kịch bản RAEMF-MC đã tạo trước đó. Nằm trong dải không đồng nghĩa dự báo hướng đã đúng; kết luận lớp chỉ có thể chấm khi đủ 20, 40 hoặc 60 phiên.",
            "",
            f"### RAEMF-MC báo cáo gì tại {outlook['as_of_date']}?",
            "",
            _display_current_table(outlook, mc_summary),
            "",
            disagreement_text,
            "",
            "![Outlook RAEMF-MC hiện tại với VN-Index](outputs/current_monitor/figures/raemf_current_outlook_vnindex.png)",
            "",
            "RAEMF-MC không dự đoán một điểm VN-Index chính xác. Mô hình báo cáo xác suất của bốn trạng thái tăng, đi ngang, giảm và căng thẳng; dải mức chỉ số có điều kiện; xác suất lợi suất dương/âm; cùng rủi ro đuôi và drawdown theo từng horizon.",
            "",
            "### Cách đọc cho người không chuyên",
            "",
            "- `Bull`, `Sideway`, `Bear`, `Stress` là bốn kịch bản thị trường, không phải lệnh mua hoặc bán.",
            "- Cột xác suất cho biết mô hình đang phân bổ niềm tin như thế nào; các xác suất gần nhau nghĩa là mô hình chưa chắc chắn.",
            "- Dải 50%, 80% và 95% càng rộng thì bất định càng lớn. Đây là kịch bản mô phỏng, không phải cam kết VN-Index sẽ nằm trong dải.",
            "- Chỉ chấm đúng/sai cho horizon khi đủ số phiên tương ứng. Theo dõi vài phiên đầu chỉ cho biết quỹ đạo đang ở đâu, chưa đo được năng lực dự báo cuối kỳ.",
            "",
            "### Hạn chế",
            "",
            "- Mô hình chỉ dùng lịch sử OHLCV VN-Index; chưa có lãi suất, tỷ giá, vĩ mô, market breadth, tin tức hay thay đổi thành phần chỉ số.",
            "- Deployment refit dùng tham số đã khóa từ nghiên cứu trước, nhưng HMM, EGARCH và EBM vẫn có thể bị regime drift khi thị trường đổi cấu trúc.",
            "- Monte Carlo phụ thuộc giả định HMM, EGARCH Student-t và cách tái trọng số bằng xác suất EBM; đuôi phân phối có thể rất rộng.",
            "- VN-Index không phải tài sản có thể giao dịch trực tiếp theo giả định đơn giản; phần này không phải backtest chiến lược và không phải lời khuyên đầu tư.",
            "",
            "Báo cáo đầy đủ cho người không chuyên: [current monitor report](outputs/current_monitor/report_for_nonspecialists.md).",
        ]
    )


def _update_readme_section(readme_path: Path, section: str) -> None:
    content = readme_path.read_text(encoding="utf-8")
    replacement = f"{MONITOR_START}\n\n{section}\n\n{MONITOR_END}"
    if MONITOR_START in content and MONITOR_END in content:
        before, rest = content.split(MONITOR_START, 1)
        _, after = rest.split(MONITOR_END, 1)
        content = before.rstrip() + "\n\n" + replacement + "\n\n" + after.lstrip()
    elif "## Khả năng tái lập" in content:
        content = content.replace("## Khả năng tái lập", replacement + "\n\n## Khả năng tái lập", 1)
    else:
        content = content.rstrip() + "\n\n" + replacement + "\n"
    readme_path.write_text(content, encoding="utf-8", newline="\n")


def generate_current_monitor(
    data_path: str | Path,
    baseline_run: str | Path,
    config: dict[str, Any],
    output_dir: str | Path = "outputs/current_monitor",
    readme_path: str | Path = "README.md",
) -> Path:
    """Generate live monitoring artifacts, current outlook, figures, and README section."""
    _apply_style()
    data_path = Path(data_path)
    baseline_run = Path(baseline_run)
    output_dir = Path(output_dir)
    figures = output_dir / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    prices, data_meta = load_price_data(data_path)
    baseline_outlook = _load_json(baseline_run / "latest_outlook.json")
    origin = pd.Timestamp(baseline_outlook["as_of_date"])
    if prices["date"].max() <= origin:
        raise ValueError("Current data must contain at least one session after the baseline forecast date")

    monitoring_path, monitor_summary = _build_monitoring_path(prices, baseline_run, baseline_outlook, config)
    outlook, current_quantiles, mc_summary, fit_metadata = _fit_current_deployment(prices, baseline_run, config)
    monitoring_path.to_csv(output_dir / "monitoring_path.csv", index=False)
    monitor_summary.to_csv(output_dir / "monitor_summary.csv", index=False)
    mc_summary.to_csv(output_dir / "current_monte_carlo_summary.csv", index=False)
    _write_json(output_dir / "current_outlook.json", outlook)
    _write_json(output_dir / "deployment_fit_metadata.json", fit_metadata)
    for horizon, frame in current_quantiles.items():
        frame.to_csv(output_dir / f"current_monte_carlo_quantiles_{horizon}.csv", index=False)

    current_predictions = pd.DataFrame(
        [
            {
                "date": outlook["as_of_date"],
                "horizon": horizon,
                **outlook["horizons"][str(horizon)]["probabilities"],
                "predicted_class": outlook["horizons"][str(horizon)]["predicted_class"],
                "confidence": outlook["horizons"][str(horizon)]["confidence"],
                "entropy": outlook["horizons"][str(horizon)]["entropy"],
                "margin": outlook["horizons"][str(horizon)]["margin"],
            }
            for horizon in HORIZONS
        ]
    )
    current_predictions.to_csv(output_dir / "current_predictions.csv", index=False)

    origin_rows = prices.loc[prices["date"] == origin, "close"]
    source_revision = None
    if not origin_rows.empty:
        source_revision = float(origin_rows.iloc[-1] / float(baseline_outlook["last_close"]) - 1.0)
    provenance = {
        "data_file": str(data_path),
        "data_sha256": sha256_file(data_path),
        "data_metadata": data_meta,
        "baseline_run": str(baseline_run),
        "baseline_forecast_date": baseline_outlook["as_of_date"],
        "baseline_anchor_close": baseline_outlook["last_close"],
        "revised_source_close_at_baseline_date": float(origin_rows.iloc[-1]) if not origin_rows.empty else None,
        "source_revision_pct": source_revision,
        "evaluation_rule": "Final horizon class is scored only after h new trading sessions are observed",
    }
    _write_json(output_dir / "provenance.json", provenance)

    for horizon in HORIZONS:
        _plot_baseline_forecast(
            prices,
            baseline_outlook,
            monitoring_path,
            baseline_run,
            horizon,
            figures / f"raemf_forecast_vs_actual_{horizon}.png",
        )
    _plot_current_outlook(prices, outlook, current_quantiles, figures / "raemf_current_outlook_vnindex.png")

    section = _plain_language_section(
        baseline_outlook,
        outlook,
        monitor_summary,
        mc_summary,
        source_revision,
        int(data_meta.get("exact_duplicate_records_removed", 0)),
        int(data_meta.get("conflicting_duplicate_records_aggregated", 0)),
    )
    report_section = section.replace("](outputs/current_monitor/figures/", "](figures/")
    report_section = report_section.replace(
        "\nBáo cáo đầy đủ cho người không chuyên: [current monitor report](outputs/current_monitor/report_for_nonspecialists.md).",
        "",
    )
    report = "# Báo cáo RAEMF-MC cho người không chuyên\n\n" + report_section
    (output_dir / "report_for_nonspecialists.md").write_text(report.rstrip() + "\n", encoding="utf-8", newline="\n")
    _update_readme_section(Path(readme_path), section)
    return output_dir
