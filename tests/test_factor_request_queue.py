"""Tests for strategies.factor_request_queue and runner shelve semantics."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from quant_research_engine.orchestration.batch_runner import (
    BatchRunConfig,
    run_single_strategy,
    summarize_results,
)
from quant_research_engine.strategies.factor_request_queue import (
    build_requests_for_strategy,
    find_missing_factor_columns,
    load_queue,
    make_schema_column_lookup,
    recheck_fulfillment,
    save_queue,
    upsert_requests,
)
from quant_research_engine.data.catalog import FactorFieldRequest


def _req(strategy_id, alias, table="factors.stock_daily_overlap_close", column="sma_50"):
    return {
        "strategy_id": strategy_id,
        "alias": alias,
        "indicator": "sma",
        "category": "overlap",
        "source": "close",
        "period": 50,
        "params": {},
        "output": None,
        "expected_table": table,
        "expected_column": column,
        "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
        "reason": f"factor required by strategy '{strategy_id}'",
        "required": True,
    }


# ---------------------------------------------------------------------------
# queue store
# ---------------------------------------------------------------------------


def test_upsert_dedup_and_timestamps(tmp_path):
    entries = []
    added = upsert_requests(entries, [_req("a", "sma_50")], seen_at="t1")
    assert added == 1
    added = upsert_requests(entries, [_req("a", "sma_50"), _req("a", "sma_7", column="sma_7")], seen_at="t2")
    assert added == 1  # only sma_7 is new
    first = next(e for e in entries if e["alias"] == "sma_50")
    assert first["first_seen"] == "t1"
    assert first["last_seen"] == "t2"
    assert first["status"] == "pending"
    assert first["fulfilled_at"] is None


def test_save_and_load_queue_sorted(tmp_path):
    path = tmp_path / "q.json"
    entries = [_req("b", "sma_50"), _req("a", "sma_7", column="sma_7")]
    save_queue(path, entries)
    loaded = load_queue(path)
    assert [e["strategy_id"] for e in loaded] == ["a", "b"]
    assert load_queue(tmp_path / "missing.json") == []


def test_recheck_fulfillment():
    entries = []
    upsert_requests(entries, [_req("a", "sma_50"), _req("b", "sma_7", column="sma_7")], seen_at="t1")
    lookup = lambda table: {"sma_50", "sma_20"}
    stats = recheck_fulfillment(entries, lookup, checked_at="t2")
    assert stats == {"checked": 2, "newly_fulfilled": 1, "pending": 1, "fulfilled": 1}
    sma50 = next(e for e in entries if e["alias"] == "sma_50")
    assert sma50["status"] == "fulfilled" and sma50["fulfilled_at"] == "t2"
    # idempotent: second recheck changes nothing
    stats = recheck_fulfillment(entries, lookup, checked_at="t3")
    assert stats["newly_fulfilled"] == 0


def test_make_schema_column_lookup_caches():
    calls = []

    class FakeStore:
        def table_exists(self, table, engine=None):
            calls.append(("exists", table))
            return table == "factors.t1"

        def get_table_columns(self, table, *, engine=None):
            calls.append(("cols", table))
            return ["c1"]

    lookup = make_schema_column_lookup(FakeStore())
    assert lookup("factors.t1") == {"c1"}
    assert lookup("factors.t1") == {"c1"}  # cached
    assert lookup("factors.t2") == set()
    assert calls.count(("cols", "factors.t1")) == 1


# ---------------------------------------------------------------------------
# spec-driven missing detection + request building
# ---------------------------------------------------------------------------


def test_find_missing_and_build_requests():
    spec = SimpleNamespace(
        factor_fields=[
            FactorFieldRequest.from_target("rsi_2", "factors.stock_daily_momentum_close.rsi_2"),
            FactorFieldRequest.from_target("sma_50", "factors.stock_daily_overlap_close.sma_50"),
        ]
    )
    lookup = lambda table: {"rsi_2"} if "momentum" in table else set()
    missing = find_missing_factor_columns(spec, lookup)
    assert [f.logical_name for f in missing] == ["sma_50"]
    requests = build_requests_for_strategy(spec, missing, strategy_id="s1", start=date(2024, 1, 1), end=date(2024, 12, 31))
    assert requests[0]["strategy_id"] == "s1"
    assert requests[0]["alias"] == "sma_50"
    assert requests[0]["indicator"] == "sma"
    assert requests[0]["period"] == 50
    assert requests[0]["expected_table"] == "factors.stock_daily_overlap_close"
    assert requests[0]["date_range"] == {"start": "2024-01-01", "end": "2024-12-31"}


# ---------------------------------------------------------------------------
# runner shelve semantics
# ---------------------------------------------------------------------------


def _make_catalog_yaml(tmp_path: Path, name: str, factor_targets: list[str]) -> Path:
    catalog = tmp_path / "catalog" / "cat"
    catalog.mkdir(parents=True)
    fields = "\n".join(f"    f{i}: {t}" for i, t in enumerate(factor_targets))
    yaml_path = catalog / f"{name}.yaml"
    yaml_path.write_text(
        f"experiment:\n  name: {name}\n"
        f"data:\n  factor_fields:\n{fields if fields else '    {}'}\n"
        "signal:\n  entry: close > 0\n"
        "evaluation: {}\n"
        "holding:\n  max_holding_days: 5\n",
        encoding="utf-8",
    )
    return yaml_path


def test_runner_shelves_missing_factor_strategy(tmp_path, monkeypatch):
    yaml_path = _make_catalog_yaml(tmp_path, "blocked_s", ["factors.stock_daily_overlap_close.sma_50"])
    monkeypatch.setattr(
        "quant_research_engine.orchestration.batch_runner._worker_schema_lookup",
        lambda: (lambda table: set()),
    )
    called = []
    monkeypatch.setattr(
        "quant_research_engine.orchestration.research_run.run_research_run",
        lambda request: called.append(1),
    )
    config = BatchRunConfig(
        output_base=tmp_path / "batch",
        start=date(2024, 1, 1),
        end=date(2024, 3, 1),
        catalog_dir=tmp_path / "catalog",
    )
    result = run_single_strategy(yaml_path, config)
    assert result.status == "missing_factors"
    assert "sma_50" in result.error_message
    assert result.missing_requests[0]["expected_column"] == "sma_50"
    assert called == []  # strategy never executed


def test_runner_executes_when_factors_present(tmp_path, monkeypatch):
    yaml_path = _make_catalog_yaml(tmp_path, "ok_s", ["factors.stock_daily_momentum_close.rsi_2"])
    monkeypatch.setattr(
        "quant_research_engine.orchestration.batch_runner._worker_schema_lookup",
        lambda: (lambda table: {"rsi_2"}),
    )
    monkeypatch.setattr(
        "quant_research_engine.orchestration.research_run.run_research_run",
        lambda request: SimpleNamespace(
            run_id="r", preflight_status="skipped", eval_status="skipped",
            backtest_status="ok", error_message=None, stage_durations_s={},
        ),
    )
    config = BatchRunConfig(
        output_base=tmp_path / "batch",
        start=date(2024, 1, 1),
        end=date(2024, 3, 1),
        catalog_dir=tmp_path / "catalog",
    )
    result = run_single_strategy(yaml_path, config)
    assert result.status == "ok"


def test_summarize_results_counts_missing_factors():
    from quant_research_engine.orchestration.batch_runner import BatchRunResult

    results = [
        BatchRunResult("a", "c", "r", "ok"),
        BatchRunResult("b", "c", "r", "missing_factors"),
        BatchRunResult("c", "c", "r", "error"),
    ]
    counts = summarize_results(results)
    assert counts["missing_factors"] == 1
    assert counts["ok"] == 1 and counts["error"] == 1
