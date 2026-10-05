"""QRE-SAAS M3 Worker 客户端测试（本地闭环：saas app test_client 当真实云端）。

- CloudClient 经注入 request_fn 直连 Flask test_client（同一个 PG 临时库，
  fixture 模式复用 test_gui_saas.py：psql 建/销库 + apply schema + TRUNCATE）。
- 引擎层（run_backtest）mock 成本地产物（真实 strategy_performance.json /
  equity_curve.csv / round_trips.csv 小数据），lab_result 组装逻辑真实过一遍。
- 基准指数查库（lab_result._benchmark_series）打桩，保持测试不依赖本地大库。
"""

from __future__ import annotations

import hashlib
import io
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


def test_job_params_prefers_params_json():
    """C5 联调修复：claim 下发 17 协议字段 params_json 必须生效（此前被丢弃按默认参数跑）。"""
    from quant_research_engine.worker.runner import _job_params

    job = {"params_json": {"start": "2026-03-01", "codes": ["300054.SZ"]}}
    assert _job_params(job)["start"] == "2026-03-01"
    assert _job_params(job)["codes"] == ["300054.SZ"]
    # 兼容：旧键 params 仍可用；params_json 为字符串 JSON 也可解析；空值安全
    assert _job_params({"params": {"a": 1}})["a"] == 1
    assert _job_params({"params_json": '{"b": 2}'})["b"] == 2
    assert _job_params({}) == {}


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
    # RUNS_DIR 隔离到临时目录（产物持久化断言用，不污染真实 outputs/）
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
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

        resp = client.report_result(job_id, {**payload, "files": []})  # 默认不上传文件
        assert resp["status"] == "completed"

        detail = _job_status(cloud, job_id)
        assert detail["status"] == "completed"
        assert detail["result"]["summary"]["strategy_total_return"] == 0.1
        assert detail["result"]["chart_data"]["equity"][0] == 100000.0
        assert detail["result"]["chart_data"]["tag_analysis"]["layers"]["A"][0]["tag"] == "银行"
        assert detail["result"]["data_until"] == "2026-01-07"

    def test_daemon_single_round_done(self, cloud, mock_engine, tmp_path):
        job_id = _create_job(cloud, kind="smoke")
        client = _make_client(cloud)
        daemon = WorkerDaemon(client, poll_seconds=0, heartbeat_seconds=3600)
        assert daemon.run_once() is True
        assert _job_status(cloud, job_id)["status"] == "completed"

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
        assert "engine boom" in job["error_message"]
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
        assert _job_status(cloud, job_id)["status"] == "completed"


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


class TestArtifactPersistence:
    """缺陷回归：worker 的 /tmp 沙箱产物必须拷回 RUNS_DIR 持久位置
    （否则 WSL 重启后详情页 chart-data 全空）。"""

    def test_artifacts_copied_to_runs_dir(self, cloud, mock_engine, tmp_path):
        job_id = _create_job(cloud)
        client = _make_client(cloud)
        job = client.lease()
        sandbox_dir = tmp_path / "sandbox"
        payload = runner_mod.execute_job(job, work_base=sandbox_dir)

        from quant_research_engine.gui import engine as gui_engine

        persistent = gui_engine.RUNS_DIR / "test_run_1" / "artifacts"
        # 产物拷回持久位置
        assert (persistent / "equity_curve.csv").exists()
        assert (persistent / "round_trips.csv").exists()
        assert (persistent / "strategy_performance.json").exists()
        # status.json 的 artifacts map / output_dir 指向持久副本
        record = json.loads((persistent.parent / "status.json").read_text(encoding="utf-8"))
        assert record["output_dir"] == str(persistent)
        assert all(str(persistent) in p for p in record["artifacts"].values())
        # /tmp 原件保留（清理由既有逻辑决定，不引入新行为）
        assert (sandbox_dir / "artifacts" / "equity_curve.csv").exists()
        # chart-data loader 能从持久副本读到（equity 序列正常组装）
        assert payload["chart_data"]["equity"][0] == 100000.0
        # 模拟 /tmp 丢失后 loader 仍可用
        import shutil

        shutil.rmtree(sandbox_dir)
        from quant_research_engine.gui.lab_result import build_lab_chart_data

        rebuilt = build_lab_chart_data(record)
        assert rebuilt["equity"] == [100000.0, 101000.0, 100500.0]

    def test_re_persist_replaces_stale_copy(self, cloud, mock_engine, tmp_path):
        """同一 run_id 重复执行：旧持久副本先清再拷（不留陈旧文件）。"""
        job_id = _create_job(cloud)
        client = _make_client(cloud)
        job = client.lease()
        runner_mod.execute_job(job, work_base=tmp_path / "a")

        from quant_research_engine.gui import engine as gui_engine

        persistent = gui_engine.RUNS_DIR / "test_run_1" / "artifacts"
        stale = persistent / "stale.txt"
        stale.write_text("old", encoding="utf-8")
        runner_mod.execute_job(job, work_base=tmp_path / "b")
        assert not stale.exists()
        assert (persistent / "equity_curve.csv").exists()


