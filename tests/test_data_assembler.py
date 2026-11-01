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


def test_build_chunked_matches_build_rows_and_slims_metadata():
    store = FakeStore()
    assembler = ResearchFrameAssembler(store)
    factor_request = FactorFieldRequest.from_target("rsi_2", "factors.stock_daily_momentum_close.rsi_2")

    frame = assembler.build_chunked(
        ts_codes=["000001.SZ"],
        start=date(2026, 1, 5),
        end=date(2026, 1, 5),
        market_fields=["open", "close"],
        factor_fields=[factor_request],
        metadata_columns=["is_st", "is_suspended"],
        chunk_size=1,
        metadata_as_of=date(2025, 12, 31),
    )

    assert str(frame["ts_code"].dtype) == "category"
    # 只并入请求的 metadata 列（board/list_date 等富字段不膨胀到每根 K 线）
    assert set(frame.columns) == {
        "ts_code", "trade_date", "open", "close", "rsi_2", "is_st", "is_suspended",
    }
    row = frame.iloc[0]
    assert str(row["ts_code"]) == "000001.SZ"
    assert row["open"] == 10.0 and row["close"] == 10.5 and row["rsi_2"] == 8.0
    assert bool(row["is_st"]) is False and bool(row["is_suspended"]) is False
    assert store.metadata_as_of == date(2025, 12, 31)


def test_build_chunked_chunk_boundaries_do_not_change_content():
    class MultiSymbolStore(FakeStore):
        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            codes = ts_codes or ["000001.SZ", "000002.SZ", "000003.SZ"]
            rows = []
            for code in codes:
                for day in ("2026-01-05", "2026-01-06"):
                    rows.append({"ts_code": code, "trade_date": pd.Timestamp(day),
                                 "open": 10.0, "close": 10.5})
            return pd.DataFrame(rows)

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(columns=["ts_code", "trade_date"])

        def load_security_metadata(self, ts_codes=None, *, as_of=None):
            codes = ts_codes or ["000001.SZ", "000002.SZ", "000003.SZ"]
            return pd.DataFrame({
                "ts_code": codes,
                "is_st": [False] * len(codes),
                "is_suspended": [False] * len(codes),
            })

    assembler = ResearchFrameAssembler(MultiSymbolStore())
    kwargs = dict(
        ts_codes=["000001.SZ", "000002.SZ", "000003.SZ"],
        start=date(2026, 1, 5), end=date(2026, 1, 6),
        market_fields=["open", "close"], factor_fields=[],
        metadata_columns=["is_st", "is_suspended"],
    )
    one = assembler.build_chunked(chunk_size=3, **kwargs)
    many = assembler.build_chunked(chunk_size=1, **kwargs)
    key = ["ts_code", "trade_date"]
    one = one.assign(ts_code=one["ts_code"].astype(str)).sort_values(key).reset_index(drop=True)
    many = many.assign(ts_code=many["ts_code"].astype(str)).sort_values(key).reset_index(drop=True)
    pd.testing.assert_frame_equal(one, many, check_dtype=False)
    assert len(one) == 6


class _NeeqLegacyStore(FakeStore):
    """全市场宇宙（ts_codes=None）用的桩：bars 与 metadata 都含北交所三板残留代码。"""

    def load_daily_bars(self, ts_codes, start, end, fields):
        codes = list(ts_codes) if ts_codes is not None else ["000001.SZ", "920809.BJ"]
        return pd.DataFrame(
            {
                "ts_code": codes,
                "trade_date": pd.to_datetime(["2015-07-22"] * len(codes)),
                "open": [10.0] * len(codes),
                "close": [10.5] * len(codes),
            }
        )

    def load_factor_history(self, ts_codes, field_requests, start, end):
        codes = list(ts_codes) if ts_codes is not None else ["000001.SZ", "920809.BJ"]
        return pd.DataFrame(
            {
                "ts_code": codes,
                "trade_date": pd.to_datetime(["2015-07-22"] * len(codes)),
                "rsi_2": [8.0] * len(codes),
            }
        )

    def load_security_metadata(self, ts_codes=None, *, as_of=None):
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "920809.BJ"],
                "is_st": [False, False],
                "is_suspended": [False, False],
            }
        )

    def list_symbols_with_bars(self, start, end):
        return ["000001.SZ", "920809.BJ"]


def test_full_universe_drops_neeq_legacy_bj_codes():
    """QRE-UNIVERSE-NEEQ-LEGACY：全市场宇宙必须剔除 920%.BJ 三板残留代码。

    这类代码 2021-11-15 之前的历史是脏数据（close 恒 1、30 股成交），
    已把 job 58/66/74/78 的全期结果污染到 12.9%~22.6% 毛盈亏（任务已删除）。
    源数据只读不改，所以在宇宙侧设闸。
    """
    store = _NeeqLegacyStore()
    assembler = ResearchFrameAssembler(store)
    factor_request = FactorFieldRequest.from_target("rsi_2", "factors.stock_daily_momentum_close.rsi_2")

    frame = assembler.build_chunked(
        ts_codes=None,  # 全市场
        start=date(2015, 7, 22),
        end=date(2015, 7, 22),
        market_fields=["open", "close"],
        factor_fields=[factor_request],
        metadata_columns=["is_st", "is_suspended"],
        chunk_size=8,
    )

    codes = {str(c) for c in frame["ts_code"].unique()}
    assert codes == {"000001.SZ"}, f"北交所三板残留代码漏进了宇宙：{codes}"


def test_full_universe_keeps_bj_codes_when_window_is_clean():
    """加载区间整体在北交所开市（2021-11-15）之后 → 北交所代码是真实行情，不排除。"""
    store = _NeeqLegacyStore()
    assembler = ResearchFrameAssembler(store)
    factor_request = FactorFieldRequest.from_target("rsi_2", "factors.stock_daily_momentum_close.rsi_2")

    frame = assembler.build_chunked(
        ts_codes=None,
        start=date(2022, 3, 1),
        end=date(2022, 3, 1),
        market_fields=["open", "close"],
        factor_fields=[factor_request],
        metadata_columns=["is_st", "is_suspended"],
        chunk_size=8,
    )

    codes = {str(c) for c in frame["ts_code"].unique()}
    assert codes == {"000001.SZ", "920809.BJ"}, codes


def test_explicit_codes_bypass_the_neeq_filter():
    """用户显式点名不替他改（包括点名一只 920xxx）。"""
    store = _NeeqLegacyStore()
    assembler = ResearchFrameAssembler(store)
    factor_request = FactorFieldRequest.from_target("rsi_2", "factors.stock_daily_momentum_close.rsi_2")

    frame = assembler.build_chunked(
        ts_codes=["920809.BJ"],
        start=date(2015, 7, 22),
        end=date(2015, 7, 22),
        market_fields=["open", "close"],
        factor_fields=[factor_request],
        metadata_columns=["is_st", "is_suspended"],
        chunk_size=8,
    )

    assert {str(c) for c in frame["ts_code"].unique()} == {"920809.BJ"}
