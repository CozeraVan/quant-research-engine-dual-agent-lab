"""Windows 侧 game 回归测试（任务单 docs/agent/46_GAME_WINDOWS_TASKS_2026-11-12.md）。

T1：样本 vol/amount 生产单位（手/千元），逐根均价区间断言；
T2：f6385d8 修复切片 6 项 RED→GREEN 测试并入（原 .tmp scratch，不再是回归资产）；
T3：game 状态显式返回 factor_basis（引用 factor_basis 契约常量，不造第二套口径）；
T4：average_price 公式登记但审计保持 skipped（Bar 无复权比率，禁止冒充前复权均价）。

本文件属 46 号 §2/§7 允许的「本轮新增 game 测试」；不改动既有测试。
"""
from __future__ import annotations

import re
import sys
from datetime import timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts" / "win"))

from game_preview_sample import N_DAYS, SampleGameStore  # noqa: E402

from quant_research_engine.game import validation  # noqa: E402
from quant_research_engine.game.data import PostgresGameDataProvider  # noqa: E402
from quant_research_engine.game.factors import DEFAULT_CANONICALS  # noqa: E402

TYP = "factors.stock_daily_overlap_typical_price.ema_5"
AVG = "factors.stock_daily_overlap_average_price.ema_5"


@pytest.fixture()
def provider():
    return PostgresGameDataProvider(SampleGameStore())


def test_sample_vol_amount_production_units():
    """T1：vol=手（1 手=100 股）、amount=千元；逐根 amount*10/vol ∈ [low, high]。

    均价（元/股）= amount×1000 元 / (vol×100 股) = amount*10/vol。
    样本若按「股/元」造，该比值是真实均价的 10 倍，必然越出当日区间。
    逐根校验全部标的全部 bar，不是抽查。
    """
    store = SampleGameStore()
    end = store.latest_trade_date()
    start = end - timedelta(days=4000)  # 覆盖 N_DAYS 个交易日（约 2240 自然日）
    symbols = store.list_symbols_with_bars(start, end)
    assert symbols, "样本必须有标的"
    checked = 0
    for symbol in symbols:
        rows = store.load_raw_bars(symbol, start, end)
        assert len(rows) == N_DAYS
        for row in rows:
            assert row["vol"] > 0
            average_price = row["amount"] * 10.0 / row["vol"]
            assert row["low"] <= average_price <= row["high"], (
                symbol, row["trade_date"], average_price, row["low"], row["high"])
            # 均价还须落在当日真实价格水平：防 vol/amount 同倍率缩放骗过区间断言
            assert abs(average_price - (row["open"] + row["close"]) / 2.0) < 0.01, (
                symbol, row["trade_date"], average_price)
            checked += 1
    assert checked == N_DAYS * len(symbols)


# ---------------------------------------------------------------- T2：f6385d8 修复切片回归
# 缺陷 1：game/validation.py 审计不按 price_basis 选择重算序列，
#         typical_price 口径 ema_5 被误报 mismatch。
# 缺陷 2：game/templates/game.html 的 .kv-grid 缺 display:grid 基类。
# 缺陷 3（样本夹具）：high==open 的 bar 前复权缩放后失去 tick 精度，
#         开盘价限价委托可能差半 tick 未成交。


def test_audit_typical_basis_no_false_mismatch(provider):
    session = provider.create_session(seed=7)
    provider.load_selected(session, (*DEFAULT_CANONICALS, TYP))
    audit = session.factor_audit
    assert TYP in audit["canonicals"], "typical 口径应被审计而非忽略"
    assert audit["canonicals"][TYP]["checked"] > 0
    assert audit["mismatches"] == 0, audit


def test_audit_still_catches_corrupted_typical(provider):
    session = provider.create_session(seed=7)
    provider.load_selected(session, (*DEFAULT_CANONICALS, TYP))
    for values in session.factors.values():
        if TYP in values:
            values[TYP] += 1.0
    audit = validation.audit_price_factors(
        session.bars, session.factors, session.selected_canonicals)
    assert audit["canonicals"][TYP]["mismatches"] > 0, "审计不得因修复而失效"


def test_audit_close_basis_regression(provider):
    session = provider.create_session(seed=7)
    audit = session.factor_audit
    assert audit["checked"] > 0
    assert audit["mismatches"] == 0, audit


def test_audit_skips_unregistered_basis(provider, monkeypatch):
    session = provider.create_session(seed=7)
    monkeypatch.setattr(validation, "factor_catalog", lambda: [{
        "canonical": AVG, "column": "ema_5", "price_basis": "average_price",
    }])
    factors = {i: {AVG: 12.34} for i in range(len(session.bars))}
    audit = validation.audit_price_factors(session.bars, factors, (AVG,))
    assert audit.get("skipped", {}).get(AVG) == "average_price"
    assert AVG not in audit["canonicals"]
    assert audit["mismatches"] == 0


