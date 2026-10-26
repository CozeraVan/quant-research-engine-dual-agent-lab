"""QRE-SAAS-NL-A1：自然语言输入前置校验（规则层 + DeepSeek 裁判）。

真实本地 PG 临时库（deploy/saas/cloud_schema.sql），LLM 与裁判全部 stub
（不触外网、不跑真实回测）。覆盖 08 号文档 QRE-SAAS-NL-A1 计划（DeepSeek 方向）：
1. 规则层三态：经典 MACD 金叉死叉 / EMA 等 pass；纯数字/符号/过短/乱码 reject；
   缺入场/缺出场/无领域语境（买房/买菜）review。
2. DeepSeek 裁判：复用 nl_compiler.call_llm（独立 system prompt），严格 JSON
   三分类 strategy/not_strategy/unclear；fenced/prose 容错解析；异常/结构错误
   降级规则层；不伪造置信度。
3. 端点契约：规则 reject=422 不可绕过；规则/裁判 review=422 nl_input_review 可
   force=true 继续；裁判只在 cache miss + 配额计数后运行（缓存命中零裁判、
   裁判拒绝也占配额、不编译不写缓存）；DB 故障回退路径同样先限流再裁判；
   A2/A3 缓存与限流不回归。
4. 页面：new.html/strategy.html 处理 review 与 reject；隐私 tip 说明 DeepSeek；
   无新增灰色小字。
"""

from __future__ import annotations

import json
import subprocess
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from quant_research_engine.gui.saas import create_saas_app
from quant_research_engine.gui.saas import nl_input_guard as guard

WORKER_TOKEN = "test-worker-token"
AUTH = {"X-User-Id": "1"}

VALID_YAML = (
    "experiment:\n  name: t\ndata:\n  market_fields: [close]\n"
    "signal:\n  entry: close > 0\n  exit: close < 0\n"
    "evaluation:\n  forward_return_horizons: [1, 3, 5, 10, 20]\n  quantiles: 5\n"
    "holding:\n  max_holding_days: 20\n"
)
LLM_ENV = {
    "QRE_NL_LLM_BASE_URL": "https://llm.test",
    "QRE_NL_LLM_API_KEY": "k",
    "QRE_NL_LLM_MODEL": "m",
}


def _psql(db: str, *args: str) -> None:
    subprocess.run(
        ["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def saas_db():
    db_name = f"qre_nl_guard_{uuid.uuid4().hex[:12]}"
    _psql("postgres", "-c", f"CREATE DATABASE {db_name}")
    _psql(db_name, "-f", "deploy/saas/cloud_schema.sql")
    yield db_name
    _psql("postgres", "-c", f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")


@pytest.fixture()
def app(saas_db):
    app = create_saas_app()
    app.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
    app.config["SAAS_WORKER_TOKEN"] = WORKER_TOKEN
    app.config["SAAS_DEV_AUTH"] = "1"
    app.config["SAAS_AUTH_CHANNEL"] = "stub"
    yield app
    engine = app.extensions.get("saas_engine")
    if engine is not None:
        engine.dispose()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _clean(app, monkeypatch):
    for key in ("QRE_NL_LLM_BASE_URL", "QRE_NL_LLM_API_KEY", "QRE_NL_LLM_MODEL",
                "QRE_GUEST_NL_COUNTER"):
        monkeypatch.delenv(key, raising=False)
    from quant_research_engine.gui.saas.app import _get_engine
    with _get_engine(app).begin() as conn:
        conn.execute(text("TRUNCATE results, jobs, strategies, users, sessions, sms_codes, "
                          "share_links, nl_rate_limits, nl_compile_cache, nl_compile_events "
                          "RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture()
def llm(monkeypatch):
    from quant_research_engine.gui import nl_compiler
    for key, value in LLM_ENV.items():
        monkeypatch.setenv(key, value)

    class _Stub:
        def __init__(self):
            self.calls: list[tuple[str, str | None]] = []
            self.exc: Exception | None = None
            self.yaml_text = VALID_YAML

        def __call__(self, description, config, **kw):
            self.calls.append((description, kw.get("system_prompt")))
            if self.exc is not None:
                raise self.exc
            return self.yaml_text

    stub = _Stub()
    monkeypatch.setattr(nl_compiler, "call_llm", stub)
    monkeypatch.setattr(nl_compiler, "_default_column_lookup", lambda db_url=None: None)
    return stub


def _engine(app):
    from quant_research_engine.gui.saas.app import _get_engine
    return _get_engine(app)


def _cache_rows(app):
    with _engine(app).connect() as conn:
        return conn.execute(text("SELECT count(*) FROM nl_compile_cache")).scalar_one()


def _quota_rows(app):
    with _engine(app).connect() as conn:
        return conn.execute(text("SELECT count(*) FROM nl_rate_limits")).scalar_one()


def _make_admin(app):
    with _engine(app).begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, phone, role) VALUES (9, 'pending_9', 'admin') "
                 "ON CONFLICT (id) DO UPDATE SET role = 'admin'"))


def _make_member(app, uid=1):
    with _engine(app).begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, phone, tier, role) VALUES (:i, :p, 'member', 'user') "
                 "ON CONFLICT (id) DO NOTHING"), {"i": uid, "p": f"pending_{uid}"})


