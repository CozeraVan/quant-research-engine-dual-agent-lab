from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from quant_research_engine.data.catalog import FactorFieldRequest


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    status: str
    message: str


@dataclass(frozen=True)
class FactorCoverage:
    logical_name: str
    table: str
    column: str
    rows: int
    non_null_rows: int
    coverage_ratio: float | None


@dataclass(frozen=True)
class PreflightRequest:
    ts_codes: list[str] | None
    start: date
    end: date
    market_fields: list[str]
    factor_fields: list[FactorFieldRequest]
    include_metadata: bool = True
    min_factor_coverage: float = 0.8
    exclude_st: bool = False
    exclude_suspended: bool = False
    exclude_risk_warning: bool = False
    min_listing_days: int | None = None
    min_amount: float | None = None
    benchmark_table: str | None = None
    benchmark_code: str | None = None
    benchmark_value_column: str = "close"


@dataclass(frozen=True)
class PreflightReport:
    status: str
    market_rows: int
    latest_market_date: str | None
    requested_symbols: list[str]
    loaded_symbols: list[str]
    missing_symbols: list[str]
    factor_coverages: dict[str, FactorCoverage] = field(default_factory=dict)
    joined_rows: int = 0
    join_coverage_ratio: float | None = None
    metadata_rows: int = 0
    universe_total_symbols: int = 0
    universe_eligible_symbols: list[str] = field(default_factory=list)
    universe_excluded_symbols: dict[str, list[str]] = field(default_factory=dict)
    benchmark_rows: int = 0
    benchmark_non_null_rows: int = 0
    checks: list[PreflightCheck] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "market_rows": self.market_rows,
            "latest_market_date": self.latest_market_date,
            "requested_symbols": self.requested_symbols,
            "loaded_symbols": self.loaded_symbols,
            "missing_symbols": self.missing_symbols,
            "factor_coverages": {
                key: {
                    "logical_name": value.logical_name,
                    "table": value.table,
                    "column": value.column,
                    "rows": value.rows,
                    "non_null_rows": value.non_null_rows,
                    "coverage_ratio": value.coverage_ratio,
                }
                for key, value in self.factor_coverages.items()
            },
            "joined_rows": self.joined_rows,
            "join_coverage_ratio": self.join_coverage_ratio,
            "metadata_rows": self.metadata_rows,
            "universe_total_symbols": self.universe_total_symbols,
            "universe_eligible_symbols": self.universe_eligible_symbols,
            "universe_excluded_symbols": self.universe_excluded_symbols,
            "benchmark_rows": self.benchmark_rows,
            "benchmark_non_null_rows": self.benchmark_non_null_rows,
            "checks": [
                {"name": check.name, "status": check.status, "message": check.message}
                for check in self.checks
            ],
        }


