"""会员订单与模拟支付 HTTP；真实渠道在后续接入。"""

from __future__ import annotations

import secrets
from typing import Any

from flask import current_app, jsonify, request
from sqlalchemy import text

PRODUCTS = {
    "starter": {"tier": "starter", "name": "初级会员", "price_cents": 2990, "days": 30},
    "advanced": {"tier": "advanced", "name": "高级会员", "price_cents": 6990, "days": 30},
    "diamond": {"tier": "diamond", "name": "钻石会员", "price_cents": 19900, "days": 30},
}


def _engine():
    from .app import _get_engine
    return _get_engine(current_app)


def ensure_payment_tables(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS membership_orders (
                id TEXT PRIMARY KEY,user_id BIGINT NOT NULL REFERENCES users(id),
                sku TEXT NOT NULL,price_cents INT NOT NULL,days INT NOT NULL,
                status TEXT NOT NULL,channel TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                paid_at TIMESTAMPTZ,fulfilled_at TIMESTAMPTZ)
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS payment_events (
                id BIGSERIAL PRIMARY KEY,order_id TEXT NOT NULL REFERENCES membership_orders(id),
                event_type TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE(order_id,event_type))
        """))


def register_payment_routes(app) -> None:
    @app.get("/api/saas/membership/products")
    def membership_products():
        return jsonify({"ok": True, "products": [{"sku": sku, **value} for sku, value in PRODUCTS.items()]})

    @app.post("/api/saas/membership/orders")
    def create_order():
        from .app import _current_user_id
        engine = _engine()
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        sku = str((request.get_json(silent=True) or {}).get("sku") or "")
        product = PRODUCTS.get(sku)
        if product is None:
            return jsonify({"ok": False, "error": "会员商品不存在"}), 400
        ensure_payment_tables(engine)
        order_id = "qre_" + secrets.token_urlsafe(18)
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO membership_orders (id,user_id,sku,price_cents,days,status,channel) "
                "VALUES (:id,:uid,:sku,:price,:days,'pending','simulator')"),
                {"id": order_id, "uid": uid, "sku": sku,
                 "price": product["price_cents"], "days": product["days"]})
        return jsonify({"ok": True, "order": {"id": order_id, "status": "pending", **product}}), 201

    def load_order(conn, order_id: str, uid: int):
        return conn.execute(text(
            "SELECT * FROM membership_orders WHERE id=:id AND user_id=:uid"
        ), {"id": order_id, "uid": uid}).mappings().first()

    @app.get("/api/saas/membership/orders/<order_id>")
    def order_detail(order_id: str):
        from .app import _current_user_id
        engine = _engine()
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        ensure_payment_tables(engine)
        with engine.connect() as conn:
            order = load_order(conn, order_id, uid)
        if order is None:
            return jsonify({"ok": False, "error": "订单不存在"}), 404
        return jsonify({"ok": True, "order": dict(order)})

    @app.post("/api/saas/membership/orders/<order_id>/simulate-pay")
    def simulate_pay(order_id: str):
        from .app import _current_user_id
        if not app.config.get("SAAS_PAYMENT_SIMULATOR"):
            return jsonify({"ok": False, "error": "模拟支付未启用"}), 404
        engine = _engine()
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        ensure_payment_tables(engine)
        with engine.begin() as conn:
            order = load_order(conn, order_id, uid)
            if order is None:
                return jsonify({"ok": False, "error": "订单不存在"}), 404
            if order["status"] == "fulfilled":
                return jsonify({"ok": True, "order": dict(order), "deduped": True})
            if order["status"] != "pending":
                return jsonify({"ok": False, "error": "订单当前不可支付"}), 409
            product = PRODUCTS[order["sku"]]
            conn.execute(text(
                "UPDATE membership_orders SET status='fulfilled',paid_at=now(),fulfilled_at=now() WHERE id=:id"
            ), {"id": order_id})
            conn.execute(text(
                "INSERT INTO payment_events (order_id,event_type) VALUES (:id,'paid'),(:id,'fulfilled')"
            ), {"id": order_id})
            conn.execute(text(
                "UPDATE users SET tier=:tier,member_since=now(),member_expire_at="
                "CASE WHEN member_expire_at>now() THEN member_expire_at ELSE now() END "
                "+ make_interval(days=>:days) WHERE id=:uid"
            ), {"tier": product["tier"], "days": product["days"], "uid": uid})
            order = load_order(conn, order_id, uid)
        return jsonify({"ok": True, "order": dict(order), "simulated": True})
