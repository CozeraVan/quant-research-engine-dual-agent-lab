"""管理台「聚类分析」状态层（QRE-ADMIN-CLUSTER-001）。

只读展示 cluster-ashare 因子工厂产出：PG cluster schema（mined_factors/
cluster_reports/keyword_tracks）+ outputs/factor_mining 下的 md/json/csv 产物。
遵循管理台"只查询状态"定位：只发 SELECT / 只读文件，不写任何数据。
每个分区独立 try/except 降级——某数据源不可用时该分区返回
{"ok": False, "error": ...}，不拖垮整页。

repo 路径：env QRE_CLUSTER_REPO，默认 <workspace>/cluster-ashare
（<workspace>/quant-research-engine-dual-agent-lab 的兄弟目录）。
"""

from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path
from typing import Any

from quant_research_engine.gui.admin import _cached, _store

ENV_CLUSTER_REPO = "QRE_CLUSTER_REPO"

# 下载白名单：仅 factor_mining 产物根下的文本类产物
CLUSTER_ARTIFACT_ROOT_REL = Path("outputs") / "factor_mining"
CLUSTER_ARTIFACT_SUFFIXES = {".md", ".csv", ".json"}

HIDDEN_MEMBERS_LIMIT = 50

STATUS_LABELS = {"在库": "active", "衰减观察": "decay"}


