"""QRE-SAAS-ACCESS-HARDENING-001（P0-2）：游客会话归属 + 用户侧端点 IDOR 矩阵。

真实本地 PG 临时库（deploy/saas/cloud_schema.sql）。覆盖 brief 目标 2/3/4：
1. 新游客结果归属 = 应用签发的随机 HttpOnly/SameSite=Lax 会话 Cookie
   （qre_guest_sid），与 IP 无关；同 IP 两个游客会话结果互不可见。
2. 旧 IP 归属（guest_key=sha256(IP+salt)）结果在新会话首次创建任务时
   一次性迁移到新会话；迁移后旧 key 不再作为新任务归属、也不再可访问。
3. 全部面向用户的 job/result/symbol GET 端点 IDOR 矩阵：匿名 / 其他用户 /
   本人 / 不存在 / 公开 verified；401/404 语义统一，不泄露任务存在性。
4. 默认私有、worker token、结果合同与 showcase verified 公开语义不变；
   主动分享不做（P1）。
"""

from __future__ import annotations

import json
import subprocess
import uuid
from http.cookies import SimpleCookie

import pytest

from quant_research_engine.gui.saas import create_saas_app
from quant_research_engine.gui.saas.app import (
    GUEST_COOKIE_NAME,
    _guest_key,
    _guest_session_key,
)

WORKER_TOKEN = "test-worker-token"
WORKER_HEADERS = {"X-Worker-Token": WORKER_TOKEN}
IP_A = "1.2.3.4"   # 模拟同一 Wi-Fi / NAT 出口 IP
IP_B = "9.9.9.9"

RESULT_GET_ENDPOINTS = (
    "/api/results/{jid}/summary",
    "/api/results/{jid}/chart-data",
    "/api/results/{jid}/tag-analysis",
    "/api/results/{jid}/risk-analysis",
    "/api/results/{jid}/symbols",
    "/api/results/{jid}/symbols/000001",
    "/api/results/{jid}/symbols/000001/gen-status",
)

# 各结果端点在「本人 + 已完成 + 有归因数据」下的业务状态（鉴权通过后的口径）
OWNER_OK = {
    "/api/results/{jid}/summary": 200,
    "/api/results/{jid}/chart-data": 200,
    "/api/results/{jid}/tag-analysis": 200,
    "/api/results/{jid}/risk-analysis": 200,
    "/api/results/{jid}/symbols": 200,
    "/api/results/{jid}/symbols/000001": 404,          # 无按需产物 → 业务 404（can_generate）
    "/api/results/{jid}/symbols/000001/gen-status": 200,
}


def _psql(db: str, *args: str) -> None:
    subprocess.run(
        ["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def saas_db():
    db_name = f"qre_access_test_{uuid.uuid4().hex[:12]}"
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
def _clean(app):
    from sqlalchemy import text

    from quant_research_engine.gui.saas.app import _get_engine

    engine = _get_engine(app)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE results, jobs, strategies, users, sessions, sms_codes "
                          "RESTART IDENTITY CASCADE"))


def _guest_submit(client, ip=IP_A, codes=("000001.SZ",), start="2025-01-01",
                  end="2026-01-01", kind="full", yaml_text="x"):
    return client.post("/api/jobs", json={
        "yaml": yaml_text, "kind": kind,
        "params": {"codes": list(codes), "start": start, "end": end},
    }, headers={"X-Forwarded-For": ip})


def _guest_cookie(resp) -> tuple[object | None, str]:
    """解析响应里的游客会话 Cookie；返回 (morsel, raw)。"""
    for raw in resp.headers.get_all("Set-Cookie") or []:
        jar = SimpleCookie()
        jar.load(raw)
        if GUEST_COOKIE_NAME in jar:
            return jar[GUEST_COOKIE_NAME], raw
    return None, ""


