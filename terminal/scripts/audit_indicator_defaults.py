"""Compare each indicator computed with our parameter defaults against the
library's own, and report where ours are measurably worse.

The generic PARAM_DEFAULTS table maps a parameter *name* to a value, but the
same name means different things to different indicators — `scalar` is "scale
to 0-100" for RSI and "band width" for Keltner, `na` is a count for one
indicator and a smoothing coefficient below 1 for Holt-Winters. Where ours
produces fewer usable values, the default is wrong for that indicator.
"""

import json
import sys
import urllib.request
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, r"D:\Hoai Nam Ng\Project\QP-TRACKING")

import numpy as np
import pandas as pd
import pandas_ta_classic as pta

from backend.indicators.builtin import build_builtin_specs

d = json.load(
    urllib.request.urlopen(
        "http://127.0.0.1:8000/api/candles?symbol=BTCUSDT&timeframe=1h&limit=600"
    )
)
candles = pd.DataFrame(d["candles"])
frame = pd.DataFrame(
    {
        "open": candles["open"], "high": candles["high"],
        "low": candles["low"], "close": candles["close"],
        "volume": [float(v["value"]) for v in d["volumes"]],
    }
)
frame.index = pd.to_datetime(candles["time"] * 1000, unit="ms", utc=True)

PRICE = {"open", "open_", "high", "low", "close", "volume"}


def usable(result) -> int:
    """How many finite numbers the result contains."""
    if result is None:
        return 0
    if isinstance(result, (tuple, list)):
        result = next((r for r in result if isinstance(r, (pd.Series, pd.DataFrame))), None)
        if result is None:
            return 0
    if isinstance(result, pd.Series):
        result = result.to_frame()
    if not isinstance(result, pd.DataFrame):
        return 0
    total = 0
    for column in result.columns:
        values = pd.to_numeric(result[column], errors="coerce").to_numpy(dtype="float64")
        total += int(np.isfinite(values).sum())
    return total


specs = build_builtin_specs()
worse = []

for iid, spec in specs.items():
    fn = getattr(pta, iid, None)
    if fn is None:
        continue

    import inspect

    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        continue

    price_args = {}
    for p in sig.parameters.values():
        if p.name in PRICE:
            column = "open" if p.name == "open_" else p.name
            if column in frame.columns:
                price_args[p.name] = frame[column]
    if not price_args:
        continue

    # What the platform actually sends, after overrides and suppressions —
    # reading the generic table instead would test something we do not do.
    ours = spec.resolve_params(None)
    if not ours:
        continue

    try:
        theirs_n = usable(fn(**price_args))
    except Exception:
        continue
    try:
        ours_n = usable(fn(**price_args, **ours))
    except Exception:
        ours_n = 0

    # A meaningful shortfall, not a one-bar difference from a longer window.
    if theirs_n > 0 and ours_n < theirs_n * 0.75:
        worse.append((iid, ours_n, theirs_n, ours))

print(f"Chi bao ma tham so mac dinh CUA MINH cho ket qua kem hon thu vien: {len(worse)}\n")
for iid, ours_n, theirs_n, params in sorted(worse, key=lambda r: r[1] / max(r[2], 1)):
    pct = ours_n / theirs_n * 100
    print(f"  {iid:<14} {ours_n:>5}/{theirs_n:<5} gia tri ({pct:>5.1f}%)   tham so minh truyen: {params}")
