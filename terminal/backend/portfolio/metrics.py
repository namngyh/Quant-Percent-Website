"""Portfolio performance metrics, each with the conditions it needs to mean anything.

Every ratio here has a denominator that can legitimately be near zero, and the
project has already shipped one number ruined by exactly that — a K-ratio
divided by a 1e-17 standard error, printed as "-0.07" and indistinguishable
from a real reading (§2.6). So no ratio is returned as a bare float: each one
comes back with a code saying whether it could be computed, and refuses rather
than dividing when its denominator is noise.

The thresholds are relative to the data's own scale, never comparisons against
zero. A portfolio whose daily returns are 0.0001 in size is not "flat", it is
small, and a rule written as `> 0` cannot tell those apart.

Log returns come in; that matters for compounding. Sums of log returns are
exact over any horizon, which is why CAGR is built from the sum rather than
from a product of simple returns.
"""

from __future__ import annotations

import math

import numpy as np

# Sessions in a Vietnamese trading year, used to annualise. Roughly 250 after
# holidays; the exact figure moves the annualised numbers by under a percent
# and using the same constant everywhere keeps them comparable to each other.
TRADING_DAYS = 250.0

# A ratio is refused when its denominator is smaller than this share of the
# series' own typical move. Relative, not absolute: see the module docstring.
_DENOMINATOR_FLOOR = 1e-6

# Below this many observations, higher moments are noise rather than shape.
MIN_FOR_MOMENTS = 30
# Capture ratios split the sample in two, so each side needs its own minimum.
MIN_PER_SIDE = 10


def _ratio(numerator: float, denominator: float, scale: float) -> tuple[float | None, str]:
    """Divide, or say why not.

    `scale` is what the denominator should be compared against — typically the
    series' own standard deviation. A denominator that is a millionth of the
    scale is floating-point residue, and dividing by it manufactures a large
    number out of nothing.
    """
    if not np.isfinite(numerator) or not np.isfinite(denominator):
        return None, "not_finite"
    if scale <= 0 or abs(denominator) < _DENOMINATOR_FLOOR * max(scale, 1e-12):
        return None, "denominator_too_small"
    value = numerator / denominator
    return (float(value), "ok") if np.isfinite(value) else (None, "not_finite")


def cagr(log_returns: np.ndarray, periods_per_year: float = TRADING_DAYS) -> float | None:
    """Annualised growth rate, compounded.

    Built from the sum of log returns rather than the mean of simple ones: the
    sum is exactly the total log growth over the window, so annualising it is
    one exponential rather than a chain of approximations.
    """
    n = log_returns.size
    if n < 2:
        return None
    total = float(log_returns.sum())
    years = n / periods_per_year
    if years <= 0:
        return None
    return float(math.expm1(total / years))


def sharpe(log_returns: np.ndarray, risk_free: float = 0.0,
           periods_per_year: float = TRADING_DAYS) -> dict:
    """Return per unit of total volatility, annualised.

    `risk_free` is an annual rate and defaults to zero, which is a choice
    rather than an omission: with a non-zero rate the number changes, and a
    platform that silently assumed one would be comparing against a benchmark
    the user never picked. The payload says which was used.
    """
    if log_returns.size < 2:
        return {"value": None, "code": "too_few_observations",
                "risk_free_pct": risk_free * 100}

    excess = log_returns - risk_free / periods_per_year
    sd = float(log_returns.std(ddof=1))
    value, code = _ratio(float(excess.mean()), sd, sd)
    return {
        "value": value * math.sqrt(periods_per_year) if value is not None else None,
        "code": code,
        "risk_free_pct": risk_free * 100,
    }


