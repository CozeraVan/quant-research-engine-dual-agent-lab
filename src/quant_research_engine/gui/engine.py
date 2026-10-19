from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import tempfile
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

GUI_BASE_DIR = Path("outputs/gui-console")
TEMPLATES_DIR = GUI_BASE_DIR / "templates"
RUNS_DIR = GUI_BASE_DIR / "runs"

RUN_MODES = frozenset({"single", "batch", "shared"})

# --- async execution & concurrency limit ---
MAX_CONCURRENT_RUNS = 2
_run_slot_lock = threading.Lock()
_running_count = 0

# --- small-sample precheck defaults ---
PRECHECK_MAX_CODES = 20
PRECHECK_WINDOW_DAYS = 180


def _ensure_dirs() -> None:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)


def _run_id() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S%f")


# --- concurrency slots ---

def try_acquire_run_slot() -> bool:
    """Try to acquire a run slot; returns False when the limit is reached."""
    global _running_count
    with _run_slot_lock:
        if _running_count >= MAX_CONCURRENT_RUNS:
            return False
        _running_count += 1
        return True


def release_run_slot() -> None:
    global _running_count
    with _run_slot_lock:
        _running_count = max(0, _running_count - 1)


def running_count() -> int:
    with _run_slot_lock:
        return _running_count


# --- precheck (小样本预检) ---

def apply_precheck(
    codes: list[str],
    start: str,
    end: str,
    *,
    max_codes: int = PRECHECK_MAX_CODES,
    window_days: int = PRECHECK_WINDOW_DAYS,
    seed: str | None = None,
    db_url: str | None = None,
) -> tuple[list[str], str, str]:
    """Truncate the universe to ``max_codes`` codes and the window
    to roughly the last ``window_days`` days before ``end``.

    codes 为空（全市场 scope）时绝不能原样放行——那会把"小样本预检"变成
    全市场回测（job 54 事故）。此时从全 A 股池按 seed（run_id）随机抽
    ``max_codes`` 只，与 _sample_random_universe 同口径、可复现。"""
    trimmed_codes = codes[:max_codes] if codes else codes
    if not trimmed_codes:
        trimmed_codes = _sample_random_universe(max_codes, seed or "precheck", db_url=db_url)
    try:
        end_date = date.fromisoformat(end)
        start_date = date.fromisoformat(start)
    except ValueError:
        return trimmed_codes, start, end
    min_start = end_date - timedelta(days=window_days)
    if start_date < min_start:
        start_date = min_start
    return trimmed_codes, start_date.isoformat(), end


def build_market_profile(overrides: dict[str, float] | None) -> Any:
    """Build an AShareMarketProfile with optional field overrides."""
    from dataclasses import replace

    from quant_research_engine.markets.ashare import AShareMarketProfile

    profile = AShareMarketProfile()
    if overrides:
        valid = {k: float(v) for k, v in overrides.items() if v is not None and hasattr(profile, k)}
        if valid:
            profile = replace(profile, **valid)
    return profile


def _override_holding_days(spec: Any, max_holding_days: int | None) -> Any:
    """显式 max_holding_days 覆盖 YAML holding 节；None 保持 YAML 原值。

    语义与 StrategySpec 一致：0 = 不限持仓天数。StrategySpec 为 frozen
    dataclass，用 replace 生成新实例。
    """
    if max_holding_days is None:
        return spec
    from dataclasses import replace

    return replace(spec, holding_days=int(max_holding_days))


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


