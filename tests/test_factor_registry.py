"""因子语义注册表测试（QRE-GUI-FACTOR-REGISTRY-001）。

守护对象：
- canonical `schema.table.column` 仍是唯一字段标识，注册表只做展示与解析；
- 别名归一化（大小写/全角/空格/下划线/连字符/中文标点）后确定性命中；
- MACD 三输出（DIF=macd / DEA·信号线=macds / 柱=macdh）不混淆；
- 同列多价格口径默认 close 并给 notice，显式 typical_price 可选；
- 其他歧义返回 candidates，不猜；未知输入返回 missing；
- 防漂移校验：坏 canonical、未注册新列都必须被报出来。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quant_research_engine.gui.factor_registry import (
    FactorRegistry,
    duplicate_aliases,
    normalize_alias,
    validate_registry,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "configs" / "factor_registry.json"
CATALOG_JSON = ROOT / "configs" / "factor_catalog_llm.json"

MACD_CLOSE = "factors.stock_daily_momentum_close.macd_12_26_9"
MACDS_CLOSE = "factors.stock_daily_momentum_close.macds_12_26_9"
MACDH_CLOSE = "factors.stock_daily_momentum_close.macdh_12_26_9"
EMA5_CLOSE = "factors.stock_daily_overlap_close.ema_5"
EMA5_TYPICAL = "factors.stock_daily_overlap_typical_price.ema_5"
EMA20_CLOSE = "factors.stock_daily_overlap_close.ema_20"


@pytest.fixture(scope="module")
def registry() -> FactorRegistry:
    return FactorRegistry.load(REGISTRY_PATH)


# --- normalize_alias ---


def test_normalize_alias_english_case_and_separators():
    assert normalize_alias("ＥＭＡ＿５") == "ema5"
    assert normalize_alias("ema-5") == "ema5"
    assert normalize_alias("Ema 5") == "ema5"
    assert normalize_alias("ema · 5") == "ema5"
    assert normalize_alias("MACD_12_26_9") == "macd12269"


def test_normalize_alias_keeps_chinese_and_grouping():
    assert normalize_alias("MACD(12,26,9)") == "macd(12,26,9)"
    assert normalize_alias("20日指数均线") == "20日指数均线"
    assert normalize_alias("ＤＥＡ线") == "dea线"


# --- canonical 精确命中 ---


def test_resolve_full_canonical(registry):
    res = registry.resolve("factors.stock_daily_momentum_close.macd_12_26_9")
    assert res.status == "unique"
    assert res.canonical == MACD_CLOSE
    assert res.kind == "factor"


def test_resolve_canonical_without_schema(registry):
    res = registry.resolve("stock_daily_momentum_close.macd_12_26_9")
    assert res.status == "unique"
    assert res.canonical == MACD_CLOSE


# --- MACD 三输出 ---


@pytest.mark.parametrize("text", ["DEA", "dea线", "信号线", "macd_signal", "MACD DEA"])
def test_resolve_dea_variants_to_macds(registry, text):
    res = registry.resolve(text)
    assert res.status == "unique", (text, res)
    assert res.canonical == MACDS_CLOSE
    assert res.output == "signal"


@pytest.mark.parametrize("text", ["MACD", "dif", "MACD DIF", "快线"])
def test_resolve_macd_dif(registry, text):
    res = registry.resolve(text)
    assert res.status == "unique", (text, res)
    assert res.canonical == MACD_CLOSE
    assert res.output == "dif"
    assert res.notice and "12,26,9" in res.notice


@pytest.mark.parametrize("text", ["MACD柱", "macd_hist", "柱状线"])
def test_resolve_macd_hist(registry, text):
    res = registry.resolve(text)
    assert res.status == "unique", (text, res)
    assert res.canonical == MACDH_CLOSE
    assert res.output == "hist"


def test_resolve_macd_explicit_params(registry):
    res = registry.resolve("MACD(6,13,5)")
    assert res.status == "unique"
    assert res.canonical == "factors.stock_daily_momentum_close.macd_6_13_5"
    assert res.notice is None or "12,26,9" not in res.notice


def test_resolve_macd_golden_cross_hint_keeps_dif(registry):
    # 金叉是 DIF 上穿 DEA，解析 MACD 仍给 DIF，不自动改成信号线
    res = registry.resolve("MACD金叉")
    assert res.canonical == MACD_CLOSE


# --- 同列多价格口径 ---


def test_resolve_ema5_defaults_close_with_notice(registry):
    res = registry.resolve("ema_5")
    assert res.status == "unique"
    assert res.canonical == EMA5_CLOSE
    assert res.price_basis == "close"
    assert res.notice and "典型价" in res.notice


def test_resolve_ema5_explicit_typical_price(registry):
    res = registry.resolve("ema_5", price_basis="typical_price")
    assert res.status == "unique"
    assert res.canonical == EMA5_TYPICAL
    assert res.price_basis == "typical_price"
    assert res.notice is None or "典型价" not in res.notice


def test_resolve_chinese_20day_ema(registry):
    res = registry.resolve("20日指数均线")
    assert res.status == "unique"
    assert res.canonical == EMA20_CLOSE


def test_resolve_typical_price_chinese_alias(registry):
    res = registry.resolve("5日典型价指数均线", price_basis="typical_price")
    assert res.status == "unique"
    assert res.canonical == EMA5_TYPICAL


# --- 其他歧义与未知 ---


def test_resolve_non_price_ambiguity_returns_candidates(registry):
    res = registry.resolve("布林带")
    assert res.status == "ambiguous"
    assert res.canonical is None
    assert set(res.candidates) >= {
        "factors.stock_daily_volatility_close.bbu_20_2_0_2_0",
        "factors.stock_daily_volatility_close.bbm_20_2_0_2_0",
        "factors.stock_daily_volatility_close.bbl_20_2_0_2_0",
    }


def test_resolve_unknown_returns_missing(registry):
    res = registry.resolve("完全不存在的指标xyz")
    assert res.status == "missing"
    assert res.canonical is None
    assert res.candidates == ()


def test_resolve_empty_returns_missing(registry):
    assert registry.resolve("   ").status == "missing"


# --- 行情字段单独识别 ---


def test_resolve_market_field_chinese(registry):
    res = registry.resolve("收盘价")
    assert res.status == "unique"
    assert res.kind == "market"
    assert res.canonical == "public.stock_daily.close"


def test_resolve_market_field_not_in_factor_fields(registry):
    assert registry.resolve("成交量").canonical == "public.stock_daily.vol"


# --- 展示与派生 ---


def test_display_returns_zh_and_canonical(registry):
    info = registry.display("factors.stock_daily_momentum_close", "macds_12_26_9")
    assert info is not None
    assert info["canonical"] == MACDS_CLOSE
    assert info["price_basis"] == "close"
    assert info["zh"]
    assert "信号线" in info["aliases"]


def test_display_unregistered_returns_none(registry):
    assert registry.display("factors.stock_daily_overlap_close", "no_such_col") is None


def test_common_factor_targets_all_exist_in_snapshot(registry):
    snapshot = json.loads(CATALOG_JSON.read_text(encoding="utf-8"))
    for target in registry.common_factor_targets():
        table, column = target.split(".", 2)[1:]
        assert column in snapshot.get(table, []), target


def test_search_matches_chinese_and_alias(registry):
    hits = registry.search("指数均线")
    assert EMA20_CLOSE in hits
    hits = registry.search("信号线")
    assert MACDS_CLOSE in hits


# --- 防漂移校验 ---


def _snapshot(registry: FactorRegistry) -> dict[str, list[str]]:
    """由注册表自身推导的因子库快照（保证校验基线干净）。"""
    snapshot: dict[str, list[str]] = {}
    for entry in registry.entries.values():
        snapshot.setdefault(entry.table, []).append(entry.column)
    return snapshot


def test_validate_registry_clean_snapshot(registry):
    assert validate_registry(_snapshot(registry), registry=registry) == []


def test_validate_registry_reports_bad_canonical(registry):
    broken = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    target = next(f for f in broken["factors"] if f["table"] == "stock_daily_momentum_close")
    target["column"] = "definitely_missing_column_xyz"
    target["canonical"] = "factors.stock_daily_momentum_close.definitely_missing_column_xyz"
    tmp = ROOT / ".tmp" / "factor-registry" / "_broken_registry.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
    broken_registry = FactorRegistry.load(tmp)
    issues = validate_registry(_snapshot(registry), registry=broken_registry)
    assert any("definitely_missing_column_xyz" in i for i in issues)
    tmp.unlink()


def test_validate_registry_reports_unregistered_column(registry):
    snapshot = _snapshot(registry)
    snapshot["stock_daily_momentum_close"].append("brand_new_indicator_1")
    report = registry.coverage_report(snapshot)
    assert "stock_daily_momentum_close.brand_new_indicator_1" in report["unregistered"]
    assert report["unregistered_columns"] > 0


def test_validate_registry_reports_dangling_alias(registry):
    broken = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    broken["extra_aliases"]["测试别名"] = ["factors.stock_daily_momentum_close.not_exist_col"]
    tmp = ROOT / ".tmp" / "factor-registry" / "_broken_registry.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
    broken_registry = FactorRegistry.load(tmp)
    issues = validate_registry(_snapshot(registry), registry=broken_registry)
    assert any("测试别名" in i and "not_exist_col" in i for i in issues)
    tmp.unlink()


def test_duplicate_alias_forms_candidates_not_override(registry):
    dupes = duplicate_aliases(registry)
    assert "ema5" in dupes
    assert set(dupes["ema5"]) == {EMA5_CLOSE, EMA5_TYPICAL}


# --- 覆盖报告 ---


def test_coverage_report_counts(registry):
    snapshot = json.loads(CATALOG_JSON.read_text(encoding="utf-8"))
    report = registry.coverage_report(snapshot)
    assert report["total_columns"] > 800
    assert report["registered_columns"] > 300
    assert report["unregistered_columns"] >= 0
    assert report["registered_columns"] + report["unregistered_columns"] == report["total_columns"]


def test_validate_registry_against_real_snapshot(registry):
    """当前因子库快照下不得有失效 canonical / 悬空别名（防漂移门禁）。"""
    snapshot = json.loads(CATALOG_JSON.read_text(encoding="utf-8"))
    assert validate_registry(snapshot, registry=registry) == []


def test_registry_covers_every_snapshot_column(registry):
    """每个真实列都要有注册条目（zh 可为 null，但 canonical 必须可对照）。"""
    snapshot = json.loads(CATALOG_JSON.read_text(encoding="utf-8"))
    for table, columns in snapshot.items():
        for column in columns:
            if column in ("ts_code", "trade_date"):
                continue
            assert registry.display(table, column) is not None, f"{table}.{column}"


def test_price_basis_preference_matches_wizard(registry):
    from quant_research_engine.gui.factor_wizard import PRICE_BASIS_PREFERENCE

    assert registry.price_basis_preference == PRICE_BASIS_PREFERENCE