def _referee_stub(monkeypatch, verdict):
    """把模块级 referee_classify 换为桩；返回调用记录列表。"""
    calls: list[str] = []

    def _fake(description, config, **kw):
        calls.append(description)
        return verdict

    monkeypatch.setattr(guard, "referee_classify", _fake)
    return calls


# ---------------------------------------------------------------- 规则层
class TestRuleCheck:
    @pytest.mark.parametrize("desc", [
        "MACD 金叉买入，死叉卖出",
        "MACD 金叉死叉策略",
        "macd golden cross buy, dead cross sell",
        "EMA 上穿 20 日均线时买入，下穿时卖出",
        "当 rsi 低于 30 时买入，高于 70 时卖出",
        "收盘价突破 20 日高点买入，跌破 10 日低点卖出",
        "金叉买死叉卖",
        "双均线策略：5 日均线上穿 20 日均线做多，下穿平仓",
        "布林带下轨买入，上轨卖出",
        "KDJ 低于 20 买入，高于 80 卖出",
        "网格交易，每跌 2% 买一格，每涨 2% 卖一格",
        "收盘价高于 10 元买入，跌破 20 日均线卖出",
        "连续 3 天上涨后买入，连续 2 天下跌后卖出",
        "开盘价高于昨日收盘价 2% 买入，尾盘 14:50 卖出",
        "换手率超过 10% 且涨幅超过 5% 时买入，换手率低于 2% 时卖出",
        "估值低且基本面改善时买入，估值过高时卖出",
    ])
    def test_classic_inputs_pass(self, desc):
        assert guard.rule_check(desc)["decision"] == "pass", desc

    @pytest.mark.parametrize("desc", [
        "123456",
        "20240101",
        "！！！！？？",
        "🙂🙂🙂🙂🙂🙂",
        "?????",
        "abc",
        "买",
        "asdfghjkl",
        "今天天气不错啊哈哈哈",
    ])
    def test_gibberish_rejected(self, desc):
        r = guard.rule_check(desc)
        assert r["decision"] == "reject", (desc, r)
        assert r["reasons"] and r["examples"]

    @pytest.mark.parametrize("desc,missing", [
        ("当 rsi 低于 30 时买入", ["exit"]),
        ("跌破 10 日低点就卖出", ["entry"]),
        ("帮我写一个能赚钱的量化交易策略，越详细越好，最好带上参数说明和风险控制的完整方案，谢谢", ["entry", "exit"]),
    ])
    def test_missing_semantics_review(self, desc, missing):
        r = guard.rule_check(desc)
        assert r["decision"] == "review", (desc, r)
        assert r["missing"] == missing, (desc, r)

    @pytest.mark.parametrize("desc", [
        "我想买房，之后卖房",
        "今天买菜后卖给邻居",
        "买一张机票然后卖掉",
        "买入一些水果再卖出去",
        "buy a house and sell it later",
    ])
    def test_generic_buy_sell_requires_domain_context(self, desc):
        r = guard.rule_check(desc)
        assert r["decision"] != "pass", (desc, r)
        if r["decision"] == "review":
            assert any("语境" in x for x in r["reasons"]), r

    def test_no_trading_words_long_text_review(self):
        desc = ("这是一段没有任何交易术语的长文本， simply talking about the weather "
                "and what we had for lunch today, plus some movies worth watching")
        assert guard.rule_check(desc)["decision"] == "review"


