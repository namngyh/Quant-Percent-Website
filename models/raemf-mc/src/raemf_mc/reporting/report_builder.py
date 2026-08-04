"""Artifact-backed Markdown reports and README result updater."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from raemf_mc.reporting.interpretation import (
    ablation_interpretation,
    backtest_interpretation,
    calibration_interpretation,
    figure_interpretation,
    latest_interpretation,
    metric_interpretation,
    monte_carlo_interpretation,
    overall_metric_interpretation,
    state_interpretation,
)
from raemf_mc.reporting.tables import markdown_table


RESULTS_START = "<!-- RESULTS_START -->"
RESULTS_END = "<!-- RESULTS_END -->"

def _write(path: Path, lines: list[str] | str) -> None:
    content = lines if isinstance(lines, str) else "\n".join(lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8", newline="\n")


def _figure_title(filename: str) -> str:
    return filename.removesuffix(".png").replace("_", " ").capitalize()


def _figure_block(run_dir: Path, title: str, filename: str, prefix: str) -> list[str]:
    return [
        f"### {title}",
        "",
        f"![{title}]({prefix}{filename})",
        "",
        f"*Chú thích:* Hình được tạo từ dữ liệu và artifact của run hiện tại: `{filename}`.",
        "",
        f"**Nhận xét định lượng:** {figure_interpretation(run_dir, filename)}",
        "",
    ]


def _readme_results(run_dir: Path) -> str:
    metrics = pd.read_csv(run_dir / "metrics_by_model_horizon.csv")
    latest = pd.read_csv(run_dir / "predictions_latest.csv")
    backtest = pd.read_csv(run_dir / "backtest_metrics.csv")
    display_metrics = metrics.loc[
        metrics["model"] == "RAEMF-MC",
        [
            "horizon",
            "n_obs",
            "macro_f1",
            "balanced_accuracy",
            "mcc",
            "brier",
            "log_loss",
            "ece",
            "recall_bull",
            "recall_sideway",
            "recall_bear",
            "recall_stress",
        ],
    ]
    display_backtest = backtest.loc[
        backtest["model"] == "RAEMF-MC",
        [
            "model",
            "cumulative_return",
            "annualized_return",
            "annualized_volatility",
            "sharpe",
            "sortino",
            "max_drawdown",
            "turnover",
            "total_transaction_cost",
            "average_exposure",
        ],
    ]
    lines = [
        "## Evaluation classifier single-split",
        "",
        "Bảng này được cập nhật tự động từ artifact point-estimate gần nhất. "
        "Đây là final TEST của protocol single-split; benchmark VB nhiều outer fold "
        "được báo cáo riêng ở phần trên.",
        "",
        markdown_table(display_metrics, max_rows=80),
        "",
        f"**Nhận xét:** {overall_metric_interpretation(run_dir)}",
        "",
        "### Xác suất triển khai gần nhất của run point-estimate",
        "",
        markdown_table(latest, max_rows=10),
        "",
        f"**Nhận xét:** {latest_interpretation(run_dir)}",
        "",
        "### Backtest final TEST",
        "",
        markdown_table(display_backtest, max_rows=10),
        "",
        "Backtest dùng position trễ một phiên và chi phí giao dịch trong config. "
        "Kết quả này không phải backtest riêng của VB scenario layer.",
    ]
    return "\n".join(lines).rstrip()


def update_readme_results(readme_path: str | Path, run_dir: str | Path) -> None:
    """Replace only the generated region bounded by stable HTML markers."""
    path = Path(readme_path)
    run_dir = Path(run_dir)
    content = path.read_text(encoding="utf-8")
    if content.count(RESULTS_START) != 1 or content.count(RESULTS_END) != 1:
        raise ValueError("README must contain exactly one RESULTS_START/RESULTS_END marker pair")
    start = content.index(RESULTS_START) + len(RESULTS_START)
    end = content.index(RESULTS_END)
    replacement = "\n\n" + _readme_results(run_dir) + "\n\n"
    path.write_text(content[:start] + replacement + content[end:], encoding="utf-8", newline="\n")


def build_run_report(run_dir: str | Path) -> None:
    """Create a complete academic report with comments after every figure."""
    run_dir = Path(run_dir)
    metrics = pd.read_csv(run_dir / "metrics_by_model_horizon.csv")
    calibration = pd.read_csv(run_dir / "calibration_comparison.csv")
    tuning = pd.read_csv(run_dir / "tuning_trials.csv")
    ablation = pd.read_csv(run_dir / "ablation_metrics.csv")
    backtest = pd.read_csv(run_dir / "backtest_metrics.csv")
    monte_carlo = pd.read_csv(run_dir / "monte_carlo_summary.csv")
    latest = pd.read_csv(run_dir / "predictions_latest.csv")
    bootstrap = pd.read_csv(run_dir / "bootstrap_differences.csv")
    mapping = pd.read_csv(run_dir / "hmm_state_mapping.csv")
    split = json.loads((run_dir / "split_boundaries.json").read_text(encoding="utf-8"))
    lines = [
        "# Báo cáo học thuật RAEMF-MC",
        "",
        "## 1. Tóm tắt",
        "",
        "RAEMF-MC kết hợp đặc trưng kỹ thuật nhân quả, Filtered HMM, EGARCH Student-t và EBM đa lớp cho VN-Index ở ba chân trời 20, 40 và 60 phiên. Báo cáo phân biệt rõ evaluation model và deployment model; metric và backtest chính chỉ sử dụng final test ngoài mẫu.",
        "",
        f"{overall_metric_interpretation(run_dir)}",
        "",
        "## 2. Câu hỏi nghiên cứu",
        "",
        "Nghiên cứu kiểm tra liệu thông tin chế độ thị trường và rủi ro có cải thiện chất lượng xác suất đa chân trời, mức độ hiệu chỉnh và kiểm soát drawdown so với các classifier head, mô hình technical-only và MACD hay không.",
        "",
        "## 3. Dữ liệu",
        "",
        f"Dữ liệu là chuỗi OHLCV VN-Index trong `data.csv`. Validation bắt đầu `{split['validation_start']}` và final test bắt đầu `{split['test_start']}`. Checksum, số dòng và phạm vi ngày được lưu cùng run.",
        "",
        "## 4. Tiền xử lý",
        "",
        "Bộ đọc dữ liệu xử lý các số bị tách bởi dấu phân cách hàng nghìn. Đặc trưng thiếu được forward-fill khi phù hợp hoặc thay bằng median fit trên train; pipeline không dùng `bfill()` xuyên toàn chuỗi.",
        "",
        "## 5. Thiết kế nhãn",
        "",
        "Nhãn Bull, Sideway, Bear và Stress dựa trên lợi suất log tương lai chuẩn hóa bởi volatility nhân quả và maximum adverse excursion. Mỗi nhãn lưu `target_end_date_h` để purge mọi quan sát có cửa sổ mục tiêu chạm boundary tiếp theo.",
        "",
        "## 6. Đặc trưng",
        "",
        "Đặc trưng bao gồm return, trend, volatility, OHLC shape, volume và calendar. Registry ghi nguồn và cửa sổ; selection chỉ dùng train của từng horizon.",
        "",
        "## 7. Filtered HMM",
        "",
        markdown_table(mapping, max_rows=10),
        "",
        state_interpretation(run_dir),
        "",
        "## 8. EGARCH Student-t",
        "",
        "EGARCH(1,1,1) Student-t được fit trên train evaluation và lọc đệ quy về phía trước. Deployment refit module rủi ro bằng lịch sử có sẵn tại ngày dự báo; bậc tự do ước lượng được chuyển trực tiếp sang Monte Carlo.",
        "",
        "## 9. EBM đa chân trời",
        "",
        "Mỗi horizon có một EBM đa lớp riêng. Global importance, shape plot và local counterfactual contribution được lưu để kiểm tra cơ chế dự báo mà không diễn giải tương quan thành nhân quả.",
        "",
        "## 10. Calibration",
        "",
        markdown_table(calibration, max_rows=40),
        "",
        calibration_interpretation(run_dir, 20),
        "",
        "## 11. Monte Carlo",
        "",
        "Trạng thái được lấy theo ma trận chuyển HMM; drift và scale rủi ro phụ thuộc state; log variance cập nhật bằng phương trình EGARCH; cú sốc dùng Student-t với bậc tự do đã fit. Xác suất EBM tái trọng số state cuối kỳ với clipping, tempering và ESS safeguard.",
        "",
        "## 12. Validation",
        "",
        "Tuning dùng purged expanding-window folds nằm hoàn toàn trước final test. Evaluation model fit trên train, học temperature trên validation và chỉ sau đó chấm final test. Backtest áp dụng signal cuối ngày t cho position ở t+1.",
        "",
        "## 13. Benchmark",
        "",
        "Classifier-head benchmark cho EBM, XGBoost và Random Forest dùng cùng bộ đặc trưng mở rộng. Architecture benchmark tách technical-only khỏi technical + HMM/EGARCH. Baseline quy tắc là MACD probabilistic: tín hiệu MACD được ánh xạ sang xác suất bốn lớp bằng bảng điều kiện học trên validation.",
        "",
        "## 14. Tuning",
        "",
        markdown_table(tuning.sort_values(["horizon", "objective"]).groupby("horizon").head(5), max_rows=20),
        "",
        "Random search tối ưu composite loss trên các fold purged, không nhìn final test. Số trial và fold được khóa trong config; HMM và EGARCH evaluation được cache ngoài vòng trial.",
        "",
        "## 15. Ablation",
        "",
        markdown_table(ablation[["configuration", "horizon", "macro_f1", "balanced_accuracy", "mcc", "brier", "log_loss", "ece", "recall_bull", "recall_sideway", "recall_bear", "recall_stress"]], max_rows=50),
        "",
        ablation_interpretation(run_dir),
        "",
        "## 16. Kết quả phân loại",
        "",
        markdown_table(metrics, max_rows=60),
        "",
        metric_interpretation(run_dir, "macro_f1"),
        "",
        "## 17. Calibration ngoài mẫu",
        "",
        "Reliability diagram báo cáo đồng thời ECE, Brier và số quan sát mỗi bin. Calibration được chọn bằng validation, nên test reliability là phép kiểm tra thực sự ngoài mẫu.",
        "",
        "## 18. Explainability",
        "",
        "Global importance mô tả mức đóng góp term trên toàn bộ deployment fit; shape plot khảo sát phản ứng xác suất khi thay từng đặc trưng; local explanation đo thay đổi xác suất khi đưa đặc trưng mới nhất về median train.",
        "",
        "## 19. Backtest ngoài mẫu",
        "",
        markdown_table(backtest, max_rows=20),
        "",
        backtest_interpretation(run_dir),
        "",
        "## 20. Rủi ro Monte Carlo",
        "",
        markdown_table(monte_carlo, max_rows=10),
        "",
        monte_carlo_interpretation(run_dir, 20),
        "",
        "## 21. Dự báo mới nhất",
        "",
        markdown_table(latest, max_rows=10),
        "",
        latest_interpretation(run_dir),
        "",
        "## 22. Bootstrap và độ ổn định",
        "",
        markdown_table(bootstrap, max_rows=60),
        "",
        "Khoảng tin cậy chứa 0 được xem là chưa đủ bằng chứng về khác biệt ổn định. Dấu có lợi phụ thuộc hướng metric và được ghi trong cột `direction`.",
        "",
        "## 23. Hạn chế và hướng nghiên cứu tiếp theo",
        "",
        "Dữ liệu không có vĩ mô, market breadth hoặc thành phần chỉ số. Final test chỉ đại diện một giai đoạn lịch sử; số state HMM và quy tắc nhãn là giả định nghiên cứu. Backtest chưa mô hình hóa tracking error, thuế, spread biến thiên hay khả năng giao dịch VN-Index trực tiếp. Nghiên cứu tiếp theo nên bổ sung dữ liệu không bị bịa đặt, nested model-refit uncertainty và nhiều cửa sổ test độc lập.",
        "",
        "## 24. Kết luận",
        "",
        "Kết luận được giới hạn ở bằng chứng ngoài mẫu và bootstrap của run này. Repository không tuyên bố RAEMF-MC vượt trội khi khoảng tin cậy hoặc kết quả giữa các horizon không hỗ trợ nhận định đó. Đây không phải lời khuyên đầu tư.",
        "",
        "## Phụ lục hình ảnh",
        "",
    ]
    for figure in sorted((run_dir / "figures").glob("*.png")):
        lines.extend(_figure_block(run_dir, _figure_title(figure.name), figure.name, "figures/"))
    _write(run_dir / "report.md", lines)


def build_docs_and_readme(run_dir: str | Path | None = None) -> None:
    """Refresh generated README region and durable methodology documents."""
    if run_dir is None:
        run_dir = Path("outputs/latest")
    run_dir = Path(run_dir)
    update_readme_results("README.md", run_dir)

    methodology = r"""# Phương pháp RAEMF-MC