def _completed_job(client, uid=1, name="classic"):
    """登录用户提交 + worker 回传 → completed（新结果自带 verified 合同）。"""
    resp = client.post("/api/jobs", json={"yaml": "x", "kind": "full", "name": name,
                                          "params": {"start": "2026-01-01", "end": "2026-03-01"}},
                       headers={"X-User-Id": str(uid)})
    job_id = resp.get_json()["job_id"]
    client.post("/api/worker/jobs/claim", json={"worker_id": "w1"}, headers=WORKER_HEADERS)
    chart = {"metrics": {"excess_return": 0.05, "sharpe": 1.2},
             "dates": ["2026-01-05"], "equity": [1.0],
             "tag_analysis": {"ok": True, "layers": {"A": [
                 {"tag": "银行", "total_pnl": 100.0, "trades": 2, "win_rate": 0.5,
                  "avg_ret": 0.01, "symbols_total": 1, "symbols_truncated": False,
                  "symbols": [{"ts_code": "000001.SZ", "name": "平安银行", "total_pnl": 100.0,
                               "trades": 2, "win_rate": 0.5, "avg_ret": 0.01}]}]}}}
    client.post(f"/api/worker/jobs/{job_id}/result/meta",
                json={"worker_id": "w1",
                      "summary": {"strategy_total_return": 0.2, "win_rate": 0.5,
                                  "max_drawdown": -0.1, "total_trade_count": 5},
                      "chart_data": chart, "data_until": "2026-02-27", "files": []},
                headers=WORKER_HEADERS)
    return job_id


def _pin_showcase(app, job_id, active=True):
    from sqlalchemy import text

    from quant_research_engine.gui.saas.app import _ensure_signal_tables, _get_engine

    engine = _get_engine(app)
    _ensure_signal_tables(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO showcase (job_id, title, subtitle, sort_order, is_active) "
                          "VALUES (:id, '经典策略', '副标题', 1, :a)"),
                     {"id": job_id, "a": active})


def _insert_legacy_guest_job(app, ip, *, today=True, completed=True):
    """直接插一条旧形态游客任务（guest_key=sha256(IP+salt)，无 Cookie 时代产物）。"""
    from sqlalchemy import text

    from quant_research_engine.gui.saas.app import _get_engine

    engine = _get_engine(app)
    with engine.begin() as conn:
        sid = conn.execute(
            text("INSERT INTO strategies (user_id, name, yaml) VALUES (NULL, 'legacy', 'y') RETURNING id")
        ).scalar_one()
        jid = conn.execute(
            text("INSERT INTO jobs (user_id, strategy_id, kind, status, params, guest_key, created_at) "
                 "VALUES (NULL, :sid, 'full', :st, CAST(:p AS jsonb), :gk, "
                 + ("now()" if today else "now() - interval '2 days'") + ") RETURNING id"),
            {"sid": sid, "st": "completed" if completed else "queued",
             "p": json.dumps({"start": "2025-01-01", "end": "2026-01-01", "codes": ["000001.SZ"]}),
             "gk": _guest_key(app, ip)},
        ).scalar_one()
        if completed:
            conn.execute(
                text("INSERT INTO results (job_id, user_id, summary, chart_data, data_until) "
                     "VALUES (:j, NULL, CAST(:s AS jsonb), CAST(:c AS jsonb), '2026-01-01')"),
                {"j": jid, "s": json.dumps({"strategy_total_return": 0.1}),
                 "c": json.dumps({"metrics": {"excess_return": 0.02}})})
    return jid


def _guest_key_of(app, job_id):
    from sqlalchemy import text

    from quant_research_engine.gui.saas.app import _get_engine

    with _get_engine(app).connect() as conn:
        return conn.execute(text("SELECT guest_key FROM jobs WHERE id = :i"),
                            {"i": job_id}).scalar_one()


