"""QRE-SAAS-NL-A2A3：NL 编译的持久限频与版本化缓存支撑层。

职责边界（批准计划 mister-terrific-echo-vision.md）：
- 不改 gui/nl_compiler.py 的编译/纠错/YAML 校验；本模块只做限频计数与缓存编排。
- 限频计数走 PostgreSQL 单条原子 upsert（INSERT ... ON CONFLICT DO UPDATE ...
  WHERE hits < limit RETURNING），跨 gunicorn worker 与重启可靠，并发不突破。
- 缓存 key = 规范化描述 + model + 规范化 base_url + 完整 build_system_prompt
  哈希 + NL_COMPILER_CACHE_VERSION；只缓存 ok=true 的完整结果，命中不调用
  LLM 也不消耗配额，失败/not_configured 不缓存。同 key 用
  pg_advisory_xact_lock(hashtext(key)) 防并发重复调用 LLM，不同 key 不串行。
- 不保存 API key；不公开缓存列表。
"""

from __future__ import annotations

import copy
import hashlib
import unicodedata
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

# 编译缓存版本：编译后处理逻辑（归一化/纠错/默认值注入）变化时必须手动 bump；
# Prompt 文案与因子目录变化由完整 build_system_prompt 哈希天然覆盖。
NL_COMPILER_CACHE_VERSION = "2026-10-26.1"

SCOPE_GUEST_DAILY = "guest_daily"
SCOPE_MEMBER_MINUTE = "member_minute"

# 已 ensure 过的 engine（同 _ensure_share_links 模式：information_schema 查询 +
# 进程 guard；ECS 上表 owner 是 postgres，懒自愈只兜底本地/测试库）。
_NL_TABLES_ENSURED: set[int] = set()
_NL_TABLES_OK: dict[int, bool] = {}


def normalize_description(description: str) -> str:
    """Unicode NFKC + trim + 连续空白折叠为单个空格（缓存键忽略无意义空白差异）。"""
    return " ".join(unicodedata.normalize("NFKC", description or "").split())


def normalize_base_url(base_url: str) -> str:
    return (base_url or "").strip().rstrip("/")


