from datetime import date

import pandas as pd
import pytest

from quant_research_engine.data.postgres import PostgresDataStore
from quant_research_engine.data.settings import DatabaseSettings, DatabaseTableConfig


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
        # Set explicit metadata table so we bypass reference.* composition.
        store = PostgresDataStore(
            DatabaseSettings(
                market_db_url="postgresql+psycopg://user:pass@localhost/db",
                tables=DatabaseTableConfig(security_metadata_table="public.my_metadata"),
            )
        )

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
        store = PostgresDataStore(
            DatabaseSettings(
                market_db_url="postgresql+psycopg://user:pass@localhost/db",
                tables=DatabaseTableConfig(security_metadata_table="public.my_metadata"),
            )
        )

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


class TestBenchmarkEngineRouting:
    def test_benchmark_engine_uses_benchmark_db_url_when_configured(self):
        store = PostgresDataStore(
            DatabaseSettings(
                market_db_url="postgresql+psycopg://user:pass@localhost/market",
                benchmark_db_url="postgresql+psycopg://user:pass@localhost/benchmark",
            )
        )
        assert str(store.benchmark_engine.url) == str(store.market_engine.url).replace("/market", "/benchmark")

    def test_benchmark_engine_falls_back_to_reference_db_url(self):
        store = PostgresDataStore(
            DatabaseSettings(
                market_db_url="postgresql+psycopg://user:pass@localhost/market",
                reference_db_url="postgresql+psycopg://user:pass@localhost/reference",
            )
        )
        assert "/reference" in str(store.benchmark_engine.url)

    def test_benchmark_engine_falls_back_to_market_db_url(self):
        store = PostgresDataStore(
            DatabaseSettings(market_db_url="postgresql+psycopg://user:pass@localhost/market")
        )
        assert "/market" in str(store.benchmark_engine.url)

    def test_load_benchmark_bars_uses_benchmark_engine(self, monkeypatch):
        captured_engine = {}

        def fake_read_sql_query(*, sql, con, params):
            captured_engine["url"] = str(con.url)
            return pd.DataFrame(
                {"ts_code": ["000300.SH"], "trade_date": ["2026-01-05"], "close": [3500.0]}
            )

        monkeypatch.setattr(pd, "read_sql_query", fake_read_sql_query)
        store = PostgresDataStore(
            DatabaseSettings(
                market_db_url="postgresql+psycopg://user:pass@localhost/market",
                benchmark_db_url="postgresql+psycopg://user:pass@localhost/benchmark",
            )
        )
        store.load_benchmark_bars(
            table_name="public.index_daily",
            ts_codes=["000300.SH"],
            start=date(2026, 1, 1),
            end=date(2026, 1, 31),
        )
        assert "/benchmark" in captured_engine["url"]