class TestGuestSessionCookie:
    """目标 3：新游客归属 = 随机 HttpOnly/SameSite=Lax 会话 Cookie，与 IP 无关。"""

    def test_submit_issues_random_httponly_cookie(self, client, app):
        resp = _guest_submit(client)
        assert resp.status_code == 200
        morsel, raw = _guest_cookie(resp)
        assert morsel is not None, "游客提交未签发会话 Cookie"
        assert morsel.key == GUEST_COOKIE_NAME
        assert len(morsel.value) >= 32
        assert morsel["httponly"] is True, f"Cookie 须 HttpOnly: {raw}"
        assert morsel["samesite"] == "Lax", f"Cookie 须 SameSite=Lax: {raw}"
        assert int(morsel["max-age"]) > 0
        # 归属键由 Cookie 值派生，且不再是 IP 哈希
        job_id = resp.get_json()["job_id"]
        gk = _guest_key_of(app, job_id)
        assert gk == _guest_session_key(app, morsel.value)
        assert gk != _guest_key(app, IP_A)

    def test_two_sessions_same_ip_get_different_cookies(self, app):
        c1, c2 = app.test_client(), app.test_client()
        r1, r2 = _guest_submit(c1), _guest_submit(c2)
        assert r1.status_code == 200 and r2.status_code == 200
        m1, _ = _guest_cookie(r1)
        m2, _ = _guest_cookie(r2)
        assert m1.value != m2.value

    def test_owner_session_sees_own_job(self, client):
        job_id = _guest_submit(client).get_json()["job_id"]
        assert client.get(f"/api/jobs/{job_id}").status_code == 200
        assert client.get(f"/api/jobs/{job_id}",
                          headers={"X-Forwarded-For": IP_B}).status_code == 200  # 换 IP 不失效

    def test_two_guest_sessions_same_ip_isolated(self, app):
        """同 Wi-Fi 两个游客会话：任务与结果互不可见（防同 IP 互见）。"""
        c1, c2 = app.test_client(), app.test_client()
        job1 = _guest_submit(c1).get_json()["job_id"]
        job2 = _guest_submit(c2, ip=IP_A, codes=("600000.SH",)).get_json()["job_id"]
        # 互访任务详情 → 401
        assert c2.get(f"/api/jobs/{job1}").status_code == 401
        assert c1.get(f"/api/jobs/{job2}").status_code == 401
        # 各自都能看自己的
        assert c1.get(f"/api/jobs/{job1}").status_code == 200
        assert c2.get(f"/api/jobs/{job2}").status_code == 200
        # worker 完成两者 → 结果端点同样隔离
        for jid in (job1, job2):
            client_post = c1 if jid == job1 else c2
            client_post.post("/api/worker/jobs/claim", json={"worker_id": "w1"},
                             headers=WORKER_HEADERS)
            client_post.post(f"/api/worker/jobs/{jid}/result/meta",
                             json={"worker_id": "w1", "summary": {"strategy_total_return": 0.1},
                                   "chart_data": {"metrics": {}}, "files": []},
                             headers=WORKER_HEADERS)
        assert c1.get(f"/api/results/{job1}/summary").status_code == 200
        assert c2.get(f"/api/results/{job1}/summary").status_code == 401
        assert c2.get(f"/api/results/{job2}/summary").status_code == 200
        assert c1.get(f"/api/results/{job2}/summary").status_code == 401
        # 游客删除同样按会话隔离
        assert c2.delete(f"/api/results/{job1}").status_code == 404
        assert c1.delete(f"/api/results/{job1}").status_code == 200

    def test_cookieless_same_ip_cannot_see(self, app):
        """没有会话 Cookie 的请求（哪怕同 IP）不能再按 IP 看到他人游客结果。"""
        owner = app.test_client()
        job_id = _guest_submit(owner).get_json()["job_id"]
        stranger = app.test_client()  # 同 IP、无 Cookie
        assert stranger.get(f"/api/jobs/{job_id}",
                            headers={"X-Forwarded-For": IP_A}).status_code == 401
        assert stranger.get(f"/api/results/{job_id}/summary",
                            headers={"X-Forwarded-For": IP_A}).status_code == 401

    def test_logged_in_user_cannot_see_guest_job(self, client, app):
        job_id = _guest_submit(client).get_json()["job_id"]
        assert client.get(f"/api/jobs/{job_id}", headers={"X-User-Id": "2"}).status_code == 404
        assert client.get(f"/api/results/{job_id}/summary",
                          headers={"X-User-Id": "2"}).status_code == 404


