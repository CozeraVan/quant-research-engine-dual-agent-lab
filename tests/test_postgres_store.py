from datetime import date

import pandas as pd
import pytest

from quant_research_engine.data.postgres import PostgresDataStore
from quant_research_engine.data.settings import DatabaseSettings


def make_store() -> PostgresDataStore:
    return PostgresDataStore(DatabaseSettings(market_db_url="postgresql+psycopg://user:pass@localhost/db"))


def test_split_table_name_defaults_public_schema():
    store = make_store()

    assert store.split_table_name("stock_daily") == ("public", "stock_daily")


def test_split_table_name_accepts_schema_qualified_table():
    store = make_store()

    assert store.split_table_name("factors.stock_daily_overlap_close") == ("factors", "stock_daily_overlap_close")


def test_split_table_name_rejects_unsafe_identifier():
    store = make_store()

    with pytest.raises(ValueError, match="Unsafe SQL identifier"):
        store.split_table_name("public.stock_daily;drop")


def test_validate_columns_rejects_unsafe_identifier():
    store = make_store()

    with pytest.raises(ValueError, match="Unsafe SQL identifier"):
        store.validate_columns(["open", "close;drop"])


def test_load_daily_bars_requires_valid_date_order():
    store = make_store()

    with pytest.raises(ValueError, match="start must be <= end"):
        store.load_daily_bars(["000001.SZ"], start=date(2026, 5, 12), end=date(2026, 5, 11))


def test_load_benchmark_bars_builds_configurable_index_query(monkeypatch):
    captured = {}

    def fake_read_sql_query(*, sql, con, params):
        captured["sql"] = str(sql)
        captured["params"] = params
        return pd.DataFrame(
            {
                "ts_code": ["000300.SH"],
                "trade_date": ["2026-01-05"],
                "close": [3500.0],
            }
        )

    monkeypatch.setattr(pd, "read_sql_query", fake_read_sql_query)
    store = make_store()

    frame = store.load_benchmark_bars(
        table_name="public.index_daily",
        ts_codes=["000300.SH"],
        start=date(2026, 1, 1),
        end=date(2026, 1, 31),
        fields=["close"],
    )

    assert "FROM public.index_daily" in captured["sql"]
    assert "ts_code IN (:ts_code_0)" in captured["sql"]
    assert captured["params"] == {
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 1, 31),
        "ts_code_0": "000300.SH",
    }
    assert frame["trade_date"].iloc[0] == pd.Timestamp("2026-01-05")


def test_load_benchmark_bars_rejects_unsafe_table_name():
    store = make_store()

    with pytest.raises(ValueError, match="Unsafe SQL identifier"):
        store.load_benchmark_bars(
            table_name="public.index_daily;drop",
            ts_codes=["000300.SH"],
            start=date(2026, 1, 1),
            end=date(2026, 1, 31),
        )


@pytest.mark.parametrize(
    ("ts_code", "expected_board"),
    [
        ("000001.SZ", "main_board"),
        ("600000.SH", "main_board"),
        ("300001.SZ", "chinext"),
        ("301001.SZ", "chinext"),
        ("688001.SH", "star_market"),
        ("430001.BJ", "beijing"),
        ("830001.BJ", "beijing"),
        ("920001.BJ", "beijing"),
    ],
)
def test_derive_board_from_ts_code(ts_code, expected_board):
    assert PostgresDataStore.derive_board(ts_code) == expected_board


class TestLoadSecurityMetadataPassthrough:
    def test_preserves_passthrough_columns_from_source_table(self, monkeypatch):
        store = make_store()

        def fake_get_table_columns(table_name, *, engine=None):
            return [
                "ts_code",
                "list_date",
                "board",
                "is_st",
                "is_risk_warning",
                "is_suspended",
                "industry",
                "sector",
            ]

        def fake_read_sql_query(*, sql, con, params):
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

        monkeypatch.setattr(store, "get_table_columns", fake_get_table_columns)
        monkeypatch.setattr(pd, "read_sql_query", fake_read_sql_query)

        frame = store.load_security_metadata()

        assert "industry" in frame.columns
        assert "sector" in frame.columns
        assert list(frame["industry"]) == ["Banking", "Tech"]
        assert list(frame["sector"]) == ["Finance", "IT"]
        # Fixed columns still present and normalized
        assert "ts_code" in frame.columns
        assert "list_date" in frame.columns
        assert "board" in frame.columns
        assert "is_st" in frame.columns

    def test_fallback_normalization_when_no_passthrough_columns(self, monkeypatch):
        store = make_store()

        def fake_get_table_columns(table_name, *, engine=None):
            return ["ts_code", "list_date", "board"]

        def fake_read_sql_query(*, sql, con, params):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "list_date": pd.to_datetime(["1991-04-03"]),
                    "board": [None],
                }
            )

        monkeypatch.setattr(store, "get_table_columns", fake_get_table_columns)
        monkeypatch.setattr(pd, "read_sql_query", fake_read_sql_query)

        frame = store.load_security_metadata()

        # Fixed columns are normalized: missing status columns are filled
        assert "is_st" in frame.columns
        assert "is_risk_warning" in frame.columns
        assert "is_suspended" in frame.columns
        assert frame["is_st"].iloc[0] == False
        # board fallback from derive_board
        assert frame["board"].iloc[0] == "main_board"
        # No passthrough columns beyond the fixed set
        assert set(frame.columns) == {
            "ts_code",
            "list_date",
            "board",
            "is_st",
            "is_risk_warning",
            "is_suspended",
        }