def cluster_repo(env: dict[str, str] | None = None) -> Path:
    env = env if env is not None else os.environ
    configured = (env.get(ENV_CLUSTER_REPO) or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    # <workspace>/quant-research-engine-dual-agent-lab/src/quant_research_engine/gui/cluster_admin.py
    # → <workspace>/cluster-ashare
    return Path(__file__).resolve().parents[4] / "cluster-ashare"


def _outputs_dir(repo: Path) -> Path:
    return repo / CLUSTER_ARTIFACT_ROOT_REL


# ---------------------------------------------------------------------------
# 分区 1：因子注册表（PG cluster.mined_factors，只读）
# ---------------------------------------------------------------------------


def factor_registry(db_url: str | None = None) -> dict[str, Any]:
    """38 因子注册表：factor_id/类型/状态/跨年数/方向一致率/+5 超额。"""
    from sqlalchemy import text

    def _produce() -> dict[str, Any]:
        try:
            store = _store(db_url)
        except Exception as exc:
            return {"ok": False, "error": f"数据库不可用（{exc}）", "factors": []}
        try:
            with store.market_engine.begin() as conn:
                rows = conn.execute(
                    text(
                        "SELECT factor_id, family, status, definition, evidence "
                        "FROM cluster.mined_factors ORDER BY factor_id"
                    )
                ).fetchall()
        except Exception as exc:
            return {"ok": False, "error": f"cluster.mined_factors 查询失败（{exc}）", "factors": []}
        finally:
            store.close()
        factors: list[dict[str, Any]] = []
        for factor_id, family, status, definition, evidence in rows:
            definition = definition or {}
            evidence = evidence or {}
            factors.append(
                {
                    "factor_id": factor_id,
                    "key": str(definition.get("key") or ""),
                    "type": str(definition.get("type") or family or ""),
                    "family": str(family or ""),
                    "status": str(status or ""),
                    "status_class": STATUS_LABELS.get(str(status), "other"),
                    "n_years": evidence.get("n_years"),
                    "consistency": evidence.get("consistency"),
                    "excess_d5": evidence.get("excess_d5"),
                    "n_instances": evidence.get("n_instances"),
                    "score": evidence.get("score"),
                }
            )
        status_counts: dict[str, int] = {}
        for f in factors:
            status_counts[f["status"]] = status_counts.get(f["status"], 0) + 1
        return {"ok": True, "factors": factors, "total": len(factors), "status_counts": status_counts}

    return _cached(f"cluster_registry:{db_url}", _produce)


# ---------------------------------------------------------------------------
# 分区 2：M4 隐性聚类（clustering/ 下 m4_meta.json + 轨迹 CSV + 成员 CSV）
# ---------------------------------------------------------------------------


def _read_csv_rows(path: Path, limit: int | None = None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            rows.append(row)
            if limit is not None and len(rows) >= limit:
                break
    return rows


def m4_overview(repo: Path | None = None) -> dict[str, Any]:
    """M4 POC 关键指标 + 显著轨迹表 + 隐性簇（traj13）当日成员名单。"""
    repo = repo or cluster_repo()
    clustering = _outputs_dir(repo) / "clustering"

    def _produce() -> dict[str, Any]:
        meta_path = clustering / "m4_meta.json"
        if not meta_path.is_file():
            return {"ok": False, "error": f"m4_meta.json 不存在（{meta_path}）"}
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"ok": False, "error": f"m4_meta.json 解析失败（{exc}）"}

        # 轨迹表：显著（q<0.05 且 mean>0）排前，其余按 mean 降序
        trajectories: list[dict[str, Any]] = []
        traj_path = clustering / "m4_trajectories_alive.csv"
        if traj_path.is_file():
            try:
                for row in _read_csv_rows(traj_path):
                    def _f(key: str) -> float | None:
                        try:
                            return float(row[key])
                        except (KeyError, TypeError, ValueError):
                            return None

                    mean = _f("mean")
                    q = _f("q")
                    trajectories.append(
                        {
                            "traj": row.get("traj", ""),
                            "days": row.get("days", ""),
                            "avg_n": _f("avg_n"),
                            "mean": mean,
                            "t": _f("t"),
                            "p": _f("p"),
                            "pos_ratio": _f("pos_ratio"),
                            "q": q,
                            "significant": bool(q is not None and q < 0.05 and mean is not None and mean > 0),
                        }
                    )
                trajectories.sort(key=lambda t: (not t["significant"], -(t["mean"] or 0.0)))
            except Exception:
                trajectories = []

        # 隐性簇画像摘要（m4_meta.hidden.explain，成员名单不进 meta 响应）
        hidden_meta = meta.get("hidden") or {}
        explain = hidden_meta.get("explain") or {}
        profile = None
        if explain:
            industry = explain.get("industry") or {}
            profile = {
                "traj": hidden_meta.get("traj"),
                "snapshot": hidden_meta.get("snapshot"),
                "n_members": explain.get("n_members"),
                "explain_total": explain.get("total"),
                "industry_top": industry.get("top"),
                "industry_share": industry.get("share"),
                "top_dims": hidden_meta.get("top_dims") or [],
            }

        # 隐性簇当日成员名单（前 50 行）
        members: list[str] = []
        members_path = clustering / "hidden_cluster_members.csv"
        if members_path.is_file():
            try:
                members = [r.get("ts_code", "") for r in _read_csv_rows(members_path, limit=HIDDEN_MEMBERS_LIMIT)]
            except Exception:
                members = []

        return {
            "ok": True,
            "dates": meta.get("dates"),
            "n_days": meta.get("n_days"),
            "best_k": meta.get("best_k"),
            "ari_mean": meta.get("ari_mean"),
            "ari_median": meta.get("ari_median"),
            "n_traj": meta.get("n_traj"),
            "n_sig": meta.get("n_sig"),
            "kept_cols": meta.get("kept_cols"),
            "forward": meta.get("forward"),
            "trajectories": trajectories,
            "hidden_profile": profile,
            "hidden_members": members,
            "hidden_members_limit": HIDDEN_MEMBERS_LIMIT,
            "hidden_members_total": explain.get("n_members"),
        }

    return _cached(f"cluster_m4:{repo}", _produce)


# ---------------------------------------------------------------------------
# 分区 3：衰减监控（monitor/monitor_<date>.md 最新一份，解析 markdown 表）
# ---------------------------------------------------------------------------

_MONITOR_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")


def parse_monitor_md(text: str) -> dict[str, Any]:
    """解析监控报告的因子表：按最后一列建议计数，收集「建议转衰减观察」清单。"""
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        match = _MONITOR_ROW_RE.match(line)
        if not match:
            continue
        cells = [c.strip() for c in match.group(1).split("|")]
        if len(cells) < 7:
            continue
        first = cells[0]
        if first in ("factor_id", "") or set(first) <= {"-", ":"}:
            continue
        if not first.startswith("MF_"):
            continue
        rows.append(
            {
                "factor_id": first,
                "condition": cells[1],
                "signal_days": cells[2],
                "excess_20d": cells[3],
                "excess_60d": cells[4],
                "trend": cells[5],
                "advice": cells[6],
            }
        )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["advice"]] = counts.get(row["advice"], 0) + 1
    decay_candidates = [r["factor_id"] for r in rows if "衰减" in r["advice"]]
    return {"rows": rows, "counts": counts, "decay_candidates": decay_candidates}


