"""统一管理台状态层（QRE-ADMIN-CONSOLE-P3A-001 / P3B-001 / STATUS-REFocus-001）。

定位：管理台只查询状态，不查询/修改/删除具体数据；增删改一律通过各项目
官方脚本传递。本模块只发 SELECT（information_schema/watermark 级）/
只读 subprocess（systemctl show、journalctl、du、indicators 列展开）。
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable

from quant_research_engine.gui.factor_wizard import parse_factor_table_name

CACHE_TTL_SECONDS = 300

TIMER_UNITS = [
    {"unit": "quant-ts-daily.timer", "label": "日线数据 quant_ts", "service": "quant-ts-daily.service"},
    {"unit": "indicators-tushare-daily.timer", "label": "因子库 indicators_tushare", "service": "indicators-tushare-daily.service"},
    {"unit": "alpha191-daily.timer", "label": "Alpha191 因子日更", "service": "alpha191-daily.service"},
    {"unit": "qre-refresh.timer", "label": "QRE 回测增量刷新", "service": "qre-refresh.service"},
    {"unit": "cluster-ashare-daily.timer", "label": "聚类反推+daily_tags", "service": "cluster-ashare-daily.service"},
    {"unit": "cluster-ashare-tags-weekly.timer", "label": "聚类标签库周更", "service": "cluster-ashare-tags-weekly.service"},
    {"unit": "qre-barometer.timer", "label": "大盘风险风向标", "service": "qre-barometer.service"},
]

QRE_REFRESH_INSTALL_HINT = (
    "sudo cp deploy/qre-refresh.* /etc/systemd/system/ && "
    "sudo systemctl daemon-reload && sudo systemctl enable --now qre-refresh.timer"
)

QRE_BAROMETER_INSTALL_HINT = (
    "sudo cp deploy/hardened/qre-barometer.* /etc/systemd/system/ && "
    "sudo systemctl daemon-reload && sudo systemctl enable --now qre-barometer.timer"
)

# 简单 TTL 缓存：{key: (timestamp, value)}；single-flight：同 key 并发共享一次计算
_cache: dict[str, tuple[float, Any]] = {}
_cache_locks: dict[str, threading.Lock] = {}
_cache_guard = threading.Lock()


def _cached(key: str, producer: Callable[[], Any], ttl: int = CACHE_TTL_SECONDS) -> Any:
    now = time.time()
    if key in _cache:
        ts, value = _cache[key]
        if now - ts < ttl:
            return value
    with _cache_guard:
        lock = _cache_locks.setdefault(key, threading.Lock())
    with lock:
        now = time.time()
        if key in _cache:
            ts, value = _cache[key]
            if now - ts < ttl:
                return value
        value = producer()
        _cache[key] = (time.time(), value)
        return value


# indicators_tushare 实际写入的规范类别表（repo 配置不可用时的回退清单）。
# 孤儿表（如历史遗留的 stock_daily_vortex_close）不在其中：vortex 数据实际
# 存放在 trend_close 表内。
MANAGED_FACTOR_TABLES_FALLBACK = [
    "stock_daily_candle_close",
    "stock_daily_momentum_average_price",
    "stock_daily_momentum_close",
    "stock_daily_overlap_close",
    "stock_daily_overlap_typical_price",
    "stock_daily_performance_close",
    "stock_daily_statistics_close",
    "stock_daily_trend_close",
    "stock_daily_volatility_close",
    "stock_daily_volume_close",
]

# alpha191 面板通道表：不符合 stock_daily_<category>_<price> 命名（无价格后缀），
# 不在 indicators config/factors.yaml 内，由 alpha191 子包独立日更，单独登记纳管。
ALPHA191_TABLE = "stock_daily_alpha191"


def managed_factor_tables(repo: Path | None = None) -> set[str]:
    """纳管表清单：由 indicators_tushare config/factors.yaml 的 category+column
    组合推导（stock_daily_<category>_<column>），另加 alpha191 面板表；
    repo 不可用时回退硬编码清单。"""
    try:
        import yaml

        from quant_research_engine.gui.factor_admin import config_path_for, indicators_repo

        config_path = config_path_for(repo or indicators_repo())
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        combos = {
            f"stock_daily_{entry['category']}_{entry['column']}"
            for entry in (data or {}).get("factors") or []
            if entry.get("category") and entry.get("column")
        }
        if combos:
            return combos | {ALPHA191_TABLE}
    except Exception:
        pass
    return set(MANAGED_FACTOR_TABLES_FALLBACK) | {ALPHA191_TABLE}


def _store(db_url: str | None = None):
    from quant_research_engine.data.settings import DatabaseSettings
    from quant_research_engine.data.postgres import PostgresDataStore

    settings = DatabaseSettings(market_db_url=db_url) if db_url else DatabaseSettings.from_env()
    store = PostgresDataStore(settings)
    store.ping()
    return store


def _estimate_rows(conn, schema: str, table: str) -> int | None:
    """pg_class.reltuples 估算行数；TimescaleDB hypertable 的 reltuples 记在
    chunk 上（父表恒 0），此时退而汇总各 chunk 的 reltuples。"""
    from sqlalchemy import text

    row = conn.execute(
        text(
            "SELECT c.reltuples::bigint "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = :schema AND c.relname = :table"
        ),
        {"schema": schema, "table": table},
    ).fetchone()
    if row is None or row[0] is None:
        return None
    estimate = int(row[0])
    if estimate > 0:
        return estimate
    # hypertable 父表 reltuples=0 → 汇总 chunk（非 hypertable 查不到行，返回 0）
    chunk_row = conn.execute(
        text(
            "SELECT COALESCE(SUM(c.reltuples), 0)::bigint "
            "FROM timescaledb_information.chunks ch "
            "JOIN pg_class c ON c.relname = ch.chunk_name "
            "JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = ch.chunk_schema "
            "WHERE ch.hypertable_name = :table AND ch.hypertable_schema = :schema"
        ),
        {"schema": schema, "table": table},
    ).fetchone()
    if chunk_row is not None and chunk_row[0] is not None and int(chunk_row[0]) > 0:
        return int(chunk_row[0])
    return estimate


# ---------------------------------------------------------------------------
# PostgreSQL 状态与控制（QRE-ADMIN-PG-STATUS；8080 管理台总览卡片）
# ---------------------------------------------------------------------------

# 安全：只允许这两个白名单动作，严格枚举校验；禁止任何拼接式命令
PG_ALLOWED_ACTIONS: frozenset[str] = frozenset({"start", "restart"})
PG_CONTROL_TIMEOUT = 30  # 秒


def pg_status(db_url: str | None = None) -> dict[str, Any]:
    """PG 实时状态：systemctl is-active + 5432 监听 + stock_daily 数据新鲜度。

    DB 不可达时 freshness 为 None + db_error 文案（不抛异常拖垮页面）。
    """
    from sqlalchemy import text

    try:
        proc = subprocess.run(
            ["systemctl", "is-active", "postgresql"],
            capture_output=True, text=True, timeout=10,
        )
        service = (proc.stdout or "").strip() or (proc.stderr or "").strip() or "unknown"
    except (OSError, subprocess.TimeoutExpired) as exc:
        service = f"unknown（{exc}）"

    try:
        ss = subprocess.run(["ss", "-tln"], capture_output=True, text=True, timeout=10)
        listen_5432 = ":5432" in (ss.stdout or "")
    except (OSError, subprocess.TimeoutExpired):
        listen_5432 = None

    freshness: str | None = None
    db_error: str | None = None
    try:
        store = _store(db_url)
        try:
            with store.market_engine.begin() as conn:
                wm = conn.execute(text("SELECT MAX(trade_date) FROM public.stock_daily")).scalar()
                freshness = str(wm) if wm else None
        finally:
            store.close()
    except Exception as exc:
        db_error = str(exc)

    return {
        "service": service,
        "listen_5432": listen_5432,
        "stock_daily_max_trade_date": freshness,
        "db_error": db_error,
    }


def pg_control(action: str) -> dict[str, Any]:
    """执行 sudo -n systemctl <action> postgresql（白名单 + 30s 超时）。

    action 不在白名单 → ValueError（路由层转 400）。返回命令结果摘要。
    """
    if action not in PG_ALLOWED_ACTIONS:
        raise ValueError(f"非法 action: {action!r}（仅允许 {sorted(PG_ALLOWED_ACTIONS)}）")
    try:
        proc = subprocess.run(
            ["sudo", "-n", "systemctl", action, "postgresql"],
            capture_output=True, text=True, timeout=PG_CONTROL_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "action": action, "error": f"命令超时（>{PG_CONTROL_TIMEOUT}s）"}
    except OSError as exc:
        return {"ok": False, "action": action, "error": str(exc)}
    ok = proc.returncode == 0
    return {
        "ok": ok,
        "action": action,
        "returncode": proc.returncode,
        "stderr": (proc.stderr or "").strip()[:500],
    }


# ---------------------------------------------------------------------------
# Tab 1 总览
# ---------------------------------------------------------------------------


def overview_daily(db_url: str | None = None) -> dict[str, Any]:
    """日线域：估算行数、watermark、估算股票数（pg_stats.n_distinct，毫秒级）、
    最近 15 个交易日。COUNT(DISTINCT) 精确值在 858 chunk 上 ~10s，已弃用。"""
    from sqlalchemy import text

    def _produce() -> dict[str, Any]:
        store = _store(db_url)
        try:
            with store.market_engine.begin() as conn:
                estimated_rows = _estimate_rows(conn, "public", "stock_daily")
                watermark = conn.execute(text("SELECT MAX(trade_date) FROM public.stock_daily")).scalar()
                # pg_stats.n_distinct：正值=估算 distinct 数；负值=占比，乘 reltuples
                n_distinct = conn.execute(
                    text(
                        "SELECT n_distinct FROM pg_stats "
                        "WHERE schemaname = 'public' AND tablename = 'stock_daily' AND attname = 'ts_code'"
                    )
                ).scalar()
                symbol_count: int | None = None
                if n_distinct is not None:
                    n_distinct = float(n_distinct)
                    if n_distinct >= 0:
                        symbol_count = int(n_distinct)
                    elif estimated_rows:
                        symbol_count = int(abs(n_distinct) * estimated_rows)
                recent = [
                    str(row[0])
                    for row in conn.execute(
                        text("SELECT DISTINCT trade_date FROM public.stock_daily ORDER BY trade_date DESC LIMIT 15")
                    ).fetchall()
                ]
            return {
                "estimated_rows": estimated_rows,
                "watermark": str(watermark) if watermark else None,
                "estimated_symbol_count": symbol_count,
                "recent_trade_dates": recent,
            }
        finally:
            store.close()

    return _cached(f"overview_daily:{db_url}", _produce)


def overview_factors(db_url: str | None = None, daily_max: str | None = None) -> dict[str, Any]:
    """因子域：纳管表逐表估算行数 + watermark + 滞后清单；未纳管表（孤儿表）
    单列信息段，不参与滞后判定与健康灯。"""
    from sqlalchemy import text

    def _produce() -> dict[str, Any]:
        managed = managed_factor_tables()
        store = _store(db_url)
        try:
            with store.market_engine.begin() as conn:
                tables = [
                    str(row[0])
                    for row in conn.execute(
                        text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'factors' ORDER BY 1")
                    ).fetchall()
                ]
                daily_watermark = daily_max
                if daily_watermark is None:
                    daily_watermark = conn.execute(text("SELECT MAX(trade_date) FROM public.stock_daily")).scalar()
                    daily_watermark = str(daily_watermark) if daily_watermark else None
                managed_infos: list[dict[str, Any]] = []
                unmanaged_infos: list[dict[str, Any]] = []
                for table in tables:
                    # 不符合 <category>_<price> 命名但在纳管清单内的表（如 alpha191）
                    # 也纳入对账，不跳过。
                    if parse_factor_table_name(table) is None and table not in managed:
                        continue
                    info = {
                        "table": f"factors.{table}",
                        "estimated_rows": _estimate_rows(conn, "factors", table),
                    }
                    if table in managed:
                        max_date = conn.execute(text(f'SELECT MAX(trade_date) FROM factors."{table}"')).scalar()
                        info["watermark"] = str(max_date) if max_date else None
                        managed_infos.append(info)
                    else:
                        unmanaged_infos.append(info)
                # 纳管但 schema 中不存在的表也如实列出
                present = {t.split(".")[-1] for t in (i["table"] for i in managed_infos)}
                for missing in sorted(managed - present):
                    managed_infos.append(
                        {"table": f"factors.{missing}", "estimated_rows": None, "watermark": None}
                    )
            lagging = [
                info["table"]
                for info in managed_infos
                if daily_watermark and (info["watermark"] is None or info["watermark"] < daily_watermark)
            ]
            return {
                "daily_watermark": daily_watermark,
                "tables": sorted(managed_infos, key=lambda i: i["table"]),
                "unmanaged_tables": sorted(unmanaged_infos, key=lambda i: i["table"]),
                "lagging_tables": sorted(lagging),
            }
        finally:
            store.close()

    return _cached(f"overview_factors:{db_url}", _produce)


def overview_backtests(outputs_dir: str | Path | None = None) -> dict[str, Any]:
    """回测域：批次数、策略产物目录数、du 磁盘占用（60s 缓存）。"""
    root = Path(outputs_dir) if outputs_dir else Path("outputs")

    def _produce() -> dict[str, Any]:
        backtests_dir = root / "backtests"
        batch_dirs = sorted([p for p in backtests_dir.iterdir() if p.is_dir()]) if backtests_dir.is_dir() else []
        strategy_dirs = 0
        for batch in batch_dirs:
            strategy_dirs += sum(1 for p in batch.iterdir() if p.is_dir())
        size_bytes: int | None = None
        try:
            # outputs 可能是符号链接（→ ~/qre-outputs），du 默认只量链接本身
            target = str(root.resolve()) if root.is_symlink() else str(root)
            proc = subprocess.run(
                ["du", "-sb", target],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if proc.returncode == 0:
                size_bytes = int(proc.stdout.split()[0])
        except Exception:
            size_bytes = None
        latest = batch_dirs[-1].name if batch_dirs else None
        return {
            "outputs_dir": str(root),
            "batch_count": len(batch_dirs),
            "strategy_dir_count": strategy_dirs,
            "size_bytes": size_bytes,
            "latest_batch": latest,
        }

    return _cached(f"overview_backtests:{root}", _produce)


#: 衍生品域六表（quant_ts derivatives schema + public.fund_daily 基金/ETF 日线；
#: 静态表无 trade_date，只报行数）。元组 = (schema, table, label, has_date)
DERIVATIVES_TABLES: list[tuple[str, str, str, bool]] = [
    ("derivatives", "cb_daily", "转债日线", True),
    ("derivatives", "cb_basic", "转债基础信息（静态）", False),
    ("derivatives", "opt_daily", "期权日线", True),
    ("derivatives", "opt_basic", "期权基础信息（静态）", False),
    ("derivatives", "yc_curve", "收益率曲线", True),
    ("public", "fund_daily", "基金/ETF 日线", True),
]


def overview_derivatives(db_url: str | None = None) -> dict[str, Any]:
    """衍生品域（QRE-GUI-DERIV-CARD-012）：derivatives schema 五表 + public.fund_daily
    各自的估算行数 + 最新 trade_date（静态表仅行数）。

    日更新鲜度（QRE-GUI-DERIV-FRESH-015）：日表 watermark 与 stock_daily 最新
    交易日对比——一致 → fresh=True（日更正常）；落后 → fresh=False（滞后，
    卡片标黄）。stock_daily 查询失败 → fresh=None 不判断。周末/节假日
    watermark 落后属正常，freshness 只相对最近交易日，不对日历日。
    表不存在/schema 未建 → present=False 优雅降级；整域查询失败 → ok=False。
    """
    from sqlalchemy import text

    def _produce() -> dict[str, Any]:
        try:
            store = _store(db_url)
        except Exception as exc:
            return {"ok": False, "error": f"数据库不可用（{exc}）", "tables": []}
        try:
            tables: list[dict[str, Any]] = []
            with store.market_engine.begin() as conn:
                latest_trade = conn.execute(
                    text("SELECT MAX(trade_date) FROM public.stock_daily")
                ).scalar()
                for schema, table, label, has_date in DERIVATIVES_TABLES:
                    exists = conn.execute(
                        text("SELECT to_regclass(:name)"),
                        {"name": f"{schema}.{table}"},
                    ).scalar()
                    info: dict[str, Any] = {
                        "table": f"{schema}.{table}",
                        "label": label,
                        "present": exists is not None,
                        "estimated_rows": None,
                        "watermark": None,
                        "fresh": None,
                    }
                    if exists is not None:
                        rows_est = _estimate_rows(conn, schema, table)
                        # reltuples=-1 = 从未 ANALYZE（新表），如实降级为 None
                        info["estimated_rows"] = rows_est if rows_est is not None and rows_est >= 0 else None
                        if has_date:
                            wm = conn.execute(
                                text(f'SELECT MAX(trade_date) FROM {schema}."{table}"')
                            ).scalar()
                            info["watermark"] = str(wm) if wm else None
                            if wm is not None and latest_trade is not None:
                                info["fresh"] = wm >= latest_trade
                    tables.append(info)
            present = sum(1 for t in tables if t["present"])
            return {
                "ok": True,
                "tables": tables,
                "present_count": present,
                "total": len(DERIVATIVES_TABLES),
                "latest_trade_date": str(latest_trade) if latest_trade else None,
            }
        except Exception as exc:
            return {"ok": False, "error": f"derivatives 查询失败（{exc}）", "tables": []}
        finally:
            store.close()

    return _cached(f"overview_derivatives:{db_url}", _produce)


#: B 层概念标签源（QRE-GUI-CONCEPT-TAG-CARD-030）：cluster.company_tags layer='B'
#: 的 source 分布卡片。2026-08-31 起 B 层 = 东财+同花顺概念板块成分
#: （em_concept / ths_concept，取代已删除的 jieba 碎片词 tushare_stock_company）。
CONCEPT_TAG_SOURCES: list[tuple[str, str]] = [
    ("em_concept", "东方财富概念板块"),
    ("ths_concept", "同花顺概念板块"),
]


def overview_concept_tags(db_url: str | None = None) -> dict[str, Any]:
    """概念标签源卡片：B 层各 source 的 tag 数 / 覆盖股票数 / 标签条数 / 最新 first_seen。

    cluster.company_tags 不存在 → present=False 优雅降级；查询失败 → ok=False，
    不拖垮总览（与 overview_derivatives 同款自降级）。
    """
    from sqlalchemy import text

    def _produce() -> dict[str, Any]:
        try:
            store = _store(db_url)
        except Exception as exc:
            return {"ok": False, "error": f"数据库不可用（{exc}）", "sources": []}
        try:
            with store.market_engine.begin() as conn:
                exists = conn.execute(
                    text("SELECT to_regclass('cluster.company_tags')")
                ).scalar()
                if exists is None:
                    return {"ok": True, "present": False, "sources": []}
                rows = conn.execute(
                    text(
                        "SELECT source, count(*) AS tag_rows, count(DISTINCT tag) AS uniq_tags, "
                        "count(DISTINCT ts_code) AS stocks, max(first_seen) AS latest_seen "
                        "FROM cluster.company_tags WHERE layer = 'B' GROUP BY source"
                    )
                ).fetchall()
            by_source = {str(r[0]): r for r in rows}
            sources: list[dict[str, Any]] = []
            for source, label in CONCEPT_TAG_SOURCES:
                r = by_source.get(source)
                sources.append({
                    "source": source,
                    "label": label,
                    "tag_rows": int(r[1]) if r else 0,
                    "uniq_tags": int(r[2]) if r else 0,
                    "stocks": int(r[3]) if r else 0,
                    "latest_seen": str(r[4]) if r and r[4] else None,
                })
            # 未登记在 CONCEPT_TAG_SOURCES 的 B 层源（如历史遗留）也如实列出
            for source, r in sorted(by_source.items()):
                if source not in dict(CONCEPT_TAG_SOURCES):
                    sources.append({
                        "source": source,
                        "label": source,
                        "tag_rows": int(r[1]),
                        "uniq_tags": int(r[2]),
                        "stocks": int(r[3]),
                        "latest_seen": str(r[4]) if r[4] else None,
                    })
            return {"ok": True, "present": True, "sources": sources}
        except Exception as exc:
            return {"ok": False, "error": f"概念标签源查询失败（{exc}）", "sources": []}
        finally:
            store.close()

    return _cached(f"overview_concept_tags:{db_url}", _produce)


# ---------------------------------------------------------------------------
# 健康灯
# ---------------------------------------------------------------------------


def health_status(
    daily_max: str | None,
    factor_watermarks: list[str | None],
    pending_trade_days: int | None = None,
) -> dict[str, Any]:
    """三域 watermark 对齐灯 + 绝对时效灯（QRE-ADMIN-HEALTH-STALENESS 修复）。

    原实现只比"日线与因子表是否互相对齐"——全链路一起断更时大家停在同一天，
    灯会误报 green（2026-09-21 断更事故即此因）。新增 pending_trade_days：
    交易日历中 (daily_max, today] 的开盘日数量；>=1 即说明数据落后于市场。
    对齐判定规则不变：全部同日=green；最小滞后 ≤3 天=yellow；否则 red。
    时效判定（优先于对齐）：pending=0 不影响；pending=1 → 至多 yellow；≥2 → red。
    """
    if not daily_max:
        return {"level": "red", "detail": "日线 watermark 不可用"}
    known = [w for w in factor_watermarks if w]
    if not known:
        return {"level": "red", "detail": "因子库 watermark 不可用"}
    daily_date = date.fromisoformat(str(daily_max)[:10])
    lagging = [w for w in known if w < str(daily_max)]
    if not lagging and len(known) == len(factor_watermarks):
        result = {"level": "green", "detail": f"全部对齐 {daily_max}"}
    else:
        min_lag = min((daily_date - date.fromisoformat(str(w)[:10])).days for w in lagging) if lagging else None
        missing = len(factor_watermarks) - len(known)
        detail_parts = []
        if lagging:
            detail_parts.append(f"{len(lagging)} 张因子表滞后（最小滞后 {min_lag} 天）")
        if missing:
            detail_parts.append(f"{missing} 张因子表无数据")
        level = "yellow" if (min_lag is not None and min_lag <= 3 and not missing) else "red"
        result = {"level": level, "detail": "；".join(detail_parts) or "对齐"}
    # 时效降级：落后于最新开盘日则降灯（green→yellow/red，yellow→red）
    if pending_trade_days is not None and pending_trade_days >= 1:
        stale_note = f"数据滞后 {pending_trade_days} 个交易日（最新 {daily_max}）"
        if pending_trade_days >= 2:
            result = {"level": "red", "detail": stale_note + "；" + result["detail"]}
        elif result["level"] == "green":
            result = {"level": "yellow", "detail": stale_note}
        else:
            result["detail"] = stale_note + "；" + result["detail"]
    return result


def pending_trade_days(daily_max: str | None, db_url: str | None = None) -> int | None:
    """交易日历口径：(daily_max, today] 内的开盘日数量。日历不可用时返回 None（不降级）。"""
    if not daily_max:
        return None
    try:
        from sqlalchemy import text

        store = _store(db_url)
        with store.market_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT count(*) FROM reference.trade_calendar "
                    "WHERE is_open = 1 AND cal_date > :since AND cal_date <= :today"
                ),
                {"since": str(daily_max)[:10], "today": date.today().isoformat()},
            ).scalar_one()
        return int(row)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Tab 2 日更状态（只读 systemctl）
# ---------------------------------------------------------------------------


def parse_systemctl_show(output: str) -> dict[str, str]:
    """解析 `systemctl show` 的 key=value 输出。"""
    result: dict[str, str] = {}
    for line in output.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            result[key.strip()] = value.strip()
    return result


def _systemctl_show(unit: str, runner: Callable[..., subprocess.CompletedProcess] | None = None) -> dict[str, str] | None:
    """systemctl show <unit>；unit 不存在返回 None。"""
    run = runner or subprocess.run
    try:
        proc = run(
            ["systemctl", "show", unit, "-p",
             "NextElapseUSecRealtime,ActiveEnterTimestamp,ExecMainStatus,Result,ActiveState,UnitFileState,LoadState"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        return None
    props = parse_systemctl_show(proc.stdout or "")
    if proc.returncode != 0 or props.get("LoadState") in ("not-found", ""):
        return None
    return props


def timer_status(
    units: list[dict[str, str]] | None = None,
    *,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> list[dict[str, Any]]:
    """逐管线读取 timer + service 状态（读不需要 root）。"""
    units = units or TIMER_UNITS
    results: list[dict[str, Any]] = []
    for spec in units:
        timer_props = _systemctl_show(spec["unit"], runner)
        entry: dict[str, Any] = {
            "unit": spec["unit"],
            "label": spec.get("label", spec["unit"]),
        }
        if timer_props is None:
            entry["status"] = "not_installed"
            if spec["unit"] == "qre-refresh.timer":
                entry["install_hint"] = QRE_REFRESH_INSTALL_HINT
            elif spec["unit"] == "qre-barometer.timer":
                entry["install_hint"] = QRE_BAROMETER_INSTALL_HINT
        else:
            entry["status"] = "installed"
            entry["active_state"] = timer_props.get("ActiveState")
            entry["unit_file_state"] = timer_props.get("UnitFileState")
            entry["next_elapse"] = timer_props.get("NextElapseUSecRealtime")
            service_props = _systemctl_show(spec.get("service", ""), runner) or {}
            entry["last_run"] = service_props.get("ActiveEnterTimestamp")
            entry["last_result"] = service_props.get("Result")
            entry["last_exit_status"] = service_props.get("ExecMainStatus")
        results.append(entry)
    return results


# ---------------------------------------------------------------------------
# 因子状态（三方对账：库中列 × 日更配置应展开列 × watermark）
# ---------------------------------------------------------------------------

# 在 indicators_tushare 的 uv 环境中做"配置 → 输出列"的纯展开：
# 用该项目自己的 factor 类 preview_columns（权威命名），全程不触 DB。
# 实测 ~1.4s 展开 10 表 206 列。
EXPECTED_COLUMNS_SCRIPT = r"""
import json
from core.factor_config import load_factor_specs
from core.factor_registry import FactorRegistry
from core.factor_base import build_factor_instance
registry = FactorRegistry()
registry.discover()
resolved = registry.resolve_specs(load_factor_specs("config/factors.yaml"))
out = {}
for spec, definition in resolved:
    table = f"stock_daily_{spec.category}_{spec.price_type}"
    entry = out.setdefault(table, {"columns": set(), "tasks": []})
    try:
        inst = build_factor_instance(definition.module, definition.class_name, spec.price_type)
        entry["columns"].update(inst.preview_columns(spec.params or [None]))
        ok = True
    except Exception:
        ok = False
    entry["tasks"].append({
        "name": spec.factor_name,
        "params": [str(p) for p in (spec.params or [None])],
        "expanded": ok,
    })
