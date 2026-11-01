"""第四入口外部 AI Agent API（AGENT-API M1）回归。

覆盖：特性开关、访问令牌签发/列举/吊销、认证三态（缺失/错误/撤销/过期）、
scope 收窄、成本信封口径、openapi 与 StrategySpec schema 的合同、
与他人资源隔离（令牌只能本人吊销）。

约定：所有 /api/agent/v1/* 在 QRE_AGENT_API_ENABLED 未设为 "1" 时一律 404，
生产默认 inert——本文件用 app.config 显式打开，避免依赖环境变量。
"""

from __future__ import annotations

import subprocess
import uuid

import pytest

from quant_research_engine.gui.saas import create_saas_app
from quant_research_engine.gui.saas.agent_api import (
    AGENT_API_PREFIX,
    DISCLAIMER,
    TOKEN_PREFIX,
    build_capabilities,
    build_openapi,
    hash_token,
    strategy_spec_json_schema,
)

WORKER_TOKEN = "test-worker-token"


def _psql(db: str, *args: str) -> None:
    subprocess.run(
        ["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def saas_db():
    db_name = f"qre_agent_test_{uuid.uuid4().hex[:12]}"
    _psql("postgres", "-c", f"CREATE DATABASE {db_name}")
    schema = subprocess.run(
        ["psql", f"postgresql:///{db_name}", "-v", "ON_ERROR_STOP=1",
         "-f", "deploy/saas/cloud_schema.sql"],
        check=True, capture_output=True, text=True,
    )
    assert schema.returncode == 0
    yield db_name
    _psql("postgres", "-c", f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")


@pytest.fixture()
def app(saas_db):
    app = create_saas_app()
    app.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
    app.config["SAAS_WORKER_TOKEN"] = WORKER_TOKEN
    app.config["SAAS_AUTH_CHANNEL"] = "stub"
    app.config["SAAS_DEV_AUTH"] = "1"  # 管理台用例走 X-User-Id 后门
    app.config["QRE_AGENT_API_ENABLED"] = "1"  # M1 用例显式打开开关
    yield app
    engine = app.extensions.get("saas_engine")
    if engine is not None:
        engine.dispose()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _clean(app):
    from sqlalchemy import text

    from quant_research_engine.gui.saas.app import _get_engine
    engine = _get_engine(app)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE api_tokens, results, jobs, strategies, users, sessions, sms_codes RESTART IDENTITY CASCADE"))


def _login(client, app, target="13800000001"):
    """stub 通道注册/登录，返回会话 Bearer 头。"""
    assert client.post("/api/saas/auth/code", json={"target": target}).status_code == 200
    sent = app.extensions["sent_codes"]
    matches = [m["code"] for m in sent if m["target"] == target]
    assert matches, "stub sender 未记录发出的验证码"
    login = client.post("/api/saas/auth/login", json={"target": target, "code": matches[-1]})
    assert login.status_code == 200, login.get_json()
    return {"Authorization": f"Bearer {login.get_json()['token']}"}


def _create_token(client, session_headers, **overrides):
    """创建令牌并返回完整响应体（明文只在 body["token"]["plaintext"] 出现一次）。"""
    payload = {"name": "agent-a"}
    payload.update(overrides)
    resp = client.post(f"{AGENT_API_PREFIX}/tokens", json=payload, headers=session_headers)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


class TestFeatureFlag:
    def test_disabled_by_default_returns_404(self, client, app):
        app.config["QRE_AGENT_API_ENABLED"] = "0"
        for path in ("/capabilities", "/openapi.json", "/schema/strategy", "/tokens"):
            resp = client.get(f"{AGENT_API_PREFIX}{path}")
            assert resp.status_code == 404, path
            assert resp.get_json()["error"]["code"] == "not_found"

    def test_enabled_requires_token(self, client):
        resp = client.get(f"{AGENT_API_PREFIX}/capabilities")
        assert resp.status_code == 401
        assert resp.get_json()["error"]["code"] == "unauthorized"


class TestTokenLifecycle:
    def test_create_returns_plaintext_once_and_list_hides_it(self, client, app):
        session = _login(client, app)
        body = _create_token(client, session, name="primary", scopes=["factors:read"])
        created = body["token"]
        plaintext = created["plaintext"]
        assert plaintext.startswith(TOKEN_PREFIX)
        assert len(plaintext) > 40
        assert created["prefix"] == plaintext[:12]
        assert created["scopes"] == ["factors:read"]
        assert created["allow_full_market"] is False
        assert "warning" in body  # 明文只返回一次的提示在响应顶层

        listed = client.get(f"{AGENT_API_PREFIX}/tokens", headers=session).get_json()["tokens"]
        assert len(listed) == 1
        row = listed[0]
        assert row["prefix"] == created["prefix"]
        assert "plaintext" not in row and "token_hash" not in row
        assert row["revoked_at"] is None

    def test_hash_is_salted_and_not_reversible_from_list(self, client, app):
        session = _login(client, app)
        created = _create_token(client, session)["token"]
        plaintext = created["plaintext"]
        salt = app.config.get("SAAS_AUTH_SALT") or "qre-saas-dev-salt"
        digest = hash_token(plaintext, salt)
        listed = client.get(f"{AGENT_API_PREFIX}/tokens", headers=session).get_json()["tokens"]
        assert digest not in str(listed)

    def test_unknown_scope_rejected(self, client, app):
        session = _login(client, app)
        resp = client.post(f"{AGENT_API_PREFIX}/tokens",
                           json={"name": "bad", "scopes": ["factors:read", "world:dominate"]},
                           headers=session)
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "invalid_yaml"

    def test_expires_days_must_be_positive(self, client, app):
        session = _login(client, app)
        assert client.post(f"{AGENT_API_PREFIX}/tokens",
                           json={"name": "x", "expires_days": 0},
                           headers=session).status_code == 400

    def test_revoke_makes_token_unusable_and_only_owner_can_revoke(self, client, app):
        session_a = _login(client, app, "13800000001")
        session_b = _login(client, app, "13800000002")
        token = _create_token(client, session_a)["token"]

        # 他人吊销：与不存在同体
        resp = client.post(f"{AGENT_API_PREFIX}/tokens/{token['id']}/revoke", headers=session_b)
        assert resp.status_code == 404

        headers = {"Authorization": f"Bearer {token['plaintext']}"}
        assert client.get(f"{AGENT_API_PREFIX}/capabilities", headers=headers).status_code == 200

        assert client.post(f"{AGENT_API_PREFIX}/tokens/{token['id']}/revoke",
                           headers=session_a).status_code == 200
        after = client.get(f"{AGENT_API_PREFIX}/capabilities", headers=headers)
        assert after.status_code == 401
        assert after.get_json()["error"]["code"] == "unauthorized"

    def test_token_management_requires_login(self, client):
        assert client.get(f"{AGENT_API_PREFIX}/tokens").status_code == 401
        assert client.post(f"{AGENT_API_PREFIX}/tokens", json={"name": "x"}).status_code == 401


class TestAgentAuthentication:
    def test_missing_bearer_401(self, client):
        resp = client.get(f"{AGENT_API_PREFIX}/capabilities")
        assert resp.status_code == 401

    def test_session_token_is_not_agent_token(self, client, app):
        session = _login(client, app)
        resp = client.get(f"{AGENT_API_PREFIX}/capabilities", headers=session)
        assert resp.status_code == 401  # 不提示「用错令牌类型」，统一无效

    def test_garbage_token_401(self, client):
        resp = client.get(f"{AGENT_API_PREFIX}/capabilities",
                          headers={"Authorization": f"Bearer {TOKEN_PREFIX}nope"})
        assert resp.status_code == 401

    def test_scope_narrowing_403(self, client, app):
        session = _login(client, app)
        token = _create_token(client, session, scopes=["jobs:read"])["token"]
        headers = {"Authorization": f"Bearer {token['plaintext']}"}
        resp = client.get(f"{AGENT_API_PREFIX}/capabilities", headers=headers)
        assert resp.status_code == 403
        assert resp.get_json()["error"]["code"] == "forbidden_scope"

    def test_full_scopes_allow_all_discovery_endpoints(self, client, app):
        session = _login(client, app)
        token = _create_token(client, session)["token"]
        headers = {"Authorization": f"Bearer {token['plaintext']}"}
        for path in ("/capabilities", "/openapi.json", "/schema/strategy"):
            resp = client.get(f"{AGENT_API_PREFIX}{path}", headers=headers)
            assert resp.status_code == 200, path
            assert resp.get_json()["disclaimer"] == DISCLAIMER


class TestCapabilities:
    def test_cost_envelope_shape_and_units(self):
        caps = build_capabilities()
        assert caps["api_version"] == "v1"
        profiles = caps["scale_profiles"]
        assert [p["name"] for p in profiles] == [
            "smoke_6m", "sample300_5y", "full_a_2y", "full_a_full",
        ]
        for profile in profiles:
            assert profile["est_seconds"] > 0
            assert profile["peak_mem_mb"] > 0
            assert profile["artifact_kb"] > 0
            assert profile["universe_size"] > 0
        # 单调性：规模越大，估计耗时与产物体积不得更小（防口径写反）
        by_size = sorted(profiles, key=lambda p: p["universe_size"])
        assert [p["est_seconds"] for p in by_size] == sorted(p["est_seconds"] for p in by_size)
        assert [p["artifact_kb"] for p in by_size] == sorted(p["artifact_kb"] for p in by_size)
        assert caps["measured_at"]
        assert caps["agent_defaults"]["nightly_only"] is True
        assert caps["note"]

    def test_defaults_match_token_table_defaults(self):
        caps = build_capabilities()
        assert caps["agent_defaults"]["daily_submit_limit"] == 50
        assert caps["agent_defaults"]["in_flight_limit"] == 5
        assert caps["agent_defaults"]["allow_full_market"] is False


class TestConsoleVisibility:
    """R-ADMIN-001：外部 Agent API 的限额必须在 9090 管理台可见，且与执行同源。"""

    def _admin(self, client, app, email="admin@example.com"):
        from sqlalchemy import text

        engine = app.extensions["saas_engine"]
        with engine.begin() as conn:
            uid = conn.execute(
                text("INSERT INTO users (email, role) VALUES (:e, 'admin') RETURNING id"),
                {"e": email},
            ).scalar_one()
        return {"X-User-Id": str(uid)}

    def test_overview_reports_flag_defaults_and_token_counts(self, client, app):
        from quant_research_engine.gui.saas import agent_api as agent_mod

        headers = self._admin(client, app)
        session = _login(client, app, "13800000009")
        _create_token(client, session, name="console-visible")

        d = client.get("/api/saas/console/overview", headers=headers).get_json()
        assert d["ok"]
        ag = d["agent_api"]
        assert ag["enabled"] is True  # 用例 fixture 显式打开开关
        # 限额与执行侧默认常量同源（无第二套配置）
        assert ag["defaults"] == agent_mod.AGENT_DEFAULTS
        assert ag["tokens_total"] == 1 and ag["tokens_active"] == 1
        row = ag["tokens"][0]
        assert row["name"] == "console-visible"
        assert row["prefix"] and "plaintext" not in row and "token_hash" not in row
        assert row["daily_submit_limit"] == agent_mod.AGENT_DEFAULTS["daily_submit_limit"]

    def test_overview_marks_revoked_token_inactive(self, client, app):
        headers = self._admin(client, app)
        session = _login(client, app, "13800000009")
        token = _create_token(client, session)["token"]
        assert client.post(f"{AGENT_API_PREFIX}/tokens/{token['id']}/revoke",
                           headers=session).status_code == 200
        d = client.get("/api/saas/console/overview", headers=headers).get_json()
        ag = d["agent_api"]
        assert ag["tokens_total"] == 1 and ag["tokens_active"] == 0
        assert ag["tokens"][0]["revoked_at"]

    def test_overview_requires_admin(self, client, app):
        assert client.get("/api/saas/console/overview").status_code == 401
        session = _login(client, app, "13800000009")
        assert client.get("/api/saas/console/overview", headers=session).status_code == 403

    def test_console_page_has_agent_card_markup(self):
        from pathlib import Path

        html = Path("src/quant_research_engine/gui/saas/templates/console.html").read_text(encoding="utf-8")
        assert 'id="ov-agent"' in html
        assert "renderAgentApi" in html
        assert "QRE_AGENT_API_ENABLED" in html  # 说明文案提到开关


class TestDiscoveryDocuments:
    def test_openapi_contract(self):
        doc = build_openapi()
        assert doc["openapi"].startswith("3.0.")
        assert doc["info"]["version"] == "v1"
        assert DISCLAIMER in doc["info"]["description"]
        assert doc["security"] == [{"bearerAuth": []}]
        assert doc["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"
        # 未实现的切片必须显式标注 planned，不得让外部 agent 误判可用
        for path in ("/validate", "/research-runs", "/sweeps", "/jobs"):
            assert doc["paths"][path]["post"]["x-status"] == "planned", path
        codes = {e["code"] for e in doc["x-error-codes"]}
        assert {"unauthorized", "forbidden_scope", "budget_exhausted",
                "daily_submit_limit", "nightly_window"} <= codes
        error_enum = set(doc["components"]["schemas"]["Error"]["properties"]["error"]["properties"]["code"]["enum"])
        assert error_enum == codes

    def test_strategy_schema_sections_and_required(self):
        schema = strategy_spec_json_schema()
        assert schema["type"] == "object"
        assert set(schema["required"]) == {"experiment", "data", "signal", "evaluation", "holding"}
        props = schema["properties"]
        assert set(props) == {
            "experiment", "data", "signal", "execution", "evaluation", "holding",
            "risk", "portfolio", "universe",
        }
        assert props["signal"]["required"] == ["entry"]
        assert props["data"]["required"] == ["factor_fields"]
        assert props["holding"]["properties"]["max_holding_days"]["description"]

    def test_strategy_schema_covers_real_strategy_keys(self):
        """防漂移：仓库内经典策略的顶层键必须全部被 schema 声明。"""
        from pathlib import Path

        import yaml

        from quant_research_engine.strategies.spec import StrategySpec

        schema = strategy_spec_json_schema()
        declared = set(schema["properties"])
        classics = sorted(Path("strategies/classic").glob("*.yaml"))
        assert classics, "strategies/classic 下应有可复现策略定义"
        for path in classics:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            assert isinstance(raw, dict)
            StrategySpec.from_mapping(raw)  # 能解析才算有效样本
            undeclared = set(raw) - declared
            assert not undeclared, f"{path.name} 有未声明节：{sorted(undeclared)}"

    def test_factor_field_pattern_rejects_non_table_column(self):
        schema = strategy_spec_json_schema()
        pattern = schema["properties"]["data"]["properties"]["factor_fields"]["additionalProperties"]["pattern"]
        import re

        assert re.match(pattern, "factors.stock_daily_ta.ema5")
        assert not re.match(pattern, "ema5")
        assert not re.match(pattern, "Factors.Ema5")
