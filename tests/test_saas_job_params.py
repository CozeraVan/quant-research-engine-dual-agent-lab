"""QRE-JOB-PARAMS-SNAPSHOT：回测参数快照端点 `/api/saas/jobs/<id>/params`。

目的：任何一次回测的输入参数都能被**原样复现**——完整 params（JSONB）、
策略 YAML、幂等键、入口模式都在同一响应里，供结果页「回测参数」折叠卡
与「复制/重跑」使用。

覆盖：本人可读全量；他人任务 404；游客跨会话 401（不泄露存在性）。
"""

from __future__ import annotations

import subprocess
import uuid

import pytest
from sqlalchemy import text

from quant_research_engine.gui.saas import create_saas_app

WORKER_TOKEN = "t"
VALID_YAML = (
    "experiment:\n  name: t\ndata:\n  market_fields: [close]\n"
    "signal:\n  entry: close > 0\n"
    "evaluation:\n  forward_return_horizons: [1, 3, 5]\n"
    "holding:\n  max_holding_days: 20\n"
)
JOB_PARAMS = {
    "start": "2009-01-05", "end": "2026-10-30", "mode": "batch",
    "initial_cash": 100000, "max_positions": 0, "max_holding_days": 20,
    "entry_price": "open", "exit_price": "open",
    "profile_overrides": {
        "commission_rate": 0.0003, "min_commission": 5.0,
        "stamp_tax_sell": 0.0005, "slippage_buy_rate": 0, "slippage_sell_rate": 0,
    },
}
IDEM = "CF-018-bo09e_channel_retest_breakout-v1"


def _psql(db: str, *args: str) -> None:
    subprocess.run(
        ["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def saas_db():
    db_name = f"qre_saas_params_{uuid.uuid4().hex[:12]}"
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
    from quant_research_engine.gui.saas.app import _get_engine

    with _get_engine(app).begin() as conn:
        conn.execute(text(
            "TRUNCATE results, jobs, strategies, users, sessions, sms_codes RESTART IDENTITY CASCADE"))
    yield app.test_client()
    engine = app.extensions.get("saas_engine")
    if engine is not None:
        engine.dispose()


def _seed(client, *, owner=1, guest_key=None):
    """种一个策略 + 一条带完整参数的回测 job，返回 job_id。"""
    from quant_research_engine.gui.saas.app import _get_engine

    engine = _get_engine(client.application)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, phone) VALUES (:id, :p) "
                          "ON CONFLICT (id) DO NOTHING"), {"id": owner, "p": f"1390000000{owner}"})
        conn.execute(text(
            "INSERT INTO strategies (user_id, name, nl_text, yaml, entry_mode) "
            "VALUES (:uid, 'bo09e 通道回踩突破', '突破后回踩不破再上行', :yaml, 'yaml')"
        ), {"uid": owner, "yaml": VALID_YAML})
        strategy_id = conn.execute(text("SELECT max(id) FROM strategies")).scalar()
        job_id = conn.execute(text(
            "INSERT INTO jobs (user_id, strategy_id, kind, status, params, idempotency_key, guest_key) "
            "VALUES (:uid, :sid, 'full', 'completed', CAST(:params AS jsonb), :idem, :gk) RETURNING id"
        ), {"uid": owner, "sid": strategy_id,
            "params": __import__("json").dumps(JOB_PARAMS), "idem": IDEM,
            "gk": guest_key}).scalar()
    return job_id


def test_owner_gets_full_params_snapshot(client):
    job_id = _seed(client)
    resp = client.get(f"/api/saas/jobs/{job_id}/params", headers={"X-User-Id": "1"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["job_id"] == job_id
    assert data["idempotency_key"] == IDEM
    assert data["kind"] == "full"
    # 完整参数一个不漏（含 profile_overrides 的费用项）
    assert data["params"] == JOB_PARAMS
    assert data["params"]["profile_overrides"]["commission_rate"] == 0.0003
    assert data["strategy"]["yaml"] == VALID_YAML
    assert data["strategy"]["entry_mode"] == "yaml"
    assert data["strategy"]["name"] == "bo09e 通道回踩突破"


def test_other_user_gets_404_not_existence_leak(client):
    job_id = _seed(client)
    resp = client.get(f"/api/saas/jobs/{job_id}/params", headers={"X-User-Id": "2"})
    assert resp.status_code == 404
    assert resp.get_json()["ok"] is False


def test_guest_without_matching_guest_key_gets_401(client):
    job_id = _seed(client)          # owner 任务：guest_key 为 NULL
    resp = client.get(f"/api/saas/jobs/{job_id}/params")
    assert resp.status_code == 401
    assert resp.get_json()["ok"] is False