# ---------------------------------------------------------------- DeepSeek 裁判
class TestRefereeClassify:
    CFG = {"base_url": "https://llm.test", "api_key": "k", "model": "m"}

    def test_uses_independent_referee_prompt(self):
        seen = {}

        def _fake(description, config, **kw):
            seen.update({"description": description, "system_prompt": kw.get("system_prompt")})
            return '{"label":"strategy"}'

        out = guard.referee_classify("MACD 金叉买入，死叉卖出", self.CFG, call_llm_fn=_fake)
        assert out == {"ok": True, "label": "strategy"}
        prompt = seen["system_prompt"]
        assert prompt and "分类裁判" in prompt
        assert "strategy" in prompt and "not_strategy" in prompt and "unclear" in prompt
        # 裁判 prompt 与编译 prompt 必须不同（独立裁判）
        from quant_research_engine.gui import nl_compiler
        assert prompt != nl_compiler.build_system_prompt()

    @pytest.mark.parametrize("raw,label", [
        ('{"label":"strategy"}', "strategy"),
        ('```json\n{"label":"not_strategy"}\n```', "not_strategy"),
        ('```\n{"label":"unclear"}\n```', "unclear"),
        ('结果是：{"label":"strategy"}，请查阅', "strategy"),
        ('{"label":"strategy","reason":"..."}', "strategy"),
    ])
    def test_robust_json_parsing(self, raw, label):
        out = guard.referee_classify("任意文本", self.CFG, call_llm_fn=lambda d, c, **kw: raw)
        assert out == {"ok": True, "label": label}, (raw, out)

    @pytest.mark.parametrize("raw", [
        "完全不是JSON",
        '{"label":"billing"}',
        '{"result":"strategy"}',
        "",
    ])
    def test_bad_structure_degrades(self, raw):
        out = guard.referee_classify("任意文本", self.CFG, call_llm_fn=lambda d, c, **kw: raw)
        assert out["ok"] is False and out["status"] == "bad_structure", (raw, out)

    def test_llm_error_degrades(self):
        def _boom(d, c, **kw):
            raise RuntimeError("LLM 响应格式异常")

        out = guard.referee_classify("任意文本", self.CFG, call_llm_fn=_boom)
        assert out["ok"] is False and out["status"] == "llm_error"

    def test_build_referee_none_without_config(self, monkeypatch):
        for key in LLM_ENV:
            monkeypatch.delenv(key, raising=False)
        from quant_research_engine.gui import nl_compiler
        assert nl_compiler.nl_config() is None
        assert guard.build_referee(None) is None


