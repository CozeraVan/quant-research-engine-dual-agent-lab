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

from quant_research_engine.gui.saas.symbol_norm import (
    normalize_ts_codes,
    resolve_ts_code,
)

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

# --- 内测三级权限（15 号文档 D 阶段定稿，2026-09-20） ---
MEMBER_DAILY_FULL_LIMIT = 3      # 登录会员/付费占位：每日全量回测 3 次（smoke 不占）
GUEST_DAILY_LIMIT = 1            # 游客：单 IP 每日 1 次
GUEST_MAX_CODES = 1              # 游客：单支股票
GUEST_MAX_DAYS = 731 + 7         # 游客：区间 ≤ 近 2 年（留一周宽限）
GUEST_RESULT_NOTE = "游客结果次日清空，注册后可永久保存记录"
_PBKDF2_ITERATIONS = 120_000


def _client_ip() -> str:
    # Nginx 反代已传 X-Forwarded-For（16 号文档 C1 配置）
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _guest_key(app: Flask, ip: str) -> str:
    return hashlib.sha256(f"guest:{ip}:{_auth_salt(app)}".encode()).hexdigest()[:32]


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

    # C5：个股明细列表 / 个股详情页（数据走 /api/results/<id>/symbols*）
    @app.get("/saas/jobs/<int:job_id>/symbols")
    def saas_symbols_page(job_id: int) -> str:
        return render_template("symbols.html", job_id=job_id)

    @app.get("/saas/jobs/<int:job_id>/symbols/<ts_code>")
    def saas_symbol_page(job_id: int, ts_code: str) -> str:
        return render_template("symbol.html", job_id=job_id, ts_code=ts_code)

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

    # --- 我的策略库（QRE-SAAS-D3）：登录会员保存/复用/管理策略 YAML ---
    # 提交回测时按 (user_id, name) upsert 复用；删除仅允许无回测引用的策略。

    @app.get("/api/saas/strategies")
    def api_strategies_list() -> Any:
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT s.id, s.name, s.created_at, s.updated_at, "
                    "count(j.id) AS job_count, max(j.created_at) AS last_used_at "
                    "FROM strategies s LEFT JOIN jobs j ON j.strategy_id = s.id "
                    "WHERE s.user_id = :uid "
                    "GROUP BY s.id ORDER BY s.updated_at DESC LIMIT 200"
                ),
                {"uid": uid},
            ).mappings().all()
        return jsonify({"ok": True, "strategies": [_jsonable(dict(r)) for r in rows]})

    @app.get("/api/saas/strategies/<int:strategy_id>")
    def api_strategy_get(strategy_id: int) -> Any:
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录"}), 401
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id, name, yaml, nl_text, created_at, updated_at "
                     "FROM strategies WHERE id = :id AND user_id = :uid"),
                {"id": strategy_id, "uid": uid},
            ).mappings().first()
        if row is None:
            return jsonify({"ok": False, "error": "策略不存在"}), 404
        return jsonify({"ok": True, "strategy": _jsonable(dict(row))})

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
                    text("UPDATE strategies SET yaml = :yaml, nl_text = :nl, updated_at = now() "
                         "WHERE id = :id"),
                    {"yaml": yaml_text, "nl": data.get("nl_text"), "id": existing.id},
                )
                return jsonify({"ok": True, "strategy_id": existing.id, "updated": True})
            sid = conn.execute(
                text("INSERT INTO strategies (user_id, name, nl_text, yaml) "
                     "VALUES (:uid, :name, :nl, :yaml) RETURNING id"),
                {"uid": uid, "name": name, "nl": data.get("nl_text"), "yaml": yaml_text},
            ).scalar_one()
        return jsonify({"ok": True, "strategy_id": sid, "updated": False})

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
        item["quota_limit"] = MEMBER_DAILY_FULL_LIMIT
        item["quota_remaining"] = max(0, MEMBER_DAILY_FULL_LIMIT - (item.get("used_today") or 0))
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

        # --- 游客通道（15 号文档 D 阶段定稿）：无 token 可提交，单 IP 每日 1 次、
        #     单支股票、区间 ≤ 近 2 年；结果次日清空（每日清理任务） ---
        guest_key = None
        if uid is None:
            codes = params_raw.get("codes") or []
            if isinstance(codes, str):
                codes = [c.strip() for c in codes.split(",") if c.strip()]
            if len(codes) != GUEST_MAX_CODES:
                return jsonify({"ok": False, "error": "游客仅支持单支股票回测。注册会员后可用全市场/板块/多股票"}), 403
            try:
                from datetime import date as _date

                d0 = _date.fromisoformat(str(params_raw.get("start")))
                d1 = _date.fromisoformat(str(params_raw.get("end")))
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "请填写回测区间（开始/结束日期）"}), 400
            if (d1 - d0).days > GUEST_MAX_DAYS or d0 > d1:
                return jsonify({"ok": False, "error": "游客仅支持近 2 年内的区间。注册会员后不限"}), 403
            guest_key = _guest_key(app, _client_ip())
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
            if kind == "full" and used >= GUEST_DAILY_LIMIT:
                return jsonify({"ok": False, "error": "游客每日可回测 1 次（今日已用完）。注册会员每日 3 次且记录永久保存"}), 403

        if uid is None and guest_key is None:
            return jsonify({"ok": False, "error": "未登录（Authorization: Bearer <token>）"}), 401
        params = params_raw
        name = str(data.get("name") or "未命名策略").strip() or "未命名策略"
        nl_text = data.get("nl_text")
        idem = str(data.get("idempotency_key") or "").strip() or None

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
                        "SELECT tier, "
                        "(SELECT count(*) FROM jobs j WHERE j.user_id = u.id "
                        " AND j.kind = 'full' AND j.created_at::date = now()::date) AS used_today "
                        "FROM users u WHERE u.id = :uid"
                    ),
                    {"uid": uid},
                ).mappings().one()
                if kind == "full" and quota_row["used_today"] >= MEMBER_DAILY_FULL_LIMIT:
                    return jsonify({"ok": False, "error": "会员每日可全量回测 3 次（今日已用完），明天再来或试试小样本验证"}), 403
            # 会员：按 (user_id, name) upsert 复用策略库行（QRE-SAAS-D3）
            if uid is not None:
                existing = conn.execute(
                    text("SELECT id FROM strategies WHERE user_id = :uid AND name = :name"),
                    {"uid": uid, "name": name},
                ).first()
                if existing is not None:
                    conn.execute(
                        text("UPDATE strategies SET yaml = :yaml, nl_text = :nl, updated_at = now() "
                             "WHERE id = :id"),
                        {"yaml": yaml_text, "nl": nl_text, "id": existing.id},
                    )
                    strategy_id = existing.id
                else:
                    strategy_id = None
            else:
                strategy_id = None
            if strategy_id is None:
                strategy_id = conn.execute(
                    text(
                        "INSERT INTO strategies (user_id, name, nl_text, yaml) "
                        "VALUES (:uid, :name, :nl, :yaml) RETURNING id"
                    ),
                    {"uid": uid, "name": name, "nl": nl_text, "yaml": yaml_text},
                ).scalar_one()
            job_id = conn.execute(
                text(
                    "INSERT INTO jobs (user_id, strategy_id, kind, params, idempotency_key, guest_key) "
                    "VALUES (:uid, :sid, :kind, CAST(:params AS jsonb), :idem, :gk) RETURNING id"
                ),
                {"uid": uid, "sid": strategy_id, "kind": kind,
                 "params": json.dumps(params), "idem": idem, "gk": guest_key},
            ).scalar_one()
        resp: dict[str, Any] = {"ok": True, "job_id": job_id, "strategy_id": strategy_id, "status": "queued"}
        if guest_key is not None:
            resp["guest"] = True
            resp["note"] = GUEST_RESULT_NOTE
        return jsonify(resp)

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
        if uid is None:
            # 游客任务：同 IP（guest_key 匹配）可查看当次结果
            if row["user_id"] is not None or row["guest_key"] != _guest_key(app, _client_ip()):
                return jsonify({"ok": False, "error": "未登录"}), 401
        elif row["user_id"] != uid:
            # 他人任务与不存在一视同仁（404，不暴露任务存在性）
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
                _touch_worker(conn, worker_id)
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

    def _load_job_for_guest(job_id: int) -> Any:
        """游客 job 按同 IP guest_key 归属取行（D1D2）；不匹配返回 None。"""
        engine = _get_engine(app)
        with engine.connect() as conn:
            return conn.execute(
                text(
                    "SELECT j.*, s.name AS strategy_name, s.yaml AS strategy_yaml, "
                    "r.summary AS result_summary, r.chart_data AS result_chart_data, "
                    "r.artifacts AS result_artifacts, r.data_until AS result_data_until "
                    "FROM jobs j JOIN strategies s ON s.id = j.strategy_id "
                    "LEFT JOIN results r ON r.job_id = j.id "
                    "WHERE j.id = :id AND j.user_id IS NULL AND j.guest_key = :gk"
                ),
                {"id": job_id, "gk": _guest_key(app, _client_ip())},
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
            row = _load_job_for_guest(job_id)
            if row is None:
                return None, (jsonify({"ok": False, "error": "未登录"}), 401)
        else:
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
        游客可删除同 IP 的游客记录（D1D2）。"""
        import shutil

        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            row = _load_job_for_guest(job_id)
        else:
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
        """与 lab 版 /api/lab/runs/<id>/symbol/<ts>/detail 同形态。

        QRE-SAAS-SYMBOL-UX：
        - ts_code 允许不带后缀（如 000001），先按本任务实际交易个股精确匹配，
          匹配不到再按号段推断后缀；非法代码 400。
        - 个股详情优先读 worker 回传的 per-symbol 产物
          （<job_dir>/_symbol_details/<ts_code>.json.gz，含 K线/买卖点/因子/
          收益曲线/磨损明细——ECS 无行情库，lab 版实时查库路径在云上用不了）；
          缺失时回退 build_lab_symbol_detail（staging 等有库部署的既有行为）。
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
                return jsonify(_jsonable(data))
        from quant_research_engine.gui.lab_result import build_lab_symbol_detail

        data = build_lab_symbol_detail(_result_record(row), code)
        if data is None:
            return jsonify({"ok": False, "error": "该股票在本次回测中无交易"}), 404
        return jsonify(_jsonable(data))

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
            workers = conn.execute(
                text(
                    "SELECT count(*) AS total, "
                    "count(*) FILTER (WHERE last_heartbeat_at > now() - interval '3 minutes') AS online "
                    "FROM workers"
                )
            ).mappings().one()
            pending_factors = conn.execute(
                text("SELECT count(*) FROM factor_requests WHERE status = 'pending'")
            ).scalar_one()
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
                        "pending_factor_requests": pending_factors, "server": server})

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
        return jsonify({"ok": True, "quota_limit": MEMBER_DAILY_FULL_LIMIT,
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
            "f.strategy_name, f.factors, f.status, f.note, f.created_at, f.reviewed_at "
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
