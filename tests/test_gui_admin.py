from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from quant_research_engine.gui import admin
from quant_research_engine.gui.admin import (
    expected_factor_columns,
    factor_status,
    health_status,
    overview_backtests,
    parse_systemctl_show,
    timer_status,
)


# --- fake DB store ---


class _FakeResult:
    def __init__(self, *, scalar=None, rows=None, mappings=None):
        self._scalar = scalar
        self._rows = rows or []
        self._mappings = mappings

    def scalar(self):
        return self._scalar

    def fetchall(self):
        return self._mappings if self._mappings is not None else self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def mappings(self):
        return self

    @property
    def scalar_one_or_none(self):
        return self._scalar


class _FakeConn:
    """按 SQL 文本特征返回固定结果；记录所有查询。"""

    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, clause, params=None):
        sql = str(clause)
        params = params or {}
        self.store.queries.append((sql, params))
        if "pg_class" in sql:
            return _FakeResult(rows=[(123456,)])
        if "pg_stats" in sql:
            return _FakeResult(scalar=5209.0)
        if "COUNT(*)" in sql:
            return _FakeResult(scalar=3)
        if "MAX(trade_date)" in sql and "factors" in sql:
            for table, wm in self.store.factor_maxes.items():
                if f'"{table}"' in sql:
                    return _FakeResult(scalar=wm)
            return _FakeResult(scalar=None)
        if "MAX(trade_date)" in sql:
            return _FakeResult(scalar="2026-07-27")
        if "DISTINCT trade_date" in sql:
            return _FakeResult(rows=[("2026-07-27",), ("2026-07-24",)])
        if "information_schema.tables" in sql:
            return _FakeResult(rows=[("stock_daily_momentum_close",), ("stock_daily_overlap_close",)])
        # data rows
        mappings = [
            {"trade_date": "2026-07-27", "ts_code": params.get("ts_code"), "close": "10.5"},
            {"trade_date": "2026-07-24", "ts_code": params.get("ts_code"), "close": "10.3"},
        ]
        return _FakeResult(mappings=mappings)


class _FakeEngine:
    def __init__(self, store):
        self.store = store

    def begin(self):
        return _FakeConn(self.store)


class FakeStore:
    def __init__(self, columns=("ts_code", "trade_date", "rsi_14"), factor_maxes=None):
        self.queries: list[tuple[str, dict]] = []
        self.market_engine = _FakeEngine(self)
        self._columns = list(columns)
        self.factor_maxes = factor_maxes or {
            "stock_daily_momentum_close": "2026-07-24",
            "stock_daily_overlap_close": "2026-07-24",
        }

    def ping(self):
        return True

    def close(self):
        pass

    def table_exists(self, table_name, *, engine=None):
        return table_name == "factors.stock_daily_momentum_close"

    def get_table_columns(self, table_name, *, engine=None):
        return list(self._columns)


# --- 因子状态对账（REFocus） ---


def _expected_payload():
    return {
        "stock_daily_momentum_close": {
            "columns": ["rsi_14", "rsi_6", "macd_12_26_9"],
            "tasks": [{"name": "rsi", "params": ["6", "14"], "expanded": True}],
        },
        "stock_daily_overlap_close": {
            "columns": ["sma_20", "sma_60"],
            "tasks": [{"name": "sma", "params": ["20", "60"], "expanded": True}],
        },
    }


def test_expected_factor_columns_ok(monkeypatch):
    admin._cache.clear()
    payload = json.dumps(_expected_payload())

    def runner(cmd, **kw):
        assert cmd[:3] == ["/home/van/.local/bin/uv", "run", "python"]
        return _Proc(stdout=payload)

    result = expected_factor_columns(runner=runner)
    assert result is not None
    assert result["stock_daily_momentum_close"]["columns"] == ["rsi_14", "rsi_6", "macd_12_26_9"]
    admin._cache.clear()


