"""CR-2026-10-09 NL 编译四层防线的测试（真实因子目录注入/别名/修复回路/兜底报错）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quant_research_engine.gui.factor_catalog_llm import (
    compress_columns,
    generate_catalog,
    load_catalog_text,
    render_catalog_text,
)
from quant_research_engine.gui.factor_correction import (
    alias_variants,
    auto_fix_column,
    load_factor_aliases,
)
from quant_research_engine.gui.nl_compiler import (
    MAX_FIX_RETRIES,
    _fixup_prompt,
    build_system_prompt,
    compile_nl,
)

MACD_POOL = {"macd_12_26_9", "macds_12_26_9", "macdh_12_26_9"}
GOOD_YAML = """experiment:
  name: t_macd
  market_profile: ashare_daily_default
  frequency: daily
data:
  market_fields: [open, high, low, close, pre_close, vol, amount]
  factor_fields:
    macd: factors.stock_daily_momentum_close.macd_12_26_9
    macd_sig: factors.stock_daily_momentum_close.macds_12_26_9
universe:
  exclude_st: true
  exclude_suspended: true
  exclude_risk_warning: true
  min_listing_days: 120
signal:
  entry: "macd > macd_sig"
  exit: "macd < macd_sig"
holding:
  max_holding_days: 10
evaluation:
  forward_return_horizons: [1, 5]
  quantiles: 5
"""
BAD_YAML = GOOD_YAML.replace(
    "factors.stock_daily_momentum_close.macds_12_26_9",
    "factors.stock_daily_momentum_close.macd_signal_12_26_9",
)
BROKEN_YAML = GOOD_YAML.replace(
    "factors.stock_daily_momentum_close.macds_12_26_9",
    "factors.stock_daily_momentum_close.xyz_nonexist_99",
).replace("macd > macd_sig", "macd > xyz_sig").replace("macd < macd_sig", "macd < xyz_sig").replace(
    "macd_sig: factors", "xyz_sig: factors")


def _lookup_factory(mapping=None):
    tables = {"factors.stock_daily_momentum_close": set(MACD_POOL)}
    if mapping:
        tables.update(mapping)
    return lambda table: tables.get(table, set())


class TestLayer1Catalog:
    def test_compress_groups_params(self):
        out = compress_columns(["ts_code", "trade_date", "macd_12_26_9", "macd_6_13_5",
                                "macds_12_26_9", "ha_close"])
        assert "macd@{12_26_9|6_13_5}" in out and "macds@{12_26_9}" in out
        assert "ha_close" in out and "ts_code" not in out

    def test_render_has_table_column_and_label(self):
        text = render_catalog_text({"stock_daily_momentum_close": list(MACD_POOL)})
        assert "factors.stock_daily_momentum_close" in text and "动量" in text
        assert "macds@{12_26_9}" in text
        assert "行情字段" in text and "close" in text

    def test_snapshot_roundtrip(self, tmp_path):
        p = tmp_path / "cat.txt"
        generate_catalog(path=p, db_url=None) if False else None  # DB 不跑；用 render 直写
        p.write_text(render_catalog_text({"stock_daily_momentum_close": list(MACD_POOL)}),
                     encoding="utf-8")
        assert load_catalog_text(p) is not None and "macds" in load_catalog_text(p)
        assert load_catalog_text(tmp_path / "missing.txt") is None

    def test_system_prompt_injects_real_catalog(self):
        # 仓库快照存在（scripts/gen_factor_catalog_llm.py 生成）
        prompt = build_system_prompt()
        assert "禁止发明" in prompt
        assert "factors.stock_daily_momentum_close" in prompt
        assert "macds@{12_26_9" in prompt  # signal 线真实列名在目录内


class TestLayer2Alias:
    def test_alias_table_loads(self):
        aliases = load_factor_aliases()
        pairs = {(a["from"], a["to"]) for a in aliases}
        assert ("signal", "s") in pairs and ("dea", "s") in pairs

    def test_alias_variants(self):
        variants = alias_variants("macd_signal_12_26_9")
        assert "macds_12_26_9" in variants or "macd_s_12_26_9" in variants

    def test_auto_fix_macd_signal_to_macds(self):
        # 用户报告的确切案例：LLM 编 macd_signal → 库内 macds
        fix = auto_fix_column("macd_signal_12_26_9", MACD_POOL)
        assert fix == "macds_12_26_9"

    def test_alias_no_ambiguous_fix(self):
        fix = auto_fix_column("signal_999", {"asdf", "qwer"})  # 无命中不变
        assert fix is None


class TestLayer3RetryLoop:
    ENV = {"QRE_NL_LLM_BASE_URL": "http://fake", "QRE_NL_LLM_API_KEY": "k",
           "QRE_NL_LLM_MODEL": "m"}

    def _http_recorder(self, replies):
        calls = []

        def http_post(url, headers, payload, timeout):
            calls.append(payload)
            return {"choices": [{"message": {"content": replies[len(calls) - 1]}}]}
        return http_post, calls

    def test_alias_fix_no_retry_needed(self):
        # 编造的 macd_signal 被别名层就地修复 → 一轮通过不重试
        http, calls = self._http_recorder([BAD_YAML])
        r = compile_nl("macd 金叉", http_post=http, column_lookup=_lookup_factory(),
                       env=self.ENV)
        assert r["ok"] is True and r.get("fix_attempts") is None
        assert len(calls) == 1
        assert "macds_12_26_9" in r["yaml"]

    def test_retry_loop_feeds_back_and_recovers(self, tmp_path):
        # 第一轮编造 xyz_nonexist_99（别名/纠错都救不了）→ 回喂重试 → 第二轮正确
        http, calls = self._http_recorder([BROKEN_YAML, GOOD_YAML])
        r = compile_nl("macd 策略", http_post=http, column_lookup=_lookup_factory(),
                       queue_path=tmp_path / "q.json", env=self.ENV)
        assert r["ok"] is True and r["fix_attempts"] == 1
        assert len(calls) == 2
        retry_prompt = calls[1]["messages"][-1]["content"]
        assert "xyz_nonexist_99" in retry_prompt and "用户需求" in retry_prompt

    def test_retry_exhausted_friendly_error(self, tmp_path):
        http, calls = self._http_recorder([BROKEN_YAML] * (1 + MAX_FIX_RETRIES))
        r = compile_nl("macd 策略", http_post=http, column_lookup=_lookup_factory(),
                       queue_path=tmp_path / "q.json", env=self.ENV)
        assert r["ok"] is False and r["code"] == "missing_factors"
        assert r["fix_attempts"] == MAX_FIX_RETRIES
        assert len(calls) == 1 + MAX_FIX_RETRIES
        assert "申请新因子" in r["error"] or "申请新增因子" in r["error"]
        assert r["suggestions"]  # 候选非空
        # 缺因子入队（queue 副作用仍在）
        assert (tmp_path / "q.json").exists()


class TestLayer4FixupPrompt:
    def test_fixup_prompt_format(self):
        hints = [{"alias": "a", "table": "factors.t", "column": "bad_col",
                  "suggestions": ["good_col_1"], "suggestion_scope": "same_table"}]
        text = _fixup_prompt("原始需求", "bad: yaml", hints)
        assert "factors.t.bad_col" in text and "good_col_1" in text
        assert "禁止编造列名" in text and "原始需求" in text
