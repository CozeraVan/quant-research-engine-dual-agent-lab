"""会员权益口径（QRE-AUTH-MEMBERSHIP，37 号文档 T4/T5 后端）。

纯函数模块：不含 Flask / SQLAlchemy 依赖，app.py 与测试共用同一套 tier 默认值、
配额视图与「是否超限」判定，避免执行侧与管理台展示侧各写一份。
"""

from __future__ import annotations

TIER_LABELS = {"guest": "游客", "member": "内测会员", "paid": "付费会员",
               "starter": "初级会员", "advanced": "高级会员", "diamond": "钻石会员"}

POLICY_KEYS = ("daily_full_limit", "max_codes", "max_days", "max_factor_fields", "max_factor_tables")
POLICY_BOOL_KEYS = ("scan_enabled",)
POLICY_INT_KEYS = ("max_watches",)

# 2026-10-04 内测期权限调整（用户拍板，19 号文档原则：注册用户功能全开，
# 限制只在并发与计算资源/R2 槽位体系）：member/paid 前三项全 0=不限。
TIER_POLICY_DEFAULTS: dict[str, dict[str, object]] = {
    "guest":  {"daily_full_limit": 1, "max_codes": 1, "max_days": 1826,
               "max_factor_fields": 3, "max_factor_tables": 3, "scan_enabled": True, "max_watches": 20},
    "member": {"daily_full_limit": 10, "max_codes": 10, "max_days": 3653,
               "max_factor_fields": 3, "max_factor_tables": 3, "scan_enabled": True, "max_watches": 20},
    "paid":   {"daily_full_limit": 0, "max_codes": 0, "max_days": 0,
               "max_factor_fields": 20, "max_factor_tables": 3, "scan_enabled": True, "max_watches": 20},
    "starter": {"daily_full_limit": 3, "max_codes": 0, "max_days": 0,
                "max_factor_fields": 5, "max_factor_tables": 3, "scan_enabled": True, "max_watches": 20},
    "advanced": {"daily_full_limit": 10, "max_codes": 0, "max_days": 0,
                 "max_factor_fields": 8, "max_factor_tables": 3, "scan_enabled": True, "max_watches": 20},
    "diamond": {"daily_full_limit": 30, "max_codes": 0, "max_days": 0,
                "max_factor_fields": 20, "max_factor_tables": 3, "scan_enabled": True, "max_watches": 20},
}

# 周期用量（要求外层 users 表别名 u）：member=自然月，其余=自然日；付费支付周期由后续订单模型接管。
USED_QUOTA_SQL = (
    "(SELECT count(*) FROM jobs j WHERE j.user_id = u.id AND j.kind = 'full'"
    " AND j.created_at >= CASE WHEN u.tier = 'member'"
    " THEN date_trunc('month', now()) ELSE now()::date END)"
)
USED_TODAY_SQL = USED_QUOTA_SQL  # 既有调用别名；字段名 daily_full_limit 为历史合同


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

# 分池与规模闸：全量/大规模次数不与中小任务 SU 互换。
MAX_RANDOM_UNIVERSE = 2000
LARGE_SCALE_COVERAGE = 0.8


def quota_pool(params: dict, available_symbols: int | None = None) -> str:
    """large=全量/板块/≥2000随机/≥80%覆盖；其余为 small。"""
    if params.get("all_market") or params.get("whole_market") or params.get("universe"):
        return "large"
    random_n = params.get("random_n")
    if random_n is not None and int(random_n) >= MAX_RANDOM_UNIVERSE:
        return "large"
    codes = params.get("codes") or []
    if isinstance(codes, str):
        codes = [code.strip() for code in codes.split(",") if code.strip()]
    if available_symbols and len(codes) / available_symbols >= LARGE_SCALE_COVERAGE:
        return "large"
    return "small"


def validate_scope_policy(params: dict, policy: dict, *, logged_in: bool, check_period: bool = True) -> str | None:
    """服务端统一标的/区间闸；NL 文本不参与 params，直接构造请求也必须经过。"""
    random_n = params.get("random_n")
    if random_n is not None:
        try:
            random_value = int(random_n)
        except (TypeError, ValueError):
            return "随机股票数量须为整数"
        if random_value < 1:
            return "随机股票数量须为正整数"
        if random_value > MAX_RANDOM_UNIVERSE:
            return f"随机股票数量最多 {MAX_RANDOM_UNIVERSE} 只"
    if not logged_in:
        return None  # 游客保留既有专属错误与自动补齐逻辑
    max_codes = int(policy.get("max_codes") or 0)
    codes = params.get("codes") or []
    if isinstance(codes, str):
        codes = [code.strip() for code in codes.split(",") if code.strip()]
    if max_codes > 0 and (len(codes) > max_codes or (random_n is not None and int(random_n) > max_codes)):
        return f"当前账号每次最多回测 {max_codes} 只股票"
    if max_codes > 0 and (params.get("universe") or params.get("all_market") or params.get("whole_market")):
        return "当前账号未开放板块或全市场范围"
    max_days = int(policy.get("max_days") or 0)
    if check_period and max_days > 0:
        from datetime import date
        try:
            start = date.fromisoformat(str(params.get("start")))
            end = date.fromisoformat(str(params.get("end")))
        except (TypeError, ValueError):
            return "请填写合法的回测开始/结束日期"
        if start > end or (end - start).days > max_days:
            return f"当前账号单次最多回测 {max_days} 天，且不允许全期"
    return None