def monitor_health(repo: Path | None = None) -> dict[str, Any]:
    """最新 monitor_<date>.md：正常/关注/衰减观察计数 + 建议转衰减清单。"""
    repo = repo or cluster_repo()
    monitor_dir = _outputs_dir(repo) / "monitor"

    def _produce() -> dict[str, Any]:
        if not monitor_dir.is_dir():
            return {"ok": False, "error": f"监控目录不存在（{monitor_dir}）"}
        reports = sorted(monitor_dir.glob("monitor_*.md"))
        if not reports:
            return {"ok": False, "error": "无 monitor_*.md 报告"}
        latest = reports[-1]
        try:
            parsed = parse_monitor_md(latest.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"ok": False, "error": f"监控报告解析失败（{exc}）"}
        return {
            "ok": True,
            "report": latest.name,
            "report_date": latest.stem.replace("monitor_", ""),
            "factor_count": len(parsed["rows"]),
            "counts": parsed["counts"],
            "decay_candidates": parsed["decay_candidates"],
            "rows": parsed["rows"],
        }

    return _cached(f"cluster_monitor:{repo}", _produce)


# ---------------------------------------------------------------------------
# 分区 4：报告链接（factor_mining 产物清单，下载走白名单路由）
# ---------------------------------------------------------------------------

# (label, 相对 factor_mining 的路径)；不存在的文件如实跳过
REPORT_ARTIFACTS = [
    ("M4 POC 报告", "clustering/m4_poc_report.md"),
    ("M4 元数据", "clustering/m4_meta.json"),
    ("M4 存活轨迹", "clustering/m4_trajectories_alive.csv"),
    ("M4 全部轨迹", "clustering/m4_trajectories_all.csv"),
    ("隐性簇当日成员", "clustering/hidden_cluster_members.csv"),
    ("M4 k 扫描", "clustering/m4_k_scan.csv"),
    ("验证排行榜 v1", "validation/leaderboard_v1.csv"),
    ("跨年存活排行榜", "validation/survival_leaderboard.csv"),
    ("跨年存活排行榜 v2", "validation/survival_leaderboard_v2.csv"),
    ("验证报告 v1", "validation/validation_v1.md"),
    ("历史重验证报告", "validation/历史重验证报告.md"),
    ("跨年度重验证报告", "validation/跨年度重验证报告.md"),
]


def report_links(repo: Path | None = None) -> dict[str, Any]:
    """关键 md/csv/json 产物链接清单；monitor 目录取最新一份一并列出。"""
    repo = repo or cluster_repo()
    root = _outputs_dir(repo)

    def _produce() -> dict[str, Any]:
        artifacts: list[dict[str, Any]] = []
        for label, rel in REPORT_ARTIFACTS:
            path = root / rel
            if not path.is_file():
                continue
            stat = path.stat()
            artifacts.append({"label": label, "rel": rel, "size_bytes": stat.st_size})
        monitor_dir = root / "monitor"
        if monitor_dir.is_dir():
            reports = sorted(monitor_dir.glob("monitor_*.md"))
            if reports:
                latest = reports[-1]
                rel = f"monitor/{latest.name}"
                artifacts.insert(
                    0,
                    {"label": f"衰减监控（{latest.stem.replace('monitor_', '')}）", "rel": rel,
                     "size_bytes": latest.stat().st_size},
                )
        return {"ok": True, "root": str(root), "artifacts": artifacts}

    return _cached(f"cluster_links:{repo}", _produce)


def resolve_artifact(rel_path: str, repo: Path | None = None) -> Path | None:
    """下载白名单解析：目标必须在 factor_mining 产物根内且后缀在白名单。"""
    repo = repo or cluster_repo()
    root = _outputs_dir(repo).resolve()
    target = (root / rel_path).resolve()
    if root not in target.parents or not target.is_file():
        return None
    if target.suffix.lower() not in CLUSTER_ARTIFACT_SUFFIXES:
        return None
    return target


# ---------------------------------------------------------------------------
# 聚合入口（路由一次调用；各分区已独立降级）
# ---------------------------------------------------------------------------


def cluster_overview(db_url: str | None = None, repo: Path | None = None) -> dict[str, Any]:
    repo = repo or cluster_repo()
    sections: dict[str, Any] = {}
    for name, producer in (
        ("registry", lambda: factor_registry(db_url)),
        ("m4", lambda: m4_overview(repo)),
        ("monitor", lambda: monitor_health(repo)),
        ("links", lambda: report_links(repo)),
    ):
        try:
            sections[name] = producer()
        except Exception as exc:  # 防御：单分区异常不影响其他分区
            sections[name] = {"ok": False, "error": f"{name} 加载失败（{exc}）"}
    return {"ok": True, "repo": str(repo), "sections": sections}
