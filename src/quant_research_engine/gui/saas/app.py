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
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import smtplib
import time
from datetime import date, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

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
                        "SELECT user_id FROM sessions "
                        "WHERE id = :token AND expires_at > now()"
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
NON_RETRYABLE = ("strategy_compile_error", "data_missing")


def _job_view(row: Any) -> dict[str, Any]:
    return _jsonable({
        "id": row.id,
        "user_id": row.user_id,
        "strategy_id": row.strategy_id,
        "kind": row.kind,
        "status": row.status,
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


def create_saas_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(SAAS_TEMPLATE_DIR),
        static_folder=str(SHARED_STATIC_DIR),
        static_url_path="/static",
    )
    app.config["SECRET_KEY"] = os.urandom(24)
    # 验证码限流计数（内存：重启清零，内测期可接受）
    app.extensions["rate_limit"] = {"target": {}, "ip": {}}

    @app.context_processor
    def _inject_saas_flags() -> dict[str, Any]:
        # SAAS_AUTH_BYPASS 注入模板（QRE-SAAS-009 修复：bypass 下前端
        # requireLogin 无 token 跳登录页 × 登录页 302 回工作台 = 无限刷新环）
        return {"saas_auth_bypass": str(_cfg(app, "SAAS_AUTH_BYPASS", "0") or "0") == "1"}

    @app.errorhandler(RuntimeError)
    def _runtime_error(exc: RuntimeError) -> Any:  # SAAS_DB_URL 缺失等配置错误
        return jsonify({"ok": False, "error": str(exc)}), 503

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

    @app.get("/saas/login")
    def saas_login_page() -> Any:
        # staging 免登录（SAAS_AUTH_BYPASS=1，生产严禁）：登录页直接跳工作台
        if str(_cfg(app, "SAAS_AUTH_BYPASS", "0") or "0") == "1":
            from flask import redirect

            return redirect("/saas/")
        return render_template("login.html")

    @app.get("/saas/")
    def saas_dashboard_page() -> str:
        return render_template("dashboard.html")

    @app.get("/saas/new")
    def saas_new_page() -> str:
        return render_template("new.html")

    @app.get("/saas/jobs/<int:job_id>")
    def saas_job_page(job_id: int) -> str:
        return render_template("job.html", job_id=job_id)

    # --- 复用既有 NL 编译 / 因子目录（同一编译函数 + factor_correction 纠错层，
    #     LLM key 只存服务端环境变量；两个路由都要求登录） ---

    @app.post("/api/saas/nl/compile")
    def api_saas_nl_compile() -> Any:
        engine = _get_engine(app)
        if _current_user_id(app, engine) is None:
            return jsonify({"ok": False, "code": "unauthorized", "error": "未登录"}), 401
        from quant_research_engine.gui.nl_compiler import compile_nl

        data = request.get_json(silent=True) or {}
        description = (data.get("description") or "").strip()
        if not description:
            return jsonify({"ok": False, "code": "empty", "error": "请先用自然语言描述策略"}), 400
        result = compile_nl(description)
        if result.get("code") == "not_configured":
            return jsonify(result), 503
        return jsonify(result)

    @app.get("/api/saas/factors")
    def api_saas_factors() -> Any:
        engine = _get_engine(app)
        if _current_user_id(app, engine) is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        from quant_research_engine.gui.factor_wizard import (
            build_factor_groups,
            load_factor_tables_columns,
        )

        try:
            tables_columns = load_factor_tables_columns()
        except Exception as exc:
            return jsonify({"ok": False, "error": f"因子库不可用（{exc}）"}), 503
        return jsonify({"ok": True, "groups": build_factor_groups(tables_columns)})

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
                    "INSERT INTO factor_requests (user_id, strategy_name, factors) "
                    "VALUES (:uid, :name, CAST(:factors AS jsonb)) RETURNING id"
                ),
                {"uid": uid, "name": strategy_name, "factors": json.dumps(factors)},
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
                    "SELECT id, strategy_name, factors, status, note, created_at "
                    "FROM factor_requests WHERE user_id = :uid "
                    "ORDER BY created_at DESC LIMIT 50"
                ),
                {"uid": uid},
            ).mappings().all()
        return jsonify({"ok": True, "requests": [_jsonable(dict(r)) for r in rows]})

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
                text(f"SELECT id, phone, email, quota_daily FROM users WHERE {col} = :target"),
                {"target": target},
            ).mappings().first()
            if user is None:
                # 首次登录自动注册：按 target 形态填 phone/email，另一列 NULL
                user = conn.execute(
                    text(
                        f"INSERT INTO users ({col}, last_login_at) VALUES (:target, now()) "
                        "RETURNING id, phone, email, quota_daily"
                    ),
                    {"target": target},
                ).mappings().one()
            else:
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

    @app.get("/api/saas/me")
    def api_me() -> Any:
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        with engine.connect() as conn:
            user = conn.execute(
                text("SELECT id, phone, email, quota_daily FROM users WHERE id = :uid"),
                {"uid": uid},
            ).mappings().first()
        if user is None:
            return jsonify({"ok": False, "error": "用户不存在"}), 401
        return jsonify({"ok": True, "user": _jsonable(dict(user))})

    # --- 用户侧：提交 / 查询 / 取消（17 协议 §2/§5；/api/saas/* 为兼容别名） ---

    @app.post("/api/jobs")
    @app.post("/api/saas/jobs")  # 兼容别名（既有前端/测试）
    def api_create_job() -> Any:
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录（Authorization: Bearer <token>）"}), 401
        data = request.get_json(silent=True) or {}
        yaml_text = str(data.get("yaml") or data.get("strategy_yaml") or "").strip()
        if not yaml_text:
            return jsonify({"ok": False, "error": "缺少策略 yaml"}), 400
        kind = str(data.get("kind") or "full")
        if kind not in JOB_KINDS:
            return jsonify({"ok": False, "error": f"kind 须为 {'/'.join(JOB_KINDS)}"}), 400
        params = data.get("params") or data.get("params_json") or {}
        if not isinstance(params, dict):
            return jsonify({"ok": False, "error": "params 须为对象"}), 400
        name = str(data.get("name") or "未命名策略").strip() or "未命名策略"
        nl_text = data.get("nl_text")
        idem = str(data.get("idempotency_key") or "").strip() or None

        with engine.begin() as conn:
            # 幂等去重（17 协议 §4.4）：同用户同 key 返回既有 job
            if idem:
                existing = conn.execute(
                    text("SELECT id FROM jobs WHERE user_id = :uid AND idempotency_key = :k"),
                    {"uid": uid, "k": idem},
                ).first()
                if existing is not None:
                    return jsonify({"ok": True, "job_id": existing.id, "deduped": True})
            # dev 后门（SAAS_DEV_AUTH=1）用户可能不存在：自动建行（phone 占位 pending_<id>）
            conn.execute(
                text(
                    "INSERT INTO users (id, phone) VALUES (:id, :phone) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"id": uid, "phone": f"pending_{uid}"},
            )
            # 每日配额：当日已建任务数（含 smoke）>= quota_daily 则拒绝
            quota_row = conn.execute(
                text(
                    "SELECT quota_daily, "
                    "(SELECT count(*) FROM jobs j WHERE j.user_id = u.id "
                    " AND j.created_at::date = now()::date) AS used_today "
                    "FROM users u WHERE u.id = :uid"
                ),
                {"uid": uid},
            ).mappings().one()
            if quota_row["used_today"] >= quota_row["quota_daily"]:
                return jsonify({"ok": False, "error": "已达当日回测次数配额"}), 429
            strategy_id = conn.execute(
                text(
                    "INSERT INTO strategies (user_id, name, nl_text, yaml) "
                    "VALUES (:uid, :name, :nl, :yaml) RETURNING id"
                ),
                {"uid": uid, "name": name, "nl": nl_text, "yaml": yaml_text},
            ).scalar_one()
            job_id = conn.execute(
                text(
                    "INSERT INTO jobs (user_id, strategy_id, kind, params, idempotency_key) "
                    "VALUES (:uid, :sid, :kind, CAST(:params AS jsonb), :idem) RETURNING id"
                ),
                {"uid": uid, "sid": strategy_id, "kind": kind,
                 "params": json.dumps(params), "idem": idem},
            ).scalar_one()
        return jsonify({"ok": True, "job_id": job_id, "strategy_id": strategy_id, "status": "queued"})

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
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT j.*, r.summary AS result_summary, r.chart_data AS result_chart_data, "
                    "r.artifacts AS result_artifacts, r.data_until AS result_data_until "
                    "FROM jobs j LEFT JOIN results r ON r.job_id = j.id WHERE j.id = :id"
                ),
                {"id": job_id},
            ).mappings().first()
        # 他人任务与不存在一视同仁（404，不暴露任务存在性）
        if row is None or row["user_id"] != uid:
            return jsonify({"ok": False, "error": "任务不存在"}), 404
        item = _job_view(row)
        if row["status"] == "completed":
            item["result"] = {
                "summary": _jsonable(row["result_summary"]),
                "chart_data": _jsonable(row["result_chart_data"]),
                "artifacts": _jsonable(row["result_artifacts"]),
                "data_until": _jsonable(row["result_data_until"]),
            }
        return jsonify({"ok": True, "job": item})

    @app.post("/api/jobs/<int:job_id>/cancel")
    @app.post("/api/saas/jobs/<int:job_id>/cancel")
    def api_cancel_job(job_id: int) -> Any:
        """用户取消（17 协议 §5）：queued 直接 canceled；执行中置 cancel_requested，
        worker 下次心跳发现后自行终止；终态 409。"""
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        with engine.begin() as conn:
            _reap_expired(conn)
            row = conn.execute(
                text("SELECT * FROM jobs WHERE id = :id FOR UPDATE"),
                {"id": job_id},
            ).mappings().first()
            if row is None or row["user_id"] != uid:
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

        engine = _get_engine(app)
        deadline = time.monotonic() + wait_seconds
        while True:
            with engine.begin() as conn:
                _reap_expired(conn)
                picked = conn.execute(
                    text(
                        "SELECT id FROM jobs "
                        "WHERE status = 'queued' "
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
            conn.execute(
                text(
                    "INSERT INTO results (job_id, user_id, summary, chart_data, artifacts, data_until) "
                    "VALUES (:jid, :uid, CAST(:summary AS jsonb), CAST(:chart AS jsonb), "
                    "CAST(:artifacts AS jsonb), :data_until) "
                    "ON CONFLICT (job_id) DO UPDATE SET "
                    "summary = EXCLUDED.summary, chart_data = EXCLUDED.chart_data, "
                    "artifacts = EXCLUDED.artifacts, data_until = EXCLUDED.data_until"
                ),
                {
                    "jid": job_id,
                    "uid": job["user_id"],
                    "summary": json.dumps(summary),
                    "chart": json.dumps(chart_data),
                    "artifacts": json.dumps(files),
                    "data_until": data.get("data_until"),
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
                safe = Path(name).name  # 防路径穿越
                if manifest and safe not in manifest:
                    return jsonify({"ok": False, "error": f"文件不在清单内: {safe}"}), 400
                blob = file.read()
                expected = (manifest.get(safe) or {}).get("sha256")
                if expected and _hashlib.sha256(blob).hexdigest() != expected:
                    return jsonify({"ok": False, "error": f"文件校验失败: {safe}"}), 400
                (job_dir / safe).write_bytes(blob)
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
                conn.execute(
                    text(
                        "INSERT INTO results (job_id, user_id, summary, chart_data, artifacts, data_until) "
                        "VALUES (:jid, :uid, CAST(:summary AS jsonb), CAST(:chart AS jsonb), "
                        "CAST(:artifacts AS jsonb), :data_until) "
                        "ON CONFLICT (job_id) DO UPDATE SET "
                        "summary = EXCLUDED.summary, chart_data = EXCLUDED.chart_data, "
                        "artifacts = EXCLUDED.artifacts, data_until = EXCLUDED.data_until"
                    ),
                    {
                        "jid": job_id, "uid": job["user_id"],
                        "summary": json.dumps(data.get("summary") or {}),
                        "chart": json.dumps(data.get("chart_data") or {}),
                        "artifacts": json.dumps(data.get("artifacts") or []),
                        "data_until": data.get("data_until"),
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

    def _load_job_for_user(job_id: int, uid: int) -> Any:
        """取 job+strategy+result；非本人/不存在返回 None（不暴露存在性）。"""
        engine = _get_engine(app)
        with engine.connect() as conn:
            return conn.execute(
                text(
                    "SELECT j.*, s.name AS strategy_name, s.yaml AS strategy_yaml, "
                    "r.summary AS result_summary, r.chart_data AS result_chart_data, "
                    "r.artifacts AS result_artifacts, r.data_until AS result_data_until "
                    "FROM jobs j JOIN strategies s ON s.id = j.strategy_id "
                    "LEFT JOIN results r ON r.job_id = j.id "
                    "WHERE j.id = :id AND j.user_id = :uid"
                ),
                {"id": job_id, "uid": uid},
            ).mappings().first()

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
        """返回 (row, error_response)。未完成 409；不存在/非本人 404。"""
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return None, (jsonify({"ok": False, "error": "未登录"}), 401)
        row = _load_job_for_user(job_id, uid)
        if row is None:
            return None, (jsonify({"ok": False, "error": "任务不存在"}), 404)
        if row["status"] != "completed":
            return None, (jsonify({"ok": False, "error": f"任务未完成（{row['status']}）",
                                   "status": row["status"]}), 409)
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
            rows = conn.execute(
                text(
                    "SELECT j.id, j.kind, j.status, j.created_at, j.params, "
                    "s.name AS strategy_name, r.summary, r.chart_data, r.data_until "
                    "FROM jobs j JOIN strategies s ON s.id = j.strategy_id "
                    "LEFT JOIN results r ON r.job_id = j.id "
                    "WHERE j.user_id = :uid AND j.kind = 'full' "
                    "ORDER BY j.created_at DESC"
                ),
                {"uid": uid},
            ).mappings().all()
        items = []
        for row in rows:
            metrics = ((row["chart_data"] or {}).get("metrics") or {})
            summary = row["summary"] or {}
            params = row["params"] or {}
            items.append({
                "job_id": row["id"],
                "strategy_name": row["strategy_name"],
                "status": row["status"],
                "date_start": params.get("start"),
                "date_end": params.get("end"),
                "symbol_count": summary.get("symbol_count"),
                "total_return": summary.get("strategy_total_return"),
                "excess_return": metrics.get("excess_return"),
                "max_drawdown": summary.get("max_drawdown"),
                "win_rate": summary.get("win_rate"),
                "total_trade_count": summary.get("total_trade_count"),
                "data_until": _jsonable(row["data_until"]),
                "created_at": _jsonable(row["created_at"]),
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
        """B1 删除：results+jobs 行 + 产物目录（job_<id>/）。策略行保留。"""
        import shutil

        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        row = _load_job_for_user(job_id, uid)
        if row is None:
            return jsonify({"ok": False, "error": "任务不存在"}), 404
        upload_root = Path(_cfg(app, "SAAS_UPLOAD_DIR", "outputs/saas_uploads") or "outputs/saas_uploads")
        job_dir = upload_root / f"job_{job_id}"
        if job_dir.is_dir():
            shutil.rmtree(job_dir)
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM results WHERE job_id = :id"), {"id": job_id})
            conn.execute(text("DELETE FROM jobs WHERE id = :id"), {"id": job_id})
        return jsonify({"ok": True, "deleted": job_id})

    @app.get("/api/results/<int:job_id>/summary")
    def api_result_summary(job_id: int) -> Any:
        row, err = _require_completed_result(job_id)
        if err:
            return err
        return jsonify({"ok": True, "job_id": job_id,
                        "strategy_name": row["strategy_name"],
                        "summary": _jsonable(row["result_summary"]),
                        "data_until": _jsonable(row["result_data_until"])})

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
        from quant_research_engine.gui.lab_result import build_lab_risk_view

        job_dir = Path(_result_record(row)["output_dir"])
        report_path = job_dir / "risk_report.json"
        data: dict[str, Any] = {"ok": True, "job_id": job_id, "has_report": False}
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                report = None
            if isinstance(report, dict):
                data["has_report"] = True
                data.update(build_lab_risk_view(report))
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
        """与 8081 /api/lab/runs/<id>/symbol/<ts>/detail 同形态。
        注意：K 线/因子明细查本地大库，仅在能连库的部署（worker 同机/staging）可用；
        云上 ECS 无库时相应字段降级为 None（lab_result 既有降级行为）。"""
        row, err = _require_completed_result(job_id)
        if err:
            return err
        from quant_research_engine.gui.lab_result import build_lab_symbol_detail

        data = build_lab_symbol_detail(_result_record(row), ts_code)
        if data is None:
            return jsonify({"ok": False, "error": "该股票在本次回测中无交易"}), 404
        return jsonify(_jsonable(data))

    return app


def launch_saas(*, host: str = "0.0.0.0", port: int = 8081, debug: bool = False) -> None:
    """Launch the SaaS API app."""
    app = create_saas_app()
    print(f"* QRE SaaS API: http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, use_reloader=False)
