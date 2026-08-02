from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_from_directory

from quant_research_engine.gui.engine import (
    compare_run_summaries,
    compile_high_level_entry,
    equity_curve_svg,
    extract_run_summary,
    get_run,
    get_run_artifacts,
    get_run_stderr,
    get_run_stdout,
    get_run_strategy_yaml,
    list_runs,
    list_templates,
    load_template,
    release_run_slot,
    run_backtest,
    save_template,
    try_acquire_run_slot,
    validate_yaml,
)

GUI_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = GUI_DIR / "templates"
STATIC_DIR = GUI_DIR / "static"
DEFAULT_STRATEGY_TEMPLATE = Path(__file__).resolve().parents[3] / "strategies" / "low_level" / "bollinger_mean_reversion.yaml"


def _load_default_strategy_yaml() -> str:
    if DEFAULT_STRATEGY_TEMPLATE.exists():
        return DEFAULT_STRATEGY_TEMPLATE.read_text(encoding="utf-8")
    return (
        "experiment:\n"
        "  name: bollinger_mean_reversion\n"
        "data:\n"
        "  market_fields:\n"
        "    - open\n"
        "    - high\n"
        "    - low\n"
        "    - close\n"
        "    - pre_close\n"
        "    - vol\n"
        "    - amount\n"
        "  factor_fields:\n"
        "    bb_lower: factors.stock_daily_volatility_close.bbl_20_2_0_2_0\n"
        "    bb_middle: factors.stock_daily_volatility_close.bbm_20_2_0_2_0\n"
        "signal:\n"
        "  entry: (close <= bb_lower)\n"
        "  exit: (close >= bb_middle)\n"
        "evaluation:\n"
        "  forward_return_horizons: [1, 3, 5, 10, 20]\n"
        "holding:\n"
        "  max_holding_days: 20\n"
        "risk:\n"
        "  stop_loss_pct: 0.08\n"
    )


def _fmtval(value: Any, is_pct: bool = False) -> str:
    """Jinja filter: two-decimal display, optional percent scaling."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value * 100:.2f}%" if is_pct else f"{value:,.2f}"
    return str(value)


def _summary_display_rows(summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Ordered display rows for the run-detail summary card."""
    if not summary:
        return []
    from quant_research_engine.gui.engine import SUMMARY_METRIC_FIELDS

    metrics = summary.get("metrics", {})
    rows: list[dict[str, Any]] = []
    known = {k for k, _, _ in SUMMARY_METRIC_FIELDS}
    for key, label, is_pct in SUMMARY_METRIC_FIELDS:
        if key in metrics:
            rows.append({"key": key, "label": label, "value": metrics[key], "is_pct": is_pct})
    for key in sorted(set(metrics) - known):
        rows.append({"key": key, "label": key, "value": metrics[key], "is_pct": False})
    return rows


