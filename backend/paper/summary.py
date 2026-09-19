"""Every paper session read as one account.

The session list answers "how is this strategy on this symbol doing". It cannot
answer "how am I doing", which is a different question and the one someone
actually has after running a few of them: the sessions are separate simulations
that happen to belong to the same person.

Two things need saying about what is and is not measurable here.

**The equity curve is stepped at trade exits, not sampled per bar.** A session
records its trades and its running balance; it does not keep a per-bar equity
series, and inventing one by interpolating between exits would draw a smooth
line through time the account never actually traced. So the curve moves only
where money actually moved, and says so.

**Open positions are marked to market but kept separate.** Realised and
unrealised are different kinds of number — one is settled and one is a current
opinion about a position still running — and adding them into a single figure
without saying which is which is how a drawdown gets hidden.
"""

from __future__ import annotations

import numpy as np

from backend.i18n import bi


def _fee(snapshot: dict, trade: dict, price: float) -> float:
    """Rebuild a fee for rows saved before the settlement fields existed."""
    config = snapshot.get("config", {})
    contract = config.get("contract")
    quantity = abs(float(trade.get("quantity", 0.0)))
    if not contract:
        return quantity * price * float(config.get("fee", 0.0))
    contracts = trade.get("contracts")
    count = int(contracts) if contracts is not None else int(round(quantity))
    if contract.get("fee_mode") == "notional":
        multiplier = float(trade.get("multiplier") or contract.get("multiplier", 1.0))
        return count * price * multiplier * float(contract.get("fee_rate", 0.0))
    return count * float(contract.get("fee_per_contract", 0.0))


def _session_rows(snapshot: dict) -> list[dict]:
    """One auditable row per closed trade, tagged with its session."""
    rows: list[dict] = []
    for trade in snapshot.get("trades", []):
        # New trades store all four numbers. Old persisted rows only have
        # `pnl`, whose established meaning is gross price P&L less exit fee;
        # derive the missing pieces from the frozen session configuration.
        entry_fee = float(trade["entry_fee"]) if trade.get("entry_fee") is not None else _fee(
            snapshot, trade, float(trade["entry_price"])
        )
        exit_fee = float(trade["exit_fee"]) if trade.get("exit_fee") is not None else _fee(
            snapshot, trade, float(trade["exit_price"])
        )
        gross = trade.get("gross_pnl")
        gross = float(gross) if gross is not None else float(trade["pnl"]) + exit_fee
        net = trade.get("net_pnl")
        net = float(net) if net is not None else gross - entry_fee - exit_fee
        rows.append({
            "session_id": snapshot["id"],
            "symbol": snapshot["symbol"],
            "timeframe": snapshot["timeframe"],
            "strategy_id": snapshot["strategy_id"],
            "side": trade["side"],
            "entry_time": trade["entry_time"],
            "exit_time": trade["exit_time"],
            "entry_price": trade["entry_price"],
            "exit_price": trade["exit_price"],
            "quantity": trade["quantity"],
            "pnl": trade["pnl"],
            "gross_pnl": gross,
            "entry_fee": entry_fee,
            "exit_fee": exit_fee,
            "fee": entry_fee + exit_fee,
            "net_pnl": net,
            "return_pct": trade["return_pct"],
            "exit_reason": trade["exit_reason"],
            "balance_before": trade.get("balance_before"),
            "balance_after": trade.get("balance_after"),
        })

    # Supply per-session balances for legacy rows. New rows carry the exact
    # values captured by the engine; the fallback produces the same accounting
    # identity for data saved by earlier versions.
    running = float(snapshot.get("config", {}).get("initial_capital", 0.0))
    for row in sorted(rows, key=lambda item: item["exit_time"]):
        before = row["balance_before"]
        before = float(before) if before is not None else running
        after = row["balance_after"]
        after = float(after) if after is not None else before + row["net_pnl"]
        row["balance_before"] = before
        row["balance_after"] = after
        running = after
    return rows


