import pytest

from quant_research_engine.game.engine import GameRuleError
from quant_research_engine.game.factors import DEFAULT_CANONICALS, factor_catalog, resolve_selection


def test_catalog_covers_all_technical_groups_without_fundamentals():
    catalog = factor_catalog()
    groups = {item["group"] for item in catalog}
    assert {"overlap", "momentum", "volatility", "volume", "trend", "performance",
            "statistics", "candle", "risk", "liquidity", "alpha"} <= groups
    assert not any(item["table"] == "_pit_financial_panel" for item in catalog)
    assert not any(item["category"] in {"value", "size", "quality", "growth"} for item in catalog)
    assert all("values" not in item and item["label"] for item in catalog)


def test_catalog_marks_overlay_and_macd_as_separate_pane():
    items = {item["canonical"]: item for item in factor_catalog()}
    assert items[DEFAULT_CANONICALS[0]]["is_overlay"] is True
    assert items[DEFAULT_CANONICALS[4]]["is_overlay"] is False
    assert items[DEFAULT_CANONICALS[9]]["is_overlay"] is True


def test_selection_is_deduplicated_and_whitelisted():
    first = DEFAULT_CANONICALS[0]
    assert resolve_selection([first, first]) == (first,)
    for invalid in ("stock_daily_overlap_close.ema_5", "factors._pit_financial_panel.close",
                    "factors.pg_catalog.pg_tables"):
        with pytest.raises(GameRuleError, match="未知技术因子"):
            resolve_selection([invalid])