def create_app() -> Flask:
    app = Flask(__name__, template_folder=str(TEMPLATE_DIR), static_folder=str(STATIC_DIR))
    app.config["SECRET_KEY"] = os.urandom(24)
    app.add_template_filter(_fmtval, "fmtval")

    # --- page routes ---

    @app.route("/")
    def index() -> str:
        templates = list_templates()
        return render_template(
            "index.html",
            templates=templates,
            default_strategy_yaml=_load_default_strategy_yaml(),
            default_strategy_name="ema200_bollinger_reversal_mvp",
        )

    @app.route("/runs")
    def runs_page() -> str:
        runs = list_runs()
        return render_template("runs.html", runs=runs)

    @app.route("/runs/<run_id>")
    def run_detail(run_id: str) -> str:
        record = get_run(run_id)
        if record is None:
            return render_template("error.html", message=f"Run {run_id} not found"), 404
        stdout = get_run_stdout(run_id)
        stderr = get_run_stderr(run_id)
        artifacts = get_run_artifacts(run_id)
        summary = extract_run_summary(record)
        equity_svg = equity_curve_svg(record)
        return render_template(
            "run_detail.html",
            run=record,
            stdout=stdout,
            stderr=stderr,
            artifacts=artifacts,
            summary=summary,
            summary_fields=_summary_display_rows(summary),
            equity_svg=equity_svg,
        )

    @app.route("/compare")
    def compare_page() -> Any:
        run_a = request.args.get("a", "")
        run_b = request.args.get("b", "")
        record_a = get_run(run_a) if run_a else None
        record_b = get_run(run_b) if run_b else None
        if record_a is None or record_b is None:
            return render_template("error.html", message="对比需要两个有效的 run ID（参数 a 和 b）"), 404
        rows = compare_run_summaries(record_a, record_b)
        return render_template("compare.html", run_a=record_a, run_b=record_b, rows=rows)

    # --- API routes ---

    @app.route("/api/validate", methods=["POST"])
    def api_validate() -> Any:
        data = request.get_json(silent=True) or {}
        yaml_text = data.get("yaml", "")
        result = validate_yaml(yaml_text)
        return jsonify(result)

    @app.route("/api/run", methods=["POST"])
    def api_run() -> Any:
        data = request.get_json(silent=True) or {}
        required = ["yaml", "mode", "start", "end"]
        missing = [f for f in required if not data.get(f)]
        if missing:
            return jsonify({"status": "error", "error": f"Missing fields: {', '.join(missing)}"}), 400

        all_market = bool(data.get("all_market"))
        codes = data.get("codes") or ""
        if not all_market and not codes.strip():
            return jsonify({"status": "error", "error": "请填写股票代码，或勾选“全部 A 股”"}), 400

        mode = data.get("mode")
        if mode not in ("single", "batch", "shared"):
            return jsonify({"status": "error", "error": f"无效的模式: {mode}"}), 400
        if all_market and mode == "single":
            return jsonify({"status": "error", "error": "单标的模式不支持“全部 A 股”，请填写一个股票代码"}), 400

        executor = data.get("executor", "module")
        profile_override_keys = (
            "commission_rate",
            "min_commission",
            "stamp_tax_sell",
            "transfer_fee_rate",
            "slippage_buy_rate",
            "slippage_sell_rate",
        )
        profile_overrides = {
            key: float(data[key])
            for key in profile_override_keys
            if data.get(key) not in (None, "")
        }

        def _opt_float(field: str) -> float | None:
            value = data.get(field)
            if value in (None, ""):
                return None
            return float(value)

        if executor != "cli" and not try_acquire_run_slot():
            return jsonify({
                "status": "error",
                "error": "已有 2 个回测在运行，请稍后再提交",
            }), 409

        try:
            record = run_backtest(
                yaml_text=data["yaml"],
                mode=mode,
                start=data["start"],
                end=data["end"],
                codes=codes,
                initial_cash=data.get("initial_cash") or None,
                max_positions=data.get("max_positions") or None,
                output_dir=data.get("output_dir") or None,
                db_url=data.get("db_url") or None,
                market_profile=data.get("market_profile") or None,
                executor=executor,
                profile_overrides=profile_overrides or None,
                engine_impl=data.get("engine_impl") or "simulator",
                stop_loss_pct=_opt_float("stop_loss_pct"),
                take_profit_pct=_opt_float("take_profit_pct"),
                trailing_stop_pct=_opt_float("trailing_stop_pct"),
                precheck=bool(data.get("precheck")),
                background=(executor != "cli"),
            )
            return jsonify(record)
        except Exception as exc:
            if executor != "cli":
                release_run_slot()
            return jsonify({"status": "failed", "error": str(exc)}), 500

    @app.route("/api/runs")
    def api_runs() -> Any:
        return jsonify(list_runs())

    @app.route("/api/runs/<run_id>")
    def api_run_detail(run_id: str) -> Any:
        record = get_run(run_id)
        if record is None:
            return jsonify({"error": "not found"}), 404
        return jsonify(record)

    @app.route("/api/runs/<run_id>/strategy")
    def api_run_strategy(run_id: str) -> Any:
        yaml_text = get_run_strategy_yaml(run_id)
        if yaml_text is None:
            return jsonify({"error": "not found"}), 404
        return jsonify({"yaml": yaml_text})

    @app.route("/api/runs/<run_id>/artifact/<path:rel_path>")
    def api_run_artifact(run_id: str, rel_path: str) -> Any:
        artifacts = get_run_artifacts(run_id)
        if rel_path not in artifacts:
            return jsonify({"error": "artifact not found"}), 404
        file_path = Path(artifacts[rel_path])
        if not file_path.exists():
            return jsonify({"error": "artifact file missing"}), 404
        try:
            if file_path.suffix == ".csv":
                import csv
                with open(file_path, "r", encoding="utf-8") as fh:
                    reader = csv.reader(fh)
                    headers = next(reader, [])
                    rows = [row for row in reader]
                return jsonify({"type": "csv", "headers": headers, "rows": rows})
            if file_path.suffix == ".json":
                content = json.loads(file_path.read_text(encoding="utf-8"))
                return jsonify({"type": "json", "data": content})
            return jsonify({"type": "text", "data": file_path.read_text(encoding="utf-8")[:50000]})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/templates", methods=["GET"])
    def api_templates() -> Any:
        return jsonify(list_templates())

    @app.route("/api/templates/<name>", methods=["GET"])
    def api_template_load(name: str) -> Any:
        yaml_text = load_template(name)
        if yaml_text is None:
            return jsonify({"error": "not found"}), 404
        return jsonify({"name": name, "yaml": yaml_text})

    @app.route("/api/templates", methods=["POST"])
    def api_template_save() -> Any:
        data = request.get_json(silent=True) or {}
        name = data.get("name", "").strip()
        yaml_text = data.get("yaml", "")
        if not name:
            return jsonify({"error": "name is required"}), 400
        try:
            save_template(name, yaml_text)
            return jsonify({"saved": name})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    # --- 管理台 MANAGE：策略删除 / 因子补全 / 因子删除 / 维护区 ---

    @app.route("/api/admin/strategies/delete", methods=["POST"])
    def api_admin_strategy_delete() -> Any:
        from quant_research_engine.gui.strategy_admin import delete_strategy

        data = request.get_json(silent=True) or {}
        strategy_id = (data.get("strategy_id") or "").strip()
        if not strategy_id:
            return jsonify({"ok": False, "error": "策略 ID 不能为空"}), 400
        try:
            result = delete_strategy(strategy_id)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, **result})

    @app.route("/api/admin/factor-backfill", methods=["POST"])
    def api_admin_factor_backfill() -> Any:
        from quant_research_engine.gui.daily_jobs import INDICATORS_DIR, UV_BIN, start_script_job
        from quant_research_engine.gui.factor_wizard import parse_factor_table_name

        data = request.get_json(silent=True) or {}
        table = (data.get("table") or "").strip()
        parsed = parse_factor_table_name(table.split(".")[-1])
        if parsed is None:
            return jsonify({"ok": False, "error": f"非法因子表名: {table}"}), 400
        category, _ = parsed
        try:
            record = start_script_job(
                lock_key="indicators",  # 与日更 indicators 管线共用锁
                label=f"因子补全 {table}",
                cmd=[UV_BIN, "run", "python", "run_factor_admin.py", "backfill",
                     "--baseline-ref", "HEAD", "--categories", category,
                     "--max-workers", "4", "--execute"],
                cwd=INDICATORS_DIR,
            )
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        return jsonify({"ok": True, **record})

    @app.route("/api/admin/factor-columns/drop", methods=["POST"])
    def api_admin_factor_columns_drop() -> Any:
        from quant_research_engine.gui.daily_jobs import INDICATORS_DIR, UV_BIN, start_script_job
        from quant_research_engine.gui.factor_wizard import parse_factor_table_name

        data = request.get_json(silent=True) or {}
        table = (data.get("table") or "").strip()
        columns = data.get("columns") or []
        if isinstance(columns, str):
            columns = [columns]
        columns = [str(c).strip() for c in columns if str(c).strip()]
        if parse_factor_table_name(table.split(".")[-1]) is None:
            return jsonify({"ok": False, "error": f"非法因子表名: {table}"}), 400
        if not columns:
            return jsonify({"ok": False, "error": "未指定要删除的列"}), 400
        if any(c in ("ts_code", "trade_date") for c in columns):
            return jsonify({"ok": False, "error": "关键列 ts_code/trade_date 不可删除"}), 400
        try:
            record = start_script_job(
                lock_key="indicators",
                label=f"删除因子列 {table}({', '.join(columns)})",
                cmd=[UV_BIN, "run", "python", "scripts/drop_factor_columns.py",
                     "--table", table.split(".")[-1], "--columns", *columns, "--execute"],
                cwd=INDICATORS_DIR,
            )
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        return jsonify({"ok": True, **record})

    @app.route("/api/admin/maintenance/batches")
    def api_admin_maintenance_batches() -> Any:
        from quant_research_engine.gui.maintenance import list_batches

        return jsonify({"ok": True, **list_batches()})

    @app.route("/api/admin/maintenance/delete", methods=["POST"])
    def api_admin_maintenance_delete() -> Any:
        from quant_research_engine.gui.maintenance import delete_batches

        data = request.get_json(silent=True) or {}
        names = data.get("names") or []
        if not isinstance(names, list) or not names:
            return jsonify({"ok": False, "error": "未选择要删除的批次"}), 400
        result = delete_batches([str(n) for n in names])
        if result["errors"] and not result["deleted"]:
            return jsonify({"ok": False, **result}), 400
        return jsonify({"ok": True, **result})

    # --- 管理台 P3b：日更手动触发 + 接入中心 ---

    @app.route("/api/admin/daily-jobs/<pipeline>", methods=["POST"])
    def api_admin_daily_job_start(pipeline: str) -> Any:
        from quant_research_engine.gui.daily_jobs import start_daily_job

        try:
            record = start_daily_job(pipeline)
        except KeyError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        return jsonify({"ok": True, **record})

    @app.route("/api/admin/daily-jobs/<job_id>")
    def api_admin_daily_job_status(job_id: str) -> Any:
        from quant_research_engine.gui.daily_jobs import get_daily_job

        record = get_daily_job(job_id)
        if record is None:
            return jsonify({"ok": False, "error": "任务不存在"}), 404
        return jsonify({"ok": True, **record})

    @app.route("/api/admin/daily-logs/<pipeline>")
    def api_admin_daily_logs(pipeline: str) -> Any:
        from quant_research_engine.gui.daily_jobs import PIPELINES, journalctl_tail

        spec = PIPELINES.get(pipeline)
        if spec is None:
            return jsonify({"ok": False, "error": f"未知管线: {pipeline}"}), 404
        result = journalctl_tail(spec["unit"])
        return jsonify({"ok": result["source"] != "error", **result})

    @app.route("/api/admin/refresh")
    def api_admin_refresh_overview() -> Any:
        from quant_research_engine.gui.refresh_registry import refresh_overview

        return jsonify({"ok": True, **refresh_overview()})

    @app.route("/api/admin/refresh/register", methods=["POST"])
    def api_admin_refresh_register() -> Any:
        from quant_research_engine.gui.refresh_registry import (
            list_catalog_strategies,
            register_strategy,
        )

        data = request.get_json(silent=True) or {}
        strategy_id = (data.get("strategy_id") or "").strip()
        if not strategy_id:
            return jsonify({"ok": False, "error": "策略 ID 不能为空"}), 400
        if strategy_id not in list_catalog_strategies():
            return jsonify({"ok": False, "error": f"策略不在 catalog 中: {strategy_id}"}), 400
        registry = register_strategy(strategy_id)
        return jsonify({"ok": True, "registered": registry["include"], "stopped": registry["stopped"]})

    @app.route("/api/admin/refresh/unregister", methods=["POST"])
    def api_admin_refresh_unregister() -> Any:
        from quant_research_engine.gui.refresh_registry import unregister_strategy

        data = request.get_json(silent=True) or {}
        strategy_id = (data.get("strategy_id") or "").strip()
        if not strategy_id:
            return jsonify({"ok": False, "error": "策略 ID 不能为空"}), 400
        registry = unregister_strategy(strategy_id)
        return jsonify({"ok": True, "registered": registry["include"], "stopped": registry["stopped"]})

    @app.route("/api/admin/strategies/toggle", methods=["POST"])
    def api_admin_strategy_toggle() -> Any:
        """持续更新开关（只改注册表，不触发任何运行）。"""
        from quant_research_engine.gui.refresh_registry import (
            list_catalog_strategies,
            set_strategy_stopped,
        )

        data = request.get_json(silent=True) or {}
        strategy_id = (data.get("strategy_id") or "").strip()
        stopped = bool(data.get("stopped"))
        if not strategy_id:
            return jsonify({"ok": False, "error": "策略 ID 不能为空"}), 400
        if strategy_id not in list_catalog_strategies():
            return jsonify({"ok": False, "error": f"策略不在 catalog 中: {strategy_id}"}), 400
        registry = set_strategy_stopped(strategy_id, stopped)
        return jsonify({
            "ok": True,
            "stopped": registry["stopped"],
            "message": "已切换，将于下个定时任务生效",
        })

    @app.route("/admin/strategy/<strategy_id>")
    def admin_strategy_detail(strategy_id: str) -> Any:
        from quant_research_engine.gui.refresh_registry import (
            latest_strategy_result,
            list_result_artifacts,
        )
        from quant_research_engine.gui.strategy_admin import strategy_catalog_info

        info = strategy_catalog_info(strategy_id)
        if not info:
            return render_template("error.html", message=f"策略不在 catalog 中: {strategy_id}"), 404
        result = latest_strategy_result(strategy_id)
        artifacts = list_result_artifacts(result["artifact_dir"]) if result else []
        return render_template(
            "strategy_status_detail.html",
            strategy_id=strategy_id,
            info=info,
            result=result,
            artifacts=artifacts,
        )

    @app.route("/api/admin/strategy/<strategy_id>/artifact/<path:rel_path>")
    def api_admin_strategy_artifact(strategy_id: str, rel_path: str) -> Any:
        from flask import send_file

        from quant_research_engine.gui.refresh_registry import (
            DEFAULT_BACKTESTS_DIR,
            latest_strategy_result,
        )

        result = latest_strategy_result(strategy_id)
        if result is None:
            return jsonify({"error": "无结果产物"}), 404
        root = Path(result["artifact_dir"]).resolve()
        backtests_root = DEFAULT_BACKTESTS_DIR.resolve()
        # 白名单：产物根必须位于 backtests 下，目标文件必须在产物根内
        if backtests_root not in root.parents:
            return jsonify({"error": "产物路径越界"}), 400
        target = (root / rel_path).resolve()
        if root not in target.parents or not target.is_file():
            return jsonify({"error": "文件不存在"}), 404
        return send_file(target, as_attachment=True, download_name=target.name)

    # --- 管理台 API（QRE-ADMIN-CONSOLE-P3A-001，只读） ---

    @app.route("/admin")
    def admin_page() -> str:
        return render_template("admin.html")

    @app.route("/api/admin/overview")
    def api_admin_overview() -> Any:
        from quant_research_engine.gui.admin import (
            health_status,
            overview_backtests,
            overview_daily,
            overview_factors,
        )

        db_url = request.args.get("db_url") or None
        try:
            daily = overview_daily(db_url)
            factors = overview_factors(db_url, daily_max=daily.get("watermark"))
        except Exception as exc:
            return jsonify({"ok": False, "error": f"数据库不可用（{exc}）"}), 503
        backtests = overview_backtests()
        health = health_status(
            daily.get("watermark"),
            [t["watermark"] for t in factors["tables"]],
        )
        return jsonify({"ok": True, "daily": daily, "factors": factors, "backtests": backtests, "health": health})

    @app.route("/api/admin/timers")
    def api_admin_timers() -> Any:
        from quant_research_engine.gui.admin import timer_status

        return jsonify({"ok": True, "timers": timer_status()})

    @app.route("/api/admin/factor-status")
    def api_admin_factor_status() -> Any:
        from quant_research_engine.gui.admin import factor_status

        try:
            return jsonify({"ok": True, **factor_status(request.args.get("db_url") or None)})
        except Exception as exc:
            return jsonify({"ok": False, "error": f"因子状态获取失败（{exc}）"}), 503

    # --- 因子向导 API（QRE-GUI-FACTOR-WIZARD-001） ---

    @app.route("/api/factors")
    def api_factors() -> Any:
        from quant_research_engine.gui.factor_wizard import build_factor_groups, load_factor_tables_columns

        try:
            tables_columns = load_factor_tables_columns(db_url=request.args.get("db_url") or None)
        except Exception as exc:
            return jsonify({
                "ok": False,
                "error": f"因子库不可用（{exc}）。请检查数据库连接，或回退使用手写 YAML / 构建器通道。",
            }), 503
        return jsonify({"ok": True, "groups": build_factor_groups(tables_columns)})

    @app.route("/api/factor-admin/indicators")
    def api_factor_admin_indicators() -> Any:
        from quant_research_engine.gui.factor_admin import config_path_for, indicators_repo, read_indicators

        config_path = config_path_for(indicators_repo())
        if not config_path.exists():
            return jsonify({
                "ok": False,
                "error": f"indicators_tushare 配置不存在: {config_path}（可用环境变量 QRE_INDICATORS_REPO 指定路径）",
            }), 503
        try:
            data = read_indicators(config_path)
        except Exception as exc:
            return jsonify({"ok": False, "error": f"读取因子配置失败：{exc}"}), 503
        return jsonify({"ok": True, **data})

    @app.route("/api/factor-admin/request", methods=["POST"])
    def api_factor_admin_request() -> Any:
        from quant_research_engine.gui.factor_admin import parse_periods, start_factor_job

        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        column = (data.get("column") or "").strip()
        if not name or not column:
            return jsonify({"ok": False, "error": "指标名与价格类型必填"}), 400
        try:
            periods = parse_periods(str(data.get("periods", "")))
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        try:
            record = start_factor_job(name=name, column=column, periods=periods)
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        except Exception as exc:
            return jsonify({"ok": False, "error": f"启动因子任务失败：{exc}"}), 500
        return jsonify({"ok": record["status"] != "failed", **record})

    @app.route("/api/factor-admin/jobs/<job_id>")
    def api_factor_admin_job(job_id: str) -> Any:
        from quant_research_engine.gui.factor_admin import get_job

        record = get_job(job_id)
        if record is None:
            return jsonify({"ok": False, "error": "任务不存在"}), 404
        return jsonify({"ok": True, **record})

    @app.route("/api/factor-admin/<job_id>/execute", methods=["POST"])
    def api_factor_admin_execute(job_id: str) -> Any:
        from quant_research_engine.gui.factor_admin import confirm_execute

        try:
            record = confirm_execute(job_id)
        except KeyError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        return jsonify({"ok": True, **record})

    # --- Builder API routes ---

    @app.route("/api/nl_compile", methods=["POST"])
    def api_nl_compile() -> Any:
        from quant_research_engine.gui.nl_compiler import compile_nl

        data = request.get_json(silent=True) or {}
        description = (data.get("description") or "").strip()
        if not description:
            return jsonify({"ok": False, "code": "empty", "error": "请先用自然语言描述策略"}), 400
        result = compile_nl(description, db_url=data.get("db_url") or None)
        if result.get("code") == "not_configured":
            return jsonify(result), 503
        return jsonify(result)

    @app.route("/api/builder/compile", methods=["POST"])
    def api_builder_compile() -> Any:
        data = request.get_json(silent=True) or {}
        result = compile_high_level_entry(data)
        if result.get("ok"):
            return jsonify(result)
        return jsonify(result), 422

    @app.route("/api/builder/indicator-catalog", methods=["GET"])
    def api_builder_indicator_catalog() -> Any:
        from quant_research_engine.strategies.compiler import _INDICATOR_CATALOG

        sources = ["close", "open", "high", "low", "typical", "hlc3", "ohlc4"]
        indicators = {}
        for name, (category, _) in sorted(_INDICATOR_CATALOG.items()):
            indicators[name] = {"category": category, "sources": sources}
        return jsonify({"indicators": indicators, "sources": sources})

    @app.route("/api/builder/validate", methods=["POST"])
    def api_builder_validate() -> Any:
        data = request.get_json(silent=True) or {}
        result = compile_high_level_entry(data)
        if result.get("ok"):
            return jsonify({"valid": True})
        return jsonify({"valid": False, "issues": result.get("issues", [])})

    return app


def launch_gui(*, host: str = "127.0.0.1", port: int = 8080, debug: bool = False) -> None:
    """Launch the local backtest console."""
    app = create_app()
    print(f"* QRE backtest console: http://{host}:{port}")
    print("* Press Ctrl+C to stop the server")
    app.run(host=host, port=port, debug=debug, use_reloader=False)
