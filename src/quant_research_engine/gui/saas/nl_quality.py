"""NL 编译质量管理员视图；数据只读自 nl_compile_events。"""

from __future__ import annotations

from typing import Any

from flask import jsonify, render_template
from sqlalchemy import text


def nl_quality_view(engine) -> dict[str, Any]:
    from .ops_support import ensure_ops_tables

    ensure_ops_tables(engine)
    with engine.connect() as conn:
        total = conn.execute(text(
            "SELECT count(*) AS total,count(*) FILTER (WHERE ok) AS ok,"
            "count(*) FILTER (WHERE cache_hit) AS cache_hits FROM nl_compile_events"
        )).mappings().one()
        failures = conn.execute(text(
            "SELECT error_class,count(*) AS count FROM nl_compile_events "
            "WHERE NOT ok AND error_class IS NOT NULL GROUP BY error_class "
            "ORDER BY count DESC,error_class LIMIT 10"
        )).mappings().all()
        daily = conn.execute(text(
            "SELECT created_at::date AS day,count(*) AS total,"
            "count(*) FILTER (WHERE ok) AS ok FROM nl_compile_events "
            "WHERE created_at >= current_date-13 GROUP BY 1 ORDER BY 1"
        )).mappings().all()
    count = int(total["total"] or 0)
    return {
        "ok": True, "total": count, "ok_count": int(total["ok"] or 0),
        "success_rate": (int(total["ok"] or 0) / count) if count else None,
        "cache_hits": int(total["cache_hits"] or 0),
        "top_failures": [dict(row) for row in failures],
        "daily": [dict(row) for row in daily],
    }


def register_nl_quality_routes(app) -> None:
    @app.get("/saas/nl-quality")
    def nl_quality_page():
        return render_template("nl_quality.html")

    @app.get("/api/saas/console/nl-quality")
    def api_nl_quality():
        from .app import _get_engine, _require_admin

        engine = _get_engine(app)
        _, denied = _require_admin(app, engine)
        if denied is not None:
            return denied
        return jsonify(nl_quality_view(engine))
