"""CR-2026-10-09 NL 编译四层防线的测试（真实因子目录注入/别名/修复回路/兜底报错）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from quant_research_engine.gui.factor_catalog_llm import (
    catalog_column_lookup,
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
    def test_render_flat_full_names(self):
        # 2026-10-10 生产实测：@{} 压缩语法 LLM 会误读，必须平铺全列名
        text = render_catalog_text({"stock_daily_momentum_close": list(MACD_POOL)})
        assert "macds_12_26_9" in text and "macd_12_26_9" in text and "@{" not in text
        assert "factors.stock_daily_momentum_close" in text and "动量" in text
        assert "行情字段" in text and "close" in text

    def test_snapshot_roundtrip(self, tmp_path):
        p = tmp_path / "cat.txt"
        p.write_text(render_catalog_text({"stock_daily_momentum_close": list(MACD_POOL)}),
                     encoding="utf-8")
        assert load_catalog_text(p) is not None and "macds_12_26_9" in load_catalog_text(p)
        assert load_catalog_text(tmp_path / "missing.txt") is None

    def test_json_lookup_fallback(self, tmp_path):
        # DB 不可用时的 lookup 兜底（ECS 纠错/重试层依赖）
        import json
        p = tmp_path / "cat.json"
        p.write_text(json.dumps({"stock_daily_momentum_close": sorted(MACD_POOL)}),
                     encoding="utf-8")
        lk = catalog_column_lookup(p)
        cols = lk("factors.stock_daily_momentum_close")
        assert "macds_12_26_9" in cols and "macd_signal_12_26_9" not in cols
        assert catalog_column_lookup(tmp_path / "missing.json") is None

    def test_system_prompt_injects_real_catalog(self):
        # 仓库快照存在（scripts/gen_factor_catalog_llm.py 生成）
        prompt = build_system_prompt()
        assert "禁止发明" in prompt
        assert "factors.stock_daily_momentum_close" in prompt
        assert "macds_12_26_9" in prompt  # 平铺全列名（非压缩语法）


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


class TestRegistryAliasResolution:
    """因子语义注册表接入 NL 链路（QRE-GUI-FACTOR-REGISTRY-001）。

    注册表精确别名取代旧子串替换的优先级；Prompt 只保留 canonical 目录和
    少量常用示例，**不注入全量别名**。
    """

    ENV = TestLayer3RetryLoop.ENV

    def _http(self, content):
        def http_post(url, headers, payload, timeout):
            return {"choices": [{"message": {"content": content}}]}

        return http_post

    def test_prompt_does_not_dump_full_aliases(self):
        prompt = build_system_prompt()
        # canonical 目录 + 少量常用示例仍在
        assert "常用已落库列" in prompt and "factors.stock_daily_momentum_close" in prompt
        # 全量别名（规则生成的中文参数写法）不得进 Prompt
        assert "20日指数移动均线" not in prompt
        assert "14日相对强弱指标" not in prompt
        assert "MACD(12,26,9)" not in prompt
        # Prompt 体积有界（不随因子库线性膨胀别名）
        assert len(prompt) < 60000

    def test_dea_chinese_name_resolves_to_macds(self, tmp_path):
        yaml_text = GOOD_YAML.replace(
            "factors.stock_daily_momentum_close.macds_12_26_9",
            "factors.stock_daily_momentum_close.dea",
        )
        result = compile_nl(
            "MACD 信号线上穿",
            http_post=self._http(yaml_text),
            column_lookup=lambda table: set(MACD_POOL) if "momentum_close" in table else set(),
            queue_path=tmp_path / "q.json",
            env=self.ENV,
        )
        assert result["ok"] is True, result
        parsed = yaml.safe_load(result["yaml"])
        assert parsed["data"]["factor_fields"]["macd_sig"] == (
            "factors.stock_daily_momentum_close.macds_12_26_9"
        )
        assert result["corrections"][0]["via"] == "registry"
        assert any("已自动纠正" in w and "dea→macds_12_26_9" in w for w in result["warnings"])
        # 默认参数/价格口径提示要送到用户面前
        assert any("未指定 MACD 参数" in w for w in result["warnings"])

    def test_ambiguous_alias_returns_candidates(self, tmp_path):
        # kdj 同时指向 K/D/J 三条线 → 歧义，只给 canonical 候选，不自动错配
        yaml_text = GOOD_YAML.replace(
            "factors.stock_daily_momentum_close.macds_12_26_9",
            "factors.stock_daily_momentum_close.kdj",
        )
        result = compile_nl(
            "x",
            http_post=self._http(yaml_text),
            column_lookup=lambda table: set(MACD_POOL) if "momentum_close" in table else set(),
            queue_path=tmp_path / "q.json",
            env=self.ENV,
        )
        assert result["ok"] is False
        assert result["code"] == "missing_factors"
        assert "kdj" in result["error"]
        assert any("k_9_3" in s for s in result["suggestions"][0]["suggestions"])
        assert "corrections" not in result

    def test_price_basis_default_close_notice(self, tmp_path):
        ema_yaml = """experiment:
  name: t_ema
  market_profile: ashare_daily_default
  frequency: daily
