"""Portfolio performance metrics.

Every ratio here divides by something that can legitimately be near zero, and
this project has already shipped one number ruined by exactly that: a K-ratio
divided by a 1e-17 standard error, printed as "-0.07", indistinguishable from
a real reading (§2.6). So most of these checks are about refusals — the cases
where the honest answer is "cannot be computed" rather than a large number
manufactured from noise.

Run:  .venv\\Scripts\\python.exe tests/test_portfolio_metrics.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from backend.portfolio import metrics as m  # noqa: E402

CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


def steady(daily_pct: float, n: int = 500) -> np.ndarray:
    """A series that grows by the same log amount every session."""
    return np.full(n, math.log1p(daily_pct))


@check("CAGR compounds rather than averaging")
def _():
    # 0.1% a session for exactly one trading year must compound, not multiply:
    # 250 * 0.001 = 25% is the wrong answer.
    out = m.cagr(steady(0.001, int(m.TRADING_DAYS)))
    assert out is not None
    expected = math.expm1(math.log1p(0.001) * m.TRADING_DAYS)
    assert abs(out - expected) < 1e-9, (out, expected)
    assert out > 0.28, out          # compounding pushes it above the naive 25%


@check("a flat series does not produce a Sharpe")
def _():
    """Zero variance is the K-ratio trap: the denominator is not small, it is
    absent, and dividing by it invents a number."""
    out = m.sharpe(np.zeros(300))
    assert out["value"] is None, out
    assert out["code"] == "denominator_too_small", out


@check("Sharpe is annualised, and the risk-free rate used is stated")
def _():
    daily = 0.0004
    returns = np.full(400, daily) + np.random.default_rng(7).normal(0, 0.01, 400)
    out = m.sharpe(returns, risk_free=0.0)
    assert out["code"] == "ok", out
    # Annualising multiplies by sqrt(250); a per-session Sharpe would be ~16x
    # smaller, so the magnitude alone distinguishes them.
    per_session = returns.mean() / returns.std(ddof=1)
    assert abs(out["value"] - per_session * math.sqrt(m.TRADING_DAYS)) < 1e-9
    # The assumption travels with the number rather than being implied.
    assert out["risk_free_pct"] == 0.0, out


@check("Sortino divides by the whole sample, not by the losses alone")
def _():
    """Dividing by the count of losing sessions would make a portfolio look
    more volatile the fewer losses it had, which is backwards."""
    rng = np.random.default_rng(3)
    returns = rng.normal(0.0005, 0.01, 400)
    out = m.sortino(returns)
    assert out["code"] == "ok", out

    shortfall = np.minimum(returns, 0.0)
    downside = math.sqrt((shortfall**2).mean())          # /n, not /n_losses
    expected = returns.mean() / downside * math.sqrt(m.TRADING_DAYS)
    assert abs(out["value"] - expected) < 1e-9, (out["value"], expected)


@check("a series that never loses reports no Sortino rather than infinity")
def _():
    out = m.sortino(steady(0.001, 300))
    assert out["value"] is None, out
    assert out["code"] == "no_downside_observed", out


@check("Calmar refuses when there has been no real drawdown")
def _():
    # "Calmar 4,000" says nothing except that the denominator was tiny.
    assert m.calmar(0.40, -0.0001)["code"] == "no_drawdown_yet"
    assert m.calmar(0.40, 0.0)["code"] == "no_drawdown_yet"

    out = m.calmar(0.40, -0.20)
    assert out["code"] == "ok" and abs(out["value"] - 2.0) < 1e-12, out


@check("a portfolio that IS the benchmark has no information ratio")
def _():
    """Tracking error near zero means there is no active bet to judge."""
    rng = np.random.default_rng(11)
    bench = rng.normal(0.0003, 0.012, 300)
    out = m.information_ratio(bench.copy(), bench)
    assert out["value"] is None, out
    assert out["code"] == "tracks_the_benchmark", out


@check("information ratio measures the active bet when there is one")
def _():
    rng = np.random.default_rng(5)
    bench = rng.normal(0.0002, 0.011, 400)
    port = bench + rng.normal(0.0003, 0.004, 400)
    out = m.information_ratio(port, bench)
    assert out["code"] == "ok", out
    assert out["tracking_error_pct"] > 0, out


@check("alpha is what beta does not explain")
def _():
    """A portfolio that is exactly 1.5x the benchmark with nothing added has no
    alpha; the same portfolio plus a constant does, and it is that constant."""
    rng = np.random.default_rng(2)
    bench = rng.normal(0.0004, 0.01, 400)

    pure = 1.5 * bench
    assert abs(m.alpha(pure, bench, beta=1.5)["value"]) < 1e-9

    edge = 0.0002
    out = m.alpha(pure + edge, bench, beta=1.5)
    assert abs(out["value"] - edge * m.TRADING_DAYS) < 1e-9, out


@check("capture needs enough sessions on each side, separately")
def _():
    # Plenty of up sessions, almost no down ones: upside is measurable and
    # downside is not, and the payload has to say so per side.
    rng = np.random.default_rng(9)
    bench = np.abs(rng.normal(0.005, 0.002, 200))
    bench[:3] = -0.004                       # three down sessions only
    port = bench * 1.2

    out = m.capture(port, bench)
    assert out["down_sessions"] == 3, out
    assert out["down"] is None, out          # refused: too few
    assert out["up"] is not None, out
    assert abs(out["up"] - 120.0) < 1e-6, out


@check("higher moments are refused on short samples")
def _():
    """Skew and kurtosis are least stable exactly when they look most
    dramatic, so the sample size travels with them."""
    short = m.distribution(np.random.default_rng(1).normal(0, 0.01, 20))
    assert short["skewness"] is None, short
    assert short["code"] == "too_few_observations", short

    long = m.distribution(np.random.default_rng(1).normal(0, 0.01, 2000))
    assert long["code"] == "ok", long
    assert long["observations"] == 2000, long
    # A normal sample has excess kurtosis near zero; being far off would mean
    # the formula is not subtracting the 3.
    assert abs(long["excess_kurtosis"]) < 0.5, long["excess_kurtosis"]


@check("a spike shows up as fat tails, which is what catches bad data")
def _():
    """This is how the unadjusted-split problem was found: kurtosis of 105 on
    a four-stock portfolio is not risk, it is one impossible bar."""
    returns = np.random.default_rng(4).normal(0, 0.01, 500)
    returns[250] = -0.62                     # a 46% "fall" from a stock split
    out = m.distribution(returns)
    assert out["excess_kurtosis"] > 20, out["excess_kurtosis"]
    assert out["skewness"] < -2, out["skewness"]


@check("rolling stability reports the spread, not just the headline")
def _():
    """A Sharpe of 1.2 that ranged from -0.4 to 3.1 is a different claim from
    one that stayed near 1.2, and only the spread separates them."""
    rng = np.random.default_rng(6)
    calm = rng.normal(0.0008, 0.004, 200)
    wild = rng.normal(0.0008, 0.030, 200)
    joined = np.concatenate([calm, wild])

    out = m.rolling_stability(joined, window=60)
    assert out["available"] is True, out
    assert out["sharpe_spread"] > 0, out
    # The two halves differ in volatility by roughly 7x, which the rolling
    # range has to show rather than average away.
    assert out["volatility_max_pct"] / out["volatility_min_pct"] > 3, out


@check("a window longer than the sample is refused, not truncated")
def _():
    out = m.rolling_stability(np.random.default_rng(8).normal(0, 0.01, 30), window=60)
    assert out["available"] is False, out
    assert out["code"] == "window_longer_than_sample", out


@check("without a benchmark the relative metrics are absent, not zero")
def _():
    returns = np.random.default_rng(12).normal(0.0003, 0.01, 300)
    out = m.performance(returns, None, beta=None, max_drawdown=-0.1)
    assert out["benchmark"]["available"] is False, out["benchmark"]
    # And the absolute ones still work: no benchmark is not no answer.
    assert out["cagr_pct"] is not None
    assert out["sharpe"]["code"] == "ok", out["sharpe"]


def main() -> int:
    passed = failed = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as exc:
            print(f"  FAIL  {name}")
            print(f"          {exc}")
            failed += 1
        except Exception as exc:
            print(f"  ERROR {name}")
            print(f"          {type(exc).__name__}: {exc}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
