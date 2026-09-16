"""What the team's own pipeline publishes, beside what this platform computes.

Four views in the `api` schema were carrying real output that nothing here read:
a forecasting model on VNINDEX, the history of what it forecast, a correlation
network over VN30, and the ingestion log. They are a second opinion from a
different method, which is worth having on screen — but only if the differences
are said out loud rather than smoothed over, because two numbers on one screen
read as comparable whether or not they are.

Three things this module is careful about, each of them measured first:

* **The team never scored its own forecasts.** `v_forecast_history` has an
  `actual_value` column and it is NULL on every one of the 66 rows
  (2026-09-16). Reporting "the model is 80% accurate" from that column would be
  reporting nothing. So the scoring here is done against **this platform's own
  VNINDEX closes**, and says so wherever it appears.
* **A horizon is in trading days, not calendar days.** Five trading days after a
  Thursday is not the following Tuesday, and counting calendar days would score
  a forecast against the wrong session.
* **`v_ingestion_gaps` logs socket drops, not missing candles.** Measured in an
  earlier round: 156 of 210 entries fell outside trading hours, when there was
  nothing to receive. It is shown as a pipeline diagnostic under that name, and
  never as a claim about the data being incomplete.
"""

from __future__ import annotations

import math
from datetime import datetime, time, timezone

from backend.i18n import bi

# The Vietnamese session in UTC (§3.6): 02:00-08:00, Monday to Friday. Used
# only to say which pipeline drops could have cost a candle.
SESSION_START = time(2, 0)
SESSION_END = time(8, 0)


def overview() -> dict:
    """Every block, each one failing on its own.

    A network snapshot that cannot be read is not a reason to withhold the
    forecast beside it, so each block carries either its content or its own
    error rather than the whole call failing.
    """
    return {
        "forecast": _block(_forecast),
        "scoring": _block(_scoring),
        "network": _block(_network),
        "pipeline": _block(_pipeline),
    }


def _block(fn) -> dict:
    from backend.data.market_vn import MarketUnavailable

    try:
        return fn()
    except MarketUnavailable as exc:
        return {"error": bi(f"Không đọc được: {exc}", f"Could not be read: {exc}")}
    except Exception as exc:  # noqa: BLE001 - one block must not take the rest down
        return {"error": bi(
            f"Không đọc được khối này: {type(exc).__name__}.",
            f"This block could not be read: {type(exc).__name__}.",
        )}


# ---------------------------------------------------------------- forecast

def _forecast() -> dict:
    from backend.data.market_vn import _to_ms, query

    rows = query(
        """
        SELECT model_id, symbol, horizon, horizon_unit, timeframe, model_version,
               status, data_as_of, generated_at, forecast_value, forecast_return,
               probability_up, volatility, interval_level, interval_lower,
               interval_upper, regime, risk_state
        FROM api.v_model_forecast_latest
        ORDER BY symbol, horizon
        """
    )
    items = []
    for row in rows:
        (model_id, symbol, horizon, unit, timeframe, version, status, as_of, made,
         value, ret, up, vol, level, lower, upper, regime, risk_state) = row
        items.append({
            "model_id": model_id,
            "symbol": symbol,
            "horizon": int(horizon) if horizon is not None else None,
            "horizon_unit": unit,
            "timeframe": timeframe,
            "model_version": version,
            "status": status,
            "data_as_of": _to_ms(as_of) if as_of else None,
            "generated_at": _to_ms(made) if made else None,
            "forecast_value": _float(value),
            "forecast_return_pct": _float(ret, scale=100.0),
            "probability_up_pct": _float(up, scale=100.0),
            "volatility_pct": _float(vol, scale=100.0),
            "interval_level": _float(level),
            "interval_lower": _float(lower),
            "interval_upper": _float(upper),
            "regime": regime,
            "risk_state": risk_state,
        })

    notes = []
    if any(item["status"] and item["status"] != "production" for item in items):
        notes.append(bi(
            "Mô hình đang ở trạng thái **thử nghiệm** theo chính cột `status` của nó. "
            "Đây là ý kiến thứ hai để đối chiếu, không phải tín hiệu để giao dịch theo.",
            "The model reports its own `status` as **experimental**. This is a second "
            "opinion to compare against, not a signal to trade on.",
        ))
    if items:
        notes.append(bi(
            "Khoảng tin cậy nới rất nhanh theo tầm dự báo: một khoảng 90% rộng hàng trăm "
            "điểm nói rằng mô hình **không** biết chỉ số sẽ ở đâu, và đó là thông tin.",
            "The interval widens fast with the horizon: a 90% band hundreds of points "
            "wide is the model saying it does **not** know where the index will be, "
            "which is itself information.",
        ))
    return {"items": items, "notes": notes}