data:
  market_fields: [open, high, low, close, pre_close, vol, amount]
  factor_fields:
    ma: factors.stock_daily_overlap_close.ema5
universe:
  exclude_st: true
  exclude_suspended: true
  exclude_risk_warning: true
  min_listing_days: 120
signal:
  entry: close > ma
holding:
  max_holding_days: 10
evaluation:
  forward_return_horizons: [1, 5]
  quantiles: 5
"""
        result = compile_nl(
            "x",
            http_post=self._http(ema_yaml),
            column_lookup=lambda table: (
                {"ema_5", "ema_20"} if "overlap_close" in table else set(MACD_POOL)
            ),
            queue_path=tmp_path / "q.json",
            env=self.ENV,
        )
        assert result["ok"] is True, result
        parsed = yaml.safe_load(result["yaml"])
        assert parsed["data"]["factor_fields"]["ma"] == "factors.stock_daily_overlap_close.ema_5"
        # 同列多价格口径：默认 close 并提示
        assert any("典型价" in w and "收盘价" in w for w in result["warnings"])


# --- NL 小样本编译验证（固定样本 + stub LLM，不消耗真实模型额度） ---

_SAMPLE_CASES = [
    # (输入, 期望 status, 期望 canonical 或候选集合)
    ("DEA", "unique", "factors.stock_daily_momentum_close.macds_12_26_9"),
    ("信号线", "unique", "factors.stock_daily_momentum_close.macds_12_26_9"),
    ("macd_signal", "unique", "factors.stock_daily_momentum_close.macds_12_26_9"),
    ("MACD", "unique", "factors.stock_daily_momentum_close.macd_12_26_9"),
    ("MACD柱", "unique", "factors.stock_daily_momentum_close.macdh_12_26_9"),
    ("MACD(6,13,5)", "unique", "factors.stock_daily_momentum_close.macd_6_13_5"),
    ("20日指数均线", "unique", "factors.stock_daily_overlap_close.ema_20"),
    ("34日指数均线", "unique", "factors.stock_daily_overlap_typical_price.ema_34"),
    ("RSI", "unique", "factors.stock_daily_momentum_close.rsi_14"),
    ("布林带上轨", "unique", "factors.stock_daily_volatility_close.bbu_20_2_0_2_0"),
    ("收盘价", "unique", "public.stock_daily.close"),
]


def test_nl_sample_matrix_resolves_deterministically():
    from quant_research_engine.gui.factor_registry import load_registry

    registry = load_registry()
    for text, status, expected in _SAMPLE_CASES:
        res = registry.resolve(text)
        assert res.status == status, (text, res)
        assert res.canonical == expected, (text, res.canonical, expected)


def test_nl_sample_matrix_price_basis_and_ambiguity():
    from quant_research_engine.gui.factor_registry import load_registry

    registry = load_registry()
    # 同列多价格口径：默认 close + 提示
    res = registry.resolve("ema_5")
    assert res.canonical == "factors.stock_daily_overlap_close.ema_5"
    assert res.notice and "典型价" in res.notice
    # 显式典型价
    assert registry.resolve("ema_5", price_basis="typical_price").canonical == (
        "factors.stock_daily_overlap_typical_price.ema_5"
    )
    # 其他歧义：只给候选
    for text in ("布林带", "kdj", "dmi"):
        res = registry.resolve(text)
        assert res.status == "ambiguous", (text, res)
        assert len(res.candidates) >= 2 and res.canonical is None, (text, res)
    # 未知
    assert registry.resolve("量子纠缠因子").status == "missing"


def _stub_http(content):
    def http_post(url, headers, payload, timeout):
        return {"choices": [{"message": {"content": content}}]}

    return http_post


def test_nl_sample_compile_end_to_end_with_stub_llm(tmp_path):
    """固定 NL 样本 → stub LLM 输出含别名写法 → 注册表纠正 → YAML 可用。"""
    sample_yaml = GOOD_YAML.replace(
        "factors.stock_daily_momentum_close.macds_12_26_9",
        "factors.stock_daily_momentum_close.macd_signal_12_26_9",
    )
    result = compile_nl(
        "MACD 金叉买入，死叉卖出",
        http_post=_stub_http(sample_yaml),
        column_lookup=lambda table: set(MACD_POOL) if "momentum_close" in table else set(),
        queue_path=tmp_path / "q.json",
        env=TestLayer3RetryLoop.ENV,
    )
    assert result["ok"] is True, result
    parsed = yaml.safe_load(result["yaml"])
    assert parsed["data"]["factor_fields"]["macd_sig"] == (
        "factors.stock_daily_momentum_close.macds_12_26_9"
    )
    # canonical / 回测口径不变：仍是同一张表的同一列
    assert parsed["signal"]["entry"] == "macd > macd_sig"
    assert not (tmp_path / "q.json").exists()
