"""Quant Portfolio checks, plus the Telegram settings writer.

Run directly:  .venv\\Scripts\\python.exe tests/test_portfolio.py

No VPN needed: ``analyse`` takes its loader as an argument, so these run
against synthetic price histories built to have a known correlation structure.
That is the only way to check risk contribution at all — on real data there is
no independent answer to compare against.

The Telegram checks live here rather than in their own file because they are
about the same thing: a small piece of code that writes something the user
cannot easily inspect, where being subtly wrong is silent. A ``.env`` writer
that drops ``MARKET_DSN`` takes the Vietnam market data down and nothing says
why until the next query fails.
"""

from __future__ import annotations

import datetime as dt
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from backend.notify import telegram  # noqa: E402
from backend.i18n import plain  # noqa: E402
from backend.portfolio import analytics  # noqa: E402

# Narrative fields ship as {vi, en} pairs; assert on the Vietnamese, which is
# the language they were written and reviewed in.
vi = plain

CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


def make_loader(series: dict[str, np.ndarray]):
    """Turn return series into a ``{symbol: {date: close}}`` loader."""
    length = len(next(iter(series.values())))
    days = [dt.date(2025, 1, 1) + dt.timedelta(days=i) for i in range(length + 1)]

    def loader(symbols, lookback):
        out = {}
        for symbol in symbols:
            if symbol not in series:
                continue
            prices = 100 * np.exp(np.cumsum(np.concatenate([[0.0], series[symbol]])))
            kept = min(lookback, len(days))
            out[symbol] = {
                days[i]: float(prices[i]) for i in range(len(days) - kept, len(days))
            }
        return out
    return loader


def correlated(n=300, seed=1):
    """AAA and BBB move together; CCC does not. VNINDEX drives the common part."""
    rng = np.random.default_rng(seed)
    common = rng.standard_normal(n) * 0.012
    return {
        "AAA": common + rng.standard_normal(n) * 0.004,
        "BBB": common * 0.95 + rng.standard_normal(n) * 0.004,
        "CCC": rng.standard_normal(n) * 0.010,
        "VNINDEX": common * 0.8 + rng.standard_normal(n) * 0.003,
    }


def holdings(*pairs):
    return [
        {"symbol": s, "quantity": q, "cost_basis": c}
        for s, q, c in pairs
    ]


def equal_weight(series, symbols):
    """Holdings whose market values are equal, whatever the paths did.

    Equal *quantities* are not equal weights: the simulated price paths drift
    apart over 300 sessions, so a naive `1000 shares each` silently tests a
    portfolio with 21%/38%/41% weights. Every claim below about risk exceeding
    money share needs the money share pinned first, or it is not testing what
    it says it is.
    """
    loader = make_loader(series)
    closes = loader(list(symbols), 10_000)
    return [
        {
            "symbol": symbol,
            # Quantity that buys one unit of value at the last close.
            "quantity": 1_000_000 / closes[symbol][max(closes[symbol])],
            "cost_basis": None,
        }
        for symbol in symbols
    ]


# ---------------------------------------------------- Ledoit-Wolf

@check("shrinkage intensity stays inside [0, 1]")
def _():
    rng = np.random.default_rng(2)
    for n_obs, n_assets in ((80, 20), (300, 5), (1000, 3)):
        _, intensity = analytics.ledoit_wolf(rng.standard_normal((n_obs, n_assets)) * 0.01)
        assert 0.0 <= intensity <= 1.0, (n_obs, n_assets, intensity)


@check("shrinkage does not saturate at 1 and flatten every correlation")
def _():
    # This is the failure the rho term exists to prevent. Without it the
    # intensity pins to 1.0 on daily equity returns, every correlation collapses
    # onto the mean, and the matrix loses the structure the panel exists to find.
    series = correlated(250, seed=3)
    returns = np.column_stack([series["AAA"], series["BBB"], series["CCC"]])
    cov, intensity = analytics.ledoit_wolf(returns)
    assert intensity < 0.9, intensity

    std = np.sqrt(np.diag(cov))
    corr = cov / np.outer(std, std)
    # AAA/BBB were built to move together and CCC not to. That must survive.
    assert corr[0, 1] > 0.7, corr[0, 1]
    assert abs(corr[0, 2]) < 0.3, corr[0, 2]


