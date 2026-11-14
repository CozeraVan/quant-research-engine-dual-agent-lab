"""NL 指标语义与 batch 工程参数的回归测试。"""

from __future__ import annotations

import pandas as pd
import pytest
import yaml

from quant_research_engine.gui import nl_semantics as sem
from quant_research_engine.gui.nl_compiler import (
    MAX_FIX_RETRIES,
    build_system_prompt,
    compile_nl,
)
from quant_research_engine.gui.nl_semantics import (
    ISSUE_BOLL_BARE_BELOW_UPPER,
    ISSUE_HIST_SHRINK_WITHOUT_POSITIVE,
    indicator_semantic_issues,
)
from quant_research_engine.strategies.spec import StrategySpec


ENV = {
    "QRE_NL_LLM_BASE_URL": "http://fake",
    "QRE_NL_LLM_API_KEY": "k",
    "QRE_NL_LLM_MODEL": "m",
}
POOL = {"macd_12_26_9", "macds_12_26_9", "macdh_12_26_9", "rsi_14"}
INDICATOR_FACTORS = {
    "dif": "factors.stock_daily_momentum_close.macd_12_26_9",
    "dea": "factors.stock_daily_momentum_close.macds_12_26_9",
    "macd_hist": "factors.stock_daily_momentum_close.macdh_12_26_9",
    "kdj_k": "factors.stock_daily_momentum_close.k_9_3",
    "bb_upper": "factors.stock_daily_volatility_close.bbu_20_2_0_2_0",
}


def _lookup(table_map=None):
    tables = {
        "factors.stock_daily_momentum_close": set(POOL),
        "factors.stock_daily_overlap_close": {
            "ema_5",
            "ema_20",
            "sma_5",
            "sma_20",
            "sma_60",
            "sma_200",
        },
        "factors.stock_daily_overlap_typical_price": {"ema_200"},
    }
    if table_map:
        tables.update(table_map)
    return lambda table: tables.get(table, set())


def _indicator_lookup():
    return _lookup(
        {
            "factors.stock_daily_momentum_close": POOL | {"k_9_3"},
            "factors.stock_daily_volatility_close": {"bbu_20_2_0_2_0"},
        }
    )


def _http(replies):
    calls: list[str] = []

    def http_post(url, headers, payload, timeout):
        calls.append(payload["messages"][-1]["content"])
        return {
            "choices": [
                {"message": {"content": replies[len(calls) - 1]}},
            ]
        }

    return http_post, calls


def _spec(entry, exit_=None, **factors):
    spec = {
        "experiment": {
            "name": "t",
            "market_profile": "ashare_daily_default",
            "frequency": "daily",
        },
        "data": {
            "market_fields": ["open", "high", "low", "close", "pre_close", "vol", "amount"],
            "factor_fields": factors or INDICATOR_FACTORS,
        },
        "universe": {
            "exclude_st": True,
            "exclude_suspended": True,
            "exclude_risk_warning": True,
            "min_listing_days": 120,
        },
        "signal": {"entry": entry},
        "holding": {"max_holding_days": 0},
        "evaluation": {"forward_return_horizons": [1, 3, 5], "quantiles": 5},
    }
    if exit_ is not None:
        spec["signal"]["exit"] = exit_
    return spec


def _yaml(entry, exit_=None, **factors):
    return yaml.safe_dump(
        _spec(entry, exit_, **factors), allow_unicode=True, sort_keys=False
    )


def test_hist_shrink_exit_requires_positive_guard():
    description = "MACD绿柱转红柱且K值大于50买入，红柱缩短或K值小于70卖出"
    mapping = _spec(
        "(macd_hist > 0) and (macd_hist.shift(1) <= 0) and (kdj_k > 50)",
        "(macd_hist < macd_hist.shift(1)) or (kdj_k < 70)",
    )

    issues = indicator_semantic_issues(mapping, description)

    assert len(issues) == 1
    assert issues[0]["severity"] == "error"
    assert issues[0]["code"] == ISSUE_HIST_SHRINK_WITHOUT_POSITIVE
    assert issues[0]["side"] == "exit"


def test_hist_shrink_with_positive_guard_is_canonical():
    description = "MACD绿柱转红柱且K值大于50买入，红柱缩短或K值小于70卖出"
    mapping = _spec(
        "(macd_hist > 0) and (macd_hist.shift(1) <= 0) and (kdj_k > 50)",
        "((macd_hist > 0) and (macd_hist < macd_hist.shift(1))) or (kdj_k < 70)",
    )

    assert indicator_semantic_issues(mapping, description) == []


def test_hist_rule_requires_description_trigger():
    mapping = _spec(
        "(macd_hist > 0) and (macd_hist.shift(1) <= 0)",
        "(macd_hist < macd_hist.shift(1)) or (kdj_k < 70)",
    )

    assert indicator_semantic_issues(mapping, "MACD指标买入，K值小于70卖出") == []


def test_bare_boll_below_upper_exit_is_rejected():
    description = "MACD绿柱转红柱买入，K值小于70或收盘跌破BOLL上轨卖出"
    mapping = _spec(
        "(macd_hist > 0) and (macd_hist.shift(1) <= 0)",
        "(kdj_k < 70) or (close < bb_upper)",
    )

    issues = indicator_semantic_issues(mapping, description)

    assert len(issues) == 1
    assert issues[0]["code"] == ISSUE_BOLL_BARE_BELOW_UPPER
    assert issues[0]["side"] == "exit"


