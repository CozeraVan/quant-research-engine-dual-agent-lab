from datetime import date

import pandas as pd

from quant_research_engine.data.assembler import ResearchFrameAssembler
from quant_research_engine.data.catalog import FactorFieldRequest


class FakeStore:
    def __init__(self) -> None:
        self.daily_fields = None
        self.factor_requests = None
        self.loaded_metadata = False

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

    def load_security_metadata(self, ts_codes=None):
        self.loaded_metadata = True
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

        def load_security_metadata(self, ts_codes=None):
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
