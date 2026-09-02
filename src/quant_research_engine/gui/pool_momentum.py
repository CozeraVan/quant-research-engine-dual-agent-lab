"""管理台「聚类动量因子研究」数据层（cluster-ashare M7 池动量管线只读消费）。

只读 cluster.pool_momentum_daily（cluster-ashare M7 日更产物），不触业务表、
不写任何数据。遵循管理台"只查询状态"定位：数据源不可用时返回
{"ok": False, "error": ...} 降级，不拖垮整页。结果经 admin._cached TTL 缓存。

口径与偏差声明（页面顶部同步展示）：
- **v2 主口径 = 前瞻收益 fwd_ret_w**：每日按当日成分等权再平衡的前瞻
  收益（fwd_ret = T 日成员 → T+1 等权实际收益，fwd_ret_w 为其复利累计），
  对标东财板块指数；回看 ret_w 列降级为对照列。M7 v2 前一日滞后：
  末日 fwd 全 NULL（T+1 收盘后由增量回填补齐），榜单默认展示最近
  fwd 已补齐的交易日并给出提示。
- 速度/加速度/热力/共振全部基于 fwd 口径：速度 = fwd_ret_50 截面排名，
  加速度 = fwd_ret_50 排名 − fwd_ret_3 排名（正 = 短窗跃升）；热力 =
  当前窗口 fwd_ret_w 截面分位；共振 = fwd_ret_w > 0 且 vwap_ret_w > 0
  且 vol_chg_w > 0（注意 vol_chg_50 构造上恒 0，故 w=50 永不共振）。
- 事件池统计（next_premium = fwd_ret 次日溢价、survive_3/5、win_rate_1）
  仅 8 个 meta.selection_artifact=true 的状态池有值（对标同花顺涨停复盘
  的前瞻统计）；这些池的回看 ret_w 是同义反复，无研究意义。survive_3/5
  需 T+3/T+5 标签，末日数天为 NULL 属正常。
- pool_type = concept：1066 个东财/同花顺概念标签池，成员为当前快照，
  历史回看存在前视偏差（survivorship/look-ahead），demo 阶段接受。
- pool_type = state：14 个技术状态标签池，point-in-time 成员，无该偏差。
- 排名口径：每个 pool_type 内、截面按指标降序竞争排名（rank 1 = 最高，
  并列共享名次）。「长弱短升」候选 = 速度排名位于后半区（> n/2）且
  短窗口排名进入前 10%（不足 10 个池时取第 1 名）。
"""

from __future__ import annotations

from typing import Any

from quant_research_engine.gui.admin import _cached, _store

#: 窗口（交易日）
WINDOWS = (3, 5, 20, 50)
#: 速度（长窗口）与加速度（短窗口）的口径窗口
SPEED_WINDOW = 50
ACCEL_WINDOW = 3
#: 单池详情时间序列长度（交易日）
DETAIL_DAYS = 250
#: 事件池统计列（仅 selection_artifact=true 的 8 个状态池有值）
EVENT_COLS = ("next_premium", "survive_3", "survive_5", "win_rate_1")

_RET_COLS = tuple(f"ret_{w}" for w in WINDOWS)
_FWD_COLS = tuple(f"fwd_ret_{w}" for w in WINDOWS)
_VWAP_COLS = tuple(f"vwap_ret_{w}" for w in WINDOWS)
_VOL_COLS = tuple(f"vol_chg_{w}" for w in WINDOWS)
_ALL_METRIC_COLS = _RET_COLS + _FWD_COLS + _VWAP_COLS + _VOL_COLS + EVENT_COLS

_SELECT_COLS = ", ".join(["pool_key", "n_stocks", *_ALL_METRIC_COLS])


