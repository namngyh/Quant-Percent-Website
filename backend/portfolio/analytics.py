"""Phân tích danh mục cổ phiếu Việt Nam.

Chuyển từ tính năng Quant Portfolio của quantpercent.com sang nền tảng này.
Phần toán giữ nguyên; phần dữ liệu và phần dự phóng thì không, và lý do được
ghi rõ bên dưới thay vì để người đọc tự phát hiện.

Nguyên tắc xuyên suốt: **mọi con số trả về đều đo được từ lịch sử giá mà
database này có, hoặc bị bỏ đi.** Không có lợi suất giả định, không có tương
quan giả định, không có giá trị lấp chỗ trống. Một mã có lịch sử quá ngắn để
đo thì được báo trong ``unpriced`` chứ không được gán một con số trông hợp lý.

Phần đáng đọc kỹ nhất là **đóng góp rủi ro**. Phần rủi ro của một vị thế không
phải là phần tiền của nó, mà là

    wᵢ · (Σw)ᵢ / (wᵀΣw)

tức là đã tính cả việc nó di chuyển cùng chiều với phần còn lại. Một mã chiếm
25% tiền nhưng đi cùng nhịp với cả danh mục có thể chiếm 45% rủi ro, và khoảng
cách đó là thứ hữu ích nhất mà module này báo cáo.

Hiệp phương sai dùng co rút Ledoit–Wolf về mục tiêu tương quan hằng số. Với
khoảng 250 quan sát và 10–30 mã, hiệp phương sai mẫu bị ước lượng rất tệ, và
mọi thứ tính từ nó còn tệ hơn; co rút là cách xử lý tiêu chuẩn chứ không phải
một tuỳ chọn nâng cao.

**Hai khác biệt so với bản gốc**, cả hai đều do quyền truy cập dữ liệu:

* **Không có ngành.** Bản gốc lấy ngành từ ``web.symbols``. Tài khoản đọc của
  nền tảng này chỉ thấy schema ``api``, nên phần tỷ trọng theo ngành bị bỏ hẳn
  thay vì đoán ngành từ mã cổ phiếu.
* **Dự phóng tự tính, không mượn mô hình.** Bản gốc ánh xạ một lần chạy
  Monte-Carlo VN-Index của mô hình RARF-FHE lên danh mục qua beta và quy tắc
  căn bậc hai của thời gian. Nền tảng này không có lần chạy đó, và mượn số của
  một mô hình mà mình không kiểm chứng được thì tệ hơn là tự mô phỏng. Nên
  phần dự phóng ở đây là **bootstrap khối** trên chính chuỗi lợi suất của danh
  mục — xem ``forward_risk``.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np

from backend.i18n import bi

TRADING_DAYS = 252
BENCHMARK = "VNINDEX"

# HOSE niêm yết giá theo nghìn đồng và feed lưu đúng như vậy: VIC đóng cửa ở
# 256.1 nghĩa là 256 100 đồng. Người dùng nhập giá vốn và tiền mặt bằng đồng,
# nên giá phải quy về đồng trước khi cộng bất cứ thứ gì với bất cứ thứ gì.
# Thiếu bước này thì mọi danh mục có giá vốn đều ra lãi/lỗ khoảng −100%.
PRICE_UNIT_VND = 1_000

# Một vị thế cần đủ quan sát để độ biến động và tương quan của nó có nghĩa.
# Sáu mươi phiên là khoảng một quý; dưới mức đó thì ước lượng là nhiễu được
# trình bày dưới dạng một con số.
MIN_OBSERVATIONS = 60

# Các mức sụt giảm mà bảng dự phóng báo cáo. Cố định chứ không suy ra từ danh
# mục: khi ngưỡng thay đổi theo từng danh mục thì mọi danh mục đều cho cùng một
# đường cong ở những nhãn hơi khác nhau, và bảng không đọc được. Cố định trục
# đẩy phần khác biệt về đúng chỗ người đọc nhìn thấy — cột xác suất.
DRAWDOWN_THRESHOLDS = (0.03, 0.05, 0.07, 0.10, 0.15, 0.20, 0.30)

MAX_HOLDINGS = 50
DEFAULT_PATHS = 4000

_RNG = np.random.default_rng(20260101)


class PortfolioError(ValueError):
    """Danh mục không đo được — do dữ liệu, không phải do lỗi lập trình."""


# ------------------------------------------------------------------ dữ liệu

def _aligned_returns(
    closes: dict[str, dict], symbols: list[str]
) -> tuple[list[date], np.ndarray]:
    """Lợi suất log trên những phiên mà **mọi** mã đều có giao dịch.

    Lấy giao thay vì điền tiếp giá trước đó: một giá được điền tạo ra lợi suất
    bằng 0, điều này kéo độ biến động đo được xuống và kéo tương quan lên. Cả
    hai sai lệch đều tâng bốc danh mục, nên không chấp nhận được ở đây.
    """
    if not symbols:
        return [], np.empty((0, 0))

    common = set(closes[symbols[0]])
    for s in symbols[1:]:
        common &= set(closes[s])
    dates = sorted(common)
    if len(dates) < 2:
        return dates, np.empty((0, len(symbols)))

    prices = np.array([[closes[s][d] for s in symbols] for d in dates])
    return dates[1:], np.diff(np.log(prices), axis=0)


def _daily_log_returns(closes: dict) -> dict:
    """Lợi suất log từng phiên, so với phiên liền trước của chính chuỗi đó.

    Khoá theo ngày để một chuỗi ghép được với chuỗi khác vốn giữ tập phiên khác
    — cần thiết vì chỉ số và cổ phiếu không phải lúc nào cũng có cùng số phiên
    trong cửa sổ.
    """
    ordered = sorted(closes)
    return {
        later: math.log(closes[later] / closes[earlier])
        for earlier, later in zip(ordered, ordered[1:], strict=False)
        if closes[earlier] > 0 and closes[later] > 0
    }


# -------------------------------------------------------------- hiệp phương sai

def ledoit_wolf(returns: np.ndarray) -> tuple[np.ndarray, float]:
    """Hiệp phương sai mẫu, co rút về mục tiêu tương quan hằng số.

    Ledoit và Wolf (2004), **có** số hạng rho. Bỏ rho — cách rút gọn phổ biến —
    làm cường độ co rút bị thổi lên, và trên lợi suất ngày của thị trường Việt
    Nam nó bão hoà ở 1.0: mọi tương quan sụp về giá trị trung bình và ma trận
    mất đúng cái cấu trúc mà phân tích này tồn tại để tìm. Một rổ toàn mã cùng
    đi với nhau phải phân biệt được với một rổ không như vậy.

    Trả về (ma trận, cường độ co rút). Cường độ được báo cáo ra ngoài chứ không
    giấu đi: nó nói cho người đọc biết bao nhiêu phần kết quả đến từ dữ liệu và
    bao nhiêu phần đến từ mục tiêu co rút.
    """
    n_obs, n_assets = returns.shape
    if n_assets < 2 or n_obs < 3:
        return np.cov(returns, rowvar=False, ddof=1).reshape(n_assets, n_assets), 0.0

    # Dùng 1/n xuyên suốt, để ma trận mẫu, pi, rho và gamma cùng một chuẩn;
    # ước lượng này được định nghĩa như vậy.
    centred = returns - returns.mean(axis=0)
    sample = centred.T @ centred / n_obs
    var = np.diag(sample)
    std = np.sqrt(var)
    outer_std = np.outer(std, std)
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = np.where(outer_std > 0, sample / outer_std, 0.0)
    off = ~np.eye(n_assets, dtype=bool)
    mean_corr = float(corr[off].mean())

    target = mean_corr * outer_std
    np.fill_diagonal(target, var)

    gamma = float(((target - sample) ** 2).sum())
    if gamma <= 0:
        return sample, 0.0

    squared = centred**2
    # pi_ij = phương sai của mô-men bậc hai mẫu.
    pi_matrix = (squared.T @ squared) / n_obs - sample**2
    pi = float(pi_matrix.sum())

    # theta_ii_ij = Cov(sample_ii, sample_ij), và chuyển vị cho jj.
    cubed_cross = (centred**3).T @ centred / n_obs
    theta_ii = cubed_cross - var[:, None] * sample
    theta_jj = cubed_cross.T - var[None, :] * sample

    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(outer_std > 0, std[None, :] / std[:, None], 0.0)
    inverse = np.where(ratio == 0, np.inf, ratio)
    cross = 0.5 * mean_corr * (ratio * theta_ii + theta_jj / inverse)
    rho = float(np.trace(pi_matrix) + cross[off].sum())

    intensity = max(0.0, min(1.0, (pi - rho) / gamma / n_obs))
    return intensity * target + (1.0 - intensity) * sample, intensity


# ------------------------------------------------------------------ rủi ro

def _max_drawdown(returns: np.ndarray) -> float:
    """Mức rơi sâu nhất từ đỉnh xuống đáy của đường lợi suất cộng dồn."""
    if returns.size == 0:
        return 0.0
    equity = np.exp(np.cumsum(returns))
    peak = np.maximum.accumulate(equity)
    return float((equity / peak - 1.0).min())


def _risk_state(volatility: float, drawdown: float) -> str:
    if volatility >= 0.35 or drawdown <= -0.25:
        return "cao"
    if volatility >= 0.25 or drawdown <= -0.15:
        return "đáng chú ý"
    if volatility >= 0.15 or drawdown <= -0.08:
        return "trung bình"
    return "thấp"


def forward_risk(
    portfolio_returns: np.ndarray,
    horizon_days: int,
    paths: int = DEFAULT_PATHS,
) -> dict:
    """Mô phỏng danh mục về phía trước bằng bootstrap khối.

    Bản gốc trên quantpercent.com mượn một lần chạy Monte-Carlo VN-Index của mô
    hình RARF-FHE rồi ánh xạ lên danh mục qua beta và quy tắc căn bậc hai thời
    gian. Nền tảng này không có lần chạy đó, và **mượn số của một mô hình mà
    mình không kiểm chứng được thì tệ hơn là tự mô phỏng**. Nên ở đây mọi thứ
    được tạo ra từ chính chuỗi lợi suất đã đo của danh mục.

    Dùng bootstrap khối tĩnh (Politis–Romano 1994) chứ không lấy mẫu độc lập
    từng ngày. Lý do: kiểm định ARCH ở tab Thống kê gần như luôn bác bỏ giả
    thuyết biến động cố định. Lấy mẫu độc lập sẽ phá vỡ hiện tượng gom cụm biến
    động, và **đánh giá thấp có hệ thống** xác suất của những đợt sụt sâu — vốn
    xảy ra chính vì các phiên xấu đi liền nhau. Lấy theo khối giữ lại điều đó.

    Độ dài khối kỳ vọng lấy theo quy tắc n^(1/3), là quy tắc thông dụng cho
    bootstrap khối; nó được báo cáo ra ngoài để người đọc biết giả định nào
    đang đứng sau các con số.

    Điều mô phỏng này **không** làm: nó không tạo ra cú sốc nào lớn hơn cú sốc
    lớn nhất đã từng xảy ra trong cửa sổ quan sát, vì nó chỉ xáo lại những ngày
    có thật. Đây là giới hạn thật và được nêu trong ``caveat``.
    """
    r = portfolio_returns[np.isfinite(portfolio_returns)]
    n = r.size
    if n < MIN_OBSERVATIONS:
        return {"available": False, "reason": bi(
            f"Cần ít nhất {MIN_OBSERVATIONS} phiên.",
            f"At least {MIN_OBSERVATIONS} sessions are needed.",
        )}

    block_length = max(5.0, round(n ** (1 / 3)))
    restart = 1.0 / block_length

    # Bootstrap khối tĩnh, véc-tơ hoá theo đường đi: mỗi bước, một phần các
    # đường nhảy tới vị trí ngẫu nhiên mới, phần còn lại đi tiếp một ngày.
    index = _RNG.integers(0, n, size=paths)
    simulated = np.empty((paths, horizon_days), dtype="float64")
    for step in range(horizon_days):
        simulated[:, step] = r[index]
        jump = _RNG.random(paths) < restart
        index = np.where(jump, _RNG.integers(0, n, size=paths), (index + 1) % n)

    cumulative = np.cumsum(simulated, axis=1)
    terminal = np.exp(cumulative[:, -1]) - 1.0

    # Sụt giảm sâu nhất trong từng đường đi, không phải chỉ kết quả cuối kỳ:
    # một danh mục kết thúc hoà vốn sau khi có lúc âm 25% vẫn là một danh mục
    # mà phần lớn người giữ đã bán ra ở giữa đường.
    equity = np.exp(cumulative)
    peak = np.maximum.accumulate(equity, axis=1)
    depth = (equity / peak - 1.0).min(axis=1)

    # Lấy mẫu các mốc thời gian dọc theo kỳ dự phóng để vẽ biểu đồ quạt (fan chart)
    step_indices = np.linspace(0, horizon_days - 1, num=min(25, horizon_days), dtype=int)
    fan_steps = []
    for s in step_indices:
        step_returns = (equity[:, s] - 1.0) * 100
        fan_steps.append({
            "day": int(s + 1),
            "p05": round(float(np.percentile(step_returns, 5)), 2),
            "p25": round(float(np.percentile(step_returns, 25)), 2),
            "p50": round(float(np.percentile(step_returns, 50)), 2),
            "p75": round(float(np.percentile(step_returns, 75)), 2),
            "p95": round(float(np.percentile(step_returns, 95)), 2),
        })

    return {
        "available": True,
        "method": bi("bootstrap khối tĩnh (Politis–Romano)",
                     "stationary block bootstrap (Politis–Romano)"),
        "horizon_days": int(horizon_days),
        "paths": int(paths),
        "observations": int(n),
        "block_length": float(block_length),
        "expected_return_pct": float(np.mean(terminal) * 100),
        "median_return_pct": float(np.median(terminal) * 100),
        "var_95_pct": float(np.percentile(terminal, 5) * 100),
        "cvar_95_pct": float(
            terminal[terminal <= np.percentile(terminal, 5)].mean() * 100
        ),
        "p05_pct": float(np.percentile(terminal, 5) * 100),
        "p95_pct": float(np.percentile(terminal, 95) * 100),
        "prob_loss_pct": float((terminal < 0).mean() * 100),
        "drawdown_probabilities": [
            {
                "threshold_pct": -level * 100,
                "probability_pct": float((depth <= -level).mean() * 100),
            }
            for level in DRAWDOWN_THRESHOLDS
        ],
        "median_max_drawdown_pct": float(np.median(depth) * 100),
        "fan_steps": fan_steps,
        "caveat": bi(
            "Mô phỏng chỉ xáo lại những ngày ĐÃ XẢY RA trong cửa sổ quan sát, "
            "nên nó không bao giờ sinh ra cú sốc lớn hơn cú sốc lớn nhất đã "
            "từng có. Nếu cửa sổ này không chứa một đợt sụp thị trường thì các "
            "xác suất bên trên là cận dưới, không phải ước lượng đầy đủ.",
            "The simulation only reshuffles days that ACTUALLY HAPPENED in the "
            "observed window, so it can never produce a shock larger than the "
            "largest one on record. If this window contains no market crash, the "
            "probabilities above are a floor rather than a full estimate.",
        ),
    }


# ----------------------------------------------------------------- tập trung

def _concentration(
    symbols: list[str], weights: np.ndarray, cov: np.ndarray
) -> dict:
    ordered = np.sort(weights)[::-1]
    hhi = float((weights**2).sum())

    std = np.sqrt(np.diag(cov))
    outer = np.outer(std, std)
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = np.where(outer > 0, cov / outer, 0.0)
    off = ~np.eye(len(symbols), dtype=bool)
    average_corr = float(corr[off].mean()) if off.any() else 0.0

    max_pair = None
    max_corr = None
    if off.any():
        masked = np.where(off, corr, -np.inf)
        i, j = divmod(int(np.argmax(masked)), len(symbols))
        max_corr = float(corr[i, j])
        max_pair = sorted([symbols[i], symbols[j]])

    # Số cược hiệu dụng: danh mục này thật sự nắm bao nhiêu vị thế độc lập.
    # Mười mã có tương quan trung bình 0.7 hành xử như ít hơn nhiều, và đây là
    # con số nói ra điều đó.
    count = len(symbols)
    if count > 1 and average_corr > -1:
        denominator = 1.0 + (count - 1) * max(average_corr, 0.0)
        effective_bets = count / denominator if denominator > 0 else float(count)
    else:
        effective_bets = float(count)

    corr_list = []
    if len(symbols) > 0 and corr.shape == (len(symbols), len(symbols)):
        corr_list = [[round(float(val), 3) for val in row] for row in corr]

    return {
        "positions": count,
        "symbols": list(symbols),
        "correlation_matrix": corr_list,
        "largest_weight_pct": float(ordered[0] * 100) if ordered.size else 0.0,
        "top_three_weight_pct": float(ordered[:3].sum() * 100),
        "herfindahl": hhi,
        "effective_assets": 1.0 / hhi if hhi > 0 else 0.0,
        "effective_bets": effective_bets,
        "average_correlation": average_corr,
        "max_pair_correlation": max_corr,
        "max_pair": max_pair,
    }


# ------------------------------------------------------------------ lắp ráp

def analyse(
    holdings: list[dict],
    cash: float,
    lookback_days: int,
    horizon_days: int,
    loader,
) -> dict:
    """Đo một danh mục đã nhập, dựa trên chính lịch sử giá của nó.

    ``loader(symbols, lookback)`` trả về ``{symbol: {date: close}}``. Truyền vào
    thay vì gọi thẳng ``market_vn`` để phần toán kiểm thử được mà không cần VPN.
    """
    if not holdings:
        raise PortfolioError("Chưa nhập mã nào.")
    if len(holdings) > MAX_HOLDINGS:
        raise PortfolioError(f"Tối đa {MAX_HOLDINGS} mã trong một danh mục.")

    by_symbol = {h["symbol"]: h for h in holdings}
    symbols = list(by_symbol)
    if len(symbols) != len(holdings):
        raise PortfolioError("Mỗi mã chỉ được xuất hiện một lần.")

    closes = loader(symbols + [BENCHMARK], lookback_days)

    priced = [s for s in symbols if len(closes.get(s, {})) >= MIN_OBSERVATIONS]
    unpriced = [s for s in symbols if s not in priced]
    if not priced:
        raise PortfolioError(
            "Không mã nào có đủ lịch sử giá để phân tích "
            f"(cần {MIN_OBSERVATIONS} phiên)."
        )

    dates, returns = _aligned_returns(closes, priced)
    n_obs = returns.shape[0]
    if n_obs < MIN_OBSERVATIONS:
        raise PortfolioError(
            "Các mã trong danh mục không có đủ phiên giao dịch chung để phân "
            f"tích (chỉ {n_obs} phiên trùng nhau, cần {MIN_OBSERVATIONS})."
        )

    # Lợi suất không có đơn vị, nên chỉ mức giá cần quy đổi.
    last_price = {s: closes[s][max(closes[s])] * PRICE_UNIT_VND for s in priced}
    values = np.array([by_symbol[s]["quantity"] * last_price[s] for s in priced])
    invested = float(values.sum())
    total_value = invested + cash
    weights = values / invested if invested > 0 else np.zeros_like(values)

    cov, shrinkage = ledoit_wolf(returns)

    # Phương sai danh mục dùng tỷ trọng trên phần đã đầu tư: tiền mặt không có
    # phương sai, và tính nó vào sẽ làm nhẹ đi rủi ro của phần đang chịu rủi ro.
    portfolio_variance = float(weights @ cov @ weights)
    volatility = math.sqrt(max(portfolio_variance, 0.0)) * math.sqrt(TRADING_DAYS)

    portfolio_returns = returns @ weights
    downside = portfolio_returns[portfolio_returns < 0]
    downside_deviation = (
        float(downside.std(ddof=1)) * math.sqrt(TRADING_DAYS)
        if downside.size > 1 else 0.0
    )

    # Mô phỏng lịch sử thay vì giả định chuẩn: đuôi trái của một danh mục cổ
    # phiếu Việt Nam dày hơn nhiều so với mức phân phối chuẩn cho phép.
    var_95 = float(np.percentile(portfolio_returns, 5))
    tail = portfolio_returns[portfolio_returns <= var_95]
    cvar_95 = float(tail.mean()) if tail.size else var_95
    max_dd = _max_drawdown(portfolio_returns)

    # Beta so với chỉ số, trên đúng những phiên hai bên cùng có.
    beta = None
    benchmark_returns = _daily_log_returns(closes.get(BENCHMARK, {}))
    shared = [i for i, d in enumerate(dates) if d in benchmark_returns]
    benchmark = np.array([benchmark_returns[dates[i]] for i in shared])
    benchmark_var = float(benchmark.var(ddof=1)) if benchmark.size > 1 else 0.0
    if len(shared) >= MIN_OBSERVATIONS and benchmark_var > 0:
        rows = np.array(shared)
        beta = float(
            np.cov(portfolio_returns[rows], benchmark, ddof=1)[0, 1] / benchmark_var
        )

    # Đóng góp rủi ro: tỷ trọng nhân đóng góp biên, chuẩn hoá về tổng bằng 1.
    marginal = cov @ weights
    contributions = weights * marginal
    total_contribution = float(contributions.sum())
    risk_shares = (
        contributions / total_contribution if total_contribution > 0
        else np.zeros_like(contributions)
    )

    asset_volatility = np.sqrt(np.diag(cov)) * math.sqrt(TRADING_DAYS)

    asset_betas: dict[str, float | None] = dict.fromkeys(priced)
    if beta is not None:
        rows = np.array(shared)
        for i, symbol in enumerate(priced):
            asset_betas[symbol] = float(
                np.cov(returns[rows, i], benchmark, ddof=1)[0, 1] / benchmark_var
            )

    positions = []
    total_cost = 0.0
    has_cost = True
    for i, symbol in enumerate(priced):
        holding = by_symbol[symbol]
        value = float(values[i])
        basis = holding.get("cost_basis")
        cost = basis * holding["quantity"] if basis else None
        if cost is None:
            has_cost = False
        else:
            total_cost += cost

        positions.append({
            "symbol": symbol,
            "quantity": holding["quantity"],
            "price": last_price[symbol],
            "market_value": value,
            "weight_pct": float(weights[i] * 100),
            "cost_basis": basis,
            "profit": value - cost if cost is not None else None,
            "profit_pct": (value - cost) / cost * 100 if cost else None,
            "volatility_pct": float(asset_volatility[i] * 100),
            "beta": asset_betas[symbol],
            "risk_contribution_pct": float(risk_shares[i] * 100),
            # Khoảng cách giữa phần rủi ro và phần tiền. Dương nghĩa là vị thế
            # này gánh nhiều rủi ro hơn mức cỡ của nó gợi ý.
            "risk_gap_pct": float((risk_shares[i] - weights[i]) * 100),
            "observations": len(closes[symbol]),
        })

    positions.sort(key=lambda p: p["risk_contribution_pct"], reverse=True)

    return {
        "total_value": total_value,
        "invested_value": invested,
        "cash": cash,
        "cash_weight_pct": cash / total_value * 100 if total_value else 0.0,
        "total_cost": total_cost if has_cost else None,
        "profit": invested - total_cost if has_cost else None,
        "profit_pct": (
            (invested - total_cost) / total_cost * 100
            if has_cost and total_cost else None
        ),
        "lookback_days": lookback_days,
        "observations": n_obs,
        "first_session": str(dates[0]) if dates else None,
        "last_session": str(dates[-1]) if dates else None,
        "volatility_pct": volatility * 100,
        "downside_deviation_pct": downside_deviation * 100,
        "max_drawdown_pct": max_dd * 100,
        "beta": beta,
        "var_95_pct": var_95 * 100,
        "cvar_95_pct": cvar_95 * 100,
        "risk_state": _risk_state(volatility, max_dd),
        "shrinkage_intensity": shrinkage,
        "positions": positions,
        "concentration": _concentration(priced, weights, cov),
        "forward": forward_risk(portfolio_returns, horizon_days),
        "unpriced": unpriced,
        "notes": _notes(positions, unpriced, shrinkage),
    }


def _notes(positions: list[dict], unpriced: list[str], shrinkage: float) -> list[str]:
    """Những điều đáng nói thành lời, thay vì để người đọc tự tìm trong bảng."""
    notes = []

    if positions:
        standout = max(positions, key=lambda p: p["risk_gap_pct"])
        if standout["risk_gap_pct"] > 5:
            notes.append(bi(
                f"{standout['symbol']} chiếm {standout['weight_pct']:.1f}% tiền "
                f"nhưng {standout['risk_contribution_pct']:.1f}% rủi ro — cao hơn "
                f"{standout['risk_gap_pct']:.1f} điểm phần trăm so với cỡ vị thế. "
                "Nguyên nhân là nó vừa biến động mạnh hơn vừa đi cùng chiều với "
                "phần còn lại của danh mục.",
                f"{standout['symbol']} is {standout['weight_pct']:.1f}% of the "
                f"money but {standout['risk_contribution_pct']:.1f}% of the risk "
                f"— {standout['risk_gap_pct']:.1f} percentage points above what "
                "its size suggests. It is both more volatile than the rest and "
                "moving in the same direction as it.",
            ))

    if unpriced:
        listed = ", ".join(unpriced)
        notes.append(bi(
            "Không phân tích được: " + listed +
            f" — chưa đủ {MIN_OBSERVATIONS} phiên lịch sử. Các mã này bị loại "
            "khỏi mọi con số bên trên, nên danh mục được đo không phải là danh "
            "mục bạn đã nhập.",
            "Could not be analysed: " + listed +
            f" — fewer than {MIN_OBSERVATIONS} sessions of history. These are "
            "excluded from every figure above, so the portfolio measured is not "
            "the portfolio you entered.",
        ))

    if shrinkage > 0.5:
        notes.append(bi(
            f"Cường độ co rút {shrinkage * 100:.0f}%: với số phiên hiện có, hơn "
            "một nửa ma trận hiệp phương sai đến từ mục tiêu tương quan hằng số "
            "chứ không từ dữ liệu. Tăng số phiên quan sát để giảm con số này.",
            f"Shrinkage intensity {shrinkage * 100:.0f}%: at this number of "
            "sessions, more than half the covariance matrix comes from the "
            "constant-correlation target rather than from the data. A longer "
            "window brings it down.",
        ))

    notes.append(bi(
        "Không có dữ liệu ngành: tài khoản đọc của nền tảng chỉ thấy schema "
        "`api`, còn bảng ngành nằm ở schema `web`. Vì vậy phần tỷ trọng theo "
        "ngành bị bỏ hẳn thay vì đoán ngành từ mã cổ phiếu.",
        "No sector data: the platform's read-only account can see only the "
        "`api` schema, and the sector table lives in `web`. Sector weights are "
        "therefore dropped entirely rather than guessed from ticker symbols.",
    ))
    return notes