def test_expected_factor_columns_failure_returns_none(monkeypatch):
    admin._cache.clear()
    assert expected_factor_columns(runner=lambda cmd, **kw: _Proc("boom", 1)) is None
    assert expected_factor_columns(runner=lambda cmd, **kw: _Proc("")) is None
    assert expected_factor_columns(runner=lambda cmd, **kw: _Proc("not json")) is None
    admin._cache.clear()


def _setup_factor_status(monkeypatch, columns_map, expected):
    """columns_map: {bare_table: [columns...]}；expected: payload 或 None。"""
    admin._cache.clear()

    class _ColumnStore(FakeStore):
        def get_table_columns(self, table_name, *, engine=None):
            bare = table_name.split(".")[-1]
            return columns_map.get(bare, ["ts_code", "trade_date"])

    monkeypatch.setattr("quant_research_engine.gui.admin._store", lambda db_url=None: _ColumnStore())
    monkeypatch.setattr(
        "quant_research_engine.gui.admin.managed_factor_tables",
        lambda repo=None: {"stock_daily_momentum_close", "stock_daily_overlap_close"},
    )
    monkeypatch.setattr(
        "quant_research_engine.gui.admin.expected_factor_columns",
        lambda repo=None, runner=None: expected,
    )


def test_factor_status_three_way(monkeypatch):
    _setup_factor_status(
        monkeypatch,
        {
            # rsi_14 在库且在配置(绿)；rsi_99 在库不在配置(黄)；缺 macd_12_26_9/rsi_6(红)
            "stock_daily_momentum_close": ["ts_code", "trade_date", "rsi_14", "rsi_99"],
            "stock_daily_overlap_close": ["ts_code", "trade_date", "sma_20", "sma_60"],
        },
        _expected_payload(),
    )
    status = factor_status()
    assert status["expected_available"] is True
    by_table = {t["table"]: t for t in status["tables"]}
    mom = by_table["factors.stock_daily_momentum_close"]
    assert mom["green"] == ["rsi_14"]
    assert mom["yellow"] == ["rsi_99"]
    assert mom["red"] == ["macd_12_26_9", "rsi_6"]
    ovl = by_table["factors.stock_daily_overlap_close"]
    assert ovl["green"] == ["sma_20", "sma_60"]
    assert ovl["yellow"] == [] and ovl["red"] == []
    assert status["summary"]["green"] == 3
    assert status["summary"]["yellow"] == 1
    assert status["summary"]["red"] == 2
    admin._cache.clear()


def test_factor_status_degrades_to_config_level(monkeypatch):
    _setup_factor_status(
        monkeypatch,
        {"stock_daily_momentum_close": ["ts_code", "trade_date", "rsi_14"]},
        None,  # 展开失败
    )
    monkeypatch.setattr(
        "quant_research_engine.gui.admin._config_level_tasks",
        lambda repo=None: [{"name": "rsi", "category": "momentum", "column": "close", "params": ["14"]}],
    )
    status = factor_status()
    assert status["expected_available"] is False
    assert status["config_level"][0]["name"] == "rsi"
    for t in status["tables"]:
        assert "green" not in t  # 无列级状态
    admin._cache.clear()


# --- 新鲜度判定（交易日 lag，QRE-ADMIN-FACTOR-FRESH-001） ---


def test_trade_day_lag_trading_days_not_calendar_days():
    """跨周末/长假只算交易日差：07-24(五)→07-27(一) 自然日 3 天但交易日差为 1。"""
    dates = ["2026-07-27", "2026-07-24", "2026-07-23", "2026-07-22"]
    assert admin.trade_day_lag("2026-07-27", "2026-07-27", dates) == 0
    assert admin.trade_day_lag("2026-07-24", "2026-07-27", dates) == 1
    assert admin.trade_day_lag("2026-07-22", "2026-07-27", dates) == 3
    # 任一输入缺失 → None（降级）
    assert admin.trade_day_lag(None, "2026-07-27", dates) is None
    assert admin.trade_day_lag("2026-07-24", None, dates) is None
    assert admin.trade_day_lag("2026-07-24", "2026-07-27", None) is None
    assert admin.trade_day_lag("2026-07-24", "2026-07-27", []) is None


