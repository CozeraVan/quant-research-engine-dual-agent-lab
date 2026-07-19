"""Backtest-time universe filtering (M10.2a).

Applies a strategy spec's universe rules to the assembled research frame
BEFORE the engine, with explicit per-rule drop accounting and
unavailable-data reporting. An intended rule whose data is unavailable is
reported as ``unavailable`` — never silently skipped, never silently dropped.

Data sources (read-only, graceful degradation):

- ``reference.stock_suspend`` (populated): latest record <= as_of decides
  suspension (suspend_type 'S' = suspended, 'R' = resumed).
- ``reference.stock_st`` (populated): latest record <= as_of with an ST
  marker in st_type decides ``is_st``. ``is_risk_warning`` is mapped to
  ``is_st`` (A-share risk-warning board = ST/*ST in practice; documented
  approximation).
- ``public.stock_daily``: per-symbol first trade_date derives ``list_date``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import text

ALLOWED_PROFILE_OVERRIDES = {
    "commission_rate",
    "min_commission",
    "stamp_tax_sell",
    "transfer_fee_rate",
    "slippage_buy_rate",
    "slippage_sell_rate",
}


@dataclass(frozen=True)
class UniverseFilterSpec:
    exclude_st: bool = False
    exclude_suspended: bool = False
    exclude_risk_warning: bool = False
    min_listing_days: int | None = None
    min_amount: float | None = None

    def any_enabled(self) -> bool:
        return bool(
            self.exclude_st
            or self.exclude_suspended
            or self.exclude_risk_warning
            or self.min_listing_days is not None
            or self.min_amount is not None
        )


@dataclass
class UniverseFilterReport:
    applied: bool
    input_rows: int = 0
    output_rows: int = 0
    input_symbols: int = 0
    output_symbols: int = 0
    dropped_by_rule: dict[str, int] = field(default_factory=dict)
    unavailable_rules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "input_rows": self.input_rows,
            "output_rows": self.output_rows,
            "input_symbols": self.input_symbols,
            "output_symbols": self.output_symbols,
            "dropped_by_rule": self.dropped_by_rule,
            "unavailable_rules": self.unavailable_rules,
        }


# ---------------------------------------------------------------------------
# metadata loader (read-only, graceful degradation)
# ---------------------------------------------------------------------------


def _placeholders(ts_codes: list[str], params: dict[str, Any], prefix: str = "c") -> str:
    keys = []
    for index, ts_code in enumerate(ts_codes):
        key = f"{prefix}_{index}"
        params[key] = ts_code
        keys.append(f":{key}")
    return ", ".join(keys)


def load_universe_metadata(
    store,
    ts_codes: list[str] | None,
    *,
    as_of: date,
) -> pd.DataFrame:
    """Per-symbol availability table: ts_code, is_suspended, is_st,
    is_risk_warning, list_date. Columns are NaN when their source is missing
    so the filter can report rules as unavailable.
    """
    codes = sorted(set(ts_codes)) if ts_codes else None
    base = pd.DataFrame({"ts_code": codes or []})

    # --- suspension status as of `as_of` (latest record per symbol) ---
    if store.table_exists("reference.stock_suspend", engine=store.reference_engine):
        params: dict[str, Any] = {"as_of": as_of}
        query = """
            SELECT ts_code, suspend_type FROM (
                SELECT ts_code, suspend_type,
                       ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date DESC) AS rn
                FROM reference.stock_suspend
                WHERE trade_date <= :as_of
            ) latest WHERE rn = 1
        """
        if codes:
            query += f" AND ts_code IN ({_placeholders(codes, params, 's')})"
        susp = pd.read_sql_query(text(query), con=store.reference_engine, params=params)
        if not susp.empty:
            susp["is_suspended"] = susp["suspend_type"].astype(str).str.upper().str.startswith("S")
            base = base.merge(susp[["ts_code", "is_suspended"]], on="ts_code", how="outer")

    # --- ST / risk-warning status as of `as_of` ---
    if store.table_exists("reference.stock_st", engine=store.reference_engine):
        params = {"as_of": as_of}
        query = """
            SELECT ts_code, st_type FROM (
                SELECT ts_code, st_type,
                       ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date DESC) AS rn
                FROM reference.stock_st
                WHERE trade_date <= :as_of
            ) latest WHERE rn = 1
        """
        if codes:
            query += f" AND ts_code IN ({_placeholders(codes, params, 't')})"
        st = pd.read_sql_query(text(query), con=store.reference_engine, params=params)
        if not st.empty:
            st["is_st"] = st["st_type"].astype(str).str.upper().str.contains("ST", regex=False)
            base = base.merge(st[["ts_code", "is_st"]], on="ts_code", how="outer")

    # --- listing date derived from first daily bar ---
    daily_table = store.settings.tables.market_daily_table
    if store.table_exists(daily_table):
        params = {}
        query = f"SELECT ts_code, MIN(trade_date) AS list_date FROM {store.qualified_table(daily_table)}"
        if codes:
            query += f" WHERE ts_code IN ({_placeholders(codes, params, 'd')})"
        query += " GROUP BY ts_code"
        listing = pd.read_sql_query(text(query), con=store.market_engine, params=params)
        if not listing.empty:
            base = base.merge(listing, on="ts_code", how="outer")

    if "is_st" in base.columns:
        base["is_risk_warning"] = base["is_st"]
    return base


# ---------------------------------------------------------------------------
# filter
# ---------------------------------------------------------------------------


def apply_universe_filter(
    frame: pd.DataFrame,
    spec: UniverseFilterSpec,
    *,
    start: date,
    metadata: pd.DataFrame,
) -> tuple[pd.DataFrame, UniverseFilterReport]:
    """Symbol-level universe filtering. Returns (filtered_frame, report)."""
    report = UniverseFilterReport(applied=spec.any_enabled())
    report.input_rows = len(frame)
    report.input_symbols = int(frame["ts_code"].nunique()) if not frame.empty else 0
    if not spec.any_enabled() or frame.empty:
        report.output_rows = report.input_rows
        report.output_symbols = report.input_symbols
        return frame, report

    symbols = pd.Series(sorted(frame["ts_code"].astype(str).unique()), name="ts_code")
    flags = pd.DataFrame({"ts_code": symbols})
    drop_reasons: dict[str, pd.Series] = {}

    meta = metadata.copy() if not metadata.empty else pd.DataFrame(columns=["ts_code"])
    for column in ("is_st", "is_suspended", "is_risk_warning", "list_date"):
        if column not in meta.columns:
            meta[column] = pd.NA

    def _flag(column: str, rule: str) -> pd.Series | None:
        """Map ts_code -> bool for the rule; None marks the rule unavailable."""
        values = meta[column]
        if values.isna().all():
            report.unavailable_rules.append(rule)
            return None
        mapped = symbols.map(meta.set_index("ts_code")[column])
        return mapped.fillna(False).astype(bool)

    if spec.exclude_st:
        st_flags = _flag("is_st", "exclude_st")
        if st_flags is not None:
            drop_reasons["exclude_st"] = st_flags

    if spec.exclude_risk_warning:
        rw_flags = _flag("is_risk_warning", "exclude_risk_warning")
        if rw_flags is not None:
            drop_reasons["exclude_risk_warning"] = rw_flags

    if spec.exclude_suspended:
        susp_flags = _flag("is_suspended", "exclude_suspended")
        if susp_flags is not None:
            drop_reasons["exclude_suspended"] = susp_flags

    if spec.min_listing_days is not None:
        list_dates = meta["list_date"]
        if list_dates.isna().all():
            report.unavailable_rules.append("min_listing_days")
        else:
            cutoff = start - timedelta(days=spec.min_listing_days)
            parsed = pd.to_datetime(list_dates, errors="coerce")
            mapped = symbols.map(meta.set_index("ts_code")["list_date"])
            mapped = pd.to_datetime(mapped, errors="coerce")
            drop_reasons["min_listing_days"] = (mapped > pd.Timestamp(cutoff)).fillna(False)

    if spec.min_amount is not None:
        if "amount" not in frame.columns:
            report.unavailable_rules.append("min_amount")
        else:
            mean_amount = frame.groupby(frame["ts_code"].astype(str))["amount"].mean()
            mapped = symbols.map(mean_amount)
            drop_reasons["min_amount"] = (mapped < spec.min_amount).fillna(False)

    drop_mask = pd.Series(False, index=symbols.index)
    for rule, mask in drop_reasons.items():
        report.dropped_by_rule[rule] = int(mask.sum())
        drop_mask = drop_mask | mask

    keep_symbols = set(symbols[~drop_mask].astype(str))
    filtered = frame.loc[frame["ts_code"].astype(str).isin(keep_symbols)].copy()
    report.output_rows = len(filtered)
    report.output_symbols = int(filtered["ts_code"].nunique()) if not filtered.empty else 0
    return filtered, report


# ---------------------------------------------------------------------------
# market profile overrides
# ---------------------------------------------------------------------------


def validate_profile_overrides(overrides: dict[str, float]) -> None:
    unknown = sorted(set(overrides) - ALLOWED_PROFILE_OVERRIDES)
    if unknown:
        raise ValueError(
            f"Unknown profile override keys: {unknown} "
            f"(allowed: {sorted(ALLOWED_PROFILE_OVERRIDES)})"
        )
    negative = {k: v for k, v in overrides.items() if v < 0}
    if negative:
        raise ValueError(f"Profile overrides must be non-negative: {negative}")