class TestLegacyGuestMigration:
    """目标 4：旧 IP 归属结果一次性迁移到新会话；之后旧 key 不再用于新任务。"""

    def test_legacy_job_migrates_once_on_new_session_submit(self, client, app):
        legacy_id = _insert_legacy_guest_job(app, IP_A, today=False)
        assert _guest_key_of(app, legacy_id) == _guest_key(app, IP_A)
        # 新会话（无 Cookie）在同一 IP 首次创建任务 → 触发一次性迁移
        resp = _guest_submit(client)
        assert resp.status_code == 200
        morsel, _ = _guest_cookie(resp)
        new_key = _guest_session_key(app, morsel.value)
        assert _guest_key_of(app, legacy_id) == new_key
        # 新会话可看迁移来的旧结果
        assert client.get(f"/api/jobs/{legacy_id}").status_code == 200
        assert client.get(f"/api/results/{legacy_id}/summary").status_code == 200
        # 第二个新会话（同 IP）看不到已迁移的旧结果（一次性 + 会话隔离）
        other = app.test_client()
        assert other.get(f"/api/jobs/{legacy_id}",
                         headers={"X-Forwarded-For": IP_A}).status_code == 401
        # 迁移后旧 IP key 不再匹配任何东西（无 Cookie 同 IP 也 401）
        cookieless = app.test_client()
        assert cookieless.get(f"/api/jobs/{legacy_id}",
                              headers={"X-Forwarded-For": IP_A}).status_code == 401

    def test_migration_not_triggered_by_get(self, client, app):
        """只读请求不迁移：旧结果仍等原访客下次创建任务时迁移。"""
        legacy_id = _insert_legacy_guest_job(app, IP_A)
        stranger = app.test_client()
        assert stranger.get(f"/api/jobs/{legacy_id}",
                            headers={"X-Forwarded-For": IP_A}).status_code == 401
        assert _guest_key_of(app, legacy_id) == _guest_key(app, IP_A)  # 未迁移
        # 原访客自己来创建任务 → 迁移
        _guest_submit(client)
        assert _guest_key_of(app, legacy_id) != _guest_key(app, IP_A)
        assert client.get(f"/api/jobs/{legacy_id}").status_code == 200

    def test_migrated_today_job_counts_toward_guest_daily_limit(self, client, app):
        """今日旧形态全量任务迁移后计入新会话当日配额（先迁移后计数）。"""
        legacy_id = _insert_legacy_guest_job(app, IP_A, today=True)
        resp = _guest_submit(client)  # 同一会话当日第 2 个 full → 403
        assert resp.status_code == 403
        # 403 响应同样带上会话 Cookie（否则浏览器拿不到迁移后的归属）
        morsel, _ = _guest_cookie(resp)
        assert morsel is not None, "403 也必须带会话 Cookie（迁移后的归属）"
        new_key = _guest_session_key(app, morsel.value)
        assert _guest_key_of(app, legacy_id) == new_key  # 已迁移到本会话
        assert client.get(f"/api/jobs/{legacy_id}").status_code == 200

    def test_migration_is_idempotent_for_second_submit(self, client, app):
        _insert_legacy_guest_job(app, IP_A, today=False)
        first = _guest_submit(client)
        assert first.status_code == 200
        # 同会话再次提交（smoke 不占配额）：迁移不重复、不出错
        second = _guest_submit(client, kind="smoke")
        assert second.status_code == 200
        assert client.get("/api/jobs").status_code == 401  # 游客无列表口径不变