def test_sample_open_price_orders_always_fill(provider):
    """样本 tick 精度回归：开盘价限价委托必须成交（真实行情同 tick 精度）。

    缺陷：high==open 的原始 bar 经前复权缩放后失去 tick 精度，
    委托价四舍五入到 0.01 可能越过 high/low 半 tick 导致未成交。
    """
    from quant_research_engine.core.models import OrderSide
    for seed in range(30):
        session = provider.create_session(seed=seed)
        session.advance()
        decision = session.decision_state()
        session.place_order(OrderSide.BUY, round(decision["next_open"], 2), 100)
        session.close_day()
        assert session.settlement["fill"] is not None, (seed, "buy unfilled")
        session.advance()
        decision = session.decision_state()
        session.place_order(OrderSide.SELL, round(decision["next_open"], 2), 100)
        session.close_day()
        assert session.settlement["fill"] is not None, (seed, "sell unfilled")


def test_template_kv_grid_display_grid():
    html = (REPO / "src" / "quant_research_engine" / "game" / "templates"
            / "game.html").read_text(encoding="utf-8")
    assert re.search(r"\.kv-grid\s*\{[^}]*display:\s*grid", html), \
        ".kv-grid 需要 display:grid 基类（lab-theme.css 无此类）"


# ---------------------------------------------------------------- T3：factor_basis 显式契约


def test_state_explicit_factor_basis():
    """T3：game 状态显式返回 factor_basis，值引用契约常量且在白名单内。

    QRE-FACTOR-BASIS-CONTRACT 第 1 条：生成侧必须带 factor_basis，不许静默省略。
    创建与 GET 两条状态出口都要带（同一 _state 序列化）。
    """
    from quant_research_engine.factor_basis import FACTOR_BASIS_QFQ_ANCHOR_V1, KNOWN_BASES
    from quant_research_engine.game.web import create_game_app
    app = create_game_app(PostgresGameDataProvider(SampleGameStore()), testing=True)
    client = app.test_client()
    created = client.post("/game/api/sessions")
    assert created.status_code == 200
    state = created.get_json()
    assert state["factor_basis"] == FACTOR_BASIS_QFQ_ANCHOR_V1
    assert state["factor_basis"] in KNOWN_BASES
    fetched = client.get(f"/game/api/sessions/{state['id']}")
    assert fetched.status_code == 200
    assert fetched.get_json()["factor_basis"] == FACTOR_BASIS_QFQ_ANCHOR_V1


# ---------------------------------------------------------------- T4：average_price 登记但保持 skipped


def test_average_price_formula_registered_but_skipped(provider, monkeypatch):
    """T4：原始公式登记为 amount×10/vol，但审计必须保持 skipped。

    Bar（core/models.py）无复权比率字段，bars_from_rows 只缩放 OHLC/pre_close、
    volume/amount 原值透传 → 前复权 Bar 上算出的是原始均价，禁止冒充前复权均价。
    启用条件：Bar 携带复权比率，或上游透传原生 vwap + 锚点（等 WSL 补齐输入）。
    """
    assert validation.AVERAGE_PRICE_RAW_FORMULA == "amount * 10 / vol"
    session = provider.create_session(seed=7)
    monkeypatch.setattr(validation, "factor_catalog", lambda: [{
        "canonical": AVG, "column": "ema_5", "price_basis": "average_price",
    }])
    factors = {i: {AVG: 12.34} for i in range(len(session.bars))}
    audit = validation.audit_price_factors(session.bars, factors, (AVG,))
    assert audit["skipped"].get(AVG) == "average_price", "登记公式不等于启用审计"
    assert AVG not in audit["canonicals"]
    assert audit["mismatches"] == 0


# ---------------------------------------------------------------- 视觉缺陷切片：禁用态可见


def test_template_disabled_visual_state():
    """禁用按钮必须有禁用视觉：游戏页只加载 lab-theme.css，不含 style.css 的
    button:disabled 规则，结算阶段「播放并结算/提交委托」disabled 却仍实心紫色。"""
    html = (REPO / "src" / "quant_research_engine" / "game" / "templates"
            / "game.html").read_text(encoding="utf-8")
    assert re.search(r"\.btn:disabled[^{]*\{[^}]*opacity", html), \
        "game.html 需要 .btn:disabled 视觉规则（opacity + cursor）"