@check("the shrunk matrix stays symmetric and positive semi-definite")
def _():
    rng = np.random.default_rng(4)
    # Fewer observations than assets: the sample covariance is singular here
    # and the shrunk one must not be.
    cov, _ = analytics.ledoit_wolf(rng.standard_normal((70, 25)) * 0.01)
    assert np.allclose(cov, cov.T), "not symmetric"
    assert float(np.linalg.eigvalsh(cov).min()) > -1e-12, np.linalg.eigvalsh(cov).min()


@check("a single asset returns its own variance rather than failing")
def _():
    returns = (np.random.default_rng(5).standard_normal(200) * 0.01).reshape(-1, 1)
    cov, intensity = analytics.ledoit_wolf(returns)
    assert cov.shape == (1, 1), cov.shape
    assert intensity == 0.0
    assert abs(float(cov[0, 0]) - float(returns.var(ddof=1))) < 1e-12


# ---------------------------------------------------- risk contribution

@check("risk contributions sum to 100%")
def _():
    result = analytics.analyse(
        holdings(("AAA", 1000, None), ("BBB", 1000, None), ("CCC", 2000, None)),
        0.0, 252, 63, make_loader(correlated()),
    )
    total = sum(p["risk_contribution_pct"] for p in result["positions"])
    assert abs(total - 100.0) < 1e-6, total


@check("a correlated name carries more risk than its share of the money")
def _():
    series = correlated()
    result = analytics.analyse(
        equal_weight(series, ["AAA", "BBB", "CCC"]),
        0.0, 252, 63, make_loader(series),
    )
    by_symbol = {p["symbol"]: p for p in result["positions"]}
    # Equal thirds of the money. AAA and BBB move together, so each amplifies
    # the other's risk; CCC is the diversifier and carries less risk than money.
    for symbol in ("AAA", "BBB", "CCC"):
        assert abs(by_symbol[symbol]["weight_pct"] - 100 / 3) < 0.5, by_symbol[symbol]
    assert by_symbol["AAA"]["risk_gap_pct"] > 0, by_symbol["AAA"]
    assert by_symbol["BBB"]["risk_gap_pct"] > 0, by_symbol["BBB"]
    assert by_symbol["CCC"]["risk_gap_pct"] < 0, by_symbol["CCC"]


@check("positions are sorted by risk, not by money")
def _():
    series = correlated()
    positions = equal_weight(series, ["AAA", "BBB", "CCC"])
    # Make the diversifier the largest position by money — but only modestly.
    # Pushed far enough (about 1.6x here) CCC dominates the portfolio variance
    # by sheer size and becomes the top risk row too, at which point the two
    # orderings agree again and the check proves nothing. 1.4x puts CCC at
    # ~41% of the money and ~29% of the risk, behind AAA on risk: the exact
    # disagreement this panel exists to surface.
    positions[2]["quantity"] *= 1.4
    result = analytics.analyse(positions, 0.0, 252, 63, make_loader(series))

    shares = [p["risk_contribution_pct"] for p in result["positions"]]
    assert shares == sorted(shares, reverse=True), shares

    largest_money = max(result["positions"], key=lambda p: p["weight_pct"])
    assert largest_money["symbol"] == "CCC", largest_money["symbol"]
    assert result["positions"][0]["symbol"] == "AAA", (
        "the top row follows money rather than risk: "
        f"{[(p['symbol'], p['weight_pct'], p['risk_contribution_pct']) for p in result['positions']]}"
    )


@check("identical uncorrelated holdings split risk evenly")
def _():
    rng = np.random.default_rng(6)
    series = {
        "AAA": rng.standard_normal(400) * 0.01,
        "BBB": rng.standard_normal(400) * 0.01,
        "VNINDEX": rng.standard_normal(400) * 0.01,
    }
    result = analytics.analyse(
        equal_weight(series, ["AAA", "BBB"]), 0.0, 400, 63, make_loader(series),
    )
    shares = [p["risk_contribution_pct"] for p in result["positions"]]
    # Same weight, same volatility, no correlation — so a near-even split. The
    # gap that remains is sampling noise in the two estimated variances.
    assert abs(shares[0] - shares[1]) < 10, shares


# ---------------------------------------------------- valuation

@check("prices are converted from thousands of dong to dong")
def _():
    # A close of 100 in the feed means 100 000 dong, so 1 000 shares is 100m.
    series = {"AAA": np.zeros(200), "VNINDEX": np.zeros(200)}
    series["AAA"][0] = 1e-9    # a hair of variance so the maths is defined
    series["VNINDEX"][0] = 1e-9
    result = analytics.analyse(
        holdings(("AAA", 1000, None)), 0.0, 252, 63, make_loader(series),
    )
    assert abs(result["invested_value"] - 100_000_000) < 1_000, result["invested_value"]


