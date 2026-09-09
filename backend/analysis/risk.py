"""Công cụ quản trị rủi ro: CVaR, ngân sách rủi ro, cỡ vị thế, trần đòn bẩy.

Trước file này, toàn bộ phần rủi ro của báo cáo là **một con số**:
`cvar_95_pct`, lấy trung bình 5% nến tệ nhất. Con số đó đúng, nhưng nó không
trả lời được câu hỏi mà người dùng thật sự hỏi — *"vậy tôi nên vào lệnh bao
nhiêu?"* — và nó im lặng về chính độ tin cậy của mình.

Ba điều file này làm mà một con số CVaR đơn lẻ không làm được:

1. **Nói ra nó được ước lượng từ bao nhiêu quan sát.** CVaR 99% trên 2 000 nến
   là trung bình của **20** quan sát. In nó ra hai chữ số thập phân mà không
   nói điều đó là vi phạm §2.6. Mỗi mức tin cậy ở đây đi kèm cỡ mẫu hiệu dụng
   và khoảng tin cậy bootstrap.

2. **Ước lượng cả bằng Cornish–Fisher.** CVaR lịch sử không bao giờ vượt quá
   quan sát tệ nhất đã thấy. Nếu lịch sử chưa có cú sập nào thì nó báo cáo
   rằng cú sập không tồn tại. Cornish–Fisher hiệu chỉnh phân vị chuẩn theo độ
   lệch và độ nhọn quan sát được, nên nó **có thể** vượt quá mẫu — đó là điểm
   mạnh, không phải lỗi.

3. **Đổi rủi ro thành cỡ vị thế.** Đây mới là công cụ: cho một ngân sách rủi ro
   ("tôi chấp nhận mất trung bình 2% vốn trong 5% phiên tệ nhất"), trả về
   `size_pct` tương ứng, cộng phân số Kelly và trần đòn bẩy trước ngưỡng thanh
   lý.

Mọi thứ ở đây đo trên lợi suất **đã quan sát được** của chính chiến lược đó.
Không có mô hình dự báo nào.
"""

from __future__ import annotations

import numpy as np
from scipy import stats as sps

from backend.i18n import bi

# Mức tin cậy báo cáo. 99% có mặt vì người dùng sẽ hỏi, nhưng nó là mức mà cỡ
# mẫu hiệu dụng nhỏ nhất, nên cảnh báo đi kèm quan trọng hơn con số.
LEVELS = (0.90, 0.95, 0.99)

# Dưới ngần này quan sát ở đuôi thì con số không đáng in ra hai chữ số thập
# phân. Ngưỡng tương đối với mức tin cậy, không phải một hằng số tuyệt đối.
MIN_TAIL_OBSERVATIONS = 10


def _finite(x) -> np.ndarray:
    a = np.asarray(x, dtype="float64")
    return a[np.isfinite(a)]


def _historical_var_cvar(returns: np.ndarray, level: float) -> tuple[float, float, int]:
    """VaR và CVaR lịch sử, cùng số quan sát thực sự nằm trong đuôi."""
    cutoff = float(np.percentile(returns, (1.0 - level) * 100.0))
    tail = returns[returns <= cutoff]
    if tail.size == 0:
        return cutoff, cutoff, 0
    return cutoff, float(tail.mean()), int(tail.size)


def _cornish_fisher_var(returns: np.ndarray, level: float) -> float:
    """Phân vị chuẩn hiệu chỉnh theo độ lệch và độ nhọn (Cornish–Fisher).

    CVaR lịch sử bị chặn bởi quan sát tệ nhất đã xảy ra. Trên một mẫu chưa gặp
    cú sập nào, nó báo rằng cú sập không tồn tại. Khai triển Cornish–Fisher đẩy
    phân vị ra xa theo đúng độ lệch trái và đuôi dày đã đo được, nên nó có thể
    nằm ngoài mẫu — và với quản trị rủi ro thì đó là điều cần.
    """
    z = float(sps.norm.ppf(1.0 - level))
    s = float(sps.skew(returns, bias=False)) if returns.size > 3 else 0.0
    k = float(sps.kurtosis(returns, bias=False)) if returns.size > 4 else 0.0
    z_cf = (
        z
        + (z**2 - 1.0) * s / 6.0
        + (z**3 - 3.0 * z) * k / 24.0
        - (2.0 * z**3 - 5.0 * z) * (s**2) / 36.0
    )
    return float(returns.mean() + z_cf * returns.std(ddof=1))


