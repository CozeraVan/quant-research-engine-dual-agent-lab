"""第四入口外部 AI Agent API（AGENT-API M1）回归。

覆盖：特性开关、访问令牌签发/列举/吊销、认证三态（缺失/错误/撤销/过期）、
scope 收窄、成本信封口径、openapi 与 StrategySpec schema 的合同、
与他人资源隔离（令牌只能本人吊销）。

约定：所有 /api/agent/v1/* 在 QRE_AGENT_API_ENABLED 未设为 "1" 时一律 404，
生产默认 inert——本文件用 app.config 显式打开，避免依赖环境变量。
"""

from __future__ import annotations

import json
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
        conn.execute(text("TRUNCATE agent_api_events, agent_rate_limits, agent_sweeps, research_runs, api_tokens, results, jobs, strategies, users, sessions, sms_codes RESTART IDENTITY CASCADE"))


def _login(client, app, target="13800000001"):
    """stub 通道注册/登录，返回会话 Bearer 头。"""
    assert client.post("/api/saas/auth/code", json={"target": target}).status_code == 200
    sent = app.extensions["sent_codes"]
    matches = [m["code"] for m in sent if m["target"] == target]
    assert matches, "stub sender 未记录发出的验证码"
    login = client.post("/api/saas/auth/login", json={"target": target, "code": matches[-1]})
    assert login.status_code == 200, login.get_json()
    return {"Authorization": f"Bearer {login.get_json()['token']}"}


def _admin_headers(app, email="admin@example.com"):
    """建一个 admin 用户并返回 X-User-Id 头（SAAS_DEV_AUTH 后门）。"""
    from sqlalchemy import text

    engine = app.extensions["saas_engine"]
    with engine.begin() as conn:
        uid = conn.execute(
            text("INSERT INTO users (email, role) VALUES (:e, 'admin') RETURNING id"),
            {"e": email},
        ).scalar_one()
    return {"X-User-Id": str(uid)}


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

    def test_disabled_also_hides_post_only_routes(self, client, app):
        """方法不匹配时 Flask 会在路由阶段抛 405；app 级前缀闸必须先拦成 404，
        否则关闭状态下也会泄露「路由存在」。"""
        app.config["QRE_AGENT_API_ENABLED"] = "0"
        for method, path in (("get", "/validate"), ("get", "/sweeps"),
                             ("post", "/capabilities"), ("get", "/sweeps/1/aggregate")):
            resp = getattr(client, method)(f"{AGENT_API_PREFIX}{path}", json={})
            assert resp.status_code == 404, (method, path)

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


