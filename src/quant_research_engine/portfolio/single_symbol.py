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
    entry_price_column: str = "open"
    mark_price_column: str = "close"


@dataclass(frozen=True)
class SingleSymbolBacktestResult:
    orders: pd.DataFrame
    trades: pd.DataFrame
    equity_curve: pd.DataFrame
    failed_orders: pd.DataFrame
    summary: dict[str, float | int | None]


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

        cash = request.initial_cash
        quantity = 0
        entry_index: int | None = None
        entry_price: float | None = None
        entry_date: pd.Timestamp | None = None
        entry_cost = 0.0

        orders: list[dict[str, object]] = []
        trades: list[dict[str, object]] = []
        equity_rows: list[dict[str, object]] = []
        failed_orders: list[dict[str, object]] = []

        pending_buy_index: int | None = None
        pending_sell = False

        for index, row in working.iterrows():
            trade_date = row["trade_date"]

            if pending_buy_index == index and quantity == 0:
                price = self.market_profile.apply_slippage(OrderSide.BUY, float(row[request.entry_price_column]))
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
                            cash -= total_cash_needed
                            quantity = buy_quantity
                            entry_index = index
                            entry_price = price
                            entry_date = trade_date
                            entry_cost = cost
                            orders.append(self._order_row(order, cost))
                            pending_buy_index = None

            if quantity > 0 and entry_index is not None and (index == entry_index + request.holding_days or pending_sell):
                price = self.market_profile.apply_slippage(OrderSide.SELL, float(row[request.entry_price_column]))
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
                    pending_sell = True
                else:
                    cost = self.market_profile.calculate_cost(OrderSide.SELL, order.notional)
                    cash += order.notional - cost
                    orders.append(self._order_row(order, cost))
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
                        }
                    )
                    quantity = 0
                    entry_index = None
                    entry_price = None
                    entry_date = None
                    entry_cost = 0.0
                    pending_sell = False

            if quantity == 0 and pending_buy_index is None and bool(row["entry_signal"]) and index + 1 < len(working):
                pending_buy_index = index + 1

            market_value = quantity * float(row[request.mark_price_column])
            equity_rows.append(
                {
                    "trade_date": trade_date,
                    "cash": cash,
                    "position_quantity": quantity,
                    "market_value": market_value,
                    "total_equity": cash + market_value,
                }
            )

        orders_frame = pd.DataFrame(orders)
        trades_frame = pd.DataFrame(trades)
        equity_frame = pd.DataFrame(equity_rows)
        failed_orders_frame = pd.DataFrame(failed_orders)
        summary = self._build_summary(request, trades_frame, equity_frame)
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
        if request.holding_days <= 0:
            raise ValueError("holding_days must be positive")

    def _empty_result(self, request: SingleSymbolBacktestRequest) -> SingleSymbolBacktestResult:
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
            },
        )

    def _order_row(self, order: Order, cost: float) -> dict[str, object]:
        return {
            "symbol": order.symbol,
            "trade_date": pd.Timestamp(order.trade_date),
            "side": order.side.value,
            "quantity": order.quantity,
            "price": order.price,
            "notional": order.notional,
            "cost": cost,
        }

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
    ) -> dict[str, float | int | None]:
        final_equity = request.initial_cash if equity_curve.empty else float(equity_curve.iloc[-1]["total_equity"])
        trade_count = int(len(trades))
        total_cost = 0.0 if trades.empty else float(trades["cost"].sum())
        win_rate = None if trades.empty else float((trades["net_pnl"] > 0).mean())
        return {
            "initial_cash": request.initial_cash,
            "final_equity": final_equity,
            "total_return": final_equity / request.initial_cash - 1,
            "trade_count": trade_count,
            "win_rate": win_rate,
            "total_cost": total_cost,
        }
