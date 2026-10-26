"""QRE-SAAS-RESULT-CONTRACT-001 结果合同测试（真实本地 PG 临时库）。

覆盖：
1. 新回传结果带 result_contract（版本 / data_until / 两种收益口径 / 验证状态）。
2. 历史结果按**显式版本映射与例外表**分类，绝不按 created_at / 当前时间动态猜测。
3. 58/66 为 verified 例外，74 未验证（price_basis 核查通过 ≠ 收益口径已验证）。
4. 经典策略公开展示只放行 verified；白名单行 / 任务 / 产物不删除。
5. 私人历史结果权限语义不变（本人可见、他人 404、匿名 401），API 仍携带合同。
6. 页面不显示验证标签/版本；曲线与总收益口径仅保留原有悬停提示。
"""

from __future__ import annotations

import subprocess
import uuid

import pytest

from quant_research_engine.gui.saas import create_saas_app
from quant_research_engine.gui.saas.result_contract import (
    DAILY_RETURN_BASIS,
    LEGACY_VERSION,
    RESULT_CONTRACT_VERSION,
    TOTAL_RETURN_BASIS,
    VERIFICATION_UNVERIFIED,
    VERIFICATION_VERIFIED,
    build_result_contract,
    contract_view,
    is_verified,
    resolve_result_contract,
)

WORKER_TOKEN = "test-worker-token"
WORKER_HEADERS = {"X-Worker-Token": WORKER_TOKEN}


