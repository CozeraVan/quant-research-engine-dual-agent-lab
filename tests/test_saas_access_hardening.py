"""QRE-SAAS-ACCESS-HARDENING-001（P0-2）：游客会话归属 + 用户侧端点 IDOR 矩阵。

真实本地 PG 临时库（deploy/saas/cloud_schema.sql）。覆盖 brief 目标 2/3/4：
1. 新游客结果归属 = 应用签发的随机 HttpOnly/SameSite=Lax 会话 Cookie
   （qre_guest_sid），与 IP 无关；同 IP 两个游客会话结果互不可见。
2. 旧 IP 归属（guest_key=sha256(IP+salt)）结果在新会话首次创建任务时
   一次性迁移到新会话；迁移后旧 key 不再作为新任务归属、也不再可访问。
3. 全部面向用户的 job/result/symbol GET 端点 IDOR 矩阵：匿名 / 其他用户 /
   本人 / 不存在 / 公开 verified；401/404 语义统一，不泄露任务存在性。
4. 默认私有、worker token、结果合同与 showcase verified 公开语义不变。

QRE-SAAS-READONLY-SHARE（P1）：登录用户可把本人已完成结果分享为可撤销的
只读链接（share_links：只存完整 token 哈希，明文仅创建响应一次）。覆盖：
创建准入（游客 401/他人不存在 404/未完成 409/有效期 allowlist/未验证可分享）、
存储（仅 64 位哈希、列表不回 hash/token）、公开只读通道（有效 token 匿名
可读允许的结果 GET、readonly_kind=share、异 job 不降级、不开放列表/策略/
worker/console）、失效（过期/撤销/错 token 与不存在同体）、写保护
（generate 403、delete/cancel/save/watch 原权限）、CASCADE 与前端 Node。
"""

from __future__ import annotations

import json
import re
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
        conn.execute(text("TRUNCATE results, jobs, strategies, users, sessions, sms_codes, "
                          "share_links RESTART IDENTITY CASCADE"))


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


# --- QRE-SAAS-READONLY-SHARE（P1）：可撤销只读分享 ---

SHARE_CREATE_URL = "/api/saas/jobs/{jid}/share-links"
SHARE_LIST_URL = "/api/saas/share-links"


def _create_share(client, job_id, days=7, uid=None, payload=None):
    body = {"expires_days": days} if payload is None else payload
    headers = {"X-User-Id": str(uid)} if uid is not None else {}
    return client.post(SHARE_CREATE_URL.format(jid=job_id), json=body, headers=headers)


def _share_token_of(resp) -> str:
    url = resp.get_json()["url"]
    assert "?share=" in url, f"创建响应必须带明文 token URL: {url}"
    return url.split("?share=", 1)[1]


def _share_rows(app):
    from sqlalchemy import text

    from quant_research_engine.gui.saas.app import _get_engine

    with _get_engine(app).connect() as conn:
        return [dict(r) for r in conn.execute(text(
            "SELECT * FROM share_links ORDER BY id")).mappings().all()]


def _share_columns(app):
    from sqlalchemy import text

    from quant_research_engine.gui.saas.app import _get_engine

    with _get_engine(app).connect() as conn:
        return {r[0] for r in conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'share_links'"))}


def _insert_unverified_job(app, uid=1):
    """直接插一条本人 completed 任务但无 result_contract（未验证口径）。"""
    from sqlalchemy import text

    from quant_research_engine.gui.saas.app import _get_engine

    engine = _get_engine(app)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, tier, role) VALUES (:u, 'member', 'user') "
                          "ON CONFLICT (id) DO NOTHING"), {"u": uid})
        sid = conn.execute(
            text("INSERT INTO strategies (user_id, name, yaml) VALUES (:u, 'unverified', 'y') RETURNING id"),
            {"u": uid},
        ).scalar_one()
        jid = conn.execute(
            text("INSERT INTO jobs (user_id, strategy_id, kind, status, params) "
                 "VALUES (:u, :sid, 'full', 'completed', CAST(:p AS jsonb)) RETURNING id"),
            {"u": uid, "sid": sid, "p": json.dumps({"start": "2026-01-01", "end": "2026-03-01"})},
        ).scalar_one()
        conn.execute(
            text("INSERT INTO results (job_id, user_id, summary, chart_data, data_until) "
                 "VALUES (:j, :u, CAST(:s AS jsonb), CAST(:c AS jsonb), '2026-02-27')"),
            {"j": jid, "u": uid, "s": json.dumps({"strategy_total_return": 0.1}),
             "c": json.dumps({"metrics": {"excess_return": 0.02}})})
    return jid


def _set_share_expires(app, link_id, delta_sql):
    from sqlalchemy import text

    from quant_research_engine.gui.saas.app import _get_engine

    with _get_engine(app).begin() as conn:
        conn.execute(
            text("UPDATE share_links SET expires_at = now() + " + delta_sql + " WHERE id = :i"),
            {"i": link_id})