class TestResultEndpointIdorMatrix:
    """目标 2：全部面向用户的结果 GET 端点 IDOR 矩阵。"""

    def test_private_job_matrix(self, client, app):
        jid = _completed_job(client)
        anon = app.test_client()
        for path in RESULT_GET_ENDPOINTS:
            url = path.format(jid=jid)
            # 匿名（无会话）→ 401
            assert anon.get(url).status_code == 401, url
            # 其他用户 → 404（与不存在一视同仁）
            other = client.get(url, headers={"X-User-Id": "2"})
            assert other.status_code == 404, url
            # 本人 → 业务状态
            owner = client.get(url, headers={"X-User-Id": "1"})
            assert owner.status_code == OWNER_OK[path], url
            # 不存在的 job → 同样 401/404，且错误体与"他人任务"一致（不泄露存在性）
            missing = path.format(jid=jid + 9999)
            assert anon.get(missing).status_code == 401
            assert anon.get(missing).get_json() == anon.get(url).get_json()
            other_missing = client.get(missing, headers={"X-User-Id": "2"})
            assert other_missing.status_code == 404
            assert other_missing.get_json() == other.get_json()

    def test_showcase_verified_public_readonly(self, client, app):
        """公开 verified：匿名/他人 200 只读，本人 200 非只读（P0-1B 语义不变）。"""
        jid = _completed_job(client)
        _pin_showcase(app, jid)
        anon = app.test_client()
        for path in RESULT_GET_ENDPOINTS:
            url = path.format(jid=jid)
            a = anon.get(url)
            o = client.get(url, headers={"X-User-Id": "2"})
            if OWNER_OK[path] == 200:
                assert a.status_code == 200, url
                assert o.status_code == 200, url
                if path.endswith("/summary"):
                    # readonly 旗标只在 summary 与按需产物缺失的 404 体上回带
                    assert a.get_json().get("readonly") is True, url
                    assert o.get_json().get("readonly") is True, url
            else:  # symbols/<code> 业务 404（can_generate），带 readonly 标记
                assert a.status_code == 404, url
                assert a.get_json().get("can_generate") is True, url
                assert a.get_json().get("readonly") is True, url
            owner = client.get(url, headers={"X-User-Id": "1"})
            assert owner.status_code == OWNER_OK[path], url
            if OWNER_OK[path] == 200 and path.endswith("/summary"):
                assert owner.get_json().get("readonly") is False, url

    def test_showcase_unverified_not_public(self, client, app):
        """白名单但未验证：公开不可见，且与未挂白名单同样 401/404（不泄露存在性）。"""
        from sqlalchemy import text

        from quant_research_engine.gui.saas.app import _get_engine

        engine = _get_engine(app)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO users (id, tier, role) VALUES (1, 'member', 'user') "
                              "ON CONFLICT (id) DO NOTHING"))
            sid = conn.execute(
                text("INSERT INTO strategies (user_id, name, yaml) VALUES (1, 'u', 'y') RETURNING id")
            ).scalar_one()
            jid = conn.execute(
                text("INSERT INTO jobs (user_id, strategy_id, kind, status, params) "
                     "VALUES (1, :sid, 'full', 'completed', CAST(:p AS jsonb)) RETURNING id"),
                {"sid": sid, "p": json.dumps({"start": "2026-01-01", "end": "2026-03-01"})},
            ).scalar_one()
            conn.execute(
                text("INSERT INTO results (job_id, user_id, summary, chart_data, data_until) "
                     "VALUES (:j, 1, '{}', '{}', '2026-02-27')"), {"j": jid})
        _pin_showcase(app, jid)
        anon = app.test_client()
        assert anon.get(f"/api/results/{jid}/summary").status_code == 401
        assert client.get(f"/api/results/{jid}/summary",
                          headers={"X-User-Id": "2"}).status_code == 404
        assert client.get(f"/api/results/{jid}/summary",
                          headers={"X-User-Id": "1"}).status_code == 200
        # 公开列表同样不出现未验证项
        assert all(it["job_id"] != jid for it in
                   client.get("/api/saas/showcase").get_json()["items"])

    def test_guest_session_result_endpoints(self, client, app):
        """游客自己的完成结果：带会话 Cookie 全端点可读，异会话 401。"""
        job_id = _guest_submit(client).get_json()["job_id"]
        client.post("/api/worker/jobs/claim", json={"worker_id": "w1"}, headers=WORKER_HEADERS)
        client.post(f"/api/worker/jobs/{job_id}/result/meta",
                    json={"worker_id": "w1", "summary": {"strategy_total_return": 0.1},
                          "chart_data": {"metrics": {"excess_return": 0.05}}, "files": []},
                    headers=WORKER_HEADERS)
        for path in RESULT_GET_ENDPOINTS:
            url = path.format(jid=job_id)
            assert client.get(url).status_code in (200, 404), url
        stranger = app.test_client()
        for path in RESULT_GET_ENDPOINTS:
            assert stranger.get(path.format(jid=job_id)).status_code == 401


class TestJobDetailIdor:
    """GET /api/jobs/<id>（含 /api/saas/jobs/<id> 别名）矩阵。"""

    @pytest.mark.parametrize("url", ["/api/jobs/{jid}", "/api/saas/jobs/{jid}"])
    def test_private_job_matrix(self, client, app, url):
        resp = client.post("/api/jobs", json={"yaml": "x", "kind": "full", "name": "t",
                                              "params": {"start": "2026-01-01", "end": "2026-03-01"}},
                           headers={"X-User-Id": "1"})
        jid = resp.get_json()["job_id"]
        anon = app.test_client()
        assert anon.get(url.format(jid=jid)).status_code == 401
        other = client.get(url.format(jid=jid), headers={"X-User-Id": "2"})
        assert other.status_code == 404
        assert client.get(url.format(jid=jid), headers={"X-User-Id": "1"}).status_code == 200
        # 不存在与他人一致
        missing = url.format(jid=jid + 9999)
        assert anon.get(missing).status_code == 401
        assert anon.get(missing).get_json() == anon.get(url.format(jid=jid)).get_json()
        other_missing = client.get(missing, headers={"X-User-Id": "2"})
        assert other_missing.status_code == 404
        assert other_missing.get_json() == other.get_json()

    def test_guest_job_matrix(self, client, app):
        jid = _guest_submit(client).get_json()["job_id"]
        anon = app.test_client()
        assert anon.get(f"/api/jobs/{jid}").status_code == 401
        assert client.get(f"/api/jobs/{jid}", headers={"X-User-Id": "2"}).status_code == 404
        assert client.get(f"/api/jobs/{jid}").status_code == 200


