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