## Dòng xử lý

RAEMF-MC tạo đặc trưng nhân quả từ OHLCV, lọc xác suất state hiện tại bằng Filtered HMM, ước lượng rủi ro bằng EGARCH Student-t và đưa toàn bộ đặc trưng vào EBM đa lớp riêng cho từng chân trời 20, 40 và 60 phiên.

## Validation và purge

Với quan sát tại thời điểm $t$ và chân trời $h$, train chỉ giữ hàng thỏa $\operatorname{target\_end\_date}_{t,h} < \operatorname{boundary}$. Tuning dùng expanding-window folds trước final test. Calibration chỉ học từ validation; final test không tham gia chọn feature, tham số hoặc temperature.

## Filtered HMM và căn chỉnh state

Xác suất $p(S_t=k\mid\mathcal{F}_t)$ được tính bằng forward recursion. State thô được căn chỉnh bằng mean return, volatility, downside, xác suất âm, tần suất và duration trên train. Tên kinh tế là tương đối và không đồng nhất trực tiếp với nhãn Bull, Sideway, Bear, Stress.

## EGARCH Student-t và Monte Carlo

Monte Carlo lấy state kế tiếp từ ma trận chuyển, dùng drift $\mu_k$, scale rủi ro theo state, cập nhật log variance EGARCH đệ quy và lấy innovation Student-t với $\nu$ đã fit. Xác suất EBM tái trọng số state cuối kỳ; ESS thấp kích hoạt clipping và tempering.

