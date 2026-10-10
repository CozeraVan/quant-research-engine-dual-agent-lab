from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from quant_research_engine.gui.engine import (
    apply_precheck,
    build_market_profile,
    compare_run_summaries,
    equity_curve_svg,
    extract_run_summary,
    release_run_slot,
    running_count,
    try_acquire_run_slot,
    MAX_CONCURRENT_RUNS,
    PRECHECK_MAX_CODES,
)


# --- build_market_profile (成本覆盖) ---


def test_build_market_profile_defaults():
    profile = build_market_profile(None)
    assert profile.commission_rate == pytest.approx(0.0003)
    assert profile.min_commission == pytest.approx(5.0)
    assert profile.stamp_tax_sell == pytest.approx(0.0005)
    assert profile.slippage_buy_rate == pytest.approx(0.0)
    assert profile.slippage_sell_rate == pytest.approx(0.0)


def test_build_market_profile_overrides():
    profile = build_market_profile({
        "commission_rate": 0.0002,
        "min_commission": 1.0,
        "stamp_tax_sell": 0.001,
        "slippage_buy_rate": 0.002,
        "slippage_sell_rate": 0.003,
    })
    assert profile.commission_rate == pytest.approx(0.0002)
    assert profile.min_commission == pytest.approx(1.0)
    assert profile.stamp_tax_sell == pytest.approx(0.001)
    assert profile.slippage_buy_rate == pytest.approx(0.002)
    assert profile.slippage_sell_rate == pytest.approx(0.003)
    # untouched fields keep defaults
    assert profile.transfer_fee_rate == pytest.approx(0.00001)


def test_build_market_profile_ignores_unknown_and_none():
    profile = build_market_profile({"commission_rate": 0.0001, "bogus_field": 9.9, "min_commission": None})
    assert profile.commission_rate == pytest.approx(0.0001)
    assert profile.min_commission == pytest.approx(5.0)
    assert not hasattr(profile, "bogus_field") or getattr(profile, "bogus_field", None) != 9.9


# --- apply_precheck (小样本预检截断) ---


def test_apply_precheck_truncates_codes():
    codes = [f"{i:06d}.SZ" for i in range(30)]
    trimmed, start, end = apply_precheck(codes, "2026-01-01", "2026-03-31")
    assert trimmed == codes[:PRECHECK_MAX_CODES]
    assert len(trimmed) == 20


def test_apply_precheck_truncates_window_to_six_months():
    trimmed, start, end = apply_precheck(["000001.SZ"], "2010-01-04", "2026-03-31")
    assert start == "2025-10-02"  # end - 180 days
    assert end == "2026-03-31"


def test_apply_precheck_keeps_short_window():
    trimmed, start, end = apply_precheck(["000001.SZ"], "2026-03-01", "2026-03-31")
    assert start == "2026-03-01"
    assert end == "2026-03-31"


def test_apply_precheck_samples_when_codes_empty(monkeypatch):
    """空 codes（全市场 scope）绝不放行——按 seed 从全 A 池随机抽 max_codes 只。

    job 54 事故：codes=[] 原样返回导致 smoke 跑了全市场 5533 只。
    """
    from quant_research_engine.gui import engine as gui_engine

    pool = [f"{i:06d}.SZ" for i in range(1, 100)]
    calls = []
    monkeypatch.setattr(
        gui_engine,
        "_sample_random_universe",
        lambda n, seed, db_url=None: (calls.append((n, seed)), pool[:n])[1],
    )
    trimmed, start, end = apply_precheck([], "2010-01-04", "2026-03-31", max_codes=1, seed="rid-1")
    assert calls == [(1, "rid-1")]
    assert trimmed == pool[:1]
    assert start == "2025-10-02"
    assert end == "2026-03-31"

    # 同 seed 可复现
    trimmed2, _, _ = apply_precheck([], "2010-01-04", "2026-03-31", max_codes=1, seed="rid-1")
    assert trimmed2 == trimmed


# --- concurrency slots (限流) ---


def test_run_slot_limit():
    acquired = []
    try:
        for _ in range(MAX_CONCURRENT_RUNS + 1):
            acquired.append(try_acquire_run_slot())
        assert acquired == [True, True, False]
        assert running_count() == MAX_CONCURRENT_RUNS
    finally:
        for ok in acquired:
            if ok:
                release_run_slot()
    assert running_count() == 0


# --- extract_run_summary ---


def _record(tmp_path: Path, run_id: str = "r1", output_dir: str | None = None) -> dict:
    return {"run_id": run_id, "output_dir": output_dir, "mode": "batch"}