def test_fresh_level_thresholds():
    assert admin._fresh_level(0) == "ok"
    assert admin._fresh_level(1) == "warn"
    assert admin._fresh_level(2) == "err"
    assert admin._fresh_level(9) == "err"
    assert admin._fresh_level(None) is None


def test_factor_status_freshness_lag(monkeypatch):
    """表 watermark 07-24、日线 07-27（交易日序列 2 天）→ lag_days=1 / fresh=warn，
    按自然日差则是 3 天会误报严重滞后——验证用的是交易日差。"""
    _setup_factor_status(
        monkeypatch,
        {
            "stock_daily_momentum_close": ["ts_code", "trade_date", "rsi_14"],
            "stock_daily_overlap_close": ["ts_code", "trade_date", "sma_20", "sma_60"],
        },
        _expected_payload(),
    )
    status = factor_status()
    assert status["fresh_available"] is True
    by_table = {t["table"]: t for t in status["tables"]}
    mom = by_table["factors.stock_daily_momentum_close"]
    assert mom["lag_days"] == 1
    assert mom["fresh"] == "warn"
    assert status["summary"]["lagging"] == 2
    assert status["summary"]["stale"] == 0
    admin._cache.clear()


def test_factor_status_freshness_levels_and_stale(monkeypatch):
    """lag 0=ok / ≥2=err 的分档；stale 计入 lagging。"""
    admin._cache.clear()

    class _ColumnStore(FakeStore):
        def get_table_columns(self, table_name, *, engine=None):
            return ["ts_code", "trade_date", "x"]

    store = _ColumnStore(factor_maxes={
        "stock_daily_momentum_close": "2026-07-27",  # 最新
        "stock_daily_overlap_close": "2026-07-22",   # 落后 3 个交易日
    })

    # 交易日序列含 4 天，让 overlap 算出 lag=3
    class _Conn(_FakeConn):
        def execute(self, clause, params=None):
            sql = str(clause)
            if "DISTINCT trade_date" in sql:
                return _FakeResult(
                    rows=[("2026-07-27",), ("2026-07-24",), ("2026-07-23",), ("2026-07-22",)]
                )
            return super().execute(clause, params)

    store.market_engine = type("_Eng", (), {"begin": lambda self: _Conn(store)})()
    monkeypatch.setattr("quant_research_engine.gui.admin._store", lambda db_url=None: store)
    monkeypatch.setattr(
        "quant_research_engine.gui.admin.managed_factor_tables",
        lambda repo=None: {"stock_daily_momentum_close", "stock_daily_overlap_close"},
    )
    monkeypatch.setattr(
        "quant_research_engine.gui.admin.expected_factor_columns",
        lambda repo=None, runner=None: None,
    )
    status = factor_status()
    by_table = {t["table"]: t for t in status["tables"]}
    assert by_table["factors.stock_daily_momentum_close"]["fresh"] == "ok"
    assert by_table["factors.stock_daily_momentum_close"]["lag_days"] == 0
    assert by_table["factors.stock_daily_overlap_close"]["fresh"] == "err"
    assert by_table["factors.stock_daily_overlap_close"]["lag_days"] == 3
    assert status["summary"]["lagging"] == 1
    assert status["summary"]["stale"] == 1
    admin._cache.clear()


