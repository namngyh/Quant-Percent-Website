"""Seed the published catalogue from the website's exported snapshot.

The catalogue (models, performance reports) lives in TypeScript config on
the website. Rather than parsing TypeScript here, the website exports a
resolved snapshot and this script consumes it, so helpers and derived
values on that side can never break seeding.

    # in frontend/
    npm run catalogue:export
    # in backend/
    python -m scripts.seed_catalogue

`--frontend` defaults to the sibling `frontend/` directory; pass it only when
seeding from a checkout laid out differently.

Re-runnable: rows are upserted by primary key.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from app.core.redis import cache_delete_prefix, close_redis
from app.db.models import (
    IndexConstituent,
    Model,
    ReportBucket,
    ReportEquityPoint,
    ReportExitReason,
    ReportFold,
    ReportMetric,
    ReportSimulation,
    Strategy,
    Symbol,
    TradingCalendar,
)
from app.db.session import SessionLocal

NOTIONAL_POINTS = 1000.0

# Metrics carried in the confidence-interval table of the multi-seed run
CI_METRICS = {
    "net_profit": "netPoints",
    "rr": "payoff",
    "profit_factor": "profitFactor",
    "sharpe": "sharpe",
    "sortino": "sortino",
    "calmar": "calmar",
    "max_dd": "maxDrawdownPoints",
    "win_rate": "winRate",
    "upi": "upi",
    "total_trades": "trades",
}
CI_PERCENT_KEYS = {"winRate"}


def load_catalogue(frontend: Path) -> dict[str, list[dict[str, Any]]]:
    path = frontend / "config" / "catalogue.json"
    if not path.exists():
        raise SystemExit(
            f"{path} not found.\n"
            "Export it first from the website repo:\n"
            "    npx tsx scripts/export-catalogue.ts"
        )
    return json.loads(path.read_text(encoding="utf-8"))


# --- Seeding ---------------------------------------------------------------


async def seed_symbols(session) -> None:
    rows = [
        {
            "symbol": "VNINDEX",
            "name": "VN-Index",
            "kind": "index",
            "point_value": None,
        },
        {
            "symbol": "VN30",
            # DataPro delivers the VN30 index under a different name; the
            # website keeps publishing it as VN30.
            "feed_symbol": "VN30INDEX",
            "name": "VN30",
            "kind": "index",
            "point_value": None,
        },
        {
            "symbol": "VN30F1M",
            "name": "VN30F1M",
            "kind": "future",
            "point_value": 100000,
        },
    ]
    vn30 = [
        "ACB", "BID", "CTG", "DGC", "FPT", "GAS", "GVR", "HDB", "HPG", "LPB",
        "MBB", "MCH", "MSN", "MWG", "SAB", "SHB", "SSB", "SSI", "STB", "TCB",
        "TCX", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VPL", "VRE",
    ]
    rows += [
        {"symbol": t, "name": t, "kind": "stock", "point_value": None}
        for t in vn30
    ]

    for row in rows:
        # Most tickers carry the same name in the feed as on the website.
        row.setdefault("feed_symbol", row["symbol"])
        stmt = insert(Symbol).values(**row)
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[Symbol.symbol],
                set_={
                    "name": stmt.excluded.name,
                    "kind": stmt.excluded.kind,
                    "feed_symbol": stmt.excluded.feed_symbol,
                },
            )
        )

    # HOSE rebalanced the VN30 basket on 2026-08-03 (TPB, PLX out; MCH, TCX in)
    valid_from = date(2026, 8, 3)
    # Replace the membership for this date rather than skipping when rows
    # already exist. The previous version inserted only when the date was
    # absent, so a corrected list could never reach a database that had
    # already been seeded with a wrong one — which is exactly what happened.
    await session.execute(
        delete(IndexConstituent).where(
            IndexConstituent.index_symbol == "VN30",
            IndexConstituent.valid_from == valid_from,
        )
    )
    session.add_all(
        IndexConstituent(
            index_symbol="VN30", member_symbol=t, valid_from=valid_from
        )
        for t in vn30
    )


async def seed_trading_calendar(session, year: int) -> None:
    """Weekday calendar for the year. Public holidays must be corrected
    afterwards — a wrong calendar shows a holiday as a trading session."""
    first = date(year, 1, 1).toordinal()
    last = date(year, 12, 31).toordinal()
    for ordinal in range(first, last + 1):
        day = date.fromordinal(ordinal)
        stmt = insert(TradingCalendar).values(
            trading_date=day, is_trading_day=day.weekday() < 5
        )
        await session.execute(
            stmt.on_conflict_do_nothing(index_elements=[TradingCalendar.trading_date])
        )


async def seed_models(session, entries: list[dict[str, Any]]) -> int:
    for order, entry in enumerate(entries):
        values = {
            "slug": entry["slug"],
            "code": entry["code"],
            "name": entry["name"],
            "markets": entry["markets"],
            "category": entry["category"],
            "status": entry["status"],
            "visibility": entry["visibility"],
            "access": entry["access"],
            "featured": entry["featured"],
            "version": entry["version"],
            "horizons": entry["horizons"],
            "show_forecast": entry["show_forecast"],
            "show_performance": entry["show_performance"],
            "sort_order": order,
            "tagline": entry["tagline"],
            "key_output": entry["keyOutput"],
            "description": entry["description"],
            "architecture": entry.get("architecture"),
            "sparkline": entry.get("sparkline"),
            "sparkline_label": entry.get("sparklineLabel"),
            "research_profile": entry.get("researchProfile"),
        }
        # `updatedAt` is optional in the website's ModelConfig. When a model
        # does not declare one, leave the column to its now() default instead
        # of failing the whole seed run.
        updated_at = entry.get("updatedAt")
        if updated_at:
            values["updated_at"] = datetime.fromisoformat(
                updated_at.replace("Z", "+00:00")
            )
        stmt = insert(Model).values(**values)
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[Model.slug],
                set_={k: v for k, v in values.items() if k != "slug"},
            )
        )
    return len(entries)


def _metric_rows(full: dict, tier3: dict | None) -> dict[str, float]:
    def pct(v: float | None) -> float | None:
        return None if v is None else v / 100

    out: dict[str, float | None] = {
        "totalReturn": pct(tier3["net_pct"]) if tier3 else None,
        "annualizedReturn": pct(tier3["car"]) if tier3 else None,
        "maxDrawdown": pct(tier3["max_dd_pct"]) if tier3 else None,
        "winRate": pct(full.get("win_rate")),
        "exposure": pct(full.get("exposure")),
        "pctMonths": pct(full.get("pct_months")),
        "wrLong": pct(full.get("wr_long")),
        "wrShort": pct(full.get("wr_short")),
        "netPoints": full.get("net_profit"),
        "maxDrawdownPoints": full.get("max_dd"),
        "expectancy": full.get("expectancy"),
        "avgWin": full.get("avg_win"),
        "avgLoss": full.get("avg_loss"),
        "longPnl": full.get("long_pnl"),
        "shortPnl": full.get("short_pnl"),
        "sharpe": full.get("sharpe"),
        "sortino": full.get("sortino"),
        "calmar": full.get("calmar"),
        "profitFactor": full.get("profit_factor"),
        "payoff": full.get("payoff"),
        "ulcer": full.get("ulcer"),
        "upi": full.get("upi"),
        "equityR2": full.get("equity_r2"),
        "trades": full.get("total_trades"),
        "maxConsecutiveLosses": full.get("max_cons_l"),
    }
    return {k: v for k, v in out.items() if v is not None}


async def seed_strategies(
    session, entries: list[dict[str, Any]], frontend: Path
) -> int:
    perf_dir = frontend / "config" / "performance"
    datasets = {
        "modus2024_2026": json.loads(
            (perf_dir / "modus-2024-2026.json").read_text(encoding="utf-8")
        ),
    }

    # Seeding upserts, so a report dropped from the catalogue would otherwise
    # stay published forever — the API would keep serving a run the project no
    # longer stands behind. Child rows go with it through ON DELETE CASCADE.
    published = [e["slug"] for e in entries]
    removed = (
        await session.execute(
            delete(Strategy)
            .where(Strategy.slug.notin_(published))
            .returning(Strategy.slug)
        )
    ).scalars().all()
    if removed:
        print(f"withdrew {len(removed)} report(s): {', '.join(sorted(removed))}")

    for order, entry in enumerate(entries):
        slug = entry["slug"]
        data = datasets[entry["dataset"]]
        period_end = date.fromisoformat(entry["periodEnd"])
        values = {
            "slug": slug,
            "system_slug": entry["systemSlug"],
            "name": entry["name"],
            "summary": entry["summary"],
            "result_type": entry["resultType"],
            "asset": entry["asset"],
            "timeframe": entry["timeframe"],
            "benchmark": entry["benchmark"],
            "period_start": date.fromisoformat(entry["periodStart"]),
            "period_end": period_end,
            "fees_note": entry["feesNote"],
            "slippage_note": entry["slippageNote"],
            "split_note": entry["splitNote"],
            "seed_note": entry["seedNote"],
            "model_version": entry["modelVersion"],
            "code_version": entry["codeVersion"],
            "caveats": entry["caveats"],
            "provenance": data["provenance"],
            "sort_order": order,
            "published": True,
            "data_as_of": datetime.combine(
                period_end, time(15, 0), tzinfo=UTC
            ),
            "generated_at": datetime.fromisoformat(
                data["provenance"]["extracted_at"]
            ).replace(tzinfo=UTC),
        }
        stmt = insert(Strategy).values(**values)
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[Strategy.slug],
                set_={k: v for k, v in values.items() if k != "slug"},
            )
        )

        # Child rows are rewritten wholesale — a report is republished as
        # a unit, never patched row by row
        for table in (
            ReportMetric,
            ReportEquityPoint,
            ReportBucket,
            ReportFold,
            ReportExitReason,
            ReportSimulation,
        ):
            await session.execute(
                delete(table).where(table.strategy_slug == slug)
            )

        # No multi-seed report is published at the moment, so this branch is
        # currently unreachable. It is kept because the research project still
        # produces multi-seed runs and one is expected back; deleting the
        # loader would mean rewriting it rather than adding a JSON file.
        if entry["dataset"] == "multiseed":
            await _seed_multiseed(session, slug, data)
        else:
            await _seed_single_run(session, slug, entry["dataset"], data)

    return len(entries)


async def _seed_single_run(session, slug: str, dataset: str, data: dict) -> None:
    metrics = _metric_rows(data["full"], data["tier3"]["all"])
    session.add_all(
        ReportMetric(strategy_slug=slug, metric=k, value=float(v))
        for k, v in metrics.items()
    )

    for point in data.get("equity", []):
        session.add(
            ReportEquityPoint(
                strategy_slug=slug,
                trade=point["trade"],
                equity=point["equity"],
                equity_pct=point["equity_pct"],
                drawdown=point["drawdown"],
                drawdown_pct=point["drawdown_pct"],
            )
        )

    for bucket in data.get("distribution", []):
        session.add(
            ReportBucket(
                strategy_slug=slug,
                kind="return_distribution",
                bucket=bucket["bucket"],
                count=bucket["count"],
            )
        )

    for reason in data.get("exit_reasons", []):
        session.add(
            ReportExitReason(
                strategy_slug=slug, reason=reason["id"], share=reason["share"]
            )
        )

    for fold in data.get("folds", []):
        session.add(
            ReportFold(
                strategy_slug=slug,
                fold=fold["fold"],
                train_from=fold["train_from"],
                train_to=fold["train_to"],
                test_year=fold["test_year"],
                net_points=fold["net_points"],
                net_pct=round(fold["net_points"] / NOTIONAL_POINTS, 4),
                trades=fold["trades"],
                long_trades=fold["long"],
                short_trades=fold["short"],
                win_rate=fold["win_rate"],
                payoff=fold["payoff"],
                max_drawdown_points=fold["max_drawdown_points"],
                partial_year=fold["partial_year"],
            )
        )


async def _seed_multiseed(session, slug: str, data: dict) -> None:
    ci = data["ci95"]

    def mean(key: str) -> float | None:
        return ci[key]["mean"] if key in ci else None

    def pct(v: float | None) -> float | None:
        return None if v is None else v / 100

    values: dict[str, float | None] = {
        "totalReturn": (mean("net_profit") or 0) / NOTIONAL_POINTS,
        "annualizedReturn": (mean("annual_ret") or 0) / NOTIONAL_POINTS,
        # Percentage drawdown is peak-relative and was not exported per
        # seed, so it stays absent rather than being approximated
        "winRate": pct(mean("win_rate")),
        "exposure": pct(mean("exposure")),
        "pctMonths": pct(mean("pct_months")),
        "wrLong": pct(mean("wr_long")),
        "wrShort": pct(mean("wr_short")),
        "netPoints": mean("net_profit"),
        "maxDrawdownPoints": mean("max_dd"),
        "expectancy": mean("expectancy"),
        "avgWin": mean("avg_win"),
        "avgLoss": mean("avg_loss"),
        "longPnl": mean("long_pnl"),
        "shortPnl": mean("short_pnl"),
        "sharpe": mean("sharpe"),
        "sortino": mean("sortino"),
        "calmar": mean("calmar"),
        "profitFactor": mean("profit_factor"),
        "payoff": mean("rr"),
        "ulcer": mean("ulcer"),
        "upi": mean("upi"),
        "equityR2": mean("equity_r2"),
        "trades": mean("total_trades"),
        "maxConsecutiveLosses": mean("max_cons_l"),
    }

    ci_by_metric = {}
    for src, key in CI_METRICS.items():
        if src in ci:
            scale = 100 if key in CI_PERCENT_KEYS else 1
            ci_by_metric[key] = (
                ci[src]["ci95_lo"] / scale,
                ci[src]["ci95_hi"] / scale,
            )

    for metric, value in values.items():
        if value is None:
            continue
        bounds = ci_by_metric.get(metric)
        session.add(
            ReportMetric(
                strategy_slug=slug,
                metric=metric,
                value=float(value),
                ci95_lo=bounds[0] if bounds else None,
                ci95_hi=bounds[1] if bounds else None,
                in_confidence_table=bounds is not None,
            )
        )

    median = data["median_seed"]
    for point in median["equity"]:
        session.add(
            ReportEquityPoint(
                strategy_slug=slug,
                trade=point["trade"],
                equity=point["equity"],
                equity_pct=point["equity_pct"],
                drawdown=point["drawdown"],
                drawdown_pct=point["drawdown_pct"],
            )
        )
    for bucket in median["distribution"]:
        session.add(
            ReportBucket(
                strategy_slug=slug,
                kind="return_distribution",
                bucket=bucket["bucket"],
                count=bucket["count"],
            )
        )
    for bucket in data["seed_distribution"]:
        session.add(
            ReportBucket(
                strategy_slug=slug,
                kind="seed_distribution",
                bucket=bucket["bucket"],
                count=bucket["count"],
            )
        )

    session.add(
        ReportSimulation(
            strategy_slug=slug,
            n_seeds=data["n_seeds"],
            pct_positive=data["pct_positive"],
            long_bias_seeds=data["long_bias_seeds"],
            short_bias_seeds=data["short_bias_seeds"],
            profit=data["profit"],
            bootstrap=data["bootstrap"],
            cost_stress=data["cost_stress"],
            median_seed=median["seed"],
        )
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--frontend",
        default=str(Path(__file__).resolve().parents[2] / "frontend"),
        help="path to the Next.js project holding config/",
    )
    parser.add_argument("--year", type=int, default=date.today().year)
    args = parser.parse_args()

    frontend = Path(args.frontend).resolve()
    catalogue = load_catalogue(frontend)

    async with SessionLocal() as session:
        await seed_symbols(session)
        await seed_trading_calendar(session, args.year)
        n_models = await seed_models(session, catalogue["models"])
        n_strategies = await seed_strategies(
            session, catalogue["strategies"], frontend
        )
        await session.commit()

    # A republished report must become visible immediately rather than wait
    # for the one-hour finished-report cache to expire.
    await cache_delete_prefix("strategies:")
    await close_redis()

    print(f"seeded {n_models} models and {n_strategies} performance reports")


if __name__ == "__main__":
    asyncio.run(main())
