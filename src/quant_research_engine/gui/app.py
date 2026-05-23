from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_from_directory

from quant_research_engine.gui.engine import (
    compile_high_level_entry,
    get_run,
    get_run_artifacts,
    get_run_stderr,
    get_run_stdout,
    get_run_strategy_yaml,
    list_runs,
    list_templates,
    load_template,
    run_backtest,
    save_template,
    validate_yaml,
)

GUI_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = GUI_DIR / "templates"
STATIC_DIR = GUI_DIR / "static"
DEFAULT_STRATEGY_TEMPLATE = Path(__file__).resolve().parents[3] / "examples" / "ema200_bollinger_reversal.yaml"


def _load_default_strategy_yaml() -> str:
    if DEFAULT_STRATEGY_TEMPLATE.exists():
        return DEFAULT_STRATEGY_TEMPLATE.read_text(encoding="utf-8")
    return (
        "experiment:\n"
        "  name: ema200_bollinger_reversal_mvp\n"
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
        "    ema200: factors.stock_daily_overlap_typical_price.ema_200\n"
        "    bb_upper: factors.stock_daily_volatility_close.bbu_20_2_0_2_0\n"
        "    bb_lower: factors.stock_daily_volatility_close.bbl_20_2_0_2_0\n"
        "signal:\n"
        "  entry: close > ema200 and close <= bb_lower\n"
        "  exit: close >= bb_upper\n"
        "evaluation:\n"
        "  forward_return_horizons: [1, 3, 5, 10, 20]\n"
        "holding:\n"
        "  max_holding_days: 9999\n"
    )


def create_app() -> Flask:
    app = Flask(__name__, template_folder=str(TEMPLATE_DIR), static_folder=str(STATIC_DIR))
    app.config["SECRET_KEY"] = os.urandom(24)

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
        return render_template(
            "run_detail.html",
            run=record,
            stdout=stdout,
            stderr=stderr,
            artifacts=artifacts,
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
        required = ["yaml", "mode", "start", "end", "codes"]
        missing = [f for f in required if not data.get(f)]
        if missing:
            return jsonify({"status": "error", "error": f"Missing fields: {', '.join(missing)}"}), 400

        try:
            record = run_backtest(
                yaml_text=data["yaml"],
                mode=data["mode"],
                start=data["start"],
                end=data["end"],
                codes=data["codes"],
                initial_cash=data.get("initial_cash") or None,
                max_positions=data.get("max_positions") or None,
                output_dir=data.get("output_dir") or None,
                db_url=data.get("db_url") or None,
                market_profile=data.get("market_profile") or None,
                executor=data.get("executor", "module"),
            )
            return jsonify(record)
        except Exception as exc:
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

    return app


def launch_gui(*, host: str = "127.0.0.1", port: int = 8080, debug: bool = False) -> None:
    """Launch the local backtest console."""
    app = create_app()
    print(f"* QRE backtest console: http://{host}:{port}")
    print("* Press Ctrl+C to stop the server")
    app.run(host=host, port=port, debug=debug, use_reloader=False)
