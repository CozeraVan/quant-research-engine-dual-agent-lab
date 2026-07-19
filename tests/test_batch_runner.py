"""Unit tests for orchestration.batch_runner and compact batch outputs.

The parallel-execution tests rely on Linux ``fork`` start method so that
monkeypatched module attributes are visible inside worker processes.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from quant_research_engine.orchestration import batch_runner
from quant_research_engine.orchestration.batch_runner import (
    BatchRunConfig,
    BatchRunResult,
    BatchSummary,
    completed_strategies,
    discover_strategies,
    execute_batch,
    result_to_payload,
    run_single_strategy,
    strategy_meta,
    summarize_results,
    write_batch_summary,
)
from quant_research_engine.orchestration.research_run import (
    ResearchRunRequest,
    run_research_run,
)
from quant_research_engine.portfolio.batch import BatchBacktestResult
from quant_research_engine.portfolio.io import write_batch_result
from quant_research_engine.portfolio.single_symbol import SingleSymbolBacktestResult


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_catalog(tmp_path: Path) -> Path:
    catalog = tmp_path / "catalog"
    (catalog / "trend_following").mkdir(parents=True)
    (catalog / "mean_reversion").mkdir(parents=True)
    (catalog / "trend_following" / "tf01.yaml").write_text("name: tf01\n")
    (catalog / "trend_following" / "tf02.yaml").write_text("name: tf02\n")
    (catalog / "mean_reversion" / "mr01.yaml").write_text("name: mr01\n")
    (catalog / "root_strategy.yaml").write_text("name: root\n")
    return catalog


def _make_config(tmp_path: Path, **overrides) -> BatchRunConfig:
    defaults = {
        "output_base": tmp_path / "batch",
        "start": date(2024, 1, 1),
        "end": date(2024, 3, 1),
    }
    defaults.update(overrides)
    return BatchRunConfig(**defaults)


def _fake_run_result(**overrides):
    defaults = {
        "run_id": "run123",
        "preflight_status": "skipped",
        "eval_status": "ok",
        "backtest_status": "ok",
        "error_message": None,
        "stage_durations_s": {"eval": 1.5, "backtest": 2.5},
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _write_manifest(run_dir: Path, backtest: str, strategy: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "kind": "research_run_manifest",
        "strategy_path": f"strategies/catalog/trend_following/{strategy}.yaml",
        "stages": {"preflight": "skipped", "eval": "ok", "backtest": backtest},
    }
    (run_dir / "research_run_manifest.json").write_text(json.dumps(payload), encoding="utf-8")


def _make_batch_result() -> BatchBacktestResult:
    equity = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-30", periods=21, freq="B"),
            "total_equity": [10000.0 + i * 100 for i in range(21)],
        }
    )
    singles = {}
    for symbol in ("000001.SZ", "000002.SZ"):
        singles[symbol] = SingleSymbolBacktestResult(
            orders=pd.DataFrame({"symbol": [symbol], "side": ["buy"]}),
            trades=pd.DataFrame({"symbol": [symbol], "net_pnl": [90.0]}),
            equity_curve=equity,
            failed_orders=pd.DataFrame(),
            summary={"initial_cash": 10000.0, "final_equity": 10000.0, "trade_count": 1},
        )
    return BatchBacktestResult(
        symbols=["000001.SZ", "000002.SZ"],
        results=singles,
        summary=pd.DataFrame(
            {
                "symbol": ["000001.SZ", "000002.SZ"],
                "trade_count": [1, 1],
                "total_return": [0.05, -0.02],
            }
        ),
        summary_metrics={"symbol_count": 2, "mean_total_return": 0.015},
    )


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------


def test_discover_strategies_all(tmp_path):
    catalog = _make_catalog(tmp_path)
    paths = discover_strategies(catalog)
    assert [p.stem for p in paths] == ["mr01", "root_strategy", "tf01", "tf02"] or len(paths) == 4


def test_discover_strategies_by_category(tmp_path):
    catalog = _make_catalog(tmp_path)
    paths = discover_strategies(catalog, category="trend_following")
    assert sorted(p.stem for p in paths) == ["tf01", "tf02"]


def test_discover_strategies_by_ids(tmp_path):
    catalog = _make_catalog(tmp_path)
    paths = discover_strategies(catalog, strategy_ids=["tf01", "mr01", "missing"])
    assert sorted(p.stem for p in paths) == ["mr01", "tf01"]


def test_discover_strategies_bad_category_raises(tmp_path):
    catalog = _make_catalog(tmp_path)
    with pytest.raises(ValueError, match="Category not found"):
        discover_strategies(catalog, category="no_such_category")


def test_strategy_meta_nested_and_root(tmp_path):
    catalog = _make_catalog(tmp_path)
    assert strategy_meta(catalog / "trend_following" / "tf01.yaml", catalog) == ("tf01", "trend_following")
    assert strategy_meta(catalog / "root_strategy.yaml", catalog) == ("root_strategy", "root")
    assert strategy_meta(Path("/elsewhere/x.yaml"), catalog) == ("x", "root")


# ---------------------------------------------------------------------------
# resume / completed strategies
# ---------------------------------------------------------------------------


def test_completed_strategies_batch_dir_level(tmp_path):
    batch = tmp_path / "outputs" / "batchAAA"
    _write_manifest(batch / "tf01", "ok", "tf01")
    _write_manifest(batch / "mr01", "error", "mr01")
    assert completed_strategies(tmp_path / "outputs") == {"tf01"}
    assert completed_strategies(batch) == {"tf01"}


def test_completed_strategies_malformed_and_missing(tmp_path):
    bad = tmp_path / "out" / "batchB" / "tf02"
    bad.mkdir(parents=True)
    (bad / "research_run_manifest.json").write_text("{not json", encoding="utf-8")
    assert completed_strategies(tmp_path / "out") == set()
    assert completed_strategies(tmp_path / "does_not_exist") == set()


# ---------------------------------------------------------------------------
# single strategy execution
# ---------------------------------------------------------------------------


def test_run_single_strategy_ok_and_compact_threading(tmp_path, monkeypatch):
    catalog = _make_catalog(tmp_path)
    captured = {}

    def fake_run(request):
        captured["request"] = request
        return _fake_run_result()

    monkeypatch.setattr(
        "quant_research_engine.orchestration.research_run.run_research_run", fake_run
    )
    config = _make_config(tmp_path, compact=True, catalog_dir=catalog)
    result = run_single_strategy(catalog / "trend_following" / "tf01.yaml", config)

    assert result.status == "ok"
    assert result.category == "trend_following"
    assert result.stage_durations_s == {"eval": 1.5, "backtest": 2.5}
    request = captured["request"]
    assert isinstance(request, ResearchRunRequest)
    assert request.compact is True
    assert request.output_dir == config.output_base / "tf01"


@pytest.mark.parametrize(
    "preflight,eval_s,backtest_s,expected",
    [
        ("error", "skipped", "error", "preflight_failed"),
        ("ok", "error", "error", "eval_failed"),
        ("ok", "ok", "error", "backtest_failed"),
    ],
)
def test_run_single_strategy_status_mapping(tmp_path, monkeypatch, preflight, eval_s, backtest_s, expected):
    catalog = _make_catalog(tmp_path)
    monkeypatch.setattr(
        "quant_research_engine.orchestration.research_run.run_research_run",
        lambda request: _fake_run_result(
            preflight_status=preflight, eval_status=eval_s, backtest_status=backtest_s,
            error_message="boom",
        ),
    )
    config = _make_config(tmp_path, catalog_dir=catalog)
    result = run_single_strategy(catalog / "trend_following" / "tf01.yaml", config)
    assert result.status == expected
    assert result.error_message == "boom"


def test_run_single_strategy_exception_becomes_error(tmp_path, monkeypatch):
    catalog = _make_catalog(tmp_path)

    def exploding(request):
        raise RuntimeError("db down")

    monkeypatch.setattr(
        "quant_research_engine.orchestration.research_run.run_research_run", exploding
    )
    config = _make_config(tmp_path, catalog_dir=catalog)
    result = run_single_strategy(catalog / "trend_following" / "tf01.yaml", config)
    assert result.status == "error"
    assert "db down" in result.error_message


# ---------------------------------------------------------------------------
# batch execution (serial and parallel)
# ---------------------------------------------------------------------------


def _patch_research_run(monkeypatch):
    monkeypatch.setattr(
        "quant_research_engine.orchestration.research_run.run_research_run",
        lambda request: _fake_run_result(),
    )


def test_execute_batch_serial_order_and_progress(tmp_path, monkeypatch):
    catalog = _make_catalog(tmp_path)
    _patch_research_run(monkeypatch)
    paths = sorted(catalog.rglob("*.yaml"))
    progress = []
    config = _make_config(tmp_path, catalog_dir=catalog)
    results = execute_batch(paths, config, jobs=1, on_progress=lambda i, n, r: progress.append((i, n, r.strategy_id)))
    assert len(results) == len(paths) == 4
    assert all(r.status == "ok" for r in results)
    assert [p[0] for p in progress] == [1, 2, 3, 4]
    assert {p[2] for p in progress} == {"tf01", "tf02", "mr01", "root_strategy"}


def test_execute_batch_parallel_completes_all(tmp_path, monkeypatch):
    catalog = _make_catalog(tmp_path)
    _patch_research_run(monkeypatch)
    paths = sorted(catalog.rglob("*.yaml"))
    config = _make_config(tmp_path, catalog_dir=catalog)
    results = execute_batch(paths, config, jobs=2, on_progress=None)
    assert len(results) == 4
    assert {r.strategy_id for r in results} == {"tf01", "tf02", "mr01", "root_strategy"}
    assert all(r.status == "ok" for r in results)


# ---------------------------------------------------------------------------
# summary writing
# ---------------------------------------------------------------------------


def test_summarize_results_counts():
    results = [
        BatchRunResult("a", "cat", "r", "ok"),
        BatchRunResult("b", "cat", "r", "ok"),
        BatchRunResult("c", "cat", "r", "preflight_failed"),
        BatchRunResult("d", "cat", "r", "eval_failed"),
        BatchRunResult("e", "cat", "r", "backtest_failed"),
        BatchRunResult("f", "cat", "r", "error"),
        BatchRunResult("g", "cat", "r", "skipped"),
    ]
    counts = summarize_results(results)
    assert counts == {
        "total": 7, "ok": 2, "preflight_failed": 1, "eval_failed": 1,
        "backtest_failed": 1, "error": 1, "skipped": 1,
    }


def test_write_batch_summary_includes_stage_durations(tmp_path):
    summary = BatchSummary(
        batch_id="batch123",
        generated_at="2026-07-18T00:00:00+00:00",
        mode="quick",
        date_range={"start": "2024-01-01", "end": "2024-12-31"},
        config={"jobs": 4, "compact": True},
        results=[
            BatchRunResult(
                "tf01", "trend_following", "run1", "ok",
                duration_s=12.34, stage_durations_s={"eval": 5.0, "backtest": 7.3},
            )
        ],
        summary={"total": 1, "ok": 1},
    )
    path = write_batch_summary(summary, tmp_path / "batch123")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["batch_id"] == "batch123"
    assert payload["config"] == {"jobs": 4, "compact": True}
    entry = payload["results"][0]
    assert entry["stage_durations_s"] == {"eval": 5.0, "backtest": 7.3}
    assert entry["duration_s"] == 12.3


def test_result_to_payload_omits_empty_stage_durations():
    payload = result_to_payload(BatchRunResult("a", "cat", "r", "ok"))
    assert "stage_durations_s" not in payload


# ---------------------------------------------------------------------------
# compact output mode
# ---------------------------------------------------------------------------


def test_write_batch_result_compact_skips_symbol_trees_and_workbook(tmp_path):
    result = _make_batch_result()
    standard_dir = tmp_path / "standard"
    compact_dir = tmp_path / "compact"

    standard_paths = write_batch_result(result, standard_dir)
    compact_paths = write_batch_result(result, compact_dir, compact=True)

    # metric-bearing artifacts are identical
    assert (standard_dir / "summary.csv").read_bytes() == (compact_dir / "summary.csv").read_bytes()
    assert json.loads((standard_dir / "summary_metrics.json").read_text()) == json.loads(
        (compact_dir / "summary_metrics.json").read_text()
    )

    # compact mode skips per-symbol directories and the full-market workbook
    assert (standard_dir / "000001.SZ").is_dir()
    assert not (compact_dir / "000001.SZ").exists()
    assert not (compact_dir / "000002.SZ").exists()
    assert not list(compact_dir.glob("backtest_report*.xlsx"))
    assert not list(compact_dir.glob("*.html"))

    # compact paths are a subset of standard paths, with strategy-level files kept
    assert set(compact_paths) <= set(standard_paths)
    for key in ("summary", "summary_metrics", "summary_markdown", "report_manifest"):
        assert key in compact_paths

    # report manifest stays parseable and references only existing files
    manifest = json.loads((compact_dir / "report_manifest.json").read_text())
    assert manifest["kind"] == "batch_backtest_report_manifest"
    for entry in manifest["files"]:
        assert (compact_dir / entry["path"]).exists()


# ---------------------------------------------------------------------------
# research_run stage timing and store cleanup
# ---------------------------------------------------------------------------


def _write_minimal_strategy(tmp_path: Path) -> Path:
    strat_path = tmp_path / "strategy.yaml"
    strat_path.write_text("name: test\nsignal:\n  entry: close > 0\n", encoding="utf-8")
    return strat_path


def test_run_research_run_records_stage_durations_and_closes_store(tmp_path, monkeypatch):
    closed = []

    class ClosableFakeStore:
        def ping(self):
            return True

        def close(self):
            closed.append(True)

    monkeypatch.setattr(
        "quant_research_engine.orchestration.research_run._build_db_store",
        lambda db_url=None: ClosableFakeStore(),
    )
    spec = SimpleNamespace()
    monkeypatch.setattr(
        "quant_research_engine.orchestration.research_run.StrategySpec",
        type("FakeSpec", (), {"from_yaml": staticmethod(lambda path: spec)}),
    )
    monkeypatch.setattr(
        "quant_research_engine.orchestration.research_run._run_backtest",
        lambda *a, **kw: ("ok", {}),
    )

    result = run_research_run(
        ResearchRunRequest(
            strategy_path=_write_minimal_strategy(tmp_path),
            start=date(2024, 1, 1),
            end=date(2024, 2, 1),
            output_dir=tmp_path / "run_output",
            skip_preflight=True,
            skip_eval=True,
        )
    )

    assert result.backtest_status == "ok"
    assert "backtest" in result.stage_durations_s
    assert result.stage_durations_s["backtest"] >= 0.0
    assert closed == [True]

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["stage_durations_s"]["backtest"] == result.stage_durations_s["backtest"]


def test_run_research_run_tolerates_store_without_close(tmp_path, monkeypatch):
    class BareFakeStore:
        def ping(self):
            return True

    monkeypatch.setattr(
        "quant_research_engine.orchestration.research_run._build_db_store",
        lambda db_url=None: BareFakeStore(),
    )
    spec = SimpleNamespace()
    monkeypatch.setattr(
        "quant_research_engine.orchestration.research_run.StrategySpec",
        type("FakeSpec", (), {"from_yaml": staticmethod(lambda path: spec)}),
    )
    monkeypatch.setattr(
        "quant_research_engine.orchestration.research_run._run_backtest",
        lambda *a, **kw: ("ok", {}),
    )

    result = run_research_run(
        ResearchRunRequest(
            strategy_path=_write_minimal_strategy(tmp_path),
            start=date(2024, 1, 1),
            end=date(2024, 2, 1),
            output_dir=tmp_path / "run_output",
            skip_preflight=True,
            skip_eval=True,
        )
    )
    assert result.backtest_status == "ok"
