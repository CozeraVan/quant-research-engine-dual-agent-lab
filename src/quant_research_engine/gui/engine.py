from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GUI_BASE_DIR = Path("outputs/gui-console")
TEMPLATES_DIR = GUI_BASE_DIR / "templates"
RUNS_DIR = GUI_BASE_DIR / "runs"

RUN_MODES = frozenset({"single", "batch", "shared"})


def _ensure_dirs() -> None:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)


def _run_id() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S%f")


def validate_yaml(yaml_text: str) -> dict[str, Any]:
    """Validate YAML text against the StrategySpec parser.

    Returns {"valid": True} or {"valid": False, "error": str}.
    """
    from quant_research_engine.strategies.spec import StrategySpec

    try:
        import yaml as _yaml

        parsed = _yaml.safe_load(yaml_text)
    except Exception as exc:
        return {"valid": False, "error": f"YAML parse error: {exc}"}
    if not isinstance(parsed, dict):
        return {"valid": False, "error": "YAML must be a mapping (top-level dict)"}
    try:
        StrategySpec.from_mapping(parsed)
    except Exception as exc:
        return {"valid": False, "error": f"StrategySpec error: {exc}"}
    return {"valid": True}


def compile_high_level_entry(data: dict[str, Any]) -> dict[str, Any]:
    """Compile a high-level strategy entry to a low-level StrategySpec YAML.

    Accepts the high-level entry format with sections:
      strategy, rules, factor_requirements, experiment

    Returns:
        {"ok": True, "yaml": "<low-level spec YAML>"}
        or
        {"ok": False, "issues": [{"level": ..., "message": ..., "key": ...}, ...]}
    """
    from quant_research_engine.strategies.compiler import (
        compile_entry,
        compile_to_strategy_spec_dict,
    )

    try:
        entry = compile_entry(data)
    except Exception as exc:
        return {"ok": False, "issues": [{"level": "error", "message": str(exc)}]}

    if not entry.ok:
        issues = [{"level": i.level, "message": i.message} for i in entry.issues]
        return {"ok": False, "issues": issues}

    try:
        import yaml as _yaml

        spec_dict = compile_to_strategy_spec_dict(entry)
        yaml_text = _yaml.safe_dump(spec_dict, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return {"ok": True, "yaml": yaml_text, "compiled": spec_dict}
    except Exception as exc:
        return {"ok": False, "issues": [{"level": "error", "message": f"Failed to generate spec: {exc}"}]}


def run_backtest(
    *,
    yaml_text: str,
    mode: str,
    start: str,
    end: str,
    codes: str,
    initial_cash: str | None = None,
    max_positions: str | None = None,
    output_dir: str | None = None,
    db_url: str | None = None,
    market_profile: str | None = None,
    executor: str = "module",
) -> dict[str, Any]:
    """Run a backtest and return the run record."""
    _ensure_dirs()
    rid = _run_id()
    run_dir = RUNS_DIR / rid
    run_dir.mkdir(parents=True, exist_ok=True)

    strategy_path = run_dir / "strategy.yaml"
    strategy_path.write_text(yaml_text, encoding="utf-8")

    codes_list = [c.strip() for c in codes.split(",") if c.strip()]

    cli_cmd = _build_cli_command(
        mode=mode,
        strategy_path=strategy_path,
        start=start,
        end=end,
        codes=codes_list,
        initial_cash=initial_cash,
        max_positions=max_positions,
        output_dir=output_dir,
        db_url=db_url,
        market_profile=market_profile,
    )

    record: dict[str, Any] = {
        "run_id": rid,
        "mode": mode,
        "start": start,
        "end": end,
        "codes": codes_list,
        "initial_cash": initial_cash,
        "max_positions": max_positions,
        "output_dir": output_dir,
        "executor": executor,
        "cli_command": " ".join(cli_cmd),
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "status": "running",
        "error": None,
    }
    _write_json(run_dir / "request.json", record)

    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"

    try:
        if executor == "cli":
            _run_via_cli(cli_cmd, stdout_path, stderr_path)
        else:
            _run_via_module(
                yaml_text=yaml_text,
                mode=mode,
                start=start,
                end=end,
                codes=codes_list,
                initial_cash=initial_cash,
                max_positions=max_positions,
                output_dir=output_dir,
                db_url=db_url,
                market_profile=market_profile,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
        record["status"] = "completed"
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = str(exc)
        stderr_path.write_text(str(exc), encoding="utf-8")

    record["finished_at"] = datetime.now(tz=timezone.utc).isoformat()
    _write_json(run_dir / "status.json", record)

    # Collect artifact pointers
    if output_dir and Path(output_dir).exists():
        artifacts: dict[str, str] = {}
        for p in Path(output_dir).rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(output_dir))
                artifacts[rel] = str(p)
        record["artifacts"] = artifacts

    return record


def _run_via_module(
    *,
    yaml_text: str,
    mode: str,
    start: str,
    end: str,
    codes: list[str],
    initial_cash: str | None,
    max_positions: str | None,
    output_dir: str | None,
    db_url: str | None,
    market_profile: str | None,
    stdout_path: Path,
    stderr_path: Path,
) -> None:
    """Execute backtest via direct Python module call (mirrors CLI flow)."""
    import io
    from contextlib import redirect_stdout, redirect_stderr

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as tf:
        tf.write(yaml_text)
        tmp_path = tf.name

    try:
        from quant_research_engine.strategies.spec import StrategySpec
        from quant_research_engine.data.settings import DatabaseSettings
        from quant_research_engine.data.postgres import PostgresDataStore
        from quant_research_engine.data.assembler import ResearchFrameAssembler
        from quant_research_engine.config.loader import load_market_profile
        from quant_research_engine.markets.ashare import AShareMarketProfile

        settings = (
            DatabaseSettings(market_db_url=db_url)
            if db_url
            else DatabaseSettings.from_env()
        )
        store = PostgresDataStore(settings)
        store.ping()

        spec = StrategySpec.from_yaml(tmp_path)

        frame = ResearchFrameAssembler(store).build(
            ts_codes=codes,
            start=start,
            end=end,
            market_fields=spec.market_fields,
            factor_fields=spec.factor_fields,
            include_metadata=True,
        )

        if market_profile:
            mp = load_market_profile(market_profile)
        else:
            mp = AShareMarketProfile()

        buf_out = io.StringIO()
        buf_err = io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            _execute_engine(
                mode=mode,
                spec=spec,
                mp=mp,
                frame=frame,
                codes=codes,
                start=start,
                end=end,
                initial_cash=initial_cash,
                max_positions=max_positions,
                output_dir=output_dir,
            )

        stdout_path.write_text(buf_out.getvalue(), encoding="utf-8")
        stderr_path.write_text(buf_err.getvalue(), encoding="utf-8")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _execute_engine(
    *,
    mode: str,
    spec: Any,
    mp: Any,
    frame: Any,
    codes: list[str],
    start: str,
    end: str,
    initial_cash: str | None,
    max_positions: str | None,
    output_dir: str | None,
) -> None:
    from quant_research_engine.portfolio.single_symbol import SingleSymbolBacktestEngine, SingleSymbolBacktestRequest
    from quant_research_engine.portfolio.batch import BatchBacktestEngine, BatchBacktestRequest
    from quant_research_engine.portfolio.shared import SharedCashBacktestEngine, SharedCashBacktestRequest
    from quant_research_engine.portfolio.io import (
        write_single_symbol_result,
        write_batch_result,
        write_shared_cash_result,
    )

    if mode == "single":
        if not codes:
            raise ValueError("At least one code required for single-symbol backtest")
        result = SingleSymbolBacktestEngine(mp).run(
            frame,
            SingleSymbolBacktestRequest(
                symbol=codes[0],
                initial_cash=float(initial_cash) if initial_cash else 100_000.0,
                entry_signal=spec.signal_expression,
                exit_signal=spec.exit_signal_expression,
                holding_days=spec.holding_days,
            ),
        )
        print(f"strategy={spec.name}")
        print(f"symbol={codes[0]}")
        print(f"orders={len(result.orders)}")
        print(f"trades={len(result.trades)}")
        for key, value in result.summary.items():
            print(f"{key}={value}")
        if output_dir:
            paths = write_single_symbol_result(result, output_dir)
            for key, path in paths.items():
                print(f"{key}_path={path}")

    elif mode == "batch":
        result = BatchBacktestEngine(mp).run(
            frame,
            BatchBacktestRequest(
                symbols=codes,
                initial_cash_per_symbol=float(initial_cash) if initial_cash else 100_000.0,
                entry_signal=spec.signal_expression,
                exit_signal=spec.exit_signal_expression,
                holding_days=spec.holding_days,
            ),
        )
        print(f"strategy={spec.name}")
        print(f"symbols={len(result.symbols)}")
        for key, value in result.summary_metrics.items():
            print(f"{key}={value}")
        print(result.summary.to_csv(index=False).strip())
        if output_dir:
            write_batch_result(result, output_dir)

    elif mode == "shared":
        cash = float(initial_cash) if initial_cash else 100_000.0
        positions = int(max_positions) if max_positions else 10
        result = SharedCashBacktestEngine(mp).run(
            frame,
            SharedCashBacktestRequest(
                symbols=codes,
                initial_cash=cash,
                entry_signal=spec.signal_expression,
                exit_signal=spec.exit_signal_expression,
                holding_days=spec.holding_days,
                max_positions=positions,
            ),
        )
        print(f"strategy={spec.name}")
        print(f"symbols={0 if codes is None else len(codes)}")
        print(f"orders={len(result.orders)}")
        print(f"trades={len(result.trades)}")
        for key, value in result.summary.items():
            print(f"{key}={value}")
        if output_dir:
            write_shared_cash_result(result, output_dir)


def _run_via_cli(cmd: list[str], stdout_path: Path, stderr_path: Path) -> None:
    with open(stdout_path, "w", encoding="utf-8") as out, open(stderr_path, "w", encoding="utf-8") as err:
        subprocess.run(cmd, stdout=out, stderr=err, check=True, text=True, timeout=600)


def _build_cli_command(
    *,
    mode: str,
    strategy_path: Path,
    start: str,
    end: str,
    codes: list[str],
    initial_cash: str | None,
    max_positions: str | None,
    output_dir: str | None,
    db_url: str | None,
    market_profile: str | None,
) -> list[str]:
    mode_map = {"single": "backtest-single", "batch": "backtest-batch", "shared": "backtest-shared"}
    cmd = [sys.executable, "-m", "quant_research_engine.apps.cli", mode_map[mode]]
    cmd.extend([str(strategy_path), "--start", start, "--end", end])
    cmd.extend(["--codes"] + codes)
    if mode == "single":
        cmd = [sys.executable, "-m", "quant_research_engine.apps.cli", "backtest-single"]
        cmd.extend([str(strategy_path), "--symbol", codes[0] if codes else "", "--start", start, "--end", end])
    else:
        cmd.extend(["--codes"] + codes)
    if initial_cash:
        cmd.extend(["--initial-cash", initial_cash])
    if max_positions:
        cmd.extend(["--max-positions", max_positions])
    if output_dir:
        cmd.extend(["--output-dir", output_dir])
    if db_url:
        cmd.extend(["--db-url", db_url])
    if market_profile:
        cmd.extend(["--market-profile", market_profile])
    return cmd


# --- run history ---

def list_runs() -> list[dict[str, Any]]:
    _ensure_dirs()
    runs: list[dict[str, Any]] = []
    if not RUNS_DIR.exists():
        return runs
    for run_dir in sorted(RUNS_DIR.iterdir(), reverse=True):
        status_path = run_dir / "status.json"
        if not status_path.exists():
            continue
        try:
            record = json.loads(status_path.read_text(encoding="utf-8"))
            runs.append(record)
        except (json.JSONDecodeError, OSError):
            continue
    return runs


def get_run(run_id: str) -> dict[str, Any] | None:
    status_path = RUNS_DIR / run_id / "status.json"
    if not status_path.exists():
        return None
    try:
        return json.loads(status_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def get_run_stdout(run_id: str) -> str | None:
    p = RUNS_DIR / run_id / "stdout.log"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return None


def get_run_stderr(run_id: str) -> str | None:
    p = RUNS_DIR / run_id / "stderr.log"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return None


def get_run_strategy_yaml(run_id: str) -> str | None:
    p = RUNS_DIR / run_id / "strategy.yaml"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return None


def get_run_artifacts(run_id: str) -> dict[str, str]:
    record = get_run(run_id)
    if record and "artifacts" in record:
        return record["artifacts"]
    return {}


# --- templates ---

def save_template(name: str, yaml_text: str) -> None:
    _ensure_dirs()
    safe_name = name.replace("/", "_").replace("\\", "_").strip()
    if not safe_name:
        raise ValueError("Template name must not be empty")
    path = TEMPLATES_DIR / f"{safe_name}.yaml"
    path.write_text(yaml_text, encoding="utf-8")


def list_templates() -> list[str]:
    _ensure_dirs()
    if not TEMPLATES_DIR.exists():
        return []
    return sorted(p.stem for p in TEMPLATES_DIR.glob("*.yaml"))


def load_template(name: str) -> str | None:
    path = TEMPLATES_DIR / f"{name}.yaml"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
