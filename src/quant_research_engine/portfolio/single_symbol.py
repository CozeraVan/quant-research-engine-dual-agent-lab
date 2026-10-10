from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant_research_engine.core.models import Order, OrderSide, OrderType
from quant_research_engine.evaluation.signals import evaluate_expression_signal
from quant_research_engine.markets.ashare import AShareMarketProfile


@dataclass(frozen=True)
class SingleSymbolBacktestRequest:
    symbol: str
    initial_cash: float
    entry_signal: str
    holding_days: int
    exit_signal: str | None = None
    entry_price_column: str = "open"
    mark_price_column: str = "close"
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    trailing_stop_pct: float | None = None


@dataclass(frozen=True)
class SingleSymbolBacktestResult:
    orders: pd.DataFrame
    trades: pd.DataFrame
    equity_curve: pd.DataFrame
    failed_orders: pd.DataFrame
    summary: dict[str, float | int | None]


def empty_single_symbol_result(request: SingleSymbolBacktestRequest) -> SingleSymbolBacktestResult:
    """Shared empty-result contract used by both engine implementations."""
    return SingleSymbolBacktestResult(
        orders=pd.DataFrame(),
        trades=pd.DataFrame(),
        equity_curve=pd.DataFrame(),
        failed_orders=pd.DataFrame(),
        summary={
            "initial_cash": request.initial_cash,
            "final_equity": request.initial_cash,
            "total_return": 0.0,
            "trade_count": 0,
            "win_rate": None,
            "total_cost": 0.0,
            "buy_hold_return": None,
            "excess_return_vs_buy_hold": None,
        },
    )


def build_single_symbol_summary(
    request: SingleSymbolBacktestRequest,
    trades: pd.DataFrame,
    equity_curve: pd.DataFrame,
    frame: pd.DataFrame,
) -> dict[str, float | int | None]:
    """Shared summary builder used by both engine implementations."""
    final_equity = request.initial_cash if equity_curve.empty else float(equity_curve.iloc[-1]["total_equity"])
    trade_count = int(len(trades))
    total_cost = 0.0 if trades.empty else float(trades["cost"].sum())
    win_rate = None if trades.empty else float((trades["net_pnl"] > 0).mean())
    total_return = final_equity / request.initial_cash - 1

    buy_hold_return = None
    excess_return_vs_buy_hold = None
    if not frame.empty and request.entry_price_column in frame.columns and request.mark_price_column in frame.columns:
        first_entry_price = float(frame.iloc[0][request.entry_price_column])
        last_mark_price = float(frame.iloc[-1][request.mark_price_column])
        if first_entry_price > 0:
            buy_hold_return = last_mark_price / first_entry_price - 1.0
            excess_return_vs_buy_hold = total_return - buy_hold_return

    return {
        "initial_cash": request.initial_cash,
        "final_equity": final_equity,
        "total_return": total_return,
        "trade_count": trade_count,
        "win_rate": win_rate,
        "total_cost": total_cost,
        "buy_hold_return": buy_hold_return,
        "excess_return_vs_buy_hold": excess_return_vs_buy_hold,
    }