def test_factor_status_freshness_degrades_when_dates_unavailable(monkeypatch):
    """交易日序列查询失败：fresh/lag_days 为 null，页面其余部分不受影响。"""
    _setup_factor_status(
        monkeypatch,
        {"stock_daily_momentum_close": ["ts_code", "trade_date", "rsi_14"]},
        _expected_payload(),
    )

    def _boom(db_url=None):
        raise RuntimeError("db down")

    monkeypatch.setattr("quant_research_engine.gui.admin.overview_daily", _boom)
    status = factor_status()
    assert status["fresh_available"] is False
    for t in status["tables"]:
        assert t["fresh"] is None
        assert t["lag_days"] is None
    assert status["summary"]["lagging"] == 0
    assert status["summary"]["stale"] == 0
    # 列级对账不受影响
    assert status["expected_available"] is True
    admin._cache.clear()


# --- systemctl 解析 ---


def test_parse_systemctl_show():
    output = "ActiveState=active\nResult=success\nNextElapseUSecRealtime=Mon 2026-07-28 16:30:00 CST\n"
    props = parse_systemctl_show(output)
    assert props["ActiveState"] == "active"
    assert props["Result"] == "success"


class _Proc:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.returncode = returncode


def _runner_factory(mapping):
    def runner(cmd, **kwargs):
        unit = cmd[2]
        return mapping.get(unit, _Proc("LoadState=not-found\n", 1))
    return runner


def test_timer_status_installed_and_not_installed():
    mapping = {
        "quant-ts-daily.timer": _Proc(
            "LoadState=loaded\nActiveState=active\nUnitFileState=enabled\nNextElapseUSecRealtime=Mon 2026-07-28 16:30\n"
        ),
        "quant-ts-daily.service": _Proc(
            "LoadState=loaded\nActiveEnterTimestamp=Mon 2026-07-27 16:30\nResult=success\nExecMainStatus=0\n"
        ),
    }
    units = [
        {"unit": "quant-ts-daily.timer", "label": "日线", "service": "quant-ts-daily.service"},
        {"unit": "qre-refresh.timer", "label": "QRE", "service": "qre-refresh.service"},
    ]
    results = timer_status(units, runner=_runner_factory(mapping))
    qt, qr = results
    assert qt["status"] == "installed"
    assert qt["active_state"] == "active"
    assert qt["next_elapse"] == "Mon 2026-07-28 16:30"
    assert qt["last_result"] == "success"
    assert qt["last_exit_status"] == "0"
    assert qr["status"] == "not_installed"
    assert "sudo cp deploy/qre-refresh" in qr["install_hint"]


# --- health ---


def test_health_green():
    h = health_status("2026-07-27", ["2026-07-27", "2026-07-27"])
    assert h["level"] == "green"


def test_health_yellow_small_lag():
    h = health_status("2026-07-27", ["2026-07-27", "2026-07-25"])
    assert h["level"] == "yellow"
    assert "滞后" in h["detail"]


def test_health_red_large_lag_or_missing():
    assert health_status("2026-07-27", ["2026-07-01"])["level"] == "red"
    assert health_status("2026-07-27", [None, "2026-07-27"])["level"] == "red"
    assert health_status(None, ["2026-07-27"])["level"] == "red"


# --- overview_backtests ---


def test_overview_backtests(tmp_path):
    (tmp_path / "backtests" / "b1" / "strat_a").mkdir(parents=True)
    (tmp_path / "backtests" / "b1" / "strat_b").mkdir(parents=True)
    (tmp_path / "backtests" / "b2" / "strat_c").mkdir(parents=True)
    admin._cache.clear()
    with patch("quant_research_engine.gui.admin.subprocess.run") as mock_run:
        mock_run.return_value = _Proc(stdout=f"{5 * 1024**3}\t{tmp_path}\n")
        result = overview_backtests(tmp_path)
    assert result["batch_count"] == 2
    assert result["strategy_dir_count"] == 3
    assert result["size_bytes"] == 5 * 1024**3
    assert result["latest_batch"] == "b2"
    # 缓存命中：第二次不再调 du
    result2 = overview_backtests(tmp_path)
    assert result2["batch_count"] == 2
    assert mock_run.call_count == 1
    admin._cache.clear()


