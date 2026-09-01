"""Load research-model output into the `quant` schema the website reads.

The API only reads `quant`; something has to write it, and until now nothing
did, which is why the model sections of the site were empty. This is that
writer. It takes artifacts the models already produce and maps them onto the
published tables, one model at a time.

Every model now syncs its own input straight from `bars_1d` and publishes an
artifact under `models/<slug>/artifacts/`, so this script no longer runs any
model - it only reads what `daily-update.bat` has just produced:

    python database/scripts/load_model_outputs.py         --msdp          models/msdp/artifacts/predictions/latest_forecast.json         --rarf-forecast models/rarf-fhe/artifacts/forecasts/latest_forecast_summary.json         --raemf         models/raemf-mc/artifacts/forecasts/latest_forecast.json         --dynamic-graph models/dynamic-graph/artifacts/latest/latest_dynamicgraph.json

`--dry-run` rolls back instead of committing. `--mark-failed <model_id>` records
a step that did not finish, so a run that dies halfway cannot leave yesterday's
row still reading as today's success.

What is deliberately NOT written
--------------------------------
`quant.stock_rankings` stays empty. It needs a regime and an up-probability per
ticker, and no model produces those per ticker — DynamicGraph publishes network
centrality and per-ticker risk measures, which are different quantities.
Mapping centrality onto "probability of going up" would invent data.

DynamicGraph's stress probabilities are also not written. Its own artifact
grades that layer AUROC 0.49 with a negative Brier skill score and carries the
warning "Treat the probability as uninformative"; publishing it as a forecast
would present a rejected result as a signal. Its *descriptive* network state is
what reaches the site, and it travels as a file rather than through this
schema: `update-latest` rewrites `artifacts/latest/nodes.json` and `edges.json`,
and `npm run research:sync` copies them into `frontend/public/research/`.
`--dynamic-graph` here records the run and its provenance, nothing more.

RAEMF-VB-MC (Tempus) is held back for a different reason. Its `predict` payload
reports VaR, CVaR and max-drawdown quantiles but no direction probability and no
two-sided interval, and `quant.model_forecasts` requires both. Deriving
`probability_up` from a one-sided VaR would be invention, so the run is recorded
and the forecast row stays unwritten until the model publishes those fields
itself.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import UTC, datetime, time as dtime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Scripts here run under several different virtualenvs, so the shared
# helper is imported by path rather than as a package.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _db import dsn_from_env  # noqa: E402

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover - dependency hint
    sys.exit('Missing dependency. Install with: pip install "psycopg[binary]"')

VN = ZoneInfo("Asia/Ho_Chi_Minh")
SESSION_CLOSE = dtime(15, 0)

DEFAULT_DSN = None  # resolved lazily by dsn_from_env()


def session_close(day: datetime | str) -> datetime:
    """Timestamp a daily figure at the VN session close, in UTC.

    A daily forecast is only meaningful once the session it was computed from
    has closed, and the freshness block on the API compares against real time.
    """
    if isinstance(day, str):
        day = datetime.fromisoformat(day.split(" ")[0].replace("Z", ""))
    return datetime.combine(day.date(), SESSION_CLOSE, tzinfo=VN).astimezone(UTC)


# --- MSDP -----------------------------------------------------------------


def load_msdp(conn, payload: dict, symbol: str = "VNINDEX") -> int:
    """Map an MSDP forecast onto quant.model_forecasts.

    Units, verified against the artifact rather than assumed:
      * `return_quantiles` and `calibrated_interval` are percent log-returns —
        spot * exp(q/100) reproduces `projected_index_quantiles` exactly.
      * `quantiles` in MSDP's config are [.05 .25 .50 .75 .95], so the interval
        spanned by the outer pair is the 90% one.
      * `volatility` is a percentage.

    Regime, regime_probability, risk_score and risk_state stay NULL: MSDP
    forecasts a distribution and makes no regime call. Migration 0005 made
    those columns nullable precisely so this loader need not invent them.
    """
    spot = float(payload["current_vnindex"])
    data_as_of = session_close(payload["data_date"])
    generated_at = datetime.now(UTC)
    version = str(payload.get("run_id", "unknown"))[:40]

    rows = []
    for horizon in payload["horizons"]:
        quantiles = horizon["return_quantiles"]
        median_pct = quantiles[len(quantiles) // 2]
        forecast_value = spot * math.exp(median_pct / 100.0)
        low_pct, high_pct = horizon["calibrated_interval"]
        rows.append((
            "msdp", symbol, int(horizon["horizon"]), data_as_of,
            version, "1D", "trading_days", generated_at,
            forecast_value,
            forecast_value / spot - 1.0,
            float(horizon["probability_positive"]),
            1.0 - float(horizon["probability_positive"]),
            float(horizon["volatility"]) / 100.0,
            0.90,
            spot * math.exp(low_pct / 100.0),
            spot * math.exp(high_pct / 100.0),
            "experimental",
        ))

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO quant.model_forecasts (
                model_id, symbol, horizon, data_as_of,
                model_version, timeframe, horizon_unit, generated_at,
                forecast_value, forecast_return,
                probability_up, probability_down, volatility,
                interval_level, interval_lower, interval_upper, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (model_id, symbol, horizon, data_as_of) DO UPDATE SET
                model_version = EXCLUDED.model_version,
                generated_at = EXCLUDED.generated_at,
                forecast_value = EXCLUDED.forecast_value,
                forecast_return = EXCLUDED.forecast_return,
                probability_up = EXCLUDED.probability_up,
                probability_down = EXCLUDED.probability_down,
                volatility = EXCLUDED.volatility,
                interval_level = EXCLUDED.interval_level,
                interval_lower = EXCLUDED.interval_lower,
                interval_upper = EXCLUDED.interval_upper,
                status = EXCLUDED.status
            """,
            rows,
        )
    note = f"as_of={payload['data_date']}; run={version}"
    if "quick" in version:
        # A `quick` run is a few trials, folds and one seed. Publishing its
        # numbers is exactly what the model's own log warns against, so the
        # fact travels with the row rather than living only in a log file.
        note += "; QUICK ARTIFACT - not publication grade"
    _mark_run(conn, "msdp", generated_at, healthy=True, note=note[:200])
    return len(rows)


