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
  When notional + fees exceed cash, the quantity is shrunk lot-by-lot
  (``fit_buy_quantity_to_cash``); if not even one lot is affordable the
  attempt is recorded in ``failed_orders`` (``insufficient_cash``) and the
  pending buy is cleared so later entry signals can retry.
- ``fixed_cash``: every entry invests a fixed notional equal to
  ``request.initial_cash`` (``int(initial_cash // price)`` rounded to lots);
  the affordability check (with the same shrink/failed-order fallback)
  still uses current cash.

Incremental continuation (P1): :meth:`run_working_incremental` resumes the
event loop from a :class:`SymbolState` checkpoint at a ``start_index`` bar.
It runs the *same* event loop as :meth:`run_working` (single shared
implementation in :meth:`_run_loop`) with two parameterized differences:

- the loop starts at ``start_index`` with restored state instead of bar 0
  with all-cash/flat state;
- triggers on the last loaded bar still schedule pendings
  (``schedule_beyond_frame=True``) whose execution bar lies in a future
  window, because a daily-update window end is not the end of the data.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from quant_research_engine.core.models import Order, OrderSide, OrderType
from quant_research_engine.evaluation.signals import evaluate_expression_signal
from quant_research_engine.markets.ashare import AShareMarketProfile
from quant_research_engine.orchestration.incremental_state import SymbolState
from quant_research_engine.portfolio.single_symbol import (
    SingleSymbolBacktestRequest,
    SingleSymbolBacktestResult,
    build_single_symbol_summary,
    empty_single_symbol_result,
)

POSITION_SIZING_MODES = ("full_compound", "fixed_cash")

_NO_INDEX = -1  # sentinel for "no pending index" (bar indices are >= 0)


def _zero_cost_parts() -> dict[str, float]:
    return {"commission": 0.0, "transfer_fee": 0.0, "stamp_tax": 0.0, "total": 0.0}


@dataclass(frozen=True)
class IncrementalSymbolResult:
    """New rows produced by one incremental window plus the final state.

    ``final_state`` is ``None`` when the symbol is flat with no pending
    orders — nothing needs recording (cash is then reconstructible by
    replaying the cumulative orders ledger).
    """

    orders: pd.DataFrame
    trades: pd.DataFrame
    failed_orders: pd.DataFrame
    equity_curve: pd.DataFrame
    final_state: SymbolState | None


@dataclass
class _Prepared:
    """Per-symbol arrays + row accessors shared by all run modes."""

    n: int
    trade_dates: np.ndarray
    open_prices: np.ndarray
    entry_prices: np.ndarray
    mark_prices: np.ndarray
    entry_signals: np.ndarray
    exit_signals: np.ndarray | None
    flag_arrays: dict[str, np.ndarray]
    high_prices: np.ndarray | None
    candidate_bars: np.ndarray
    working: pd.DataFrame | None = None


@dataclass
class _LoopState:
    """Mutable event-loop state; also the restore/return container."""

    cash: float
    quantity: int = 0
    entry_index: int = _NO_INDEX
    entry_price: float = 0.0
    entry_date: pd.Timestamp | None = None
    entry_cost: float = 0.0
    entry_cost_parts: dict[str, float] = field(default_factory=_zero_cost_parts)
    pending_buy_index: int = _NO_INDEX
    pending_sell_index: int = _NO_INDEX
    pending_sell_reason: str | None = None
    trailing_anchor: float = 0.0


@dataclass
class _LoopOutcome:
    orders: list[dict[str, object]]
    trades: list[dict[str, object]]
    failed_orders: list[dict[str, object]]
    fills: list[tuple[int, float, int]]
    state: _LoopState


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

        prepared = self._prepare(working, request)
        outcome = self._run_loop(
            request,
            prepared,
            position_sizing=position_sizing,
            start_index=0,
            initial=_LoopState(cash=float(request.initial_cash)),
            schedule_beyond_frame=False,
        )

        # --- vectorized equity reconstruction ---
        equity_frame = self._build_equity_curve(
            prepared.trade_dates,
            prepared.mark_prices,
            float(request.initial_cash),
            outcome.fills,
        )

        orders_frame = pd.DataFrame(outcome.orders)
        trades_frame = pd.DataFrame(outcome.trades)
        failed_orders_frame = pd.DataFrame(outcome.failed_orders)
        summary = build_single_symbol_summary(request, trades_frame, equity_frame, prepared.working)
        return SingleSymbolBacktestResult(
            orders=orders_frame,
            trades=trades_frame,
            equity_curve=equity_frame,
            failed_orders=failed_orders_frame,
            summary=summary,
        )

    def run_working_incremental(
        self,
        working: pd.DataFrame,
        request: SingleSymbolBacktestRequest,
        *,
        position_sizing: str = "full_compound",
        start_index: int | None = None,
        last_processed_date=None,
        initial_state: SymbolState | None = None,
    ) -> IncrementalSymbolResult:
        """Resume the event loop on a pre-filtered single-symbol frame.

        ``working`` includes warmup bars (they feed signal ``shift``/
        ``rolling`` computation only — no state transitions happen before
        ``start_index``). ``start_index`` is the first bar with
        ``trade_date > last_processed_date``; when omitted it is derived
        from ``last_processed_date`` (``None`` → 0, i.e. bootstrap, which
        with ``initial_state=None`` behaves exactly like
        :meth:`run_working`). Returns only rows at/after ``start_index``
        plus the final resumable :class:`SymbolState`.
        """
        self._validate(request, position_sizing)
        empty_frames = IncrementalSymbolResult(
            orders=pd.DataFrame(),
            trades=pd.DataFrame(),
            failed_orders=pd.DataFrame(),
            equity_curve=pd.DataFrame(),
            final_state=initial_state,
        )
        if working.empty:
            return empty_frames

        prepared = self._prepare(working, request)
        if start_index is None:
            if last_processed_date is None:
                start_index = 0
            else:
                start_index = int(
                    np.searchsorted(
                        prepared.trade_dates,
                        np.datetime64(pd.Timestamp(last_processed_date)),
                        side="right",
                    )
                )
        if start_index >= prepared.n:
            # No new bars for this symbol in the window: state unchanged.
            return empty_frames

        if initial_state is None:
            initial = _LoopState(cash=float(request.initial_cash))
        else:
            initial = self._init_from_symbol_state(prepared, request.symbol, initial_state)

        # The loop mutates `initial` in place; capture the window-start state
        # for equity reconstruction before running.
        start_cash = float(initial.cash)
        start_quantity = int(initial.quantity)
        outcome = self._run_loop(
            request,
            prepared,
            position_sizing=position_sizing,
            start_index=start_index,
            initial=initial,
            schedule_beyond_frame=True,
        )
        equity_frame = self._build_equity_curve(
            prepared.trade_dates,
            prepared.mark_prices,
            start_cash,
            outcome.fills,
            start_index=start_index,
            initial_quantity=start_quantity,
        )
        final_state = self._final_symbol_state(prepared.trade_dates, outcome.state)
        return IncrementalSymbolResult(
            orders=pd.DataFrame(outcome.orders),
            trades=pd.DataFrame(outcome.trades),
            failed_orders=pd.DataFrame(outcome.failed_orders),
            equity_curve=equity_frame,
            final_state=final_state,
        )

    # ------------------------------------------------------------------
    # checkpoint state mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _map_trigger_date(trade_dates: np.ndarray, trigger_date) -> int:
        """Execution index for a stored trigger date: first bar strictly
        after the trigger bar. May be ``>= n`` (execution bar not loaded
        yet — pending stays live) or ``< start_index`` (bar already past —
        the pending keeps the simulator's dead-pending semantics)."""
        return int(
            np.searchsorted(
                trade_dates, np.datetime64(pd.Timestamp(trigger_date)), side="right"
            )
        )

    def _init_from_symbol_state(
        self, prepared: _Prepared, symbol: str, state: SymbolState
    ) -> _LoopState:
        dates = prepared.trade_dates
        n = prepared.n
        initial = _LoopState(cash=float(state.cash))
        initial.quantity = int(state.quantity)
        initial.pending_buy_index = (
            self._map_trigger_date(dates, state.pending_buy_date)
            if state.pending_buy_date is not None
            else _NO_INDEX
        )
        initial.pending_sell_index = (
            self._map_trigger_date(dates, state.pending_sell_date)
            if state.pending_sell_date is not None
            else _NO_INDEX
        )
        initial.pending_sell_reason = (
            state.pending_sell_reason if initial.pending_sell_index != _NO_INDEX else None
        )
        if initial.quantity > 0:
            target = np.datetime64(pd.Timestamp(state.entry_date))
            pos = int(np.searchsorted(dates, target))
            if pos < n and dates[pos] == target:
                initial.entry_index = pos
            elif pos > 0:
                # Entry bar not in the loaded window (should not happen when
                # the loader extends the window to the oldest checkpoint
                # entry): fall back to the nearest prior bar so holding-days
                # expiry arithmetic stays approximately aligned.
                initial.entry_index = pos - 1
            else:
                raise ValueError(
                    f"entry_date {state.entry_date} for {symbol} predates the loaded "
                    "frame — enlarge warmup_days so the window covers open positions"
                )
            initial.entry_date = pd.Timestamp(state.entry_date)
            initial.entry_price = float(state.entry_price)
            initial.entry_cost = float(state.entry_cost)
            initial.entry_cost_parts = dict(state.entry_cost_parts or _zero_cost_parts())
            initial.trailing_anchor = float(state.trailing_anchor or 0.0)
        return initial

    @staticmethod
    def _final_symbol_state(trade_dates: np.ndarray, st: _LoopState) -> SymbolState | None:
        if (
            st.quantity == 0
            and st.pending_buy_index == _NO_INDEX
            and st.pending_sell_index == _NO_INDEX
        ):
            return None

        n = len(trade_dates)

        def trigger_date(index: int):
            if index == _NO_INDEX:
                return None
            # Execution bar j was scheduled at trigger bar j-1. For restored
            # pendings whose trigger bar is missing from this frame, j-1 is
            # the bar just before the execution gap — any date in that gap
            # re-maps to the same execution bar, so the state round-trips.
            idx = min(max(index - 1, 0), n - 1)
            return pd.Timestamp(trade_dates[idx]).date()

        holding = st.quantity > 0
        return SymbolState(
            cash=float(st.cash),
            quantity=int(st.quantity),
            entry_date=st.entry_date.date() if holding and st.entry_date is not None else None,
            entry_price=float(st.entry_price) if holding else None,
            entry_cost=float(st.entry_cost) if holding else None,
            entry_cost_parts=dict(st.entry_cost_parts) if holding else None,
            trailing_anchor=float(st.trailing_anchor) if holding else None,
            pending_buy_date=trigger_date(st.pending_buy_index),
            pending_sell_date=trigger_date(st.pending_sell_index),
            pending_sell_reason=(
                st.pending_sell_reason if st.pending_sell_index != _NO_INDEX else None
            ),
        )

    # ------------------------------------------------------------------
    # shared event loop (single implementation for full + incremental runs)
    # ------------------------------------------------------------------

    def _prepare(self, working: pd.DataFrame, request: SingleSymbolBacktestRequest) -> _Prepared:
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
            for column in ("is_suspended", "limit_up", "limit_down", "is_st", "pre_close",
                           "raw_open", "raw_pre_close")
            if column in working.columns
        }
        high_prices = working["high"].to_numpy(dtype=float) if "high" in working.columns else None

        # Static candidates: any bar where a signal could schedule something.
        # With stops enabled, any bar's close can cross a stop level while
        # holding — dense candidate set (sparse event-loop only without stops).
        stops_enabled = (
            request.stop_loss_pct is not None
            or request.take_profit_pct is not None
            or request.trailing_stop_pct is not None
        )
        if stops_enabled:
            candidate_bars = np.arange(n)
        elif exit_signals is not None:
            candidate_bars = np.flatnonzero(entry_signals | exit_signals)
        else:
            candidate_bars = np.flatnonzero(entry_signals)

        prepared = _Prepared(
            n=n,
            trade_dates=trade_dates,
            open_prices=open_prices,
            entry_prices=entry_prices,
            mark_prices=mark_prices,
            entry_signals=entry_signals,
            exit_signals=exit_signals,
            flag_arrays=flag_arrays,
            high_prices=high_prices,
            candidate_bars=candidate_bars,
            working=working,
        )
        return prepared

    def _run_loop(
        self,
        request: SingleSymbolBacktestRequest,
        prepared: _Prepared,
        *,
        position_sizing: str,
        start_index: int,
        initial: _LoopState,
        schedule_beyond_frame: bool,
    ) -> _LoopOutcome:
        """The trade-level event loop shared by ``run_working`` and
        ``run_working_incremental`` — one implementation, no semantic fork.

        Bars before ``start_index`` never cause state transitions (warmup
        only); ``schedule_beyond_frame`` lets triggers on the last loaded
        bar schedule pendings whose execution bar lies beyond the frame
        (used by incremental windows; full runs keep the simulator's
        ``i + 1 < n`` guard).
        """
        n = prepared.n
        open_prices = prepared.open_prices
        entry_prices = prepared.entry_prices
        mark_prices = prepared.mark_prices
        trade_dates = prepared.trade_dates
        entry_signals = prepared.entry_signals
        exit_signals = prepared.exit_signals
        flag_arrays = prepared.flag_arrays
        high_prices = prepared.high_prices
        candidate_bars = prepared.candidate_bars

        def flag(i: int, column: str) -> bool:
            # Mirrors simulator `_row_flag` exactly.
            arr = flag_arrays.get(column)
            if arr is not None and not pd.isna(arr[i]):
                return bool(arr[i])
            if column == "limit_up":
                return self.market_profile.is_limit_up(
                    request.symbol,
                    pre_close=opt_float(i, "raw_pre_close") or opt_float(i, "pre_close"),
                    price=opt_float(i, "raw_open") or float(open_prices[i]),
                    is_st=flag(i, "is_st"),
                )
            if column == "limit_down":
                return self.market_profile.is_limit_down(
                    request.symbol,
                    pre_close=opt_float(i, "raw_pre_close") or opt_float(i, "pre_close"),
                    price=opt_float(i, "raw_open") or float(open_prices[i]),
                    is_st=flag(i, "is_st"),
                )
            return False

        def opt_float(i: int, column: str) -> float | None:
            # Mirrors simulator `_optional_float` exactly.
            arr = flag_arrays.get(column)
            if arr is None or pd.isna(arr[i]):
                return None
            return float(arr[i])

        st = initial
        orders: list[dict[str, object]] = []
        trades: list[dict[str, object]] = []
        failed_orders: list[dict[str, object]] = []
        fills: list[tuple[int, float, int]] = []  # (bar, cash_after, quantity_after)

        holding_days = request.holding_days
        heap: list[int] = []  # dynamic candidates: execution/expiry/retry bars
        static_pos = int(np.searchsorted(candidate_bars, start_index))
        last_bar = start_index - 1

        # Restored state contributes its future event bars.
        if start_index <= st.pending_buy_index < n:
            heapq.heappush(heap, st.pending_buy_index)
        if start_index <= st.pending_sell_index < n:
            heapq.heappush(heap, st.pending_sell_index)
        if st.quantity > 0 and st.entry_index != _NO_INDEX and holding_days > 0:
            restored_expiry = st.entry_index + holding_days
            if start_index <= restored_expiry < n:
                heapq.heappush(heap, restored_expiry)

        def can_schedule(i: int) -> bool:
            return schedule_beyond_frame or i + 1 < n

        def push_execution(index: int) -> None:
            if index < n:
                heapq.heappush(heap, index)

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
            if st.pending_buy_index == i and st.quantity == 0:
                price_raw = float(entry_prices[i])
                price = self.market_profile.apply_slippage(OrderSide.BUY, price_raw)
                if position_sizing == "fixed_cash":
                    raw_quantity = int(float(request.initial_cash) // price)
                else:
                    raw_quantity = int(st.cash // price)
                buy_quantity = self.market_profile.round_order_quantity(OrderSide.BUY, raw_quantity)
                if buy_quantity <= 0:
                    order = Order(
                        symbol=request.symbol,
                        trade_date=pd.Timestamp(trade_dates[i]).date(),
                        side=OrderSide.BUY,
                        order_type=OrderType.MARKET,
                        quantity=buy_quantity,
                        price=price,
                    )
                    failed_orders.append(self._failed_order_row(order, "insufficient_cash"))
                    st.pending_buy_index = _NO_INDEX
                else:
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
                        st.pending_buy_index = _NO_INDEX
                    else:
                        cost = self.market_profile.calculate_cost(OrderSide.BUY, order.notional)
                        if order.notional + cost > st.cash:
                            shrunk_quantity = self.market_profile.fit_buy_quantity_to_cash(
                                buy_quantity, price, st.cash
                            )
                            if shrunk_quantity > 0:
                                # No re-validation needed: same bar/price, still
                                # lot-rounded, smaller quantity.
                                buy_quantity = shrunk_quantity
                                order = Order(
                                    symbol=request.symbol,
                                    trade_date=pd.Timestamp(trade_dates[i]).date(),
                                    side=OrderSide.BUY,
                                    order_type=OrderType.MARKET,
                                    quantity=buy_quantity,
                                    price=price,
                                )
                                cost = self.market_profile.calculate_cost(OrderSide.BUY, order.notional)
                            else:
                                failed_orders.append(self._failed_order_row(order, "insufficient_cash"))
                                st.pending_buy_index = _NO_INDEX
                                order = None
                        if order is not None:
                            total_cash_needed = order.notional + cost
                            cost_parts = self.market_profile.calculate_cost_breakdown(OrderSide.BUY, order.notional)
                            st.cash -= total_cash_needed
                            st.quantity = buy_quantity
                            st.entry_index = i
                            st.entry_price = price
                            st.entry_date = pd.Timestamp(trade_dates[i])
                            st.entry_cost = cost
                            st.entry_cost_parts = cost_parts
                            st.trailing_anchor = float(price)
                            orders.append(self._order_row(order, cost, price_raw=price_raw, cost_parts=cost_parts))
                            st.pending_buy_index = _NO_INDEX
                            fills.append((i, st.cash, st.quantity))
                            if holding_days > 0:  # 0 = 不限持仓天数，不登记到期 bar
                                expiry = i + holding_days
                                if expiry < n:
                                    heapq.heappush(heap, expiry)

            # --- sell logic (mirrors simulator lines 101-157) ---
            if st.quantity > 0 and st.entry_index != _NO_INDEX:
                if request.trailing_stop_pct is not None:
                    if high_prices is not None and not pd.isna(high_prices[i]):
                        anchor_value = float(high_prices[i])
                    else:
                        anchor_value = float(mark_prices[i])
                    st.trailing_anchor = max(st.trailing_anchor, anchor_value)
                sell_reason: str | None = None
                if st.pending_sell_index != _NO_INDEX and i == st.pending_sell_index:
                    sell_reason = st.pending_sell_reason or "exit_signal"
                elif holding_days > 0 and i == st.entry_index + holding_days:
                    sell_reason = "holding_period"
                elif (
                    request.stop_loss_pct is not None
                    and float(mark_prices[i]) <= float(st.entry_price) * (1 - request.stop_loss_pct)
                    and can_schedule(i)
                ):
                    next_index = i + 1
                    if st.pending_sell_index == _NO_INDEX or next_index < st.pending_sell_index:
                        st.pending_sell_index = next_index
                        st.pending_sell_reason = "stop_loss"
                        push_execution(next_index)
                elif (
                    request.take_profit_pct is not None
                    and float(mark_prices[i]) >= float(st.entry_price) * (1 + request.take_profit_pct)
                    and can_schedule(i)
                ):
                    next_index = i + 1
                    if st.pending_sell_index == _NO_INDEX or next_index < st.pending_sell_index:
                        st.pending_sell_index = next_index
                        st.pending_sell_reason = "take_profit"
                        push_execution(next_index)
                elif (
                    request.trailing_stop_pct is not None
                    and float(mark_prices[i]) <= st.trailing_anchor * (1 - request.trailing_stop_pct)
                    and can_schedule(i)
                ):
                    next_index = i + 1
                    if st.pending_sell_index == _NO_INDEX or next_index < st.pending_sell_index:
                        st.pending_sell_index = next_index
                        st.pending_sell_reason = "trailing_stop"
                        push_execution(next_index)
                elif (
                    exit_signals is not None
                    and bool(exit_signals[i])
                    and can_schedule(i)
                ):
                    next_index = i + 1
                    if st.pending_sell_index == _NO_INDEX or next_index < st.pending_sell_index:
                        st.pending_sell_index = next_index
                        st.pending_sell_reason = "exit_signal"
                        push_execution(next_index)

                if sell_reason is not None:
                    price_raw = float(entry_prices[i])
                    price = self.market_profile.apply_slippage(OrderSide.SELL, price_raw)
                    order = Order(
                        symbol=request.symbol,
                        trade_date=pd.Timestamp(trade_dates[i]).date(),
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET,
                        quantity=st.quantity,
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
                        st.pending_sell_index = i + 1
                        st.pending_sell_reason = sell_reason
                        push_execution(i + 1)
                    else:
                        cost = self.market_profile.calculate_cost(OrderSide.SELL, order.notional)
                        exit_cost_parts = self.market_profile.calculate_cost_breakdown(OrderSide.SELL, order.notional)
                        st.cash += order.notional - cost
                        orders.append(self._order_row(order, cost, price_raw=price_raw, cost_parts=exit_cost_parts))
                        trades.append(
                            {
                                "symbol": request.symbol,
                                "entry_date": st.entry_date,
                                "exit_date": pd.Timestamp(trade_dates[i]),
                                "quantity": st.quantity,
                                "entry_price": st.entry_price,
                                "exit_price": price,
                                "gross_pnl": (price - float(st.entry_price)) * st.quantity,
                                "cost": st.entry_cost + cost,
                                "net_pnl": (price - float(st.entry_price)) * st.quantity - st.entry_cost - cost,
                                "exit_reason": sell_reason,
                                "entry_commission": st.entry_cost_parts["commission"],
                                "entry_stamp_tax": st.entry_cost_parts["stamp_tax"],
                                "entry_transfer_fee": st.entry_cost_parts["transfer_fee"],
                                "exit_commission": exit_cost_parts["commission"],
                                "exit_stamp_tax": exit_cost_parts["stamp_tax"],
                                "exit_transfer_fee": exit_cost_parts["transfer_fee"],
                            }
                        )
                        st.quantity = 0
                        st.entry_index = _NO_INDEX
                        st.entry_price = 0.0
                        st.entry_date = None
                        st.entry_cost = 0.0
                        st.entry_cost_parts = _zero_cost_parts()
                        st.trailing_anchor = 0.0
                        st.pending_sell_index = _NO_INDEX
                        st.pending_sell_reason = None
                        fills.append((i, st.cash, st.quantity))

            # --- schedule new buy (mirrors simulator line 159) ---
            if (
                st.quantity == 0
                and st.pending_buy_index == _NO_INDEX
                and bool(entry_signals[i])
                and can_schedule(i)
            ):
                st.pending_buy_index = i + 1
                push_execution(i + 1)

        return _LoopOutcome(
            orders=orders,
            trades=trades,
            failed_orders=failed_orders,
            fills=fills,
            state=st,
        )

    @staticmethod
    def _build_equity_curve(
        trade_dates: np.ndarray,
        mark_prices: np.ndarray,
        initial_cash: float,
        fills: list[tuple[int, float, int]],
        *,
        start_index: int = 0,
        initial_quantity: int = 0,
    ) -> pd.DataFrame:
        """Rebuild the simulator's per-bar equity rows from execution segments.

        Cash and quantity only change at fills; each segment [fill_k, fill_{k+1})
        keeps the post-fill state, and market value is close * quantity. With
        ``start_index > 0`` only bars at/after it are emitted, starting from
        the (restored) ``initial_cash``/``initial_quantity`` state.
        """
        n = len(trade_dates)
        bounds = [start_index] + [bar for bar, _, _ in fills] + [n]
        seg_cash = [initial_cash] + [c for _, c, _ in fills]
        seg_qty = [initial_quantity] + [q for _, _, q in fills]
        length = n - start_index
        cash_arr = np.empty(length, dtype=float)
        qty_arr = np.empty(length, dtype=np.int64)
        for k in range(len(seg_cash)):
            s, e = bounds[k] - start_index, bounds[k + 1] - start_index
            cash_arr[s:e] = seg_cash[k]
            qty_arr[s:e] = seg_qty[k]
        market_values = qty_arr * mark_prices[start_index:]
        total_equity = cash_arr + market_values
        first_mark = float(mark_prices[0]) if n else 0.0
        buy_hold_full = (
            initial_cash * mark_prices / first_mark if first_mark > 0 else np.full(n, np.nan)
        )
        return pd.DataFrame(
            {
                "trade_date": trade_dates[start_index:],
                "cash": cash_arr,
                "position_quantity": qty_arr,
                "market_value": market_values,
                "total_equity": total_equity,
                "buy_hold_equity": buy_hold_full[start_index:],
            }
        )

    def _validate(self, request: SingleSymbolBacktestRequest, position_sizing: str) -> None:
        if request.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if request.holding_days < 0:
            raise ValueError("holding_days must be >= 0 (0 = 不限持仓天数)")
        if position_sizing not in POSITION_SIZING_MODES:
            raise ValueError(
                f"Unsupported position_sizing: {position_sizing!r} "
                f"(expected one of {POSITION_SIZING_MODES})"
            )

    def _order_row(
        self,
        order: Order,
        cost: float,
        *,
        price_raw: float | None = None,
        cost_parts: dict[str, float] | None = None,
    ) -> dict[str, object]:
        # Same shape/key order as the simulator's _order_row.
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