# --- overview_daily / overview_factors（fake store 注入） ---


def test_overview_daily_and_factors(monkeypatch):
    admin._cache.clear()
    monkeypatch.setattr("quant_research_engine.gui.admin._store", lambda db_url=None: FakeStore())
    monkeypatch.setattr(
        "quant_research_engine.gui.admin.managed_factor_tables",
        lambda repo=None: {"stock_daily_momentum_close", "stock_daily_overlap_close"},
    )
    daily = admin.overview_daily()
    assert daily["estimated_rows"] == 123456
    assert daily["watermark"] == "2026-07-27"
    assert daily["estimated_symbol_count"] == 5209  # pg_stats.n_distinct 估算
    assert "symbol_count" not in daily
    assert daily["recent_trade_dates"] == ["2026-07-27", "2026-07-24"]

    factors = admin.overview_factors()
    assert factors["daily_watermark"] == "2026-07-27"
    assert len(factors["tables"]) == 2
    assert factors["unmanaged_tables"] == []
    assert factors["lagging_tables"] == [
        "factors.stock_daily_momentum_close",
        "factors.stock_daily_overlap_close",
    ]
    admin._cache.clear()


# --- 纳管表清单（QRE-ADMIN-FACTOR-HEALTH-FIX-001） ---


def test_managed_factor_tables_from_config(tmp_path, monkeypatch):
    import quant_research_engine.gui.factor_admin as fa

    repo = tmp_path / "indicators"
    (repo / "config").mkdir(parents=True)
    (repo / "config" / "factors.yaml").write_text(
        "factors:\n"
        "  - name: sma\n    category: overlap\n    column: close\n    periods: [5]\n"
        "  - name: ema\n    category: overlap\n    column: typical_price\n    periods: [3]\n"
        "  - name: rsi\n    category: momentum\n    column: close\n    periods: [14]\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(fa, "indicators_repo", lambda env=None: repo)
    tables = admin.managed_factor_tables()
    assert tables == {
        "stock_daily_overlap_close",
        "stock_daily_overlap_typical_price",
        "stock_daily_momentum_close",
        "stock_daily_alpha191",
    }


def test_managed_factor_tables_fallback(monkeypatch, tmp_path):
    import quant_research_engine.gui.factor_admin as fa

    monkeypatch.setattr(fa, "indicators_repo", lambda env=None: tmp_path / "nonexistent")
    tables = admin.managed_factor_tables()
    assert tables == set(admin.MANAGED_FACTOR_TABLES_FALLBACK) | {"stock_daily_alpha191"}
    assert len(tables) == 11
    assert "stock_daily_vortex_close" not in tables


def test_factor_status_includes_alpha191(monkeypatch):
    """alpha191 表不符合 <category>_<price> 命名，但纳管后仍参与对账。"""
    expected = _expected_payload()
    expected["stock_daily_alpha191"] = {
        "columns": ["alpha001", "alpha002"],
        "tasks": [{"name": "alpha191_panel", "params": [], "expanded": True}],
    }
    _setup_factor_status(
        monkeypatch,
        {
            "stock_daily_momentum_close": ["ts_code", "trade_date", "rsi_14", "rsi_6", "macd_12_26_9"],
            "stock_daily_overlap_close": ["ts_code", "trade_date", "sma_20", "sma_60"],
            # alpha191 表在库但列尚未全建（回填中）：alpha002 缺失 → red
            "stock_daily_alpha191": ["ts_code", "trade_date", "alpha001"],
        },
        expected,
    )
    monkeypatch.setattr(
        "quant_research_engine.gui.admin.managed_factor_tables",
        lambda repo=None: {
            "stock_daily_momentum_close",
            "stock_daily_overlap_close",
            "stock_daily_alpha191",
        },
    )
    status = factor_status()
    by_table = {t["table"]: t for t in status["tables"]}
    alpha = by_table["factors.stock_daily_alpha191"]
    assert alpha["green"] == ["alpha001"]
    assert alpha["red"] == ["alpha002"]
    assert alpha["yellow"] == []
    admin._cache.clear()


def test_overview_factors_orphan_goes_unmanaged(monkeypatch):
    """孤儿表（不在纳管清单）进未纳管段，不参与滞后判定。"""
    admin._cache.clear()
    monkeypatch.setattr("quant_research_engine.gui.admin._store", lambda db_url=None: FakeStore())
    # 只纳管 momentum；overlap 视为孤儿表
    monkeypatch.setattr(
        "quant_research_engine.gui.admin.managed_factor_tables",
        lambda repo=None: {"stock_daily_momentum_close"},
    )
    factors = admin.overview_factors()
    assert [t["table"] for t in factors["tables"]] == ["factors.stock_daily_momentum_close"]
    assert [t["table"] for t in factors["unmanaged_tables"]] == ["factors.stock_daily_overlap_close"]
    assert factors["lagging_tables"] == ["factors.stock_daily_momentum_close"]
    admin._cache.clear()


def test_overview_factors_orphan_does_not_affect_health(monkeypatch):
    """纳管表全部新鲜时健康灯为绿，即使存在滞后/空的孤儿表。"""
    admin._cache.clear()
    store = FakeStore(factor_maxes={
        "stock_daily_momentum_close": "2026-07-27",  # 纳管，新鲜
        "stock_daily_overlap_close": None,           # 孤儿，无数据
    })
    monkeypatch.setattr("quant_research_engine.gui.admin._store", lambda db_url=None: store)
    monkeypatch.setattr(
        "quant_research_engine.gui.admin.managed_factor_tables",
        lambda repo=None: {"stock_daily_momentum_close"},
    )
    factors = admin.overview_factors()
    assert factors["lagging_tables"] == []
    health = admin.health_status(
        factors["daily_watermark"], [t["watermark"] for t in factors["tables"]]
    )
    assert health["level"] == "green"
    # 孤儿表仍在未纳管段可见
    assert factors["unmanaged_tables"][0]["table"] == "factors.stock_daily_overlap_close"
    admin._cache.clear()


# --- 路由层 ---


@pytest.fixture
def app_client(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "quant_research_engine.gui.app.TEMPLATE_DIR",
        Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "templates",
    )
    monkeypatch.setattr(
        "quant_research_engine.gui.app.STATIC_DIR",
        Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "static",
    )
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path / "templates")
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("quant_research_engine.gui.engine.GUI_BASE_DIR", tmp_path)
    admin._cache.clear()

    from quant_research_engine.gui.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client
    admin._cache.clear()


