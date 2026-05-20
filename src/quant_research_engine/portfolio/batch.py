from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from quant_research_engine.markets.ashare import AShareMarketProfile
from quant_research_engine.portfolio.analytics import summarize_batch_summary
from quant_research_engine.portfolio.single_symbol import SingleSymbolBacktestEngine, SingleSymbolBacktestRequest, SingleSymbolBacktestResult

SUMMARY_METADATA_COLUMNS = [
    "board",
    "industry",
    "benchmark",
    "is_st",
    "is_risk_warning",
]


@dataclass(frozen=True)
class BatchBacktestRequest:
    symbols: list[str] | None
    initial_cash_per_symbol: float
    entry_signal: str
    holding_days: int
    entry_price_column: str = "open"
    mark_price_column: str = "close"
    summary_metadata_columns: list[str] | None = None


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
                    holding_days=request.holding_days,
                    entry_price_column=request.entry_price_column,
                    mark_price_column=request.mark_price_column,
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

    def _validate_request(self, request: BatchBacktestRequest) -> None:
        if request.initial_cash_per_symbol <= 0:
            raise ValueError("initial_cash_per_symbol must be positive")
        if request.holding_days <= 0:
            raise ValueError("holding_days must be positive")

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