# ----------------------------------------------------------------- scoring

def _scoring() -> dict:
    """Score past forecasts against this platform's own closes.

    The team's `actual_value` column is empty, so the alternative to doing this
    here is showing a history with nothing to compare it to.
    """
    from backend.data.market_vn import _to_ms, query

    rows = query(
        """
        SELECT model_id, symbol, horizon, data_as_of, forecast_value,
               interval_lower, interval_upper, actual_value
        FROM api.v_forecast_history
        ORDER BY data_as_of
        """
    )
    if not rows:
        return {"horizons": [], "scored": 0, "pending": 0, "notes": []}

    symbols = {row[1] for row in rows if row[1]}
    closes: dict[str, list[tuple]] = {}
    for symbol in symbols:
        series = query(
            """
            SELECT trading_date, close FROM api.v_history_1d
            WHERE symbol = %s AND close IS NOT NULL
            ORDER BY trading_date
            """,
            (symbol,),
        )
        closes[symbol] = [(d, float(c)) for d, c in series]

    by_horizon: dict[int, dict] = {}
    scored = pending = 0
    team_scored = 0
    for (model_id, symbol, horizon, as_of, value, lower, upper, actual) in rows:
        horizon = int(horizon or 0)
        bucket = by_horizon.setdefault(horizon, {
            "horizon": horizon, "forecasts": 0, "scored": 0, "pending": 0,
            "errors_pct": [], "abs_errors_pct": [], "inside": 0, "directional": 0,
            "directional_scored": 0,
        })
        bucket["forecasts"] += 1
        if actual is not None:
            team_scored += 1

        series = closes.get(symbol) or []
        made_on = as_of.date() if hasattr(as_of, "date") else as_of
        # The last session at or before the forecast's own timestamp, then the
        # session `horizon` trading days later — counted in sessions, because
        # that is the unit the horizon is written in.
        start = _session_index(series, made_on)
        target = start + horizon if start is not None else None
        if target is None or target >= len(series):
            bucket["pending"] += 1
            pending += 1
            continue

        actual_close = series[target][1]
        forecast = _float(value)
        if forecast is None or not actual_close:
            bucket["pending"] += 1
            pending += 1
            continue

        error_pct = (forecast - actual_close) / actual_close * 100.0
        bucket["errors_pct"].append(error_pct)
        bucket["abs_errors_pct"].append(abs(error_pct))
        bucket["scored"] += 1
        scored += 1
        if lower is not None and upper is not None:
            if float(lower) <= actual_close <= float(upper):
                bucket["inside"] += 1
        # Direction: where the model said the index would go from where it
        # stood, against where it went.
        start_close = series[start][1]
        if start_close:
            predicted_up = forecast >= start_close
            actually_up = actual_close >= start_close
            bucket["directional_scored"] += 1
            if predicted_up == actually_up:
                bucket["directional"] += 1

    horizons = []
    for horizon in sorted(by_horizon):
        b = by_horizon[horizon]
        n = b["scored"]
        horizons.append({
            "horizon": horizon,
            "forecasts": b["forecasts"],
            "scored": n,
            "pending": b["pending"],
            "mean_abs_error_pct": (sum(b["abs_errors_pct"]) / n) if n else None,
            "bias_pct": (sum(b["errors_pct"]) / n) if n else None,
            "interval_hit_pct": (b["inside"] / n * 100.0) if n else None,
            "directional_hit_pct": _hit_rate(b["directional"], b["directional_scored"]),
            # The sampling error on that hit rate. Seventeen forecasts put it at
            # about eleven points, which is the difference between "this model
            # calls direction badly" and "this is seventeen coin tosses" (§2.6).
            "directional_error_pct": _hit_error(b["directional"], b["directional_scored"]),
            "directional_scored": b["directional_scored"],
        })

    notes = [bi(
        "Cột `actual_value` của team trống ở **toàn bộ** các dòng, nên phần chấm điểm này "
        "so dự báo với **giá đóng cửa VNINDEX của chính nền tảng**, đếm theo số phiên đúng "
        "như đơn vị của tầm dự báo.",
        "The team's own `actual_value` column is empty on **every** row, so this scoring "
        "compares each forecast with **this platform's own VNINDEX closes**, counted in "
        "sessions to match the unit the horizon is written in.",
    )]
    if scored and scored < 10:
        notes.append(bi(
            f"Chỉ **{scored}** dự báo đã tới hạn để chấm. Ở cỡ mẫu này, tỷ lệ đúng hướng "
            "chưa phân biệt được với tung đồng xu.",
            f"Only **{scored}** forecasts have come due. At this sample size, a hit rate "
            "is not distinguishable from a coin toss.",
        ))
    if team_scored:
        notes.append(bi(
            f"{team_scored} dòng đã có `actual_value` của team; phần còn lại vẫn chấm theo giá nền tảng.",
            f"{team_scored} rows now carry the team's own `actual_value`; the rest are still "
            "scored against the platform's prices.",
        ))
    return {
        "horizons": horizons,
        "scored": scored,
        "pending": pending,
        "team_scored": team_scored,
        "notes": notes,
        "as_of": _to_ms(rows[-1][3]) if rows[-1][3] else None,
    }