class TestA3ExecutionLoop:
    """A3：取消传播 / 两步回传（meta+files）/ 幂等重传 / 环境变量别名。"""

    def test_cancel_propagation(self, cloud):
        """心跳发现 cancel_requested → fail(canceled) 上报，结果不回传。"""
        job_id = _create_job(cloud)
        client = _make_client(cloud)
        job = client.claim()
        # 用户取消
        _, tc = cloud
        tc.post(f"/api/jobs/{job_id}/cancel", headers={"X-User-Id": "1"})
        calls = {"fail": None, "result": None}
        orig_fail, orig_report = client.fail, client.report_result
        client.fail = lambda *a, **kw: (calls.__setitem__("fail", (a, kw)), orig_fail(*a, **kw))[1]
        client.report_result = lambda *a, **kw: (calls.__setitem__("result", True), orig_report(*a, **kw))[1]

        def slow_runner(j):
            import time as _t
            _t.sleep(0.4)  # 等心跳线程发现取消
            return {"summary": {}, "chart_data": {}, "artifacts": [], "files": [], "data_until": "2026-09-04"}

        daemon = WorkerDaemon(client, runner=slow_runner, heartbeat_seconds=0.05)
        daemon._run_job(job)
        assert calls["fail"] is not None and calls["fail"][1].get("error_class") == "canceled"
        assert calls["result"] is None  # 取消后不回传结果
        assert _job_status(cloud, job_id)["status"] == "canceled"

    def test_two_step_result_with_file_upload(self, cloud, tmp_path, monkeypatch):
        """meta → upload_token → files：文件到达云端且 sha256 校验过。"""
        monkeypatch.setenv("QRE_WORKER_UPLOAD_FILES", "1")
        job_id = _create_job(cloud)
        blob = b"trade_date,total_equity\n2026-01-05,100000\n"
        art = tmp_path / "equity_curve.csv"
        art.write_bytes(blob)
        _, tc = cloud

        client = _make_client(cloud)
        # upload_fn 走 saas test_client（与 request_fn 同一个云端）
        def upload_fn(jid, token, files):
            data = {name: (io.BytesIO(b), name) for name, b in files.items()}
            resp = tc.post(f"/api/worker/jobs/{jid}/result/files?upload_token={token}",
                           data=data, headers={"X-Worker-Token": WORKER_TOKEN})
            return resp.get_json()
        client._upload_fn = upload_fn

        job = client.claim()
        payload = {
            "summary": {"strategy_total_return": 0.1}, "chart_data": {}, "data_until": "2026-09-04",
            "files": [{"name": "equity_curve.csv", "size": len(blob),
                       "sha256": hashlib.sha256(blob).hexdigest(), "path": str(art)}],
        }
        daemon = WorkerDaemon(client, runner=lambda j: payload, heartbeat_seconds=3600)
        daemon._run_job(job)
        assert _job_status(cloud, job_id)["status"] == "completed"
        # 幂等：重复 meta 提交不报错（覆盖写）
        again = client.report_result(job_id, payload)
        assert again["ok"] or again.get("status") in ("completed", "uploading")

    def test_env_var_aliases(self, monkeypatch):
        monkeypatch.setenv("QRE_SAAS_BASE_URL", "http://new")
        monkeypatch.setenv("QRE_WORKER_TOKEN", "tok")
        monkeypatch.setenv("QRE_WORKER_ID", "wid")
        c = CloudClient.from_env(request_fn=lambda m, p, j: (200, {"job": None}))
        assert c.base_url == "http://new" and c.worker_id == "wid"
        # 旧变量回退
        monkeypatch.delenv("QRE_SAAS_BASE_URL")
        monkeypatch.setenv("SAAS_CLOUD_URL", "http://old")
        c2 = CloudClient.from_env(request_fn=lambda m, p, j: (200, {}))
        assert c2.base_url == "http://old"

    def test_module_entrypoint(self):
        import quant_research_engine.worker.__main__  # noqa: F401


