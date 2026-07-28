"""统一管理台只读层（QRE-ADMIN-CONSOLE-P3A-001）。

红线：GUI 对 DB 只读；本模块只发 SELECT / 只读 subprocess（systemctl show、du）。
写/删操作一律走各项目官方脚本（P3b/P3c 才涉及）。
"""

from __future__ import annotations

import csv
import io
import subprocess
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable

from quant_research_engine.gui.factor_wizard import parse_factor_table_name

MAX_QUERY_LIMIT = 1000
CACHE_TTL_SECONDS = 60

TIMER_UNITS = [
    {"unit": "quant-ts-daily.timer", "label": "日线数据 quant_ts", "service": "quant-ts-daily.service"},
    {"unit": "indicators-tushare-daily.timer", "label": "因子库 indicators_tushare", "service": "indicators-tushare-daily.service"},
    {"unit": "qre-refresh.timer", "label": "QRE 回测增量刷新", "service": "qre-refresh.service"},
]

QRE_REFRESH_INSTALL_HINT = (
    "sudo cp deploy/qre-refresh.* /etc/systemd/system/ && "
    "sudo systemctl daemon-reload && sudo systemctl enable --now qre-refresh.timer"
)

# 简单 TTL 缓存：{key: (timestamp, value)}
_cache: dict[str, tuple[float, Any]] = {}


def _cached(key: str, producer: Callable[[], Any], ttl: int = CACHE_TTL_SECONDS) -> Any:
    now = time.time()
    if key in _cache:
        ts, value = _cache[key]
        if now - ts < ttl:
            return value
    value = producer()
    _cache[key] = (now, value)
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


def managed_factor_tables(repo: Path | None = None) -> set[str]:
    """纳管表清单：由 indicators_tushare config/factors.yaml 的 category+column
    组合推导（stock_daily_<category>_<column>）；repo 不可用时回退硬编码清单。"""
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
            return combos
    except Exception:
        pass
    return set(MANAGED_FACTOR_TABLES_FALLBACK)


def _store(db_url: str | None = None):
    from quant_research_engine.data.settings import DatabaseSettings
    from quant_research_engine.data.postgres import PostgresDataStore

    settings = DatabaseSettings(market_db_url=db_url) if db_url else DatabaseSettings.from_env()
    store = PostgresDataStore(settings)
    store.ping()
    return store


def _estimate_rows(conn, schema: str, table: str) -> int | None:
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
    return int(row[0])


# ---------------------------------------------------------------------------
# Tab 1 总览
# ---------------------------------------------------------------------------


