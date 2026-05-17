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
