"""《我不是股神》WSL 本地 API；匿名响应不含真实代码、日期或未来行情。"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from quant_research_engine.factor_basis import FACTOR_BASIS_QFQ_ANCHOR_V1
from quant_research_engine.game.engine import GameRuleError
from quant_research_engine.game.factors import GROUP_LABELS, GROUP_ORDER, factor_catalog
from quant_research_engine.game.session import GameSession

OWNER_COOKIE = "qre_game_owner"

# S1：开局配置白名单（服务端最终闸，防篡改 22 号:97）。默认基线 1250 / 1,000,000 不变。
ALLOWED_GAME_BARS = (250, 750, 1250)
ALLOWED_INITIAL_CASH = (100_000, 500_000, 1_000_000, 5_000_000)


@dataclass
class GameSessionRegistry:
    provider: object
    sessions: dict[str, GameSession] | None = None

    def __post_init__(self) -> None:
        if self.sessions is None:
            self.sessions = {}

    def create(self, **options) -> GameSession:
        game = self.provider.create_session(**options)
        game_id = secrets.token_urlsafe(24)
        while game_id in self.sessions:
            game_id = secrets.token_urlsafe(24)
        game.web_id = game_id
        game.owner_id = secrets.token_urlsafe(24)
        # DB 按需会话使用真实日期，只有离线快照才应用导出时的日期偏移。
        if not game.symbol.startswith("X"):
            game.reveal_date_offset_days = 0
            game.reveal_identity = self.provider.reveal_identity(game.symbol)
        self.sessions[game_id] = game
        return game

    def get(self, game_id: str, owner_id: str) -> GameSession | None:
        game = self.sessions.get(game_id)
        if game is None or game.owner_id != owner_id:
            return None
        return game


# 终局揭示的数据来源（只读，零 DB）：快照脱敏元数据 manifest.json 的日期偏移，
# 以及可选的真实身份映射 identity.json（匿名代码 → {name, code}）。
# identity.json 由 WSL 侧提供（真实名称只在终局揭示，游戏中全程匿名）；缺失时真实名称留空，
# 前端显示「待揭示」占位——这是「需要 WSL 补充的接口」，Windows 不伪造真实证券名称。
_SNAPSHOT_DIR = Path(__file__).resolve().parents[3] / "data" / "game_snapshots"


def _reveal_meta() -> tuple[int, dict]:
    offset = 0
    identity: dict = {}
    try:
        manifest = json.loads((_SNAPSHOT_DIR / "manifest.json").read_text(encoding="utf-8"))
        offset = int(manifest.get("date_offset_days", 0))
    except (OSError, ValueError, TypeError):
        offset = 0
    try:
        loaded = json.loads((_SNAPSHOT_DIR / "identity.json").read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            identity = loaded
    except (OSError, ValueError, TypeError):
        identity = {}
    return offset, identity


def _reveal(game: GameSession) -> dict:
    """仅终局随 _state 下发：真实名称/代码 + 真实时间区间 + 总结统计。

    真实日期 = 快照日期 − 脱敏偏移（manifest.date_offset_days）；游戏中 K 线只用匿名 turn，
    真实日期与名称只在 finished 后揭示。equity_curve / trade_marks 供总结页收益曲线与买卖点。
    """
    snapshot_offset, identity = _reveal_meta()
    offset = getattr(game, "reveal_date_offset_days", snapshot_offset)
    ident = getattr(game, "reveal_identity", None)
    if ident is None:
        ident = identity.get(game.symbol, {}) if isinstance(identity, dict) else {}
    if not isinstance(ident, dict):
        ident = {}
    first_idx = game.start_index + game.warmup_bars
    last_idx = game.cursor
    shift = timedelta(days=offset)
    turn_of = {bar.trade_date: idx - game.start_index + 1 for idx, bar in enumerate(game.bars)}
    return {
        "real_name": ident.get("name"),
        "real_code": ident.get("code"),
        "start_date": (game.bars[first_idx].trade_date - shift).isoformat(),
        "end_date": (game.bars[last_idx].trade_date - shift).isoformat(),
        "selected_bars": game.game_bars,
        "played_bars": last_idx - first_idx + 1,
        "date_offset_days": offset,
        "equity_curve": [float(value) for value in game.equity_curve],
        "trade_marks": [
            {"t": turn_of.get(fill.trade_date), "side": fill.side.value,
             "price": fill.price, "quantity": fill.quantity, "cost": fill.cost,
             "date": (fill.trade_date - shift).isoformat()}
            for fill in game.trades
        ],
    }


def _state(game: GameSession) -> dict:
    return {
        "id": game.web_id,
        "display_name": game.display_name,
        "display_code": game.display_code,
        "phase": game.phase,
        "cursor": game.cursor - game.start_index + 1,
        "warmup_bars": game.warmup_bars,
        "game_bars": game.game_bars,
        # S1：资金基线与收益统计（additive，默认值不变；收益率/回撤为小数）。
        "initial_cash": game.engine.initial_cash,
        "return_pct": game.return_pct,
        "max_drawdown": game.max_drawdown,
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
        # QRE-FACTOR-BASIS-CONTRACT 第 1 条：生成侧显式带口径标记（46 号 T3）。
        # 游戏价格型因子已按 K 线前复权锚点换算（族白名单除以 anchor），
        # 满足 qfq_anchor_v1；沿用现有 price_basis 逻辑，不新增换算层。
        "factor_basis": FACTOR_BASIS_QFQ_ANCHOR_V1,
        "factor_audit": getattr(game, "factor_audit", None),
        "factor_errors": dict(getattr(game, "factor_errors", {}) or {}),
        "trades": [
            {"side": fill.side.value, "price": fill.price,
             "quantity": fill.quantity, "cost": fill.cost}
            for fill in game.trades
        ],
        # 终局揭示（additive，仅 finished 下发；游戏中为 None，不泄露真实身份/日期）。
        "reveal": _reveal(game) if game.finished else None,
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
        data = request.get_json(silent=True) or {}
        options: dict = {}
        for key, allowed in (("game_bars", ALLOWED_GAME_BARS), ("initial_cash", ALLOWED_INITIAL_CASH)):
            if key not in data:
                continue
            try:
                value = int(data[key])
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": f"{key} 必须为整数"}), 400
            if value not in allowed:
                return jsonify({"ok": False, "error": f"{key} 仅支持 {list(allowed)}"}), 400
            options[key] = value
        try:
            game = registry.create(**options)
        except GameRuleError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        owner = request.cookies.get(OWNER_COOKIE) or game.owner_id
        game.owner_id = owner
        response = jsonify(_state(game))
        response.set_cookie(OWNER_COOKIE, owner, max_age=60 * 60 * 24 * 365,
                            httponly=True, samesite="Lax",
                            secure=bool(app.config.get("GAME_COOKIE_SECURE")))
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
