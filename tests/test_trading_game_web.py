from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from quant_research_engine.game.data import PostgresGameDataProvider
from quant_research_engine.game.factors import DEFAULT_CANONICALS
from quant_research_engine.game.web import create_game_app

START = date(2020, 1, 1)
TYPICAL_EMA5 = "factors.stock_daily_overlap_typical_price.ema_5"


class FakeStore:
    settings = SimpleNamespace(tables=SimpleNamespace(market_daily_table="public.stock_daily"))

    def qualified_table(self, name):
        return name

    def latest_trade_date(self):
        return START + timedelta(days=1499)

    def list_symbols_with_bars(self, start, end):
        return ["600000.SH"]

    def load_raw_bars(self, symbol, start, end):
        return [{"trade_date": START + timedelta(days=i), "open": 10, "high": 11,
                 "low": 9, "close": 10, "pre_close": 10, "vol": 100,
                 "amount": 1000, "adj_factor": 1} for i in range(1500)]

    def load_factor_history(self, symbols, requests, start, end):
        data = {"ts_code": ["600000.SH"] * 1500,
                "trade_date": [pd.Timestamp(START) + pd.Timedelta(days=i) for i in range(1500)]}
        for request in requests:
            data[request.logical_name] = [10.0] * 1500
        return pd.DataFrame(data)


@pytest.fixture()
def client():
    return create_game_app(PostgresGameDataProvider(FakeStore()), testing=True).test_client()


def create(client):
    response = client.post("/game/api/sessions")
    assert response.status_code == 200
    return response.get_json()


def test_full_round_and_idempotent_close(client):
    data = create(client)
    assert data["display_code"] == "X00001B"
    assert "symbol" not in data and "seed" not in data
    opened = client.post(f"/game/api/sessions/{data['id']}/advance").get_json()
    assert set(opened["history"][-1]) == {"t", "open"}
    assert opened["decision"]["next_open"] == 10.0

    ordered = client.post(f"/game/api/sessions/{data['id']}/orders",
                          json={"side": "buy", "price": 10.0, "quantity": 100})
    assert ordered.status_code == 200
    closed = client.post(f"/game/api/sessions/{data['id']}/close").get_json()
    assert closed["settlement"]["fill"]["quantity"] == 100
    assert closed["account"]["quantity"] == 100
    assert closed["trades"][0]["side"] == "buy"
    assert closed["decision"]["can_trade"] is False

    again = client.post(f"/game/api/sessions/{data['id']}/close").get_json()
    assert len(again["trades"]) == 1


def test_cancel_then_empty_close(client):
    data = create(client)
    client.post(f"/game/api/sessions/{data['id']}/advance")
    client.post(f"/game/api/sessions/{data['id']}/orders",
                json={"side": "buy", "price": 10.0, "quantity": 100})
    canceled = client.post(f"/game/api/sessions/{data['id']}/cancel")
    assert canceled.status_code == 200 and canceled.get_json()["pending_order"] is None
    closed = client.post(f"/game/api/sessions/{data['id']}/close").get_json()
    assert closed["settlement"]["unfilled"] == "no_order"
    assert closed["account"]["quantity"] == 0


def test_factor_catalog_selection_and_invalid_target(client):
    groups = client.get("/game/api/factors").get_json()["groups"]
    labels = {group["label"] for group in groups}
    assert {"风险", "流动性", "Alpha 因子"} <= labels
    data = create(client)
    selected = client.post(f"/game/api/sessions/{data['id']}/factors",
                           json={"canonicals": [DEFAULT_CANONICALS[0], TYPICAL_EMA5]})
    assert selected.status_code == 200
    payload = selected.get_json()
    assert payload["loaded"] == sorted([*DEFAULT_CANONICALS, TYPICAL_EMA5])
    assert payload["history"][-1]["factors"][TYPICAL_EMA5] == 10.0
    invalid = client.post(f"/game/api/sessions/{data['id']}/factors",
                          json={"canonicals": ["factors._pit_financial_panel.close"]})
    assert invalid.status_code == 400


def test_other_browser_cannot_access_session(client):
    data = create(client)
    other = client.application.test_client()
    other.delete_cookie("qre_game_owner")
    assert other.get(f"/game/api/sessions/{data['id']}").status_code == 401
    assert other.post(f"/game/api/sessions/{data['id']}/advance").status_code == 401


def test_template_has_turn_based_layout_without_autoplay_or_shared_chips():
    template = Path("src/quant_research_engine/game/templates/game.html").read_text()
    for marker in ("game-layout", "game-side", "markArea", "btn-advance", "btn-settle",
                   "factor-groups", "order-price"):
        assert marker in template
    assert "setInterval" not in template
    # QRE-KLINE-PANE-OPTION（T1，2026-10-29）：游戏现在**故意**引入共享
    # factor-layout.js——为了让 pane 的 grid/yAxisIndex 与 symbol.html、
    # replay.js 单一来源（原先三处各写一份 2+i，错位 bug 复发多次）。
    # 但游戏仍不得使用共享的 **chip UI / plan()**：它有自己的因子选择与分组，
    # 只用 panesToOption 这一层纯映射。
    assert "factor-layout.js" in template, "游戏必须引入共享 pane 映射层"
    assert "QREFactorLayout.panesToOption(" in template, "游戏必须走 panesToOption"
    assert "QREFactorLayout.plan(" not in template, "游戏不得使用共享 chip/plan UI"
    assert "fct-chip" not in template, "游戏不得复用 SaaS 的 chip 组件"
    assert "$('game-start').classList.add('hidden')" in template