class TestReferenceMetadataComposition:
    def _make_store(self):
        return PostgresDataStore(
            DatabaseSettings(market_db_url="postgresql+psycopg://user:pass@localhost/db")
        )

    def test_explicit_metadata_table_takes_precedence(self, monkeypatch):
        """When QRE_SECURITY_METADATA_TABLE is set, reference.* composition is skipped."""
        store = PostgresDataStore(
            DatabaseSettings(
                market_db_url="postgresql+psycopg://user:pass@localhost/db",
                tables=DatabaseTableConfig(security_metadata_table="public.my_metadata"),
            )
        )

        def fake_get_table_columns(table_name, *, engine=None):
            return ["ts_code", "list_date", "board"]

        def fake_read_sql_query(*, sql, con, params):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "list_date": pd.to_datetime(["1991-04-03"]),
                    "board": ["main_board"],
                }
            )

        monkeypatch.setattr(store, "get_table_columns", fake_get_table_columns)
        monkeypatch.setattr(pd, "read_sql_query", fake_read_sql_query)

        frame = store.load_security_metadata()
        # Explicit table was used (not reference composition, not daily-derived)
        assert "ts_code" in frame.columns
        assert frame["ts_code"].iloc[0] == "000001.SZ"

    def test_reference_metadata_preserves_passthrough_columns(self, monkeypatch):
        store = self._make_store()

        def fake_table_exists(table_name, *, engine=None):
            return table_name == "reference.stock_basic"

        def fake_get_table_columns(table_name, *, engine=None):
            if table_name == "reference.stock_basic":
                return ["ts_code", "list_date", "board", "name", "area", "industry", "market"]
            return ["ts_code"]

        called_queries = []

        def fake_read_sql_query(*, sql, con, params):
            called_queries.append(str(sql))
            if "reference.stock_basic" in str(sql):
                return pd.DataFrame(
                    {
                        "ts_code": ["000001.SZ", "000002.SZ"],
                        "list_date": pd.to_datetime(["1991-04-03", "1991-05-01"]),
                        "board": ["main_board", "main_board"],
                        "name": ["Ping An", "Vanke"],
                        "area": ["Shenzhen", "Shenzhen"],
                        "industry": ["Finance", "Real Estate"],
                        "market": ["主板", "主板"],
                    }
                )
            # Status queries return empty sets
            return pd.DataFrame({"ts_code": []})

        monkeypatch.setattr(store, "table_exists", fake_table_exists)
        monkeypatch.setattr(store, "get_table_columns", fake_get_table_columns)
        monkeypatch.setattr(pd, "read_sql_query", fake_read_sql_query)

        frame = store.load_security_metadata()

        assert "name" in frame.columns
        assert "area" in frame.columns
        assert "industry" in frame.columns
        assert "market" in frame.columns
        assert list(frame["name"]) == ["Ping An", "Vanke"]
        assert list(frame["area"]) == ["Shenzhen", "Shenzhen"]
        assert list(frame["industry"]) == ["Finance", "Real Estate"]
        assert list(frame["market"]) == ["主板", "主板"]
        # Fixed columns present
        assert "ts_code" in frame.columns
        assert "list_date" in frame.columns
        assert "board" in frame.columns
        assert "is_st" in frame.columns
        assert "is_risk_warning" in frame.columns
        assert "is_suspended" in frame.columns

    def test_reference_sets_is_suspended_from_stock_suspend(self, monkeypatch):
        store = self._make_store()

        def fake_table_exists(table_name, *, engine=None):
            return table_name in ("reference.stock_basic", "reference.stock_suspend")

        def fake_get_table_columns(table_name, *, engine=None):
            if table_name == "reference.stock_basic":
                return ["ts_code", "list_date", "board"]
            if table_name == "reference.stock_suspend":
                return ["ts_code", "trade_date"]
            return ["ts_code"]

        def fake_read_sql_query(*, sql, con, params):
            sql_str = str(sql)
            if "reference.stock_basic" in sql_str:
                return pd.DataFrame(
                    {
                        "ts_code": ["000001.SZ", "000002.SZ"],
                        "list_date": pd.to_datetime(["1991-04-03", "1991-05-01"]),
                        "board": ["main_board", "main_board"],
                    }
                )
            if "reference.stock_suspend" in sql_str:
                return pd.DataFrame({"ts_code": ["000002.SZ"]})
            return pd.DataFrame({"ts_code": []})

        monkeypatch.setattr(store, "table_exists", fake_table_exists)
        monkeypatch.setattr(store, "get_table_columns", fake_get_table_columns)
        monkeypatch.setattr(pd, "read_sql_query", fake_read_sql_query)

        frame = store.load_security_metadata()

        assert frame["is_suspended"].tolist() == [False, True]

    def test_reference_sets_is_st_from_stock_st(self, monkeypatch):
        store = self._make_store()

        def fake_table_exists(table_name, *, engine=None):
            return table_name in ("reference.stock_basic", "reference.stock_st")

        def fake_get_table_columns(table_name, *, engine=None):
            if table_name == "reference.stock_basic":
                return ["ts_code", "list_date", "board"]
            if table_name == "reference.stock_st":
                return ["ts_code", "trade_date"]
            return ["ts_code"]

        def fake_read_sql_query(*, sql, con, params):
            sql_str = str(sql)
            if "reference.stock_basic" in sql_str:
                return pd.DataFrame(
                    {
                        "ts_code": ["000001.SZ", "000002.SZ"],
                        "list_date": pd.to_datetime(["1991-04-03", "1991-05-01"]),
                        "board": ["main_board", "main_board"],
                    }
                )
            if "reference.stock_st" in sql_str:
                return pd.DataFrame({"ts_code": ["000001.SZ"]})
            return pd.DataFrame({"ts_code": []})

        monkeypatch.setattr(store, "table_exists", fake_table_exists)
        monkeypatch.setattr(store, "get_table_columns", fake_get_table_columns)
        monkeypatch.setattr(pd, "read_sql_query", fake_read_sql_query)

        frame = store.load_security_metadata()

        assert frame["is_st"].tolist() == [True, False]

    def test_reference_sets_is_risk_warning_from_stock_risk_warning(self, monkeypatch):
        store = self._make_store()

        def fake_table_exists(table_name, *, engine=None):
            return table_name in ("reference.stock_basic", "reference.stock_risk_warning")

        def fake_get_table_columns(table_name, *, engine=None):
            if table_name == "reference.stock_basic":
                return ["ts_code", "list_date", "board"]
            if table_name == "reference.stock_risk_warning":
                return ["ts_code", "start_date", "end_date"]
            return ["ts_code"]

        def fake_read_sql_query(*, sql, con, params):
            sql_str = str(sql)
            if "reference.stock_basic" in sql_str:
                return pd.DataFrame(
                    {
                        "ts_code": ["000001.SZ", "000002.SZ"],
                        "list_date": pd.to_datetime(["1991-04-03", "1991-05-01"]),
                        "board": ["main_board", "main_board"],
                    }
                )
            if "reference.stock_risk_warning" in sql_str:
                return pd.DataFrame({"ts_code": ["000001.SZ"]})
            return pd.DataFrame({"ts_code": []})

        monkeypatch.setattr(store, "table_exists", fake_table_exists)
        monkeypatch.setattr(store, "get_table_columns", fake_get_table_columns)
        monkeypatch.setattr(pd, "read_sql_query", fake_read_sql_query)

        frame = store.load_security_metadata()

        assert frame["is_risk_warning"].tolist() == [True, False]

    def test_missing_status_tables_default_flags_to_false(self, monkeypatch):
        store = self._make_store()

        def fake_table_exists(table_name, *, engine=None):
            return table_name == "reference.stock_basic"

        def fake_get_table_columns(table_name, *, engine=None):
            return ["ts_code", "list_date", "board"]

        def fake_read_sql_query(*, sql, con, params):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "list_date": pd.to_datetime(["1991-04-03"]),
                    "board": ["main_board"],
                }
            )

        monkeypatch.setattr(store, "table_exists", fake_table_exists)
        monkeypatch.setattr(store, "get_table_columns", fake_get_table_columns)
        monkeypatch.setattr(pd, "read_sql_query", fake_read_sql_query)

        frame = store.load_security_metadata()

        assert frame["is_suspended"].iloc[0] == False
        assert frame["is_st"].iloc[0] == False
        assert frame["is_risk_warning"].iloc[0] == False

    def test_no_stock_basic_falls_back_to_daily_derived(self, monkeypatch):
        store = self._make_store()

        def fake_table_exists(table_name, *, engine=None):
            return False

        def fake_read_sql_query(*, sql, con, params):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "list_date": pd.to_datetime(["1991-04-03"]),
                }
            )

        monkeypatch.setattr(store, "table_exists", fake_table_exists)
        monkeypatch.setattr(pd, "read_sql_query", fake_read_sql_query)

        frame = store.load_security_metadata()

        assert frame["ts_code"].iloc[0] == "000001.SZ"
        assert frame["board"].iloc[0] == "main_board"
        assert frame["is_st"].iloc[0] == False
        assert frame["is_risk_warning"].iloc[0] == False
        assert frame["is_suspended"].iloc[0] == False


