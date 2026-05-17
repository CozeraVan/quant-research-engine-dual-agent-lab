from pathlib import Path

from quant_research_engine.config.loader import load_market_profile
from quant_research_engine.markets.ashare import AShareMarketProfile


def test_load_ashare_market_profile_from_yaml():
    path = Path("configs/market_profiles/ashare_daily_default.yaml")

    profile = load_market_profile(path)

    assert isinstance(profile, AShareMarketProfile)
    assert profile.name == "ashare_daily_default"
    assert profile.buy_lot == 100
    assert profile.price_limit_by_board["chinext"] == 0.20
    assert profile.stamp_tax_sell == 0.0005
    assert profile.slippage_model == "percent"
    assert profile.slippage_buy_rate == 0.0005
    assert profile.slippage_sell_rate == 0.0005