# --- RARF-FHE -------------------------------------------------------------


def _risk_state(var_95: float, drawdown: float) -> str:
    """Grade risk from the 95% VaR and the current drawdown.

    A published label needs a rule someone can check, so it is written here
    rather than guessed per run. Thresholds follow the loss magnitudes the
    model itself reports over the horizon.
    """
    loss = abs(var_95)
    if loss >= 0.20 or drawdown <= -0.20:
        return "high"
    if loss >= 0.12 or drawdown <= -0.10:
        return "elevated"
    if loss >= 0.06:
        return "moderate"
    return "low"


def _observed_risk(conn, symbol: str = "VNINDEX") -> dict:
    """Realised drawdown and volatility, straight from the price history.

    These are observations, not forecasts, so they come from the database
    rather than from a model artifact.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT trading_date, close FROM bars_1d
            WHERE symbol = %s AND close IS NOT NULL
            ORDER BY trading_date DESC LIMIT 260
            """,
            (symbol,),
        )
        rows = cur.fetchall()[::-1]
    closes = [float(c) for _, c in rows]
    peak = max(closes)
    current_drawdown = closes[-1] / peak - 1.0
    window = closes[-61:]
    peak_60 = max(window)
    rolling_drawdown_60d = min(
        c / max(window[: i + 1]) - 1.0 for i, c in enumerate(window)
    )
    returns = [
        math.log(closes[i] / closes[i - 1])
        for i in range(1, len(closes))
        if closes[i - 1] > 0
    ][-60:]
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / max(len(returns) - 1, 1)
    return {
        "current_drawdown": current_drawdown,
        "rolling_drawdown_60d": rolling_drawdown_60d,
        # Annualised with the 252-session convention used across the project.
        "volatility": math.sqrt(variance * 252),
        "peak_60": peak_60,
    }


