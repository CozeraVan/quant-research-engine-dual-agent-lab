"""QRE-SAAS M3 Worker 客户端测试（本地闭环：saas app test_client 当真实云端）。

- CloudClient 经注入 request_fn 直连 Flask test_client（同一个 PG 临时库，
  fixture 模式复用 test_gui_saas.py：psql 建/销库 + apply schema + TRUNCATE）。
- 引擎层（run_backtest）mock 成本地产物（真实 strategy_performance.json /
  equity_curve.csv / round_trips.csv 小数据），lab_result 组装逻辑真实过一遍。
- 基准指数查库（lab_result._benchmark_series）打桩，保持测试不依赖本地大库。
"""

from __future__ import annotations

import json
import subprocess
import uuid
import urllib.error
from pathlib import Path

import pytest

from quant_research_engine.gui.saas import create_saas_app
from quant_research_engine.worker.client import CloudClient, CloudError
from quant_research_engine.worker.daemon import WorkerDaemon
from quant_research_engine.worker import runner as runner_mod

WORKER_TOKEN = "test-worker-token"


def _psql(db: str, *args: str) -> None:
    subprocess.run(
        ["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def saas_db():
    db_name = f"qre_worker_test_{uuid.uuid4().hex[:12]}"
    _psql("postgres", "-c", f"CREATE DATABASE {db_name}")
    _psql(db_name, "-f", "deploy/saas/cloud_schema.sql")
    yield db_name
    _psql("postgres", "-c", f"DROP DATABASE IF EXISTS {db_name}")


@pytest.fixture()
def cloud(saas_db):
    app = create_saas_app()
    app.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
    app.config["SAAS_WORKER_TOKEN"] = WORKER_TOKEN
    app.config["SAAS_DEV_AUTH"] = "1"
    app.config["SAAS_AUTH_CHANNEL"] = "stub"
    tc = app.test_client()
    engine_holder = app
    yield app, tc
    engine = engine_holder.extensions.get("saas_engine")
    if engine is not None:
        engine.dispose()


@pytest.fixture(autouse=True)
def _clean(cloud):
    from sqlalchemy import text

    app, _ = cloud
    from quant_research_engine.gui.saas.app import _get_engine

    engine = _get_engine(app)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE results, jobs, strategies, users, sessions, sms_codes RESTART IDENTITY CASCADE"))


def _make_client(cloud, **kwargs) -> CloudClient:
    """CloudClient 直连 saas app test_client（本地闭环，不出网）。"""
    _, tc = cloud

    def request_fn(method, path, payload):
        resp = tc.open(path, method=method, json=payload,
                       headers={"X-Worker-Token": WORKER_TOKEN})
        return resp.status_code, resp.get_json(silent=True) or {}

    return CloudClient("http://cloud.local", WORKER_TOKEN, worker_id="w-test",
                       request_fn=request_fn, sleep=lambda s: None, **kwargs)


def _create_job(cloud, kind="full", params=None):
    _, tc = cloud
    resp = tc.post("/api/saas/jobs", json={
        "yaml": "experiment:\n  name: t\ndata:\n  market_fields: [close]\nsignal:\n  entry: close > 0\n",
        "kind": kind,
        "params": params or {"start": "2026-01-01", "end": "2026-03-01"},
    }, headers={"X-User-Id": "1"})
    assert resp.status_code == 200
    return resp.get_json()["job_id"]


def _job_status(cloud, job_id):
    _, tc = cloud
    return tc.get(f"/api/saas/jobs/{job_id}", headers={"X-User-Id": "1"}).get_json()["job"]


def _fake_run_backtest(output_dir: str):
    """mock 引擎层：写真实小数据产物，返回 completed run 记录。"""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    perf = out / "strategy_performance.json"
    perf.write_text(json.dumps({
        "strategy_name": "t", "strategy_total_return": 0.1, "buy_hold_return": 0.05,
        "win_rate": 0.6, "max_drawdown": -0.02, "total_trade_count": 3,
    }), encoding="utf-8")
    equity = out / "equity_curve.csv"
    equity.write_text("trade_date,total_equity\n2026-01-05,100000\n2026-01-06,101000\n2026-01-07,100500\n",
                      encoding="utf-8")
    trades = out / "round_trips.csv"
    trades.write_text("symbol,entry_date,exit_date,net_return,net_pnl\n"
                      "000001.SZ,2026-01-05,2026-01-06,0.01,1000\n", encoding="utf-8")
    record = {
        "run_id": "test_run_1", "mode": "shared", "status": "completed", "error": None,
        "start": "2026-01-01", "end": "2026-03-01", "codes": [],
        "output_dir": str(out),
        "artifacts": {p.name: str(p) for p in (perf, equity, trades)},
    }
    return record


@pytest.fixture()
def mock_engine(monkeypatch, tmp_path):
    """mock run_backtest（写产物到 tmp_path），打桩基准指数查库与归因 DB 查询。"""
    monkeypatch.setattr(runner_mod, "run_backtest",
                        lambda **kw: _fake_run_backtest(kw["output_dir"]))
    monkeypatch.setattr("quant_research_engine.gui.lab_result._benchmark_series",
                        lambda dates: ({}, "test: no benchmark"))
    # 归因 DB 查询打桩（保持测试不依赖本地大库）：A 层行业标签
    monkeypatch.setattr(
        "quant_research_engine.gui.lab_result._fetch_company_tags",
        lambda symbols: ([("000001.SZ", "申万L1:银行", "A")], {"000001.SZ": "平安银行"}, None),
    )
    monkeypatch.setattr("quant_research_engine.gui.lab_result._fetch_industries",
                        lambda symbols: {})
    monkeypatch.setattr("quant_research_engine.gui.lab_result._fetch_symbol_range_returns",
                        lambda symbols, start, end: {"000001.SZ": 0.02})


class TestEndToEnd:
    def test_lease_run_report_done(self, cloud, mock_engine, tmp_path):
        job_id = _create_job(cloud)
        client = _make_client(cloud)

        job = client.lease()
        assert job["id"] == job_id
        assert job["status"] == "leased" and job["attempts"] == 1
        assert job["strategy"]["yaml"].startswith("experiment:")

        payload = runner_mod.execute_job(job, work_base=tmp_path)
        assert payload["summary"]["strategy_total_return"] == 0.1
        assert payload["chart_data"]["equity"] == [100000.0, 101000.0, 100500.0]
        assert payload["chart_data"]["dates"] == ["2026-01-05", "2026-01-06", "2026-01-07"]
        assert payload["artifacts"] == []  # TODO(M4) OSS
        assert payload["data_until"] == "2026-01-07"  # 净值曲线末日（数据实际覆盖）
        # 归因数据：与 8081 同一组装函数，截断后挂 chart_data.tag_analysis
        attr = payload["chart_data"]["tag_analysis"]
        assert attr["ok"] and attr["layers"]["A"][0]["tag"] == "银行"
        assert attr["layers"]["A"][0]["symbols"][0]["ts_code"] == "000001.SZ"
        assert attr["layers"]["A"][0]["symbols_total"] == 1

        resp = client.report_result(job_id, {"status": "done", **payload})
        assert resp["status"] == "done"

        detail = _job_status(cloud, job_id)
        assert detail["status"] == "done"
        assert detail["result"]["summary"]["strategy_total_return"] == 0.1
        assert detail["result"]["chart_data"]["equity"][0] == 100000.0
        assert detail["result"]["chart_data"]["tag_analysis"]["layers"]["A"][0]["tag"] == "银行"
        assert detail["result"]["data_until"] == "2026-01-07"

    def test_daemon_single_round_done(self, cloud, mock_engine, tmp_path):
        job_id = _create_job(cloud, kind="smoke")
        client = _make_client(cloud)
        daemon = WorkerDaemon(client, poll_seconds=0, heartbeat_seconds=3600)
        assert daemon.run_once() is True
        assert _job_status(cloud, job_id)["status"] == "done"

    def test_daemon_empty_round(self, cloud):
        daemon = WorkerDaemon(_make_client(cloud), poll_seconds=0)
        assert daemon.run_once() is False

    def test_runner_failure_reports_failed_then_requeued(self, cloud, monkeypatch):
        job_id = _create_job(cloud)
        monkeypatch.setattr(runner_mod, "run_backtest",
                            lambda **kw: {"status": "failed", "error": "engine boom"})
        daemon = WorkerDaemon(_make_client(cloud), poll_seconds=0, heartbeat_seconds=3600)
        assert daemon.run_once() is True
        job = _job_status(cloud, job_id)
        assert job["status"] == "queued"  # attempts 1 < max 2 → 回队
        assert "engine boom" in job["error"]
        # 第二轮：attempts 耗尽 → failed
        assert daemon.run_once() is True
        assert _job_status(cloud, job_id)["status"] == "failed"

    def test_heartbeat_sent_during_run(self, cloud):
        job_id = _create_job(cloud)
        client = _make_client(cloud)
        job = client.lease()
        beats = []
        orig_hb = client.heartbeat
        client.heartbeat = lambda jid: (beats.append(jid), orig_hb(jid))[1]
        gate = [False]

        def slow_runner(j):
            # 等心跳线程至少发 2 次（heartbeat_seconds 很小）
            import time as _t
            for _ in range(100):
                if len(beats) >= 2:
                    break
                _t.sleep(0.01)
            gate[0] = True
            return {"summary": {}, "chart_data": {}, "artifacts": [], "data_until": "2026-03-01"}

        daemon = WorkerDaemon(client, runner=slow_runner, heartbeat_seconds=0.05)
        daemon._run_job(job)
        assert gate[0] and len(beats) >= 2
        assert _job_status(cloud, job_id)["status"] == "done"


class TestCloudClientRetry:
    def test_retry_on_network_error(self, cloud):
        calls = {"n": 0}
        _, tc = cloud

        def flaky(method, path, payload):
            calls["n"] += 1
            if calls["n"] < 3:
                raise urllib.error.URLError("connection reset")
            resp = tc.open(path, method=method, json=payload,
                           headers={"X-Worker-Token": WORKER_TOKEN})
            return resp.status_code, resp.get_json(silent=True) or {}

        client = CloudClient("http://x", WORKER_TOKEN, worker_id="w1",
                             request_fn=flaky, sleep=lambda s: None)
        assert client.lease() is None  # 第 3 次成功（空队列）
        assert calls["n"] == 3

    def test_give_up_after_max_retries(self):
        def always_fail(method, path, payload):
            raise urllib.error.URLError("down")

        client = CloudClient("http://x", "tok", request_fn=always_fail,
                             max_retries=3, sleep=lambda s: None)
        with pytest.raises(CloudError):
            client.lease()

    def test_4xx_not_retried(self):
        calls = {"n": 0}

        def bad_auth(method, path, payload):
            calls["n"] += 1
            return 401, {"ok": False, "error": "worker token 无效"}

        client = CloudClient("http://x", "tok", request_fn=bad_auth, sleep=lambda s: None)
        with pytest.raises(CloudError) as exc_info:
            client.lease()
        assert exc_info.value.status == 401
        assert calls["n"] == 1

    def test_wrong_token_end_to_end(self, cloud):
        _, tc = cloud

        def request_fn(method, path, payload):
            resp = tc.open(path, method=method, json=payload,
                           headers={"X-Worker-Token": "wrong"})
            return resp.status_code, resp.get_json(silent=True) or {}

        client = CloudClient("http://x", "wrong", worker_id="w1",
                             request_fn=request_fn, sleep=lambda s: None)
        with pytest.raises(CloudError) as exc_info:
            client.lease()
        assert exc_info.value.status == 401

    def test_cli_worker_subcommand_registered(self):
        from quant_research_engine.apps.cli import build_parser

        args = build_parser().parse_args(["worker", "--once", "--poll-seconds", "1"])
        assert args.command == "worker" and args.once and args.poll_seconds == 1.0


class TestTrimTagAnalysis:
    def test_truncates_symbols_keeps_aggregates(self):
        symbols = [{"ts_code": f"{i:06d}.SZ", "total_pnl": 1000 - i, "trades": 1, "win_rate": 0.5}
                   for i in range(150)]
        data = {"ok": True, "layers": {"A": [{"tag": "银行", "total_pnl": 123, "symbols": symbols}],
                                       "B": [], "C": []}, "notes": {}}
        trimmed = runner_mod.trim_tag_analysis(data)
        item = trimmed["layers"]["A"][0]
        assert item["total_pnl"] == 123  # 板块聚合不动
        assert item["symbols_total"] == 150 and item["symbols_truncated"] is True
        assert len(item["symbols"]) == 100  # TOP 50 + BOTTOM 50
        assert item["symbols"][0]["total_pnl"] == 1000
        assert item["symbols"][-1]["total_pnl"] == 1000 - 149

    def test_small_set_untouched(self):
        data = {"layers": {"A": [{"tag": "x", "symbols": [{"ts_code": "1"}]}]}}
        item = runner_mod.trim_tag_analysis(data)["layers"]["A"][0]
        assert item["symbols_truncated"] is False and item["symbols_total"] == 1