class PreflightRunner:
    def __init__(self, store: object) -> None:
        self.store = store

    def run(self, request: PreflightRequest) -> PreflightReport:
        checks: list[PreflightCheck] = []
        bars = self.store.load_daily_bars(
            ts_codes=request.ts_codes,
            start=request.start,
            end=request.end,
            fields=request.market_fields,
        )
        bars = self._normalize_frame(bars)
        market_rows = int(len(bars))
        latest_market_date = self._latest_date(bars)
        requested_symbols = sorted(request.ts_codes or [])
        loaded_symbols = self._symbols(bars)
        missing_symbols = sorted(set(requested_symbols).difference(loaded_symbols))
        checks.append(
            PreflightCheck(
                name="market_rows",
                status="ok" if market_rows > 0 else "error",
                message=f"loaded {market_rows} market rows",
            )
        )
        if requested_symbols:
            checks.append(
                PreflightCheck(
                    name="symbol_coverage",
                    status="ok" if not missing_symbols else "warning",
                    message=(
                        "all requested symbols loaded"
                        if not missing_symbols
                        else f"missing symbols: {', '.join(missing_symbols)}"
                    ),
                )
            )

        factor_coverages: dict[str, FactorCoverage] = {}
        factors = pd.DataFrame(columns=["ts_code", "trade_date"])
        if request.factor_fields:
            for factor in request.factor_fields:
                checks.extend(self._factor_schema_checks(factor))
            factors = self.store.load_factor_history(
                ts_codes=request.ts_codes,
                field_requests=request.factor_fields,
                start=request.start,
                end=request.end,
            )
            factors = self._normalize_frame(factors)
            for factor in request.factor_fields:
                non_null_rows = (
                    int(factors[factor.logical_name].notna().sum())
                    if factor.logical_name in factors.columns
                    else 0
                )
                rows = int(len(factors))
                coverage_ratio = non_null_rows / rows if rows else None
                factor_coverages[factor.logical_name] = FactorCoverage(
                    logical_name=factor.logical_name,
                    table=factor.qualified_table,
                    column=factor.source_column,
                    rows=rows,
                    non_null_rows=non_null_rows,
                    coverage_ratio=coverage_ratio,
                )
                status = "ok" if coverage_ratio is not None and coverage_ratio >= request.min_factor_coverage else "warning"
                if rows == 0:
                    status = "error"
                checks.append(
                    PreflightCheck(
                        name=f"factor_coverage:{factor.logical_name}",
                        status=status,
                        message=f"{non_null_rows}/{rows} non-null rows",
                    )
                )

        joined_rows = market_rows
        join_coverage_ratio = 1.0 if market_rows else None
        if request.factor_fields:
            joined = bars.merge(factors, on=["ts_code", "trade_date"], how="inner")
            joined_rows = int(len(joined))
            join_coverage_ratio = joined_rows / market_rows if market_rows else None
            checks.append(
                PreflightCheck(
                    name="factor_join",
                    status="ok" if joined_rows > 0 and join_coverage_ratio == 1.0 else "warning",
                    message=f"joined {joined_rows}/{market_rows} market rows",
                )
            )

        metadata_rows = 0
        universe_total_symbols = 0
        universe_eligible_symbols: list[str] = []
        universe_excluded_symbols: dict[str, list[str]] = {
            "new_listing": [],
            "st": [],
            "risk_warning": [],
            "suspended": [],
            "low_amount": [],
        }
        metadata = pd.DataFrame()
        if request.include_metadata:
            metadata = self.store.load_security_metadata(ts_codes=request.ts_codes, benchmark_code=request.benchmark_code)
            metadata = self._normalize_frame(metadata)
            metadata_rows = int(len(metadata))
            checks.append(
                PreflightCheck(
                    name="metadata",
                    status="ok" if metadata_rows > 0 else "warning",
                    message=f"loaded {metadata_rows} metadata rows",
                )
            )
            universe_total_symbols, universe_eligible_symbols, universe_excluded_symbols = self._universe_diagnostics(
                bars=bars,
                metadata=metadata,
                request=request,
            )
            excluded_count = len(set().union(*[set(values) for values in universe_excluded_symbols.values()]))
            checks.append(
                PreflightCheck(
                    name="universe",
                    status="ok" if excluded_count == 0 else "warning",
                    message=f"{len(universe_eligible_symbols)}/{universe_total_symbols} symbols eligible",
                )
            )

        benchmark_rows = 0
        benchmark_non_null_rows = 0
        if request.benchmark_table or request.benchmark_code:
            if not request.benchmark_table or not request.benchmark_code:
                checks.append(
                    PreflightCheck(
                        name="benchmark",
                        status="error",
                        message="benchmark_table and benchmark_code must be provided together",
                    )
                )
            else:
                benchmark = self.store.load_benchmark_bars(
                    table_name=request.benchmark_table,
                    ts_codes=[request.benchmark_code],
                    start=request.start,
                    end=request.end,
                    fields=[request.benchmark_value_column],
                )
                benchmark_rows = int(len(benchmark))
                benchmark_non_null_rows = (
                    int(benchmark[request.benchmark_value_column].notna().sum())
                    if request.benchmark_value_column in benchmark.columns
                    else 0
                )
                checks.append(
                    PreflightCheck(
                        name="benchmark",
                        status="ok" if benchmark_rows > 0 and benchmark_non_null_rows > 0 else "warning",
                        message=f"{benchmark_non_null_rows}/{benchmark_rows} non-null benchmark rows",
                    )
                )

        return PreflightReport(
            status=self._overall_status(checks),
            market_rows=market_rows,
            latest_market_date=latest_market_date,
            requested_symbols=requested_symbols,
            loaded_symbols=loaded_symbols,
            missing_symbols=missing_symbols,
            factor_coverages=factor_coverages,
            joined_rows=joined_rows,
            join_coverage_ratio=join_coverage_ratio,
            metadata_rows=metadata_rows,
            universe_total_symbols=universe_total_symbols,
            universe_eligible_symbols=universe_eligible_symbols,
            universe_excluded_symbols=universe_excluded_symbols,
            benchmark_rows=benchmark_rows,
            benchmark_non_null_rows=benchmark_non_null_rows,
            checks=checks,
        )

    def _universe_diagnostics(
        self,
        *,
        bars: pd.DataFrame,
        metadata: pd.DataFrame,
        request: PreflightRequest,
    ) -> tuple[int, list[str], dict[str, list[str]]]:
        loaded_symbols = set(self._symbols(bars))
        metadata = metadata.copy()
        if "ts_code" not in metadata.columns:
            metadata = pd.DataFrame({"ts_code": sorted(loaded_symbols)})
        metadata_symbols = set(metadata["ts_code"].dropna().astype(str).tolist())
        all_symbols = sorted(loaded_symbols.union(metadata_symbols))
        excluded: dict[str, set[str]] = {
            "new_listing": set(),
            "st": set(),
            "risk_warning": set(),
            "suspended": set(),
            "low_amount": set(),
        }

        latest_date = pd.to_datetime(bars["trade_date"].max()) if "trade_date" in bars.columns and not bars.empty else None
        if request.min_listing_days is not None and latest_date is not None and "list_date" in metadata.columns:
            meta_dates = metadata.loc[:, ["ts_code", "list_date"]].dropna(subset=["ts_code"]).copy()
            meta_dates["list_date"] = pd.to_datetime(meta_dates["list_date"])
            for _, row in meta_dates.iterrows():
                list_date = row["list_date"]
                if pd.isna(list_date):
                    continue
                listing_days = int((latest_date - list_date).days)
                if listing_days < request.min_listing_days:
                    excluded["new_listing"].add(str(row["ts_code"]))

        for flag, key, enabled in (
            ("is_st", "st", request.exclude_st),
            ("is_risk_warning", "risk_warning", request.exclude_risk_warning),
            ("is_suspended", "suspended", request.exclude_suspended),
        ):
            if enabled and flag in metadata.columns:
                flagged = metadata.loc[metadata[flag].fillna(False).astype(bool), "ts_code"]
                excluded[key].update(flagged.dropna().astype(str).tolist())

        if request.min_amount is not None and "amount" in bars.columns:
            amount_by_symbol = bars.groupby("ts_code")["amount"].mean(numeric_only=True)
            low_amount = amount_by_symbol.loc[amount_by_symbol < request.min_amount].index.astype(str).tolist()
            excluded["low_amount"].update(low_amount)
        elif request.min_amount is not None:
            excluded["low_amount"].update(all_symbols)

        excluded_any = set().union(*excluded.values()) if excluded else set()
        eligible = sorted(set(all_symbols).difference(excluded_any))
        return (
            len(all_symbols),
            eligible,
            {key: sorted(values) for key, values in excluded.items()},
        )

    def _factor_schema_checks(self, factor: FactorFieldRequest) -> list[PreflightCheck]:
        engine = getattr(self.store, "factor_engine", None)
        if not self.store.table_exists(factor.qualified_table, engine=engine):
            return [
                PreflightCheck(
                    name=f"factor_schema:{factor.logical_name}",
                    status="error",
                    message=f"missing factor table {factor.qualified_table}",
                )
            ]
        columns = self.store.get_table_columns(factor.qualified_table, engine=engine)
        if factor.source_column not in columns:
            return [
                PreflightCheck(
                    name=f"factor_schema:{factor.logical_name}",
                    status="error",
                    message=f"missing factor column {factor.qualified_table}.{factor.source_column}",
                )
            ]
        return [
            PreflightCheck(
                name=f"factor_schema:{factor.logical_name}",
                status="ok",
                message=f"found {factor.qualified_table}.{factor.source_column}",
            )
        ]

    @staticmethod
    def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
        if "trade_date" in frame.columns:
            frame = frame.copy()
            frame["trade_date"] = pd.to_datetime(frame["trade_date"])
        return frame

    @staticmethod
    def _symbols(frame: pd.DataFrame) -> list[str]:
        if "ts_code" not in frame.columns or frame.empty:
            return []
        return sorted(frame["ts_code"].dropna().astype(str).unique().tolist())

    @staticmethod
    def _latest_date(frame: pd.DataFrame) -> str | None:
        if "trade_date" not in frame.columns or frame.empty:
            return None
        return pd.Timestamp(frame["trade_date"].max()).date().isoformat()

    @staticmethod
    def _overall_status(checks: list[PreflightCheck]) -> str:
        if any(check.status == "error" for check in checks):
            return "error"
        if any(check.status == "warning" for check in checks):
            return "warning"
        return "ok"
