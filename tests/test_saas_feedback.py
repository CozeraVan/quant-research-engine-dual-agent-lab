"""QRE-SAAS-FEEDBACK-FACTOR-REQ 测试（真实本地 PG 临时库）。

覆盖：意见反馈（登录限定提交 / 校验 / 每日上限 / 本人列表 / 管理台只读列表
三态权限）、申请新因子扩展字段（formula/purpose 落库与透出）、新页面路由、
全页面统一侧边栏入口与禁链纪律、new.html 缺因子弹层跳转与向导兜底校验。
fixture 复制 test_gui_saas_console.py 的临时库模式（TRUNCATE 列表加 feedback）。
"""

from __future__ import annotations

import subprocess
import uuid

import pytest
from sqlalchemy import text

from quant_research_engine.gui.saas import create_saas_app

WORKER_TOKEN = "test-worker-token"
AUTH = {"X-User-Id": "1"}      # dev 后门用户
AUTH2 = {"X-User-Id": "2"}


def _psql(db: str, *args: str) -> None:
    subprocess.run(
        ["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def saas_db():
    db_name = f"qre_saas_test_{uuid.uuid4().hex[:12]}"
    _psql("postgres", "-c", f"CREATE DATABASE {db_name}")
    subprocess.run(
        ["psql", f"postgresql:///{db_name}", "-v", "ON_ERROR_STOP=1",
         "-f", "deploy/saas/cloud_schema.sql"],
        check=True, capture_output=True, text=True,
    )
    yield db_name
    _psql("postgres", "-c", f"DROP DATABASE IF EXISTS {db_name}")


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
def _clean(app):
    from quant_research_engine.gui.saas.app import _get_engine
    engine = _get_engine(app)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE results, jobs, strategies, users, sessions, sms_codes, "
                          "factor_requests, workers, feedback RESTART IDENTITY CASCADE"))


def _make_admin(app):
    engine = app.extensions["saas_engine"]
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, phone, role) VALUES (9, 'pending_9', 'admin') "
                 "ON CONFLICT (id) DO UPDATE SET role = 'admin'")
        )


class TestFeedbackApi:
    def test_submit_ok_and_own_list(self, client):
        resp = client.post("/api/saas/feedback",
                           json={"content": "希望支持分钟级回测", "page": "/saas/new",
                                 "contact": "u@example.com"}, headers=AUTH)
        assert resp.status_code == 200 and resp.get_json()["ok"]
        lst = client.get("/api/saas/feedback", headers=AUTH).get_json()["feedback"]
        assert len(lst) == 1
        assert lst[0]["content"] == "希望支持分钟级回测"
        assert lst[0]["page"] == "/saas/new"

    def test_guest_rejected_401(self, client):
        # 决策：仅登录用户可提交（游客不开放，见 06 决策日志）
        resp = client.post("/api/saas/feedback", json={"content": "x"})
        assert resp.status_code == 401
        assert "登录" in resp.get_json()["error"]

    def test_empty_or_oversize_400(self, client):
        assert client.post("/api/saas/feedback", json={"content": "  "}, headers=AUTH).status_code == 400
        assert client.post("/api/saas/feedback", json={}, headers=AUTH).status_code == 400
        resp = client.post("/api/saas/feedback", json={"content": "x" * 2001}, headers=AUTH)
        assert resp.status_code == 400

    def test_daily_limit_429(self, client):
        for i in range(20):
            r = client.post("/api/saas/feedback", json={"content": f"fb {i}"}, headers=AUTH)
            assert r.status_code == 200
        over = client.post("/api/saas/feedback", json={"content": "too many"}, headers=AUTH)
        assert over.status_code == 429

    def test_isolated_by_user(self, client):
        client.post("/api/saas/feedback", json={"content": "mine"}, headers=AUTH)
        other = client.get("/api/saas/feedback", headers=AUTH2).get_json()["feedback"]
        assert other == []