# ---------------------------------------------------------------- 组合决策
class TestEvaluateInput:
    def test_rule_reject_short_circuits_referee(self):
        calls = []
        out = guard.evaluate_input(
            "123456",
            referee=lambda d: (calls.append(d), {"ok": True, "label": "strategy"})[1])
        assert out["decision"] == "reject" and calls == []

    def test_referee_strategy_passes(self):
        out = guard.evaluate_input("MACD 金叉买入，死叉卖出",
                                   referee=lambda d: {"ok": True, "label": "strategy"})
        assert out["decision"] == "pass"
        assert out["referee"]["label"] == "strategy"

    @pytest.mark.parametrize("label", ["not_strategy", "unclear"])
    def test_referee_negative_upgrades_to_review(self, label):
        out = guard.evaluate_input("MACD 金叉买入，死叉卖出",
                                   referee=lambda d: {"ok": True, "label": label})
        assert out["decision"] == "review" and out["rule"] == "pass"
        assert any("DeepSeek" in r or "校验" in r for r in out["reasons"])

    @pytest.mark.parametrize("failure", [
        {"ok": False, "status": "llm_error"},
        {"ok": False, "status": "bad_structure"},
    ])
    def test_referee_failure_degrades_to_rule(self, failure):
        out = guard.evaluate_input("MACD 金叉买入，死叉卖出", referee=lambda d: failure)
        assert out["decision"] == "pass"  # 规则层放行，不因裁判故障阻挡
        assert out["referee"]["status"] == failure["status"]

    def test_referee_none_means_not_configured(self):
        out = guard.evaluate_input("MACD 金叉买入，死叉卖出", referee=None)
        assert out["decision"] == "pass" and out["referee"] is None