## Backtest

Signal sau đóng cửa ngày $t$ tạo position cho lợi suất ngày $t+1$. Chi phí giao dịch bằng turnover nhân cost rate. Bảng chính chỉ dùng final test và so sánh các chiến lược trên cùng ngày.
"""
    model_card = """# Model card RAEMF-MC

## Mục đích

RAEMF-MC là mô hình nghiên cứu xác suất trạng thái VN-Index ở 20, 40 và 60 phiên. Đầu ra gồm Bull, Sideway, Bear, Stress, confidence, Monte Carlo risk và backtest proxy.

## Người phát triển

Nguyễn Hoài Nam.

## Phạm vi sử dụng

Phù hợp cho nghiên cứu định lượng, kiểm tra calibration và phân tích chế độ thị trường. Không dùng như khuyến nghị đầu tư hoặc cam kết giá tương lai.

## Giới hạn

Dữ liệu đầu vào chỉ gồm OHLCV VN-Index; thiếu vĩ mô, breadth và dữ liệu thành phần. Nhãn và state phụ thuộc quy tắc; thị trường có thể drift. VN-Index không phải tài sản có thể giao dịch trực tiếp theo giả định backtest đơn giản.

## Đánh giá

Evaluation model dùng train, validation và final test tách thời gian có purge. Deployment model refit sau khi khóa kiến trúc và tham số. Kết luận ưu thế chỉ được phép khi metric, bootstrap và consistency giữa horizon cùng hỗ trợ.
"""
    reproducibility = """# Khả năng tái lập

Mỗi run lưu Python version, OS, random seed, Git SHA, config snapshot, checksum dữ liệu, thời gian bắt đầu, kết thúc, tổng runtime và mode. Dependency trực tiếp được khóa trong `requirements-lock.txt`.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m pytest -q
python -m raemf_mc.cli run --data data.csv --config configs/laptop.yaml
```

Run mới nằm trong `outputs/runs/<timestamp>_<git-sha>/`; `outputs/latest/` là bản sao của run hoàn tất gần nhất.
"""
    _write(Path("docs/methodology.md"), methodology)
    _write(Path("docs/model_card.md"), model_card)
    _write(Path("docs/reproducibility.md"), reproducibility)
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    technical = report.replace("# Báo cáo học thuật RAEMF-MC", "# Báo cáo kỹ thuật RAEMF-MC").replace(
        "](figures/", "](../outputs/latest/figures/"
    )
    _write(Path("docs/technical_report.md"), technical)
