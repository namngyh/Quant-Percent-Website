"""Fixtures for tests/test_render.js.

Runs the real walk-forward and Monte Carlo code over a synthetic random walk
and writes the payloads to render_payloads.json, so the render test needs
neither a database nor a running server.
"""
import json, sys, os
sys.path.insert(0, os.path.abspath('.'))
import numpy as np, pandas as pd
from backend.optimizer.validation import walk_forward, monte_carlo
from backend.optimizer.grid import ParamRange
from backend.strategy.engine import BacktestConfig

def candles(n=4000, seed=4):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.standard_normal(n) * 0.01))
    return pd.DataFrame({"open_time": [i * 3_600_000 for i in range(n)],
        "open": close, "high": close * 1.002, "low": close * 0.998,
        "close": close, "volume": np.ones(n)})

df = candles()
ranges = [ParamRange("fast", 10, 30, 10), ParamRange("slow", 50, 100, 25)]
cfg = BacktestConfig(initial_capital=10_000)

out = {}
for name, mode, purge in (('wf_rolling', 'rolling', 0), ('wf_anchored', 'anchored', 200)):
    out[name] = walk_forward("example_ema_cross", df, "1h", ranges, config=cfg,
        metric="sharpe", train_bars=1200, test_bars=300,
        purge_bars=purge, fold_mode=mode)
    s = out[name]["summary"]
    print(f"{name:12} folds={len(out[name]['folds'])} "
          f"code={s['walk_forward_efficiency_code']:11} wfe={s['walk_forward_efficiency']} "
          f"is={s['is_mean_normalised_pct']:.3f} oos={s['oos_mean_normalised_pct']:.3f}")

from backend.optimizer.validation import _signals_for
from backend.strategy.engine import run_backtest
sig = _signals_for("example_ema_cross", df, {"fast": 20, "slow": 50})
bt = run_backtest(df, sig, cfg)
out['mc'] = monte_carlo([t.as_dict() for t in bt.trades], 10_000.0, simulations=2000)
print("mc           trades=%d actual_pct=%.2f ordering=%.2f" % (
    len(bt.trades), out['mc']['actual_percentile'], out['mc']['ordering_effect_pct']))

# The random-walk fixture loses money on both sides, so it only exercises the
# no_is_edge branch. The render harness needs all three states, so two copies of
# the rolling payload get their summaries adjusted to the other two.
import copy
for name, is_pct, oos_pct in (('wf_ratio', 2.0, 1.0), ('wf_inverted', 2.0, -1.0)):
    v2 = copy.deepcopy(out['wf_rolling'])
    s2 = v2['summary']
    s2['is_mean_normalised_pct'] = is_pct
    s2['oos_mean_normalised_pct'] = oos_pct
    s2['degradation_pct'] = is_pct - oos_pct
    s2['walk_forward_efficiency'] = oos_pct / is_pct
    s2['walk_forward_efficiency_code'] = 'ratio' if oos_pct > 0 else 'inverted'
    out[name] = v2

# The optimiser panel: a plateau grid and a random-walk grid, so the render
# test sees both a surviving and a deflated-away verdict.
from backend.optimizer.grid import optimize
out['opt'] = optimize("example_ema_cross", df, "1h",
    [ParamRange("fast", 5, 30, 5), ParamRange("slow", 40, 90, 10)],
    config=cfg, metric="sharpe")
rb, dfl = out['opt']['summary']['robustness'], out['opt']['summary']['deflated']
print("opt          combos=%d robust=%s deflated=%s" % (
    out['opt']['summary']['completed'], rb.get('code'), dfl.get('code')))

# The full backtest report, so every tab can be rendered.
from backend.analysis.report import build_report
out['report'] = build_report(bt, df, "1h")
# Print the shape, never the contents: the ml block carries bilingual prose and
# this console is cp1252, so dumping it raises UnicodeEncodeError and kills the
# script after it has written nothing. That failure is invisible if the output
# is being filtered — the stale fixture is still on disk and the next test run
# passes against it.
print("report       tabs ready; risk_tools=%s  ml=%s" % (
    sorted(out['report']['risk_tools']),
    'absent' if out['report']['ml'] is None else 'present'))

# A second report from a strategy that publishes a probability, because the ML
# tab is now shown only for those. A hand-written `ml` block in the test would
# be a fixture of my own expectations; this one comes out of the same code the
# app calls. The probability is a squashed EMA spread — not a real model, but
# a real array of the right shape, correlated with the signal the way a model's
# output would be.
import numpy as np
spread = (df["close"].ewm(span=20).mean() - df["close"].ewm(span=50).mean())
prob = 1.0 / (1.0 + np.exp(-spread.to_numpy() / max(spread.std(), 1e-9)))
out['report_ml'] = build_report(bt, df, "1h", probability=prob)
print("report_ml    ml=%s" % (
    out['report_ml']['ml'].get('error') or
    "accuracy=%.3f baseline=%.3f" % (out['report_ml']['ml']['accuracy'],
                                     out['report_ml']['ml']['baseline_accuracy'])))

# The portfolio performance tab. Two payloads, because the tab has two kinds
# of content that break differently: numbers, and refusals printed as reasons.
# A calm random portfolio against a benchmark exercises every ratio; a
# never-losing series with no benchmark exercises the refusal paths
# (no_downside_observed, no_drawdown_yet, no benchmark, too short to roll).
from backend.portfolio import metrics as pm
rng = np.random.default_rng(21)
bench_r = rng.normal(0.0003, 0.011, 400)
port_r = 1.1 * bench_r + rng.normal(0.0002, 0.005, 400)
eq = np.exp(np.cumsum(port_r))
mdd = float((eq / np.maximum.accumulate(eq) - 1).min())
out['portfolio'] = {"observations": 400, "beta": 1.1, "max_drawdown_pct": mdd * 100,
                    "performance": pm.performance(port_r, bench_r, 1.1, mdd)}
flat_up = np.full(40, np.log1p(0.001))
out['portfolio_refusals'] = {"observations": 40, "beta": None, "max_drawdown_pct": 0.0,
                             "performance": pm.performance(flat_up, None, None, 0.0)}
print("portfolio    sharpe=%s  refusals: sortino=%s calmar=%s rolling=%s" % (
    out['portfolio']['performance']['sharpe']['code'],
    out['portfolio_refusals']['performance']['sortino']['code'],
    out['portfolio_refusals']['performance']['calmar']['code'],
    out['portfolio_refusals']['performance']['rolling']['code']))

path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    'render_payloads.json')
with open(path, 'w', encoding='utf-8') as f:
    json.dump(out, f, default=float)
print("wrote", path)