class TestMarketCapLiquidityBuckets:
    def test_market_cap_bucket_mapping(self):
        series = pd.Series([1_000_000, 5_000_000, 10_000_000, 50_000_000, 100_000_000, None])
        buckets = PostgresDataStore._compute_market_cap_bucket(series)

        assert buckets.iloc[0] == "small"
        assert buckets.iloc[1] == "mid"
        assert buckets.iloc[2] == "mid"
        assert buckets.iloc[3] == "large"
        assert buckets.iloc[4] == "large"
        assert pd.isna(buckets.iloc[5])

    def test_liquidity_bucket_mapping(self):
        series = pd.Series([0.5, 1.0, 3.0, 5.0, 10.0, None])
        buckets = PostgresDataStore._compute_liquidity_bucket(series)

        assert buckets.iloc[0] == "low"
        assert buckets.iloc[1] == "mid"
        assert buckets.iloc[2] == "mid"
        assert buckets.iloc[3] == "high"
        assert buckets.iloc[4] == "high"
        assert pd.isna(buckets.iloc[5])


class TestDailyBasicEnrichment:
    def _make_store(self):
        return PostgresDataStore(
            DatabaseSettings(market_db_url="postgresql+psycopg://user:pass@localhost/db")
        )

    def test_reference_metadata_enriched_with_daily_basic(self, monkeypatch):
        store = self._make_store()

        def fake_table_exists(table_name, *, engine=None):
            if table_name == "reference.stock_basic":
                return True
            if table_name == "reference.daily_basic":
                return True
            return False

        def fake_get_table_columns(table_name, *, engine=None):
            if table_name == "reference.stock_basic":
                return ["ts_code", "list_date", "board"]
            if table_name == "reference.daily_basic":
                return ["ts_code", "trade_date", "total_mv", "circ_mv", "turnover_rate", "turnover_rate_f", "volume_ratio"]
            return ["ts_code"]

        def fake_read_sql_query(*, sql, con, params):
            sql_str = str(sql)
            if "reference.stock_basic" in sql_str:
                return pd.DataFrame(
                    {
                        "ts_code": ["000001.SZ", "000002.SZ"],
                        "list_date": pd.to_datetime(["1991-04-03", "1991-05-01"]),
                        "board": ["main_board", "main_board"],
                    }
                )
            if "reference.daily_basic" in sql_str:
                return pd.DataFrame(
                    {
                        "ts_code": ["000001.SZ", "000002.SZ"],
                        "total_mv": [60_000_000, 1_000_000],
                        "circ_mv": [55_000_000, 800_000],
                        "turnover_rate": [2.5, 0.5],
                        "turnover_rate_f": [3.0, 0.8],
                        "volume_ratio": [1.2, 0.9],
                    }
                )
            return pd.DataFrame({"ts_code": []})

        monkeypatch.setattr(store, "table_exists", fake_table_exists)
        monkeypatch.setattr(store, "get_table_columns", fake_get_table_columns)
        monkeypatch.setattr(pd, "read_sql_query", fake_read_sql_query)

        frame = store.load_security_metadata()

        assert "total_mv" in frame.columns
        assert "circ_mv" in frame.columns
        assert "turnover_rate" in frame.columns
        assert "turnover_rate_f" in frame.columns
        assert "volume_ratio" in frame.columns
        assert "market_cap_bucket" in frame.columns
        assert "liquidity_bucket" in frame.columns
        assert frame["total_mv"].tolist() == [60_000_000, 1_000_000]
        assert frame["market_cap_bucket"].tolist() == ["large", "small"]
        assert frame["liquidity_bucket"].tolist() == ["mid", "low"]

    def test_explicit_metadata_table_no_daily_basic_enrichment(self, monkeypatch):
        store = PostgresDataStore(
            DatabaseSettings(
                market_db_url="postgresql+psycopg://user:pass@localhost/db",
                tables=DatabaseTableConfig(security_metadata_table="public.my_metadata"),
            )
        )

        def fake_get_table_columns(table_name, *, engine=None):
            return ["ts_code", "list_date", "board"]

        def fake_read_sql_query(*, sql, con, params):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "list_date": pd.to_datetime(["1991-04-03"]),
                    "board": ["main_board"],
                }
            )

        monkeypatch.setattr(store, "get_table_columns", fake_get_table_columns)
        monkeypatch.setattr(pd, "read_sql_query", fake_read_sql_query)

        frame = store.load_security_metadata()

        assert "total_mv" not in frame.columns
        assert "market_cap_bucket" not in frame.columns

    def test_missing_daily_basic_keeps_previous_behavior(self, monkeypatch):
        store = self._make_store()

        def fake_table_exists(table_name, *, engine=None):
            return table_name == "reference.stock_basic"

        def fake_get_table_columns(table_name, *, engine=None):
            return ["ts_code", "list_date", "board"]

        def fake_read_sql_query(*, sql, con, params):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "list_date": pd.to_datetime(["1991-04-03"]),
                    "board": ["main_board"],
                }
            )

        monkeypatch.setattr(store, "table_exists", fake_table_exists)
        monkeypatch.setattr(store, "get_table_columns", fake_get_table_columns)
        monkeypatch.setattr(pd, "read_sql_query", fake_read_sql_query)

        frame = store.load_security_metadata()

        assert "ts_code" in frame.columns
        assert frame["ts_code"].iloc[0] == "000001.SZ"
        assert "total_mv" not in frame.columns
        assert "market_cap_bucket" not in frame.columns

    def test_reference_metadata_partial_daily_basic_columns(self, monkeypatch):
        store = self._make_store()

        def fake_table_exists(table_name, *, engine=None):
            return table_name in ("reference.stock_basic", "reference.daily_basic")

        def fake_get_table_columns(table_name, *, engine=None):
            if table_name == "reference.stock_basic":
                return ["ts_code", "list_date", "board"]
            if table_name == "reference.daily_basic":
                return ["ts_code", "trade_date", "total_mv"]
            return ["ts_code"]

        def fake_read_sql_query(*, sql, con, params):
            sql_str = str(sql)
            if "reference.stock_basic" in sql_str:
                return pd.DataFrame(
                    {
                        "ts_code": ["000001.SZ"],
                        "list_date": pd.to_datetime(["1991-04-03"]),
                        "board": ["main_board"],
                    }
                )
            if "reference.daily_basic" in sql_str:
                return pd.DataFrame({"ts_code": ["000001.SZ"], "total_mv": [10_000_000]})
            return pd.DataFrame({"ts_code": []})

        monkeypatch.setattr(store, "table_exists", fake_table_exists)
        monkeypatch.setattr(store, "get_table_columns", fake_get_table_columns)
        monkeypatch.setattr(pd, "read_sql_query", fake_read_sql_query)

        frame = store.load_security_metadata()

        assert "total_mv" in frame.columns
        assert "market_cap_bucket" in frame.columns
        assert "turnover_rate_f" not in frame.columns
        assert "liquidity_bucket" not in frame.columns

    def test_daily_derived_path_enriched_with_daily_basic(self, monkeypatch):
        store = self._make_store()

        def fake_table_exists(table_name, *, engine=None):
            if table_name == "reference.daily_basic":
                return True
            return False

        def fake_get_table_columns(table_name, *, engine=None):
            if table_name == "reference.daily_basic":
                return ["ts_code", "trade_date", "total_mv", "turnover_rate_f"]
            return ["ts_code"]

        def fake_read_sql_query(*, sql, con, params):
            sql_str = str(sql)
            if "reference.daily_basic" in sql_str:
                return pd.DataFrame(
                    {"ts_code": ["000001.SZ"], "total_mv": [20_000_000], "turnover_rate_f": [3.5]}
                )
            if "MIN(trade_date)" in sql_str:
                return pd.DataFrame(
                    {"ts_code": ["000001.SZ"], "list_date": pd.to_datetime(["1991-04-03"])}
                )
            return pd.DataFrame({"ts_code": []})

        monkeypatch.setattr(store, "table_exists", fake_table_exists)
        monkeypatch.setattr(store, "get_table_columns", fake_get_table_columns)
        monkeypatch.setattr(pd, "read_sql_query", fake_read_sql_query)

        frame = store.load_security_metadata()

        assert frame["ts_code"].iloc[0] == "000001.SZ"
        assert frame["board"].iloc[0] == "main_board"
        assert "total_mv" in frame.columns
        assert frame["total_mv"].iloc[0] == 20_000_000
        assert "market_cap_bucket" in frame.columns
        assert "liquidity_bucket" in frame.columns


