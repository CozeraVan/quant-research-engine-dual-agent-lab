"""策略实验台（lab）Flask 应用（QRE-GUI-LAB-PORT-017）。

8081 独立端口应用，面向普通投资者：「新增策略」（NL/快速向导/高级 YAML）
+「回测管理（回测记录）」两个 tab。QRE-SAAS-011（2026-09-07 用户决策，
冻结解除）原位减法：删除「新增因子」tab（缺因子改走申请通道
/api/lab/factor-requests，JSONL 落盘 outputs/factor_requests.jsonl，
TODO(M4) 迁云到 saas factor_requests 表），创建流程后台化（一键回测）。
路由通过 ``strategy_lab_routes.register_strategy_lab_routes`` 与
``register_factor_lab_routes`` 与 8080 主控制台共享。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from quant_research_engine.gui.engine import list_templates
from quant_research_engine.gui.lab_result import register_lab_result_routes
from quant_research_engine.gui.strategy_lab_routes import (
    register_factor_lab_routes,
    register_strategy_lab_routes,
)

# 缺因子申请落盘（JSONL，一行一条；TODO(M4)：上云后迁 saas factor_requests 表）
FACTOR_REQUESTS_PATH = Path("outputs/factor_requests.jsonl")


def create_lab_app() -> Flask:
    from quant_research_engine.gui import app as gui_app

    app = Flask(
        __name__,
        template_folder=str(gui_app.TEMPLATE_DIR),
        static_folder=str(gui_app.STATIC_DIR),
    )
    app.config["SECRET_KEY"] = os.urandom(24)
    app.add_template_filter(gui_app._fmtval, "fmtval")

    @app.after_request
    def lab_no_store(resp):  # type: ignore[no-untyped-def]
        # QRE-LAB-UI-LANDING 缺陷修复：HTML 页面默认无 Cache-Control，浏览器启发式缓存
        # 会让用户拿到编辑/重启窗口期的中间态页面（回测记录空白即此因）。lab 页面禁缓存。
        if resp.content_type.startswith("text/html") or request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.route("/")
    def lab_index() -> str:
        templates = list_templates()
        return render_template(
            "lab.html",
            templates=templates,
            default_strategy_yaml=gui_app._load_default_strategy_yaml(),
            default_strategy_name="ema200_bollinger_reversal_mvp",
        )

    @app.route("/api/lab/factor-requests", methods=["POST"])
    def api_lab_factor_requests():
        """缺因子申请（QRE-SAAS-011）：JSONL 追加落盘，运营离线审核。"""
        data = request.get_json(silent=True) or {}
        factors = data.get("factors")
        if not isinstance(factors, list) or not factors or not all(
            isinstance(f, str) and f.strip() for f in factors
        ):
            return jsonify({"ok": False, "error": "factors 须为非空字符串数组"}), 400
        record = {
            "factors": sorted({f.strip() for f in factors}),
            "strategy_name": str(data.get("strategy_name") or "")[:200],
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        FACTOR_REQUESTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with FACTOR_REQUESTS_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return jsonify({"ok": True})

    # --- 标的范围归类（QRE-SAAS-012，8081 专属；8080 不挂） ---
    from quant_research_engine.gui.admin import _cached
    from quant_research_engine.gui.universe import list_universes, universe_members

    @app.route("/api/lab/universes")
    def api_lab_universes():
        try:
            return jsonify(_cached("lab_universes", lambda: list_universes()))
        except Exception as exc:
            return jsonify({"ok": False, "error": f"归类数据不可用（{exc}）"}), 503

    @app.route("/api/lab/universes/members")
    def api_lab_universe_members():
        group = request.args.get("group", "")
        key = request.args.get("key", "")
        try:
            codes = _cached(f"lab_universe_members:{group}:{key}",
                            lambda: universe_members(group, key))
        except KeyError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404
        except Exception as exc:
            return jsonify({"ok": False, "error": f"归类数据不可用（{exc}）"}), 503
        return jsonify({"ok": True, "codes": codes, "count": len(codes)})

    register_strategy_lab_routes(app)
    # 新增因子（路径 A/B + 任务状态轮询，QRE-GUI-CONSOL-039）
    register_factor_lab_routes(app)
    # 8081 专属：ECharts 回测结果页（/lab/runs/<id>，8080 的 /runs/<id> 不变）
    register_lab_result_routes(app)
    return app


def launch_lab_gui(*, host: str = "127.0.0.1", port: int = 8081, debug: bool = False) -> None:
    """Launch the strategy lab console (port 8081)."""
    app = create_lab_app()
    print(f"* QRE strategy lab console: http://{host}:{port}")
    print("* Press Ctrl+C to stop the server")
    app.run(host=host, port=port, debug=debug, use_reloader=False)
