from datetime import date

import pandas as pd

from quant_research_engine.data.assembler import ResearchFrameAssembler
from quant_research_engine.data.catalog import FactorFieldRequest


class FakeStore:
    def __init__(self) -> None:
        self.daily_fields = None
        self.factor_requests = None
        self.loaded_metadata = False
        self.metadata_as_of = None

    def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
        self.daily_fields = fields
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": pd.to_datetime(["2026-01-05"]),
                "open": [10.0],
                "close": [10.5],
            }
        )

    def load_factor_history(self, ts_codes, field_requests, start, end):
        self.factor_requests = field_requests
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": pd.to_datetime(["2026-01-05"]),
                "rsi_2": [8.0],
            }
        )

    def load_security_metadata(self, ts_codes=None, *, as_of=None):
        self.loaded_metadata = True
        self.metadata_as_of = as_of
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


def test_research_frame_assembler_reads_declared_market_and_factor_fields():
    store = FakeStore()
    assembler = ResearchFrameAssembler(store)
    factor_request = FactorFieldRequest.from_target("rsi_2", "factors.stock_daily_momentum_close.rsi_2")

    frame = assembler.build(
        ts_codes=["000001.SZ"],
        start=date(2026, 1, 5),
        end=date(2026, 1, 5),
        market_fields=["open", "close"],
        factor_fields=[factor_request],
    )

    assert store.daily_fields == ["open", "close"]
    assert store.factor_requests == [factor_request]
    assert frame.to_dict("records") == [
        {
            "ts_code": "000001.SZ",
            "trade_date": pd.Timestamp("2026-01-05"),
            "open": 10.0,
            "close": 10.5,
            "rsi_2": 8.0,
        }
    ]


def test_research_frame_assembler_can_merge_security_metadata():
    store = FakeStore()
    assembler = ResearchFrameAssembler(store)

    frame = assembler.build(
        ts_codes=["000001.SZ"],
        start=date(2026, 1, 5),
        end=date(2026, 1, 5),
        market_fields=["open", "close"],
        factor_fields=[],
        include_metadata=True,
    )

    assert store.loaded_metadata is True
    assert frame.to_dict("records") == [
        {
            "ts_code": "000001.SZ",
            "trade_date": pd.Timestamp("2026-01-05"),
            "open": 10.0,
            "close": 10.5,
            "list_date": pd.Timestamp("1991-04-03"),
            "board": "main_board",
            "is_st": False,
            "is_risk_warning": False,
            "is_suspended": False,
        }
    ]


def test_research_frame_assembler_preserves_passthrough_metadata_columns():
    class FakeStoreWithPassthrough:
        daily_fields = None
        factor_requests = None
        loaded_metadata = False

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            self.daily_fields = fields
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-05"]),
                    "open": [10.0],
                    "close": [10.5],
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(columns=["ts_code", "trade_date"])

        def load_security_metadata(self, ts_codes=None, *, as_of=None):
            self.loaded_metadata = True
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "list_date": pd.to_datetime(["1991-04-03"]),
                    "board": ["main_board"],
                    "is_st": [False],
                    "is_risk_warning": [False],
                    "is_suspended": [False],
                    "industry": ["Banking"],
                    "market_cap": [1_000_000],
                }
            )

    store = FakeStoreWithPassthrough()
    assembler = ResearchFrameAssembler(store)

    frame = assembler.build(
        ts_codes=["000001.SZ"],
        start=date(2026, 1, 5),
        end=date(2026, 1, 5),
        market_fields=["open", "close"],
        factor_fields=[],
        include_metadata=True,
    )

    assert "industry" in frame.columns
    assert "market_cap" in frame.columns
    assert frame["industry"].iloc[0] == "Banking"
    assert frame["market_cap"].iloc[0] == 1_000_000


# --- benchmark series wiring ---