def _sample_random_universe(random_n: int, seed: str, *, db_url: str | None = None) -> list[str]:
    """从全 A 股池随机抽 N 只（种子=run_id，可复现；N 超池子上限则截断）。"""
    from quant_research_engine.data.settings import DatabaseSettings
    from quant_research_engine.data.postgres import PostgresDataStore

    settings = DatabaseSettings(market_db_url=db_url) if db_url else DatabaseSettings.from_env()
    store = PostgresDataStore(settings)
    meta = store.load_security_metadata(ts_codes=None)
    pool = sorted(meta["ts_code"].dropna().astype(str).unique().tolist())
    return random.Random(seed).sample(pool, min(random_n, len(pool)))


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
    profile_overrides: dict[str, float] | None = None,
    engine_impl: str = "simulator",
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
    trailing_stop_pct: float | None = None,
    max_holding_days: int | None = None,
    precheck: bool = False,
    random_n: int | None = None,
    background: bool = False,
    mark: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a backtest and return the run record.

    With ``background=True`` the execution runs in a daemon thread and the
    record is returned immediately with ``status="running"``; status.json is
    updated in place when the run finishes. The caller is responsible for
    acquiring/releasing a concurrency slot (see api_run).

    ``mark`` 的键值在线程启动前合并进 run 记录（如 sandbox_strategy/purpose），
    避免事后补写与后台线程的完成回写产生竞态。
    """
    _ensure_dirs()
    rid = _run_id()
    run_dir = RUNS_DIR / rid
    run_dir.mkdir(parents=True, exist_ok=True)

    strategy_path = run_dir / "strategy.yaml"
    strategy_path.write_text(yaml_text, encoding="utf-8")

    codes_list = [c.strip() for c in codes.split(",") if c.strip()]

    # 服务端随机抽样（QRE-LAB-RANDOM-UNIVERSE）：random_n 指定时从全 A 股池抽 N 只。
    # 种子取 run_id（同 run 可复现）；实际抽中的 codes 写进 record（status.json），
    # 结果页/记录页可见实际抽中名单。
    sampled_random = False
    if random_n and not codes_list:
        codes_list = _sample_random_universe(random_n, rid, db_url=db_url)
        sampled_random = True

    full_params: dict[str, Any] | None = None
    if precheck:
        full_params = {
            "codes": codes,
            "start": start,
            "end": end,
            "initial_cash": initial_cash,
            "max_positions": max_positions,
            "engine_impl": engine_impl,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "trailing_stop_pct": trailing_stop_pct,
            "max_holding_days": max_holding_days,
            "profile_overrides": profile_overrides,
        }
        codes_list, start, end = apply_precheck(codes_list, start, end, seed=rid, db_url=db_url)

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
        "engine_impl": engine_impl,
        "cli_command": " ".join(cli_cmd),
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "status": "running",
        "error": None,
        # QRE-LAB-UI-LANDING-R6：僵尸 run 自愈——记录提交时的 GUI 进程 PID，
        # module 执行器生命周期依附该进程，PID 不一致即执行器已随旧进程死亡
        "gui_pid": os.getpid(),
    }
    if profile_overrides:
        record["profile_overrides"] = profile_overrides
    if stop_loss_pct is not None:
        record["stop_loss_pct"] = stop_loss_pct
    if take_profit_pct is not None:
        record["take_profit_pct"] = take_profit_pct
    if trailing_stop_pct is not None:
        record["trailing_stop_pct"] = trailing_stop_pct
    if max_holding_days is not None:
        # 与 stop/take/trailing 同口径：显式传入时以参数为准覆盖 YAML holding 节
        record["max_holding_days"] = int(max_holding_days)
    if sampled_random:
        record["random_n"] = random_n
        record["universe"] = "random"
    if precheck:
        record["precheck"] = True
        record["full_params"] = full_params
    if mark:
        record.update(mark)
    _write_json(run_dir / "request.json", record)
    _write_json(run_dir / "status.json", record)

    exec_kwargs: dict[str, Any] = {
        "yaml_text": yaml_text,
        "mode": mode,
        "start": start,
        "end": end,
        "codes": codes_list,
        "initial_cash": initial_cash,
        "max_positions": max_positions,
        "output_dir": output_dir,
        "db_url": db_url,
        "market_profile": market_profile,
        "profile_overrides": profile_overrides,
        "engine_impl": engine_impl,
        "stop_loss_pct": stop_loss_pct,
        "take_profit_pct": take_profit_pct,
        "trailing_stop_pct": trailing_stop_pct,
        "max_holding_days": max_holding_days,
    }

    if background:
        thread = threading.Thread(
            target=_execute_and_finalize,
            args=(record, run_dir, cli_cmd, exec_kwargs),
            kwargs={"release_slot": True},
            daemon=True,
        )
        thread.start()
        return record

    _execute_and_finalize(record, run_dir, cli_cmd, exec_kwargs)
    return record


def _execute_and_finalize(
    record: dict[str, Any],
    run_dir: Path,
    cli_cmd: list[str],
    exec_kwargs: dict[str, Any],
    *,
    release_slot: bool = False,
) -> None:
    """Execute the backtest and update status.json + artifacts in place."""
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    try:
        if record["executor"] == "cli":
            _run_via_cli(cli_cmd, stdout_path, stderr_path)
        else:
            _run_via_module(
                **exec_kwargs,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
        record["status"] = "completed"
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = str(exc)
        stderr_path.write_text(str(exc), encoding="utf-8")
    finally:
        if release_slot:
            release_run_slot()

    record["finished_at"] = datetime.now(tz=timezone.utc).isoformat()
    _write_json(run_dir / "status.json", record)

    # Collect artifact pointers
    output_dir = record.get("output_dir")
    if output_dir and Path(output_dir).exists():
        artifacts: dict[str, str] = {}
        for p in Path(output_dir).rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(output_dir))
                artifacts[rel] = str(p)
        record["artifacts"] = artifacts
        _write_json(run_dir / "status.json", record)

    # 沙箱策略冒烟闭环：run 终态回写 <name>.smoke.json sidecar。
    # sidecar 回写失败不应影响 run 本身的收尾，故整体兜底。
    if record.get("sandbox_strategy"):
        try:
            from quant_research_engine.gui import strategy_create

            strategy_create.finalize_smoke(record)
        except Exception:
            pass

    # 晋升全量回测闸：评估并回写 outputs/refresh/gates/<name>.json（同样兜底）。
    if record.get("promotion_gate"):
        try:
            from quant_research_engine.gui import strategy_create

            strategy_create.finalize_promotion_gate(record)
        except Exception:
            pass

    # FRM 风险分析：completed run 自动生成 risk_report.json + 报告风险节。
    # 失败绝不影响 run 本身（与 smoke/promotion_gate 同模式兜底）。
    if record.get("status") == "completed":
        try:
            from quant_research_engine.gui import risk_report

            risk_report.finalize_risk_report(record)
        except Exception:
            pass


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
    profile_overrides: dict[str, float] | None = None,
    engine_impl: str = "simulator",
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
    trailing_stop_pct: float | None = None,
    max_holding_days: int | None = None,
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

        settings = (
            DatabaseSettings(market_db_url=db_url)
            if db_url
            else DatabaseSettings.from_env()
        )
        store = PostgresDataStore(settings)
        store.ping()

        spec = StrategySpec.from_yaml(tmp_path)
        # max_holding_days 参数覆盖（SaaS 高级参数为权威来源）：jobs.params 落库值
        # 与引擎生效值保持一致，不再依赖前端把表单值注入 YAML holding 节
        # （YAML 自带 max_holding_days 时前端不覆盖，导致落库≠生效）。
        spec = _override_holding_days(spec, max_holding_days)

        # Empty code list = whole market (assembler/engine accept None).
        ts_codes = codes or None

        # 批量模式流式执行（内存峰值控制，2026-09-14）：股票数超过
        # QRE_BATCH_CHUNK_SIZE（默认 250）或为全市场时，按块加载+跑+落盘，
        # 避免全池 frame 一次性进内存。单标的/共享资金路径不变。
        if mode == "batch":
            all_symbols = ts_codes
            if all_symbols is None:
                metadata = store.load_security_metadata(ts_codes=None)
                all_symbols = sorted(metadata["ts_code"].dropna().astype(str).unique().tolist())
            from quant_research_engine.portfolio.streaming_batch import (
                STREAMING_MIN_SYMBOLS,
                run_batch_streaming,
            )

            if len(all_symbols) > STREAMING_MIN_SYMBOLS:
                if market_profile:
                    mp = load_market_profile(market_profile)
                    if profile_overrides:
                        from dataclasses import replace

                        valid = {k: float(v) for k, v in profile_overrides.items() if v is not None and hasattr(mp, k)}
                        if valid:
                            mp = replace(mp, **valid)
                else:
                    mp = build_market_profile(profile_overrides)

                def frame_factory(chunk_symbols: list[str]) -> Any:
                    return ResearchFrameAssembler(store).build(
                        ts_codes=chunk_symbols,
                        start=start,
                        end=end,
                        market_fields=spec.market_fields,
                        factor_fields=spec.factor_fields,
                        include_metadata=True,
                    )

                from quant_research_engine.portfolio.batch import BatchBacktestRequest
                from quant_research_engine.portfolio.io import write_batch_result

                buf_out = io.StringIO()
                buf_err = io.StringIO()
                with redirect_stdout(buf_out), redirect_stderr(buf_err):
                    result = run_batch_streaming(
                        frame_factory=frame_factory,
                        symbols=all_symbols,
                        request=BatchBacktestRequest(
                            symbols=all_symbols,
                            initial_cash_per_symbol=float(initial_cash) if initial_cash else 100_000.0,
                            entry_signal=spec.signal_expression,
                            exit_signal=spec.exit_signal_expression,
                            holding_days=spec.holding_days,
                            engine_impl=engine_impl,
                            stop_loss_pct=stop_loss_pct,
                            take_profit_pct=take_profit_pct,
                            trailing_stop_pct=trailing_stop_pct,
                        ),
                        market_profile=mp,
                        output_dir=output_dir,
                    )
                    print(f"strategy={spec.name}")
                    print(f"symbols={len(result.symbols)}")
                    for key, value in result.summary_metrics.items():
                        print(f"{key}={value}")
                    print(result.summary.to_csv(index=False).strip())
                    if output_dir:
                        write_batch_result(result, output_dir)
                stdout_path.write_text(buf_out.getvalue(), encoding="utf-8")
                stderr_path.write_text(buf_err.getvalue(), encoding="utf-8")
                return

        # 共享资金（shared）模式的内存收敛（2026-10-18，job#71 全市场全期 OOM 修复）：
        # 分块装配（build_chunked）——按股分块加载/合并，metadata 只并撮合必需列
        # （外加信号表达式实际引用的列，防裁剪掉信号输入），ts_code 转 category；
        # 全市场 frame 不再一次性物化多份拷贝。交易信号/成交价/收益统计与旧口径一致
        # （同表同区间同字段，仅装载组织方式不同）。
        if mode == "shared":
            from quant_research_engine.evaluation.signals import referenced_fields

            signal_fields = referenced_fields(spec.signal_expression) | referenced_fields(
                spec.exit_signal_expression
            )
            known_data_cols = set(spec.market_fields) | {
                f.logical_name for f in spec.factor_fields
            }
            meta_extra = sorted(signal_fields - known_data_cols)
            frame = ResearchFrameAssembler(store).build_chunked(
                ts_codes=ts_codes,
                start=start,
                end=end,
                market_fields=spec.market_fields,
                factor_fields=spec.factor_fields,
                metadata_columns=["is_st", "is_suspended", *meta_extra],
            )
        else:
            frame = ResearchFrameAssembler(store).build(
                ts_codes=ts_codes,
                start=start,
                end=end,
                market_fields=spec.market_fields,
                factor_fields=spec.factor_fields,
                include_metadata=True,
            )

        if market_profile:
            mp = load_market_profile(market_profile)
            if profile_overrides:
                from dataclasses import replace

                valid = {k: float(v) for k, v in profile_overrides.items() if v is not None and hasattr(mp, k)}
                if valid:
                    mp = replace(mp, **valid)
        else:
            mp = build_market_profile(profile_overrides)

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
                engine_impl=engine_impl,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                trailing_stop_pct=trailing_stop_pct,
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
    engine_impl: str = "simulator",
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
    trailing_stop_pct: float | None = None,
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
                symbols=codes or None,
                initial_cash_per_symbol=float(initial_cash) if initial_cash else 100_000.0,
                entry_signal=spec.signal_expression,
                exit_signal=spec.exit_signal_expression,
                holding_days=spec.holding_days,
                engine_impl=engine_impl,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                trailing_stop_pct=trailing_stop_pct,
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
        # QRE-MAXPOS-UNLIMITED：0 → None（不限制）；缺省保持 GUI 默认 10
        if max_positions in (None, ""):
            positions = 10
        elif int(max_positions) == 0:
            positions = None
        else:
            positions = int(max_positions)
        result = SharedCashBacktestEngine(mp).run(
            frame,
            SharedCashBacktestRequest(
                symbols=codes or None,
                initial_cash=cash,
                entry_signal=spec.signal_expression,
                exit_signal=spec.exit_signal_expression,
                holding_days=spec.holding_days,
                max_positions=positions,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                trailing_stop_pct=trailing_stop_pct,
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


# --- summary extraction (出口摘要卡) ---

# (key, 中文标签, 是否按百分比显示)
SUMMARY_METRIC_FIELDS: list[tuple[str, str, bool]] = [
    ("strategy_name", "策略名称", False),
    ("date_start", "开始日期", False),
    ("date_end", "结束日期", False),
    ("traded_symbol_count", "触发交易股票数", False),
    ("symbol_count", "总股票数", False),
    ("total_trade_count", "总交易数", False),
    ("win_rate", "胜率", True),
    ("strategy_total_return", "总收益率", True),
    ("buy_hold_return", "买入持有收益率", True),
    ("excess_return_vs_buy_hold", "超额收益(对买入持有)", True),
    ("max_drawdown", "最大回撤", True),
    ("profit_factor", "盈亏比", False),
]


# stdout key=value 回退解析时的键名别名（对齐 strategy_performance.json 的键）
_STDOUT_KEY_ALIASES = {
    "total_return": "strategy_total_return",
    "trades": "total_trade_count",
    "symbols": "symbol_count",
}


def _find_output_file(record: dict[str, Any], filename: str) -> Path | None:
    """Locate a named output file via the artifacts map, then rglob fallback."""
    artifacts = record.get("artifacts") or {}
    for rel, abs_path in artifacts.items():
        if Path(rel).name == filename and Path(abs_path).exists():
            return Path(abs_path)
    output_dir = record.get("output_dir")
    if output_dir and Path(output_dir).exists():
        for p in sorted(Path(output_dir).rglob(filename)):
            if p.is_file():
                return p
    return None


def extract_run_summary(record: dict[str, Any]) -> dict[str, Any] | None:
    """Extract display metrics for a run.

    Prefers ``strategy_performance.json`` (batch/full-market artifact);
    falls back to parsing ``key=value`` lines from stdout.log.
    Returns {"source": "json"|"stdout", "metrics": {key: value}} or None.
    """
    json_path = _find_output_file(record, "strategy_performance.json")
    if json_path is not None:
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = None
        if isinstance(data, dict):
            metrics = {key: data.get(key) for key, _, _ in SUMMARY_METRIC_FIELDS if data.get(key) is not None}
            if metrics:
                return {"source": "json", "metrics": metrics}

    stdout = get_run_stdout(record.get("run_id", ""))
    if not stdout:
        return None
    metrics: dict[str, Any] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if "=" not in line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key or not value:
            continue
        key = _STDOUT_KEY_ALIASES.get(key, key)
        try:
            metrics[key] = float(value)
        except ValueError:
            metrics[key] = value
    if not metrics:
        return None
    return {"source": "stdout", "metrics": metrics}


def compare_run_summaries(
    record_a: dict[str, Any],
    record_b: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build per-metric comparison rows: {"key", "label", "a", "b", "diff", "is_pct"}.

    ``diff`` is b - a for numeric values, else None.
    """
    summary_a = extract_run_summary(record_a) or {}
    summary_b = extract_run_summary(record_b) or {}
    metrics_a = summary_a.get("metrics", {})
    metrics_b = summary_b.get("metrics", {})

    keys: list[tuple[str, str, bool]] = list(SUMMARY_METRIC_FIELDS)
    known = {k for k, _, _ in keys}
    for extra in sorted((set(metrics_a) | set(metrics_b)) - known):
        keys.append((extra, extra, False))

    rows: list[dict[str, Any]] = []
    for key, label, is_pct in keys:
        va = metrics_a.get(key)
        vb = metrics_b.get(key)
        if va is None and vb is None:
            continue
        diff = None
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            diff = vb - va
        rows.append({"key": key, "label": label, "a": va, "b": vb, "diff": diff, "is_pct": is_pct})
    return rows


