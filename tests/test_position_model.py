"""Position models: the linear model held to a recorded run, the contract model
held to hand-computed numbers.

Run:  .venv\\Scripts\\python.exe tests/test_position_model.py

Design: docs/superpowers/specs/2026-09-15-contract-position-model-design.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import make_linear_golden  # noqa: E402

GOLDEN = HERE / "fixtures" / "linear_golden.json"

CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


def close_to(actual: float, expected: float, tol: float = 1e-9) -> bool:
    return abs(actual - expected) <= tol * max(1.0, abs(expected))


def same(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return abs(a - b) <= 1e-12 * max(1.0, abs(b))
    return a == b


# --------------------------------------------------------------------------

@check("the golden run exercises liquidation and many trades")
def _():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    leveraged = golden["leverage_25_liquidates"]
    liquidations = sum(t["exit_reason"] == "liquidation" for t in leveraged["trades"])
    # Several liquidations, with the account still trading after them: one
    # liquidation that wipes the account tests only the first trade.
    assert leveraged["liquidated"] is True and liquidations >= 2, liquidations
    assert leveraged["ruined"] is False and len(leveraged["trades"]) > liquidations, leveraged["trades"][-1:]
    assert len(golden["no_costs"]["trades"]) >= 20, len(golden["no_costs"]["trades"])


@check("the linear engine reproduces the recorded run, trade for trade")
def _():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    now = make_linear_golden.record()
    for name, want in golden.items():
        got = now[name]
        assert len(got["trades"]) == len(want["trades"]), (name, len(got["trades"]), len(want["trades"]))
        assert got["liquidated"] == want["liquidated"] and got["ruined"] == want["ruined"], name
        assert len(got["equity"]) == len(want["equity"]), name
        for i, (a, b) in enumerate(zip(got["equity"], want["equity"])):
            assert same(a, b), (name, "equity", i, a, b)
        for i, (ta, tb) in enumerate(zip(got["trades"], want["trades"])):
            for key in tb:
                assert same(ta[key], tb[key]), (name, i, key, ta[key], tb[key])


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
