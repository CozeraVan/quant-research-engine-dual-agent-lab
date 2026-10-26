"""QRE-SAAS-PUBLIC-BETA-OPS：公测运营指标、反馈分类闭环与 NL 编译事件。

真实本地 PG 临时库（deploy/saas/cloud_schema.sql），LLM 层 monkeypatch
nl_compiler.call_llm（不触真实 DeepSeek、不跑真实回测）。覆盖 08 号文档
QRE-SAAS-PUBLIC-BETA-OPS 计划 §4：
1. NL 编译事件：成功/失败/缓存命中/scope；超限拒绝不记事件；事件表不存
   策略文本、API key、原始 IP（列集合锁定）。
2. console ops：鉴权三态、窗口校验、成功率/排队/失败分组/转化/反馈计数
   口径与空数据 null（不编造历史）。
3. 反馈分类与处理状态：allowlist、缺省、本人列表透出、管理台筛选与状态
   流转权限矩阵；既有隔离/每日上限/鉴权不回归。
4. 页面标记：console 公测运营 tab 与反馈筛选、feedback.html 类型控件。
"""

from __future__ import annotations

import json
import subprocess
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from quant_research_engine.gui.saas import create_saas_app

WORKER_TOKEN = "test-worker-token"
AUTH = {"X-User-Id": "1"}      # dev 后门用户（会员）
AUTH2 = {"X-User-Id": "2"}
ADMIN = {"X-User-Id": "9"}

VALID_YAML = (
    "experiment:\n  name: t\ndata:\n  market_fields: [close]\n"
    "signal:\n  entry: close > 0\n"
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
    db_name = f"qre_pub_ops_{uuid.uuid4().hex[:12]}"
    _psql("postgres", "-c", f"CREATE DATABASE {db_name}")
    _psql(db_name, "-f", "deploy/saas/cloud_schema.sql")
    # schema 幂等：二次 apply 不报错（feedback 两列 + nl_compile_events）
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
def _referee_pass(monkeypatch):
    """QRE-SAAS-NL-A1：本文件验证运营事件/配额口径，不关心裁判——桩成 strategy
    放行（裁判自身行为由 tests/test_nl_input_guard.py 覆盖）。"""
    from quant_research_engine.gui.saas import nl_input_guard
    monkeypatch.setattr(nl_input_guard, "referee_classify",
                        lambda d, c, **kw: {"ok": True, "label": "strategy"})


@pytest.fixture(autouse=True)
def _clean(app):
    from quant_research_engine.gui.saas.app import _get_engine
    with _get_engine(app).begin() as conn:
        conn.execute(text("TRUNCATE results, jobs, strategies, users, sessions, sms_codes, "
                          "factor_requests, workers, feedback, share_links, nl_rate_limits, "
                          "nl_compile_cache, nl_compile_events RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture()
def llm(monkeypatch):
    from quant_research_engine.gui import nl_compiler
    for key, value in LLM_ENV.items():
        monkeypatch.setenv(key, value)

    class _Stub:
        def __init__(self):
            self.calls: list[str] = []
            self.exc: Exception | None = None
            self.yaml_text = VALID_YAML

        def __call__(self, description, config, **kw):
            self.calls.append(description)
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


def _make_admin(app):
    with _engine(app).begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, phone, role) VALUES (9, 'pending_9', 'admin') "
                 "ON CONFLICT (id) DO UPDATE SET role = 'admin'")
        )


def _make_member(app, uid=1):
    with _engine(app).begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, phone, tier, role) VALUES (:i, :p, 'member', 'user') "
                 "ON CONFLICT (id) DO NOTHING"), {"i": uid, "p": f"pending_{uid}"})


def _nl_events(app):
    with _engine(app).connect() as conn:
        rows = conn.execute(
            text("SELECT ok, cache_hit, error_class, scope FROM nl_compile_events "
                 "ORDER BY id")).mappings().all()
    return [dict(r) for r in rows]