class FakeStoreWithBenchmark:
    def __init__(self, benchmark_close: list[float] | None = None):
        self.benchmark_close = benchmark_close or [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]

    def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ", "000002.SZ"],
                "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-05", "2026-01-06"]),
                "open": [10.0, 11.0, 20.0, 21.0],
                "close": [10.5, 11.2, 20.3, 21.1],
            }
        )

    def load_factor_history(self, ts_codes, field_requests, start, end):
        return pd.DataFrame(columns=["ts_code", "trade_date"])

    def load_security_metadata(self, ts_codes=None, *, as_of=None):
        return pd.DataFrame(columns=["ts_code"])

    def load_benchmark_bars(self, table_name, ts_codes, start, end, fields=None, limit=None):
        dates = pd.date_range("2026-01-05", periods=len(self.benchmark_close), freq="B")
        return pd.DataFrame(
            {
                "ts_code": [ts_codes[0]] * len(dates),
                "trade_date": dates,
                "close": self.benchmark_close,
            }
        )


def test_benchmark_columns_appear_when_params_provided():
    store = FakeStoreWithBenchmark()
    assembler = ResearchFrameAssembler(store)
    frame = assembler.build(
        ts_codes=["000001.SZ"],
        start=date(2026, 1, 5),
        end=date(2026, 1, 8),
        market_fields=["open", "close"],
        factor_fields=[],
        benchmark_table="public.index_daily",
        benchmark_code="000300.SH",
        benchmark_value_column="close",
    )
    assert "benchmark_close" in frame.columns
    assert "benchmark_return" in frame.columns
    # benchmark_close should be the same for all symbols on a given date
    assert frame["benchmark_close"].notna().any()


def test_benchmark_columns_absent_when_no_params():
    store = FakeStoreWithBenchmark()
    assembler = ResearchFrameAssembler(store)
    frame = assembler.build(
        ts_codes=["000001.SZ"],
        start=date(2026, 1, 5),
        end=date(2026, 1, 8),
        market_fields=["open", "close"],
        factor_fields=[],
    )
    assert "benchmark_close" not in frame.columns
    assert "benchmark_return" not in frame.columns


def test_benchmark_close_uses_value_column():
    """benchmark_value_column should rename to benchmark_close."""
    store = FakeStoreWithBenchmark()
    assembler = ResearchFrameAssembler(store)
    frame = assembler.build(
        ts_codes=["000001.SZ"],
        start=date(2026, 1, 5),
        end=date(2026, 1, 8),
        market_fields=["open", "close"],
        factor_fields=[],
        benchmark_table="public.index_daily",
        benchmark_code="000300.SH",
        benchmark_value_column="close",
    )
    assert "benchmark_close" in frame.columns


def test_benchmark_requires_both_table_and_code():
    """benchmark params must have both table and code to trigger loading."""
    store = FakeStoreWithBenchmark()
    assembler = ResearchFrameAssembler(store)

    # Only table, no code
    frame1 = assembler.build(
        ts_codes=["000001.SZ"],
        start=date(2026, 1, 5),
        end=date(2026, 1, 8),
        market_fields=["open", "close"],
        factor_fields=[],
        benchmark_table="public.index_daily",
        benchmark_code=None,
    )
    assert "benchmark_close" not in frame1.columns

    # Only code, no table
    frame2 = assembler.build(
        ts_codes=["000001.SZ"],
        start=date(2026, 1, 5),
        end=date(2026, 1, 8),
        market_fields=["open", "close"],
        factor_fields=[],
        benchmark_table=None,
        benchmark_code="000300.SH",
    )
    assert "benchmark_close" not in frame2.columns


# --- metadata as-of threading ---


def test_metadata_as_of_passed_to_store():
    store = FakeStore()
    assembler = ResearchFrameAssembler(store)
    as_of_date = date(2025, 12, 31)

    assembler.build(
        ts_codes=["000001.SZ"],
        start=date(2026, 1, 5),
        end=date(2026, 1, 5),
        market_fields=["open", "close"],
        factor_fields=[],
        include_metadata=True,
        metadata_as_of=as_of_date,
    )

    assert store.metadata_as_of == as_of_date


def test_metadata_as_of_none_when_omitted():
    store = FakeStore()
    assembler = ResearchFrameAssembler(store)

    assembler.build(
        ts_codes=["000001.SZ"],
        start=date(2026, 1, 5),
        end=date(2026, 1, 5),
        market_fields=["open", "close"],
        factor_fields=[],
        include_metadata=True,
    )

    assert store.metadata_as_of is None
