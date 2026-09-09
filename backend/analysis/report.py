"""Báo cáo backtest đầy đủ, theo bộ chỉ số của AmiBroker.

Bảng tóm tắt ở panel Kết quả cố tình ngắn: nó trả lời "chạy xong chưa, lãi hay
lỗ". Module này trả lời câu hỏi tiếp theo, *vì sao*, và nó cần nhiều số hơn
mức nhét vừa một panel bên cạnh biểu đồ, nên nó có cửa sổ riêng.

Bốn nhóm, cộng một nhóm thứ năm cho mô hình học máy:

* **Tổng quan**: lãi ròng, CAR, phơi nhiễm, và lợi suất đã hiệu chỉnh theo
  phơi nhiễm. Con số cuối cùng là con số AmiBroker gọi là RAR và là con số hay
  bị bỏ qua nhất: một hệ thống chỉ nắm giữ 20% thời gian mà đạt cùng lợi nhuận
  với mua-và-giữ đang tạo ra lợi suất cao gấp năm lần trên vốn thực sự chịu rủi ro.
* **Lệnh**: tách riêng lệnh mua và lệnh bán. Rất nhiều chiến lược "hai chiều"
  hoá ra chỉ kiếm tiền ở một chiều, và bảng gộp giấu điều đó.
* **Rủi ro**: sụt giảm, chỉ số Ulcer, CAR/MDD, hệ số K. Sụt giảm tối đa nói độ
  sâu; Ulcer nói cả độ sâu lẫn độ dài; hệ số K nói đường vốn có đi lên đều đặn
  hay chỉ nhảy một phát rồi đứng yên.
* **Theo kỳ**: bảng lợi suất theo tháng và theo năm. Đây là nơi phát hiện một
  chiến lược chỉ hoạt động trong đúng một đợt sóng của quá khứ.
* **Học máy**: coi tín hiệu như một bộ phân loại hướng nến kế tiếp, rồi chấm
  nó bằng các thước đo phân loại chuẩn. Việc này áp dụng được cho *mọi* chiến
  lược, không riêng chiến lược ML, và nó tách bạch hai câu hỏi mà lợi nhuận
  trộn lẫn: mô hình đoán đúng hướng bao nhiêu lần, và mỗi lần đúng thì ăn được
  bao nhiêu.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np
import pandas as pd
from scipy import stats as sps

from backend.analysis.risk import risk_tools
from backend.i18n import bi
from backend.strategy.engine import BacktestResult
from backend.strategy.metrics import BARS_PER_YEAR, max_drawdown

# Giờ Việt Nam. Bảng theo tháng phải chia kỳ theo múi giờ người đọc sống, nếu
# không thì các nến cuối tháng rơi nhầm sang tháng sau.
VN_OFFSET_SECONDS = 7 * 3600

# Số điểm tối đa gửi cho mỗi biểu đồ. Trình duyệt không vẽ nổi 20 000 điểm mượt
# mà, và mắt người cũng không đọc thêm được gì từ chúng.
MAX_CHART_POINTS = 1500


def _safe(value: float, fallback: float = 0.0) -> float:
    return float(value) if value is not None and math.isfinite(value) else fallback


def _downsample(values: np.ndarray, times: list[int]) -> list[dict]:
    """Thưa chuỗi bằng cách lấy mẫu đều, giữ nguyên điểm đầu và điểm cuối."""
    n = values.size
    if n == 0:
        return []
    if n <= MAX_CHART_POINTS:
        indices = range(n)
    else:
        indices = np.unique(
            np.linspace(0, n - 1, MAX_CHART_POINTS).astype(int)
        ).tolist()
    return [{"t": times[i], "v": round(float(values[i]), 4)} for i in indices]


# ------------------------------------------------------------------ tổng quan

def _overview(result: BacktestResult, df: pd.DataFrame, timeframe: str) -> dict:
    equity = result.equity
    initial = result.config.initial_capital
    final = float(equity[-1])

    span_seconds = max(result.times[-1] - result.times[0], 1)
    years = span_seconds / (365.25 * 24 * 3600)

    net_profit = final - initial
    net_pct = (final / initial - 1.0) * 100.0
    car = ((final / initial) ** (1.0 / years) - 1.0) * 100.0 if years > 0 and final > 0 else (
        -100.0 if final <= 0 else 0.0
    )

    bars_in_market = int(np.count_nonzero(result.position))
    exposure = bars_in_market / len(equity) * 100.0 if len(equity) else 0.0

    first_close = float(df["close"].iloc[0])
    last_close = float(df["close"].iloc[-1])
    buy_hold_pct = (last_close / first_close - 1.0) * 100.0
    buy_hold_car = (
        ((last_close / first_close) ** (1.0 / years) - 1.0) * 100.0
        if years > 0 and first_close > 0 else 0.0
    )

    return {
        "initial_capital": initial,
        "final_equity": final,
        "net_profit": net_profit,
        "net_profit_pct": net_pct,
        "car_pct": car,
        # AmiBroker gọi là RAR: lợi suất trên phần thời gian thực sự có vị thế.
        # Vốn đứng ngoài thị trường không chịu rủi ro thị trường, nên chia CAR
        # cho tỷ lệ phơi nhiễm là cách so sánh công bằng một hệ thống ra vào
        # liên tục với một hệ thống nắm giữ suốt.
        "rar_pct": car / (exposure / 100.0) if exposure > 0 else 0.0,
        "exposure_pct": exposure,
        "bars_in_market": bars_in_market,
        "bars": len(equity),
        "years": years,
        "buy_hold_pct": buy_hold_pct,
        "buy_hold_car_pct": buy_hold_car,
        "vs_buy_hold_pct": net_pct - buy_hold_pct,
        "start_time": result.times[0],
        "end_time": result.times[-1],
        "timeframe": timeframe,
        "ruined": result.ruined,
    }


# --------------------------------------------------------------------- lệnh

def _trade_block(trades: list, initial: float) -> dict:
    """Thống kê cho một tập lệnh: dùng chung cho tất cả, mua, và bán."""
    if not trades:
        return {"count": 0}

    pnls = np.array([t.pnl for t in trades], dtype="float64")
    returns = np.array([t.return_pct for t in trades], dtype="float64")
    bars = np.array([t.bars_held for t in trades], dtype="float64")

    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    win_bars = bars[pnls > 0]
    loss_bars = bars[pnls < 0]

    gross_profit = float(wins.sum()) if wins.size else 0.0
    gross_loss = float(-losses.sum()) if losses.size else 0.0

    avg_win = float(wins.mean()) if wins.size else 0.0
    avg_loss = float(losses.mean()) if losses.size else 0.0
    win_rate = wins.size / len(trades)

    return {
        "count": len(trades),
        "wins": int(wins.size),
        "losses": int(losses.size),
        "win_rate_pct": win_rate * 100.0,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_profit": float(pnls.sum()),
        "profit_factor": (
            gross_profit / gross_loss if gross_loss > 0
            else (float("inf") if gross_profit > 0 else 0.0)
        ),
        "avg_profit": float(pnls.mean()),
        "avg_profit_pct": float(returns.mean()),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        # Tỷ lệ lãi/lỗ: cùng với tỷ lệ thắng, hai số này quyết định hệ thống có
        # kỳ vọng dương hay không, và mỗi số một mình thì không nói lên gì.
        "payoff_ratio": abs(avg_win / avg_loss) if avg_loss != 0 else 0.0,
        "expectancy": win_rate * avg_win + (1 - win_rate) * avg_loss,
        "expectancy_pct": float(returns.mean()),
        "largest_win": float(pnls.max()) if pnls.size else 0.0,
        "largest_loss": float(pnls.min()) if pnls.size else 0.0,

        # --- Các ô AmiBroker báo cáo mà bảng này còn thiếu ---
        #
        # Tổng và cực đại số nến nắm giữ. Trung bình đã có ở "avg_bars_held";
        # tổng cho biết vốn bị khoá bao lâu, cực đại cho biết lệnh dai nhất.
        "total_bars_held": float(bars.sum()) if bars.size else 0.0,
        "max_bars_held": float(bars.max()) if bars.size else 0.0,

        # Sụt giảm *trong* một lệnh, đo bằng MAE. Sụt giảm hệ thống nói tài
        # khoản đã xuống bao nhiêu; con số này nói một lệnh đơn lẻ đã đi ngược
        # bao xa trước khi đóng, tức là cái mà một lệnh dừng lỗ sẽ cắt phải.
        "max_trade_drawdown_pct": (
            float(max(t.mae_pct for t in trades)) if trades else 0.0
        ),
        "avg_trade_drawdown_pct": (
            float(np.mean([t.mae_pct for t in trades])) if trades else 0.0
        ),

        # AmiBroker gọi là Standard Error. Độ phân tán theo tiền đã có ở
        # "profit_std"; đây là bản theo phần trăm, so được giữa các mức vốn.
        "std_dev_return_pct": float(returns.std(ddof=1)) if returns.size > 1 else 0.0,

        # Tỷ lệ lời/lỗ theo mức lớn nhất, không phải theo trung bình.
        "risk_reward_ratio": (
            float(pnls.max() / abs(pnls.min()))
            if pnls.size and pnls.min() < 0 else None
        ),

        # Chi phí giao dịch cộng dồn: phí hai chiều cộng trượt giá hai chiều
        # trên giá trị danh nghĩa của từng lệnh. Đây là con số chiến lược phải
        # vượt qua trước khi kiếm được đồng nào.
        "exit_reasons": {
            reason: int(sum(1 for t in trades if t.exit_reason == reason))
            for reason in sorted({t.exit_reason for t in trades})
        },
        # Lệnh lãi lớn nhất chiếm bao nhiêu phần trăm tổng lãi. Nếu một lệnh
        # duy nhất là 60% lợi nhuận thì hệ số lợi nhuận không mô tả chiến lược,
        # nó mô tả một lần may.
        "best_trade_share_pct": (
            float(pnls.max()) / gross_profit * 100.0
            if gross_profit > 0 and pnls.max() > 0 else 0.0
        ),
        # Kelly: phần vốn tối ưu theo lý thuyết cho tỷ lệ thắng và tỷ lệ
        # lãi/lỗ này. Gần như luôn quá cao để dùng thật, nó tối đa hoá tăng
        # trưởng dài hạn mà không quan tâm sụt giảm dọc đường, nhưng nó là
        # trần: đặt cỡ vị thế trên mức này thì tăng trưởng kỳ vọng GIẢM.
        "kelly_pct": (
            (win_rate - (1 - win_rate) / abs(avg_win / avg_loss)) * 100.0
            if avg_loss != 0 and avg_win != 0 else 0.0
        ),
        # Kỳ vọng tính theo R: R là mức lỗ trung bình, nên "0.4R" nghĩa là mỗi
        # lệnh kiếm được 0.4 lần mức thua điển hình. Cách duy nhất so sánh được
        # hai chiến lược có cỡ vị thế khác nhau.
        "expectancy_r": (
            (win_rate * avg_win + (1 - win_rate) * avg_loss) / abs(avg_loss)
            if avg_loss != 0 else 0.0
        ),
        "profit_std": float(pnls.std(ddof=1)) if pnls.size > 1 else 0.0,
        # Sai số chuẩn của lãi trung bình mỗi lệnh: khoảng bất định quanh con
        # số kỳ vọng, thứ mà một giá trị trung bình đơn lẻ giấu đi.
        "profit_se": (
            float(pnls.std(ddof=1) / np.sqrt(pnls.size)) if pnls.size > 1 else 0.0
        ),
        "avg_bars_held": float(bars.mean()),
        "avg_bars_win": float(win_bars.mean()) if win_bars.size else 0.0,
        "avg_bars_loss": float(loss_bars.mean()) if loss_bars.size else 0.0,
        "return_on_initial_pct": float(pnls.sum()) / initial * 100.0,
    }


def _streaks(trades: list) -> dict:
    """Chuỗi thắng và chuỗi thua dài nhất, kèm chuỗi đang diễn ra."""
    best_win = best_loss = current = 0
    sign = 0
    for trade in trades:
        this_sign = 1 if trade.pnl > 0 else (-1 if trade.pnl < 0 else 0)
        if this_sign == sign and this_sign != 0:
            current += 1
        else:
            sign = this_sign
            current = 1 if this_sign != 0 else 0
        if sign > 0:
            best_win = max(best_win, current)
        elif sign < 0:
            best_loss = max(best_loss, current)

    return {
        "max_consecutive_wins": best_win,
        "max_consecutive_losses": best_loss,
        "current_streak": current * sign,
        "note": bi(
            "Chuỗi thua dài nhất là con số cần biết TRƯỚC khi chạy tiền thật: "
            "đây là số lệnh liên tiếp bạn phải chịu mà không mất niềm tin. "
            "Chuỗi thua trong tương lai gần như chắc chắn dài hơn, đơn giản vì "
            "tương lai có nhiều lệnh hơn quá khứ.",
            "The longest losing streak is the figure to know BEFORE trading real "
            "money: it is how many losses in a row you must absorb without "
            "losing faith. The future streak is almost certainly longer, simply "
            "because the future holds more trades than the past.",
        ),
    }


def _excursions(trades: list) -> dict:
    """MFE và MAE: dữ liệu để đặt dừng lỗ và chốt lãi bằng số liệu."""
    if not trades:
        return {"count": 0}

    mfe = np.array([t.mfe_pct for t in trades], dtype="float64")
    mae = np.array([t.mae_pct for t in trades], dtype="float64")
    pnl = np.array([t.pnl for t in trades], dtype="float64")
    won = pnl > 0

    def _stats(values: np.ndarray) -> dict:
        if values.size == 0:
            return {"mean": 0.0, "median": 0.0, "worst": 0.0}
        return {
            "mean": float(values.mean()),
            "median": float(np.median(values)),
            "worst": float(values.min() if values.mean() < 0 else values.max()),
        }

    return {
        "count": len(trades),
        "mae_winners": _stats(mae[won]),
        "mae_losers": _stats(mae[~won]),
        "mfe_winners": _stats(mfe[won]),
        "mfe_losers": _stats(mfe[~won]),
        # Điểm cho biểu đồ tán xạ MAE–kết quả.
        "points": [
            {
                "mae": round(float(t.mae_pct), 3),
                "mfe": round(float(t.mfe_pct), 3),
                "ret": round(float(t.return_pct), 3),
                "win": bool(t.pnl > 0),
                "side": t.side,
            }
            for t in trades
        ][:2000],
        "stop_note": bi(
            "MAE của các lệnh THẮNG là ngưỡng dừng lỗ không được vượt qua: đặt "
            "dừng chặt hơn mức đó nghĩa là cắt đúng những lệnh lẽ ra có lãi.",
            "The MAE of the WINNERS is the line a stop must not cross: set it "
            "tighter and you cut exactly the trades that would have paid.",
        ),
        "target_note": bi(
            "MFE của các lệnh THUA cho biết đã bỏ lỡ bao nhiêu: nếu lệnh thua "
            "thường xanh vài phần trăm trước khi đỏ, một mức chốt lãi cứu được chúng.",
            "The MFE of the LOSERS shows what was left behind: if losing trades "
            "are routinely a few percent up before turning, a profit target "
            "would rescue them.",
        ),
    }


# --------------------------------------------------------------------- rủi ro

def _ulcer_index(equity: np.ndarray) -> tuple[float, np.ndarray]:
    """Chỉ số Ulcer, và chuỗi sụt giảm dùng để tính nó.

    Khác sụt giảm tối đa ở chỗ nó phạt cả độ sâu lẫn thời gian ở dưới đỉnh.
    Hai chiến lược cùng sụt 30% nhưng một cái hồi trong một tháng và một cái
    hồi trong hai năm là hai trải nghiệm hoàn toàn khác nhau, và sụt giảm tối
    đa cho hai con số giống hệt.
    """
    if equity.size == 0:
        return 0.0, np.array([])
    peak = np.maximum.accumulate(equity)
    with np.errstate(divide="ignore", invalid="ignore"):
        drawdown = np.where(peak > 0, (equity - peak) / peak * 100.0, -100.0)
    return float(np.sqrt(np.mean(drawdown**2))), drawdown


def _k_ratio(equity: np.ndarray) -> dict:
    """Độ dốc đường vốn (thang log) chia sai số chuẩn của chính độ dốc đó.

    Đo tính *đều đặn*, không phải độ lớn. Một đường vốn đi lên thẳng cho hệ số
    K cao; một đường lên bằng đúng một cú nhảy rồi đi ngang cho hệ số K thấp,
    dù tổng lợi nhuận có thể bằng nhau.

    Chuẩn hoá theo √n để con số không tự động lớn lên khi thêm dữ liệu. Vẫn
    phụ thuộc khung thời gian, nên chỉ so sánh được giữa các lần chạy cùng
    khung, điều này được ghi rõ thay vì để người đọc tự đoán.
    """
    positive = equity[equity > 0]
    n = positive.size
    if n < 30:
        return {"value": None, "note": bi(
            "Cần ít nhất 30 nến có vốn dương.",
            "At least 30 bars with positive equity are needed.",
        )}

    y = np.log(positive)
    x = np.arange(n, dtype="float64")
    slope, intercept = np.polyfit(x, y, 1)
    residuals = y - (slope * x + intercept)

    # Ngưỡng tương đối, không phải ngưỡng "khác 0". Một đường vốn phẳng hoàn
    # toàn cho phần dư cỡ 1e-17: nhiễu dấu phẩy động, không phải biến động,
    # và chia cho nó ra một hệ số K trông như một con số thật. Đây đúng là loại
    # lỗi mà một bảng báo cáo không được phép mắc: nó không sai một cách ồn ào,
    # nó chỉ đưa ra một con số bịa với hai chữ số thập phân.
    scale = max(float(np.abs(y).mean()), 1e-12)
    if float(np.std(residuals)) <= 1e-10 * scale:
        return {
            "value": None,
            "note": bi(
                "Đường vốn là một đường thẳng hoàn hảo trên thang log: không "
                "có độ phân tán để đo tính đều đặn. Thường gặp khi chiến lược "
                "chưa vào lệnh nào.",
                "The equity curve is a perfect straight line on a log scale: "
                "there is no dispersion to measure consistency against. Usually "
                "this means the strategy never traded.",
            ),
        }

    # Sai số chuẩn của độ dốc trong hồi quy tuyến tính đơn.
    dof = n - 2
    spread = float(np.sum((x - x.mean()) ** 2))
    se_slope = math.sqrt(
        float(np.sum(residuals**2)) / dof / spread
    ) if dof > 0 and spread > 0 else 0.0

    if se_slope <= 0:
        return {"value": None, "note": bi(
            "Đường vốn không có biến động để đo.",
            "The equity curve has no variation to measure.",
        )}

    return {
        "value": float(slope / se_slope / math.sqrt(n)),
        "slope": float(slope),
        "slope_se": se_slope,
        "note": bi(
            "Giá trị này phụ thuộc khung thời gian, nên chỉ so sánh giữa các "
            "lần chạy cùng khung. Nó đo độ đều của tăng trưởng, không đo độ lớn.",
            "This value depends on the timeframe, so compare it only across runs "
            "on the same one. It measures how steady growth is, not how large.",
        ),
    }


def _ratios(returns: np.ndarray, periods: float) -> dict:
    """Các tỷ số đo cùng một thứ theo những cách khác nhau về mẫu số.

    Sharpe chia cho độ lệch chuẩn, tức phạt biến động lên cũng ngang biến động
    xuống. Bốn tỷ số dưới đây đổi mẫu số vì lý do đó, và trên một chiến lược có
    phân phối lệch chúng có thể xếp hạng ngược nhau, điều đó tự nó là thông tin.
    """
    if returns.size < 10:
        return {}

    gains = returns[returns > 0]
    losses = returns[returns < 0]

    # Omega: tổng phần lời chia tổng phần lỗ, ở ngưỡng 0. Dùng TOÀN BỘ phân
    # phối chứ không chỉ hai mô-men đầu, nên nó không bỏ qua đuôi như Sharpe.
    total_gain = float(gains.sum()) if gains.size else 0.0
    total_loss = float(-losses.sum()) if losses.size else 0.0
    omega = total_gain / total_loss if total_loss > 0 else float("inf")

    # Tail ratio: đuôi phải so với đuôi trái. Dưới 1 nghĩa là những ngày tệ
    # nhất tệ hơn những ngày tốt nhất tốt.
    right = float(np.percentile(returns, 95))
    left = float(np.percentile(returns, 5))
    tail_ratio = abs(right / left) if left != 0 else float("inf")

    # Độ ổn định: R² của hồi quy log đường vốn theo thời gian. 1.0 là một đường
    # thẳng hoàn hảo; 0.3 nghĩa là phần lớn chuyển động không phải xu hướng.
    equity = np.cumsum(returns)
    x = np.arange(equity.size, dtype="float64")
    if equity.size > 2 and float(np.var(equity)) > 0:
        correlation = float(np.corrcoef(x, equity)[0, 1])
        stability = correlation**2
    else:
        stability = 0.0

    return {
        "omega": omega,
        "tail_ratio": tail_ratio,
        "stability": stability,
        "skew": float(sps.skew(returns, bias=False)) if returns.size > 3 else 0.0,
        "kurtosis": float(sps.kurtosis(returns, bias=False)) if returns.size > 4 else 0.0,
        "var_95_pct": float(np.percentile(returns, 5)) * 100.0,
        "cvar_95_pct": (
            float(returns[returns <= np.percentile(returns, 5)].mean()) * 100.0
            if (returns <= np.percentile(returns, 5)).any() else 0.0
        ),
        "best_bar_pct": float(returns.max()) * 100.0,
        "worst_bar_pct": float(returns.min()) * 100.0,
        "positive_bars_pct": float((returns > 0).mean()) * 100.0,
        "periods_per_year": periods,
    }


def _gain_to_pain(monthly: list[dict]) -> dict:
    """Tổng lợi suất chia tổng độ lớn của các tháng lỗ.

    Tính trên lợi suất THÁNG, không phải theo nến. Ngưỡng "trên 1.0 là tốt" của
    Jack Schwager là một phát biểu về dữ liệu tháng; áp cùng công thức lên 8 000
    nến giờ cho 0.01, và con số đó không phải điểm kém, nó nằm ở một thang
    khác, đứng cạnh một ngưỡng không liên quan gì tới nó.
    """
    values = np.array([m["return_pct"] for m in monthly], dtype="float64")
    if values.size < 6:
        return {
            "value": None,
            "months": int(values.size),
            "note": bi(
                "Cần ít nhất 6 tháng để con số này có nghĩa.",
                "At least 6 months are needed for this figure to mean anything.",
            ),
        }

    pain = float(-values[values < 0].sum())
    return {
        "value": float(values.sum()) / pain if pain > 0 else float("inf"),
        "months": int(values.size),
        "note": bi(
            "Tính trên lợi suất tháng. Trên 1.0 là mức Schwager coi là tốt; "
            "trên 2.0 là hiếm.",
            "Computed on monthly returns. Above 1.0 is what Schwager calls good; "
            "above 2.0 is rare.",
        ),
    }


def _drawdown_episodes(equity: np.ndarray, times: list[int]) -> dict:
    """Mọi đợt sụt giảm riêng lẻ, không chỉ đợt sâu nhất.

    Sụt giảm tối đa là một quan sát duy nhất. Nó không nói đợt sụt *điển hình*
    sâu bao nhiêu, cũng không nói mất bao lâu để hồi, và với người phải ngồi
    qua chúng, hai câu đó quan trọng hơn kỷ lục.
    """
    if equity.size < 3:
        return {"episodes": [], "count": 0}

    peak = np.maximum.accumulate(equity)
    with np.errstate(divide="ignore", invalid="ignore"):
        drawdown = np.where(peak > 0, equity / peak - 1.0, -1.0)

    episodes = []
    start = None
    for i, value in enumerate(drawdown):
        if value < -1e-9 and start is None:
            start = i
        elif value >= -1e-9 and start is not None:
            segment = drawdown[start:i]
            trough = start + int(np.argmin(segment))
            episodes.append({
                "start": int(start),
                "trough": int(trough),
                "end": int(i),
                "depth_pct": float(drawdown[trough]) * 100.0,
                "length_bars": int(i - start),
                "recovery_bars": int(i - trough),
                "recovered": True,
            })
            start = None

    # Đợt đang diễn ra lúc dữ liệu kết thúc: chưa hồi, và phải nói rõ như vậy
    # thay vì lặng lẽ bỏ đi, nó thường là đợt người đọc đang ở trong.
    if start is not None:
        segment = drawdown[start:]
        trough = start + int(np.argmin(segment))
        episodes.append({
            "start": int(start),
            "trough": int(trough),
            "end": int(equity.size - 1),
            "depth_pct": float(drawdown[trough]) * 100.0,
            "length_bars": int(equity.size - start),
            "recovery_bars": None,
            "recovered": False,
        })

    if not episodes:
        return {"episodes": [], "count": 0}

    depths = np.array([e["depth_pct"] for e in episodes])
    sum_squared = float((depths**2).sum())
    recovered = [e for e in episodes if e["recovered"]]
    worst = sorted(episodes, key=lambda e: e["depth_pct"])[:5]

    return {
        "count": len(episodes),
        "average_depth_pct": float(depths.mean()),
        "sum_squared_depths": sum_squared,
        "median_depth_pct": float(np.median(depths)),
        "average_length_bars": float(np.mean([e["length_bars"] for e in episodes])),
        "average_recovery_bars": (
            float(np.mean([e["recovery_bars"] for e in recovered])) if recovered else None
        ),
        "longest_recovery_bars": (
            max(e["recovery_bars"] for e in recovered) if recovered else None
        ),
        "unrecovered": any(not e["recovered"] for e in episodes),
        "worst": [
            {
                "depth_pct": e["depth_pct"],
                "length_bars": e["length_bars"],
                "recovery_bars": e["recovery_bars"],
                "start_time": times[e["start"]] if e["start"] < len(times) else None,
                "trough_time": times[e["trough"]] if e["trough"] < len(times) else None,
                "recovered": e["recovered"],
            }
            for e in worst
        ],
    }


def _rolling_sharpe(
    returns: np.ndarray, times: list[int], periods: float, window: int | None = None
) -> list[dict]:
    """Sharpe trên cửa sổ trượt: cách thấy một lợi thế đã tắt từ khi nào.

    Một Sharpe 1.2 cho toàn giai đoạn có thể là 2.5 trong hai năm đầu và −0.3
    trong hai năm sau. Con số tổng hợp không phân biệt được hai trường hợp đó
    với một chiến lược đều đặn, còn đường này thì có.
    """
    n = returns.size
    if window is None:
        # Khoảng một năm giao dịch, nhưng không quá một phần tư dữ liệu: cửa
        # sổ dài hơn thế chỉ cho vài điểm và không còn là "trượt" nữa.
        window = int(min(max(periods, 60), n // 4))
    if n < window * 2 or window < 30:
        return []

    # Trung bình và phương sai trượt bằng tổng tích luỹ: O(n) thay vì O(n·w).
    cumulative = np.concatenate([[0.0], np.cumsum(returns)])
    cumulative_sq = np.concatenate([[0.0], np.cumsum(returns**2)])
    total = cumulative[window:] - cumulative[:-window]
    total_sq = cumulative_sq[window:] - cumulative_sq[:-window]

    mean = total / window
    variance = np.maximum(total_sq / window - mean**2, 0.0) * window / max(window - 1, 1)
    std = np.sqrt(variance)

    with np.errstate(divide="ignore", invalid="ignore"):
        sharpe = np.where(std > 0, mean / std * math.sqrt(periods), np.nan)

    stamps = times[window:]
    points = [
        {"t": stamps[i], "v": round(float(sharpe[i]), 3)}
        for i in range(min(sharpe.size, len(stamps)))
        if math.isfinite(sharpe[i])
    ]
    if len(points) <= MAX_CHART_POINTS:
        return points
    step = len(points) / MAX_CHART_POINTS
    return [points[int(i * step)] for i in range(MAX_CHART_POINTS)]


def _risk(
    result: BacktestResult,
    overview: dict,
    timeframe: str,
    monthly_returns: list[dict],
) -> dict:
    equity = result.equity
    drawdown_pct, peak_idx, trough_idx = max_drawdown(equity)
    ulcer, drawdown_series = _ulcer_index(equity)

    with np.errstate(divide="ignore", invalid="ignore"):
        returns = np.diff(equity) / np.where(equity[:-1] > 0, equity[:-1], np.nan)
    returns = returns[np.isfinite(returns)]

    periods = BARS_PER_YEAR.get(timeframe, 365.0)
    std = float(returns.std(ddof=1)) if returns.size > 1 else 0.0
    downside = returns[returns < 0]
    downside_dev = float(np.sqrt(np.mean(downside**2))) if downside.size else 0.0

    sharpe = (
        float(returns.mean()) / std * math.sqrt(periods) if std > 0 else 0.0
    )
    sortino = (
        float(returns.mean()) / downside_dev * math.sqrt(periods)
        if downside_dev > 0 else 0.0
    )

    car = overview["car_pct"]
    net_pct = overview["net_profit_pct"]

    # Thời gian nằm dưới đỉnh: bao lâu tài khoản chưa lập đỉnh mới. Với người
    # giao dịch thật, đây thường là con số khó chịu hơn cả độ sâu.
    underwater = int(np.count_nonzero(drawdown_series < -0.01))
    longest_underwater = 0
    run = 0
    for value in drawdown_series:
        if value < -0.01:
            run += 1
            longest_underwater = max(longest_underwater, run)
        else:
            run = 0

    # Sụt giảm sâu nhất trong phạm vi một lệnh, lấy từ MAE.
    worst_trade_dd = min((t.mae_pct for t in result.trades), default=0.0)

    # Sterling và Burke: cùng ý tưởng với CAR/MDD nhưng mẫu số dùng nhiều đợt
    # sụt giảm thay vì đúng một đợt, nên chúng không bị một tai nạn đơn lẻ chi
    # phối. Burke lấy căn bậc hai tổng bình phương, nên nó phạt các đợt sâu
    # mạnh hơn Sterling.
    episodes = _drawdown_episodes(equity, result.times)
    average_depth = episodes.get("average_depth_pct") or 0.0
    sterling = car / -average_depth if average_depth < 0 else 0.0
    # Burke's denominator is every drawdown on record. Taking it from the five
    # kept for the table would make the ratio depend on how many rows the UI
    # happens to show.
    sum_squares = episodes.get("sum_squared_depths", 0.0)
    burke = car / math.sqrt(sum_squares) if sum_squares > 0 else 0.0

    return {
        "max_drawdown_pct": drawdown_pct,
        "episodes": episodes,
        "sterling": sterling,
        "burke": burke,
        "ratios": _ratios(returns, periods),
        "gain_to_pain": _gain_to_pain(monthly_returns),
        "rolling_sharpe": _rolling_sharpe(returns, result.times[1:], periods),
        "max_drawdown_value": float(
            equity[peak_idx] - equity[trough_idx]
        ) if equity.size else 0.0,
        "drawdown_peak_index": peak_idx,
        "drawdown_trough_index": trough_idx,
        "max_trade_drawdown_pct": worst_trade_dd,
        "ulcer_index": ulcer,
        # UPI: cùng ý tưởng với Sharpe nhưng mẫu số là nỗi đau thực tế của việc
        # nắm giữ, không phải độ lệch chuẩn của lợi suất.
        "ulcer_performance_index": car / ulcer if ulcer > 0 else 0.0,
        "car_mdd": car / drawdown_pct if drawdown_pct > 0 else 0.0,
        # AmiBroker in RAR/MaxDD ngay dưới CAR/MaxDD. Khác biệt là RAR đã chia
        # cho tỷ lệ thời gian thực sự nằm trong thị trường, nên một chiến lược
        # chỉ vào lệnh 10% thời gian không bị phạt vì 90% còn lại đứng ngoài.
        "rar_mdd": (
            overview["rar_pct"] / drawdown_pct if drawdown_pct > 0 else 0.0
        ),
        "recovery_factor": net_pct / drawdown_pct if drawdown_pct > 0 else 0.0,
        "sharpe": sharpe,
        "sortino": sortino,
        "volatility_annual_pct": std * math.sqrt(periods) * 100.0,
        "k_ratio": _k_ratio(equity),
        "bars_underwater": underwater,
        "bars_underwater_pct": underwater / len(equity) * 100.0 if len(equity) else 0.0,
        "longest_underwater_bars": longest_underwater,
        "liquidations": sum(1 for t in result.trades if t.exit_reason == "liquidation"),
    }


# ------------------------------------------------------------------ theo kỳ

def _periodic(result: BacktestResult) -> dict:
    """Lợi suất theo tháng và theo năm, chia kỳ theo giờ Việt Nam.

    Bảng theo tháng là nơi lộ ra một chiến lược chỉ hoạt động trong đúng một
    đợt sóng: tổng lợi nhuận trông đều, nhưng bảng cho thấy tất cả đến từ ba
    tháng của năm 2021 và phần còn lại đi ngang.
    """
    equity = result.equity
    if equity.size == 0:
        return {"monthly": [], "annual": []}

    stamps = pd.to_datetime(
        np.array(result.times, dtype="int64") + VN_OFFSET_SECONDS,
        unit="s", utc=True,
    )
    series = pd.Series(equity, index=stamps)

    def _returns(rule: str) -> pd.Series:
        # Vốn cuối mỗi kỳ; lợi suất kỳ đầu tính từ vốn ban đầu, không từ 0.
        closes = series.resample(rule).last().dropna()
        if closes.empty:
            return closes
        opens = closes.shift(1)
        opens.iloc[0] = result.config.initial_capital
        return (closes / opens - 1.0) * 100.0

    monthly = _returns("ME")
    annual = _returns("YE")

    monthly_rows = [
        {
            "year": int(stamp.year),
            "month": int(stamp.month),
            "return_pct": _safe(value),
        }
        for stamp, value in monthly.items()
    ]
    annual_rows = [
        {"year": int(stamp.year), "return_pct": _safe(value)}
        for stamp, value in annual.items()
    ]

    positive_months = sum(1 for r in monthly_rows if r["return_pct"] > 0)
    return {
        "monthly": monthly_rows,
        "annual": annual_rows,
        "positive_months": positive_months,
        "total_months": len(monthly_rows),
        "positive_month_pct": (
            positive_months / len(monthly_rows) * 100.0 if monthly_rows else 0.0
        ),
        "best_month_pct": max((r["return_pct"] for r in monthly_rows), default=0.0),
        "worst_month_pct": min((r["return_pct"] for r in monthly_rows), default=0.0),
        "timezone": "Asia/Ho_Chi_Minh (GMT+7)",
    }


# ---------------------------------------------------------------- học máy

def _histogram(values: np.ndarray, bins: int = 30) -> list[dict]:
    if values.size == 0:
        return []
    counts, edges = np.histogram(values, bins=bins)
    return [
        {
            "from": round(float(edges[i]), 3),
            "to": round(float(edges[i + 1]), 3),
            "count": int(counts[i]),
        }
        for i in range(len(counts))
    ]


def ml_evaluation(
    df: pd.DataFrame,
    position: np.ndarray,
    probability: np.ndarray | None = None,
) -> dict:
    """Chấm điểm tín hiệu như một bộ phân loại hướng của nến kế tiếp.

    Áp dụng được cho mọi chiến lược, không riêng chiến lược học máy, và đó
    chính là điểm hữu ích: nó tách hai thứ mà con số lợi nhuận trộn lẫn vào
    nhau. Một hệ thống có thể đoán đúng hướng 48% số lần mà vẫn lãi đậm nếu
    những lần đúng ăn to hơn nhiều những lần sai; ngược lại, đoán đúng 56% mà
    vẫn lỗ là chuyện thường khi phí ăn hết phần chênh.

    Nhãn là dấu của lợi suất nến **kế tiếp**, so với vị thế đang giữ ở nến đó:
    tức là đúng thứ mà vị thế đó đặt cược, không lệch pha một nến. Những nến
    đứng ngoài thị trường không được chấm: không có dự đoán thì không có gì để
    đúng hay sai.
    """
    close = df["close"].to_numpy(dtype="float64")
    n = min(len(close), position.size)
    if n < 30:
        return {"error": bi("Cần ít nhất 30 nến.",
                            "At least 30 bars are needed.")}

    # Lợi suất của nến kế tiếp, gióng với vị thế đang giữ ở nến hiện tại.
    future = np.sign(np.diff(close[:n]))
    held = position[: n - 1]

    active = (held != 0) & (future != 0)
    if active.sum() < 20:
        return {
            "error": bi(
                f"Chỉ {int(active.sum())} nến vừa có vị thế vừa có nến sau biến "
                "động: quá ít để chấm điểm phân loại.",
                f"Only {int(active.sum())} bars both hold a position and are "
                "followed by a bar that moved: too few to score a classifier.",
            )
        }

    y_pred = held[active]
    y_true = future[active]

    correct = int((y_pred == y_true).sum())
    total = int(active.sum())
    accuracy = correct / total

    # Đường cơ sở: luôn đoán lớp phổ biến nhất trong CHÍNH tập được chấm.
    # So với 50% là sai, vì thị trường hiếm khi cân bằng 50/50.
    up_share = float((y_true > 0).mean())
    baseline = max(up_share, 1.0 - up_share)

    tp = int(((y_pred > 0) & (y_true > 0)).sum())
    fp = int(((y_pred > 0) & (y_true < 0)).sum())
    tn = int(((y_pred < 0) & (y_true < 0)).sum())
    fn = int(((y_pred < 0) & (y_true > 0)).sum())

    def _ratio(numerator: int, denominator: int) -> float:
        return numerator / denominator if denominator else 0.0

    precision_long = _ratio(tp, tp + fp)
    recall_long = _ratio(tp, tp + fn)
    precision_short = _ratio(tn, tn + fn)
    recall_short = _ratio(tn, tn + fp)

    def _f1(precision: float, recall: float) -> float:
        return (
            2 * precision * recall / (precision + recall)
            if precision + recall > 0 else 0.0
        )

    mcc_denominator = math.sqrt(
        float((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    )
    mcc = (tp * tn - fp * fn) / mcc_denominator if mcc_denominator > 0 else 0.0

    # Kiểm định nhị thức một phía: độ chính xác quan sát được có thật sự vượt
    # đường cơ sở không, hay chỉ là dao động lấy mẫu? Không có bước này thì
    # "51,2% so với 50,8%" trông như một chiến thắng.
    from scipy import stats as sps

    p_value = float(sps.binomtest(correct, total, baseline, alternative="greater").pvalue)

    # Hệ số thông tin: tương quan hạng Spearman giữa vị thế đang giữ và lợi
    # suất nến kế tiếp. Khác độ chính xác ở chỗ nó tính cả ĐỘ LỚN: đoán đúng
    # một cú tăng 3% được tính nặng hơn đoán đúng một cú tăng 0.05%, mà độ
    # chính xác thì coi hai cái như nhau. Trong quản lý quỹ định lượng, IC 0.03
    # đã là một tín hiệu dùng được.
    future_returns = np.diff(close[:n])[active]
    if y_pred.size > 10 and np.std(future_returns) > 0:
        ic, ic_p = sps.spearmanr(y_pred, future_returns)
        information_coefficient = float(ic) if np.isfinite(ic) else 0.0
        ic_p_value = float(ic_p) if np.isfinite(ic_p) else 1.0
    else:
        information_coefficient = 0.0
        ic_p_value = 1.0

    # Cohen's kappa: độ chính xác sau khi trừ đi phần đúng do may. Với hai lớp
    # lệch nhau, đây là con số trung thực hơn độ chính xác thô.
    observed = accuracy
    predicted_up = float((y_pred > 0).mean())
    expected = predicted_up * up_share + (1 - predicted_up) * (1 - up_share)
    kappa = (observed - expected) / (1 - expected) if expected < 1 else 0.0

    # Balanced accuracy: trung bình của recall hai lớp, nên một mô hình luôn
    # đoán lớp phổ biến chỉ đạt 0.5 dù độ chính xác thô có cao đến đâu.
    balanced = (recall_long + recall_short) / 2.0

    result = {
        "information_coefficient": information_coefficient,
        "ic_p_value": ic_p_value,
        "cohens_kappa": kappa,
        "balanced_accuracy": balanced,
        "n_scored": total,
        "n_bars": int(n),
        "coverage_pct": total / (n - 1) * 100.0,
        "accuracy": accuracy,
        "baseline_accuracy": baseline,
        "edge_pct": (accuracy - baseline) * 100.0,
        "binomial_p": p_value,
        "beats_baseline": bool(p_value < 0.05),
        "precision_long": precision_long,
        "recall_long": recall_long,
        "f1_long": _f1(precision_long, recall_long),
        "precision_short": precision_short,
        "recall_short": recall_short,
        "f1_short": _f1(precision_short, recall_short),
        "mcc": mcc,
        "confusion": {
            "true_up_pred_up": tp,
            "true_down_pred_up": fp,
            "true_down_pred_down": tn,
            "true_up_pred_down": fn,
        },
        "note": bi(
            f"Đường cơ sở {baseline * 100:.1f}% là độ chính xác của quy tắc ngây "
            "thơ nhất: luôn đoán lớp phổ biến hơn. Mọi so sánh phải so với con "
            "số đó, không phải với 50%.",
            f"The {baseline * 100:.1f}% baseline is the accuracy of the most "
            "naive rule: always predict the more common class. Every comparison "
            "must be against that figure, not against 50%.",
        ),
        "conclusion": bi(
            ((f"Độ chính xác {accuracy * 100:.1f}% vượt đường cơ sở "
              f"{baseline * 100:.1f}% với p = {p_value:.4f}: chênh lệch này khó "
              "giải thích bằng may rủi.")
             if p_value < 0.05 else
             (f"Độ chính xác {accuracy * 100:.1f}% so với đường cơ sở "
              f"{baseline * 100:.1f}%, p = {p_value:.3f}: chưa phân biệt được "
              "với đoán mò. Lợi nhuận (nếu có) đang đến từ độ lớn của các lần "
              "đúng, không phải từ tần suất đúng.")),
            ((f"Accuracy of {accuracy * 100:.1f}% beats the "
              f"{baseline * 100:.1f}% baseline at p = {p_value:.4f}: that gap is "
              "hard to explain by chance.")
             if p_value < 0.05 else
             (f"Accuracy of {accuracy * 100:.1f}% against a "
              f"{baseline * 100:.1f}% baseline, p = {p_value:.3f}: not "
              "distinguishable from guessing. Any profit is coming from the size "
              "of the correct calls, not from how often they are correct.")),
        ),
        "assumptions": bi(
            "Kiểm định nhị thức giả định các nến độc lập. Vị thế giữ qua nhiều "
            "nến liên tiếp thì không độc lập, nên p-value ở đây lạc quan hơn "
            "thực tế. Nó dùng để loại bỏ những chênh lệch rõ ràng là nhiễu, "
            "không dùng để khẳng định một lợi thế nhỏ.",
            "The binomial test assumes independent bars. A position held across "
            "consecutive bars is not independent, so this p-value is more "
            "optimistic than the truth. Use it to rule out gaps that are "
            "obviously noise, not to assert a small edge.",
        ),
    }

    # Nếu chiến lược có công bố xác suất thì chấm thêm phần hiệu chuẩn.
    if probability is not None:
        prob = np.asarray(probability, dtype="float64")[: n - 1][active]
        valid = np.isfinite(prob)
        if valid.sum() >= 20:
            prob = np.clip(prob[valid], 1e-6, 1 - 1e-6)
            labels = (y_true[valid] > 0).astype("float64")
            if 0 < labels.sum() < labels.size:
                try:
                    from sklearn.metrics import roc_auc_score

                    auc = float(roc_auc_score(labels, prob))
                except Exception:
                    auc = None
                brier = float(np.mean((prob - labels) ** 2))
                log_loss = float(
                    -np.mean(labels * np.log(prob) + (1 - labels) * np.log(1 - prob))
                )
                result["probability"] = {
                    "n": int(valid.sum()),
                    "roc_auc": auc,
                    "brier": brier,
                    "log_loss": log_loss,
                    # Hiệu chuẩn: chia xác suất thành mười rổ và so xác suất
                    # trung bình của rổ với tần suất thực tế trong rổ đó.
                    "calibration": _calibration(prob, labels),
                    "note": bi(
                        "Điểm Brier và log-loss đo mức hiệu chuẩn: một mô hình "
                        "nói '70%' nên đúng khoảng 70% số lần đó. AUC đo khả "
                        "năng xếp hạng và không quan tâm tới ngưỡng đang dùng.",
                        "Brier score and log-loss measure calibration: a model "
                        "that says '70%' should be right about 70% of the time. "
                        "AUC measures ranking and ignores the threshold in use.",
                    ),
                }

    return result


def _calibration(prob: np.ndarray, labels: np.ndarray, bins: int = 10) -> list[dict]:
    edges = np.linspace(0.0, 1.0, bins + 1)
    out = []
    for i in range(bins):
        mask = (prob >= edges[i]) & (
            prob < edges[i + 1] if i < bins - 1 else prob <= edges[i + 1]
        )
        if not mask.any():
            continue
        out.append({
            "predicted": round(float(prob[mask].mean()), 4),
            "observed": round(float(labels[mask].mean()), 4),
            "count": int(mask.sum()),
        })
    return out


# ------------------------------------------------------------------ lắp ráp

def build_report(
    result: BacktestResult,
    df: pd.DataFrame,
    timeframe: str,
    *,
    probability: np.ndarray | None = None,
) -> dict:
    """Toàn bộ báo cáo, sẵn sàng cho cửa sổ kết quả."""
    if result.equity.size == 0:
        return {"error": bi("Backtest không tạo ra dữ liệu nào.",
                            "The backtest produced no data.")}

    overview = _overview(result, df, timeframe)
    initial = result.config.initial_capital

    longs = [t for t in result.trades if t.side == "long"]
    shorts = [t for t in result.trades if t.side == "short"]

    _, drawdown_series = _ulcer_index(result.equity)
    periodic = _periodic(result)
    trade_returns = np.array(
        [t.return_pct for t in result.trades], dtype="float64"
    )

    # Đường mua-và-giữ, chuẩn hoá về cùng vốn ban đầu, để hai đường vẽ chung
    # một trục mà không cần người đọc tự quy đổi.
    close = df["close"].to_numpy(dtype="float64")
    buy_hold_curve = close / close[0] * initial

    # Lợi suất theo nến của cả hai đường, để đo tương quan và beta của chiến
    # lược với chính thị trường nó giao dịch.
    with np.errstate(divide="ignore", invalid="ignore"):
        strategy_returns = np.diff(result.equity) / np.where(
            result.equity[:-1] > 0, result.equity[:-1], np.nan
        )
    hold_returns = np.diff(buy_hold_curve[: result.equity.size]) / np.where(
        buy_hold_curve[: result.equity.size - 1] > 0,
        buy_hold_curve[: result.equity.size - 1], np.nan,
    )
    both = np.isfinite(strategy_returns) & np.isfinite(hold_returns)
    if both.sum() > 30 and float(np.var(hold_returns[both])) > 0:
        beta_vs_hold = float(
            np.cov(strategy_returns[both], hold_returns[both], ddof=1)[0, 1]
            / np.var(hold_returns[both], ddof=1)
        )
        correlation_vs_hold = float(
            np.corrcoef(strategy_returns[both], hold_returns[both])[0, 1]
        )
        # Alpha: phần lợi suất còn lại sau khi trừ đi phần giải thích được bằng
        # việc chỉ đơn giản nắm thị trường. Quy về năm.
        periods = BARS_PER_YEAR.get(timeframe, 365.0)
        alpha = float(
            (strategy_returns[both].mean() - beta_vs_hold * hold_returns[both].mean())
            * periods * 100.0
        )
    else:
        beta_vs_hold = correlation_vs_hold = alpha = None

    return {
        "overview": overview,
        "benchmark": {
            "beta": beta_vs_hold,
            "correlation": correlation_vs_hold,
            "alpha_annual_pct": alpha,
            "note": bi(
                "Beta và alpha đo so với chính tài sản này khi mua-và-giữ, "
                "không phải so với một chỉ số thị trường. Beta gần 1 nghĩa là "
                "chiến lược gần như chỉ đang nắm giữ; beta gần 0 nghĩa là lợi "
                "nhuận của nó đến từ nơi khác.",
                "Beta and alpha are measured against buy-and-hold on this asset "
                "itself, not against a market index. A beta near 1 means the "
                "strategy is essentially just holding; a beta near 0 means its "
                "return comes from somewhere else.",
            ),
        },
        "trades": {
            "all": _trade_block(result.trades, initial),
            "long": _trade_block(longs, initial),
            "short": _trade_block(shorts, initial),
        },
        "streaks": _streaks(result.trades),
        "excursions": _excursions(result.trades),
        "risk": _risk(result, overview, timeframe, periodic["monthly"]),
        # Quản trị rủi ro: CVaR nhiều mức kèm độ tin cậy của chính nó, Kelly,
        # ngân sách rủi ro -> cỡ vị thế, và trần đòn bẩy. "risk" ở trên là các
        # chỉ số mô tả; khối này là công cụ để quyết định vào lệnh bao nhiêu.
        "risk_tools": risk_tools(
            strategy_returns[np.isfinite(strategy_returns)],
            [t.as_dict() for t in result.trades],
        ),
        "periodic": periodic,
        "ml": ml_evaluation(df, result.position, probability),
        "charts": {
            "equity": _downsample(result.equity, result.times),
            "buy_hold": _downsample(buy_hold_curve[: len(result.times)], result.times),
            "drawdown": _downsample(drawdown_series, result.times),
            "trade_returns": _histogram(trade_returns),
            "bar_returns": _histogram(
                strategy_returns[np.isfinite(strategy_returns)] * 100.0, bins=40
            ),
            # Lãi lỗ cộng dồn theo thứ tự lệnh, để thấy lợi nhuận đến từ đâu
            # trong chuỗi: dồn vào một đoạn hay rải đều.
            "trade_sequence": [
                {"i": i + 1, "v": round(float(v), 2)}
                for i, v in enumerate(np.cumsum([t.pnl for t in result.trades]))
            ][:2000],
            "monthly": periodic["monthly"],
            "annual": periodic["annual"],
        },
        "config": result.config.as_dict(),
    }