def sortino(log_returns: np.ndarray, risk_free: float = 0.0,
            periods_per_year: float = TRADING_DAYS) -> dict:
    """Return per unit of downside deviation.

    The downside deviation divides by the full sample size, not by the number
    of losing sessions. Dividing by the losses alone would make a portfolio
    that rarely loses look more volatile the fewer losses it had, which is
    backwards.
    """
    if log_returns.size < 2:
        return {"value": None, "code": "too_few_observations"}

    target = risk_free / periods_per_year
    shortfall = np.minimum(log_returns - target, 0.0)
    downside = float(np.sqrt((shortfall**2).mean()))

    if downside <= 0:
        # No losing session at all. That is not an infinite Sortino, it is a
        # sample too short or too lucky to have met a loss yet.
        return {"value": None, "code": "no_downside_observed"}

    value, code = _ratio(float((log_returns - target).mean()), downside,
                         float(log_returns.std(ddof=1)))
    return {
        "value": value * math.sqrt(periods_per_year) if value is not None else None,
        "code": code,
    }


def calmar(cagr_value: float | None, max_drawdown: float | None) -> dict:
    """CAGR per unit of worst drawdown.

    Refuses when the drawdown is negligible rather than reporting a huge
    ratio: a portfolio that has not drawn down yet has not been tested, and
    "Calmar 4,000" says nothing except that the denominator was small.
    """
    if cagr_value is None or max_drawdown is None:
        return {"value": None, "code": "missing_input"}
    depth = abs(max_drawdown)
    if depth < 0.005:                       # half a percent: no real drawdown yet
        return {"value": None, "code": "no_drawdown_yet"}
    return {"value": float(cagr_value / depth), "code": "ok"}


def information_ratio(portfolio: np.ndarray, benchmark: np.ndarray,
                      periods_per_year: float = TRADING_DAYS) -> dict:
    """Excess return over the benchmark per unit of tracking error.

    Tracking error near zero means the portfolio *is* the benchmark; the ratio
    is then meaningless rather than infinite, and saying so is the point.
    """
    if portfolio.size != benchmark.size or portfolio.size < 2:
        return {"value": None, "code": "too_few_observations"}

    active = portfolio - benchmark
    tracking = float(active.std(ddof=1))
    value, code = _ratio(float(active.mean()), tracking,
                         float(portfolio.std(ddof=1)))
    if code == "denominator_too_small":
        code = "tracks_the_benchmark"
    return {
        "value": value * math.sqrt(periods_per_year) if value is not None else None,
        "code": code,
        "tracking_error_pct": tracking * math.sqrt(periods_per_year) * 100,
    }


def alpha(portfolio: np.ndarray, benchmark: np.ndarray, beta: float | None,
          risk_free: float = 0.0, periods_per_year: float = TRADING_DAYS) -> dict:
    """Return not explained by market exposure (Jensen's alpha), annualised."""
    if beta is None or portfolio.size < 2 or portfolio.size != benchmark.size:
        return {"value": None, "code": "missing_beta"}

    rf = risk_free / periods_per_year
    residual = (portfolio - rf) - beta * (benchmark - rf)
    return {
        "value": float(residual.mean() * periods_per_year),
        "code": "ok",
    }


def capture(portfolio: np.ndarray, benchmark: np.ndarray) -> dict:
    """How much of the benchmark's up and down moves the portfolio takes.

    Split by the sign of the *benchmark*, which is what "when the market
    falls" means. Each side is refused separately: a window with three down
    sessions has no downside capture worth printing, even if its upside is
    well measured.
    """
    if portfolio.size != benchmark.size or portfolio.size < 2:
        return {"up": None, "down": None, "code": "too_few_observations"}

    out: dict = {"up": None, "down": None, "up_sessions": 0, "down_sessions": 0,
                 "code": "ok"}

    for side, mask in (("up", benchmark > 0), ("down", benchmark < 0)):
        count = int(mask.sum())
        out[f"{side}_sessions"] = count
        if count < MIN_PER_SIDE:
            continue
        bench_mean = float(benchmark[mask].mean())
        port_mean = float(portfolio[mask].mean())
        value, code = _ratio(port_mean, bench_mean, float(abs(benchmark[mask]).mean()))
        if code == "ok":
            out[side] = value * 100          # as a percentage, the usual form
    return out


