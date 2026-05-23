from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_research_engine.portfolio.risk import summarize_equity_curve

_TRADES_LEDGER_COLUMNS = [
    "run_id", "strategy_id", "symbol", "trade_date", "side", "quantity",
    "lot_count", "price_raw", "price_executed", "notional", "commission",
    "stamp_tax", "transfer_fee", "slippage_amount", "total_cost",
    "realized_pnl", "cash_after", "position_after", "order_reason", "status",
]

_ROUND_TRIPS_COLUMNS = [
    "run_id", "strategy_id", "symbol", "entry_date", "exit_date",
    "holding_days", "entry_price", "exit_price", "quantity",
    "entry_notional", "exit_notional", "gross_pnl", "net_pnl",
    "gross_return", "net_return", "total_cost", "exit_reason",
    "max_favorable_return", "max_adverse_return",
]

_SYMBOL_PERFORMANCE_COLUMNS = [
    "symbol", "board", "industry", "trade_count", "open_trade_count",
    "win_count", "loss_count", "win_rate", "gross_profit", "gross_loss",
    "net_profit", "profit_factor", "expectancy", "strategy_total_return",
    "buy_hold_return", "excess_return_vs_buy_hold", "sharpe", "sortino",
    "information_ratio_vs_buy_hold", "max_drawdown", "turnover", "total_cost",
    "failed_order_count",
]

_EQUITY_CURVE_COLUMNS = [
    "trade_date", "cash", "market_value", "total_equity",
    "daily_return", "cumulative_return", "position_count", "turnover",
]

_DRAWDOWN_CURVE_COLUMNS = [
    "trade_date", "total_equity", "running_peak", "drawdown",
    "drawdown_pct", "drawdown_duration_days",
]

_EXCEL_SHEET_NAMES = [
    "Overview", "Performance", "TradesLedger", "RoundTrips",
    "SymbolPerformance", "EquityCurve", "DrawdownCurve",
    "TradeAnalysis", "CapitalUsage", "Artifacts",
]


