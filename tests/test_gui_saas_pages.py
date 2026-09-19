"""QRE-SAAS-004 SaaS 前端页面测试。

页面路由 200 + 关键元素存在；/api/saas/nl/compile 与 /api/saas/factors
在 saas app 中可用（LLM 层 monkeypatch nl_compiler.call_llm 为固定 YAML，
与既有 test_gui_nl_compiler.py 的 stub 思路一致——不触真实 DeepSeek）。
"""

from __future__ import annotations

import subprocess
import uuid

import pytest

from quant_research_engine.gui.saas import create_saas_app

WORKER_TOKEN = "t"
VALID_YAML = (
    "experiment:\n  name: t\ndata:\n  market_fields: [close]\n"
    "signal:\n  entry: close > 0\n"
    "evaluation:\n  forward_return_horizons: [1, 3, 5]\n"
    "holding:\n  max_holding_days: 20\n"
)


def _psql(db: str, *args: str) -> None:
    subprocess.run(
        ["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def saas_db():
    db_name = f"qre_saas_pages_{uuid.uuid4().hex[:12]}"
    _psql("postgres", "-c", f"CREATE DATABASE {db_name}")
    _psql(db_name, "-f", "deploy/saas/cloud_schema.sql")
    yield db_name
    _psql("postgres", "-c", f"DROP DATABASE IF EXISTS {db_name}")


@pytest.fixture()
def client(saas_db):
    app = create_saas_app()
    app.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
    app.config["SAAS_WORKER_TOKEN"] = WORKER_TOKEN
    app.config["SAAS_DEV_AUTH"] = "1"
    app.config["SAAS_AUTH_CHANNEL"] = "stub"
    from sqlalchemy import text

    from quant_research_engine.gui.saas.app import _get_engine

    with _get_engine(app).begin() as conn:
        conn.execute(text("TRUNCATE results, jobs, strategies, users, sessions, sms_codes RESTART IDENTITY CASCADE"))
    yield app.test_client()
    engine = app.extensions.get("saas_engine")
    if engine is not None:
        engine.dispose()


AUTH = {"X-User-Id": "1"}  # dev 后门


class TestPages:
    def test_login_page(self, client):
        resp = client.get("/saas/login")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'id="login-target"' in html and 'id="login-code"' in html
        assert 'id="btn-send-code"' in html and 'id="btn-login"' in html
        assert 'name="viewport"' in html

    def test_dashboard_page(self, client):
        resp = client.get("/saas/")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'id="jobs-tbody"' in html and 'id="btn-new-job"' in html
        assert '排队中' in html or "STATUS_LABEL" in html

    def test_new_page(self, client):
        resp = client.get("/saas/new")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'id="tab-nl"' in html and 'id="tab-wizard"' in html
        assert 'id="nl-input"' in html and 'id="wz-factor"' in html
        assert 'id="btn-submit"' in html  # 单一「开始回测」（后台自动预检+提交）
        assert 'id="yaml-preview"' in html  # 策略代码预览（高级，默认折叠）

    def test_job_page(self, client):
        resp = client.get("/saas/jobs/1")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'id="chart-main"' in html and 'id="bench-bar"' in html  # 净值 vs 基准可切换
        assert 'id="job-badge"' in html and '/static/echarts.min.js' in html
        assert 'id="chart-tags"' in html and 'id="tag-rank"' in html  # 归因区块
        assert 'id="metric-strip"' in html and 'id="meta-chips"' in html

    def test_no_engineering_jargon(self, client):
        # 零术语原则：页面不得出现 沙箱/晋升/promote/试算 等内部词
        for page in ("/saas/", "/saas/new", "/saas/jobs/1"):
            html = client.get(page).get_data(as_text=True)
            for word in ("沙箱", "晋升", "promote", "试算"):
                assert word not in html, f"{page} 含术语 {word}"

    def test_static_echarts_served(self, client):
        resp = client.get("/static/echarts.min.js")
        assert resp.status_code == 200
        assert len(resp.data) > 100_000  # vendored echarts 复用，非占位


class TestSaasNlCompileRoute:
    def test_unauthorized_401(self, client):
        assert client.post("/api/saas/nl/compile", json={"description": "x"}).status_code == 401

    def test_empty_description_400(self, client):
        resp = client.post("/api/saas/nl/compile", json={"description": " "}, headers=AUTH)
        assert resp.status_code == 400

    def test_compile_success_with_stubbed_llm(self, client, monkeypatch):
        monkeypatch.setenv("QRE_NL_LLM_BASE_URL", "https://llm.test")
        monkeypatch.setenv("QRE_NL_LLM_API_KEY", "k")
        monkeypatch.setenv("QRE_NL_LLM_MODEL", "m")
        monkeypatch.setattr(
            "quant_research_engine.gui.nl_compiler.call_llm",
            lambda description, config, **kw: VALID_YAML,
        )
        monkeypatch.setattr(
            "quant_research_engine.gui.nl_compiler._default_column_lookup",
            lambda db_url=None: None,  # DB 不可用 → 跳过因子存在性检查
        )
        resp = client.post("/api/saas/nl/compile",
                           json={"description": "收盘价大于 0 买入"}, headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] and "entry" in data["yaml"]

    def test_not_configured_503(self, client, monkeypatch):
        for var in ("QRE_NL_LLM_BASE_URL", "QRE_NL_LLM_API_KEY", "QRE_NL_LLM_MODEL"):
            monkeypatch.delenv(var, raising=False)
        resp = client.post("/api/saas/nl/compile", json={"description": "x"}, headers=AUTH)
        assert resp.status_code == 503
        assert resp.get_json()["code"] == "not_configured"


class TestSaasFactorsRoute:
    def test_unauthorized_401(self, client):
        assert client.get("/api/saas/factors").status_code == 401

    def test_groups_shape(self, client, monkeypatch):
        monkeypatch.setattr(
            "quant_research_engine.gui.factor_wizard.load_factor_tables_columns",
            lambda db_url=None: {"stock_daily_momentum_close": ["rsi_14", "mom_10"]},
        )
        resp = client.get("/api/saas/factors", headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] and data["groups"]
        assert data["groups"][0]["group"] == "market"  # 首组行情字段
        assert any(g["label"] for g in data["groups"])


class TestFactorRequests:
    def test_submit_list_dedup(self, client):
        resp = client.post("/api/saas/factor-requests",
                           json={"strategy_name": "s1", "factors": ["rsi_99", "foo_1"]}, headers=AUTH)
        assert resp.status_code == 200 and resp.get_json()["status"] == "pending"
        # 24h 内同因子集合去重（顺序无关）
        dup = client.post("/api/saas/factor-requests",
                          json={"factors": ["foo_1", "rsi_99"]}, headers=AUTH)
        assert dup.status_code == 409
        # 不同集合可提交
        other = client.post("/api/saas/factor-requests", json={"factors": ["bar_2"]}, headers=AUTH)
        assert other.status_code == 200

        lst = client.get("/api/saas/factor-requests", headers=AUTH).get_json()["requests"]
        assert len(lst) == 2
        assert lst[0]["factors"] == ["bar_2"]  # 倒序
        assert lst[1]["status"] == "pending"

    def test_isolated_by_user(self, client):
        client.post("/api/saas/factor-requests", json={"factors": ["x_1"]}, headers=AUTH)
        other = client.get("/api/saas/factor-requests", headers={"X-User-Id": "2"}).get_json()
        assert other["requests"] == []

    def test_unauthorized_401(self, client):
        assert client.post("/api/saas/factor-requests", json={"factors": ["x"]}).status_code == 401
        assert client.get("/api/saas/factor-requests").status_code == 401

    def test_bad_payload_400(self, client):
        assert client.post("/api/saas/factor-requests", json={"factors": []}, headers=AUTH).status_code == 400
        assert client.post("/api/saas/factor-requests", json={}, headers=AUTH).status_code == 400


class TestNoAdminLinks:
    """需求 2：SaaS 页面不得出现指向内网管理端/未实现功能的链接。"""

    @pytest.mark.parametrize("page", ["/saas/login", "/saas/", "/saas/new", "/saas/jobs/1"])
    def test_no_admin_or_internal_links(self, client, page):
        html = client.get(page).get_data(as_text=True)
        for banned in ("/admin", "factor-admin", "factor-create", "8080", "8081"):
            assert banned not in html, f"{page} 含禁链 {banned}"

    def test_new_page_has_factor_modal(self, client):
        html = client.get("/saas/new").get_data(as_text=True)
        assert 'id="factor-modal"' in html and '提交因子需求' in html and '换个策略' in html

    def test_dashboard_has_factor_request_section(self, client):
        html = client.get("/saas/").get_data(as_text=True)
        assert 'id="factor-req-tbody"' in html and '我的因子申请' in html


class TestStubEcho:
    def test_echo_off_by_default(self, client):
        resp = client.post("/api/saas/auth/code", json={"target": "echo@example.com"})
        assert "dev_code" not in resp.get_json()

    def test_echo_on_returns_dev_code(self, saas_db, monkeypatch):
        app2 = create_saas_app()
        app2.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
        app2.config["SAAS_WORKER_TOKEN"] = WORKER_TOKEN
        app2.config["SAAS_AUTH_CHANNEL"] = "stub"
        app2.config["SAAS_STUB_ECHO"] = "1"
        c2 = app2.test_client()
        resp = c2.post("/api/saas/auth/code", json={"target": "echo2@example.com"})
        data = resp.get_json()
        assert data["ok"] and len(data["dev_code"]) == 6
        # dev_code 可直接登录
        login = c2.post("/api/saas/auth/login",
                        json={"target": "echo2@example.com", "code": data["dev_code"]})
        assert login.status_code == 200 and login.get_json()["token"]
        engine = app2.extensions.get("saas_engine")
        if engine is not None:
            engine.dispose()


class TestAuthBypass:
    """SAAS_AUTH_BYPASS=1（staging 专用，生产严禁）：免登录直用核心功能。"""

    @pytest.fixture()
    def bypass_client(self, saas_db):
        app2 = create_saas_app()
        app2.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
        app2.config["SAAS_WORKER_TOKEN"] = WORKER_TOKEN
        app2.config["SAAS_AUTH_BYPASS"] = "1"
        yield app2.test_client()
        engine = app2.extensions.get("saas_engine")
        if engine is not None:
            engine.dispose()

    def test_login_page_redirects(self, bypass_client):
        resp = bypass_client.get("/saas/login")
        assert resp.status_code == 302 and "/saas/" in resp.headers["Location"]

    def test_core_apis_without_token(self, bypass_client):
        # 无 token 直接建任务、查列表、查 me（自动建 staging@local 用户）
        created = bypass_client.post("/api/saas/jobs", json={"yaml": "x", "kind": "smoke"})
        assert created.status_code == 200
        me = bypass_client.get("/api/saas/me").get_json()["user"]
        assert me["email"] == "staging@local"
        jobs = bypass_client.get("/api/saas/jobs").get_json()["jobs"]
        assert jobs[0]["user_id"] == me["id"]

    def test_bypass_off_keeps_401(self, client):
        # 默认关（client fixture 未开 bypass）：维持 401
        assert client.get("/api/saas/me").status_code == 401
        assert client.post("/api/saas/jobs", json={"yaml": "x"}).status_code == 401


class TestResultsDataSource:
    """B3：回测记录/结果详情页数据源切到 B1/B2 的 /api/results 系列。"""

    def test_dashboard_uses_results_api(self, client):
        html = client.get("/saas/").get_data(as_text=True)
        assert "/api/results'" in html                      # 列表走 /api/results
        assert "/api/saas/jobs')" not in html              # 不再走旧 jobs 列表
        assert "job.job_id" in html                        # 新字段名
        assert "strategy_name" in html

    def test_job_page_uses_results_detail_apis(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        assert "/api/results/' + JOB_ID + '/summary'" in html
        assert "/chart-data" in html and "/tag-analysis" in html
        assert "resp.status === 409" in html               # 未完成 → 进行状态轮询
        assert "/api/saas/jobs/' + JOB_ID" not in html     # 不再走旧 job 嵌套 result
