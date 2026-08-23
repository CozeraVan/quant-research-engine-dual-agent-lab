"""策略实验台（lab）Flask 应用（QRE-GUI-LAB-PORT-017）。

8081 独立端口应用：只含「新增策略」与「回测管理（策略状态）」两个页面，
内容分别从 8080 的 index.html strategy tab 与 admin.html onboard tab 原样移植。
路由通过 ``strategy_lab_routes.register_strategy_lab_routes`` 与 8080 主控制台共享，
不做任何优化/美化/功能增删。
"""

from __future__ import annotations

import os

from flask import Flask, render_template

from quant_research_engine.gui.engine import list_templates
from quant_research_engine.gui.strategy_lab_routes import register_strategy_lab_routes


def create_lab_app() -> Flask:
    from quant_research_engine.gui import app as gui_app

    app = Flask(
        __name__,
        template_folder=str(gui_app.TEMPLATE_DIR),
        static_folder=str(gui_app.STATIC_DIR),
    )
    app.config["SECRET_KEY"] = os.urandom(24)
    app.add_template_filter(gui_app._fmtval, "fmtval")

    @app.route("/")
    def lab_index() -> str:
        templates = list_templates()
        return render_template(
            "lab.html",
            templates=templates,
            default_strategy_yaml=gui_app._load_default_strategy_yaml(),
            default_strategy_name="ema200_bollinger_reversal_mvp",
        )

    register_strategy_lab_routes(app)
    return app


def launch_lab_gui(*, host: str = "127.0.0.1", port: int = 8081, debug: bool = False) -> None:
    """Launch the strategy lab console (port 8081)."""
    app = create_lab_app()
    print(f"* QRE strategy lab console: http://{host}:{port}")
    print("* Press Ctrl+C to stop the server")
    app.run(host=host, port=port, debug=debug, use_reloader=False)
