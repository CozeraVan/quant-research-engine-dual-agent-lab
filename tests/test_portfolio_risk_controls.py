import pandas as pd

from quant_research_engine.portfolio.risk_controls import RiskControlConfig, evaluate_long_exit


def test_evaluate_long_exit_triggers_stop_loss_from_current_bar_low():
    row = pd.Series({"low": 9.0, "high": 10.5, "open": 9.8})
    config = RiskControlConfig(stop_loss_pct=0.08)

    decision = evaluate_long_exit(entry_price=10.0, row=row, config=config)

    assert decision.should_exit is True
    assert decision.reason == "stop_loss"
    assert decision.price == 9.2


def test_evaluate_long_exit_triggers_take_profit_from_current_bar_high():
    row = pd.Series({"low": 10.1, "high": 11.5, "open": 11.0})
    config = RiskControlConfig(take_profit_pct=0.10)

    decision = evaluate_long_exit(entry_price=10.0, row=row, config=config)

    assert decision.should_exit is True
    assert decision.reason == "take_profit"
    assert decision.price == 11.0


def test_evaluate_long_exit_prefers_stop_loss_when_both_trigger_on_daily_bar():
    row = pd.Series({"low": 9.0, "high": 11.5, "open": 10.2})
    config = RiskControlConfig(stop_loss_pct=0.08, take_profit_pct=0.10)

    decision = evaluate_long_exit(entry_price=10.0, row=row, config=config)

    assert decision.reason == "stop_loss"
    assert decision.price == 9.2


def test_evaluate_long_exit_triggers_trailing_stop_from_anchor():
    row = pd.Series({"low": 10.3, "high": 10.8, "open": 10.5})
    config = RiskControlConfig(trailing_stop_pct=0.08)

    decision = evaluate_long_exit(entry_price=10.0, row=row, config=config, trailing_anchor=11.5)

    assert decision.should_exit is True
    assert decision.reason == "trailing_stop"
    assert decision.price == 10.58


def test_evaluate_long_exit_prefers_trailing_stop_before_take_profit():
    row = pd.Series({"low": 10.3, "high": 12.0, "open": 10.5})
    config = RiskControlConfig(take_profit_pct=0.10, trailing_stop_pct=0.08)

    decision = evaluate_long_exit(entry_price=10.0, row=row, config=config, trailing_anchor=11.5)

    assert decision.reason == "trailing_stop"
    assert decision.price == 10.58


def test_evaluate_long_exit_returns_no_exit_without_trigger():
    row = pd.Series({"low": 9.8, "high": 10.5, "open": 10.2})
    config = RiskControlConfig(stop_loss_pct=0.08, take_profit_pct=0.10)

    decision = evaluate_long_exit(entry_price=10.0, row=row, config=config)

    assert decision.should_exit is False
    assert decision.reason is None