def _bootstrap_cvar(returns: np.ndarray, level: float, draws: int, rng) -> tuple[float, float]:
    """Sai số chuẩn và khoảng tin cậy 95% của CVaR, bằng bootstrap.

    CVaR là trung bình của một cái đuôi, nên độ chính xác của nó phụ thuộc vào
    số quan sát trong cái đuôi đó, không phải tổng số nến. Không có bước này
    thì CVaR 99% và CVaR 90% trông đáng tin ngang nhau, trong khi cái đầu
    thường dựa trên ít hơn cái sau hai bậc độ lớn.
    """
    n = returns.size
    values = np.empty(draws, dtype="float64")
    for i in range(draws):
        sample = returns[rng.integers(0, n, n)]
        cutoff = np.percentile(sample, (1.0 - level) * 100.0)
        tail = sample[sample <= cutoff]
        values[i] = tail.mean() if tail.size else cutoff
    return float(values.std(ddof=1)), (
        float(np.percentile(values, 2.5)),
        float(np.percentile(values, 97.5)),
    )


def tail_risk(bar_returns, simulations: int = 500, seed: int | None = 7) -> dict:
    """VaR/CVaR ở nhiều mức tin cậy, mỗi mức kèm độ tin cậy của chính nó."""
    r = _finite(bar_returns)
    if r.size < 60:
        return {"available": False, "reason": bi(
            f"Cần ít nhất 60 nến để ước lượng đuôi phân phối, hiện có {r.size}.",
            f"Estimating the tail needs at least 60 bars; there are {r.size}.",
        )}

    rng = np.random.default_rng(seed)
    levels = []
    for level in LEVELS:
        var_h, cvar_h, tail_n = _historical_var_cvar(r, level)
        var_cf = _cornish_fisher_var(r, level)
        se, (lo, hi) = _bootstrap_cvar(r, level, simulations, rng)
        thin = tail_n < MIN_TAIL_OBSERVATIONS
        levels.append({
            "level_pct": level * 100.0,
            "var_pct": var_h * 100.0,
            "cvar_pct": cvar_h * 100.0,
            "var_cornish_fisher_pct": var_cf * 100.0,
            # Cornish–Fisher vượt xa lịch sử nghĩa là đuôi quan sát được mỏng
            # hơn mức mà độ lệch và độ nhọn của chính nó ngụ ý.
            "cornish_fisher_gap_pct": (var_cf - var_h) * 100.0,
            "tail_observations": tail_n,
            "standard_error_pct": se * 100.0,
            "ci95_low_pct": lo * 100.0,
            "ci95_high_pct": hi * 100.0,
            "thin_tail": bool(thin),
            "note": bi(
                f"Chỉ {tail_n} nến nằm trong đuôi {level * 100:.0f}%. "
                "Trung bình của ngần ấy quan sát không đáng đọc tới hai chữ số "
                "thập phân; hãy đọc khoảng tin cậy thay vì con số điểm."
                if thin else
                f"{tail_n} nến trong đuôi.",
                f"Only {tail_n} bars fall in the {level * 100:.0f}% tail. The "
                "mean of that many observations does not deserve two decimal "
                "places; read the confidence interval, not the point estimate."
                if thin else
                f"{tail_n} bars in the tail.",
            ),
        })

    return {
        "available": True,
        "bars": int(r.size),
        "levels": levels,
        "method": bi(
            "CVaR lịch sử là trung bình các nến tệ nhất; nó **không bao giờ** "
            "vượt quá quan sát tệ nhất đã xảy ra, nên trên một mẫu chưa gặp cú "
            "sập nào nó sẽ báo rằng cú sập không tồn tại. Cột Cornish–Fisher "
            "hiệu chỉnh phân vị chuẩn theo độ lệch và độ nhọn đo được, nên nó "
            "có thể nằm ngoài mẫu — với quản trị rủi ro thì đó là điều cần.",
            "Historical CVaR is the mean of the worst bars; it can **never** "
            "exceed the worst observation that has already happened, so on a "
            "sample that has not met a crash it reports that crashes do not "
            "exist. The Cornish–Fisher column adjusts the normal quantile by "
            "the observed skew and kurtosis, so it can fall outside the "
            "sample — which for risk management is the point.",
        ),
    }


