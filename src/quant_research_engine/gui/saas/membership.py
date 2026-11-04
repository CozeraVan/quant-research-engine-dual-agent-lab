"""会员权益口径（QRE-AUTH-MEMBERSHIP，37 号文档 T4/T5 后端）。

纯函数模块：不含 Flask / SQLAlchemy 依赖，app.py 与测试共用同一套 tier 默认值、
配额视图与「是否超限」判定，避免执行侧与管理台展示侧各写一份。
"""

from __future__ import annotations

TIER_LABELS = {"guest": "游客", "member": "内测会员", "paid": "付费会员"}

POLICY_KEYS = ("daily_full_limit", "max_codes", "max_days", "max_factor_fields", "max_factor_tables")
POLICY_BOOL_KEYS = ("scan_enabled",)
POLICY_INT_KEYS = ("max_watches",)

# 2026-10-04 内测期权限调整（用户拍板，19 号文档原则：注册用户功能全开，
# 限制只在并发与计算资源/R2 槽位体系）：member/paid 前三项全 0=不限。
TIER_POLICY_DEFAULTS: dict[str, dict[str, object]] = {
    "guest":  {"daily_full_limit": 1, "max_codes": 10, "max_days": 3650 + 7,
               "max_factor_fields": 20, "max_factor_tables": 3, "scan_enabled": True, "max_watches": 20},
    "member": {"daily_full_limit": 0, "max_codes": 0, "max_days": 0,
               "max_factor_fields": 20, "max_factor_tables": 3, "scan_enabled": True, "max_watches": 20},
    "paid":   {"daily_full_limit": 0, "max_codes": 0, "max_days": 0,
               "max_factor_fields": 20, "max_factor_tables": 3, "scan_enabled": True, "max_watches": 20},
}

# 当日全量回测用量（要求外层 users 表别名 u）：三处端点共用同一口径。
USED_TODAY_SQL = (
    "(SELECT count(*) FROM jobs j WHERE j.user_id = u.id"
    " AND j.kind = 'full' AND j.created_at::date = now()::date)"
)


def default_policy(tier: str | None) -> dict[str, object]:
    """层级默认权益；未知层级回落 member（内测期最宽松口径）。"""
    return dict(TIER_POLICY_DEFAULTS.get(str(tier or ""), TIER_POLICY_DEFAULTS["member"]))


def normalize_policy(row: object, tier: str | None) -> dict[str, object]:
    """tier_policies 行（mapping/None）→ 补默认值的完整策略；字符串数值转 int。"""
    policy = default_policy(tier)
    if row is None:
        return policy
    for key in POLICY_KEYS + POLICY_INT_KEYS:
        value = row.get(key) if hasattr(row, "get") else None
        if value is None:
            continue
        try:
            policy[key] = int(value)
        except (TypeError, ValueError):
            continue
    for key in POLICY_BOOL_KEYS:
        if hasattr(row, "get") and row.get(key) is not None:
            policy[key] = bool(row.get(key))
    return policy


def tier_label(tier: str | None) -> str:
    """层级展示名；None 视为已注册会员，未知层级原样返回便于运营自查。"""
    if tier is None:
        return TIER_LABELS["member"]
    return TIER_LABELS.get(tier, str(tier))


def quota_view(policy: object, used_today: int, is_admin: bool = False) -> dict[str, object]:
    """日全量配额视图：limit=「不限」/int，remaining=None 表示不限。"""
    used = int(used_today or 0)
    limit = int(policy.get("daily_full_limit") or 0)  # type: ignore[union-attr]
    if is_admin or limit <= 0:
        return {"limit": "不限", "used": used, "remaining": None, "unlimited": True}
    return {"limit": limit, "used": used, "remaining": max(0, limit - used), "unlimited": False}


def is_quota_exceeded(policy: object, used_today: int, is_admin: bool = False) -> bool:
    if is_admin:
        return False
    limit = int(policy.get("daily_full_limit") or 0)  # type: ignore[union-attr]
    if limit <= 0:
        return False
    return bool(int(used_today or 0) >= limit)


def is_watch_exceeded(policy: object, watch_count: int) -> bool:
    """信号监控上限；max_watches<=0 视为不限。"""
    max_watches = int(policy.get("max_watches", 20) or 0)  # type: ignore[union-attr]
    if max_watches <= 0:
        return False
    return bool(int(watch_count or 0) >= max_watches)