@check("profit is withheld entirely when any holding lacks a cost basis")
def _():
    loader = make_loader(correlated())
    with_all = analytics.analyse(
        holdings(("AAA", 1000, 90_000), ("BBB", 1000, 90_000)), 0.0, 252, 63, loader,
    )
    with_gap = analytics.analyse(
        holdings(("AAA", 1000, 90_000), ("BBB", 1000, None)), 0.0, 252, 63, loader,
    )
    assert with_all["profit"] is not None, with_all["profit"]
    # A partial total would be a smaller number presented as the whole answer.
    assert with_gap["profit"] is None, with_gap["profit"]
    assert with_gap["profit_pct"] is None


@check("cash is counted in total value but not in risk")
def _():
    loader = make_loader(correlated())
    positions = holdings(("AAA", 1000, None), ("CCC", 1000, None))
    without = analytics.analyse(positions, 0.0, 252, 63, loader)
    with_cash = analytics.analyse(positions, 500_000_000, 252, 63, loader)

    assert with_cash["total_value"] > without["total_value"]
    assert with_cash["cash_weight_pct"] > 0
    # Volatility is measured on the invested part only; cash would dilute it.
    assert abs(with_cash["volatility_pct"] - without["volatility_pct"]) < 1e-9, (
        with_cash["volatility_pct"], without["volatility_pct"],
    )


# ---------------------------------------------------- concentration

@check("effective bets fall below effective assets when names correlate")
def _():
    result = analytics.analyse(
        holdings(("AAA", 1000, None), ("BBB", 1000, None), ("CCC", 1000, None)),
        0.0, 252, 63, make_loader(correlated()),
    )
    c = result["concentration"]
    assert c["effective_bets"] < c["effective_assets"], c
    assert c["max_pair"] == ["AAA", "BBB"], c["max_pair"]
    assert c["max_pair_correlation"] > 0.7, c["max_pair_correlation"]


@check("effective assets is the inverse Herfindahl")
def _():
    result = analytics.analyse(
        holdings(("AAA", 1000, None), ("BBB", 1000, None), ("CCC", 1000, None)),
        0.0, 252, 63, make_loader(correlated()),
    )
    c = result["concentration"]
    assert abs(c["effective_assets"] - 1.0 / c["herfindahl"]) < 1e-9, c


# ---------------------------------------------------- forward simulation