def _equity_curve(trades: list[dict], starting: float) -> list[dict]:
    """Account balance after each closed trade, oldest first.

    Stepped on purpose: these are the only moments the balance is known. The
    first point is the opening balance at the first exit's time, so the curve
    starts from where the account started rather than from its first result.
    """
    if not trades:
        return []
    ordered = sorted(trades, key=lambda t: t["exit_time"])
    equity = starting
    points = [{"time": ordered[0]["exit_time"], "equity": round(starting, 2)}]
    for trade in ordered:
        equity += trade["net_pnl"]
        points.append({"time": trade["exit_time"], "equity": round(equity, 2)})
    return points


def _balance_history(trades: list[dict], starting: float) -> list[dict]:
    """Combined-account settlement ledger, newest first."""
    balance = starting
    rows = []
    for trade in sorted(trades, key=lambda item: item["exit_time"]):
        before = balance
        balance = before + trade["net_pnl"]
        rows.append({
            "time": trade["exit_time"],
            "balance_before": before,
            "balance_after": balance,
            "gross_pnl": trade["gross_pnl"],
            "fee": trade["fee"],
            "entry_fee": trade["entry_fee"],
            "exit_fee": trade["exit_fee"],
            "net_pnl": trade["net_pnl"],
            "symbol": trade["symbol"],
            "side": trade["side"],
            "exit_reason": trade["exit_reason"],
        })
    return list(reversed(rows))


def _drawdown(points: list[dict]) -> dict:
    """Worst peak-to-trough fall along the stepped curve."""
    if len(points) < 2:
        return {"max_drawdown_pct": 0.0, "max_drawdown_abs": 0.0}
    values = np.array([p["equity"] for p in points], dtype="float64")
    peaks = np.maximum.accumulate(values)
    # A peak of zero would divide by zero; an account that reached zero has a
    # 100% drawdown by definition and no further arithmetic is meaningful.
    safe = np.where(peaks > 0, peaks, np.nan)
    falls = (values - peaks) / safe
    worst = float(np.nanmin(falls)) if np.isfinite(falls).any() else 0.0
    return {
        "max_drawdown_pct": abs(worst) * 100.0,
        "max_drawdown_abs": float(np.min(values - peaks)),
    }


VN_ACCOUNT_CLASSES = {"equity", "fund", "futures_vn", "warrant"}


def account_currency(symbol: str) -> str:
    """The currency a session's money is counted in.

    Binance symbols settle in USDT; Vietnamese listings and index futures in
    VND. Anything else on the VN feed (indices, the G- international series)
    has no account currency of its own and is kept apart as plain units.
    """
    name = (symbol or "").strip()
    if not name.upper().startswith("VN:"):
        return "USDT"
    from backend.data.market_vn import classify
    return "VND" if classify(name[3:]) in VN_ACCOUNT_CLASSES else "units"


def build(snapshots: list[dict]) -> dict:
    """The account view over every paper session, one per currency.

    Sessions in different currencies are never added together: a 10 000 USDT
    session and a 100 million VND one summed to a "starting capital" of
    100 010 000 (2026-09-17), a number in no currency at all. `accounts` holds
    one full summary per currency, largest by session count first; the top
    level repeats the first so a single-currency reader is unchanged.
    """
    if not snapshots:
        return {
            "sessions": 0,
            "note": bi(
                "Chưa có phiên giao dịch mô phỏng nào.",
                "No simulated trading sessions yet.",
            ),
        }

    groups: dict[str, list[dict]] = {}
    for snap in snapshots:
        groups.setdefault(account_currency(snap["symbol"]), []).append(snap)
    accounts = sorted(
        ({"currency": currency, **_account(group)} for currency, group in groups.items()),
        key=lambda a: a["sessions"], reverse=True,
    )
    return {**accounts[0], "sessions": len(snapshots), "accounts": accounts}


