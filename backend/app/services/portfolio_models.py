"""The two model outputs a portfolio can be laid over.

Both come from the descriptive tier of a research model — the part each
model's own validation supports — and both are read from views the pipeline
already publishes. Nothing here is a direction call.

* **DynamicGraph** publishes the VN30 dependency network: which stocks move
  together after the market is stripped out, and the communities that
  structure forms. Laying the holdings on it answers a question the
  correlation figures answer only as a number — whether "eight names" is
  eight bets or two.

* **Causa (MSDP)** publishes a calibrated interval for the index return at
  5, 20 and 60 sessions. Its own README says the point forecast has not
  beaten a baseline, so the median is not shown as a prediction; the
  interval is, scaled to the book by beta and onto equity by leverage, and
  set against two lines the reader already has: the return that pays the
  interest, and the fall that reaches the warning threshold.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.portfolio import (
    NetworkCommunity,
    NetworkEdge,
    NetworkNode,
    OutlookHorizon,
    PortfolioNetwork,
    PortfolioOutlook,
)

OUTLOOK_MODEL = "msdp"
OUTLOOK_SYMBOL = "VNINDEX"


async def load_network(
    session: AsyncSession, weights: dict[str, float]
) -> PortfolioNetwork | None:
    """The latest VN30 network with the holdings marked on it.

    `weights` are the holdings' shares of the measured book. A holding
    outside VN30 is listed as uncovered rather than dropped: the map is a
    partial view of the portfolio and must say so.
    """
    row = (
        await session.execute(
            text(
                """
                SELECT as_of_date, graph_window, stress_label, stress_score,
                       nodes, edges
                FROM api.v_network_latest
                WHERE index_name = 'VN30'
                ORDER BY as_of_date DESC
                LIMIT 1
                """
            )
        )
    ).mappings().first()
    if row is None:
        return None

    raw_nodes: list[dict] = row["nodes"] or []
    raw_edges: list[dict] = row["edges"] or []
    if not raw_nodes:
        return None

    held = set(weights)
    nodes = [
        NetworkNode(
            id=n["id"],
            community=int(n.get("community", 0)),
            strength=float(n.get("strength") or 0.0),
            degree=int(n.get("degree") or 0),
            risk_score=float(n.get("risk_score") or 0.0),
            volatility_20d=(
                float(n["volatility_20d"])
                if n.get("volatility_20d") is not None
                else None
            ),
            in_portfolio=n["id"] in held,
            weight=weights.get(n["id"]),
        )
        for n in raw_nodes
    ]
    edges = [
        NetworkEdge(
            source=e["source"],
            target=e["target"],
            weight=float(e.get("absolute_weight") or abs(e.get("weight", 0.0))),
            signed_weight=float(e.get("signed_weight") or e.get("weight", 0.0)),
        )
        for e in raw_edges
    ]

    # Communities from the node labels, so the list and the map agree even
    # when the snapshot's own community table is absent.
    by_community: dict[int, list[NetworkNode]] = {}
    for n in nodes:
        by_community.setdefault(n.community, []).append(n)
    communities = []
    for cid, members in sorted(by_community.items()):
        held_members = [m for m in members if m.in_portfolio]
        communities.append(
            NetworkCommunity(
                id=cid,
                members=[m.id for m in members],
                held=[m.id for m in held_members],
                portfolio_weight=round(
                    sum(m.weight or 0.0 for m in held_members), 6
                ),
            )
        )
    communities.sort(key=lambda c: c.portfolio_weight, reverse=True)

    node_ids = {n.id for n in nodes}
    return PortfolioNetwork(
        as_of=row["as_of_date"],
        window=int(row["graph_window"] or 0),
        stress_label=row["stress_label"],
        stress_score=(
            float(row["stress_score"]) if row["stress_score"] is not None else None
        ),
        nodes=nodes,
        edges=edges,
        communities=communities,
        covered=sorted(held & node_ids),
        uncovered=sorted(held - node_ids),
        covered_weight=round(sum(weights[s] for s in held & node_ids), 6),
    )


async def load_outlook(
    session: AsyncSession,
    *,
    beta: float | None,
    measured_value: float,
    equity: float | None,
    debt: float | None,
    rate: float | None,
    call_drop: float | None,
) -> PortfolioOutlook | None:
    """Causa's index interval, carried onto the book and onto equity.

    Returns None without a beta: the interval is an index statement and
    only beta connects it to these holdings. Equity figures are None without
    a loan. The break-even return — what the stocks must make over the
    horizon to pay the interest — and `call_drop`, the fall that reaches
    the warning threshold, are the two reference lines from the margin
    block, computed here on the same horizons so the chart can draw them on
    one axis.
    """
    if beta is None or beta == 0:
        return None

    rows = (
        await session.execute(
            text(
                """
                SELECT horizon, data_as_of, forecast_value, forecast_return,
                       interval_level, interval_lower, interval_upper
                FROM api.v_model_forecast_latest
                WHERE model_id = :model AND symbol = :symbol
                ORDER BY horizon
                """
            ),
            {"model": OUTLOOK_MODEL, "symbol": OUTLOOK_SYMBOL},
        )
    ).mappings().all()
    if not rows:
        return None

    horizons: list[OutlookHorizon] = []
    level = float(rows[0]["interval_level"])
    origin = rows[0]["data_as_of"]
    for r in rows:
        # The interval is published as price levels; the origin price is
        # what the forecast value and return together imply.
        fv, fr = float(r["forecast_value"]), float(r["forecast_return"])
        if 1.0 + fr == 0:
            continue
        origin_price = fv / (1.0 + fr)
        idx_lo = float(r["interval_lower"]) / origin_price - 1.0
        idx_hi = float(r["interval_upper"]) / origin_price - 1.0
        # Beta scales the index move onto the book. A negative beta swaps
        # the ends of the interval, so they are re-sorted.
        lo, hi = sorted((idx_lo * beta, idx_hi * beta))
        h = int(r["horizon"])
        on_equity = (
            (lambda x: round(x * measured_value / equity, 6))
            if equity is not None and equity > 0
            else (lambda x: None)
        )
        horizons.append(
            OutlookHorizon(
                horizon_days=h,
                index_lower=round(idx_lo, 6),
                index_upper=round(idx_hi, 6),
                portfolio_lower=round(lo, 6),
                portfolio_upper=round(hi, 6),
                equity_lower=on_equity(lo),
                equity_upper=on_equity(hi),
                breakeven_return=(
                    round(debt * rate * h / 252 / measured_value, 6)
                    if debt and rate is not None and measured_value > 0
                    else None
                ),
            )
        )
    if not horizons:
        return None

    as_of: date = origin.date() if hasattr(origin, "date") else origin
    return PortfolioOutlook(
        source_model=OUTLOOK_MODEL,
        data_as_of=as_of,
        interval_level=level,
        portfolio_beta=round(beta, 4),
        call_drop=call_drop,
        horizons=horizons,
    )
