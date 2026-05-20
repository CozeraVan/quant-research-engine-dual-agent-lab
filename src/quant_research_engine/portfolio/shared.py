from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant_research_engine.core.models import Order, OrderSide, OrderType
from quant_research_engine.evaluation.signals import evaluate_expression_signal
from quant_research_engine.markets.ashare import AShareMarketProfile
from quant_research_engine.portfolio.risk import summarize_equity_curve
from quant_research_engine.portfolio.risk_controls import RiskControlConfig, evaluate_long_exit
from quant_research_engine.portfolio.weights import build_target_weights


@dataclass(frozen=True)
class SharedCashBacktestRequest:
    symbols: list[str] | None
    initial_cash: float
    entry_signal: str
    holding_days: int
    max_positions: int
    entry_price_column: str = "open"
    mark_price_column: str = "close"
    weight_model: str = "equal_weight"
    score_column: str | None = None
    volatility_column: str | None = None
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    trailing_stop_pct: float | None = None
    rebalance_interval_days: int | None = None
    metadata_columns: list[str] | None = None


@dataclass(frozen=True)
class SharedCashBacktestResult:
    orders: pd.DataFrame
    trades: pd.DataFrame
    equity_curve: pd.DataFrame
    failed_orders: pd.DataFrame
    summary: dict[str, float | int | None]


