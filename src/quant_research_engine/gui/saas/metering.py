"""会员额度的内部 SU 影子计量；不执行权限拦截或收费。"""

from __future__ import annotations

from datetime import date
from typing import Any

import yaml

FULL_SCALE_REFERENCE_SU = 470_493


def calculate_su(
    symbol_count: int,
    years: float,
    factor_fields: int = 1,
    factor_tables: int = 1,
    trades: int = 0,
) -> int:
    """按 50 号合同换算标准回测单位，返回近似整数。"""
    if symbol_count < 1 or years <= 0 or factor_fields < 1 or factor_tables < 1 or trades < 0:
        raise ValueError("SU 输入必须为正数，交易笔数不得为负")
    stock_years = symbol_count * years
    factor_weight = 1 + 0.05 * (factor_fields - 1) + 0.15 * (factor_tables - 1)
    turnover_weight = 1 + 0.1 * trades / stock_years
    return max(1, round(stock_years * factor_weight * turnover_weight))


def years_between(start: str, end: str) -> float:
    days = (date.fromisoformat(end) - date.fromisoformat(start)).days
    return max(days / 365.25, 1 / 365.25)


FULL_SCALE_CYCLES = {"starter": 3, "advanced": 10, "diamond": 30}


def _add_month(day: date) -> date:
    import calendar

    year, month = divmod(day.year * 12 + day.month, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def period_window(tier: str, at: date, member_since: date | None = None) -> tuple[date, date]:
    """游客=自然日，登录=自然月，付费=从会员生效日起的支付周期。"""
    if tier == "guest":
        return at, at
    if tier == "member":
        return at.replace(day=1), _add_month(at.replace(day=1))
    start = member_since or at
    while _add_month(start) <= at:
        start = _add_month(start)
    return start, _add_month(start)


def allowance_su(tier: str) -> int:
    return FULL_SCALE_CYCLES.get(tier, 0) * FULL_SCALE_REFERENCE_SU


def usage_from_result(job: dict[str, Any], summary: dict[str, Any], strategy_yaml: str) -> dict[str, Any] | None:
    params = job.get("params") or {}
    strategy = yaml.safe_load(strategy_yaml) or {}
    fields = ((strategy.get("data") or {}).get("factor_fields") or {})
    references = list(fields.values()) if isinstance(fields, dict) else []
    tables = {str(value).rsplit(".", 1)[0] for value in references}
    start = str(summary.get("date_start") or params.get("start") or "")
    end = str(summary.get("date_end") or summary.get("data_until") or params.get("end") or "")
    if not start or not end:
        return None  # 旧/最小结果缺区间时不猜造用量
    years = years_between(start, end)
    symbols = int(summary.get("symbol_count") or 0)
    if symbols < 1:
        codes = params.get("codes") or []
        symbols = len(codes) if isinstance(codes, list) else 0
    if symbols < 1:
        symbols = 5201 if params.get("all_market") or not params.get("codes") else 1
    trades = int(summary.get("total_trade_count") or 0)
    return {
        "symbol_count": symbols,
        "years": years,
        "factor_fields": max(1, len(references)),
        "factor_tables": max(1, len(tables)),
        "trades": trades,
        "estimated_su": calculate_su(symbols, years, max(1, len(references)), max(1, len(tables))),
        "actual_su": calculate_su(symbols, years, max(1, len(references)), max(1, len(tables)), trades),
        "mode": "shadow",
    }


_USAGE_READY: set[int] = set()


def ensure_usage_ledger(engine) -> bool:
    """幂等建立影子账本；失败时返回 False，不阻断回测结果接收。"""
    from sqlalchemy import text

    key = id(engine)
    if key in _USAGE_READY:
        return True
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS backtest_usage (
                    job_id BIGINT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
                    user_id BIGINT,
                    symbol_count INT NOT NULL,
                    years DOUBLE PRECISION NOT NULL,
                    factor_fields INT NOT NULL,
                    factor_tables INT NOT NULL,
                    trades INT NOT NULL,
                    estimated_su BIGINT NOT NULL,
                    actual_su BIGINT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'shadow',
                    cycle_start DATE,
                    cycle_end DATE,
                    allowance_su BIGINT NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    settled_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """))
            for column, definition in (("cycle_start", "DATE"), ("cycle_end", "DATE"),
                                       ("allowance_su", "BIGINT NOT NULL DEFAULT 0")):
                conn.execute(text(
                    f"ALTER TABLE backtest_usage ADD COLUMN IF NOT EXISTS {column} {definition}"
                ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_backtest_usage_user ON backtest_usage (user_id, created_at DESC)"
            ))
    except Exception:
        return False  # 影子账本不可用时主结果仍须可接收
    _USAGE_READY.add(key)
    return True


def record_shadow_usage(conn, job: dict[str, Any], summary: dict[str, Any], strategy_yaml: str) -> None:
    """在结果接收事务内幂等写入；单次权益任务不参与 SU 评估。"""
    from sqlalchemy import text

    if job.get("quota_pool") == "single" or job.get("entitlement_order_id"):
        return
    try:
        usage = usage_from_result(job, summary, strategy_yaml)
    except (ValueError, TypeError, AttributeError, yaml.YAMLError):
        return  # 旧策略文本或不完整结果不参与影子计量，不能阻断主结果
    if usage is None:
        return
    created = job.get("created_at")
    at = created.date() if hasattr(created, "date") else date.today()
    tier = str(job.get("tier") or ("guest" if job.get("user_id") is None else "member"))
    cycle_start, cycle_end = period_window(tier, at, job.get("member_since"))
    usage.update({"cycle_start": cycle_start, "cycle_end": cycle_end,
                  "allowance_su": allowance_su(tier)})
    conn.execute(text("""
        INSERT INTO backtest_usage (
            job_id,user_id,symbol_count,years,factor_fields,factor_tables,trades,
            estimated_su,actual_su,mode,cycle_start,cycle_end,allowance_su
        ) VALUES (
            :job_id,:user_id,:symbol_count,:years,:factor_fields,:factor_tables,:trades,
            :estimated_su,:actual_su,'shadow',:cycle_start,:cycle_end,:allowance_su
        ) ON CONFLICT (job_id) DO UPDATE SET
            symbol_count=EXCLUDED.symbol_count,years=EXCLUDED.years,
            factor_fields=EXCLUDED.factor_fields,factor_tables=EXCLUDED.factor_tables,
            trades=EXCLUDED.trades,estimated_su=EXCLUDED.estimated_su,
            actual_su=EXCLUDED.actual_su,cycle_start=EXCLUDED.cycle_start,
            cycle_end=EXCLUDED.cycle_end,allowance_su=EXCLUDED.allowance_su,settled_at=now()
    """), {"job_id": job["id"], "user_id": job.get("user_id"), **usage})


def cycle_usage(conn, user_id: int, cycle_start: date, cycle_end: date) -> dict[str, int]:
    """读取指定账号/周期的真实影子用量；仅供内部运营与后续额度闸。"""
    from sqlalchemy import text

    row = conn.execute(text("""
        SELECT count(*) AS jobs,coalesce(sum(estimated_su),0) AS estimated,
               coalesce(sum(actual_su),0) AS actual,max(allowance_su) AS allowance
        FROM backtest_usage
        WHERE user_id=:uid AND cycle_start=:start AND cycle_end=:end AND mode='shadow'
    """), {"uid": user_id, "start": cycle_start, "end": cycle_end}).mappings().one()
    return {"jobs": int(row["jobs"]), "estimated_su": int(row["estimated"]),
            "actual_su": int(row["actual"]), "allowance_su": int(row["allowance"])}