def test_admin_page_200(app_client):
    resp = app_client.get("/admin")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "管理台" in html
    assert "总览" in html and "日更中心" in html and "因子状态" in html and "策略状态" in html
    assert "数据查询" not in html  # REFocus：查询 tab 已撤
    assert "fc-create" not in html  # 新建因子子区已迁往首页「新增因子」tab
    assert "新增因子请前往首页" in html


def test_api_admin_overview_ok(app_client, monkeypatch):
    monkeypatch.setattr("quant_research_engine.gui.admin._store", lambda db_url=None: FakeStore())
    monkeypatch.setattr(
        "quant_research_engine.gui.admin.managed_factor_tables",
        lambda repo=None: {"stock_daily_momentum_close", "stock_daily_overlap_close"},
    )
    resp = app_client.get("/api/admin/overview")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["daily"]["watermark"] == "2026-07-27"
    assert data["health"]["level"] in ("yellow", "red")  # fake 因子表滞后
    assert "backtests" in data


def test_api_admin_overview_db_down(app_client, monkeypatch):
    def boom(db_url=None):
        raise ConnectionError("refused")

    monkeypatch.setattr("quant_research_engine.gui.admin._store", boom)
    resp = app_client.get("/api/admin/overview")
    assert resp.status_code == 503
    assert "数据库不可用" in resp.get_json()["error"]