@check("block sampling fattens the tail that clustering fattens")
def _():
    # Block bootstrap versus independent draws, on a series whose bad days
    # cluster: quiet first half, stormy second half.
    #
    # The effect is in the TAIL, and only in the tail. Blocks make the typical
    # path *less* extreme, because a path built from ~8 long blocks often sits
    # entirely inside the quiet regime — so the median drawdown is actually
    # shallower under blocks (-15.1% against -16.1% here). What clustering does
    # is make the bad case worse: consecutive storm days compound, and the
    # expected shortfall and the deepest drawdown bucket both move out.
    #
    # Asserting on the median would therefore fail while the sampler is working
    # correctly, which is what the first draft of this check did.
    rng = np.random.default_rng(7)
    n = 500
    clustered = np.concatenate([
        rng.standard_normal(n // 2) * 0.004,
        rng.standard_normal(n // 2) * 0.025,
    ])
    shuffled = rng.permutation(clustered)

    blocked = analytics.forward_risk(clustered, 63, paths=8000)
    independent = analytics.forward_risk(shuffled, 63, paths=8000)
    assert blocked["available"] and independent["available"]

    # Expected shortfall of the terminal return: deeper when storms stay together.
    assert blocked["cvar_95_pct"] < independent["cvar_95_pct"], (
        blocked["cvar_95_pct"], independent["cvar_95_pct"],
    )
    # And the deepest published drawdown bucket is more likely.
    deepest_blocked = blocked["drawdown_probabilities"][-1]["probability_pct"]
    deepest_independent = independent["drawdown_probabilities"][-1]["probability_pct"]
    assert deepest_blocked > deepest_independent, (
        deepest_blocked, deepest_independent,
    )


@check("the block length follows the n^(1/3) rule and is reported")
def _():
    returns = np.random.default_rng(22).standard_normal(1000) * 0.01
    forward = analytics.forward_risk(returns, 63, paths=500)
    assert forward["block_length"] == 10.0, forward["block_length"]
    assert vi(forward["method"]).startswith("bootstrap khối"), forward["method"]
    assert forward["caveat"], forward


@check("drawdown probabilities fall as the threshold deepens")
def _():
    returns = np.random.default_rng(8).standard_normal(300) * 0.015
    forward = analytics.forward_risk(returns, 63, paths=2000)
    probabilities = [b["probability_pct"] for b in forward["drawdown_probabilities"]]
    assert probabilities == sorted(probabilities, reverse=True), probabilities
    assert all(0 <= p <= 100 for p in probabilities), probabilities


@check("a longer horizon cannot lower the chance of a given drawdown")
def _():
    returns = np.random.default_rng(9).standard_normal(400) * 0.012
    short = analytics.forward_risk(returns, 21, paths=4000)
    long = analytics.forward_risk(returns, 252, paths=4000)
    for a, b in zip(short["drawdown_probabilities"], long["drawdown_probabilities"]):
        assert b["probability_pct"] >= a["probability_pct"] - 2.0, (a, b)


@check("the forward block says why it is unavailable on a short history")
def _():
    forward = analytics.forward_risk(np.random.default_rng(10).standard_normal(20), 63)
    assert forward["available"] is False, forward
    assert forward["reason"], forward


@check("VaR is at least as deep as the 5th percentile of terminal returns")
def _():
    returns = np.random.default_rng(11).standard_normal(300) * 0.012
    forward = analytics.forward_risk(returns, 63, paths=3000)
    assert abs(forward["var_95_pct"] - forward["p05_pct"]) < 1e-9, forward
    assert forward["cvar_95_pct"] <= forward["var_95_pct"], forward


# ---------------------------------------------------- refusals

@check("a symbol with too little history is reported, not silently dropped")
def _():
    series = correlated()
    series["DDD"] = series["CCC"][:30]     # only 30 sessions
    loader = make_loader({k: v for k, v in series.items() if k != "DDD"})

    def partial(symbols, lookback):
        out = loader(symbols, lookback)
        if "DDD" in symbols:
            days = sorted(out["AAA"])[-30:]
            out["DDD"] = {d: 50.0 + i for i, d in enumerate(days)}
        return out

    result = analytics.analyse(
        holdings(("AAA", 1000, None), ("BBB", 1000, None), ("DDD", 1000, None)),
        0.0, 252, 63, partial,
    )
    assert result["unpriced"] == ["DDD"], result["unpriced"]
    assert {p["symbol"] for p in result["positions"]} == {"AAA", "BBB"}
    # And it has to be said out loud, not just left in a field.
    assert any("DDD" in vi(note) for note in result["notes"]), result["notes"]


@check("every portfolio note carries both languages")
def _():
    result = analytics.analyse(
        holdings(("AAA", 1000, None), ("CCC", 1000, None)),
        0.0, 252, 63, make_loader(correlated()),
    )
    for note in result["notes"]:
        assert isinstance(note, dict), f"note is not a pair: {note}"
        assert note.get("vi") and note.get("en"), note
        assert note["vi"] != note["en"], note
    forward = result["forward"]
    assert forward["caveat"].get("en"), forward["caveat"]


@check("an empty portfolio is refused with a reason")
def _():
    try:
        analytics.analyse([], 0.0, 252, 63, make_loader(correlated()))
    except analytics.PortfolioError as exc:
        assert "Chưa nhập mã nào" in str(exc), exc
    else:
        raise AssertionError("expected a PortfolioError")


@check("a portfolio with no usable history is refused, not approximated")
def _():
    def empty(symbols, lookback):
        return {}
    try:
        analytics.analyse(holdings(("AAA", 100, None)), 0.0, 252, 63, empty)
    except analytics.PortfolioError as exc:
        assert "lịch sử giá" in str(exc), exc
    else:
        raise AssertionError("expected a PortfolioError")


@check("more than fifty holdings is refused")
def _():
    many = holdings(*[(f"S{i:03d}", 100, None) for i in range(51)])
    try:
        analytics.analyse(many, 0.0, 252, 63, make_loader(correlated()))
    except analytics.PortfolioError as exc:
        assert "50" in str(exc), exc
    else:
        raise AssertionError("expected a PortfolioError")


@check("beta is None rather than 0 when the benchmark is missing")
def _():
    series = correlated()
    del series["VNINDEX"]
    result = analytics.analyse(
        holdings(("AAA", 1000, None), ("BBB", 1000, None)),
        0.0, 252, 63, make_loader(series),
    )
    assert result["beta"] is None, result["beta"]
    assert all(p["beta"] is None for p in result["positions"]), result["positions"]


@check("the missing-sector limitation is stated in every result")
def _():
    result = analytics.analyse(
        holdings(("AAA", 1000, None), ("CCC", 1000, None)),
        0.0, 252, 63, make_loader(correlated()),
    )
    assert any("ngành" in vi(note) for note in result["notes"]), result["notes"]
    assert "sector_weights" not in result["concentration"], result["concentration"]


# ---------------------------------------------------- Telegram settings

def env_sandbox():
    """A temporary project root holding a realistic .env."""
    root = Path(tempfile.mkdtemp())
    (root / ".env").write_text(
        "# comment stays\n"
        "MARKET_DSN=postgresql://qp_remote:secret@100.84.96.26:5432/market\n"
        "\n"
        "# --- Telegram ---\n"
        "TELEGRAM_BOT_TOKEN=\n"
        "TELEGRAM_CHAT_ID=\n"
        "OTHER=keepme\n",
        encoding="utf-8",
    )
    return root


@check("saving a token leaves MARKET_DSN and every comment untouched")
def _():
    root = env_sandbox()
    original = telegram.PROJECT_ROOT
    try:
        telegram.PROJECT_ROOT = root
        telegram.save_credentials("111:AAAtoken", "999")
        text = (root / ".env").read_text(encoding="utf-8")
    finally:
        telegram.PROJECT_ROOT = original

    assert "MARKET_DSN=postgresql://qp_remote:secret@100.84.96.26:5432/market" in text
    assert "# comment stays" in text
    assert "OTHER=keepme" in text
    assert "TELEGRAM_BOT_TOKEN=111:AAAtoken" in text
    assert "TELEGRAM_CHAT_ID=999" in text


@check("saving twice does not leave two answers to the same key")
def _():
    root = env_sandbox()
    original = telegram.PROJECT_ROOT
    try:
        telegram.PROJECT_ROOT = root
        telegram.save_credentials("111:AAA", "1")
        telegram.save_credentials("222:BBB", "2")
        lines = (root / ".env").read_text(encoding="utf-8").splitlines()
    finally:
        telegram.PROJECT_ROOT = original

    tokens = [line for line in lines if line.startswith("TELEGRAM_BOT_TOKEN=")]
    assert tokens == ["TELEGRAM_BOT_TOKEN=222:BBB"], tokens


@check("credentials are trimmed, so a pasted trailing space does not break the token")
def _():
    root = env_sandbox()
    original = telegram.PROJECT_ROOT
    try:
        telegram.PROJECT_ROOT = root
        telegram.save_credentials("  111:AAA  ", " 42 ")
        text = (root / ".env").read_text(encoding="utf-8")
    finally:
        telegram.PROJECT_ROOT = original
    assert "TELEGRAM_BOT_TOKEN=111:AAA\n" in text, text
    assert "TELEGRAM_CHAT_ID=42\n" in text, text


@check("clearing blanks the keys and keeps the rest of the file")
def _():
    root = env_sandbox()
    original = telegram.PROJECT_ROOT
    try:
        telegram.PROJECT_ROOT = root
        telegram.save_credentials("111:AAA", "1")
        telegram.clear_credentials()
        text = (root / ".env").read_text(encoding="utf-8")
    finally:
        telegram.PROJECT_ROOT = original

    assert "TELEGRAM_BOT_TOKEN=\n" in text, text
    assert "MARKET_DSN=" in text, text


@check("the write is atomic and leaves no temporary file behind")
def _():
    root = env_sandbox()
    original = telegram.PROJECT_ROOT
    try:
        telegram.PROJECT_ROOT = root
        telegram.save_credentials("111:AAA", "1")
    finally:
        telegram.PROJECT_ROOT = original
    assert sorted(p.name for p in root.iterdir()) == [".env"], list(root.iterdir())


@check("a masked token shows the bot id but not the secret")
def _():
    masked = telegram.mask("123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw")
    assert masked.startswith("123456789:"), masked
    assert "AAHdqTcv" not in masked, masked
    assert masked.endswith("Dsaw"), masked
    assert telegram.mask(None) is None
    assert telegram.mask("") is None


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