class TestIndustryGroupNormalization:
    def test_industry_group_normalized_from_raw_industry(self):
        series = pd.Series(["  Banking  ", "Tech", "", None, "  Real Estate  "])
        result = PostgresDataStore._compute_industry_group(series)

        assert result.iloc[0] == "Banking"
        assert result.iloc[1] == "Tech"
        assert pd.isna(result.iloc[2])
        assert pd.isna(result.iloc[3])
        assert result.iloc[4] == "Real Estate"

    def test_industry_group_preserves_raw_industry(self, monkeypatch):
        store = PostgresDataStore(
            DatabaseSettings(
                market_db_url="postgresql+psycopg://user:pass@localhost/db",
                tables=DatabaseTableConfig(security_metadata_table="public.my_metadata"),
            )
        )

        def fake_get_table_columns(table_name, *, engine=None):
            return ["ts_code", "list_date", "board", "industry"]

        def fake_read_sql_query(*, sql, con, params):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "list_date": pd.to_datetime(["1991-04-03"]),
                    "board": ["main_board"],
                    "industry": ["  Finance  "],
                }
            )

        monkeypatch.setattr(store, "get_table_columns", fake_get_table_columns)
        monkeypatch.setattr(pd, "read_sql_query", fake_read_sql_query)

        frame = store.load_security_metadata()

        assert frame["industry"].iloc[0] == "  Finance  "
        assert frame["industry_group"].iloc[0] == "Finance"