def test_api_admin_query_routes_removed(app_client):
    # REFocus：数据查询路由已撤
    assert app_client.get("/api/admin/query/daily").status_code == 404
    assert app_client.get("/api/admin/query/factor").status_code == 404


def test_api_admin_factor_status_ok(app_client, monkeypatch):
    monkeypatch.setattr(
        "quant_research_engine.gui.admin.factor_status",
        lambda db_url=None: {
            "expected_available": True,
            "daily_watermark": "2026-07-27",
            "tables": [],
            "unmanaged_tables": [],
            "config_level": None,
            "summary": {"green": 3, "yellow": 1, "red": 0},
        },
    )
    resp = app_client.get("/api/admin/factor-status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["summary"]["green"] == 3


def test_api_admin_factor_status_503(app_client, monkeypatch):
    def boom(db_url=None):
        raise ConnectionError("refused")

    monkeypatch.setattr("quant_research_engine.gui.admin.factor_status", boom)
    resp = app_client.get("/api/admin/factor-status")
    assert resp.status_code == 503
    assert "因子状态获取失败" in resp.get_json()["error"]


def test_api_admin_timers(app_client, monkeypatch):
    monkeypatch.setattr(
        "quant_research_engine.gui.admin.timer_status",
        lambda units=None: [{"unit": "qre-refresh.timer", "status": "not_installed"}],
    )
    resp = app_client.get("/api/admin/timers")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["timers"][0]["status"] == "not_installed"


# --- Dashboard 查询台模式（QRE-ADMIN-DASH-QUERY-001） ---


def test_cache_ttl_is_300():
    assert admin.CACHE_TTL_SECONDS == 300


def test_cached_single_flight():
    """并发同 key 请求共享同一次计算。"""
    import threading

    admin._cache.clear()
    admin._cache_locks.clear()
    calls = {"n": 0}

    def producer():
        calls["n"] += 1
        time.sleep(0.2)
        return "value"

    results = []

    def worker():
        results.append(admin._cached("sf-test", producer, ttl=300))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert calls["n"] == 1
    assert results == ["value"] * 4
    admin._cache.clear()
    admin._cache_locks.clear()


def test_admin_page_query_only_mode(app_client):
    resp = app_client.get("/admin")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    # 搜索框
    assert 'id="fs-search"' in html
    assert 'id="ob-search"' in html
    # MANAGE：注册/新建入口已恢复；维护区 tab 存在
    assert "维护区" in html
    assert "data-del" in html
    assert "data-backfill" in html


def test_admin_template_script_parses_with_node():
    """回归：admin.html 内联 JS 必须通过 node --check（语法错误会使整页事件失效）。"""
    import re
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node") or (
        "/home/van/codex-local/node-v22/bin/node"
        if Path("/home/van/codex-local/node-v22/bin/node").exists()
        else None
    )
    if not node:
        import pytest

        pytest.skip("node 不可用")
    tpl = (
        Path(__file__).resolve().parents[1]
        / "src/quant_research_engine/gui/templates/admin.html"
    ).read_text(encoding="utf-8")
    scripts = re.findall(r"<script>(.*?)</script>", tpl, re.S)
    assert scripts, "admin.html 应包含内联 script"
    js_path = Path("/tmp/qre_admin_template_check.js")
    js_path.write_text("\n".join(scripts), encoding="utf-8")
    result = subprocess.run([node, "--check", str(js_path)], capture_output=True, text=True)
    assert result.returncode == 0, f"admin.html 内联 JS 语法错误: {result.stderr[:500]}"


# --- 衍生品域卡片（QRE-GUI-DERIV-CARD-012） ---


