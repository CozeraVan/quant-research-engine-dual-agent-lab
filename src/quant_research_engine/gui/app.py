from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_from_directory

from quant_research_engine.gui.engine import (
    compare_run_summaries,
    compile_high_level_entry,
    get_run,
)

# 兼容锚点：既有测试（tests/test_gui_strategy_create.py）将 monkeypatch 打在
# gui.app 命名空间的这三个符号上；共享路由模块 strategy_lab_routes 在调用时经
# 本模块解析它们，故此处保持 re-export（QRE-GUI-LAB-PORT-017）。
from quant_research_engine.gui.engine import (  # noqa: F401
    release_run_slot,
    run_backtest,
    try_acquire_run_slot,
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


def _risk_display(report: dict[str, Any] | None) -> dict[str, Any] | None:
    """把 risk_report.json 整理成模板卡片视图（None → 模板显示「未生成」）。"""
    if not isinstance(report, dict):
        return None

    def _pct(value: Any) -> str:
        if value is None or isinstance(value, bool):
            return "—"
        try:
            return f"{float(value) * 100:.2f}%"
        except (TypeError, ValueError):
            return str(value)

    def _f2(value: Any) -> str:
        if value is None or isinstance(value, bool):
            return "—"
        try:
            return f"{float(value):.2f}"
        except (TypeError, ValueError):
            return str(value)

    def _p4(value: Any) -> str:
        try:
            return f"{float(value):.4f}"
        except (TypeError, ValueError):
            return "—"

    method_labels = {
        "parametric_normal": "参数正态",
        "historical_simulation": "历史模拟",
        "ewma_parametric": "EWMA 参数",
    }
    view: dict[str, Any] = {"meta": report.get("meta", {})}

    dist = report.get("distribution", {})
    if isinstance(dist, dict) and "error" not in dist:
        view["distribution"] = {
            "jb_statistic": _f2(dist.get("jb_statistic")),
            "jb_p_value": _p4(dist.get("jb_p_value")),
            "reject_normal": bool(dist.get("reject_normal_5pct")),
            "skew": _f2(dist.get("skew_sample")),
            "excess_kurtosis": _f2(dist.get("excess_kurtosis_sample")),
        }

    tail_rows: list[dict[str, str]] = []
    for level_key, methods in (report.get("tail") or {}).items():
        for method_key, entry in (methods or {}).items():
            if not isinstance(entry, dict) or "error" in entry:
                continue
            tail_rows.append({
                "level": level_key.replace("pct", "%"),
                "method": method_labels.get(method_key, method_key),
                "var": _pct(entry.get("var")),
                "es": _pct(entry.get("es")),
            })
    view["tail_rows"] = tail_rows

    bt_rows: list[dict[str, str]] = []
    var_bt = report.get("var_backtest") or {}
    if var_bt.get("enabled"):
        for level_key, entry in (var_bt.get("levels") or {}).items():
            if not isinstance(entry, dict) or "error" in entry:
                continue
            bt_rows.append({
                "level": level_key.replace("pct", "%"),
                "violations": f"{entry.get('violations')}/{_f2(entry.get('expected_violations'))}",
                "violation_rate": _pct(entry.get("violation_rate")),
                "coverage_p": _p4((entry.get("coverage") or {}).get("p_value")),
                "independence_p": _p4((entry.get("independence") or {}).get("p_value")),
                "conclusion": str(entry.get("conclusion", "—")),
            })
    view["var_backtest_rows"] = bt_rows

    vol = report.get("volatility") or {}
    ewma = vol.get("ewma_latest") or {}
    garch = vol.get("garch11") or {}
    regime = vol.get("regime") or {}
    ann = (report.get("meta") or {}).get("annualization_factor", 252)
    daily_vol = ewma.get("volatility_forecast")
    view["volatility"] = {
        "ewma_daily": _pct(daily_vol),
        "ewma_annual": _pct(daily_vol * ann**0.5 if isinstance(daily_vol, (int, float)) else None),
        "garch_persistence": _f2(garch.get("persistence")),
        "garch_long_run": _pct(garch.get("long_run_volatility")),
        "garch_error": garch.get("error"),
        "regime": regime.get("latest") if isinstance(regime, dict) and "error" not in regime else None,
    }

    stress_rows: list[dict[str, str]] = []
    stress_section = report.get("stress") or {}
    for name, entry in (stress_section.get("scenarios") or {}).items():
        if not isinstance(entry, dict):
            continue
        if "error" in entry:
            stress_rows.append({"name": name, "note": "样本不覆盖该窗口"})
            continue
        window = entry.get("window") or {}
        stress_rows.append({
            "name": name,
            "window": f"{window.get('start', '?')}~{window.get('end', '?')}",
            "n_days": str(entry.get("n_days", "—")),
            "cum_loss": _pct(entry.get("strategy_cumulative_loss")),
            "peak_trough": _pct(entry.get("strategy_peak_trough_drawdown")),
            "peak_to_var": _f2(entry.get("peak_to_var")),
            "note": "",
        })
    view["stress_rows"] = stress_rows

    perf = report.get("performance") or {}
    if isinstance(perf, dict) and "error" not in perf:
        view["performance"] = {
            "sharpe": _f2((perf.get("sharpe") or {}).get("sharpe")),
            "sortino": _f2((perf.get("sortino") or {}).get("sortino")),
            "beta": _f2(perf.get("beta")),
            "treynor": _f2((perf.get("treynor") or {}).get("treynor") if perf.get("treynor") else None),
            "information_ratio": _f2((perf.get("information_ratio") or {}).get("information_ratio") if perf.get("information_ratio") else None),
        }

    # R7 组合与衍生品风险（可选节；老 run 无此节 → 不渲染卡片）
    portfolio = report.get("portfolio")
    if isinstance(portfolio, dict) and "error" not in portfolio:
        card: dict[str, Any] = {}
        fi = portfolio.get("fixed_income")
        if isinstance(fi, dict) and "error" not in fi:
            card["fixed_income"] = {
                "n_positions": fi.get("n_positions"),
                "total_market_value": _f2(fi.get("total_market_value")),
                "dv01": _f2(fi.get("dv01")),
                "duration": _f2(fi.get("duration")),
                "convexity": _f2(fi.get("convexity")),
            }
            kr01 = fi.get("kr01")
            if isinstance(kr01, dict):
                card["kr01_rows"] = [
                    {"tenor": _f2(k), "kr01": _f2(v)}
                    for k, v in zip(kr01.get("key_tenors") or [], kr01.get("kr01") or [])
                ]
                card["kr01_sum"] = _f2(kr01.get("kr01_sum"))
        opts = portfolio.get("options")
        if isinstance(opts, dict) and "error" not in opts:
            card["options"] = {
                "n_positions": opts.get("n_positions"),
                "delta": _f2(opts.get("delta")),
                "gamma": _f2(opts.get("gamma")),
                "vega": _f2(opts.get("vega")),
                "theta": _f2(opts.get("theta")),
                "rho": _f2(opts.get("rho")),
            }
        dgv = portfolio.get("dgv_var")
        if isinstance(dgv, dict) and "error" not in dgv:
            card["dgv_var"] = {
                "method": dgv.get("method"),
                "confidence": _pct(dgv.get("confidence")),
                "var": _f2(dgv.get("var")),
            }
        if card:
            view["portfolio"] = card
    return view


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
        # QRE-GUI-CONSOL-039：写策略/写因子已迁移到 8081 回测台，首页为引导页
        return render_template("index.html")

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
    # 「新增策略 / 策略状态 / run 查看」相关路由已抽至共享注册函数
    # register_strategy_lab_routes（QRE-GUI-LAB-PORT-017，见 gui/strategy_lab_routes.py），
    # 由本函数尾部统一注册，8080 行为不变。


    # --- 管理台 MANAGE：因子补全 / 因子删除 / 维护区 ---

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

    @app.route("/api/admin/daily-logs/<pipeline>")
    def api_admin_daily_logs(pipeline: str) -> Any:
        from quant_research_engine.gui.daily_jobs import PIPELINES, journalctl_tail

        spec = PIPELINES.get(pipeline)
        if spec is None:
            return jsonify({"ok": False, "error": f"未知管线: {pipeline}"}), 404
        result = journalctl_tail(spec["unit"])
        return jsonify({"ok": result["source"] != "error", **result})


    # --- 管理台「大盘风险」风向标（QRE-RISK-BAROMETER-M3-010，只读 market_risk.daily） ---

    @app.route("/api/admin/market-risk")
    def api_admin_market_risk() -> Any:
        from quant_research_engine.gui.market_risk import market_risk_overview

        return jsonify(market_risk_overview(request.args.get("db_url") or None))

    # --- 管理台「聚类动量因子研究」（QRE-GUI-POOL-MOM-031，只读 cluster.pool_momentum_daily） ---

    @app.route("/api/admin/pool-momentum")
    def api_admin_pool_momentum() -> Any:
        from quant_research_engine.gui.pool_momentum import pool_momentum_overview

        return jsonify(
            pool_momentum_overview(
                request.args.get("db_url") or None,
                request.args.get("trade_date") or None,
            )
        )

    @app.route("/api/admin/pool-momentum/detail")
    def api_admin_pool_momentum_detail() -> Any:
        from quant_research_engine.gui.pool_momentum import pool_momentum_detail

        return jsonify(
            pool_momentum_detail(
                request.args.get("pool_type", ""),
                request.args.get("pool_key", ""),
                request.args.get("db_url") or None,
                request.args.get("end_date") or None,
            )
        )

    @app.route("/api/admin/pool-momentum/members")
    def api_admin_pool_momentum_members() -> Any:
        from quant_research_engine.gui.pool_momentum import pool_momentum_members

        return jsonify(
            pool_momentum_members(
                request.args.get("pool_type", ""),
                request.args.get("pool_key", ""),
                request.args.get("trade_date") or None,
                request.args.get("db_url") or None,
            )
        )

    # --- 管理台「聚类分析」（QRE-ADMIN-CLUSTER-001，只读展示 cluster-ashare 产出） ---

    @app.route("/api/admin/cluster")
    def api_admin_cluster() -> Any:
        from quant_research_engine.gui.cluster_admin import cluster_overview

        return jsonify(cluster_overview(request.args.get("db_url") or None))

    @app.route("/api/admin/cluster/artifact/<path:rel_path>")
    def api_admin_cluster_artifact(rel_path: str) -> Any:
        from flask import send_file

        from quant_research_engine.gui.cluster_admin import resolve_artifact

        target = resolve_artifact(rel_path)
        if target is None:
            return jsonify({"error": "文件不存在或不在白名单内"}), 404
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
            overview_concept_tags,
            overview_daily,
            overview_derivatives,
            overview_factors,
            overview_minute,
            pending_trade_days,
        )

        db_url = request.args.get("db_url") or None
        try:
            daily = overview_daily(db_url)
            factors = overview_factors(db_url, daily_max=daily.get("watermark"))
        except Exception as exc:
            return jsonify({"ok": False, "error": f"数据库不可用（{exc}）"}), 503
        backtests = overview_backtests()
        derivatives = overview_derivatives(db_url)  # 内部自降级，不拖垮总览
        concept_tags = overview_concept_tags(db_url)  # 内部自降级，不拖垮总览
        minute = overview_minute(db_url)  # 内部自降级，不拖垮总览
        health = health_status(
            daily.get("watermark"),
            # 未接日更的 panel 面板表不参与健康灯（避免误报红色故障）
            [t["watermark"] for t in factors["tables"] if t.get("daily_pipeline", True)],
            pending_trade_days=pending_trade_days(daily.get("watermark"), db_url),
        )
        return jsonify({"ok": True, "daily": daily, "factors": factors, "backtests": backtests, "health": health, "derivatives": derivatives, "concept_tags": concept_tags, "minute": minute})

    @app.route("/api/admin/pg-status")
    def api_admin_pg_status() -> Any:
        from quant_research_engine.gui.admin import pg_status

        return jsonify({"ok": True, **pg_status(request.args.get("db_url") or None)})

    @app.route("/api/admin/pg-control", methods=["POST"])
    def api_admin_pg_control() -> Any:
        from quant_research_engine.gui.admin import pg_control

        data = request.get_json(silent=True) or {}
        action = str(data.get("action") or "")
        try:
            result = pg_control(action)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(result), (200 if result.get("ok") else 502)

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

    # --- Builder API routes ---


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

    # --- 共享路由：新增策略 / 策略状态 / run 查看（QRE-GUI-LAB-PORT-017） ---
    # --- 共享路由：新增因子（路径 A/B + 任务状态轮询，QRE-GUI-CONSOL-039） ---
    from quant_research_engine.gui.strategy_lab_routes import (
        register_factor_lab_routes,
        register_strategy_lab_routes,
    )

    register_strategy_lab_routes(app)
    register_factor_lab_routes(app)

    return app


def launch_gui(*, host: str = "127.0.0.1", port: int = 8080, debug: bool = False) -> None:
    """Launch the local backtest console."""
    app = create_app()
    print(f"* QRE backtest console: http://{host}:{port}")
    print("* Press Ctrl+C to stop the server")
    app.run(host=host, port=port, debug=debug, use_reloader=False)
