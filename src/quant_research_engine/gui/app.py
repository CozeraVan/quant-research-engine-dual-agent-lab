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

    @app.route("/api/admin/query/daily")
    def api_admin_query_daily() -> Any:
        from quant_research_engine.gui.admin import query_daily, rows_to_csv

        try:
            result = query_daily(
                ts_code=request.args.get("ts_code", ""),
                start=request.args.get("start", ""),
                end=request.args.get("end", ""),
                limit=request.args.get("limit", 200),
                offset=request.args.get("offset", 0),
                db_url=request.args.get("db_url") or None,
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": f"查询失败（{exc}）"}), 503
        if request.args.get("format") == "csv":
            from flask import Response

            return Response(
                rows_to_csv(result["rows"]),
                mimetype="text/csv",
                headers={"Content-Disposition": "attachment; filename=daily_query.csv"},
            )
        return jsonify({"ok": True, **result})

    @app.route("/api/admin/query/factor")
    def api_admin_query_factor() -> Any:
        from quant_research_engine.gui.admin import query_factor, rows_to_csv

        try:
            result = query_factor(
                table=request.args.get("table", ""),
                column=request.args.get("column", ""),
                ts_code=request.args.get("ts_code", ""),
                start=request.args.get("start", ""),
                end=request.args.get("end", ""),
                limit=request.args.get("limit", 200),
                offset=request.args.get("offset", 0),
                db_url=request.args.get("db_url") or None,
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": f"查询失败（{exc}）"}), 503
        if request.args.get("format") == "csv":
            from flask import Response

            return Response(
                rows_to_csv(result["rows"]),
                mimetype="text/csv",
                headers={"Content-Disposition": "attachment; filename=factor_query.csv"},
            )
        return jsonify({"ok": True, **result})

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