class TestShareLinkCreate:
    """创建准入：游客 401、他人/不存在 404、未完成 409、有效期 allowlist。"""

    def test_guest_cannot_create(self, client):
        jid = _guest_submit(client).get_json()["job_id"]
        resp = _create_share(client, jid)  # 无登录态
        assert resp.status_code == 401
        assert resp.get_json() == {"ok": False, "error": "未登录"}

    def test_other_and_missing_404(self, client):
        jid = _completed_job(client)
        other = _create_share(client, jid, uid=2)
        assert other.status_code == 404
        missing = _create_share(client, jid + 9999, uid=2)
        assert missing.status_code == 404
        assert missing.get_json() == other.get_json()

    def test_incomplete_409(self, client):
        resp = client.post("/api/jobs", json={"yaml": "x", "kind": "full",
                                              "params": {"start": "2026-01-01", "end": "2026-03-01"}},
                           headers={"X-User-Id": "1"})
        jid = resp.get_json()["job_id"]
        r = _create_share(client, jid, uid=1)
        assert r.status_code == 409

    def test_expires_allowlist(self, client):
        jid = _completed_job(client)
        for days in (1, 7, 30, 0):
            r = _create_share(client, jid, days=days, uid=1)
            assert r.status_code == 200, days
            body = r.get_json()
            assert body["ok"] is True and body["id"] and "?share=" in body["url"]
            if days == 0:
                assert body["expires_at"] is None
            else:
                assert body["expires_at"]
        for bad in (3, 365, -1, "abc", None, 1.5):
            r = _create_share(client, jid, uid=1, payload={"expires_days": bad})
            assert r.status_code == 400, bad
        # 缺省默认 7 天
        r = _create_share(client, jid, uid=1, payload={})
        assert r.status_code == 200 and r.get_json()["expires_at"]

    def test_unverified_result_shareable_and_contract_kept(self, client, app):
        jid = _insert_unverified_job(app)
        r = _create_share(client, jid, uid=1)
        assert r.status_code == 200
        token = _share_token_of(r)
        anon = app.test_client()
        summary = anon.get(f"/api/results/{jid}/summary?share={token}")
        assert summary.status_code == 200
        contract = summary.get_json()["result_contract"]
        assert contract["verified"] is False, "未验证徽标不得因分享被隐藏"
        assert contract["label"] == "旧口径·未验证"

    def test_response_is_only_plaintext_token_surface(self, client, app):
        jid = _completed_job(client)
        r = _create_share(client, jid, uid=1)
        body = r.get_json()
        assert set(body) >= {"ok", "id", "url", "expires_at"}
        assert "token_hash" not in body and "token" not in body
        rows = _share_rows(app)
        assert len(rows) == 1
        assert rows[0]["token_hash"] not in json.dumps(body)


class TestShareLinkStorage:
    """存储形态：DB 只有 64 位哈希；列表不回 hash/明文。"""

    def test_columns_minimal(self, client, app):
        jid = _completed_job(client)
        _create_share(client, jid, uid=1)
        cols = _share_columns(app)
        assert cols == {"id", "token_hash", "job_id", "owner_id",
                        "expires_at", "revoked_at", "created_at"}, cols

    def test_only_full_hash_stored(self, client, app):
        import hashlib
        import re as _re

        from quant_research_engine.gui.saas.app import _auth_salt

        jid = _completed_job(client)
        r1 = _create_share(client, jid, uid=1)
        t1 = _share_token_of(r1)
        r2 = _create_share(client, jid, uid=1)
        t2 = _share_token_of(r2)
        rows = _share_rows(app)
        assert len(rows) == 2
        for row in rows:
            assert _re.fullmatch(r"[0-9a-f]{64}", row["token_hash"]), row["token_hash"]
        hashes = {row["token_hash"] for row in rows}
        assert hashes == {
            hashlib.sha256(f"share:{t1}:{_auth_salt(app)}".encode()).hexdigest(),
            hashlib.sha256(f"share:{t2}:{_auth_salt(app)}".encode()).hexdigest(),
        }
        # 明文不出现在任何存储字段
        blob = json.dumps(rows, default=str)
        assert t1 not in blob and t2 not in blob

    def test_list_hides_token_and_scoped(self, client, app):
        jid = _completed_job(client)
        _create_share(client, jid, uid=1)
        _completed_job(client, uid=2, name="u2")
        r = client.get(SHARE_LIST_URL, headers={"X-User-Id": "1"})
        assert r.status_code == 200
        items = r.get_json()["items"]
        assert len(items) == 1
        item = items[0]
        assert set(item) == {"id", "job_id", "strategy_name", "created_at",
                             "expires_at", "revoked_at", "status"}, item
        assert item["job_id"] == jid and item["status"] == "active"
        assert "token_hash" not in item
        other = client.get(SHARE_LIST_URL, headers={"X-User-Id": "2"})
        assert other.get_json()["items"] == []
        assert client.get(SHARE_LIST_URL).status_code == 401

    def test_status_transitions(self, client, app):
        jid = _completed_job(client)
        created = _create_share(client, jid, uid=1).get_json()
        _set_share_expires(app, created["id"], "interval '-1 day'")
        items = client.get(SHARE_LIST_URL, headers={"X-User-Id": "1"}).get_json()["items"]
        assert items[0]["status"] == "expired"
        assert client.post(f"/api/saas/share-links/{created['id']}/revoke",
                           headers={"X-User-Id": "1"}).status_code == 200
        items = client.get(SHARE_LIST_URL, headers={"X-User-Id": "1"}).get_json()["items"]
        assert items[0]["status"] == "revoked" and items[0]["revoked_at"]


