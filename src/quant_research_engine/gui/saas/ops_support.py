"""QRE-SAAS-PUBLIC-BETA-OPS：公测运营指标与反馈分类支撑层。

职责边界（批准计划见 08_IMPLEMENTATION_BRIEF.md QRE-SAAS-PUBLIC-BETA-OPS）：
- 指标只做「读权威库 + 简单聚合」，不编造历史、不回填、不估算；
  空数据（分母为 0）一律返回 None，由前端显示「—」。
- NL 编译事件表 nl_compile_events 是最小隐私安全记录：只存
  ok/cache_hit/error_class/scope/created_at，不存策略文本、API key、原始 IP；
  自本功能上线起统计，上线前无历史。
- 反馈分类/状态为最小闭环（不建工单系统）：category=bug/experience/factor/other，
  status=open/doing/done/closed；allowlist 在此单一权威处定义。
- 懒自愈（information_schema 先查再 CREATE/ALTER）只兜底本地/测试库；
  ECS 表 owner 是 postgres，由 postgres apply cloud_schema.sql。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import Engine

# 公测运营按 A 股自然日（Asia/Shanghai）边界，不用 UTC 日——UTC 00:00 对应上海
# 08:00，会把当日凌晨 8 小时的运营数据漏到「昨日」。
SHANGHAI = ZoneInfo("Asia/Shanghai")

# --- 反馈分类与处理状态（单一权威：提交校验、管理台筛选/流转、前端文案同源） ---
FEEDBACK_CATEGORIES = ("bug", "experience", "factor", "other")
FEEDBACK_CATEGORY_LABELS = {
    "bug": "问题缺陷",
    "experience": "体验建议",
    "factor": "因子需求",
    "other": "其他",
}
FEEDBACK_STATUSES = ("open", "doing", "done", "closed")
FEEDBACK_STATUS_LABELS = {
    "open": "待处理",
    "doing": "处理中",
    "done": "已解决",
    "closed": "已关闭",
}

# --- 运营指标时间窗口 ---
OPS_WINDOWS = ("today", "7d", "30d", "all")
OPS_WINDOW_LABELS = {"today": "今日", "7d": "近 7 天", "30d": "近 30 天", "all": "累计"}

# NL 编译失败分类（compile_nl 返回的 code；成功为 None）
NL_ERROR_CLASSES = ("llm_error", "invalid_yaml", "missing_factors", "not_configured")

# 已 ensure 过的 engine（同 nl_compile_support 模式）
_OPS_TABLES_ENSURED: set[int] = set()
_OPS_TABLES_OK: dict[int, bool] = {}


def _now_shanghai() -> datetime:
    """当前上海时间（可 monkeypatch 的日界测试助手）。"""
    return datetime.now(SHANGHAI)


def window_start(window: str) -> datetime | None:
    """窗口起点（UTC）；all 返回 None（不限起点）。today = 上海当日零点。"""
    if window == "today":
        start_sh = _now_shanghai().replace(hour=0, minute=0, second=0, microsecond=0)
        return start_sh.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if window == "7d":
        return now - timedelta(days=7)
    if window == "30d":
        return now - timedelta(days=30)
    return None


def ensure_ops_tables(engine: Engine) -> bool:
    """幂等确保 nl_compile_events 与 feedback 两列存在（失败返回 False 降级）。"""
    key = id(engine)
    if key in _OPS_TABLES_ENSURED:
        return _OPS_TABLES_OK.get(key, False)
    ok = True
    try:
        with engine.begin() as conn:
            tables = {
                r[0]
                for r in conn.execute(
                    text("SELECT table_name FROM information_schema.tables "
                         "WHERE table_name IN ('nl_compile_events')")
                )
            }
            if "nl_compile_events" not in tables:
                conn.execute(text(
                    "CREATE TABLE IF NOT EXISTS nl_compile_events ("
                    "id BIGSERIAL PRIMARY KEY, "
                    "ok BOOLEAN NOT NULL, "
                    "cache_hit BOOLEAN NOT NULL DEFAULT false, "
                    "error_class TEXT, "
                    "scope TEXT NOT NULL DEFAULT 'guest', "
                    "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
                ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_nl_compile_events_created "
                    "ON nl_compile_events (created_at DESC)"
                ))
            cols = {
                r[0]
                for r in conn.execute(
                    text("SELECT column_name FROM information_schema.columns "
                         "WHERE table_name = 'feedback' "
                         "AND column_name IN ('category', 'status')")
                )
            }
            if "category" not in cols:
                conn.execute(text(
                    "ALTER TABLE feedback ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'other'"))
            if "status" not in cols:
                conn.execute(text(
                    "ALTER TABLE feedback ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'open'"))
    except Exception:
        ok = False
    _OPS_TABLES_ENSURED.add(key)
    _OPS_TABLES_OK[key] = ok
    return ok


def record_nl_event_on(conn: Any, *, ok: bool, cache_hit: bool,
                       error_class: str | None, scope: str) -> None:
    """在既有连接/事务上记录一条 NL 编译事件（调用方保证 ops 表已 ensure）。"""
    conn.execute(
        text(
            "INSERT INTO nl_compile_events (ok, cache_hit, error_class, scope) "
            "VALUES (:ok, :ch, :ec, :scope)"
        ),
        {"ok": bool(ok), "ch": bool(cache_hit), "ec": error_class, "scope": scope},
    )


def record_nl_event(engine: Engine, *, ok: bool, cache_hit: bool,
                    error_class: str | None, scope: str) -> None:
    """尽力记录一条 NL 编译事件（独立短事务；失败静默降级，绝不影响编译响应）。"""
    try:
        if not ensure_ops_tables(engine):
            return
        with engine.begin() as conn:
            record_nl_event_on(conn, ok=ok, cache_hit=cache_hit,
                               error_class=error_class, scope=scope)
    except Exception:
        pass


def _ratio(num: int, den: int) -> float | None:
    return (num / den) if den else None


def compute_ops(conn: Any, window: str) -> dict[str, Any]:
    """公测运营指标（窗口内聚合）。conn 为只读连接；比率分母为 0 时返回 None。"""
    since = window_start(window)
    since_sql = "AND created_at >= :since" if since is not None else ""
    params: dict[str, Any] = {"since": since} if since is not None else {}

    # --- NL 编译（自 nl_compile_events 上线起统计；表缺失时 total=0 → 全部 None） ---
    nl_row = conn.execute(
        text(
            "SELECT count(*) AS total, "
            "count(*) FILTER (WHERE ok) AS ok, "
            "count(*) FILTER (WHERE NOT ok) AS failed, "
            "count(*) FILTER (WHERE cache_hit) AS cache_hits, "
            "min(created_at) AS first_event_at "
            f"FROM nl_compile_events WHERE true {since_sql}"
        ),
        params,
    ).mappings().one()
    nl_failures = conn.execute(
        text(
            "SELECT error_class, count(*) AS cnt FROM nl_compile_events "
            f"WHERE NOT ok AND error_class IS NOT NULL {since_sql} "
            "GROUP BY error_class ORDER BY cnt DESC, error_class LIMIT 5"
        ),
        params,
    ).mappings().all()
    nl_total = int(nl_row["total"] or 0)

    # --- 回测（kind='full'：smoke 为内部小样本试算，不计入公测运营口径；
    #     canceled 为用户主动取消，不计入成功率分母） ---
    bt_row = conn.execute(
        text(
            "SELECT count(*) AS total, "
            "count(*) FILTER (WHERE status = 'completed') AS completed, "
            "count(*) FILTER (WHERE status IN ('failed','expired')) AS failed, "
            "avg(extract(epoch FROM (started_at - created_at))) FILTER (WHERE started_at IS NOT NULL) AS avg_queue_s, "
            "avg(extract(epoch FROM (finished_at - started_at))) FILTER (WHERE started_at IS NOT NULL AND finished_at IS NOT NULL) AS avg_run_s "
            f"FROM jobs WHERE kind = 'full' {since_sql.replace('created_at', 'jobs.created_at')}"
        ),
        params,
    ).mappings().one()
    bt_failures = conn.execute(
        text(
            "SELECT coalesce(error_class, 'unclassified') AS error_class, count(*) AS cnt "
            "FROM jobs WHERE kind = 'full' AND status IN ('failed','expired') "
            f"{since_sql.replace('created_at', 'jobs.created_at')} "
            "GROUP BY error_class ORDER BY cnt DESC, error_class LIMIT 5"
        ),
        params,
    ).mappings().all()

    # --- 游客到注册转化（口径：游客=提交过任务的独立会话 guest_key 去重；
    #     未提交任务的访客不可见；无跨会话关联，不做个体级归因） ---
    # Required Fix 1（2026-10-26 复核）：new_users/guest_sessions 只是两个未关联
    # 总量的比，不是转化率，可超过 100%——不计算、不展示比率；measurement=
    # unlinked 明示「需会话关联，当前不计算」。未来做真实转化须先有游客会话与
    # 注册账号的关联记录，本切片只做诚实降级。
    conv_row = conn.execute(
        text(
            "SELECT (SELECT count(DISTINCT guest_key) FROM jobs "
            "WHERE guest_key IS NOT NULL AND true " + since_sql + ") AS guest_sessions, "
            "(SELECT count(*) FROM users WHERE true " + since_sql + ") AS new_users"
        ),
        params,
    ).mappings().one()

    # --- 反馈（按类型/状态计数） ---
    fb_rows = conn.execute(
        text(
            "SELECT category, status, count(*) AS cnt FROM feedback "
            f"WHERE true {since_sql} GROUP BY category, status"
        ),
        params,
    ).mappings().all()
    by_category = {c: 0 for c in FEEDBACK_CATEGORIES}
    by_status = {s: 0 for s in FEEDBACK_STATUSES}
    fb_total = 0
    for row in fb_rows:
        cat = row["category"] if row["category"] in by_category else "other"
        st = row["status"] if row["status"] in by_status else "open"
        by_category[cat] += int(row["cnt"])
        by_status[st] += int(row["cnt"])
        fb_total += int(row["cnt"])

    bt_completed = int(bt_row["completed"] or 0)
    bt_failed = int(bt_row["failed"] or 0)
    guest_sessions = int(conv_row["guest_sessions"] or 0)
    new_users = int(conv_row["new_users"] or 0)
    return {
        "window": window,
        "since": since,
        "nl": {
            "total": nl_total,
            "ok": int(nl_row["ok"] or 0),
            "failed": int(nl_row["failed"] or 0),
            "success_rate": _ratio(int(nl_row["ok"] or 0), nl_total),
            "cache_hits": int(nl_row["cache_hits"] or 0),
            "cache_hit_rate": _ratio(int(nl_row["cache_hits"] or 0), nl_total),
            "first_event_at": nl_row["first_event_at"],
            "top_failures": [
                {"error_class": r["error_class"], "count": int(r["cnt"])} for r in nl_failures
            ],
        },
        "backtest": {
            "total": int(bt_row["total"] or 0),
            "completed": bt_completed,
            "failed": bt_failed,
            "success_rate": _ratio(bt_completed, bt_completed + bt_failed),
            "avg_queue_seconds": (
                round(float(bt_row["avg_queue_s"]), 1) if bt_row["avg_queue_s"] is not None else None
            ),
            "avg_run_seconds": (
                round(float(bt_row["avg_run_s"]), 1) if bt_row["avg_run_s"] is not None else None
            ),
            "top_failures": [
                {"error_class": r["error_class"], "count": int(r["cnt"])} for r in bt_failures
            ],
        },
        "conversion": {
            "guest_sessions": guest_sessions,
            "new_users": new_users,
            # 不计算未关联总量的比（Required Fix 1）：可能 >100%，构成误导
            "ratio": None,
            "measurement": "unlinked",
        },
        "feedback": {
            "total": fb_total,
            "open": by_status["open"],
            "by_category": by_category,
            "by_status": by_status,
        },
    }