def build_cache_key(*, description: str, model: str, base_url: str,
                    prompt: str, cache_version: str) -> str:
    """缓存键：规范化输入 + model + 规范化 base_url + 完整 prompt 哈希 + 缓存版本。"""
    prompt_hash = hashlib.sha256((prompt or "").encode("utf-8")).hexdigest()
    payload = "\x1f".join([
        normalize_description(description),
        (model or "").strip(),
        normalize_base_url(base_url),
        prompt_hash,
        cache_version or "",
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def prompt_fingerprint(prompt: str) -> str:
    return hashlib.sha256((prompt or "").encode("utf-8")).hexdigest()


def guest_window_start() -> date:
    return date.today()


def member_window_start() -> datetime:
    return datetime.now(timezone.utc).replace(second=0, microsecond=0)


def member_reset_seconds() -> int:
    """距下一 UTC 分钟窗口的秒数（1..60）。"""
    return 60 - datetime.now(timezone.utc).second


def guest_subject_hash(guest_key: str) -> str:
    """游客限流主体：复用现有 _guest_key(ip)（sha256(guest:ip:salt) 截断）。"""
    return guest_key


def member_subject_hash(uid: int, salt: str) -> str:
    """会员限流主体：域分离 sha256("nl:user:"+uid+salt) 截断，不落原始 IP。"""
    return hashlib.sha256(f"nl:user:{uid}:{salt}".encode()).hexdigest()[:32]


def ensure_nl_tables(engine: Engine) -> bool:
    """幂等确保两表存在（信息架构查询 + 进程 guard；建表失败返回 False 降级）。"""
    key = id(engine)
    if key in _NL_TABLES_ENSURED:
        return _NL_TABLES_OK.get(key, False)
    ok = True
    try:
        with engine.begin() as conn:
            for table in ("nl_rate_limits", "nl_compile_cache"):
                exists = conn.execute(
                    text("SELECT 1 FROM information_schema.tables WHERE table_name = :t"),
                    {"t": table},
                ).first() is not None
                if exists:
                    continue
                if table == "nl_rate_limits":
                    conn.execute(text(
                        "CREATE TABLE IF NOT EXISTS nl_rate_limits ("
                        "scope TEXT NOT NULL, "
                        "subject_hash TEXT NOT NULL, "
                        "window_start TIMESTAMPTZ NOT NULL, "
                        "hits INT NOT NULL DEFAULT 0, "
                        "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                        "PRIMARY KEY (scope, subject_hash, window_start))"
                    ))
                else:
                    conn.execute(text(
                        "CREATE TABLE IF NOT EXISTS nl_compile_cache ("
                        "cache_key TEXT PRIMARY KEY, "
                        "description TEXT NOT NULL, "
                        "result JSONB NOT NULL, "
                        "model TEXT NOT NULL, "
                        "prompt_hash TEXT NOT NULL, "
                        "cache_version TEXT NOT NULL, "
                        "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                        "last_hit_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                        "hit_count INT NOT NULL DEFAULT 0)"
                    ))
                    conn.execute(text(
                        "CREATE INDEX IF NOT EXISTS idx_nl_compile_cache_last_hit "
                        "ON nl_compile_cache (last_hit_at)"
                    ))
    except Exception:
        ok = False
    _NL_TABLES_ENSURED.add(key)
    _NL_TABLES_OK[key] = ok
    return ok


def consume_quota(engine: Engine, scope: str, subject_hash: str,
                  window_start: Any, limit: int) -> int | None:
    """原子消耗一次配额（独立事务包装，见 consume_quota_on）。"""
    with engine.begin() as conn:
        return consume_quota_on(conn, scope, subject_hash, window_start, limit)


def consume_quota_on(conn: Any, scope: str, subject_hash: str,
                     window_start: Any, limit: int) -> int | None:
    """原子消耗一次配额：未超限返回新 hits 值，已达上限返回 None（不递增）。

    单条 INSERT ... ON CONFLICT DO UPDATE ... WHERE hits < limit RETURNING，
    多 worker/并发下总数不超过 limit。在既有连接/事务上执行，避免嵌套取连接
    （锁事务持有连接期间再取连接会耗尽连接池）。
    """
    row = conn.execute(
        text(
            "INSERT INTO nl_rate_limits (scope, subject_hash, window_start, hits) "
            "VALUES (:scope, :subject_hash, :window_start, 1) "
            "ON CONFLICT (scope, subject_hash, window_start) "
            "DO UPDATE SET hits = nl_rate_limits.hits + 1, updated_at = now() "
            "WHERE nl_rate_limits.hits < :limit "
            "RETURNING hits"
        ),
        {"scope": scope, "subject_hash": subject_hash,
         "window_start": window_start, "limit": limit},
    ).first()
    return int(row[0]) if row is not None else None


def cache_lookup(engine: Engine, cache_key: str) -> dict[str, Any] | None:
    """快路径命中返回结果深拷贝（并更新 last_hit_at/hit_count），未命中 None。"""
    with engine.begin() as conn:
        row = cache_get(conn, cache_key)
        if row is None:
            return None
        cache_touch(conn, cache_key)
        return row


def cache_get(conn: Any, cache_key: str) -> dict[str, Any] | None:
    """事务内查询：命中返回结果深拷贝，未命中 None（不更新命中统计）。"""
    row = conn.execute(
        text("SELECT result FROM nl_compile_cache WHERE cache_key = :k"),
        {"k": cache_key},
    ).first()
    return copy.deepcopy(dict(row[0])) if row is not None else None


def cache_touch(conn: Any, cache_key: str) -> None:
    conn.execute(
        text("UPDATE nl_compile_cache SET last_hit_at = now(), "
             "hit_count = hit_count + 1 WHERE cache_key = :k"),
        {"k": cache_key},
    )


def cache_store(conn: Any, cache_key: str, *, description: str,
                result: dict[str, Any], model: str, prompt_hash: str,
                cache_version: str) -> None:
    """只存 ok=true 的完整结果（调用方保证）；不含 cache_hit 字段。"""
    conn.execute(
        text(
            "INSERT INTO nl_compile_cache "
            "(cache_key, description, result, model, prompt_hash, cache_version) "
            "VALUES (:k, :d, CAST(:r AS JSONB), :m, :p, :v) "
            "ON CONFLICT (cache_key) DO NOTHING"
        ),
        {"k": cache_key, "d": normalize_description(description),
         "r": json_dumps(result), "m": model, "p": prompt_hash,
         "v": cache_version},
    )


def advisory_lock(conn: Any, cache_key: str) -> None:
    """同 key 事务级咨询锁：防止并发重复调用 LLM；不同 key（不同 hashtext）不串行。"""
    conn.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": cache_key}
    )


def json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)