def distribution(log_returns: np.ndarray) -> dict:
    """Skewness and excess kurtosis, with the sample size that produced them.

    Both are fourth- and third-moment statistics and are wildly unstable on
    short samples — which is exactly when they look most dramatic. The count
    travels with them so the reader can discount accordingly.
    """
    n = log_returns.size
    if n < MIN_FOR_MOMENTS:
        return {"skewness": None, "excess_kurtosis": None,
                "observations": int(n), "code": "too_few_observations"}

    centred = log_returns - log_returns.mean()
    sd = float(centred.std(ddof=0))
    if sd <= 0:
        return {"skewness": None, "excess_kurtosis": None,
                "observations": int(n), "code": "no_variation"}

    skew = float((centred**3).mean() / sd**3)
    kurt = float((centred**4).mean() / sd**4) - 3.0
    return {"skewness": skew, "excess_kurtosis": kurt,
            "observations": int(n), "code": "ok"}


def rolling_stability(log_returns: np.ndarray, window: int = 60,
                      periods_per_year: float = TRADING_DAYS) -> dict:
    """Rolling Sharpe and volatility: is the result steady or one lucky stretch?

    A single Sharpe over the whole window cannot tell a strategy that worked
    throughout from one that made everything in a fortnight. The spread of the
    rolling figure answers that, and the series itself is returned so the
    interface can draw it.
    """
    n = log_returns.size
    if n < window + 5:
        return {"available": False, "code": "window_longer_than_sample",
                "window": window, "observations": int(n)}

    sharpes, vols = [], []
    root = math.sqrt(periods_per_year)
    for end in range(window, n + 1):
        chunk = log_returns[end - window:end]
        sd = float(chunk.std(ddof=1))
        vols.append(sd * root)
        value, code = _ratio(float(chunk.mean()), sd, sd)
        sharpes.append(value * root if code == "ok" else None)

    measured = [s for s in sharpes if s is not None]
    return {
        "available": True,
        "code": "ok",
        "window": window,
        "sharpe": sharpes,
        "volatility_pct": [v * 100 for v in vols],
        "sharpe_min": min(measured) if measured else None,
        "sharpe_max": max(measured) if measured else None,
        # The spread is the reading that matters: a Sharpe of 1.2 that ranged
        # from -0.4 to 3.1 is a different claim from one that stayed near 1.2.
        "sharpe_spread": (max(measured) - min(measured)) if len(measured) > 1 else None,
        "volatility_min_pct": min(vols) * 100,
        "volatility_max_pct": max(vols) * 100,
    }


def performance(log_returns: np.ndarray, benchmark: np.ndarray | None,
                beta: float | None, max_drawdown: float | None,
                risk_free: float = 0.0) -> dict:
    """Every metric above, assembled, with the benchmark ones omitted when
    there is no benchmark to compare against rather than filled with zeros."""
    growth = cagr(log_returns)
    out = {
        "cagr_pct": growth * 100 if growth is not None else None,
        "sharpe": sharpe(log_returns, risk_free),
        "sortino": sortino(log_returns, risk_free),
        "calmar": calmar(growth, max_drawdown),
        "distribution": distribution(log_returns),
        "rolling": rolling_stability(log_returns),
        "risk_free_pct": risk_free * 100,
        "trading_days_per_year": TRADING_DAYS,
    }

    if benchmark is None or benchmark.size != log_returns.size or benchmark.size < 2:
        out["benchmark"] = {"available": False, "code": "no_benchmark_overlap"}
        return out

    out["benchmark"] = {
        "available": True,
        "information_ratio": information_ratio(log_returns, benchmark),
        "alpha": alpha(log_returns, benchmark, beta, risk_free),
        "capture": capture(log_returns, benchmark),
    }
    return out
