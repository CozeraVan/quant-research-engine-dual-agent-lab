"""聚类分析 tab（QRE-ADMIN-CLUSTER-001）：数据解析、容错降级、路由、下载白名单。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quant_research_engine.gui import cluster_admin
from quant_research_engine.gui.cluster_admin import (
    m4_overview,
    monitor_health,
    parse_monitor_md,
    report_links,
    resolve_artifact,
)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "outputs" / "factor_mining"
    (root / "clustering").mkdir(parents=True)
    (root / "monitor").mkdir()
    (root / "validation").mkdir()
    (root / "clustering" / "m4_meta.json").write_text(
        json.dumps(
            {
                "dates": ["2024-08-01", "2026-08-17"],
                "n_days": 495,
                "best_k": 20,
                "ari_mean": 0.311,
                "ari_median": 0.307,
                "n_traj": 20,
                "n_sig": 2,
                "kept_cols": 191,
                "forward": "T 收盘 -> T+5 收盘",
                "hidden": {
                    "traj": 13,
                    "snapshot": "2026-08-10",
                    "explain": {
                        "industry": {"top": "机械设备", "share": 0.225},
                        "total": 0.346,
                        "n_members": 3,
                    },
                    "top_dims": [["alpha097", -0.342]],
                },
            }
        ),
        encoding="utf-8",
    )
    (root / "clustering" / "m4_trajectories_alive.csv").write_text(
        "traj,present,first,last,coverage,avg_n,days,mean,t,p,pos_ratio,q\n"
        "13,490,2024-08-01,2026-08-10,1.0,328,490,0.0037,3.1,0.002,0.55,0.02\n"
        "0,490,2024-08-01,2026-08-10,1.0,258,490,-0.0009,-1.13,0.258,0.43,0.52\n",
        encoding="utf-8",
    )
    (root / "clustering" / "hidden_cluster_members.csv").write_text(
        "ts_code\n000029.SZ\n000586.SZ\n000762.SZ\n", encoding="utf-8"
    )
    (root / "monitor" / "monitor_2026-08-18.md").write_text(
        "# 因子信号衰减监控（2026-08-18）\n\n"
        "| factor_id | 条件 | 信号日数 | 近20日超额 | 近60日超额 | 趋势 | 建议 |\n"
        "|---|---|---|---|---|---|---|\n"
        "| MF_001 | factor:atrr_14 ∧ tag:hv20:极低 | 59 | +0.06% | -0.06% | ↗ | 正常 |\n"
        "| MF_002 | factor:alpha072 | 59 | -0.55% | -0.13% | ↗ | 关注 |\n"
        "| MF_008 | factor:alpha127 ∧ tag:atr:收缩 | 59 | -0.17% | +0.03% | ↘ | 建议转衰减观察 |\n",
        encoding="utf-8",
    )
    (root / "validation" / "leaderboard_v1.csv").write_text("date,group\n", encoding="utf-8")
    return tmp_path


def test_parse_monitor_md_counts_and_decay_candidates() -> None:
    text = (
        "# 标题\n\n"
        "| factor_id | 条件 | 信号日数 | 近20日超额 | 近60日超额 | 趋势 | 建议 |\n"
        "|---|---|---|---|---|---|---|\n"
        "| MF_001 | a | 59 | +0.06% | -0.06% | ↗ | 正常 |\n"
        "| MF_002 | b | 59 | -0.55% | -0.13% | ↗ | 关注 |\n"
        "| MF_008 | c | 59 | -0.17% | +0.03% | ↘ | 建议转衰减观察 |\n"
        "非表格行\n"
    )
    parsed = parse_monitor_md(text)
    assert len(parsed["rows"]) == 3
    assert parsed["counts"] == {"正常": 1, "关注": 1, "建议转衰减观察": 1}
    assert parsed["decay_candidates"] == ["MF_008"]


def test_m4_overview_ok(repo: Path) -> None:
    result = m4_overview(repo)
    assert result["ok"] is True
    assert result["best_k"] == 20
    assert result["n_sig"] == 2
    # 显著轨迹（q<0.05 且正超额）排最前
    assert result["trajectories"][0]["traj"] == "13"
    assert result["trajectories"][0]["significant"] is True
    assert result["trajectories"][1]["significant"] is False
    assert result["hidden_profile"]["industry_top"] == "机械设备"
    assert result["hidden_members"] == ["000029.SZ", "000586.SZ", "000762.SZ"]


def test_m4_overview_missing_meta_degrades(tmp_path: Path) -> None:
    result = m4_overview(tmp_path)
    assert result["ok"] is False
    assert "m4_meta.json" in result["error"]


def test_m4_overview_bad_json_degrades(repo: Path) -> None:
    (repo / "outputs" / "factor_mining" / "clustering" / "m4_meta.json").write_text(
        "{not json", encoding="utf-8"
    )
    result = m4_overview(repo)
    assert result["ok"] is False


def test_monitor_health_ok(repo: Path) -> None:
    result = monitor_health(repo)
    assert result["ok"] is True
    assert result["report"] == "monitor_2026-08-18.md"
    assert result["factor_count"] == 3
    assert result["counts"]["正常"] == 1
    assert result["decay_candidates"] == ["MF_008"]


def test_monitor_health_missing_dir_degrades(tmp_path: Path) -> None:
    result = monitor_health(tmp_path)
    assert result["ok"] is False


def test_monitor_health_empty_dir_degrades(repo: Path) -> None:
    for f in (repo / "outputs" / "factor_mining" / "monitor").glob("*.md"):
        f.unlink()
    result = monitor_health(repo)
    assert result["ok"] is False
    assert "无" in result["error"]


def test_report_links_lists_existing_only(repo: Path) -> None:
    result = report_links(repo)
    assert result["ok"] is True
    rels = {a["rel"] for a in result["artifacts"]}
    assert "clustering/m4_poc_report.md" not in rels  # 不存在则跳过
    assert "clustering/m4_meta.json" in rels
    assert "validation/leaderboard_v1.csv" in rels
    # 最新 monitor 报告自动列入
    assert "monitor/monitor_2026-08-18.md" in rels


def test_resolve_artifact_whitelist(repo: Path) -> None:
    ok = resolve_artifact("clustering/m4_meta.json", repo)
    assert ok is not None and ok.name == "m4_meta.json"
    # 越界路径
    assert resolve_artifact("../../etc/passwd", repo) is None
    assert resolve_artifact("../m4_meta.json", repo) is None
    # 不存在的文件
    assert resolve_artifact("clustering/nope.md", repo) is None


def test_resolve_artifact_suffix_whitelist(repo: Path) -> None:
    parquet = repo / "outputs" / "factor_mining" / "clustering" / "m4_labels.parquet"
    parquet.write_bytes(b"PAR1")
    assert resolve_artifact("clustering/m4_labels.parquet", repo) is None


# --- 路由 ---


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, clause, params=None):
        return _FakeResult(self._rows)


class _FakeEngine:
    def __init__(self, rows):
        self._rows = rows

    def begin(self):
        return _FakeConn(self._rows)


class _FakeStore:
    def __init__(self, rows):
        self.market_engine = _FakeEngine(rows)

    def close(self):
        pass


def _clear_cache() -> None:
    from quant_research_engine.gui import admin

    admin._cache.clear()


def test_factor_registry_and_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_cache()
    rows = [
        (
            "MF_001",
            "复合",
            "衰减观察",
            {"key": "factor:atrr_14 ∧ tag:hv20:极低", "type": "composite"},
            {"n_years": 6, "consistency": 0.8889, "excess_d5": 0.0789, "score": 0.21},
        ),
        ("MF_007", "alpha单因子", "在库", {"key": "factor:alpha185", "type": "single"}, {"n_years": 5}),
    ]
    monkeypatch.setattr(cluster_admin, "_store", lambda db_url=None: _FakeStore(rows))
    monkeypatch.setattr(cluster_admin, "cluster_repo", lambda env=None: tmp_path)

    result = cluster_admin.factor_registry()
    assert result["ok"] is True
    assert result["total"] == 2
    assert result["factors"][0]["factor_id"] == "MF_001"
    assert result["factors"][0]["status_class"] == "decay"
    assert result["factors"][1]["status_class"] == "active"
    assert result["status_counts"] == {"衰减观察": 1, "在库": 1}

    from quant_research_engine.gui.app import create_app

    client = create_app().test_client()
    resp = client.get("/api/admin/cluster")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["sections"]["registry"]["total"] == 2
    # repo 为空目录：m4/monitor 分区降级但不拖垮整页
    assert data["sections"]["m4"]["ok"] is False
    assert data["sections"]["monitor"]["ok"] is False


def test_factor_registry_db_error_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_cache()

    def _boom(db_url=None):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(cluster_admin, "_store", _boom)
    result = cluster_admin.factor_registry()
    assert result["ok"] is False
    assert result["factors"] == []


def test_cluster_artifact_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "outputs" / "factor_mining" / "clustering"
    root.mkdir(parents=True)
    (root / "m4_meta.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cluster_admin, "cluster_repo", lambda env=None: tmp_path)

    from quant_research_engine.gui.app import create_app

    client = create_app().test_client()
    assert client.get("/api/admin/cluster/artifact/clustering/m4_meta.json").status_code == 200
    assert client.get("/api/admin/cluster/artifact/clustering/nope.md").status_code == 404
    assert client.get("/api/admin/cluster/artifact/..%2F..%2Fetc%2Fpasswd").status_code == 404


def test_admin_page_contains_cluster_tab() -> None:
    from quant_research_engine.gui.app import create_app

    client = create_app().test_client()
    resp = client.get("/admin")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'data-tab="cluster"' in html
    assert "聚类分析" in html
    assert "/api/admin/cluster" in html