def kelly(trades: list[dict]) -> dict:
    """Phân số Kelly từ phân phối lãi/lỗ thật của các lệnh.

    Dùng lợi suất trên vốn tại thời điểm mở lệnh (`equity_after/equity_before`),
    đúng đại lượng engine thực sự cộng dồn — `pnl/initial_capital` là lợi suất
    trên một gốc cố định và chỉ đúng cho lệnh đầu tiên.
    """
    steps = []
    for t in trades:
        before = t.get("equity_before")
        after = t.get("equity_after")
        if before and after and before > 0:
            steps.append(after / before - 1.0)
    r = _finite(steps)
    if r.size < 20:
        return {"available": False, "reason": bi(
            f"Cần ít nhất 20 lệnh để ước lượng Kelly, hiện có {r.size}.",
            f"Estimating Kelly needs at least 20 trades; there are {r.size}.",
        )}

    wins, losses = r[r > 0], r[r < 0]
    if wins.size == 0 or losses.size == 0:
        return {"available": False, "reason": bi(
            "Cần có cả lệnh lãi và lệnh lỗ để tính Kelly.",
            "Kelly needs both winning and losing trades.",
        )}

    p = float(wins.size) / r.size
    avg_win = float(wins.mean())
    avg_loss = float(-losses.mean())
    payoff = avg_win / avg_loss
    f = (p * payoff - (1.0 - p)) / payoff

    return {
        "available": True,
        "trades": int(r.size),
        "win_rate": p,
        "payoff_ratio": payoff,
        "kelly_fraction": f,
        # Kelly đầy đủ tối đa hoá tốc độ tăng trưởng dài hạn nhưng đi kèm sụt
        # giảm mà gần như không ai chịu nổi; một nửa Kelly giữ ~75% tốc độ tăng
        # trưởng với khoảng một nửa biến động, nên đó mới là con số dùng được.
        "half_kelly_fraction": f / 2.0,
        "watch": bi(
            "Kelly giả định lợi suất mỗi lệnh độc lập và phân phối không đổi. "
            "Cả hai giả định đều sai với chuỗi giao dịch thật. Ước lượng này "
            "còn dùng chính mẫu đã sinh ra chiến lược, nên nó **thiên cao**. "
            "Kelly đầy đủ hầu như luôn quá lớn; nửa Kelly là mức thực dụng.",
            "Kelly assumes trade returns are independent and identically "
            "distributed. Both assumptions are false for a real trade "
            "sequence. This estimate also uses the very sample the strategy "
            "was built on, so it is **biased high**. Full Kelly is almost "
            "always too large; half Kelly is the practical figure.",
        ),
    }


