"""Statistical tests, checked against series whose answer is known in advance.

Run directly:  .venv\\Scripts\\python.exe tests/test_stats.py

The point of these checks is not that the functions return numbers. It is that
they return the RIGHT numbers on data built to have a specific property, and —
just as important — that they *fail to reject* on data built to have none. A
test suite that only feeds real market data cannot tell a working test from one
that always says "significant".

Three synthetic series recur:

* ``random_walk`` — independent normal returns. Every randomness test must fail
  to reject on this. An estimator that finds structure here is broken, and the
  uncorrected R/S Hurst estimator genuinely does.
* ``mean_reverting`` — AR(1) with a negative coefficient. Variance ratio must
  come back below 1 and reject.
* ``trending`` — AR(1) with a positive coefficient. Variance ratio above 1.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backend.analysis import stats  # noqa: E402
from backend.i18n import plain  # noqa: E402


# Narrative fields are {vi, en} pairs. The checks below assert on the
# Vietnamese, which is the language the wording was written and reviewed in;
# "every narrative field carries both languages" is what guards the English.
vi = plain


def random_walk(n: int = 3000, seed: int = 1) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal(n) * 0.01


def ar1(n: int, phi: float, seed: int = 2) -> np.ndarray:
    rng = np.random.default_rng(seed)
    shock = rng.standard_normal(n) * 0.01
    out = np.zeros(n)
    for i in range(1, n):
        out[i] = phi * out[i - 1] + shock[i]
    return out


def frame(returns: np.ndarray) -> pd.DataFrame:
    close = 100 * np.exp(np.cumsum(np.concatenate([[0.0], returns])))
    return pd.DataFrame({"close": close})


CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


# ---------------------------------------------------- multiple testing

@check("Benjamini-Hochberg leaves a single p-value untouched")
def _():
    assert stats.benjamini_hochberg([0.03]) == [0.03]


@check("Benjamini-Hochberg raises p-values and stays monotone")
def _():
    raw = [0.001, 0.008, 0.039, 0.041, 0.9]
    adjusted = stats.benjamini_hochberg(raw)
    assert all(a >= r - 1e-12 for a, r in zip(adjusted, raw)), adjusted
    assert adjusted == sorted(adjusted), f"not monotone: {adjusted}"
    # Smallest of five: 0.001 * 5/1 = 0.005.
    assert abs(adjusted[0] - 0.005) < 1e-12, adjusted[0]


@check("Benjamini-Hochberg never reports a p-value above 1")
def _():
    assert all(p <= 1.0 for p in stats.benjamini_hochberg([0.5, 0.6, 0.7, 0.9]))


@check("adjusted p-values are attached to every test in a family")
def _():
    result = stats.analyse_series(frame(random_walk()))
    family = result["multiple_testing"]
    assert family["n_tests"] >= 7, family
    assert family["n_significant_adjusted"] <= family["n_significant_raw"], family
    assert result["autocorrelation"]["ljung_box"]["p_adjusted"] is not None


# ---------------------------------------------------- distribution

@check("skew and kurtosis carry standard errors that shrink with n")
def _():
    small = stats.moments(random_walk(200))
    large = stats.moments(random_walk(5000))
    assert small["skew_se"] > large["skew_se"], (small["skew_se"], large["skew_se"])
    # Cramér's SE for skew at n=200 is about 0.171.
    assert abs(small["skew_se"] - 0.1714) < 0.002, small["skew_se"]


@check("normal returns are not flagged as significantly skewed")
def _():
    m = stats.moments(random_walk(5000, seed=11))
    assert not m["skew_significant"], m["skew_z"]
    assert not m["kurtosis_significant"], m["kurtosis_z"]


@check("a fat-tailed series is flagged as non-normal by both tests")
def _():
    heavy = np.random.default_rng(5).standard_t(3, 3000) * 0.005
    result = stats.normality(heavy)
    assert result["jarque_bera"]["reject"], result["jarque_bera"]["p_value"]
    assert result["dagostino"]["reject"], result["dagostino"]["p_value"]


@check("tail risk reports how many observations back each estimate")
def _():
    tail = stats.tail_risk(random_walk(2000))
    # 1% of 2000 is 20 observations, which the module must call unreliable.
    assert tail["tail_n_99"] <= 25, tail["tail_n_99"]
    assert tail["tail_reliable_99"] is False, tail
    assert tail["tail_n_95"] >= 90, tail["tail_n_95"]
    assert tail["tail_reliable_95"] is True


@check("VaR is more negative at 99% than at 95%")
def _():
    tail = stats.tail_risk(random_walk(4000))
    assert tail["var_99_pct"] < tail["var_95_pct"], tail
    assert tail["cvar_95_pct"] <= tail["var_95_pct"], tail


@check("the VaR confidence interval brackets the point estimate")
def _():
    tail = stats.tail_risk(random_walk(3000))
    assert tail["var_95_ci_low_pct"] <= tail["var_95_pct"] <= tail["var_95_ci_high_pct"], tail


# ---------------------------------------------------- Hurst

@check("corrected Hurst does not claim structure in a random walk")
def _():
    # This is the check the old estimator failed: sqrt-of-std on raw prices
    # returns roughly 0.6 here and the panel reported "xu hướng".
    result = stats.hurst(random_walk(4000, seed=7))
    assert result["p_value"] >= 0.05, (result["statistic"], result["p_value"])
    assert vi(result["reading"]).startswith("không phân biệt"), result["reading"]


@check("the Anis-Lloyd expectation grows with window size")
def _():
    small = stats._anis_lloyd_expected(32)
    large = stats._anis_lloyd_expected(512)
    assert 0 < small < large, (small, large)
    # E[R/S] for an independent series scales as roughly sqrt(n); 512/32 = 16,
    # so the ratio should land near 4.
    assert 3.0 < large / small < 5.0, large / small


@check("the Hurst permutation null centres on 0.5")
def _():
    result = stats.hurst(random_walk(3000, seed=13))
    assert abs(result["null_mean"] - 0.5) < 0.05, result["null_mean"]


@check("Hurst reports the reason when the series is too short")
def _():
    result = stats.hurst(random_walk(100))
    assert "unavailable" in result, result
    assert "256" in result["unavailable"], result["unavailable"]


# ---------------------------------------------------- variance ratio

@check("variance ratio does not reject a random walk")
def _():
    result = stats.variance_ratio(random_walk(4000, seed=3))
    assert result["p_value"] >= 0.05, (result["statistic"], result["p_value"])
    for period in result["per_period"]:
        assert abs(period["variance_ratio"] - 1.0) < 0.15, period


@check("variance ratio falls below 1 on a mean-reverting series")
def _():
    result = stats.variance_ratio(ar1(4000, -0.3))
    assert result["reject"], result["p_value"]
    for period in result["per_period"]:
        assert period["variance_ratio"] < 1.0, period
        assert vi(period["reading"]) == "hồi quy trung bình", period


@check("variance ratio rises above 1 on a trending series")
def _():
    result = stats.variance_ratio(ar1(4000, 0.3))
    assert result["reject"], result["p_value"]
    for period in result["per_period"]:
        assert period["variance_ratio"] > 1.0, period


def _z_ratios(returns: np.ndarray) -> list[float]:
    """|z homoskedastic| / |z robust| at each horizon."""
    result = stats.variance_ratio(returns)
    out = []
    for period in result["per_period"]:
        assert period["z_homoskedastic"] is not None, period
        assert period["z_heteroskedastic"] is not None, period
        out.append(abs(period["z_homoskedastic"] / period["z_heteroskedastic"]))
    return out


@check("the two z statistics agree when variance really is constant")
def _():
    # Theory says they coincide under homoskedasticity. If they did not, the
    # robust correction would be a constant fudge rather than a correction.
    for value in _z_ratios(random_walk(4000, seed=3)):
        assert abs(value - 1.0) < 0.05, value


@check("the robust z is materially smaller when variance changes over time")
def _():
    # A series whose volatility quadruples halfway through. The homoskedastic
    # statistic does not know that and is overconfident; the robust one is not.
    #
    # This is the bug the old implementation shipped: it computed the
    # homoskedastic statistic and labelled it heteroskedastic. On real BTC 1h
    # data that mislabel turned z = -2.35 (reject the random walk) into the
    # reported answer, when the honest robust figure was z = -1.32 (do not
    # reject) — an entirely different conclusion about whether the market has
    # exploitable mean reversion.
    rng = np.random.default_rng(21)
    n = 4000
    scale = np.concatenate([np.full(n // 2, 0.005), np.full(n // 2, 0.02)])
    for value in _z_ratios(rng.standard_normal(n) * scale):
        assert value > 1.15, f"robust z is not discounting the changing variance: {value}"


@check("the Chow-Denning threshold is stricter than a single-test 1.96")
def _():
    result = stats.variance_ratio(random_walk(4000))
    assert result["critical_value"] > 1.96, result["critical_value"]
    assert result["n_periods"] == 4, result


# ---------------------------------------------------- stationarity, ARCH

@check("ADF rejects a unit root in returns but not in prices")
def _():
    returns = random_walk(2000)
    result = stats.stationarity(
        100 * np.exp(np.cumsum(returns)), returns,
    )
    assert result["adf_return"]["p_value"] < 0.05, result["adf_return"]["p_value"]
    assert result["adf_price"]["p_value"] > 0.05, result["adf_price"]["p_value"]


@check("ADF and KPSS are read together into one verdict")
def _():
    returns = random_walk(2000)
    result = stats.stationarity(100 * np.exp(np.cumsum(returns)), returns)
    assert "verdict" in result, result.keys()
    assert "kpss_return" in result
    assert vi(result["kpss_return"]["null"]).startswith("Chuỗi lợi suất dừng")


@check("ARCH-LM finds volatility clustering and Ljung-Box does not confuse it for a trend")
def _():
    # GARCH-like: variance follows the previous squared shock, but the sign of
    # each return is independent — so there is clustering and no direction.
    rng = np.random.default_rng(9)
    n = 3000
    out = np.zeros(n)
    variance = 1e-4
    for i in range(n):
        variance = 2e-5 + 0.1 * out[i - 1] ** 2 + 0.85 * variance
        out[i] = rng.standard_normal() * np.sqrt(variance)

    result = stats.autocorrelation(out)
    assert result["arch_lm"]["reject"], result["arch_lm"]["p_value"]
    assert not result["ljung_box"]["reject"], result["ljung_box"]["p_value"]


# ---------------------------------------------------- inference

@check("a coin-flip strategy is not called significant")
def _():
    trades = np.random.default_rng(4).standard_normal(120) * 0.02
    result = stats.inference(trades)
    assert not result["t_test"]["reject"], result["t_test"]["p_value"]
    assert not result["sign_permutation"]["reject"], result["sign_permutation"]["p_value"]


@check("a genuine edge is found by all three tests")
def _():
    trades = np.random.default_rng(6).standard_normal(400) * 0.01 + 0.006
    result = stats.inference(trades)
    assert result["t_test"]["reject"], result["t_test"]["p_value"]
    assert result["wilcoxon"]["reject"], result["wilcoxon"]["p_value"]
    assert result["sign_permutation"]["reject"], result["sign_permutation"]["p_value"]
    assert result["bootstrap_mean"]["excludes_zero"], result["bootstrap_mean"]


@check("the permutation p-value is never exactly zero")
def _():
    trades = np.full(60, 0.05)   # every trade wins by the same amount
    result = stats.inference(trades)
    assert result["sign_permutation"]["p_value"] > 0, result["sign_permutation"]


@check("too few trades is reported as such, with power, not as a null result")
def _():
    trades = np.random.default_rng(8).standard_normal(15) * 0.01 + 0.002
    result = stats.inference(trades)
    power = result["power"]
    assert power["adequate"] is False, power
    assert power["n_required_for_80pct"] > 15, power
    reading = vi(power["reading"])
    assert "chưa đủ" in reading or "KHÔNG chứng minh" in reading, power


@check("inference refuses to run on fewer than eight trades")
def _():
    result = stats.inference(np.array([0.01, -0.02, 0.03]))
    assert "error" in result, result


@check("the bootstrap interval brackets the observed mean")
def _():
    sample = np.random.default_rng(12).standard_normal(200) * 0.01 + 0.003
    result = stats._bootstrap_ci(sample, lambda x: float(np.mean(x)))
    assert result["ci_low"] < result["observed"] < result["ci_high"], result


# ---------------------------------------------------- Sharpe deflation

@check("deflated Sharpe is never above the undeflated one")
def _():
    returns = np.random.default_rng(14).standard_normal(2000) * 0.01 + 0.0004
    single = stats.sharpe_tests(returns, 8760, n_trials=1)
    swept = stats.sharpe_tests(returns, 8760, n_trials=2000)
    assert single["deflated_sharpe_ratio"] == single["psr"], single
    assert swept["deflated_sharpe_ratio"] < swept["psr"], swept
    assert swept["deflation_threshold_sharpe"] > 0, swept


@check("a Sharpe that survives one trial can fail after two thousand")
def _():
    # The whole reason the deflated ratio exists: a sweep's winner has to clear
    # the bar that the sweep itself raises.
    returns = np.random.default_rng(15).standard_normal(1500) * 0.01 + 0.0006
    single = stats.sharpe_tests(returns, 8760, n_trials=1)
    swept = stats.sharpe_tests(returns, 8760, n_trials=5000)
    assert single["psr_significant"], single["psr"]
    assert not swept["dsr_significant"], swept["deflated_sharpe_ratio"]


@check("minimum track record length exceeds n when the history is too short")
def _():
    returns = np.random.default_rng(16).standard_normal(200) * 0.01 + 0.0002
    result = stats.sharpe_tests(returns, 8760)
    assert result["min_track_record_length"] > result["n_observations"], result
    assert result["sufficient_history"] is False


# ---------------------------------------------------- assembly

@check("every test in a series analysis names its null and its assumptions")
def _():
    result = stats.analyse_series(frame(random_walk(2000)))
    tests = [
        result["autocorrelation"]["ljung_box"],
        result["autocorrelation"]["arch_lm"],
        result["stationarity"]["adf_price"],
        result["stationarity"]["adf_return"],
        result["stationarity"]["kpss_return"],
        result["normality"]["jarque_bera"],
        result["normality"]["dagostino"],
        result["variance_ratio"],
        result["hurst"],
    ]
    for test in tests:
        for field in ("name", "null", "alternative", "conclusion", "assumptions"):
            assert test.get(field), f"{test.get('name')} is missing {field}"


@check("every narrative field carries both languages")
def _():
    # The whole reason for the {vi, en} shape is that a translation cannot go
    # missing silently — an English reader would just see Vietnamese, which
    # reads as a rendering bug rather than an untranslated string.
    result = stats.analyse_series(frame(random_walk(2000, seed=31)))
    tests = [
        result["autocorrelation"]["ljung_box"],
        result["autocorrelation"]["arch_lm"],
        result["stationarity"]["adf_price"],
        result["stationarity"]["adf_return"],
        result["stationarity"]["kpss_return"],
        result["normality"]["jarque_bera"],
        result["normality"]["dagostino"],
        result["variance_ratio"],
        result["hurst"],
    ]
    for test in tests:
        # A name that carries a Vietnamese phrase needs a pair too; a name that
        # is only a proper noun ("Jarque-Bera") reads the same either way.
        name = test["name"]
        if isinstance(name, dict):
            assert name.get("vi") and name.get("en"), name

        for field in ("null", "alternative", "conclusion", "assumptions"):
            value = test[field]
            assert isinstance(value, dict), f"{test['name']}.{field} is not a pair"
            assert value.get("vi"), f"{test['name']}.{field} has no Vietnamese"
            assert value.get("en"), f"{test['name']}.{field} has no English"
            assert value["vi"] != value["en"], (
                f"{test['name']}.{field} is identical in both languages"
            )

    verdict = result["verdict"]
    for field in ("headline", "detail"):
        assert verdict[field].get("en"), f"verdict.{field} has no English"
    for note in verdict["notes"]:
        assert note.get("en"), "a verdict note has no English"


@check("verdicts carry a stable code, not just prose")
def _():
    # The statistics panel picks its colour from this code. It used to match on
    # the Vietnamese headline, which broke silently the moment that headline
    # became a {vi, en} pair — the whole panel threw and rendered nothing. A
    # code that is independent of wording is what makes that impossible.
    walk = stats.analyse_series(frame(random_walk(3000, seed=41)))
    assert walk["verdict"]["code"] in {"structured", "random"}, walk["verdict"]
    assert walk["verdict"]["code"] == "random", walk["verdict"]

    reverting = stats.analyse_series(frame(ar1(3000, -0.3, seed=42)))
    assert reverting["verdict"]["code"] == "structured", reverting["verdict"]

    trades = [{"pnl": v} for v in np.random.default_rng(43).normal(5, 200, 20)]
    strategy = stats.analyse_strategy(trades, 10_000.0)
    assert strategy["verdict"]["code"] in {
        "robust", "deflated_away", "underpowered", "no_edge",
    }, strategy["verdict"]

    # The code must never itself be a translated string, or it is no better
    # than matching on the headline.
    assert isinstance(walk["verdict"]["code"], str)
    assert isinstance(strategy["verdict"]["code"], str)


@check("a random walk gets the random-walk verdict")
def _():
    result = stats.analyse_series(frame(random_walk(4000, seed=17)))
    assert vi(result["verdict"]["headline"]).startswith("Không phân biệt"), \
        result["verdict"]


@check("a mean-reverting series gets the structure verdict")
def _():
    result = stats.analyse_series(frame(ar1(4000, -0.3, seed=18)))
    assert vi(result["verdict"]["headline"]).startswith("Có cấu trúc"), \
        result["verdict"]


@check("strategy analysis no longer produces a Bayesian block")
def _():
    trades = [{"pnl": v} for v in np.random.default_rng(19).normal(30, 200, 80)]
    result = stats.analyse_strategy(trades, 10_000.0)
    assert "bayesian" not in result, sorted(result)
    assert not any("bayes" in str(k).lower() for k in result), sorted(result)


@check("strategy analysis passes the trial count through to the deflated Sharpe")
def _():
    rng = np.random.default_rng(20)
    trades = [{"pnl": v} for v in rng.normal(40, 180, 100)]
    bars = rng.standard_normal(2000) * 0.01 + 0.0005
    swept = stats.analyse_strategy(
        trades, 10_000.0, bar_returns=bars, periods_per_year=8760, n_trials=3000,
    )
    assert swept["sharpe"]["n_trials"] == 3000, swept["sharpe"]
    assert swept["sharpe"]["deflated_sharpe_ratio"] < swept["sharpe"]["psr"]


@check("an empty trade list is reported, not divided by zero")
def _():
    assert "error" in stats.analyse_strategy([], 10_000.0)


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