def _account(snapshots: list[dict]) -> dict:
    """One currency's sessions read as one account."""
    trades: list[dict] = []
    for snap in snapshots:
        trades.extend(_session_rows(snap))

    starting = sum(s["config"]["initial_capital"] for s in snapshots)
    realised = sum(s["realized_pnl"] for s in snapshots)
    unrealised = sum(s["unrealized_pnl"] for s in snapshots)
    equity = sum(s["equity"] for s in snapshots)

    pnls = np.array([t["net_pnl"] for t in trades], dtype="float64")
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]

    curve = _equity_curve(trades, starting)
    balance_history = _balance_history(trades, starting)

    # Per symbol, because "how am I doing" usually turns straight into "on
    # what". Sorted by realised P&L: the tails are what a reader looks for.
    by_symbol: dict[str, dict] = {}
    for t in trades:
        row = by_symbol.setdefault(t["symbol"], {
            "symbol": t["symbol"], "trades": 0, "pnl": 0.0, "wins": 0,
        })
        row["trades"] += 1
        row["pnl"] += t["net_pnl"]
        if t["net_pnl"] > 0:
            row["wins"] += 1
    for row in by_symbol.values():
        row["win_rate_pct"] = row["wins"] / row["trades"] * 100.0 if row["trades"] else 0.0

    open_positions = [
        {
            "session_id": s["id"],
            "symbol": s["symbol"],
            "timeframe": s["timeframe"],
            "side": "long" if s["position"] > 0 else "short",
            "quantity": s["quantity"],
            "entry_price": s["entry_price"],
            "last_price": s["last_price"],
            "unrealized_pnl": s["unrealized_pnl"],
            "stop_loss": s.get("stop_loss"),
            "take_profit": s.get("take_profit"),
        }
        for s in snapshots if s["position"] != 0
    ]

    return {
        "sessions": len(snapshots),
        "active_sessions": sum(1 for s in snapshots if s["active"]),
        "starting_capital": starting,
        "equity": equity,
        # Kept apart rather than summed into one number: one is settled, the
        # other is a current opinion about positions still running.
        "realized_pnl": realised,
        "unrealized_pnl": unrealised,
        "return_pct": (equity / starting - 1.0) * 100.0 if starting else 0.0,
        "num_trades": len(trades),
        "num_wins": int(wins.size),
        "win_rate_pct": (wins.size / len(trades) * 100.0) if trades else 0.0,
        "avg_win": float(wins.mean()) if wins.size else 0.0,
        "avg_loss": float(losses.mean()) if losses.size else 0.0,
        "best_trade": float(pnls.max()) if pnls.size else 0.0,
        "worst_trade": float(pnls.min()) if pnls.size else 0.0,
        "profit_factor": (
            float(wins.sum() / abs(losses.sum())) if losses.size and losses.sum() else None
        ),
        "profitable_trades_pnl": float(wins.sum()) if wins.size else 0.0,
        "expectancy_money": float(pnls.mean()) if pnls.size else 0.0,
        "expectancy_pct": (
            float(np.mean([
                t["net_pnl"] / t["balance_before"] * 100.0
                for t in trades if t["balance_before"]
            ])) if any(t["balance_before"] for t in trades) else 0.0
        ),
        "avg_rr": (
            float(wins.mean() / abs(losses.mean())) if wins.size and losses.size else None
        ),
        "total_fees": float(sum(t["fee"] for t in trades)),
        **_drawdown(curve),
        "equity_curve": curve,
        "balance_history": balance_history,
        "by_symbol": sorted(by_symbol.values(), key=lambda r: r["pnl"], reverse=True),
        "open_positions": open_positions,
        # Newest first: a trade log is read from the top.
        "trades": sorted(trades, key=lambda t: t["exit_time"], reverse=True),
        "curve_note": bi(
            "Đường vốn chỉ có điểm tại thời điểm đóng lệnh, vì đó là những lúc "
            "duy nhất số dư được biết chắc. Nối trơn giữa các điểm sẽ vẽ ra một "
            "đường mà tài khoản chưa bao giờ thật sự đi qua.",
            "The equity curve has a point at each trade exit, because those are "
            "the only moments the balance is actually known. Smoothing between "
            "them would draw a line the account never traced.",
        ),
    }