class _DerivConn(_FakeConn):
    """derivatives schema 五表：to_regclass 存在性 + 行数 + MAX(trade_date)。"""

    def __init__(self, store, present_tables, watermarks=None):
        super().__init__(store)
        self._present = set(present_tables)
        self._watermarks = watermarks or {}

    def execute(self, clause, params=None):
        sql = str(clause)
        if "to_regclass" in sql:
            name = (params or {}).get("name", "")
            table = name.split(".")[-1]
            return _FakeResult(scalar=name if table in self._present else None)
        if "MAX(trade_date)" in sql and "derivatives" in sql:
            for table, wm in self._watermarks.items():
                if f'"{table}"' in sql:
                    return _FakeResult(scalar=wm)
            return _FakeResult(scalar=None)
        return super().execute(clause, params)


class _DerivStore(FakeStore):
    def __init__(self, conn):
        self._conn = conn
        self.queries = []

    @property
    def market_engine(self):
        store = self

        class _E:
            def begin(self):
                return store._conn

        return _E()


def _setup_derivatives(monkeypatch, present, watermarks=None):
    admin._cache.clear()
    store = FakeStore()
    conn = _DerivConn(store, present, watermarks)
    monkeypatch.setattr(
        "quant_research_engine.gui.admin._store", lambda db_url=None: _DerivStore(conn)
    )
    return conn


def test_overview_derivatives_ok(monkeypatch):
    _setup_derivatives(
        monkeypatch,
        present={"cb_daily", "cb_basic", "yc_curve", "opt_daily", "opt_basic"},
        watermarks={"cb_daily": "2026-08-20", "yc_curve": "2026-08-20", "opt_daily": "2026-08-19"},
    )
    out = admin.overview_derivatives()
    assert out["ok"] is True
    assert out["present_count"] == 5 and out["total"] == 5
    by_table = {t["table"]: t for t in out["tables"]}
    assert by_table["derivatives.cb_daily"]["watermark"] == "2026-08-20"
    assert by_table["derivatives.cb_daily"]["estimated_rows"] == 123456  # pg_class fake
    # 静态表：只有行数，无 watermark
    assert by_table["derivatives.cb_basic"]["watermark"] is None
    assert by_table["derivatives.cb_basic"]["estimated_rows"] == 123456
    admin._cache.clear()


def test_overview_derivatives_partial_and_missing(monkeypatch):
    """部分表存在；缺失表 present=False、行数/日期为 None（卡片显示未初始化）。"""
    _setup_derivatives(monkeypatch, present={"cb_basic"}, watermarks={})
    out = admin.overview_derivatives()
    assert out["ok"] is True
    assert out["present_count"] == 1
    by_table = {t["table"]: t for t in out["tables"]}
    assert by_table["derivatives.cb_basic"]["present"] is True
    assert by_table["derivatives.opt_daily"]["present"] is False
    assert by_table["derivatives.opt_daily"]["estimated_rows"] is None
    admin._cache.clear()


def test_overview_derivatives_db_down(monkeypatch):
    admin._cache.clear()

    def boom(db_url=None):
        raise ConnectionError("refused")

    monkeypatch.setattr("quant_research_engine.gui.admin._store", boom)
    out = admin.overview_derivatives()
    assert out["ok"] is False
    assert "数据库不可用" in out["error"]
    admin._cache.clear()


def test_api_admin_overview_includes_derivatives(app_client, monkeypatch):
    _setup_derivatives(
        monkeypatch,
        present={"cb_daily", "cb_basic"},
        watermarks={"cb_daily": "2026-08-20"},
    )
    monkeypatch.setattr(
        "quant_research_engine.gui.admin.managed_factor_tables",
        lambda repo=None: {"stock_daily_momentum_close", "stock_daily_overlap_close"},
    )
    resp = app_client.get("/api/admin/overview")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["derivatives"]["present_count"] == 2


def test_admin_template_has_derivatives_card(app_client):
    html = app_client.get("/admin").data.decode("utf-8")
    assert 'id="ov-derivatives"' in html
    assert "衍生品数据" in html
