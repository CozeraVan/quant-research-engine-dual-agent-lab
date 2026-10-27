from datetime import date, timedelta

import pytest

from quant_research_engine.core.models import Bar, OrderSide
from quant_research_engine.game.session import GameSession, GameSessionFactory


def make_bars(count=1500):
    return [Bar(symbol="600000.SH", trade_date=date(2020, 1, 1) + timedelta(days=i),
                open=10.0, high=11.0, low=9.0, close=10.0, pre_close=10.0, volume=1000)
            for i in range(count)]


def make_game():
    return GameSessionFactory().create({"600000.SH": make_bars()}, seed=2026)


def test_decision_only_exposes_next_open_and_limits():
    game = make_game()
    game.advance()
    current = game.public_history()[-1]
    assert set(current) == {"t", "open"}
    decision = game.decision_state()
    assert decision["next_open"] == 10.0
    assert decision["limit_lower"] == 9.0 and decision["limit_upper"] == 11.0
    assert decision["can_trade"] is True


def test_close_reveals_bar_and_settlement_then_blocks_trade():
    game = make_game()
    game.advance()
    game.place_order(OrderSide.BUY, 10.0, 100)
    game.close_day()
    assert game.phase == "closed"
    assert game.settlement["close"] == 10.0
    assert game.settlement["fill"]["quantity"] == 100
    assert game.decision_state()["can_trade"] is False
    with pytest.raises(Exception, match="决策阶段"):
        game.place_order(OrderSide.BUY, 10.0, 100)


def test_cancel_allows_empty_close():
    game = make_game()
    game.advance()
    game.place_order(OrderSide.BUY, 10.0, 100)
    game.cancel_order()
    game.close_day()
    assert game.quantity == 0 and game.settlement["unfilled"] == "no_order"
    game.advance()
    assert game.settlement is None


def test_advance_requires_closed_phase():
    game = make_game()
    game.advance()
    with pytest.raises(Exception, match="结算当前回合"):
        game.advance()


def test_finished_when_time_exhausted():
    game = GameSessionFactory(warmup_bars=250, game_bars=1).create({"600000.SH": make_bars()}, seed=1)
    game.advance()
    game.close_day()
    assert game.finished
    with pytest.raises(Exception, match="游戏已结束"):
        game.advance()
