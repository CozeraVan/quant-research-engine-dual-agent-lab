from pathlib import Path

from quant_research_engine.strategies.spec import StrategySpec


def test_strategy_spec_loads_factor_fields_from_yaml():
    spec = StrategySpec.from_yaml(Path("strategies/low_level/rsi2_reversal_research.yaml"))

    assert spec.name == "rsi2_reversal_research_mvp"
    assert spec.signal_expression == "rsi_2 < 10"
    assert spec.market_fields == ["open", "high", "low", "close", "pre_close", "vol", "amount"]
    assert len(spec.factor_fields) == 1
    assert spec.factor_fields[0].logical_name == "rsi_2"
    assert spec.factor_fields[0].qualified_table == "factors.stock_daily_momentum_close"
    assert spec.factor_fields[0].source_column == "rsi_2"
    assert spec.forward_horizons == [1, 3, 5, 10, 20]
    assert spec.quantiles == 5
    assert spec.holding_days == 5
    assert spec.exclude_st is True
    assert spec.exclude_suspended is True
    assert spec.min_listing_days == 120
    assert spec.min_amount is None


def test_strategy_spec_loads_risk_controls_from_yaml():
    spec = StrategySpec.from_yaml(Path("strategies/low_level/rsi2_reversal_with_risk.yaml"))

    assert spec.stop_loss_pct == 0.08
    assert spec.take_profit_pct == 0.12
    assert spec.trailing_stop_pct == 0.10


def test_strategy_spec_loads_portfolio_weighting_from_yaml():
    spec = StrategySpec.from_yaml(Path("strategies/low_level/rsi2_reversal_with_risk_and_weight.yaml"))

    assert spec.weight_model == "score_weight"
    assert spec.score_column == "rsi_2"
    assert spec.volatility_column is None


def test_strategy_spec_loads_rebalance_interval_from_portfolio_yaml():
    spec = StrategySpec.from_mapping(
        {
            "experiment": {"name": "rebalance_test"},
            "data": {"factor_fields": {"rsi_2": "factors.stock_daily_momentum_close.rsi_2"}},
            "signal": {"entry": "rsi_2 < 10"},
            "evaluation": {"forward_return_horizons": [1, 3]},
            "holding": {"max_holding_days": 5},
            "portfolio": {"rebalance_interval_days": 5},
        }
    )

    assert spec.rebalance_interval_days == 5


def test_strategy_spec_loads_exit_signal_from_yaml_mapping():
    spec = StrategySpec.from_mapping(
        {
            "experiment": {"name": "ema200_bollinger_reversal"},
            "data": {
                "factor_fields": {
                    "ema200": "factors.stock_daily_overlap_typical_price.ema_200",
                    "bb_upper": "factors.stock_daily_volatility_close.bbu_20_2_0_2_0",
                    "bb_lower": "factors.stock_daily_volatility_close.bbl_20_2_0_2_0",
                }
            },
            "signal": {"entry": "close > ema200 and close <= bb_lower", "exit": "close >= bb_upper"},
            "evaluation": {"forward_return_horizons": [1, 3]},
            "holding": {"max_holding_days": 9999},
        }
    )

    assert spec.signal_expression == "close > ema200 and close <= bb_lower"
    assert spec.exit_signal_expression == "close >= bb_upper"
