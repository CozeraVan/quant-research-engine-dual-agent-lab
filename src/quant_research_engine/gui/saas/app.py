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

LEASE_MINUTES = 15
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
    """测试/开发通道：不真发，记录到 app.extensions['sent_codes']。"""

    def __init__(self, app: Flask) -> None:
        self._app = app

    def send(self, target: str, code: str) -> None:
        self._app.extensions.setdefault("sent_codes", []).append(
            {"target": target, "code": code}
        )


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
    """Bearer token → session user；SAAS_DEV_AUTH=1 时 X-User-Id 后门兜底。"""
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
        "lease_expires": row.lease_expires,
        "error": row.error,
        "created_at": row.created_at,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
    })


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

    @app.errorhandler(RuntimeError)
    def _runtime_error(exc: RuntimeError) -> Any:  # SAAS_DB_URL 缺失等配置错误
        return jsonify({"ok": False, "error": str(exc)}), 503

    # --- 页面（QRE-SAAS-004 四功能前端；页面本身不鉴权，JS 检查 localStorage
    #     token，401 时跳 /saas/login；数据全走 /api/saas/* Bearer 鉴权） ---

    @app.get("/saas/login")
    def saas_login_page() -> str:
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
        return jsonify({"ok": True, "channel": channel, "expires_in": AUTH_CODE_TTL_MINUTES * 60})

    @app.post("/api/saas/auth/login")
    def api_auth_login() -> Any:
        data = request.get_json(silent=True) or {}
        target = str(data.get("target") or "").strip()
        code = str(data.get("code") or "").strip()
        if not target or not code:
            return jsonify({"ok": False, "error": "缺少 target/code"}), 400

        engine = _get_engine(app)
        with engine.begin() as conn:
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

    # --- 用户侧：提交任务 / 查询 ---

    @app.post("/api/saas/jobs")
    def api_create_job() -> Any:
        engine = _get_engine(app)
        uid = _current_user_id(app, engine)
        if uid is None:
            return jsonify({"ok": False, "error": "未登录（Authorization: Bearer <token>）"}), 401
        data = request.get_json(silent=True) or {}
        yaml_text = str(data.get("yaml") or "").strip()
        if not yaml_text:
            return jsonify({"ok": False, "error": "缺少策略 yaml"}), 400
        kind = str(data.get("kind") or "full")
        if kind not in JOB_KINDS:
            return jsonify({"ok": False, "error": f"kind 须为 {'/'.join(JOB_KINDS)}"}), 400
        params = data.get("params") or {}
        if not isinstance(params, dict):
            return jsonify({"ok": False, "error": "params 须为对象"}), 400
        name = str(data.get("name") or "未命名策略").strip() or "未命名策略"
        nl_text = data.get("nl_text")

        with engine.begin() as conn:
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
                    "INSERT INTO jobs (user_id, strategy_id, kind, params) "
                    "VALUES (:uid, :sid, :kind, CAST(:params AS jsonb)) RETURNING id"
                ),
                {"uid": uid, "sid": strategy_id, "kind": kind, "params": json.dumps(params)},
            ).scalar_one()
        return jsonify({"ok": True, "job_id": job_id, "strategy_id": strategy_id, "status": "queued"})

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
        if row["status"] == "done":
            item["result"] = {
                "summary": _jsonable(row["result_summary"]),
                "chart_data": _jsonable(row["result_chart_data"]),
                "artifacts": _jsonable(row["result_artifacts"]),
                "data_until": _jsonable(row["result_data_until"]),
            }
        return jsonify({"ok": True, "job": item})

    # --- Worker 侧：认领 / 心跳 / 回传（X-Worker-Token） ---

    @app.post("/api/saas/worker/jobs/lease")
    def api_lease_job() -> Any:
        denied = _check_worker_auth(app)
        if denied is not None:
            return denied
        data = request.get_json(silent=True) or {}
        worker_id = str(data.get("worker_id") or "").strip()
        if not worker_id:
            return jsonify({"ok": False, "error": "缺少 worker_id"}), 400

        engine = _get_engine(app)
        with engine.begin() as conn:
            picked = conn.execute(
                text(
                    "SELECT id FROM jobs "
                    "WHERE status = 'queued' "
                    "   OR (status IN ('leased', 'running') AND lease_expires < now() "
                    "       AND attempts < max_attempts) "
                    "ORDER BY priority DESC, created_at LIMIT 1 "
                    "FOR UPDATE SKIP LOCKED"
                )
            ).first()
            if picked is None:
                return jsonify({"ok": True, "job": None})
            row = conn.execute(
                text(
                    "UPDATE jobs SET status = 'leased', attempts = attempts + 1, "
                    "leased_by = :wid, lease_expires = now() + make_interval(mins => :mins), "
                    "started_at = COALESCE(started_at, now()), finished_at = NULL, error = NULL "
                    "WHERE id = :id RETURNING *"
                ),
                {"wid": worker_id, "mins": LEASE_MINUTES, "id": picked.id},
            ).mappings().one()
            strategy = conn.execute(
                text("SELECT id, name, nl_text, yaml FROM strategies WHERE id = :sid"),
                {"sid": row["strategy_id"]},
            ).mappings().one()
        job = _job_view(row)
        job["strategy"] = _jsonable(dict(strategy))
        return jsonify({"ok": True, "job": job})

    @app.post("/api/saas/worker/jobs/<int:job_id>/heartbeat")
    def api_heartbeat(job_id: int) -> Any:
        denied = _check_worker_auth(app)
        if denied is not None:
            return denied
        data = request.get_json(silent=True) or {}
        worker_id = str(data.get("worker_id") or "").strip()
        engine = _get_engine(app)
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    "UPDATE jobs SET lease_expires = now() + make_interval(mins => :mins) "
                    "WHERE id = :id AND status IN ('leased', 'running') AND leased_by = :wid "
                    "RETURNING id, lease_expires"
                ),
                {"mins": LEASE_MINUTES, "id": job_id, "wid": worker_id},
            ).mappings().first()
        if row is None:
            return jsonify({"ok": False, "error": "任务不存在、非运行中或 leased_by 不匹配"}), 409
        return jsonify({"ok": True, "job_id": row["id"], "lease_expires": _jsonable(row["lease_expires"])})

    @app.post("/api/saas/worker/jobs/<int:job_id>/result")
    def api_report_result(job_id: int) -> Any:
        denied = _check_worker_auth(app)
        if denied is not None:
            return denied
        data = request.get_json(silent=True) or {}
        worker_id = str(data.get("worker_id") or "").strip()
        status = str(data.get("status") or "")
        if status not in ("done", "failed"):
            return jsonify({"ok": False, "error": "status 须为 done/failed"}), 400

        engine = _get_engine(app)
        with engine.begin() as conn:
            job = conn.execute(
                text("SELECT * FROM jobs WHERE id = :id FOR UPDATE"),
                {"id": job_id},
            ).mappings().first()
            if job is None:
                return jsonify({"ok": False, "error": "任务不存在"}), 404
            if job["status"] not in ("leased", "running") or job["leased_by"] != worker_id:
                return jsonify({"ok": False, "error": "任务非当前 worker 持有"}), 409

            if status == "done":
                summary = data.get("summary") or {}
                chart_data = data.get("chart_data") or {}
                artifacts = data.get("artifacts") or []
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
                        "artifacts": json.dumps(artifacts),
                        "data_until": data.get("data_until"),
                    },
                )
                conn.execute(
                    text(
                        "UPDATE jobs SET status = 'done', finished_at = now(), error = NULL, "
                        "lease_expires = NULL WHERE id = :id"
                    ),
                    {"id": job_id},
                )
                return jsonify({"ok": True, "job_id": job_id, "status": "done"})

            # failed：attempts 耗尽置 failed，否则回 queued 等待重排
            error = str(data.get("error") or "worker 报告失败")
            if job["attempts"] >= job["max_attempts"]:
                conn.execute(
                    text(
                        "UPDATE jobs SET status = 'failed', error = :err, finished_at = now(), "
                        "lease_expires = NULL WHERE id = :id"
                    ),
                    {"err": error, "id": job_id},
                )
                final_status = "failed"
            else:
                conn.execute(
                    text(
                        "UPDATE jobs SET status = 'queued', error = :err, "
                        "leased_by = NULL, lease_expires = NULL WHERE id = :id"
                    ),
                    {"err": error, "id": job_id},
                )
                final_status = "queued"
        return jsonify({"ok": True, "job_id": job_id, "status": final_status})

    return app


def launch_saas(*, host: str = "0.0.0.0", port: int = 8081, debug: bool = False) -> None:
    """Launch the SaaS API app."""
    app = create_saas_app()
    print(f"* QRE SaaS API: http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, use_reloader=False)
