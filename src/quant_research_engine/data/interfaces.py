from __future__ import annotations

from datetime import date
from typing import Protocol

import pandas as pd

from quant_research_engine.data.catalog import FactorFieldRequest


class MarketDataStore(Protocol):
    def load_daily_bars(
        self,
        ts_codes: list[str] | None,
        start: date,
        end: date,
        fields: list[str] | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        ...


class FactorDataStore(Protocol):
    def load_factor_history(
        self,
        ts_codes: list[str] | None,
        field_requests: list[FactorFieldRequest],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        ...


class ReferenceDataStore(Protocol):
    def load_calendar(self, start: date, end: date) -> pd.DataFrame:
        ...

    def load_security_metadata(self, ts_codes: list[str] | None = None, *, benchmark_code: str | None = None, as_of: date | None = None) -> pd.DataFrame:
        ...
