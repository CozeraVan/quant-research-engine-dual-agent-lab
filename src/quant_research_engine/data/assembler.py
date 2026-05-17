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
            metadata = self.store.load_security_metadata(ts_codes=ts_codes)
            frame = frame.merge(metadata, on="ts_code", how="left")
        return frame.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
