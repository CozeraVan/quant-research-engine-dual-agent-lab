"""Vectorized trade-level single-symbol backtest engine (M9.1b).

Produces metric-identical results to :class:`SingleSymbolBacktestEngine`
(the per-bar ``iterrows`` simulator) while replacing its two main costs:

- per-symbol full-frame filtering (the batch engine now pre-splits the frame
  once and calls :meth:`SingleSymbolVectorizedEngine.run_working` per group)
- the per-bar Python loop: this engine iterates only *candidate event bars*
  (signal bars, execution bars, exit bars, rejection-retry bars) on numpy
  arrays — all other bars are provably no-ops — and reconstructs the daily
  equity curve vectorized from execution segments.

Equality contract (enforced by ``tests/test_single_symbol_vectorized.py``):
``orders`` / ``trades`` / ``failed_orders`` / ``equity_curve`` / ``summary``
must match the simulator exactly for identical inputs.

``position_sizing``:

- ``full_compound`` (default): every entry invests all available cash
  (``int(cash // price)`` rounded to lots) — identical to the simulator.
- ``fixed_cash``: every entry invests a fixed notional equal to
  ``request.initial_cash`` (``int(initial_cash // price)`` rounded to lots);
  the affordability check still uses current cash, so the same
  dead-pending semantics apply once cash runs out.
"""

from __future__ import annotations

import heapq

import numpy as np
import pandas as pd

from quant_research_engine.core.models import Order, OrderSide, OrderType
from quant_research_engine.evaluation.signals import evaluate_expression_signal
from quant_research_engine.markets.ashare import AShareMarketProfile
from quant_research_engine.portfolio.single_symbol import (
    SingleSymbolBacktestRequest,
    SingleSymbolBacktestResult,
    build_single_symbol_summary,
    empty_single_symbol_result,
)

POSITION_SIZING_MODES = ("full_compound", "fixed_cash")

_NO_INDEX = -1  # sentinel for "no pending index" (bar indices are >= 0)


