"""免费用户功能上线通知；只关联现有账号，不收集额外联系方式。"""

from __future__ import annotations

from flask import jsonify
from sqlalchemy import text


def ensure_subscription_tables(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS feature_subscriptions (
                id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL REFERENCES users(id),
                feature TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE(user_id,feature))
        """))


def register_subscription_routes(app) -> None:
    @app.post("/api/saas/membership/notify")
    def membership_notify():
        from .app import _current_user_id, _get_engine

        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "请先登录"}), 401
        ensure_subscription_tables(engine)
        with engine.begin() as conn:
            inserted = conn.execute(text(
                "INSERT INTO feature_subscriptions (user_id,feature) "
                "VALUES (:uid,'membership_launch') ON CONFLICT DO NOTHING RETURNING id"
            ), {"uid": uid}).first()
        if inserted is None:
            return jsonify({"ok": True, "subscribed": True, "deduped": True})
        return jsonify({"ok": True, "subscribed": True}), 201
