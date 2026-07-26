"""Incremental backtest orchestration (P1, batch mode, vectorized engine).

Daily-update flow per strategy (see ``docs/design/incremental_backtest.md``):

1. Load the checkpoint at ``<output_root>/<strategy_id>/state.json`` — a
   config_hash/schema mismatch means "no checkpoint" (full rebuild).
2. ``D = checkpoint.last_processed_date``; ``W = data watermark`` (explicit
   ``request.watermark`` or ``MAX(trade_date)`` of the market table, capped
   at ``request.end``). ``W <= D`` → no-op.
3. Load frames for ``[D - warmup, W]`` (bootstrap: ``[start, W]`` — no
   warmup, matching the batch full run exactly), chunked by symbol.
4. Per symbol: restore state from the checkpoint (or reconstruct flat
   symbols' cash by replaying the cumulative orders ledger — bit-identical
   to the engine's own cash path) and run
   :meth:`SingleSymbolVectorizedEngine.run_working_incremental`, which
   processes only bars ``> D``.
5. Append/dedup the ledgers, recompute ``summary.csv`` from the cumulative
   ledgers, then write the new checkpoint LAST (ledger-first ordering makes
   a crash mid-run re-executable: the next run redoes the same window and
   ledger dedup absorbs the duplicate rows).

Ledger layout under ``<output_root>/<strategy_id>/``::

    state.json           checkpoint (written last)
    orders.csv           dedup key (symbol, trade_date, side)
    trades.csv           dedup key (symbol, entry_date, exit_date)
    failed_orders.csv    dedup key (symbol, trade_date, side)
    equity_curve.csv     append-only (symbol, trade_date, cash, quantity,
                         market_value, total_equity); dedup on read
    summary_inputs.json  per-symbol buy-hold edges + first-row metadata,
                         needed to recompute summary.csv without the frame
    summary.csv          recomputed from cumulative ledgers every update
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_research_engine.data.assembler import ResearchFrameAssembler
from quant_research_engine.markets.ashare import AShareMarketProfile
from quant_research_engine.orchestration.incremental_state import (
    StrategyCheckpoint,
    SymbolState,
    compute_config_hash,
    load_checkpoint,
    save_checkpoint,
)
from quant_research_engine.portfolio.batch import SUMMARY_METADATA_COLUMNS
from quant_research_engine.portfolio.single_symbol import SingleSymbolBacktestRequest
from quant_research_engine.portfolio.single_symbol_vectorized import (
    SingleSymbolVectorizedEngine,
)
from quant_research_engine.strategies.spec import StrategySpec

ORDERS_KEY = ["symbol", "trade_date", "side"]
TRADES_KEY = ["symbol", "entry_date", "exit_date"]
FAILED_KEY = ["symbol", "trade_date", "side"]

SUMMARY_COLUMNS = [
    "symbol",
    "initial_cash",
    "final_equity",
    "total_return",
    "trade_count",
    "win_rate",
    "total_cost",
    "buy_hold_return",
    "excess_return_vs_buy_hold",
    "order_count",
    "failed_order_count",
]


@dataclass(frozen=True)
class IncrementalRequest:
    strategy_path: Path
    start: date
    end: date
    output_root: Path
    initial_cash: float = 1_000_000
    engine_impl: str = "vectorized"
    position_sizing: str = "full_compound"
    apply_stops: bool = False
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    trailing_stop_pct: float | None = None
    universe_filter: bool = False
    codes: list[str] | None = None
    warmup_days: int = 150
    watermark: date | None = None  # default: query the market table MAX(trade_date)
    symbol_chunk_size: int = 400


@dataclass
class IncrementalResult:
    strategy_id: str
    updated: bool
    new_rows: dict[str, int] = field(default_factory=dict)
    watermark: date | None = None
    last_processed_date: date | None = None
    checkpoint_path: Path | None = None
    state_dir: Path | None = None
    symbols_processed: int = 0
    duration_s: float = 0.0


# ---------------------------------------------------------------------------
# ledger IO
# ---------------------------------------------------------------------------


def _read_csv(path: Path, parse_dates: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, parse_dates=parse_dates)


def _update_row_ledger(
    path: Path,
    new_rows: pd.DataFrame,
    *,
    subset: list[str],
    sort_cols: list[str],
    parse_dates: list[str],
) -> None:
    """Full read + concat + dedup(keep last) + rewrite (row ledgers are small)."""
    frames = []
    existing = _read_csv(path, parse_dates)
    if not existing.empty:
        frames.append(existing)
    if not new_rows.empty:
        frames.append(new_rows)
    if not frames:
        return
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(subset=subset, keep="last")
    combined = combined.sort_values(sort_cols, kind="stable").reset_index(drop=True)
    combined.to_csv(path, index=False)


def _append_equity_ledger(path: Path, new_rows: pd.DataFrame) -> None:
    """Append-only equity ledger; duplicates (crash re-run) are absorbed by
    dedup at summary recompute time."""
    if new_rows.empty:
        return
    new_rows.to_csv(path, mode="a", header=not path.exists(), index=False)


def _json_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if value is pd.NaT:
        return None
    return value


def _load_summary_inputs(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _update_summary_inputs(
    inputs: dict[str, dict[str, Any]],
    symbol: str,
    effective_rows: pd.DataFrame,
    *,
    entry_price_column: str,
    mark_price_column: str,
) -> None:
    """Record buy-hold edges + first-row metadata for one symbol.

    ``effective_rows`` are this window's new bars (trade_date > D, or the
    full loaded frame on bootstrap) sorted by date — matching the batch
    run's per-symbol frame edges over the full window.
    """
    if effective_rows.empty:
        return
    entry = inputs.get(symbol)
    if entry is None:
        first = effective_rows.iloc[0]
        metadata = {
            column: _json_scalar(first[column])
            for column in SUMMARY_METADATA_COLUMNS
            if column in effective_rows.columns
        }
        entry = {
            "first_trade_date": str(pd.Timestamp(first["trade_date"]).date()),
            "first_entry_price": float(first[entry_price_column]),
            "first_mark_price": float(first[mark_price_column]),
            "metadata": metadata,
        }
        inputs[symbol] = entry
    last = effective_rows.iloc[-1]
    entry["last_trade_date"] = str(pd.Timestamp(last["trade_date"]).date())
    entry["last_mark_price"] = float(last[mark_price_column])


def _recompute_summary(
    state_dir: Path,
    *,
    initial_cash: float,
    symbols: list[str],
) -> pd.DataFrame:
    """Rebuild summary.csv from the cumulative ledgers (batch-aligned rows)."""
    orders = _read_csv(state_dir / "orders.csv", ["trade_date"])
    trades = _read_csv(state_dir / "trades.csv", ["entry_date", "exit_date"])
    failed = _read_csv(state_dir / "failed_orders.csv", ["trade_date"])
    equity = _read_csv(state_dir / "equity_curve.csv", ["trade_date"])
    if not equity.empty:
        equity = equity.drop_duplicates(subset=["symbol", "trade_date"], keep="last")
    inputs = _load_summary_inputs(state_dir / "summary_inputs.json")

    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        final_equity = initial_cash
        if not equity.empty:
            sym_eq = equity.loc[equity["symbol"] == symbol]
            if not sym_eq.empty:
                sym_eq = sym_eq.sort_values("trade_date", kind="stable")
                final_equity = float(sym_eq.iloc[-1]["total_equity"])
        total_return = final_equity / initial_cash - 1

        sym_trades = trades.loc[trades["symbol"] == symbol] if not trades.empty else trades
        trade_count = int(len(sym_trades))
        win_rate = None if trade_count == 0 else float((sym_trades["net_pnl"] > 0).mean())
        total_cost = 0.0 if trade_count == 0 else float(sym_trades["cost"].sum())

        buy_hold_return = None
        excess_return = None
        metadata: dict[str, Any] = {}
        entry = inputs.get(symbol)
        if entry is not None:
            first_price = entry.get("first_entry_price")
            last_price = entry.get("last_mark_price")
            if first_price and last_price is not None and first_price > 0:
                buy_hold_return = last_price / first_price - 1.0
                excess_return = total_return - buy_hold_return
            metadata = dict(entry.get("metadata") or {})

        row: dict[str, Any] = {
            "symbol": symbol,
            "initial_cash": initial_cash,
            "final_equity": final_equity,
            "total_return": total_return,
            "trade_count": trade_count,
            "win_rate": win_rate,
            "total_cost": total_cost,
            "buy_hold_return": buy_hold_return,
            "excess_return_vs_buy_hold": excess_return,
        }
        row.update(metadata)
        row["order_count"] = (
            int((orders["symbol"] == symbol).sum()) if not orders.empty else 0
        )
        row["failed_order_count"] = (
            int((failed["symbol"] == symbol).sum()) if not failed.empty else 0
        )
        rows.append(row)

    summary = pd.DataFrame(rows)
    summary.to_csv(state_dir / "summary.csv", index=False)
    return summary


def _replay_cash(orders: pd.DataFrame, symbol: str, initial_cash: float) -> float:
    """Reconstruct a flat symbol's cash by replaying its cumulative orders.

    Bit-identical to the engine's own cash path (same operations in the same
    order), which keeps incremental equity curves byte-equal to a full run.
    """
    cash = float(initial_cash)
    if orders.empty:
        return cash
    sym_orders = orders.loc[orders["symbol"] == symbol].sort_values("trade_date", kind="stable")
    for row in sym_orders.itertuples():
        if row.side == "buy":
            cash -= row.notional + row.cost
        else:
            cash += row.notional - row.cost
    return cash


# ---------------------------------------------------------------------------
# main entry
# ---------------------------------------------------------------------------


def run_incremental(store, spec: StrategySpec, request: IncrementalRequest) -> IncrementalResult:
    t0 = time.perf_counter()
    if request.engine_impl != "vectorized":
        raise ValueError("incremental backtest supports engine_impl='vectorized' only")

    strategy_id = Path(request.strategy_path).stem
    state_dir = Path(request.output_root) / strategy_id
    state_dir.mkdir(parents=True, exist_ok=True)

    # --- effective stops (same request-over-spec rule as research_run) ---
    if request.apply_stops:
        stop_loss = request.stop_loss_pct if request.stop_loss_pct is not None else spec.stop_loss_pct
        take_profit = request.take_profit_pct if request.take_profit_pct is not None else spec.take_profit_pct
        trailing_stop = request.trailing_stop_pct if request.trailing_stop_pct is not None else spec.trailing_stop_pct
    else:
        stop_loss = take_profit = trailing_stop = None

    market_profile = AShareMarketProfile()
    config_hash = compute_config_hash(
        request.strategy_path,
        request.engine_impl,
        asdict(market_profile),
        {
            "apply_stops": request.apply_stops,
            "stop_loss_pct": stop_loss,
            "take_profit_pct": take_profit,
            "trailing_stop_pct": trailing_stop,
            "position_sizing": request.position_sizing,
            "initial_cash": request.initial_cash,
            "holding_days": spec.holding_days,
        },
        {
            "universe_filter": request.universe_filter,
            "exclude_st": spec.exclude_st,
            "exclude_suspended": spec.exclude_suspended,
            "exclude_risk_warning": spec.exclude_risk_warning,
            "min_listing_days": spec.min_listing_days,
            "min_amount": spec.min_amount,
        },
    )

    checkpoint = load_checkpoint(state_dir / "state.json", expected_config_hash=config_hash)
    last_processed = checkpoint.last_processed_date if checkpoint else None

    # --- watermark ---
    watermark = request.watermark
    if watermark is None:
        from quant_research_engine.orchestration.refresh import data_watermark

        watermark = data_watermark(store)
    if watermark is None:
        return IncrementalResult(
            strategy_id=strategy_id, updated=False, state_dir=state_dir,
            duration_s=time.perf_counter() - t0,
        )
    watermark = min(watermark, request.end)

    if last_processed is not None and watermark <= last_processed:
        return IncrementalResult(
            strategy_id=strategy_id,
            updated=False,
            new_rows={"orders": 0, "trades": 0, "failed_orders": 0, "equity_curve": 0},
            watermark=watermark,
            last_processed_date=last_processed,
            checkpoint_path=state_dir / "state.json",
            state_dir=state_dir,
            duration_s=time.perf_counter() - t0,
        )
    if last_processed is None and watermark < request.start:
        return IncrementalResult(
            strategy_id=strategy_id, updated=False, watermark=watermark,
            state_dir=state_dir, duration_s=time.perf_counter() - t0,
        )

    # --- symbol set + load window ---
    cp_states: dict[str, SymbolState] = dict(checkpoint.symbols) if checkpoint else {}
    window_start = last_processed or request.start
    if request.codes is not None:
        symbols = sorted(set(request.codes) | set(cp_states))
    else:
        symbols = sorted(set(store.list_symbols_with_bars(window_start, watermark)) | set(cp_states))

    if last_processed is None:
        load_start = request.start  # bootstrap: identical frame to a batch full run
    else:
        load_start = last_processed - timedelta(days=request.warmup_days * 2)
        entry_dates = [
            state.entry_date for state in cp_states.values()
            if state.quantity > 0 and state.entry_date is not None
        ]
        if entry_dates:
            load_start = min(load_start, min(entry_dates) - timedelta(days=7))

    # --- universe filter (affects NEW entries only; checkpoint symbols keep
    # their positions regardless — design §4.3) ---
    universe_spec = None
    universe_metadata = None
    if request.universe_filter:
        from quant_research_engine.portfolio.universe import (
            UniverseFilterSpec,
            load_universe_metadata,
        )

        universe_spec = UniverseFilterSpec(
            exclude_st=spec.exclude_st,
            exclude_suspended=spec.exclude_suspended,
            exclude_risk_warning=spec.exclude_risk_warning,
            min_listing_days=spec.min_listing_days,
            min_amount=spec.min_amount,
        )
        if universe_spec.any_enabled():
            universe_metadata = load_universe_metadata(store, symbols, as_of=request.start)

    # --- flat symbols' cash reconstructed from the cumulative orders ledger
    # (checkpoint drops flat/no-pending symbols; their cash is initial_cash
    # plus the exact replay of their historical orders) ---
    orders_ledger = pd.DataFrame()
    if checkpoint is not None:
        orders_ledger = _read_csv(state_dir / "orders.csv", ["trade_date"])

    engine = SingleSymbolVectorizedEngine(market_profile)
    assembler = ResearchFrameAssembler(store)
    summary_inputs = _load_summary_inputs(state_dir / "summary_inputs.json")

    new_orders: list[pd.DataFrame] = []
    new_trades: list[pd.DataFrame] = []
    new_failed: list[pd.DataFrame] = []
    new_equity: list[pd.DataFrame] = []
    new_states: dict[str, SymbolState | None] = dict(cp_states)
    processed_symbols: list[str] = []

    chunk_size = max(int(request.symbol_chunk_size), 1)
    for chunk_start in range(0, len(symbols), chunk_size):
        chunk = symbols[chunk_start : chunk_start + chunk_size]
        frame = assembler.build(
            ts_codes=chunk,
            start=load_start,
            end=watermark,
            market_fields=spec.market_fields,
            factor_fields=spec.factor_fields,
        )
        if universe_metadata is not None:
            from quant_research_engine.portfolio.universe import apply_universe_filter

            filtered, _report = apply_universe_filter(
                frame, universe_spec, start=request.start, metadata=universe_metadata
            )
            allowed = set(filtered["ts_code"].astype(str)) | (set(chunk) & set(cp_states))
            frame = frame.loc[frame["ts_code"].astype(str).isin(allowed)]
        if frame.empty:
            continue
        frame["trade_date"] = pd.to_datetime(frame["trade_date"])
        groups = dict(tuple(frame.groupby("ts_code", sort=False)))

        for symbol in chunk:
            sub = groups.get(symbol)
            if sub is None:
                continue  # no bars in the loaded window: state carried forward
            state = new_states.get(symbol)
            if state is None and checkpoint is not None and not orders_ledger.empty:
                if (orders_ledger["symbol"] == symbol).any():
                    state = SymbolState(
                        cash=_replay_cash(orders_ledger, symbol, request.initial_cash)
                    )
            single_request = SingleSymbolBacktestRequest(
                symbol=symbol,
                initial_cash=request.initial_cash,
                entry_signal=spec.signal_expression,
                exit_signal=spec.exit_signal_expression,
                holding_days=spec.holding_days,
                stop_loss_pct=stop_loss,
                take_profit_pct=take_profit,
                trailing_stop_pct=trailing_stop,
            )
            result = engine.run_working_incremental(
                sub,
                single_request,
                position_sizing=request.position_sizing,
                last_processed_date=last_processed,
                initial_state=state,
            )
            new_states[symbol] = result.final_state
            if not result.orders.empty:
                new_orders.append(result.orders)
            if not result.trades.empty:
                new_trades.append(result.trades)
            if not result.failed_orders.empty:
                new_failed.append(result.failed_orders)
            if not result.equity_curve.empty:
                equity = result.equity_curve.copy()
                # Re-anchor buy-hold to the ORIGINAL backtest window's first
                # mark price (the engine's frame-local anchor is the warmup
                # start in continuation windows, which would break equality
                # with a full single-pass run).
                anchor = summary_inputs.get(symbol, {}).get("first_mark_price")
                if anchor is None or anchor <= 0:
                    anchor = float(sub.iloc[0][single_request.mark_price_column])
                mark_by_date = sub.set_index("trade_date")[single_request.mark_price_column]
                equity["buy_hold_equity"] = (
                    single_request.initial_cash
                    * equity["trade_date"].map(mark_by_date).astype(float)
                    / anchor
                )
                equity.insert(0, "symbol", symbol)
                equity = equity.rename(columns={"position_quantity": "quantity"})
                new_equity.append(equity)
            # summary inputs: batch-equivalent frame edges for this symbol
            if last_processed is None:
                effective = sub
            else:
                effective = sub.loc[sub["trade_date"] > pd.Timestamp(last_processed)]
            _update_summary_inputs(
                summary_inputs,
                symbol,
                effective.sort_values("trade_date"),
                entry_price_column=single_request.entry_price_column,
                mark_price_column=single_request.mark_price_column,
            )
            processed_symbols.append(symbol)

    orders_new = pd.concat(new_orders, ignore_index=True) if new_orders else pd.DataFrame()
    trades_new = pd.concat(new_trades, ignore_index=True) if new_trades else pd.DataFrame()
    failed_new = pd.concat(new_failed, ignore_index=True) if new_failed else pd.DataFrame()
    equity_new = pd.concat(new_equity, ignore_index=True) if new_equity else pd.DataFrame()

    # --- ledger writes FIRST, checkpoint LAST ---
    _update_row_ledger(
        state_dir / "orders.csv", orders_new,
        subset=ORDERS_KEY, sort_cols=["symbol", "trade_date"], parse_dates=["trade_date"],
    )
    _update_row_ledger(
        state_dir / "trades.csv", trades_new,
        subset=TRADES_KEY, sort_cols=["symbol", "entry_date"], parse_dates=["entry_date", "exit_date"],
    )
    _update_row_ledger(
        state_dir / "failed_orders.csv", failed_new,
        subset=FAILED_KEY, sort_cols=["symbol", "trade_date"], parse_dates=["trade_date"],
    )
    _append_equity_ledger(state_dir / "equity_curve.csv", equity_new)
    (state_dir / "summary_inputs.json").write_text(
        json.dumps(summary_inputs, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    summary_symbols = sorted(set(summary_inputs) | set(processed_symbols) | set(new_states))
    _recompute_summary(state_dir, initial_cash=request.initial_cash, symbols=summary_symbols)

    final_states = {
        symbol: state for symbol, state in new_states.items() if state is not None
    }
    new_checkpoint = StrategyCheckpoint(
        strategy_id=strategy_id,
        config_hash=config_hash,
        last_processed_date=watermark,
        data_watermark=watermark,
        symbols=final_states,
    )
    checkpoint_path = save_checkpoint(state_dir / "state.json", new_checkpoint)

    return IncrementalResult(
        strategy_id=strategy_id,
        updated=True,
        new_rows={
            "orders": len(orders_new),
            "trades": len(trades_new),
            "failed_orders": len(failed_new),
            "equity_curve": len(equity_new),
        },
        watermark=watermark,
        last_processed_date=watermark,
        checkpoint_path=checkpoint_path,
        state_dir=state_dir,
        symbols_processed=len(processed_symbols),
        duration_s=time.perf_counter() - t0,
    )
