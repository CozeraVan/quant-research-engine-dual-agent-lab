"""Shared symbol-metadata composer.

``reference.stock_basic`` is not populated upstream yet, so
``load_security_metadata`` leaves board/industry empty. This module composes
per-symbol metadata from the sources that *are* available:

- ``board``: derived from the ts_code pattern (``derive_board``)
- ``industry_group``: ``unknown`` placeholder until stock_basic is filled
- ``market_cap_bucket`` / ``liquidity_bucket``: from the latest
  ``reference.daily_basic`` snapshot (``total_mv`` / ``turnover_rate_f``)

Used by the research-run backtest stage (to fill summary metadata columns)
and by ``scripts/strategy_fit_report.py``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from quant_research_engine.data.tushare_security import derive_board

METADATA_COMPOSE_COLUMNS = [
    "ts_code",
    "board",
    "industry_group",
    "market_cap_bucket",
    "liquidity_bucket",
]


def compose_symbol_metadata(
    store: Any,
    ts_codes: list[str] | None,
    as_of: date | None = None,
) -> pd.DataFrame:
    """Compose per-symbol metadata for ``ts_codes`` as of ``as_of``.

    Returns a DataFrame with columns ``METADATA_COMPOSE_COLUMNS``. ``store``
    only needs ``_load_reference_daily_basic_snapshot`` (PostgresDataStore
    duck type); bucket helpers are static methods reused from
    PostgresDataStore.
    """
    from quant_research_engine.data.postgres import PostgresDataStore

    snapshot = store._load_reference_daily_basic_snapshot(ts_codes, as_of=as_of)
    if snapshot is None or snapshot.empty:
        snapshot = pd.DataFrame({"ts_code": list(ts_codes or [])})
    elif ts_codes:
        missing = sorted(set(ts_codes) - set(snapshot["ts_code"].astype(str)))
        if missing:
            snapshot = pd.concat(
                [snapshot, pd.DataFrame({"ts_code": missing})], ignore_index=True
            )

    frame = snapshot.copy()
    frame["board"] = frame["ts_code"].map(derive_board)
    if "total_mv" in frame.columns:
        frame["market_cap_bucket"] = PostgresDataStore._compute_market_cap_bucket(frame["total_mv"])
    else:
        frame["market_cap_bucket"] = pd.NA
    if "turnover_rate_f" in frame.columns:
        frame["liquidity_bucket"] = PostgresDataStore._compute_liquidity_bucket(frame["turnover_rate_f"])
    else:
        frame["liquidity_bucket"] = pd.NA
    frame["industry_group"] = "unknown"

    return frame[METADATA_COMPOSE_COLUMNS].sort_values("ts_code").reset_index(drop=True)


def merge_symbol_metadata(frame: pd.DataFrame, metadata: pd.DataFrame) -> pd.DataFrame:
    """Left-join composed metadata onto a research frame by ``ts_code``.

    Columns already present in ``frame`` are kept but their NA values are
    filled from ``metadata``; new columns are appended. The engine only reads
    its own signal/price columns, so extra columns do not change behavior.
    """
    if metadata is None or metadata.empty or "ts_code" not in frame.columns:
        return frame
    meta = metadata.drop_duplicates(subset=["ts_code"]).set_index("ts_code")
    result = frame.copy()
    new_columns = [c for c in meta.columns if c not in result.columns]
    if new_columns:
        result = result.join(meta[new_columns], on="ts_code")
    for column in (c for c in meta.columns if c in frame.columns):
        result[column] = result[column].fillna(result["ts_code"].map(meta[column]))
    return result
