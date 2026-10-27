"""SaaS 版 Flask app：QRE-SAAS-002 任务队列协议 + QRE-SAAS-006 登录鉴权。

独立 app，不挂在既有 8080/8081 路由上。数据全部走 SAAS_DB_URL 指向的
云小库（deploy/saas/cloud_schema.sql），SQLAlchemy text() 参数化 SQL，
不落任何 K线/因子明细。无 Redis：队列与 session 均直接用 PG 表。

任务状态机：queued → leased →（Worker 心跳续租）→ done / failed；
lease 过期且 attempts < max_attempts 的任务可被重新认领（自动回队语义）。

鉴权（QRE-SAAS-006）：
- 用户侧：`POST /api/saas/auth/code` 发 6 位验证码 → `POST /api/saas/auth/login`
  换 session token → 之后一律 `Authorization: Bearer <token>`。
- X-User-Id 保留为 dev 后门，仅当 SAAS_DEV_AUTH=1 时可用（默认关）。
- 验证码发送层可插拔：SAAS_AUTH_CHANNEL=email（默认，SMTP STARTTLS）/
  sms（占位，未开通）/stub（测试用，发送记录落 app.extensions['sent_codes']）。
- TODO：图形验证码（内测期省略，上线前评估）。
- Worker 侧 header X-Worker-Token（SAAS_WORKER_TOKEN，未配置一律 503）。
- 游客归属（QRE-SAAS-ACCESS-HARDENING-001）：不按 IP。Cookie 缺失时应用签发随机
  HttpOnly/SameSite=Lax 会话（qre_guest_sid），归属键由其派生；旧 IP 归属结果在
  新会话首次创建任务时一次性迁移。默认私有不变。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import smtplib
import time
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from flask import Flask, g, jsonify, render_template, request, session
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from quant_research_engine.gui.saas.result_contract import (
    DAILY_RETURN_BASIS,
    TOTAL_RETURN_BASIS,
    build_result_contract,
    contract_view,
)
from quant_research_engine.gui.saas import nl_input_guard, ops_support
from quant_research_engine.gui.saas.symbol_norm import (
    normalize_ts_codes,
    resolve_ts_code,
)
from quant_research_engine.security.yaml_guard import check_factor_limits

DEFAULT_LEASE_MINUTES = 15
JOB_KINDS = ("smoke", "full")

GUI_DIR = Path(__file__).resolve().parent.parent
SAAS_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
SHARED_STATIC_DIR = GUI_DIR / "static"  # 复用 8080/8081 vendored echarts 等，不双份
AUTH_CODE_TTL_MINUTES = 5
AUTH_CODE_LENGTH = 6
SESSION_TTL_DAYS = 30
DEFAULT_AUTH_SALT = "qre-saas-dev-salt"  # 生产必须经 SAAS_AUTH_SALT 覆盖
# 限流参数（内存计数：重启清零，内测期可接受；上线如需持久再迁 PG 表）
RATE_LIMIT_TARGET_SECONDS = 60   # 同 target 60 秒内只能发 1 次
RATE_LIMIT_IP_MAX = 10           # 同 IP 每小时最多 10 次
RATE_LIMIT_IP_WINDOW = 3600
SMTP_TIMEOUT_SECONDS = 10


def _safe_saas_next(value: Any) -> str:
    from urllib.parse import urlsplit

    raw = str(value or "").strip()
    if not raw or "\\" in raw or raw.startswith("//"):
        return "/saas/"
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/saas/"):
        return "/saas/"
    return raw


class EmailSender:
    """SMTP（STARTTLS）验证码邮件。配置：SAAS_SMTP_HOST/PORT/USER/PASS/FROM。"""

    def send(self, target: str, code: str) -> None:
        host = os.environ.get("SAAS_SMTP_HOST", "")
        if not host:
            raise RuntimeError("SAAS_SMTP_HOST 未配置")
        port = int(os.environ.get("SAAS_SMTP_PORT", "465"))
        user = os.environ.get("SAAS_SMTP_USER", "")
        password = os.environ.get("SAAS_SMTP_PASS", "")
        sender = os.environ.get("SAAS_SMTP_FROM", user)
        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = target
        msg["Subject"] = "回测台登录验证码"
        msg.set_content(f"您的验证码：{code}（{AUTH_CODE_TTL_MINUTES} 分钟内有效）")
        try:
            with smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
                smtp.starttls()
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg)
        except (OSError, smtplib.SMTPException) as exc:
            raise RuntimeError(f"邮件发送失败：{exc}") from exc


class SmsSender:
    """短信通道占位：个人开发者无法申请短信签名，M2 不实现。"""

    def send(self, target: str, code: str) -> None:
        raise NotImplementedError("短信通道未开通")


class StubSender:
    """测试/开发通道：不真发，记录到 app.extensions['sent_codes']。

    env SAAS_STUB_LOG（如 /tmp/saas_codes.log）设置时同步追加
    `target code` 一行——供独立进程（本地演练/联调）读取验证码，
    生产环境严禁设置。
    """

    def __init__(self, app: Flask) -> None:
        self._app = app

    def send(self, target: str, code: str) -> None:
        self._app.extensions.setdefault("sent_codes", []).append(
            {"target": target, "code": code}
        )
        log_path = os.environ.get("SAAS_STUB_LOG")
        if log_path:
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(f"{target} {code}\n")


_SENDERS = {"email": EmailSender, "sms": SmsSender}


def _get_engine(app: Flask) -> Engine:
    engine = app.extensions.get("saas_engine")
    if engine is None:
        db_url = app.config.get("SAAS_DB_URL") or os.environ.get("SAAS_DB_URL")
        if not db_url:
            raise RuntimeError("SAAS_DB_URL 未配置")
        engine = create_engine(db_url)
        app.extensions["saas_engine"] = engine
    return engine


def _lease_minutes(app: Flask) -> float:
    try:
        return float(_cfg(app, "SAAS_LEASE_MINUTES", str(DEFAULT_LEASE_MINUTES)) or DEFAULT_LEASE_MINUTES)
    except ValueError:
        return DEFAULT_LEASE_MINUTES


def _worker_token(app: Flask) -> str | None:
    return app.config.get("SAAS_WORKER_TOKEN") or os.environ.get("SAAS_WORKER_TOKEN")


def _check_worker_auth(app: Flask) -> Any:
    """None = 通过；否则返回 (response, status)。"""
    token = _worker_token(app)
    if not token:
        return jsonify({"ok": False, "error": "SAAS_WORKER_TOKEN 未配置，worker 接口未开放"}), 503
    if request.headers.get("X-Worker-Token", "") != token:
        return jsonify({"ok": False, "error": "worker token 无效"}), 401
    return None


def _cfg(app: Flask, key: str, default: str | None = None) -> str | None:
    value = app.config.get(key)
    if value is None:
        value = os.environ.get(key, default)
    return value


def _load_saas_metadata(app: Flask) -> dict | None:
    """SaaS 元数据（因子目录+板块概念名单，QRE-SAAS-METADATA）：
    读 SAAS_METADATA_PATH（默认仓库 deploy/saas/metadata.json），按 mtime 缓存。
    文件不存在返回 None（路由回退本地 DB 口径，8081/staging 行为不变）。"""
    path = Path(
        _cfg(app, "SAAS_METADATA_PATH")
        or Path(__file__).resolve().parents[4] / "deploy" / "saas" / "metadata.json"
    )
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    cached = app.extensions.get("saas_metadata")
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    app.extensions["saas_metadata"] = (mtime, data)
    return data


def _get_sender(app: Flask) -> Any:
    channel = (_cfg(app, "SAAS_AUTH_CHANNEL", "email") or "email").strip()
    if channel == "stub":
        return StubSender(app)
    sender_cls = _SENDERS.get(channel)
    if sender_cls is None:
        raise RuntimeError(f"未知 SAAS_AUTH_CHANNEL: {channel}")
    return sender_cls()


def _auth_salt(app: Flask) -> str:
    return _cfg(app, "SAAS_AUTH_SALT", DEFAULT_AUTH_SALT) or DEFAULT_AUTH_SALT


def _code_hash(code: str, target: str, salt: str) -> str:
    return hashlib.sha256(f"{code}:{target}:{salt}".encode()).hexdigest()


def _share_token_hash(app: Flask, token: str) -> str:
    """P1 只读分享令牌哈希：完整 SHA-256（域分离前缀 + token + 现有 salt），
    64 位十六进制入库；明文 token 只在创建响应出现一次，任何接口不回显。"""
    return hashlib.sha256(f"share:{token}:{_auth_salt(app)}".encode()).hexdigest()


def _dev_auth_enabled(app: Flask) -> bool:
    return str(_cfg(app, "SAAS_DEV_AUTH", "0") or "0") == "1"


def _current_user_id(app: Flask, engine: Engine) -> int | None:
    """Bearer token → session user；SAAS_DEV_AUTH=1 时 X-User-Id 后门兜底。

    SAAS_AUTH_BYPASS=1（staging 专用，生产严禁）：免登录，全部请求以
    默认 staging 用户（email='staging@local'）身份通过，无则自动建行。
    """
    if str(_cfg(app, "SAAS_AUTH_BYPASS", "0") or "0") == "1":
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    "INSERT INTO users (email) VALUES ('staging@local') "
                    "ON CONFLICT (email) WHERE email IS NOT NULL DO NOTHING RETURNING id"
                ),
            ).first()
            if row is None:
                row = conn.execute(
                    text("SELECT id FROM users WHERE email = 'staging@local'")
                ).first()
        return int(row.id)
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[len("Bearer "):].strip()
        if token:
            with engine.connect() as conn:
                row = conn.execute(
                    text(
                        "SELECT s.user_id FROM sessions s JOIN users u ON u.id = s.user_id "
                        "WHERE s.id = :token AND s.expires_at > now() AND u.status = 'active'"
                    ),
                    {"token": token},
                ).first()
            if row is not None:
                return int(row.user_id)
            return None
    if _dev_auth_enabled(app):
        raw = request.headers.get("X-User-Id", "").strip()
        if raw:
            try:
                uid = int(raw)
            except ValueError:
                return None
            return uid if uid > 0 else None
    return None


def _require_admin(app: Flask, engine: Engine) -> tuple[int | None, Any]:
    """后台管理门禁（QRE-SAAS-ADMIN-E1E3）：返回 (uid, None) 或 (None, response)。
    未登录 401；非管理员 403（用户存在性不回显更多细节）。"""
    uid = _current_user_id(app, engine)
    if uid is None:
        return None, (jsonify({"ok": False, "error": "未登录"}), 401)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT role FROM users WHERE id = :uid"), {"uid": uid}
        ).first()
    if row is None or row.role != "admin":
        return None, (jsonify({"ok": False, "error": "无权限：仅管理员可用"}), 403)
    return uid, None


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


# 状态机与字段对齐 docs/agent/17_JOB_PROTOCOL.md（QRE-JOB-API / A2）
JOB_STATUSES = ("queued", "leased", "running", "uploading",
                "completed", "failed", "expired", "canceled")
TERMINAL_STATUSES = ("completed", "failed", "expired", "canceled")
HEARTBEAT_INTERVAL_SECONDS = 60
HARD_TIMEOUT = {"smoke": "10 minutes", "full": "6 hours"}  # 17 协议 §5，可调
UPLOAD_HARD_TIMEOUT = "30 minutes"
ERROR_CLASSES = ("strategy_compile_error", "data_missing",
                 "engine_error", "system_error", "canceled")

# --- 内测三级权限（15 号文档 D 阶段定稿，2026-09-20；2026-10-03 参数化入库） ---
MEMBER_DAILY_FULL_LIMIT = 3      # 登录会员/付费占位：每日全量回测 3 次（smoke 不占）
GUEST_DAILY_LIMIT = 1            # 游客：单 IP 每日 1 次
GUEST_MAX_CODES = 10             # 游客：最多 10 只（自选不足自动随机补齐；2026-10-04 内测调整）
GUEST_MAX_DAYS = 3650 + 7        # 游客：区间 ≤ 近 10 年（留一周宽限；2026-10-04 由近 2 年放宽）
GUEST_RESULT_NOTE = "游客结果次日清空，注册后可永久保存记录"
_PBKDF2_ITERATIONS = 120_000

# N1b/N1c 权限参数化（tier_policies 表）：角色→回测限额配置，管理台可改；
# 框架支持无限加角色行（付费阶梯留空占位）。daily_full_limit=次数/日，
# max_codes=标的数上限（0=不限），max_days=回测区间天数上限（0=不限），
# max_factor_fields / max_factor_tables=单策略因子条数/因子表数上限（0=不限）。
_TIER_POLICY_DEFAULTS = {
    "guest":  {"daily_full_limit": GUEST_DAILY_LIMIT, "max_codes": GUEST_MAX_CODES, "max_days": GUEST_MAX_DAYS,
               "max_factor_fields": 20, "max_factor_tables": 3, "scan_enabled": True, "max_watches": 20},
    # 2026-10-04 内测期权限调整（用户拍板，19 号文档原则：注册用户功能全开，
    # 限制只在并发与计算资源/R2 槽位体系）：daily_full_limit/max_codes/max_days 全 0=不限
    "member": {"daily_full_limit": 0, "max_codes": 0, "max_days": 0,
               "max_factor_fields": 20, "max_factor_tables": 3, "scan_enabled": True, "max_watches": 20},
    "paid":   {"daily_full_limit": 0, "max_codes": 0, "max_days": 0,
               "max_factor_fields": 20, "max_factor_tables": 3, "scan_enabled": True, "max_watches": 20},
}
_POLICY_KEYS = ("daily_full_limit", "max_codes", "max_days", "max_factor_fields", "max_factor_tables")
_POLICY_BOOL_KEYS = ("scan_enabled",)
_POLICY_INT_KEYS = ("max_watches",)
# 进程级"已自愈"标记：避免每次缓存未命中都重复 CREATE/ALTER（减少锁开销）
_POLICY_SCHEMA_ENSURED: set[int] = set()


def _ensure_tier_policies(engine: Engine) -> None:
    """幂等建表 + 种子行（本地/ECS 两库随服务启动自愈，cloud_schema.sql 同步维护）。"""
    key = id(engine)
    if key in _POLICY_SCHEMA_ENSURED:
        return
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS tier_policies ("
            " tier TEXT PRIMARY KEY,"
            " daily_full_limit INT NOT NULL,"
            " max_codes INT NOT NULL DEFAULT 0,"
            " max_days INT NOT NULL DEFAULT 0,"
            " max_factor_fields INT NOT NULL DEFAULT 20,"
            " max_factor_tables INT NOT NULL DEFAULT 3,"
            " updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        ))
        # 老库自愈：逐列补齐（ALTER ... IF NOT EXISTS 幂等）
        conn.execute(text("ALTER TABLE tier_policies ADD COLUMN IF NOT EXISTS max_factor_fields INT NOT NULL DEFAULT 20"))
        conn.execute(text("ALTER TABLE tier_policies ADD COLUMN IF NOT EXISTS max_factor_tables INT NOT NULL DEFAULT 3"))
        # CR-2026-10-04 模块二：信号扫描开关与每用户 watch 上限（内测期全 true/20）
        conn.execute(text("ALTER TABLE tier_policies ADD COLUMN IF NOT EXISTS scan_enabled BOOL NOT NULL DEFAULT true"))
        conn.execute(text("ALTER TABLE tier_policies ADD COLUMN IF NOT EXISTS max_watches INT NOT NULL DEFAULT 20"))
        for tier, d in _TIER_POLICY_DEFAULTS.items():
            conn.execute(
                text(
                    "INSERT INTO tier_policies (tier, daily_full_limit, max_codes, max_days, "
                    " max_factor_fields, max_factor_tables) "
                    "VALUES (:t, :l, :c, :d, :ff, :ft) ON CONFLICT (tier) DO NOTHING"
                ),
                {"t": tier, "l": d["daily_full_limit"], "c": d["max_codes"], "d": d["max_days"],
                 "ff": d["max_factor_fields"], "ft": d["max_factor_tables"]},
            )
    _POLICY_SCHEMA_ENSURED.add(key)


def _get_policy(app: Flask, engine: Engine, tier: str) -> dict[str, int]:
    """读 tier_policies（60s 缓存）；表缺失/缺行回退到常量默认，永不因配置故障拒绝服务。"""
    if not tier:
        tier = "member"
    cache = app.extensions.setdefault("tier_policy_cache", {})
    hit = cache.get(tier)
    now = time.time()
    if hit and now - hit[0] < 60:
        return hit[1]
    default = _TIER_POLICY_DEFAULTS.get(tier, _TIER_POLICY_DEFAULTS["member"])
    try:
        _ensure_tier_policies(engine)
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT daily_full_limit, max_codes, max_days, max_factor_fields, max_factor_tables, "
                     "scan_enabled, max_watches FROM tier_policies WHERE tier = :t"),
                {"t": tier},
            ).mappings().first()
        policy = dict(row) if row else dict(default)
    except Exception:
        policy = dict(default)
    cache[tier] = (now, policy)
    return policy


# --- R2 多租户弹性调度：任务轻重分级（2026-10-03，依据 N3 容量基线） ---
# 内存 ≈ 标的数 × 天数 × 因子表数：全A×2年峰值 5.79G（重），单股/小范围 ~1.5G（轻）。
# 轻任务走专属槽位，避免游客单股测试被全市场任务堵死。
JOB_WEIGHT_CLASSES = ("light", "heavy")
LIGHT_MAX_CODES = 5

# jobs.weight_class 懒自愈（同 tier_policies 模式：进程级标记防重复 ALTER）
_WEIGHT_CLASS_ENSURED: set[int] = set()


def _ensure_weight_class_column(engine: Engine) -> None:
    key = id(engine)
    if key in _WEIGHT_CLASS_ENSURED:
        return
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS weight_class TEXT NOT NULL DEFAULT 'heavy'"
        ))
    _WEIGHT_CLASS_ENSURED.add(key)


# workers.status/status_at 懒自愈（同 weight_class 模式：进程级标记防重复 ALTER）。
# R3 切片1：worker 实时状态（槽位占用/内存水位）JSONB 快照；旧库首次请求时补齐。
_WORKER_STATUS_ENSURED: set[int] = set()


def _ensure_worker_status_columns(engine: Engine) -> None:
    key = id(engine)
    if key in _WORKER_STATUS_ENSURED:
        return
    # 先查 information_schema（普通 SELECT 即可）：列已存在就完全不发 ALTER——
    # ECS 上 workers 表属 postgres（schema apply 创建），app 账号非 owner，
    # ALTER 即使 IF NOT EXISTS 命中已有列也会报 must be owner（生产实测 500）。
    with engine.begin() as conn:
        existing = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'workers' AND column_name IN ('status', 'status_at')"
                )
            )
        }
        if "status" not in existing:
            conn.execute(text("ALTER TABLE workers ADD COLUMN IF NOT EXISTS status JSONB"))
        if "status_at" not in existing:
            conn.execute(text("ALTER TABLE workers ADD COLUMN IF NOT EXISTS status_at TIMESTAMPTZ"))
    _WORKER_STATUS_ENSURED.add(key)


# R3 切片2（2026-10-04）：资源调配封装——worker_configs 表承载各 worker 的期望
# 槽位/内存闸门配置（version 单调递增），status 响应回带、管理台可编辑。
_WORKER_CONFIGS_ENSURED: set[int] = set()

_WORKER_CONFIG_KEYS = ("light_slots", "heavy_slots", "light_min_avail_mb", "heavy_min_avail_mb")


def _ensure_worker_configs(engine: Engine) -> None:
    key = id(engine)
    if key in _WORKER_CONFIGS_ENSURED:
        return
    # 先查 information_schema 再决定是否 CREATE/ALTER（同 _ensure_worker_status_columns
    # 的 owner 踩坑：ECS 上手工 apply 后表属 postgres，app 账号 CREATE/ALTER 会 500）。
    with engine.begin() as conn:
        table_exists = conn.execute(
            text("SELECT 1 FROM information_schema.tables "
                 "WHERE table_name = 'worker_configs'")
        ).first() is not None
        if not table_exists:
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS worker_configs ("
                "worker_id TEXT PRIMARY KEY, "
                "desired_light_slots INT, "
                "desired_heavy_slots INT, "
                "desired_light_min_avail_mb INT, "
                "desired_heavy_min_avail_mb INT, "
                "version INT NOT NULL DEFAULT 1, "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "updated_by TEXT)"
            ))
    _WORKER_CONFIGS_ENSURED.add(key)


# QRE-SAAS-RESULT-CONTRACT-001：结果合同列（P0-1B）。新回传结果写入
# result_contract（版本/data_until/两种收益口径/验证状态）；历史行留空，按
# result_contract.LEGACY_RESULT_CONTRACTS 显式例外表归类，不按时间猜测。
_RESULT_CONTRACT_ENSURED: set[int] = set()
_RESULT_CONTRACT_COL: dict[int, bool] = {}


def _ensure_result_contract_column(engine: Engine) -> bool:
    """尽力补齐 results.result_contract，返回该列当前是否可用。

    ECS 老库 results 表 owner 是 postgres，app 账号 ALTER 会报 must be owner
    （同 workers 表踩坑）：先查 information_schema，缺列才 ALTER；ALTER 失败
    返回 False，调用方降级——不写该列，读取时按显式例外表解析（安全方向：
    未知结果一律未验证，不会因缺列把历史结果误放行成 verified）。
    """
    key = id(engine)
    if key in _RESULT_CONTRACT_ENSURED:
        return _RESULT_CONTRACT_COL.get(key, False)
    ok = False
    try:
        with engine.begin() as conn:
            existing = {
                r[0]
                for r in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'results' AND column_name = 'result_contract'"
                    )
                )
            }
            if not existing:
                conn.execute(text("ALTER TABLE results ADD COLUMN IF NOT EXISTS result_contract JSONB"))
            ok = True
    except Exception:
        ok = False
    _RESULT_CONTRACT_ENSURED.add(key)
    _RESULT_CONTRACT_COL[key] = ok
    return ok


# QRE-SAAS-READONLY-SHARE（P1）：share_links 懒自愈。先查 information_schema
# 再 CREATE（同 _ensure_worker_configs 的 owner 踩坑：ECS 上表由 postgres apply
# cloud_schema.sql 创建，app 账号 CREATE 会 500）；CREATE 失败返回 False，
# 调用方降级为「分享通道不可用」——不报错、不降级授权，与表不存在时语义一致。
_SHARE_LINKS_ENSURED: set[int] = set()
_SHARE_LINKS_OK: dict[int, bool] = {}


def _ensure_share_links(engine: Engine) -> bool:
    key = id(engine)
    if key in _SHARE_LINKS_ENSURED:
        return _SHARE_LINKS_OK.get(key, False)
    ok = True
    try:
        with engine.begin() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_name = 'share_links'")
            ).first() is not None
            if not exists:
                conn.execute(text(
                    "CREATE TABLE IF NOT EXISTS share_links ("
                    "id BIGSERIAL PRIMARY KEY, "
                    "token_hash TEXT NOT NULL UNIQUE, "
                    "job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, "
                    "owner_id BIGINT NOT NULL REFERENCES users(id), "
                    "expires_at TIMESTAMPTZ, "
                    "revoked_at TIMESTAMPTZ, "
                    "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
                ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_share_links_job "
                    "ON share_links (job_id, created_at DESC)"))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_share_links_owner "
                    "ON share_links (owner_id, created_at DESC)"))
    except Exception:
        ok = False
    _SHARE_LINKS_ENSURED.add(key)
    _SHARE_LINKS_OK[key] = ok
    return ok


# CR-2026-10-04 模块一：策略资产化——strategies 加 entry_mode/wizard_state
_STRATEGY_ASSET_ENSURED: set[int] = set()

STRATEGY_ENTRY_MODES = ("nl", "wizard", "yaml")
ENTRY_MODE_LABELS = {"nl": "自然语言", "wizard": "自选因子", "yaml": "策略代码"}


def _ensure_strategy_asset_columns(engine: Engine) -> None:
    key = id(engine)
    if key in _STRATEGY_ASSET_ENSURED:
        return
    # information_schema 先查再 ALTER（ECS strategies 表 owner 是 postgres，同
    # workers 表踩坑）；存量推断：nl_text 非空 → nl，否则 → yaml。
    # QRE-SAAS-RESULT-ACTIONS（2026-10-05）：in_library 旗标——提交回测建行不入库，
    # 显式保存/建 watch 才进策略库；存量行 backfill true（它们本就在库）。
    with engine.begin() as conn:
        existing = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'strategies' "
                    "AND column_name IN ('entry_mode', 'wizard_state', 'in_library')"
                )
            )
        }
        if "entry_mode" not in existing:
            conn.execute(text("ALTER TABLE strategies ADD COLUMN IF NOT EXISTS entry_mode TEXT"))
        if "wizard_state" not in existing:
            conn.execute(text("ALTER TABLE strategies ADD COLUMN IF NOT EXISTS wizard_state JSONB"))
        if "in_library" not in existing:
            conn.execute(text(
                "ALTER TABLE strategies ADD COLUMN IF NOT EXISTS in_library BOOL NOT NULL DEFAULT false"))
            conn.execute(text("UPDATE strategies SET in_library = true"))  # 存量本就在库
        conn.execute(text(
            "UPDATE strategies SET entry_mode = "
            "CASE WHEN nl_text IS NOT NULL AND btrim(nl_text) <> '' THEN 'nl' ELSE 'yaml' END "
            "WHERE entry_mode IS NULL"
        ))
    _STRATEGY_ASSET_ENSURED.add(key)


# CR-2026-10-04 模块二：策略信号监控——strategy_watches / signal_events /
# users.signals_last_read_at（懒自愈，information_schema 先查再 CREATE/ALTER）
_SIGNAL_TABLES_ENSURED: set[int] = set()

WATCH_SCOPE_TYPES = ("last_run_universe", "sector", "all_a", "custom")


def _ensure_signal_tables(engine: Engine) -> None:
    key = id(engine)
    if key in _SIGNAL_TABLES_ENSURED:
        return
    with engine.begin() as conn:
        existing_tables = {
            r[0]
            for r in conn.execute(
                text("SELECT table_name FROM information_schema.tables "
                     "WHERE table_name IN ('strategy_watches', 'signal_events', 'showcase', 'showcase_daily')")
            )
        }
        if "strategy_watches" not in existing_tables:
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS strategy_watches ("
                "id BIGSERIAL PRIMARY KEY, "
                "strategy_id BIGINT NOT NULL REFERENCES strategies(id), "
                "user_id BIGINT NOT NULL REFERENCES users(id), "
                "scope_type TEXT NOT NULL DEFAULT 'last_run_universe', "
                "scope_payload JSONB, "
                "enabled BOOL NOT NULL DEFAULT true, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            ))
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_watches_strategy_user "
                "ON strategy_watches (strategy_id, user_id)"
            ))
        if "signal_events" not in existing_tables:
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS signal_events ("
                "id BIGSERIAL PRIMARY KEY, "
                "watch_id BIGINT NOT NULL REFERENCES strategy_watches(id), "
                "trade_date DATE NOT NULL, "
                "ts_code TEXT NOT NULL, "
                "signal_type TEXT NOT NULL, "
                "price NUMERIC, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            ))
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_signals_unique "
                "ON signal_events (watch_id, trade_date, ts_code, signal_type)"
            ))
        if "showcase" not in existing_tables:
            # 经典策略展示（QRE-SAAS-SHOWCASE）：job 公开放行白名单，只读
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS showcase ("
                "job_id BIGINT PRIMARY KEY REFERENCES jobs(id), "
                "title TEXT NOT NULL, "
                "subtitle TEXT, "
                "sort_order INT NOT NULL DEFAULT 0, "
                "is_active BOOL NOT NULL DEFAULT true, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            ))
        if "showcase_daily" not in existing_tables:
            # 阶段二增量日更：滚动器逐日回传的组合收益（基线 job 冻结点之后）
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS showcase_daily ("
                "job_id BIGINT NOT NULL REFERENCES jobs(id), "
                "trade_date DATE NOT NULL, "
                "daily_return DOUBLE PRECISION NOT NULL, "
                "equity DOUBLE PRECISION, "
                "n_positions INT, "
                "n_entries INT, "
                "n_exits INT, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "PRIMARY KEY (job_id, trade_date))"
            ))
        has_col = conn.execute(
            text("SELECT 1 FROM information_schema.columns "
                 "WHERE table_name = 'users' AND column_name = 'signals_last_read_at'")
        ).first() is not None
        if not has_col:
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS signals_last_read_at TIMESTAMPTZ"))
    _SIGNAL_TABLES_ENSURED.add(key)


def _norm_entry_mode(value: Any) -> str | None:
    """入参规范化：合法模式原样返回；缺省/非法返回 None（调用方按 nl_text 推断）。"""
    v = str(value or "").strip().lower()
    return v if v in STRATEGY_ENTRY_MODES else None


def _infer_entry_mode(entry_mode: Any, nl_text: Any) -> str:
    return _norm_entry_mode(entry_mode) or ("nl" if nl_text and str(nl_text).strip() else "yaml")


def _norm_wizard_state(value: Any) -> str | None:
    """wizard_state 入参：dict → JSON 字符串；None/其他 → None（不改写）。"""
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return None


def _unify_price_basis_yaml(yaml_text: str) -> tuple[str, str | None]:
    """同类指标基础价格口径统一（job#71 复盘，QRE-WIZARD-PRICE-BASIS-001）。

    向导/NL/YAML 三入口汇聚的策略 YAML 在落库/提交前，把同类指标（如
    ema 不同周期）统一到同一基础价格表（默认 close；某周期在 close 表
    缺失时整组回退到能全覆盖的价格表）。返回 (yaml, 提示|None)；
    解析失败或因子库不可用时原样返回（不阻塞主流程）。
    """
    try:
        import yaml as _yaml

        from quant_research_engine.gui.factor_wizard import (
            format_price_basis_note,
            unify_factor_price_basis,
        )
        from quant_research_engine.gui.nl_compiler import _default_column_lookup

        mapping = _yaml.safe_load(yaml_text)
        if not isinstance(mapping, dict):
            return yaml_text, None
        factor_fields = (mapping.get("data") or {}).get("factor_fields")
        if not isinstance(factor_fields, dict) or not factor_fields:
            return yaml_text, None
        lookup = _default_column_lookup()
        if lookup is None:
            return yaml_text, None
        remaps = unify_factor_price_basis(factor_fields, lookup)
        if not remaps:
            return yaml_text, None
        return (
            _yaml.safe_dump(mapping, allow_unicode=True, sort_keys=False),
            format_price_basis_note(remaps),
        )
    except Exception:
        return yaml_text, None


def _worker_config_view(row: Any) -> dict[str, Any]:
    """worker_configs 行 → API 视图（limits 键名与 worker 上报的 limits 对齐）。"""
    return _jsonable({
        "worker_id": row["worker_id"],
        "light_slots": row["desired_light_slots"],
        "heavy_slots": row["desired_heavy_slots"],
        "light_min_avail_mb": row["desired_light_min_avail_mb"],
        "heavy_min_avail_mb": row["desired_heavy_min_avail_mb"],
        "version": row["version"],
        "updated_at": row["updated_at"],
        "updated_by": row["updated_by"],
    })


def worker_config_mismatch(limits: dict[str, Any] | None,
                           desired: dict[str, Any] | None) -> bool:
    """一致性判定（R3 切片2）：worker 上报的当前生效 limits 与期望配置逐键比较。
    无期望配置 → False（不涉及）；未上报 limits（旧 worker）→ True（降级提示）。"""
    if not desired:
        return False
    if not limits:
        return True
    for k in _WORKER_CONFIG_KEYS:
        if desired.get(k) is None:
            continue  # 期望里未设的键不约束
        if limits.get(k) != desired.get(k):
            return True
    return False


def classify_job_weight(kind: str, params: dict[str, Any]) -> str:
    """任务轻重分类：smoke/小范围显式标的 → light；板块/全市场/多标的 → heavy。"""
    if kind == "smoke":
        return "light"
    if not isinstance(params, dict):
        return "heavy"
    universe = params.get("universe")
    if isinstance(universe, dict) and universe.get("key"):
        return "heavy"
    codes = params.get("codes") or []
    if isinstance(codes, str):
        codes = [c.strip() for c in codes.split(",") if c.strip()]
    if isinstance(codes, list) and 0 < len(codes) <= LIGHT_MAX_CODES:
        return "light"
    return "heavy"


def _client_ip() -> str:
    # Nginx 反代已传 X-Forwarded-For（16 号文档 C1 配置）
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _guest_key(app: Flask, ip: str) -> str:
    """旧形态游客归属键（QRE-SAAS-D1D2）：sha256(IP+salt)。

    QRE-SAAS-ACCESS-HARDENING-001 起新任务不再使用它归属（同 Wi-Fi 互见风险），
    仅保留两个用途：① 新会话首次创建任务时把同 IP 的旧结果一次性迁移到新会话；
    ② 游客 NL 编译限流计数（成本口径，与归属无关，仍按 IP）。
    """
    return hashlib.sha256(f"guest:{ip}:{_auth_salt(app)}".encode()).hexdigest()[:32]


# QRE-SAAS-ACCESS-HARDENING-001（P0-2）：游客归属从"纯 IP"改为随机会话 Cookie。
# 应用在 Cookie 缺失时自动签发随机 sid（HttpOnly + SameSite=Lax），归属键只由
# sid + 现有 salt 派生（sha256 截断 32 位，与旧 guest_key 同形同列，无 schema
# 变更）；浏览器自动携带，JS 读不到也不需要读。同 Wi-Fi 的不同浏览器/隐身窗
# 因此拿到不同 sid，结果互不可见。
GUEST_COOKIE_NAME = "qre_guest_sid"
GUEST_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 天
# Secure 标志：ECS 全站 HTTPS 建议置 1（/etc/qre-saas.env 加 SAAS_GUEST_COOKIE_SECURE=1）；
# 本地 staging 走 http，默认 0，否则浏览器不存 Cookie 会断游客链路。
GUEST_COOKIE_SECURE_DEFAULT = "0"


def _guest_cookie_secure(app: Flask) -> bool:
    return str(_cfg(app, "SAAS_GUEST_COOKIE_SECURE", GUEST_COOKIE_SECURE_DEFAULT) or "0") == "1"


def _guest_session_key(app: Flask, sid: str) -> str:
    """游客会话归属键：只由随机会话值 + 现有 salt 派生（不明文存敏感信息）。"""
    return hashlib.sha256(f"gsess:{sid}:{_auth_salt(app)}".encode()).hexdigest()[:32]


def _guest_identity(app: Flask) -> tuple[str, str | None]:
    """返回 (归属键, 需签发的 sid)。

    Cookie 缺失时生成随机 sid 并随第二元素返回——调用方必须把它 Set-Cookie 到
    响应上（_attach_guest_cookie），否则浏览器下次请求又是新会话。Cookie 存在
    时第二元素为 None（绝不轮换已有会话）。
    """
    sid = request.cookies.get(GUEST_COOKIE_NAME)
    if sid:
        return _guest_session_key(app, sid), None
    sid = secrets.token_urlsafe(32)
    return _guest_session_key(app, sid), sid


def _attach_guest_cookie(app: Flask, resp: Any, sid: str | None) -> Any:
    """把新签发的游客会话 Cookie 写到响应上（sid 为 None 时原样返回）。"""
    if sid is None:
        return resp
    resp.set_cookie(
        GUEST_COOKIE_NAME, sid,
        max_age=GUEST_COOKIE_MAX_AGE,
        httponly=True, samesite="Lax", secure=_guest_cookie_secure(app),
    )
    return resp


def _with_guest_cookie(app: Flask, err: tuple[Any, int], sid: str | None) -> tuple[Any, int]:
    """给 (response, status) 错误元组补挂游客 Cookie（sid 为 None 时原样返回）。"""
    if sid is None:
        return err
    return _attach_guest_cookie(app, err[0], sid), err[1]


def _migrate_legacy_guest_jobs(app: Flask, engine: Engine, new_key: str) -> int:
    """旧 IP 归属游客结果一次性迁移到新会话（QRE-SAAS-ACCESS-HARDENING-001）。

    仅由"新会话首次创建游客任务"触发：把同 IP 旧 key（sha256(IP+salt)）的游客
    任务改挂到新会话键下。迁移后旧 key 不再作为任何新任务的归属依据，也不再
    能访问这些结果（无 Cookie 的同 IP 请求同样 401）——历史同 IP 风险只限旧
    数据这一次，新会话彼此隔离。幂等：旧 key 行搬完后 UPDATE 影响 0 行；
    进程级 guard 避免每个请求重复扫描。返回迁移行数。
    """
    old_key = _guest_key(app, _client_ip())
    if old_key == new_key:  # 理论不可达（派生前缀不同），防御性短路
        return 0
    guard = app.extensions.setdefault("guest_migrated_old_keys", set())
    if old_key in guard:
        return 0
    with engine.begin() as conn:
        moved = conn.execute(
            text("UPDATE jobs SET guest_key = :new WHERE user_id IS NULL AND guest_key = :old"),
            {"new": new_key, "old": old_key},
        ).rowcount or 0
    guard.add(old_key)
    return moved


# 游客 NL 编译限流（QRE-SAAS-GUEST-NL）：LLM 调用有成本，游客单 IP 每日上限。
# QRE-SAAS-NL-A2A3 起主路径为 PostgreSQL 原子计数（nl_rate_limits，跨 worker/重启
# 可靠）；_guest_nl_hit 保留为无 DB 场景的本地回退，PG 故障时不得悄悄放开限流。
GUEST_NL_DAILY_LIMIT = 10
# 会员防突发（QRE-SAAS-NL-A2A3）：每日编译次数仍不限，仅 6 次/分钟；超限 429。
MEMBER_NL_MINUTE_LIMIT = 6


def _guest_nl_hit(app: Flask, ip: str) -> bool:
    """游客 NL 编译计数（legacy 文件回退，QRE-SAAS-NL-A2A3）：当日未超上限则
    计数 +1 返回 True，超限 False。仅在 PG 原子计数不可用（DB 故障/表缺失）时
    使用，避免计数故障把限流悄悄放开。"""
    import fcntl

    path = Path(os.environ.get("QRE_GUEST_NL_COUNTER", "/tmp/qre-guest-nl-counter.json"))
    key = _guest_key(app, ip)
    today = date.today().isoformat()
    try:
        with open(path, "a+", encoding="utf-8") as fh:
            fh.seek(0)
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                data = json.loads(fh.read() or "{}")
            except json.JSONDecodeError:
                data = {}
            if data.get("date") != today:
                data = {"date": today, "hits": {}}
            hits = data["hits"]
            if hits.get(key, 0) >= GUEST_NL_DAILY_LIMIT:
                return False
            hits[key] = hits.get(key, 0) + 1
            fh.seek(0)
            fh.truncate()
            fh.write(json.dumps(data))
            return True
    except OSError:
        return True  # 计数文件不可写时放行（不因此卡死游客功能）


def _password_hash(password: str, salt: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ITERATIONS)
    return f"pbkdf2${_PBKDF2_ITERATIONS}${salt}${dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        _alg, iters, salt, _hex = stored.split("$", 3)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters))
        return hmac.compare_digest(dk.hex(), _hex)
    except (ValueError, AttributeError):
        return False
NON_RETRYABLE = ("strategy_compile_error", "data_missing")


def _job_view(row: Any) -> dict[str, Any]:
    return _jsonable({
        "id": row.id,
        "user_id": row.user_id,
        "strategy_id": row.strategy_id,
        "kind": row.kind,
        "status": row.status,
        "weight_class": getattr(row, "weight_class", None),
        "params": row.params,
        "priority": row.priority,
        "attempts": row.attempts,
        "max_attempts": row.max_attempts,
        "leased_by": row.leased_by,
        "lease_expires_at": row.lease_expires_at,
        "heartbeat_at": row.heartbeat_at,
        "progress": row.progress,
        "progress_message": row.progress_message,
        "cancel_requested": row.cancel_requested,
        "error_class": row.error_class,
        "error_message": row.error_message,
        "parent_job_id": row.parent_job_id,
        "created_at": row.created_at,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
    })


# --- 任务运行态只读口径（QRE-SAAS-FIRST-SUCCESS-UX-001）---
# GET /api/jobs/<id> 与 /api/results/<id>/summary 的 409 共用同一套排队位置与
# worker 在线判定，避免两处各写一套。公网只暴露布尔 worker_online 与排队计数，
# 不暴露 worker 名称/地址/资源/内部日志。

_ACTIVE_JOB_STATUSES = ("queued", "leased", "running", "uploading")


def _queue_position(conn: Any, priority: Any, created_at: Any) -> int:
    """排队位置：同优先级按创建先后，前面还有几个 queued 任务。"""
    return conn.execute(
        text(
            "SELECT count(*) FROM jobs WHERE status = 'queued' "
            "AND (priority > :p OR (priority = :p AND created_at < :c))"
        ),
        {"p": priority, "c": created_at},
    ).scalar_one()


def _worker_online(conn: Any) -> bool:
    """worker 在线判定：任一 worker 心跳 < 3 分钟（心跳间隔 60s 的 3 倍）。"""
    return conn.execute(
        text(
            "SELECT count(*) FROM workers "
            "WHERE last_heartbeat_at > now() - interval '3 minutes'"
        ),
    ).scalar_one() > 0


def _job_runtime_fields(engine: Any, row: Any) -> dict[str, Any]:
    """按现有任务数据派生运行态字段：queue_position 仅 queued；worker_online
    仅未完成任务（终态不需要）。不读取 worker 明细，只回布尔状态。"""
    status = row["status"]
    out: dict[str, Any] = {}
    if status == "queued":
        with engine.connect() as conn:
            out["queue_position"] = _queue_position(conn, row["priority"], row["created_at"])
    if status in _ACTIVE_JOB_STATUSES:
        with engine.connect() as conn:
            out["worker_online"] = _worker_online(conn)
    return out


def _reap_expired(conn: Any) -> None:
    """惰性租约回收（17 协议 §4.2）：在 claim/heartbeat/cancel 时顺带执行，
    不起后台线程。租约过期的 leased/running/uploading 任务回队或置 failed；
    超硬超时的置 expired（终态不回队）。"""
    conn.execute(
        text(
            "UPDATE jobs SET status = 'queued', leased_by = NULL, lease_expires_at = NULL, "
            "heartbeat_at = NULL "
            "WHERE status IN ('leased','running','uploading') "
            "AND lease_expires_at < now() AND attempts < max_attempts"
        )
    )
    conn.execute(
        text(
            "UPDATE jobs SET status = 'failed', error_class = 'system_error', "
            "error_message = '租约超时且重试次数耗尽', finished_at = now(), lease_expires_at = NULL "
            "WHERE status IN ('leased','running','uploading') "
            "AND lease_expires_at < now() AND attempts >= max_attempts"
        )
    )
    # 硬超时：smoke 10min / full 6h 自 started_at 起算；uploading 单独 30min
    conn.execute(
        text(
            "UPDATE jobs SET status = 'expired', error_class = 'system_error', "
            "error_message = '超过任务硬超时', finished_at = now(), lease_expires_at = NULL "
            "WHERE (status IN ('leased','running') AND started_at IS NOT NULL AND "
            "       started_at < now() - CASE kind WHEN 'smoke' THEN interval '10 minutes' "
            "                                     ELSE interval '6 hours' END) "
            "   OR (status = 'uploading' AND heartbeat_at < now() - interval '30 minutes')"
        )
    )


def _touch_worker(conn: Any, worker_id: str) -> None:
    """worker 在线落账（E3）：claim/heartbeat 时 upsert workers 表，
    在线判定 = last_heartbeat_at 距今 < 3 分钟（心跳间隔 60s 的 3 倍）。"""
    if not worker_id:
        return
    conn.execute(
        text(
            "INSERT INTO workers (name, last_heartbeat_at) VALUES (:wid, now()) "
            "ON CONFLICT (name) DO UPDATE SET last_heartbeat_at = now()"
        ),
        {"wid": worker_id},
    )


def create_saas_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(SAAS_TEMPLATE_DIR),
        static_folder=str(SHARED_STATIC_DIR),
        static_url_path="/static",
    )
    app.config["SECRET_KEY"] = os.urandom(24)
    # 模板热加载（本地 staging 调文案用）：QRE_TEMPLATE_AUTORELOAD=1 时每次请求
    # 重读模板，改完 Ctrl+S 刷新即生效；生产 ECS 不设置该变量（保持缓存性能）
    if os.environ.get("QRE_TEMPLATE_AUTORELOAD") == "1":
        app.config["TEMPLATES_AUTO_RELOAD"] = True
    # 验证码限流计数（内存：重启清零，内测期可接受）
    app.extensions["rate_limit"] = {"target": {}, "ip": {}}

    @app.context_processor
    def _inject_saas_flags() -> dict[str, Any]:
        # SAAS_AUTH_BYPASS 注入模板（QRE-SAAS-009 修复：bypass 下前端
        # requireLogin 无 token 跳登录页 × 登录页 302 回工作台 = 无限刷新环）
        return {"saas_auth_bypass": str(_cfg(app, "SAAS_AUTH_BYPASS", "0") or "0") == "1"}

    # 静态资源缓存破除（2026-10-04）：/static/ 有 nginx expires 1h + 浏览器
    # 内存缓存，部署后用户可能拿到旧 JS/CSS（重播布局错位即此类事故）。
    # 进程启动时间戳作版本号——每次部署 restart 即全量刷新客户端缓存。
    app.extensions["asset_v"] = str(int(time.time()))

    @app.context_processor
    def _inject_asset_v() -> dict[str, Any]:
        return {"asset_v": app.extensions["asset_v"]}

    @app.errorhandler(RuntimeError)
    def _runtime_error(exc: RuntimeError) -> Any:  # SAAS_DB_URL 缺失等配置错误
        return jsonify({"ok": False, "error": str(exc)}), 503

    # N4 安全响应头（QRE-SAAS-SEC-HARDEN）：防 MIME 嗅探/点击劫持/来源泄漏
    @app.after_request
    def _security_headers(resp: Any) -> Any:
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        # HTML 页面禁启发式缓存：旧 HTML 会引用旧 asset_v 的静态资源，
        # 部署后用户可能一直看到旧页面（2026-10-20 因子布局"没有变化"即此类）。
        # 静态 /static/* 自带 ?v=asset_v 版本号，不受影响。
        if resp.mimetype == "text/html":
            resp.headers.setdefault("Cache-Control", "no-cache")
        return resp

    # --- 页面（QRE-SAAS-004 四功能前端；页面本身不鉴权，JS 检查 localStorage
    #     token，401 时跳 /saas/login；数据全走 /api/saas/* Bearer 鉴权） ---

    @app.context_processor
    def _saas_template_ctx() -> dict[str, Any]:
        # 免登录开关注入模板（staging）：JS 据此跳过 token 检查与登录页跳转
        return {"auth_bypass": str(_cfg(app, "SAAS_AUTH_BYPASS", "0") or "0") == "1"}

    @app.get("/")
    def saas_root() -> Any:
        # SaaS 应用根路径直接进工作台（8081 staging 单用途端口）
        from flask import redirect

        return redirect("/saas/")

    # PWA（QRE-SAAS-PWA）：manifest 与 service worker 必须挂在站点根路径
    #（sw.js 若只在 /static/ 下，作用域被限制在 /static/，无法控制整站安装提示）
    @app.get("/manifest.json")
    def pwa_manifest() -> Any:
        from flask import send_from_directory

        return send_from_directory(str(SHARED_STATIC_DIR), "manifest.json", mimetype="application/manifest+json")

    @app.get("/sw.js")
    def pwa_service_worker() -> Any:
        from flask import send_from_directory

        return send_from_directory(str(SHARED_STATIC_DIR), "sw.js", mimetype="application/javascript")

    # SEO（QRE-SAAS-SEO）：robots.txt 与 sitemap.xml 需挂站点根路径，搜索引擎爬虫只认根
    @app.get("/robots.txt")
    def seo_robots() -> Any:
        from flask import send_from_directory

        return send_from_directory(str(SHARED_STATIC_DIR), "robots.txt", mimetype="text/plain")

    @app.get("/sitemap.xml")
    def seo_sitemap() -> Any:
        from flask import send_from_directory

        return send_from_directory(str(SHARED_STATIC_DIR), "sitemap.xml", mimetype="application/xml")

    # 百度站长文件验证（QRE-SAAS-SEO）：验证文件必须挂根路径
    @app.get("/baidu_verify_codeva-gDNoSKn1Mp.html")
    def seo_baidu_verify() -> Any:
        from flask import send_from_directory

        return send_from_directory(str(SHARED_STATIC_DIR), "baidu_verify_codeva-gDNoSKn1Mp.html", mimetype="text/html")

    # Google Search Console 文件验证（2026-10-04）：同百度，挂根路径
    @app.get("/google706490730bf04d58.html")
    def seo_google_verify() -> Any:
        from flask import send_from_directory

        return send_from_directory(str(SHARED_STATIC_DIR), "google706490730bf04d58.html", mimetype="text/html")

    @app.get("/saas/login")
    def saas_login_page() -> Any:
        # staging 免登录（SAAS_AUTH_BYPASS=1，生产严禁）：登录页直接跳工作台
        if str(_cfg(app, "SAAS_AUTH_BYPASS", "0") or "0") == "1":
            from flask import redirect

            return redirect("/saas/")
        return render_template(
            "login.html", login_next=_safe_saas_next(request.args.get("next"))
        )

    @app.get("/saas/")
    def saas_dashboard_page() -> str:
        return render_template("dashboard.html")

    # QRE-SAAS-PROFILE：个人信息页（账号/会员/配额 + 内嵌回测记录）
    @app.get("/saas/profile")
    def saas_profile_page() -> str:
        return render_template("profile.html")

    @app.get("/saas/new")
    def saas_new_page() -> str:
        return render_template("new.html")

    # QRE-SAAS-SHOWCASE：经典策略展示页（游客可见、全站只读、无操作入口）
    @app.get("/saas/showcase")
    def saas_showcase_page() -> str:
        return render_template("showcase.html")

    # QRE-SAAS-RESULT-UNDERSTANDING：公开「使用说明」集中帮助页。游客与登录用户
    # 均可访问（不新增 API / 表 / 鉴权门槛）；结果合同两种收益口径文案由
    # result_contract 常量同源注入，避免页面与 API 措辞漂移。
    @app.get("/saas/help")
    def saas_help_page() -> str:
        return render_template(
            "help.html",
            daily_return_basis=DAILY_RETURN_BASIS,
            total_return_basis=TOTAL_RETURN_BASIS,
        )

    @app.get("/api/saas/showcase")
    def api_showcase_list() -> Any:
        """经典策略公开展示列表（无需登录）。返回白名单 job 的摘要指标。

        QRE-SAAS-RESULT-CONTRACT-001：只公开**结果合同 verified** 的条目；
        未验证条目仅从公开列表消失——showcase 白名单行、job 与产物一律不动
        （管理台 /api/saas/console/showcase 仍可见并带未验证原因）。
        """
        engine = _get_engine(app)
        _ensure_signal_tables(engine)
        contract_col = (", r.result_contract AS result_result_contract"
                        if _ensure_result_contract_column(engine) else "")
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT sc.job_id, sc.title, sc.subtitle, sc.sort_order, "
                    "s.name AS strategy_name, j.created_at, j.params, "
                    "r.summary, r.chart_data, r.data_until" + contract_col +
                    " FROM showcase sc "
                    "JOIN jobs j ON j.id = sc.job_id "
                    "JOIN strategies s ON s.id = j.strategy_id "
                    "LEFT JOIN results r ON r.job_id = j.id "
                    "WHERE sc.is_active AND j.status = 'completed' "
                    "ORDER BY sc.sort_order, sc.job_id"
                )
            ).mappings().all()
            items = []
            for row in rows:
                # 显式合同 / 例外表判定；未验证直接跳过（不删白名单行、不删产物）
                contract = contract_view(row["job_id"], row.get("result_result_contract"),
                                         row["data_until"])
                if not contract["verified"]:
                    continue
                metrics = ((row["chart_data"] or {}).get("metrics") or {})
                summary = row["summary"] or {}
                params = row["params"] or {}
                # 阶段二持续跟踪：冻结点之后的逐日收益复利延伸到最新交易日
                daily_rows = conn.execute(
                    text("SELECT trade_date, daily_return FROM showcase_daily "
                         "WHERE job_id = :id ORDER BY trade_date"),
                    {"id": row["job_id"]},
                ).mappings().all()
                total_return = summary.get("strategy_total_return")
                tracking_since = None
                if daily_rows:
                    ext = 1.0 + (total_return or 0.0)
                    for d in daily_rows:
                        ext *= 1.0 + float(d["daily_return"])
                    total_return = ext - 1.0
                    tracking_since = _jsonable(daily_rows[0]["trade_date"])
                    data_until = _jsonable(daily_rows[-1]["trade_date"])
                else:
                    data_until = _jsonable(row["data_until"])
                items.append({
                    "job_id": row["job_id"],
                    "title": row["title"],
                    "subtitle": row["subtitle"],
                    "strategy_name": row["strategy_name"],
                    "date_start": params.get("start"),
                    "date_end": params.get("end"),
                    "total_return": total_return,
                    "excess_return": metrics.get("excess_return"),
                    "max_drawdown": summary.get("max_drawdown"),
                    "win_rate": summary.get("win_rate"),
                    "total_trade_count": summary.get("total_trade_count"),
                    "sharpe": metrics.get("sharpe"),
                    "data_until": data_until,
                    "tracking_since": tracking_since,
                    "tracking_days": len(daily_rows),
                    "result_contract": dict(contract, data_until=data_until),
                })
        return jsonify({"ok": True, "items": items})

    # QRE-SAAS-FEEDBACK-FACTOR-REQ：意见反馈 / 申请新因子独立页（侧边栏入口，
    # 仅登录用户可提交——游客不可，决策见 06 日志）
    @app.get("/saas/feedback")
    def saas_feedback_page() -> str:
        return render_template("feedback.html")

    @app.get("/saas/factor-request")
    def saas_factor_request_page() -> str:
        return render_template("factor_request.html")

    @app.get("/saas/jobs/<int:job_id>")
    def saas_job_page(job_id: int) -> str:
        return render_template("job.html", job_id=job_id)

    # C5：个股明细列表 / 个股详情页（数据走 /api/results/<id>/symbols*）
    @app.get("/saas/jobs/<int:job_id>/symbols")
    def saas_symbols_page(job_id: int) -> str:
        return render_template("symbols.html", job_id=job_id)

    @app.get("/saas/jobs/<int:job_id>/symbols/<ts_code>")
    def saas_symbol_page(job_id: int, ts_code: str) -> str:
        return render_template("symbol.html", job_id=job_id, ts_code=ts_code)

    @app.get("/saas/strategies/<int:strategy_id>")
    def saas_strategy_detail_page(strategy_id: int) -> str:
        # CR-2026-10-04 模块一：策略资产详情页（登录限定由数据 API 强制：401/404）
        return render_template("strategy.html", strategy_id=strategy_id)

    @app.get("/saas/signals")
    def saas_signals_page() -> str:
        # CR-2026-10-04 模块二：站内信号中心（登录限定由数据 API 强制）
        return render_template("signals.html")

    # --- 复用既有 NL 编译 / 因子目录（同一编译函数 + factor_correction 纠错层，
    #     LLM key 只存服务端环境变量）---
    # QRE-SAAS-NL-A2A3：持久限频（nl_rate_limits 原子计数）+ 版本化编译缓存
    # （nl_compile_cache）。编排在此，计数/缓存/key 细节在
    # gui/saas/nl_compile_support.py；不改 nl_compiler 的编译/纠错/YAML 校验。
    # 语义：缓存命中不调用 LLM 也不占配额；miss 才计数（失败同样计，防绕过）；
    # 只缓存 ok=true 完整结果；not_configured 仍 503。

    @app.post("/api/saas/nl/compile")
    def api_saas_nl_compile() -> Any:
        from quant_research_engine.gui import nl_compiler
        from quant_research_engine.gui.saas import nl_compile_support as nls

        engine = _get_engine(app)
        try:
            uid = _current_user_id(app, engine)
        except SQLAlchemyError:
            uid = None  # DB 抖动：按游客走文件回退计数（见下方 except 分支）
        data = request.get_json(silent=True) or {}
        description = (data.get("description") or "").strip()
        if not description:
            return jsonify({"ok": False, "code": "empty", "error": "请先用自然语言描述策略"}), 400
        # QRE-SAAS-NL-A1：输入前置校验（纯规则层），位于 prompt/缓存/配额/LLM
        # 之前。reject=422 不可绕过；review=422 code=nl_input_review，用户确认后
        # 以 force=true 重发（仅 review 可绕过）。规则层不消耗配额、不写缓存、
        # 不调用 LLM；DeepSeek 裁判只在缓存 miss + 配额计数后运行（见下方
        # _referee_gate），本段只做规则层。force 只认 JSON 布尔 true。
        force = data.get("force") is True
        if force:
            # force 只豁免 review：硬拒仍按规则层拦截（裁判结论本就不可硬拒，
            # 无需重复调用裁判）
            rule = nl_input_guard.rule_check(description)
            if rule["decision"] == nl_input_guard.DECISION_REJECT:
                return jsonify({
                    "ok": False, "code": "nl_input_rejected",
                    "error": "暂无法把这条描述识别为交易策略（{}）。可参考下方示例后重写。".format(
                        "；".join(rule["reasons"]) or "不符合策略描述要求"),
                    "reasons": rule["reasons"],
                    "examples": rule["examples"],
                }), 422
        else:
            guard_result = nl_input_guard.evaluate_input(description)
            if guard_result["decision"] == nl_input_guard.DECISION_REJECT:
                return jsonify({
                    "ok": False, "code": "nl_input_rejected",
                    "error": "暂无法把这条描述识别为交易策略（{}）。可参考下方示例后重写。".format(
                        "；".join(guard_result["reasons"]) or "不符合策略描述要求"),
                    "reasons": guard_result["reasons"],
                    "examples": guard_result["examples"],
                }), 422
            if guard_result["decision"] == nl_input_guard.DECISION_REVIEW:
                return jsonify({
                    "ok": False, "code": "nl_input_review",
                    "error": "这条描述还不太完整，确认仍要编译吗？",
                    "reasons": guard_result["reasons"],
                    "missing": guard_result["missing"],
                    "examples": guard_result["examples"],
                    "force_hint": True,
                }), 422

        config = nl_compiler.nl_config()
        model = config["model"] if config else ""
        base_url = config["base_url"] if config else ""
        prompt = nl_compiler.build_system_prompt()
        cache_key = nls.build_cache_key(
            description=description, model=model, base_url=base_url,
            prompt=prompt, cache_version=nls.NL_COMPILER_CACHE_VERSION,
        )
        prompt_hash = nls.prompt_fingerprint(prompt)

        def _guest_limit_response():
            return jsonify({"ok": False, "code": "guest_nl_limit",
                            "error": f"游客每日可生成策略 {GUEST_NL_DAILY_LIMIT} 次（今日已用完）。注册会员不限次数"}), 403

        def _member_limit_response():
            return jsonify({"ok": False, "code": "nl_rate_limited",
                            "scope": nls.SCOPE_MEMBER_MINUTE,
                            "reset_seconds": nls.member_reset_seconds(),
                            "error": f"编译太频繁了，请稍后再试（每分钟最多 {MEMBER_NL_MINUTE_LIMIT} 次）"}), 429

        # QRE-SAAS-NL-A1（DeepSeek 裁判）：缓存 miss 且配额计数后的裁判门。
        # 复用现有 QRE_NL_LLM_* 通道与独立裁判 prompt；通过才编译，裁判认为
        # 非策略/不明确 → 422 review（不硬拒；配额已计，防免费刷 token）；
        # 裁判故障/未配置 → 降级继续编译（不伪装裁判成功）。管理员与会员同样
        # 经过裁判（无 admin 豁免；admin 仅不限配额）。force=true 的用户已确认，
        # 调用方跳过本门。
        def _referee_gate():
            if config is None:
                return None
            try:
                verdict = nl_input_guard.referee_classify(description, config)
            except Exception:
                return None
            if verdict.get("ok") and verdict.get("label") in ("not_strategy", "unclear"):
                reason = ("DeepSeek 校验认为这条描述与交易策略无关，请确认后继续"
                          if verdict["label"] == "not_strategy" else
                          "DeepSeek 校验无法确定这是否是交易策略，请补充具体规则或确认后继续")
                return jsonify({
                    "ok": False, "code": "nl_input_review",
                    "error": "DeepSeek 校验认为这条描述不太像完整的交易策略，确认仍要编译吗？",
                    "reasons": [reason], "missing": [],
                    "examples": nl_input_guard.LEGAL_EXAMPLES, "force_hint": True,
                }), 422
            return None

        try:
            db_ready = nls.ensure_nl_tables(engine)
            # 主体类型（游客/会员/admin）先判定：运营事件与配额豁免同源。
            # 游客跳过角色查询；会员/admin 一次主键查询（缓存命中路径也多这一跳，
            # 保证运营事件 scope 准确）。
            is_admin = False
            if uid is not None and db_ready:
                with engine.connect() as conn:
                    row = conn.execute(
                        text("SELECT role FROM users WHERE id = :uid"), {"uid": uid}
                    ).first()
                is_admin = bool(row) and row.role == "admin"
            nl_scope = "admin" if is_admin else ("member" if uid is not None else "guest")
            # QRE-SAAS-PUBLIC-BETA-OPS：运营事件表就绪标志（缺表时锁事务内不写事件，
            # 避免失败语句毒化锁事务；表由 postgres apply / 懒自愈保证存在）
            ops_ready = ops_support.ensure_ops_tables(engine)
            # 快路径：不加锁查缓存（命中不调用 LLM、不占配额）
            if config is not None and db_ready:
                hit = nls.cache_lookup(engine, cache_key)
                if hit is not None:
                    # QRE-SAAS-PUBLIC-BETA-OPS：运营事件（尽力，失败不影响响应）
                    if ops_ready:
                        ops_support.record_nl_event(engine, ok=True, cache_hit=True,
                                                    error_class=None, scope=nl_scope)
                    return jsonify({**hit, "cache_hit": True})
            # 同 key 事务级咨询锁：并发同 key 只调用一次 LLM，不同 key 不串行。
            # 配额与写缓存同在锁事务内（每次请求只占一个连接，避免嵌套取连接
            # 耗尽连接池）；正常返回即提交，编译失败同样计数。
            with engine.begin() as conn:
                nls.advisory_lock(conn, cache_key)
                hit = nls.cache_get(conn, cache_key)
                if hit is not None:
                    nls.cache_touch(conn, cache_key)
                    # 运营事件与缓存命中同在锁事务内（同连接，避免嵌套取连接）
                    if ops_ready:
                        ops_support.record_nl_event_on(conn, ok=True, cache_hit=True,
                                                       error_class=None, scope=nl_scope)
                    return jsonify({**hit, "cache_hit": True})
                if not is_admin:
                    if uid is None:
                        # 游客：PG 原子计数（与锁同事务，编译失败也计数）；
                        # DB 不可用回退既有文件计数
                        if db_ready:
                            allowed = nls.consume_quota_on(
                                conn, nls.SCOPE_GUEST_DAILY,
                                nls.guest_subject_hash(_guest_key(app, _client_ip())),
                                nls.guest_window_start(), GUEST_NL_DAILY_LIMIT,
                            ) is not None
                        else:
                            allowed = _guest_nl_hit(app, _client_ip())
                        if not allowed:
                            return _guest_limit_response()
                    else:
                        if not db_ready:
                            return jsonify({"ok": False, "code": "rate_limit_unavailable",
                                            "error": "服务暂时不可用，请稍后再试"}), 503
                        hits = nls.consume_quota_on(
                            conn, nls.SCOPE_MEMBER_MINUTE,
                            nls.member_subject_hash(uid, _auth_salt(app)),
                            nls.member_window_start(), MEMBER_NL_MINUTE_LIMIT,
                        )
                        if hits is None:
                            return _member_limit_response()
                # QRE-SAAS-NL-A1：DeepSeek 裁判（仅 cache miss + 配额计数后；
                # force=true 的用户已确认，不再裁判）。管理员不限配额，但与会员
                # 一样经过裁判（无 admin 豁免）。通过才编译，否则 422 review。
                if not force:
                    gate = _referee_gate()
                    if gate is not None:
                        return gate
                result = nl_compiler.compile_nl(description)
                if result.get("ok") and config is not None and db_ready:
                    nls.cache_store(conn, cache_key, description=description,
                                    result=result, model=model,
                                    prompt_hash=prompt_hash,
                                    cache_version=nls.NL_COMPILER_CACHE_VERSION)
                # QRE-SAAS-PUBLIC-BETA-OPS：编译结果事件（与配额/缓存同事务；
                # 超限拒绝不计入——那不是编译尝试）。失败分类取 compile_nl 的 code。
                if ops_ready:
                    ops_support.record_nl_event_on(
                        conn, ok=bool(result.get("ok")), cache_hit=False,
                        error_class=None if result.get("ok") else str(result.get("code") or "unknown"),
                        scope=nl_scope,
                    )
        except SQLAlchemyError:
            # 计数/缓存故障不放开限流：游客回退文件计数，会员按不可用拒绝
            if uid is None:
                if not _guest_nl_hit(app, _client_ip()):
                    return _guest_limit_response()
                # QRE-SAAS-NL-A1：DB 故障回退路径同样先既有文件限流，再裁判，再编译；
                # force=true 与正常路径语义一致（跳过裁判），规则硬拒已在最前拦截
                if not force:
                    gate = _referee_gate()
                    if gate is not None:
                        return gate
                result = nl_compiler.compile_nl(description)
                # 运营事件尽力补记（DB 故障回退路径，静默降级）
                ops_support.record_nl_event(
                    engine, ok=bool(result.get("ok")), cache_hit=False,
                    error_class=None if result.get("ok") else str(result.get("code") or "unknown"),
                    scope="guest",
                )
                if result.get("code") == "not_configured":
                    return jsonify(result), 503
                return jsonify({**result, "cache_hit": False})
            return jsonify({"ok": False, "code": "rate_limit_unavailable",
                            "error": "服务暂时不可用，请稍后再试"}), 503
        if result.get("code") == "not_configured":
            return jsonify(result), 503
        return jsonify({**result, "cache_hit": False})

    @app.get("/api/saas/factors")
    def api_saas_factors() -> Any:
        # 因子目录是纯只读元数据，对游客开放（向导选因子需要；
        # NL 编译仍登录限定——2026-09-20 用户拍板）。配额在提交环节收口。
        from quant_research_engine.gui.factor_wizard import (
            build_factor_groups,
            load_factor_tables_columns,
        )

        # 元数据文件优先（ECS 无行情库；本地 staging 文件缺失时回退实时查库）
        metadata = _load_saas_metadata(app)
        if metadata and metadata.get("factors"):
            return jsonify({"ok": True, "groups": metadata["factors"],
                            "generated_at": metadata.get("generated_at")})
        try:
            tables_columns = load_factor_tables_columns()
        except Exception as exc:
            return jsonify({"ok": False, "error": f"因子库不可用（{exc}）"}), 503
        return jsonify({"ok": True, "groups": build_factor_groups(tables_columns)})

    @app.get("/api/saas/universes")
    def api_saas_universes() -> Any:
        """板块/概念范围名单（名称+成员数；不含成分股明细）。
        元数据文件优先，本地回退实时查库（gui/universe.py 七组）。
        纯只读元数据，对游客开放（配额在提交环节收口）。
        all_a_count 供前端大范围耗时护栏（QRE-SAAS-LARGE-UNIVERSE-GUARD）估算全部 A 股数量。"""
        metadata = _load_saas_metadata(app)
        if metadata and metadata.get("universes"):
            return jsonify({"ok": True, "groups": metadata["universes"],
                            "all_a_count": metadata.get("all_a_count"),
                            "generated_at": metadata.get("generated_at")})
        from quant_research_engine.gui.universe import all_a_count, list_universes

        try:
            data = list_universes()
            try:
                data["all_a_count"] = all_a_count()
            except Exception:
                data["all_a_count"] = None  # 计数失败不拖垮名单：前端按未知数量降级文案
            return jsonify(data)
        except Exception as exc:
            return jsonify({"ok": False, "error": f"归类数据不可用（{exc}）"}), 503

    @app.get("/api/saas/random-symbol")
    def api_saas_random_symbol() -> Any:
        """随机抽取 1 只 A 股代码（QRE-SAAS-GUEST-RANDOM-SYMBOL）。
        元数据 all_a_codes 优先（ECS 口径）；本地回退 reference.stock_basic 随机取一。
        纯只读元数据，对游客开放。"""
        import random as _random

        metadata = _load_saas_metadata(app)
        codes = (metadata or {}).get("all_a_codes") or []
        if codes:
            return jsonify({"ok": True, "ts_code": _random.choice(codes)})
        try:
            from quant_research_engine.gui.universe import random_symbol

            code = random_symbol()
            if code:
                return jsonify({"ok": True, "ts_code": code})
        except Exception as exc:
            return jsonify({"ok": False, "error": f"股票池不可用（{exc}）"}), 503
        return jsonify({"ok": False, "error": "股票池为空"}), 503

    # --- 我的策略库（QRE-SAAS-D3）：登录会员保存/复用/管理策略 YAML ---
    # 提交回测时按 (user_id, name) upsert 复用；删除仅允许无回测引用的策略。

    @app.get("/api/saas/strategies")
    def api_strategies_list() -> Any:
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        _ensure_strategy_asset_columns(engine)  # CR-2026-10-04：读连接前懒自愈
        _ensure_signal_tables(engine)  # 模块二收编：列表行集成信号状态
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT s.id, s.name, s.entry_mode, s.created_at, s.updated_at, "
                    "count(j.id) AS job_count, max(j.created_at) AS last_used_at "
                    "FROM strategies s LEFT JOIN jobs j ON j.strategy_id = s.id "
                    "WHERE s.user_id = :uid AND s.in_library "
                    "GROUP BY s.id ORDER BY s.updated_at DESC LIMIT 200"
                ),
                {"uid": uid},
            ).mappings().all()
            # 模块二收编（2026-10-04 用户拍板：信号集成进策略库，不做独立栏目）：
            # watch 状态 + 各 watch 最近信号日统计 + 未读判定，两次聚合查询避免 N+1。
            watches = conn.execute(
                text("SELECT strategy_id, scope_type, scope_payload, enabled "
                     "FROM strategy_watches WHERE user_id = :uid"),
                {"uid": uid},
            ).mappings().all()
            last_read = conn.execute(
                text("SELECT signals_last_read_at FROM users WHERE id = :uid"),
                {"uid": uid},
            ).scalar_one_or_none()
            sig_stats = conn.execute(
                text(
                    "SELECT w.strategy_id, e.trade_date, "
                    "count(*) FILTER (WHERE e.signal_type = 'entry') AS entry_n, "
                    "count(*) FILTER (WHERE e.signal_type = 'exit') AS exit_n, "
                    "count(*) FILTER (WHERE e.created_at > :lr OR :lr_is_null) AS unread_n "
                    "FROM signal_events e JOIN strategy_watches w ON w.id = e.watch_id "
                    "WHERE w.user_id = :uid AND e.trade_date = ("
                    "  SELECT max(e2.trade_date) FROM signal_events e2 WHERE e2.watch_id = e.watch_id) "
                    "GROUP BY w.strategy_id, e.trade_date"
                ),
                {"uid": uid, "lr": last_read, "lr_is_null": last_read is None},
            ).mappings().all()
        watch_by_sid = {w["strategy_id"]: _jsonable(dict(w)) for w in watches}
        stats_by_sid = {s["strategy_id"]: s for s in sig_stats}
        items = []
        for r in rows:
            item = _jsonable(dict(r))
            item["watch"] = watch_by_sid.get(r["id"])
            st = stats_by_sid.get(r["id"])
            item["latest_signals"] = (
                {"trade_date": _jsonable(st["trade_date"]),
                 "entry_n": st["entry_n"], "exit_n": st["exit_n"]} if st else None)
            item["signal_unread"] = bool(st and st["unread_n"] > 0)
            items.append(item)
        return jsonify({"ok": True, "strategies": items})

    @app.get("/api/saas/strategies/<int:strategy_id>")
    def api_strategy_get(strategy_id: int) -> Any:
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        _ensure_strategy_asset_columns(engine)
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id, name, yaml, nl_text, entry_mode, wizard_state, in_library, created_at, updated_at "
                     "FROM strategies WHERE id = :id AND user_id = :uid"),
                {"id": strategy_id, "uid": uid},
            ).mappings().first()
        if row is None:
            return jsonify({"ok": False, "error": "策略不存在"}), 404
        return jsonify({"ok": True, "strategy": _jsonable(dict(row))})

    @app.get("/api/saas/strategies/<int:strategy_id>/detail")
    def api_strategy_detail(strategy_id: int) -> Any:
        """CR-2026-10-04 模块一：策略详情页数据（源文件 + 全部历史回测）。"""
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        _ensure_strategy_asset_columns(engine)
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id, name, yaml, nl_text, entry_mode, wizard_state, in_library, created_at, updated_at "
                     "FROM strategies WHERE id = :id AND user_id = :uid"),
                {"id": strategy_id, "uid": uid},
            ).mappings().first()
            if row is None:
                return jsonify({"ok": False, "error": "策略不存在"}), 404
            jobs = conn.execute(
                text(
                    "SELECT j.id, j.kind, j.status, j.created_at, j.params, "
                    "r.summary, r.chart_data "
                    "FROM jobs j LEFT JOIN results r ON r.job_id = j.id "
                    "WHERE j.strategy_id = :sid AND j.user_id = :uid "
                    "ORDER BY j.created_at DESC LIMIT 100"
                ),
                {"sid": strategy_id, "uid": uid},
            ).mappings().all()
        history = []
        for j in jobs:
            metrics = ((j["chart_data"] or {}).get("metrics") or {})
            summary = j["summary"] or {}
            params = j["params"] or {}
            codes = params.get("codes")
            if isinstance(codes, str):
                codes = [c.strip() for c in codes.split(",") if c.strip()]
            symbol_count = summary.get("symbol_count") or (
                len(codes) if codes else params.get("random_n"))
            history.append({
                "job_id": j["id"], "kind": j["kind"], "status": j["status"],
                "date_start": params.get("start"), "date_end": params.get("end"),
                "symbol_count": symbol_count,
                "total_return": summary.get("strategy_total_return"),
                "excess_return": metrics.get("excess_return"),
                "created_at": _jsonable(j["created_at"]),
            })
        # 模块二：信号监控卡数据（watch 行 + 最近 7 日信号数）
        _ensure_signal_tables(engine)
        with engine.connect() as conn:
            watch = conn.execute(
                text("SELECT id, scope_type, scope_payload, enabled, updated_at "
                     "FROM strategy_watches WHERE strategy_id = :sid AND user_id = :uid"),
                {"sid": strategy_id, "uid": uid},
            ).mappings().first()
            recent_signals = 0
            if watch is not None:
                recent_signals = conn.execute(
                    text("SELECT count(*) FROM signal_events "
                         "WHERE watch_id = :wid AND trade_date >= CURRENT_DATE - 7"),
                    {"wid": watch["id"]},
                ).scalar_one()
        return jsonify({"ok": True, "strategy": _jsonable(dict(row)), "jobs": history,
                        "watch": _jsonable(dict(watch)) if watch else None,
                        "recent_signals_7d": recent_signals})

    # --- CR-2026-10-04 模块二：策略信号监控（用户侧） ---

    def _get_owned_strategy(conn: Any, strategy_id: int, uid: int) -> Any:
        return conn.execute(
            text("SELECT id, user_id FROM strategies WHERE id = :id AND user_id = :uid"),
            {"id": strategy_id, "uid": uid},
        ).mappings().first()

    @app.post("/api/saas/strategies/<int:strategy_id>/watch")
    def api_strategy_watch_set(strategy_id: int) -> Any:
        """开启/更新信号监控：body {enabled, scope_type, scope_payload}。
        scan_enabled=false 的层级 403；每用户 watch 上限 tier_policies.max_watches。"""
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        data = request.get_json(silent=True) or {}
        scope_type = str(data.get("scope_type") or "last_run_universe").strip()
        if scope_type not in WATCH_SCOPE_TYPES:
            return jsonify({"ok": False, "error": "scope_type 须为 last_run_universe/sector/all_a/custom"}), 400
        scope_payload = data.get("scope_payload")
        if scope_payload is not None and not isinstance(scope_payload, dict):
            return jsonify({"ok": False, "error": "scope_payload 须为对象"}), 400
        enabled = bool(data.get("enabled", True))
        _ensure_signal_tables(engine)
        with engine.begin() as conn:
            st = _get_owned_strategy(conn, strategy_id, uid)
            if st is None:
                return jsonify({"ok": False, "error": "策略不存在"}), 404
            # 开启交易信号隐含保存策略入库（2026-10-05 用户拍板：watch 依赖策略持久化）
            conn.execute(
                text("UPDATE strategies SET in_library = true WHERE id = :sid"),
                {"sid": strategy_id},
            )
            tier_row = conn.execute(
                text("SELECT tier FROM users WHERE id = :uid"), {"uid": uid}).first()
            pol = _get_policy(app, engine, str(tier_row.tier or "member") if tier_row else "member")
            if not pol.get("scan_enabled", True):
                return jsonify({"ok": False, "error": "当前账号层级未开放信号监控"}), 403
            existing = conn.execute(
                text("SELECT id FROM strategy_watches WHERE strategy_id = :sid AND user_id = :uid"),
                {"sid": strategy_id, "uid": uid},
            ).first()
            if existing is None and enabled:
                count = conn.execute(
                    text("SELECT count(*) FROM strategy_watches WHERE user_id = :uid AND enabled"),
                    {"uid": uid},
                ).scalar_one()
                max_watches = int(pol.get("max_watches", 20))
                if max_watches > 0 and count >= max_watches:
                    return jsonify({"ok": False,
                                    "error": f"信号监控上限 {max_watches} 个（已达上限，可先关闭其他策略的监控）"}), 403
                # 默认范围 = 最近回测标的快照（last_run_universe）
                if scope_type == "last_run_universe" and not scope_payload:
                    snap = conn.execute(
                        text("SELECT params FROM jobs WHERE strategy_id = :sid "
                             "ORDER BY created_at DESC LIMIT 1"),
                        {"sid": strategy_id},
                    ).first()
                    codes = ((snap.params if snap else None) or {}).get("codes") or []
                    if isinstance(codes, str):
                        codes = [c.strip() for c in codes.split(",") if c.strip()]
                    scope_payload = {"codes": codes}
            if existing is not None:
                row = conn.execute(
                    text("UPDATE strategy_watches SET enabled = :en, scope_type = :st, "
                         "scope_payload = CAST(:sp AS jsonb), updated_at = now() "
                         "WHERE id = :id RETURNING id"),
                    {"en": enabled, "st": scope_type,
                     "sp": json.dumps(scope_payload) if scope_payload is not None else None,
                     "id": existing.id},
                ).first()
                return jsonify({"ok": True, "watch_id": row.id, "updated": True})
            row = conn.execute(
                text("INSERT INTO strategy_watches (strategy_id, user_id, scope_type, scope_payload, enabled) "
                     "VALUES (:sid, :uid, :st, CAST(:sp AS jsonb), :en) RETURNING id"),
                {"sid": strategy_id, "uid": uid, "st": scope_type,
                 "sp": json.dumps(scope_payload) if scope_payload is not None else None,
                 "en": enabled},
            ).first()
        return jsonify({"ok": True, "watch_id": row.id, "updated": False})

    @app.delete("/api/saas/strategies/<int:strategy_id>/watch")
    def api_strategy_watch_delete(strategy_id: int) -> Any:
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        _ensure_signal_tables(engine)
        with engine.begin() as conn:
            row = conn.execute(
                text("DELETE FROM strategy_watches WHERE strategy_id = :sid AND user_id = :uid RETURNING id"),
                {"sid": strategy_id, "uid": uid},
            ).first()
        if row is None:
            return jsonify({"ok": False, "error": "监控不存在"}), 404
        return jsonify({"ok": True, "deleted": row.id})

    @app.get("/api/saas/signals")
    def api_signals_list() -> Any:
        """信号中心列表：?date_from&date_to&strategy_id&signal_type&ts_code&page&page_size"""
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        try:
            page = max(1, int(request.args.get("page", 1)))
            page_size = min(100, max(1, int(request.args.get("page_size", 50))))
        except ValueError:
            return jsonify({"ok": False, "error": "page/page_size 须为整数"}), 400
        conds = ["w.user_id = :uid"]
        params: dict[str, Any] = {"uid": uid}
        for key, col in (("date_from", "e.trade_date >= "), ("date_to", "e.trade_date <= ")):
            v = str(request.args.get(key) or "").strip()
            if v:
                try:
                    from datetime import date as _date
                    _date.fromisoformat(v)
                except ValueError:
                    return jsonify({"ok": False, "error": f"{key} 须为 YYYY-MM-DD"}), 400
                conds.append(f"{col} :{key}")
                params[key] = v
        sid = str(request.args.get("strategy_id") or "").strip()
        if sid:
            if not sid.isdigit():
                return jsonify({"ok": False, "error": "strategy_id 须为整数"}), 400
            conds.append("w.strategy_id = :sid")
            params["sid"] = int(sid)
        sig = str(request.args.get("signal_type") or "").strip()
        if sig:
            if sig not in ("entry", "exit"):
                return jsonify({"ok": False, "error": "signal_type 须为 entry/exit"}), 400
            conds.append("e.signal_type = :sig")
            params["sig"] = sig
        code = str(request.args.get("ts_code") or "").strip()
        if code:
            conds.append("e.ts_code = :code")
            params["code"] = code
        where = " AND ".join(conds)
        _ensure_signal_tables(engine)
        with engine.connect() as conn:
            total = conn.execute(
                text(f"SELECT count(*) FROM signal_events e "
                     f"JOIN strategy_watches w ON w.id = e.watch_id WHERE {where}"),
                params,
            ).scalar_one()
            rows = conn.execute(
                text(f"SELECT e.id, e.trade_date, e.ts_code, e.signal_type, e.price, e.created_at, "
                     f"w.strategy_id, s.name AS strategy_name "
                     f"FROM signal_events e JOIN strategy_watches w ON w.id = e.watch_id "
                     f"JOIN strategies s ON s.id = w.strategy_id "
                     f"WHERE {where} ORDER BY e.trade_date DESC, e.id DESC "
                     f"LIMIT :lim OFFSET :off"),
                {**params, "lim": page_size, "off": (page - 1) * page_size},
            ).mappings().all()
        return jsonify({"ok": True, "total": total, "page": page, "page_size": page_size,
                        "items": [_jsonable(dict(r)) for r in rows]})

    @app.get("/api/saas/signals/unread-count")
    def api_signals_unread() -> Any:
        """header 未读红点：signals_last_read_at 之后到达的信号数（未读过长 null → 全部）。"""
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        _ensure_signal_tables(engine)
        with engine.connect() as conn:
            last_read = conn.execute(
                text("SELECT signals_last_read_at FROM users WHERE id = :uid"),
                {"uid": uid},
            ).scalar_one_or_none()
            if last_read is None:
                count = conn.execute(
                    text("SELECT count(*) FROM signal_events e "
                         "JOIN strategy_watches w ON w.id = e.watch_id WHERE w.user_id = :uid"),
                    {"uid": uid},
                ).scalar_one()
            else:
                count = conn.execute(
                    text("SELECT count(*) FROM signal_events e "
                         "JOIN strategy_watches w ON w.id = e.watch_id "
                         "WHERE w.user_id = :uid AND e.created_at > :lr"),
                    {"uid": uid, "lr": last_read},
                ).scalar_one()
        return jsonify({"ok": True, "unread": count})

    @app.post("/api/saas/signals/mark-read")
    def api_signals_mark_read() -> Any:
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        _ensure_signal_tables(engine)
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE users SET signals_last_read_at = now() WHERE id = :uid"),
                {"uid": uid},
            )
        return jsonify({"ok": True})

    @app.post("/api/saas/strategies")
    def api_strategy_save() -> Any:
        """保存到我的策略库：按 (user_id, name) upsert（同名更新 YAML）。"""
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "游客无法保存策略，注册会员后可保存到我的策略库"}), 401
        data = request.get_json(silent=True) or {}
        name = str(data.get("name") or "").strip()
        yaml_text = str(data.get("yaml") or "").strip()
        if not name:
            return jsonify({"ok": False, "error": "缺少策略名称"}), 400
        if not yaml_text:
            return jsonify({"ok": False, "error": "缺少策略 yaml"}), 400
        # 同类指标基础价格口径统一（QRE-WIZARD-PRICE-BASIS-001）
        yaml_text, basis_note = _unify_price_basis_yaml(yaml_text)
        if data.get("entry_mode") is not None and _norm_entry_mode(data.get("entry_mode")) is None:
            return jsonify({"ok": False, "error": "entry_mode 须为 nl/wizard/yaml"}), 400
        entry_mode = _infer_entry_mode(data.get("entry_mode"), data.get("nl_text"))
        wizard_state = _norm_wizard_state(data.get("wizard_state"))
        _ensure_strategy_asset_columns(engine)
        with engine.begin() as conn:
            # dev 后门（SAAS_DEV_AUTH=1）用户可能不存在：自动建行（同 jobs 路由）
            conn.execute(
                text("INSERT INTO users (id, phone) VALUES (:id, :phone) ON CONFLICT (id) DO NOTHING"),
                {"id": uid, "phone": f"pending_{uid}"},
            )
            existing = conn.execute(
                text("SELECT id FROM strategies WHERE user_id = :uid AND name = :name"),
                {"uid": uid, "name": name},
            ).first()
            if existing is not None:
                conn.execute(
                    text("UPDATE strategies SET yaml = :yaml, nl_text = :nl, entry_mode = :em, "
                         "wizard_state = COALESCE(CAST(:ws AS jsonb), wizard_state), "
                         "in_library = true, updated_at = now() "  # 显式保存即入库
                         "WHERE id = :id"),
                    {"yaml": yaml_text, "nl": data.get("nl_text"), "em": entry_mode,
                     "ws": wizard_state, "id": existing.id},
                )
                return jsonify({"ok": True, "strategy_id": existing.id, "updated": True,
                                **({"warnings": [basis_note]} if basis_note else {})})
            sid = conn.execute(
                text("INSERT INTO strategies (user_id, name, nl_text, yaml, entry_mode, wizard_state, in_library) "
                     "VALUES (:uid, :name, :nl, :yaml, :em, CAST(:ws AS jsonb), true) RETURNING id"),
                {"uid": uid, "name": name, "nl": data.get("nl_text"), "yaml": yaml_text,
                 "em": entry_mode, "ws": wizard_state},
            ).scalar_one()
        return jsonify({"ok": True, "strategy_id": sid, "updated": False,
                        **({"warnings": [basis_note]} if basis_note else {})})

    @app.post("/api/saas/strategies/<int:strategy_id>/save")
    def api_strategy_save_to_library(strategy_id: int) -> Any:
        """QRE-SAAS-RESULT-ACTIONS（2026-10-05 用户拍板）：结果页「保存到我的策略库」——
        把提交回测时自动建的策略行标记入库（幂等；提交回测不再自动入库）。"""
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "游客结果次日清空，注册会员后可保存策略"}), 401
        _ensure_strategy_asset_columns(engine)
        with engine.begin() as conn:
            row = conn.execute(
                text("UPDATE strategies SET in_library = true, updated_at = now() "
                     "WHERE id = :id AND user_id = :uid RETURNING id, in_library"),
                {"id": strategy_id, "uid": uid},
            ).mappings().first()
        if row is None:
            return jsonify({"ok": False, "error": "策略不存在"}), 404
        return jsonify({"ok": True, "strategy_id": row["id"], "in_library": True})

    @app.post("/api/saas/strategies/<int:strategy_id>/rename")
    def api_strategy_rename(strategy_id: int) -> Any:
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        data = request.get_json(silent=True) or {}
        name = str(data.get("name") or "").strip()
        if not name:
            return jsonify({"ok": False, "error": "缺少新名称"}), 400
        with engine.begin() as conn:
            dup = conn.execute(
                text("SELECT id FROM strategies WHERE user_id = :uid AND name = :name AND id <> :id"),
                {"uid": uid, "name": name, "id": strategy_id},
            ).first()
            if dup is not None:
                return jsonify({"ok": False, "error": "已有同名策略"}), 409
            row = conn.execute(
                text("UPDATE strategies SET name = :name, updated_at = now() "
                     "WHERE id = :id AND user_id = :uid RETURNING id"),
                {"name": name, "id": strategy_id, "uid": uid},
            ).first()
        if row is None:
            return jsonify({"ok": False, "error": "策略不存在"}), 404
        return jsonify({"ok": True, "strategy_id": row.id})

    @app.delete("/api/saas/strategies/<int:strategy_id>")
    def api_strategy_delete(strategy_id: int) -> Any:
        """删除策略：被回测任务引用的策略禁删（保历史可溯），提示先清理关联回测。"""
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        with engine.begin() as conn:
            used = conn.execute(
                text("SELECT count(*) FROM jobs WHERE strategy_id = :id"), {"id": strategy_id}
            ).scalar_one()
            if used:
                return jsonify({"ok": False, "error": f"该策略已关联 {used} 条回测记录，为保证历史可溯不允许删除；可重命名或另存新版本"}), 409
            row = conn.execute(
                text("DELETE FROM strategies WHERE id = :id AND user_id = :uid RETURNING id"),
                {"id": strategy_id, "uid": uid},
            ).first()
        if row is None:
            return jsonify({"ok": False, "error": "策略不存在"}), 404
        return jsonify({"ok": True, "deleted": strategy_id})

    # --- 缺因子申请（QRE-SAAS-007）：用户不直接增/改因子；申请落库，
    #     运营方按需求热度人工审核后离线计算入库（8080 审核界面为后续任务） ---

    @app.post("/api/saas/factor-requests")
    def api_factor_request_create() -> Any:
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        data = request.get_json(silent=True) or {}
        factors = data.get("factors")
        if not isinstance(factors, list) or not factors or not all(isinstance(f, str) and f.strip() for f in factors):
            return jsonify({"ok": False, "error": "factors 须为非空字符串数组"}), 400
        factors = sorted({f.strip() for f in factors})
        strategy_name = str(data.get("strategy_name") or "").strip() or None
        # QRE-SAAS-FEEDBACK-FACTOR-REQ：申请新因子页可附因子定义/用途，辅助人工审核
        formula = str(data.get("formula") or "").strip()[:2000] or None
        purpose = str(data.get("purpose") or "").strip()[:2000] or None

        with engine.begin() as conn:
            # dev 后门（SAAS_DEV_AUTH=1）用户可能不存在：自动建行（同 jobs 路由）
            conn.execute(
                text("INSERT INTO users (id, phone) VALUES (:id, :phone) ON CONFLICT (id) DO NOTHING"),
                {"id": uid, "phone": f"pending_{uid}"},
            )
            recent = conn.execute(
                text(
                    "SELECT factors FROM factor_requests "
                    "WHERE user_id = :uid AND created_at > now() - interval '24 hours'"
                ),
                {"uid": uid},
            ).scalars().all()
            if any(sorted(set(r)) == factors for r in recent):
                return jsonify({"ok": False, "error": "这些因子你已提交过申请，我们会按需求热度评估，请耐心等待"}), 409
            rid = conn.execute(
                text(
                    "INSERT INTO factor_requests (user_id, strategy_name, factors, formula, purpose) "
                    "VALUES (:uid, :name, CAST(:factors AS jsonb), :formula, :purpose) RETURNING id"
                ),
                {"uid": uid, "name": strategy_name, "factors": json.dumps(factors),
                 "formula": formula, "purpose": purpose},
            ).scalar_one()
        return jsonify({"ok": True, "id": rid, "status": "pending"})

    @app.get("/api/saas/factor-requests")
    def api_factor_request_list() -> Any:
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, strategy_name, factors, formula, purpose, status, note, created_at "
                    "FROM factor_requests WHERE user_id = :uid "
                    "ORDER BY created_at DESC LIMIT 50"
                ),
                {"uid": uid},
            ).mappings().all()
        return jsonify({"ok": True, "requests": [_jsonable(dict(r)) for r in rows]})

    # --- 内测意见反馈（QRE-SAAS-FEEDBACK-FACTOR-REQ）：仅登录用户提交
    #     （游客不可提交，决策见 06 日志）；管理台只读查看。
    #     QRE-SAAS-PUBLIC-BETA-OPS：分类（category）与处理状态（status）最小闭环，
    #     allowlist 与 ops_support 单一权威同源；不建工单系统。 ---
    FEEDBACK_DAILY_LIMIT = 20  # 单用户每日反馈上限（防滥用，内测口径）

    @app.post("/api/saas/feedback")
    def api_feedback_create() -> Any:
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "反馈需登录后提交（游客可先在「新建策略」免登录试用）"}), 401
        data = request.get_json(silent=True) or {}
        content = str(data.get("content") or "").strip()
        if not content:
            return jsonify({"ok": False, "error": "请填写反馈内容"}), 400
        if len(content) > 2000:
            return jsonify({"ok": False, "error": "反馈内容过长（最多 2000 字）"}), 400
        page = str(data.get("page") or "").strip()[:200] or None
        contact = str(data.get("contact") or "").strip()[:200] or None
        category = str(data.get("category") or "other").strip()
        if category not in ops_support.FEEDBACK_CATEGORIES:
            return jsonify({"ok": False, "error": "反馈类型无效"}), 400
        # 分类/状态列懒自愈（本地/测试库；生产由 postgres apply cloud_schema.sql）
        ops_ready = ops_support.ensure_ops_tables(engine)
        with engine.begin() as conn:
            # dev 后门（SAAS_DEV_AUTH=1）用户可能不存在：自动建行（同 jobs 路由）
            conn.execute(
                text("INSERT INTO users (id, phone) VALUES (:id, :phone) ON CONFLICT (id) DO NOTHING"),
                {"id": uid, "phone": f"pending_{uid}"},
            )
            used = conn.execute(
                text(
                    "SELECT count(*) FROM feedback "
                    "WHERE user_id = :uid AND created_at::date = now()::date"
                ),
                {"uid": uid},
            ).scalar_one()
            if used >= FEEDBACK_DAILY_LIMIT:
                return jsonify({"ok": False, "error": "今日反馈提交次数已达上限，请明天再来"}), 429
            if ops_ready:
                fid = conn.execute(
                    text(
                        "INSERT INTO feedback (user_id, content, page, contact, category) "
                        "VALUES (:uid, :content, :page, :contact, :category) RETURNING id"
                    ),
                    {"uid": uid, "content": content, "page": page, "contact": contact,
                     "category": category},
                ).scalar_one()
            else:
                # 列缺失（旧库未 apply）：按既有形态降级入库，不报错、不丢反馈
                fid = conn.execute(
                    text(
                        "INSERT INTO feedback (user_id, content, page, contact) "
                        "VALUES (:uid, :content, :page, :contact) RETURNING id"
                    ),
                    {"uid": uid, "content": content, "page": page, "contact": contact},
                ).scalar_one()
        return jsonify({"ok": True, "id": fid})

    @app.get("/api/saas/feedback")
    def api_feedback_list() -> Any:
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        ops_ready = ops_support.ensure_ops_tables(engine)
        cols = ("id, content, page, created_at" if not ops_ready else
                "id, content, page, category, status, created_at")
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT {cols} FROM feedback "
                    "WHERE user_id = :uid ORDER BY created_at DESC LIMIT 50"
                ),
                {"uid": uid},
            ).mappings().all()
        return jsonify({"ok": True, "feedback": [_jsonable(dict(r)) for r in rows]})

    # --- 鉴权（QRE-SAAS-006） ---

    @app.post("/api/saas/auth/code")
    def api_auth_code() -> Any:
        data = request.get_json(silent=True) or {}
        target = str(data.get("target") or "").strip()
        if not target:
            return jsonify({"ok": False, "error": "缺少 target（手机号或邮箱）"}), 400

        now = time.time()
        rl = app.extensions["rate_limit"]
        last = rl["target"].get(target, 0.0)
        if now - last < RATE_LIMIT_TARGET_SECONDS:
            return jsonify({"ok": False, "error": "发送过于频繁，请稍后再试"}), 429
        ip = request.remote_addr or "unknown"
        hits = [t for t in rl["ip"].get(ip, []) if now - t < RATE_LIMIT_IP_WINDOW]
        if len(hits) >= RATE_LIMIT_IP_MAX:
            return jsonify({"ok": False, "error": "发送过于频繁，请稍后再试"}), 429

        code = f"{secrets.randbelow(10 ** AUTH_CODE_LENGTH):0{AUTH_CODE_LENGTH}d}"
        channel = "email" if "@" in target else "sms"
        try:
            _get_sender(app).send(target, code)
        except (RuntimeError, NotImplementedError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 502

        engine = _get_engine(app)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO sms_codes (phone, code_hash, channel, expires_at) "
                    "VALUES (:target, :hash, :channel, now() + make_interval(mins => :mins))"
                ),
                {
                    "target": target,
                    "hash": _code_hash(code, target, _auth_salt(app)),
                    "channel": channel,
                    "mins": AUTH_CODE_TTL_MINUTES,
                },
            )
        rl["target"][target] = now
        rl["ip"][ip] = [*hits, now]
        # 响应不暴露 target 是否已注册
        resp: dict[str, Any] = {"ok": True, "channel": channel, "expires_in": AUTH_CODE_TTL_MINUTES * 60}
        # staging 友好开关：响应直接带验证码（生产严禁开启，仅供本地预发联调）
        if str(_cfg(app, "SAAS_STUB_ECHO", "0") or "0") == "1":
            resp["dev_code"] = code
        return jsonify(resp)

    @app.post("/api/saas/auth/register")
    def api_auth_register() -> Any:
        """内测临时注册（邮箱+密码，密码 pbkdf2 哈希存储）。

        用户拍板：登录/验证码/短信/微信正式版外购，不自建；本端点仅内测期使用，
        正式版替换为外购身份服务（15 号文档 D 阶段注释）。
        """
        data = request.get_json(silent=True) or {}
        email = str(data.get("email") or data.get("target") or "").strip().lower()
        password = str(data.get("password") or "")
        if not email or "@" not in email or len(email) > 200:
            return jsonify({"ok": False, "error": "邮箱格式不正确"}), 400
        if len(password) < 8 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
            return jsonify({"ok": False, "error": "密码至少 8 位且需同时包含字母和数字"}), 400
        engine = _get_engine(app)
        with engine.begin() as conn:
            existing = conn.execute(
                text("SELECT id FROM users WHERE email = :e"), {"e": email}
            ).first()
            if existing is not None:
                return jsonify({"ok": False, "error": "该邮箱已注册，请直接登录"}), 409
            salt = secrets.token_hex(8)
            user = conn.execute(
                text(
                    "INSERT INTO users (email, password_hash, tier, last_login_at) "
                    "VALUES (:e, :h, 'member', now()) "
                    "RETURNING id, phone, email, quota_daily, tier"
                ),
                {"e": email, "h": _password_hash(password, salt)},
            ).mappings().one()
            token = secrets.token_urlsafe(32)
            conn.execute(
                text(
                    "INSERT INTO sessions (id, user_id, expires_at) "
                    "VALUES (:token, :uid, now() + make_interval(days => :days))"
                ),
                {"token": token, "uid": user["id"], "days": SESSION_TTL_DAYS},
            )
        return jsonify({"ok": True, "token": token, "user": _jsonable(dict(user))})

    @app.post("/api/saas/auth/login")
    def api_auth_login() -> Any:
        data = request.get_json(silent=True) or {}
        target = str(data.get("target") or "").strip()
        code = str(data.get("code") or "").strip()
        if not target or not code:
            return jsonify({"ok": False, "error": "缺少 target/code"}), 400

        engine = _get_engine(app)
        with engine.begin() as conn:
            # 内置测试账号（QRE-ECS-C4）：env SAAS_TEST_ACCOUNT_EMAIL/PASSWORD
            # 配置时，该 target+code 直接放行（跳过验证码表；SMTP 未配期间的
            # 联调通道，配置即凭证，生产内测前须移除或置空）。
            test_email = _cfg(app, "SAAS_TEST_ACCOUNT_EMAIL")
            test_pass = _cfg(app, "SAAS_TEST_ACCOUNT_PASSWORD")
            bypass_code = bool(
                test_email and test_pass
                and hmac.compare_digest(target, test_email)
                and hmac.compare_digest(code, test_pass)
            )
            if not bypass_code:
                # 邮箱+密码登录（内测临时方案，正式版外购身份服务后移除）
                pw_user = conn.execute(
                    text("SELECT id, password_hash FROM users WHERE email = :t"),
                    {"t": target.lower()},
                ).mappings().first()
                if pw_user is not None and pw_user["password_hash"]:
                    if not _verify_password(code, pw_user["password_hash"]):
                        return jsonify({"ok": False, "error": "邮箱或密码错误"}), 401
                else:
                    row = conn.execute(
                        text(
                            "SELECT id, code_hash FROM sms_codes "
                            "WHERE phone = :target AND used_at IS NULL AND expires_at > now() "
                            "ORDER BY id DESC LIMIT 1"
                        ),
                        {"target": target},
                    ).mappings().first()
                    expected = row["code_hash"] if row else ""
                    actual = _code_hash(code, target, _auth_salt(app))
                    if row is None or not hmac.compare_digest(expected, actual):
                        return jsonify({"ok": False, "error": "验证码错误或已过期"}), 401
                    conn.execute(text("UPDATE sms_codes SET used_at = now() WHERE id = :id"), {"id": row["id"]})

            is_email = "@" in target
            col = "email" if is_email else "phone"
            user = conn.execute(
                text(f"SELECT id, phone, email, quota_daily, status FROM users WHERE {col} = :target"),
                {"target": target},
            ).mappings().first()
            if user is None:
                # 首次登录自动注册：按 target 形态填 phone/email，另一列 NULL
                user = conn.execute(
                    text(
                        f"INSERT INTO users ({col}, last_login_at) VALUES (:target, now()) "
                        "RETURNING id, phone, email, quota_daily, status"
                    ),
                    {"target": target},
                ).mappings().one()
            else:
                if user["status"] != "active":
                    return jsonify({"ok": False, "error": "账号已被禁用，请联系运营方"}), 403
                conn.execute(text("UPDATE users SET last_login_at = now() WHERE id = :id"), {"id": user["id"]})
            token = secrets.token_urlsafe(32)
            conn.execute(
                text(
                    "INSERT INTO sessions (id, user_id, expires_at) "
                    "VALUES (:token, :uid, now() + make_interval(days => :days))"
                ),
                {"token": token, "uid": user["id"], "days": SESSION_TTL_DAYS},
            )
        return jsonify({"ok": True, "token": token, "user": _jsonable(dict(user))})

    # --- Authing OIDC 登录（QRE-AUTH-MEMBERSHIP / A3，18 号设计文档） ---
    # 托管登录页授权码流程：/saas/login/authing 302 → Authing（短信/扫码 UI 托管）
    # → /saas/login/callback 换票验签 → 按 sub 建档/关联 → 发本地 session token。
    # POST /api/saas/auth/authing 为同语义的 JSON 端点（程序化接入/测试）。

    def _session_for_user(conn: Any, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        conn.execute(
            text(
                "INSERT INTO sessions (id, user_id, expires_at) "
                "VALUES (:token, :uid, now() + make_interval(days => :days))"
            ),
            {"token": token, "uid": user_id, "days": SESSION_TTL_DAYS},
        )
        return token

    def _user_from_authing_claims(conn: Any, claims: dict) -> Any:
        """按 sub（authing_id）查用户；无则自动建档（首登即注册，18 号文档 §2）。
        返回 users 行（mappings）。手机号撞已有旧账号时新行 phone 置 NULL，
        关联走 /api/saas/auth/bind 绑定入口。"""
        from quant_research_engine.gui.saas import authing

        sub = str(claims["sub"])
        row = conn.execute(
            text("SELECT id, phone, email, nickname, quota_daily, tier, status "
                 "FROM users WHERE authing_id = :sub"),
            {"sub": sub},
        ).mappings().first()
        if row is not None:
            if row["status"] != "active":
                raise authing.AuthingError("账号已被禁用，请联系运营方")
            conn.execute(
                text("UPDATE users SET last_login_at = now(), "
                     "nickname = COALESCE(:nick, nickname), "
                     "avatar_url = COALESCE(:avatar, avatar_url) WHERE id = :id"),
                {"nick": claims.get("nickname") or claims.get("name"),
                 "avatar": claims.get("picture"), "id": row["id"]},
            )
            return row
        phone = (claims.get("phone") or claims.get("phone_number") or "").strip() or None
        if phone:
            dup = conn.execute(
                text("SELECT id FROM users WHERE phone = :p"), {"p": phone}
            ).first()
            if dup is not None:
                phone = None  # 手机号属旧账号，先置空，由绑定入口关联
        row = conn.execute(
            text(
                "INSERT INTO users (authing_id, phone, nickname, avatar_url, tier, "
                "last_login_at, member_since) "
                "VALUES (:sub, :phone, :nick, :avatar, 'member', now(), now()) "
                "RETURNING id, phone, email, nickname, quota_daily, tier, status"
            ),
            {"sub": sub, "phone": phone,
             "nick": claims.get("nickname") or claims.get("name"),
             "avatar": claims.get("picture")},
        ).mappings().one()
        return row

    @app.get("/saas/login/authing")
    def saas_login_authing_redirect() -> Any:
        from flask import redirect

        from quant_research_engine.gui.saas import authing

        session["authing_next"] = _safe_saas_next(request.args.get("next"))
        try:
            url = authing.build_authorize_url(app, authing.new_state(app))
        except authing.AuthingError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 503
        return redirect(url)

    @app.get("/saas/login/callback")
    def saas_login_callback() -> Any:
        from quant_research_engine.gui.saas import authing

        next_url = _safe_saas_next(session.pop("authing_next", "/saas/"))
        code = str(request.args.get("code") or "").strip()
        state = str(request.args.get("state") or "")
        if not code or not authing.pop_state(app, state):
            return render_template("login_callback.html", error="登录状态已失效，请返回登录页重试"), 400
        try:
            claims = authing.exchange_code(app, code)
        except authing.AuthingError as exc:
            return render_template("login_callback.html", error=str(exc)), 502
        engine = _get_engine(app)
        with engine.begin() as conn:
            try:
                user = _user_from_authing_claims(conn, claims)
            except authing.AuthingError as exc:
                return render_template("login_callback.html", error=str(exc)), 403
            token = _session_for_user(conn, user["id"])
        return render_template("login_callback.html", token=token,
                               nickname=user["nickname"] or "", next=next_url)

    @app.post("/api/saas/auth/authing")
    def api_auth_authing() -> Any:
        """JSON 版换票：{code, state} → {token, user}（同回调语义，供程序化接入）。"""
        from quant_research_engine.gui.saas import authing

        data = request.get_json(silent=True) or {}
        code = str(data.get("code") or "").strip()
        state = str(data.get("state") or "")
        if not code:
            return jsonify({"ok": False, "error": "缺少 code"}), 400
        if not authing.pop_state(app, state):
            return jsonify({"ok": False, "error": "state 无效或已过期"}), 400
        try:
            claims = authing.exchange_code(app, code)
        except authing.AuthingError as exc:
            status = 503 if "未配置" in str(exc) else 502
            return jsonify({"ok": False, "error": str(exc)}), status
        engine = _get_engine(app)
        with engine.begin() as conn:
            try:
                user = _user_from_authing_claims(conn, claims)
            except authing.AuthingError as exc:
                return jsonify({"ok": False, "error": str(exc)}), 403
            token = _session_for_user(conn, user["id"])
        return jsonify({"ok": True, "token": token, "user": _jsonable(dict(user))})

    @app.post("/api/saas/auth/bind")
    def api_auth_bind() -> Any:
        """绑定旧账号（18 号文档 §4）：当前须为 Authing 登录态（Bearer），
        提交旧账号 邮箱+密码 验证后把 authing_id 迁到旧账号行；
        自动建档产生的新行若无任何回测/策略则随绑定删除（否则 409 人工处理）。"""
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        data = request.get_json(silent=True) or {}
        email = str(data.get("email") or "").strip().lower()
        password = str(data.get("password") or "")
        if not email or not password:
            return jsonify({"ok": False, "error": "请填写旧账号的邮箱和密码"}), 400
        with engine.begin() as conn:
            current = conn.execute(
                text("SELECT id, authing_id FROM users WHERE id = :uid"), {"uid": uid}
            ).mappings().first()
            if current is None or not current["authing_id"]:
                return jsonify({"ok": False, "error": "当前账号不是 Authing 登录态，无法绑定"}), 400
            old = conn.execute(
                text("SELECT id, password_hash, authing_id, status FROM users WHERE email = :e"),
                {"e": email},
            ).mappings().first()
            if old is None or not old["password_hash"] or not _verify_password(password, old["password_hash"]):
                return jsonify({"ok": False, "error": "邮箱或密码错误"}), 401
            if old["status"] != "active":
                return jsonify({"ok": False, "error": "该账号已被禁用，请联系运营方"}), 403
            if old["id"] == uid:
                return jsonify({"ok": True, "user_id": uid, "already": True})
            if old["authing_id"]:
                return jsonify({"ok": False, "error": "该旧账号已绑定过其他登录身份"}), 409
            used = conn.execute(
                text("SELECT (SELECT count(*) FROM jobs WHERE user_id = :uid) + "
                     "(SELECT count(*) FROM strategies WHERE user_id = :uid) + "
                     "(SELECT count(*) FROM feedback WHERE user_id = :uid) + "
                     "(SELECT count(*) FROM factor_requests WHERE user_id = :uid)"),
                {"uid": uid},
            ).scalar_one()
            if used:
                return jsonify({"ok": False, "error": "当前新账号已有回测/策略数据，无法自动合并，请联系运营方人工关联"}), 409
            conn.execute(text("DELETE FROM sessions WHERE user_id = :uid"), {"uid": uid})
            conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": uid})
            conn.execute(
                text("UPDATE users SET authing_id = :sub, last_login_at = now() WHERE id = :id"),
                {"sub": current["authing_id"], "id": old["id"]},
            )
            token = _session_for_user(conn, old["id"])
        return jsonify({"ok": True, "token": token, "user_id": old["id"], "bound": email})

    @app.get("/api/saas/me")
    def api_me() -> Any:
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        with engine.connect() as conn:
            user = conn.execute(
                text(
                    "SELECT id, phone, email, quota_daily, tier, role, "
                    "(SELECT count(*) FROM jobs j WHERE j.user_id = u.id "
                    " AND j.kind = 'full' AND j.created_at::date = now()::date) AS used_today "
                    "FROM users u WHERE u.id = :uid"
                ),
                {"uid": uid},
            ).mappings().first()
        if user is None:
            return jsonify({"ok": False, "error": "用户不存在"}), 401
        item = _jsonable(dict(user))
        item["is_admin"] = item.get("role") == "admin"
        if item["is_admin"]:  # admin 不限回测次数（QRE-SAAS-PROFILE）
            item["quota_limit"] = "不限"
            item["quota_remaining"] = None
        else:
            pol = _get_policy(app, engine, str(item.get("tier") or "member"))
            if int(pol["daily_full_limit"] or 0) <= 0:  # 2026-10-05 内测调整：注册用户不限次数
                item["quota_limit"] = "不限"
                item["quota_remaining"] = None
            else:
                item["quota_limit"] = pol["daily_full_limit"]
                item["quota_remaining"] = max(0, pol["daily_full_limit"] - (item.get("used_today") or 0))
        return jsonify({"ok": True, "user": item})

    # --- 用户侧：提交 / 查询 / 取消（17 协议 §2/§5；/api/saas/* 为兼容别名） ---

    @app.post("/api/jobs")
    @app.post("/api/saas/jobs")  # 兼容别名（既有前端/测试）
    def api_create_job() -> Any:
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        data = request.get_json(silent=True) or {}
        params_raw = data.get("params") or data.get("params_json") or {}
        if not isinstance(params_raw, dict):
            return jsonify({"ok": False, "error": "params 须为对象"}), 400
        kind = str(data.get("kind") or "full")
        if kind not in JOB_KINDS:
            return jsonify({"ok": False, "error": f"kind 须为 {'/'.join(JOB_KINDS)}"}), 400
        # QRE-SAAS-SYMBOL-UX：标的代码输入规范化——支持只输 6 位数字自动补
        # 交易所后缀（60/68→SH，00/30→SZ，4/8/920→BJ），兼容已带后缀输入；
        # 非法代码 400 友好报错。内部存储保持带后缀原样。
        if params_raw.get("codes"):
            try:
                params_raw = dict(params_raw)
                params_raw["codes"] = normalize_ts_codes(params_raw["codes"])
            except ValueError as exc:
                return jsonify({"ok": False, "error": str(exc)}), 400
        yaml_text = str(data.get("yaml") or data.get("strategy_yaml") or "").strip()
        if not yaml_text:
            return jsonify({"ok": False, "error": "缺少策略 yaml"}), 400
        # 同类指标基础价格口径统一（QRE-WIZARD-PRICE-BASIS-001）：
        # 在配额闸之前归一，配额按最终表口径核算
        yaml_text, basis_note = _unify_price_basis_yaml(yaml_text)
        # 因子资源配额闸（2026-10-03）：提交时提前拦截"枚举全库因子"的资源滥用，
        # 三个入口（NL/向导/ YAML 编辑）均汇聚于此。上限按角色读 tier_policies
        # （管理台可改），并随 params 透传给 worker 做执行前权威复核。
        if uid is None:
            factor_pol = _get_policy(app, engine, "guest")
        else:
            with engine.connect() as conn:
                tier_row = conn.execute(
                    text("SELECT tier FROM users WHERE id = :uid"), {"uid": uid}
                ).first()
            factor_pol = _get_policy(app, engine, str(tier_row[0]) if tier_row else "member")
        limit_issues = check_factor_limits(
            yaml_text,
            max_fields=int(factor_pol.get("max_factor_fields", 20)),
            max_tables=int(factor_pol.get("max_factor_tables", 3)),
        )
        if limit_issues:
            return jsonify({"ok": False, "error": "；".join(limit_issues)}), 400
        params_raw = dict(params_raw)
        params_raw["_factor_limits"] = {
            "max_fields": int(factor_pol.get("max_factor_fields", 20)),
            "max_tables": int(factor_pol.get("max_factor_tables", 3)),
        }

        # --- 游客通道（15 号文档 D 阶段定稿；2026-10-03 限额参数化读 tier_policies；
        #     2026-10-04 内测调整：最多 10 只（自选不足自动随机补齐）/近 10 年/日 1 次不变；
        #     QRE-SAAS-ACCESS-HARDENING-001：归属改随机会话 Cookie，不再纯 IP） ---
        guest_key = None
        new_guest_sid: str | None = None
        if uid is None:
            pol = _get_policy(app, engine, "guest")
            codes = params_raw.get("codes") or []
            if isinstance(codes, str):
                codes = [c.strip() for c in codes.split(",") if c.strip()]
            random_n = params_raw.get("random_n")
            max_codes = int(pol["max_codes"])
            if params_raw.get("universe"):
                return jsonify({"ok": False, "error": "游客暂不支持板块/概念与全市场回测——可选「指定股票代码」（最多 10 只）或「随机股票」。注册会员后不限范围"}), 403
            if codes:
                if max_codes > 0 and len(codes) > max_codes:
                    return jsonify({"ok": False, "error": f"游客最多回测 {max_codes} 只股票（当前 {len(codes)} 只）。注册会员后不限数量"}), 403
                # 自选不足上限 → 标记 worker 执行前随机补齐（params 落库可见口径）
                if max_codes > 0 and len(codes) < max_codes:
                    params_raw = dict(params_raw)
                    params_raw["codes_auto_fill"] = max_codes
            elif random_n is not None:
                try:
                    rn = int(random_n)
                except (TypeError, ValueError):
                    return jsonify({"ok": False, "error": "随机股票数量须为整数"}), 400
                if max_codes > 0 and (rn < 1 or rn > max_codes):
                    return jsonify({"ok": False, "error": f"游客随机股票数量须为 1~{max_codes} 只"}), 403
            else:
                return jsonify({"ok": False, "error": "游客请选择「指定股票代码」（最多 10 只，不足自动随机补齐）或「随机股票」（≤10 只）"}), 403
            try:
                from datetime import date as _date

                d0 = _date.fromisoformat(str(params_raw.get("start")))
                d1 = _date.fromisoformat(str(params_raw.get("end")))
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "请填写回测区间（开始/结束日期）"}), 400
            if pol["max_days"] > 0 and ((d1 - d0).days > pol["max_days"] or d0 > d1):
                return jsonify({"ok": False, "error": "游客仅支持近 10 年内的区间。注册会员后不限"}), 403
            # QRE-SAAS-ACCESS-HARDENING-001：归属键由会话 Cookie 派生（缺失时本次
            # 请求签发，响应带上 Set-Cookie）；同 IP 旧结果在新会话首次创建任务时
            # 一次性迁移到本会话（先迁移后计数，今日旧任务照占当日配额）。
            guest_key, new_guest_sid = _guest_identity(app)
            if new_guest_sid is not None:
                _migrate_legacy_guest_jobs(app, engine, guest_key)
            used = 0
            if kind == "full":
                with engine.connect() as conn:
                    used = conn.execute(
                        text(
                            "SELECT count(*) FROM jobs WHERE guest_key = :k "
                            "AND kind = 'full' AND created_at::date = now()::date"
                        ),
                        {"k": guest_key},
                    ).scalar_one()
            if kind == "full" and pol["daily_full_limit"] > 0 and used >= pol["daily_full_limit"]:
                # 403 也要带会话 Cookie：迁移后的归属得让浏览器拿到
                return _with_guest_cookie(app, (
                    jsonify({"ok": False, "error": "游客每日可回测 1 次（今日已用完）。注册会员后不限次数且记录永久保存"}),
                    403,
                ), new_guest_sid)

        if uid is None and guest_key is None:
            return jsonify({"ok": False, "error": "未登录（Authorization: Bearer <token>）"}), 401
        params = params_raw
        name = str(data.get("name") or "未命名策略").strip() or "未命名策略"
        nl_text = data.get("nl_text")
        idem = str(data.get("idempotency_key") or "").strip() or None
        _ensure_weight_class_column(engine)
        # CR-2026-10-04 模块一：提交链路落创建入口模式与向导快照（游客不入策略库）
        entry_mode = _infer_entry_mode(data.get("entry_mode"), nl_text)
        wizard_state = _norm_wizard_state(data.get("wizard_state"))
        _ensure_strategy_asset_columns(engine)
        weight_class = classify_job_weight(kind, params)

        with engine.begin() as conn:
            # 幂等去重（17 协议 §4.4）：同用户同 key 返回既有 job（游客不开放）
            if idem and uid is not None:
                existing = conn.execute(
                    text("SELECT id FROM jobs WHERE user_id = :uid AND idempotency_key = :k"),
                    {"uid": uid, "k": idem},
                ).first()
                if existing is not None:
                    return jsonify({"ok": True, "job_id": existing.id, "deduped": True})
            if uid is not None:
                # dev 后门（SAAS_DEV_AUTH=1）用户可能不存在：自动建行（phone 占位 pending_<id>）
                conn.execute(
                    text(
                        "INSERT INTO users (id, phone) VALUES (:id, :phone) "
                        "ON CONFLICT (id) DO NOTHING"
                    ),
                    {"id": uid, "phone": f"pending_{uid}"},
                )
                # 会员配额（15 号文档）：每日全量回测 3 次，smoke 不占；付费占位同会员
                quota_row = conn.execute(
                    text(
                        "SELECT tier, role, "
                        "(SELECT count(*) FROM jobs j WHERE j.user_id = u.id "
                        " AND j.kind = 'full' AND j.created_at::date = now()::date) AS used_today "
                        "FROM users u WHERE u.id = :uid"
                    ),
                    {"uid": uid},
                ).mappings().one()
                # admin 不限测试次数（运营/开发者账号）；限额参数化读 tier_policies
                pol = _get_policy(app, engine, str(quota_row["tier"] or "member"))
                if kind == "full" and quota_row["role"] != "admin" and pol["daily_full_limit"] > 0 and quota_row["used_today"] >= pol["daily_full_limit"]:
                    return jsonify({"ok": False, "error": "会员每日可全量回测 3 次（今日已用完），明天再来或试试小样本验证"}), 403
            # 会员：按 (user_id, name) upsert 复用策略库行（QRE-SAAS-D3）
            if uid is not None:
                existing = conn.execute(
                    text("SELECT id FROM strategies WHERE user_id = :uid AND name = :name"),
                    {"uid": uid, "name": name},
                ).first()
                if existing is not None:
                    conn.execute(
                        text("UPDATE strategies SET yaml = :yaml, nl_text = :nl, entry_mode = :em, "
                             "wizard_state = COALESCE(CAST(:ws AS jsonb), wizard_state), updated_at = now() "
                             "WHERE id = :id"),
                        {"yaml": yaml_text, "nl": nl_text, "em": entry_mode,
                         "ws": wizard_state, "id": existing.id},
                    )
                    strategy_id = existing.id
                else:
                    strategy_id = None
            else:
                strategy_id = None
            if strategy_id is None:
                strategy_id = conn.execute(
                    text(
                        "INSERT INTO strategies (user_id, name, nl_text, yaml, entry_mode, wizard_state) "
                        "VALUES (:uid, :name, :nl, :yaml, :em, CAST(:ws AS jsonb)) RETURNING id"
                    ),
                    {"uid": uid, "name": name, "nl": nl_text, "yaml": yaml_text,
                     "em": entry_mode, "ws": wizard_state},
                ).scalar_one()
            job_id = conn.execute(
                text(
                    "INSERT INTO jobs (user_id, strategy_id, kind, params, idempotency_key, guest_key, weight_class) "
                    "VALUES (:uid, :sid, :kind, CAST(:params AS jsonb), :idem, :gk, :wc) RETURNING id"
                ),
                {"uid": uid, "sid": strategy_id, "kind": kind,
                 "params": json.dumps(params), "idem": idem, "gk": guest_key, "wc": weight_class},
            ).scalar_one()
        resp: dict[str, Any] = {"ok": True, "job_id": job_id, "strategy_id": strategy_id,
                                "status": "queued", "weight_class": weight_class}
        if basis_note:
            resp["warnings"] = [basis_note]
        if guest_key is not None:
            resp["guest"] = True
            resp["note"] = GUEST_RESULT_NOTE
        response = jsonify(resp)
        if new_guest_sid is not None:
            _attach_guest_cookie(app, response, new_guest_sid)
        return response

    @app.get("/api/jobs")
    @app.get("/api/saas/jobs")
    def api_list_jobs() -> Any:
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT j.*, r.summary AS result_summary, r.data_until AS result_data_until "
                    "FROM jobs j LEFT JOIN results r ON r.job_id = j.id "
                    "WHERE j.user_id = :uid ORDER BY j.created_at DESC, j.id DESC LIMIT 50"
                ),
                {"uid": uid},
            ).mappings().all()
        jobs = []
        for row in rows:
            item = _job_view(row)
            item["result_summary"] = _jsonable(row["result_summary"])
            item["data_until"] = _jsonable(row["result_data_until"])
            jobs.append(item)
        return jsonify({"ok": True, "jobs": jobs})

    @app.get("/api/jobs/<int:job_id>")
    @app.get("/api/saas/jobs/<int:job_id>")
    def api_get_job(job_id: int) -> Any:
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT j.*, r.summary AS result_summary, r.chart_data AS result_chart_data, "
                    "r.artifacts AS result_artifacts, r.data_until AS result_data_until "
                    "FROM jobs j LEFT JOIN results r ON r.job_id = j.id WHERE j.id = :id"
                ),
                {"id": job_id},
            ).mappings().first()
        if row is None:
            if uid is None:
                return jsonify({"ok": False, "error": "未登录"}), 401
            return jsonify({"ok": False, "error": "任务不存在"}), 404
        guest_sid: str | None = None
        if uid is None:
            # QRE-SAAS-ACCESS-HARDENING-001：游客按会话 Cookie 归属（不再纯 IP）。
            # 不存在/他人/异会话统一 401（不泄露存在性）；Cookie 缺失时顺手签发，
            # 让随后的轮询（new.html pollJob）带上会话。
            guest_key, guest_sid = _guest_identity(app)
            if row["user_id"] is not None or row["guest_key"] != guest_key:
                return _with_guest_cookie(
                    app, (jsonify({"ok": False, "error": "未登录"}), 401), guest_sid)
        elif row["user_id"] != uid:
            # 他人任务与不存在一视同仁（404，不暴露任务存在性）
            return jsonify({"ok": False, "error": "任务不存在"}), 404
        item = _job_view(row)
        # QRE-SAAS-FIRST-SUCCESS-UX-001：排队位置 + worker 在线布尔（只读口径复用）
        item.update(_job_runtime_fields(engine, row))
        if row["status"] == "completed":
            item["result"] = {
                "summary": _jsonable(row["result_summary"]),
                "chart_data": _jsonable(row["result_chart_data"]),
                "artifacts": _jsonable(row["result_artifacts"]),
                "data_until": _jsonable(row["result_data_until"]),
            }
        return _attach_guest_cookie(app, jsonify({"ok": True, "job": item}), guest_sid)

    @app.post("/api/jobs/<int:job_id>/cancel")
    @app.post("/api/saas/jobs/<int:job_id>/cancel")
    def api_cancel_job(job_id: int) -> Any:
        """用户取消（17 协议 §5）：queued 直接 canceled；执行中置 cancel_requested，
        worker 下次心跳发现后自行终止；终态 409。
        QRE-SAAS-ACCESS-HARDENING-001：游客按会话 Cookie 归属取消（同会话可取消，
        异会话/无 Cookie 401，不泄露存在性）；登录用户他人任务 404。"""
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        guest_key: str | None = None
        guest_sid: str | None = None
        if uid is None:
            guest_key, guest_sid = _guest_identity(app)
        with engine.begin() as conn:
            _reap_expired(conn)
            row = conn.execute(
                text("SELECT * FROM jobs WHERE id = :id FOR UPDATE"),
                {"id": job_id},
            ).mappings().first()
            owned = (
                row is not None and (
                    row["user_id"] == uid if uid is not None
                    else row["user_id"] is None and row["guest_key"] == guest_key
                )
            )
            if not owned:
                # 不存在/他人/异会话一视同仁：登录用户 404，匿名 401（不泄露存在性）
                if uid is None:
                    return _with_guest_cookie(
                        app, (jsonify({"ok": False, "error": "未登录"}), 401), guest_sid)
                return jsonify({"ok": False, "error": "任务不存在"}), 404
            if row["status"] in TERMINAL_STATUSES:
                return jsonify({"ok": False, "error": f"任务已终态（{row['status']}），无法取消"}), 409
            if row["status"] == "queued":
                conn.execute(
                    text("UPDATE jobs SET status = 'canceled', finished_at = now() WHERE id = :id"),
                    {"id": job_id},
                )
                return jsonify({"ok": True, "status": "canceled"})
            conn.execute(
                text("UPDATE jobs SET cancel_requested = true WHERE id = :id"),
                {"id": job_id},
            )
        return jsonify({"ok": True, "status": row["status"], "cancel_requested": True})

    # --- Worker 侧（17 协议 §3；X-Worker-Token） ---

    @app.post("/api/worker/jobs/claim")
    @app.post("/api/saas/worker/jobs/lease")  # 兼容别名
    def api_claim_job() -> Any:
        denied = _check_worker_auth(app)
        if denied is not None:
            return denied
        data = request.get_json(silent=True) or {}
        worker_id = str(data.get("worker_id") or "").strip()
        if not worker_id:
            return jsonify({"ok": False, "error": "缺少 worker_id"}), 400
        try:
            wait_seconds = min(max(float(data.get("wait_seconds") or 0), 0.0), 30.0)
        except (TypeError, ValueError):
            wait_seconds = 0.0
        # R2：任务分级认领。classes="light" 只领轻任务（轻量槽专用）；
        # 缺省/"any" 领任意任务（向后兼容旧 worker）。非法值 400。
        classes = str(data.get("classes") or "any").strip().lower()
        if classes not in ("any", "light"):
            return jsonify({"ok": False, "error": "classes 须为 any/light"}), 400

        engine = _get_engine(app)
        _ensure_weight_class_column(engine)
        class_filter = "AND weight_class = 'light' " if classes == "light" else ""
        deadline = time.monotonic() + wait_seconds
        while True:
            with engine.begin() as conn:
                _reap_expired(conn)
                _touch_worker(conn, worker_id)
                picked = conn.execute(
                    text(
                        "SELECT id FROM jobs "
                        "WHERE status = 'queued' "
                        + class_filter +
                        "ORDER BY priority DESC, created_at LIMIT 1 "
                        "FOR UPDATE SKIP LOCKED"
                    )
                ).first()
                if picked is not None:
                    row = conn.execute(
                        text(
                            "UPDATE jobs SET status = 'leased', attempts = attempts + 1, "
                            "leased_by = :wid, lease_expires_at = now() + :mins * interval '1 minute', "
                            "started_at = COALESCE(started_at, now()), finished_at = NULL, "
                            "error_message = NULL, error_class = NULL, heartbeat_at = NULL, "
                            "progress = 0, progress_message = NULL, upload_token = NULL "
                            "WHERE id = :id RETURNING *"
                        ),
                        {"wid": worker_id, "mins": _lease_minutes(app), "id": picked.id},
                    ).mappings().one()
                    strategy = conn.execute(
                        text("SELECT id, name, nl_text, yaml FROM strategies WHERE id = :sid"),
                        {"sid": row["strategy_id"]},
                    ).mappings().one()
                    job = _job_view(row)
                    job["strategy"] = _jsonable(dict(strategy))
                    job["attempt"] = row["attempts"]
                    # 17 协议字段名：params_json
                    job["params_json"] = job.pop("params")
                    return jsonify({"ok": True, "job": job})
            if time.monotonic() >= deadline:
                # 空响应语义：200 + job:null（17 协议 §3.1）
                return jsonify({"ok": True, "job": None})
            time.sleep(0.5)

    @app.post("/api/worker/jobs/<int:job_id>/heartbeat")
    @app.post("/api/saas/worker/jobs/<int:job_id>/heartbeat")
    def api_heartbeat(job_id: int) -> Any:
        denied = _check_worker_auth(app)
        if denied is not None:
            return denied
        data = request.get_json(silent=True) or {}
        worker_id = str(data.get("worker_id") or "").strip()
        progress = data.get("progress")
        message = data.get("message")
        engine = _get_engine(app)
        with engine.begin() as conn:
            _reap_expired(conn)
            _touch_worker(conn, worker_id)
            row = conn.execute(
                text(
                    "UPDATE jobs SET lease_expires_at = now() + :mins * interval '1 minute', "
                    "heartbeat_at = now(), "
                    "progress = COALESCE(:progress, progress), "
                    "progress_message = COALESCE(:message, progress_message), "
                    "status = CASE WHEN status = 'leased' THEN 'running' ELSE status END "
                    "WHERE id = :id AND status IN ('leased','running','uploading') AND leased_by = :wid "
                    "RETURNING id, lease_expires_at, cancel_requested, status"
                ),
                {"mins": _lease_minutes(app), "id": job_id, "wid": worker_id,
                 "progress": progress if progress is None else int(progress),
                 "message": None if message is None else str(message)},
            ).mappings().first()
        if row is None:
            return jsonify({"ok": False, "error": "任务不存在、非运行中或 leased_by 不匹配"}), 409
        return jsonify({
            "ok": True, "job_id": row["id"],
            "lease_expires_at": _jsonable(row["lease_expires_at"]),
            "cancel_requested": bool(row["cancel_requested"]),
            "status": row["status"],
        })

    @app.post("/api/worker/status")
    def api_worker_status() -> Any:
        """R3 切片1：worker 实时状态上报（槽位占用 + 内存水位）。

        body: {worker_id, mem_available_mb, mem_total_mb,
               slots: [{name, kind(light/heavy), busy, job_id}],
               limits: {light_slots, heavy_slots, light_min_avail_mb, heavy_min_avail_mb}}
        整个负载原样落 workers.status（JSONB），status_at=now()，同时刷新
        last_heartbeat_at。旧 worker 不上报时列为 NULL，管理台降级展示。
        R3 切片2：响应新增 desired_config（worker_configs 表该 worker 的期望
        槽位/闸门配置 + version；无配置则 null），worker 侧据此比对记日志。
        """
        denied = _check_worker_auth(app)
        if denied is not None:
            return denied
        data = request.get_json(silent=True) or {}
        worker_id = str(data.get("worker_id") or "").strip()
        if not worker_id:
            return jsonify({"ok": False, "error": "缺少 worker_id"}), 400
        slots = data.get("slots")
        if slots is not None and not isinstance(slots, list):
            return jsonify({"ok": False, "error": "slots 须为数组"}), 400
        limits = data.get("limits")
        if limits is not None and not isinstance(limits, dict):
            return jsonify({"ok": False, "error": "limits 须为对象"}), 400
        status = {
            "mem_available_mb": data.get("mem_available_mb"),
            "mem_total_mb": data.get("mem_total_mb"),
            "slots": slots or [],
            "limits": limits or {},
        }
        engine = _get_engine(app)
        _ensure_worker_status_columns(engine)
        _ensure_worker_configs(engine)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO workers (name, last_heartbeat_at, status, status_at) "
                    "VALUES (:wid, now(), CAST(:status AS jsonb), now()) "
                    "ON CONFLICT (name) DO UPDATE SET last_heartbeat_at = now(), "
                    "status = CAST(:status AS jsonb), status_at = now()"
                ),
                {"wid": worker_id, "status": json.dumps(status)},
            )
            # R3 切片2：回带该 worker 的期望配置（无配置 → null）
            desired_row = conn.execute(
                text("SELECT * FROM worker_configs WHERE worker_id = :wid"),
                {"wid": worker_id},
            ).mappings().first()
        return jsonify({
            "ok": True,
            "desired_config": _worker_config_view(desired_row) if desired_row else None,
        })

    @app.get("/api/worker/watches")
    def api_worker_watches() -> Any:
        """CR-2026-10-04 模块二：扫描脚本拉取全部 enabled watch + 策略 yaml + scope。
        scan_enabled=false 层级的 watch 不下发。"""
        denied = _check_worker_auth(app)
        if denied is not None:
            return denied
        engine = _get_engine(app)
        _ensure_signal_tables(engine)
        _ensure_tier_policies(engine)
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT w.id AS watch_id, w.strategy_id, w.scope_type, w.scope_payload, "
                    "s.name AS strategy_name, s.yaml, u.tier "
                    "FROM strategy_watches w "
                    "JOIN strategies s ON s.id = w.strategy_id "
                    "JOIN users u ON u.id = w.user_id "
                    "WHERE w.enabled ORDER BY w.id"
                )
            ).mappings().all()
        watches = []
        for r in rows:
            pol = _get_policy(app, engine, str(r["tier"] or "member"))
            if not pol.get("scan_enabled", True):
                continue
            watches.append(_jsonable({
                "watch_id": r["watch_id"], "strategy_id": r["strategy_id"],
                "strategy_name": r["strategy_name"], "yaml": r["yaml"],
                "scope_type": r["scope_type"], "scope_payload": r["scope_payload"],
            }))
        return jsonify({"ok": True, "watches": watches})

    @app.post("/api/worker/signals")
    def api_worker_signals_ingest() -> Any:
        """模块二：批量回传信号事件（唯一约束 ON CONFLICT DO NOTHING，重跑幂等）。"""
        denied = _check_worker_auth(app)
        if denied is not None:
            return denied
        data = request.get_json(silent=True) or {}
        events = data.get("events")
        if not isinstance(events, list) or not events:
            return jsonify({"ok": False, "error": "events 须为非空数组"}), 400
        if len(events) > 10000:
            return jsonify({"ok": False, "error": "单次最多 10000 条"}), 400
        clean = []
        for i, ev in enumerate(events):
            if not isinstance(ev, dict):
                return jsonify({"ok": False, "error": f"events[{i}] 须为对象"}), 400
            sig = str(ev.get("signal_type") or "")
            td = str(ev.get("trade_date") or "")
            code = str(ev.get("ts_code") or "").strip()
            if sig not in ("entry", "exit"):
                return jsonify({"ok": False, "error": f"events[{i}].signal_type 须为 entry/exit"}), 400
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", td):
                return jsonify({"ok": False, "error": f"events[{i}].trade_date 须为 YYYY-MM-DD"}), 400
            try:
                from datetime import date as _date
                _date.fromisoformat(td)  # 真实日期校验（2026-13-01 之类非法值拒收）
            except ValueError:
                return jsonify({"ok": False, "error": f"events[{i}].trade_date 非法日期"}), 400
            if not code or len(code) > 16:
                return jsonify({"ok": False, "error": f"events[{i}].ts_code 非法"}), 400
            price = ev.get("price")
            try:
                price = None if price is None else float(price)
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": f"events[{i}].price 须为数值"}), 400
            clean.append({"wid": ev.get("watch_id"), "td": td, "code": code,
                          "sig": sig, "price": price})
        engine = _get_engine(app)
        _ensure_signal_tables(engine)
        inserted = 0
        with engine.begin() as conn:
            for ev in clean:
                try:
                    wid = int(ev["wid"])
                except (TypeError, ValueError):
                    return jsonify({"ok": False, "error": "watch_id 须为整数"}), 400
                res = conn.execute(
                    text("INSERT INTO signal_events (watch_id, trade_date, ts_code, signal_type, price) "
                         "VALUES (:wid, :td, :code, :sig, :price) "
                         "ON CONFLICT (watch_id, trade_date, ts_code, signal_type) DO NOTHING"),
                    {"wid": wid, "td": ev["td"], "code": ev["code"],
                     "sig": ev["sig"], "price": ev["price"]},
                )
                inserted += res.rowcount
        return jsonify({"ok": True, "received": len(clean), "inserted": inserted})

    @app.get("/api/worker/showcase/jobs")
    def api_worker_showcase_jobs() -> Any:
        """QRE-SAAS-SHOWCASE 阶段二：滚动器拉取激活 showcase 的策略 yaml + 回测参数
        + 已回传的最大 trade_date（增量起点）。"""
        denied = _check_worker_auth(app)
        if denied is not None:
            return denied
        engine = _get_engine(app)
        _ensure_signal_tables(engine)
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT sc.job_id, sc.title, s.yaml, s.name AS strategy_name, j.params, "
                    "(SELECT max(d.trade_date) FROM showcase_daily d WHERE d.job_id = sc.job_id) AS last_daily "
                    "FROM showcase sc "
                    "JOIN jobs j ON j.id = sc.job_id "
                    "JOIN strategies s ON s.id = j.strategy_id "
                    "WHERE sc.is_active AND j.status = 'completed' ORDER BY sc.sort_order, sc.job_id"
                )
            ).mappings().all()
        return jsonify({"ok": True, "jobs": _jsonable([dict(r) for r in rows])})

    @app.post("/api/worker/showcase/jobs/<int:job_id>/daily")
    def api_worker_showcase_daily_ingest(job_id: int) -> Any:
        """阶段二：滚动器批量回传逐日组合收益（主键幂等 upsert，重跑安全）。"""
        denied = _check_worker_auth(app)
        if denied is not None:
            return denied
        data = request.get_json(silent=True) or {}
        rows = data.get("rows")
        if not isinstance(rows, list) or not rows:
            return jsonify({"ok": False, "error": "rows 须为非空数组"}), 400
        if len(rows) > 500:
            return jsonify({"ok": False, "error": "单次最多 500 行"}), 400
        clean = []
        from datetime import date as _date
        for i, r in enumerate(rows):
            if not isinstance(r, dict):
                return jsonify({"ok": False, "error": f"rows[{i}] 须为对象"}), 400
            td = str(r.get("trade_date") or "")
            try:
                _date.fromisoformat(td)
            except ValueError:
                return jsonify({"ok": False, "error": f"rows[{i}].trade_date 须为合法 YYYY-MM-DD"}), 400
            try:
                dr = float(r.get("daily_return"))
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": f"rows[{i}].daily_return 须为数值"}), 400
            def _f(key):
                v = r.get(key)
                if v is None:
                    return None
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return None
            def _i(key):
                v = r.get(key)
                if v is None:
                    return None
                try:
                    return int(v)
                except (TypeError, ValueError):
                    return None
            clean.append({"td": td, "dr": dr, "eq": _f("equity"),
                          "np": _i("n_positions"), "ne": _i("n_entries"), "nx": _i("n_exits")})
        engine = _get_engine(app)
        _ensure_signal_tables(engine)
        with engine.begin() as conn:
            if conn.execute(text("SELECT 1 FROM showcase WHERE job_id = :id AND is_active"),
                            {"id": job_id}).first() is None:
                return jsonify({"ok": False, "error": "非激活 showcase 任务"}), 404
            upserted = 0
            for r in clean:
                res = conn.execute(
                    text("INSERT INTO showcase_daily (job_id, trade_date, daily_return, equity, "
                         "n_positions, n_entries, n_exits) "
                         "VALUES (:id, :td, :dr, :eq, :np, :ne, :nx) "
                         "ON CONFLICT (job_id, trade_date) DO UPDATE SET "
                         "daily_return = EXCLUDED.daily_return, equity = EXCLUDED.equity, "
                         "n_positions = EXCLUDED.n_positions, n_entries = EXCLUDED.n_entries, "
                         "n_exits = EXCLUDED.n_exits"),
                    {"id": job_id, **r},
                )
                upserted += res.rowcount
            last = conn.execute(
                text("SELECT max(trade_date) FROM showcase_daily WHERE job_id = :id"),
                {"id": job_id},
            ).scalar_one()
        return jsonify({"ok": True, "upserted": upserted, "data_until": _jsonable(last)})

    @app.post("/api/worker/jobs/<int:job_id>/result/meta")
    def api_result_meta(job_id: int) -> Any:
        """17 协议 §3.3 第一步：回传元数据 + 文件清单 → upload_token，job 置 uploading；
        清单为空则直接 completed。"""
        denied = _check_worker_auth(app)
        if denied is not None:
            return denied
        data = request.get_json(silent=True) or {}
        worker_id = str(data.get("worker_id") or "").strip()
        engine = _get_engine(app)
        with engine.begin() as conn:
            job = conn.execute(
                text("SELECT * FROM jobs WHERE id = :id FOR UPDATE"),
                {"id": job_id},
            ).mappings().first()
            if job is None:
                return jsonify({"ok": False, "error": "任务不存在"}), 404
            # 幂等（17 协议 §4.3）：已 completed 的重复 meta 提交 → 200 no-op
            if job["status"] == "completed":
                return jsonify({"ok": True, "status": "completed", "deduped": True})
            if job["status"] not in ("leased", "running", "uploading") or job["leased_by"] != worker_id:
                return jsonify({"ok": False, "error": "任务非当前 worker 持有"}), 409
            if job["cancel_requested"]:
                conn.execute(
                    text("UPDATE jobs SET status='canceled', finished_at=now(), "
                         "lease_expires_at=NULL WHERE id=:id"),
                    {"id": job_id},
                )
                return jsonify({"ok": True, "status": "canceled"})

            summary = data.get("summary") or {}
            chart_data = data.get("chart_data") or {}
            files = data.get("files") or []
            upload_token = secrets.token_urlsafe(24)
            # QRE-SAAS-RESULT-CONTRACT-001：在 worker 回传接收层注入结果合同
            # （版本 / data_until / 两种收益口径 / 验证状态），不改 worker 与引擎。
            contract = build_result_contract(data_until=data.get("data_until"))
            contract_cols = ", result_contract" if _ensure_result_contract_column(engine) else ""
            contract_vals = ", CAST(:contract AS jsonb)" if contract_cols else ""
            contract_set = (", result_contract = EXCLUDED.result_contract"
                            if contract_cols else "")
            conn.execute(
                text(
                    "INSERT INTO results (job_id, user_id, summary, chart_data, artifacts, "
                    "data_until" + contract_cols + ") "
                    "VALUES (:jid, :uid, CAST(:summary AS jsonb), CAST(:chart AS jsonb), "
                    "CAST(:artifacts AS jsonb), :data_until" + contract_vals + ") "
                    "ON CONFLICT (job_id) DO UPDATE SET "
                    "summary = EXCLUDED.summary, chart_data = EXCLUDED.chart_data, "
                    "artifacts = EXCLUDED.artifacts, data_until = EXCLUDED.data_until"
                    + contract_set
                ),
                {
                    "jid": job_id,
                    "uid": job["user_id"],
                    "summary": json.dumps(summary),
                    "chart": json.dumps(chart_data),
                    "artifacts": json.dumps(files),
                    "data_until": data.get("data_until"),
                    "contract": json.dumps(contract),
                },
            )
            if not files:
                conn.execute(
                    text("UPDATE jobs SET status='completed', finished_at=now(), "
                         "lease_expires_at=NULL WHERE id=:id"),
                    {"id": job_id},
                )
                return jsonify({"ok": True, "status": "completed"})
            conn.execute(
                text("UPDATE jobs SET status='uploading', upload_token=:tok, "
                     "lease_expires_at = now() + interval '30 minutes' WHERE id=:id"),
                {"tok": upload_token, "id": job_id},
            )
        return jsonify({"ok": True, "status": "uploading", "upload_token": upload_token})

    @app.post("/api/worker/jobs/<int:job_id>/result/files")
    def api_result_files(job_id: int) -> Any:
        """17 协议 §3.3 第二步：multipart 上传产物文件（校验 upload_token + sha256），
        全部到齐 → completed。文件落 SAAS_UPLOAD_DIR（默认 outputs/saas_uploads/job_<id>/）。"""
        import hashlib as _hashlib

        denied = _check_worker_auth(app)
        if denied is not None:
            return denied
        engine = _get_engine(app)
        upload_root = Path(_cfg(app, "SAAS_UPLOAD_DIR", "outputs/saas_uploads") or "outputs/saas_uploads")
        with engine.begin() as conn:
            job = conn.execute(
                text("SELECT * FROM jobs WHERE id = :id FOR UPDATE"),
                {"id": job_id},
            ).mappings().first()
            if job is None:
                return jsonify({"ok": False, "error": "任务不存在"}), 404
            if job["status"] != "uploading":
                return jsonify({"ok": False, "error": "任务不在产物上传阶段"}), 409
            if not job["upload_token"] or request.args.get("upload_token") != job["upload_token"]:
                return jsonify({"ok": False, "error": "upload_token 无效"}), 401
            manifest = {f["name"]: f for f in
                        ((conn.execute(text("SELECT artifacts FROM results WHERE job_id=:id"),
                                       {"id": job_id}).scalar()) or [])}
            job_dir = upload_root / f"job_{job_id}"
            job_dir.mkdir(parents=True, exist_ok=True)
            uploaded = []
            for name, file in request.files.items():
                # C5 修复：清单键是带子目录的相对路径（如 000001.SZ/trades.csv），
                # 按完整相对路径匹配并保留子目录落盘；仅拒绝绝对路径与 .. 穿越
                rel = Path(name)
                if rel.is_absolute() or ".." in rel.parts:
                    return jsonify({"ok": False, "error": f"非法文件名: {name}"}), 400
                safe = str(rel)
                if manifest and safe not in manifest:
                    return jsonify({"ok": False, "error": f"文件不在清单内: {safe}"}), 400
                blob = file.read()
                expected = (manifest.get(safe) or {}).get("sha256")
                if expected and _hashlib.sha256(blob).hexdigest() != expected:
                    return jsonify({"ok": False, "error": f"文件校验失败: {safe}"}), 400
                dest = job_dir / safe
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(blob)
                uploaded.append(safe)
            remaining = [n for n in manifest if not (job_dir / n).exists()]
            if remaining:
                return jsonify({"ok": True, "status": "uploading", "uploaded": uploaded,
                                "remaining": remaining})
            conn.execute(
                text("UPDATE jobs SET status='completed', finished_at=now(), "
                     "lease_expires_at=NULL, upload_token=NULL WHERE id=:id"),
                {"id": job_id},
            )
            # symbol_detail 按需任务：产物落到父 job 目录（详情页只认父 job 目录），
            # 失败不拖垮 completed 状态（gen-status 会因产物未就位允许重试）
            if job["kind"] == "symbol_detail":
                try:
                    p = job["params"] or {}
                    parent_id = int(p.get("parent_job_id"))
                    code = str(p.get("ts_code"))
                    src = job_dir / "_symbol_details" / f"{code}.json.gz"
                    if src.is_file():
                        dst_dir = upload_root / f"job_{parent_id}" / "_symbol_details"
                        dst_dir.mkdir(parents=True, exist_ok=True)
                        (dst_dir / f"{code}.json.gz").write_bytes(src.read_bytes())
                except Exception:
                    pass
        return jsonify({"ok": True, "status": "completed", "uploaded": uploaded})

    @app.post("/api/worker/jobs/<int:job_id>/fail")
    def api_fail_job(job_id: int) -> Any:
        """17 协议 §3.4：error_class 分类；不可重试直接 failed，可重试回队。"""
        denied = _check_worker_auth(app)
        if denied is not None:
            return denied
        data = request.get_json(silent=True) or {}
        worker_id = str(data.get("worker_id") or "").strip()
        error_class = str(data.get("error_class") or "engine_error")
        if error_class not in ERROR_CLASSES:
            return jsonify({"ok": False, "error": f"error_class 须为 {'/'.join(ERROR_CLASSES)}"}), 400
        error_message = str(data.get("error_message") or data.get("error") or "worker 报告失败")
        retryable = bool(data.get("retryable", error_class not in NON_RETRYABLE))
        engine = _get_engine(app)
        with engine.begin() as conn:
            job = conn.execute(
                text("SELECT * FROM jobs WHERE id = :id FOR UPDATE"),
                {"id": job_id},
            ).mappings().first()
            if job is None:
                return jsonify({"ok": False, "error": "任务不存在"}), 404
            if job["status"] not in ("leased", "running", "uploading") or job["leased_by"] != worker_id:
                return jsonify({"ok": False, "error": "任务非当前 worker 持有"}), 409
            if error_class == "canceled":
                conn.execute(
                    text("UPDATE jobs SET status='canceled', error_class='canceled', "
                         "error_message=:em, finished_at=now(), lease_expires_at=NULL WHERE id=:id"),
                    {"em": error_message, "id": job_id},
                )
                return jsonify({"ok": True, "job_id": job_id, "status": "canceled"})
            if not retryable or job["attempts"] >= job["max_attempts"]:
                conn.execute(
                    text("UPDATE jobs SET status='failed', error_class=:ec, error_message=:em, "
                         "finished_at=now(), lease_expires_at=NULL WHERE id=:id"),
                    {"ec": error_class, "em": error_message, "id": job_id},
                )
                final_status = "failed"
            else:
                conn.execute(
                    text("UPDATE jobs SET status='queued', error_class=:ec, error_message=:em, "
                         "leased_by=NULL, lease_expires_at=NULL WHERE id=:id"),
                    {"ec": error_class, "em": error_message, "id": job_id},
                )
                final_status = "queued"
        return jsonify({"ok": True, "job_id": job_id, "status": final_status})

    # --- 过渡版兼容：POST /api/saas/worker/jobs/<id>/result（单包 done/failed） ---
    @app.post("/api/saas/worker/jobs/<int:job_id>/result")
    def api_report_result_legacy(job_id: int) -> Any:
        """旧单包回传：done → result/meta 语义（无文件直接 completed）；
        failed → fail 语义（engine_error 可重试）。"""
        denied = _check_worker_auth(app)
        if denied is not None:
            return denied
        data = request.get_json(silent=True) or {}
        worker_id = str(data.get("worker_id") or "").strip()
        status = str(data.get("status") or "")
        if status not in ("done", "completed", "failed"):
            return jsonify({"ok": False, "error": "status 须为 done/failed"}), 400
        engine = _get_engine(app)
        with engine.begin() as conn:
            job = conn.execute(
                text("SELECT * FROM jobs WHERE id = :id FOR UPDATE"),
                {"id": job_id},
            ).mappings().first()
            if job is None:
                return jsonify({"ok": False, "error": "任务不存在"}), 404
            if job["status"] not in ("leased", "running", "uploading") or job["leased_by"] != worker_id:
                return jsonify({"ok": False, "error": "任务非当前 worker 持有"}), 409
            if status in ("done", "completed"):
                # QRE-SAAS-RESULT-CONTRACT-001：旧单包回传同样在接收层注入合同
                contract = build_result_contract(data_until=data.get("data_until"))
                contract_cols = ", result_contract" if _ensure_result_contract_column(engine) else ""
                contract_vals = ", CAST(:contract AS jsonb)" if contract_cols else ""
                contract_set = (", result_contract = EXCLUDED.result_contract"
                                if contract_cols else "")
                conn.execute(
                    text(
                        "INSERT INTO results (job_id, user_id, summary, chart_data, artifacts, data_until"
                        + contract_cols + ") "
                        "VALUES (:jid, :uid, CAST(:summary AS jsonb), CAST(:chart AS jsonb), "
                        "CAST(:artifacts AS jsonb), :data_until" + contract_vals + ") "
                        "ON CONFLICT (job_id) DO UPDATE SET "
                        "summary = EXCLUDED.summary, chart_data = EXCLUDED.chart_data, "
                        "artifacts = EXCLUDED.artifacts, data_until = EXCLUDED.data_until"
                        + contract_set
                    ),
                    {
                        "jid": job_id, "uid": job["user_id"],
                        "summary": json.dumps(data.get("summary") or {}),
                        "chart": json.dumps(data.get("chart_data") or {}),
                        "artifacts": json.dumps(data.get("artifacts") or []),
                        "data_until": data.get("data_until"),
                        "contract": json.dumps(contract),
                    },
                )
                conn.execute(
                    text("UPDATE jobs SET status='completed', finished_at=now(), "
                         "error_message=NULL, error_class=NULL, lease_expires_at=NULL WHERE id=:id"),
                    {"id": job_id},
                )
                return jsonify({"ok": True, "job_id": job_id, "status": "completed"})
            error_message = str(data.get("error") or "worker 报告失败")
            if job["attempts"] >= job["max_attempts"]:
                conn.execute(
                    text("UPDATE jobs SET status='failed', error_class='engine_error', "
                         "error_message=:em, finished_at=now(), lease_expires_at=NULL WHERE id=:id"),
                    {"em": error_message, "id": job_id},
                )
                final_status = "failed"
            else:
                conn.execute(
                    text("UPDATE jobs SET status='queued', error_class='engine_error', "
                         "error_message=:em, leased_by=NULL, lease_expires_at=NULL WHERE id=:id"),
                    {"em": error_message, "id": job_id},
                )
                final_status = "queued"
        return jsonify({"ok": True, "job_id": job_id, "status": final_status})

    # --- 结果系统（QRE-SAAS-RESULTS / B1+B2；语义对齐 8081 lab_result 路由） ---

    # 策略信息列（QRE-SAAS-JOB-STRATEGY-CARD）：详情页「策略信息」折叠卡数据源
    _STRATEGY_COLS = (
        "s.name AS strategy_name, s.yaml AS strategy_yaml, "
        "s.entry_mode AS strategy_entry_mode, s.nl_text AS strategy_nl_text, "
        "s.wizard_state AS strategy_wizard_state, s.created_at AS strategy_created_at"
    )

    def _result_cols(engine: Engine) -> str:
        """results 投影列；result_contract 列不可用（ECS 老库未 apply schema）时降级省略，
        读取侧按显式例外表解析，缺列永不等于 verified。"""
        cols = ("r.summary AS result_summary, r.chart_data AS result_chart_data, "
                "r.artifacts AS result_artifacts, r.data_until AS result_data_until")
        if _ensure_result_contract_column(engine):
            cols += ", r.result_contract AS result_result_contract"
        return cols

    def _contract_of(row: Any) -> dict[str, Any]:
        """行 → 合同视图（job_id + 已存合同；无列/无值时走显式例外表）。"""
        return _jsonable(contract_view(row["id"], row.get("result_result_contract"),
                                       row.get("result_data_until")))

    def _load_job_for_user(job_id: int, uid: int) -> Any:
        """取 job+strategy+result；非本人/不存在返回 None（不暴露存在性）。"""
        engine = _get_engine(app)
        with engine.connect() as conn:
            return conn.execute(
                text(
                    "SELECT j.*, " + _STRATEGY_COLS + ", " + _result_cols(engine) +
                    " FROM jobs j JOIN strategies s ON s.id = j.strategy_id "
                    "LEFT JOIN results r ON r.job_id = j.id "
                    "WHERE j.id = :id AND j.user_id = :uid"
                ),
                {"id": job_id, "uid": uid},
            ).mappings().first()

    def _load_job_for_guest(job_id: int, guest_key: str) -> Any:
        """游客 job 按会话归属键取行（QRE-SAAS-ACCESS-HARDENING-001：键由 Cookie
        派生，不再按 IP）；不匹配返回 None（不暴露存在性）。"""
        engine = _get_engine(app)
        with engine.connect() as conn:
            return conn.execute(
                text(
                    "SELECT j.*, " + _STRATEGY_COLS + ", " + _result_cols(engine) +
                    " FROM jobs j JOIN strategies s ON s.id = j.strategy_id "
                    "LEFT JOIN results r ON r.job_id = j.id "
                    "WHERE j.id = :id AND j.user_id IS NULL AND j.guest_key = :gk"
                ),
                {"id": job_id, "gk": guest_key},
            ).mappings().first()

    def _load_job_public(job_id: int) -> Any:
        """showcase 公开只读通道：不看归属，仅当 job 在 showcase 白名单且激活、
        且结果合同为 verified 时放行（P0-1B）。调用方需先查 showcase 表；
        此处只做取行。"""
        engine = _get_engine(app)
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT j.*, " + _STRATEGY_COLS + ", " + _result_cols(engine) +
                    " FROM jobs j JOIN strategies s ON s.id = j.strategy_id "
                    "LEFT JOIN results r ON r.job_id = j.id "
                    "WHERE j.id = :id"
                ),
                {"id": job_id},
            ).mappings().first()
        if row is not None and not _contract_of(row)["verified"]:
            return None
        return row

    def _is_showcase_job(job_id: int) -> bool:
        engine = _get_engine(app)
        _ensure_signal_tables(engine)  # showcase 表与信号表同批惰性建表
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT 1 FROM showcase WHERE job_id = :id AND is_active"),
                {"id": job_id},
            ).first() is not None

    def _load_job_for_share(job_id: int, token: str) -> Any:
        """P1 只读分享通道（QRE-SAAS-READONLY-SHARE）：token 哈希命中、未撤销、
        未过期且绑定本 job 时返回行（不看登录/游客会话；未验证结果同样放行，
        合同徽标由 summary 原样返回）。其余一切情况返回 None——调用方按原有
        匿名 401 / 登录他人 404 语义继续，不降级、不泄露链接状态。"""
        engine = _get_engine(app)
        if not _ensure_share_links(engine):
            return None
        with engine.connect() as conn:
            link = conn.execute(
                text("SELECT job_id FROM share_links "
                     "WHERE token_hash = :h AND revoked_at IS NULL "
                     "AND (expires_at IS NULL OR expires_at > now())"),
                {"h": _share_token_hash(app, token)},
            ).mappings().first()
            if link is None or int(link["job_id"]) != int(job_id):
                return None
            return conn.execute(
                text(
                    "SELECT j.*, " + _STRATEGY_COLS + ", " + _result_cols(engine) +
                    " FROM jobs j JOIN strategies s ON s.id = j.strategy_id "
                    "LEFT JOIN results r ON r.job_id = j.id "
                    "WHERE j.id = :id"
                ),
                {"id": job_id},
            ).mappings().first()

    def _public_readonly_kind() -> str | None:
        """当前请求的公开只读通道：share / showcase / None（本人与游客正常访问）。"""
        if getattr(g, "share_readonly", False):
            return "share"
        if getattr(g, "showcase_readonly", False):
            return "showcase"
        return None

    def _is_public_readonly() -> bool:
        return _public_readonly_kind() is not None

    def _result_record(row: Any) -> dict[str, Any]:
        """把 job 行构造成 lab_result.py 认识的 run record（复用 8081 解析函数的关键）：
        output_dir 指向上传目录 job_<id>/（产物同名同格式），_find_output_file 走 rglob。"""
        params = row["params"] or {}
        upload_root = Path(_cfg(app, "SAAS_UPLOAD_DIR", "outputs/saas_uploads") or "outputs/saas_uploads")
        codes = params.get("codes") or []
        if isinstance(codes, str):
            codes = [c.strip() for c in codes.split(",") if c.strip()]
        return {
            "run_id": f"job-{row['id']}",
            "mode": params.get("mode") or "shared",
            "start": params.get("start"),
            "end": params.get("end"),
            "codes": codes,
            "initial_cash": params.get("initial_cash"),
            "max_positions": params.get("max_positions"),
            "engine_impl": params.get("engine_impl") or "simulator",
            "output_dir": str(upload_root / f"job_{row['id']}"),
            "artifacts": {},
        }

    def _require_completed_result(job_id: int) -> Any:
        """返回 (row, error_response)。未完成 409；不存在/非本人 404。
        showcase 白名单 job 对任何人放行只读（g.showcase_readonly=True），
        但 P0-1B 起仅当结果合同为 verified——未验证的经典策略不再公开可见
        （白名单行/job/产物不动，本人仍按原权限可见）；
        复用此入口的写端点必须显式拒绝 showcase_readonly。
        P1 只读分享（QRE-SAAS-READONLY-SHARE）：?share=<token> 有效时按 token
        对应 job 放行只读（g.share_readonly=True，readonly_kind="share"），不依赖
        登录或游客会话；无效/过期/撤销/错 job 一律不降级——匿名仍 401、登录他人
        仍 404，错误体与既有语义逐字节一致。
        游客按会话 Cookie 归属（QRE-SAAS-ACCESS-HARDENING-001）：匿名且不匹配
        时 401（与不存在一致，不泄露存在性），Cookie 缺失时顺手签发。"""
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        guest_sid: str | None = None
        row = None
        share_token = (request.args.get("share") or "").strip()
        if share_token:
            row = _load_job_for_share(job_id, share_token)
            if row is not None:
                g.share_readonly = True
        if row is None:
            if uid is None:
                guest_key, guest_sid = _guest_identity(app)
                row = _load_job_for_guest(job_id, guest_key)
                if row is None:
                    if not share_token and _is_showcase_job(job_id):
                        row = _load_job_public(job_id)
                        g.showcase_readonly = row is not None
                    if row is None:
                        return None, _with_guest_cookie(
                            app, (jsonify({"ok": False, "error": "未登录"}), 401), guest_sid)
            else:
                row = _load_job_for_user(job_id, uid)
                if row is None:
                    if not share_token and _is_showcase_job(job_id):
                        row = _load_job_public(job_id)
                        g.showcase_readonly = row is not None
                    if row is None:
                        return None, (jsonify({"ok": False, "error": "任务不存在"}), 404)
        if row["status"] != "completed":
            # QRE-SAAS-FIRST-SUCCESS-UX-001：未完成时把排队位置、worker 在线布尔、
            # 真实失败原因与策略 ID 一并返回（仅本任务所有者/既有合法只读调用方
            # 能到达这里；匿名/他人仍在上面 401/404，不泄露存在性）。
            body: dict[str, Any] = {
                "ok": False,
                "error": f"任务未完成（{row['status']}）",
                "status": row["status"],
                "strategy_id": row["strategy_id"],
                "cancel_requested": bool(row["cancel_requested"]),
                "error_class": row["error_class"],
                "error_message": row["error_message"],
            }
            body.update(_job_runtime_fields(engine, row))
            return None, _with_guest_cookie(app, (jsonify(body), 409), guest_sid)
        return row, None

    @app.get("/api/results")
    def api_results_list() -> Any:
        """B1 结果列表：?sort=created_at|excess_return&order=desc|asc&page=&page_size="""
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        sort = request.args.get("sort", "created_at")
        order = "asc" if request.args.get("order") == "asc" else "desc"
        try:
            page = max(1, int(request.args.get("page", 1)))
            page_size = min(100, max(1, int(request.args.get("page_size", 20))))
        except ValueError:
            return jsonify({"ok": False, "error": "page/page_size 须为整数"}), 400
        with engine.connect() as conn:
            contract_col = (", r.result_contract AS result_result_contract"
                            if _ensure_result_contract_column(engine) else "")
            rows = conn.execute(
                text(
                    "SELECT j.id, j.kind, j.status, j.created_at, j.params, "
                    "s.name AS strategy_name, r.summary, r.chart_data, r.data_until"
                    + contract_col +
                    " FROM jobs j JOIN strategies s ON s.id = j.strategy_id "
                    "LEFT JOIN results r ON r.job_id = j.id "
                    "WHERE j.user_id = :uid AND j.kind = 'full' "
                    "ORDER BY j.created_at DESC"
                ),
                {"uid": uid},
            ).mappings().all()
            _ensure_signal_tables(engine)
            showcase_ids = {
                r[0] for r in conn.execute(text("SELECT job_id FROM showcase WHERE is_active"))
            }
        items = []
        for row in rows:
            metrics = ((row["chart_data"] or {}).get("metrics") or {})
            summary = row["summary"] or {}
            params = row["params"] or {}
            # symbol_count 兜底：summary 无此字段时按提交参数推导
            # （指定代码数 / 随机 N 只；都没有 = 全 A，保持 None 由前端显示「全 A 股」）
            symbol_count = summary.get("symbol_count")
            if symbol_count is None:
                codes = params.get("codes")
                if isinstance(codes, str):
                    codes = [c.strip() for c in codes.split(",") if c.strip()]
                if codes:
                    symbol_count = len(codes)
                elif params.get("random_n"):
                    symbol_count = params.get("random_n")
            items.append({
                "job_id": row["id"],
                "strategy_name": row["strategy_name"],
                "status": row["status"],
                "date_start": params.get("start"),
                "date_end": params.get("end"),
                "symbol_count": symbol_count,
                "total_return": summary.get("strategy_total_return"),
                "excess_return": metrics.get("excess_return"),
                "max_drawdown": summary.get("max_drawdown"),
                "win_rate": summary.get("win_rate"),
                "total_trade_count": summary.get("total_trade_count"),
                "data_until": _jsonable(row["data_until"]),
                "created_at": _jsonable(row["created_at"]),
                "showcase": row["id"] in showcase_ids,
                # QRE-SAAS-RESULT-CONTRACT-001：私人历史结果照旧按原权限可见，只加口径标签
                "result_contract": _jsonable(contract_view(
                    row["id"], row.get("result_result_contract"), row["data_until"])),
            })
        if sort == "excess_return":
            items.sort(key=lambda x: (x["excess_return"] is None, x["excess_return"]),
                       reverse=(order == "desc"))
        else:
            items.sort(key=lambda x: x["created_at"] or "", reverse=(order == "desc"))
        total = len(items)
        items = items[(page - 1) * page_size: page * page_size]
        return jsonify({"ok": True, "total": total, "page": page,
                        "page_size": page_size, "items": items})

    @app.delete("/api/results/<int:job_id>")
    def api_result_delete(job_id: int) -> Any:
        """B1 删除：results+jobs 行 + 产物目录（job_<id>/）。策略行保留。
        游客可删除本人会话的游客记录（QRE-SAAS-ACCESS-HARDENING-001：按会话
        Cookie 归属，不再按 IP）；他人/不存在统一 404（不泄露存在性）。"""
        import shutil

        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        guest_sid: str | None = None
        if uid is None:
            guest_key, guest_sid = _guest_identity(app)
            row = _load_job_for_guest(job_id, guest_key)
        else:
            row = _load_job_for_user(job_id, uid)
        if row is None:
            return _with_guest_cookie(
                app, (jsonify({"ok": False, "error": "任务不存在"}), 404), guest_sid)
        upload_root = Path(_cfg(app, "SAAS_UPLOAD_DIR", "outputs/saas_uploads") or "outputs/saas_uploads")
        job_dir = upload_root / f"job_{job_id}"
        if job_dir.is_dir():
            shutil.rmtree(job_dir)
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM results WHERE job_id = :id"), {"id": job_id})
            conn.execute(text("DELETE FROM jobs WHERE id = :id"), {"id": job_id})
        return _attach_guest_cookie(app, jsonify({"ok": True, "deleted": job_id}), guest_sid)

    @app.get("/api/results/<int:job_id>/summary")
    def api_result_summary(job_id: int) -> Any:
        row, err = _require_completed_result(job_id)
        if err:
            return err
        return jsonify({"ok": True, "job_id": job_id,
                        "readonly": _is_public_readonly(),
                        "readonly_kind": _public_readonly_kind(),
                        "strategy_id": row["strategy_id"],
                        "strategy_name": row["strategy_name"],
                        "strategy": _jsonable({
                            "name": row["strategy_name"],
                            "entry_mode": row["strategy_entry_mode"],
                            "nl_text": row["strategy_nl_text"],
                            "wizard_state": row["strategy_wizard_state"],
                            "yaml": row["strategy_yaml"],
                            "created_at": row["strategy_created_at"],
                        }),
                        "summary": _jsonable(row["result_summary"]),
                        "data_until": _jsonable(row["result_data_until"]),
                        # QRE-SAAS-RESULT-CONTRACT-001：合同版本/口径/验证状态随摘要增量返回
                        "result_contract": _contract_of(row)})

    @app.get("/api/results/<int:job_id>/chart-data")
    def api_result_chart_data(job_id: int) -> Any:
        """与 8081 /api/lab/runs/<id>/chart-data 同形态（worker 侧 build_lab_chart_data 产物）。"""
        row, err = _require_completed_result(job_id)
        if err:
            return err
        return jsonify(row["result_chart_data"] or {"ok": False, "error": "无图表数据"})

    @app.get("/api/results/<int:job_id>/tag-analysis")
    def api_result_tag_analysis(job_id: int) -> Any:
        """与 8081 同形态；为 worker 回传的截断版（板块聚合全量+个股 TOP/BOTTOM 各 50）。"""
        row, err = _require_completed_result(job_id)
        if err:
            return err
        tag = (row["result_chart_data"] or {}).get("tag_analysis")
        if not tag:
            return jsonify({"ok": False, "error": "无归因数据"}), 404
        return jsonify(tag)

    @app.get("/api/results/<int:job_id>/risk-analysis")
    def api_result_risk_analysis(job_id: int) -> Any:
        """与 8081 /api/lab/runs/<id>/risk-analysis 同形态；risk_report.json 须在上传产物里
        （未上传或 worker 未生成时 has_report=false，前端显示暂无）。"""
        row, err = _require_completed_result(job_id)
        if err:
            return err
        from quant_research_engine.gui.lab_result import build_lab_risk_view, histogram_from_cumret

        job_dir = Path(_result_record(row)["output_dir"])
        report_path = job_dir / "risk_report.json"
        data: dict[str, Any] = {"ok": True, "job_id": job_id, "has_report": False, "histogram": None}
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                report = None
            if isinstance(report, dict):
                data["has_report"] = True
                data.update(build_lab_risk_view(report))
                # 直方图需要日收益原始序列：SaaS 产物通常没有组合级 equity_curve.csv，
                # 但 chart_data.cumret 是同一交集口径的累计收益，由其差分还原日收益；
                # 不用 total_equity.pct_change（会引入新股注资跳变或误取单股曲线）。
                dist = data.get("dist") or {}
                cumret = (row["result_chart_data"] or {}).get("cumret")
                data["histogram"] = histogram_from_cumret(
                    cumret, dist.get("mean"), dist.get("std")
                )
        return jsonify(_jsonable(data))

    @app.get("/api/results/<int:job_id>/symbols")
    def api_result_symbols(job_id: int) -> Any:
        """个股列表（8081 语义：tag-analysis 驱动的个股贡献聚合）。"""
        row, err = _require_completed_result(job_id)
        if err:
            return err
        tag = (row["result_chart_data"] or {}).get("tag_analysis")
        if not tag:
            return jsonify({"ok": False, "error": "无归因数据"}), 404
        # 跨层按股合并（与 saas 结果页贡献榜同口径）
        by_symbol: dict[str, Any] = {}
        for items in (tag.get("layers") or {}).values():
            for item in items or []:
                for s in item.get("symbols") or []:
                    cur = by_symbol.get(s["ts_code"])
                    if cur is None or abs(s["total_pnl"]) > abs(cur["total_pnl"]):
                        by_symbol[s["ts_code"]] = s
        symbols = sorted(by_symbol.values(), key=lambda s: s["total_pnl"], reverse=True)
        return jsonify({"ok": True, "job_id": job_id, "symbols": _jsonable(symbols)})

    @app.get("/api/results/<int:job_id>/symbols/<ts_code>")
    def api_result_symbol_detail(job_id: int, ts_code: str) -> Any:
        """与 lab 版 /api/lab/runs/<id>/symbol/<ts>/detail 同形态。

        QRE-SAAS-SYMBOL-UX：
        - ts_code 允许不带后缀（如 000001），先按本任务实际交易个股精确匹配，
          匹配不到再按号段推断后缀；非法代码 400。
        - 个股详情优先读 worker 回传的 per-symbol 产物
          （<job_dir>/_symbol_details/<ts_code>.json.gz，含 K线/买卖点/因子/
          收益曲线/磨损明细——ECS 无行情库，lab 版实时查库路径在云上用不了）；
          缺失时回退 build_lab_symbol_detail（staging 等有库部署的既有行为）。
        QRE-SAAS-RESULT-UNDERSTANDING：两条返回路径都注入任务级
        `data_until`（results.data_until，不改 gzip 产物、不回填），供页面头部
        展示数据截止并链接口径说明；缺列/缺值时由前端显示「未声明」，不编日期。
        """
        import gzip

        row, err = _require_completed_result(job_id)
        if err:
            return err
        # 已知代码表：归因里的实际交易个股（截断版可能不全，故仅作匹配辅助）
        known: list[str] = []
        tag = (row["result_chart_data"] or {}).get("tag_analysis") or {}
        for items in (tag.get("layers") or {}).values():
            for item in items or []:
                for s in item.get("symbols") or []:
                    if s.get("ts_code"):
                        known.append(s["ts_code"])
        try:
            code = resolve_ts_code(ts_code, known)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        job_dir = Path(_result_record(row)["output_dir"])
        detail_dir = job_dir / "_symbol_details"
        detail_path = detail_dir / f"{code}.json.gz"
        if not detail_path.exists() and detail_dir.is_dir():
            # 后缀推断与实际回传不一致时的兜底：按 6 位数字前缀找文件
            prefix = code.split(".")[0]
            for p in sorted(detail_dir.glob(f"{prefix}.*.json.gz")):
                detail_path = p
                break
        if detail_path.exists():
            try:
                data = json.loads(gzip.decompress(detail_path.read_bytes()).decode("utf-8"))
            except (OSError, ValueError):
                data = None
            if isinstance(data, dict) and data.get("ok"):
                # 基准指数对齐个股净值日期：复用任务级 chart_data.benchmarks
                # （per-symbol 产物不带基准序列以控制回传体积）
                eq = data.get("equity") or {}
                benches = (row["result_chart_data"] or {}).get("benchmarks") or {}
                eq_dates = eq.get("dates") or []
                if eq_dates and benches:
                    job_dates = (row["result_chart_data"] or {}).get("dates") or []
                    aligned: dict[str, Any] = {}
                    for bcode, b in benches.items():
                        closes = b.get("closes") or []
                        by_date = {d: c for d, c in zip(job_dates, closes)}
                        series = [by_date.get(d) for d in eq_dates]
                        if any(v is not None for v in series):
                            aligned[bcode] = {"name": b.get("name"), "closes": series}
                    data["benchmarks"] = aligned or None
                else:
                    data["benchmarks"] = None
                data["data_until"] = _jsonable(row["result_data_until"])
                return jsonify(_jsonable(data))
        from quant_research_engine.gui.lab_result import build_lab_symbol_detail

        data = build_lab_symbol_detail(_result_record(row), code)
        if data is None:
            # 产物未回传（批量截断）不等于无交易：提示可按需生成，由前端出按钮
            return jsonify({"ok": False, "error": "该股详情产物未随任务回传",
                            "can_generate": True,
                            "readonly": _is_public_readonly(),
                            "readonly_kind": _public_readonly_kind()}), 404
        data["data_until"] = _jsonable(row["result_data_until"])
        return jsonify(_jsonable(data))

    def _symbol_detail_ready(job_id: int, code: str) -> bool:
        """按需/批量产物是否已就位（与 api_result_symbol_detail 同套查找口径）。"""
        job_dir = Path(_cfg(app, "SAAS_UPLOAD_DIR", "outputs/saas_uploads") or "outputs/saas_uploads") / f"job_{job_id}"
        detail_dir = job_dir / "_symbol_details"
        if (detail_dir / f"{code}.json.gz").exists():
            return True
        if detail_dir.is_dir():
            prefix = code.split(".")[0]
            return any(detail_dir.glob(f"{prefix}.*.json.gz"))
        return False

    @app.post("/api/results/<int:job_id>/symbols/<ts_code>/generate")
    def api_symbol_detail_generate(job_id: int, ts_code: str) -> Any:
        """按需生成个股详情（QRE-SAAS-SYMBOL-ONDEMAND）：创建 kind=symbol_detail
        轻量任务，worker 本地用行情库补生成该股详情 gzip 回传，ECS 落父 job 目录。
        幂等：产物已存在直接 ready；同 (父job, 股票) 有未完结任务则复用。"""
        row, err = _require_completed_result(job_id)
        if err:
            return err
        if _is_public_readonly():
            kind = _public_readonly_kind()
            message = ("经典策略为只读展示" if kind == "showcase"
                       else "分享链接为只读，不支持按需生成")
            return jsonify({"ok": False, "error": message}), 403
        try:
            code = resolve_ts_code(ts_code, [])
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        if _symbol_detail_ready(job_id, code):
            return jsonify({"ok": True, "status": "ready"})
        run_id = ((row.get("result_summary") or {}).get("run_id")) if isinstance(row.get("result_summary"), dict) else None
        if not run_id:
            return jsonify({"ok": False, "error": "父任务缺少 run_id，无法按需生成"}), 409
        engine = _get_engine(app)
        with engine.begin() as conn:
            pending = conn.execute(
                text("SELECT id, status FROM jobs WHERE kind='symbol_detail' "
                     "AND params->>'parent_job_id' = :pid AND params->>'ts_code' = :c "
                     "AND status IN ('queued','leased','running','uploading') "
                     "ORDER BY id DESC LIMIT 1"),
                {"pid": str(job_id), "c": code},
            ).mappings().first()
            if pending:
                return jsonify({"ok": True, "status": pending["status"], "gen_job_id": pending["id"]})
            gen_id = conn.execute(
                text("INSERT INTO jobs (user_id, strategy_id, kind, params, weight_class, priority) "
                     "VALUES (:uid, :sid, 'symbol_detail', CAST(:params AS jsonb), 'light', 10) "
                     "RETURNING id"),
                {"uid": row["user_id"], "sid": row["strategy_id"],
                 "params": json.dumps({"parent_job_id": job_id, "ts_code": code, "run_id": run_id})},
            ).scalar_one()
        return jsonify({"ok": True, "status": "queued", "gen_job_id": gen_id})

    @app.get("/api/results/<int:job_id>/symbols/<ts_code>/gen-status")
    def api_symbol_detail_gen_status(job_id: int, ts_code: str) -> Any:
        """前端轮询：ready（产物就位）/ 生成中（gen 任务状态）/ failed（含 worker 报错）。"""
        row, err = _require_completed_result(job_id)
        if err:
            return err
        try:
            code = resolve_ts_code(ts_code, [])
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        if _symbol_detail_ready(job_id, code):
            return jsonify({"ok": True, "status": "ready"})
        engine = _get_engine(app)
        with engine.begin() as conn:
            gen = conn.execute(
                text("SELECT id, status, error_message FROM jobs WHERE kind='symbol_detail' "
                     "AND params->>'parent_job_id' = :pid AND params->>'ts_code' = :c "
                     "ORDER BY id DESC LIMIT 1"),
                {"pid": str(job_id), "c": code},
            ).mappings().first()
        if gen is None:
            return jsonify({"ok": True, "status": "none"})
        if gen["status"] == "completed":
            # 已完成但产物未就位（如文件校验失败）——视为可重试
            return jsonify({"ok": True, "status": "none"})
        return jsonify({"ok": True, "status": gen["status"], "gen_job_id": gen["id"],
                        "error": gen["error_message"] if gen["status"] == "failed" else None})

    # --- P1 只读分享（QRE-SAAS-READONLY-SHARE）：可撤销、可设有效期的结果分享链接 ---
    # 默认私有不变：仅登录 owner 可创建/列表/撤销；游客不开放；链接绑定单个
    # completed job；token 明文只在创建响应出现一次，库中只有完整哈希。

    SHARE_EXPIRY_DAYS = (1, 7, 30, 0)  # 0=永久；默认 7

    @app.post("/api/saas/jobs/<int:job_id>/share-links")
    def api_share_link_create(job_id: int) -> Any:
        """创建只读分享链接：登录 + 本人 + status=completed。
        游客 401；他人/不存在 404；未完成 409。有效期只接受 1/7/30/0 天
        （0=永久），服务端计算 expires_at，不接受任意时间。
        返回 {ok,id,url,expires_at}——唯一返回明文 token 的响应。"""
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        row = _load_job_for_user(job_id, uid)
        if row is None:
            return jsonify({"ok": False, "error": "任务不存在"}), 404
        if row["status"] != "completed":
            return jsonify({"ok": False, "error": f"任务未完成（{row['status']}）"}), 409
        data = request.get_json(silent=True) or {}
        raw_days = data.get("expires_days", 7)
        # 只接受整数 allowlist（拒绝字符串/浮点/布尔，避免 1.5→1 这类静默取整）
        if (isinstance(raw_days, bool) or not isinstance(raw_days, int)
                or raw_days not in SHARE_EXPIRY_DAYS):
            return jsonify({"ok": False, "error": "有效期只支持 1/7/30 天或 0（永久）"}), 400
        days = raw_days
        if not _ensure_share_links(engine):
            return jsonify({"ok": False, "error": "分享功能暂不可用，请联系管理员"}), 503
        token = secrets.token_urlsafe(32)
        expires_at = (None if days == 0
                      else datetime.now(timezone.utc) + timedelta(days=days))
        with engine.begin() as conn:
            link = conn.execute(
                text("INSERT INTO share_links (token_hash, job_id, owner_id, expires_at) "
                     "VALUES (:h, :j, :o, :e) RETURNING id, expires_at"),
                {"h": _share_token_hash(app, token), "j": job_id, "o": uid, "e": expires_at},
            ).mappings().first()
        public_base_url = (_cfg(app, "SAAS_PUBLIC_BASE_URL", "") or request.url_root).rstrip("/")
        return jsonify({"ok": True, "id": link["id"],
                        "url": f"{public_base_url}/saas/jobs/{job_id}?share={token}",
                        "expires_at": _jsonable(link["expires_at"])})

    @app.get("/api/saas/share-links")
    def api_share_links_list() -> Any:
        """我的分享（仅当前用户，最近 50 条）：id/job_id/策略名/created_at/
        expires_at/revoked_at/status（active/expired/revoked）。
        不回 token_hash 或明文——链接只在创建时可见一次。"""
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        if not _ensure_share_links(engine):
            return jsonify({"ok": False, "items": []})
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT sl.id, sl.job_id, sl.created_at, sl.expires_at, sl.revoked_at, "
                     "s.name AS strategy_name "
                     "FROM share_links sl JOIN jobs j ON j.id = sl.job_id "
                     "LEFT JOIN strategies s ON s.id = j.strategy_id "
                     "WHERE sl.owner_id = :uid "
                     "ORDER BY sl.created_at DESC, sl.id DESC LIMIT 50"),
                {"uid": uid},
            ).mappings().all()
        now = datetime.now(timezone.utc)
        items = []
        for r in rows:
            revoked = r["revoked_at"] is not None
            expired = (not revoked and r["expires_at"] is not None
                       and r["expires_at"] <= now)
            items.append({
                "id": r["id"], "job_id": r["job_id"],
                "strategy_name": r["strategy_name"],
                "created_at": _jsonable(r["created_at"]),
                "expires_at": _jsonable(r["expires_at"]),
                "revoked_at": _jsonable(r["revoked_at"]),
                "status": "revoked" if revoked else ("expired" if expired else "active"),
            })
        return jsonify({"ok": True, "items": items})

    @app.post("/api/saas/share-links/<int:link_id>/revoke")
    def api_share_link_revoke(link_id: int) -> Any:
        """撤销分享：仅创建者可撤销；重复撤销、他人或不存在统一 404；
        成功置 revoked_at=now()，立即失效。"""
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        if not _ensure_share_links(engine):
            return jsonify({"ok": False, "error": "分享不存在"}), 404
        with engine.begin() as conn:
            row = conn.execute(
                text("UPDATE share_links SET revoked_at = now() "
                     "WHERE id = :id AND owner_id = :uid AND revoked_at IS NULL "
                     "RETURNING id"),
                {"id": link_id, "uid": uid},
            ).first()
        if row is None:
            return jsonify({"ok": False, "error": "分享不存在"}), 404
        return jsonify({"ok": True, "id": link_id, "revoked": True})

    # --- 后台管理（QRE-SAAS-ADMIN-E1E3，15 号文档 E 阶段） ---
    # 路由前缀用 /saas/console（不用 /admin 字样：SaaS 页面禁链纪律含 HTML/JS 注释，
    # 见 12_UI_STYLE_GUIDE.md §7）。页面本身不鉴权（JS 门），数据端点全部
    # _require_admin 服务端强制。管理员提升方式：UPDATE users SET role='admin'。

    @app.get("/saas/console")
    def saas_console_page() -> str:
        return render_template("console.html")

    @app.get("/api/saas/console/overview")
    def api_console_overview() -> Any:
        """E1 总览：用户/任务/配额/worker 关键指标 + 队列深度 + 服务器资源。"""
        engine = _get_engine(app)
        _, denied = _require_admin(app, engine)
        if denied is not None:
            return denied
        # R3 切片1：workers.status 懒自愈须在开读连接前完成（ALTER 需排他锁，
        # 读连接的事务持有 workers 共享锁，嵌套调用会自我等待）
        _ensure_worker_status_columns(engine)
        _ensure_worker_configs(engine)  # R3 切片2：期望配置表同上
        from quant_research_engine.gui.saas import nl_compile_support as _nls
        _nls.ensure_nl_tables(engine)  # NL A2A3：两表懒自愈（须在开读连接前）
        with engine.connect() as conn:
            users = conn.execute(
                text(
                    "SELECT count(*) AS total, "
                    "count(*) FILTER (WHERE created_at::date = now()::date) AS new_today, "
                    "count(*) FILTER (WHERE status <> 'active') AS disabled, "
                    "count(*) FILTER (WHERE tier = 'member') AS member, "
                    "count(*) FILTER (WHERE tier = 'paid') AS paid "
                    "FROM users"
                )
            ).mappings().one()
            jobs = conn.execute(
                text(
                    "SELECT count(*) AS total, "
                    "count(*) FILTER (WHERE created_at::date = now()::date) AS today, "
                    "count(*) FILTER (WHERE status = 'queued') AS queued, "
                    "count(*) FILTER (WHERE status = 'queued' AND weight_class = 'light') AS queued_light, "
                    "count(*) FILTER (WHERE status = 'queued' AND weight_class = 'heavy') AS queued_heavy, "
                    "count(*) FILTER (WHERE status IN ('leased','running','uploading')) AS running, "
                    "count(*) FILTER (WHERE status = 'completed' AND finished_at::date = now()::date) AS completed_today, "
                    "count(*) FILTER (WHERE status IN ('failed','expired') AND finished_at::date = now()::date) AS failed_today, "
                    "count(*) FILTER (WHERE status IN ('failed','expired')) AS failed_total "
                    "FROM jobs"
                )
            ).mappings().one()
            quota = conn.execute(
                text(
                    "SELECT count(DISTINCT user_id) AS active_members "
                    "FROM jobs WHERE user_id IS NOT NULL AND kind = 'full' "
                    "AND created_at::date = now()::date"
                )
            ).mappings().one()
            # N1a 游客统计口径：guest_key 非空即游客任务。QRE-SAAS-ACCESS-HARDENING-001
            # 起归属键由会话 Cookie 派生（历史 IP 哈希行一次性迁移后同形），distinct
            # 即独立游客会话数（清 Cookie/换浏览器会略高于独立访客数，属预期）。
            guests = conn.execute(
                text(
                    "SELECT count(*) AS total, "
                    "count(*) FILTER (WHERE created_at::date = now()::date) AS today, "
                    "count(DISTINCT guest_key) AS unique_visitors, "
                    "count(*) FILTER (WHERE status = 'completed') AS completed, "
                    "count(*) FILTER (WHERE status IN ('failed','expired')) AS failed "
                    "FROM jobs WHERE guest_key IS NOT NULL"
                )
            ).mappings().one()
            workers = conn.execute(
                text(
                    "SELECT count(*) AS total, "
                    "count(*) FILTER (WHERE last_heartbeat_at > now() - interval '3 minutes') AS online "
                    "FROM workers"
                )
            ).mappings().one()
            # R3 切片1：worker 资源明细（槽位/内存水位快照）。online 口径 = 心跳 <60s
            # （上报默认 15s）；status 为 NULL 的旧 worker 降级为空槽位。
            worker_rows = conn.execute(
                text(
                    "SELECT name, last_heartbeat_at, status, status_at, "
                    "(last_heartbeat_at > now() - interval '60 seconds') AS online "
                    "FROM workers ORDER BY last_heartbeat_at DESC"
                )
            ).mappings().all()
            # R3 切片2：期望配置（worker_configs），供「当前生效 vs 期望」比对
            desired_rows = conn.execute(
                text("SELECT * FROM worker_configs")
            ).mappings().all()
            pending_factors = conn.execute(
                text("SELECT count(*) FROM factor_requests WHERE status = 'pending'")
            ).scalar_one()
            # QRE-SAAS-NL-A2A3 + R-ADMIN-001：管理台展示的 NL 限流/缓存口径必须与执行
            # 同一权威来源——限额直接读当前执行常量，计数读两表真实行。
            nl_rate = conn.execute(
                text("SELECT count(*) AS rows, coalesce(sum(hits), 0) AS hits "
                     "FROM nl_rate_limits")
            ).mappings().one()
            nl_cache = conn.execute(
                text("SELECT count(*) AS entries, coalesce(sum(hit_count), 0) AS hits "
                     "FROM nl_compile_cache")
            ).mappings().one()
        desired_by_worker = {r["worker_id"]: _worker_config_view(r) for r in desired_rows}
        workers_detail = []
        for row in worker_rows:
            st = row["status"] or {}
            limits = st.get("limits") or {}
            desired = desired_by_worker.get(row["name"])
            workers_detail.append(_jsonable({
                "name": row["name"],
                "last_heartbeat_at": row["last_heartbeat_at"],
                "online": bool(row["online"]),
                "mem_available_mb": st.get("mem_available_mb"),
                "mem_total_mb": st.get("mem_total_mb"),
                "slots": st.get("slots") or [],
                "limits": limits,
                "desired_config": desired,
                "config_mismatch": worker_config_mismatch(limits or None, desired),
                "status_at": row["status_at"],
            }))
        terminal_today = (jobs["completed_today"] or 0) + (jobs["failed_today"] or 0)
        # 服务器资源（真实采集，无第三方依赖）：负载 + 产物盘占用
        server: dict[str, Any] = {}
        try:
            server["loadavg"] = [round(v, 2) for v in os.getloadavg()]
        except OSError:
            server["loadavg"] = None
        try:
            import shutil

            upload_root = Path(_cfg(app, "SAAS_UPLOAD_DIR", "outputs/saas_uploads") or "outputs/saas_uploads")
            usage = shutil.disk_usage(upload_root if upload_root.exists() else ".")
            server["disk"] = {"total": usage.total, "used": usage.used, "free": usage.free}
        except OSError:
            server["disk"] = None
        return jsonify({"ok": True, "users": _jsonable(dict(users)),
                        "jobs": _jsonable(dict(jobs)),
                        "jobs_today_success_rate": (jobs["completed_today"] / terminal_today) if terminal_today else None,
                        "quota": _jsonable(dict(quota)), "workers": _jsonable(dict(workers)),
                        "workers_detail": workers_detail,
                        "guests": _jsonable(dict(guests)),
                        "pending_factor_requests": pending_factors, "server": server,
                        # R-ADMIN-001：NL 限流/缓存与执行同源（常量即当前生效值）
                        "nl": {
                            "guest_daily": GUEST_NL_DAILY_LIMIT,
                            "member_minute": MEMBER_NL_MINUTE_LIMIT,
                            "admin": "不限",
                            "cache_version": _nls.NL_COMPILER_CACHE_VERSION,
                            "rate_limit_rows": int(nl_rate["rows"]),
                            "rate_limit_hits": int(nl_rate["hits"]),
                            "cache_entries": int(nl_cache["entries"]),
                            "cache_hits": int(nl_cache["hits"]),
                        }})

    @app.get("/api/saas/console/users")
    def api_console_users() -> Any:
        """E2 用户列表（含当日已用配额与任务数）。"""
        engine = _get_engine(app)
        _, denied = _require_admin(app, engine)
        if denied is not None:
            return denied
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT u.id, u.email, u.phone, u.tier, u.role, u.status, "
                    "u.created_at, u.last_login_at, "
                    "(SELECT count(*) FROM jobs j WHERE j.user_id = u.id) AS job_count, "
                    "(SELECT count(*) FROM jobs j WHERE j.user_id = u.id AND j.kind = 'full' "
                    " AND j.created_at::date = now()::date) AS used_today "
                    "FROM users u ORDER BY u.created_at DESC LIMIT 500"
                )
            ).mappings().all()
        # 2026-10-05 内测调整：日配额读 tier_policies.member 实时值（0/不限 → 前端显示「不限」）
        member_pol = _get_policy(app, engine, "member")
        quota_limit = int(member_pol.get("daily_full_limit") or 0)
        return jsonify({"ok": True, "quota_limit": quota_limit if quota_limit > 0 else "不限",
                        "users": [_jsonable(dict(r)) for r in rows]})

    @app.post("/api/saas/console/users/<int:user_id>/tier")
    def api_console_user_tier(user_id: int) -> Any:
        """E2 手动调 tier（member/paid；guest 是匿名口径不落 users 行）。"""
        engine = _get_engine(app)
        _, denied = _require_admin(app, engine)
        if denied is not None:
            return denied
        data = request.get_json(silent=True) or {}
        tier = str(data.get("tier") or "").strip()
        if tier not in ("member", "paid"):
            return jsonify({"ok": False, "error": "tier 须为 member/paid"}), 400
        with engine.begin() as conn:
            row = conn.execute(
                text("UPDATE users SET tier = :tier WHERE id = :uid RETURNING id"),
                {"tier": tier, "uid": user_id},
            ).first()
        if row is None:
            return jsonify({"ok": False, "error": "用户不存在"}), 404
        return jsonify({"ok": True, "user_id": row.id, "tier": tier})

    @app.post("/api/saas/console/users/<int:user_id>/status")
    def api_console_user_status(user_id: int) -> Any:
        """E2 禁用/恢复账号。禁用后：登录 403、既有 session 立即失效
        （_current_user_id 的 status='active' 过滤）。管理员不能禁用自己。"""
        engine = _get_engine(app)
        admin_uid, denied = _require_admin(app, engine)
        if denied is not None:
            return denied
        data = request.get_json(silent=True) or {}
        status = str(data.get("status") or "").strip()
        if status not in ("active", "disabled"):
            return jsonify({"ok": False, "error": "status 须为 active/disabled"}), 400
        if status == "disabled" and user_id == admin_uid:
            return jsonify({"ok": False, "error": "不能禁用当前登录的管理员账号"}), 400
        with engine.begin() as conn:
            row = conn.execute(
                text("UPDATE users SET status = :st WHERE id = :uid RETURNING id"),
                {"st": status, "uid": user_id},
            ).first()
        if row is None:
            return jsonify({"ok": False, "error": "用户不存在"}), 404
        return jsonify({"ok": True, "user_id": row.id, "status": status})

    # --- N1b/N1c 权限管理：tier_policies 读改（角色→次数/标的/区间上限，阶梯留空可扩展） ---
    @app.get("/api/saas/console/showcase")
    def api_console_showcase_list() -> Any:
        """QRE-SAAS-SHOWCASE 管理：全部条目（含未激活）+ 策略名/任务状态/日更进度。

        QRE-SAAS-RESULT-CONTRACT-001：每条带回 result_contract（版本/验证状态/原因），
        让运营能看出哪些条目因未验证而被公开列表隐藏（条目本身不删）。
        """
        engine = _get_engine(app)
        _, denied = _require_admin(app, engine)
        if denied is not None:
            return denied
        _ensure_signal_tables(engine)
        contract_col = (", r.result_contract AS result_result_contract, r.data_until AS result_data_until"
                        if _ensure_result_contract_column(engine) else "")
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT sc.job_id, sc.title, sc.subtitle, sc.sort_order, sc.is_active, "
                    "sc.created_at, s.name AS strategy_name, j.status AS job_status"
                    + contract_col +
                    ", (SELECT max(d.trade_date) FROM showcase_daily d WHERE d.job_id = sc.job_id) AS last_daily "
                    "FROM showcase sc "
                    "JOIN jobs j ON j.id = sc.job_id "
                    "JOIN strategies s ON s.id = j.strategy_id "
                    "LEFT JOIN results r ON r.job_id = sc.job_id "
                    "ORDER BY sc.sort_order, sc.job_id"
                )
            ).mappings().all()
        items = []
        for r in rows:
            item = dict(r)
            item["result_contract"] = contract_view(
                r["job_id"], r.get("result_result_contract"), r.get("result_data_until"))
            items.append(item)
        return jsonify({"ok": True, "items": _jsonable(items)})

    @app.post("/api/saas/console/showcase")
    def api_console_showcase_add() -> Any:
        """新增 showcase 条目：job 须存在且 completed。"""
        engine = _get_engine(app)
        _, denied = _require_admin(app, engine)
        if denied is not None:
            return denied
        data = request.get_json(silent=True) or {}
        try:
            job_id = int(data.get("job_id"))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "job_id 须为整数"}), 400
        title = str(data.get("title") or "").strip()
        if not title or len(title) > 80:
            return jsonify({"ok": False, "error": "title 必填且 ≤80 字"}), 400
        subtitle = str(data.get("subtitle") or "").strip() or None
        if subtitle and len(subtitle) > 120:
            return jsonify({"ok": False, "error": "subtitle ≤120 字"}), 400
        try:
            sort_order = int(data.get("sort_order") or 0)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "sort_order 须为整数"}), 400
        _ensure_signal_tables(engine)
        with engine.begin() as conn:
            job = conn.execute(
                text("SELECT status FROM jobs WHERE id = :id"), {"id": job_id}
            ).mappings().first()
            if job is None:
                return jsonify({"ok": False, "error": "任务不存在"}), 404
            if job["status"] != "completed":
                return jsonify({"ok": False, "error": f"任务未完成（{job['status']}）"}), 409
            res = conn.execute(
                text("INSERT INTO showcase (job_id, title, subtitle, sort_order) "
                     "VALUES (:id, :t, :st, :so) ON CONFLICT (job_id) DO NOTHING"),
                {"id": job_id, "t": title, "st": subtitle, "so": sort_order},
            )
        if res.rowcount == 0:
            return jsonify({"ok": False, "error": "该任务已在展示列表中"}), 409
        return jsonify({"ok": True, "job_id": job_id})

    @app.post("/api/saas/console/showcase/<int:job_id>")
    def api_console_showcase_update(job_id: int) -> Any:
        """更新 title/subtitle/sort_order/is_active（至少一项）。"""
        engine = _get_engine(app)
        _, denied = _require_admin(app, engine)
        if denied is not None:
            return denied
        data = request.get_json(silent=True) or {}
        sets, params = [], {"id": job_id}
        if "title" in data:
            title = str(data.get("title") or "").strip()
            if not title or len(title) > 80:
                return jsonify({"ok": False, "error": "title 必填且 ≤80 字"}), 400
            sets.append("title = :t"); params["t"] = title
        if "subtitle" in data:
            subtitle = str(data.get("subtitle") or "").strip() or None
            if subtitle and len(subtitle) > 120:
                return jsonify({"ok": False, "error": "subtitle ≤120 字"}), 400
            sets.append("subtitle = :st"); params["st"] = subtitle
        if "sort_order" in data:
            try:
                params["so"] = int(data.get("sort_order"))
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "sort_order 须为整数"}), 400
            sets.append("sort_order = :so")
        if "is_active" in data:
            sets.append("is_active = :a"); params["a"] = bool(data.get("is_active"))
        if not sets:
            return jsonify({"ok": False, "error": "没有需要更新的字段"}), 400
        _ensure_signal_tables(engine)
        with engine.begin() as conn:
            res = conn.execute(
                text(f"UPDATE showcase SET {', '.join(sets)} WHERE job_id = :id"), params
            )
        if res.rowcount == 0:
            return jsonify({"ok": False, "error": "条目不存在"}), 404
        return jsonify({"ok": True, "job_id": job_id, "updated": sorted(data)})

    @app.delete("/api/saas/console/showcase/<int:job_id>")
    def api_console_showcase_delete(job_id: int) -> Any:
        """移出展示（只删 showcase 行与日更数据，job/结果不动）。"""
        engine = _get_engine(app)
        _, denied = _require_admin(app, engine)
        if denied is not None:
            return denied
        _ensure_signal_tables(engine)
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM showcase_daily WHERE job_id = :id"), {"id": job_id})
            res = conn.execute(text("DELETE FROM showcase WHERE job_id = :id"), {"id": job_id})
        if res.rowcount == 0:
            return jsonify({"ok": False, "error": "条目不存在"}), 404
        return jsonify({"ok": True, "deleted": job_id})

    @app.get("/api/saas/console/policies")
    def api_console_policies() -> Any:
        engine = _get_engine(app)
        _, denied = _require_admin(app, engine)
        if denied is not None:
            return denied
        _ensure_tier_policies(engine)
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT tier, daily_full_limit, max_codes, max_days, "
                     "max_factor_fields, max_factor_tables, updated_at "
                     "FROM tier_policies ORDER BY tier")
            ).mappings().all()
        return jsonify({"ok": True, "policies": _jsonable([dict(r) for r in rows])})

    @app.post("/api/saas/console/policies/<tier>")
    def api_console_policy_update(tier: str) -> Any:
        engine = _get_engine(app)
        _, denied = _require_admin(app, engine)
        if denied is not None:
            return denied
        if not re.fullmatch(r"[a-z0-9_]{1,32}", tier or ""):
            return jsonify({"ok": False, "error": "非法角色名"}), 400
        data = request.get_json(silent=True) or {}
        fields: dict[str, int] = {}
        for k in _POLICY_KEYS:
            if k in data:
                try:
                    v = int(data[k])
                except (TypeError, ValueError):
                    return jsonify({"ok": False, "error": f"{k} 必须为整数"}), 400
                if v < 0 or v > 100000:
                    return jsonify({"ok": False, "error": f"{k} 超出允许范围（0~100000）"}), 400
                fields[k] = v
        if not fields:
            return jsonify({"ok": False, "error": "没有需要更新的字段"}), 400
        default = _TIER_POLICY_DEFAULTS.get(tier, _TIER_POLICY_DEFAULTS["member"])
        _ensure_tier_policies(engine)
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO tier_policies (tier, daily_full_limit, max_codes, max_days, "
                     " max_factor_fields, max_factor_tables) "
                     "VALUES (:t, :l, :c, :d, :ff, :ft) ON CONFLICT (tier) DO NOTHING"),
                {"t": tier, "l": default["daily_full_limit"], "c": default["max_codes"], "d": default["max_days"],
                 "ff": default["max_factor_fields"], "ft": default["max_factor_tables"]},
            )
            set_clause = ", ".join(f"{k} = :{k}" for k in fields)
            params = dict(fields)
            params["t"] = tier
            conn.execute(
                text(f"UPDATE tier_policies SET {set_clause}, updated_at = now() WHERE tier = :t"),
                params,
            )
        # 清缓存让新配置即时生效（60s 缓存之外的主动失效）
        app.extensions.get("tier_policy_cache", {}).pop(tier, None)
        return jsonify({"ok": True, "tier": tier, "updated": sorted(fields)})

    @app.get("/api/saas/console/factor-requests")
    def api_console_factor_requests() -> Any:
        """E2 因子申请审核队列（默认 pending，?status=all 看全部）。"""
        engine = _get_engine(app)
        _, denied = _require_admin(app, engine)
        if denied is not None:
            return denied
        status = str(request.args.get("status") or "pending").strip()
        sql = (
            "SELECT f.id, f.user_id, u.email AS user_email, u.phone AS user_phone, "
            "f.strategy_name, f.factors, f.formula, f.purpose, f.status, f.note, f.created_at, f.reviewed_at "
            "FROM factor_requests f LEFT JOIN users u ON u.id = f.user_id "
        )
        params: dict[str, Any] = {}
        if status != "all":
            if status not in ("pending", "approved", "rejected"):
                return jsonify({"ok": False, "error": "status 须为 pending/approved/rejected/all"}), 400
            sql += "WHERE f.status = :st "
            params["st"] = status
        sql += "ORDER BY f.created_at DESC LIMIT 200"
        with engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        return jsonify({"ok": True, "requests": [_jsonable(dict(r)) for r in rows]})

    @app.post("/api/saas/console/factor-requests/<int:req_id>/review")
    def api_console_factor_review(req_id: int) -> Any:
        """E2 审核：approve → approved（运营方据此离线计算入库）/ reject → rejected；
        note 为审核备注。仅 pending 可审，重复审核 409。"""
        engine = _get_engine(app)
        _, denied = _require_admin(app, engine)
        if denied is not None:
            return denied
        data = request.get_json(silent=True) or {}
        action = str(data.get("action") or "").strip()
        if action not in ("approve", "reject"):
            return jsonify({"ok": False, "error": "action 须为 approve/reject"}), 400
        new_status = "approved" if action == "approve" else "rejected"
        note = str(data.get("note") or "").strip() or None
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    "UPDATE factor_requests SET status = :st, note = :note, reviewed_at = now() "
                    "WHERE id = :id AND status = 'pending' RETURNING id"
                ),
                {"st": new_status, "note": note, "id": req_id},
            ).first()
        if row is None:
            return jsonify({"ok": False, "error": "申请不存在或已审核"}), 409
        return jsonify({"ok": True, "id": row.id, "status": new_status})

    @app.get("/api/saas/console/feedback")
    def api_console_feedback() -> Any:
        """反馈列表（QRE-SAAS-FEEDBACK-FACTOR-REQ）：最新 200 条。
        QRE-SAAS-PUBLIC-BETA-OPS：支持 ?category=bug/experience/factor/other 与
        ?status=open/doing/done/closed 筛选（分派闭环）；列形态随 ops 表就绪降级。"""
        engine = _get_engine(app)
        _, denied = _require_admin(app, engine)
        if denied is not None:
            return denied
        category = str(request.args.get("category") or "").strip()
        status = str(request.args.get("status") or "").strip()
        if category and category not in ops_support.FEEDBACK_CATEGORIES:
            return jsonify({"ok": False, "error": "category 无效"}), 400
        if status and status not in ops_support.FEEDBACK_STATUSES:
            return jsonify({"ok": False, "error": "status 无效"}), 400
        ops_ready = ops_support.ensure_ops_tables(engine)
        cols = ("f.id, f.user_id, u.email AS user_email, u.phone AS user_phone, "
                "f.content, f.page, f.contact, f.created_at" if not ops_ready else
                "f.id, f.user_id, u.email AS user_email, u.phone AS user_phone, "
                "f.content, f.page, f.contact, f.category, f.status, f.created_at")
        sql = (f"SELECT {cols} FROM feedback f "
               "LEFT JOIN users u ON u.id = f.user_id")
        params: dict[str, Any] = {}
        where: list[str] = []
        if category:
            where.append("f.category = :cat")
            params["cat"] = category
        if status:
            where.append("f.status = :st")
            params["st"] = status
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY f.created_at DESC LIMIT 200"
        with engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        return jsonify({"ok": True, "feedback": [_jsonable(dict(r)) for r in rows]})

    @app.post("/api/saas/console/feedback/<int:feedback_id>/status")
    def api_console_feedback_status(feedback_id: int) -> Any:
        """反馈处理状态流转（QRE-SAAS-PUBLIC-BETA-OPS）：仅 admin；
        status ∈ open/doing/done/closed；不存在 404（不泄露存在性差异）。"""
        engine = _get_engine(app)
        _, denied = _require_admin(app, engine)
        if denied is not None:
            return denied
        data = request.get_json(silent=True) or {}
        status = str(data.get("status") or "").strip()
        if status not in ops_support.FEEDBACK_STATUSES:
            return jsonify({"ok": False, "error": "status 无效"}), 400
        if not ops_support.ensure_ops_tables(engine):
            return jsonify({"ok": False, "error": "反馈状态字段不可用"}), 503
        with engine.begin() as conn:
            row = conn.execute(
                text("UPDATE feedback SET status = :st WHERE id = :id RETURNING id"),
                {"st": status, "id": feedback_id},
            ).first()
        if row is None:
            return jsonify({"ok": False, "error": "反馈不存在"}), 404
        return jsonify({"ok": True, "id": feedback_id, "status": status})

    @app.get("/api/saas/console/ops")
    def api_console_ops() -> Any:
        """公测运营指标（QRE-SAAS-PUBLIC-BETA-OPS）：窗口 today/7d/30d/all。
        指标全部来自权威表（nl_compile_events / jobs / users / feedback），
        空数据比率返回 null（前端显示「—」），不编造历史。"""
        engine = _get_engine(app)
        _, denied = _require_admin(app, engine)
        if denied is not None:
            return denied
        window = str(request.args.get("window") or "today").strip()
        if window not in ops_support.OPS_WINDOWS:
            return jsonify({"ok": False, "error": "window 须为 today/7d/30d/all"}), 400
        ops_support.ensure_ops_tables(engine)
        with engine.connect() as conn:
            ops = ops_support.compute_ops(conn, window)
        return jsonify({"ok": True, "ops": _jsonable(ops),
                        "categories": ops_support.FEEDBACK_CATEGORY_LABELS,
                        "statuses": ops_support.FEEDBACK_STATUS_LABELS,
                        "window_labels": ops_support.OPS_WINDOW_LABELS})

    @app.get("/api/saas/console/workers")
    def api_console_workers() -> Any:
        """E3 worker 在线状态（近 3 分钟有心跳 = 在线）+ 当前持有的在跑任务数。"""
        engine = _get_engine(app)
        _, denied = _require_admin(app, engine)
        if denied is not None:
            return denied
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT w.name, w.capacity, w.first_seen_at, w.last_heartbeat_at, "
                    "(w.last_heartbeat_at > now() - interval '3 minutes') AS online, "
                    "(SELECT count(*) FROM jobs j WHERE j.leased_by = w.name "
                    " AND j.status IN ('leased','running','uploading')) AS active_jobs "
                    "FROM workers w ORDER BY w.last_heartbeat_at DESC"
                )
            ).mappings().all()
        return jsonify({"ok": True, "workers": [_jsonable(dict(r)) for r in rows]})

    @app.post("/api/saas/console/worker-config")
    def api_console_worker_config() -> Any:
        """R3 切片2：设置某 worker 的期望槽位/内存闸门配置（version 每次 +1）。
        生效路径：worker 下次 status 上报响应带回 → 日志提示 → 管理员在本机执行
        deploy/saas/worker-tune.sh 应用并重启 worker，上报 limits 回到一致态。"""
        engine = _get_engine(app)
        uid, denied = _require_admin(app, engine)
        if denied is not None:
            return denied
        data = request.get_json(silent=True) or {}
        worker_id = str(data.get("worker_id") or "").strip()
        if not worker_id or len(worker_id) > 128:
            return jsonify({"ok": False, "error": "worker_id 必填且 ≤128 字符"}), 400
        fields: dict[str, int] = {}
        for k in _WORKER_CONFIG_KEYS:
            if k not in data or data[k] is None:
                return jsonify({"ok": False, "error": f"缺少 {k}"}), 400
            try:
                v = int(data[k])
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": f"{k} 必须为整数"}), 400
            if v < 0 or v > 1000000:
                return jsonify({"ok": False, "error": f"{k} 超出允许范围（0~1000000）"}), 400
            fields[k] = v
        _ensure_worker_configs(engine)
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    "INSERT INTO worker_configs (worker_id, desired_light_slots, desired_heavy_slots, "
                    "desired_light_min_avail_mb, desired_heavy_min_avail_mb, version, updated_at, updated_by) "
                    "VALUES (:wid, :light_slots, :heavy_slots, :light_min_avail_mb, :heavy_min_avail_mb, "
                    "1, now(), :uby) "
                    "ON CONFLICT (worker_id) DO UPDATE SET "
                    "desired_light_slots = :light_slots, desired_heavy_slots = :heavy_slots, "
                    "desired_light_min_avail_mb = :light_min_avail_mb, "
                    "desired_heavy_min_avail_mb = :heavy_min_avail_mb, "
                    "version = worker_configs.version + 1, updated_at = now(), updated_by = :uby "
                    "RETURNING *"
                ),
                {"wid": worker_id, "uby": f"user#{uid}", **fields},
            ).mappings().one()
        return jsonify({"ok": True, "config": _worker_config_view(row)})

    @app.get("/api/saas/console/jobs")
    def api_console_jobs() -> Any:
        """E3 全量任务查看（默认 failed/expired，?status=all|queued|...）。"""
        engine = _get_engine(app)
        _, denied = _require_admin(app, engine)
        if denied is not None:
            return denied
        status = str(request.args.get("status") or "failed").strip()
        sql = (
            "SELECT j.id, j.user_id, u.email AS user_email, j.kind, j.status, "
            "j.attempts, j.max_attempts, j.leased_by, j.progress, j.error_class, "
            "j.error_message, j.created_at, j.started_at, j.finished_at, "
            "s.name AS strategy_name "
            "FROM jobs j LEFT JOIN users u ON u.id = j.user_id "
            "LEFT JOIN strategies s ON s.id = j.strategy_id "
        )
        params: dict[str, Any] = {}
        if status == "failed":
            sql += "WHERE j.status IN ('failed','expired') "
        elif status != "all":
            if status not in JOB_STATUSES:
                return jsonify({"ok": False, "error": f"status 须为 all/failed/{'/'.join(JOB_STATUSES)}"}), 400
            sql += "WHERE j.status = :st "
            params["st"] = status
        sql += "ORDER BY j.created_at DESC LIMIT 200"
        with engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        return jsonify({"ok": True, "jobs": [_jsonable(dict(r)) for r in rows]})

    @app.post("/api/saas/console/jobs/<int:job_id>/retry")
    def api_console_job_retry(job_id: int) -> Any:
        """E3 失败任务重试：终态（failed/expired/canceled）重置回 queued，
        attempts 清零、错误与租约字段清空（job 幂等：产物按 job_id 覆盖写）。"""
        engine = _get_engine(app)
        _, denied = _require_admin(app, engine)
        if denied is not None:
            return denied
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    "UPDATE jobs SET status = 'queued', attempts = 0, leased_by = NULL, "
                    "lease_expires_at = NULL, heartbeat_at = NULL, progress = 0, "
                    "progress_message = NULL, cancel_requested = false, "
                    "error_class = NULL, error_message = NULL, "
                    "started_at = NULL, finished_at = NULL, upload_token = NULL "
                    "WHERE id = :id AND status IN ('failed','expired','canceled') RETURNING id"
                ),
                {"id": job_id},
            ).first()
        if row is None:
            return jsonify({"ok": False, "error": "任务不存在或非终态（仅失败/超时/已取消可重试）"}), 409
        return jsonify({"ok": True, "job_id": row.id, "status": "queued"})

    @app.post("/api/saas/console/jobs/<int:job_id>/cancel")
    def api_console_job_cancel(job_id: int) -> Any:
        """E3 管理员取消任意任务（语义同用户取消：queued 直接终态，
        执行中置 cancel_requested 由 worker 心跳发现）。"""
        engine = _get_engine(app)
        _, denied = _require_admin(app, engine)
        if denied is not None:
            return denied
        with engine.begin() as conn:
            _reap_expired(conn)
            row = conn.execute(
                text("SELECT * FROM jobs WHERE id = :id FOR UPDATE"),
                {"id": job_id},
            ).mappings().first()
            if row is None:
                return jsonify({"ok": False, "error": "任务不存在"}), 404
            if row["status"] in TERMINAL_STATUSES:
                return jsonify({"ok": False, "error": f"任务已终态（{row['status']}），无法取消"}), 409
            if row["status"] == "queued":
                conn.execute(
                    text("UPDATE jobs SET status = 'canceled', finished_at = now() WHERE id = :id"),
                    {"id": job_id},
                )
                return jsonify({"ok": True, "job_id": job_id, "status": "canceled"})
            conn.execute(
                text("UPDATE jobs SET cancel_requested = true WHERE id = :id"),
                {"id": job_id},
            )
        return jsonify({"ok": True, "job_id": job_id, "status": row["status"], "cancel_requested": True})

    return app


def launch_saas(*, host: str = "0.0.0.0", port: int = 8081, debug: bool = False) -> None:
    """Launch the SaaS API app."""
    app = create_saas_app()
    print(f"* QRE SaaS API: http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, use_reloader=False)