def size_for_budget(bar_returns, budget_pct: float, level: float = 0.95) -> dict:
    """Cỡ vị thế suy ra từ ngân sách rủi ro, thay vì gõ tay một con số.

    Người dùng phát biểu điều họ chịu được — "trong 5% phiên tệ nhất tôi chấp
    nhận mất trung bình 2% vốn" — và đây trả lời `size_pct` nào tạo ra đúng mức
    đó. Đây là chiều ngược của bảng CVaR: bảng đo rủi ro của cỡ vị thế hiện
    tại, hàm này chọn cỡ vị thế cho một mức rủi ro cho trước.
    """
    r = _finite(bar_returns)
    if r.size < 60:
        return {"available": False, "reason": bi(
            f"Cần ít nhất 60 nến, hiện có {r.size}.",
            f"Needs at least 60 bars; there are {r.size}.",
        )}
    if budget_pct <= 0:
        return {"available": False, "reason": bi(
            "Ngân sách rủi ro phải lớn hơn 0.",
            "The risk budget must be above zero.",
        )}

    _, cvar, tail_n = _historical_var_cvar(r, level)
    loss = abs(cvar)
    if loss <= 0:
        return {"available": False, "reason": bi(
            "Không có nến lỗ nào trong đuôi, không suy ra được cỡ vị thế.",
            "No losing bars in the tail, so no position size can be derived.",
        )}

    # Lợi suất đã đo ứng với cỡ vị thế đã chạy backtest; tỷ lệ tuyến tính theo
    # cỡ vị thế vì cả hai đều nhân vào cùng giá trị danh nghĩa.
    scale = (budget_pct / 100.0) / loss
    return {
        "available": True,
        "budget_pct": budget_pct,
        "level_pct": level * 100.0,
        "measured_cvar_pct": cvar * 100.0,
        "tail_observations": tail_n,
        "size_multiplier": scale,
        "suggested_size_pct": min(scale * 100.0, 100.0),
        "capped": bool(scale > 1.0),
        "watch": bi(
            "Phép tỷ lệ này tuyến tính, đúng với ký quỹ và giá trị danh nghĩa, "
            "nhưng **không** đúng với thanh lý: tăng cỡ vị thế làm khoảng cách "
            "tới giá thanh lý ngắn lại theo cách phi tuyến. Nó cũng giả định "
            "phân phối lợi suất tương lai giống quá khứ đã đo.",
            "The scaling is linear, which is correct for margin and notional "
            "but **not** for liquidation: a larger position shortens the "
            "distance to the liquidation price non-linearly. It also assumes "
            "the future return distribution matches the measured past.",
        ),
    }


def leverage_ceiling(bar_returns, liquidation_buffer: float = 0.5) -> dict:
    """Đòn bẩy tối đa trước khi một nến xấu đủ sức chạm ngưỡng thanh lý.

    Engine thanh lý **trong nến** khi lỗ ăn hết ký quỹ (§3.1). Với đòn bẩy L,
    một biến động bất lợi 1/L là đủ. Hàm này so 1/L với các phân vị đuôi đã
    quan sát để nói mức đòn bẩy nào là mức mà lịch sử của chính chiến lược này
    đã từng chạm tới.
    """
    r = _finite(bar_returns)
    if r.size < 60:
        return {"available": False, "reason": bi(
            f"Cần ít nhất 60 nến, hiện có {r.size}.",
            f"Needs at least 60 bars; there are {r.size}.",
        )}

    worst = float(r.min())
    rows = []
    for level in LEVELS:
        cutoff, _, tail_n = _historical_var_cvar(r, level)
        move = abs(cutoff)
        rows.append({
            "level_pct": level * 100.0,
            "adverse_move_pct": move * 100.0,
            "max_leverage": (1.0 / move * liquidation_buffer) if move > 0 else None,
            "tail_observations": tail_n,
        })

    return {
        "available": True,
        "worst_bar_pct": worst * 100.0,
        "max_leverage_worst_bar": (1.0 / abs(worst) * liquidation_buffer) if worst < 0 else None,
        "buffer": liquidation_buffer,
        "levels": rows,
        "watch": bi(
            f"Tính trên biến động **theo nến đóng cửa**, nhân hệ số an toàn "
            f"{liquidation_buffer:.2f}. Thanh lý thật xét giá thấp nhất (mua) "
            "hoặc cao nhất (bán) trong nến, luôn xấu hơn giá đóng cửa, nên đây "
            "là **trần trên** chứ không phải mức an toàn. Nó cũng chỉ nói về "
            "những cú sốc đã từng xảy ra trong mẫu này.",
            f"Computed on **close-to-close** moves with a {liquidation_buffer:.2f} "
            "safety factor. Real liquidation checks the bar's low (long) or "
            "high (short), which is always worse than the close, so this is an "
            "**upper bound**, not a safe level. It also speaks only about "
            "shocks that have already happened in this sample.",
        ),
    }


def risk_tools(
    bar_returns,
    trades: list[dict],
    budget_pct: float = 2.0,
    simulations: int = 500,
) -> dict:
    """Toàn bộ bảng quản trị rủi ro cho một lần backtest."""
    return {
        "tail": tail_risk(bar_returns, simulations=simulations),
        "kelly": kelly(trades or []),
        "budget": size_for_budget(bar_returns, budget_pct),
        "leverage": leverage_ceiling(bar_returns),
    }