class TestUniversePassthrough:
    """QRE-SAAS-METADATA：params.universe={group,key} 在 worker 本地解析为 codes。"""

    def test_universe_resolved_to_codes(self, cloud, mock_engine, tmp_path, monkeypatch):
        captured = {}
        orig = runner_mod.run_backtest

        def capture(**kw):
            captured.update(kw)
            return orig(**kw)

        monkeypatch.setattr(runner_mod, "run_backtest", capture)
        monkeypatch.setattr(
            "quant_research_engine.gui.universe.universe_members",
            lambda group, key, db_url=None: ["000001.SZ", "600000.SH"],
        )
        job_id = _create_job(cloud)
        client = _make_client(cloud)
        job = client.claim()
        job["params"] = {"start": "2026-01-01", "end": "2026-03-01",
                         "universe": {"group": "sw1", "key": "电子"}}
        payload = runner_mod.execute_job(job, work_base=tmp_path)
        assert captured["codes"] == "000001.SZ,600000.SH"
        assert payload["summary"]["strategy_total_return"] == 0.1

    def test_universe_empty_fails(self, cloud, mock_engine, tmp_path, monkeypatch):
        monkeypatch.setattr("quant_research_engine.gui.universe.universe_members",
                            lambda group, key, db_url=None: [])
        job_id = _create_job(cloud)
        job = _make_client(cloud).claim()
        job["params"] = {"universe": {"group": "sw1", "key": "空板块"}}
        with pytest.raises(RuntimeError, match="无成分股"):
            runner_mod.execute_job(job, work_base=tmp_path)


class TestGuestCodesAutoFill:
    """2026-10-05 内测调整：游客自选不足 10 只时 worker 执行前随机补齐。"""

    def test_fill_to_ten(self):
        from quant_research_engine.worker.runner import fill_guest_codes
        pool = [f"000{i:03d}.SZ" for i in range(50)]
        out = fill_guest_codes(["000001.SZ", "600519.SH"], 10, pool_fn=lambda: pool)
        assert len(out) == 10
        assert out[:2] == ["000001.SZ", "600519.SH"]  # 自选保留在前
        assert len(set(out)) == 10  # 无重复

    def test_already_full_noop(self):
        from quant_research_engine.worker.runner import fill_guest_codes
        codes = [f"c{i}" for i in range(10)]
        assert fill_guest_codes(codes, 10, pool_fn=lambda: ["x"]) == codes

    def test_no_marker_noop(self):
        from quant_research_engine.worker.runner import fill_guest_codes
        assert fill_guest_codes(["a"], None, pool_fn=lambda: ["b"]) == ["a"]

    def test_pool_smaller_than_need(self):
        from quant_research_engine.worker.runner import fill_guest_codes
        out = fill_guest_codes(["a"], 10, pool_fn=lambda: ["a", "b", "c"])
        assert out == ["a", "b", "c"] or sorted(out) == ["a", "b", "c"]
