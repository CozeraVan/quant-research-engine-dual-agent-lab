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


def test_pool_definition_hash_is_stable_and_changes_with_definition():
    from quant_research_engine.stock_pool import pool_definition_hash

    condition = {"left": EMA5, "operator": ">", "right": EMA200}
    first = pool_definition_hash("condition", {"condition": condition})
    assert first == pool_definition_hash("condition", {"condition": dict(condition)})
    changed = pool_definition_hash("condition", {"condition": {**condition, "operator": "<"}})
    assert changed != first


def test_build_pool_snapshot_computes_added_and_removed():
    from quant_research_engine.stock_pool import build_pool_snapshot

    previous = {"stocks": [
        {"ts_code": "000001.SZ", "name": "平安银行"},
        {"ts_code": "600000.SH", "name": "浦发银行"},
    ]}
    result = {
        "trade_date": "2026-11-21", "total_count": 5200, "matched_count": 2,
        "indicators": [{"key": EMA5, "label": "指数移动均线(5)", "precision": 4}],
        "stocks": [
            {"ts_code": "600000.SH", "name": "浦发银行", "close": 10.0,
             "indicator_values": {EMA5: 10.1}},
            {"ts_code": "300750.SZ", "name": "宁德时代", "close": 200.0,
             "indicator_values": {EMA5: 201.0}},
        ],
    }
    snapshot = build_pool_snapshot(result, previous)
    assert snapshot["trade_date"] == "2026-11-21"
    assert snapshot["total_count"] == 5200 and snapshot["matched_count"] == 2
    assert snapshot["added"] == [{"ts_code": "300750.SZ", "name": "宁德时代"}]
    assert snapshot["removed"] == [{"ts_code": "000001.SZ", "name": "平安银行"}]
    assert [s["ts_code"] for s in snapshot["stocks"]] == ["600000.SH", "300750.SZ"]


def test_build_pool_snapshot_without_previous_has_no_diff():
    from quant_research_engine.stock_pool import build_pool_snapshot

    snapshot = build_pool_snapshot({
        "trade_date": "2026-11-21", "total_count": 1, "matched_count": 1,
        "indicators": [], "stocks": [{"ts_code": "000001.SZ", "name": "平安银行"}],
    }, None)
    assert snapshot["added"] == [] and snapshot["removed"] == []


def test_saved_pool_csv_includes_indicator_columns_and_guards_formula_injection():
    from quant_research_engine.stock_pool import saved_pool_csv

    text = saved_pool_csv({
        "indicators": [{"key": EMA5, "label": "指数移动均线(5)", "precision": 4}],
        "stocks": [{
            "ts_code": "000001.SZ", "name": "=SUM(A1)", "close": 12.5,
            "indicator_values": {EMA5: 12.75},
        }],
    })
    lines = text.lstrip("\ufeff").splitlines()
    assert lines[0] == "股票代码,股票名称,收盘价,指数移动均线(5)"
    assert "'=SUM(A1)" in lines[1]
    assert "000001.SZ" in lines[1] and "12.5" in lines[1] and "12.75" in lines[1]


def test_stock_pool_page_exposes_saved_pool_controls_and_history():
    from quant_research_engine.gui.saas import create_saas_app

    html = create_saas_app().test_client().get('/saas/stock-pool').get_data(as_text=True)
    for marker in ('已保存股票池', 'sp-save-name', 'sp-save-pool',
                   '/api/saas/saved-stock-pools', '用于回测', '导出CSV',
                   'sp-saved-history', '新增', '移出'):
        assert marker in html


def test_new_strategy_page_supports_saved_pool_scope_prefill():
    from quant_research_engine.gui.saas import create_saas_app

    html = create_saas_app().test_client().get('/saas/new').get_data(as_text=True)
    assert 'saved-stock-pools' in html
    assert 'pool' in html and 'param-codes' in html


def test_saved_pool_delete_uses_accessible_modal_not_native_confirm():
    from quant_research_engine.gui.saas import create_saas_app

    html = create_saas_app().test_client().get('/saas/stock-pool').get_data(as_text=True)
    for marker in ('sp-delete-modal', 'sp-delete-confirm', 'sp-delete-cancel', 'aria-modal="true"'):
        assert marker in html
    assert 'if(!confirm(' not in html


def test_saved_pool_schema_grants_app_role_and_sequences():
    from pathlib import Path

    schema = (Path(__file__).parents[1] / 'deploy/saas/cloud_schema.sql').read_text()
    assert 'GRANT SELECT, INSERT, UPDATE, DELETE ON saved_stock_pools TO aguhuice' in schema
    assert 'GRANT SELECT, INSERT, UPDATE, DELETE ON saved_stock_pool_snapshots TO aguhuice' in schema
    assert 'GRANT USAGE, SELECT ON SEQUENCE saved_stock_pools_id_seq TO aguhuice' in schema
    assert 'GRANT USAGE, SELECT ON SEQUENCE saved_stock_pool_snapshots_id_seq TO aguhuice' in schema


def test_saved_pool_ensure_skips_ddl_when_schema_already_applied():
    from contextlib import contextmanager
    from quant_research_engine.gui.saas import app as app_module

    calls = []
    class Connection:
        def execute(self, statement):
            calls.append(str(statement))
            return [('saved_stock_pools',), ('saved_stock_pool_snapshots',)]
    class Engine:
        @contextmanager
        def begin(self):
            yield Connection()
    app_module._SAVED_STOCK_POOL_TABLES_ENSURED.clear()
    app_module._ensure_saved_stock_pool_tables(Engine())
    assert len(calls) == 1 and 'information_schema.tables' in calls[0]