class TestNlCompileEvents:
    def test_success_then_cache_hit_events(self, client, app, llm):
        r1 = client.post("/api/saas/nl/compile", json={"description": "MACD 金叉买入，死叉卖出"})
        assert r1.status_code == 200 and r1.get_json()["cache_hit"] is False
        r2 = client.post("/api/saas/nl/compile", json={"description": "MACD  金叉买入，死叉卖出 "})
        assert r2.status_code == 200 and r2.get_json()["cache_hit"] is True
        assert llm.calls == ["MACD 金叉买入，死叉卖出"]  # 命中未再调用 LLM
        events = _nl_events(app)
        assert events == [
            {"ok": True, "cache_hit": False, "error_class": None, "scope": "guest"},
            {"ok": True, "cache_hit": True, "error_class": None, "scope": "guest"},
        ]

    def test_failure_event_class(self, client, app, llm):
        llm.exc = RuntimeError("boom")
        resp = client.post("/api/saas/nl/compile", json={"description": "MACD 金叉买入，死叉卖出"})
        assert resp.status_code == 200 and resp.get_json()["ok"] is False
        events = _nl_events(app)
        assert len(events) == 1
        assert events[0]["ok"] is False and events[0]["cache_hit"] is False
        assert events[0]["error_class"] == "llm_error"

    def test_member_scope(self, client, app, llm):
        _make_member(app)
        resp = client.post("/api/saas/nl/compile", json={"description": "RSI 低于 30 买入，高于 70 卖出"},
                           headers=AUTH)
        assert resp.status_code == 200
        events = _nl_events(app)
        assert events[0]["scope"] == "member"

    def test_rate_limited_not_recorded(self, client, app, llm):
        # 游客 10 次编译机会：前 10 次各记 1 条事件，第 11 次 403 不记（不是编译尝试）
        for i in range(10):
            assert client.post("/api/saas/nl/compile",
                               json={"description": f"MACD 金叉买入，死叉卖出 游客{i}"}).status_code == 200
        over = client.post("/api/saas/nl/compile", json={"description": "MACD 金叉买入，死叉卖出 游客10"})
        assert over.status_code == 403 and over.get_json()["code"] == "guest_nl_limit"
        assert len(_nl_events(app)) == 10

    def test_no_sensitive_columns(self, app):
        cols = {r[0] for r in _engine(app).connect().execute(
            text("SELECT column_name FROM information_schema.columns "
                 "WHERE table_name = 'nl_compile_events'"))}
        assert cols == {"id", "ok", "cache_hit", "error_class", "scope", "created_at"}
        for banned in ("description", "content", "api_key", "key", "ip", "guest_key",
                       "subject", "prompt"):
            assert banned not in cols


