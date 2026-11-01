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
result / artifacts 属 M2–M5，openapi 中以 `x-status: planned` 标注，未实现前不得声称可用。
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
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

# 成本信封（设计文档 §5）。数值来源 14_LAUNCH_ROADMAP.md §10 容量基线与
# docs/agent/27_STRESS_TEST_2026-11-02.md 全期全量压测；压测结果出来后必须校准，
# 偏差 >50% 需在同名文档记录原因。口径：est_seconds 为串行单 job 的墙上时间估计，
# peak_mem_mb 为 worker 子进程内存峰值估计，artifact_kb 为产物体积估计。
SCALE_PROFILES: list[dict[str, Any]] = [
    {
        "name": "smoke_6m",
        "universe": "1 只固定标的（600519.SH）",
        "universe_size": 1,
        "window": "近 6 个月",
        "est_seconds": 5,
        "peak_mem_mb": 1500,
        "artifact_kb": 400,
    },
    {
        "name": "sample300_5y",
        "universe": "随机 300 只 A 股",
        "universe_size": 300,
        "window": "近 5 年",
        "est_seconds": 14,
        "peak_mem_mb": 2000,
        "artifact_kb": 900,
    },
    {
        "name": "full_a_2y",
        "universe": "全 A 约 5860 只",
        "universe_size": 5860,
        "window": "近 2 年",
        "est_seconds": 111,
        "peak_mem_mb": 5900,
        "artifact_kb": 400000,
    },
    {
        "name": "full_a_full",
        "universe": "全 A 约 5860 只",
        "universe_size": 5860,
        "window": "全区间（2009 至今）",
        "est_seconds": 900,
        "peak_mem_mb": 5900,
        "artifact_kb": 4000000,
    },
]
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
    _touch_last_used(engine, row["id"])
    return row, None


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
    """OpenAPI 3.0.3 文档。M2–M5 端点以 x-status: planned 标注，未实现不得声称可用。"""
    envelope = {
        "type": "object",
        "properties": {
            "ok": {"type": "boolean"},
            "disclaimer": {"type": "string"},
        },
    }
    planned = {"x-status": "planned", "x-slice": "M2-M5"}
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
                    **planned,
                }
            },
            "/research-runs": {
                "post": {
                    "summary": "创建研究会话（边界/清单/预算）",
                    "responses": {"201": {"description": "created"}, "409": {"description": "budget_exhausted"}},
                    **planned,
                }
            },
            "/sweeps": {
                "post": {
                    "summary": "参数扫描（screen→confirm 两阶段）",
                    "responses": {"201": {"description": "created"}, "409": {"description": "stage_not_allowed"}},
                    **planned,
                }
            },
            "/jobs": {
                "post": {
                    "summary": "单配置提交（强制 Idempotency-Key）",
                    "responses": {"201": {"description": "created"}, "400": {"description": "missing_idempotency_key"}},
                    **planned,
                }
            },
            "/jobs/{job_id}/result": {
                "get": {
                    "summary": "读取标准化结果",
                    "responses": {"200": {"description": "OK"}, "404": {"description": "not_found"}},
                    **planned,
                }
            },
            "/jobs/{job_id}/artifacts/{name}": {
                "get": {
                    "summary": "受控产物下载（白名单 + 限速 + TTL）",
                    "responses": {"200": {"description": "OK"}, "404": {"description": "not_found"}},
                    **planned,
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

    plaintext = generate_token()
    digest = hash_token(plaintext, _auth_salt(app))
    with engine.begin() as conn:
        token_id = conn.execute(
            text(
                "INSERT INTO api_tokens (user_id, name, prefix, token_hash, scopes, "
                "allow_full_market, expires_at) VALUES (:uid, :name, :prefix, :hash, "
                "CAST(:scopes AS text[]), :afm, :exp) RETURNING id"
            ),
            {
                "uid": uid,
                "name": name,
                "prefix": token_prefix(plaintext),
                "hash": digest,
                "scopes": scopes,
                "afm": allow_full_market,
                "exp": expires_at,
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
                "SELECT id, name, prefix, scopes, allow_full_market, expires_at, "
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
    """把第四入口蓝图挂到 SaaS app 上（开关关闭时路由仍注册但全部 404）。"""
    app.register_blueprint(agent_api_bp, url_prefix=AGENT_API_PREFIX)