def test_extract_summary_from_json_in_backtest_subdir(monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    (runs_dir / "r1").mkdir(parents=True)
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", runs_dir)

    out = tmp_path / "out"
    (out / "backtest").mkdir(parents=True)
    payload = {
        "strategy_name": "测试策略",
        "date_start": "2026-01-01",
        "date_end": "2026-03-31",
        "symbol_count": 100,
        "traded_symbol_count": 42,
        "total_trade_count": 88,
        "win_rate": 0.4545,
        "strategy_total_return": 0.0321,
        "buy_hold_return": 0.0512,
        "excess_return_vs_buy_hold": -0.0191,
        "max_drawdown": -0.12,
        "profit_factor": 1.35,
    }
    (out / "backtest" / "strategy_performance.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    summary = extract_run_summary(_record(tmp_path, output_dir=str(out)))
    assert summary is not None
    assert summary["source"] == "json"
    m = summary["metrics"]
    assert m["strategy_name"] == "测试策略"
    assert m["win_rate"] == pytest.approx(0.4545)
    assert m["traded_symbol_count"] == 42
    assert m["profit_factor"] == pytest.approx(1.35)
    assert m["max_drawdown"] == pytest.approx(-0.12)


def test_extract_summary_fallback_stdout(monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    run_dir = runs_dir / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / "stdout.log").write_text(
        "strategy=demo\nsymbols=2\ntotal_return=0.05\nwin_rate=0.5\nnot_a_metric line\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", runs_dir)

    summary = extract_run_summary(_record(tmp_path))
    assert summary is not None
    assert summary["source"] == "stdout"
    assert summary["metrics"]["strategy_total_return"] == pytest.approx(0.05)
    assert summary["metrics"]["strategy"] == "demo"


def test_extract_summary_none_when_nothing(monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    (runs_dir / "r1").mkdir(parents=True)
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", runs_dir)
    assert extract_run_summary(_record(tmp_path)) is None


# --- compare_run_summaries ---


def test_compare_run_summaries_diff(monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    for rid, ret in (("ra", 0.01), ("rb", 0.05)):
        run_dir = runs_dir / rid
        run_dir.mkdir(parents=True)
        (run_dir / "stdout.log").write_text(f"total_return={ret}\nwin_rate=0.4\n", encoding="utf-8")
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", runs_dir)

    rows = compare_run_summaries(_record(tmp_path, "ra"), _record(tmp_path, "rb"))
    by_key = {r["key"]: r for r in rows}
    assert by_key["strategy_total_return"]["diff"] == pytest.approx(0.04)
    assert by_key["win_rate"]["diff"] == pytest.approx(0.0)
    assert by_key["strategy_total_return"]["label"] == "总收益率"


# --- equity_curve_svg ---


def test_equity_curve_svg(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "equity_curve.csv").write_text(
        "trade_date,total_equity\n2026-01-01,100000\n2026-01-02,101000\n2026-01-03,99500\n",
        encoding="utf-8",
    )
    svg = equity_curve_svg(_record(tmp_path, output_dir=str(out)))
    assert svg is not None
    assert "<svg" in svg and "polyline" in svg
    assert "101000.00" in svg  # hi label


def test_equity_curve_svg_missing(tmp_path):
    assert equity_curve_svg(_record(tmp_path, output_dir=str(tmp_path))) is None


# --- Flask routes: 409 限流 / 预检记录 / compare 页 ---


@pytest.fixture
def app_client(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "quant_research_engine.gui.app.TEMPLATE_DIR",
        Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "templates",
    )
    monkeypatch.setattr(
        "quant_research_engine.gui.app.STATIC_DIR",
        Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "static",
    )
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path / "templates")
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("quant_research_engine.gui.engine.GUI_BASE_DIR", tmp_path)

    from quant_research_engine.gui.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


_VALID_YAML = (
    "experiment:\n  name: default\n  engine:\n    kind: single\n"
    "data:\n  factor_fields:\n    f: factors.t.c\n"
    "signal:\n  entry: x < 0\nevaluation:\n  forward_return_horizons: [1]\n"
    "holding:\n  max_holding_days: 1\n"
)


def _run_payload(**overrides):
    payload = {
        "yaml": _VALID_YAML,
        "mode": "batch",
        "start": "2026-01-05",
        "end": "2026-03-31",
        "codes": "000001.SZ,000002.SZ",
    }
    payload.update(overrides)
    return payload


def test_api_run_requires_codes_without_all_market(app_client):
    resp = app_client.post("/api/run", json=_run_payload(codes=""))
    assert resp.status_code == 400
    assert "全部 A 股" in resp.get_json()["error"]


def test_api_run_all_market_rejected_for_single(app_client):
    resp = app_client.post("/api/run", json=_run_payload(mode="single", codes="", all_market=True))
    assert resp.status_code == 400
    assert "单标的" in resp.get_json()["error"]


def test_api_run_concurrency_limit_returns_409(app_client, monkeypatch):
    monkeypatch.setattr(
        "quant_research_engine.gui.engine._run_via_module",
        lambda **kw: time.sleep(0.2),
    )
    assert try_acquire_run_slot()
    assert try_acquire_run_slot()
    try:
        resp = app_client.post("/api/run", json=_run_payload())
        assert resp.status_code == 409
        assert "已有 2 个回测在运行" in resp.get_json()["error"]
    finally:
        release_run_slot()
        release_run_slot()


def test_api_run_precheck_records_full_params(app_client, monkeypatch):
    monkeypatch.setattr(
        "quant_research_engine.gui.engine._run_via_module",
        lambda **kw: kw["stdout_path"].write_text("ok=1\n", encoding="utf-8"),
    )
    codes = ",".join(f"{i:06d}.SZ" for i in range(25))
    resp = app_client.post(
        "/api/run",
        json=_run_payload(codes=codes, start="2010-01-04", precheck=True,
                          commission_rate="0.0002", stop_loss_pct="0.08"),
    )
    assert resp.status_code == 200
    record = resp.get_json()
    assert record["precheck"] is True
    assert len(record["codes"]) == PRECHECK_MAX_CODES
    assert record["start"] == "2025-10-02"  # truncated to ~6 months
    full = record["full_params"]
    assert full["codes"] == codes
    assert full["start"] == "2010-01-04"
    assert full["stop_loss_pct"] == 0.08
    assert full["profile_overrides"] == {"commission_rate": 0.0002}

    # wait for the background thread; run record on disk carries precheck flags
    from quant_research_engine.gui.engine import get_run

    for _ in range(100):
        disk = get_run(record["run_id"])
        if disk and disk["status"] != "running":
            break
        time.sleep(0.05)
    assert disk["status"] == "completed"
    assert disk["precheck"] is True


def test_api_run_passes_overrides_to_module(app_client, monkeypatch):
    captured = {}

    def fake_run(**kw):
        captured.update(kw)
        kw["stdout_path"].write_text("ok=1\n", encoding="utf-8")

    monkeypatch.setattr("quant_research_engine.gui.engine._run_via_module", fake_run)
    resp = app_client.post(
        "/api/run",
        json=_run_payload(
            engine_impl="vectorized",
            commission_rate="0.0002",
            slippage_buy_rate="0.001",
            take_profit_pct="0.15",
        ),
    )
    assert resp.status_code == 200
    run_id = resp.get_json()["run_id"]
    from quant_research_engine.gui.engine import get_run

    for _ in range(100):
        disk = get_run(run_id)
        if disk and disk["status"] != "running":
            break
        time.sleep(0.05)
    assert captured["engine_impl"] == "vectorized"
    assert captured["profile_overrides"] == {"commission_rate": 0.0002, "slippage_buy_rate": 0.001}
    assert captured["take_profit_pct"] == 0.15


def test_compare_page(app_client, monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    for rid, ret in (("cmp-a", 0.01), ("cmp-b", 0.03)):
        run_dir = runs_dir / rid
        run_dir.mkdir(parents=True)
        (run_dir / "status.json").write_text(
            json.dumps({"run_id": rid, "mode": "batch", "start": "2026-01-05",
                        "end": "2026-03-31", "status": "completed"}),
            encoding="utf-8",
        )
        (run_dir / "stdout.log").write_text(f"total_return={ret}\n", encoding="utf-8")
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", runs_dir)

    resp = app_client.get("/compare?a=cmp-a&b=cmp-b")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "总收益率" in html
    assert "2.00%" in html  # diff 0.02 as percent


def test_compare_page_missing_run(app_client):
    resp = app_client.get("/compare?a=nope&b=alsonope")
    assert resp.status_code == 404


def test_run_detail_shows_precheck_banner(app_client, monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    run_dir = runs_dir / "pre-1"
    run_dir.mkdir(parents=True)
    (run_dir / "status.json").write_text(
        json.dumps({
            "run_id": "pre-1", "mode": "batch", "start": "2025-10-02", "end": "2026-03-31",
            "status": "completed", "precheck": True,
            "full_params": {"codes": "000001.SZ", "start": "2010-01-04", "end": "2026-03-31"},
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", runs_dir)

    resp = app_client.get("/runs/pre-1")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "小样本预检" in html
    assert "放大到完整范围" in html