def overview_daily(db_url: str | None = None) -> dict[str, Any]:
    """日线域：估算行数、watermark、股票数、最近 15 个交易日。"""
    from sqlalchemy import text

    def _produce() -> dict[str, Any]:
        store = _store(db_url)
        try:
            with store.market_engine.begin() as conn:
                estimated_rows = _estimate_rows(conn, "public", "stock_daily")
                watermark = conn.execute(text("SELECT MAX(trade_date) FROM public.stock_daily")).scalar()
                symbol_count = conn.execute(text("SELECT COUNT(DISTINCT ts_code) FROM public.stock_daily")).scalar()
                recent = [
                    str(row[0])
                    for row in conn.execute(
                        text("SELECT DISTINCT trade_date FROM public.stock_daily ORDER BY trade_date DESC LIMIT 15")
                    ).fetchall()
                ]
            return {
                "estimated_rows": estimated_rows,
                "watermark": str(watermark) if watermark else None,
                "symbol_count": int(symbol_count) if symbol_count is not None else None,
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
                    if parse_factor_table_name(table) is None:
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


# ---------------------------------------------------------------------------
# 健康灯
# ---------------------------------------------------------------------------


def health_status(daily_max: str | None, factor_watermarks: list[str | None]) -> dict[str, Any]:
    """三域 watermark 对齐灯：全部同日=green；最小滞后 ≤3 天=yellow；否则 red。"""
    if not daily_max:
        return {"level": "red", "detail": "日线 watermark 不可用"}
    known = [w for w in factor_watermarks if w]
    if not known:
        return {"level": "red", "detail": "因子库 watermark 不可用"}
    daily_date = date.fromisoformat(str(daily_max)[:10])
    lagging = [w for w in known if w < str(daily_max)]
    if not lagging and len(known) == len(factor_watermarks):
        return {"level": "green", "detail": f"全部对齐 {daily_max}"}
    min_lag = min((daily_date - date.fromisoformat(str(w)[:10])).days for w in lagging) if lagging else None
    missing = len(factor_watermarks) - len(known)
    detail_parts = []
    if lagging:
        detail_parts.append(f"{len(lagging)} 张因子表滞后（最小滞后 {min_lag} 天）")
    if missing:
        detail_parts.append(f"{missing} 张因子表无数据")
    level = "yellow" if (min_lag is not None and min_lag <= 3 and not missing) else "red"
    return {"level": level, "detail": "；".join(detail_parts) or "对齐"}


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
# Tab 3 数据查询（只读，参数化 + 白名单）
# ---------------------------------------------------------------------------


def _clamp_limit(limit: Any) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = 200
    return max(1, min(value, MAX_QUERY_LIMIT))


def query_daily(
    *,
    ts_code: str,
    start: str,
    end: str,
    limit: Any = 200,
    offset: Any = 0,
    db_url: str | None = None,
    store: Any = None,
) -> dict[str, Any]:
    """public.stock_daily 分页查询（参数化 SQL，limit ≤ 1000）。"""
    from sqlalchemy import text

    if not ts_code or not ts_code.strip():
        raise ValueError("股票代码不能为空")
    limit = _clamp_limit(limit)
    offset = max(0, int(offset or 0))
    own_store = store is None
    store = store or _store(db_url)
    try:
        with store.market_engine.begin() as conn:
            total = conn.execute(
                text(
                    "SELECT COUNT(*) FROM public.stock_daily "
                    "WHERE ts_code = :ts_code AND trade_date BETWEEN :start AND :end"
                ),
                {"ts_code": ts_code.strip(), "start": start, "end": end},
            ).scalar()
            rows = conn.execute(
                text(
                    "SELECT trade_date, ts_code, open, high, low, close, pre_close, vol, amount "
                    "FROM public.stock_daily "
                    "WHERE ts_code = :ts_code AND trade_date BETWEEN :start AND :end "
                    "ORDER BY trade_date LIMIT :limit OFFSET :offset"
                ),
                {"ts_code": ts_code.strip(), "start": start, "end": end, "limit": limit, "offset": offset},
            ).mappings().fetchall()
        records = [{k: (str(v) if v is not None else None) for k, v in row.items()} for row in rows]
        return {"total": int(total or 0), "limit": limit, "offset": offset, "rows": records}
    finally:
        if own_store:
            store.close()


def query_factor(
    *,
    table: str,
    column: str,
    ts_code: str,
    start: str,
    end: str,
    limit: Any = 200,
    offset: Any = 0,
    db_url: str | None = None,
    store: Any = None,
) -> dict[str, Any]:
    """factors.* 单因子分页查询。table/column 走白名单（实时 information_schema）防注入。"""
    from sqlalchemy import text

    if not ts_code or not ts_code.strip():
        raise ValueError("股票代码不能为空")
    bare_table = table.split(".")[-1]
    if parse_factor_table_name(bare_table) is None:
        raise ValueError(f"非法因子表名: {table}")
    limit = _clamp_limit(limit)
    offset = max(0, int(offset or 0))
    own_store = store is None
    store = store or _store(db_url)
    try:
        # 白名单校验：表必须存在、列必须是真实列
        if not store.table_exists(f"factors.{bare_table}"):
            raise ValueError(f"因子表不存在: factors.{bare_table}")
        valid_columns = set(store.get_table_columns(f"factors.{bare_table}"))
        if column not in valid_columns - {"ts_code", "trade_date"}:
            raise ValueError(f"非法因子列名: {column}")
        with store.market_engine.begin() as conn:
            total = conn.execute(
                text(
                    f'SELECT COUNT(*) FROM factors."{bare_table}" '
                    "WHERE ts_code = :ts_code AND trade_date BETWEEN :start AND :end"
                ),
                {"ts_code": ts_code.strip(), "start": start, "end": end},
            ).scalar()
            rows = conn.execute(
                text(
                    f'SELECT trade_date, ts_code, "{column}" FROM factors."{bare_table}" '
                    "WHERE ts_code = :ts_code AND trade_date BETWEEN :start AND :end "
                    "ORDER BY trade_date LIMIT :limit OFFSET :offset"
                ),
                {"ts_code": ts_code.strip(), "start": start, "end": end, "limit": limit, "offset": offset},
            ).mappings().fetchall()
        records = [{k: (str(v) if v is not None else None) for k, v in row.items()} for row in rows]
        return {"total": int(total or 0), "limit": limit, "offset": offset, "rows": records}
    finally:
        if own_store:
            store.close()


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    """查询结果行 → CSV 文本（含表头）。"""
    if not rows:
        return ""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
