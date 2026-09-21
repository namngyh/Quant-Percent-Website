"""The team's own model output, read honestly.

Four `api` views carry a forecasting model, its history, a correlation network
and the ingestion log. The checks below fix the three things that would
otherwise be reported wrongly: a horizon counted in calendar days instead of
sessions, an accuracy claim built on a column that is empty, and a socket-drop
log presented as missing data.

Offline throughout — the database is replaced with recorded shapes — plus a
live section that runs only when the VPN is up.

Run:  .venv\\Scripts\\python.exe tests/test_team_models.py
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.data import market_vn, team_models  # noqa: E402

CHECKS = []
LIVE_CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


def live(name):
    def wrap(fn):
        LIVE_CHECKS.append((name, fn))
        return fn
    return wrap


@contextmanager
def _answers(handler):
    """Swap `market_vn.query` for one that answers by SQL fragment."""
    original = market_vn.query
    market_vn.query = handler
    try:
        yield
    finally:
        market_vn.query = original


def _utc(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 8, 0, tzinfo=timezone.utc)


# Twelve consecutive sessions, so a 5-session horizon has somewhere to land.
SESSIONS = [date(2026, 8, 3) + timedelta(days=i) for i in range(12)]
CLOSES = [(day, 1000.0 + 10 * i) for i, day in enumerate(SESSIONS)]


# ------------------------------------------------------------------ scoring

@check("a horizon is counted in sessions, not in calendar days")
def _():
    # Forecast made on session 0 for 5 sessions out: the close that matters is
    # session 5 (1050), not the close five calendar days later — which here is
    # the same row only because this fixture has no weekend, so the fixture
    # below adds one to make the difference real.
    weekend = [date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5), date(2026, 8, 6),
               date(2026, 8, 7), date(2026, 8, 10), date(2026, 8, 11)]
    closes = [(day, 100.0 + 10 * i) for i, day in enumerate(weekend)]

    def handler(sql, params=()):
        if "v_forecast_history" in sql:
            return [("msdp", "VNINDEX", 5, _utc(weekend[0]), 160.0, 150.0, 170.0, None)]
        if "v_history_1d" in sql:
            return closes
        return []

    with _answers(handler):
        out = team_models._scoring()

    row = out["horizons"][0]
    assert row["scored"] == 1, out
    # Session 5 is 2026-08-10 at 150.0 — a calendar count would have landed on
    # 2026-08-08, a Saturday, and scored against the wrong session or none.
    assert abs(row["bias_pct"] - (160.0 - 150.0) / 150.0 * 100) < 1e-9, row


@check("a forecast whose horizon has not elapsed is pending, not scored")
def _():
    def handler(sql, params=()):
        if "v_forecast_history" in sql:
            return [
                ("msdp", "VNINDEX", 5, _utc(SESSIONS[0]), 1050.0, 1000.0, 1100.0, None),
                ("msdp", "VNINDEX", 60, _utc(SESSIONS[0]), 1200.0, 1000.0, 1400.0, None),
            ]
        if "v_history_1d" in sql:
            return CLOSES
        return []

    with _answers(handler):
        out = team_models._scoring()

    assert out["scored"] == 1 and out["pending"] == 1, out
    horizons = {row["horizon"]: row for row in out["horizons"]}
    assert horizons[60]["scored"] == 0 and horizons[60]["mean_abs_error_pct"] is None
    # A pending forecast is not an accurate one; it is one that has not come due.
    assert horizons[60]["pending"] == 1


@check("the scoring says whose actuals it used, because the team's are empty")
def _():
    def handler(sql, params=()):
        if "v_forecast_history" in sql:
            return [("msdp", "VNINDEX", 5, _utc(SESSIONS[0]), 1050.0, 1000.0, 1100.0, None)]
        if "v_history_1d" in sql:
            return CLOSES
        return []

    with _answers(handler):
        out = team_models._scoring()

    said = " ".join(note["vi"] + note["en"] for note in out["notes"])
    assert "actual_value" in said, said
    assert out["team_scored"] == 0, out
    # A handful of forecasts cannot support a hit rate, and the notes say so.
    assert "coin toss" in said or "đồng xu" in said, said


@check("the interval is scored as a hit only when the close lands inside it")
def _():
    def handler(sql, params=()):
        if "v_forecast_history" in sql:
            return [
                # Session 5 closes at 1050: inside the first band, outside the second.
                ("msdp", "VNINDEX", 5, _utc(SESSIONS[0]), 1040.0, 1000.0, 1100.0, None),
                ("msdp", "VNINDEX", 5, _utc(SESSIONS[1]), 1000.0, 900.0, 1010.0, None),
            ]
        if "v_history_1d" in sql:
            return CLOSES
        return []

    with _answers(handler):
        out = team_models._scoring()

    row = out["horizons"][0]
    assert row["scored"] == 2 and abs(row["interval_hit_pct"] - 50.0) < 1e-9, row


@check("direction is scored against where the index actually stood")
def _():
    def handler(sql, params=()):
        if "v_forecast_history" in sql:
            return [
                # Up from 1000, and the index does go up: a hit.
                ("msdp", "VNINDEX", 5, _utc(SESSIONS[0]), 1100.0, 900.0, 1300.0, None),
                # Down from 1010, and the index goes up: a miss.
                ("msdp", "VNINDEX", 5, _utc(SESSIONS[1]), 900.0, 800.0, 1000.0, None),
            ]
        if "v_history_1d" in sql:
            return CLOSES
        return []

    with _answers(handler):
        out = team_models._scoring()

    row = out["horizons"][0]
    assert row["directional_scored"] == 2, row
    assert abs(row["directional_hit_pct"] - 50.0) < 1e-9, row
    # One right out of two is not a 50% skill claim, and the error bar says so:
    # sqrt(0.5 x 0.5 / 2) is 35 percentage points.
    assert abs(row["directional_error_pct"] - 35.355339) < 1e-5, row


# ----------------------------------------------------------------- forecast

@check("an experimental model is labelled as one before its numbers are read")
def _():
    def handler(sql, params=()):
        return [(
            "msdp", "VNINDEX", 5, "trading_days", "1D", "20260722_gpu", "experimental",
            _utc(SESSIONS[-1]), _utc(SESSIONS[-1]), 1779.77, -0.00473, 0.5189, None,
            None, 0.1578, 0.9, 1679.53, 1871.28,
        )]

    with _answers(handler):
        out = team_models._forecast()

    item = out["items"][0]
    assert item["status"] == "experimental"
    assert abs(item["probability_up_pct"] - 51.89) < 1e-6, item
    assert abs(item["forecast_return_pct"] - (-0.473)) < 1e-6, item
    said = " ".join(note["vi"] + note["en"] for note in out["notes"])
    assert "thử nghiệm" in said and "experimental" in said, said


# ------------------------------------------------------------------ network

@check("the network keeps the strongest of the graph, and states what an edge is")
def _():
    nodes = [{"id": f"S{i}", "pagerank": i / 100, "degree": i, "community": i % 3,
              "return_20d": 0.1, "volatility_20d": 0.3} for i in range(30)]
    edges = [{"source": f"S{i}", "target": f"S{i + 1}", "absolute_weight": i / 100,
              "signed_weight": -i / 100, "stability": 1.0} for i in range(40)]

    def handler(sql, params=()):
        return [(
            "VN30", date(2026, 9, 14), _utc(date(2026, 9, 14)), "0.1.0",
            "partial_correlation", 60, 30, 68.28, "normal", 0.6783,
            nodes, edges, [{"size": 7, "members": ["BCM", "BVH"]}],
        )]

    with _answers(handler):
        out = team_models._network()

    assert out["node_count"] == 30 and out["edge_count"] == 40
    assert len(out["nodes"]) == team_models.TOP_NODES
    assert len(out["edges"]) == team_models.TOP_EDGES
    # Strongest first, and a negative relationship keeps its sign.
    assert out["nodes"][0]["id"] == "S29", out["nodes"][0]
    assert out["edges"][0]["weight"] < 0, out["edges"][0]
    assert abs(out["stress_percentile_pct"] - 67.83) < 1e-6
    said = " ".join(note["vi"] + note["en"] for note in out["notes"])
    assert "causal" in said and "nhân quả" in said, said


# ----------------------------------------------------------------- pipeline

@check("a disconnect outside the session is counted apart from one inside it")
def _():
    # 2026-09-14 is a Monday. 03:00 UTC is mid-session; 20:00 UTC is not, and
    # Saturday is not a session at all.
    def handler(sql, params=()):
        return [
            ("VN30F1M", datetime(2026, 9, 14, 3, 0, tzinfo=timezone.utc),
             datetime(2026, 9, 14, 3, 2, tzinfo=timezone.utc)),
            ("VN30F1M", datetime(2026, 9, 14, 20, 0, tzinfo=timezone.utc), None),
            ("VIC", datetime(2026, 9, 12, 3, 0, tzinfo=timezone.utc),
             datetime(2026, 9, 12, 3, 0, 5, tzinfo=timezone.utc)),
        ]

    with _answers(handler):
        out = team_models._pipeline()

    # One of the three: the Monday 03:00 drop. The 20:00 one is after the
    # close and 2026-09-12 is a Saturday, so neither could cost a candle.
    assert out["total"] == 3 and out["in_session"] == 1, out
    assert out["unclosed"] == 1 and out["longer_than_a_minute"] == 1, out
    assert out["by_symbol"][0] == {"symbol": "VN30F1M", "count": 2}, out["by_symbol"]
    said = " ".join(note["vi"] + note["en"] for note in out["notes"])
    assert "data_coverage" in said and "missing data" in said, said


@check("one block failing does not take the others down")
def _():
    def handler(sql, params=()):
        if "v_network_latest" in sql:
            raise market_vn.MarketUnavailable("network view is gone")
        if "v_model_forecast_latest" in sql:
            return []
        return []

    with _answers(handler):
        out = team_models.overview()

    assert set(out) == {"forecast", "scoring", "network", "pipeline"}
    assert "error" in out["network"], out["network"]
    assert set(out["network"]["error"]) == {"vi", "en"}
    assert "error" not in out["forecast"], out["forecast"]


# ---------------------------------------------------------------------- live

@live("the four views answer, and the forecast carries its own status")
def _():
    out = team_models.overview()
    for name in ("forecast", "scoring", "network", "pipeline"):
        assert "error" not in out[name], (name, out[name])

    items = out["forecast"]["items"]
    assert items, "no forecast rows"
    assert {item["horizon"] for item in items}, items
    print(f"        forecast: {len(items)} horizons, status "
          f"{items[0]['status']}, model {items[0]['model_version']}")
    print(f"        scoring: {out['scoring']['scored']} scored, "
          f"{out['scoring']['pending']} still pending")
    print(f"        network: {out['network']['node_count']} nodes, stress "
          f"{out['network']['stress_score']} ({out['network']['stress_label']})")
    print(f"        pipeline: {out['pipeline']['total']} drops, "
          f"{out['pipeline']['in_session']} of them inside a session")


def _plain(exc) -> str:
    """A message this console can actually print.

    These payloads carry Vietnamese notes and the Windows console is cp1252, so
    printing one raw kills the runner in the middle of its report — and a suite
    that dies while reporting looks like a suite that passed.
    """
    return str(exc).encode("ascii", "replace").decode("ascii")


def main() -> int:
    passed = failed = 0
    checks = list(CHECKS)
    if market_vn.configured():
        checks += LIVE_CHECKS
    else:
        print("  (live checks skipped: no MARKET_DSN)")

    for name, fn in checks:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as exc:
            print(f"  FAIL  {name}")
            print(f"          {_plain(exc)}")
            failed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR {name}")
            print(f"          {type(exc).__name__}: {_plain(exc)}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