class TestBenchmarkMembershipEnrichment:
    def _make_store(self):
        return PostgresDataStore(
            DatabaseSettings(market_db_url="postgresql+psycopg://user:pass@localhost/db")
        )

    def test_benchmark_membership_enriched_when_benchmark_code_provided(self, monkeypatch):
        store = self._make_store()

        def fake_table_exists(table_name, *, engine=None):
            if table_name == "reference.stock_basic":
                return True
            if table_name == "reference.index_weight":
                return True
            return False

        def fake_get_table_columns(table_name, *, engine=None):
            if table_name == "reference.stock_basic":
                return ["ts_code", "list_date", "board"]
            if table_name == "reference.index_weight":
                return ["index_code", "con_code", "weight", "trade_date"]
            return ["ts_code"]

        def fake_read_sql_query(*, sql, con, params):
            sql_str = str(sql)
            if "reference.stock_basic" in sql_str:
                return pd.DataFrame(
                    {
                        "ts_code": ["000001.SZ", "000002.SZ", "000003.SZ"],
                        "list_date": pd.to_datetime(["1991-04-03", "1991-05-01", "1992-01-01"]),
                        "board": ["main_board", "main_board", "main_board"],
                    }
                )
            if "reference.index_weight" in sql_str:
                return pd.DataFrame(
                    {
                        "ts_code": ["000001.SZ", "000003.SZ"],
                        "benchmark_code": ["000300.SH", "000300.SH"],
                        "benchmark_weight": [5.2, 2.1],
                        "is_benchmark_member": [True, True],
                    }
                )
            return pd.DataFrame({"ts_code": []})

        monkeypatch.setattr(store, "table_exists", fake_table_exists)
        monkeypatch.setattr(store, "get_table_columns", fake_get_table_columns)
        monkeypatch.setattr(pd, "read_sql_query", fake_read_sql_query)

        frame = store.load_security_metadata(benchmark_code="000300.SH")

        assert "benchmark_code" in frame.columns
        assert "benchmark_weight" in frame.columns
        assert "is_benchmark_member" in frame.columns
        assert frame["is_benchmark_member"].tolist() == [True, False, True]
        weights = frame["benchmark_weight"].tolist()
        assert weights[0] == 5.2
        assert pd.isna(weights[1])
        assert weights[2] == 2.1
        assert frame["benchmark_code"].tolist() == ["000300.SH", "000300.SH", "000300.SH"]

    def test_missing_index_weight_keeps_previous_behavior(self, monkeypatch):
        store = self._make_store()

        def fake_table_exists(table_name, *, engine=None):
            return table_name == "reference.stock_basic"

        def fake_get_table_columns(table_name, *, engine=None):
            return ["ts_code", "list_date", "board"]

        def fake_read_sql_query(*, sql, con, params):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "list_date": pd.to_datetime(["1991-04-03"]),
                    "board": ["main_board"],
                }
            )

        monkeypatch.setattr(store, "table_exists", fake_table_exists)
        monkeypatch.setattr(store, "get_table_columns", fake_get_table_columns)
        monkeypatch.setattr(pd, "read_sql_query", fake_read_sql_query)

        frame = store.load_security_metadata(benchmark_code="000300.SH")

        assert "ts_code" in frame.columns
        assert "benchmark_code" not in frame.columns
        assert "is_benchmark_member" not in frame.columns

    def test_explicit_metadata_table_skips_benchmark_enrichment(self, monkeypatch):
        store = PostgresDataStore(
            DatabaseSettings(
                market_db_url="postgresql+psycopg://user:pass@localhost/db",
                tables=DatabaseTableConfig(security_metadata_table="public.my_metadata"),
            )
        )

        def fake_get_table_columns(table_name, *, engine=None):
            return ["ts_code", "list_date", "board"]

        def fake_read_sql_query(*, sql, con, params):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "list_date": pd.to_datetime(["1991-04-03"]),
                    "board": ["main_board"],
                }
            )

        monkeypatch.setattr(store, "get_table_columns", fake_get_table_columns)
        monkeypatch.setattr(pd, "read_sql_query", fake_read_sql_query)

        frame = store.load_security_metadata(benchmark_code="000300.SH")

        assert "benchmark_code" not in frame.columns
        assert "is_benchmark_member" not in frame.columns

    def test_no_benchmark_code_skips_enrichment(self, monkeypatch):
        store = self._make_store()

        def fake_table_exists(table_name, *, engine=None):
            return table_name == "reference.stock_basic"

        def fake_get_table_columns(table_name, *, engine=None):
            return ["ts_code", "list_date", "board"]

        def fake_read_sql_query(*, sql, con, params):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "list_date": pd.to_datetime(["1991-04-03"]),
                    "board": ["main_board"],
                }
            )

        monkeypatch.setattr(store, "table_exists", fake_table_exists)
        monkeypatch.setattr(store, "get_table_columns", fake_get_table_columns)
        monkeypatch.setattr(pd, "read_sql_query", fake_read_sql_query)

        frame = store.load_security_metadata()

        assert "benchmark_code" not in frame.columns
        assert "is_benchmark_member" not in frame.columns