# alpha191 面板通道：不在 config/factors.yaml，列清单来自其静态 manifest
# （由 indicators 侧 scripts/gen_alpha191_manifest.py 生成）。
try:
    from pathlib import Path

    import yaml

    manifest = Path("alpha191/factors_manifest.yaml")
    if manifest.exists():
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        columns = data.get("columns") or []
        if columns:
            out["stock_daily_alpha191"] = {
                "columns": sorted(str(c) for c in columns),
                "tasks": [{"name": "alpha191_panel", "params": [], "expanded": True}],
            }
except Exception:
    pass
print(json.dumps({
    table: {"columns": sorted(v["columns"]), "tasks": v["tasks"]}
    for table, v in out.items()
}))
"""

EXPECTED_COLUMNS_TTL = 300


def expected_factor_columns(
    repo: Path | None = None,
    *,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> dict[str, Any] | None:
    """日更配置展开为"应存在的列"。失败（repo/环境/脚本异常）返回 None → 降级。"""
    from quant_research_engine.gui.daily_jobs import INDICATORS_DIR, UV_BIN

    repo = repo or INDICATORS_DIR
    run = runner or subprocess.run

    def _produce() -> dict[str, Any] | None:
        try:
            proc = run(
                [UV_BIN, "run", "python", "-c", EXPECTED_COLUMNS_SCRIPT],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=240,
            )
            if proc.returncode != 0 or not proc.stdout.strip():
                return None
            payload = json.loads(proc.stdout)
            if not isinstance(payload, dict) or not payload:
                return None
            return payload
        except Exception:
            return None

    return _cached(f"expected_factor_columns:{repo}", _produce, ttl=EXPECTED_COLUMNS_TTL)


def trade_day_lag(
    table_watermark: str | None,
    daily_watermark: str | None,
    trade_dates: list[str] | None,
) -> int | None:
    """交易日差（非自然日差）：stock_daily 日期序列中晚于表 watermark 且
    不晚于日线基准的日期个数。任一输入缺失返回 None（前端降级显示 "-"）。"""
    if not table_watermark or not daily_watermark or not trade_dates:
        return None
    tw = str(table_watermark)[:10]
    dw = str(daily_watermark)[:10]
    return sum(1 for d in trade_dates if tw < str(d)[:10] <= dw)


def _fresh_level(lag_days: int | None) -> str | None:
    """lag 0=ok（最新）；1=warn（滞后1日）；≥2=err（严重滞后）。"""
    if lag_days is None:
        return None
    if lag_days <= 0:
        return "ok"
    if lag_days == 1:
        return "warn"
    return "err"


def factor_status(
    db_url: str | None = None,
    *,
    repo: Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> dict[str, Any]:
    """三方对账（状态，不含任何数据行）：

    - green 在库且在日更配置；
    - yellow 在库但不在日更配置（停滞风险）；
    - red 在日更配置但库中缺列（缺因子）。
    另附新鲜度判定：以 stock_daily 最近交易日序列算各表交易日 lag，
    lag 0=ok / 1=warn / ≥2=err；基准查询失败时 fresh/lag_days 为 null。
    配置展开失败时降级为"配置级"展示（expected_available=False，不打列级状态）。
    """
    factors = overview_factors(db_url)
    expected = expected_factor_columns(repo, runner=runner)

    # 新鲜度判定的交易日序列（复用 overview_daily 的 DISTINCT trade_date 查询，
    # 同一 TTL 缓存）；查询失败时 trade_dates=None → fresh 字段为 null 降级。
    try:
        trade_dates: list[str] | None = overview_daily(db_url).get("recent_trade_dates")
    except Exception:
        trade_dates = None

    store = _store(db_url)
    try:
        db_columns: dict[str, set[str]] = {}
        for info in factors["tables"]:
            bare = info["table"].split(".")[-1]
            db_columns[bare] = set(store.get_table_columns(info["table"])) - {"ts_code", "trade_date"}
    finally:
        store.close()

    tables: list[dict[str, Any]] = []
    for info in factors["tables"]:
        bare = info["table"].split(".")[-1]
        actual = db_columns.get(bare, set())
        entry: dict[str, Any] = {
            "table": info["table"],
            "watermark": info["watermark"],
            "estimated_rows": info["estimated_rows"],
            "db_column_count": len(actual),
        }
        lag = trade_day_lag(info["watermark"], factors["daily_watermark"], trade_dates)
        entry["lag_days"] = lag
        entry["fresh"] = _fresh_level(lag)
        if expected is not None and bare in expected:
            want = set(expected[bare]["columns"])
            entry["expected_available"] = True
            entry["green"] = sorted(actual & want)
            entry["yellow"] = sorted(actual - want)
            entry["red"] = sorted(want - actual)
            entry["tasks"] = expected[bare]["tasks"]
        elif expected is not None:
            # 配置展开成功但该表不在配置中（不应发生在纳管表，防御）
            entry["expected_available"] = True
            entry["green"] = []
            entry["yellow"] = sorted(actual)
            entry["red"] = []
            entry["tasks"] = []
        else:
            entry["expected_available"] = False
        tables.append(entry)

    # 配置展开失败时的配置级降级视图（指标名+参数，无列级状态）
    config_level: list[dict[str, Any]] | None = None
    if expected is None:
        config_level = _config_level_tasks(repo)

    red_total = sum(len(t.get("red", [])) for t in tables)
    yellow_total = sum(len(t.get("yellow", [])) for t in tables)
    return {
        "expected_available": expected is not None,
        "daily_watermark": factors["daily_watermark"],
        "fresh_available": trade_dates is not None,
        "tables": tables,
        "unmanaged_tables": factors["unmanaged_tables"],
        "config_level": config_level,
        "summary": {
            "green": sum(len(t.get("green", [])) for t in tables),
            "yellow": yellow_total,
            "red": red_total,
            "lagging": sum(1 for t in tables if t["lag_days"] is not None and t["lag_days"] >= 1),
            "stale": sum(1 for t in tables if t["lag_days"] is not None and t["lag_days"] >= 2),
        },
    }


def _config_level_tasks(repo: Path | None = None) -> list[dict[str, Any]]:
    """降级：直接解析 factors.yaml 为 指标名+类别+价格列+参数 列表（配置级）。"""
    try:
        import yaml

        from quant_research_engine.gui.factor_admin import config_path_for, indicators_repo

        config_path = config_path_for(repo or indicators_repo())
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        tasks = []
        for entry in (data or {}).get("factors") or []:
            params = entry.get("periods") or entry.get("params") or []
            if not isinstance(params, list):
                params = [params]
            tasks.append(
                {
                    "name": str(entry.get("name")),
                    "category": str(entry.get("category")),
                    "column": str(entry.get("column")),
                    "params": [str(p) for p in params],
                }
            )
        return tasks
    except Exception:
        return []