class TestConsoleOps:
    def _seed(self, app):
        """窗口内：3 full（2 completed 1 failed）+ 1 canceled + 1 smoke + 2 游客会话
        + 2 新用户 + 3 反馈（两类型两状态）+ 2 NL 事件（1 失败）。"""
        with _engine(app).begin() as conn:
            conn.execute(text("INSERT INTO users (id, phone, tier, role) "
                              "VALUES (1, 'a@x.com', 'member', 'user'), "
                              "(2, 'b@x.com', 'member', 'user') ON CONFLICT (id) DO NOTHING"))
            sid = conn.execute(text(
                "INSERT INTO strategies (user_id, name, yaml) VALUES (1, 's', 'y') RETURNING id"
            )).scalar_one()

            def job(status, kind="full", guest=None, error_class=None,
                    queue_s=10, run_s=100, created_offset_h=1):
                return conn.execute(text(
                    "INSERT INTO jobs (user_id, strategy_id, kind, status, params, guest_key, "
                    "error_class, created_at, started_at, finished_at) VALUES "
                    "(1, :sid, :kind, :st, '{}', :gk, :ec, "
                    "now() - :co * interval '1 hour', "
                    "now() - :co * interval '1 hour' + :q * interval '1 second', "
                    "now() - :co * interval '1 hour' + :q * interval '1 second' + :r * interval '1 second') "
                    "RETURNING id"),
                    {"sid": sid, "kind": kind, "st": status, "gk": guest,
                     "ec": error_class, "q": queue_s, "r": run_s,
                     "co": created_offset_h}).scalar_one()

            job("completed", queue_s=10, run_s=100)
            job("completed", queue_s=20, run_s=200)
            job("failed", error_class="engine_error", queue_s=30, run_s=50)
            job("canceled")  # 主动取消：不计入成功率分母
            job("completed", kind="smoke")  # 内部试算：不计入口径
            job("completed", guest="gk_a")
            job("completed", guest="gk_b")
            conn.execute(text("INSERT INTO feedback (user_id, content, category, status) "
                              "VALUES (1, '坏 bug', 'bug', 'open'), "
                              "(2, '建议', 'experience', 'done'), "
                              "(1, '再来', 'bug', 'doing')"))
            conn.execute(text("INSERT INTO nl_compile_events (ok, cache_hit, error_class, scope) "
                              "VALUES (true, true, NULL, 'member'), (false, false, 'llm_error', 'guest')"))

    def test_permission_tri_state(self, client, app):
        assert client.get("/api/saas/console/ops").status_code == 401
        _make_member(app)
        assert client.get("/api/saas/console/ops", headers=AUTH).status_code == 403
        _make_admin(app)
        assert client.get("/api/saas/console/ops", headers=ADMIN).status_code == 200

    def test_window_validation(self, client, app):
        _make_admin(app)
        resp = client.get("/api/saas/console/ops?window=bogus", headers=ADMIN)
        assert resp.status_code == 400

    def test_metrics_math(self, client, app):
        _make_admin(app)
        self._seed(app)
        ops = client.get("/api/saas/console/ops?window=today", headers=ADMIN).get_json()["ops"]
        bt = ops["backtest"]
        assert bt["total"] == 6          # 4 completed(2 会员+2 游客) + 1 failed + 1 canceled；smoke 不计
        assert bt["completed"] == 4 and bt["failed"] == 1
        assert abs(bt["success_rate"] - 4 / 5) < 1e-9
        assert bt["avg_queue_seconds"] == 15.0   # (10+20+30+10+10+10)/6（含 canceled）
        assert bt["avg_run_seconds"] == pytest.approx(108.3, abs=0.1)  # (100+200+50+100+100+100)/6
        assert bt["top_failures"][0] == {"error_class": "engine_error", "count": 1}
        nl = ops["nl"]
        assert nl["total"] == 2 and nl["ok"] == 1
        assert abs(nl["success_rate"] - 0.5) < 1e-9
        assert nl["cache_hits"] == 1
        assert nl["top_failures"] == [{"error_class": "llm_error", "count": 1}]
        assert nl["first_event_at"] is not None
        cv = ops["conversion"]
        assert cv["guest_sessions"] == 2
        assert cv["new_users"] >= 2  # 含管理员行（_make_admin 先建）
        # Required Fix 1：不展示未关联总量的比（可能 >100%，构成误导）
        assert cv["ratio"] is None
        assert cv["measurement"] == "unlinked"
        fb = ops["feedback"]
        assert fb["total"] == 3 and fb["open"] == 1
        assert fb["by_category"] == {"bug": 2, "experience": 1, "factor": 0, "other": 0}
        assert fb["by_status"] == {"open": 1, "doing": 1, "done": 1, "closed": 0}

    def test_empty_window_nulls(self, client, app):
        _make_admin(app)
        ops = client.get("/api/saas/console/ops?window=7d", headers=ADMIN).get_json()["ops"]
        assert ops["nl"]["success_rate"] is None and ops["nl"]["cache_hit_rate"] is None
        assert ops["nl"]["first_event_at"] is None
        assert ops["backtest"]["success_rate"] is None
        assert ops["backtest"]["avg_queue_seconds"] is None
        assert ops["conversion"]["ratio"] is None
        assert ops["feedback"]["total"] == 0

    def test_conversion_ratio_never_computed(self, client, app):
        """Required Fix 1：两边都有真实计数时也不得产出比率（无会话关联，
        new_users/guest_sessions 之比可超过 100%，是误导）。"""
        _make_admin(app)
        self._seed(app)
        ops = client.get("/api/saas/console/ops?window=today", headers=ADMIN).get_json()["ops"]
        cv = ops["conversion"]
        assert cv["guest_sessions"] >= 1 and cv["new_users"] >= 1
        assert cv["ratio"] is None
        assert cv["measurement"] == "unlinked"

    def test_window_all_includes_older_rows(self, client, app):
        _make_admin(app)
        with _engine(app).begin() as conn:
            conn.execute(text("INSERT INTO users (id, phone) VALUES (1, 'a@x.com') "
                              "ON CONFLICT (id) DO NOTHING"))
            sid = conn.execute(text(
                "INSERT INTO strategies (user_id, name, yaml) VALUES (1, 's', 'y') RETURNING id"
            )).scalar_one()
            conn.execute(text(
                "INSERT INTO jobs (user_id, strategy_id, kind, status, params, created_at, "
                "started_at, finished_at) VALUES (1, :sid, 'full', 'completed', '{}', "
                "now() - interval '400 days', now() - interval '400 days', "
                "now() - interval '400 days')"), {"sid": sid})
        today = client.get("/api/saas/console/ops?window=today", headers=ADMIN).get_json()["ops"]
        every = client.get("/api/saas/console/ops?window=all", headers=ADMIN).get_json()["ops"]
        assert today["backtest"]["total"] == 0
        assert every["backtest"]["total"] == 1 and every["backtest"]["completed"] == 1


