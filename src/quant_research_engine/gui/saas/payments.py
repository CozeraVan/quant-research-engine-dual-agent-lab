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
    "single_full": {"tier": "single_full", "name": "单次全期全量回测",
                    "price_cents": 990, "days": 0, "available": False},
}


def _engine():
    from .app import _get_engine
    return _get_engine(current_app)


ORDER_TTL_MINUTES = 30


def ensure_payment_tables(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS membership_orders (
                id TEXT PRIMARY KEY,user_id BIGINT NOT NULL REFERENCES users(id),
                sku TEXT NOT NULL,price_cents INT NOT NULL,days INT NOT NULL,
                status TEXT NOT NULL,channel TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                paid_at TIMESTAMPTZ,fulfilled_at TIMESTAMPTZ,expires_at TIMESTAMPTZ,
                closed_at TIMESTAMPTZ)
        """))
        conn.execute(text("ALTER TABLE membership_orders ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE membership_orders ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS payment_events (
                id BIGSERIAL PRIMARY KEY,order_id TEXT NOT NULL REFERENCES membership_orders(id),
                event_type TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                channel_event_id TEXT,UNIQUE(order_id,event_type))
        """))
        conn.execute(text("ALTER TABLE payment_events ADD COLUMN IF NOT EXISTS channel_event_id TEXT"))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_events_channel_event "
            "ON payment_events(channel_event_id) WHERE channel_event_id IS NOT NULL"
        ))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS payment_reconciliation_issues (
                id BIGSERIAL PRIMARY KEY,order_id TEXT NOT NULL REFERENCES membership_orders(id),
                issue_type TEXT NOT NULL,detail TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                resolved_at TIMESTAMPTZ,UNIQUE(order_id,issue_type))
        """))


def expire_due_orders(engine) -> int:
    """将超过支付时限的 pending 订单置为 expired；重复执行不新增事件。"""
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT id FROM membership_orders WHERE status='pending' "
            "AND COALESCE(expires_at,created_at + make_interval(mins=>:ttl))<=now() FOR UPDATE"
        ), {"ttl": ORDER_TTL_MINUTES}).all()
        if not rows:
            return 0
        ids = [row[0] for row in rows]
        conn.execute(text(
            "UPDATE membership_orders SET status='expired' WHERE id=ANY(:ids)"
        ), {"ids": ids})
        conn.execute(text(
            "INSERT INTO payment_events (order_id,event_type) "
            "SELECT id,'expired' FROM membership_orders WHERE id=ANY(:ids) ON CONFLICT DO NOTHING"
        ), {"ids": ids})
        return len(ids)


def _record_reconciliation_issue(engine, order_id: str, issue_type: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO payment_reconciliation_issues (order_id,issue_type,detail) "
            "VALUES (:id,:kind,:detail) ON CONFLICT (order_id,issue_type) DO UPDATE SET "
            "detail=EXCLUDED.detail,created_at=now(),resolved_at=NULL"
        ), {"id": order_id, "kind": issue_type, "detail": issue_type})


def reconcile_native_orders(engine, client, *, limit: int = 100) -> dict[str, Any]:
    """管理员主动查单对账；仅真实 SUCCESS 且商户/金额匹配才履约。"""
    with engine.connect() as conn:
        orders = conn.execute(text(
            "SELECT * FROM membership_orders WHERE channel='native' "
            "AND status IN ('pending','paid','fulfilled') "
            "ORDER BY created_at DESC LIMIT :limit"
        ), {"limit": limit}).mappings().all()
    recovered = 0
    issues = 0
    for row in orders:
        order = dict(row)
        try:
            paid = client.query_order(order["id"])
        except Exception:
            # 渠道异常只进入异常队列，不改变本地订单或权益。
            _record_reconciliation_issue(engine, order["id"], "channel_error")
            issues += 1
            continue
        if paid.get("trade_state") != "SUCCESS":
            continue
        if paid.get("mchid") != client.config.mchid or (paid.get("amount") or {}).get("total") != order["price_cents"]:
            _record_reconciliation_issue(engine, order["id"], "amount_or_mchid_mismatch")
            issues += 1
            continue
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE payment_reconciliation_issues SET resolved_at=now() "
                "WHERE order_id=:id AND resolved_at IS NULL"
            ), {"id": order["id"]})
        if order["status"] in ("pending", "paid"):
            fulfill_order(engine, order["id"])
            recovered += 1
    return {"ok": True, "checked": len(orders), "recovered": recovered, "issues": issues}


def fulfill_order(engine, order_id: str, uid: int | None = None) -> dict[str, Any] | None:
    """支付成功后的幂等履约；真实回调与模拟渠道共用同一事务。"""
    with engine.begin() as conn:
        condition = "id=:id" + (" AND user_id=:uid" if uid is not None else "")
        params = {"id": order_id}
        if uid is not None:
            params["uid"] = uid
        order = conn.execute(text(
            f"SELECT * FROM membership_orders WHERE {condition} FOR UPDATE"
        ), params).mappings().first()
        if order is None:
            return None
        if order["status"] == "fulfilled":
            return dict(order)
        if order["status"] != "paid" and order["status"] != "pending":
            raise ValueError("订单当前不可履约")
        product = PRODUCTS[order["sku"]]
        conn.execute(text(
            "UPDATE membership_orders SET status='fulfilled',paid_at=COALESCE(paid_at,now()),"
            "fulfilled_at=now() WHERE id=:id"
        ), {"id": order_id})
        conn.execute(text(
            "INSERT INTO payment_events (order_id,event_type) VALUES (:id,'paid'),(:id,'fulfilled') "
            "ON CONFLICT DO NOTHING"
        ), {"id": order_id})
        conn.execute(text(
            "UPDATE users SET tier=:tier,member_since=now(),member_expire_at="
            "CASE WHEN member_expire_at>now() THEN member_expire_at ELSE now() END "
            "+ make_interval(days=>:days) WHERE id=:uid"
        ), {"tier": product["tier"], "days": product["days"], "uid": order["user_id"]})
        expiry = conn.execute(text(
            "SELECT member_expire_at FROM users WHERE id=:uid"
        ), {"uid": order["user_id"]}).scalar_one()
        conn.execute(text(
            "INSERT INTO membership_entitlements (order_id,user_id,tier,starts_at,ends_at,status) "
            "VALUES (:id,:uid,:tier,now(),:expiry,'active') ON CONFLICT (order_id) DO NOTHING"
        ), {"id": order_id, "uid": order["user_id"], "tier": product["tier"], "expiry": expiry})
        return dict(conn.execute(text(
            "SELECT * FROM membership_orders WHERE id=:id"
        ), {"id": order_id}).mappings().one())


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
        if not product.get("available", True):
            return jsonify({"ok": False, "error": "该单次项目尚未开放购买"}), 403
        ensure_payment_tables(engine)
        order_id = "qre_" + secrets.token_urlsafe(18)
        from .wechat_native import NativeClient, NativeConfig
        native_config = NativeConfig.from_env()
        channel = "native" if native_config is not None else "simulator"
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO membership_orders (id,user_id,sku,price_cents,days,status,channel,expires_at) "
                "VALUES (:id,:uid,:sku,:price,:days,'pending',:channel,"
                "now()+make_interval(mins=>:ttl))"),
                {"id": order_id, "uid": uid, "sku": sku, "channel": channel,
                 "price": product["price_cents"], "days": product["days"], "ttl": ORDER_TTL_MINUTES})
        code_url = None
        if native_config is not None:
            try:
                code_url = NativeClient(native_config).create_order(
                    order_id=order_id, description=product["name"], price_cents=product["price_cents"],
                )
            except Exception:
                # 渠道下单失败：关闭本地 pending，避免留下可继续支付的孤儿单。
                with engine.begin() as conn:
                    conn.execute(text(
                        "UPDATE membership_orders SET status='closed',closed_at=now() "
                        "WHERE id=:id AND status='pending'"
                    ), {"id": order_id})
                    conn.execute(text(
                        "INSERT INTO payment_events (order_id,event_type) "
                        "VALUES (:id,'channel_order_failed') ON CONFLICT DO NOTHING"
                    ), {"id": order_id})
                return jsonify({"ok": False, "error": "支付渠道下单失败，请稍后重新创建订单"}), 502
        return jsonify({"ok": True, "order": {"id": order_id, "status": "pending", **product},
                        "channel": channel, "code_url": code_url}), 201

    def load_order(conn, order_id: str, uid: int):
        return conn.execute(text(
            "SELECT * FROM membership_orders WHERE id=:id AND user_id=:uid"
        ), {"id": order_id, "uid": uid}).mappings().first()

    @app.get("/api/saas/membership/orders")
    def order_list():
        from .app import _current_user_id
        engine = _engine()
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        ensure_payment_tables(engine)
        expire_due_orders(engine)
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT * FROM membership_orders WHERE user_id=:uid ORDER BY created_at DESC LIMIT 50"
            ), {"uid": uid}).mappings().all()
        return jsonify({"ok": True, "orders": [dict(row) for row in rows]})

    @app.get("/api/saas/membership/orders/<order_id>")
    def order_detail(order_id: str):
        from .app import _current_user_id
        engine = _engine()
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        ensure_payment_tables(engine)
        expire_due_orders(engine)
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
        expire_due_orders(engine)
        with engine.connect() as conn:
            existing = load_order(conn, order_id, uid)
        if existing is None:
            return jsonify({"ok": False, "error": "订单不存在"}), 404
        if existing["status"] == "fulfilled":
            return jsonify({"ok": True, "order": dict(existing), "deduped": True})
        if existing["status"] != "pending":
            return jsonify({"ok": False, "error": "订单当前不可支付"}), 409
        order = fulfill_order(engine, order_id, uid)
        return jsonify({"ok": True, "order": order, "simulated": True})

    @app.post("/api/saas/membership/payments/wechat/notify")
    def wechat_notify():
        from .wechat_native import NativeClient, NativeConfig
        config = NativeConfig.from_env()
        if config is None:
            return jsonify({"ok": False, "error": "支付渠道未配置"}), 404
        engine = _engine()
        ensure_payment_tables(engine)
        try:
            paid = NativeClient(config).verify_callback(request.get_data(), request.headers)
        except Exception:
            return jsonify({"ok": False, "error": "支付通知验签失败"}), 400
        order_id = str(paid.get("out_trade_no") or "")
        with engine.connect() as conn:
            order = conn.execute(text(
                "SELECT * FROM membership_orders WHERE id=:id"
            ), {"id": order_id}).mappings().first()
        if order is None or paid.get("trade_state") != "SUCCESS":
            return jsonify({"ok": False, "error": "订单或支付状态无效"}), 400
        if paid.get("mchid") != config.mchid or (paid.get("amount") or {}).get("total") != order["price_cents"]:
            return jsonify({"ok": False, "error": "支付金额或商户不匹配"}), 400
        fulfilled = fulfill_order(engine, order_id)
        if paid.get("_event_id"):
            with engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO payment_events (order_id,event_type,channel_event_id) "
                    "VALUES (:id,'notification',:event_id) ON CONFLICT DO NOTHING"
                ), {"id": order_id, "event_id": str(paid["_event_id"])})
        return jsonify({"ok": True, "status": fulfilled["status"]})

    @app.post("/api/saas/membership/orders/<order_id>/query-payment")
    def query_payment(order_id: str):
        from .app import _current_user_id
        from .wechat_native import NativeClient, NativeConfig
        engine = _engine()
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        config = NativeConfig.from_env()
        if config is None:
            return jsonify({"ok": False, "error": "支付渠道未配置"}), 404
        ensure_payment_tables(engine)
        with engine.connect() as conn:
            order = load_order(conn, order_id, uid)
        if order is None:
            return jsonify({"ok": False, "error": "订单不存在"}), 404
        paid = NativeClient(config).query_order(order_id)
        if paid.get("trade_state") == "SUCCESS":
            if paid.get("mchid") != config.mchid or (paid.get("amount") or {}).get("total") != order["price_cents"]:
                return jsonify({"ok": False, "error": "支付金额或商户不匹配"}), 400
            order = fulfill_order(engine, order_id, uid)
        return jsonify({"ok": True, "order": order, "trade_state": paid.get("trade_state")})

    @app.post("/api/saas/membership/orders/<order_id>/close")
    def close_order(order_id: str):
        from .app import _current_user_id
        engine = _engine()
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        ensure_payment_tables(engine)
        expire_due_orders(engine)
        with engine.begin() as conn:
            order = load_order(conn, order_id, uid)
            if order is None:
                return jsonify({"ok": False, "error": "订单不存在"}), 404
            if order["status"] == "closed":
                return jsonify({"ok": True, "order": dict(order), "deduped": True})
            if order["status"] != "pending":
                return jsonify({"ok": False, "error": "仅待支付订单可关闭"}), 409
            conn.execute(text(
                "UPDATE membership_orders SET status='closed',closed_at=now() WHERE id=:id"
            ), {"id": order_id})
            conn.execute(text(
                "INSERT INTO payment_events (order_id,event_type) VALUES (:id,'closed') ON CONFLICT DO NOTHING"
            ), {"id": order_id})
            order = load_order(conn, order_id, uid)
        return jsonify({"ok": True, "order": dict(order)})

    @app.post("/api/saas/membership/orders/<order_id>/retry-fulfillment")
    def retry_fulfillment(order_id: str):
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
        if order["status"] == "fulfilled":
            return jsonify({"ok": True, "order": dict(order), "deduped": True})
        if order["status"] != "paid":
            return jsonify({"ok": False, "error": "仅已支付未履约订单可重试"}), 409
        order = fulfill_order(engine, order_id, uid)
        return jsonify({"ok": True, "order": order, "recovered": True})

    @app.post("/api/saas/console/payments/reconcile")
    def reconcile_payments():
        from .app import _require_admin
        from .wechat_native import NativeClient, NativeConfig
        engine = _engine()
        _, denied = _require_admin(app, engine)
        if denied is not None:
            return denied
        config = NativeConfig.from_env()
        if config is None:
            return jsonify({"ok": False, "error": "支付渠道未配置"}), 404
        ensure_payment_tables(engine)
        return jsonify(reconcile_native_orders(engine, NativeClient(config)))

    @app.post("/api/saas/membership/orders/<order_id>/simulate-refund")
    def simulate_refund(order_id: str):
        from .app import _current_user_id
        if not app.config.get("SAAS_PAYMENT_SIMULATOR"):
            return jsonify({"ok": False, "error": "模拟退款未启用"}), 404
        engine = _engine()
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        ensure_payment_tables(engine)
        with engine.begin() as conn:
            order = load_order(conn, order_id, uid)
            if order is None:
                return jsonify({"ok": False, "error": "订单不存在"}), 404
            if order["status"] == "refunded":
                return jsonify({"ok": True, "order": dict(order), "deduped": True})
            if order["status"] != "fulfilled":
                return jsonify({"ok": False, "error": "仅已生效订单可退款"}), 409
            conn.execute(text("UPDATE membership_orders SET status='refunded' WHERE id=:id"), {"id": order_id})
            conn.execute(text("INSERT INTO payment_events (order_id,event_type) VALUES (:id,'refunded') ON CONFLICT DO NOTHING"), {"id": order_id})
            conn.execute(text("UPDATE membership_entitlements SET status='revoked',revoked_at=now(),revoke_reason='refunded' WHERE order_id=:id AND status='active'"), {"id": order_id})
            conn.execute(text("UPDATE users SET tier='member',member_expire_at=now() WHERE id=:uid"), {"uid": uid})
            order = load_order(conn, order_id, uid)
        return jsonify({"ok": True, "order": dict(order), "simulated": True})