class TestConsoleFeedback:
    def test_permission_tri_state(self, client, app):
        assert client.get("/api/saas/console/feedback").status_code == 401
        client.post("/api/saas/feedback", json={"content": "页面按钮不好找"}, headers=AUTH)
        assert client.get("/api/saas/console/feedback", headers=AUTH).status_code == 403
        _make_admin(app)
        resp = client.get("/api/saas/console/feedback", headers={"X-User-Id": "9"})
        assert resp.status_code == 200
        rows = resp.get_json()["feedback"]
        assert len(rows) == 1 and rows[0]["content"] == "页面按钮不好找"

    def test_console_page_has_feedback_tab(self, client):
        html = client.get("/saas/console").get_data(as_text=True)
        assert 'data-tab="feedback"' in html and 'id="pane-feedback"' in html
        assert "/api/saas/console/feedback" in html


class TestFactorRequestExtended:
    def test_formula_purpose_roundtrip(self, client, app):
        resp = client.post("/api/saas/factor-requests",
                           json={"factors": ["my_factor_1"], "formula": "(a-b)/c",
                                 "purpose": "动量反转策略", "strategy_name": "s1"}, headers=AUTH)
        assert resp.status_code == 200
        mine = client.get("/api/saas/factor-requests", headers=AUTH).get_json()["requests"]
        assert mine[0]["formula"] == "(a-b)/c" and mine[0]["purpose"] == "动量反转策略"
        # 管理台审核队列透出公式/用途
        _make_admin(app)
        rows = client.get("/api/saas/console/factor-requests",
                          headers={"X-User-Id": "9"}).get_json()["requests"]
        assert rows[0]["formula"] == "(a-b)/c" and rows[0]["purpose"] == "动量反转策略"
        # 既有审核流转不受影响
        rev = client.post(f"/api/saas/console/factor-requests/{rows[0]['id']}/review",
                          json={"action": "approve"}, headers={"X-User-Id": "9"})
        assert rev.status_code == 200 and rev.get_json()["status"] == "approved"

    def test_old_payload_still_works(self, client):
        # 兼容旧载荷（无 formula/purpose，缺因子弹层的快捷提交）
        resp = client.post("/api/saas/factor-requests",
                           json={"factors": ["legacy_x"]}, headers=AUTH)
        assert resp.status_code == 200
        mine = client.get("/api/saas/factor-requests", headers=AUTH).get_json()["requests"]
        assert mine[0]["formula"] is None and mine[0]["purpose"] is None


class TestNewPagesAndSidebar:
    def test_feedback_page(self, client):
        resp = client.get("/saas/feedback")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'id="fb-content"' in html and 'id="fb-submit"' in html
        assert "/api/saas/feedback" in html and "意见反馈" in html

    def test_factor_request_page(self, client):
        resp = client.get("/saas/factor-request")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'id="fr-names"' in html and 'id="fr-formula"' in html and 'id="fr-purpose"' in html
        assert "/api/saas/factor-requests" in html and "申请新因子" in html
        # 缺因子弹层跳转预填
        assert "q.get('factors')" in html

    @pytest.mark.parametrize("page", ["/saas/login", "/saas/", "/saas/new", "/saas/jobs/1",
                                      "/saas/feedback", "/saas/factor-request"])
    def test_sidebar_on_all_pages(self, client, page):
        html = client.get(page).get_data(as_text=True)
        assert 'class="sidenav"' in html
        assert 'href="/saas/feedback"' in html and 'href="/saas/factor-request"' in html
        assert "意见反馈" in html and "申请新因子" in html

    @pytest.mark.parametrize("page", ["/saas/feedback", "/saas/factor-request"])
    def test_no_banned_links_on_new_pages(self, client, page):
        html = client.get(page).get_data(as_text=True)
        for banned in ("/admin", "factor-admin", "factor-create", "8080", "8081"):
            assert banned not in html, f"{page} 含禁链 {banned}"


class TestMissingFactorInterception:
    def test_new_page_modal_jump_button(self, client):
        html = client.get("/saas/new").get_data(as_text=True)
        # 弹层提示文案（需求指定措辞）+ 跳转申请页按钮
        assert "当前数据库中不含此因子" in html
        assert 'id="btn-factor-goto"' in html and "/saas/factor-request" in html
        # 保留快捷提交
        assert 'id="btn-factor-submit"' in html

    def test_wizard_fallback_validation(self, client):
        html = client.get("/saas/new").get_data(as_text=True)
        assert "unknownYamlFactors" in html and "yamlFactorAliases" in html
        assert "factor_fields" in html
