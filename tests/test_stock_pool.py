from __future__ import annotations

import math

import pytest
from sqlalchemy import create_engine, text

from quant_research_engine.stock_pool import normalize_condition, screen_latest_stock_pool

EMA5 = "factors.stock_daily_overlap_typical_price.ema_5"
EMA200 = "factors.stock_daily_overlap_typical_price.ema_200"


def test_normalize_ema_condition():
    condition = normalize_condition({"left": EMA5, "operator": ">", "right": EMA200})
    assert condition["left"] == EMA5 and condition["right"] == EMA200


@pytest.mark.parametrize("raw", [
    {"left": "factors.stock_daily;drop.x", "operator": ">", "right": 1},
    {"left": EMA5, "operator": "OR 1=1", "right": EMA200},
    {"left": EMA5, "operator": ">", "right": math.nan},
    {"left": "reference.stock_basic.name", "operator": ">", "right": 1},
])
def test_invalid_condition_rejected(raw):
    with pytest.raises(ValueError):
        normalize_condition(raw)


def test_latest_ema_pool_matches_independent_count():
    engine = create_engine("postgresql+psycopg:///tushare_data")
    result = screen_latest_stock_pool({"left": EMA5, "operator": ">", "right": EMA200}, engine)
    with engine.connect() as conn:
        latest = conn.execute(text("SELECT max(trade_date) FROM public.stock_daily")).scalar_one()
        expected = conn.execute(text("""
            SELECT count(*) FROM public.stock_daily m
            JOIN factors.stock_daily_overlap_typical_price f
              ON f.ts_code=m.ts_code AND f.trade_date=m.trade_date
            WHERE m.trade_date=:latest AND f.ema_5>f.ema_200
        """), {"latest": latest}).scalar_one()
    assert result["trade_date"] == str(latest)
    assert result["matched_count"] == expected == len(result["stocks"])
    assert expected > 0
    assert all(row["left_value"] > row["right_value"] for row in result["stocks"][:50])


def test_worker_dispatches_stock_pool_without_strategy_yaml(monkeypatch):
    from quant_research_engine.worker import runner
    expected = {"summary": {"kind": "stock_pool", "matched_count": 2}, "chart_data": {}, "files": []}
    monkeypatch.setattr("quant_research_engine.stock_pool.execute_stock_pool_job", lambda job: expected)
    assert runner.execute_job({"kind": "stock_pool", "params": {}}) == expected


def test_stock_pool_page_contains_condition_builder():
    from quant_research_engine.gui.saas import create_saas_app
    response = create_saas_app().test_client().get('/saas/stock-pool')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    for marker in ('最新股票池', 'sp-left', 'sp-right', 'sp-operator', '生成股票池', '/api/saas/stock-pools'):
        assert marker in html


EMA_STRATEGY_YAML = """
experiment:
  name: ema_pool
  market_profile: ashare_daily_default
  frequency: daily
data:
  market_fields: [open, high, low, close, pre_close, vol, amount]
  factor_fields:
    ema_5: factors.stock_daily_overlap_typical_price.ema_5
    ema_200: factors.stock_daily_overlap_typical_price.ema_200
signal:
  entry: ema_5 > ema_200
  exit: null
holding:
  max_holding_days: 10
risk:
  stop_loss_pct: null
  take_profit_pct: null
  trailing_stop_pct: null
evaluation:
  forward_return_horizons: [1, 3, 5, 10, 20]
universe:
  exclude_st: true
  exclude_suspended: true
  exclude_risk_warning: true
  min_listing_days: 120
"""


def test_latest_yaml_pool_matches_simple_condition():
    from quant_research_engine.stock_pool import screen_latest_strategy_pool
    engine = create_engine("postgresql+psycopg:///tushare_data")
    expression = screen_latest_strategy_pool(EMA_STRATEGY_YAML, engine)
    simple = screen_latest_stock_pool({"left": EMA5, "operator": ">", "right": EMA200}, engine)
    assert expression["trade_date"] == simple["trade_date"]
    assert expression["matched_count"] == simple["matched_count"]
    assert [r["ts_code"] for r in expression["stocks"]] == [r["ts_code"] for r in simple["stocks"]]


def test_stock_pool_page_has_backtest_style_three_entries():
    from quant_research_engine.gui.saas import create_saas_app
    html = create_saas_app().test_client().get('/saas/stock-pool').get_data(as_text=True)
    for marker in ('data-sp-entry="nl"', 'data-sp-entry="wizard"', 'data-sp-entry="yaml"',
                   'sp-nl-input', 'sp-yaml', '/api/saas/nl/compile'):
        assert marker in html


def test_latest_pool_exposes_named_indicator_values():
    engine = create_engine("postgresql+psycopg:///tushare_data")
    result = screen_latest_stock_pool({"left": EMA5, "operator": ">", "right": EMA200}, engine)
    assert [item["canonical"] for item in result["indicators"]] == [EMA5, EMA200]
    assert all(item["label"] for item in result["indicators"])
    first = result["stocks"][0]
    assert first["indicator_values"][EMA5] == first["left_value"]
    assert first["indicator_values"][EMA200] == first["right_value"]


def test_latest_yaml_pool_exposes_actual_latest_indicator_values():
    from quant_research_engine.stock_pool import screen_latest_strategy_pool
    engine = create_engine("postgresql+psycopg:///tushare_data")
    result = screen_latest_strategy_pool(EMA_STRATEGY_YAML, engine)
    assert [item["canonical"] for item in result["indicators"]] == [EMA5, EMA200]
    first = result["stocks"][0]
    values = first["indicator_values"]
    assert values[EMA5] is not None and values[EMA200] is not None
    assert values[EMA5] > values[EMA200]


def test_stock_pool_results_use_dynamic_named_columns_and_search():
    from quant_research_engine.gui.saas import create_saas_app
    html = create_saas_app().test_client().get('/saas/stock-pool').get_data(as_text=True)
    for marker in ('entry-grid', 'sp-search', 'sp-indicator-head', 'summary.indicators',
                   'indicator_values', 'role="tab"', 'aria-selected'):
        assert marker in html
    assert '<th class="num">左侧值</th>' not in html
    assert '<th class="num">右侧值</th>' not in html
