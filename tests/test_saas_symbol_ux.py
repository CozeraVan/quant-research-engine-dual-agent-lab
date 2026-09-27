"""QRE-SAAS-SYMBOL-UX 测试：股票代码规范化/显示脱敏 + per-symbol 产物回传链路。

- symbol_norm 纯函数：号段推断、已带后缀兼容、非法代码友好报错、显示剥离、解析。
- /api/saas/jobs：params.codes 规范化落库（带后缀），非法代码 400。
- /api/results/<id>/symbols/<code>：无后缀 URL 解析 + 优先读 worker 回传的
  _symbol_details/<ts_code>.json.gz（ECS 无行情库路径），基准序列按个股净值日期对齐。
- worker.runner：_fill_excess_return（shared 模式超额收益补齐）与
  build_symbol_detail_files（产物生成/登记/体积截断）。
"""

from __future__ import annotations

import gzip
import json
import subprocess
import uuid

import pytest

from quant_research_engine.gui.saas import create_saas_app
from quant_research_engine.gui.saas.symbol_norm import (
    infer_exchange,
    normalize_ts_code,
    normalize_ts_codes,
    resolve_ts_code,
    strip_ts_suffix,
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
    db_name = f"qre_saas_test_{uuid.uuid4().hex[:12]}"
    _psql("postgres", "-c", f"CREATE DATABASE {db_name}")
    subprocess.run(
        ["psql", f"postgresql:///{db_name}", "-v", "ON_ERROR_STOP=1",
         "-f", "deploy/saas/cloud_schema.sql"],
        check=True, capture_output=True, text=True,
    )
    yield db_name
    _psql("postgres", "-c", f"DROP DATABASE IF EXISTS {db_name}")


@pytest.fixture()
def app(saas_db, tmp_path):
    app = create_saas_app()
    app.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
    app.config["SAAS_WORKER_TOKEN"] = WORKER_TOKEN
    app.config["SAAS_DEV_AUTH"] = "1"
    app.config["SAAS_AUTH_CHANNEL"] = "stub"
    app.config["SAAS_UPLOAD_DIR"] = str(tmp_path)
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
        conn.execute(text("TRUNCATE results, jobs, strategies, users, sessions, sms_codes RESTART IDENTITY CASCADE"))


class TestSymbolNorm:
    @pytest.mark.parametrize("raw,expected", [
        ("000001", "000001.SZ"), ("300750", "300750.SZ"),
        ("600519", "600519.SH"), ("688981", "688981.SH"),
        ("430047", "430047.BJ"), ("830799", "830799.BJ"), ("920001", "920001.BJ"),
        ("000001.SZ", "000001.SZ"), ("600519.sh", "600519.SH"),
        (" 000002 ", "000002.SZ"),
    ])
    def test_normalize(self, raw, expected):
        assert normalize_ts_code(raw) == expected

    @pytest.mark.parametrize("bad", ["", "12345", "1234567", "abcdef", "000001.XX", "150001"])
    def test_invalid_raises_friendly(self, bad):
        with pytest.raises(ValueError) as exc:
            normalize_ts_code(bad)
        assert "代码" in str(exc.value)

    def test_normalize_codes_split_and_dedup(self):
        assert normalize_ts_codes("000001, 600519，300750\n000001") == [
            "000001.SZ", "600519.SH", "300750.SZ"]
        assert normalize_ts_codes(["600519", "000001.SZ"]) == ["600519.SH", "000001.SZ"]
        assert normalize_ts_codes(None) == []

    def test_strip_suffix(self):
        assert strip_ts_suffix("000001.SZ") == "000001"
        assert strip_ts_suffix("600519.sh") == "600519"
        assert strip_ts_suffix("000001") == "000001"

    def test_resolve_prefers_known_list(self):
        known = ["000001.SZ", "600519.SH"]
        assert resolve_ts_code("000001", known) == "000001.SZ"
        assert resolve_ts_code("600519", known) == "600519.SH"
        assert resolve_ts_code("300750", known) == "300750.SZ"  # 不在表内按号段推断
        assert resolve_ts_code("000001.sz") == "000001.SZ"
        with pytest.raises(ValueError):
            resolve_ts_code("bogus", known)


class TestCreateJobNormalizeCodes:
    def _create(self, client, codes):
        return client.post(
            "/api/saas/jobs",
            json={"yaml": "signal:\n  entry: 'true'\n", "kind": "full",
                  "params": {"codes": codes}, "name": "t"},
            headers={"X-User-Id": "1"},
        )

    def test_bare_digits_normalized_on_submit(self, client):
        resp = self._create(client, ["000001", "600519", "430047"])
        assert resp.status_code == 200
        job_id = resp.get_json()["job_id"]
        job = client.get(f"/api/saas/jobs/{job_id}", headers={"X-User-Id": "1"}).get_json()["job"]
        assert job["params"]["codes"] == ["000001.SZ", "600519.SH", "430047.BJ"]

    def test_string_codes_and_suffix_passthrough(self, client):
        resp = self._create(client, "000001.SZ, 600519")
        assert resp.status_code == 200
        job_id = resp.get_json()["job_id"]
        job = client.get(f"/api/saas/jobs/{job_id}", headers={"X-User-Id": "1"}).get_json()["job"]
        assert job["params"]["codes"] == ["000001.SZ", "600519.SH"]

    def test_invalid_code_400_friendly(self, client):
        resp = self._create(client, ["12345"])
        assert resp.status_code == 400
        assert "代码" in resp.get_json()["error"]


def _complete_job_with_chart(client, chart_data):
    """创建会员任务并以旧单包协议直接置 completed（带 chart_data）。"""
    resp = client.post(
        "/api/saas/jobs",
        json={"yaml": "signal:\n  entry: 'true'\n", "kind": "full",
              "params": {"codes": ["000001"]}, "name": "t"},
        headers={"X-User-Id": "1"},
    )
    job_id = resp.get_json()["job_id"]
    client.post("/api/saas/worker/jobs/lease", json={"worker_id": "w1"}, headers=WORKER_HEADERS)
    done = client.post(
        f"/api/saas/worker/jobs/{job_id}/result",
        json={"worker_id": "w1", "status": "done",
              "summary": {"strategy_total_return": 0.1}, "chart_data": chart_data},
        headers=WORKER_HEADERS,
    )
    assert done.get_json()["status"] == "completed"
    return job_id


class TestSymbolDetailFromUpload:
    def _write_detail(self, app, job_id, ts_code, payload):
        from pathlib import Path
        d = Path(app.config["SAAS_UPLOAD_DIR"]) / f"job_{job_id}" / "_symbol_details"
        d.mkdir(parents=True)
        (d / f"{ts_code}.json.gz").write_bytes(
            gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        )

    def _detail_payload(self):
        return {
            "ok": True,
            "summary": {"ts_code": "000001.SZ", "name": "平安银行", "total_pnl": 123.4,
                        "trades": 2, "avg_ret": 0.01, "win_rate": 0.5, "percentile": 0.1,
                        "bench_ret": 0.02, "total_ret_pct": 0.03},
            "trades": [{"entry_date": "2026-01-05", "exit_date": "2026-01-10"}],
            "orders": [{"trade_date": "2026-01-05", "side": "buy", "price": 10.0}],
            "failed_orders": [],
            "equity": {"dates": ["2026-01-05", "2026-01-06"], "values": [100000.0, 100100.0]},
            "kline": {"dates": ["2026-01-05", "2026-01-06"],
                      "ohlc": [[10.0, 10.1, 9.9, 10.2], [10.1, 10.0, 9.8, 10.3]],
                      "vols": [1000.0, 1200.0]},
            "factors": [{"name": "rsi_14", "values": [30.0, 31.0], "thresholds": [30.0]}],
        }

    def test_reads_uploaded_gzip_and_aligns_benchmarks(self, app, client):
        chart_data = {
            "dates": ["2026-01-05", "2026-01-06"],
            "benchmarks": {"000001.SH": {"name": "上证指数", "closes": [3000.0, 3010.0]}},
            "tag_analysis": {"layers": {"A": [{"tag": "银行", "symbols": [
                {"ts_code": "000001.SZ", "total_pnl": 1.0}]}]}},
        }
        job_id = _complete_job_with_chart(client, chart_data)
        self._write_detail(app, job_id, "000001.SZ", self._detail_payload())

        # 无后缀 URL 解析（展示脱敏后的链接形态）
        resp = client.get(f"/api/results/{job_id}/symbols/000001", headers={"X-User-Id": "1"})
        assert resp.status_code == 200
        d = resp.get_json()
        assert d["summary"]["ts_code"] == "000001.SZ"
        assert d["kline"]["dates"] == ["2026-01-05", "2026-01-06"]
        assert d["factors"][0]["name"] == "rsi_14"
        # 基准按个股净值日期从任务级 chart_data 对齐注入
        assert d["benchmarks"]["000001.SH"]["closes"] == [3000.0, 3010.0]

        # 带后缀 URL 兼容
        resp2 = client.get(f"/api/results/{job_id}/symbols/000001.SZ", headers={"X-User-Id": "1"})
        assert resp2.status_code == 200

    def test_suffixless_resolves_via_traded_symbols(self, app, client):
        """号段推断与实际不一致时，按实际交易个股匹配（known codes）。"""
        chart_data = {"tag_analysis": {"layers": {"A": [{"tag": "t", "symbols": [
            {"ts_code": "600000.SH", "total_pnl": 1.0}]}]}}}
        job_id = _complete_job_with_chart(client, chart_data)
        self._write_detail(app, job_id, "600000.SH", self._detail_payload())
        resp = client.get(f"/api/results/{job_id}/symbols/600000", headers={"X-User-Id": "1"})
        assert resp.status_code == 200

    def test_unknown_symbol_404_and_bad_code_400(self, app, client):
        job_id = _complete_job_with_chart(client, {"tag_analysis": {"layers": {}}})
        resp = client.get(f"/api/results/{job_id}/symbols/000002", headers={"X-User-Id": "1"})
        assert resp.status_code == 404
        resp = client.get(f"/api/results/{job_id}/symbols/abc", headers={"X-User-Id": "1"})
        assert resp.status_code == 400


class TestWorkerExcessFallback:
    def test_fill_excess_return_shared_mode(self, monkeypatch, tmp_path):
        from quant_research_engine.gui import lab_result
        from quant_research_engine.worker import runner

        monkeypatch.setattr(lab_result, "_symbol_trade_stats",
                            lambda record: {"000001.SZ": {}, "600519.SH": {}})
        monkeypatch.setattr(lab_result, "_fetch_symbol_range_returns",
                            lambda symbols, start, end: {"000001.SZ": 0.10, "600519.SH": 0.20})
        chart_data = {"metrics": {"total_return": 0.25, "excess_return": None,
                                  "buy_hold_return": None, "date_start": "2026-01-01",
                                  "date_end": "2026-06-01"}}
        runner._fill_excess_return({"run_id": "r1"}, chart_data)
        m = chart_data["metrics"]
        assert m["buy_hold_return"] == pytest.approx(0.15)
        assert m["excess_return"] == pytest.approx(0.10)
        assert "buy_hold_note" in m

    def test_fill_excess_return_noop_when_present(self, monkeypatch):
        from quant_research_engine.worker import runner

        chart_data = {"metrics": {"total_return": 0.25, "excess_return": 0.05}}
        runner._fill_excess_return({"run_id": "r1"}, chart_data)
        assert chart_data["metrics"]["excess_return"] == 0.05

    def test_fill_excess_return_db_down_keeps_none(self, monkeypatch):
        from quant_research_engine.gui import lab_result
        from quant_research_engine.worker import runner

        monkeypatch.setattr(lab_result, "_symbol_trade_stats",
                            lambda record: {"000001.SZ": {}})
        monkeypatch.setattr(lab_result, "_fetch_symbol_range_returns",
                            lambda symbols, start, end: None)
        chart_data = {"metrics": {"total_return": 0.25, "excess_return": None}}
        runner._fill_excess_return({"run_id": "r1"}, chart_data)
        assert chart_data["metrics"]["excess_return"] is None


class TestWorkerSymbolDetailFiles:
    def _record(self, tmp_path):
        out = tmp_path / "out"
        out.mkdir()
        (out / "round_trips.csv").write_text(
            "symbol,net_pnl,net_return,holding_days\n"
            "000001.SZ,100.0,0.01,5\n"
            "600519.SH,-50.0,-0.02,3\n",
            encoding="utf-8",
        )
        return {"run_id": "r1", "output_dir": str(out), "artifacts": {}}

    def test_builds_gzip_per_traded_symbol(self, monkeypatch, tmp_path):
        from quant_research_engine.gui import lab_result
        from quant_research_engine.worker import runner

        monkeypatch.setattr(
            lab_result, "build_lab_symbol_detail",
            lambda record, ts: {"ok": True, "summary": {"ts_code": ts},
                                "benchmarks": {"000001.SH": {"closes": [1]}},
                                "kline": {"dates": ["2026-01-05"]}},
        )
        record = self._record(tmp_path)
        meta = runner.build_symbol_detail_files(record)
        assert meta["count"] == 2 and meta["bytes"] > 0 and not meta["truncated"]
        path = tmp_path / "out" / "_symbol_details" / "000001.SZ.json.gz"
        assert path.exists()
        data = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
        assert data["summary"]["ts_code"] == "000001.SZ"
        assert "benchmarks" not in data  # 基准不随个股重复回传
        assert record["artifacts"]["_{p}/000001.SZ.json.gz".format(p="symbol_details")] == str(path)
        # collect_result_files 把 per-symbol 产物排在清单最前
        files = runner.collect_result_files(record)
        assert files[0]["name"].startswith("_symbol_details/")

    def test_truncation_by_bytes(self, monkeypatch, tmp_path):
        from quant_research_engine.gui import lab_result
        from quant_research_engine.worker import runner

        monkeypatch.setattr(
            lab_result, "build_lab_symbol_detail",
            lambda record, ts: {"ok": True, "pad": "x" * 10000},
        )
        record = self._record(tmp_path)
        meta = runner.build_symbol_detail_files(record, max_total_bytes=100)
        assert meta["truncated"] and meta["count"] < 2

    def test_no_trades_noop(self, tmp_path):
        from quant_research_engine.worker import runner

        out = tmp_path / "out"
        out.mkdir()
        meta = runner.build_symbol_detail_files({"run_id": "r", "output_dir": str(out)})
        assert meta["count"] == 0