class TestResearchRuns:
    """M2：研究会话容器——归属隔离、预算收敛、状态机、结论只存不解释。"""

    def _token(self, client, app, scopes=None):
        session = _login(client, app)
        token = _create_token(client, session, scopes=scopes or
                              ["jobs:submit", "jobs:read", "results:read", "factors:read"])["token"]
        return {"Authorization": f"Bearer {token['plaintext']}"}

    def _create_run(self, client, headers, **payload):
        body = {"title": "EMA 周期是否有意义"}
        body.update(payload)
        resp = client.post(f"{AGENT_API_PREFIX}/research-runs", json=body, headers=headers)
        assert resp.status_code == 201, resp.get_json()
        return resp.get_json()["research_run"]

    def test_create_defaults_and_view(self, client, app):
        headers = self._token(client, app)
        run = self._create_run(client, headers, boundary_text="只测 EMA，不测组合",
                               todo=[{"step": 1, "what": "EMA 5..250 扫描"}])
        assert run["status"] == "planned"
        assert run["budget"] == {}  # 未给预算 = 不设上限（仍受 token 与会话默认值约束）
        detail = client.get(f"{AGENT_API_PREFIX}/research-runs/{run['id']}",
                            headers=headers).get_json()["research_run"]
        assert detail["boundary_text"] == "只测 EMA，不测组合"
        assert detail["todo"][0]["what"] == "EMA 5..250 扫描"
        assert detail["usage"]["jobs_total"] == 0
        assert detail["budget_exceeded"] is None

    def test_title_required_and_bounded(self, client, app):
        headers = self._token(client, app)
        assert client.post(f"{AGENT_API_PREFIX}/research-runs", json={},
                           headers=headers).status_code == 400
        assert client.post(f"{AGENT_API_PREFIX}/research-runs",
                           json={"title": "x" * 200}, headers=headers).status_code == 400

    def test_budget_unknown_key_rejected(self, client, app):
        headers = self._token(client, app)
        resp = client.post(f"{AGENT_API_PREFIX}/research-runs",
                           json={"title": "t", "budget": {"max_everything": 5}}, headers=headers)
        assert resp.status_code == 400
        assert "未知 budget 键" in resp.get_json()["error"]["message"]

    def test_budget_clamped_to_session_caps(self, client, app):
        from quant_research_engine.gui.saas import agent_api as agent_mod

        headers = self._token(client, app)
        run = self._create_run(client, headers, budget={
            "max_jobs": 10 ** 9,
            "max_artifact_bytes": 10 ** 15,
            "max_wall_clock_hours": 10 ** 6,
        })
        caps = agent_mod.AGENT_DEFAULTS
        assert run["budget"]["max_jobs"] == caps["research_run_max_jobs"]
        assert run["budget"]["max_artifact_bytes"] == caps["research_run_max_artifact_bytes"]
        assert run["budget"]["max_wall_clock_hours"] == caps["research_run_max_wall_clock_hours"]

    def test_budget_negative_and_type_rejected(self, client, app):
        headers = self._token(client, app)
        for bad in ({"max_jobs": -1}, {"max_jobs": "many"}, {"allow_full_market": "yes"}):
            resp = client.post(f"{AGENT_API_PREFIX}/research-runs",
                               json={"title": "t", "budget": bad}, headers=headers)
            assert resp.status_code == 400, bad

    def test_status_transitions_and_illegal_move(self, client, app):
        headers = self._token(client, app)
        run = self._create_run(client, headers)
        rid = run["id"]
        assert client.post(f"{AGENT_API_PREFIX}/research-runs/{rid}/status",
                           json={"status": "running"}, headers=headers).status_code == 200
        assert client.post(f"{AGENT_API_PREFIX}/research-runs/{rid}/status",
                           json={"status": "aggregated"}, headers=headers).status_code == 200
        # concluded 是终态之一，只能去 archived
        resp = client.post(f"{AGENT_API_PREFIX}/research-runs/{rid}/status",
                           json={"status": "running"}, headers=headers)
        assert resp.status_code == 409
        assert client.post(f"{AGENT_API_PREFIX}/research-runs/{rid}/status",
                           json={"status": "nonsense"}, headers=headers).status_code == 400

    def test_conclusion_stored_verbatim_and_marks_concluded(self, client, app):
        headers = self._token(client, app)
        run = self._create_run(client, headers)
        table = [{"config": {"ema": 5}, "sharpe": 0.31}, {"config": {"ema": 60}, "sharpe": 0.12}]
        resp = client.post(f"{AGENT_API_PREFIX}/research-runs/{run['id']}/conclusion",
                           json={"conclusion_text": "EMA5 在本样本内夏普最高",
                                 "conclusion_table": table}, headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()["research_run"]["stored"] is True
        detail = client.get(f"{AGENT_API_PREFIX}/research-runs/{run['id']}",
                            headers=headers).get_json()["research_run"]
        assert detail["status"] == "concluded"
        assert detail["conclusion_text"] == "EMA5 在本样本内夏普最高"
        assert detail["conclusion_table"] == table  # 原样存储，不改写
        assert detail["concluded_at"]

    def test_conclusion_requires_at_least_one_field(self, client, app):
        headers = self._token(client, app)
        run = self._create_run(client, headers)
        resp = client.post(f"{AGENT_API_PREFIX}/research-runs/{run['id']}/conclusion",
                           json={}, headers=headers)
        assert resp.status_code == 400

    def test_archived_run_rejects_conclusion(self, client, app):
        headers = self._token(client, app)
        run = self._create_run(client, headers)
        client.post(f"{AGENT_API_PREFIX}/research-runs/{run['id']}/status",
                    json={"status": "archived"}, headers=headers)
        resp = client.post(f"{AGENT_API_PREFIX}/research-runs/{run['id']}/conclusion",
                           json={"conclusion_text": "太晚了"}, headers=headers)
        assert resp.status_code == 409

    def test_other_users_run_is_404(self, client, app):
        headers_a = self._token(client, app)
        session_b = _login(client, app, "13800000002")
        token_b = _create_token(client, session_b)["token"]
        headers_b = {"Authorization": f"Bearer {token_b['plaintext']}"}
        run = self._create_run(client, headers_a)
        for method, path in (
            ("get", f"{AGENT_API_PREFIX}/research-runs/{run['id']}"),
            ("post", f"{AGENT_API_PREFIX}/research-runs/{run['id']}/status"),
            ("post", f"{AGENT_API_PREFIX}/research-runs/{run['id']}/conclusion"),
        ):
            resp = getattr(client, method)(path, json={"status": "archived",
                                                       "conclusion_text": "x"}, headers=headers_b)
            assert resp.status_code == 404, (method, path)

    def test_scope_required(self, client, app):
        headers = self._token(client, app, scopes=["factors:read"])
        assert client.post(f"{AGENT_API_PREFIX}/research-runs", json={"title": "t"},
                           headers=headers).status_code == 403
        assert client.get(f"{AGENT_API_PREFIX}/research-runs", headers=headers).status_code == 403

    def test_usage_counts_jobs_of_this_run(self, client, app):
        """预算记账：把一条 job 挂到会话上，usage 立即反映（M3 sweep 的前置）。"""
        from sqlalchemy import text

        headers = self._token(client, app)
        run = self._create_run(client, headers, budget={"max_jobs": 2})
        engine = app.extensions["saas_engine"]
        with engine.begin() as conn:
            uid = conn.execute(text("SELECT id FROM users ORDER BY id LIMIT 1")).scalar_one()
            sid = conn.execute(
                text("INSERT INTO strategies (user_id, name, yaml) "
                     "VALUES (:uid, 'agent-run', :y) RETURNING id"),
                {"uid": uid, "y": "signal:\n  entry: 'true'\n"},
            ).scalar_one()
            conn.execute(text(
                "INSERT INTO jobs (user_id, strategy_id, kind, params, research_run_id, status, "
                "started_at, finished_at) VALUES (:uid, :sid, 'full', '{}'::jsonb, :rid, "
                "'completed', now() - interval '60 s', now())"),
                {"uid": uid, "sid": sid, "rid": run["id"]})
        detail = client.get(f"{AGENT_API_PREFIX}/research-runs/{run['id']}",
                            headers=headers).get_json()["research_run"]
        assert detail["usage"]["jobs_total"] == 1
        assert detail["usage"]["jobs_completed"] == 1
        assert detail["usage"]["wall_clock_seconds"] >= 59
        assert detail["budget_exceeded"] is None

    def test_console_reports_research_run_counts(self, client, app):
        headers = _admin_headers(app)
        agent_headers = self._token(client, app)
        self._create_run(client, agent_headers, title="控制台可见会话")
        d = client.get("/api/saas/console/overview", headers=headers).get_json()
        ag = d["agent_api"]
        assert ag["research_runs_total"] == 1
        assert ag["research_runs_open"] == 1
        assert ag["research_runs"][0]["title"] == "控制台可见会话"
        assert ag["research_runs"][0]["has_conclusion"] is False


class TestValidateAndSweeps:
    """M3：validate 合同 + sweep 两阶段护栏 + 预算预检 + 幂等 + aggregate 口径。"""

    BASE_YAML = (
        "experiment:\n  name: ema_scan\n"
        "data:\n  factor_fields:\n    ema_fast: factors.stock_daily_ta.ema5\n"
        "signal:\n  entry: 'ema_fast > close'\n  exit: 'ema_fast < close'\n"
        "evaluation:\n  forward_return_horizons: [1]\n"
        "holding:\n  max_holding_days: 20\n"
    )

    def _token(self, client, app, scopes=None):
        session = _login(client, app)
        # nightly_only=False：这些用例测展开/护栏/幂等，不该被墙上时钟影响状态码
        #（2026-11-03 教训：默认 true 时，06:00 后跑全套件会 6 例 202≠201 全红）
        token = _create_token(client, session, scopes=scopes or
                              ["jobs:submit", "jobs:read", "results:read", "factors:read"],
                              nightly_only=False)["token"]
        return {"Authorization": f"Bearer {token['plaintext']}"}

    def _run(self, client, headers, **budget):
        resp = client.post(f"{AGENT_API_PREFIX}/research-runs",
                           json={"title": "EMA 扫描", "budget": budget}, headers=headers)
        assert resp.status_code == 201, resp.get_json()
        return resp.get_json()["research_run"]["id"]

    # --- validate ---
    def test_validate_ok_returns_cost_estimate_without_executing(self, client, app):
        headers = self._token(client, app)
        resp = client.post(f"{AGENT_API_PREFIX}/validate",
                           json={"yaml": self.BASE_YAML,
                                 "params": {"random_n": 300, "start": "2021-01-04",
                                            "end": "2026-10-30"}},
                           headers=headers)
        assert resp.status_code == 200
        body = resp.get_json()["validate"]
        assert body["valid"] is True and body["issues"] == []
        assert body["executed"] is False and body["quota_charged"] is False
        assert body["cost_estimate"]["profile"] == "sample300_5y"
        assert 10 <= body["cost_estimate"]["est_seconds"] <= 25

    def test_validate_rejects_bad_yaml_and_missing_dates(self, client, app):
        headers = self._token(client, app)
        resp = client.post(f"{AGENT_API_PREFIX}/validate",
                           json={"yaml": "signal: [", "params": {}}, headers=headers)
        assert resp.status_code == 200  # validate 不因非法而 500，只在 body 里报告
        body = resp.get_json()["validate"]
        assert body["valid"] is False
        assert any("YAML" in issue for issue in body["issues"])
        assert any("start" in issue for issue in body["issues"])

    def test_validate_normalizes_codes(self, client, app):
        headers = self._token(client, app)
        resp = client.post(f"{AGENT_API_PREFIX}/validate",
                           json={"yaml": self.BASE_YAML,
                                 "params": {"codes": ["600519"], "start": "2024-01-02",
                                            "end": "2024-06-28"}},
                           headers=headers)
        codes = resp.get_json()["validate"]["normalized_params"]["codes"]
        assert codes == ["600519.SH"]

    def test_validate_full_market_estimates_full_profile(self, client, app):
        headers = self._token(client, app)
        resp = client.post(f"{AGENT_API_PREFIX}/validate",
                           json={"yaml": self.BASE_YAML,
                                 "params": {"all_market": True, "start": "2025-01-02",
                                            "end": "2026-10-30"}},
                           headers=headers)
        estimate = resp.get_json()["validate"]["cost_estimate"]
        assert estimate["profile"] == "full_a_2y"
        assert estimate["method"] in ("profile_match", "profile_match_scaled")

    # --- sweeps ---
    def _sweep(self, client, headers, run_id, *, stage="screen", grid=None, params=None,
               idem="sweep-1", labels=None):
        body = {
            "research_run_id": run_id,
            "base_yaml": self.BASE_YAML,
            "grid": grid if grid is not None else {
                "data.factor_fields.ema_fast": [
                    "factors.stock_daily_ta.ema5",
                    "factors.stock_daily_ta.ema10",
                    "factors.stock_daily_ta.ema20",
                ]
            },
            "params": params or {"random_n": 50, "start": "2024-01-02", "end": "2025-06-30"},
            "stage": stage,
            "idempotency_key": idem,
        }
        if labels is not None:
            body["labels"] = labels
        return client.post(f"{AGENT_API_PREFIX}/sweeps", json=body, headers=headers)

    def test_screen_sweep_expands_jobs_and_links_run(self, client, app):
        headers = self._token(client, app)
        run_id = self._run(client, headers, max_jobs=10)
        resp = self._sweep(client, headers, run_id)
        assert resp.status_code == 201, resp.get_json()
        sweep = resp.get_json()["sweep"]
        assert sweep["job_count"] == 3 and sweep["stage"] == "screen"
        assert len(sweep["job_ids"]) == 3

        detail = client.get(f"{AGENT_API_PREFIX}/sweeps/{sweep['id']}",
                            headers=headers).get_json()
        assert len(detail["jobs"]) == 3
        assert all(j["status"] == "queued" for j in detail["jobs"])
        run = client.get(f"{AGENT_API_PREFIX}/research-runs/{run_id}",
                         headers=headers).get_json()["research_run"]
        assert run["usage"]["jobs_total"] == 3

    def test_screen_defaults_random_n_when_absent(self, client, app):
        headers = self._token(client, app)
        run_id = self._run(client, headers)
        resp = self._sweep(client, headers, run_id,
                           params={"start": "2024-01-02", "end": "2025-06-30"})
        assert resp.status_code == 201, resp.get_json()
        assert resp.get_json()["sweep"]["params"]["random_n"] == 300

    def test_screen_rejects_full_market_and_long_window(self, client, app):
        headers = self._token(client, app)
        run_id = self._run(client, headers)
        resp = self._sweep(client, headers, run_id,
                           params={"all_market": True, "start": "2024-01-02",
                                   "end": "2025-06-30"})
        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "stage_not_allowed"
        resp = self._sweep(client, headers, run_id, idem="sweep-long",
                           params={"random_n": 50, "start": "2015-01-02",
                                   "end": "2026-10-30"})
        assert resp.status_code == 409

    def test_confirm_requires_allow_full_market(self, client, app):
        headers = self._token(client, app)
        run_id = self._run(client, headers)
        resp = self._sweep(client, headers, run_id, stage="confirm")
        assert resp.status_code == 409
        assert "allow_full_market" in resp.get_json()["error"]["message"]

    def test_confirm_allows_full_market_with_budget(self, client, app):
        headers = self._token(client, app)
        run_id = self._run(client, headers, allow_full_market=True)
        resp = self._sweep(client, headers, run_id, stage="confirm",
                           grid={"data.factor_fields.ema_fast": [
                               "factors.stock_daily_ta.ema5",
                               "factors.stock_daily_ta.ema20"]},
                           params={"all_market": True, "start": "2024-01-02",
                                   "end": "2025-06-30"})
        assert resp.status_code == 201, resp.get_json()
        assert resp.get_json()["sweep"]["job_count"] == 2

    def test_confirm_rejects_too_many_configs(self, client, app):
        headers = self._token(client, app)
        run_id = self._run(client, headers, allow_full_market=True)
        grid = {"data.factor_fields.ema_fast": [f"factors.stock_daily_ta.ema{n}"
                                                for n in (5, 10, 20, 30, 60, 120)]}
        resp = self._sweep(client, headers, run_id, stage="confirm", grid=grid,
                           params={"all_market": True, "start": "2024-01-02",
                                   "end": "2025-06-30"})
        assert resp.status_code == 409
        assert "最多 5 个配置" in resp.get_json()["error"]["message"]

    def test_budget_max_jobs_blocks_expansion(self, client, app):
        headers = self._token(client, app)
        run_id = self._run(client, headers, max_jobs=2)
        resp = self._sweep(client, headers, run_id)  # 3 个配置 > max_jobs=2
        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "budget_exhausted"

    def test_token_daily_limit_blocks(self, client, app):
        from sqlalchemy import text

        headers = self._token(client, app)
        run_id = self._run(client, headers)
        engine = app.extensions["saas_engine"]
        with engine.begin() as conn:
            uid = conn.execute(text("SELECT id FROM users ORDER BY id LIMIT 1")).scalar_one()
            sid = conn.execute(
                text("INSERT INTO strategies (user_id, name, yaml) VALUES (:u, 's', :y) RETURNING id"),
                {"u": uid, "y": self.BASE_YAML}).scalar_one()
            tid = conn.execute(text("SELECT id FROM api_tokens ORDER BY id DESC LIMIT 1")).scalar_one()
            for _ in range(50):  # 打满默认 50/日
                conn.execute(text(
                    "INSERT INTO jobs (user_id, strategy_id, kind, params, token_id) "
                    "VALUES (:u, :s, 'full', '{}'::jsonb, :t)"), {"u": uid, "s": sid, "t": tid})
        resp = self._sweep(client, headers, run_id)
        assert resp.status_code == 429
        assert resp.get_json()["error"]["code"] == "daily_submit_limit"

    def test_idempotency_returns_existing_sweep(self, client, app):
        headers = self._token(client, app)
        run_id = self._run(client, headers)
        first = self._sweep(client, headers, run_id, idem="same-key")
        assert first.status_code == 201
        second = self._sweep(client, headers, run_id, idem="same-key")
        assert second.status_code == 200
        assert second.get_json()["deduped"] is True
        assert second.get_json()["sweep"]["id"] == first.get_json()["sweep"]["id"]
        detail = client.get(f"{AGENT_API_PREFIX}/sweeps/{first.get_json()['sweep']['id']}",
                            headers=headers).get_json()
        assert len(detail["jobs"]) == 3  # 没有重复展开

    def test_missing_idempotency_key_rejected(self, client, app):
        headers = self._token(client, app)
        run_id = self._run(client, headers)
        resp = self._sweep(client, headers, run_id, idem="")
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "missing_idempotency_key"

    def test_unknown_grid_key_rejected(self, client, app):
        headers = self._token(client, app)
        run_id = self._run(client, headers)
        resp = self._sweep(client, headers, run_id,
                           grid={"holding.max_holding_days": [5, 10]})
        assert resp.status_code == 400
        assert "data.factor_fields" in resp.get_json()["error"]["message"]

    def test_agent_jobs_do_not_consume_member_daily_quota(self, client, app):
        """关键决策：agent job 不占用户人工会员日配额，否则扫描立刻被 3 次/日挡死。"""
        from sqlalchemy import text

        headers = self._token(client, app)
        run_id = self._run(client, headers)
        assert self._sweep(client, headers, run_id).status_code == 201
        engine = app.extensions["saas_engine"]
        with engine.connect() as conn:
            # 该用户今日 full job 数已超过 member 默认 3 次，但 agent 任务照常入队
            used = conn.execute(text(
                "SELECT count(*) FROM jobs j JOIN users u ON u.id = j.user_id "
                "WHERE j.kind='full' AND j.created_at::date = now()::date "
                "AND j.token_id IS NOT NULL")).scalar_one()
        assert used == 3

    def test_aggregate_returns_numbers_only(self, client, app):
        from sqlalchemy import text

        headers = self._token(client, app)
        run_id = self._run(client, headers)
        sweep_id = self._sweep(client, headers, run_id).get_json()["sweep"]["id"]
        engine = app.extensions["saas_engine"]
        with engine.begin() as conn:
            job_id = conn.execute(text(
                "SELECT id FROM jobs WHERE sweep_id = :s ORDER BY id LIMIT 1"), {"s": sweep_id}
            ).scalar_one()
            conn.execute(text(
                "UPDATE jobs SET status='completed', started_at=now(), finished_at=now() "
                "WHERE id = :j"), {"j": job_id})
            conn.execute(text(
                "INSERT INTO results (job_id, user_id, summary, chart_data) "
                "SELECT id, user_id, '{}'::jsonb, "
                "jsonb_build_object('metrics', jsonb_build_object("
                "'total_return', 0.42, 'sharpe', 1.1, 'max_drawdown', -0.2, "
                "'trades', 88, 'win_rate', 0.5)) FROM jobs WHERE id = :j"),
                {"j": job_id})
        resp = client.get(f"{AGENT_API_PREFIX}/sweeps/{sweep_id}/aggregate",
                          headers=headers)
        assert resp.status_code == 200
        agg = resp.get_json()["aggregate"]
        assert agg["total"] == 3 and agg["completed"] == 1
        assert agg["sorted_by"] == "total_return"
        assert "不含任何投资建议" in agg["note"]
        done = [r for r in agg["rows"] if r["job_id"] == job_id][0]
        assert done["total_return"] == 0.42 and done["sharpe"] == 1.1
        assert done["annual_return"] is None  # 缺字段 null，不编造
        others = [r for r in agg["rows"] if r["job_id"] != job_id][0]
        assert others["total_return"] is None

    def test_aggregate_sort_by_whitelist(self, client, app):
        headers = self._token(client, app)
        run_id = self._run(client, headers)
        sweep_id = self._sweep(client, headers, run_id).get_json()["sweep"]["id"]
        resp = client.get(f"{AGENT_API_PREFIX}/sweeps/{sweep_id}/aggregate?sort_by=profit",
                          headers=headers)
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "invalid_yaml"

    def test_other_users_sweep_is_404(self, client, app):
        headers_a = self._token(client, app)
        run_id = self._run(client, headers_a)
        sweep_id = self._sweep(client, headers_a, run_id).get_json()["sweep"]["id"]
        session_b = _login(client, app, "13800000003")
        token_b = _create_token(client, session_b)["token"]
        headers_b = {"Authorization": f"Bearer {token_b['plaintext']}"}
        for path in (f"{AGENT_API_PREFIX}/sweeps/{sweep_id}",
                     f"{AGENT_API_PREFIX}/sweeps/{sweep_id}/aggregate"):
            assert client.get(path, headers=headers_b).status_code == 404, path


class TestRateLimitNightlyAndAudit:
    """M4：每分钟限流、夜间窗口 eligible_at、claim 不认领未到点任务、审计最小口径。"""

    BASE_YAML = (
        "experiment:\n  name: ema_scan\n"
        "data:\n  factor_fields:\n    ema_fast: factors.stock_daily_ta.ema5\n"
        "signal:\n  entry: 'ema_fast > close'\n  exit: 'ema_fast < close'\n"
        "evaluation:\n  forward_return_horizons: [1]\n"
        "holding:\n  max_holding_days: 20\n"
    )

    def _token(self, client, app, scopes=None, target=None, **token_kwargs):
        session = _login(client, app, target or "13800000001")
        payload = {"name": "agent-a", "scopes": scopes or [
            "jobs:submit", "jobs:read", "results:read", "factors:read"],
            # 除窗口专项用例外，一律关窗口，避免墙上时钟决定状态码
            #（2026-11-03 教训：默认 true 时 06:00 后跑全套件 6 例 202≠201 全红）
            "nightly_only": False}
        payload.update(token_kwargs)
        token = _create_token(client, session, **payload)["token"]
        return {"Authorization": f"Bearer {token['plaintext']}"}

    def _run(self, client, headers, **budget):
        resp = client.post(f"{AGENT_API_PREFIX}/research-runs",
                           json={"title": "EMA 扫描", "budget": budget}, headers=headers)
        assert resp.status_code == 201, resp.get_json()
        return resp.get_json()["research_run"]["id"]

    def _sweep(self, client, headers, run_id, idem="s1"):
        return client.post(f"{AGENT_API_PREFIX}/sweeps", json={
            "research_run_id": run_id,
            "base_yaml": self.BASE_YAML,
            "grid": {"data.factor_fields.ema_fast": ["factors.stock_daily_ta.ema5"]},
            "params": {"random_n": 20, "start": "2024-01-02", "end": "2025-06-30"},
            "idempotency_key": idem,
        }, headers=headers)

    # --- 限流 ---
    def test_rate_limit_returns_429_with_retry_after(self, client, app):
        headers = self._token(client, app, rate_per_minute=3)
        codes = []
        for _ in range(5):
            codes.append(client.get(f"{AGENT_API_PREFIX}/capabilities", headers=headers).status_code)
        assert codes[:3] == [200, 200, 200]
        assert codes[3] == 429
        last = client.get(f"{AGENT_API_PREFIX}/capabilities", headers=headers)
        assert last.status_code == 429
        assert int(last.headers["Retry-After"]) >= 1
        assert last.get_json()["error"]["code"] == "rate_limited"

    def test_rate_limit_is_per_token(self, client, app):
        headers_a = self._token(client, app, rate_per_minute=2)
        for _ in range(2):
            assert client.get(f"{AGENT_API_PREFIX}/capabilities", headers=headers_a).status_code == 200
        assert client.get(f"{AGENT_API_PREFIX}/capabilities", headers=headers_a).status_code == 429
        # 另一个令牌不受影响（按令牌分别计数；换手机号避开验证码 60s 限流）
        headers_b = self._token(client, app, rate_per_minute=2, target="13800000091")
        assert client.get(f"{AGENT_API_PREFIX}/capabilities", headers=headers_b).status_code == 200

    def test_rate_limit_zero_means_unlimited(self, client, app):
        headers = self._token(client, app, rate_per_minute=0)
        for _ in range(5):
            assert client.get(f"{AGENT_API_PREFIX}/capabilities", headers=headers).status_code == 200

    def test_rate_limit_rows_cleaned_up(self, client, app):
        from sqlalchemy import text

        headers = self._token(client, app, rate_per_minute=5)
        engine = app.extensions["saas_engine"]
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO agent_rate_limits (scope, subject_hash, window_start, hits) "
                "VALUES ('agent_minute', 'stale', now() - interval '5 hours', 9)"))
        assert client.get(f"{AGENT_API_PREFIX}/capabilities", headers=headers).status_code == 200
        with engine.connect() as conn:
            stale = conn.execute(text(
                "SELECT count(*) FROM agent_rate_limits WHERE subject_hash = 'stale'")).scalar_one()
        assert stale == 0  # 2 小时前的行被机会式清理

    # --- 夜间窗口 ---
    def test_nightly_window_inside_window_is_not_limited(self, client, app, monkeypatch):
        """窗口内 → 不限制。窗口配置成必然覆盖当前时刻，与墙上时钟无关。"""
        from quant_research_engine.gui.saas import agent_api as agent_mod

        monkeypatch.setitem(agent_mod.AGENT_DEFAULTS, "nightly_window", "00:00-23:59 Asia/Shanghai")
        assert agent_mod._nightly_eligible_at({"nightly_only": True}) is None

    def test_nightly_window_outside_window_defers_to_next_start(self, client, app, monkeypatch):
        """窗口外 → 返回下一个窗口起点（UTC aware），且必须晚于 now。"""
        from datetime import datetime, timedelta, timezone

        from quant_research_engine.gui.saas import agent_api as agent_mod

        cst = timezone(timedelta(hours=8))
        now_h = datetime.now(timezone.utc).astimezone(cst).hour
        closed = (now_h + 2) % 24  # 必然不含当前时刻的一小时窗口
        monkeypatch.setitem(agent_mod.AGENT_DEFAULTS, "nightly_window",
                            f"{closed:02d}:00-{closed:02d}:30 Asia/Shanghai")
        eligible = agent_mod._nightly_eligible_at({"nightly_only": True})
        assert eligible is not None
        assert eligible > datetime.now(timezone.utc)
        local = eligible.astimezone(cst)
        assert local.hour == closed and local.minute == 0

    def test_nightly_only_false_never_defers(self, client, app, monkeypatch):
        from quant_research_engine.gui.saas import agent_api as agent_mod

        monkeypatch.setitem(agent_mod.AGENT_DEFAULTS, "nightly_window", "03:00-03:01 Asia/Shanghai")
        assert agent_mod._nightly_eligible_at({"nightly_only": False}) is None

    def test_nightly_window_parsing_failure_does_not_block(self, client, app, monkeypatch):
        from quant_research_engine.gui.saas import agent_api as agent_mod

        monkeypatch.setitem(agent_mod.AGENT_DEFAULTS, "nightly_window", "垃圾配置")
        assert agent_mod._nightly_eligible_at({"nightly_only": True}) is None

    def test_claim_skips_not_yet_eligible_jobs(self, client, app):
        """夜间窗口核心断言：eligible_at 未到点的 agent job 不被认领，人工 job 不受影响。"""
        from sqlalchemy import text

        from quant_research_engine.gui.saas.app import _get_engine

        _login(client, app, "13800000077")  # 先建一个用户，job 才有归属
        engine = _get_engine(app)
        with engine.begin() as conn:
            uid = conn.execute(text("SELECT id FROM users ORDER BY id LIMIT 1")).scalar_one()
            sid = conn.execute(
                text("INSERT INTO strategies (user_id, name, yaml) VALUES (:u, 's', :y) RETURNING id"),
                {"u": uid, "y": self.BASE_YAML}).scalar_one()
            # 人工 job（eligible_at NULL）+ agent job（1 小时后才可认领）
            human = conn.execute(text(
                "INSERT INTO jobs (user_id, strategy_id, kind, params, status) "
                "VALUES (:u, :s, 'full', '{}'::jsonb, 'queued') RETURNING id"),
                {"u": uid, "s": sid}).scalar_one()
            agent_job = conn.execute(text(
                "INSERT INTO jobs (user_id, strategy_id, kind, params, status, eligible_at) "
                "VALUES (:u, :s, 'full', '{}'::jsonb, 'queued', now() + interval '1 hour') "
                "RETURNING id"), {"u": uid, "s": sid}).scalar_one()
        claim = client.post("/api/worker/jobs/claim",
                            json={"worker_id": "w1", "wait_seconds": 0},
                            headers={"X-Worker-Token": "test-worker-token"})
        picked = claim.get_json()["job"]
        assert picked is not None and picked["id"] == human  # 只领到人工 job
        # 到点后可认领
        with engine.begin() as conn:
            conn.execute(text("UPDATE jobs SET eligible_at = now() - interval '1 minute' "
                              "WHERE id = :i"), {"i": agent_job})
        claim2 = client.post("/api/worker/jobs/claim",
                             json={"worker_id": "w2", "wait_seconds": 0},
                             headers={"X-Worker-Token": "test-worker-token"})
        assert claim2.get_json()["job"]["id"] == agent_job

    # --- 审计 ---
    def test_audit_events_recorded_without_sensitive_fields(self, client, app):
        from sqlalchemy import text

        headers = self._token(client, app)
        run_id = self._run(client, headers)
        assert self._sweep(client, headers, run_id).status_code in (201, 202)
        engine = app.extensions["saas_engine"]
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT endpoint, ok FROM agent_api_events ORDER BY id")).all()
            cols = [r[0] for r in conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'agent_api_events'")).all()]
        assert ("POST /sweeps", True) in [(r[0], r[1]) for r in rows]
        # 最小口径：不落策略文本/令牌明文/原始 IP
        assert set(cols) == {"id", "token_id", "endpoint", "ok", "error_class", "created_at"}

    def test_console_reports_rate_limit_and_nightly(self, client, app):
        headers_agent = self._token(client, app, rate_per_minute=10)
        assert client.get(f"{AGENT_API_PREFIX}/capabilities",
                          headers=headers_agent).status_code == 200
        run_id = self._run(client, headers_agent)
        assert self._sweep(client, headers_agent, run_id, idem="audit-1").status_code in (201, 202)
        admin = _admin_headers(app, "admin2@example.com")
        d = client.get("/api/saas/console/overview", headers=admin).get_json()
        ag = d["agent_api"]
        assert ag["rate_limit_rows"] >= 1
        assert ag["rate_limit_hits"] >= 1
        assert ag["event_total"] >= 1
        assert isinstance(ag["nightly_window_open"], bool)
        assert ag["nightly_pending_jobs"] >= 0


class TestResultAndArtifacts:
    """M5：结果读取（默认不带 chart_data）+ 受控产物下载 + TTL 清理纯函数。"""

    BASE_YAML = (
        "experiment:\n  name: ema_scan\n"
        "data:\n  factor_fields:\n    ema_fast: factors.stock_daily_ta.ema5\n"
        "signal:\n  entry: 'ema_fast > close'\n  exit: 'ema_fast < close'\n"
        "evaluation:\n  forward_return_horizons: [1]\n"
        "holding:\n  max_holding_days: 20\n"
    )

    def _token(self, client, app, scopes=None, target=None, nightly_only=False):
        session = _login(client, app, target or "13800000044")
        token = _create_token(client, session, scopes=scopes or [
            "jobs:submit", "jobs:read", "results:read", "factors:read"],
            nightly_only=nightly_only)["token"]
        return {"Authorization": f"Bearer {token['plaintext']}"}

    def _completed_job(self, client, app, headers, *, with_result=True, chart=True):
        """建会话 + sweep（1 个配置）→ 直接置 completed 并造 results 行。"""
        from sqlalchemy import text

        run = client.post(f"{AGENT_API_PREFIX}/research-runs",
                          json={"title": "结果读取"}, headers=headers)
        run_id = run.get_json()["research_run"]["id"]
        sweep = client.post(f"{AGENT_API_PREFIX}/sweeps", json={
            "research_run_id": run_id,
            "base_yaml": self.BASE_YAML,
            "grid": {"data.factor_fields.ema_fast": ["factors.stock_daily_ta.ema5"]},
            "params": {"random_n": 10, "start": "2024-01-02", "end": "2025-06-30"},
            "idempotency_key": f"res-{run_id}",
        }, headers=headers)
        assert sweep.status_code in (201, 202), sweep.get_json()
        sweep_id = sweep.get_json()["sweep"]["id"]
        engine = app.extensions["saas_engine"]
        with engine.begin() as conn:
            job_id = conn.execute(text(
                "SELECT id FROM jobs WHERE sweep_id = :s ORDER BY id LIMIT 1"),
                {"s": sweep_id}).scalar_one()
            conn.execute(text(
                "UPDATE jobs SET status='completed', started_at=now(), finished_at=now() "
                "WHERE id = :j"), {"j": job_id})
            if with_result:
                chart_data = ({"metrics": {"total_return": 0.31, "sharpe": 0.9},
                               "dates": ["2024-01-02"], "equity": [1.0]} if chart else {})
                conn.execute(text(
                    "INSERT INTO results (job_id, user_id, summary, chart_data, artifacts, "
                    "data_until, result_contract) SELECT id, user_id, "
                    "CAST(:summary AS jsonb), CAST(:chart AS jsonb), "
                    "CAST(:artifacts AS jsonb), DATE '2026-10-30', "
                    "CAST(:contract AS jsonb) FROM jobs WHERE id = :j"),
                    {"summary": '{"total_return": 0.31}', "chart": json.dumps(chart_data),
                     "artifacts": '[{"kind": "excel", "size": 123}]',
                     "contract": '{"version": 1}', "j": job_id})
        return job_id

    def test_result_excludes_chart_data_by_default(self, client, app):
        headers = self._token(client, app)
        job_id = self._completed_job(client, app, headers)
        resp = client.get(f"{AGENT_API_PREFIX}/jobs/{job_id}/result", headers=headers)
        assert resp.status_code == 200
        body = resp.get_json()["result"]
        assert body["summary"]["total_return"] == 0.31
        assert body["data_until"] == "2026-10-30"
        assert body["result_contract"]["version"] == 1
        assert body["artifacts"] == [{"kind": "excel", "size": 123}]
        assert "chart_data" not in body  # 默认不回，避免一次响应打爆 agent
        assert body["chart_data_url"].endswith(f"/jobs/{job_id}/result/chart-data")

    def test_chart_data_on_demand(self, client, app):
        headers = self._token(client, app)
        job_id = self._completed_job(client, app, headers)
        resp = client.get(f"{AGENT_API_PREFIX}/jobs/{job_id}/result/chart-data",
                          headers=headers)
        assert resp.status_code == 200
        chart = resp.get_json()["chart_data"]
        assert chart["metrics"]["total_return"] == 0.31

    def test_uncompleted_job_returns_409(self, client, app):
        from sqlalchemy import text

        headers = self._token(client, app)
        job_id = self._completed_job(client, app, headers, with_result=False)
        engine = app.extensions["saas_engine"]
        with engine.begin() as conn:
            conn.execute(text("UPDATE jobs SET status='queued', finished_at=NULL "
                              "WHERE id = :j"), {"j": job_id})
        resp = client.get(f"{AGENT_API_PREFIX}/jobs/{job_id}/result", headers=headers)
        assert resp.status_code == 409
        assert "未完成" in resp.get_json()["error"]["message"]

    def test_other_users_job_is_404(self, client, app):
        headers_a = self._token(client, app)
        job_id = self._completed_job(client, app, headers_a)
        session_b = _login(client, app, "13800000055")
        token_b = _create_token(client, session_b)["token"]
        headers_b = {"Authorization": f"Bearer {token_b['plaintext']}"}
        for path in (f"{AGENT_API_PREFIX}/jobs/{job_id}/result",
                     f"{AGENT_API_PREFIX}/jobs/{job_id}/result/chart-data",
                     f"{AGENT_API_PREFIX}/jobs/{job_id}/artifacts/equity_curve.csv"):
            assert client.get(path, headers=headers_b).status_code == 404, path

    def test_scope_required_for_results(self, client, app):
        setup = self._token(client, app)  # 全权令牌负责建任务
        job_id = self._completed_job(client, app, setup)
        narrow = self._token(client, app, scopes=["jobs:read"], target="13800000066")
        resp = client.get(f"{AGENT_API_PREFIX}/jobs/{job_id}/result", headers=narrow)
        assert resp.status_code == 403
        assert resp.get_json()["error"]["code"] == "forbidden_scope"

    def test_artifact_traversal_and_missing_rejected(self, client, app, tmp_path):
        headers = self._token(client, app)
        job_id = self._completed_job(client, app, headers)
        app.config["SAAS_UPLOAD_DIR"] = str(tmp_path / "uploads")
        # 目录里放一个正常文件 + 一个 job 目录外的文件
        job_dir = tmp_path / "uploads" / f"job_{job_id}"
        job_dir.mkdir(parents=True)
        (job_dir / "equity_curve.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        (tmp_path / "uploads" / "secret.txt").write_text("nope", encoding="utf-8")
        ok = client.get(f"{AGENT_API_PREFIX}/jobs/{job_id}/artifacts/equity_curve.csv",
                        headers=headers)
        assert ok.status_code == 200
        assert ok.data == b"a,b\n1,2\n"
        for bad in ("../secret.txt", "..%2Fsecret.txt", "secret.txt", ".hidden",
                    "sub/dir.csv"):
            resp = client.get(f"{AGENT_API_PREFIX}/jobs/{job_id}/artifacts/{bad}",
                              headers=headers)
            assert resp.status_code == 404, bad
        # 绝对路径：URL 里的 // 会被 Flask 规范成 308，跟随后仍由白名单判 404；
        # 二者都算「未取到文件」，不放行即可
        resp = client.get(f"{AGENT_API_PREFIX}/jobs/{job_id}/artifacts//etc/passwd",
                          headers=headers, follow_redirects=True)
        assert resp.status_code == 404

    def test_purge_ttl_function_behaviour(self, client, app, tmp_path):
        from sqlalchemy import text

        from quant_research_engine.gui.saas import agent_api as agent_mod

        headers = self._token(client, app)
        job_id = self._completed_job(client, app, headers)
        upload = tmp_path / "uploads"
        (upload / f"job_{job_id}").mkdir(parents=True)
        (upload / f"job_{job_id}" / "a.csv").write_text("x" * 100, encoding="utf-8")
        # 人工 job 的产物目录即使过期也不删
        engine = app.extensions["saas_engine"]
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE jobs SET finished_at = now() - interval '40 days' WHERE id = :j"),
                {"j": job_id})
            uid = conn.execute(text("SELECT id FROM users ORDER BY id LIMIT 1")).scalar_one()
            sid = conn.execute(text(
                "INSERT INTO strategies (user_id, name, yaml) VALUES (:u, 's', :y) RETURNING id"),
                {"u": uid, "y": self.BASE_YAML}).scalar_one()
            human_job = conn.execute(text(
                "INSERT INTO jobs (user_id, strategy_id, kind, params, status, finished_at) "
                "VALUES (:u, :s, 'full', '{}'::jsonb, 'completed', now() - interval '40 days') "
                "RETURNING id"), {"u": uid, "s": sid}).scalar_one()
        (upload / f"job_{human_job}").mkdir(parents=True)
        (upload / f"job_{human_job}" / "keep.csv").write_text("keep", encoding="utf-8")

        report = agent_mod.purge_expired_agent_artifacts(engine, upload_root=upload, ttl_days=15)
        assert report["scanned"] >= 1
        assert report["removed"] >= 1
        assert report["bytes_freed"] >= 100
        assert report["errors"] == 0
        assert not (upload / f"job_{job_id}").exists()      # agent 过期产物已清
        assert (upload / f"job_{human_job}" / "keep.csv").exists()  # 人工产物不碰

    def test_purge_keeps_unexpired(self, client, app, tmp_path):
        from sqlalchemy import text

        from quant_research_engine.gui.saas import agent_api as agent_mod

        headers = self._token(client, app)
        job_id = self._completed_job(client, app, headers)
        upload = tmp_path / "uploads"
        (upload / f"job_{job_id}").mkdir(parents=True)
        (upload / f"job_{job_id}" / "a.csv").write_text("x", encoding="utf-8")
        engine = app.extensions["saas_engine"]
        report = agent_mod.purge_expired_agent_artifacts(engine, upload_root=upload, ttl_days=15)
        assert report["removed"] == 0
        assert (upload / f"job_{job_id}" / "a.csv").exists()


class TestConsoleVisibility:
    """R-ADMIN-001：外部 Agent API 的限额必须在 9090 管理台可见，且与执行同源。"""

    def _admin(self, client, app, email="admin@example.com"):
        return _admin_headers(app, email)

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
        # 未实现的单配置提交不得出现在 paths 里（agent 应走 /sweeps，避免两套提交路径）
        assert "/jobs" not in doc["paths"]
        # 已实现的端点不得带 planned 标注
        for path, method in (("/validate", "post"), ("/research-runs", "post"),
                             ("/sweeps", "post"), ("/sweeps/{sweep_id}/aggregate", "get"),
                             ("/jobs/{job_id}/result", "get"),
                             ("/jobs/{job_id}/artifacts/{name}", "get")):
            assert "x-status" not in doc["paths"][path][method], path
        # 已实现的端点不得带 planned 标注
        for path in ("/validate", "/research-runs", "/sweeps", "/sweeps/{sweep_id}/aggregate"):
            assert "x-status" not in doc["paths"][path][
                "post" if path in ("/validate", "/research-runs", "/sweeps") else "get"], path
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
