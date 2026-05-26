from datetime import date

import pandas as pd

from quant_research_engine.data.catalog import FactorFieldRequest
from quant_research_engine.preflight import PreflightRequest, PreflightRunner


class FakePreflightStore:
    factor_engine = object()

    def table_exists(self, table_name, *, engine=None):
        return table_name in {"factors.stock_daily_momentum_close", "public.stock_daily"}

    def get_table_columns(self, table_name, *, engine=None):
        if table_name == "factors.stock_daily_momentum_close":
            return ["ts_code", "trade_date", "rsi_2"]
        if table_name == "public.stock_daily":
            return ["ts_code", "trade_date", "close"]
        return []

    def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ"],
                "trade_date": pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-05"]),
                "open": [10.0, 10.5, 20.0],
                "close": [10.5, 10.8, 20.5],
                "amount": [500.0, 1000.0, 10.0],
            }
        )

    def load_factor_history(self, ts_codes, field_requests, start, end):
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ"],
                "trade_date": pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-05"]),
                "rsi_2": [8.0, None, 12.0],
            }
        )

    def load_security_metadata(self, ts_codes=None, *, benchmark_code=None):
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "000002.SZ"],
                "list_date": pd.to_datetime(["1991-04-03", "2026-01-01"]),
                "board": ["main_board", "main_board"],
                "is_st": [False, True],
                "is_risk_warning": [False, False],
                "is_suspended": [False, True],
            }
        )

    def load_benchmark_bars(self, table_name, ts_codes, start, end, fields, limit=None):
        assert table_name == "public.stock_daily"
        assert ts_codes == ["000002.SZ"]
        assert fields == ["close"]
        return pd.DataFrame(
            {
                "ts_code": ["000002.SZ", "000002.SZ"],
                "trade_date": pd.to_datetime(["2026-01-02", "2026-01-05"]),
                "close": [20.0, 20.5],
            }
        )


def test_preflight_runner_reports_market_factor_join_metadata_and_benchmark():
    request = PreflightRequest(
        ts_codes=["000001.SZ", "000002.SZ", "600000.SH"],
        start=date(2026, 1, 2),
        end=date(2026, 1, 5),
        market_fields=["open", "close"],
        factor_fields=[FactorFieldRequest.from_target("rsi_2", "factors.stock_daily_momentum_close.rsi_2")],
        benchmark_table="public.stock_daily",
        benchmark_code="000002.SZ",
        benchmark_value_column="close",
    )

    report = PreflightRunner(FakePreflightStore()).run(request)

    assert report.status == "warning"
    assert report.market_rows == 3
    assert report.latest_market_date == "2026-01-05"
    assert report.missing_symbols == ["600000.SH"]
    assert report.factor_coverages["rsi_2"].non_null_rows == 2
    assert report.factor_coverages["rsi_2"].coverage_ratio == 2 / 3
    assert report.joined_rows == 3
    assert report.join_coverage_ratio == 1.0
    assert report.metadata_rows == 2
    assert report.benchmark_rows == 2
    assert report.benchmark_non_null_rows == 2
    assert any(check.name == "symbol_coverage" and check.status == "warning" for check in report.checks)


def test_preflight_universe_diagnostics_with_passthrough_metadata_columns():
    class FakeStoreWithPassthroughMetadata:
        factor_engine = object()

        def table_exists(self, table_name, *, engine=None):
            return table_name in {"factors.stock_daily_momentum_close", "public.stock_daily"}

        def get_table_columns(self, table_name, *, engine=None):
            if table_name == "factors.stock_daily_momentum_close":
                return ["ts_code", "trade_date", "rsi_2"]
            if table_name == "public.stock_daily":
                return ["ts_code", "trade_date", "close"]
            return []

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-05"]),
                    "open": [10.0, 10.5, 20.0],
                    "close": [10.5, 10.8, 20.5],
                    "amount": [500.0, 1000.0, 10.0],
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-05"]),
                    "rsi_2": [8.0, None, 12.0],
                }
            )

        def load_security_metadata(self, ts_codes=None, *, benchmark_code=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000002.SZ"],
                    "list_date": pd.to_datetime(["1991-04-03", "2026-01-01"]),
                    "board": ["main_board", "main_board"],
                    "is_st": [False, True],
                    "is_risk_warning": [False, False],
                    "is_suspended": [False, True],
                    "industry": ["Banking", "Tech"],
                    "sector": ["Finance", "IT"],
                }
            )

    request = PreflightRequest(
        ts_codes=["000001.SZ", "000002.SZ"],
        start=date(2026, 1, 2),
        end=date(2026, 1, 5),
        market_fields=["open", "close", "amount"],
        factor_fields=[],
        min_listing_days=120,
        exclude_st=True,
        exclude_suspended=True,
        exclude_risk_warning=True,
    )

    report = PreflightRunner(FakeStoreWithPassthroughMetadata()).run(request)

    # Universe diagnostics must still work correctly with extra metadata columns
    assert report.status == "warning"
    assert report.universe_total_symbols == 2
    assert report.universe_eligible_symbols == ["000001.SZ"]
    assert report.universe_excluded_symbols["st"] == ["000002.SZ"]
    assert report.universe_excluded_symbols["suspended"] == ["000002.SZ"]


