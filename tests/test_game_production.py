from __future__ import annotations

from datetime import date

import pytest

from quant_research_engine.core.models import Bar
from quant_research_engine.game.data import PostgresGameDataProvider
from quant_research_engine.game.session import GameSession
from quant_research_engine.game.web import _reveal


def test_on_demand_reveal_uses_real_dates_and_identity():
    session = GameSession(
        symbol="600000.SH",
        bars=[Bar("600000.SH", date(2024, 1, day), 10, 11, 9, 10) for day in range(1, 4)],
        start_index=0, warmup_bars=1, game_bars=2, seed=1,
    )
    session.reveal_date_offset_days = 0
    session.reveal_identity = {"name": "浦发银行", "code": "600000.SH"}
    session.advance()
    session.close_day()
    session.advance()
    session.close_day()
    reveal = _reveal(session)
    assert reveal["real_name"] == "浦发银行"
    assert reveal["real_code"] == "600000.SH"
    assert reveal["start_date"] == "2024-01-02"
    assert reveal["end_date"] == "2024-01-03"
    assert reveal["date_offset_days"] == 0


def test_provider_reveal_identity_handles_missing_name():
    class Store:
        def load_security_metadata(self, symbols):
            assert symbols == ["300630.SZ"]
            import pandas as pd
            return pd.DataFrame()

    assert PostgresGameDataProvider(Store()).reveal_identity("300630.SZ") == {
        "name": None, "code": "300630.SZ",
    }


def test_nginx_game_proxy_is_loopback_only():
    from pathlib import Path
    config = (Path(__file__).parents[1] / "deploy/landing/nginx-aguhuice.conf").read_text(encoding="utf-8")
    assert "location /game" in config
    assert "proxy_pass http://127.0.0.1:8092;" in config


def test_provider_cache_preserves_seed_and_invalidates():
    class Store:
        def __init__(self):
            self.latest_calls = 0
            self.pool_calls = 0
            self.latest = date(2026, 1, 6)

        def latest_trade_date(self):
            self.latest_calls += 1
            return self.latest

        def list_symbols_with_bars(self, start, end):
            self.pool_calls += 1
            return ["X00002B"]

        def load_raw_bars(self, symbol, start, end):
            return [{
                "trade_date": date(2026, 1, day + 1), "open": 10, "high": 11,
                "low": 9, "close": 10, "pre_close": 10, "vol": 100,
                "amount": 100, "adj_factor": 1,
            } for day in range(5)]

    store = Store()
    provider = PostgresGameDataProvider(
        store, warmup_bars=2, game_bars=3, with_factors=False,
    )
    first = provider.create_session(seed=7)
    second = provider.create_session(seed=7)
    assert (store.latest_calls, store.pool_calls) == (1, 1)
    assert (first.symbol, first.start_index) == (second.symbol, second.start_index)
    assert first.display_code == "X00002B"
    store.latest = date(2026, 1, 7)
    provider.invalidate_cache()
    provider.create_session(seed=8)
    assert (store.latest_calls, store.pool_calls) == (2, 2)


def test_real_symbol_never_becomes_display_code():
    class Store:
        def latest_trade_date(self):
            return date(2026, 1, 5)

        def list_symbols_with_bars(self, start, end):
            return ["600000.SH"]

        def load_raw_bars(self, symbol, start, end):
            return [{
                "trade_date": date(2026, 1, day + 1), "open": 10, "high": 11,
                "low": 9, "close": 10, "pre_close": 10, "vol": 100,
                "amount": 100, "adj_factor": 1,
            } for day in range(5)]

    session = PostgresGameDataProvider(
        Store(), warmup_bars=2, game_bars=3, with_factors=False,
    ).create_session(seed=1)
    assert session.symbol == "600000.SH"
    assert session.display_code == "X00001B"


def test_pool_disk_cache_survives_restart(tmp_path):
    class Store:
        def __init__(self):
            self.pool_calls = 0

        def list_symbols_with_bars(self, start, end):
            self.pool_calls += 1
            return ["600000.SH", "000001.SZ"]

    path = tmp_path / "pool.json"
    store = Store()
    first = PostgresGameDataProvider(store, pool_cache_path=path)
    assert first._pool_cached(date(2026, 1, 6)) == ["600000.SH", "000001.SZ"]
    restarted = PostgresGameDataProvider(store, pool_cache_path=path)
    assert restarted._pool_cached(date(2026, 1, 6)) == ["600000.SH", "000001.SZ"]
    assert store.pool_calls == 1


def test_corrupt_pool_disk_cache_falls_back(tmp_path):
    class Store:
        def list_symbols_with_bars(self, start, end):
            return ["000001.SZ"]

    path = tmp_path / "pool.json"
    path.write_text("not-json", encoding="utf-8")
    provider = PostgresGameDataProvider(Store(), pool_cache_path=path)
    assert provider._pool_cached(date(2026, 1, 6)) == ["000001.SZ"]
    assert '"schema": 1' in path.read_text(encoding="utf-8")