class TestListAndAdjacentEndpoints:
    """列表/策略/信号等相邻用户侧 GET：匿名 401、按归属隔离。"""

    LIST_ENDPOINTS = (
        "/api/jobs",
        "/api/results",
        "/api/saas/strategies",
        "/api/saas/signals",
        "/api/saas/signals/unread-count",
        "/api/saas/factor-requests",
        "/api/saas/feedback",
        "/api/saas/me",
    )

    @pytest.mark.parametrize("url", LIST_ENDPOINTS)
    def test_lists_require_login(self, client, url):
        assert client.get(url).status_code == 401

    def test_lists_scoped_to_owner(self, client, app):
        _completed_job(client, uid=1, name="u1")
        _completed_job(client, uid=2, name="u2")
        r1 = client.get("/api/results", headers={"X-User-Id": "1"}).get_json()
        r2 = client.get("/api/results", headers={"X-User-Id": "2"}).get_json()
        assert [i["strategy_name"] for i in r1["items"]] == ["u1"]
        assert [i["strategy_name"] for i in r2["items"]] == ["u2"]
        j1 = client.get("/api/jobs", headers={"X-User-Id": "1"}).get_json()["jobs"]
        j2 = client.get("/api/jobs", headers={"X-User-Id": "2"}).get_json()["jobs"]
        assert all(j["user_id"] == 1 for j in j1)
        assert all(j["user_id"] == 2 for j in j2)

    def test_strategy_detail_idor(self, client, app):
        resp = client.post("/api/saas/strategies", json={"name": "s1", "yaml": "signal:\n  entry: true\n"},
                           headers={"X-User-Id": "1"})
        sid = resp.get_json()["strategy_id"]
        anon = app.test_client()
        for url in (f"/api/saas/strategies/{sid}", f"/api/saas/strategies/{sid}/detail"):
            assert anon.get(url).status_code == 401, url
            other = client.get(url, headers={"X-User-Id": "2"})
            assert other.status_code == 404, url
            missing = url.replace(str(sid), str(sid + 9999))
            assert anon.get(missing).status_code == 401
            other_missing = client.get(missing, headers={"X-User-Id": "2"})
            assert other_missing.status_code == 404
            assert other_missing.get_json() == other.get_json()
            assert client.get(url, headers={"X-User-Id": "1"}).status_code == 200, url


class TestWriteSurfacesUnchanged:
    """写/删表面语义不变：默认私有、showcase 只读、游客按会话删除。"""

    def test_delete_matrix(self, client, app):
        jid = _completed_job(client)
        anon = app.test_client()
        assert anon.delete(f"/api/results/{jid}").status_code == 404
        assert client.delete(f"/api/results/{jid}", headers={"X-User-Id": "2"}).status_code == 404
        assert client.delete(f"/api/results/{jid}", headers={"X-User-Id": "1"}).status_code == 200
        assert client.delete(f"/api/results/{jid}", headers={"X-User-Id": "1"}).status_code == 404

    def test_showcase_generate_readonly(self, client, app):
        jid = _completed_job(client)
        _pin_showcase(app, jid)
        for headers in ({}, {"X-User-Id": "2"}):
            resp = client.post(f"/api/results/{jid}/symbols/000001/generate", headers=headers)
            assert resp.status_code == 403
            assert resp.get_json()["error"] == "经典策略为只读展示"

    def test_worker_token_unchanged(self, client):
        assert client.post("/api/worker/jobs/claim", json={"worker_id": "w"},
                           headers={"X-Worker-Token": "wrong"}).status_code == 401
        assert client.post("/api/worker/jobs/claim", json={"worker_id": "w"},
                           headers=WORKER_HEADERS).status_code == 200


class TestGuestNlLimitStaysIpBased:
    """游客 NL 编译限流保持 IP 口径（成本控制，不随归属改造改动）。"""

    def test_nl_counter_keyed_by_ip(self, app, tmp_path, monkeypatch):
        from quant_research_engine.gui.saas import app as app_mod

        monkeypatch.setattr(app_mod, "GUEST_NL_DAILY_LIMIT", 1)
        monkeypatch.setenv("QRE_GUEST_NL_COUNTER", str(tmp_path / "nl.json"))
        assert app_mod._guest_nl_hit(app, IP_A) is True
        assert app_mod._guest_nl_hit(app, IP_A) is False   # 同 IP 超限
        assert app_mod._guest_nl_hit(app, IP_B) is True     # 异 IP 独立计数
