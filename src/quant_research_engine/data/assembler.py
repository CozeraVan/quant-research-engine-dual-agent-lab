from __future__ import annotations

from datetime import date

import pandas as pd

from quant_research_engine.data.catalog import FactorFieldRequest
from quant_research_engine.data.interfaces import FactorDataStore, MarketDataStore, ReferenceDataStore


class ResearchFrameAssembler:
    def __init__(self, store: MarketDataStore | FactorDataStore | ReferenceDataStore) -> None:
        self.store = store

    def build(
        self,
        *,
        ts_codes: list[str] | None,
        start: date,
        end: date,
        market_fields: list[str],
        factor_fields: list[FactorFieldRequest],
        include_metadata: bool = False,
        metadata_as_of: date | None = None,
        benchmark_table: str | None = None,
        benchmark_code: str | None = None,
        benchmark_value_column: str = "close",
    ) -> pd.DataFrame:
        bars = self.store.load_daily_bars(
            ts_codes=ts_codes,
            start=start,
            end=end,
            fields=market_fields,
        )
        frame = bars
        if factor_fields:
            factors = self.store.load_factor_history(
                ts_codes=ts_codes,
                field_requests=factor_fields,
                start=start,
                end=end,
            )
            frame = frame.merge(factors, on=["ts_code", "trade_date"], how="inner")
        if include_metadata:
            metadata = self.store.load_security_metadata(ts_codes=ts_codes, as_of=metadata_as_of)
            frame = frame.merge(metadata, on="ts_code", how="left")
        if benchmark_table and benchmark_code:
            benchmark_bars = self.store.load_benchmark_bars(
                table_name=benchmark_table,
                ts_codes=[benchmark_code],
                start=start,
                end=end,
                fields=[benchmark_value_column],
            )
            benchmark_bars = benchmark_bars.rename(columns={benchmark_value_column: "benchmark_close"})
            benchmark_bars["benchmark_return"] = (
                benchmark_bars.groupby("ts_code")["benchmark_close"].pct_change()
            )
            benchmark_cols = benchmark_bars[["trade_date", "benchmark_close", "benchmark_return"]].dropna(
                subset=["benchmark_close"]
            )
            frame = frame.merge(benchmark_cols, on="trade_date", how="left")
        return frame.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