class SharedCashBacktestEngine:
    def __init__(self, market_profile: AShareMarketProfile) -> None:
        self.market_profile = market_profile

    def run(self, frame: pd.DataFrame, request: SharedCashBacktestRequest) -> SharedCashBacktestResult:
        self._validate_request(request)
        working = self._prepare_frame(frame, request)
        if working.empty:
            return self._empty_result(request)

        symbol_metadata = self._build_metadata_lookup(working, request.metadata_columns or [])

        dates = working["trade_date"].drop_duplicates().sort_values().tolist()
        symbol_bar_indices = self._symbol_bar_indices(working)

        cash = request.initial_cash
        positions: dict[str, dict[str, object]] = {}
        pending_buys: dict[pd.Timestamp, list[str]] = {}

        orders: list[dict[str, object]] = []
        trades: list[dict[str, object]] = []
        failed_orders: list[dict[str, object]] = []
        equity_rows: list[dict[str, object]] = []

        for date_index, trade_date in enumerate(dates):
            day_frame = working.loc[working["trade_date"] == trade_date].set_index("ts_code", drop=False)

            cash = self._execute_due_sells(
                request=request,
                trade_date=trade_date,
                day_frame=day_frame,
                symbol_bar_indices=symbol_bar_indices,
                cash=cash,
                positions=positions,
                orders=orders,
                trades=trades,
                failed_orders=failed_orders,
                symbol_metadata=symbol_metadata,
            )
            cash = self._execute_pending_buys(
                request=request,
                trade_date=trade_date,
                day_frame=day_frame,
                cash=cash,
                total_equity=cash + self._market_value(day_frame, positions, request.mark_price_column),
                positions=positions,
                symbols=pending_buys.pop(trade_date, []),
                orders=orders,
                failed_orders=failed_orders,
                symbol_metadata=symbol_metadata,
            )
            if self._should_rebalance(date_index, request):
                cash = self._execute_rebalance(
                    request=request,
                    trade_date=trade_date,
                    day_frame=day_frame,
                    cash=cash,
                    positions=positions,
                orders=orders,
                trades=trades,
                failed_orders=failed_orders,
                symbol_metadata=symbol_metadata,
            )

            if date_index + 1 < len(dates):
                next_trade_date = dates[date_index + 1]
                available_slots = request.max_positions - len(positions) - len(pending_buys.get(next_trade_date, []))
                if available_slots > 0:
                    candidates = self._entry_candidates(day_frame, positions, pending_buys, next_trade_date)
                    pending_buys.setdefault(next_trade_date, []).extend(candidates[:available_slots])

            market_value = self._market_value(day_frame, positions, request.mark_price_column)
            equity_rows.append(
                {
                    "trade_date": trade_date,
                    "cash": cash,
                    "market_value": market_value,
                    "total_equity": cash + market_value,
                    "position_count": len(positions),
                }
            )

        orders_frame = pd.DataFrame(orders)
        trades_frame = pd.DataFrame(trades)
        equity_frame = pd.DataFrame(equity_rows)
        failed_orders_frame = pd.DataFrame(failed_orders)
        return SharedCashBacktestResult(
            orders=orders_frame,
            trades=trades_frame,
            equity_curve=equity_frame,
            failed_orders=failed_orders_frame,
            summary=self._build_summary(request, orders_frame, trades_frame, equity_frame, failed_orders_frame),
        )

    def _prepare_frame(self, frame: pd.DataFrame, request: SharedCashBacktestRequest) -> pd.DataFrame:
        working = frame.copy()
        if request.symbols:
            working = working.loc[working["ts_code"].isin(request.symbols)].copy()
        if working.empty:
            return working
        working["trade_date"] = pd.to_datetime(working["trade_date"])
        parts = []
        for _, symbol_frame in working.sort_values(["ts_code", "trade_date"]).groupby("ts_code", sort=True):
            chunk = symbol_frame.copy()
            chunk["entry_signal"] = evaluate_expression_signal(chunk, request.entry_signal)
            chunk["symbol_bar_index"] = range(len(chunk))
            parts.append(chunk)
        return pd.concat(parts, ignore_index=True).sort_values(["trade_date", "ts_code"]).reset_index(drop=True)

    def _build_metadata_lookup(
        self,
        frame: pd.DataFrame,
        requested_columns: list[str],
    ) -> dict[str, dict[str, object]]:
        if not requested_columns:
            return {}
        available = [col for col in requested_columns if col in frame.columns]
        if not available:
            return {}
        lookup: dict[str, dict[str, object]] = {}
        for ts_code, group in frame.groupby("ts_code", sort=False):
            metadata: dict[str, object] = {}
            for col in available:
                values = group[col].dropna()
                if not values.empty:
                    metadata[col] = values.iloc[0]
            if metadata:
                lookup[str(ts_code)] = metadata
        return lookup

    def _symbol_bar_indices(self, frame: pd.DataFrame) -> dict[tuple[str, pd.Timestamp], int]:
        return {
            (str(row["ts_code"]), row["trade_date"]): int(row["symbol_bar_index"])
            for _, row in frame.iterrows()
        }

    def _execute_due_sells(
        self,
        *,
        request: SharedCashBacktestRequest,
        trade_date: pd.Timestamp,
        day_frame: pd.DataFrame,
        symbol_bar_indices: dict[tuple[str, pd.Timestamp], int],
        cash: float,
        positions: dict[str, dict[str, object]],
        orders: list[dict[str, object]],
        trades: list[dict[str, object]],
        failed_orders: list[dict[str, object]],
        symbol_metadata: dict[str, dict[str, object]],
    ) -> float:
        for symbol in sorted(list(positions)):
            if symbol not in day_frame.index:
                continue
            row = day_frame.loc[symbol]
            current_bar_index = symbol_bar_indices[(symbol, trade_date)]
            position = positions[symbol]
            exit_decision = evaluate_long_exit(
                entry_price=float(position["entry_price"]),
                row=row,
                config=RiskControlConfig(
                    stop_loss_pct=request.stop_loss_pct,
                    take_profit_pct=request.take_profit_pct,
                    trailing_stop_pct=request.trailing_stop_pct,
                ),
                trailing_anchor=self._updated_trailing_anchor(position, row),
            )
            exit_reason = exit_decision.reason
            if not exit_decision.should_exit and current_bar_index < int(position["entry_bar_index"]) + request.holding_days:
                continue
            if exit_reason is None:
                exit_reason = "holding_period"
            sellable_quantity = self._sellable_quantity(position, current_bar_index)
            if sellable_quantity <= 0:
                continue

            raw_exit_price = exit_decision.price if exit_decision.price is not None else float(row[request.entry_price_column])
            price = self.market_profile.apply_slippage(OrderSide.SELL, float(raw_exit_price))
            order = Order(
                symbol=symbol,
                trade_date=trade_date.date(),
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=sellable_quantity,
                price=price,
            )
            validation = self.market_profile.validate_order(
                order,
                is_suspended=self._row_flag(row, "is_suspended"),
                limit_up=self._row_flag(row, "limit_up"),
                limit_down=self._row_flag(row, "limit_down"),
            )
            if not validation.allowed:
                failed_orders.append(self._failed_order_row(order, validation.reason, symbol_metadata=symbol_metadata))
                continue
            cost = self.market_profile.calculate_cost(OrderSide.SELL, order.notional)
            cash += order.notional - cost
            orders.append(self._order_row(order, cost, symbol_metadata=symbol_metadata))
            trades.append(
                self._trade_row(
                    symbol=symbol,
                    exit_date=trade_date,
                    quantity=sellable_quantity,
                    exit_price=price,
                    position=position,
                    exit_cost=cost,
                    exit_reason=exit_reason,
                    symbol_metadata=symbol_metadata,
                )
            )
            self._refresh_position_from_lots(position)
            if int(position["quantity"]) <= 0:
                del positions[symbol]
        return cash

    def _trade_row(
        self,
        *,
        symbol: str,
        exit_date: pd.Timestamp,
        quantity: int,
        exit_price: float,
        position: dict[str, object],
        exit_cost: float,
        exit_reason: str,
        symbol_metadata: dict[str, dict[str, object]] | None = None,
    ) -> dict[str, object]:
        consumed = self._consume_lots(position, quantity)
        entry_price = float(consumed["entry_notional"]) / quantity if quantity > 0 else float(position["entry_price"])
        gross_pnl = (exit_price * quantity) - float(consumed["entry_notional"])
        cost = float(consumed["entry_cost"]) + exit_cost
        row = {
            "symbol": symbol,
            "entry_date": consumed["entry_date"],
            "exit_date": exit_date,
            "quantity": quantity,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "gross_pnl": gross_pnl,
            "cost": cost,
            "net_pnl": gross_pnl - cost,
            "exit_reason": exit_reason,
        }
        if symbol_metadata and symbol in symbol_metadata:
            for key, value in symbol_metadata[symbol].items():
                if key not in row:
                    row[key] = value
        return row

    def _consume_lots(self, position: dict[str, object], quantity: int) -> dict[str, object]:
        lots = list(position.get("lots", []))
        remaining = quantity
        entry_notional = 0.0
        entry_cost = 0.0
        entry_date = None
        updated_lots: list[dict[str, object]] = []
        for lot in lots:
            lot_quantity = int(lot["quantity"])
            if remaining <= 0:
                updated_lots.append(lot)
                continue
            consumed_quantity = min(remaining, lot_quantity)
            if consumed_quantity > 0:
                if entry_date is None:
                    entry_date = lot["entry_date"]
                entry_notional += consumed_quantity * float(lot["entry_price"])
                entry_cost += float(lot["entry_cost"]) * consumed_quantity / lot_quantity
                remaining -= consumed_quantity
            leftover_quantity = lot_quantity - consumed_quantity
            if leftover_quantity > 0:
                updated_lots.append(
                    {
                        **lot,
                        "quantity": leftover_quantity,
                        "entry_cost": float(lot["entry_cost"]) * leftover_quantity / lot_quantity,
                    }
                )
        position["lots"] = updated_lots
        return {
            "entry_date": entry_date if entry_date is not None else position["entry_date"],
            "entry_notional": entry_notional,
            "entry_cost": entry_cost,
        }

    def _sellable_quantity(self, position: dict[str, object], current_bar_index: int) -> int:
        lots = list(position.get("lots", []))
        return sum(
            int(lot["quantity"])
            for lot in lots
            if int(lot["entry_bar_index"]) < current_bar_index
        )

    def _refresh_position_from_lots(self, position: dict[str, object]) -> None:
        lots = list(position.get("lots", []))
        quantity = sum(int(lot["quantity"]) for lot in lots)
        position["quantity"] = quantity
        position["entry_cost"] = sum(float(lot["entry_cost"]) for lot in lots)
        if quantity <= 0:
            position["entry_price"] = 0.0
            return
        position["entry_price"] = sum(int(lot["quantity"]) * float(lot["entry_price"]) for lot in lots) / quantity
        first_lot = lots[0]
        position["entry_date"] = first_lot["entry_date"]
        position["entry_bar_index"] = int(first_lot["entry_bar_index"])

    def _append_lot(
        self,
        position: dict[str, object],
        *,
        quantity: int,
        entry_price: float,
        entry_date: pd.Timestamp,
        entry_cost: float,
        entry_bar_index: int,
    ) -> None:
        lots = list(position.get("lots", []))
        lots.append(
            {
                "quantity": quantity,
                "entry_price": entry_price,
                "entry_date": entry_date,
                "entry_cost": entry_cost,
                "entry_bar_index": entry_bar_index,
            }
        )
        position["lots"] = lots
        self._refresh_position_from_lots(position)

    def _execute_pending_buys(
        self,
        *,
        request: SharedCashBacktestRequest,
        trade_date: pd.Timestamp,
        day_frame: pd.DataFrame,
        cash: float,
        total_equity: float,
        positions: dict[str, dict[str, object]],
        symbols: list[str],
        orders: list[dict[str, object]],
        failed_orders: list[dict[str, object]],
        symbol_metadata: dict[str, dict[str, object]],
    ) -> float:
        executable_symbols = [
            symbol
            for symbol in sorted(symbols)
            if symbol not in positions and symbol in day_frame.index
        ]
        weights = self._target_weights(request, day_frame, executable_symbols)
        for symbol in sorted(symbols):
            if symbol in positions or symbol not in day_frame.index or len(positions) >= request.max_positions:
                continue
            row = day_frame.loc[symbol]
            allocation = total_equity * weights.get(symbol, 0.0)
            price = self.market_profile.apply_slippage(OrderSide.BUY, float(row[request.entry_price_column]))
            raw_quantity = int(min(cash, allocation) // price)
            quantity = self.market_profile.round_order_quantity(OrderSide.BUY, raw_quantity)
            if quantity <= 0:
                continue
            order = Order(
                symbol=symbol,
                trade_date=trade_date.date(),
                side=OrderSide.BUY,
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
                failed_orders.append(self._failed_order_row(order, validation.reason, symbol_metadata=symbol_metadata))
                continue
            cost = self.market_profile.calculate_cost(OrderSide.BUY, order.notional)
            total_cash_needed = order.notional + cost
            if total_cash_needed > cash:
                continue
            cash -= total_cash_needed
            orders.append(self._order_row(order, cost, symbol_metadata=symbol_metadata))
            positions[symbol] = {
                "quantity": quantity,
                "entry_price": price,
                "entry_date": trade_date,
                "entry_cost": cost,
                "entry_bar_index": int(row["symbol_bar_index"]),
                "trailing_anchor": self._optional_float(row, "high") or price,
                "lots": [
                    {
                        "quantity": quantity,
                        "entry_price": price,
                        "entry_date": trade_date,
                        "entry_cost": cost,
                        "entry_bar_index": int(row["symbol_bar_index"]),
                    }
                ],
            }
        return cash

    def _should_rebalance(self, date_index: int, request: SharedCashBacktestRequest) -> bool:
        return (
            request.rebalance_interval_days is not None
            and date_index > 0
            and date_index % request.rebalance_interval_days == 0
        )

    def _execute_rebalance(
        self,
        *,
        request: SharedCashBacktestRequest,
        trade_date: pd.Timestamp,
        day_frame: pd.DataFrame,
        cash: float,
        positions: dict[str, dict[str, object]],
        orders: list[dict[str, object]],
        trades: list[dict[str, object]],
        failed_orders: list[dict[str, object]],
        symbol_metadata: dict[str, dict[str, object]],
    ) -> float:
        symbols = sorted(symbol for symbol in positions if symbol in day_frame.index)
        if not symbols:
            return cash

        total_equity = cash + self._market_value(day_frame, positions, request.mark_price_column)
        weights = self._target_weights(request, day_frame, symbols)
        current_values = {
            symbol: int(positions[symbol]["quantity"]) * float(day_frame.loc[symbol, request.mark_price_column])
            for symbol in symbols
        }
        target_values = {symbol: total_equity * weights.get(symbol, 0.0) for symbol in symbols}

        for symbol in symbols:
            cash = self._rebalance_sell(
                request=request,
                trade_date=trade_date,
                row=day_frame.loc[symbol],
                cash=cash,
                position=positions[symbol],
                target_value=target_values[symbol],
                current_value=current_values[symbol],
                orders=orders,
                trades=trades,
                failed_orders=failed_orders,
                symbol_metadata=symbol_metadata,
            )
        for symbol in list(positions):
            if int(positions[symbol]["quantity"]) <= 0:
                del positions[symbol]

        for symbol in symbols:
            if symbol not in positions:
                continue
            cash = self._rebalance_buy(
                request=request,
                trade_date=trade_date,
                row=day_frame.loc[symbol],
                cash=cash,
                position=positions[symbol],
                target_value=target_values[symbol],
                current_value=current_values[symbol],
                orders=orders,
                failed_orders=failed_orders,
                symbol_metadata=symbol_metadata,
            )
        return cash

    def _rebalance_sell(
        self,
        *,
        request: SharedCashBacktestRequest,
        trade_date: pd.Timestamp,
        row: pd.Series,
        cash: float,
        position: dict[str, object],
        target_value: float,
        current_value: float,
        orders: list[dict[str, object]],
        trades: list[dict[str, object]],
        failed_orders: list[dict[str, object]],
        symbol_metadata: dict[str, dict[str, object]],
    ) -> float:
        excess_value = current_value - target_value
        if excess_value <= 0:
            return cash
        price = self.market_profile.apply_slippage(OrderSide.SELL, float(row[request.mark_price_column]))
        sellable_quantity = self._sellable_quantity(position, int(row["symbol_bar_index"]))
        quantity = min(
            sellable_quantity,
            self.market_profile.round_order_quantity(OrderSide.SELL, int(excess_value // price)),
        )
        if quantity <= 0:
            return cash
        order = Order(
            symbol=str(row["ts_code"]),
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
            failed_orders.append(self._failed_order_row(order, validation.reason, reason="rebalance", symbol_metadata=symbol_metadata))
            return cash
        cost = self.market_profile.calculate_cost(OrderSide.SELL, order.notional)
        cash += order.notional - cost
        orders.append(self._order_row(order, cost, reason="rebalance", symbol_metadata=symbol_metadata))
        trades.append(
            self._trade_row(
                symbol=order.symbol,
                exit_date=trade_date,
                quantity=quantity,
                exit_price=price,
                position=position,
                exit_cost=cost,
                exit_reason="rebalance",
                symbol_metadata=symbol_metadata,
            )
        )
        self._refresh_position_from_lots(position)
        return cash

    def _rebalance_buy(
        self,
        *,
        request: SharedCashBacktestRequest,
        trade_date: pd.Timestamp,
        row: pd.Series,
        cash: float,
        position: dict[str, object],
        target_value: float,
        current_value: float,
        orders: list[dict[str, object]],
        failed_orders: list[dict[str, object]],
        symbol_metadata: dict[str, dict[str, object]],
    ) -> float:
        shortfall_value = target_value - current_value
        if shortfall_value <= 0:
            return cash
        price = self.market_profile.apply_slippage(OrderSide.BUY, float(row[request.mark_price_column]))
        quantity = self.market_profile.round_order_quantity(OrderSide.BUY, int(min(shortfall_value, cash) // price))
        while quantity > 0:
            cost = self.market_profile.calculate_cost(OrderSide.BUY, quantity * price)
            if quantity * price + cost <= cash:
                break
            quantity = self.market_profile.round_order_quantity(OrderSide.BUY, quantity - self.market_profile.buy_lot)
        if quantity <= 0:
            return cash
        order = Order(
            symbol=str(row["ts_code"]),
            trade_date=trade_date.date(),
            side=OrderSide.BUY,
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
            failed_orders.append(self._failed_order_row(order, validation.reason, reason="rebalance", symbol_metadata=symbol_metadata))
            return cash
        cost = self.market_profile.calculate_cost(OrderSide.BUY, order.notional)
        total_cash_needed = order.notional + cost
        if total_cash_needed > cash:
            return cash
        cash -= total_cash_needed
        orders.append(self._order_row(order, cost, reason="rebalance", symbol_metadata=symbol_metadata))
        self._append_lot(
            position,
            quantity=quantity,
            entry_price=price,
            entry_date=trade_date,
            entry_cost=cost,
            entry_bar_index=int(row["symbol_bar_index"]),
        )
        position["trailing_anchor"] = max(float(position.get("trailing_anchor", price)), price)
        return cash

    def _updated_trailing_anchor(self, position: dict[str, object], row: pd.Series) -> float:
        current_anchor = float(position.get("trailing_anchor", position["entry_price"]))
        high = self._optional_float(row, "high")
        if high is None:
            return current_anchor
        updated_anchor = max(current_anchor, high)
        position["trailing_anchor"] = updated_anchor
        return updated_anchor

    def _target_weights(
        self,
        request: SharedCashBacktestRequest,
        day_frame: pd.DataFrame,
        symbols: list[str],
    ) -> dict[str, float]:
        scores = self._column_values(day_frame, symbols, request.score_column)
        volatilities = self._column_values(day_frame, symbols, request.volatility_column)
        raw_weights = build_target_weights(
            symbols,
            model=request.weight_model,
            scores=scores,
            volatilities=volatilities,
        )
        slot_exposure = min(len(symbols), request.max_positions) / request.max_positions
        return {symbol: weight * slot_exposure for symbol, weight in raw_weights.items()}

    def _column_values(
        self,
        day_frame: pd.DataFrame,
        symbols: list[str],
        column: str | None,
    ) -> dict[str, float]:
        if not column or column not in day_frame.columns:
            return {}
        values: dict[str, float] = {}
        for symbol in symbols:
            value = day_frame.loc[symbol, column]
            if pd.notna(value):
                values[symbol] = float(value)
        return values

    def _entry_candidates(
        self,
        day_frame: pd.DataFrame,
        positions: dict[str, dict[str, object]],
        pending_buys: dict[pd.Timestamp, list[str]],
        next_trade_date: pd.Timestamp,
    ) -> list[str]:
        already_pending = set(pending_buys.get(next_trade_date, []))
        rows = day_frame.loc[day_frame["entry_signal"]].sort_index()
        return [
            str(row["ts_code"])
            for _, row in rows.iterrows()
            if str(row["ts_code"]) not in positions and str(row["ts_code"]) not in already_pending
        ]

    def _market_value(
        self,
        day_frame: pd.DataFrame,
        positions: dict[str, dict[str, object]],
        mark_price_column: str,
    ) -> float:
        market_value = 0.0
        for symbol, position in positions.items():
            if symbol in day_frame.index:
                market_value += int(position["quantity"]) * float(day_frame.loc[symbol, mark_price_column])
        return market_value

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

    def _order_row(
        self, order: Order, cost: float, *, reason: str | None = None,
        symbol_metadata: dict[str, dict[str, object]] | None = None,
    ) -> dict[str, object]:
        row: dict[str, object] = {
            "symbol": order.symbol,
            "trade_date": pd.Timestamp(order.trade_date),
            "side": order.side.value,
            "quantity": order.quantity,
            "price": order.price,
            "notional": order.notional,
            "cost": cost,
            "reason": reason,
        }
        if symbol_metadata and order.symbol in symbol_metadata:
            for key, value in symbol_metadata[order.symbol].items():
                if key not in row:
                    row[key] = value
        return row

    def _failed_order_row(
        self, order: Order, failure_reason: str, *, reason: str | None = None,
        symbol_metadata: dict[str, dict[str, object]] | None = None,
    ) -> dict[str, object]:
        row: dict[str, object] = {
            "symbol": order.symbol,
            "trade_date": pd.Timestamp(order.trade_date),
            "side": order.side.value,
            "quantity": order.quantity,
            "price": order.price,
            "notional": order.notional,
            "reason": reason,
            "failure_reason": failure_reason,
        }
        if symbol_metadata and order.symbol in symbol_metadata:
            for key, value in symbol_metadata[order.symbol].items():
                if key not in row:
                    row[key] = value
        return row

    def _build_summary(
        self,
        request: SharedCashBacktestRequest,
        orders: pd.DataFrame,
        trades: pd.DataFrame,
        equity_curve: pd.DataFrame,
        failed_orders: pd.DataFrame,
    ) -> dict[str, float | int | None]:
        final_equity = request.initial_cash if equity_curve.empty else float(equity_curve.iloc[-1]["total_equity"])
        trade_count = int(len(trades))
        total_cost = 0.0 if trades.empty else float(trades["cost"].sum())
        win_rate = None if trades.empty else float((trades["net_pnl"] > 0).mean())
        rebalance_metrics = self._rebalance_summary_metrics(orders, equity_curve)
        failed_rebalance_metrics = self._failed_rebalance_summary_metrics(failed_orders)
        failed_diagnostics = self._failed_order_diagnostics(failed_orders)
        return {
            "initial_cash": request.initial_cash,
            "final_equity": final_equity,
            "total_return": final_equity / request.initial_cash - 1,
            "trade_count": trade_count,
            "win_rate": win_rate,
            "total_cost": total_cost,
            **rebalance_metrics,
            **failed_rebalance_metrics,
            **failed_diagnostics,
            **summarize_equity_curve(equity_curve),
        }

    def _rebalance_summary_metrics(
        self,
        orders: pd.DataFrame,
        equity_curve: pd.DataFrame,
    ) -> dict[str, float | int]:
        if orders.empty or "reason" not in orders.columns:
            return {
                "rebalance_order_count": 0,
                "rebalance_notional": 0.0,
                "rebalance_cost": 0.0,
                "rebalance_turnover": 0.0,
            }
        rebalance_orders = orders.loc[orders["reason"] == "rebalance"]
        rebalance_notional = float(rebalance_orders["notional"].sum()) if not rebalance_orders.empty else 0.0
        average_equity = (
            float(equity_curve["total_equity"].mean())
            if not equity_curve.empty and "total_equity" in equity_curve.columns
            else 0.0
        )
        return {
            "rebalance_order_count": int(len(rebalance_orders)),
            "rebalance_notional": rebalance_notional,
            "rebalance_cost": float(rebalance_orders["cost"].sum()) if not rebalance_orders.empty else 0.0,
            "rebalance_turnover": rebalance_notional / average_equity if average_equity > 0 else 0.0,
        }

    def _failed_rebalance_summary_metrics(self, failed_orders: pd.DataFrame) -> dict[str, float | int]:
        if failed_orders.empty or "reason" not in failed_orders.columns:
            return {
                "failed_rebalance_order_count": 0,
                "failed_rebalance_notional": 0.0,
            }
        failed_rebalance_orders = failed_orders.loc[failed_orders["reason"] == "rebalance"]
        return {
            "failed_rebalance_order_count": int(len(failed_rebalance_orders)),
            "failed_rebalance_notional": (
                float(failed_rebalance_orders["notional"].sum())
                if not failed_rebalance_orders.empty
                else 0.0
            ),
        }

    def _failed_order_diagnostics(self, failed_orders: pd.DataFrame) -> dict[str, object]:
        if failed_orders.empty:
            return {
                "failed_order_count": 0,
                "failed_order_count_by_reason": {},
                "failed_order_count_by_failure_reason": {},
                "failed_order_notional_by_reason": {},
                "failed_order_notional_by_failure_reason": {},
                "failed_order_count_by_side": {},
                "failed_order_notional_by_side": {},
            }
        reason_column = failed_orders["reason"].fillna("entry_exit")
        count_by_reason = reason_column.value_counts().to_dict()
        count_by_failure_reason = failed_orders["failure_reason"].value_counts().to_dict()
        notional_by_reason = failed_orders.groupby(reason_column)["notional"].sum().to_dict()
        notional_by_failure_reason = failed_orders.groupby("failure_reason")["notional"].sum().to_dict()
        count_by_side = failed_orders["side"].value_counts().to_dict()
        notional_by_side = failed_orders.groupby("side")["notional"].sum().to_dict()
        return {
            "failed_order_count": int(len(failed_orders)),
            "failed_order_count_by_reason": {str(k): int(v) for k, v in count_by_reason.items()},
            "failed_order_count_by_failure_reason": {str(k): int(v) for k, v in count_by_failure_reason.items()},
            "failed_order_notional_by_reason": {str(k): float(v) for k, v in notional_by_reason.items()},
            "failed_order_notional_by_failure_reason": {str(k): float(v) for k, v in notional_by_failure_reason.items()},
            "failed_order_count_by_side": {str(k): int(v) for k, v in count_by_side.items()},
            "failed_order_notional_by_side": {str(k): float(v) for k, v in notional_by_side.items()},
        }

    def _empty_result(self, request: SharedCashBacktestRequest) -> SharedCashBacktestResult:
        return SharedCashBacktestResult(
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
                "rebalance_order_count": 0,
                "rebalance_notional": 0.0,
                "rebalance_cost": 0.0,
                "rebalance_turnover": 0.0,
                "failed_rebalance_order_count": 0,
                "failed_rebalance_notional": 0.0,
                "failed_order_count": 0,
                "failed_order_count_by_reason": {},
                "failed_order_count_by_failure_reason": {},
                "failed_order_notional_by_reason": {},
                "failed_order_notional_by_failure_reason": {},
                "failed_order_count_by_side": {},
                "failed_order_notional_by_side": {},
            },
        )

    def _validate_request(self, request: SharedCashBacktestRequest) -> None:
        if request.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if request.holding_days <= 0:
            raise ValueError("holding_days must be positive")
        if request.max_positions <= 0:
            raise ValueError("max_positions must be positive")
        if request.weight_model == "score_weight" and not request.score_column:
            raise ValueError("score_column is required for score_weight")
        if request.weight_model == "inverse_volatility" and not request.volatility_column:
            raise ValueError("volatility_column is required for inverse_volatility")
        if request.stop_loss_pct is not None and request.stop_loss_pct <= 0:
            raise ValueError("stop_loss_pct must be positive")
        if request.take_profit_pct is not None and request.take_profit_pct <= 0:
            raise ValueError("take_profit_pct must be positive")
        if request.trailing_stop_pct is not None and request.trailing_stop_pct <= 0:
            raise ValueError("trailing_stop_pct must be positive")
        if request.rebalance_interval_days is not None and request.rebalance_interval_days <= 0:
            raise ValueError("rebalance_interval_days must be positive")