def _hit_rate(hits: int, tries: int):
    return (hits / tries * 100.0) if tries else None


def _hit_error(hits: int, tries: int):
    """Standard error of a hit rate, in percentage points."""
    if not tries:
        return None
    p = hits / tries
    return math.sqrt(p * (1 - p) / tries) * 100.0


def _session_index(series: list[tuple], when) -> int | None:
    """Index of the last session at or before ``when``."""
    if not series or when is None:
        return None
    found = None
    for i, (day, _close) in enumerate(series):
        if day <= when:
            found = i
        else:
            break
    return found


# ----------------------------------------------------------------- network

# Enough of the graph to read, not all of it: 30 nodes and 84 edges do not fit
# a panel, and the ones that matter are the strongest.
TOP_NODES = 10
TOP_EDGES = 12


def _network() -> dict:
    from backend.data.market_vn import _to_ms, query

    rows = query(
        """
        SELECT index_name, as_of_date, generated_at, model_version, graph_layer,
               graph_window, node_count, stress_score, stress_label,
               stress_percentile, nodes, edges, communities
        FROM api.v_network_latest
        """
    )
    if not rows:
        return {"available": False}

    (index_name, as_of, made, version, layer, window, node_count, stress,
     label, percentile, nodes, edges, communities) = rows[0]

    nodes = nodes or []
    edges = edges or []
    communities = communities or []

    top_nodes = sorted(nodes, key=lambda n: -(n.get("pagerank") or 0))[:TOP_NODES]
    top_edges = sorted(edges, key=lambda e: -(e.get("absolute_weight") or 0))[:TOP_EDGES]

    return {
        "available": True,
        "index_name": index_name,
        "as_of": _to_ms(as_of) if as_of else None,
        "generated_at": _to_ms(made) if made else None,
        "model_version": version,
        "graph_layer": layer,
        "graph_window": int(window) if window is not None else None,
        "node_count": int(node_count) if node_count is not None else len(nodes),
        "edge_count": len(edges),
        "stress_score": _float(stress),
        "stress_label": label,
        "stress_percentile_pct": _float(percentile, scale=100.0),
        "nodes": [{
            "id": n.get("id"),
            "pagerank": _float(n.get("pagerank")),
            "degree": _float(n.get("degree")),
            "community": n.get("community"),
            "return_20d_pct": _float(n.get("return_20d"), scale=100.0),
            "volatility_20d_pct": _float(n.get("volatility_20d"), scale=100.0),
        } for n in top_nodes],
        "edges": [{
            "source": e.get("source"),
            "target": e.get("target"),
            "weight": _float(e.get("signed_weight") if e.get("signed_weight") is not None
                             else e.get("weight")),
            "stability": _float(e.get("stability")),
        } for e in top_edges],
        "communities": [{
            "id": c.get("id", i),
            "size": c.get("size") or len(c.get("members") or []),
            "members": (c.get("members") or [])[:12],
        } for i, c in enumerate(communities)],
        "notes": [
            bi(
                f"Đồ thị dựng bằng **{layer or 'tương quan'}** trên cửa sổ {window or '?'} phiên. "
                "Cạnh là quan hệ thống kê trong cửa sổ đó, không phải quan hệ nhân quả, và nó "
                "đổi khi cửa sổ trượt.",
                f"The graph is built from **{layer or 'correlation'}** over a {window or '?'}-session "
                "window. An edge is a statistical relationship inside that window, not a causal "
                "one, and it changes as the window moves.",
            ),
            bi(
                "Điểm căng thẳng chỉ đọc được so với lịch sử của chính nó: bách phân vị đi kèm "
                "nói con số hôm nay đứng ở đâu trong phân phối đó.",
                "The stress score only reads against its own history: the percentile beside it "
                "says where today's number sits in that distribution.",
            ),
        ],
    }