class SingleSymbolVectorizedEngine:
    """Trade-level engine producing simulator-identical results."""

    def __init__(self, market_profile: AShareMarketProfile) -> None:
        self.market_profile = market_profile

    def run(
        self,
        frame: pd.DataFrame,
        request: SingleSymbolBacktestRequest,
        *,
        position_sizing: str = "full_compound",
    ) -> SingleSymbolBacktestResult:
        """Same public interface as the simulator: full frame, filter inside."""
        self._validate(request, position_sizing)
        working = frame.loc[frame["ts_code"] == request.symbol].copy()
        if working.empty:
            return empty_single_symbol_result(request)
        return self.run_working(working, request, position_sizing=position_sizing)

    def run_working(
        self,
        working: pd.DataFrame,
        request: SingleSymbolBacktestRequest,
        *,
        position_sizing: str = "full_compound",
    ) -> SingleSymbolBacktestResult:
        """Run on a pre-filtered single-symbol frame (batch fast path)."""
        self._validate(request, position_sizing)
        if working.empty:
            return empty_single_symbol_result(request)

        working = working.copy()
        working["trade_date"] = pd.to_datetime(working["trade_date"])
        working = working.sort_values("trade_date").reset_index(drop=True)
        working["entry_signal"] = evaluate_expression_signal(working, request.entry_signal)
        if request.exit_signal is not None:
            working["exit_signal"] = evaluate_expression_signal(working, request.exit_signal)

        n = len(working)
        # Simulator uses row["open"] for limit checks and row[entry_price_column]
        # for fills; keep both arrays.
        open_prices = working["open"].to_numpy(dtype=float)
        entry_prices = working[request.entry_price_column].to_numpy(dtype=float)
        mark_prices = working[request.mark_price_column].to_numpy(dtype=float)
        trade_dates = working["trade_date"].to_numpy()
        entry_signals = working["entry_signal"].to_numpy(dtype=bool)
        exit_signals = (
            working["exit_signal"].to_numpy(dtype=bool)
            if request.exit_signal is not None
            else None
        )
        flag_arrays = {
            column: working[column].to_numpy()
            for column in ("is_suspended", "limit_up", "limit_down", "is_st", "pre_close")
            if column in working.columns
        }

        def flag(i: int, column: str) -> bool:
            # Mirrors simulator `_row_flag` exactly.
            arr = flag_arrays.get(column)
            if arr is not None and not pd.isna(arr[i]):
                return bool(arr[i])
            if column == "limit_up":
                return self.market_profile.is_limit_up(
                    request.symbol,
                    pre_close=opt_float(i, "pre_close"),
                    price=float(open_prices[i]),
                    is_st=flag(i, "is_st"),
                )
            if column == "limit_down":
                return self.market_profile.is_limit_down(
                    request.symbol,
                    pre_close=opt_float(i, "pre_close"),
                    price=float(open_prices[i]),
                    is_st=flag(i, "is_st"),
                )
            return False

        def opt_float(i: int, column: str) -> float | None:
            # Mirrors simulator `_optional_float` exactly.
            arr = flag_arrays.get(column)
            if arr is None or pd.isna(arr[i]):
                return None
            return float(arr[i])

        # Static candidates: any bar where a signal could schedule something.
        if exit_signals is not None:
            candidate_bars = np.flatnonzero(entry_signals | exit_signals)
        else:
            candidate_bars = np.flatnonzero(entry_signals)

        cash = float(request.initial_cash)
        quantity = 0
        entry_index = _NO_INDEX
        entry_price = 0.0
        entry_date: pd.Timestamp | None = None
        entry_cost = 0.0
        pending_buy_index = _NO_INDEX
        pending_sell_index = _NO_INDEX
        pending_sell_reason: str | None = None

        orders: list[dict[str, object]] = []
        trades: list[dict[str, object]] = []
        failed_orders: list[dict[str, object]] = []
        fills: list[tuple[int, float, int]] = []  # (bar, cash_after, quantity_after)

        holding_days = request.holding_days
        heap: list[int] = []  # dynamic candidates: execution/expiry/retry bars
        static_pos = 0
        last_bar = _NO_INDEX

        while True:
            nxt = _NO_INDEX
            if static_pos < len(candidate_bars):
                nxt = int(candidate_bars[static_pos])
            if heap and (nxt == _NO_INDEX or heap[0] < nxt):
                nxt = heap[0]
            if nxt == _NO_INDEX:
                break
            if static_pos < len(candidate_bars) and int(candidate_bars[static_pos]) == nxt:
                static_pos += 1
            if heap and heap[0] == nxt:
                heapq.heappop(heap)
            if nxt <= last_bar:
                continue
            if nxt >= n:
                break  # retry/schedule past the last bar: simulator loop simply ends
            last_bar = nxt
            i = nxt

            # --- pending buy execution (mirrors simulator lines 66-99) ---
            if pending_buy_index == i and quantity == 0:
                price = self.market_profile.apply_slippage(OrderSide.BUY, float(entry_prices[i]))
                if position_sizing == "fixed_cash":
                    raw_quantity = int(float(request.initial_cash) // price)
                else:
                    raw_quantity = int(cash // price)
                buy_quantity = self.market_profile.round_order_quantity(OrderSide.BUY, raw_quantity)
                if buy_quantity > 0:
                    order = Order(
                        symbol=request.symbol,
                        trade_date=pd.Timestamp(trade_dates[i]).date(),
                        side=OrderSide.BUY,
                        order_type=OrderType.MARKET,
                        quantity=buy_quantity,
                        price=price,
                    )
                    validation = self.market_profile.validate_order(
                        order,
                        is_suspended=flag(i, "is_suspended"),
                        limit_up=flag(i, "limit_up"),
                        limit_down=flag(i, "limit_down"),
                    )
                    if not validation.allowed:
                        failed_orders.append(self._failed_order_row(order, validation.reason))
                        pending_buy_index = _NO_INDEX
                    else:
                        cost = self.market_profile.calculate_cost(OrderSide.BUY, order.notional)
                        total_cash_needed = order.notional + cost
                        if total_cash_needed <= cash:
                            cash -= total_cash_needed
                            quantity = buy_quantity
                            entry_index = i
                            entry_price = price
                            entry_date = pd.Timestamp(trade_dates[i])
                            entry_cost = cost
                            orders.append(self._order_row(order, cost))
                            pending_buy_index = _NO_INDEX
                            fills.append((i, cash, quantity))
                            expiry = i + holding_days
                            if expiry < n:
                                heapq.heappush(heap, expiry)
                        # else: simulator leaves pending_buy_index set (dead) — no
                        # further buys for this symbol; preserved identically.
                # buy_quantity == 0: same dead-pending semantics as the simulator.

            # --- sell logic (mirrors simulator lines 101-157) ---
            if quantity > 0 and entry_index != _NO_INDEX:
                sell_reason: str | None = None
                if pending_sell_index != _NO_INDEX and i == pending_sell_index:
                    sell_reason = pending_sell_reason or "exit_signal"
                elif i == entry_index + holding_days:
                    sell_reason = "holding_period"
                elif (
                    exit_signals is not None
                    and bool(exit_signals[i])
                    and i + 1 < n
                ):
                    next_index = i + 1
                    if pending_sell_index == _NO_INDEX or next_index < pending_sell_index:
                        pending_sell_index = next_index
                        pending_sell_reason = "exit_signal"
                        heapq.heappush(heap, next_index)

                if sell_reason is not None:
                    price = self.market_profile.apply_slippage(OrderSide.SELL, float(entry_prices[i]))
                    order = Order(
                        symbol=request.symbol,
                        trade_date=pd.Timestamp(trade_dates[i]).date(),
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET,
                        quantity=quantity,
                        price=price,
                    )
                    validation = self.market_profile.validate_order(
                        order,
                        is_suspended=flag(i, "is_suspended"),
                        limit_up=flag(i, "limit_up"),
                        limit_down=flag(i, "limit_down"),
                    )
                    if not validation.allowed:
                        failed_orders.append(self._failed_order_row(order, validation.reason))
                        pending_sell_index = i + 1
                        pending_sell_reason = sell_reason
                        heapq.heappush(heap, i + 1)
                    else:
                        cost = self.market_profile.calculate_cost(OrderSide.SELL, order.notional)
                        cash += order.notional - cost
                        orders.append(self._order_row(order, cost))
                        trades.append(
                            {
                                "symbol": request.symbol,
                                "entry_date": entry_date,
                                "exit_date": pd.Timestamp(trade_dates[i]),
                                "quantity": quantity,
                                "entry_price": entry_price,
                                "exit_price": price,
                                "gross_pnl": (price - float(entry_price)) * quantity,
                                "cost": entry_cost + cost,
                                "net_pnl": (price - float(entry_price)) * quantity - entry_cost - cost,
                                "exit_reason": sell_reason,
                            }
                        )
                        quantity = 0
                        entry_index = _NO_INDEX
                        entry_price = 0.0
                        entry_date = None
                        entry_cost = 0.0
                        pending_sell_index = _NO_INDEX
                        pending_sell_reason = None
                        fills.append((i, cash, quantity))

            # --- schedule new buy (mirrors simulator line 159) ---
            if quantity == 0 and pending_buy_index == _NO_INDEX and bool(entry_signals[i]) and i + 1 < n:
                pending_buy_index = i + 1
                heapq.heappush(heap, i + 1)

        # --- vectorized equity reconstruction ---
        equity_frame = self._build_equity_curve(
            n, trade_dates, mark_prices, float(request.initial_cash), fills
        )

        orders_frame = pd.DataFrame(orders)
        trades_frame = pd.DataFrame(trades)
        failed_orders_frame = pd.DataFrame(failed_orders)
        summary = build_single_symbol_summary(request, trades_frame, equity_frame, working)
        return SingleSymbolBacktestResult(
            orders=orders_frame,
            trades=trades_frame,
            equity_curve=equity_frame,
            failed_orders=failed_orders_frame,
            summary=summary,
        )

    @staticmethod
    def _build_equity_curve(
        n: int,
        trade_dates: np.ndarray,
        mark_prices: np.ndarray,
        initial_cash: float,
        fills: list[tuple[int, float, int]],
    ) -> pd.DataFrame:
        """Rebuild the simulator's per-bar equity rows from execution segments.

        Cash and quantity only change at fills; each segment [fill_k, fill_{k+1})
        keeps the post-fill state, and market value is close * quantity.
        """
        bounds = [0] + [bar for bar, _, _ in fills] + [n]
        seg_cash = [initial_cash] + [c for _, c, _ in fills]
        seg_qty = [0] + [q for _, _, q in fills]
        cash_arr = np.empty(n, dtype=float)
        qty_arr = np.empty(n, dtype=np.int64)
        for k in range(len(seg_cash)):
            s, e = bounds[k], bounds[k + 1]
            cash_arr[s:e] = seg_cash[k]
            qty_arr[s:e] = seg_qty[k]
        market_values = qty_arr * mark_prices
        total_equity = cash_arr + market_values
        return pd.DataFrame(
            {
                "trade_date": trade_dates,
                "cash": cash_arr,
                "position_quantity": qty_arr,
                "market_value": market_values,
                "total_equity": total_equity,
            }
        )

    def _validate(self, request: SingleSymbolBacktestRequest, position_sizing: str) -> None:
        if request.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if request.holding_days <= 0:
            raise ValueError("holding_days must be positive")
        if position_sizing not in POSITION_SIZING_MODES:
            raise ValueError(
                f"Unsupported position_sizing: {position_sizing!r} "
                f"(expected one of {POSITION_SIZING_MODES})"
            )

    def _order_row(self, order: Order, cost: float) -> dict[str, object]:
        # Same shape/key order as the simulator's _order_row.
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
        # Same shape/key order as the simulator's _failed_order_row.
        return {
            "symbol": order.symbol,
            "trade_date": pd.Timestamp(order.trade_date),
            "side": order.side.value,
            "quantity": order.quantity,
            "price": order.price,
            "notional": order.notional,
            "reason": reason,
        }
