"""《我不是股神》WSL 本地 API；匿名响应不含真实代码、日期或未来行情。"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from flask import Flask, jsonify, render_template, request

from quant_research_engine.game.engine import GameRuleError
from quant_research_engine.game.factors import GROUP_LABELS, GROUP_ORDER, factor_catalog
from quant_research_engine.game.session import GameSession

OWNER_COOKIE = "qre_game_owner"


@dataclass
class GameSessionRegistry:
    provider: object
    sessions: dict[str, GameSession] | None = None

    def __post_init__(self) -> None:
        if self.sessions is None:
            self.sessions = {}

    def create(self) -> GameSession:
        game = self.provider.create_session()
        game_id = secrets.token_urlsafe(24)
        while game_id in self.sessions:
            game_id = secrets.token_urlsafe(24)
        game.web_id = game_id
        game.owner_id = secrets.token_urlsafe(24)
        self.sessions[game_id] = game
        return game

    def get(self, game_id: str, owner_id: str) -> GameSession | None:
        game = self.sessions.get(game_id)
        if game is None or game.owner_id != owner_id:
            return None
        return game


def _state(game: GameSession) -> dict:
    return {
        "id": game.web_id,
        "display_name": game.display_name,
        "display_code": game.display_code,
        "phase": game.phase,
        "cursor": game.cursor - game.start_index + 1,
        "warmup_bars": game.warmup_bars,
        "game_bars": game.game_bars,
        "finished": game.finished,
        "should_end": game.engine.should_end,
        "history": game.public_history(),
        "account": {
            "cash": game.engine.cash,
            "quantity": game.quantity,
            "sellable": game.sellable,
            "equity": game.equity,
            "total_cost": game.total_cost,
            "cost_breakdown": game.cost_breakdown,
        },
        "pending_order": None if game.pending_order is None else {
            "side": game.pending_order.side.value,
            "price": game.pending_order.price,
            "quantity": game.pending_order.quantity,
        },
        "decision": game.decision_state(),
        "settlement": game.settlement,
        "selected": list(game.selected_canonicals),
        "loaded": sorted(game.loaded_canonicals),
        "price_anchor": getattr(game, "price_anchor", None),
        "factor_audit": getattr(game, "factor_audit", None),
        "factor_errors": dict(getattr(game, "factor_errors", {}) or {}),
        "trades": [
            {"side": fill.side.value, "price": fill.price,
             "quantity": fill.quantity, "cost": fill.cost}
            for fill in game.trades
        ],
    }


def create_game_app(provider: object, *, testing: bool = False) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="../gui/static",
                static_url_path="/static")
    app.config.update(TESTING=testing, SECRET_KEY=secrets.token_hex(32))
    registry = GameSessionRegistry(provider)

    @app.get("/game")
    def game_page():
        return render_template("game.html")

    @app.get("/game/api/factors")
    def factor_library():
        catalog = factor_catalog()
        groups = []
        for key in GROUP_ORDER:
            items = [item for item in catalog if item["group"] == key]
            if items:
                groups.append({"key": key, "label": GROUP_LABELS[key], "factors": items})
        return jsonify({"ok": True, "groups": groups, "total": len(catalog)})

    @app.post("/game/api/sessions")
    def create_session():
        try:
            game = registry.create()
        except GameRuleError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        owner = request.cookies.get(OWNER_COOKIE) or game.owner_id
        game.owner_id = owner
        response = jsonify(_state(game))
        response.set_cookie(OWNER_COOKIE, owner, max_age=60 * 60 * 24 * 365,
                            httponly=True, samesite="Lax")
        return response

    def authorized(game_id: str) -> GameSession | None:
        return registry.get(game_id, request.cookies.get(OWNER_COOKIE, ""))

    def require_game(game_id: str):
        game = authorized(game_id)
        if game is None:
            return None, (jsonify({"ok": False, "error": "游戏不存在或无权访问"}), 401)
        return game, None

    @app.get("/game/api/sessions/<game_id>")
    def get_session(game_id: str):
        game, error = require_game(game_id)
        return error or jsonify(_state(game))

    @app.post("/game/api/sessions/<game_id>/advance")
    def advance(game_id: str):
        game, error = require_game(game_id)
        if error:
            return error
        try:
            game.advance()
        except GameRuleError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        return jsonify(_state(game))

    @app.post("/game/api/sessions/<game_id>/orders")
    def place_order(game_id: str):
        game, error = require_game(game_id)
        if error:
            return error
        data = request.get_json(silent=True) or {}
        try:
            side_value = str(data.get("side") or "").lower()
            from quant_research_engine.core.models import OrderSide
            side = OrderSide.BUY if side_value == "buy" else OrderSide.SELL if side_value == "sell" else None
            if side is None:
                return jsonify({"ok": False, "error": "side 必须为 buy 或 sell"}), 400
            game.place_order(side, float(data.get("price")), int(data.get("quantity")))
        except (GameRuleError, TypeError, ValueError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(_state(game))

    @app.post("/game/api/sessions/<game_id>/cancel")
    def cancel_order(game_id: str):
        game, error = require_game(game_id)
        if error:
            return error
        try:
            game.cancel_order()
        except GameRuleError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        return jsonify(_state(game))

    @app.post("/game/api/sessions/<game_id>/close")
    def close_day(game_id: str):
        game, error = require_game(game_id)
        if error:
            return error
        if game.phase == "closed":
            return jsonify(_state(game))
        try:
            game.close_day()
        except GameRuleError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        return jsonify(_state(game))

    @app.get("/game/api/sessions/<game_id>/factors")
    def get_selected_factors(game_id: str):
        game, error = require_game(game_id)
        return error or jsonify({
            "ok": True,
            "selected": list(game.selected_canonicals),
            "loaded": sorted(game.loaded_canonicals),
        })

    @app.post("/game/api/sessions/<game_id>/factors")
    def set_selected_factors(game_id: str):
        game, error = require_game(game_id)
        if error:
            return error
        data = request.get_json(silent=True) or {}
        canonicals = data.get("canonicals")
        if not isinstance(canonicals, list):
            return jsonify({"ok": False, "error": "canonicals 必须为数组"}), 400
        try:
            registry.provider.load_selected(game, canonicals)
        except GameRuleError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(_state(game))

    @app.get("/game/api/sessions/<game_id>/result")
    def result(game_id: str):
        game, error = require_game(game_id)
        if error:
            return error
        payload = _state(game)
        payload["events"] = [
            {"type": event["type"], "reason": event.get("reason")}
            for event in game.engine.events
        ]
        return jsonify(payload)

    return app
