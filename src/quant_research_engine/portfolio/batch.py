from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from quant_research_engine.markets.ashare import AShareMarketProfile
from quant_research_engine.portfolio.analytics import summarize_batch_summary
from quant_research_engine.portfolio.single_symbol import (
    SingleSymbolBacktestEngine,
    SingleSymbolBacktestRequest,
    SingleSymbolBacktestResult,
    empty_single_symbol_result,
)

SUMMARY_METADATA_COLUMNS = [
    "board",
    "industry",
    "industry_group",
    "benchmark",
    "is_st",
    "is_risk_warning",
]

ENGINE_IMPLS = ("simulator", "vectorized")
POSITION_SIZING_MODES = ("full_compound", "fixed_cash")


@dataclass(frozen=True)
class BatchBacktestRequest:
    symbols: list[str] | None
    initial_cash_per_symbol: float
    entry_signal: str
    holding_days: int
    exit_signal: str | None = None
    entry_price_column: str = "open"
    mark_price_column: str = "close"
    summary_metadata_columns: list[str] | None = None
    engine_impl: str = "simulator"
    position_sizing: str = "full_compound"
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    trailing_stop_pct: float | None = None


@dataclass(frozen=True)
class BatchBacktestResult:
    symbols: list[str]
    results: dict[str, SingleSymbolBacktestResult]
    summary: pd.DataFrame
    summary_metrics: dict[str, object] = field(default_factory=dict)


class BatchBacktestEngine:
    def __init__(self, market_profile: AShareMarketProfile) -> None:
        self.market_profile = market_profile
        self.single_symbol_engine = SingleSymbolBacktestEngine(market_profile)

    def run(self, frame: pd.DataFrame, request: BatchBacktestRequest) -> BatchBacktestResult:
        self._validate_request(request)
        if request.engine_impl == "vectorized":
            return self._run_vectorized(frame, request)
        if request.position_sizing != "full_compound":
            raise ValueError("position_sizing other than 'full_compound' requires engine_impl='vectorized'")
        symbols = request.symbols or self._infer_symbols(frame)
        results: dict[str, SingleSymbolBacktestResult] = {}
        summary_rows: list[dict[str, object]] = []
        extra_metadata_columns = request.summary_metadata_columns or []

        for symbol in symbols:
            single_result = self.single_symbol_engine.run(
                frame,
                SingleSymbolBacktestRequest(
                    symbol=symbol,
                    initial_cash=request.initial_cash_per_symbol,
                    entry_signal=request.entry_signal,
                    exit_signal=request.exit_signal,
                    holding_days=request.holding_days,
                    entry_price_column=request.entry_price_column,
                    mark_price_column=request.mark_price_column,
                    stop_loss_pct=request.stop_loss_pct,
                    take_profit_pct=request.take_profit_pct,
                    trailing_stop_pct=request.trailing_stop_pct,
                ),
            )
            results[symbol] = single_result
            summary_rows.append(self._summary_row(symbol, single_result, frame, extra_metadata_columns))

        summary = pd.DataFrame(summary_rows)
        return BatchBacktestResult(
            symbols=symbols,
            results=results,
            summary=summary,
            summary_metrics=summarize_batch_summary(summary),
        )

    def _run_vectorized(self, frame: pd.DataFrame, request: BatchBacktestRequest) -> BatchBacktestResult:
        """Vectorized fast path: one groupby pre-split, trade-level engine.

        Produces the same BatchBacktestResult shape (and, for
        ``position_sizing='full_compound'``, identical values) as the
        simulator path.
        """
        from quant_research_engine.portfolio.single_symbol_vectorized import (
            SingleSymbolVectorizedEngine,
        )

        vengine = SingleSymbolVectorizedEngine(self.market_profile)
        symbols = request.symbols or self._infer_symbols(frame)
        groups = dict(tuple(frame.groupby("ts_code", sort=False)))
        results: dict[str, SingleSymbolBacktestResult] = {}
        summary_rows: list[dict[str, object]] = []
        extra_metadata_columns = request.summary_metadata_columns or []

        for symbol in symbols:
            sub = groups.get(symbol)
            single_request = SingleSymbolBacktestRequest(
                symbol=symbol,
                initial_cash=request.initial_cash_per_symbol,
                entry_signal=request.entry_signal,
                exit_signal=request.exit_signal,
                holding_days=request.holding_days,
                entry_price_column=request.entry_price_column,
                mark_price_column=request.mark_price_column,
                stop_loss_pct=request.stop_loss_pct,
                take_profit_pct=request.take_profit_pct,
                trailing_stop_pct=request.trailing_stop_pct,
            )
            if sub is None:
                single_result = empty_single_symbol_result(single_request)
            else:
                single_result = vengine.run_working(
                    sub, single_request, position_sizing=request.position_sizing
                )
            results[symbol] = single_result
            # _summary_row only needs the per-symbol rows for metadata; the
            # group subframe yields the same first row as a full-frame filter.
            summary_rows.append(
                self._summary_row(symbol, single_result, sub if sub is not None else frame, extra_metadata_columns)
            )

        summary = pd.DataFrame(summary_rows)
        return BatchBacktestResult(
            symbols=symbols,
            results=results,
            summary=summary,
            summary_metrics=summarize_batch_summary(summary),
        )

    def _validate_request(self, request: BatchBacktestRequest) -> None:
        if request.initial_cash_per_symbol <= 0:
            raise ValueError("initial_cash_per_symbol must be positive")
        if request.holding_days < 0:
            raise ValueError("holding_days must be >= 0 (0 = 不限持仓天数)")
        if request.engine_impl not in ENGINE_IMPLS:
            raise ValueError(f"Unsupported engine_impl: {request.engine_impl!r} (expected one of {ENGINE_IMPLS})")
        if request.position_sizing not in POSITION_SIZING_MODES:
            raise ValueError(
                f"Unsupported position_sizing: {request.position_sizing!r} (expected one of {POSITION_SIZING_MODES})"
            )
        if request.stop_loss_pct is not None and not 0 < request.stop_loss_pct < 1:
            raise ValueError("stop_loss_pct must be in (0, 1)")
        if request.take_profit_pct is not None and request.take_profit_pct <= 0:
            raise ValueError("take_profit_pct must be positive")
        if request.trailing_stop_pct is not None and request.trailing_stop_pct <= 0:
            raise ValueError("trailing_stop_pct must be positive")

    def _infer_symbols(self, frame: pd.DataFrame) -> list[str]:
        if "ts_code" not in frame.columns:
            raise ValueError("frame must include ts_code when symbols is None")
        return sorted(frame["ts_code"].dropna().astype(str).unique().tolist())

    def _summary_row(
        self, symbol: str, result: SingleSymbolBacktestResult, frame: pd.DataFrame,
        extra_metadata_columns: list[str] | None = None,
    ) -> dict[str, object]:
        row: dict[str, object] = {"symbol": symbol}
        row.update(result.summary)
        row.update(self._metadata_row(symbol, frame, extra_metadata_columns))
        row["order_count"] = len(result.orders)
        row["failed_order_count"] = len(result.failed_orders)
        return row

    def _metadata_row(
        self, symbol: str, frame: pd.DataFrame, extra_columns: list[str] | None = None,
    ) -> dict[str, object]:
        symbol_frame = frame.loc[frame["ts_code"] == symbol]
        if symbol_frame.empty:
            return {}
        columns = list(SUMMARY_METADATA_COLUMNS)
        for col in extra_columns or []:
            if col not in columns:
                columns.append(col)
        first_row = symbol_frame.iloc[0]
        return {column: first_row[column] for column in columns if column in first_row.index}