def test_preflight_runner_reports_universe_filter_diagnostics():
    request = PreflightRequest(
        ts_codes=["000001.SZ", "000002.SZ"],
        start=date(2026, 1, 2),
        end=date(2026, 1, 5),
        market_fields=["open", "close", "amount"],
        factor_fields=[],
        min_listing_days=120,
        min_amount=100.0,
        exclude_st=True,
        exclude_suspended=True,
        exclude_risk_warning=True,
    )

    report = PreflightRunner(FakePreflightStore()).run(request)

    assert report.status == "warning"
    assert report.universe_total_symbols == 2
    assert report.universe_eligible_symbols == ["000001.SZ"]
    assert report.universe_excluded_symbols["new_listing"] == ["000002.SZ"]
    assert report.universe_excluded_symbols["st"] == ["000002.SZ"]
    assert report.universe_excluded_symbols["suspended"] == ["000002.SZ"]
    assert report.universe_excluded_symbols["low_amount"] == ["000002.SZ"]
    assert any(check.name == "universe" and check.status == "warning" for check in report.checks)


def test_preflight_threads_benchmark_code_to_load_security_metadata():
    captured_benchmark_code = []

    class FakeStoreWithBenchmarkCapture:
        factor_engine = object()

        def table_exists(self, table_name, *, engine=None):
            return True

        def get_table_columns(self, table_name, *, engine=None):
            return ["ts_code", "trade_date", "close"]

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000001.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-02", "2026-01-05"]),
                    "open": [10.0, 10.5],
                    "close": [10.5, 10.8],
                    "amount": [500.0, 1000.0],
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame()

        def load_security_metadata(self, ts_codes=None, *, benchmark_code=None):
            captured_benchmark_code.append(benchmark_code)
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "list_date": pd.to_datetime(["1991-04-03"]),
                    "board": ["main_board"],
                    "is_st": [False],
                    "is_risk_warning": [False],
                    "is_suspended": [False],
                }
            )

        def load_benchmark_bars(self, table_name, ts_codes, start, end, fields, limit=None):
            return pd.DataFrame()

    request = PreflightRequest(
        ts_codes=["000001.SZ"],
        start=date(2026, 1, 2),
        end=date(2026, 1, 5),
        market_fields=["open", "close"],
        factor_fields=[],
        benchmark_code="000300.SH",
    )

    PreflightRunner(FakeStoreWithBenchmarkCapture()).run(request)
    assert captured_benchmark_code == ["000300.SH"]


def test_preflight_benchmark_code_none_when_not_provided():
    captured_benchmark_code = []

    class FakeStoreWithBenchmarkCapture:
        factor_engine = object()

        def table_exists(self, table_name, *, engine=None):
            return True

        def get_table_columns(self, table_name, *, engine=None):
            return ["ts_code", "trade_date", "close"]

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000001.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-02", "2026-01-05"]),
                    "open": [10.0, 10.5],
                    "close": [10.5, 10.8],
                    "amount": [500.0, 1000.0],
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame()

        def load_security_metadata(self, ts_codes=None, *, benchmark_code=None):
            captured_benchmark_code.append(benchmark_code)
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "list_date": pd.to_datetime(["1991-04-03"]),
                    "board": ["main_board"],
                    "is_st": [False],
                    "is_risk_warning": [False],
                    "is_suspended": [False],
                }
            )

        def load_benchmark_bars(self, table_name, ts_codes, start, end, fields, limit=None):
            return pd.DataFrame()

    request = PreflightRequest(
        ts_codes=["000001.SZ"],
        start=date(2026, 1, 2),
        end=date(2026, 1, 5),
        market_fields=["open", "close"],
        factor_fields=[],
    )

    PreflightRunner(FakeStoreWithBenchmarkCapture()).run(request)
    assert captured_benchmark_code == [None]