# ---------------------------------------------------------------- pipeline

def _pipeline() -> dict:
    from backend.data.market_vn import _to_ms, query

    rows = query(
        """
        SELECT symbol, disconnect_ts, reconnect_ts
        FROM api.v_ingestion_gaps
        ORDER BY disconnect_ts DESC
        LIMIT 500
        """
    )
    total = len(rows)
    unclosed = in_session = long_ones = 0
    by_symbol: dict[str, int] = {}
    recent = []
    for symbol, down, up in rows:
        by_symbol[symbol] = by_symbol.get(symbol, 0) + 1
        seconds = None
        if up is not None:
            seconds = (up - down).total_seconds()
            if seconds > 60:
                long_ones += 1
        else:
            unclosed += 1
        during = _in_session(down)
        if during:
            in_session += 1
        if len(recent) < 20:
            recent.append({
                "symbol": symbol,
                "disconnected_at": _to_ms(down) if down else None,
                "reconnected_at": _to_ms(up) if up else None,
                "seconds": seconds,
                "in_session": during,
            })

    return {
        "total": total,
        "unclosed": unclosed,
        "longer_than_a_minute": long_ones,
        "in_session": in_session,
        "by_symbol": sorted(
            ({"symbol": s, "count": n} for s, n in by_symbol.items()),
            key=lambda row: -row["count"],
        )[:10],
        "recent": recent,
        "notes": [bi(
            "Đây là nhật ký **rớt kết nối của pipeline**, không phải dữ liệu thiếu. Một lần "
            "rớt ngoài giờ giao dịch không làm mất nến nào, và đo trên chính bảng này trước "
            "đây: phần lớn rơi ngoài phiên. Muốn biết dữ liệu có thủng hay không thì đếm nến, "
            "và đó là việc của `data_coverage`.",
            "This is a log of **pipeline disconnects**, not of missing data. A drop outside "
            "trading hours costs no candle, and measured on this very table before, most of "
            "them fall outside the session. Whether the data has holes is a question about "
            "candle counts, which is what `data_coverage` answers.",
        )],
    }


def _in_session(when: datetime | None) -> bool:
    if when is None:
        return False
    moment = when.astimezone(timezone.utc)
    if moment.weekday() >= 5:
        return False
    return SESSION_START <= moment.time() <= SESSION_END


def _float(value, scale: float = 1.0):
    return None if value is None else float(value) * scale
