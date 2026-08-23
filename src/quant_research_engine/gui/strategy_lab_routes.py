"""「新增策略 + 回测管理（策略状态）」共享路由注册（QRE-GUI-LAB-PORT-017）。

这些路由原本是 ``app.create_app()`` 内的闭包；为让 8081 lab 应用
（``gui/lab.py``）与 8080 主控制台复用同一份实现，抽成共享注册函数。
``create_app`` 与 ``create_lab_app`` 都调用本函数，8080 路由行为不变。
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

from quant_research_engine.gui.engine import (
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
    save_template,
    validate_yaml,
)


# 并发闸与回测入口经 gui.app 命名空间在调用时解析：既有测试
# （tests/test_gui_strategy_create.py）的 monkeypatch 打在 gui.app 上，
# 直接绑定 engine 符号会使补丁失效（QRE-GUI-LAB-PORT-017）。
def _try_acquire_run_slot() -> bool:
    from quant_research_engine.gui import app as gui_app

    return gui_app.try_acquire_run_slot()


def _release_run_slot() -> None:
    from quant_research_engine.gui import app as gui_app

    gui_app.release_run_slot()


def _run_backtest(**kwargs: Any) -> Any:
    from quant_research_engine.gui import app as gui_app

    return gui_app.run_backtest(**kwargs)


def register_strategy_lab_routes(app: Flask) -> None:
    """注册「新增策略 / 策略状态 / run 查看」相关页面与 API 路由（两应用共享）。"""

    # --- run 查看页面（新增策略 tab 的冒烟/回测/深度验证链接目标） ---

    @app.route("/runs")
    def runs_page() -> str:
        runs = list_runs()
        return render_template("runs.html", runs=runs)

    @app.route("/runs/<run_id>")
    def run_detail(run_id: str) -> str:
        from quant_research_engine.gui.app import _risk_display, _summary_display_rows

        record = get_run(run_id)
        if record is None:
            return render_template("error.html", message=f"Run {run_id} not found"), 404
        stdout = get_run_stdout(run_id)
        stderr = get_run_stderr(run_id)
        artifacts = get_run_artifacts(run_id)
        summary = extract_run_summary(record)
        equity_svg = equity_curve_svg(record)
        from quant_research_engine.gui import risk_report as rr

        risk_report = rr.load_risk_report(run_id)
        return render_template(
            "run_detail.html",
            run=record,
            stdout=stdout,
            stderr=stderr,
            artifacts=artifacts,
            summary=summary,
            summary_fields=_summary_display_rows(summary),
            equity_svg=equity_svg,
            risk_report=risk_report,
            risk_view=_risk_display(risk_report),
        )

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

        if executor != "cli" and not _try_acquire_run_slot():
            return jsonify({
                "status": "error",
                "error": "已有 2 个回测在运行，请稍后再提交",
            }), 409

        try:
            record = _run_backtest(
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
                _release_run_slot()
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

    # --- 风险分析（FRM 风险模块 R3）---

    @app.route("/api/runs/<run_id>/risk-report", methods=["POST"])
    def api_run_risk_report(run_id: str) -> Any:
        """按需生成风险分析（bootstrap 开），异步 job 复用 daily_jobs 基建。"""
        from quant_research_engine.gui import risk_report as rr

        record = get_run(run_id)
        if record is None:
            return jsonify({"error": "run not found"}), 404
        if record.get("status") != "completed":
            return jsonify({"error": f"run 状态为 {record.get('status')}，仅 completed run 可生成"}), 400
        try:
            job = rr.start_risk_report_job(record)
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 409
        return jsonify({"job_id": job["job_id"], "status": job["status"]})

    @app.route("/api/runs/<run_id>/risk-report/job/<job_id>")
    def api_run_risk_report_job(run_id: str, job_id: str) -> Any:
        from quant_research_engine.gui.daily_jobs import get_daily_job

        job = get_daily_job(job_id)
        if job is None or job.get("pipeline") != f"risk-report:{run_id}":
            return jsonify({"error": "job not found"}), 404
        return jsonify(job)

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

    # --- 管理台 MANAGE：策略删除 ---

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

    # --- 管理台：refresh 状态 / 注册表 / 持续更新开关 / 策略详情 ---

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
            DEFAULT_INCREMENTAL_ROOT,
            latest_strategy_result,
        )

        result = latest_strategy_result(strategy_id)
        if result is None:
            return jsonify({"error": "无结果产物"}), 404
        root = Path(result["artifact_dir"]).resolve()
        # 白名单：产物根必须位于 backtests 或 refresh/incremental 下，目标文件必须在产物根内
        allowed_roots = (DEFAULT_BACKTESTS_DIR.resolve(), DEFAULT_INCREMENTAL_ROOT.resolve())
        if not any(ar in root.parents for ar in allowed_roots):
            return jsonify({"error": "产物路径越界"}), 400
        target = (root / rel_path).resolve()
        if root not in target.parents or not target.is_file():
            return jsonify({"error": "文件不存在"}), 404
        return send_file(target, as_attachment=True, download_name=target.name)

    # --- 因子目录（新增策略 tab 可视化构建第 1 步） ---

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

    # --- NL 编译 ---

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

    # --- 策略创建闭环 API（P1：查重 → 沙箱 → 冒烟 → 用户确认晋升 → catalog） ---

    @app.route("/api/strategies/create", methods=["POST"])
    def api_strategy_create() -> Any:
        from quant_research_engine.gui import strategy_create
        from quant_research_engine.gui.nl_compiler import (
            _default_column_lookup,
            _enqueue_missing_factors,
            compile_nl,
        )
        from quant_research_engine.strategies.factor_request_queue import (
            DEFAULT_QUEUE_PATH,
            find_missing_factor_columns,
        )
        from quant_research_engine.strategies.spec import StrategySpec

        data = request.get_json(silent=True) or {}
        mode = data.get("mode", "manual")
        warnings: list[str] = []

        if mode == "nl":
            description = (data.get("description") or "").strip()
            if not description:
                return jsonify({"ok": False, "code": "empty", "error": "请先用自然语言描述策略"}), 400
            compiled = compile_nl(description, db_url=data.get("db_url") or None)
            if not compiled.get("ok"):
                status = 503 if compiled.get("code") == "not_configured" else 200
                return jsonify(compiled), status
            yaml_text = compiled["yaml"]
            warnings.extend(compiled.get("warnings") or [])
        else:
            yaml_text = data.get("yaml_text") or data.get("yaml") or ""
            validation = validate_yaml(yaml_text)
            if not validation["valid"]:
                return jsonify({"ok": False, "code": "invalid_yaml", "error": validation["error"]}), 400
            # 因子存在性检查（DB 不可用时降级为 warning，与 NL 通道一致）
            lookup = _default_column_lookup(data.get("db_url") or None)
            if lookup is None:
                warnings.append("因子库不可用，跳过因子存在性检查（提交回测时仍会校验）")
            else:
                import yaml as _yaml

                spec = StrategySpec.from_mapping(_yaml.safe_load(yaml_text))
                missing = find_missing_factor_columns(spec, lookup)
                if missing:
                    _enqueue_missing_factors(spec, missing, queue_path=DEFAULT_QUEUE_PATH)
                    names = "、".join(f"{f.logical_name}({f.qualified_table}.{f.source_column})" for f in missing)
                    return jsonify({
                        "ok": False,
                        "code": "missing_factors",
                        "error": f"该策略未入沙箱：缺因子 {names}，已加入补因子队列通知 indicators_tushare 项目。",
                        "missing_factors": [f.logical_name for f in missing],
                    })

        saved = strategy_create.save_to_sandbox(yaml_text)
        if not saved["ok"]:
            status = 409 if saved.get("code") == "duplicate_name" else 400
            return jsonify(saved), status
        return jsonify({"ok": True, "name": saved["name"], "yaml": yaml_text, "warnings": warnings})

    @app.route("/api/strategies/sandbox")
    def api_strategy_sandbox() -> Any:
        from quant_research_engine.gui import strategy_create

        return jsonify({
            "ok": True,
            "strategies": strategy_create.list_sandbox(),
            "categories": list(strategy_create.CATALOG_CATEGORIES),
        })

    @app.route("/api/strategies/smoke", methods=["POST"])
    def api_strategy_smoke() -> Any:
        from quant_research_engine.gui import strategy_create

        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"ok": False, "error": "策略名不能为空"}), 400
        yaml_text = strategy_create.load_sandbox_yaml(name)
        if yaml_text is None:
            return jsonify({"ok": False, "error": f"沙箱中不存在策略: {name}"}), 404

        code = (data.get("code") or strategy_create.SMOKE_DEFAULT_CODE).strip()
        end = date.today()
        start = end - timedelta(days=strategy_create.SMOKE_WINDOW_DAYS)
        if not _try_acquire_run_slot():
            return jsonify({"ok": False, "error": "已有 2 个回测在运行，请稍后再提交"}), 409
        try:
            record = _run_backtest(
                yaml_text=yaml_text,
                mode="single",
                start=start.isoformat(),
                end=end.isoformat(),
                codes=code,
                background=True,
                # 标记在线程启动前合并进 run 记录；run 终态由 engine 回写 sidecar
                mark={"sandbox_strategy": name, "purpose": "smoke"},
            )
        except Exception as exc:
            _release_run_slot()
            return jsonify({"ok": False, "error": str(exc)}), 500
        strategy_create.record_smoke(name, record["run_id"], status="running")
        return jsonify({"ok": True, "run_id": record["run_id"], "code": code,
                        "start": start.isoformat(), "end": end.isoformat()})

    @app.route("/api/strategies/promote", methods=["POST"])
    def api_strategy_promote() -> Any:
        from quant_research_engine.gui import strategy_create

        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        category = (data.get("category") or "").strip()
        force = bool(data.get("force"))
        if not name:
            return jsonify({"ok": False, "error": "策略名不能为空"}), 400

        result = strategy_create.promote(name, category, force=force)
        if not result["ok"]:
            status = 404 if result.get("code") == "not_found" else (409 if result.get("code") == "smoke_not_passed" else 400)
            return jsonify(result), status

        # 晋升后立刻触发一次全量后台回测（shared 全市场、近 2 年窗口，
        # 与 refresh 默认 window-years=2 对齐；refresh 本身是独立 CLI 管线）。
        run_id = None
        warning = None
        if _try_acquire_run_slot():
            try:
                yaml_text = Path(result["path"]).read_text(encoding="utf-8")
                end = date.today()
                start = end - timedelta(days=730)
                record = _run_backtest(
                    yaml_text=yaml_text,
                    mode="shared",
                    start=start.isoformat(),
                    end=end.isoformat(),
                    codes="",  # 空 = 全市场
                    background=True,
                    # 晋升闸标记：run 收尾时由 engine 钩子评估并回写 gate 文件
                    mark={
                        "promotion_gate": True,
                        "promoted_strategy": result["name"],
                        "purpose": "promote_full",
                        "promotion_forced": bool(result.get("forced")),
                    },
                )
                run_id = record["run_id"]
            except Exception as exc:
                _release_run_slot()
                warning = f"已晋升，但全量回测启动失败：{exc}"
        else:
            warning = "已晋升；当前回测并发已满，全量回测未启动（将随下次 refresh 日更运行）"

        resp: dict[str, Any] = {"ok": True, "path": result["path"], "run_id": run_id}
        if result.get("forced"):
            resp["forced"] = True
            resp["warning"] = (warning + "；" if warning else "") + "已使用 force=true 跳过冒烟校验（管理员通道）"
            resp["gate_note"] = "force 晋升：全量回测闸仍会评估并展示，结果不阻止日更（强制在库）"
        elif warning:
            resp["warning"] = warning
        return jsonify(resp)

    @app.route("/api/strategies/<name>/deep-validate", methods=["POST"])
    def api_strategy_deep_validate(name: str) -> Any:
        """深度验证：策略 YAML → 逐日信号池 → cluster-ashare 四关验证（异步）。

        链路：定位策略 YAML（沙箱优先，其次 catalog）→ StrategySpec 解析 →
        因子存在性检查（缺失入补因子队列）→ deep_validate.start_deep_validate_job
        （复用 daily_jobs 基建，lock_key=deep-validate:<name> 同名串行）。
        立即返回 job_id，前端轮询 GET .../deep-validate/<job_id>。
        """
        from quant_research_engine.gui import deep_validate
        from quant_research_engine.gui.nl_compiler import (
            _default_column_lookup,
            _enqueue_missing_factors,
        )
        from quant_research_engine.strategies.factor_request_queue import (
            DEFAULT_QUEUE_PATH,
            find_missing_factor_columns,
        )
        from quant_research_engine.strategies.spec import StrategySpec

        data = request.get_json(silent=True) or {}
        name = name.strip()
        yaml_text = deep_validate.locate_strategy_yaml(name)
        if yaml_text is None:
            return jsonify({"ok": False, "code": "not_found",
                            "error": f"沙箱与 catalog 中均不存在策略: {name}"}), 404
        try:
            import yaml as _yaml

            spec = StrategySpec.from_mapping(_yaml.safe_load(yaml_text))
        except Exception as exc:
            return jsonify({"ok": False, "code": "invalid_yaml",
                            "error": f"策略 YAML 解析失败: {exc}"}), 400
        if not (spec.signal_expression or "").strip():
            return jsonify({"ok": False, "code": "no_entry_signal",
                            "error": f"策略 {name} 无入场表达式（signal.entry），"
                                     "无法生成信号池"}), 400

        env_error = deep_validate.cluster_available()
        if env_error:
            return jsonify({"ok": False, "code": "cluster_unavailable",
                            "error": f"cluster-ashare 环境不可用：{env_error}"}), 500

        warnings: list[str] = []
        lookup = _default_column_lookup(data.get("db_url") or None)
        if lookup is None:
            warnings.append("因子库不可用，跳过因子存在性检查（信号池生成时缺列会失败）")
        else:
            missing = find_missing_factor_columns(spec, lookup)
            if missing:
                _enqueue_missing_factors(spec, missing, queue_path=DEFAULT_QUEUE_PATH)
                names = "、".join(
                    f"{f.logical_name}({f.qualified_table}.{f.source_column})"
                    for f in missing)
                return jsonify({
                    "ok": False,
                    "code": "missing_factors",
                    "error": f"缺因子 {names}，已加入补因子队列通知 indicators_tushare 项目。",
                    "missing_factors": [f.logical_name for f in missing],
                }), 400

        try:
            record = deep_validate.start_deep_validate_job(
                name, spec,
                d0=(data.get("d0") or "").strip() or None,
                d1=(data.get("d1") or "").strip() or None,
            )
        except ValueError as exc:
            return jsonify({"ok": False, "code": "invalid_params",
                            "error": str(exc)}), 400
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        if warnings:
            record["warnings"] = warnings
        return jsonify(record)

    @app.route("/api/strategies/<name>/deep-validate/<job_id>")
    def api_strategy_deep_validate_status(name: str, job_id: str) -> Any:
        from quant_research_engine.gui.daily_jobs import DAILY_JOBS_DIR, get_daily_job

        record = get_daily_job(job_id)
        if record is None:
            return jsonify({"ok": False, "error": "任务不存在"}), 404
        resp: dict[str, Any] = {"ok": True, "job_id": job_id,
                                "status": record["status"]}
        if record["status"] == "running":
            return jsonify(resp)
        result: dict[str, Any] | None = None
        result_path = DAILY_JOBS_DIR / job_id / "result.json"
        if result_path.exists():
            try:
                parsed = json.loads(result_path.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    result = parsed
            except (json.JSONDecodeError, OSError):
                result = None
        resp["result"] = result or {
            "ok": False,
            "error": record.get("error") or "深度验证失败（无结果文件）",
        }
        return jsonify(resp)

    @app.route("/api/strategies/sandbox/delete", methods=["POST"])
    def api_strategy_sandbox_delete() -> Any:
        from quant_research_engine.gui import strategy_create

        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"ok": False, "error": "策略名不能为空"}), 400
        result = strategy_create.discard(name)
        if not result["ok"]:
            return jsonify(result), 404
        return jsonify(result)
