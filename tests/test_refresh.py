"""Tests for orchestration.refresh (M10.3) and the refresh_batch script."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from quant_research_engine.orchestration.batch_runner import BatchRunResult
from quant_research_engine.orchestration.refresh import (
    DELTA_MANIFEST_KIND,
    RefreshState,
    compute_delta,
    compute_window,
    load_state,
    needs_refresh,
    save_state,
    write_delta_report,
)
from quant_research_engine.portfolio.report_manifest import ReportManifest


# ---------------------------------------------------------------------------
# state + watermark logic
# ---------------------------------------------------------------------------


def test_state_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    assert load_state(path) is None
    state = RefreshState(
        last_data_date="2026-05-20",
        last_run_at="2026-05-20T18:30:00+00:00",
        last_batch_dir="/x/batch1",
        window_years=3,
        codes=["000001.SZ"],
        strategy_count=106,
        ok_count=104,
        config={"jobs": 4},
    )
    save_state(path, state)
    loaded = load_state(path)
    assert loaded == state


def test_needs_refresh_logic():
    assert needs_refresh(date(2026, 5, 20), None) is True
    assert needs_refresh(date(2026, 5, 20), RefreshState()) is True
    state = RefreshState(last_data_date="2026-05-19")
    assert needs_refresh(date(2026, 5, 20), state) is True
    assert needs_refresh(date(2026, 5, 19), state) is False
    assert needs_refresh(date(2026, 5, 18), state) is False


def test_compute_window():
    start, end = compute_window(date(2026, 5, 20), 2)
    assert (start, end) == (date(2024, 5, 20), date(2026, 5, 20))
    start, _ = compute_window(date(2024, 2, 29), 1)
    assert start == date(2023, 2, 28)
    with pytest.raises(ValueError):
        compute_window(date(2026, 1, 1), 0)


# ---------------------------------------------------------------------------
# delta computation
# ---------------------------------------------------------------------------


def _make_batch(base: Path, rows: list[dict]) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    results = []
    for row in rows:
        sid = row["strategy_id"]
        out = base / sid / "backtest"
        out.mkdir(parents=True)
        (out / "summary_metrics.json").write_text(
            json.dumps(
                {
                    "mean_total_return": row.get("mean_total_return"),
                    "total_trades": row.get("total_trades"),
                    "positive_return_symbol_rate": row.get("positive_return_symbol_rate"),
                }
            ),
            encoding="utf-8",
        )
        results.append(
            {
                "strategy_id": sid,
                "category": row.get("category", "test"),
                "status": row.get("status", "ok"),
                "output_dir": str(base / sid),
            }
        )
    (base / "batch_summary.json").write_text(json.dumps({"results": results}), encoding="utf-8")
    return base


def test_compute_delta_transitions(tmp_path):
    prev = _make_batch(tmp_path / "prev", [
        {"strategy_id": "a", "mean_total_return": 0.01, "total_trades": 10, "positive_return_symbol_rate": 0.5},
        {"strategy_id": "b", "mean_total_return": -0.02, "total_trades": 5, "positive_return_symbol_rate": 0.2},
        {"strategy_id": "gone", "mean_total_return": 0.0, "total_trades": 1, "positive_return_symbol_rate": 0.0},
    ])
    curr = _make_batch(tmp_path / "curr", [
        {"strategy_id": "a", "mean_total_return": 0.03, "total_trades": 12, "positive_return_symbol_rate": 0.6},
        {"strategy_id": "b", "status": "error", "mean_total_return": -0.02, "total_trades": 5, "positive_return_symbol_rate": 0.2},
        {"strategy_id": "new_s", "mean_total_return": 0.05, "total_trades": 8, "positive_return_symbol_rate": 0.7},
    ])
    rows = compute_delta(prev, curr)
    by_id = {r["strategy_id"]: r for r in rows}
    assert by_id["a"]["transition"] == "unchanged"
    assert by_id["a"]["delta_mean_total_return"] == pytest.approx(0.02)
    assert by_id["a"]["delta_total_trades"] == 2
    assert by_id["b"]["transition"] == "ok->error"
    assert by_id["gone"]["transition"] == "removed"
    assert by_id["new_s"]["transition"] == "new"


def test_compute_delta_first_run(tmp_path):
    curr = _make_batch(tmp_path / "curr", [{"strategy_id": "a", "mean_total_return": 0.01}])
    rows = compute_delta(None, curr)
    assert rows[0]["transition"] == "new"


def test_write_delta_report_and_manifest(tmp_path):
    new_batch = _make_batch(tmp_path / "new", [{"strategy_id": "a", "mean_total_return": 0.01, "total_trades": 3, "positive_return_symbol_rate": 0.4}])
    rows = compute_delta(None, new_batch)
    out = tmp_path / "delta"
    paths = write_delta_report(
        out,
        data_date=date(2026, 5, 20),
        window=(date(2024, 5, 20), date(2026, 5, 20)),
        previous_batch_dir=None,
        new_batch_dir=new_batch,
        delta_rows=rows,
        generated_at="2026-07-19T00:00:00+00:00",
    )
    for path in paths.values():
        assert path.exists()
    manifest = json.loads(paths["report_manifest"].read_text(encoding="utf-8"))
    assert manifest["kind"] == DELTA_MANIFEST_KIND
    rm = ReportManifest.from_path(paths["report_manifest"])
    assert rm.validate_contents() == []
    md = paths["delta_report_md"].read_text(encoding="utf-8")
    assert "R-QRE-008" in md


# ---------------------------------------------------------------------------
# script end-to-end (mocked store + batch execution)
# ---------------------------------------------------------------------------


def _load_script(tmp_path: Path):
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "refresh_batch.py"
    spec = importlib.util.spec_from_file_location("refresh_batch_script", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeStore:
    def ping(self):
        return True

    def close(self):
        pass


def _patch_script_env(script, tmp_path, monkeypatch, watermark):
    catalog = tmp_path / "catalog" / "cat"
    catalog.mkdir(parents=True)
    for sid in ("s1", "s2"):
        (catalog / f"{sid}.yaml").write_text(f"name: {sid}\n")
    monkeypatch.setattr(script, "CATALOG_DIR", tmp_path / "catalog")
    # the script imports the data layer inside main(); patch the source modules
    import quant_research_engine.data.postgres as pg_mod
    import quant_research_engine.data.settings as settings_mod

    monkeypatch.setattr(pg_mod, "PostgresDataStore", lambda settings: _FakeStore())
    monkeypatch.setattr(settings_mod.DatabaseSettings, "from_env", staticmethod(lambda: None))
    monkeypatch.setattr(script, "data_watermark", lambda store: watermark)

    def fake_execute(yaml_paths, config, *, jobs=1, on_progress=None):
        results = []
        for path in yaml_paths:
            sid = path.stem
            out = config.output_base / sid / "backtest"
            out.mkdir(parents=True, exist_ok=True)
            (out / "summary_metrics.json").write_text(
                json.dumps({"mean_total_return": 0.01, "total_trades": 3, "positive_return_symbol_rate": 0.5}),
                encoding="utf-8",
            )
            results.append(
                BatchRunResult(
                    strategy_id=sid,
                    category="cat",
                    research_run_id="r",
                    status="ok",
                    output_dir=str(config.output_base / sid),
                )
            )
        return results

    monkeypatch.setattr(script, "execute_batch", fake_execute)
    return catalog


def _argv(tmp_path, *extra):
    return [
        "--state-file", str(tmp_path / "state.json"),
        "--output-root", str(tmp_path / "batches"),
        "--mode", "full",  # 这些用例验证全窗路径（execute_batch 已 mock）
        *extra,
    ]


def test_script_first_run_then_noop_then_refresh(tmp_path, monkeypatch, capsys):
    script = _load_script(tmp_path)
    _patch_script_env(script, tmp_path, monkeypatch, date(2026, 5, 20))
    monkeypatch.setattr(script, "DEFAULT_DELTA_ROOT", tmp_path / "delta")

    # first run: no state → refresh executes
    monkeypatch.setattr(sys, "argv", ["refresh_batch.py", *_argv(tmp_path)])
    assert script.main() == 0
    state = load_state(tmp_path / "state.json")
    assert state is not None and state.last_data_date == "2026-05-20"
    assert state.strategy_count == 2 and state.ok_count == 2
    delta_dirs = list((tmp_path / "delta").glob("*"))
    assert len(delta_dirs) == 1
    payload = json.loads((delta_dirs[0] / "delta_report.json").read_text(encoding="utf-8"))
    assert payload["previous_batch_dir"] is None
    assert payload["changed"] == 2  # both strategies are "new"

    # second run, same watermark: no-op
    assert script.main() == 0
    assert len(list((tmp_path / "delta").glob("*"))) == 1

    # watermark bump: refresh again with delta vs previous
    monkeypatch.setattr(script, "data_watermark", lambda store: date(2026, 5, 21))
    assert script.main() == 0
    assert len(list((tmp_path / "delta").glob("*"))) == 2
    state = load_state(tmp_path / "state.json")
    assert state.last_data_date == "2026-05-21"


def test_script_check_only_runs_nothing(tmp_path, monkeypatch):
    script = _load_script(tmp_path)
    _patch_script_env(script, tmp_path, monkeypatch, date(2026, 5, 20))
    monkeypatch.setattr(sys, "argv", ["refresh_batch.py", *_argv(tmp_path, "--check-only")])
    assert script.main() == 0
    assert not (tmp_path / "state.json").exists()
    assert not (tmp_path / "batches").exists()


def test_script_force_overrides_watermark(tmp_path, monkeypatch):
    script = _load_script(tmp_path)
    _patch_script_env(script, tmp_path, monkeypatch, date(2026, 5, 20))
    monkeypatch.setattr(script, "DEFAULT_DELTA_ROOT", tmp_path / "delta")
    monkeypatch.setattr(sys, "argv", ["refresh_batch.py", *_argv(tmp_path, "--force")])
    assert script.main() == 0
    monkeypatch.setattr(sys, "argv", ["refresh_batch.py", *_argv(tmp_path, "--force")])
    assert script.main() == 0
    assert len(list((tmp_path / "delta").glob("*"))) == 2


# ---------------------------------------------------------------------------
# 晋升全量回测闸过滤（QRE-GUI-PROMO-GATE-001）


def test_apply_gate_filter(tmp_path):
    script = _load_script(tmp_path)
    paths = [tmp_path / f"{sid}.yaml" for sid in ("a", "b", "c", "d")]
    gates = {
        "b": {"gate": "failed", "forced": False},
        "c": {"gate": "failed", "forced": True},   # 强制在库：不跳过
        "d": {"gate": "passed", "forced": False},
    }
    kept, skipped = script._apply_gate_filter(paths, gates)
    assert [p.stem for p in kept] == ["a", "c", "d"]
    assert skipped == ["b"]


def test_script_skips_gate_failed_strategies(tmp_path, monkeypatch, capsys):
    from quant_research_engine.gui.refresh_registry import save_gate

    script = _load_script(tmp_path)
    _patch_script_env(script, tmp_path, monkeypatch, date(2026, 5, 20))
    monkeypatch.setattr(script, "DEFAULT_DELTA_ROOT", tmp_path / "delta")
    gates_dir = tmp_path / "gates"
    monkeypatch.setattr(script, "DEFAULT_GATES_DIR", gates_dir)
    save_gate("s2", {"strategy": "s2", "gate": "failed", "forced": False}, gates_dir)

    monkeypatch.setattr(sys, "argv", ["refresh_batch.py", *_argv(tmp_path)])
    assert script.main() == 0
    out = capsys.readouterr().out
    assert "promotion-gate: skipped 1 failed strategies: s2" in out
    state = load_state(tmp_path / "state.json")
    assert state.strategy_count == 1  # 只剩 s1
    # 跳过名单记入批次 config
    batches = list((tmp_path / "batches").glob("*"))
    assert len(batches) == 1
    summary = json.loads((batches[0] / "batch_summary.json").read_text(encoding="utf-8"))
    assert summary["config"]["gate_skipped"] == ["s2"]