# ---------------------------------------------------------------- 端点契约
class TestCompileEndpointGuard:
    def test_reject_422_not_bypassable(self, client, app, llm):
        resp = client.post("/api/saas/nl/compile", json={"description": "123456"})
        assert resp.status_code == 422
        body = resp.get_json()
        assert body["code"] == "nl_input_rejected" and body["reasons"] and body["examples"]
        resp2 = client.post("/api/saas/nl/compile",
                            json={"description": "123456", "force": True})
        assert resp2.status_code == 422 and resp2.get_json()["code"] == "nl_input_rejected"
        assert llm.calls == [] and _cache_rows(app) == 0 and _quota_rows(app) == 0

    def test_rule_review_422_then_force(self, client, app, llm):
        resp = client.post("/api/saas/nl/compile", json={"description": "当 rsi 低于 30 时买入"})
        assert resp.status_code == 422
        body = resp.get_json()
        assert body["code"] == "nl_input_review" and "exit" in body["missing"]
        assert llm.calls == [] and _cache_rows(app) == 0 and _quota_rows(app) == 0
        ok = client.post("/api/saas/nl/compile",
                         json={"description": "当 rsi 低于 30 时买入", "force": True})
        assert ok.status_code == 200 and ok.get_json()["ok"] is True
        assert [d for d, _ in llm.calls] == ["当 rsi 低于 30 时买入"]

    def test_cache_hit_zero_referee(self, client, app, llm, monkeypatch):
        """缓存命中不得调用裁判（成本控制）。"""
        calls = _referee_stub(monkeypatch, {"ok": True, "label": "strategy"})
        r1 = client.post("/api/saas/nl/compile", json={"description": "MACD 金叉买入，死叉卖出"})
        assert r1.status_code == 200 and r1.get_json()["cache_hit"] is False
        assert calls == ["MACD 金叉买入，死叉卖出"]
        r2 = client.post("/api/saas/nl/compile", json={"description": "MACD 金叉买入，死叉卖出"})
        assert r2.status_code == 200 and r2.get_json()["cache_hit"] is True
        assert calls == ["MACD 金叉买入，死叉卖出"]  # 命中未再裁判
        assert llm.calls == [("MACD 金叉买入，死叉卖出", None)]

    def test_referee_review_blocks_but_consumes_quota(self, client, app, llm, monkeypatch):
        """裁判认为非策略/不明确 → 422 review；配额已计、不编译、不写缓存。"""
        desc = "收盘价大于 10 元买入，小于 8 元卖出"
        _referee_stub(monkeypatch, {"ok": True, "label": "not_strategy"})
        resp = client.post("/api/saas/nl/compile", json={"description": desc})
        assert resp.status_code == 422
        body = resp.get_json()
        assert body["code"] == "nl_input_review" and body["reasons"]
        assert llm.calls == [] and _cache_rows(app) == 0
        assert _quota_rows(app) == 1, "裁判拒绝也占一次配额（防免费刷 token）"
        # force 后编译成功（force 不再裁判）
        ok = client.post("/api/saas/nl/compile", json={"description": desc, "force": True})
        assert ok.status_code == 200 and ok.get_json()["ok"] is True
        assert llm.calls == [(desc, None)]

    def test_referee_unclear_blocks(self, client, app, llm, monkeypatch):
        _referee_stub(monkeypatch, {"ok": True, "label": "unclear"})
        resp = client.post("/api/saas/nl/compile", json={"description": "MACD 金叉买入，死叉卖出"})
        assert resp.status_code == 422 and resp.get_json()["code"] == "nl_input_review"
        assert llm.calls == [] and _quota_rows(app) == 1

    def test_referee_failure_degrades(self, client, app, llm, monkeypatch):
        _referee_stub(monkeypatch, {"ok": False, "status": "llm_error"})
        resp = client.post("/api/saas/nl/compile", json={"description": "MACD 金叉买入，死叉卖出"})
        assert resp.status_code == 200 and resp.get_json()["ok"] is True
        assert _quota_rows(app) == 1

    def test_admin_also_refereed(self, client, app, llm, monkeypatch):
        """Required Fix：删除 admin 豁免——管理员不限配额，但与会员一样经过裁判。"""
        _make_admin(app)
        calls = _referee_stub(monkeypatch, {"ok": True, "label": "not_strategy"})
        resp = client.post("/api/saas/nl/compile",
                           json={"description": "MACD 金叉买入，死叉卖出"},
                           headers={"X-User-Id": "9"})
        assert resp.status_code == 422 and resp.get_json()["code"] == "nl_input_review"
        assert calls == ["MACD 金叉买入，死叉卖出"]
        # admin 不限配额：连续裁判拒绝不触发限流（配额口径不变）
        resp2 = client.post("/api/saas/nl/compile",
                            json={"description": "MACD 金叉买入，死叉卖出"},
                            headers={"X-User-Id": "9"})
        assert resp2.status_code == 422
        # force 确认后编译成功（admin 同样可 force）
        ok = client.post("/api/saas/nl/compile",
                         json={"description": "MACD 金叉买入，死叉卖出", "force": True},
                         headers={"X-User-Id": "9"})
        assert ok.status_code == 200 and ok.get_json()["ok"] is True

    def test_db_fallback_still_referees(self, client, app, llm, monkeypatch, tmp_path):
        """DB 故障回退路径：先既有文件限流，再裁判，再编译。
        force=true 与正常路径语义一致——跳过裁判直接编译（规则硬拒仍在最前）。"""
        from quant_research_engine.gui.saas import nl_compile_support as nls

        def _boom(engine):
            raise SQLAlchemyError("db down")

        monkeypatch.setattr(nls, "ensure_nl_tables", _boom)
        monkeypatch.setenv("QRE_GUEST_NL_COUNTER", str(tmp_path / "nl-counter.json"))
        calls = _referee_stub(monkeypatch, {"ok": True, "label": "strategy"})
        resp = client.post("/api/saas/nl/compile", json={"description": "MACD 金叉买入，死叉卖出"})
        assert resp.status_code == 200 and resp.get_json()["ok"] is True
        assert calls == ["MACD 金叉买入，死叉卖出"]
        # 裁判拒绝时同样拦截且不编译
        calls = _referee_stub(monkeypatch, {"ok": True, "label": "not_strategy"})
        resp2 = client.post("/api/saas/nl/compile", json={"description": "RSI 低于 30 买入，高于 70 卖出"})
        assert resp2.status_code == 422 and resp2.get_json()["code"] == "nl_input_review"
        assert calls == ["RSI 低于 30 买入，高于 70 卖出"]
        assert [d for d, _ in llm.calls] == ["MACD 金叉买入，死叉卖出"]
        # Required Fix：DB 故障 + force=true 必须跳过裁判并进入编译（与正常路径一致）
        calls = _referee_stub(monkeypatch, {"ok": True, "label": "not_strategy"})
        resp3 = client.post("/api/saas/nl/compile",
                            json={"description": "KDJ 低于 20 买入，高于 80 卖出", "force": True})
        assert resp3.status_code == 200 and resp3.get_json()["ok"] is True
        assert calls == [], "force=true 在 DB 回退路径不得再被裁判拦截"
        # 规则硬拒在 force 下仍不可绕过（回退路径同样最前）
        resp4 = client.post("/api/saas/nl/compile",
                            json={"description": "123456", "force": True})
        assert resp4.status_code == 422 and resp4.get_json()["code"] == "nl_input_rejected"

    def test_guard_runs_before_cache(self, client, app, llm, monkeypatch):
        _referee_stub(monkeypatch, {"ok": True, "label": "strategy"})
        r1 = client.post("/api/saas/nl/compile", json={"description": "跌破 10 日低点就卖出"})
        assert r1.status_code == 422 and r1.get_json()["code"] == "nl_input_review"
        assert _cache_rows(app) == 0
        r2 = client.post("/api/saas/nl/compile",
                         json={"description": "跌破 10 日低点就卖出", "force": True})
        assert r2.status_code == 200 and r2.get_json()["cache_hit"] is False
        r3 = client.post("/api/saas/nl/compile", json={"description": "跌破 10 日低点就卖出"})
        assert r3.status_code == 422 and r3.get_json()["code"] == "nl_input_review"
        r4 = client.post("/api/saas/nl/compile",
                         json={"description": "跌破 10 日低点就卖出", "force": True})
        assert r4.status_code == 200 and r4.get_json()["cache_hit"] is True
        assert llm.calls == [("跌破 10 日低点就卖出", None)]

    def test_guest_quota_not_consumed_by_rule_guard(self, client, app, llm):
        for _ in range(10):
            assert client.post("/api/saas/nl/compile",
                               json={"description": "123456"}).status_code == 422
        ok = client.post("/api/saas/nl/compile", json={"description": "MACD 金叉买入，死叉卖出"})
        assert ok.status_code == 200

    def test_force_string_not_truthy(self, client, app, llm):
        r1 = client.post("/api/saas/nl/compile",
                         json={"description": "跌破 10 日低点就卖出", "force": "false"})
        assert r1.status_code == 422 and r1.get_json()["code"] == "nl_input_review"
        r2 = client.post("/api/saas/nl/compile",
                         json={"description": "跌破 10 日低点就卖出", "force": "true"})
        assert r2.status_code == 422 and r2.get_json()["code"] == "nl_input_review"


