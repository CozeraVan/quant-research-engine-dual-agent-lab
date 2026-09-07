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
        assert 'id="btn-smoke"' in html and 'id="btn-submit"' in html

    def test_job_page(self, client):
        resp = client.get("/saas/jobs/1")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'id="chart-equity"' in html and 'id="chart-drawdown"' in html
        assert 'id="job-badge"' in html and '/static/echarts.min.js' in html
        assert 'id="chart-attr"' in html and 'id="contrib-tbody"' in html  # 归因区块

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