class TestFeedbackCategoryStatus:
    def test_submit_category_roundtrip_and_default(self, client):
        resp = client.post("/api/saas/feedback",
                           json={"content": "按钮点不动", "category": "bug"}, headers=AUTH)
        assert resp.status_code == 200
        resp = client.post("/api/saas/feedback", json={"content": "随便说说"}, headers=AUTH)
        assert resp.status_code == 200
        rows = client.get("/api/saas/feedback", headers=AUTH).get_json()["feedback"]
        by_content = {r["content"]: r for r in rows}
        assert by_content["按钮点不动"]["category"] == "bug"
        assert by_content["按钮点不动"]["status"] == "open"
        assert by_content["随便说说"]["category"] == "other"

    def test_invalid_category_400(self, client):
        resp = client.post("/api/saas/feedback",
                           json={"content": "x", "category": "urgent"}, headers=AUTH)
        assert resp.status_code == 400

    def test_console_filters(self, client, app):
        _make_admin(app)
        client.post("/api/saas/feedback", json={"content": "b1", "category": "bug"}, headers=AUTH)
        client.post("/api/saas/feedback", json={"content": "e1", "category": "experience"}, headers=AUTH)
        rows = client.get("/api/saas/console/feedback?category=bug",
                          headers=ADMIN).get_json()["feedback"]
        assert [r["content"] for r in rows] == ["b1"]
        rows = client.get("/api/saas/console/feedback?category=bogus", headers=ADMIN)
        assert rows.status_code == 400
        rows = client.get("/api/saas/console/feedback?status=open",
                          headers=ADMIN).get_json()["feedback"]
        assert len(rows) == 2
        rows = client.get("/api/saas/console/feedback?status=done", headers=ADMIN)
        assert rows.status_code == 200 and rows.get_json()["feedback"] == []

    def test_status_flow(self, client, app):
        _make_admin(app)
        fid = client.post("/api/saas/feedback",
                          json={"content": "崩溃了", "category": "bug"},
                          headers=AUTH).get_json()["id"]
        # 权限矩阵
        assert client.post(f"/api/saas/console/feedback/{fid}/status",
                           json={"status": "doing"}).status_code == 401
        _make_member(app)
        assert client.post(f"/api/saas/console/feedback/{fid}/status",
                           json={"status": "doing"}, headers=AUTH).status_code == 403
        # admin 流转
        ok = client.post(f"/api/saas/console/feedback/{fid}/status",
                         json={"status": "doing"}, headers=ADMIN)
        assert ok.status_code == 200 and ok.get_json()["status"] == "doing"
        row = client.get("/api/saas/console/feedback", headers=ADMIN).get_json()["feedback"][0]
        assert row["status"] == "doing" and row["category"] == "bug"
        # 非法状态 / 不存在
        assert client.post(f"/api/saas/console/feedback/{fid}/status",
                           json={"status": "wontfix"}, headers=ADMIN).status_code == 400
        assert client.post("/api/saas/console/feedback/999999/status",
                           json={"status": "done"}, headers=ADMIN).status_code == 404
        # 用户本人列表可见处理状态（闭环可见）
        mine = client.get("/api/saas/feedback", headers=AUTH).get_json()["feedback"]
        assert mine[0]["status"] == "doing"

    def test_isolation_and_daily_limit_unchanged(self, client):
        client.post("/api/saas/feedback", json={"content": "mine"}, headers=AUTH)
        assert client.get("/api/saas/feedback", headers=AUTH2).get_json()["feedback"] == []
        for i in range(20):
            assert client.post("/api/saas/feedback", json={"content": f"fb {i}"},
                               headers=AUTH2).status_code == 200
        over = client.post("/api/saas/feedback", json={"content": "too many"}, headers=AUTH2)
        assert over.status_code == 429

    def test_console_page_markers(self, client):
        html = client.get("/saas/console").get_data(as_text=True)
        assert 'data-tab="ops"' in html and 'id="pane-ops"' in html
        assert "/api/saas/console/ops" in html
        assert 'id="ops-window"' in html and 'data-win="7d"' in html
        # 反馈筛选与状态流转
        assert 'id="feedback-filter"' in html and 'data-cat="bug"' in html
        assert 'data-st="doing"' in html
        assert "/api/saas/console/feedback/" in html and "/status" in html

    def test_feedback_page_markers(self, client):
        html = client.get("/saas/feedback").get_data(as_text=True)
        assert 'id="fb-category"' in html
        for value in ("bug", "experience", "factor", "other"):
            assert f'value="{value}"' in html