def load_rarf(conn, payload: dict, symbol: str = "VNINDEX") -> None:
    """Map a RARF-FHE run onto quant.risk_metrics.

    The artifact reports VaR, expected shortfall and drawdown for the
    simulated horizon; realised drawdown and volatility come from the price
    history so the row mixes no forecast into an observation.
    """
    data_as_of = session_close(payload["forecast_origin"])
    generated_at = datetime.now(UTC)
    observed = _observed_risk(conn, symbol)
    var_95 = float(payload["var_95"])
    risk_state = _risk_state(var_95, observed["current_drawdown"])

    # Probability that the simulated maximum drawdown reaches at least each
    # threshold. The website charts this as "how far it could fall", so the
    # bucket is stored as a negative drawdown to match the axis formatting.
    distribution = [
        (data_as_of, "market", -abs(float(threshold)), float(probability))
        for threshold, probability in sorted(
            (payload.get("drawdown_probabilities") or {}).items(),
            key=lambda kv: float(kv[0]),
        )
    ]

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO quant.risk_metrics (
                ts, scope, current_drawdown, rolling_drawdown_60d, volatility,
                var_95, es_95, downside_probability, risk_state, mc_paths,
                generated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (ts, scope) DO UPDATE SET
                current_drawdown = EXCLUDED.current_drawdown,
                rolling_drawdown_60d = EXCLUDED.rolling_drawdown_60d,
                volatility = EXCLUDED.volatility,
                var_95 = EXCLUDED.var_95,
                es_95 = EXCLUDED.es_95,
                downside_probability = EXCLUDED.downside_probability,
                risk_state = EXCLUDED.risk_state,
                mc_paths = EXCLUDED.mc_paths,
                generated_at = EXCLUDED.generated_at
            """,
            (
                data_as_of, "market",
                observed["current_drawdown"],
                observed["rolling_drawdown_60d"],
                observed["volatility"],
                var_95,
                float(payload["expected_shortfall_95"]),
                float(payload["probability_negative_return"]),
                risk_state,
                int(payload.get("number_of_paths") or 0),
                generated_at,
            ),
        )
        if distribution:
            cur.executemany(
                """
                INSERT INTO quant.risk_mc_distribution
                    (ts, scope, bucket, probability)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (ts, scope, bucket) DO UPDATE SET
                    probability = EXCLUDED.probability
                """,
                distribution,
            )
    # Carry the run's own publication gate through to the database. RARF-FHE
    # sets promotion_eligible=false while its drawdown calibration is still
    # experimental, and that verdict should be visible to whoever decides
    # whether to turn the Risk tab on.
    status = str(payload.get("drawdown_calibration_status") or "unknown")
    eligible = bool(payload.get("promotion_eligible"))
    note = (
        f"as_of={payload['forecast_origin']}; drawdown {status}; "
        f"promotion_eligible={eligible}"
    )
    _mark_run(conn, "rarf-fhe", generated_at, healthy=True, note=note[:200])
    return len(distribution)


# --- DynamicGraph ---------------------------------------------------------


def load_dynamic_graph(conn, payload: dict) -> str:
    """Record a DynamicGraph run. No forecast row is written.

    The network state is descriptive, not predictive, and it reaches the site
    as a file (`nodes.json` / `edges.json` copied by `npm run research:sync`),
    not through `quant`. What belongs here is the fact that the run happened
    and what it saw, so `/system-status` can tell a fresh network from a
    three-week-old one.

    The stress probabilities in the same artifact are read only to be refused:
    the model grades that layer as no better than the base rate, and a run
    that carries `confidence_warning` on a horizon says so in the note rather
    than passing the number on.
    """
    model = payload["model"]
    state = payload["network_state"]
    as_of = str(model["as_of_date"])
    generated_at = datetime.now(UTC)

    warned = sorted(
        horizon
        for horizon, block in (payload.get("stress_probabilities") or {}).items()
        if isinstance(block, dict) and block.get("confidence_warning")
    )
    note = (
        f"as_of={as_of}; {state['label']} stress={state['stress_score']}; "
        f"nodes={payload['universe']['node_count']}; layer={model['graph_layer']}"
    )
    if warned:
        note += f"; stress probabilities withheld ({', '.join(warned)})"

    _mark_run(conn, "dynamic-graph", generated_at, healthy=True, note=note[:200])
    return as_of


# --- RAEMF-VB-MC (Tempus) -------------------------------------------------


def load_raemf(conn, payload: dict) -> str:
    """Record a RAEMF-VB-MC run. No forecast row is written.

    `quant.model_forecasts` needs `probability_up`, `probability_down` and a
    two-sided interval on every row. This model's `predict` payload publishes
    neither: its `risk` table is one-sided (VaR and CVaR are loss quantiles)
    and it reports no direction probability at all. A `probability_up` backed
    out of a one-sided tail would be a number this model never computed, so
    the row is left unwritten and the run is recorded instead.

    The model's own caveat list travels into the note, because the reason the
    forecast is withheld should be visible next to the run, not only in this
    docstring.
    """
    as_of = str(payload["as_of_date"])
    generated_at = datetime.now(UTC)

    # The longest reported horizon is the one the simulation is configured
    # around; the shorter rows are slices of the same paths.
    risk = payload.get("risk") or {}
    horizon = max(risk, key=lambda h: int(h)) if risk else None
    tail = ""
    if horizon:
        row = risk[horizon]
        tail = (
            f"; h={horizon} VaR95={row['VaR_95']:.4f} "
            f"CVaR95={row['CVaR_95']:.4f} mdd50={row['median_max_drawdown']:.4f}"
        )

    note = (
        f"as_of={as_of}; sessions={payload.get('sessions_used')}; "
        f"paths={(payload.get('monte_carlo') or {}).get('paths')}"
        f"{tail}; forecast withheld (no direction probability)"
    )
    _mark_run(conn, "raemf-mc", generated_at, healthy=True, note=note[:200])
    return as_of


# --- shared ---------------------------------------------------------------


def _mark_run(conn, model_id: str, when: datetime, healthy: bool, note: str | None):
    """Upsert the run row. A failure records the attempt without erasing the
    last known success: `COALESCE` keeps the stored timestamp when the new one
    is NULL, so "it broke today, it last worked on the 28th" stays answerable.
    Writing EXCLUDED straight through would replace that date with NULL and
    throw away the only evidence of when the model was last right."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO quant.model_runs (
                model_id, last_run_at, last_success_at, healthy, note)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (model_id) DO UPDATE SET
                last_run_at = EXCLUDED.last_run_at,
                last_success_at = COALESCE(
                    EXCLUDED.last_success_at, quant.model_runs.last_success_at
                ),
                healthy = EXCLUDED.healthy,
                note = EXCLUDED.note
            """,
            (model_id, when, when if healthy else None, healthy, note),
        )


# Every model the daily session can report on. `--mark-failed` only accepts
# these, so a typo cannot quietly create a row for a model that does not exist.
MODEL_IDS = ("msdp", "rarf-fhe", "raemf-mc", "dynamic-graph")


def _read(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=None)
    parser.add_argument("--symbol", default="VNINDEX")
    parser.add_argument("--msdp", help="MSDP latest_forecast.json")
    parser.add_argument("--rarf-forecast", help="latest_forecast_summary.json")
    parser.add_argument("--raemf", help="RAEMF-VB-MC latest_forecast.json")
    parser.add_argument("--dynamic-graph", help="latest_dynamicgraph.json")
    parser.add_argument(
        "--mark-failed",
        action="append",
        default=[],
        choices=MODEL_IDS,
        metavar="MODEL_ID",
        help=(
            "Record that this model's step did not finish. Repeatable. "
            "Without it a failed step leaves the previous run's row in place, "
            "which reads on /system-status as a success."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Roll back instead of committing"
    )
    args = parser.parse_args()

    sources = (
        args.msdp, args.rarf_forecast, args.raemf, args.dynamic_graph,
    )
    if not any(sources) and not args.mark_failed:
        parser.error(
            "give at least one of --msdp, --rarf-forecast, --raemf, "
            "--dynamic-graph, --mark-failed"
        )

    failed_at = datetime.now(UTC)
    with psycopg.connect(dsn_from_env(args.dsn)) as conn:
        if args.msdp:
            payload = _read(args.msdp)
            n = load_msdp(conn, payload, args.symbol)
            print(f"msdp      : {n} forecast row(s), data_date={payload['data_date']}")
        if args.rarf_forecast:
            payload = _read(args.rarf_forecast)
            buckets = load_rarf(conn, payload, args.symbol)
            print(
                f"rarf-fhe  : risk row + {buckets} drawdown bucket(s), "
                f"origin={payload['forecast_origin']}"
            )
        if args.raemf:
            as_of = load_raemf(conn, _read(args.raemf))
            print(f"raemf-mc  : run recorded, as_of={as_of} (no forecast row)")
        if args.dynamic_graph:
            as_of = load_dynamic_graph(conn, _read(args.dynamic_graph))
            print(f"dyn-graph : run recorded, as_of={as_of} (no forecast row)")

        # Failures are marked after the successes so that a model named in
        # both -- an artifact that loaded but whose step exited non-zero --
        # ends up flagged rather than green.
        for model_id in dict.fromkeys(args.mark_failed):
            _mark_run(
                conn, model_id, failed_at, healthy=False,
                note="step did not finish; see logs/daily-update-*.log",
            )
            print(f"{model_id:<10}: marked FAILED")

        if args.dry_run:
            conn.rollback()
            print("dry run: rolled back")
        else:
            conn.commit()
            print("committed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