class TestShareLinkRevoke:
    """撤销：仅创建者；重复/他人/不存在统一 404；立即失效。"""

    def test_revoke_invalidates_immediately(self, client, app):
        jid = _completed_job(client)
        token = _share_token_of(_create_share(client, jid, uid=1))
        link_id = _share_rows(app)[0]["id"]
        anon = app.test_client()
        assert anon.get(f"/api/results/{jid}/summary?share={token}").status_code == 200
        assert client.post(f"/api/saas/share-links/{link_id}/revoke",
                           headers={"X-User-Id": "1"}).status_code == 200
        after = anon.get(f"/api/results/{jid}/summary?share={token}")
        assert after.status_code == 401
        # 与"错误 token"响应逐字节一致（不泄露链接状态）
        wrong = anon.get(f"/api/results/{jid}/summary?share=nope")
        assert after.get_json() == wrong.get_json()

    def test_repeat_and_other_and_missing_404(self, client, app):
        jid = _completed_job(client)
        _create_share(client, jid, uid=1)
        link_id = _share_rows(app)[0]["id"]
        first = client.post(f"/api/saas/share-links/{link_id}/revoke",
                            headers={"X-User-Id": "1"})
        assert first.status_code == 200
        assert client.post(f"/api/saas/share-links/{link_id}/revoke",
                           headers={"X-User-Id": "1"}).status_code == 404
        assert client.post(f"/api/saas/share-links/{link_id}/revoke",
                           headers={"X-User-Id": "2"}).status_code == 404
        assert client.post("/api/saas/share-links/999999/revoke",
                           headers={"X-User-Id": "1"}).status_code == 404
        assert client.post(f"/api/saas/share-links/{link_id}/revoke").status_code == 401


class TestShareLinkReadChannel:
    """公开只读通道：有效 token 匿名可读；异 job 不降级；列表/写表面不开放。"""

    def test_valid_token_anonymous_reads(self, client, app):
        jid = _completed_job(client)
        token = _share_token_of(_create_share(client, jid, uid=1))
        anon = app.test_client()
        for path in RESULT_GET_ENDPOINTS:
            url = path.format(jid=jid) + f"?share={token}"
            resp = anon.get(url)
            assert resp.status_code == OWNER_OK[path], url
            if path.endswith("/summary"):
                body = resp.get_json()
                assert body["readonly"] is True
                assert body["readonly_kind"] == "share"

    def test_valid_token_other_logged_in_reads(self, client, app):
        jid = _completed_job(client)
        token = _share_token_of(_create_share(client, jid, uid=1))
        resp = client.get(f"/api/results/{jid}/summary?share={token}",
                          headers={"X-User-Id": "2"})
        assert resp.status_code == 200
        assert resp.get_json()["readonly_kind"] == "share"

    def test_owner_normal_access_has_no_readonly_mark(self, client):
        jid = _completed_job(client)
        body = client.get(f"/api/results/{jid}/summary",
                          headers={"X-User-Id": "1"}).get_json()
        assert body["readonly"] is False
        assert body.get("readonly_kind") is None

    def test_job_a_token_on_job_b_denied(self, client, app):
        jid_a = _completed_job(client, name="a")
        jid_b = _completed_job(client, name="b")
        token = _share_token_of(_create_share(client, jid_a, uid=1))
        anon = app.test_client()
        for path in RESULT_GET_ENDPOINTS:
            url = path.format(jid=jid_b) + f"?share={token}"
            assert anon.get(url).status_code == 401, url
            other = client.get(url, headers={"X-User-Id": "2"})
            assert other.status_code == 404, url

    def test_invalid_token_does_not_degrade(self, client, app):
        jid = _completed_job(client)
        _create_share(client, jid, uid=1)
        anon = app.test_client()
        plain = anon.get(f"/api/results/{jid}/summary")
        bad = anon.get(f"/api/results/{jid}/summary?share=bogus-token")
        assert plain.status_code == 401 and bad.status_code == 401
        assert bad.get_json() == plain.get_json()
        other_plain = client.get(f"/api/results/{jid}/summary", headers={"X-User-Id": "2"})
        other_bad = client.get(f"/api/results/{jid}/summary?share=bogus-token",
                               headers={"X-User-Id": "2"})
        assert other_plain.status_code == 404 and other_bad.status_code == 404
        assert other_bad.get_json() == other_plain.get_json()

    def test_expired_token_denied_like_missing(self, client, app):
        jid = _completed_job(client)
        created = _create_share(client, jid, uid=1).get_json()
        token = _share_token_of(_create_share(client, jid, days=1, uid=1))
        _set_share_expires(app, created["id"], "interval '-1 minute'")
        # 注意：上面创建的第二个链接也置过去（同 job 两条，取最新一条过期）
        from sqlalchemy import text

        from quant_research_engine.gui.saas.app import _get_engine

        with _get_engine(app).begin() as conn:
            conn.execute(text("UPDATE share_links SET expires_at = now() - interval '1 day'"))
        anon = app.test_client()
        resp = anon.get(f"/api/results/{jid}/summary?share={token}")
        assert resp.status_code == 401
        assert resp.get_json() == anon.get(f"/api/results/{jid}/summary").get_json()

    def test_no_list_or_admin_surface_opened(self, client, app):
        jid = _completed_job(client)
        token = _share_token_of(_create_share(client, jid, uid=1))
        anon = app.test_client()
        for url in ("/api/results", "/api/jobs", "/api/saas/strategies",
                    "/api/saas/share-links", "/api/saas/signals", "/api/saas/me",
                    "/api/saas/console/overview", "/api/saas/console/users"):
            assert anon.get(url + f"?share={token}").status_code == 401, url
        assert anon.post("/api/worker/jobs/claim", json={"worker_id": "w"}).status_code == 401
        assert anon.post("/api/worker/jobs/claim", json={"worker_id": "w"},
                         headers={"X-Worker-Token": "wrong"}).status_code == 401

    def test_write_surfaces_still_denied(self, client, app):
        jid = _completed_job(client)
        token = _share_token_of(_create_share(client, jid, uid=1))
        anon = app.test_client()
        qs = f"?share={token}"
        gen = anon.post(f"/api/results/{jid}/symbols/000001/generate" + qs)
        assert gen.status_code == 403
        assert "只读" in gen.get_json()["error"]
        assert anon.delete(f"/api/results/{jid}" + qs).status_code == 404
        assert anon.post(f"/api/saas/jobs/{jid}/cancel" + qs).status_code == 401
        assert anon.post(f"/api/saas/share-links/1/revoke" + qs).status_code == 401
        # 他人登录态同样不能借分享链接写
        assert client.post(f"/api/results/{jid}/symbols/000001/generate" + qs,
                           headers={"X-User-Id": "2"}).status_code == 403
        assert client.delete(f"/api/results/{jid}" + qs,
                             headers={"X-User-Id": "2"}).status_code == 404
        assert client.post(f"/api/saas/jobs/{jid}/cancel" + qs,
                           headers={"X-User-Id": "2"}).status_code == 404

    def test_share_and_showcase_kinds_distinct(self, client, app):
        jid = _completed_job(client)
        _pin_showcase(app, jid)
        token = _share_token_of(_create_share(client, jid, uid=1))
        anon = app.test_client()
        showcase = anon.get(f"/api/results/{jid}/summary").get_json()
        assert showcase["readonly_kind"] == "showcase"
        share = anon.get(f"/api/results/{jid}/summary?share={token}").get_json()
        assert share["readonly_kind"] == "share"
        # 分享视图的 generate 同样 403（showcase 文案不变）
        sc = anon.post(f"/api/results/{jid}/symbols/000001/generate")
        assert sc.status_code == 403 and sc.get_json()["error"] == "经典策略为只读展示"