@pytest.mark.parametrize(
    "exit_expression",
    [
        "(kdj_k < 70) or ((close.shift(1) >= bb_upper.shift(1)) and (close < bb_upper))",
        "(close > bb_upper) and (close.shift(1) <= bb_upper.shift(1))",
    ],
)
def test_guarded_boll_exit_is_canonical(exit_expression):
    description = "MACD绿柱转红柱买入，K值小于70或收盘脱离BOLL上轨卖出"
    mapping = _spec(
        "(macd_hist > 0) and (macd_hist.shift(1) <= 0)", exit_expression
    )

    assert indicator_semantic_issues(mapping, description) == []


def test_compile_nl_feeds_indicator_issue_back_and_recovers():
    description = "MACD绿柱转红柱且K值大于50买入，红柱缩短或K值小于70卖出"
    entry = "(macd_hist > 0) and (macd_hist.shift(1) <= 0) and (kdj_k > 50)"
    bad = _yaml(entry, "(macd_hist < macd_hist.shift(1)) or (kdj_k < 70)")
    good = _yaml(
        entry,
        "((macd_hist > 0) and (macd_hist < macd_hist.shift(1))) or (kdj_k < 70)",
    )
    http_post, calls = _http([bad, good])

    result = compile_nl(
        description, env=ENV, http_post=http_post, column_lookup=_indicator_lookup()
    )

    assert result["ok"] is True
    assert result["fix_attempts"] == 1
    assert len(calls) == 2
    assert "macd_hist > 0" in calls[1]


def test_compile_nl_stops_with_indicator_error_after_retries():
    description = "MACD绿柱转红柱且K值大于50买入，红柱缩短或K值小于70或收盘跌破BOLL上轨卖出"
    entry = "(macd_hist > 0) and (macd_hist.shift(1) <= 0) and (kdj_k > 50)"
    bad = _yaml(
        entry,
        "(macd_hist < macd_hist.shift(1)) or (kdj_k < 70) or (close < bb_upper)",
    )
    http_post, calls = _http([bad] * (1 + MAX_FIX_RETRIES))

    result = compile_nl(
        description, env=ENV, http_post=http_post, column_lookup=_indicator_lookup()
    )

    assert result["ok"] is False
    assert result["code"] == "semantic_indicator_invalid"
    assert len(calls) == 1 + MAX_FIX_RETRIES
    assert {issue["code"] for issue in result["semantic_issues"]} >= {
        ISSUE_HIST_SHRINK_WITHOUT_POSITIVE,
        ISSUE_BOLL_BARE_BELOW_UPPER,
    }
    assert result["yaml"]


def test_market_profile_is_loaded_from_spec_and_explicit_reference(tmp_path):
    from quant_research_engine.apps.cli import _resolve_market_profile
    from quant_research_engine.markets.ashare import AShareMarketProfile

    assert StrategySpec.from_mapping(
        _spec("dif > dea")
    ).market_profile == "ashare_daily_default"
    without_profile = _spec("dif > dea")
    del without_profile["experiment"]["market_profile"]
    assert StrategySpec.from_mapping(without_profile).market_profile is None

    assert isinstance(_resolve_market_profile(None), AShareMarketProfile)
    assert isinstance(
        _resolve_market_profile("ashare_daily_default"), AShareMarketProfile
    )
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        "market_profile:\n  name: test_profile\n  lot_size:\n    buy_lot: 200\n",
        encoding="utf-8",
    )
    assert _resolve_market_profile(str(profile_path)).buy_lot == 200
    with pytest.raises(ValueError):
        _resolve_market_profile("no_such_profile_xyz_20261114")


def test_batch_universe_exclusions_are_applied():
    from quant_research_engine.apps.cli import _apply_universe_exclusions

    metadata = pd.DataFrame(
        {
            "ts_code": ["A.SZ", "B.SZ", "C.SZ", "D.SZ"],
            "is_st": [True, False, False, False],
            "is_risk_warning": [False, True, False, False],
            "is_suspended": [False, False, True, False],
        }
    )
    spec = StrategySpec.from_mapping(_spec("dif > dea"))

    kept, excluded = _apply_universe_exclusions(
        list(metadata["ts_code"]), metadata, spec
    )

    assert kept == ["D.SZ"]
    assert excluded["st"] == {"A.SZ"}
    assert excluded["risk_warning"] == {"B.SZ"}
    assert excluded["suspended"] == {"C.SZ"}

    mapping = _spec("dif > dea")
    mapping["universe"]["exclude_st"] = False
    kept, _ = _apply_universe_exclusions(
        list(metadata["ts_code"]), metadata, StrategySpec.from_mapping(mapping)
    )
    assert "A.SZ" in kept

    kept, excluded = _apply_universe_exclusions(["A.SZ"], None, spec)
    assert kept == ["A.SZ"]
    assert excluded == {"st": set(), "risk_warning": set(), "suspended": set()}

    kept, excluded = _apply_universe_exclusions(
        ["A.SZ"], pd.DataFrame({"ts_code": ["A.SZ"]}), spec
    )
    assert kept == ["A.SZ"]
    assert excluded == {"st": set(), "risk_warning": set(), "suspended": set()}


def test_system_prompt_contains_real_indicator_columns():
    prompt = build_system_prompt()

    assert "macdh_12_26_9" in prompt
    assert "bbu_20_2_0_2_0" in prompt
    assert sem.ISSUE_HIST_SHRINK_WITHOUT_POSITIVE == ISSUE_HIST_SHRINK_WITHOUT_POSITIVE