# ---------------------------------------------------------------- 页面
class TestPages:
    def test_new_page_guard_ui(self, client):
        html = client.get("/saas/new").get_data(as_text=True)
        assert 'id="nl-review-modal"' in html and 'id="nl-review-yes"' in html
        assert "nl_input_review" in html and "nl_input_rejected" in html
        assert "force" in html
        assert 'role="dialog"' in html and 'aria-modal="true"' in html
        assert 'aria-labelledby="nl-review-title"' in html and 'id="nl-review-title"' in html
        # 隐私说明：DeepSeek 用于校验与编译（tip-trigger，无灰色小字）
        assert "tip-trigger" in html and "DeepSeek" in html
        assert "你输入的描述会发送给 DeepSeek" in html

    def test_strategy_page_guard_ui(self, client):
        html = client.get("/saas/strategies/1").get_data(as_text=True)
        assert "nl_input_review" in html and "nl_input_rejected" in html
        assert "sd-nl-review" in html and "force" in html
        assert "tip-trigger" in html and "DeepSeek" in html
        assert "重新编译会把描述发送给 DeepSeek" in html

    def test_new_page_no_new_grey_notes(self, client):
        html = client.get("/saas/new").get_data(as_text=True)
        start = html.find('id="nl-review-modal"')
        assert start > 0
        end = html.find("自选因子三栏弹窗选择器", start)
        assert end > start
        assert 'class="opt"' not in html[start:end], "新增区块不得引入灰色小字"