def _num(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v == v else None  # NaN → None


# ---------------------------------------------------------------------------
# 纯逻辑（无 DB 依赖，直接可测）
# ---------------------------------------------------------------------------


def rank_desc(values: list[float | None]) -> list[int | None]:
    """降序竞争排名：rank 1 = 最大值，并列共享名次，None 不参与排名。"""

    indexed = sorted(
        ((v, i) for i, v in enumerate(values) if v is not None),
        key=lambda t: -t[0],
    )
    ranks: list[int | None] = [None] * len(values)
    prev_value: float | None = None
    prev_rank = 0
    for pos, (value, idx) in enumerate(indexed, start=1):
        if prev_value is not None and value == prev_value:
            ranks[idx] = prev_rank
        else:
            ranks[idx] = pos
            prev_rank = pos
            prev_value = value
    return ranks


def compute_acceleration(
    rows: list[dict[str, Any]],
    metric: str = "fwd_ret",
) -> list[dict[str, Any]]:
    """原地补充速度/加速度/长弱短升标记（单个 pool_type 截面内排名）。

    速度 = {metric}_{SPEED_WINDOW} 降序排名；短窗排名 = {metric}_{ACCEL_WINDOW}
    降序排名；加速度 = 速度排名 − 短窗排名（正 = 短窗口更靠前）。
    任一排名缺失 → 加速度 None。metric 默认 fwd_ret（v2 前瞻口径）。
    长弱短升候选：速度排名 > n/2（长窗口弱）且短窗排名 <= max(1, n//10)（短窗口急升）。
    """

    n = len(rows)
    speed_ranks = rank_desc([r.get(f"{metric}_{SPEED_WINDOW}") for r in rows])
    short_ranks = rank_desc([r.get(f"{metric}_{ACCEL_WINDOW}") for r in rows])
    short_top = max(1, n // 10)
    for row, speed, short in zip(rows, speed_ranks, short_ranks):
        row["speed_rank"] = speed
        row["short_rank"] = short
        if speed is None or short is None:
            row["acceleration"] = None
            row["weak_long_strong_short"] = False
        else:
            row["acceleration"] = speed - short
            row["weak_long_strong_short"] = speed > n / 2 and short <= short_top
    return rows


def resonance_flag(row: dict[str, Any], window: int) -> bool:
    """价量共振（v2 前瞻口径）：fwd_ret_w > 0 且 vwap_ret_w > 0 且 vol_chg_w > 0。"""

    ret = row.get(f"fwd_ret_{window}")
    vwap = row.get(f"vwap_ret_{window}")
    vol = row.get(f"vol_chg_{window}")
    if ret is None or vwap is None or vol is None:
        return False
    return ret > 0 and vwap > 0 and vol > 0


def sort_by_acceleration(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按加速度降序（None 恒排末位）。"""

    return sorted(
        rows,
        key=lambda r: (r.get("acceleration") is None, -(r.get("acceleration") or 0)),
    )


#: 事后验证窗口（T 日之后 w 个交易日的 fwd 复利收益）
POST_WINDOWS = (3, 5, 20)


def compute_post_returns(
    rows: list[dict[str, Any]],
    fwd_series: dict[tuple[str, str], list[float | None]],
    windows: tuple[int, ...] = POST_WINDOWS,
) -> list[dict[str, Any]]:
    """事后收益（原地补充 row["post_3/5/20"]，纯函数）。

    fwd_series: {(pool_type, pool_key): T 日之后逐交易日 fwd_ret（升序，
    长度 = T 之后已有交易日数）}。post_w = ∏(1+fwd_ret)−1 over (T, T+w]；
    T 之后不足 w 个交易日、或前 w 个值含 None → None（未满窗口）。
    """

    for row in rows:
        series = fwd_series.get((row["_pool_type"], row["pool_key"]), [])
        for w in windows:
            window_vals = series[:w]
            if len(window_vals) < w or any(v is None for v in window_vals):
                row[f"post_{w}"] = None
            else:
                acc = 1.0
                for v in window_vals:
                    acc *= 1.0 + float(v)
                row[f"post_{w}"] = acc - 1.0
    return rows


def accel_top_summary(
    rows: list[dict[str, Any]],
    post_key: str = "post_5",
    top_n: int = 10,
) -> dict[str, Any]:
    """验证摘要（纯函数）：加速度 Top N 池的 post 收益 vs 全体对照。

    返回 {"top_n", "n_top", "top_mean", "top_median", "top_win_rate",
    "all_mean", "n_all"}；post 值缺失的池不计入各自均值/胜率；
    无可用 post 值时对应字段为 None。
    """

    def _stats(vals: list[float]) -> tuple[float | None, float | None, float | None]:
        if not vals:
            return None, None, None
        s = sorted(vals)
        n = len(s)
        median = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0
        win = sum(1 for v in vals if v > 0) / n
        return sum(vals) / n, median, win

    ranked = [r for r in sort_by_acceleration(rows) if r.get("acceleration") is not None]
    top = ranked[:top_n]
    top_vals = [r[post_key] for r in top if r.get(post_key) is not None]
    all_vals = [r[post_key] for r in rows if r.get(post_key) is not None]
    top_mean, top_median, top_win = _stats(top_vals)
    all_mean, _, _ = _stats(all_vals)
    return {
        "post_key": post_key,
        "top_n": top_n,
        "n_top": len(top),
        "top_mean": top_mean,
        "top_median": top_median,
        "top_win_rate": top_win,
        "all_mean": all_mean,
        "n_all": len(all_vals),
    }


def sort_rows(
    rows: list[dict[str, Any]],
    key: str,
    desc: bool = True,
) -> list[dict[str, Any]]:
    """通用排序：None 恒排末位（与前端表头排序口径一致，供默认序与测试）。"""

    def _key(r: dict[str, Any]) -> Any:
        v = r.get(key)
        return (v is None, (-v if desc and isinstance(v, (int, float)) else v))

    return sorted(rows, key=_key)


def compute_heat(
    rows: list[dict[str, Any]],
    windows: tuple[int, ...] = WINDOWS,
    metric: str = "fwd_ret",
) -> list[dict[str, Any]]:
    """行热力值（原地补充 row["heat"][str(w)] ∈ [-1, 1]，截面分位口径抗极值）。

    heat = 2 × 分位 − 1：{metric}_w 截面最高 → +1（最红），最低 → −1（最绿），
    中位 ≈ 0（近无色）；并列共享分位（与 rank_desc 同规则）；None → None。
    A 股惯例红涨绿跌，前端按 |heat| 定透明度。metric 默认 fwd_ret（v2 前瞻口径）。
    """

    for w in windows:
        ranks = rank_desc([r.get(f"{metric}_{w}") for r in rows])
        valid = [v for v in (r.get(f"{metric}_{w}") for r in rows) if v is not None]
        n = len(valid)
        for row, rank in zip(rows, ranks):
            heat = row.setdefault("heat", {})
            if rank is None or n <= 1:
                heat[str(w)] = None
            else:
                heat[str(w)] = round(2.0 * (n - rank) / (n - 1) - 1.0, 4)
    return rows


def compute_member_metrics(
    price_rows: list[tuple[Any, ...]],
    calendar: list[str],
    windows: tuple[int, ...] = WINDOWS,
    vol_base: int = 50,
) -> dict[str, dict[str, Any]]:
    """单池成员个股在 calendar[-1] 当日的窗口指标（纯函数，与 M7 管线同口径）。

    price_rows: (ts_code, trade_date, close, adj_factor, vwap, vol) 可迭代，
    trade_date 为 date 或 'YYYY-MM-DD' 字符串。calendar 为升序交易日
    （字符串），末元素为基准日 t。
    - ret_w      = (close×adj_factor)(t) / (close×adj_factor)(t−w) − 1，
      t−w 按统一交易日历取位置，个股该日缺行 → None（同管线宽表 shift）；
    - vwap_ret_w = vwap(t)/vwap(t−w) − 1（未复权）；
    - vol_chg_w  = 近 w 日均量 / 近 vol_base 日均量 − 1，窗口内个股任一日
      缺行 → None（同管线 rolling(min_periods=w)）；
    - close      = 个股在 t 的原始收盘价（无行情行 → None）。
    返回 {ts_code: {close, ret_3, ..., vwap_ret_3, vwap_ret_50,
    vol_chg_3, vol_chg_50, ...}}（全部窗口）。
    """

    by_code: dict[str, dict[str, tuple[Any, ...]]] = {}
    for row in price_rows:
        ts_code, trade_date = row[0], str(row[1])
        by_code.setdefault(ts_code, {})[trade_date] = row[2:]
    t = calendar[-1] if calendar else None
    out: dict[str, dict[str, Any]] = {}
    for ts_code, days in by_code.items():
        entry: dict[str, Any] = {"close": _num(days.get(t, (None,))[0]) if t else None}
        for w in windows:
            prev = calendar[-1 - w] if t and len(calendar) > w else None
            today_row = days.get(t) if t else None
            prev_row = days.get(prev) if prev else None
            adj_t = adj_p = None
            if today_row is not None and today_row[0] is not None and today_row[1] is not None:
                adj_t = float(today_row[0]) * float(today_row[1])
            if prev_row is not None and prev_row[0] is not None and prev_row[1] is not None:
                adj_p = float(prev_row[0]) * float(prev_row[1])
            entry[f"ret_{w}"] = (
                adj_t / adj_p - 1.0
                if adj_t is not None and adj_p not in (None, 0.0)
                else None
            )
            vwap_t = _num(today_row[2]) if today_row is not None else None
            vwap_p = _num(prev_row[2]) if prev_row is not None else None
            entry[f"vwap_ret_{w}"] = (
                vwap_t / vwap_p - 1.0
                if vwap_t is not None and vwap_p not in (None, 0.0)
                else None
            )
            if t and len(calendar) > vol_base:
                recent = calendar[-w:]
                base = calendar[-vol_base:]
                vols_w = [days[d][3] for d in recent if d in days and days[d][3] is not None]
                vols_b = [days[d][3] for d in base if d in days and days[d][3] is not None]
                if len(vols_w) == w and len(vols_b) == vol_base:
                    mean_w = sum(float(v) for v in vols_w) / w
                    mean_b = sum(float(v) for v in vols_b) / vol_base
                    entry[f"vol_chg_{w}"] = mean_w / mean_b - 1.0 if mean_b else None
                else:
                    entry[f"vol_chg_{w}"] = None
            else:
                entry[f"vol_chg_{w}"] = None
        out[ts_code] = entry
    return out


# ---------------------------------------------------------------------------
# DB 只读层
# ---------------------------------------------------------------------------


def _row_to_pool(row: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {"pool_key": row[0], "n_stocks": row[1]}
    for i, col in enumerate(_ALL_METRIC_COLS, start=2):
        entry[col] = _num(row[i])
    return entry


def pool_momentum_overview(
    db_url: str | None = None,
    trade_date: str | None = None,
) -> dict[str, Any]:
    """榜单截面：两 pool_type 分区（速度/加速度/共振/热力 + 事后验证列）。

    trade_date 指定历史交易日（只能用该日及之前数据，表天然 point-in-time）；
    缺省 = 最近 fwd 已补齐的交易日。payload 另含 fwd 可选日期列表
    （dates，降序）与加速度 Top10 验证摘要（summary，按 pool_type 分组）。
    """

    def _produce() -> dict[str, Any]:
        from sqlalchemy import text

        try:
            store = _store(db_url)
        except Exception as exc:
            return {"ok": False, "error": f"数据库不可用（{exc}）"}
        try:
            with store.market_engine.begin() as conn:
                latest = conn.execute(
                    text("SELECT max(trade_date) FROM cluster.pool_momentum_daily")
                ).scalar()
                if latest is None:
                    return {
                        "ok": True,
                        "empty": True,
                        "note": "cluster.pool_momentum_daily 暂无数据（先跑 cluster-ashare M7 管线）",
                    }
                # v2：末日 fwd 全 NULL 属正常一日滞后（T+1 收盘后补齐）；
                # 榜单默认展示最近 fwd 已补齐的交易日
                fwd_latest = conn.execute(
                    text(
                        "SELECT max(trade_date) FROM cluster.pool_momentum_daily "
                        "WHERE fwd_ret_3 IS NOT NULL"
                    )
                ).scalar()
                shown = str(trade_date) if trade_date else str(fwd_latest or latest)
                rows = conn.execute(
                    text(
                        f"SELECT pool_type, {_SELECT_COLS} FROM cluster.pool_momentum_daily "
                        "WHERE trade_date = :d"
                    ),
                    {"d": shown},
                ).fetchall()
                # v3：可选日期列表（有 fwd 数据的交易日，降序）
                dates = [
                    str(r[0])
                    for r in conn.execute(
                        text(
                            "SELECT DISTINCT trade_date FROM cluster.pool_momentum_daily "
                            "WHERE fwd_ret_3 IS NOT NULL ORDER BY trade_date DESC"
                        )
                    ).fetchall()
                ]
                # v3：事后验证——T 之后最多 max(POST_WINDOWS) 个交易日的 fwd_ret 日序列
                post_dates = [
                    r[0]
                    for r in conn.execute(
                        text(
                            "SELECT DISTINCT trade_date FROM cluster.pool_momentum_daily "
                            "WHERE trade_date > :d ORDER BY trade_date LIMIT :n"
                        ),
                        {"d": shown, "n": max(POST_WINDOWS)},
                    ).fetchall()
                ]
                post_rows = (
                    conn.execute(
                        text(
                            "SELECT pool_type, pool_key, trade_date, fwd_ret "
                            "FROM cluster.pool_momentum_daily "
                            "WHERE trade_date > :d AND trade_date <= :d1 "
                            "ORDER BY trade_date"
                        ),
                        {"d": shown, "d1": post_dates[-1]},
                    ).fetchall()
                    if post_dates
                    else []
                )
        except Exception as exc:
            return {"ok": False, "error": f"cluster.pool_momentum_daily 查询失败（{exc}）"}
        finally:
            store.close()

        fwd_series: dict[tuple[str, str], list[float | None]] = {}
        for pt, pk, _d, fwd in post_rows:
            fwd_series.setdefault((pt, pk), []).append(_num(fwd))

        groups: dict[str, list[dict[str, Any]]] = {"concept": [], "state": []}
        for row in rows:
            pool_type = row[0]
            if pool_type not in groups:
                continue
            entry = _row_to_pool(row[1:])
            entry["_pool_type"] = pool_type
            entry["resonance"] = {str(w): resonance_flag(entry, w) for w in WINDOWS}
            # 事件池标记：selection_artifact=true 的 8 个状态池才有事件统计
            entry["has_event"] = any(entry.get(c) is not None for c in EVENT_COLS)
            groups[pool_type].append(entry)
        summary: dict[str, Any] = {}
        for pool_type, group in groups.items():
            compute_post_returns(group, fwd_series)
            groups[pool_type] = sort_by_acceleration(compute_heat(compute_acceleration(group)))
            summary[pool_type] = accel_top_summary(group)
            for entry in group:
                entry.pop("_pool_type", None)
        fwd_lag = fwd_latest is not None and fwd_latest < latest
        return {
            "ok": True,
            "empty": False,
            "latest_date": shown,
            "latest_date_overall": str(latest),
            "fwd_lag": fwd_lag,
            "windows": list(WINDOWS),
            "post_windows": list(POST_WINDOWS),
            "dates": dates,
            "summary": summary,
            "speed_window": SPEED_WINDOW,
            "accel_window": ACCEL_WINDOW,
            "concept": groups["concept"],
            "state": groups["state"],
            "note": (
                "只读 cluster.pool_momentum_daily（M7 v2）；主口径=fwd_ret_w 前瞻收益"
                "（当日成分等权再平衡，对标东财板块指数），回看 ret_w 仅对照；"
                "concept 池成员为当前快照（前视偏差，demo 接受），state 池 point-in-time；"
                "加速度 = fwd_ret_50 排名 − fwd_ret_3 排名（正 = 短窗跃升）；"
                "post_w = T 日之后 w 个交易日的 fwd_ret 复利收益（不足 w 日 → NULL 未满窗口）"
            ),
            "fwd_note": (
                f"前瞻收益 T+1 收盘后补齐：末日 {latest} 的 fwd 列仍为 NULL（正常一日滞后），"
                f"榜单展示最近已补齐日 {shown}"
                if fwd_lag
                else "前瞻收益已补齐至榜单日期"
            ),
        }

    return _cached(f"pool_momentum_overview:{db_url}:{trade_date}", _produce)


def pool_momentum_detail(
    pool_type: str,
    pool_key: str,
    db_url: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """单池近 DETAIL_DAYS 个交易日时间序列（升序返回；end_date 指定序列末日）。"""

    if pool_type not in ("concept", "state"):
        return {"ok": False, "error": f"非法 pool_type：{pool_type!r}（仅 concept/state）"}
    if not pool_key:
        return {"ok": False, "error": "缺少 pool_key"}

    def _produce() -> dict[str, Any]:
        from sqlalchemy import text

        try:
            store = _store(db_url)
        except Exception as exc:
            return {"ok": False, "error": f"数据库不可用（{exc}）"}
        try:
            with store.market_engine.begin() as conn:
                sql = (
                    "SELECT trade_date, n_stocks, "
                    "ret_3, ret_20, ret_50, vwap_ret_3, vwap_ret_50, vol_chg_3, vol_chg_50, "
                    "fwd_ret, fwd_ret_3, fwd_ret_20, fwd_ret_50 "
                    "FROM cluster.pool_momentum_daily "
                    "WHERE pool_type = :pt AND pool_key = :pk "
                )
                params: dict[str, Any] = {"pt": pool_type, "pk": pool_key, "n": DETAIL_DAYS}
                if end_date:
                    sql += "AND trade_date <= :end "
                    params["end"] = end_date
                sql += "ORDER BY trade_date DESC LIMIT :n"
                rows = conn.execute(text(sql), params).fetchall()
        except Exception as exc:
            return {"ok": False, "error": f"cluster.pool_momentum_daily 查询失败（{exc}）"}
        finally:
            store.close()

        if not rows:
            return {"ok": True, "empty": True, "note": f"池 {pool_type}:{pool_key} 暂无数据"}
        rows = list(reversed(rows))  # 升序
        series = {
            "dates": [str(r[0]) for r in rows],
            "n_stocks": [r[1] for r in rows],
            "ret_3": [_num(r[2]) for r in rows],
            "ret_20": [_num(r[3]) for r in rows],
            "ret_50": [_num(r[4]) for r in rows],
            "vwap_ret_3": [_num(r[5]) for r in rows],
            "vwap_ret_50": [_num(r[6]) for r in rows],
            "vol_chg_3": [_num(r[7]) for r in rows],
            "vol_chg_50": [_num(r[8]) for r in rows],
            "fwd_ret": [_num(r[9]) for r in rows],
            "fwd_ret_3": [_num(r[10]) for r in rows],
            "fwd_ret_20": [_num(r[11]) for r in rows],
            "fwd_ret_50": [_num(r[12]) for r in rows],
        }
        return {
            "ok": True,
            "empty": False,
            "pool_type": pool_type,
            "pool_key": pool_key,
            "series": series,
        }

    return _cached(f"pool_momentum_detail:{pool_type}:{pool_key}:{end_date}:{db_url}", _produce)


def pool_momentum_members(
    pool_type: str,
    pool_key: str,
    trade_date: str | None = None,
    db_url: str | None = None,
) -> dict[str, Any]:
    """单池成员个股明细（指定交易日，缺省=池动量表最新交易日）。

    成员名单：concept 取 cluster.company_tags 快照（与 M7 管线同口径，
    前视偏差）；state 取该日 cluster.daily_tags（point-in-time）。
    个股指标由 public.stock_daily 即时计算（compute_member_metrics，
    与 M7 管线同口径）；名称 LEFT JOIN reference.stock_basic（表缺失/
    查询失败降级为无名称，不拖垮整页）。
    """

    if pool_type not in ("concept", "state"):
        return {"ok": False, "error": f"非法 pool_type：{pool_type!r}（仅 concept/state）"}
    if not pool_key:
        return {"ok": False, "error": "缺少 pool_key"}

    def _produce() -> dict[str, Any]:
        from sqlalchemy import text

        try:
            store = _store(db_url)
        except Exception as exc:
            return {"ok": False, "error": f"数据库不可用（{exc}）"}
        names: dict[str, str] = {}
        try:
            with store.market_engine.begin() as conn:
                if trade_date:
                    day = trade_date
                else:
                    day = conn.execute(
                        text("SELECT max(trade_date) FROM cluster.pool_momentum_daily")
                    ).scalar()
                if day is None:
                    return {"ok": True, "empty": True, "note": "cluster.pool_momentum_daily 暂无数据"}
                day = str(day)
                if pool_type == "concept":
                    codes = [
                        r[0]
                        for r in conn.execute(
                            text(
                                "SELECT DISTINCT ts_code FROM cluster.company_tags "
                                "WHERE tag = :pk ORDER BY ts_code"
                            ),
                            {"pk": pool_key},
                        ).fetchall()
                    ]
                else:
                    codes = [
                        r[0]
                        for r in conn.execute(
                            text(
                                "SELECT ts_code FROM cluster.daily_tags "
                                "WHERE trade_date = :d AND tag = :pk ORDER BY ts_code"
                            ),
                            {"d": day, "pk": pool_key},
                        ).fetchall()
                    ]
                if not codes:
                    return {
                        "ok": True,
                        "empty": True,
                        "pool_type": pool_type,
                        "pool_key": pool_key,
                        "trade_date": day,
                        "note": f"池 {pool_type}:{pool_key} 在 {day} 无成员",
                    }
                calendar = [
                    str(r[0])
                    for r in conn.execute(
                        text(
                            "SELECT DISTINCT trade_date FROM public.stock_daily "
                            "WHERE trade_date <= :d ORDER BY trade_date DESC LIMIT :n"
                        ),
                        {"d": day, "n": 51},
                    ).fetchall()
                ]
                calendar.sort()
                price_rows = conn.execute(
                    text(
                        "SELECT ts_code, trade_date, close, adj_factor, vwap, vol "
                        "FROM public.stock_daily "
                        "WHERE trade_date >= :d0 AND trade_date <= :d "
                        "AND ts_code = ANY(:codes)"
                    ),
                    {"d0": calendar[0], "d": day, "codes": codes},
                ).fetchall()
                try:
                    names = {
                        r[0]: r[1]
                        for r in conn.execute(
                            text(
                                "SELECT ts_code, name FROM reference.stock_basic "
                                "WHERE ts_code = ANY(:codes)"
                            ),
                            {"codes": codes},
                        ).fetchall()
                    }
                except Exception:
                    names = {}  # 名称表缺失/失败降级，不影响明细
        except Exception as exc:
            return {"ok": False, "error": f"成员明细查询失败（{exc}）"}
        finally:
            store.close()

        metrics = compute_member_metrics([tuple(r) for r in price_rows], calendar)
        members = [
            {
                "ts_code": code,
                "name": names.get(code),
                "close": None,
                **{f"ret_{w}": None for w in WINDOWS},
                "vwap_ret_3": None,
                "vwap_ret_50": None,
                "vol_chg_3": None,
                "vol_chg_50": None,
                **metrics.get(code, {}),
            }
            for code in codes
        ]
        members = sort_rows(members, f"ret_{ACCEL_WINDOW}", desc=True)
        return {
            "ok": True,
            "empty": False,
            "pool_type": pool_type,
            "pool_key": pool_key,
            "trade_date": day,
            "members": members,
            "note": (
                "成员名单：concept=cluster.company_tags 快照（前视偏差），"
                "state=当日 cluster.daily_tags（point-in-time）；"
                "指标即时算自 public.stock_daily（复权 close×adj_factor 比值 / "
                "vwap 比值 / 近 w 日均量对近 50 日均量），与 cluster.pool_momentum_daily 同口径"
            ),
        }

    return _cached(
        f"pool_momentum_members:{pool_type}:{pool_key}:{trade_date}:{db_url}",
        _produce,
    )
