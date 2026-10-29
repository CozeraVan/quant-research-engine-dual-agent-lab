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
from pathlib import Path

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
            # QRE-FACTOR-QFQ-ANCHOR-DATE：现行产物必须带口径标记，否则 API 视为
            # 「口径未知」的旧快照而不下发（防止 EMA 等按 hfq 与 qfq K 线并列）
            "factor_basis": "qfq_anchor_v1",
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


class TestSymbolDetailDataUntil:
    """QRE-SAAS-RESULT-UNDERSTANDING：个股详情响应注入任务级数据截止。

    worker 回传 gzip 与本地 fallback 两条返回路径都要带 `data_until`
    （不改 gzip 产物、不回填），供页面头部展示并链接口径说明。
    """

    def _write_detail(self, app, job_id, ts_code, payload):
        import gzip
        import json

        d = Path(app.config["SAAS_UPLOAD_DIR"]) / f"job_{job_id}" / "_symbol_details"
        d.mkdir(parents=True)
        (d / f"{ts_code}.json.gz").write_bytes(
            gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        )

    def test_gzip_path_injects_task_data_until(self, app, client):
        chart_data = {"tag_analysis": {"layers": {"A": [{"tag": "银行", "symbols": [
            {"ts_code": "000001.SZ", "total_pnl": 1.0}]}]}}}
        resp = client.post(
            "/api/saas/jobs",
            json={"yaml": "signal:\n  entry: 'true'\n", "kind": "full",
                  "params": {"codes": ["000001"]}, "name": "t"},
            headers={"X-User-Id": "1"},
        )
        job_id = resp.get_json()["job_id"]
        client.post("/api/saas/worker/jobs/lease", json={"worker_id": "w1"},
                    headers=WORKER_HEADERS)
        done = client.post(
            f"/api/saas/worker/jobs/{job_id}/result",
            json={"worker_id": "w1", "status": "done",
                  "summary": {"strategy_total_return": 0.1}, "chart_data": chart_data,
                  "data_until": "2026-02-27"},
            headers=WORKER_HEADERS,
        )
        assert done.get_json()["status"] == "completed"
        self._write_detail(app, job_id, "000001.SZ", {
            "ok": True, "factor_basis": "qfq_anchor_v1",
            "summary": {"ts_code": "000001.SZ", "name": "平安银行"},
            "trades": [], "orders": [], "failed_orders": []})
        d = client.get(f"/api/results/{job_id}/symbols/000001",
                       headers={"X-User-Id": "1"}).get_json()
        assert d["data_until"] == "2026-02-27"
        assert d["summary"]["name"] == "平安银行"  # 原字段不受影响

    def test_local_fallback_injects_task_data_until(self, app, client, monkeypatch):
        chart_data = {"tag_analysis": {"layers": {}}}
        resp = client.post(
            "/api/saas/jobs",
            json={"yaml": "signal:\n  entry: 'true'\n", "kind": "full",
                  "params": {"codes": ["000001"]}, "name": "t"},
            headers={"X-User-Id": "1"},
        )
        job_id = resp.get_json()["job_id"]
        client.post("/api/saas/worker/jobs/lease", json={"worker_id": "w1"},
                    headers=WORKER_HEADERS)
        client.post(
            f"/api/saas/worker/jobs/{job_id}/result",
            json={"worker_id": "w1", "status": "done",
                  "summary": {"strategy_total_return": 0.1}, "chart_data": chart_data,
                  "data_until": "2026-02-27"},
            headers=WORKER_HEADERS,
        )
        monkeypatch.setattr(
            "quant_research_engine.gui.lab_result.build_lab_symbol_detail",
            lambda record, ts, **kw: {"ok": True, "summary": {"ts_code": ts},
                                      "trades": [], "orders": [], "failed_orders": []},
        )
        d = client.get(f"/api/results/{job_id}/symbols/000001",
                       headers={"X-User-Id": "1"}).get_json()
        assert d["data_until"] == "2026-02-27"


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
            lambda record, ts, **kw: {"ok": True, "summary": {"ts_code": ts},
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

    def test_risk_report_survives_upload_budget(self, tmp_path):
        """全量任务触及回传上限时，FRM 小文件也不得被逐股 CSV 挤掉。"""
        from quant_research_engine.worker import runner

        out = tmp_path / "out"
        (out / "_symbol_details").mkdir(parents=True)
        (out / "_symbol_details" / "000001.SZ.json.gz").write_bytes(b"s" * 60)
        (out / "a.csv").write_bytes(b"a" * 35)
        (out / "risk_report.json").write_bytes(b"r" * 10)
        record = {
            "artifacts": {
                "a.csv": str(out / "a.csv"),
                "risk_report.json": str(out / "risk_report.json"),
                "_symbol_details/000001.SZ.json.gz": str(out / "_symbol_details" / "000001.SZ.json.gz"),
            }
        }
        files = runner.collect_result_files(record, max_total_bytes=100)
        assert [f["name"] for f in files] == [
            "risk_report.json", "_symbol_details/000001.SZ.json.gz",
        ]

    def test_truncation_by_bytes(self, monkeypatch, tmp_path):
        from quant_research_engine.gui import lab_result
        from quant_research_engine.worker import runner

        monkeypatch.setattr(
            lab_result, "build_lab_symbol_detail",
            lambda record, ts, **kw: {"ok": True, "pad": "x" * 10000},
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


    def test_round_trips_parsed_once_for_many_symbols(self, monkeypatch, tmp_path):
        """Bug 4 回归：N 只股票的 detail 构建只解析一次 round_trips.csv
        （job 54 卡死根因：每 symbol 重读全量 CSV，O(股票数×交易数)）。"""
        from quant_research_engine.gui import lab_result
        from quant_research_engine.worker import runner

        record = self._record(tmp_path)  # round_trips.csv 含 2 只 symbol

        stats_calls = []
        orig_stats = lab_result._symbol_trade_stats
        monkeypatch.setattr(
            lab_result, "_symbol_trade_stats",
            lambda rec: (stats_calls.append(1), orig_stats(rec))[1],
        )
        read_calls = []
        orig_read = lab_result._read_csv
        monkeypatch.setattr(
            lab_result, "_read_csv",
            lambda p: (read_calls.append(str(p)), orig_read(p))[1],
        )
        captured = {}

        def spy_detail(rec, ts, **kw):
            captured[ts] = kw
            return {"ok": True, "summary": {"ts_code": ts}}

        monkeypatch.setattr(lab_result, "build_lab_symbol_detail", spy_detail)
        meta = runner.build_symbol_detail_files(record)

        assert meta["count"] == 2
        assert len(stats_calls) == 1  # stats 只算一次
        # round_trips.csv 全文读取仅 2 次（stats 聚合 + 按 symbol 预分组），与股票数无关
        rt_reads = [p for p in read_calls if p.endswith("round_trips.csv")]
        assert len(rt_reads) == 2
        # 每股调用都拿到了预算好的 stats 与分组行
        for ts in ("000001.SZ", "600519.SH"):
            assert ts in captured[ts]["stats"]
            assert captured[ts]["round_trips_by_symbol"][ts]


class TestEnrichSharedSymbolDetail:
    """shared（共享资金）模式无 per-symbol 目录：enrich 从任务级产物补齐
    orders/failed_orders/wear/单票净值（job 21 线上缺陷修复）。"""

    def _record(self, tmp_path):
        out = tmp_path / "out"
        out.mkdir()
        (out / "orders.csv").write_text(
            "symbol,trade_date,side,quantity,price,notional,cost,reason\n"
            "603970.SH,2024-10-15,buy,700,13.58,9506.0,5.09,\n"
            "603970.SH,2024-11-12,sell,700,14.73,10311.0,10.26,\n"
            "000001.SZ,2024-10-15,buy,100,10.0,1000.0,1.0,\n",
            encoding="utf-8",
        )
        (out / "failed_orders.csv").write_text(
            "symbol,trade_date,side,quantity,price,notional,reason\n"
            "603970.SH,2024-12-01,buy,100,15.0,1500.0,price_limit\n",
            encoding="utf-8",
        )
        (out / "equity_curve.csv").write_text(
            "trade_date,cash,market_value,total_equity,position_count\n"
            "2024-10-14,100000.0,0.0,100000.0,0\n"
            "2024-10-15,90500.0,9506.0,100006.0,1\n"
            "2024-11-12,100500.0,0.0,100500.0,0\n",
            encoding="utf-8",
        )
        return {"run_id": "r1", "output_dir": str(out), "artifacts": {}}

    def _trades(self):
        return [{"symbol": "603970.SH", "commission": 5.09, "stamp_tax": 10.26,
                 "transfer_fee": 0.5, "total_cost": 15.85, "gross_pnl": 805.0,
                 "net_pnl": 789.15, "entry_notional": 9506.0}]

    def test_fills_orders_failed_wear_equity_single_symbol(self, tmp_path):
        from quant_research_engine.worker.runner import _enrich_shared_symbol_detail

        data = {"summary": {}, "trades": self._trades(),
                "orders": None, "failed_orders": None, "equity": None}
        _enrich_shared_symbol_detail(self._record(tmp_path), data, "603970.SH",
                                     single_symbol=True)
        assert len(data["orders"]) == 2  # 只含该股，不含 000001.SZ 的行
        assert all(o["symbol"] == "603970.SH" for o in data["orders"])
        assert len(data["failed_orders"]) == 1
        w = data["wear"]
        assert w["total_cost"] == 15.85 and w["invested"] == 9506.0
        assert w["gross_pnl"] == 805.0 and w["net_pnl"] == 789.15 and w["trades"] == 1
        # other_cost = total_cost − commission − stamp_tax（已含 transfer_fee 与滑点残差，
        # 与 job 的 fees_summary.other_cost 同口径）；显示层不得再叠加 transfer_fee
        assert w["commission"] == 5.09 and w["stamp_tax"] == 10.26
        assert w["transfer_fee"] == 0.5
        assert w["other_cost"] == 0.5
        assert round(w["commission"] + w["stamp_tax"] + w["other_cost"], 2) == w["total_cost"]
        eq = data["equity"]
        assert eq["dates"] == ["2024-10-14", "2024-10-15", "2024-11-12"]
        assert eq["values"] == [100000.0, 100006.0, 100500.0]
        assert data["summary"]["total_ret_pct"] == pytest.approx(0.005)

    def test_multi_symbol_keeps_equity_none(self, tmp_path):
        from quant_research_engine.worker.runner import _enrich_shared_symbol_detail

        data = {"summary": {}, "trades": self._trades(),
                "orders": None, "failed_orders": None, "equity": None}
        _enrich_shared_symbol_detail(self._record(tmp_path), data, "603970.SH",
                                     single_symbol=False)
        assert data["equity"] is None  # 多股 shared 组合净值无法按股拆，不编数
        assert len(data["orders"]) == 2  # orders/wear 仍可补齐

    def test_existing_fields_not_overwritten(self, tmp_path):
        from quant_research_engine.worker.runner import _enrich_shared_symbol_detail

        data = {"summary": {}, "trades": self._trades(),
                "orders": [{"trade_date": "2024-10-15"}],
                "failed_orders": [],
                "equity": {"dates": ["2024-01-01"], "values": [1.0]},
                "wear": {"total_cost": 1.0}}
        _enrich_shared_symbol_detail(self._record(tmp_path), data, "603970.SH",
                                     single_symbol=True)
        assert data["orders"] == [{"trade_date": "2024-10-15"}]
        assert data["failed_orders"] == []
        assert data["equity"]["values"] == [1.0]
        assert data["wear"] == {"total_cost": 1.0}

    def test_no_top_level_files_noop(self, tmp_path):
        from quant_research_engine.worker.runner import _enrich_shared_symbol_detail

        out = tmp_path / "empty"
        out.mkdir()
        data = {"summary": {}, "trades": [], "orders": None, "equity": None}
        _enrich_shared_symbol_detail({"run_id": "r", "output_dir": str(out)},
                                     data, "603970.SH", single_symbol=True)
        assert data["orders"] is None and data["equity"] is None and "wear" not in data

    def test_e2e_shared_job_produces_enriched_gzip(self, monkeypatch, tmp_path):
        """build_symbol_detail_files 端到端：单股 shared run 的 gz 含 equity/orders/wear。"""
        from quant_research_engine.gui import lab_result
        from quant_research_engine.worker import runner

        record = self._record(tmp_path)
        out = tmp_path / "out"
        (out / "round_trips.csv").write_text(
            "symbol,net_pnl,net_return,holding_days,commission,stamp_tax,transfer_fee,"
            "total_cost,gross_pnl,entry_notional\n"
            "603970.SH,789.15,0.083,28,5.09,10.26,0.5,15.85,805.0,9506.0\n",
            encoding="utf-8",
        )

        def fake_detail(rec, ts, **kw):
            return {"ok": True, "summary": {"ts_code": ts},
                    "trades": [{"symbol": ts, "commission": 5.09, "stamp_tax": 10.26,
                                "transfer_fee": 0.5, "total_cost": 15.85,
                                "gross_pnl": 805.0, "net_pnl": 789.15,
                                "entry_notional": 9506.0}],
                    "trades_source": "round_trips",
                    "orders": None, "failed_orders": None, "equity": None,
                    "kline": {"dates": ["2024-10-15"]}, "factors": []}

        monkeypatch.setattr(lab_result, "build_lab_symbol_detail", fake_detail)
        meta = runner.build_symbol_detail_files(record)
        assert meta["count"] == 1
        blob = (out / "_symbol_details" / "603970.SH.json.gz").read_bytes()
        data = json.loads(gzip.decompress(blob).decode("utf-8"))
        assert data["equity"]["values"][-1] == 100500.0
        assert len(data["orders"]) == 2
        assert data["wear"]["total_cost"] == 15.85


class TestSymbolDetailArchiveFallback:
    """QRE-SAAS-ARTIFACT-ARCHIVE：旧系产物归档后，详情页仍可读（TV R6 收尾）。

    背景：MACD 旧系列名产物（job 58/66 共 496 个 per-symbol gzip）按用户
    2026-10-30 的「归档」决定移出 `SAAS_UPLOAD_DIR`，让周扫 `legacy_total`
    合法归零（20_DATA_DICTIONARY §4.1.1 退场前置动作）。但 58/66 是公开展示的
    经典策略，详情页必须继续可读——故 live 找不到时回落到归档目录，
    再找不到才走既有 fallback（ECS 无行情库 → 404 + can_generate）。
    """

    def _payload(self):
        return {
            "ok": True,
            "factor_basis": "qfq_anchor_v1",
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
            "factors": [{"name": "macd_dif", "values": [0.1, 0.2], "thresholds": []}],
        }

    def _write(self, base, job_id, ts_code):
        d = Path(base) / f"job_{job_id}" / "_symbol_details"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{ts_code}.json.gz").write_bytes(
            gzip.compress(json.dumps(self._payload(), ensure_ascii=False).encode("utf-8"))
        )

    def _isolate(self, app, tmp_path):
        """把 upload_root 也挪进本测试的 tmp_path，归档根（upload_root 的兄弟目录
        archive/）随之隔离——否则跨测试共用 pytest session tmp 会互相污染。"""
        app.config["SAAS_UPLOAD_DIR"] = str(tmp_path / "up")
        return tmp_path / "archive"

    def test_served_from_default_archive_when_live_missing(self, app, client, tmp_path):
        """缺省归档根 = upload_root 的兄弟目录 archive/（不配 SAAS_ARCHIVE_DIR）。"""
        base = self._isolate(app, tmp_path)
        job_id = _complete_job_with_chart(client, {"tag_analysis": {"layers": {}}})
        self._write(base, job_id, "000001.SZ")

        resp = client.get(f"/api/results/{job_id}/symbols/000001", headers={"X-User-Id": "1"})
        assert resp.status_code == 200
        d = resp.get_json()
        assert d["ok"] is True
        assert d["summary"]["ts_code"] == "000001.SZ"
        assert d["factors"][0]["name"] == "macd_dif"

    def test_served_from_explicit_archive_dir(self, app, client, tmp_path):
        """SAAS_ARCHIVE_DIR 可显式覆盖归档根。"""
        app.config["SAAS_ARCHIVE_DIR"] = str(tmp_path / "vault")
        job_id = _complete_job_with_chart(client, {"tag_analysis": {"layers": {}}})
        self._write(tmp_path / "vault", job_id, "000001.SZ")

        resp = client.get(f"/api/results/{job_id}/symbols/000001", headers={"X-User-Id": "1"})
        assert resp.status_code == 200
        assert resp.get_json()["summary"]["ts_code"] == "000001.SZ"

    def test_live_dir_still_wins_over_archive(self, app, client, tmp_path):
        """live 与归档同时存在时 live 优先（新产物不被旧快照盖住）。"""
        app.config["SAAS_ARCHIVE_DIR"] = str(tmp_path / "vault")
        self._isolate(app, tmp_path)
        job_id = _complete_job_with_chart(client, {"tag_analysis": {"layers": {}}})
        self._write(tmp_path / "vault", job_id, "000001.SZ")
        live_payload = self._payload()
        live_payload["summary"]["name"] = "LIVE版"
        d = Path(app.config["SAAS_UPLOAD_DIR"]) / f"job_{job_id}" / "_symbol_details"
        d.mkdir(parents=True)
        (d / "000001.SZ.json.gz").write_bytes(
            gzip.compress(json.dumps(live_payload, ensure_ascii=False).encode("utf-8"))
        )

        resp = client.get(f"/api/results/{job_id}/symbols/000001", headers={"X-User-Id": "1"})
        assert resp.status_code == 200
        assert resp.get_json()["summary"]["name"] == "LIVE版"

    def test_missing_everywhere_still_404_can_generate(self, app, client, tmp_path):
        """live 与归档都没有 → 保持既有 404 + can_generate（不静默给空数据）。"""
        self._isolate(app, tmp_path)
        job_id = _complete_job_with_chart(client, {"tag_analysis": {"layers": {}}})
        resp = client.get(f"/api/results/{job_id}/symbols/000001", headers={"X-User-Id": "1"})
        assert resp.status_code == 404
        assert resp.get_json()["can_generate"] is True