def equity_curve_svg(record: dict[str, Any], *, width: int = 640, height: int = 180) -> str | None:
    """Render an inline SVG polyline of equity_curve.csv (offline, no JS)."""
    csv_path = _find_output_file(record, "equity_curve.csv")
    if csv_path is None:
        return None
    try:
        import csv

        with open(csv_path, "r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
    except OSError:
        return None
    if not rows or reader.fieldnames is None:
        return None

    col = None
    for candidate in ("total_equity", "equity", "total_value"):
        if candidate in reader.fieldnames:
            col = candidate
            break
    if col is None:
        return None

    values: list[float] = []
    for row in rows:
        try:
            values.append(float(row[col]))
        except (TypeError, ValueError):
            continue
    if len(values) < 2:
        return None

    # Downsample to at most ~300 points to keep the SVG small.
    step = max(1, len(values) // 300)
    values = values[::step]

    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    pad = 4
    n = len(values)
    points = []
    for i, v in enumerate(values):
        x = pad + (width - 2 * pad) * i / (n - 1)
        y = pad + (height - 2 * pad) * (1 - (v - lo) / span)
        points.append(f"{x:.1f},{y:.1f}")
    polyline = " ".join(points)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="权益曲线">'
        f'<rect width="{width}" height="{height}" fill="#fafafa" stroke="#ddd"/>'
        f'<polyline fill="none" stroke="#2563eb" stroke-width="1.5" points="{polyline}"/>'
        f'<text x="{pad}" y="{pad + 10}" font-size="10" fill="#666">{hi:.2f}</text>'
        f'<text x="{pad}" y="{height - pad}" font-size="10" fill="#666">{lo:.2f}</text>'
        f"</svg>"
    )


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
