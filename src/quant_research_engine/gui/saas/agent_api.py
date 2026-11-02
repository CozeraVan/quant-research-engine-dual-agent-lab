"""第四入口外部 AI Agent API（M1：访问令牌 + 能力信封 + 机器可读发现文档）。

边界（2026-11-02 用户设定，权威文档
`docs/superpowers/specs/2026-11-02-external-agent-api-design.md`）：

1. QRE **不自建、不调用任何模型**。智能全部在用户自带的外部 agent
   （Claude / Grok / WorkBuddy / DeepSeek 等）；本模块不含任何 LLM 调用。
2. 只做回测相关动作：发现 → 校验 → 提交 → 轮询 → 读结果 → 聚合。
   不做盯盘、下单、信号、资讯、组合管理。
3. **不做投资建议**：只提供标准化指标与聚合数字，不做显著性判定与结论生成。
   所有响应统一带 `disclaimer`。

特性开关：`QRE_AGENT_API_ENABLED`（默认关）。关闭时本蓝图所有路由返回 404，
生产在用户验收前保持 inert；测试用 `app.config["QRE_AGENT_API_ENABLED"] = "1"` 打开。

本切片（M1）只交付：令牌签发/列举/吊销、`capabilities` 成本信封、
`openapi.json`、`schema/strategy`。validate / research_runs / sweeps / jobs /
单配置提交（`POST /jobs`）属 M6 前的可选项，openapi 中以 `x-status: planned` 标注，未实现前不得声称可用。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from quant_research_engine.gui.saas.app import (  # 延迟导入在函数内，避免环
    _cfg,
    _current_user_id,
    _get_engine,
)

AGENT_API_VERSION = "v1"
AGENT_API_PREFIX = f"/api/agent/{AGENT_API_VERSION}"
TOKEN_PREFIX = "qre_agent_"
TOKEN_PREFIX_DISPLAY_LEN = 12

# 边界 3：所有响应统一携带，且聚合类端点不得输出任何解释性字段。
DISCLAIMER = "本研究结果仅供研究使用，不构成投资建议。"

DEFAULT_SCOPES = ("jobs:submit", "jobs:read", "results:read", "factors:read")
KNOWN_SCOPES = DEFAULT_SCOPES  # M2–M5 新增 scope 时同步扩充，未知 scope 一律 400

# 成本信封（设计文档 §5）。数值来源 14_LAUNCH_ROADMAP.md §10 容量基线、
# docs/agent/27_STRESS_TEST_2026-11-02.md 全期全量压测、以及 2026-11-03 M6 实测。
# B2（2026-11-03 评审发现）：原先的 est_seconds 基准是拍的，全区间档按 years/100 缩放
# 会把 4312s 的实测估成 160s，直接破坏「agent 跟用户定边界」的可信度。
# 现改为「固定开销 + 每股年耗时」两段式模型（见 _COST_MODEL），档位仅作参考锚点。
SCALE_PROFILES: list[dict[str, Any]] = [
    {
        "name": "smoke_6m",
        "universe": "1 只固定标的（600519.SH）",
        "universe_size": 1,
        "window": "近 6 个月",
        "est_seconds": 5,
        "peak_mem_mb": 1500,
        "artifact_kb": 400,
        "measured_at": "2026-11-02",
        "note": "harness 实测（3 只 smoke，job 4/5，执行 5s）",
    },
    {
        "name": "sample300_5y",
        "universe": "随机 300 只 A 股",
        "universe_size": 300,
        "window": "近 5 年",
        "est_seconds": 142,
        "peak_mem_mb": 2000,
        "artifact_kb": 900,
        "measured_at": "2026-11-03",
        "note": "两段式模型推算（85.4 + 0.03773×1500）；M6 实测 20 只×1.5 年≈86.5s/job",
    },
    {
        "name": "full_a_2y",
        "universe": "全 A 约 5860 只",
        "universe_size": 5860,
        "window": "近 2 年",
        "est_seconds": 528,
        "peak_mem_mb": 5900,
        "artifact_kb": 400000,
        "measured_at": "2026-10-03",
        "note": "两段式模型推算（85.4 + 0.03773×11720）；§10 曾实测 111s（机器/代码状态不同，待复测）",
    },
    {
        "name": "full_a_full",
        "universe": "全 A 约 5860 只",
        "universe_size": 5860,
        "window": "全区间（2009 至今）",
        "est_seconds": 3579,
        "peak_mem_mb": 13973,
        "artifact_kb": 1635200,
        "measured_at": "2026-11-02",
        "note": "item1/2/3 实测均值（3854/2571/4312s）；内存与产物取 item3 最大值",
    },
]
COST_ENVELOPE_MEASURED_AT = "2026-11-03"
COST_ENVELOPE_SOURCE = "27_STRESS_TEST_2026-11-02.md + M6 实测（2026-11-03）；两段式模型校准"

# B2 两段式成本模型：est = FIXED + RATE × stock_years
# 用两组实测点拟合：
#   小：M6 20 只 × 1.5 年 = 30 股年 → 86.5s/job
#   大：item1/2/3 均值 5201 只 × 17.8 年 = 92578 股年 → 3579s/job
# 解得 RATE=(3579-86.5)/(92578-30)=0.03773 s/股年，FIXED=86.5-RATE×30=85.4s。
_COST_MODEL = {"fixed_overhead_seconds": 85.4, "rate_per_stock_year": 0.03773}
COST_ENVELOPE_MEASURED_AT = "2026-10-03"
COST_ENVELOPE_SOURCE = "14_LAUNCH_ROADMAP.md §10 容量基线；27_STRESS_TEST_2026-11-02.md 待校准"

# M1 起的默认运营参数（设计文档 §10）。与 api_tokens 行内默认值一致，
# 这里作为发现面暴露给外部 agent，便于它在定边界时给出真实数字。
AGENT_DEFAULTS: dict[str, Any] = {
    "daily_submit_limit": 50,
    "in_flight_limit": 5,
    "rate_per_minute": 60,
    "nightly_only": True,
    "nightly_window": "00:00-06:00 Asia/Shanghai",
    "sweep_screen_universe": 300,
    "sweep_screen_window_years": 5,
    "sweep_confirm_max_configs": 5,
    "allow_full_market": False,
    "research_run_max_jobs": 200,
    "research_run_max_artifact_bytes": 20 * 1024**3,
    "research_run_max_wall_clock_hours": 12,
    "artifact_ttl_days": 15,
}

ERROR_CODES: list[dict[str, str]] = [
    {"code": "unauthorized", "http": "401", "meaning": "缺少/错误/过期/已吊销的访问令牌"},
    {"code": "forbidden_scope", "http": "403", "meaning": "令牌缺少所需 scope"},
    {"code": "not_found", "http": "404", "meaning": "资源不存在或不属于本人（与不存在同体，不泄露存在性）"},
    {"code": "invalid_yaml", "http": "400", "meaning": "YAML 或 StrategySpec 不合法"},
    {"code": "factor_limit_exceeded", "http": "400", "meaning": "超出 max_factor_fields / max_factor_tables"},
    {"code": "missing_idempotency_key", "http": "400", "meaning": "单配置提交缺少幂等键"},
    {"code": "budget_exhausted", "http": "409", "meaning": "研究会话预算用尽"},
    {"code": "stage_not_allowed", "http": "409", "meaning": "screen 阶段请求全量，或 confirm 超出配置数上限"},
    {"code": "in_flight_limit", "http": "429", "meaning": "在飞任务数超限"},
    {"code": "daily_submit_limit", "http": "429", "meaning": "每令牌每日提交数超限"},
    {"code": "rate_limited", "http": "429", "meaning": "每分钟请求数超限（响应带 Retry-After）"},
    {"code": "nightly_window", "http": "202", "meaning": "已受理，eligible_at 之后才可被认领（非错误）"},
]

_AGENT_TABLES_ENSURED: set[tuple[str, int]] = set()
_AGENT_TABLES_OK: dict[tuple[str, int], bool] = {}

agent_api_bp = Blueprint("agent_api", __name__)


# --------------------------------------------------------------------------
# 令牌工具
# --------------------------------------------------------------------------
def hash_token(plaintext: str, salt: str) -> str:
    """令牌散列：sha256("apitok:" + token + salt)。与 share_links 同族做法，
    不明文、不存前缀以外的片段。"""
    return hashlib.sha256(f"apitok:{plaintext}{salt}".encode("utf-8")).hexdigest()


def generate_token() -> str:
    """生成新令牌明文（只在创建响应返回一次）。"""
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def token_prefix(plaintext: str) -> str:
    return plaintext[:TOKEN_PREFIX_DISPLAY_LEN]


#: 每令牌限额字段：上限见 _TOKEN_LIMIT_CAPS（越界收敛），0 = 不限（仅 rate_per_minute 支持）
_TOKEN_LIMIT_FIELDS = ("daily_submit_limit", "in_flight_limit", "rate_per_minute")
_TOKEN_LIMIT_CAPS = {
    "daily_submit_limit": 1000,
    "in_flight_limit": 50,
    "rate_per_minute": 600,
}


def _normalize_token_limits(data: dict[str, Any]) -> dict[str, Any] | str:
    """归一每令牌限额：非整数/负数返回错误串；越界收敛到上限；缺省用 AGENT_DEFAULTS。"""
    limits: dict[str, Any] = {
        "daily_submit_limit": AGENT_DEFAULTS["daily_submit_limit"],
        "in_flight_limit": AGENT_DEFAULTS["in_flight_limit"],
        "rate_per_minute": AGENT_DEFAULTS["rate_per_minute"],
        "nightly_only": bool(AGENT_DEFAULTS["nightly_only"]),
    }
    for key in _TOKEN_LIMIT_FIELDS:
        if key not in data or data[key] is None:
            continue
        value = data[key]
        if isinstance(value, bool) or not isinstance(value, int):
            return f"{key} 须为整数"
        if value < 0:
            return f"{key} 不得为负"
        limits[key] = min(value, _TOKEN_LIMIT_CAPS[key])
    if "nightly_only" in data and data["nightly_only"] is not None:
        if not isinstance(data["nightly_only"], bool):
            return "nightly_only 须为布尔值"
        limits["nightly_only"] = data["nightly_only"]
    return limits


def _auth_salt(app) -> str:
    from quant_research_engine.gui.saas.app import DEFAULT_AUTH_SALT

    return _cfg(app, "SAAS_AUTH_SALT", DEFAULT_AUTH_SALT) or DEFAULT_AUTH_SALT


def ensure_api_tokens(engine) -> bool:
    """幂等确保 `api_tokens` 表存在（信息架构查询 + 进程 guard；失败返回 False 降级）。

    老库没有 apply 过 cloud_schema 时由本函数兜底，行为与
    `nl_compile_support.ensure_nl_tables` 一致；jobs 三列由启动路径的
    `_ensure_*` 系列另行补齐（缺列时按「无标签」降级，不阻断接口）。
    """
    key = ("api_tokens", id(engine))
    if key in _AGENT_TABLES_ENSURED:
        return _AGENT_TABLES_OK.get(key, False)
    from sqlalchemy import text

    ok = True
    try:
        with engine.begin() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_name = 'api_tokens'")
            ).first() is not None
            if not exists:
                conn.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS api_tokens ("
                        "id BIGSERIAL PRIMARY KEY, "
                        "user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                        "name TEXT NOT NULL, "
                        "prefix TEXT NOT NULL, "
                        "token_hash TEXT NOT NULL UNIQUE, "
                        "scopes TEXT[] NOT NULL DEFAULT ARRAY['jobs:submit','jobs:read','results:read','factors:read'], "
                        "allow_full_market BOOL NOT NULL DEFAULT false, "
                        "daily_submit_limit INT NOT NULL DEFAULT 50, "
                        "in_flight_limit INT NOT NULL DEFAULT 5, "
                        "rate_per_minute INT NOT NULL DEFAULT 60, "
                        "nightly_only BOOL NOT NULL DEFAULT true, "
                        "expires_at TIMESTAMPTZ, "
                        "revoked_at TIMESTAMPTZ, "
                        "last_used_at TIMESTAMPTZ, "
                        "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
                    )
                )
                conn.execute(
                    text("CREATE INDEX IF NOT EXISTS idx_api_tokens_user ON api_tokens (user_id, created_at DESC)")
                )
    except Exception:
        ok = False
    _AGENT_TABLES_ENSURED.add(key)
    _AGENT_TABLES_OK[key] = ok
    return ok


def authenticate_agent(app, engine):
    """解析 `Authorization: Bearer <agent token>`。

    返回 `(token_row, None)` 或 `(None, (response, status))`。
    令牌不明文落库；查表用 hash。 revoked / 过期一律 401，且不区分「不存在」
    与「已失效」的具体原因（避免探针）。
    """
    from sqlalchemy import text

    header = request.headers.get("Authorization", "")
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        return None, (jsonify(_err("unauthorized", "缺少 Bearer 访问令牌")), 401)
    plaintext = parts[1].strip()
    if not plaintext.startswith(TOKEN_PREFIX):
        # 会话 token 不是 agent 令牌：统一 401，不提示「用错令牌类型」
        return None, (jsonify(_err("unauthorized", "访问令牌无效")), 401)
    if not ensure_api_tokens(engine):
        return None, (jsonify(_err("unauthorized", "访问令牌无效")), 401)
    digest = hash_token(plaintext, _auth_salt(app))
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM api_tokens WHERE token_hash = :h"), {"h": digest}
        ).mappings().first()
    if row is None or row["revoked_at"] is not None:
        return None, (jsonify(_err("unauthorized", "访问令牌无效")), 401)
    expires_at = row["expires_at"]
    if expires_at is not None and _as_aware(expires_at) < datetime.now(timezone.utc):
        return None, (jsonify(_err("unauthorized", "访问令牌无效")), 401)
    # M4：每分钟限流（PG 原子计数；超限 429 + Retry-After，覆盖全部 agent 端点）
    limited, retry_after = _consume_rate_limit(app, engine, row)
    if limited:
        resp = jsonify(_err("rate_limited",
                            f"每分钟请求上限 {row['rate_per_minute']}，请稍后重试"))
        resp.headers["Retry-After"] = str(retry_after)
        return None, (resp, 429)
    _touch_last_used(engine, row["id"])
    return row, None


def _consume_rate_limit(app, engine, row) -> tuple[bool, int]:
    """令牌级每分钟限流：PG 原子计数，超限返回 (True,  retry_after_seconds)。

    与 `nl_compile_support` 同族做法：单条 INSERT … ON CONFLICT DO UPDATE … WHERE
    hits < limit RETURNING，已达上限不递增；表缺失时放行（降级不阻断业务）。
    """
    from sqlalchemy import text

    limit = int(row["rate_per_minute"] or 0)
    if limit <= 0:
        return False, 0
    try:
        with engine.begin() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_name = 'agent_rate_limits'")
            ).first() is not None
            if not exists:
                return False, 0
            subject = hashlib.sha256(
                f"agent:tid:{row['id']}{_auth_salt(app)}".encode("utf-8")
            ).hexdigest()[:32]
            allowed = conn.execute(
                text(
                    "INSERT INTO agent_rate_limits (scope, subject_hash, window_start, hits) "
                    "VALUES ('agent_minute', :sub, date_trunc('minute', now()), 1) "
                    "ON CONFLICT (scope, subject_hash, window_start) DO UPDATE SET "
                    "hits = agent_rate_limits.hits + 1, updated_at = now() "
                    "WHERE agent_rate_limits.hits < :lim RETURNING hits"
                ),
                {"sub": subject, "lim": limit},
            ).first()
            # 机会式清理：限流行按分钟增长，删掉 2 小时前的。
            # B5：只在每第 10 次成功计数时清理一次，避免每请求一次写。
            # 注意必须放在 INSERT 之后（allowed 已赋值），否则 NameError 会被外层
            # except 吞掉，静默把限流变成 no-op——已被回归测试抓住。
            if allowed is not None and int(allowed[0]) % 10 == 0:
                conn.execute(
                    text("DELETE FROM agent_rate_limits "
                         "WHERE window_start < date_trunc('minute', now()) - interval '2 hours'")
                )
            if allowed is not None:
                return False, 0
            row_left = conn.execute(
                text(
                    "SELECT EXTRACT(EPOCH FROM (date_trunc('minute', now()) "
                    "+ interval '1 minute' - now()))::int AS secs"
                )
            ).first()
            return True, int(row_left[0]) if row_left else 60
    except Exception:
        # 限流是容量保护而非正确性依赖：DB 异常时放行并交由令牌级日/在飞上限兜底
        return False, 0


def _log_agent_event(engine, token_id: int | None, endpoint: str, ok: bool,
                     error_class: str | None = None) -> None:
    """最小审计：只记 token_id/endpoint/ok/error_class/created_at。

    不记策略文本、不记令牌明文、不记原始 IP（与 nl_compile_events 同一纪律）；
    写失败不影响业务（静默 catch 带理由）。
    """
    from sqlalchemy import text

    try:
        with engine.begin() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_name = 'agent_api_events'")
            ).first() is not None
            if not exists:
                return
            conn.execute(
                text("INSERT INTO agent_api_events (token_id, endpoint, ok, error_class) "
                     "VALUES (:tid, :ep, :ok, :ec)"),
                {"tid": token_id, "ep": endpoint, "ok": ok, "ec": error_class},
            )
    except Exception:
        # 审计写入失败不阻断主流程
        pass


def _nightly_eligible_at(row) -> datetime | None:
    """夜间窗口：`nightly_only=true` 且当前在窗口外时，返回下一个窗口起点（Asia/Shanghai）。

    窗口内或未启用返回 None（立即可认领）。窗口配置来自 AGENT_DEFAULTS.nightly_window，
    形如 "00:00-06:00 Asia/Shanghai"；解析失败按「不限制」处理（宁可不拦，不可误拦）。
    """
    if not row["nightly_only"]:
        return None
    spec = str(AGENT_DEFAULTS.get("nightly_window") or "")
    try:
        hours, _, rest = spec.partition("-")
        start_h = int(hours.split(":")[0])
        end_part = rest.split()[0] if rest else "06:00"
        end_h = int(end_part.split(":")[0])
    except (ValueError, IndexError):
        return None
    tz = timezone(timedelta(hours=8))  # Asia/Shanghai 无 DST，固定 +8
    now_local = datetime.now(timezone.utc).astimezone(tz)
    # B4：支持跨零点窗口（如 22:00-06:00）；start > end 时按「晚段或早段」判定。
    if start_h == end_h:
        in_window = False  # 起止相同视为无开放窗口（全部顺延），配置错误可被发现
    elif start_h < end_h:
        in_window = start_h <= now_local.hour < end_h
    else:
        in_window = now_local.hour >= start_h or now_local.hour < end_h
    if in_window:
        return None
    candidate = now_local.replace(hour=start_h, minute=0, second=0, microsecond=0)
    if candidate <= now_local:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _touch_last_used(engine, token_id: int) -> None:
    """最近使用时间尽力而为更新：失败不影响请求（静默 catch 带理由）。"""
    from sqlalchemy import text

    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE api_tokens SET last_used_at = now() WHERE id = :id"), {"id": token_id}
            )
    except Exception:
        # 只读统计字段，写失败不阻断业务请求
        pass


def _require_scope(row, scope: str):
    scopes = list(row["scopes"] or [])
    if scope not in scopes:
        return jsonify(_err("forbidden_scope", f"令牌缺少 scope：{scope}")), 403
    return None


# --------------------------------------------------------------------------
# 响应封装
# --------------------------------------------------------------------------
def _ok(data: dict[str, Any], status: int = 200):
    payload = {"ok": True, "disclaimer": DISCLAIMER}
    payload.update(data)
    return jsonify(payload), status


def _err(code: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {"code": code, "message": message},
        "disclaimer": DISCLAIMER,
    }


# --------------------------------------------------------------------------
# 能力信封 / 发现文档
# --------------------------------------------------------------------------
def build_capabilities() -> dict[str, Any]:
    """成本信封：把实测容量基线机器可读化，供外部 agent 与用户对话定边界。"""
    return {
        "api_version": AGENT_API_VERSION,
        "scale_profiles": SCALE_PROFILES,
        "measured_at": COST_ENVELOPE_MEASURED_AT,
        "source": COST_ENVELOPE_SOURCE,
        "agent_defaults": AGENT_DEFAULTS,
        "constraints": {
            "engine_unchanged": True,
            "no_model_inference": True,
            "no_investment_advice": True,
            "worker_is_bottleneck": "家里 PC worker 为执行瓶颈；容量以 scale_profiles 为上限估计",
        },
        "note": "数值为历史实测估计，不承诺；实际以 job 记录为准。压测结果出来后必须校准。",
    }


def strategy_spec_json_schema() -> dict[str, Any]:
    """StrategySpec 的 JSON Schema（与 `strategies/spec.py::from_mapping` 对齐）。

    手写而非反射生成：`from_mapping` 的分节语义（哪些节必需、哪些键有默认值、
    哪些节被忽略）无法从 dataclass 字段直接还原。漂移风险由
    `tests/test_saas_agent_api.py` 的「示例策略顶层键必须被 schema 声明」用例锁定。

    注意 `additionalProperties` 为 True：`StrategySpec.from_mapping` 对未知节/键是
    容忍的（如 `experiment.frequency`、`execution.*`、`holding.direction`、
    `signal.type` 只作说明用途），schema 因此把它们声明为「可读但不由本 schema 约束」，
    外部 agent 写这些键不会因 schema 校验失败，也不保证引擎消费。
    """
    # 因子目标：`table.column` 或 `schema.table.column` 两种形态都在用
    factor_field_pattern = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,2}$"
    passthrough = {"description": "说明性字段，StrategySpec 容忍但不消费"}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "StrategySpec",
        "description": "QRE 低阶策略定义；signal.entry 为布尔表达式，因子以 data.factor_fields 声明。",
        "type": "object",
        "required": ["experiment", "data", "signal", "evaluation", "holding"],
        "additionalProperties": True,
        "properties": {
            "experiment": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "frequency": {**passthrough, "type": "string"},
                    "market_profile": {**passthrough, "type": "string"},
                    "objective": {**passthrough, "type": "string"},
                },
            },
            "data": {
                "type": "object",
                "required": ["factor_fields"],
                "properties": {
                    "market_fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": ["open", "high", "low", "close", "pre_close", "vol", "amount"],
                    },
                    "market_table": {**passthrough, "type": "string"},
                    "factor_schema": {**passthrough, "type": "string"},
                    "factor_fields": {
                        "type": "object",
                        "description": "逻辑名 -> 因子表.列，如 ema_fast: factors.stock_daily_ta.ema5",
                        "additionalProperties": {"type": "string", "pattern": factor_field_pattern},
                    },
                },
            },
            "signal": {
                "type": "object",
                "required": ["entry"],
                "properties": {
                    "type": {**passthrough, "type": "string"},
                    "entry": {"type": "string", "description": "入场布尔表达式"},
                    "exit": {"type": ["string", "null"], "description": "出场布尔表达式，可空"},
                },
            },
            "execution": {
                "type": "object",
                "properties": {
                    "signal_date": {**passthrough, "type": "string"},
                    "entry_execution": {**passthrough, "type": "string"},
                    "exit_execution": {**passthrough, "type": "string"},
                },
            },
            "evaluation": {
                "type": "object",
                "properties": {
                    "forward_return_horizons": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "default": [1, 3, 5],
                    },
                    "quantiles": {"type": ["integer", "null"]},
                    "benchmarks": {**passthrough, "type": "array"},
                },
            },
            "holding": {
                "type": "object",
                "properties": {
                    "direction": {**passthrough, "type": "string"},
                    "max_holding_days": {
                        "type": ["integer", "null"],
                        "description": "缺省=1；显式 0 或 null=不限持仓天数",
                    }
                },
            },
            "risk": {
                "type": "object",
                "properties": {
                    "stop_loss_pct": {"type": ["number", "null"], "description": "0 或 null=不启用"},
                    "take_profit_pct": {"type": ["number", "null"]},
                    "trailing_stop_pct": {"type": ["number", "null"]},
                },
            },
            "portfolio": {
                "type": "object",
                "properties": {
                    "weight_model": {"type": ["string", "null"]},
                    "score_column": {"type": ["string", "null"]},
                    "volatility_column": {"type": ["string", "null"]},
                    "rebalance_interval_days": {"type": ["integer", "null"]},
                },
            },
            "universe": {
                "type": "object",
                "properties": {
                    "market": {**passthrough, "type": "string"},
                    "exclude_st": {"type": "boolean", "default": False},
                    "exclude_suspended": {"type": "boolean", "default": False},
                    "exclude_risk_warning": {"type": "boolean", "default": False},
                    "min_listing_days": {"type": ["integer", "null"]},
                    "min_amount": {"type": ["number", "null"]},
                },
            },
        },
    }


def build_openapi() -> dict[str, Any]:
    """OpenAPI 3.0.3 文档。尚未实现的端点以 x-status: planned 标注，不得声称可用。

    注意：M4/M5 已上线，`/jobs` 单配置提交仍留 planned——外部 agent 应通过
    `/sweeps`（哪怕 grid 只有一个配置）提交任务，避免两套提交路径漂移。
    """
    envelope = {
        "type": "object",
        "properties": {
            "ok": {"type": "boolean"},
            "disclaimer": {"type": "string"},
        },
    }
    planned = {"x-status": "planned", "x-slice": "M6"}
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "QRE External Agent API",
            "version": AGENT_API_VERSION,
            "description": (
                "第四入口：供用户自带的外部 AI Agent 调用 QRE 做回测研究。"
                "QRE 不自建模型、不做投资建议，只提供执行、记账与结果聚合。"
                f"{DISCLAIMER}"
            ),
        },
        "servers": [{"url": AGENT_API_PREFIX}],
        "security": [{"bearerAuth": []}],
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "opaque",
                    "description": f"访问令牌，形如 {TOKEN_PREFIX}<43 chars>；明文只在创建时返回一次。",
                }
            },
            "schemas": {
                "Envelope": envelope,
                "Error": {
                    "type": "object",
                    "properties": {
                        "ok": {"const": False},
                        "error": {
                            "type": "object",
                            "properties": {
                                "code": {"type": "string", "enum": [e["code"] for e in ERROR_CODES]},
                                "message": {"type": "string"},
                            },
                        },
                        "disclaimer": {"type": "string"},
                    },
                },
                "StrategySpec": strategy_spec_json_schema(),
            },
        },
        "paths": {
            "/capabilities": {
                "get": {
                    "summary": "成本信封与默认参数",
                    "description": "全市场/抽样/冒烟各档的耗时、内存、产物体积估计，供定边界使用。",
                    "responses": {"200": {"description": "OK", "content": {"application/json": {}}}},
                }
            },
            "/schema/strategy": {
                "get": {
                    "summary": "StrategySpec JSON Schema",
                    "responses": {"200": {"description": "OK", "content": {"application/json": {}}}},
                }
            },
            "/openapi.json": {
                "get": {
                    "summary": "本文档自身",
                    "responses": {"200": {"description": "OK", "content": {"application/json": {}}}},
                }
            },
            "/validate": {
                "post": {
                    "summary": "校验策略与参数（不执行、不计配额）",
                    "responses": {"200": {"description": "OK"}, "400": {"description": "invalid_yaml"}},
                }
            },
            "/research-runs": {
                "post": {
                    "summary": "创建研究会话（边界/清单/预算）",
                    "responses": {"201": {"description": "created"}, "400": {"description": "invalid_yaml"}},
                },
                "get": {
                    "summary": "本人研究会话列表",
                    "responses": {"200": {"description": "OK"}},
                },
            },
            "/research-runs/{run_id}": {
                "get": {
                    "summary": "会话详情（含预算用量）",
                    "responses": {"200": {"description": "OK"}, "404": {"description": "not_found"}},
                },
            },
            "/research-runs/{run_id}/status": {
                "post": {
                    "summary": "状态迁移（planned→running→aggregated→concluded）",
                    "responses": {"200": {"description": "OK"}, "409": {"description": "illegal_transition"}},
                },
            },
            "/research-runs/{run_id}/conclusion": {
                "post": {
                    "summary": "提交结论（原样存储，QRE 不解释）",
                    "responses": {"200": {"description": "OK"}, "409": {"description": "archived"}},
                },
            },
            "/sweeps": {
                "post": {
                    "summary": "参数扫描（screen→confirm 两阶段，串行展开）",
                    "responses": {"201": {"description": "created"},
                                  "409": {"description": "stage_not_allowed / budget_exhausted"},
                                  "429": {"description": "daily_submit_limit / in_flight_limit"}},
                },
                "get": {
                    "summary": "本人扫描列表",
                    "responses": {"200": {"description": "OK"}},
                },
            },
            "/sweeps/{sweep_id}": {
                "get": {
                    "summary": "扫描详情（含子 job 状态）",
                    "responses": {"200": {"description": "OK"}, "404": {"description": "not_found"}},
                },
            },
            "/sweeps/{sweep_id}/aggregate": {
                "get": {
                    "summary": "聚合排名（只回数字，不含解读）",
                    "parameters": [{"name": "sort_by", "in": "query",
                                    "schema": {"enum": list(AGGREGATE_SORT_KEYS)}}],
                    "responses": {"200": {"description": "OK"}, "404": {"description": "not_found"}},
                },
            },
            "/jobs/{job_id}/result": {
                "get": {
                    "summary": "读取标准化结果摘要（默认不含 chart_data）",
                    "responses": {"200": {"description": "OK"}, "404": {"description": "not_found"},
                                  "409": {"description": "not_completed"}},
                }
            },
            "/jobs/{job_id}/result/chart-data": {
                "get": {
                    "summary": "按需取绘图数据（体积可能很大）",
                    "responses": {"200": {"description": "OK"}, "404": {"description": "not_found"}},
                }
            },
            "/jobs/{job_id}/artifacts/{name}": {
                "get": {
                    "summary": "受控产物下载（文件名白名单 + 路径限定 job 目录）",
                    "responses": {"200": {"description": "OK"}, "404": {"description": "not_found"}},
                }
            },
        },
        "x-error-codes": ERROR_CODES,
        "x-disclaimer": DISCLAIMER,
    }


# --------------------------------------------------------------------------
# 路由
# --------------------------------------------------------------------------
@agent_api_bp.before_request
def _gate():
    """特性开关：未显式启用时整组路由 404（生产默认 inert）。"""
    if str(_cfg(current_app, "QRE_AGENT_API_ENABLED", "0") or "0") != "1":
        return jsonify(_err("not_found", "接口未启用")), 404
    return None


@agent_api_bp.get("/capabilities")
def agent_capabilities():
    row, denied = authenticate_agent(current_app, _get_engine(current_app))
    if denied is not None:
        return denied
    scope_err = _require_scope(row, "factors:read")
    if scope_err is not None:
        return scope_err
    return _ok({"capabilities": build_capabilities()})


@agent_api_bp.get("/openapi.json")
def agent_openapi():
    row, denied = authenticate_agent(current_app, _get_engine(current_app))
    if denied is not None:
        return denied
    scope_err = _require_scope(row, "factors:read")
    if scope_err is not None:
        return scope_err
    return _ok({"openapi": build_openapi()})


@agent_api_bp.get("/schema/strategy")
def agent_schema_strategy():
    row, denied = authenticate_agent(current_app, _get_engine(current_app))
    if denied is not None:
        return denied
    scope_err = _require_scope(row, "factors:read")
    if scope_err is not None:
        return scope_err
    return _ok({"schema": strategy_spec_json_schema()})


# --------------------------------------------------------------------------
# 校验与参数扫描（M3）
# --------------------------------------------------------------------------
#: sweep screen 阶段强制约束（防一夜跑满 worker/磁盘）：抽样股票池与区间上限
SWEEP_SCREEN_MAX_RANDOM_N = 500
SWEEP_SCREEN_MAX_CODES = 500
SWEEP_SCREEN_MAX_YEARS = 5
#: confirm 阶段短名单上限（全量前必须先粗筛）
SWEEP_CONFIRM_MAX_CONFIGS = 5
#: 线性外推基准：full_a_2y 档（5860 只 × 2 年 ≈ 111s / 400MB 产物）
_COST_BASE = {"symbols": 5860, "years": 2.0, "seconds": 111.0, "artifact_kb": 400000}
#: aggregate 允许的排序键（白名单，禁排解释性字段）
AGGREGATE_SORT_KEYS = (
    "total_return", "annual_return", "sharpe", "max_drawdown", "win_rate",
    "trades", "avg_holding_days", "excess_return",
)


def _universe_size(params: dict[str, Any]) -> int | None:
    """估算标的数量：显式 codes / random_n / universe / all_market；无法判断返回 None。"""
    codes = params.get("codes")
    if isinstance(codes, str):
        codes = [c.strip() for c in codes.split(",") if c.strip()]
    if isinstance(codes, list) and codes:
        return len(codes)
    random_n = params.get("random_n")
    if random_n is not None:
        try:
            return max(1, int(random_n))
        except (TypeError, ValueError):
            return None
    if params.get("all_market"):
        return _COST_BASE["symbols"]
    if isinstance(params.get("universe"), dict) and params["universe"].get("key"):
        return _COST_BASE["symbols"]  # 板块成员数未知，按全量量级保守估计
    return None


def _window_years(params: dict[str, Any]) -> float | None:
    try:
        d0 = date.fromisoformat(str(params.get("start")))
        d1 = date.fromisoformat(str(params.get("end")))
    except (TypeError, ValueError):
        return None
    return max((d1 - d0).days / 365.25, 1 / 365.25)


def estimate_cost(params: dict[str, Any]) -> dict[str, Any]:
    """成本估计：两段式模型 `est = FIXED_OVERHEAD + RATE × stock_years`。

    模型由两组实测点拟合（M6 小样本与全期全量压测），比按区间长度等比缩放更接近真实：
    小 run 由固定开销（数据加载/绘图/序列化）主导，大 run 由每股年耗时主导。
    估计不承诺；`measured_at` 与来源随响应返回。
    """
    size = _universe_size(params)
    years = _window_years(params)
    if size is None or years is None:
        return {"profile": None, "est_seconds": None, "peak_mem_mb": None,
                "artifact_kb": None, "method": "unknown",
                "note": "无法判断股票池或区间，无法估计"}
    ordered = sorted(SCALE_PROFILES, key=lambda p: p["universe_size"])
    chosen = next((p for p in ordered if size <= p["universe_size"]), ordered[-1])
    stock_years = size * years
    fixed = _COST_MODEL["fixed_overhead_seconds"]
    rate = _COST_MODEL["rate_per_stock_year"]
    return {
        "profile": chosen["name"],
        "est_seconds": round(fixed + rate * stock_years, 1),
        "peak_mem_mb": chosen["peak_mem_mb"],
        "artifact_kb": chosen["artifact_kb"],
        "method": "two_part_model",
        "model": dict(_COST_MODEL),
        "measured_at": COST_ENVELOPE_MEASURED_AT,
        "note": f"固定开销 {fixed}s + {rate}s/股年 × {stock_years:.0f} 股年（{size} 只 × {years:.1f} 年）",
    }


def _profile_years(profile: dict[str, Any]) -> float:
    """档位对应的区间长度（年）：从 window 字段解析，解析不出返回 5。"""
    text = str(profile.get("window") or "")
    if "6 个月" in text:
        return 0.5
    if "5 年" in text:
        return 5.0
    if "2 年" in text:
        return 2.0
    if "全区间" in text:
        return 100.0
    return 5.0


@agent_api_bp.post("/validate")
def agent_validate():
    """校验策略与参数：不执行、不建 job、不计配额（设计文档 §4.2）。"""
    app = current_app
    engine = _get_engine(app)
    row, denied = authenticate_agent(app, engine)
    if denied is not None:
        return denied
    scope_err = _require_scope(row, "factors:read")
    if scope_err is not None:
        return scope_err

    from quant_research_engine.gui.engine import validate_yaml
    from quant_research_engine.gui.saas.symbol_norm import normalize_ts_codes

    data = request.get_json(silent=True) or {}
    yaml_text = str(data.get("yaml") or "").strip()
    if not yaml_text:
        return jsonify(_err("invalid_yaml", "缺少策略 yaml")), 400
    issues: list[str] = []
    verdict = validate_yaml(yaml_text)
    if not verdict.get("valid"):
        issues.append(str(verdict.get("error") or "YAML 不合法"))

    params_raw = data.get("params") or {}
    if not isinstance(params_raw, dict):
        return jsonify(_err("invalid_yaml", "params 须为对象")), 400
    params = dict(params_raw)
    if params.get("codes"):
        try:
            params["codes"] = normalize_ts_codes(params["codes"])
        except ValueError as exc:
            issues.append(str(exc))
    for key in ("start", "end"):
        if not params.get(key):
            issues.append(f"缺少 {key}")
        else:
            try:
                date.fromisoformat(str(params[key]))
            except ValueError:
                issues.append(f"{key} 须为 YYYY-MM-DD")

    from quant_research_engine.security.yaml_guard import check_factor_limits

    pol = _owner_policy(app, engine, row["user_id"])
    for issue in check_factor_limits(
        yaml_text,
        max_fields=int(pol.get("max_factor_fields", 20)),
        max_tables=int(pol.get("max_factor_tables", 3)),
    ):
        issues.append(issue)

    _log_agent_event(engine, row["id"], "POST /validate", not issues,
                    "invalid_yaml" if issues else None)
    return _ok({
        "validate": {
            "valid": not issues,
            "issues": issues,
            "normalized_params": params,
            "factor_limits": {"max_fields": int(pol.get("max_factor_fields", 20)),
                              "max_tables": int(pol.get("max_factor_tables", 3))},
            "cost_estimate": estimate_cost(params),
            "executed": False,
            "quota_charged": False,
        }
    })


def _owner_policy(app, engine, uid: int) -> dict[str, int]:
    """令牌属主的 tier 策略（与人工入口同一张 tier_policies 表）。"""
    from sqlalchemy import text

    with engine.connect() as conn:
        tier = conn.execute(
            text("SELECT tier FROM users WHERE id = :uid"), {"uid": uid}
        ).first()
    from quant_research_engine.gui.saas.app import _get_policy

    return _get_policy(app, engine, str(tier[0]) if tier else "member")


def _expand_grid(grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """笛卡尔积展开（键按名字典序，保证可复现）；空 grid 返回单条空配置。"""
    if not isinstance(grid, dict) or not grid:
        return [{}]
    keys = sorted(grid)
    pools: list[list[Any]] = []
    for key in keys:
        values = grid[key]
        if not isinstance(values, list) or not values:
            raise ValueError(f"grid.{key} 须为非空数组")
        pools.append(values)
    combos: list[dict[str, Any]] = [{}]
    for key, values in zip(keys, pools):
        combos = [{**combo, key: value} for combo in combos for value in values]
    return combos


def _apply_config_to_yaml(base_yaml: str, config: dict[str, Any]) -> str:
    """把 grid 配置写进 YAML：只支持 `data.factor_fields.<逻辑名>` 形式的点分键。

    V1 只覆盖「换因子列」这一类最常见扫描（如 EMA 周期=换 ema5/ema10/…列）；
    其余参数（持仓天数、止损等）由调用方直接改 base_yaml，不在 grid 里表达。
    """
    import yaml as _yaml

    if not config:
        return base_yaml
    raw = _yaml.safe_load(base_yaml)
    if not isinstance(raw, dict):
        raise ValueError("base_yaml 须为 mapping")
    for dotted, value in config.items():
        parts = dotted.split(".")
        if len(parts) != 3 or parts[0] != "data" or parts[1] != "factor_fields":
            raise ValueError(
                f"grid 键仅支持 data.factor_fields.<逻辑名> 形式，收到：{dotted}"
            )
        if not isinstance(raw.get("data"), dict):
            raise ValueError("base_yaml 的 data 节必须是 mapping")
        data = raw["data"]
        fields = data.setdefault("factor_fields", {})
        if not isinstance(fields, dict):
            raise ValueError("base_yaml 的 data.factor_fields 必须是 mapping")
        if parts[2] not in fields:
            raise ValueError(f"base_yaml 的 data.factor_fields 中不存在逻辑名 {parts[2]}")
        fields[parts[2]] = str(value)
    return _yaml.safe_dump(raw, allow_unicode=True, sort_keys=False)


def _token_usage(engine, token_id: int) -> dict[str, int]:
    from sqlalchemy import text

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT count(*) FILTER (WHERE created_at::date = now()::date) AS today, "
                "count(*) FILTER (WHERE status IN ('queued','leased','running','uploading')) AS in_flight "
                "FROM jobs WHERE token_id = :tid"
            ),
            {"tid": token_id},
        ).mappings().one()
    return {"today": int(row["today"] or 0), "in_flight": int(row["in_flight"] or 0)}


def _screen_guard(params: dict[str, Any]) -> str | None:
    """screen 阶段护栏：强制抽样 + 短区间，拒绝全市场/板块/超大 codes。"""
    if params.get("all_market"):
        return "screen 阶段不允许 all_market——请先用抽样股票池粗筛，再用 confirm 阶段上全量"
    if isinstance(params.get("universe"), dict) and params["universe"].get("key"):
        return "screen 阶段不允许板块/概念范围——请改用 random_n 抽样"
    codes = params.get("codes")
    if isinstance(codes, str):
        codes = [c.strip() for c in codes.split(",") if c.strip()]
    if isinstance(codes, list) and len(codes) > SWEEP_SCREEN_MAX_CODES:
        return f"screen 阶段最多 {SWEEP_SCREEN_MAX_CODES} 只显式标的（当前 {len(codes)}）"
    random_n = params.get("random_n")
    if random_n is not None:
        try:
            rn = int(random_n)
        except (TypeError, ValueError):
            return "random_n 须为整数"
        if rn < 1 or rn > SWEEP_SCREEN_MAX_RANDOM_N:
            return f"screen 阶段 random_n 须为 1~{SWEEP_SCREEN_MAX_RANDOM_N}"
    elif not codes:
        params["random_n"] = AGENT_DEFAULTS["sweep_screen_universe"]
    years = _window_years(params)
    if years is None:
        return "screen 阶段必须给出合法的 start/end"
    if years > SWEEP_SCREEN_MAX_YEARS:
        return f"screen 阶段区间不得超过 {SWEEP_SCREEN_MAX_YEARS} 年（当前 {years:.1f}）"
    return None


def _confirm_guard(budget: dict[str, Any], config_count: int) -> str | None:
    if not budget.get("allow_full_market"):
        return "confirm 阶段需要会话 budget.allow_full_market=true"
    if config_count > SWEEP_CONFIRM_MAX_CONFIGS:
        return f"confirm 阶段最多 {SWEEP_CONFIRM_MAX_CONFIGS} 个配置（当前 {config_count}）"
    return None


def _flask_app():
    from flask import current_app as _ca

    return _ca._get_current_object()


def _create_agent_jobs(
    engine,
    *,
    uid: int,
    token_id: int,
    research_run_id: int,
    sweep_id: int,
    yaml_texts: list[str],
    params: dict[str, Any],
    labels: dict[str, Any] | None,
    strategy_name: str,
    eligible_at: datetime | None = None,
) -> int:
    """把展开后的 N 个配置落成 N 条 job（串行入队；V1 无并发调度）。

    复用人工入口的同源步骤：价格口径归一 → 权重分级；
    agent job **不占用户会员日配额**（决策见 26_WEEKLY_HANDOFF §7 M3 计划），
    容量由令牌级上限与会话预算约束。
    """
    from sqlalchemy import text

    from quant_research_engine.gui.saas.app import (
        _ensure_weight_class_column,
        _unify_price_basis_yaml,
        classify_job_weight,
    )

    _ensure_weight_class_column(engine)
    # 与人工入口同源：因子配额随 params 透传，worker 执行前权威复核
    pol = _owner_policy(_flask_app(), engine, uid)
    params = dict(params)
    params["_factor_limits"] = {
        "max_fields": int(pol.get("max_factor_fields", 20)),
        "max_tables": int(pol.get("max_factor_tables", 3)),
    }
    created = 0
    with engine.begin() as conn:
        strategy_id = conn.execute(
            text("INSERT INTO strategies (user_id, name, yaml) "
                 "VALUES (:uid, :name, :yaml) RETURNING id"),
            {"uid": uid, "name": strategy_name, "yaml": yaml_texts[0]},
        ).scalar_one()
        for index, yaml_text in enumerate(yaml_texts):
            unified, _note = _unify_price_basis_yaml(yaml_text)
            weight_class = classify_job_weight("full", params)
            conn.execute(
                text(
                    "INSERT INTO jobs (user_id, strategy_id, kind, params, token_id, "
                    "research_run_id, sweep_id, labels, weight_class, eligible_at) VALUES "
                    "(:uid, :sid, 'full', CAST(:params AS jsonb), :tid, :rid, :swid, "
                    "CAST(:labels AS jsonb), :wc, :eligible)"
                ),
                {
                    "uid": uid,
                    "sid": strategy_id,
                    "params": json.dumps(params, ensure_ascii=False),
                    "tid": token_id,
                    "rid": research_run_id,
                    "swid": sweep_id,
                    "labels": json.dumps(labels or {}, ensure_ascii=False),
                    "wc": weight_class,
                    "eligible": eligible_at,
                },
            )
            created += 1
    return created


def ensure_agent_sweeps(engine) -> bool:
    """幂等确保 `agent_sweeps` 表存在（老库未 apply schema 时兜底）。"""
    from sqlalchemy import text

    key = ("agent_sweeps", id(engine))
    if key in _AGENT_TABLES_ENSURED:
        return _AGENT_TABLES_OK.get(key, False)
    ok = True
    try:
        with engine.begin() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_name = 'agent_sweeps'")
            ).first() is not None
            if not exists:
                conn.execute(text(
                    "CREATE TABLE IF NOT EXISTS agent_sweeps ("
                    "id BIGSERIAL PRIMARY KEY, "
                    "user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                    "token_id BIGINT REFERENCES api_tokens(id) ON DELETE SET NULL, "
                    "research_run_id BIGINT REFERENCES research_runs(id) ON DELETE CASCADE, "
                    "stage TEXT NOT NULL DEFAULT 'screen', "
                    "base_yaml TEXT NOT NULL, "
                    "grid JSONB NOT NULL, "
                    "params JSONB NOT NULL, "
                    "labels JSONB, "
                    "idempotency_key TEXT, "
                    "job_ids JSONB NOT NULL DEFAULT '[]'::jsonb, "
                    "status TEXT NOT NULL DEFAULT 'queued', "
                    "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"))
    except Exception:
        ok = False
    _AGENT_TABLES_ENSURED.add(key)
    _AGENT_TABLES_OK[key] = ok
    return ok


def _sweep_view(row, job_ids: list[int] | None = None,
               eligible_at: str | None = None) -> dict[str, Any]:
    view = {
        "id": row["id"],
        "external_id": row["sweep_id_external"] or f"agent-sweep-{row['id']}",
        "research_run_id": row["research_run_id"],
        "stage": row["stage"],
        "grid": row["grid"],
        "params": row["params"],
        "labels": row["labels"],
        "status": row["status"],
        "job_count": len(row["job_ids"] or []),
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }
    if job_ids is not None:
        view["job_ids"] = job_ids
    if eligible_at is not None:
        view["eligible_at"] = eligible_at
        view["note"] = "令牌启用夜间窗口，任务到点后才可被 worker 认领"
    return view


@agent_api_bp.post("/sweeps")
def agent_sweep_create():
    app = current_app
    engine = _get_engine(app)
    row, denied = authenticate_agent(app, engine)
    if denied is not None:
        return denied
    scope_err = _require_scope(row, "jobs:submit")
    if scope_err is not None:
        return scope_err
    if not (ensure_api_tokens(engine) and ensure_research_runs(engine) and ensure_agent_sweeps(engine)):
        return jsonify(_err("unauthorized", "扫描存储不可用")), 503

    from sqlalchemy import text

    data = request.get_json(silent=True) or {}
    base_yaml = str(data.get("base_yaml") or "").strip()
    if not base_yaml:
        return jsonify(_err("invalid_yaml", "缺少 base_yaml")), 400
    from quant_research_engine.gui.engine import validate_yaml

    verdict = validate_yaml(base_yaml)
    if not verdict.get("valid"):
        return jsonify(_err("invalid_yaml", str(verdict.get("error") or "YAML 不合法"))), 400

    run_id = data.get("research_run_id")
    try:
        run_id = int(run_id)
    except (TypeError, ValueError):
        return jsonify(_err("invalid_yaml", "research_run_id 须为整数")), 400
    run = _load_research_run(engine, run_id, row["user_id"])
    if run is None:
        return jsonify(_err("not_found", "研究会话不存在")), 404
    if run["status"] in ("archived", "concluded"):
        return jsonify(_err("budget_exhausted",
                            f"会话状态为 {run['status']}，不能再提交扫描")), 409

    idem = str(data.get("idempotency_key") or "").strip()
    if not idem:
        return jsonify(_err("missing_idempotency_key", "sweep 必须带 Idempotency-Key")), 400
    with engine.connect() as conn:
        existing = conn.execute(
            text("SELECT * FROM agent_sweeps WHERE token_id = :tid AND idempotency_key = :k"),
            {"tid": row["id"], "k": idem},
        ).mappings().first()
    if existing is not None:
        return _ok({"sweep": _sweep_view(existing), "deduped": True})

    params = data.get("params") or {}
    if not isinstance(params, dict):
        return jsonify(_err("invalid_yaml", "params 须为对象")), 400
    params = dict(params)
    params.setdefault("mode", "batch")
    stage = str(data.get("stage") or "screen")
    if stage not in ("screen", "confirm"):
        return jsonify(_err("invalid_yaml", "stage 须为 screen 或 confirm")), 400

    grid = data.get("grid") or {}
    try:
        combos = _expand_grid(grid)
    except ValueError as exc:
        return jsonify(_err("invalid_yaml", str(exc))), 400

    budget = dict(run["budget"] or {})
    if stage == "screen":
        guard = _screen_guard(params)
        if guard is not None:
            return jsonify(_err("stage_not_allowed", guard)), 409
    else:
        guard = _confirm_guard(budget, len(combos))
        if guard is not None:
            return jsonify(_err("stage_not_allowed", guard)), 409

    # 令牌级上限 + 会话预算预检（超限不展开）
    token_usage = _token_usage(engine, row["id"])
    if token_usage["today"] + len(combos) > int(row["daily_submit_limit"]):
        return jsonify(_err("daily_submit_limit",
                            f"今日令牌提交上限 {row['daily_submit_limit']}，已用 {token_usage['today']}，"
                            f"本次需 {len(combos)}")), 429
    if token_usage["in_flight"] + len(combos) > int(row["in_flight_limit"]):
        return jsonify(_err("in_flight_limit",
                            f"在飞任务上限 {row['in_flight_limit']}，当前 {token_usage['in_flight']}，"
                            f"本次需 {len(combos)}")), 429
    usage = research_run_usage(engine, run_id)
    if "max_jobs" in budget and usage["jobs_total"] + len(combos) > int(budget["max_jobs"]):
        return jsonify(_err("budget_exhausted",
                            f"会话 max_jobs={budget['max_jobs']}，已用 {usage['jobs_total']}，"
                            f"本次需 {len(combos)}")), 409
    if "max_wall_clock_hours" in budget:
        estimate = estimate_cost(params)
        est_hours = (estimate.get("est_seconds") or 0) * len(combos) / 3600
        if usage["wall_clock_seconds"] / 3600 + est_hours > float(budget["max_wall_clock_hours"]):
            return jsonify(_err("budget_exhausted",
                                f"会话 max_wall_clock_hours={budget['max_wall_clock_hours']}，"
                                f"已用 {usage['wall_clock_seconds'] / 3600:.2f}h，"
                                f"本次估计 {est_hours:.2f}h")), 409

    labels = data.get("labels")
    if labels is not None and not isinstance(labels, dict):
        return jsonify(_err("invalid_yaml", "labels 须为对象")), 400

    try:
        yaml_texts = [_apply_config_to_yaml(base_yaml, combo) for combo in combos]
    except ValueError as exc:
        return jsonify(_err("invalid_yaml", str(exc))), 400

    with engine.begin() as conn:
        sweep_id = conn.execute(
            text(
                "INSERT INTO agent_sweeps (user_id, token_id, research_run_id, stage, base_yaml, "
                "grid, params, labels, idempotency_key) VALUES (:uid, :tid, :rid, :stage, :yaml, "
                "CAST(:grid AS jsonb), CAST(:params AS jsonb), CAST(:labels AS jsonb), :idem) "
                "RETURNING id"
            ),
            {
                "uid": row["user_id"], "tid": row["id"], "rid": run_id, "stage": stage,
                "yaml": base_yaml,
                "grid": json.dumps(grid, ensure_ascii=False),
                "params": json.dumps(params, ensure_ascii=False),
                "labels": json.dumps(labels or {}, ensure_ascii=False),
                "idem": idem,
            },
        ).scalar_one()
        conn.execute(
            text("UPDATE agent_sweeps SET sweep_id_external = :ext WHERE id = :id"),
            {"ext": f"agent-sweep-{sweep_id}", "id": sweep_id},
        )

    eligible_at = _nightly_eligible_at(row)
    created = _create_agent_jobs(
        engine,
        uid=row["user_id"],
        token_id=row["id"],
        research_run_id=run_id,
        sweep_id=sweep_id,
        yaml_texts=yaml_texts,
        params=params,
        labels=labels,
        strategy_name=f"agent-sweep-{sweep_id}",
        eligible_at=eligible_at,
    )
    _log_agent_event(engine, row["id"], "POST /sweeps", True)
    with engine.begin() as conn:
        job_ids = [r[0] for r in conn.execute(
            text("SELECT id FROM jobs WHERE sweep_id = :sid ORDER BY id"), {"sid": sweep_id}
        ).all()]
        conn.execute(
            text("UPDATE agent_sweeps SET job_ids = CAST(:ids AS jsonb), status = 'running' "
                 "WHERE id = :id"),
            {"ids": json.dumps(job_ids), "id": sweep_id},
        )
    return _ok({"sweep": _sweep_view({
        "id": sweep_id, "sweep_id_external": f"agent-sweep-{sweep_id}",
        "research_run_id": run_id, "stage": stage, "grid": grid, "params": params,
        "labels": labels or {}, "status": "running", "job_ids": job_ids,
        "created_at": None,
    }, job_ids=job_ids, eligible_at=eligible_at.isoformat() if eligible_at else None)},
        status=202 if eligible_at is not None else 201)


@agent_api_bp.get("/sweeps")
def agent_sweep_list():
    app = current_app
    engine = _get_engine(app)
    row, denied = authenticate_agent(app, engine)
    if denied is not None:
        return denied
    scope_err = _require_scope(row, "jobs:read")
    if scope_err is not None:
        return scope_err
    if not ensure_agent_sweeps(engine):
        return _ok({"sweeps": []})

    from sqlalchemy import text

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM agent_sweeps WHERE user_id = :uid "
                 "ORDER BY created_at DESC LIMIT 100"),
            {"uid": row["user_id"]},
        ).mappings().all()
    return _ok({"sweeps": [_sweep_view(r) for r in rows]})


@agent_api_bp.get("/sweeps/<int:sweep_id>")
def agent_sweep_detail(sweep_id: int):
    app = current_app
    engine = _get_engine(app)
    row, denied = authenticate_agent(app, engine)
    if denied is not None:
        return denied
    scope_err = _require_scope(row, "jobs:read")
    if scope_err is not None:
        return scope_err
    from sqlalchemy import text

    with engine.connect() as conn:
        sweep = conn.execute(
            text("SELECT * FROM agent_sweeps WHERE id = :id AND user_id = :uid"),
            {"id": sweep_id, "uid": row["user_id"]},
        ).mappings().first()
        if sweep is None:
            return jsonify(_err("not_found", "扫描不存在")), 404
        jobs = conn.execute(
            text("SELECT id, status, progress, error_class, error_message, created_at, "
                 "finished_at FROM jobs WHERE sweep_id = :sid ORDER BY id"),
            {"sid": sweep_id},
        ).mappings().all()
    return _ok({"sweep": _sweep_view(sweep), "jobs": [_jsonable_job(j) for j in jobs]})


def _jsonable_job(job) -> dict[str, Any]:
    return {
        "id": job["id"],
        "status": job["status"],
        "progress": job["progress"],
        "error_class": job["error_class"],
        "error_message": job["error_message"],
        "created_at": job["created_at"].isoformat() if job["created_at"] else None,
        "finished_at": job["finished_at"].isoformat() if job["finished_at"] else None,
    }


@agent_api_bp.get("/sweeps/<int:sweep_id>/aggregate")
def agent_sweep_aggregate(sweep_id: int):
    """聚合：只回数字不回解读（用户边界 3）。缺字段 null，不编造、不补默认值。"""
    app = current_app
    engine = _get_engine(app)
    row, denied = authenticate_agent(app, engine)
    if denied is not None:
        return denied
    scope_err = _require_scope(row, "results:read")
    if scope_err is not None:
        return scope_err
    from sqlalchemy import text

    sort_by = str(request.args.get("sort_by") or "total_return")
    if sort_by not in AGGREGATE_SORT_KEYS:
        return jsonify(_err("invalid_yaml",
                            f"sort_by 须为 {'/'.join(AGGREGATE_SORT_KEYS)}")), 400
    with engine.connect() as conn:
        sweep = conn.execute(
            text("SELECT * FROM agent_sweeps WHERE id = :id AND user_id = :uid"),
            {"id": sweep_id, "uid": row["user_id"]},
        ).mappings().first()
        if sweep is None:
            return jsonify(_err("not_found", "扫描不存在")), 404
        jobs = conn.execute(
            text("SELECT j.id, j.status, j.labels, r.summary, r.chart_data "
                 "FROM jobs j LEFT JOIN results r ON r.job_id = j.id "
                 "WHERE j.sweep_id = :sid ORDER BY j.id"),
            {"sid": sweep_id},
        ).mappings().all()

    rows: list[dict[str, Any]] = []
    for job in jobs:
        config = (job["labels"] or {}).get("config") if isinstance(job["labels"], dict) else None
        metrics = {}
        chart = job["chart_data"] if isinstance(job["chart_data"], dict) else {}
        if isinstance(chart.get("metrics"), dict):
            metrics = chart["metrics"]
        rows.append({
            "job_id": job["id"],
            "config": config,
            "status": job["status"],
            "total_return": _num(metrics.get("total_return")),
            "annual_return": _num(metrics.get("annual_return")),
            "sharpe": _num(metrics.get("sharpe")),
            "max_drawdown": _num(metrics.get("max_drawdown")),
            "win_rate": _num(metrics.get("win_rate")),
            "trades": _num(metrics.get("trades")),
            "avg_holding_days": _num(metrics.get("avg_holding_days")),
            "excess_return": _num(metrics.get("excess_return")),
            "buy_hold_return": _num(metrics.get("buy_hold_return")),
        })
    rows.sort(key=lambda r: (r[sort_by] is None, r[sort_by] if r[sort_by] is not None else 0),
              reverse=(sort_by != "max_drawdown"))
    return _ok({
        "aggregate": {
            "sweep_id": sweep_id,
            "stage": sweep["stage"],
            "sorted_by": sort_by,
            "rows": rows,
            "completed": sum(1 for r in rows if r["status"] == "completed"),
            "total": len(rows),
            "note": "聚合仅为数值计算结果，不含任何投资建议；缺失指标为 null，未做任何填补",
        }
    })


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


# --------------------------------------------------------------------------
# 结果与产物读取（M5）
# --------------------------------------------------------------------------
#: 受控下载的文件名白名单：禁路径分隔符与点号开头，双防目录穿越
_ARTIFACT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
#: agent 产物的保留期（天）；与 D-21 归档保留期一致。过期清理绝不挂在请求路径上，
#: 由 purge_expired_agent_artifacts() 供周扫 timer 调用（见 26_WEEKLY_HANDOFF §7 M5 计划）。
AGENT_ARTIFACT_TTL_DAYS = 15


def _load_agent_job(engine, job_id: int, token_row):
    """按令牌归属读 job：本令牌创建的 job，或同属主的人工 job（令牌代表用户行事）。

    他人/不存在一律 None（路由层统一 404，不泄露存在性）。
    """
    from sqlalchemy import text

    with engine.connect() as conn:
        return conn.execute(
            text("SELECT * FROM jobs WHERE id = :id AND user_id = :uid "
                 "AND (token_id = :tid OR token_id IS NULL)"),
            {"id": job_id, "uid": token_row["user_id"], "tid": token_row["id"]},
        ).mappings().first()


def _load_agent_result(engine, job_id: int):
    from sqlalchemy import text

    with engine.connect() as conn:
        return conn.execute(
            text("SELECT * FROM results WHERE job_id = :jid"), {"jid": job_id}
        ).mappings().first()


@agent_api_bp.get("/jobs/<int:job_id>/result")
def agent_job_result(job_id: int):
    """结果摘要：默认**不返回 chart_data**（全市场产物可达数百 MB，避免打爆 agent）。"""
    app = current_app
    engine = _get_engine(app)
    row, denied = authenticate_agent(app, engine)
    if denied is not None:
        return denied
    scope_err = _require_scope(row, "results:read")
    if scope_err is not None:
        return scope_err
    job = _load_agent_job(engine, job_id, row)
    if job is None:
        return jsonify(_err("not_found", "任务不存在")), 404
    if job["status"] != "completed":
        return jsonify(_err("budget_exhausted",
                            f"任务未完成（{job['status']}）")), 409
    result = _load_agent_result(engine, job_id)
    if result is None:
        return jsonify(_err("not_found", "结果不存在")), 404
    return _ok({"result": {
        "job_id": job_id,
        "status": job["status"],
        "summary": result["summary"],
        "data_until": str(result["data_until"]) if result["data_until"] else None,
        "result_contract": result["result_contract"],
        "artifacts": result["artifacts"],
        "research_run_id": job["research_run_id"],
        "sweep_id": job["sweep_id"],
        "chart_data_url": f"{AGENT_API_PREFIX}/jobs/{job_id}/result/chart-data",
    }})


@agent_api_bp.get("/jobs/<int:job_id>/result/chart-data")
def agent_job_chart_data(job_id: int):
    """按需取绘图数据（净值曲线/回撤/热力图/归因）。体积可能很大，调用方自行决定是否拉取。"""
    app = current_app
    engine = _get_engine(app)
    row, denied = authenticate_agent(app, engine)
    if denied is not None:
        return denied
    scope_err = _require_scope(row, "results:read")
    if scope_err is not None:
        return scope_err
    job = _load_agent_job(engine, job_id, row)
    if job is None:
        return jsonify(_err("not_found", "任务不存在")), 404
    if job["status"] != "completed":
        return jsonify(_err("budget_exhausted", f"任务未完成（{job['status']}）")), 409
    result = _load_agent_result(engine, job_id)
    if result is None:
        return jsonify(_err("not_found", "结果不存在")), 404
    return _ok({"chart_data": result["chart_data"]})


@agent_api_bp.get("/jobs/<int:job_id>/artifacts/<path:name>")
def agent_job_artifact(job_id: int, name: str):
    """受控产物下载：文件名白名单 + 路径必须落在 job_<id>/ 内 + 文件必须存在。

    限速复用 M4 每分钟闸（authenticate_agent 内统一执行）。
    """
    app = current_app
    engine = _get_engine(app)
    row, denied = authenticate_agent(app, engine)
    if denied is not None:
        return denied
    scope_err = _require_scope(row, "results:read")
    if scope_err is not None:
        return scope_err
    if not _ARTIFACT_NAME_RE.match(name) or "/" in name or "\\" in name:
        return jsonify(_err("not_found", "产物不存在")), 404
    job = _load_agent_job(engine, job_id, row)
    if job is None:
        return jsonify(_err("not_found", "任务不存在")), 404
    if job["status"] != "completed":
        return jsonify(_err("budget_exhausted", f"任务未完成（{job['status']}）")), 409

    from flask import send_from_directory

    upload_root = Path(_cfg(app, "SAAS_UPLOAD_DIR", "outputs/saas_uploads") or "outputs/saas_uploads")
    job_dir = (upload_root / f"job_{job_id}").resolve()
    target = (job_dir / name).resolve()
    # 双重防穿越：解析后的真实路径必须仍在 job 目录内
    if not str(target).startswith(str(job_dir) + os.sep) or not target.is_file():
        return jsonify(_err("not_found", "产物不存在")), 404
    return send_from_directory(str(job_dir), name, as_attachment=True)


def purge_expired_agent_artifacts(engine, upload_root: Path | None = None,
                                  ttl_days: int | None = None) -> dict[str, int]:
    """清理过期的 agent 产物目录（供周扫 timer 调用；**绝不挂在请求路径上**）。

    只删「令牌创建的 job 且终态、 finished_at 早于 TTL」对应的 `job_<id>/` 目录；
    人工 job 的产物一律不碰。返回 {scanned, removed, bytes_freed, errors}。
    """
    from datetime import timedelta

    from sqlalchemy import text

    ttl = AGENT_ARTIFACT_TTL_DAYS if ttl_days is None else int(ttl_days)
    # 目录来源：显式参数 > 环境变量 > 仓库默认。刻意不读 Flask app config——周扫 timer
    # 与脚本在应用上下文之外调用，`current_app` 会直接抛 RuntimeError。
    root = upload_root or Path(os.environ.get("SAAS_UPLOAD_DIR") or "outputs/saas_uploads")
    scanned = removed = bytes_freed = errors = 0
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id FROM jobs WHERE token_id IS NOT NULL "
                    "AND status IN ('completed','failed','expired','canceled') "
                    "AND finished_at IS NOT NULL "
                    "AND finished_at < now() - make_interval(days => :ttl)"
                ),
                {"ttl": ttl},
            ).all()
    except Exception:
        return {"scanned": 0, "removed": 0, "bytes_freed": 0, "errors": 1}
    import shutil

    for (job_id,) in rows:
        scanned += 1
        job_dir = root / f"job_{job_id}"
        if not job_dir.exists():
            continue
        try:
            size = sum(f.stat().st_size for f in job_dir.rglob("*") if f.is_file())
            shutil.rmtree(job_dir)
            removed += 1
            bytes_freed += size
        except OSError:
            errors += 1
    return {"scanned": scanned, "removed": removed, "bytes_freed": bytes_freed, "errors": errors}


# --------------------------------------------------------------------------
# 研究会话 research_runs（M2）
# --------------------------------------------------------------------------
RESEARCH_STATUSES = ("planned", "running", "aggregated", "concluded", "archived")
RESEARCH_TRANSITIONS: dict[str, set[str]] = {
    "planned": {"running", "archived"},
    "running": {"aggregated", "concluded", "archived"},
    "aggregated": {"concluded", "archived"},
    "concluded": {"archived"},
    "archived": set(),
}
# budget 白名单：只接受这四个键，值不得为负；上限由 AGENT_DEFAULTS 收敛。
BUDGET_KEYS = ("max_jobs", "max_artifact_bytes", "max_wall_clock_hours", "allow_full_market")
BUDGET_CAPS: dict[str, Any] = {
    "max_jobs": AGENT_DEFAULTS["research_run_max_jobs"],
    "max_artifact_bytes": AGENT_DEFAULTS["research_run_max_artifact_bytes"],
    "max_wall_clock_hours": AGENT_DEFAULTS["research_run_max_wall_clock_hours"],
    "allow_full_market": None,  # 布尔，无上限，但需 token scope 再次确认（M3）
}


def _normalize_budget(raw: Any) -> tuple[dict[str, Any] | None, str | None]:
    """校验并收敛会话预算：未知键拒绝、负值拒绝、超过 AGENT_DEFAULTS 上限时收敛到上限。"""
    if raw is None:
        return {}, None
    if not isinstance(raw, dict):
        return None, "budget 须为对象"
    unknown = [k for k in raw if k not in BUDGET_KEYS]
    if unknown:
        return None, f"未知 budget 键：{', '.join(sorted(unknown))}"
    budget: dict[str, Any] = {}
    for key in BUDGET_KEYS:
        if key not in raw or raw[key] is None:
            continue
        value = raw[key]
        if key == "allow_full_market":
            if not isinstance(value, bool):
                return None, "allow_full_market 须为布尔值"
            budget[key] = value
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None, f"{key} 须为非负整数"
        if value < 0:
            return None, f"{key} 不得为负"
        cap = BUDGET_CAPS[key]
        if cap is not None and value > cap:
            value = cap  # 收敛到会话级上限，不报错也不放任
        budget[key] = int(value)
    return budget, None


def research_run_usage(engine, run_id: int) -> dict[str, Any]:
    """会话预算用量：任务数 / 完成数 / 产物体积 / 墙上时间。

    - 任务数与完成数：`jobs.research_run_id` 汇总；
    - 产物体积：`results.artifacts` 内 size 字段求和（缺字段按 0，不猜）；
    - 墙上时间：`finished_at - started_at` 求和（未完成任务不计，进行中任务另计 in_flight）。
    """
    from sqlalchemy import text

    with engine.connect() as conn:
        jobs = conn.execute(
            text(
                "SELECT count(*) AS total, "
                "count(*) FILTER (WHERE status = 'completed') AS completed, "
                "count(*) FILTER (WHERE status IN ('leased','running','uploading')) AS in_flight, "
                "coalesce(sum(EXTRACT(EPOCH FROM (finished_at - started_at))), 0) AS seconds "
                "FROM jobs WHERE research_run_id = :rid"
            ),
            {"rid": run_id},
        ).mappings().one()
        artifacts = conn.execute(
            text(
                "SELECT coalesce(sum((a->>'size')::numeric), 0) AS bytes "
                "FROM results r JOIN jobs j ON j.id = r.job_id "
                "CROSS JOIN LATERAL jsonb_array_elements(r.artifacts) AS a "
                "WHERE j.research_run_id = :rid"
            ),
            {"rid": run_id},
        ).mappings().one()
    return {
        "jobs_total": int(jobs["total"] or 0),
        "jobs_completed": int(jobs["completed"] or 0),
        "jobs_in_flight": int(jobs["in_flight"] or 0),
        "artifact_bytes": int(artifacts["bytes"] or 0),
        "wall_clock_seconds": round(float(jobs["seconds"] or 0), 1),
        # B3（2026-11-03 评审发现）：artifact_bytes 只统计**已回传**的产物。
        # 20MiB 回传预算静默截断（27_STRESS_TEST §8.5）会让全量 run 只回传约 1% 的产物，
        # 因此该数字**不代表真实产物体积**，artifact 预算对全量 run 实际失效。
        # 根治需要 worker 在 result/meta 里补 produced_bytes 字段（已登记 CR-2026-11-03）。
        "artifact_accounting": "uploaded_only",
    }


def _budget_exceeded(budget: dict[str, Any], usage: dict[str, Any]) -> str | None:
    """返回首个超限的预算键名；未超限返回 None。"""
    if "max_jobs" in budget and usage["jobs_total"] >= int(budget["max_jobs"]):
        return "max_jobs"
    if "max_artifact_bytes" in budget and usage["artifact_bytes"] >= int(budget["max_artifact_bytes"]):
        return "max_artifact_bytes"
    if "max_wall_clock_hours" in budget and usage["wall_clock_seconds"] >= float(budget["max_wall_clock_hours"]) * 3600:
        return "max_wall_clock_hours"
    return None


def _research_run_view(row, usage: dict[str, Any] | None = None) -> dict[str, Any]:
    view = {
        "id": row["id"],
        "title": row["title"],
        "boundary_text": row["boundary_text"],
        "todo": row["todo"],
        "budget": row["budget"],
        "status": row["status"],
        "conclusion_text": row["conclusion_text"],
        "conclusion_table": row["conclusion_table"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        "concluded_at": row["concluded_at"].isoformat() if row["concluded_at"] else None,
    }
    if usage is not None:
        view["usage"] = usage
    return view


def _load_research_run(engine, run_id: int, uid: int):
    """按 id + 归属读取会话；不存在/他人一律 None（路由层统一 404，不泄露存在性）。"""
    from sqlalchemy import text

    with engine.connect() as conn:
        return conn.execute(
            text("SELECT * FROM research_runs WHERE id = :id AND user_id = :uid"),
            {"id": run_id, "uid": uid},
        ).mappings().first()


@agent_api_bp.post("/research-runs")
def agent_research_run_create():
    app = current_app
    engine = _get_engine(app)
    row, denied = authenticate_agent(app, engine)
    if denied is not None:
        return denied
    scope_err = _require_scope(row, "jobs:submit")
    if scope_err is not None:
        return scope_err
    if not ensure_api_tokens(engine) or not ensure_research_runs(engine):
        return jsonify(_err("unauthorized", "研究会话存储不可用")), 503

    from sqlalchemy import text

    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()
    if not title:
        return jsonify(_err("invalid_yaml", "title 不能为空")), 400
    if len(title) > 120:
        return jsonify(_err("invalid_yaml", "title 过长（≤120 字符）")), 400
    boundary_text = data.get("boundary_text")
    if boundary_text is not None and not isinstance(boundary_text, str):
        return jsonify(_err("invalid_yaml", "boundary_text 须为字符串")), 400
    todo = data.get("todo")
    if todo is None:
        todo = []
    if not isinstance(todo, list):
        return jsonify(_err("invalid_yaml", "todo 须为数组")), 400
    budget, budget_err = _normalize_budget(data.get("budget"))
    if budget_err is not None:
        return jsonify(_err("invalid_yaml", budget_err)), 400

    with engine.begin() as conn:
        run_id = conn.execute(
            text(
                "INSERT INTO research_runs (user_id, token_id, title, boundary_text, todo, budget) "
                "VALUES (:uid, :tid, :title, :boundary, CAST(:todo AS jsonb), CAST(:budget AS jsonb)) "
                "RETURNING id"
            ),
            {
                "uid": row["user_id"],
                "tid": row["id"],
                "title": title,
                "boundary": boundary_text,
                "todo": json.dumps(todo, ensure_ascii=False),
                "budget": json.dumps(budget, ensure_ascii=False),
            },
        ).scalar_one()
    return _ok({"research_run": {"id": run_id, "title": title, "status": "planned",
                                 "budget": budget, "todo": todo}}, status=201)


@agent_api_bp.get("/research-runs")
def agent_research_run_list():
    app = current_app
    engine = _get_engine(app)
    row, denied = authenticate_agent(app, engine)
    if denied is not None:
        return denied
    scope_err = _require_scope(row, "jobs:read")
    if scope_err is not None:
        return scope_err
    if not ensure_research_runs(engine):
        return _ok({"research_runs": []})

    from sqlalchemy import text

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM research_runs WHERE user_id = :uid "
                 "ORDER BY created_at DESC LIMIT 100"),
            {"uid": row["user_id"]},
        ).mappings().all()
    return _ok({"research_runs": [_research_run_view(r) for r in rows]})


@agent_api_bp.get("/research-runs/<int:run_id>")
def agent_research_run_detail(run_id: int):
    app = current_app
    engine = _get_engine(app)
    row, denied = authenticate_agent(app, engine)
    if denied is not None:
        return denied
    scope_err = _require_scope(row, "jobs:read")
    if scope_err is not None:
        return scope_err
    run = _load_research_run(engine, run_id, row["user_id"])
    if run is None:
        return jsonify(_err("not_found", "研究会话不存在")), 404
    usage = research_run_usage(engine, run_id)
    budget = dict(run["budget"] or {})
    exceeded = _budget_exceeded(budget, usage)
    view = _research_run_view(run, usage)
    view["budget_exceeded"] = exceeded
    view["artifact_note"] = ("artifact_bytes 仅统计已回传产物；全量回测受 20MiB 回传预算截断时，"
                            "该值可能只有真实产物体积的约 1%，artifact 预算对全量 run 实际失效"
                            "（B3，已登记 CR-2026-11-03）")
    view["budget_remaining"] = {
        key: max(0, int(budget[key]) - usage_key)
        for key, usage_key in (
            ("max_jobs", usage["jobs_total"]),
            ("max_artifact_bytes", usage["artifact_bytes"]),
            ("max_wall_clock_hours", int(usage["wall_clock_seconds"] // 3600)),
        )
        if key in budget
    }
    return _ok({"research_run": view})


@agent_api_bp.post("/research-runs/<int:run_id>/status")
def agent_research_run_status(run_id: int):
    app = current_app
    engine = _get_engine(app)
    row, denied = authenticate_agent(app, engine)
    if denied is not None:
        return denied
    scope_err = _require_scope(row, "jobs:submit")
    if scope_err is not None:
        return scope_err
    run = _load_research_run(engine, run_id, row["user_id"])
    if run is None:
        return jsonify(_err("not_found", "研究会话不存在")), 404

    from sqlalchemy import text

    data = request.get_json(silent=True) or {}
    target = str(data.get("status") or "").strip()
    if target not in RESEARCH_STATUSES:
        return jsonify(_err("invalid_yaml", f"status 须为 {'/'.join(RESEARCH_STATUSES)}")), 400
    if target not in RESEARCH_TRANSITIONS.get(run["status"], set()):
        return jsonify(_err("budget_exhausted",
                            f"不允许的状态迁移：{run['status']} → {target}")), 409
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE research_runs SET status = :st, updated_at = now() WHERE id = :id"),
            {"st": target, "id": run_id},
        )
    return _ok({"research_run": {"id": run_id, "status": target}})


@agent_api_bp.post("/research-runs/<int:run_id>/conclusion")
def agent_research_run_conclusion(run_id: int):
    """存结论：QRE 只存不解释——不生成、不改写、不判定显著性（用户边界 3）。"""
    app = current_app
    engine = _get_engine(app)
    row, denied = authenticate_agent(app, engine)
    if denied is not None:
        return denied
    scope_err = _require_scope(row, "jobs:submit")
    if scope_err is not None:
        return scope_err
    run = _load_research_run(engine, run_id, row["user_id"])
    if run is None:
        return jsonify(_err("not_found", "研究会话不存在")), 404
    if run["status"] in ("archived",):
        return jsonify(_err("budget_exhausted", "已归档会话不可再提交结论")), 409

    from sqlalchemy import text

    data = request.get_json(silent=True) or {}
    conclusion_text = data.get("conclusion_text")
    if conclusion_text is not None and not isinstance(conclusion_text, str):
        return jsonify(_err("invalid_yaml", "conclusion_text 须为字符串")), 400
    conclusion_table = data.get("conclusion_table")
    if conclusion_table is not None and not isinstance(conclusion_table, (list, dict)):
        return jsonify(_err("invalid_yaml", "conclusion_table 须为数组或对象")), 400
    if conclusion_text is None and conclusion_table is None:
        return jsonify(_err("invalid_yaml", "conclusion_text 与 conclusion_table 至少给一个")), 400
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE research_runs SET conclusion_text = :txt, "
                "conclusion_table = CAST(:tbl AS jsonb), status = 'concluded', "
                "concluded_at = now(), updated_at = now() WHERE id = :id"
            ),
            {
                "txt": conclusion_text,
                "tbl": json.dumps(conclusion_table, ensure_ascii=False) if conclusion_table is not None else None,
                "id": run_id,
            },
        )
    _log_agent_event(engine, row["id"], "POST /conclusion", True)
    return _ok({"research_run": {"id": run_id, "status": "concluded",
                                 "stored": True,
                                 "note": "结论由外部 agent 提供，QRE 原样存储、不做解释或改写"}})


def ensure_research_runs(engine) -> bool:
    """幂等确保 `research_runs` 表存在（老库未 apply schema 时兜底）。"""
    from sqlalchemy import text

    key = ("research_runs", id(engine))
    if key in _AGENT_TABLES_ENSURED:
        return _AGENT_TABLES_OK.get(key, False)
    ok = True
    try:
        with engine.begin() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_name = 'research_runs'")
            ).first() is not None
            if not exists:
                conn.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS research_runs ("
                        "id BIGSERIAL PRIMARY KEY, "
                        "user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                        "token_id BIGINT REFERENCES api_tokens(id) ON DELETE SET NULL, "
                        "title TEXT NOT NULL, "
                        "boundary_text TEXT, "
                        "todo JSONB NOT NULL DEFAULT '[]'::jsonb, "
                        "budget JSONB NOT NULL DEFAULT '{}'::jsonb, "
                        "status TEXT NOT NULL DEFAULT 'planned', "
                        "conclusion_text TEXT, "
                        "conclusion_table JSONB, "
                        "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                        "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                        "concluded_at TIMESTAMPTZ)"
                    )
                )
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_research_runs_user "
                    "ON research_runs (user_id, created_at DESC)"))
    except Exception:
        ok = False
    _AGENT_TABLES_ENSURED.add(key)
    _AGENT_TABLES_OK[key] = ok
    return ok


# --- 令牌管理（会话鉴权，不是 agent 令牌；R-ADMIN-001：管理台可视化随 M4 上线） ---
@agent_api_bp.post("/tokens")
def agent_token_create():
    app = current_app
    engine = _get_engine(app)
    uid = _current_user_id(app, engine)
    if uid is None:
        return jsonify(_err("unauthorized", "请先登录")), 401
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip() or "未命名令牌"
    if len(name) > 64:
        return jsonify(_err("invalid_yaml", "令牌名称过长（≤64 字符）")), 400
    scopes = data.get("scopes")
    if scopes is None:
        scopes = list(DEFAULT_SCOPES)
    if not isinstance(scopes, list) or not all(isinstance(s, str) for s in scopes):
        return jsonify(_err("invalid_yaml", "scopes 须为字符串数组")), 400
    unknown = [s for s in scopes if s not in KNOWN_SCOPES]
    if unknown:
        return jsonify(_err("invalid_yaml", f"未知 scope：{', '.join(sorted(unknown))}")), 400
    allow_full_market = bool(data.get("allow_full_market", False))
    # 每令牌限额：缺省用 api_tokens 行内默认（= AGENT_DEFAULTS）；越界收敛而非报错，
    # 避免调用方因一个小错误整张令牌建不出来；0 = 不限（仅 rate_per_minute 支持）。
    limits = _normalize_token_limits(data)
    if isinstance(limits, str):
        return jsonify(_err("invalid_yaml", limits)), 400
    expires_days = data.get("expires_days")
    expires_at = None
    if expires_days is not None:
        try:
            days = int(expires_days)
        except (TypeError, ValueError):
            return jsonify(_err("invalid_yaml", "expires_days 须为整数")), 400
        if days <= 0:
            return jsonify(_err("invalid_yaml", "expires_days 须为正整数")), 400
        expires_at = datetime.now(timezone.utc) + timedelta(days=days)
    if not ensure_api_tokens(engine):
        return jsonify(_err("unauthorized", "令牌存储不可用")), 503

    from sqlalchemy import text

    # dev 后门（SAAS_DEV_AUTH=1）可能给出不存在的 uid：与人工入口同款幂等补行，
    # 避免 api_tokens 外键把整个签发打成 500。生产会话用户必然已有行，这里是 no-op。
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, phone) VALUES (:uid, :phone) "
                 "ON CONFLICT (id) DO NOTHING"),
            {"uid": uid, "phone": f"pending_{uid}"},
        )

    plaintext = generate_token()
    digest = hash_token(plaintext, _auth_salt(app))
    with engine.begin() as conn:
        token_id = conn.execute(
            text(
                "INSERT INTO api_tokens (user_id, name, prefix, token_hash, scopes, "
                "allow_full_market, expires_at, daily_submit_limit, in_flight_limit, "
                "rate_per_minute, nightly_only) VALUES (:uid, :name, :prefix, :hash, "
                "CAST(:scopes AS text[]), :afm, :exp, :daily, :flight, :rate, :nightly) "
                "RETURNING id"
            ),
            {
                "uid": uid,
                "name": name,
                "prefix": token_prefix(plaintext),
                "hash": digest,
                "scopes": scopes,
                "afm": allow_full_market,
                "exp": expires_at,
                "daily": limits["daily_submit_limit"],
                "flight": limits["in_flight_limit"],
                "rate": limits["rate_per_minute"],
                "nightly": limits["nightly_only"],
            },
        ).scalar_one()
    # 明文只在这里返回一次；后续列举/查询一律不回明文
    return _ok(
        {
            "token": {
                "id": token_id,
                "name": name,
                "prefix": token_prefix(plaintext),
                "scopes": scopes,
                "allow_full_market": allow_full_market,
                "daily_submit_limit": limits["daily_submit_limit"],
                "in_flight_limit": limits["in_flight_limit"],
                "rate_per_minute": limits["rate_per_minute"],
                "nightly_only": limits["nightly_only"],
                "expires_at": expires_at.isoformat() if expires_at else None,
                "plaintext": plaintext,
            },
            "warning": "明文令牌只显示这一次，请立即保存；丢失只能重新签发。",
        },
        status=201,
    )


@agent_api_bp.get("/tokens")
def agent_token_list():
    app = current_app
    engine = _get_engine(app)
    uid = _current_user_id(app, engine)
    if uid is None:
        return jsonify(_err("unauthorized", "请先登录")), 401
    if not ensure_api_tokens(engine):
        return _ok({"tokens": []})

    from sqlalchemy import text

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, name, prefix, scopes, allow_full_market, daily_submit_limit, "
                "in_flight_limit, rate_per_minute, nightly_only, expires_at, "
                "revoked_at, last_used_at, created_at FROM api_tokens "
                "WHERE user_id = :uid ORDER BY created_at DESC LIMIT 100"
            ),
            {"uid": uid},
        ).mappings().all()
    tokens = []
    for row in rows:
        expires_at = row["expires_at"]
        tokens.append(
            {
                "id": row["id"],
                "name": row["name"],
                "prefix": row["prefix"],
                "scopes": list(row["scopes"] or []),
                "allow_full_market": row["allow_full_market"],
                "daily_submit_limit": row["daily_submit_limit"],
                "in_flight_limit": row["in_flight_limit"],
                "rate_per_minute": row["rate_per_minute"],
                "nightly_only": row["nightly_only"],
                "expires_at": expires_at.isoformat() if expires_at else None,
                "revoked_at": row["revoked_at"].isoformat() if row["revoked_at"] else None,
                "last_used_at": row["last_used_at"].isoformat() if row["last_used_at"] else None,
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
        )
    return _ok({"tokens": tokens})


@agent_api_bp.post("/tokens/<int:token_id>/revoke")
def agent_token_revoke(token_id: int):
    app = current_app
    engine = _get_engine(app)
    uid = _current_user_id(app, engine)
    if uid is None:
        return jsonify(_err("unauthorized", "请先登录")), 401
    if not ensure_api_tokens(engine):
        return jsonify(_err("not_found", "令牌不存在")), 404

    from sqlalchemy import text

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id FROM api_tokens WHERE id = :id AND user_id = :uid"),
            {"id": token_id, "uid": uid},
        ).first()
        if row is None:
            # 他人令牌与不存在同体
            return jsonify(_err("not_found", "令牌不存在")), 404
        conn.execute(
            text("UPDATE api_tokens SET revoked_at = now() WHERE id = :id AND revoked_at IS NULL"),
            {"id": token_id},
        )
    return _ok({"token_id": token_id, "revoked": True})


def register_agent_api(app) -> None:
    """把第四入口蓝图挂到 SaaS app 上（开关关闭时路由仍注册但全部 404）。

    除了蓝图内的 before_request，还要在 **app 级**加一道前缀闸：方法不匹配时
    Flask 在路由阶段就抛 405，蓝图 before_request 不会执行，会泄露「路由存在」。
    app 级闸按路径前缀判断，与蓝图闸同源同 Flag，关闭时统一 404。
    """
    app.register_blueprint(agent_api_bp, url_prefix=AGENT_API_PREFIX)

    @app.before_request
    def _agent_api_prefix_gate() -> Any:
        if not request.path.startswith(f"{AGENT_API_PREFIX}/"):
            return None
        if str(_cfg(app, "QRE_AGENT_API_ENABLED", "0") or "0") == "1":
            return None
        return jsonify(_err("not_found", "接口未启用")), 404
