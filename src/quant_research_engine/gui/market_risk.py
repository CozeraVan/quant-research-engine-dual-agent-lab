"""管理台「大盘风险」风向标数据层（CR_2026-08-23_market_risk_barometer M3）。

只读 market_risk.daily（barometer_job 日更产物），不触业务表、不写任何数据。
遵循管理台"只查询状态"定位：数据源不可用时返回 {"ok": False, "error": ...}
降级，不拖垮整页。结果经 admin._cached TTL 缓存。
"""

from __future__ import annotations

from typing import Any

from quant_research_engine.gui.admin import _cached, _store

#: 时间序列窗口（交易日，与分位归一化窗口一致）
SERIES_DAYS = 252

_SCOPE_MARKET = "market"


def _num(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v == v else None  # NaN → None


def _row_to_board(scope: str, n_stocks: Any, indicators: dict, scores: Any, alert: Any) -> dict[str, Any]:
    ind = indicators or {}
    sc = scores or {}
    al = alert or {}
    return {
        "scope": scope,
        "n_stocks": n_stocks,
        "total_score": _num(sc.get("total_score")),
        "warmup": bool(sc.get("warmup", True)),
        "alert": al.get("alert"),
        "median_sigma": _num(ind.get("median_sigma")),
        "dispersion": _num(ind.get("dispersion_equal_weight")),
        "avg_corr": _num(ind.get("avg_pairwise_corr_equal_weight")),
        "breach_ratio": _num(ind.get("var_breach_ratio")),
    }


def market_risk_overview(db_url: str | None = None) -> dict[str, Any]:
    """风向标总览：最新 market 行 + 近 252 日序列 + 行业/簇两视图板块表。"""

    def _produce() -> dict[str, Any]:
        from sqlalchemy import text

        try:
            store = _store(db_url)
        except Exception as exc:
            return {"ok": False, "error": f"数据库不可用（{exc}）"}
        try:
            with store.market_engine.begin() as conn:
                latest = conn.execute(
                    text("SELECT max(trade_date) FROM market_risk.daily")
                ).scalar()
                if latest is None:
                    return {"ok": True, "empty": True, "note": "market_risk.daily 暂无数据（先跑 barometer_job）"}
                market_rows = conn.execute(
                    text(
                        "SELECT trade_date, n_stocks, indicators, scores, alert "
                        "FROM market_risk.daily WHERE scope = 'market' "
                        "ORDER BY trade_date DESC LIMIT :n"
                    ),
                    {"n": SERIES_DAYS},
                ).fetchall()
                board_rows = conn.execute(
                    text(
                        "SELECT scope, n_stocks, indicators, scores, alert "
                        "FROM market_risk.daily WHERE trade_date = :d AND scope <> 'market'"
                    ),
                    {"d": latest},
                ).fetchall()
        except Exception as exc:
            return {"ok": False, "error": f"market_risk.daily 查询失败（{exc}）"}
        finally:
            store.close()

        market_rows = list(reversed(market_rows))  # 升序
        series = {
            "dates": [str(r[0]) for r in market_rows],
            "total_score": [_num((r[3] or {}).get("total_score")) for r in market_rows],
            "median_sigma": [_num((r[2] or {}).get("median_sigma")) for r in market_rows],
            "dispersion": [_num((r[2] or {}).get("dispersion_equal_weight")) for r in market_rows],
            "avg_corr": [_num((r[2] or {}).get("avg_pairwise_corr_equal_weight")) for r in market_rows],
            "breach_ratio": [_num((r[2] or {}).get("var_breach_ratio")) for r in market_rows],
            "alert": [((r[4] or {}).get("alert")) for r in market_rows],
        }
        latest_market = market_rows[-1]
        alert_detail = latest_market[4] or {}
        market = _row_to_board("market", latest_market[1], latest_market[2], latest_market[3], latest_market[4])
        market["alert_detail"] = {
            "corr_change": _num(alert_detail.get("corr_change")),
            "corr_jump_threshold": _num(alert_detail.get("corr_jump_threshold")),
            "corr_exceed": alert_detail.get("corr_exceed"),
            "breach_ratio_latest": _num(alert_detail.get("breach_ratio_latest")),
            "breach_ratio_threshold": _num(alert_detail.get("breach_ratio_threshold")),
            "breach_exceed": alert_detail.get("breach_exceed"),
        }

        industries: list[dict[str, Any]] = []
        clusters: list[dict[str, Any]] = []
        for scope, n_stocks, indicators, scores, alert in board_rows:
            entry = _row_to_board(scope, n_stocks, indicators, scores, alert)
            if scope.startswith("industry:"):
                entry["name"] = scope[len("industry:"):]
                industries.append(entry)
            elif scope.startswith("cluster:"):
                entry["name"] = scope[len("cluster:"):]
                clusters.append(entry)
        # 排序：有分数按分数降序，无分数（簇）按突破占比降序
        industries.sort(key=lambda e: (e["total_score"] is not None, e["total_score"] or -1), reverse=True)
        clusters.sort(key=lambda e: e["breach_ratio"] or -1, reverse=True)
        return {
            "ok": True,
            "empty": False,
            "latest_date": str(latest),
            "market": market,
            "series": series,
            "industries": industries,
            "clusters": clusters,
            "note": "只读 market_risk.daily；簇分数 M2 不算（成员逐日变动），簇表按突破占比排序",
        }

    return _cached(f"market_risk_overview:{db_url}", _produce)