def build_trades_ledger(
    results: dict[str, Any] | pd.DataFrame,
    run_id: str | None = None,
    strategy_id: str | None = None,
    engine_mode: str = "batch",
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if engine_mode == "shared_cash":
        orders: pd.DataFrame = results  # type: ignore[assignment]
        if orders.empty:
            return pd.DataFrame(columns=_TRADES_LEDGER_COLUMNS)
        for record in orders.to_dict("records"):
            side = str(record.get("side", ""))
            rows.append({
                "run_id": run_id,
                "strategy_id": strategy_id,
                "symbol": record.get("symbol"),
                "trade_date": _to_date(record.get("trade_date")),
                "side": side,
                "quantity": record.get("quantity"),
                "lot_count": None,
                "price_raw": record.get("price"),
                "price_executed": record.get("price"),
                "notional": record.get("notional"),
                "commission": None,
                "stamp_tax": None,
                "transfer_fee": None,
                "slippage_amount": None,
                "total_cost": record.get("cost"),
                "realized_pnl": None,
                "cash_after": None,
                "position_after": None,
                "order_reason": record.get("reason"),
                "status": "filled",
            })
    else:
        for symbol, single_result in results.items():  # type: ignore[union-attr]
            orders = getattr(single_result, "orders", None)
            if orders is None or (hasattr(orders, "empty") and orders.empty):
                continue
            for record in orders.to_dict("records"):
                side = str(record.get("side", ""))
                rows.append({
                    "run_id": run_id,
                    "strategy_id": strategy_id,
                    "symbol": record.get("symbol", symbol),
                    "trade_date": _to_date(record.get("trade_date")),
                    "side": side,
                    "quantity": record.get("quantity"),
                    "lot_count": None,
                    "price_raw": record.get("price"),
                    "price_executed": record.get("price"),
                    "notional": record.get("notional"),
                    "commission": None,
                    "stamp_tax": None,
                    "transfer_fee": None,
                    "slippage_amount": None,
                    "total_cost": record.get("cost"),
                    "realized_pnl": None,
                    "cash_after": None,
                    "position_after": None,
                    "order_reason": None,
                    "status": "filled",
                })
    if not rows:
        return pd.DataFrame(columns=_TRADES_LEDGER_COLUMNS)
    return pd.DataFrame(rows, columns=_TRADES_LEDGER_COLUMNS)


def build_round_trips(
    results: dict[str, Any] | pd.DataFrame,
    run_id: str | None = None,
    strategy_id: str | None = None,
    engine_mode: str = "batch",
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if engine_mode == "shared_cash":
        trades: pd.DataFrame = results  # type: ignore[assignment]
        if trades.empty:
            return pd.DataFrame(columns=_ROUND_TRIPS_COLUMNS)
        for record in trades.to_dict("records"):
            entry_date = _to_date(record.get("entry_date"))
            exit_date = _to_date(record.get("exit_date"))
            holding_days = None
            if entry_date is not None and exit_date is not None:
                try:
                    holding_days = int((pd.Timestamp(exit_date) - pd.Timestamp(entry_date)).days)
                except Exception:
                    holding_days = None
            quantity = record.get("quantity")
            entry_price = record.get("entry_price")
            exit_price = record.get("exit_price")
            entry_notional = _safe_float(quantity) * _safe_float(entry_price) if quantity is not None and entry_price is not None else None
            exit_notional = _safe_float(quantity) * _safe_float(exit_price) if quantity is not None and exit_price is not None else None
            gross_pnl = record.get("gross_pnl")
            net_pnl = record.get("net_pnl")
            gross_return = _safe_float(gross_pnl) / _safe_float(entry_notional) if entry_notional and gross_pnl is not None else None
            net_return = _safe_float(net_pnl) / _safe_float(entry_notional) if entry_notional and net_pnl is not None else None
            rows.append({
                "run_id": run_id,
                "strategy_id": strategy_id,
                "symbol": record.get("symbol"),
                "entry_date": entry_date,
                "exit_date": exit_date,
                "holding_days": holding_days,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "quantity": quantity,
                "entry_notional": entry_notional,
                "exit_notional": exit_notional,
                "gross_pnl": gross_pnl,
                "net_pnl": net_pnl,
                "gross_return": gross_return,
                "net_return": net_return,
                "total_cost": record.get("cost"),
                "exit_reason": record.get("exit_reason"),
                "max_favorable_return": None,
                "max_adverse_return": None,
            })
    else:
        for symbol, single_result in results.items():  # type: ignore[union-attr]
            trades = getattr(single_result, "trades", None)
            if trades is None or (hasattr(trades, "empty") and trades.empty):
                continue
            for record in trades.to_dict("records"):
                entry_date = _to_date(record.get("entry_date"))
                exit_date = _to_date(record.get("exit_date"))
                holding_days = None
                if entry_date is not None and exit_date is not None:
                    try:
                        holding_days = int((pd.Timestamp(exit_date) - pd.Timestamp(entry_date)).days)
                    except Exception:
                        holding_days = None
                quantity = record.get("quantity")
                entry_price = record.get("entry_price")
                exit_price = record.get("exit_price")
                entry_notional = _safe_float(quantity) * _safe_float(entry_price) if quantity is not None and entry_price is not None else None
                exit_notional = _safe_float(quantity) * _safe_float(exit_price) if quantity is not None and exit_price is not None else None
                gross_pnl = record.get("gross_pnl")
                net_pnl = record.get("net_pnl")
                gross_return = _safe_float(gross_pnl) / _safe_float(entry_notional) if entry_notional and gross_pnl is not None else None
                net_return = _safe_float(net_pnl) / _safe_float(entry_notional) if entry_notional and net_pnl is not None else None
                rows.append({
                    "run_id": run_id,
                    "strategy_id": strategy_id,
                    "symbol": record.get("symbol", symbol),
                    "entry_date": entry_date,
                    "exit_date": exit_date,
                    "holding_days": holding_days,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "quantity": quantity,
                    "entry_notional": entry_notional,
                    "exit_notional": exit_notional,
                    "gross_pnl": gross_pnl,
                    "net_pnl": net_pnl,
                    "gross_return": gross_return,
                    "net_return": net_return,
                    "total_cost": record.get("cost"),
                    "exit_reason": record.get("exit_reason"),
                    "max_favorable_return": None,
                    "max_adverse_return": None,
                })
    if not rows:
        return pd.DataFrame(columns=_ROUND_TRIPS_COLUMNS)
    return pd.DataFrame(rows, columns=_ROUND_TRIPS_COLUMNS)


def build_symbol_performance(
    summary: pd.DataFrame | None = None,
    results: dict[str, Any] | None = None,
    engine_mode: str = "batch",
    round_trips: pd.DataFrame | None = None,
    orders: pd.DataFrame | None = None,
    failed_orders: pd.DataFrame | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if engine_mode == "shared_cash":
        rt = round_trips if round_trips is not None else pd.DataFrame()
        od = orders if orders is not None else pd.DataFrame()
        fo = failed_orders if failed_orders is not None else pd.DataFrame()
        if rt.empty:
            return pd.DataFrame(columns=_SYMBOL_PERFORMANCE_COLUMNS)
        symbols = sorted(rt["symbol"].dropna().unique())
        failed_by_symbol: dict[str, int] = {}
        if not fo.empty and "symbol" in fo.columns:
            failed_by_symbol = fo.groupby("symbol").size().to_dict()
        for symbol in symbols:
            sym_trades = rt[rt["symbol"] == symbol]
            trade_count = len(sym_trades)
            win_mask = sym_trades["net_pnl"] > 0
            loss_mask = sym_trades["net_pnl"] < 0
            win_count = int(win_mask.sum())
            loss_count = int(loss_mask.sum())
            win_rate = win_count / trade_count if trade_count > 0 else None
            gross_profit = float(sym_trades.loc[win_mask, "gross_pnl"].sum()) if win_count > 0 else 0.0
            gross_loss = float(sym_trades.loc[loss_mask, "gross_pnl"].sum()) if loss_count > 0 else 0.0
            net_profit = float(sym_trades["net_pnl"].sum())
            profit_factor = abs(gross_profit / gross_loss) if gross_loss != 0 else None
            positive_pnl = sym_trades.loc[win_mask, "net_pnl"]
            negative_pnl = sym_trades.loc[loss_mask, "net_pnl"]
            avg_win = float(positive_pnl.mean()) if not positive_pnl.empty else 0.0
            avg_loss = float(negative_pnl.mean()) if not negative_pnl.empty else 0.0
            expectancy = None
            if win_rate is not None and trade_count > 0:
                expectancy = float(win_rate) * avg_win - (1.0 - float(win_rate)) * abs(avg_loss)
            open_trades = od[(od["symbol"] == symbol) & (od.get("reason") == "entry_exit")] if not od.empty else pd.DataFrame()
            open_trade_count = len(open_trades) - (2 * trade_count) if not open_trades.empty else None
            rows.append({
                "symbol": str(symbol),
                "board": None,
                "industry": None,
                "trade_count": trade_count,
                "open_trade_count": open_trade_count,
                "win_count": win_count,
                "loss_count": loss_count,
                "win_rate": win_rate,
                "gross_profit": gross_profit,
                "gross_loss": gross_loss,
                "net_profit": net_profit,
                "profit_factor": profit_factor,
                "expectancy": expectancy,
                "strategy_total_return": None,
                "buy_hold_return": None,
                "excess_return_vs_buy_hold": None,
                "sharpe": None,
                "sortino": None,
                "information_ratio_vs_buy_hold": None,
                "max_drawdown": None,
                "turnover": None,
                "total_cost": float(sym_trades["total_cost"].sum()) if "total_cost" in sym_trades.columns else None,
                "failed_order_count": failed_by_symbol.get(symbol, 0),
            })
    else:
        for record in summary.to_dict("records"):  # type: ignore[union-attr]
            symbol = str(record.get("symbol", ""))
            single_result = results.get(symbol) if results is not None else None  # type: ignore[union-attr]
            equity_curve = getattr(single_result, "equity_curve", None) if single_result is not None else None
            risk_metrics = {}
            if equity_curve is not None and not equity_curve.empty and "total_equity" in equity_curve.columns:
                risk_metrics = summarize_equity_curve(equity_curve)

            win_count = record.get("win_count")
            loss_count = record.get("loss_count")
            trade_count = record.get("trade_count")
            win_rate = record.get("win_rate")
            net_profit = record.get("net_profit", record.get("total_return"))

            profit_factor = None
            gross_profit = record.get("gross_profit")
            gross_loss = record.get("gross_loss")
            if gross_profit is not None and gross_loss is not None and gross_loss != 0:
                profit_factor = abs(_safe_float(gross_profit) / _safe_float(gross_loss))

            expectancy = None
            if win_rate is not None and trade_count is not None and trade_count > 0:
                avg_win = _safe_float(record.get("avg_win", 0.0))
                avg_loss = _safe_float(record.get("avg_loss", 0.0))
                if avg_win is not None and avg_loss is not None:
                    expectancy = float(win_rate) * avg_win - (1.0 - float(win_rate)) * abs(avg_loss)

            rows.append({
                "symbol": symbol,
                "board": record.get("board"),
                "industry": record.get("industry"),
                "trade_count": trade_count,
                "open_trade_count": record.get("open_trade_count"),
                "win_count": win_count,
                "loss_count": loss_count,
                "win_rate": win_rate,
                "gross_profit": gross_profit,
                "gross_loss": gross_loss,
                "net_profit": net_profit,
                "profit_factor": profit_factor,
                "expectancy": expectancy,
                "strategy_total_return": record.get("total_return"),
                "buy_hold_return": record.get("buy_hold_return"),
                "excess_return_vs_buy_hold": record.get("excess_return_vs_buy_hold"),
                "sharpe": risk_metrics.get("sharpe"),
                "sortino": None,
                "information_ratio_vs_buy_hold": record.get("information_ratio_vs_buy_hold"),
                "max_drawdown": record.get("max_drawdown") or risk_metrics.get("max_drawdown"),
                "turnover": record.get("turnover"),
                "total_cost": record.get("total_cost"),
                "failed_order_count": record.get("failed_order_count", 0),
            })
    if not rows:
        return pd.DataFrame(columns=_SYMBOL_PERFORMANCE_COLUMNS)
    return pd.DataFrame(rows, columns=_SYMBOL_PERFORMANCE_COLUMNS)


def build_full_market_equity_curve(
    results: dict[str, Any] | pd.DataFrame,
    engine_mode: str = "batch",
) -> pd.DataFrame:
    if engine_mode == "shared_cash":
        eq: pd.DataFrame = results.copy()  # type: ignore[assignment, union-attr]
        if eq.empty or "total_equity" not in eq.columns:
            return pd.DataFrame(columns=_EQUITY_CURVE_COLUMNS)
        eq["trade_date"] = pd.to_datetime(eq["trade_date"])
        eq = eq.sort_values("trade_date")
        daily_returns = []
        cumulative = 1.0
        prev_equity = None
        for _, row in eq.iterrows():
            te = _safe_float(row.get("total_equity"))
            dr = None
            if prev_equity is not None and prev_equity > 0:
                dr = (te / prev_equity) - 1.0
            daily_returns.append(dr)
            cumulative *= (1.0 + (dr or 0.0))
            prev_equity = te
        return pd.DataFrame({
            "trade_date": eq["trade_date"],
            "cash": eq.get("cash", 0.0),
            "market_value": eq.get("market_value", 0.0),
            "total_equity": eq["total_equity"],
            "daily_return": daily_returns,
            "cumulative_return": [cumulative - 1.0] * len(eq),
            "position_count": eq.get("position_count", 0),
            "turnover": None,
        }, columns=_EQUITY_CURVE_COLUMNS)

    # batch mode
    all_dates: set[pd.Timestamp] = set()
    symbol_curves: dict[str, pd.DataFrame] = {}
    for symbol, single_result in results.items():  # type: ignore[union-attr]
        eq = getattr(single_result, "equity_curve", None)
        if eq is None or eq.empty or "trade_date" not in eq.columns:
            continue
        eq = eq.copy()
        eq["trade_date"] = pd.to_datetime(eq["trade_date"])
        eq = eq.sort_values("trade_date")
        symbol_curves[symbol] = eq
        all_dates.update(eq["trade_date"].dropna().tolist())

    if not all_dates:
        return pd.DataFrame(columns=_EQUITY_CURVE_COLUMNS)

    dates = sorted(all_dates)
    rows: list[dict[str, Any]] = []
    cumulative_return = 1.0
    prev_total_equity: float | None = None

    for date in dates:
        total_equity = 0.0
        cash = 0.0
        market_value = 0.0
        position_count = 0
        for eq in symbol_curves.values():
            day_data = eq[eq["trade_date"] == date]
            if day_data.empty:
                continue
            total_equity += _safe_float(day_data["total_equity"].iloc[0])
            if "cash" in day_data.columns:
                cash += _safe_float(day_data["cash"].iloc[0])
            if "market_value" in day_data.columns:
                market_value += _safe_float(day_data["market_value"].iloc[0])
            pos_qty = _safe_float(day_data.get("position_quantity", pd.Series([0])).iloc[0])
            if pos_qty is not None and pos_qty > 0:
                position_count += 1
        daily_return = None
        if prev_total_equity is not None and prev_total_equity > 0:
            daily_return = (total_equity / prev_total_equity) - 1.0
        cumulative_return *= (1.0 + (daily_return or 0.0))

        rows.append({
            "trade_date": date,
            "cash": cash,
            "market_value": market_value,
            "total_equity": total_equity,
            "daily_return": daily_return,
            "cumulative_return": cumulative_return - 1.0,
            "position_count": position_count,
            "turnover": None,
        })
        prev_total_equity = total_equity

    return pd.DataFrame(rows, columns=_EQUITY_CURVE_COLUMNS)


def build_drawdown_curve(equity_curve: pd.DataFrame) -> pd.DataFrame:
    if equity_curve.empty or "total_equity" not in equity_curve.columns:
        return pd.DataFrame(columns=_DRAWDOWN_CURVE_COLUMNS)

    eq = equity_curve.copy()
    eq["running_peak"] = eq["total_equity"].cummax()
    eq["drawdown"] = eq["total_equity"] - eq["running_peak"]
    eq["drawdown_pct"] = np.where(
        eq["running_peak"] > 0,
        eq["drawdown"] / eq["running_peak"],
        0.0,
    )

    duration_days: list[int | None] = []
    current_duration = 0
    for _, row in eq.iterrows():
        dd_val = float(row["drawdown"])
        if dd_val < 0:
            current_duration += 1
        elif dd_val == 0:
            current_duration = 0
        else:
            current_duration = 0
        duration_days.append(current_duration if current_duration > 0 else 0)

    return pd.DataFrame({
        "trade_date": eq["trade_date"],
        "total_equity": eq["total_equity"],
        "running_peak": eq["running_peak"],
        "drawdown": eq["drawdown"],
        "drawdown_pct": eq["drawdown_pct"],
        "drawdown_duration_days": duration_days,
    }, columns=_DRAWDOWN_CURVE_COLUMNS)


def build_strategy_performance(
    summary_metrics: dict[str, Any],
    summary: pd.DataFrame | None = None,
    round_trips: pd.DataFrame | None = None,
    equity_curve: pd.DataFrame | None = None,
    run_id: str | None = None,
    strategy_id: str | None = None,
    strategy_name: str | None = None,
    strategy_family: str | None = None,
    engine_mode: str = "batch",
) -> dict[str, Any]:
    rt = round_trips if round_trips is not None else pd.DataFrame()
    eq = equity_curve if equity_curve is not None else pd.DataFrame()

    risk = {}
    if not eq.empty and "total_equity" in eq.columns:
        risk = summarize_equity_curve(eq)

    win_count = int((rt["net_pnl"] > 0).sum()) if not rt.empty else 0
    loss_count = int((rt["net_pnl"] < 0).sum()) if not rt.empty else 0
    total_trades = len(rt)

    positive_pnl = rt[rt["net_pnl"] > 0]["net_pnl"] if not rt.empty else pd.Series(dtype=float)
    negative_pnl = rt[rt["net_pnl"] < 0]["net_pnl"] if not rt.empty else pd.Series(dtype=float)

    sortino = None
    if not eq.empty and "daily_return" in eq.columns:
        returns = eq["daily_return"].dropna()
        downside = returns[returns < 0]
        if len(returns) > 1 and len(downside) > 0:
            downside_std = float(downside.std() * (252 ** 0.5))
            ann_return = risk.get("annualized_return")
            if ann_return is not None and downside_std > 0:
                sortino = float(ann_return / downside_std)

    if engine_mode == "shared_cash":
        best_symbols: list[dict[str, Any]] = []
        worst_symbols: list[dict[str, Any]] = []
        if not rt.empty and "symbol" in rt.columns:
            sym_pnl = rt.groupby("symbol")["net_pnl"].sum().dropna().sort_values()
            sym_pnl = sym_pnl[sym_pnl != 0]
            if not sym_pnl.empty:
                worst_symbols = [{"symbol": str(k), "total_return": _json_ready(v)} for k, v in sym_pnl.head(3).items()]
                best_symbols = [{"symbol": str(k), "total_return": _json_ready(v)} for k, v in sym_pnl.tail(3).items()][::-1]

        return {
            "run_id": run_id,
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "strategy_family": strategy_family,
            "date_start": summary_metrics.get("date_start"),
            "date_end": summary_metrics.get("date_end"),
            "symbol_count": summary_metrics.get("symbol_count"),
            "traded_symbol_count": summary_metrics.get("traded_symbol_count"),
            "total_trade_count": total_trades,
            "open_trade_count": None,
            "winning_trade_count": win_count,
            "losing_trade_count": loss_count,
            "win_rate": win_count / total_trades if total_trades > 0 else None,
            "gross_profit": float(positive_pnl.sum()) if not positive_pnl.empty else 0.0,
            "gross_loss": float(negative_pnl.sum()) if not negative_pnl.empty else 0.0,
            "net_profit": float(rt["net_pnl"].sum()) if not rt.empty else 0.0,
            "profit_factor": abs(float(positive_pnl.sum()) / float(negative_pnl.sum())) if not negative_pnl.empty and negative_pnl.sum() != 0 else None,
            "expectancy": float(rt["net_pnl"].mean()) if not rt.empty else None,
            "recovery_factor": risk.get("return_drawdown_ratio"),
            "sharpe": summary_metrics.get("sharpe") or risk.get("sharpe"),
            "sortino": sortino,
            "information_ratio": None,
            "strategy_total_return": summary_metrics.get("total_return") or risk.get("total_return"),
            "buy_hold_return": None,
            "excess_return_vs_buy_hold": None,
            "positive_symbol_rate": None,
            "mean_symbol_return": None,
            "median_symbol_return": None,
            "max_drawdown": summary_metrics.get("max_drawdown") or risk.get("max_drawdown"),
            "max_drawdown_duration_days": summary_metrics.get("max_drawdown_duration_days") or risk.get("max_drawdown_duration_days"),
            "total_cost": summary_metrics.get("total_cost"),
            "largest_winning_trade": float(positive_pnl.max()) if not positive_pnl.empty else None,
            "largest_losing_trade": float(negative_pnl.min()) if not negative_pnl.empty else None,
            "average_winning_trade": float(positive_pnl.mean()) if not positive_pnl.empty else None,
            "average_losing_trade": float(negative_pnl.mean()) if not negative_pnl.empty else None,
            "average_win_loss_ratio": _safe_div(float(positive_pnl.mean()), abs(float(negative_pnl.mean()))) if not positive_pnl.empty and not negative_pnl.empty else None,
            "max_consecutive_wins": _max_consecutive(rt, "net_pnl", "win"),
            "max_consecutive_losses": _max_consecutive(rt, "net_pnl", "loss"),
            "average_bars_in_trade": float(rt["holding_days"].mean()) if not rt.empty else None,
            "average_bars_in_winning_trades": float(positive_pnl.index.to_series().map(
                lambda i: rt.loc[i, "holding_days"] if i in rt.index else None
            ).mean()) if not positive_pnl.empty and "holding_days" in rt.columns else None,
            "average_bars_in_losing_trades": float(negative_pnl.index.to_series().map(
                lambda i: rt.loc[i, "holding_days"] if i in rt.index else None
            ).mean()) if not negative_pnl.empty and "holding_days" in rt.columns else None,
            "best_symbols": best_symbols,
            "worst_symbols": worst_symbols,
        }

    # batch mode
    return {
        "run_id": run_id,
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "strategy_family": strategy_family,
        "date_start": summary_metrics.get("date_start"),
        "date_end": summary_metrics.get("date_end"),
        "symbol_count": summary_metrics.get("symbol_count", len(summary) if summary is not None else 0),
        "traded_symbol_count": summary_metrics.get("traded_symbol_count"),
        "total_trade_count": total_trades,
        "open_trade_count": None,
        "winning_trade_count": win_count,
        "losing_trade_count": loss_count,
        "win_rate": win_count / total_trades if total_trades > 0 else None,
        "gross_profit": float(positive_pnl.sum()) if not positive_pnl.empty else 0.0,
        "gross_loss": float(negative_pnl.sum()) if not negative_pnl.empty else 0.0,
        "net_profit": float(rt["net_pnl"].sum()) if not rt.empty else 0.0,
        "profit_factor": abs(float(positive_pnl.sum()) / float(negative_pnl.sum())) if not negative_pnl.empty and negative_pnl.sum() != 0 else None,
        "expectancy": float(rt["net_pnl"].mean()) if not rt.empty else None,
        "recovery_factor": risk.get("return_drawdown_ratio"),
        "sharpe": risk.get("sharpe"),
        "sortino": sortino,
        "information_ratio": None,
        "strategy_total_return": risk.get("total_return"),
        "buy_hold_return": summary_metrics.get("buy_hold_return"),
        "excess_return_vs_buy_hold": summary_metrics.get("excess_return_vs_buy_hold"),
        "positive_symbol_rate": summary_metrics.get("positive_return_symbol_rate"),
        "mean_symbol_return": summary_metrics.get("mean_total_return"),
        "median_symbol_return": summary_metrics.get("median_total_return"),
        "max_drawdown": risk.get("max_drawdown"),
        "max_drawdown_duration_days": risk.get("max_drawdown_duration_days"),
        "total_cost": summary_metrics.get("total_cost"),
        "largest_winning_trade": float(positive_pnl.max()) if not positive_pnl.empty else None,
        "largest_losing_trade": float(negative_pnl.min()) if not negative_pnl.empty else None,
        "average_winning_trade": float(positive_pnl.mean()) if not positive_pnl.empty else None,
        "average_losing_trade": float(negative_pnl.mean()) if not negative_pnl.empty else None,
        "average_win_loss_ratio": _safe_div(float(positive_pnl.mean()), abs(float(negative_pnl.mean()))) if not positive_pnl.empty and not negative_pnl.empty else None,
        "max_consecutive_wins": _max_consecutive(rt, "net_pnl", "win"),
        "max_consecutive_losses": _max_consecutive(rt, "net_pnl", "loss"),
        "average_bars_in_trade": float(rt["holding_days"].mean()) if not rt.empty else None,
        "average_bars_in_winning_trades": float(positive_pnl.index.to_series().map(
            lambda i: rt.loc[i, "holding_days"] if i in rt.index else None
        ).mean()) if not positive_pnl.empty and "holding_days" in rt.columns else None,
        "average_bars_in_losing_trades": float(negative_pnl.index.to_series().map(
            lambda i: rt.loc[i, "holding_days"] if i in rt.index else None
        ).mean()) if not negative_pnl.empty and "holding_days" in rt.columns else None,
        "best_symbols": _best_symbols(summary, "total_return", 3) if summary is not None else [],
        "worst_symbols": _worst_symbols(summary, "total_return", 3) if summary is not None else [],
    }


def build_trade_analysis(round_trips: pd.DataFrame) -> dict[str, Any]:
    if round_trips.empty:
        return {
            "pnl_distribution_bins": [],
            "win_loss_counts": {"win": 0, "loss": 0},
            "percent_profitable": None,
            "average_pnl": None,
            "average_winning_trade": None,
            "average_losing_trade": None,
            "average_win_loss_ratio": None,
            "largest_winning_trade": None,
            "largest_losing_trade": None,
            "outlier_count": 0,
            "outlier_pnl": 0.0,
            "average_bars_in_trade": None,
            "average_bars_in_winning_trades": None,
            "average_bars_in_losing_trades": None,
        }

    pnl = round_trips["net_pnl"].dropna()
    positive = pnl[pnl > 0]
    negative = pnl[pnl < 0]
    total = len(pnl)
    wins = len(positive)
    losses = len(negative)

    bins: list[dict[str, Any]] = []
    if total > 0:
        pnl_min = float(pnl.min())
        pnl_max = float(pnl.max())
        bin_count = min(10, total)
        if pnl_max > pnl_min and bin_count > 0:
            bin_edges = np.linspace(pnl_min, pnl_max, bin_count + 1)
            bin_counts, _ = np.histogram(pnl, bins=bin_edges)
            for i in range(bin_count):
                bins.append({
                    "label": f"{bin_edges[i]:.2f} – {bin_edges[i + 1]:.2f}",
                    "count": int(bin_counts[i]),
                })

    mean_val = float(pnl.mean())
    std_val = float(pnl.std()) if len(pnl) > 1 else 0.0
    outlier_threshold = mean_val + 3 * std_val if std_val > 0 else None
    outliers = pnl[pnl > outlier_threshold] if outlier_threshold is not None else pd.Series(dtype=float)

    return {
        "pnl_distribution_bins": bins,
        "win_loss_counts": {"win": wins, "loss": losses},
        "percent_profitable": wins / total if total > 0 else None,
        "average_pnl": mean_val if total > 0 else None,
        "average_winning_trade": float(positive.mean()) if not positive.empty else None,
        "average_losing_trade": float(negative.mean()) if not negative.empty else None,
        "average_win_loss_ratio": _safe_div(float(positive.mean()), abs(float(negative.mean()))) if not positive.empty and not negative.empty else None,
        "largest_winning_trade": float(positive.max()) if not positive.empty else None,
        "largest_losing_trade": float(negative.min()) if not negative.empty else None,
        "outlier_count": len(outliers),
        "outlier_pnl": float(outliers.sum()),
        "average_bars_in_trade": float(round_trips["holding_days"].mean()) if "holding_days" in round_trips.columns else None,
        "average_bars_in_winning_trades": float(round_trips.loc[positive.index, "holding_days"].mean()) if not positive.empty and "holding_days" in round_trips.columns else None,
        "average_bars_in_losing_trades": float(round_trips.loc[negative.index, "holding_days"].mean()) if not negative.empty and "holding_days" in round_trips.columns else None,
    }


def build_capital_usage(
    equity_curve: pd.DataFrame,
    strategy_perf: dict[str, Any],
) -> dict[str, Any]:
    cagr = None
    if not equity_curve.empty and "total_equity" in equity_curve.columns:
        start_eq = float(equity_curve["total_equity"].iloc[0])
        end_eq = float(equity_curve["total_equity"].iloc[-1])
        if start_eq > 0:
            periods = max(len(equity_curve) - 1, 1)
            years = periods / 252.0
            if years > 0 and end_eq > 0:
                cagr = float((end_eq / start_eq) ** (1.0 / years) - 1.0)

    return {
        "cagr": cagr,
        "initial_capital_return": strategy_perf.get("strategy_total_return"),
        "required_account_size": None,
        "account_size_return": None,
        "net_profit_as_pct_of_max_loss": _safe_div(
            strategy_perf.get("net_profit"),
            abs(strategy_perf.get("max_drawdown") or 0.0),
        ),
        "average_margin_used": None,
        "maximum_margin_used": None,
        "margin_efficiency": None,
        "margin_call_count": 0,
    }


def write_full_market_excel(
    output_dir: Path,
    overview: dict[str, Any],
    trades_ledger: pd.DataFrame,
    round_trips: pd.DataFrame,
    symbol_perf: pd.DataFrame,
    equity: pd.DataFrame,
    drawdown: pd.DataFrame,
    trade_analysis: dict[str, Any],
    capital_usage: dict[str, Any],
) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    header_font = Font(bold=True)

    def _write_df_sheet(ws, df: pd.DataFrame) -> None:
        ws.append(list(df.columns))
        for cell in ws[1]:
            cell.font = header_font
        for _, row in df.iterrows():
            ws.append([_excel_value(v) for v in row])

    def _write_kv_sheet(ws, data: dict[str, Any]) -> None:
        ws.append(["Key", "Value"])
        for cell in ws[1]:
            cell.font = header_font
        for key, value in data.items():
            ws.append([key, _excel_value(value)])

    # Overview
    _write_kv_sheet(wb.active, overview)
    wb.active.title = "Overview"

    # Performance (strategy_performance is embedded in Overview for now; separate view)
    ws_perf = wb.create_sheet("Performance")
    _write_kv_sheet(ws_perf, {})

    # TradesLedger
    ws_ledger = wb.create_sheet("TradesLedger")
    _write_df_sheet(ws_ledger, trades_ledger)

    # RoundTrips
    ws_rt = wb.create_sheet("RoundTrips")
    _write_df_sheet(ws_rt, round_trips)

    # SymbolPerformance
    ws_sp = wb.create_sheet("SymbolPerformance")
    _write_df_sheet(ws_sp, symbol_perf)

    # EquityCurve
    ws_eq = wb.create_sheet("EquityCurve")
    _write_df_sheet(ws_eq, equity)

    # DrawdownCurve
    ws_dd = wb.create_sheet("DrawdownCurve")
    _write_df_sheet(ws_dd, drawdown)

    # TradeAnalysis
    ws_ta = wb.create_sheet("TradeAnalysis")
    _write_kv_sheet(ws_ta, trade_analysis)

    # CapitalUsage
    ws_cu = wb.create_sheet("CapitalUsage")
    _write_kv_sheet(ws_cu, capital_usage)

    # Artifacts
    ws_art = wb.create_sheet("Artifacts")
    ws_art.append(["Artifact", "Description"])
    for cell in ws_art[1]:
        cell.font = header_font
    for name, desc in [
        ("backtest_report.xlsx", "Full-market backtest report workbook"),
        ("trades_ledger.csv", "Transaction ledger, all symbols"),
        ("round_trips.csv", "Completed entry-to-exit trade cycles"),
        ("symbol_performance.csv", "Per-symbol performance summary"),
        ("strategy_performance.json", "Aggregate strategy performance"),
        ("equity_curve.csv", "Full-market equity curve"),
        ("drawdown_curve.csv", "Daily drawdown curve"),
        ("trade_analysis.json", "TradingView-style trade analysis"),
        ("capital_usage.json", "Capital and margin usage"),
    ]:
        ws_art.append([name, desc])

    path = output_dir / "backtest_report.xlsx"
    wb.save(str(path))
    return path


def write_full_market_report(
    result: Any,
    output_dir: str | Path,
    run_request: dict[str, Any] | None = None,
    run_id: str | None = None,
    engine_mode: str = "batch",
) -> dict[str, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    strategy_id = None
    strategy_name = None
    strategy_family = None
    if run_request is not None:
        req = run_request.get("request", {})
        strategy_id = req.get("strategy_id")
        strategy_name = req.get("strategy_name")
        strategy_family = req.get("strategy_family")

    if engine_mode == "shared_cash":
        orders = getattr(result, "orders", pd.DataFrame())
        trades = getattr(result, "trades", pd.DataFrame())
        eq_curve = getattr(result, "equity_curve", pd.DataFrame())
        shared_summary = getattr(result, "summary", {})

        trades_ledger = build_trades_ledger(orders, run_id=run_id, strategy_id=strategy_id, engine_mode="shared_cash")
        round_trips = build_round_trips(trades, run_id=run_id, strategy_id=strategy_id, engine_mode="shared_cash")
        symbol_perf = build_symbol_performance(
            engine_mode="shared_cash", round_trips=round_trips, orders=orders,
            failed_orders=getattr(result, "failed_orders", pd.DataFrame()),
        )
        fm_equity_curve = build_full_market_equity_curve(eq_curve, engine_mode="shared_cash")
        drawdown_curve = build_drawdown_curve(fm_equity_curve)
        strategy_perf = build_strategy_performance(
            shared_summary, round_trips=round_trips, equity_curve=fm_equity_curve,
            run_id=run_id, strategy_id=strategy_id,
            strategy_name=strategy_name, strategy_family=strategy_family,
            engine_mode="shared_cash",
        )
        trade_analysis = build_trade_analysis(round_trips)
        capital_usage = build_capital_usage(fm_equity_curve, strategy_perf)

        symbol_count = 0
        if not orders.empty and "symbol" in orders.columns:
            symbol_count = orders["symbol"].nunique()

        overview: dict[str, Any] = {
            "run_id": run_id,
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "strategy_family": strategy_family,
            "strategy_description": None,
            "engine_mode": "shared_cash",
            "date_start": shared_summary.get("date_start"),
            "date_end": shared_summary.get("date_end"),
            "market": "ashare",
            "frequency": "daily",
            "universe": "all_a",
            "symbol_count": shared_summary.get("symbol_count", symbol_count),
            "traded_symbol_count": shared_summary.get("traded_symbol_count"),
            "initial_cash": shared_summary.get("initial_cash"),
            "market_profile": shared_summary.get("market_profile"),
            "entry_execution": "t_plus_1_open",
            "exit_execution": "t_plus_1_open",
            "cost_model": "ashare_default",
            "slippage_model": "percent",
            "factor_requirements": None,
            "strategy_source_path": run_request.get("strategy_path") if run_request else None,
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        }

        paths: dict[str, Path] = {
            "trades_ledger": directory / "trades_ledger.csv",
            "round_trips": directory / "round_trips.csv",
            "symbol_performance": directory / "symbol_performance.csv",
            "strategy_performance": directory / "strategy_performance.json",
            "full_market_equity_curve": directory / "full_market_equity_curve.csv",
            "drawdown_curve": directory / "drawdown_curve.csv",
            "trade_analysis": directory / "trade_analysis.json",
            "capital_usage": directory / "capital_usage.json",
            "backtest_report": write_full_market_excel(
                directory, overview, trades_ledger, round_trips, symbol_perf,
                fm_equity_curve, drawdown_curve, trade_analysis, capital_usage,
            ),
        }

        trades_ledger.to_csv(paths["trades_ledger"], index=False)
        round_trips.to_csv(paths["round_trips"], index=False)
        symbol_perf.to_csv(paths["symbol_performance"], index=False)
        fm_equity_curve.to_csv(paths["full_market_equity_curve"], index=False)
        drawdown_curve.to_csv(paths["drawdown_curve"], index=False)
        paths["strategy_performance"].write_text(
            json.dumps(_json_ready(strategy_perf), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        paths["trade_analysis"].write_text(
            json.dumps(_json_ready(trade_analysis), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        paths["capital_usage"].write_text(
            json.dumps(_json_ready(capital_usage), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        return paths

    # batch mode
    summary = getattr(result, "summary", pd.DataFrame())
    summary_metrics = getattr(result, "summary_metrics", {})
    results = getattr(result, "results", {})

    trades_ledger = build_trades_ledger(results, run_id=run_id, strategy_id=strategy_id)
    round_trips = build_round_trips(results, run_id=run_id, strategy_id=strategy_id)
    symbol_perf = build_symbol_performance(summary, results) if not summary.empty else pd.DataFrame(columns=_SYMBOL_PERFORMANCE_COLUMNS)
    equity_curve = build_full_market_equity_curve(results)
    drawdown_curve = build_drawdown_curve(equity_curve)
    strategy_perf = build_strategy_performance(
        summary_metrics, summary, round_trips, equity_curve,
        run_id=run_id, strategy_id=strategy_id,
        strategy_name=strategy_name, strategy_family=strategy_family,
    )
    trade_analysis = build_trade_analysis(round_trips)
    capital_usage = build_capital_usage(equity_curve, strategy_perf)

    overview: dict[str, Any] = {
        "run_id": run_id,
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "strategy_family": strategy_family,
        "strategy_description": None,
        "engine_mode": "batch",
        "date_start": summary_metrics.get("date_start"),
        "date_end": summary_metrics.get("date_end"),
        "market": "ashare",
        "frequency": "daily",
        "universe": "all_a",
        "symbol_count": summary_metrics.get("symbol_count"),
        "traded_symbol_count": summary_metrics.get("traded_symbol_count"),
        "initial_cash": None,
        "market_profile": summary_metrics.get("market_profile"),
        "entry_execution": "t_plus_1_open",
        "exit_execution": "t_plus_1_open",
        "cost_model": "ashare_default",
        "slippage_model": "percent",
        "factor_requirements": None,
        "strategy_source_path": run_request.get("strategy_path") if run_request else None,
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
    }

    paths: dict[str, Path] = {
        "trades_ledger": directory / "trades_ledger.csv",
        "round_trips": directory / "round_trips.csv",
        "symbol_performance": directory / "symbol_performance.csv",
        "strategy_performance": directory / "strategy_performance.json",
        "equity_curve": directory / "equity_curve.csv",
        "drawdown_curve": directory / "drawdown_curve.csv",
        "trade_analysis": directory / "trade_analysis.json",
        "capital_usage": directory / "capital_usage.json",
        "backtest_report": write_full_market_excel(
            directory, overview, trades_ledger, round_trips, symbol_perf,
            equity_curve, drawdown_curve, trade_analysis, capital_usage,
        ),
    }

    # Write CSV/JSON artifacts
    trades_ledger.to_csv(paths["trades_ledger"], index=False)
    round_trips.to_csv(paths["round_trips"], index=False)
    symbol_perf.to_csv(paths["symbol_performance"], index=False)
    equity_curve.to_csv(paths["equity_curve"], index=False)
    drawdown_curve.to_csv(paths["drawdown_curve"], index=False)
    paths["strategy_performance"].write_text(
        json.dumps(_json_ready(strategy_perf), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    paths["trade_analysis"].write_text(
        json.dumps(_json_ready(trade_analysis), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    paths["capital_usage"].write_text(
        json.dumps(_json_ready(capital_usage), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return paths


# ---- helpers ----


def _to_date(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return pd.Timestamp(value).date().isoformat()
    except Exception:
        return str(value)


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _safe_div(a: float | None, b: float) -> float | None:
    if a is None or b == 0.0:
        return None
    return a / b


def _excel_value(value: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, (int, float, str, bool)):
        return value
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _max_consecutive(frame: pd.DataFrame, column: str, direction: str) -> int:
    if frame.empty or column not in frame.columns:
        return 0
    max_count = 0
    current = 0
    for val in frame[column]:
        if direction == "win" and val > 0:
            current += 1
        elif direction == "loss" and val < 0:
            current += 1
        else:
            max_count = max(max_count, current)
            current = 0
    return max(max_count, current)


def _best_symbols(summary: pd.DataFrame, column: str, n: int) -> list[dict[str, Any]]:
    if summary.empty or column not in summary.columns:
        return []
    top = summary.dropna(subset=[column]).sort_values(column, ascending=False).head(n)
    return [{str(k): _json_ready(v) for k, v in record.items()} for record in top.to_dict("records")]


def _worst_symbols(summary: pd.DataFrame, column: str, n: int) -> list[dict[str, Any]]:
    if summary.empty or column not in summary.columns:
        return []
    bottom = summary.dropna(subset=[column]).sort_values(column, ascending=True).head(n)
    return [{str(k): _json_ready(v) for k, v in record.items()} for record in bottom.to_dict("records")]


def _json_ready(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _json_ready(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_ready(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        if pd.isna(obj):
            return None
        return float(obj)
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj
