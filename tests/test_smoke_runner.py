from __future__ import annotations

import json
import tempfile
from pathlib import Path

import yaml

from quant_research_engine.strategies.smoke_runner import (
    SmokeSummary,
    StrategySmokeResult,
    _check_db_available,
    _try_backtest_smoke,
    _try_compile,
    _write_smoke_report_manifest,
    _write_smoke_summary,
    run_strategy_smoke,
)


# ---------------------------------------------------------------------------
# Standalone unit tests
# ---------------------------------------------------------------------------

def test_check_db_available_returns_bool():
    result = _check_db_available()
    assert isinstance(result, bool)


def test_strategy_smoke_result_defaults():
    r = StrategySmokeResult(strategy_id="test", compile="", preflight="", missing_factor="", backtest_smoke="")
    assert r.compile == ""
    assert r.preflight == ""
    assert r.missing_factor == ""
    assert r.backtest_smoke == ""
    assert r.reason == ""
    assert r.artifacts == {}


def test_smoke_summary_fields():
    s = SmokeSummary(
        run_id="abc123",
        generated_at="2024-01-01T00:00:00Z",
        environment={"db_configured": False},
        strategies=[],
        overall_status="pass",
    )
    assert s.run_id == "abc123"
    assert s.overall_status == "pass"


def test_write_smoke_summary_produces_valid_json(tmp_path: Path):
    strategies = [
        StrategySmokeResult(
            strategy_id="test_strategy",
            compile="pass",
            preflight="skip",
            missing_factor="skip",
            backtest_smoke="skip",
            reason="no DB configured",
            artifacts={"compiled_strategy_spec": "/tmp/test.json"},
        )
    ]
    summary = SmokeSummary(
        run_id="test_001",
        generated_at="2024-06-01T12:00:00Z",
        environment={"db_configured": False},
        strategies=strategies,
        overall_status="pass",
    )
    path = _write_smoke_summary(summary, tmp_path)
    assert path.exists()

    data = json.loads(path.read_text())
    assert data["run_id"] == "test_001"
    assert data["overall_status"] == "pass"
    assert data["environment"]["db_configured"] is False
    assert len(data["strategies"]) == 1
    s = data["strategies"][0]
    assert s["strategy_id"] == "test_strategy"
    assert s["compile"] == "pass"
    assert s["preflight"] == "skip"
    assert s["missing_factor"] == "skip"
    assert s["backtest_smoke"] == "skip"
    assert s["reason"] == "no DB configured"
    assert "compiled_strategy_spec" in s["artifacts"]


# ---------------------------------------------------------------------------
# Compile integration tests
# ---------------------------------------------------------------------------

RSI2_VALID_YAML = """\
strategy:
  id: rsi2_oversold_reversal
  name: RSI2 Oversold Reversal
  family: mean_reversion
  direction: long_only
  version: "1.0.0"
rules:
  entry:
    all:
      - alias: rsi_fast
        operator: "<"
        value: 10
  exit:
    any:
      - alias: rsi_fast
        operator: ">"
        value: 70
  risk:
    stop_loss_pct: 0.08
    max_holding_days: 5
factor_requirements:
  - alias: rsi_fast
    indicator: rsi
    source: close
    period: 2
    required: true
    reason: RSI2 signal
experiment:
  id: rsi2_smoke
  frequency: daily
  market: ashare
  start: 2024-01-01
  end: 2024-02-01
  universe:
    include: all_a
"""

INVALID_YAML = "strategy: [unclosed"


def test_try_compile_valid_yaml(tmp_path: Path):
    """Valid YAML compiles and writes compiled_strategy_spec.json."""
    yaml_path = tmp_path / "valid_entry.yaml"
    yaml_path.write_text(RSI2_VALID_YAML)
    output_dir = tmp_path / "output"

    status, strategy_id, reason, artifacts = _try_compile(yaml_path, output_dir)

    assert status == "pass"
    assert strategy_id == "rsi2_oversold_reversal"
    assert reason == ""
    assert "compiled_strategy_spec" in artifacts

    spec_path = Path(artifacts["compiled_strategy_spec"])
    assert spec_path.exists()
    spec = json.loads(spec_path.read_text())
    assert spec["signal"]["entry"] == "(rsi_fast < 10)"
    assert spec["signal"]["exit"] == "(rsi_fast > 70)"


def test_try_compile_invalid_yaml(tmp_path: Path):
    """Invalid YAML returns fail status."""
    yaml_path = tmp_path / "invalid.yaml"
    yaml_path.write_text(INVALID_YAML)
    output_dir = tmp_path / "output"

    status, strategy_id, reason, artifacts = _try_compile(yaml_path, output_dir)

    assert status == "fail"
    assert reason != ""
    assert artifacts == {}


def test_try_compile_missing_strategy_section(tmp_path: Path):
    """YAML without strategy section returns fail."""
    yaml_path = tmp_path / "no_strategy.yaml"
    yaml_path.write_text("factor_requirements: []\nexperiment: {}\n")
    output_dir = tmp_path / "output"

    status, strategy_id, reason, artifacts = _try_compile(yaml_path, output_dir)

    assert status == "fail"


# ---------------------------------------------------------------------------
# Runner orchestration tests (no-DB)
# ---------------------------------------------------------------------------

def test_run_strategy_smoke_no_db_all_pass(tmp_path: Path):
    """In a no-DB environment, all three strategies compile but skip later stages."""
    rsi2_path = tmp_path / "rsi2.yaml"
    rsi2_path.write_text(RSI2_VALID_YAML)

    ema_path = tmp_path / "ema200.yaml"
    ema_path.write_text("""\
strategy:
  id: ema200_bollinger_reversal
  name: EMA200 BB Reversal
  family: mean_reversion
  direction: long_only
rules:
  entry:
    all:
      - alias: close
        operator: ">"
        alias_b: ema_200
  risk:
    stop_loss_pct: 0.10
factor_requirements:
  - alias: ema_200
    indicator: ema
    source: close
    period: 200
    required: true
    reason: trend filter
experiment:
  id: smk
  frequency: daily
  market: ashare
  start: 2024-01-01
  end: 2024-02-01
  universe:
    include: all_a
""")

    output_dir = tmp_path / "output"

    summary = run_strategy_smoke(
        strategy_paths=[rsi2_path, ema_path],
        output_dir=output_dir,
        run_preflight=True,
        run_backtest=True,
    )

    assert summary.overall_status == "pass"
    assert summary.environment["db_configured"] is False
    assert len(summary.strategies) == 2

    for s in summary.strategies:
        assert s.compile == "pass"
        assert s.preflight == "skip"
        assert s.missing_factor == "skip"
        assert s.backtest_smoke == "skip"
        assert "database" in s.reason.lower() or "db" in s.reason.lower()
        assert "compiled_strategy_spec" in s.artifacts

    # Verify smoke_summary.json was written
    summary_path = output_dir / "smoke_summary.json"
    assert summary_path.exists()
    data = json.loads(summary_path.read_text())
    assert data["environment"]["db_configured"] is False
    assert data["overall_status"] == "pass"
    assert len(data["strategies"]) == 2


def test_run_strategy_smoke_compile_failure(tmp_path: Path):
    """When a strategy fails to compile, overall status is fail."""
    good_path = tmp_path / "good.yaml"
    good_path.write_text(RSI2_VALID_YAML)

    bad_path = tmp_path / "bad.yaml"
    bad_path.write_text(INVALID_YAML)

    output_dir = tmp_path / "output"

    summary = run_strategy_smoke(
        strategy_paths=[good_path, bad_path],
        output_dir=output_dir,
        run_preflight=False,
        run_backtest=False,
    )

    assert summary.overall_status == "fail"
    results_by_id = {s.strategy_id: s for s in summary.strategies}
    assert results_by_id["rsi2_oversold_reversal"].compile == "pass"
    assert "bad" in results_by_id or any(
        r.compile == "fail" for r in summary.strategies
    )


def test_run_strategy_smoke_emits_deterministic_summary_schema(tmp_path: Path):
    """smoke_summary.json always has the required fields regardless of DB state."""
    yaml_path = tmp_path / "entry.yaml"
    yaml_path.write_text(RSI2_VALID_YAML)
    output_dir = tmp_path / "output"

    run_strategy_smoke(
        strategy_paths=[yaml_path],
        output_dir=output_dir,
    )

    summary_path = output_dir / "smoke_summary.json"
    data = json.loads(summary_path.read_text())

    # Required top-level fields
    assert "run_id" in data
    assert "generated_at" in data
    assert "environment" in data
    assert "strategies" in data
    assert "overall_status" in data

    # Each strategy has required fields
    for s in data["strategies"]:
        assert "strategy_id" in s
        assert "compile" in s
        assert "preflight" in s
        assert "missing_factor" in s
        assert "backtest_smoke" in s
        assert "artifacts" in s
        # reason is present only when skip/fail
        if s["compile"] != "pass" or s["preflight"] == "skip":
            assert "reason" in s

    # overall_status is one of pass/fail
    assert data["overall_status"] in ("pass", "fail")

    # All per-strategy status values are valid
    valid_statuses = {"pass", "skip", "fail"}
    for s in data["strategies"]:
        assert s["compile"] in valid_statuses
        assert s["preflight"] in valid_statuses
        assert s["missing_factor"] in valid_statuses
        assert s["backtest_smoke"] in valid_statuses


def test_run_strategy_smoke_no_preflight_no_backtest_flags(tmp_path: Path):
    """When run_preflight=False and run_backtest=False, all DB stages are skipped."""
    yaml_path = tmp_path / "entry.yaml"
    yaml_path.write_text(RSI2_VALID_YAML)
    output_dir = tmp_path / "output"

    summary = run_strategy_smoke(
        strategy_paths=[yaml_path],
        output_dir=output_dir,
        run_preflight=False,
        run_backtest=False,
    )

    for s in summary.strategies:
        assert s.compile == "pass"
        assert s.preflight == "skip"
        assert s.missing_factor == "skip"
        assert s.backtest_smoke == "skip"


def test_run_strategy_smoke_writes_to_configured_output_dir(tmp_path: Path):
    """Artifacts go to the specified output directory, not a hardcoded path."""
    yaml_path = tmp_path / "entry.yaml"
    yaml_path.write_text(RSI2_VALID_YAML)
    custom_dir = tmp_path / "custom-smoke-output"

    summary = run_strategy_smoke(
        strategy_paths=[yaml_path],
        output_dir=custom_dir,
    )

    assert custom_dir.exists()
    assert (custom_dir / "smoke_summary.json").exists()
    strategy_dir = custom_dir / "rsi2_oversold_reversal"
    assert strategy_dir.exists()
    assert (strategy_dir / "compiled_strategy_spec.json").exists()


# ---------------------------------------------------------------------------
# Backtest-smoke truthiness tests
# ---------------------------------------------------------------------------

def test_try_backtest_smoke_compile_failure_returns_fail(tmp_path: Path):
    """Invalid YAML makes _try_backtest_smoke return ('fail', reason)."""
    yaml_path = tmp_path / "bad.yaml"
    yaml_path.write_text("strategy: [invalid yaml")
    out_dir = tmp_path / "out"
    artifacts: dict[str, str] = {}

    status, reason = _try_backtest_smoke(
        yaml_path, "dummy", out_dir, artifacts, "2024-01-01", "2024-02-01",
    )

    assert status == "fail"
    assert reason != ""
    assert reason.startswith("backtest smoke failed:")


def test_try_backtest_smoke_no_db_connection_returns_fail(
    tmp_path: Path, monkeypatch
):
    """Missing DB URL leads to failure, not a false pass."""
    yaml_path = tmp_path / "entry.yaml"
    yaml_path.write_text(RSI2_VALID_YAML)
    out_dir = tmp_path / "out"
    artifacts: dict[str, str] = {}

    # Force an empty DB URL so that PostgresDataStore cannot connect.
    monkeypatch.setenv("QRE_MARKET_DB_URL", "")
    monkeypatch.setenv("SR_MARKET_DB_URL", "")

    status, reason = _try_backtest_smoke(
        yaml_path, "test_id", out_dir, artifacts, "2024-01-01", "2024-02-01",
    )

    assert status == "fail"
    assert reason != ""


def test_run_strategy_smoke_backtest_fail_sets_overall_fail(
    tmp_path: Path, monkeypatch
):
    """When _try_backtest_smoke returns fail, overall_status becomes fail."""
    yaml_path = tmp_path / "entry.yaml"
    yaml_path.write_text(RSI2_VALID_YAML)
    out_dir = tmp_path / "out"

    # Force DB available + preflight pass so the backtest stage runs.
    monkeypatch.setattr(
        "quant_research_engine.strategies.smoke_runner._check_db_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "quant_research_engine.strategies.smoke_runner._try_preflight",
        lambda *a, **kw: "pass",
    )
    # Inject failure into the backtest-smoke stage.
    monkeypatch.setattr(
        "quant_research_engine.strategies.smoke_runner._try_backtest_smoke",
        lambda *a, **kw: ("fail", "backtest smoke failed: engine error"),
    )

    summary = run_strategy_smoke(
        strategy_paths=[yaml_path],
        output_dir=out_dir,
        run_preflight=True,
        run_backtest=True,
    )

    assert summary.overall_status == "fail"
    assert summary.strategies[0].compile == "pass"
    assert summary.strategies[0].preflight == "pass"
    assert summary.strategies[0].backtest_smoke == "fail"
    assert "engine error" in summary.strategies[0].reason


def test_run_strategy_smoke_backtest_pass_sets_overall_pass(
    tmp_path: Path, monkeypatch
):
    """When _try_backtest_smoke returns pass, overall_status stays pass."""
    yaml_path = tmp_path / "entry.yaml"
    yaml_path.write_text(RSI2_VALID_YAML)
    out_dir = tmp_path / "out"

    monkeypatch.setattr(
        "quant_research_engine.strategies.smoke_runner._check_db_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "quant_research_engine.strategies.smoke_runner._try_preflight",
        lambda *a, **kw: "pass",
    )
    monkeypatch.setattr(
        "quant_research_engine.strategies.smoke_runner._try_backtest_smoke",
        lambda *a, **kw: ("pass", ""),
    )

    summary = run_strategy_smoke(
        strategy_paths=[yaml_path],
        output_dir=out_dir,
        run_preflight=True,
        run_backtest=True,
    )

    assert summary.overall_status == "pass"
    assert summary.strategies[0].backtest_smoke == "pass"
    assert summary.strategies[0].reason == ""


def test_try_backtest_smoke_empty_frame_returns_fail(
    tmp_path: Path, monkeypatch
):
    """An empty research frame causes backtest smoke failure."""
    yaml_path = tmp_path / "entry.yaml"
    yaml_path.write_text(RSI2_VALID_YAML)
    out_dir = tmp_path / "out"
    artifacts: dict[str, str] = {}

    import pandas as pd

    monkeypatch.setenv("QRE_MARKET_DB_URL", "postgresql://localhost/test")
    # Patch the DB chain so the assembler is reached but returns empty.
    monkeypatch.setattr(
        "quant_research_engine.strategies.smoke_runner.PostgresDataStore",
        type("FakeStore", (), {"__init__": lambda s, st: None, "ping": lambda s: None}),
    )
    monkeypatch.setattr(
        "quant_research_engine.strategies.smoke_runner.ResearchFrameAssembler.build",
        lambda self, **kw: pd.DataFrame(),
    )

    status, reason = _try_backtest_smoke(
        yaml_path, "test_id", out_dir, artifacts, "2024-01-01", "2024-02-01",
    )

    assert status == "fail"
    assert "empty research frame" in reason


# ---------------------------------------------------------------------------
# Artifact parity and timing tests
# ---------------------------------------------------------------------------

def test_strategy_smoke_result_durations_s_default():
    """durations_s defaults to empty dict."""
    r = StrategySmokeResult(
        strategy_id="test", compile="pass", preflight="skip",
        missing_factor="skip", backtest_smoke="skip",
    )
    assert r.durations_s == {}


def test_run_strategy_smoke_populates_durations_s(tmp_path: Path):
    """Every strategy result has a non-empty durations_s dict after a run."""
    yaml_path = tmp_path / "entry.yaml"
    yaml_path.write_text(RSI2_VALID_YAML)
    out_dir = tmp_path / "out"

    summary = run_strategy_smoke(
        strategy_paths=[yaml_path],
        output_dir=out_dir,
        run_preflight=False,
        run_backtest=False,
    )

    for s in summary.strategies:
        assert "compile" in s.durations_s
        assert s.durations_s["compile"] > 0.0


def test_write_smoke_summary_includes_durations_s(tmp_path: Path):
    """smoke_summary.json includes durations_s for each strategy."""
    strategies = [
        StrategySmokeResult(
            strategy_id="timed_strategy",
            compile="pass",
            preflight="skip",
            missing_factor="skip",
            backtest_smoke="skip",
            reason="no DB",
            artifacts={"compiled_strategy_spec": "/tmp/test.json"},
            durations_s={"compile": 0.042},
        )
    ]
    summary = SmokeSummary(
        run_id="dur_001",
        generated_at="2024-06-01T12:00:00Z",
        environment={"db_configured": False},
        strategies=strategies,
        overall_status="pass",
    )
    path = _write_smoke_summary(summary, tmp_path)
    data = json.loads(path.read_text())
    s = data["strategies"][0]
    assert "durations_s" in s
    assert s["durations_s"]["compile"] == 0.042


def test_run_strategy_smoke_compile_fail_still_has_durations_s(tmp_path: Path):
    """Even when compile fails, durations_s is populated with compile timing."""
    yaml_path = tmp_path / "bad.yaml"
    yaml_path.write_text("strategy: [bad")
    out_dir = tmp_path / "out"

    summary = run_strategy_smoke(
        strategy_paths=[yaml_path],
        output_dir=out_dir,
    )

    assert summary.strategies[0].compile == "fail"
    assert "compile" in summary.strategies[0].durations_s
    assert summary.strategies[0].durations_s["compile"] > 0.0


def test_run_strategy_smoke_artifacts_preserved_in_summary(tmp_path: Path):
    """Artifact keys and paths are preserved through the full pipeline."""
    yaml_path = tmp_path / "entry.yaml"
    yaml_path.write_text(RSI2_VALID_YAML)
    out_dir = tmp_path / "out"

    summary = run_strategy_smoke(
        strategy_paths=[yaml_path],
        output_dir=out_dir,
        run_preflight=False,
        run_backtest=False,
    )

    s = summary.strategies[0]
    assert "compiled_strategy_spec" in s.artifacts
    spec_path = Path(s.artifacts["compiled_strategy_spec"])
    assert spec_path.exists()

    # Verify smoke_summary.json also has artifacts
    data = json.loads((out_dir / "smoke_summary.json").read_text())
    assert "compiled_strategy_spec" in data["strategies"][0]["artifacts"]


# ---------------------------------------------------------------------------
# Manifest emission tests
# ---------------------------------------------------------------------------

def test_write_smoke_report_manifest_produces_valid_json(tmp_path: Path):
    """Manifest is valid JSON with required top-level fields."""
    strategies = [
        StrategySmokeResult(
            strategy_id="test_strategy",
            compile="pass",
            preflight="skip",
            missing_factor="skip",
            backtest_smoke="skip",
            reason="no DB",
            artifacts={"compiled_strategy_spec": "/tmp/out/test_strategy/compiled_strategy_spec.json"},
        )
    ]
    summary = SmokeSummary(
        run_id="manifest_001",
        generated_at="2024-06-01T12:00:00Z",
        environment={"db_configured": False},
        strategies=strategies,
        overall_status="pass",
    )
    path = _write_smoke_report_manifest(summary, tmp_path)
    assert path.name == "smoke_report_manifest.json"
    assert path.exists()

    data = json.loads(path.read_text())
    assert data["schema_version"] == 1
    assert data["kind"] == "strategy_smoke_report_manifest"
    assert isinstance(data["files"], list)
    assert len(data["files"]) >= 2  # smoke_summary + at least one per-strategy artifact


def test_write_smoke_report_manifest_includes_smoke_summary_entry(tmp_path: Path):
    """Manifest always includes a run-level smoke_summary entry."""
    summary = SmokeSummary(
        run_id="manifest_002",
        generated_at="2024-06-01T12:00:00Z",
        environment={"db_configured": False},
        strategies=[],
        overall_status="pass",
    )
    path = _write_smoke_report_manifest(summary, tmp_path)
    data = json.loads(path.read_text())

    smoke_entry = next(f for f in data["files"] if f["role"] == "smoke_summary")
    assert smoke_entry["key"] == "smoke_summary"
    assert smoke_entry["filename"] == "smoke_summary.json"
    assert "symbol" not in smoke_entry  # run-level entry has no symbol


def test_write_smoke_report_manifest_per_strategy_entries(tmp_path: Path):
    """Per-strategy artifact entries carry role, symbol=strategy_id, and stable key."""
    out_dir = tmp_path / "out"
    strategy_dir = out_dir / "mystrat"
    strategy_dir.mkdir(parents=True)
    spec_path = strategy_dir / "compiled_strategy_spec.json"
    spec_path.write_text("{}")

    strategies = [
        StrategySmokeResult(
            strategy_id="mystrat",
            compile="pass",
            preflight="skip",
            missing_factor="skip",
            backtest_smoke="skip",
            artifacts={"compiled_strategy_spec": str(spec_path)},
        )
    ]
    summary = SmokeSummary(
        run_id="m3",
        generated_at="2024-06-01T12:00:00Z",
        environment={"db_configured": False},
        strategies=strategies,
        overall_status="pass",
    )
    path = _write_smoke_report_manifest(summary, out_dir)
    data = json.loads(path.read_text())

    spec_entries = [f for f in data["files"] if f["role"] == "compiled_strategy_spec"]
    assert len(spec_entries) == 1
    s = spec_entries[0]
    assert s["symbol"] == "mystrat"
    assert "compiled_strategy_spec" in s["key"]
    assert s["filename"] == "compiled_strategy_spec.json"


def test_run_strategy_smoke_emits_manifest(tmp_path: Path):
    """Full run emits smoke_report_manifest.json alongside smoke_summary.json."""
    yaml_path = tmp_path / "entry.yaml"
    yaml_path.write_text(RSI2_VALID_YAML)
    out_dir = tmp_path / "out"

    run_strategy_smoke(
        strategy_paths=[yaml_path],
        output_dir=out_dir,
        run_preflight=False,
        run_backtest=False,
    )

    manifest_path = out_dir / "smoke_report_manifest.json"
    assert manifest_path.exists()

    data = json.loads(manifest_path.read_text())
    assert data["kind"] == "strategy_smoke_report_manifest"
    assert data["schema_version"] == 1

    roles = {f["role"] for f in data["files"]}
    assert "smoke_summary" in roles
    assert "compiled_strategy_spec" in roles


def test_manifest_entries_use_relative_paths(tmp_path: Path):
    """Manifest file paths are relative to output_dir."""
    out_dir = tmp_path / "manifest_out"
    strategy_dir = out_dir / "strata"
    strategy_dir.mkdir(parents=True)
    spec_path = strategy_dir / "compiled_strategy_spec.json"
    spec_path.write_text("{}")

    strategies = [
        StrategySmokeResult(
            strategy_id="strata",
            compile="pass",
            preflight="skip",
            missing_factor="skip",
            backtest_smoke="skip",
            artifacts={"compiled_strategy_spec": str(spec_path)},
        )
    ]
    summary = SmokeSummary(
        run_id="r4",
        generated_at="2024-06-01T12:00:00Z",
        environment={"db_configured": False},
        strategies=strategies,
        overall_status="pass",
    )
    _write_smoke_report_manifest(summary, out_dir)
    data = json.loads((out_dir / "smoke_report_manifest.json").read_text())

    for f in data["files"]:
        assert not f["path"].startswith("/")  # relative
        if f["role"] != "smoke_summary":
            assert f["path"].startswith("strata/")