def _psql(db: str, *args: str) -> None:
    subprocess.run(
        ["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def saas_db():
    db_name = f"qre_contract_test_{uuid.uuid4().hex[:12]}"
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


def _engine(app):
    from quant_research_engine.gui.saas.app import _get_engine

    return _get_engine(app)


def _lease(client, worker_id="w1"):
    return client.post("/api/worker/jobs/claim", json={"worker_id": worker_id},
                       headers=WORKER_HEADERS)


def _complete_via_worker(client, job_id, *, summary=None, chart=None, data_until="2026-02-27"):
    """走真实 worker 回传端点（result/meta，无文件直接 completed）。"""
    return client.post(
        f"/api/worker/jobs/{job_id}/result/meta",
        json={"worker_id": "w1",
              "summary": summary or {"strategy_total_return": 0.2, "win_rate": 0.5,
                                     "max_drawdown": -0.1, "total_trade_count": 5},
              "chart_data": chart or {"metrics": {"excess_return": 0.05, "sharpe": 1.2},
                                      "dates": ["2026-01-05"], "equity": [1.0],
                                      "cumret": [0.0]},
              "data_until": data_until, "files": []},
        headers=WORKER_HEADERS,
    )


def _new_job(client, uid=1):
    resp = client.post("/api/jobs", json={"yaml": "x", "kind": "full", "name": "t",
                                          "params": {"start": "2026-01-01", "end": "2026-03-01"}},
                       headers={"X-User-Id": str(uid)})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["job_id"]


def _seed_legacy_result(app, *, job_id, uid=1, contract="omit", data_until="2025-12-31",
                        created_at="2026-01-05 10:00:00+08"):
    """直接落一行历史结果（不带 worker 回传）。contract='omit' → 列留空（旧库形态）。"""
    from sqlalchemy import text

    with _engine(app).begin() as conn:
        conn.execute(text("INSERT INTO users (id, tier, role) VALUES (:u, 'member', 'user') "
                          "ON CONFLICT (id) DO NOTHING"), {"u": uid})
        strategy_id = conn.execute(
            text("INSERT INTO strategies (user_id, name, yaml) VALUES (:u, 't', 'x') RETURNING id"),
            {"u": uid},
        ).scalar_one()
        conn.execute(
            text("INSERT INTO jobs (id, user_id, strategy_id, kind, status, params, created_at) "
                 "VALUES (:id, :u, :s, 'full', 'completed', CAST(:p AS jsonb), CAST(:c AS timestamptz))"),
            {"id": job_id, "u": uid, "s": strategy_id,
             "p": '{"start": "2024-01-01", "end": "2024-06-30"}', "c": created_at},
        )
        cols = "job_id, user_id, summary, chart_data, artifacts, data_until"
        values = ":id, :u, CAST(:s AS jsonb), CAST(:c AS jsonb), '[]'::jsonb, :d"
        params = {"id": job_id, "u": uid,
                  "s": '{"strategy_total_return": 0.1, "max_drawdown": -0.2, "win_rate": 0.4}',
                  "c": '{"metrics": {"excess_return": 0.01}}', "d": data_until}
        if contract != "omit":
            cols += ", result_contract"
            values += ", CAST(:rc AS jsonb)"
            params["rc"] = "null" if contract is None else __import__("json").dumps(contract)
        conn.execute(text(f"INSERT INTO results ({cols}) VALUES ({values})"), params)


def _pin_showcase(app, job_id, title="经典策略", active=True):
    from sqlalchemy import text

    from quant_research_engine.gui.saas.app import _ensure_signal_tables

    _ensure_signal_tables(_engine(app))
    with _engine(app).begin() as conn:
        conn.execute(text("INSERT INTO showcase (job_id, title, subtitle, sort_order, is_active) "
                          "VALUES (:id, :t, '副标题', 1, :a)"),
                     {"id": job_id, "t": title, "a": active})


def _admin(app):
    """管理台账号（console 端点要求 role=admin）。"""
    from sqlalchemy import text

    with _engine(app).begin() as conn:
        conn.execute(text("SELECT setval('users_id_seq', COALESCE((SELECT max(id) FROM users), 1))"))
        uid = conn.execute(
            text("INSERT INTO users (email, role, status, tier) "
                 "VALUES ('admin@sc.com', 'admin', 'active', 'member') RETURNING id")
        ).scalar_one()
    return {"X-User-Id": str(uid)}


# ---------------------------------------------------------------- 纯函数：合同构造与分类


class TestContractModel:
    def test_build_current_contract(self):
        c = build_result_contract(data_until="2026-02-27")
        assert c["version"] == RESULT_CONTRACT_VERSION
        assert c["verification"] == VERIFICATION_VERIFIED
        assert c["data_until"] == "2026-02-27"
        assert c["daily_return_basis"] == DAILY_RETURN_BASIS
        assert c["total_return_basis"] == TOTAL_RETURN_BASIS

    def test_resolve_stored_contract_wins(self):
        stored = {"version": "2026-10-25.1", "verification": VERIFICATION_VERIFIED,
                  "data_until": "2026-02-27"}
        c = resolve_result_contract(74, stored)
        # 显式存储的合同优先于例外表：74 的旧行无合同，有合同就以合同为准
        assert c["version"] == "2026-10-25.1" and c["verification"] == VERIFICATION_VERIFIED
        assert c["daily_return_basis"] == DAILY_RETURN_BASIS
        assert c["total_return_basis"] == TOTAL_RETURN_BASIS

    def test_resolve_legacy_exceptions(self):
        for job_id in (58, 66):
            c = resolve_result_contract(job_id, None)
            assert c["verification"] == VERIFICATION_VERIFIED, job_id
            assert c["version"] == LEGACY_VERSION
            assert is_verified(job_id, None) is True
        c74 = resolve_result_contract(74, None)
        assert c74["verification"] == VERIFICATION_UNVERIFIED
        assert is_verified(74, None) is False

    def test_unknown_legacy_result_is_unverified(self):
        c = resolve_result_contract(999999, None)
        assert c["verification"] == VERIFICATION_UNVERIFIED
        assert c["version"] == LEGACY_VERSION
        assert c["note"]

    def test_classification_never_depends_on_time(self):
        # 合同分类只接受 job_id / 已存合同：签名里没有时间参数，
        # 新增/刚产生的结果没有合同也必须落「未验证」，不能按 created_at 猜。
        import inspect

        params = list(inspect.signature(resolve_result_contract).parameters)
        assert params == ["job_id", "stored", "data_until"], params
        assert resolve_result_contract(1234, None)["verification"] == VERIFICATION_UNVERIFIED
        assert resolve_result_contract(58, None)["verification"] == VERIFICATION_VERIFIED

    def test_broken_stored_value_falls_back_to_mapping(self):
        c = resolve_result_contract(74, "not-a-dict")
        assert c["verification"] == VERIFICATION_UNVERIFIED
        assert c["version"] == LEGACY_VERSION

    def test_contract_view_shape(self):
        v = contract_view(74, None, data_until="2026-01-31")
        assert v["verified"] is False
        assert v["label"] and v["tip"]
        assert v["data_until"] == "2026-01-31"
        assert DAILY_RETURN_BASIS in v["tip"] and TOTAL_RETURN_BASIS in v["tip"]
        assert v["verification"] == VERIFICATION_UNVERIFIED


# ---------------------------------------------------------------- 新结果：回传即带合同


class TestNewResultContract:
    def test_worker_meta_injects_current_contract(self, client, app):
        job_id = _new_job(client)
        assert _lease(client).status_code == 200
        assert _complete_via_worker(client, job_id).status_code == 200
        body = client.get(f"/api/results/{job_id}/summary",
                          headers={"X-User-Id": "1"}).get_json()
        c = body["result_contract"]
        assert c["version"] == RESULT_CONTRACT_VERSION
        assert c["verification"] == VERIFICATION_VERIFIED
        assert c["verified"] is True
        assert c["data_until"] == "2026-02-27"
        assert c["daily_return_basis"] == DAILY_RETURN_BASIS
        assert c["total_return_basis"] == TOTAL_RETURN_BASIS
        assert c["label"]
        assert c["tip"]
        # 原有数值字段不受影响
        assert body["summary"]["strategy_total_return"] == 0.2

    def test_legacy_single_packet_endpoint_also_injects(self, client, app):
        job_id = _new_job(client)
        assert _lease(client).status_code == 200
        resp = client.post(f"/api/saas/worker/jobs/{job_id}/result",
                           json={"worker_id": "w1", "status": "done",
                                 "summary": {"strategy_total_return": 0.3},
                                 "chart_data": {"metrics": {}}, "data_until": "2026-02-20"},
                           headers=WORKER_HEADERS)
        assert resp.status_code == 200, resp.get_json()
        c = client.get(f"/api/results/{job_id}/summary",
                       headers={"X-User-Id": "1"}).get_json()["result_contract"]
        assert c["version"] == RESULT_CONTRACT_VERSION and c["verified"] is True
        assert c["data_until"] == "2026-02-20"

    def test_results_list_carries_contract(self, client, app):
        job_id = _new_job(client)
        _lease(client)
        _complete_via_worker(client, job_id)
        items = client.get("/api/results", headers={"X-User-Id": "1"}).get_json()["items"]
        assert len(items) == 1
        c = items[0]["result_contract"]
        assert c["version"] == RESULT_CONTRACT_VERSION and c["verified"] is True
        assert items[0]["data_until"] == "2026-02-27"


# ---------------------------------------------------------------- 历史结果：显式分类


class TestLegacyClassification:
    def test_newly_seeded_result_without_contract_is_unverified(self, client, app):
        # created_at 是「现在」也必须是未验证：分类只认显式合同/例外表
        _seed_legacy_result(app, job_id=901, uid=1, created_at="2026-10-25 12:00:00+08")
        c = client.get("/api/results/901/summary",
                       headers={"X-User-Id": "1"}).get_json()["result_contract"]
        assert c["verification"] == VERIFICATION_UNVERIFIED
        assert c["verified"] is False
        assert c["version"] == LEGACY_VERSION

    def test_58_66_are_verified_exceptions(self, client, app):
        for job_id in (58, 66):
            _seed_legacy_result(app, job_id=job_id, uid=1)
            body = client.get(f"/api/results/{job_id}/summary",
                              headers={"X-User-Id": "1"}).get_json()
            c = body["result_contract"]
            assert c["verification"] == VERIFICATION_VERIFIED, job_id
            assert c["verified"] is True
            assert c["data_until"] == "2025-12-31"  # ISO 日期，不是 HTTP 日期串
            assert "复核" in c["note"]
            # 历史数值一个字节都没改
            assert body["summary"]["strategy_total_return"] == 0.1

    def test_74_is_unverified(self, client, app):
        _seed_legacy_result(app, job_id=74, uid=1)
        body = client.get("/api/results/74/summary", headers={"X-User-Id": "1"}).get_json()
        c = body["result_contract"]
        assert c["verification"] == VERIFICATION_UNVERIFIED
        assert c["version"] == LEGACY_VERSION
        assert "price_basis" in c["note"] or "收益口径" in c["note"]

    def test_private_visibility_unchanged_with_label(self, client, app):
        _seed_legacy_result(app, job_id=74, uid=1)
        # 本人：照旧可见，且带未验证标签
        owner = client.get("/api/results/74/summary", headers={"X-User-Id": "1"})
        assert owner.status_code == 200
        assert owner.get_json()["result_contract"]["verified"] is False
        # 他人：照旧 404（不暴露存在性）
        assert client.get("/api/results/74/summary", headers={"X-User-Id": "2"}).status_code == 404
        # 匿名：未挂公开白名单时照旧 401
        assert client.get("/api/results/74/summary").status_code == 401
        # 本人列表照旧返回，带标签
        items = client.get("/api/results", headers={"X-User-Id": "1"}).get_json()["items"]
        assert [i["job_id"] for i in items] == [74]
        assert items[0]["result_contract"]["verified"] is False


# ---------------------------------------------------------------- 经典策略：只公开 verified


class TestShowcaseOnlyVerified:
    def test_public_list_filters_unverified_but_keeps_whitelist(self, client, app):
        _seed_legacy_result(app, job_id=58, uid=1)
        _seed_legacy_result(app, job_id=74, uid=1)
        _pin_showcase(app, 58, title="已验证策略")
        _pin_showcase(app, 74, title="未验证策略")
        public = client.get("/api/saas/showcase").get_json()["items"]
        assert [i["job_id"] for i in public] == [58]
        assert public[0]["result_contract"]["verified"] is True
        # 白名单行没被删：管理台仍看得到两条，且都还是 active
        admin_items = client.get("/api/saas/console/showcase",
                                 headers=_admin(app)).get_json()["items"]
        assert {i["job_id"] for i in admin_items} == {58, 74}
        assert all(i["is_active"] for i in admin_items)
        by_id = {i["job_id"]: i for i in admin_items}
        assert by_id[74]["result_contract"]["verified"] is False
        assert by_id[74]["result_contract"]["verification"] == VERIFICATION_UNVERIFIED
        assert by_id[58]["result_contract"]["verified"] is True

    def test_public_readonly_channel_requires_verified(self, client, app):
        _seed_legacy_result(app, job_id=74, uid=1)
        _pin_showcase(app, 74)
        # 未验证 → 不再走公开只读通道（与未挂白名单同样 404/401，不泄露存在性）
        assert client.get("/api/results/74/summary").status_code == 401
        assert client.get("/api/results/74/summary", headers={"X-User-Id": "2"}).status_code == 404
        # 任务与产物仍在，本人照旧可见
        assert client.get("/api/results/74/summary", headers={"X-User-Id": "1"}).status_code == 200

    def test_verified_whitelisted_job_still_public_readonly(self, client, app):
        job_id = _new_job(client)
        _lease(client)
        _complete_via_worker(client, job_id)
        _pin_showcase(app, job_id)
        anon = client.get(f"/api/results/{job_id}/summary")
        assert anon.status_code == 200 and anon.get_json()["readonly"] is True
        assert anon.get_json()["result_contract"]["verified"] is True
        assert [i["job_id"] for i in client.get("/api/saas/showcase").get_json()["items"]] == [job_id]

    def test_inactive_whitelist_entry_stays_hidden(self, client, app):
        _seed_legacy_result(app, job_id=58, uid=1)
        _pin_showcase(app, 58, active=False)
        assert client.get("/api/saas/showcase").get_json()["items"] == []
        assert client.get("/api/results/58/summary").status_code == 401


# ---------------------------------------------------------------- 前端：合同留在系统内，口径提示保留


class TestPageLabels:
    def test_job_page_hides_contract_badge_but_keeps_basis_tips(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        assert "contract-badge" not in html
        assert "contract-note" not in html
        assert 'id="box-contract"' not in html
        # 曲线与总收益口径仍通过原有悬停提示解释
        assert "日收益累乘" in html
        assert "初始资金加权" in html

    def test_showcase_page_hides_contract_labels_and_versions(self, client):
        html = client.get("/saas/showcase").get_data(as_text=True)
        assert "已验证口径" not in html
        assert "旧口径·未验证" not in html
        assert "合同版本" not in html
        assert "result_contract" not in html

    def test_records_list_hides_contract_label(self, client):
        html = client.get("/saas/").get_data(as_text=True)
        assert "contractBadge" not in html
        assert "job.result_contract" not in html