class SingleSymbolBacktestEngine:
    def __init__(self, market_profile: AShareMarketProfile) -> None:
        self.market_profile = market_profile

    def run(self, frame: pd.DataFrame, request: SingleSymbolBacktestRequest) -> SingleSymbolBacktestResult:
        self._validate_request(request)
        working = frame.loc[frame["ts_code"] == request.symbol].copy()
        if working.empty:
            return self._empty_result(request)
        working["trade_date"] = pd.to_datetime(working["trade_date"])
        working = working.sort_values("trade_date").reset_index(drop=True)
        working["entry_signal"] = evaluate_expression_signal(working, request.entry_signal)
        if request.exit_signal is not None:
            working["exit_signal"] = evaluate_expression_signal(working, request.exit_signal)
        first_mark_price = float(working.iloc[0][request.mark_price_column])

        cash = request.initial_cash
        quantity = 0
        entry_index: int | None = None
        entry_price: float | None = None
        entry_date: pd.Timestamp | None = None
        entry_cost = 0.0
        entry_cost_parts: dict[str, float] = {"commission": 0.0, "transfer_fee": 0.0, "stamp_tax": 0.0, "total": 0.0}
        trailing_anchor = 0.0

        orders: list[dict[str, object]] = []
        trades: list[dict[str, object]] = []
        equity_rows: list[dict[str, object]] = []
        failed_orders: list[dict[str, object]] = []

        pending_buy_index: int | None = None
        pending_sell_index: int | None = None
        pending_sell_reason: str | None = None

        for index, row in working.iterrows():
            trade_date = row["trade_date"]

            if pending_buy_index == index and quantity == 0:
                price_raw = float(row[request.entry_price_column])
                price = self.market_profile.apply_slippage(OrderSide.BUY, price_raw)
                raw_quantity = int(cash // price)
                buy_quantity = self.market_profile.round_order_quantity(OrderSide.BUY, raw_quantity)
                if buy_quantity > 0:
                    order = Order(
                        symbol=request.symbol,
                        trade_date=trade_date.date(),
                        side=OrderSide.BUY,
                        order_type=OrderType.MARKET,
                        quantity=buy_quantity,
                        price=price,
                    )
                    validation = self.market_profile.validate_order(
                        order,
                        is_suspended=self._row_flag(row, "is_suspended"),
                        limit_up=self._row_flag(row, "limit_up"),
                        limit_down=self._row_flag(row, "limit_down"),
                    )
                    if not validation.allowed:
                        failed_orders.append(self._failed_order_row(order, validation.reason))
                        pending_buy_index = None
                    else:
                        cost = self.market_profile.calculate_cost(OrderSide.BUY, order.notional)
                        total_cash_needed = order.notional + cost
                        if total_cash_needed <= cash:
                            cost_parts = self.market_profile.calculate_cost_breakdown(OrderSide.BUY, order.notional)
                            cash -= total_cash_needed
                            quantity = buy_quantity
                            entry_index = index
                            entry_price = price
                            entry_date = trade_date
                            entry_cost = cost
                            entry_cost_parts = cost_parts
                            trailing_anchor = float(price)
                            orders.append(self._order_row(order, cost, price_raw=price_raw, cost_parts=cost_parts))
                            pending_buy_index = None

            if quantity > 0 and entry_index is not None:
                if request.trailing_stop_pct is not None:
                    anchor_value = self._optional_float(row, "high")
                    if anchor_value is None:
                        anchor_value = float(row[request.mark_price_column])
                    trailing_anchor = max(trailing_anchor, anchor_value)
                sell_reason: str | None = None
                if pending_sell_index is not None and index == pending_sell_index:
                    sell_reason = pending_sell_reason or "exit_signal"
                elif request.holding_days > 0 and index == entry_index + request.holding_days:
                    sell_reason = "holding_period"
                elif (
                    request.stop_loss_pct is not None
                    and float(row[request.mark_price_column]) <= float(entry_price) * (1 - request.stop_loss_pct)
                    and index + 1 < len(working)
                ):
                    next_index = index + 1
                    if pending_sell_index is None or next_index < pending_sell_index:
                        pending_sell_index = next_index
                        pending_sell_reason = "stop_loss"
                elif (
                    request.take_profit_pct is not None
                    and float(row[request.mark_price_column]) >= float(entry_price) * (1 + request.take_profit_pct)
                    and index + 1 < len(working)
                ):
                    next_index = index + 1
                    if pending_sell_index is None or next_index < pending_sell_index:
                        pending_sell_index = next_index
                        pending_sell_reason = "take_profit"
                elif (
                    request.trailing_stop_pct is not None
                    and float(row[request.mark_price_column]) <= trailing_anchor * (1 - request.trailing_stop_pct)
                    and index + 1 < len(working)
                ):
                    next_index = index + 1
                    if pending_sell_index is None or next_index < pending_sell_index:
                        pending_sell_index = next_index
                        pending_sell_reason = "trailing_stop"
                elif request.exit_signal is not None and bool(row.get("exit_signal", False)) and index + 1 < len(working):
                    next_index = index + 1
                    if pending_sell_index is None or next_index < pending_sell_index:
                        pending_sell_index = next_index
                        pending_sell_reason = "exit_signal"

                if sell_reason is not None:
                    price_raw = float(row[request.entry_price_column])
                    price = self.market_profile.apply_slippage(OrderSide.SELL, price_raw)
                    order = Order(
                        symbol=request.symbol,
                        trade_date=trade_date.date(),
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET,
                        quantity=quantity,
                        price=price,
                    )
                    validation = self.market_profile.validate_order(
                        order,
                        is_suspended=self._row_flag(row, "is_suspended"),
                        limit_up=self._row_flag(row, "limit_up"),
                        limit_down=self._row_flag(row, "limit_down"),
                    )
                    if not validation.allowed:
                        failed_orders.append(self._failed_order_row(order, validation.reason))
                        pending_sell_index = index + 1
                        pending_sell_reason = sell_reason
                    else:
                        cost = self.market_profile.calculate_cost(OrderSide.SELL, order.notional)
                        exit_cost_parts = self.market_profile.calculate_cost_breakdown(OrderSide.SELL, order.notional)
                        cash += order.notional - cost
                        orders.append(self._order_row(order, cost, price_raw=price_raw, cost_parts=exit_cost_parts))
                        trades.append(
                            {
                                "symbol": request.symbol,
                                "entry_date": entry_date,
                                "exit_date": trade_date,
                                "quantity": quantity,
                                "entry_price": entry_price,
                                "exit_price": price,
                                "gross_pnl": (price - float(entry_price)) * quantity,
                                "cost": entry_cost + cost,
                                "net_pnl": (price - float(entry_price)) * quantity - entry_cost - cost,
                                "exit_reason": sell_reason,
                                "entry_commission": entry_cost_parts["commission"],
                                "entry_stamp_tax": entry_cost_parts["stamp_tax"],
                                "entry_transfer_fee": entry_cost_parts["transfer_fee"],
                                "exit_commission": exit_cost_parts["commission"],
                                "exit_stamp_tax": exit_cost_parts["stamp_tax"],
                                "exit_transfer_fee": exit_cost_parts["transfer_fee"],
                            }
                        )
                        quantity = 0
                        entry_index = None
                        entry_price = None
                        entry_date = None
                        entry_cost = 0.0
                        entry_cost_parts = {"commission": 0.0, "transfer_fee": 0.0, "stamp_tax": 0.0, "total": 0.0}
                        trailing_anchor = 0.0
                        pending_sell_index = None
                        pending_sell_reason = None

            if quantity == 0 and pending_buy_index is None and bool(row["entry_signal"]) and index + 1 < len(working):
                pending_buy_index = index + 1

            mark_price = float(row[request.mark_price_column])
            market_value = quantity * mark_price
            equity_rows.append(
                {
                    "trade_date": trade_date,
                    "cash": cash,
                    "position_quantity": quantity,
                    "market_value": market_value,
                    "total_equity": cash + market_value,
                    "buy_hold_equity": request.initial_cash * mark_price / first_mark_price
                    if first_mark_price > 0
                    else None,
                }
            )

        orders_frame = pd.DataFrame(orders)
        trades_frame = pd.DataFrame(trades)
        equity_frame = pd.DataFrame(equity_rows)
        failed_orders_frame = pd.DataFrame(failed_orders)
        summary = self._build_summary(request, trades_frame, equity_frame, working)
        return SingleSymbolBacktestResult(
            orders=orders_frame,
            trades=trades_frame,
            equity_curve=equity_frame,
            failed_orders=failed_orders_frame,
            summary=summary,
        )

    def _validate_request(self, request: SingleSymbolBacktestRequest) -> None:
        if request.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if request.holding_days < 0:
            raise ValueError("holding_days must be >= 0 (0 = 不限持仓天数)")

    def _empty_result(self, request: SingleSymbolBacktestRequest) -> SingleSymbolBacktestResult:
        return empty_single_symbol_result(request)

    def _order_row(
        self,
        order: Order,
        cost: float,
        *,
        price_raw: float | None = None,
        cost_parts: dict[str, float] | None = None,
    ) -> dict[str, object]:
        row: dict[str, object] = {
            "symbol": order.symbol,
            "trade_date": pd.Timestamp(order.trade_date),
            "side": order.side.value,
            "quantity": order.quantity,
            "price": order.price,
            "notional": order.notional,
            "cost": cost,
        }
        if price_raw is not None:
            row["price_raw"] = price_raw
        if cost_parts is not None:
            row["commission"] = cost_parts["commission"]
            row["stamp_tax"] = cost_parts["stamp_tax"]
            row["transfer_fee"] = cost_parts["transfer_fee"]
        return row

    def _failed_order_row(self, order: Order, reason: str) -> dict[str, object]:
        return {
            "symbol": order.symbol,
            "trade_date": pd.Timestamp(order.trade_date),
            "side": order.side.value,
            "quantity": order.quantity,
            "price": order.price,
            "notional": order.notional,
            "reason": reason,
        }

    def _row_flag(self, row: pd.Series, column: str) -> bool:
        if column in row.index and pd.notna(row[column]):
            return bool(row[column])
        if column == "limit_up":
            return self.market_profile.is_limit_up(
                str(row["ts_code"]),
                pre_close=self._optional_float(row, "pre_close"),
                price=float(row["open"]),
                is_st=self._row_flag(row, "is_st"),
            )
        if column == "limit_down":
            return self.market_profile.is_limit_down(
                str(row["ts_code"]),
                pre_close=self._optional_float(row, "pre_close"),
                price=float(row["open"]),
                is_st=self._row_flag(row, "is_st"),
            )
        return False

    def _optional_float(self, row: pd.Series, column: str) -> float | None:
        if column not in row.index or pd.isna(row[column]):
            return None
        return float(row[column])

    def _build_summary(
        self,
        request: SingleSymbolBacktestRequest,
        trades: pd.DataFrame,
        equity_curve: pd.DataFrame,
        frame: pd.DataFrame,
    ) -> dict[str, float | int | None]:
        return build_single_symbol_summary(request, trades, equity_curve, frame)