class TestOpsWindowBoundary:
    """Required Fix 2：today 窗口按 Asia/Shanghai 自然日（非 UTC 日）。"""

    def test_today_start_is_shanghai_midnight(self, monkeypatch):
        from quant_research_engine.gui.saas import ops_support
        # 上海 2026-10-26 00:30（= UTC 2026-10-25 16:30）
        fixed = datetime(2026, 10, 26, 0, 30, tzinfo=ops_support.SHANGHAI)
        monkeypatch.setattr(ops_support, "_now_shanghai", lambda: fixed)
        start = ops_support.window_start("today")
        assert start == datetime(2026, 10, 25, 16, 0, tzinfo=timezone.utc)
        # UTC 口径会取 10-25 00:00 UTC（上海 08:00），漏掉当日 00:00–08:00 共 8 小时
        assert start != datetime(2026, 10, 25, 0, 0, tzinfo=timezone.utc)

    def test_today_window_includes_shanghai_early_morning(self, client, app, monkeypatch):
        """上海当日 00:00–08:00 产生的任务必须计入 today（UTC 口径会漏）。"""
        from quant_research_engine.gui.saas import ops_support
        _make_admin(app)
        # 上海 2026-10-26 07:00 = UTC 2026-10-25 23:00
        with _engine(app).begin() as conn:
            conn.execute(text("INSERT INTO users (id, phone) VALUES (1, 'a@x.com') "
                              "ON CONFLICT (id) DO NOTHING"))
            sid = conn.execute(text(
                "INSERT INTO strategies (user_id, name, yaml) VALUES (1, 's', 'y') RETURNING id"
            )).scalar_one()
            conn.execute(text(
                "INSERT INTO jobs (user_id, strategy_id, kind, status, params, created_at, "
                "started_at, finished_at) VALUES (1, :sid, 'full', 'completed', '{}', "
                "'2026-10-25 23:00:00+00', '2026-10-25 23:00:00+00', "
                "'2026-10-25 23:02:00+00')"), {"sid": sid})
        # 当前时间固定为上海 2026-10-26 12:00
        monkeypatch.setattr(ops_support, "_now_shanghai",
                            lambda: datetime(2026, 10, 26, 12, 0, tzinfo=ops_support.SHANGHAI))
        ops = client.get("/api/saas/console/ops?window=today", headers=ADMIN).get_json()["ops"]
        assert ops["backtest"]["total"] == 1, "上海当日凌晨任务必须计入 today"
        assert ops["backtest"]["completed"] == 1