class TestShareLinkCascade:
    """级联与游客边界。"""

    def test_delete_job_removes_share_links(self, client, app):
        jid = _completed_job(client)
        token = _share_token_of(_create_share(client, jid, uid=1))
        assert len(_share_rows(app)) == 1
        assert client.delete(f"/api/results/{jid}",
                             headers={"X-User-Id": "1"}).status_code == 200
        assert _share_rows(app) == []
        anon = app.test_client()
        assert anon.get(f"/api/results/{jid}/summary?share={token}").status_code == 401

    def test_guest_session_cannot_create_share(self, client):
        jid = _guest_submit(client).get_json()["job_id"]
        resp = client.post(SHARE_CREATE_URL.format(jid=jid), json={"expires_days": 7})
        assert resp.status_code == 401


def _node() -> str:
    import shutil
    from pathlib import Path

    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    return node


def _run_node(script: str) -> None:
    import subprocess

    result = subprocess.run([_node(), "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


def _job_share_source(html: str) -> str:
    match = re.search(r"(// --- P1 只读分享[\s\S]*?)\nif \(new URLSearchParams", html)
    assert match, "未找到 job.html 分享脚本段"
    return match.group(1)


def _job_readonly_branch(html: str) -> str:
    match = re.search(r"(    if \(data\.readonly\)\{[\s\S]*?\n    \})\n    initShareButton\(data\);", html)
    assert match, "未找到 job.html 只读分支"
    return match.group(1)


def _profile_share_source(html: str) -> str:
    match = re.search(r"(// --- P1 只读分享[\s\S]*?)\nbindShareRevoke\(\);", html)
    assert match, "未找到 profile.html 分享脚本段"
    return match.group(1)


_EL_FACTORY = r"""
function makeEl(){
  const e = {
    children: [], childNodes: [], style: {}, className: '', _text: '', innerHTML: '',
    disabled: false, dataset: {}, listeners: {}, classes: new Set(), value: '', checked: false,
    attributes: {},
    setAttribute(n, v){ this.attributes[n] = String(v); },
    getAttribute(n){ return this.attributes[n]; },
    appendChild(...n){ this.children.push(...n); this.childNodes.push(...n); return n[n.length - 1]; },
    replaceChildren(...n){ this.children = [...n]; this.childNodes = [...n]; },
    addEventListener(t, fn){ (this.listeners[t] ||= []).push(fn); },
    querySelectorAll(){ return []; },
    focus(){}, select(){},
  };
  Object.defineProperty(e, 'textContent', {get(){ return e._text; }, set(v){ e._text = v; }});
  e.classList = {
    add(c){ e.classes.add(c); },
    remove(c){ e.classes.delete(c); },
    toggle(c, on){ if (on === undefined) on = !e.classes.has(c); if (on) e.classes.add(c); else e.classes.delete(c); },
    contains(c){ return e.classes.has(c); },
  };
  return e;
}
"""


class TestShareUiMarkers:
    """job/profile 分享 UI 结构标记（不依赖 Node）。"""

    def test_job_share_markup(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        for marker in (
            'id="box-share"', 'id="btn-share"', 'id="share-modal"', 'id="share-modal-no"',
            'id="share-modal-yes"', 'id="share-exp-1"', 'id="share-exp-7"', 'id="share-exp-30"',
            'id="share-exp-0"', 'id="share-link-modal"', 'id="share-link-input"',
            'id="btn-copy-share"', 'id="share-link-done"', 'id="share-status"',
            "data.readonly_kind === 'share' ? '只读分享'",
            "back.textContent = '← 返回首页'",
            "shareUrl('/api/saas/jobs/' + JOB_ID + '/share-links')",
            "function initShareButton(data)",
            "'box-actions', 'download-card', 'guest-result-note', 'guest-note', 'box-share', 'guest-strip'",
            "fmtShareTime(d.expires_at)",
            "LabUI.fmtLocalTime",
            "gs.classList.add('hidden'); gs.style.display = 'none';",
        ):
            assert marker in html, marker
        # 明文链接绝不写 localStorage
        assert "localStorage.setItem" not in _job_share_source(html)

    def test_profile_share_markup(self, client):
        html = client.get("/saas/profile").get_data(as_text=True)
        for marker in (
            'id="share-card"', 'id="share-list"', 'id="share-revoke-modal"',
            'id="share-revoke-no"', 'id="share-revoke-yes"',
            "'/api/saas/share-links'", "'/api/saas/share-links/' + shareRevokeTarget + '/revoke'",
            "const SHARE_STATUS_LABEL = {active: '有效', expired: '已过期', revoked: '已撤销'}",
            "it.status === 'active'",
        ):
            assert marker in html, marker
        assert "localStorage" not in _profile_share_source(html)

    def test_share_token_propagates_to_result_calls(self, client):
        """分享视图下 job/symbols/symbol 三页的结果 API 与导航都带 token。"""
        for path in ("/saas/jobs/1", "/saas/jobs/1/symbols", "/saas/jobs/1/symbols/000001"):
            html = client.get(path).get_data(as_text=True)
            assert "shareUrl(" in html or "shareSuffix()" in html, path
            assert "new URLSearchParams(location.search).get('share')" in html, path


_JOB_SHARE_HARNESS = (
    _EL_FACTORY
    + r"""
function realFmtLocalTime(iso){  // 与 static/lab-ui.js LabUI.fmtLocalTime 同实现
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return String(iso);
  const p = n => ('0' + n).slice(-2);
  return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate())
    + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
}
function createJobShareHarness(options){
  const elements = new Proxy({}, {get(obj, key){ return obj[key] || (obj[key] = makeEl()); }});
  const calls = {requests: [], clipboard: [], localStorageWrites: []};
  const document = {
    getElementById(id){ return elements[id]; },
    querySelector(){ return null; },
    querySelectorAll(){ return []; },
    createElement(){ return makeEl(); },
  };
  const labui = options.labui === null ? {} : {LabUI: options.labui || {fmtLocalTime: realFmtLocalTime}};
  const context = vm.createContext(Object.assign({
    console, document, JOB_ID: 7,
    SAAS_BYPASS: !!options.bypass,
    location: {search: options.search || ''},
    URLSearchParams, encodeURIComponent,
    navigator: options.navigator || {clipboard: null},
    saasToken(){ return options.token || ''; },
    apiFetch(url, opts){ calls.requests.push({url, options: opts}); return options.fetchImpl(url, opts); },
    localStorage: {setItem(k, v){ calls.localStorageWrites.push([k, v]); }, getItem(){ return null; }},
    setTimeout(fn){ Promise.resolve().then(fn); return 1; }, clearTimeout(){},
  }, labui));
  return {context, calls, elements};
}
"""
)

_JOB_READONLY_HARNESS = (
    _EL_FACTORY
    + r"""
function createReadonlyHarness(){
  const elements = {};
  const h1 = makeEl(), back = makeEl();
  back.attributes.href = '/saas/';
  const known = ['box-actions', 'download-card', 'guest-result-note', 'guest-note', 'box-share', 'guest-strip'];
  const document = {
    getElementById(id){
      if (known.indexOf(id) < 0) return null;
      return elements[id] || (elements[id] = makeEl());
    },
    querySelector(sel){ return sel === 'h1' ? h1 : (sel === 'a[href="/saas/"]' ? back : null); },
    createElement(){ return makeEl(); },
  };
  const context = vm.createContext({console, document});
  return {context, h1, back};
}
"""
)

_PROFILE_SHARE_HARNESS = (
    _EL_FACTORY
    + r"""
function realFmtLocalTime(iso){  // 与 static/lab-ui.js LabUI.fmtLocalTime 同实现
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return String(iso);
  const p = n => ('0' + n).slice(-2);
  return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate())
    + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
}
function createProfileShareHarness(options){
  const elements = new Proxy({}, {get(obj, key){ return obj[key] || (obj[key] = makeEl()); }});
  const listBox = elements['share-list'];
  // 与真实 DOM 一致：innerHTML 不变则 querySelectorAll 返回同一批按钮
  // （重渲染后才换新元素），否则监听会丢
  let qsaCache = {html: null, buttons: []};
  listBox.querySelectorAll = function(sel){
    if (sel !== '[data-share-revoke]') return [];
    const html = String(this.innerHTML);
    if (qsaCache.html !== html){
      const ids = [...html.matchAll(/data-share-revoke="(\d+)"/g)].map(m => Number(m[1]));
      qsaCache = {html, buttons: ids.map(id => {
        const b = makeEl();
        b.setAttribute('data-share-revoke', id);
        return b;
      })};
    }
    return qsaCache.buttons;
  };
  const calls = {requests: []};
  const document = {getElementById(id){ return elements[id]; }};
  const labui = options.labui === null ? {} : {LabUI: options.labui || {fmtLocalTime: realFmtLocalTime}};
  const context = vm.createContext(Object.assign({
    console, document,
    escH(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); },
    apiFetch(url, opts){ calls.requests.push({url, options: opts}); return options.fetchImpl(url, opts); },
  }, labui));
  return {context, calls, elements, listBox};
}
"""
)


class TestJobShareJs:
    """Node harness：job.html 分享按钮/模态/一次性链接/只读分享文案分流。"""

    def _run(self, html, scenario):
        import json as _json

        source = _job_share_source(html)
        _run_node(_JOB_SHARE_HARNESS + "\nconst source = " + _json.dumps(source)
                  + ";\n" + scenario)

    def test_guest_and_readonly_hide_share_button(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        self._run(html, r"""
(function(){
  const fetchImpl = async () => { throw new Error('不应发请求'); };
  for (const options of [
    {token: '', bypass: false, fetchImpl},          // 游客
    {token: 'tok', bypass: false, fetchImpl, readonly: true},  // 公开只读
  ]){
    const h = createJobShareHarness(options);
    vm.runInContext(source, h.context);
    vm.runInContext('initShareButton(' + JSON.stringify({readonly: !!options.readonly}) + ')', h.context);
    assert.ok(h.elements['box-share'].classList.contains('hidden'), '游客/只读不得显示分享入口');
    assert.equal(h.calls.requests.length, 0);
  }
})();
""")

    def test_logged_in_owner_sees_button_and_creates_once(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        self._run(html, r"""
(async () => {
  const created = [];
  const h = createJobShareHarness({
    bypass: true, fetchImpl: async (url, opts) => {
      created.push({url, options: opts});
      return {status: 200, ok: true, json: async () => ({ok: true, id: 9,
        url: '/saas/jobs/7?share=plain-token-xyz', expires_at: '2026-11-02T00:00:00+00:00'})};
    },
  });
  vm.runInContext(source, h.context);
  vm.runInContext('initShareButton({readonly: false})', h.context);
  assert.ok(!h.elements['box-share'].classList.contains('hidden'), '登录已完成必须显示分享入口');
  // 打开模态 → 默认 7 天 → 创建
  h.elements['share-exp-7'].checked = true; h.elements['share-exp-7'].value = '7';
  await h.elements['btn-share'].listeners.click[0]();
  assert.ok(h.elements['share-modal'].classList.contains('show'));
  await h.elements['share-modal-yes'].listeners.click[0]();
  assert.equal(created.length, 1);
  assert.equal(created[0].url, '/api/saas/jobs/7/share-links');
  assert.deepEqual(created[0].options.json, {expires_days: 7});
  // 链接只读 input 一次性展示；不写 localStorage
  assert.equal(h.elements['share-link-input'].value, '/saas/jobs/7?share=plain-token-xyz');
  assert.ok(h.elements['share-link-modal'].classList.contains('show'));
  assert.match(h.elements['share-link-note'].textContent, /只显示一次/);
  // 有效期走 LabUI.fmtLocalTime：本地 YYYY-MM-DD HH:mm，无 ISO 微秒
  assert.match(h.elements['share-link-note'].textContent,
    /有效期至 \d{4}-\d{2}-\d{2} \d{2}:\d{2}。/);
  assert.ok(!/T\d{2}:\d{2}:\d{2}/.test(h.elements['share-link-note'].textContent),
    '不得直接展示 ISO 时间: ' + h.elements['share-link-note'].textContent);
  assert.ok(!/\.\d{6}/.test(h.elements['share-link-note'].textContent),
    '不得展示微秒: ' + h.elements['share-link-note'].textContent);
  assert.equal(h.calls.localStorageWrites.length, 0, '分享链接不得写 localStorage');
  // 有效期选择被服务端 allowlist 校验（1/7/30/0）
  h.elements['share-exp-7'].checked = false;  // 真实浏览器同组单选互斥
  h.elements['share-exp-30'].checked = true; h.elements['share-exp-30'].value = '30';
  await h.elements['share-modal-yes'].listeners.click[0]();
  assert.deepEqual(created[1].options.json, {expires_days: 30});
  // 复制：Clipboard API 成功路径
  const clip = [];
  const h2 = createJobShareHarness({
    bypass: true, navigator: {clipboard: {writeText: async t => clip.push(t)}},
    fetchImpl: async () => ({status: 200, ok: true, json: async () => ({ok: true, id: 1, url: '/saas/jobs/7?share=t'})}),
  });
  vm.runInContext(source, h2.context);
  vm.runInContext('initShareButton({readonly: false})', h2.context);
  h2.elements['share-exp-7'].checked = true; h2.elements['share-exp-7'].value = '7';
  await h2.elements['btn-share'].listeners.click[0]();
  await h2.elements['share-modal-yes'].listeners.click[0]();
  await h2.elements['btn-copy-share'].listeners.click[0]();
  await new Promise(r => setTimeout(r, 0));
  assert.deepEqual(clip, ['/saas/jobs/7?share=t']);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_share_view_url_carries_token(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        self._run(html, r"""
(function(){
  const h = createJobShareHarness({bypass: true, search: '?share=tok-123', fetchImpl: async () => ({})});
  vm.runInContext(source, h.context);
  assert.equal(vm.runInContext("shareUrl('/api/results/7/summary')", h.context), '/api/results/7/summary?share=tok-123');
  assert.equal(vm.runInContext("shareUrl('/api/results/7/summary?x=1')", h.context), '/api/results/7/summary?x=1&share=tok-123');
  assert.equal(vm.runInContext("shareSuffix()", h.context), '?share=tok-123');
  const plain = createJobShareHarness({bypass: true, search: '', fetchImpl: async () => ({})});
  vm.runInContext(source, plain.context);
  assert.equal(vm.runInContext("shareUrl('/api/results/7/summary')", plain.context), '/api/results/7/summary');
})();
""")

    def test_readonly_chip_and_back_copy_split(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        branch = _job_readonly_branch(html)
        import json as _json

        _run_node(_JOB_READONLY_HARNESS + "\nconst source = " + _json.dumps(branch) + ";\n" + r"""
(function(){
  for (const kind of ['share', 'showcase']){
    const h = createReadonlyHarness();
    vm.runInContext('const data = {readonly: true, readonly_kind: ' + JSON.stringify(kind) + '};', h.context);
    vm.runInContext(source, h.context);
    const chip = h.h1.children[0];
    assert.ok(chip, kind + ' 必须插入只读 chip');
    assert.equal(chip.textContent, kind === 'share' ? '只读分享' : '经典策略展示 · 只读');
    if (kind === 'share'){
      assert.equal(h.back.href, '/saas/');
      assert.equal(h.back.textContent, '← 返回首页');
    } else {
      assert.equal(h.back.href, '/saas/showcase');
      assert.equal(h.back.textContent, '← 返回经典策略');
    }
    // 操作入口与分享入口一并隐藏
    for (const id of ['box-actions', 'download-card', 'guest-result-note', 'guest-note', 'box-share', 'guest-strip']){
      assert.ok(h.context.document.getElementById(id).classList.contains('hidden'), id);
    }
  }
})();
""")

    def test_expiry_note_fallback_and_permanent(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        self._run(html, r"""
(async () => {
  // LabUI 缺失：回退原值（不编日期），仍带「只显示一次」
  const noLab = createJobShareHarness({
    bypass: true, labui: null,
    fetchImpl: async () => ({status: 200, ok: true, json: async () => ({ok: true, id: 1,
      url: '/saas/jobs/7?share=t', expires_at: '2026-11-02T00:00:00+00:00'})}),
  });
  vm.runInContext(source, noLab.context);
  vm.runInContext('initShareButton({readonly: false})', noLab.context);
  await noLab.elements['btn-share'].listeners.click[0]();
  await noLab.elements['share-modal-yes'].listeners.click[0]();
  assert.match(noLab.elements['share-link-note'].textContent,
    /有效期至 2026-11-02T00:00:00\+00:00/);
  // 永久（expires_at=null）：明确「永久有效」
  const perm = createJobShareHarness({
    bypass: true,
    fetchImpl: async () => ({status: 200, ok: true, json: async () => ({ok: true, id: 2,
      url: '/saas/jobs/7?share=t', expires_at: null})}),
  });
  vm.runInContext(source, perm.context);
  vm.runInContext('initShareButton({readonly: false})', perm.context);
  await perm.elements['btn-share'].listeners.click[0]();
  await perm.elements['share-modal-yes'].listeners.click[0]();
  assert.match(perm.elements['share-link-note'].textContent, /^永久有效。/);
  assert.match(perm.elements['share-link-note'].textContent, /只显示一次/);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_create_failure_surfaces_error(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        self._run(html, r"""
(async () => {
  const h = createJobShareHarness({
    bypass: true,
    fetchImpl: async () => ({status: 409, ok: false, json: async () => ({ok: false, error: '任务未完成（queued）'})}),
  });
  vm.runInContext(source, h.context);
  vm.runInContext('initShareButton({readonly: false})', h.context);
  await h.elements['btn-share'].listeners.click[0]();
  await h.elements['share-modal-yes'].listeners.click[0]();
  assert.equal(h.elements['share-status'].textContent, '任务未完成（queued）');
  assert.ok(!h.elements['share-link-modal'].classList.contains('show'), '失败不得展示链接');
  assert.equal(h.elements['btn-share'].disabled, false, '失败后必须允许重试');
})().catch(error => { console.error(error); process.exit(1); });
""")


class TestProfileShareJs:
    """Node harness：profile 我的分享列表/状态/撤销二次确认。"""

    def _run(self, html, scenario):
        import json as _json

        source = _profile_share_source(html)
        _run_node(_PROFILE_SHARE_HARNESS + "\nconst source = " + _json.dumps(source)
                  + ";\n" + scenario)

    def test_list_renders_status_and_hides_token(self, client):
        html = client.get("/saas/profile").get_data(as_text=True)
        self._run(html, r"""
(async () => {
  const items = [
    {id: 1, job_id: 11, strategy_name: 'alpha', created_at: '2026-10-26T01:00:00+00:00',
     expires_at: '2026-11-02T01:00:00+00:00', revoked_at: null, status: 'active'},
    {id: 2, job_id: 12, strategy_name: 'beta', created_at: '2026-10-20T01:00:00+00:00',
     expires_at: '2026-10-21T01:00:00+00:00', revoked_at: null, status: 'expired'},
    {id: 3, job_id: 13, strategy_name: 'gamma', created_at: '2026-10-19T01:00:00+00:00',
     expires_at: null, revoked_at: '2026-10-25T01:00:00+00:00', status: 'revoked'},
    {id: 4, job_id: 14, strategy_name: 'delta', created_at: '2026-10-18T01:00:00+00:00',
     expires_at: null, revoked_at: null, status: 'active'},
  ];
  const h = createProfileShareHarness({
    fetchImpl: async url => {
      assert.equal(url, '/api/saas/share-links');
      return {status: 200, ok: true, json: async () => ({ok: true, items})};
    },
  });
  vm.runInContext(source, h.context);
  await vm.runInContext('loadShares()', h.context);
  assert.ok(!h.elements['share-card'].classList.contains('hidden'));
  const body = h.listBox.innerHTML;
  assert.ok(body.includes('#11') && body.includes('alpha'), body);
  // 创建时间与有效期走 LabUI.fmtLocalTime：本地 YYYY-MM-DD HH:mm，无 ISO 微秒
  assert.match(body, /\d{4}-\d{2}-\d{2} \d{2}:\d{2}/, body);
  assert.ok(!/T\d{2}:\d{2}:\d{2}/.test(body), '列表不得直接展示 ISO 时间: ' + body);
  assert.ok(!/\.\d{6}/.test(body), '列表不得展示微秒: ' + body);
  assert.ok(body.includes('已撤销'), body);
  assert.ok(body.includes('永久有效'), body);
  assert.ok(!body.includes('token_hash') && !body.includes('share='), '列表不得出现令牌痕迹');
  // 仅 active 行有撤销按钮；revoked/expired 不提供撤销
  const buttons = [...body.matchAll(/data-share-revoke="(\d+)"/g)].map(m => Number(m[1]));
  assert.deepEqual(buttons, [1, 4], '仅 active 行有撤销按钮');
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_revoke_flow_with_confirm(self, client):
        html = client.get("/saas/profile").get_data(as_text=True)
        self._run(html, r"""
(async () => {
  let revoked = null, lists = 0;
  const h = createProfileShareHarness({
    fetchImpl: async (url, opts) => {
      if (url === '/api/saas/share-links'){ lists += 1; return {status: 200, ok: true, json: async () => ({ok: true, items: [
        {id: 5, job_id: 21, strategy_name: 'alpha', created_at: '2026-10-26T01:00:00+00:00',
         expires_at: null, revoked_at: null, status: 'active'}]})}; }
      if (url.endsWith('/revoke')){ revoked = url; return {status: 200, ok: true, json: async () => ({ok: true})}; }
      throw new Error('unexpected ' + url);
    },
  });
  vm.runInContext(source, h.context);
  vm.runInContext('bindShareRevoke()', h.context);
  await vm.runInContext('loadShares()', h.context);
  const btn = h.listBox.querySelectorAll('[data-share-revoke]')[0];
  await btn.listeners.click[0]();
  assert.ok(h.elements['share-revoke-modal'].classList.contains('show'), '撤销必须二次确认');
  assert.equal(revoked, null, '确认前不得撤销');
  await h.elements['share-revoke-no'].listeners.click[0]();
  assert.ok(!h.elements['share-revoke-modal'].classList.contains('show'));
  assert.equal(revoked, null, '取消后不得撤销');
  await btn.listeners.click[0]();
  await h.elements['share-revoke-yes'].listeners.click[0]();
  assert.equal(revoked, '/api/saas/share-links/5/revoke');
  assert.ok(!h.elements['share-revoke-modal'].classList.contains('show'));
  assert.ok(lists >= 2, '撤销后必须刷新列表');
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_guest_hides_card(self, client):
        html = client.get("/saas/profile").get_data(as_text=True)
        self._run(html, r"""
(async () => {
  const h = createProfileShareHarness({
    fetchImpl: async () => { const e = new Error('unauthorized'); e.status = 401; throw e; },
  });
  vm.runInContext(source, h.context);
  await vm.runInContext('loadShares()', h.context);
  assert.ok(h.elements['share-card'].classList.contains('hidden'), '未登录不展示我的分享');
})().catch(error => { console.error(error); process.exit(1); });
""")
