"""策略实验台（lab，8081）应用测试（QRE-GUI-LAB-PORT-017）。

覆盖：lab 首页两个 tab、策略详情页与产物下载、关键 API
（/api/admin/refresh、/api/strategies/sandbox、/api/strategies/create 校验路径、
/api/admin/strategies/toggle），并确认 lab 不挂 8080 专有路由而 create_app 保持不变。

QRE-GUI-LAB-ENTRY-018：「新增策略」tab 三入口结构（自然语言/快速向导/高级 YAML）、
必选标注、高级选项折叠、NL 示例句与两步确认冒烟按钮。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def lab_client(monkeypatch, tmp_path):
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

    from quant_research_engine.gui.lab import create_lab_app

    app = create_lab_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# --- 首页：三个 tab（新增策略 / 回测管理 / 新增因子） ---


def test_lab_home_200_two_tabs(lab_client):
    resp = lab_client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    # 三个 tab 标记
    assert 'data-tab="strategy"' in html
    assert "新增策略" in html
    assert 'data-tab="onboard"' in html
    assert "回测管理" in html
    assert 'data-tab="factor"' in html
    assert "新增因子" in html
    # 新增策略 tab 关键交互（自 index.html strategy tab 移植）
    assert 'id="tab-strategy"' in html
    assert 'id="btn-nl-compile"' in html
    assert 'id="btn-save-sandbox"' in html
    assert 'id="sandbox-panel"' in html
    assert 'id="btn-deep-validate"' in html
    # 回测管理 tab：回测记录列表（QRE-GUI-CONSOL-040，原策略注册表已移除）
    assert 'id="tab-onboard"' in html
    assert 'id="btn-ob-refresh"' in html  # refresh 状态卡保留
    assert "/api/admin/refresh" in html
    assert 'id="btn-runs-refresh"' in html
    assert "ob-runs-table" in html
    assert "回测记录" in html
    assert "/api/lab/runs" in html
    # 原「策略注册表」元素与交互已移除
    assert "ob-registry-table" not in html
    assert "策略注册表" not in html
    assert "/api/admin/strategies/toggle" not in html
    assert "/api/admin/strategies/delete" not in html
    assert "renderRegistryTable" not in html


def test_lab_does_not_mount_full_console_routes(lab_client):
    # lab 只含三个页面相关路由：8080 的管理台/构建器路由不在 lab 上
    assert lab_client.get("/admin").status_code == 404
    assert lab_client.get("/api/admin/overview").status_code == 404
    assert lab_client.get("/api/builder/indicator-catalog").status_code == 404


# --- 新增因子 tab（QRE-GUI-CONSOL-039：自 8080 index.html 平移，三路径保留） ---


def test_lab_factor_tab_content(lab_client):
    resp = lab_client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    # tab 容器与三路径
    assert 'id="tab-factor"' in html
    assert "路径 A" in html and "补数据" in html
    assert "路径 B" in html and "造新指标" in html
    assert "路径 C" in html and "Alpha191" in html
    # 路径 A（factor-admin 补周期）关键元素
    assert 'id="wz-admin-name"' in html
    assert 'id="wz-admin-submit"' in html
    assert "wzGotoFactorAdmin" in html
    # 路径 B（factor-create 全新指标）关键元素
    assert 'id="fc-code"' in html
    assert 'id="fc-check"' in html
    assert 'id="fc-smoke"' in html
    assert 'id="fc-promote"' in html
    assert 'id="fc-sandbox-list"' in html
    # 冒烟轮询与状态文案（自 8080 平移的 JS）
    assert "/api/factor-create/smoke/" in html
    assert "wzGotoFactorAdmin" in html


def test_lab_factor_apis_available(lab_client, monkeypatch, tmp_path):
    """因子 API 在 8081 可用（与 8080 共享同一实现）。"""
    import quant_research_engine.gui.factor_create as fc

    monkeypatch.setattr(fc, "indicators_repo", lambda env=None: tmp_path)
    resp = lab_client.get("/api/factor-create/sandbox")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    # 校验路径
    assert lab_client.post(
        "/api/factor-create/check", json={"name": "", "category": "", "column": ""}
    ).status_code == 400
    assert lab_client.post(
        "/api/factor-admin/request", json={"name": "", "column": "close", "periods": "5"}
    ).status_code == 400
    assert lab_client.get("/api/factor-admin/jobs/nope").status_code == 404
    assert lab_client.get("/api/factor-create/smoke/nope").status_code == 404
    # 晋升后轮询用的 daily-jobs 状态查询（只读）也在 lab 上
    assert lab_client.get("/api/admin/daily-jobs/nope").status_code == 404


# --- 新增策略 tab 三入口结构（QRE-GUI-LAB-ENTRY-018） ---


def test_lab_strategy_three_entry_tabs(lab_client):
    resp = lab_client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    # 三个入口 tab，自然语言默认选中
    assert 'data-entry-tab="nl"' in html
    assert 'data-entry-tab="wizard"' in html
    assert 'data-entry-tab="yaml"' in html
    assert 'id="entry-tab-nl" class="entry-content active"' in html
    assert 'id="entry-tab-wizard" class="entry-content"' in html
    assert 'id="entry-tab-yaml" class="entry-content"' in html
    # NL 入口：大号输入框 + 可点击示例句（≥3 个，含规格指定两句）
    assert html.count('class="nl-example"') >= 3
    assert "5日均线上穿200日均线买入，下穿卖出，止损8%" in html
    assert "收盘价低于10元买入，高于12元卖出" in html
    # 快速向导：入场/出场条件必选（红色 * 标注）+ 占位示例提示
    assert '入场条件 <span class="req">*</span>' in html
    assert '出场条件 <span class="req">*</span>' in html
    assert "EMA5 上穿 EMA200" in html
    assert "EMA5 下穿 EMA200" in html
    # 向导比较符含上穿/下穿
    assert 'crosses_above' in html and '上穿' in html
    assert 'crosses_below' in html and '下穿' in html
    # 高级选项（可选）默认折叠
    assert 'data-section="wz-advanced"' in html
    assert 'id="sec-wz-advanced" class="section-body collapsed"' in html
    # 高级 YAML 底部冒烟按钮（两步确认第 1 步）
    assert 'id="btn-save-smoke"' in html
    assert "正式回测（晋升）" in html
    # 向导内鼠标-only 闭环（QRE-GUI-LAB-ENTRY-022）：冒烟按钮在向导页 + 去高级 YAML 为次按钮
    assert 'id="wz-save-smoke"' in html
    assert "去高级 YAML 修改详情" in html
    assert "saveAndSmoke" in html  # 向导/高级共用冒烟流程
    # 回测参数：必选仅回测区间与标的范围；其余收进折叠的高级参数
    assert '回测区间 <span class="req">*</span>' in html
    assert '标的范围 <span class="req">*</span>' in html
    assert 'id="param-all-market" checked' in html
    assert 'id="sec-adv-params" class="section-body collapsed"' in html
    assert 'id="param-commission" value="0.0003"' in html
    assert 'id="param-min-commission" value="5.0"' in html
    assert 'id="param-stamp-tax" value="0.0005"' in html
    # 旧平铺结构（checkbox 因子菜单栏）已移除
    assert 'id="wz-factor-groups"' not in html
    assert 'sec-wz-factors' not in html
    # 因子三级联动选单（QRE-GUI-LAB-ENTRY-020/021）：大类 → 子类 → 因子
    assert "wz-fact-group" in html          # 一级：大类
    assert "wz-fact-sub" in html            # 二级：子类（表/分段）
    assert "syncFactorSelect" in html       # 三级联动同步
    assert "optgroup" not in html           # 旧单组长下拉已移除
    assert "wz-fact-filter" not in html     # 搜索框已删除（用户反馈多余）
    # 每条件取反（NOT）：引擎 ast.Not + 向导勾选
    assert "wz-not" in html and "取反" in html


# --- 策略详情页 + 产物下载 ---


def _write_result(root: Path, batch: str, sid: str) -> Path:
    path = root / batch / sid / "backtest" / "strategy_performance.json"
    path.parent.mkdir(parents=True)
    payload = {
        "strategy_name": sid,
        "date_start": "2024-07-01",
        "date_end": "2026-07-27",
        "symbol_count": 5547,
        "traded_symbol_count": 3200,
        "excess_return_vs_buy_hold": -0.0234,
        "max_drawdown": -0.35,
        "strategy_total_return": 0.05,
        "buy_hold_return": 0.08,
        "win_rate": 0.45,
        "profit_factor": 1.2,
        "total_trade_count": 500,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _setup_detail_env(monkeypatch, tmp_path):
    import quant_research_engine.gui.refresh_registry as rr
    import quant_research_engine.gui.strategy_admin as sa

    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "s1.yaml").write_text(
        "# 说明: 测试策略\nexperiment:\n  name: s1_exp\nsignal:\n  entry: rsi_14 > 30\n",
        encoding="utf-8",
    )
    backtests = tmp_path / "backtests"
    _write_result(backtests, "b1", "s1")
    monkeypatch.setattr(rr, "DEFAULT_BACKTESTS_DIR", backtests)
    monkeypatch.setattr(rr, "CATALOG_DIR", catalog)
    monkeypatch.setattr(sa, "CATALOG_DIR", catalog)
    return catalog, backtests


def test_lab_strategy_detail(lab_client, monkeypatch, tmp_path):
    _setup_detail_env(monkeypatch, tmp_path)
    resp = lab_client.get("/admin/strategy/s1")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "s1" in html
    assert "测试策略" in html
    assert "产物文件下载" in html

    assert lab_client.get("/admin/strategy/ghost").status_code == 404


def test_lab_strategy_artifact(lab_client, monkeypatch, tmp_path):
    _setup_detail_env(monkeypatch, tmp_path)
    resp = lab_client.get("/api/admin/strategy/s1/artifact/backtest/strategy_performance.json")
    assert resp.status_code == 200
    # 越界拒绝
    resp = lab_client.get("/api/admin/strategy/s1/artifact/..%2F..%2Fsecret.txt")
    assert resp.status_code in (400, 404)
    assert lab_client.get("/api/admin/strategy/ghost/artifact/x.json").status_code == 404


# --- 关键 API 在 lab 上可用 ---


def test_lab_api_admin_refresh(lab_client, monkeypatch, tmp_path):
    import quant_research_engine.gui.refresh_registry as rr

    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "s1.yaml").write_text("experiment:\n  name: s1\n", encoding="utf-8")
    monkeypatch.setattr(rr, "CATALOG_DIR", catalog)
    monkeypatch.setattr(rr, "DEFAULT_REGISTRY_PATH", tmp_path / "registry.json")
    monkeypatch.setattr(rr, "DEFAULT_STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(rr, "DEFAULT_BACKTESTS_DIR", tmp_path / "backtests")
    monkeypatch.setattr(rr, "DEFAULT_INCREMENTAL_ROOT", tmp_path / "incremental")
    monkeypatch.setattr(rr, "DEFAULT_DELTA_ROOT", tmp_path / "delta")

    resp = lab_client.get("/api/admin/refresh")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["catalog_total"] == 1


def test_lab_api_refresh_register_validation(lab_client, monkeypatch, tmp_path):
    import quant_research_engine.gui.refresh_registry as rr

    catalog = tmp_path / "catalog"
    catalog.mkdir()
    monkeypatch.setattr(rr, "CATALOG_DIR", catalog)
    monkeypatch.setattr(rr, "DEFAULT_REGISTRY_PATH", tmp_path / "registry.json")

    assert lab_client.post("/api/admin/refresh/register", json={"strategy_id": ""}).status_code == 400
    assert lab_client.post("/api/admin/refresh/register", json={"strategy_id": "ghost"}).status_code == 400
    assert lab_client.post("/api/admin/refresh/unregister", json={"strategy_id": ""}).status_code == 400


def test_lab_api_toggle(lab_client, monkeypatch, tmp_path):
    import quant_research_engine.gui.refresh_registry as rr

    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "s1.yaml").write_text("x: 1", encoding="utf-8")
    monkeypatch.setattr(rr, "DEFAULT_REGISTRY_PATH", tmp_path / "registry.json")
    monkeypatch.setattr(rr, "CATALOG_DIR", catalog)

    resp = lab_client.post("/api/admin/strategies/toggle",
                           json={"strategy_id": "s1", "stopped": True})
    assert resp.status_code == 200
    assert resp.get_json()["stopped"] == ["s1"]
    assert lab_client.post("/api/admin/strategies/toggle",
                           json={"strategy_id": "ghost", "stopped": True}).status_code == 400


def test_lab_api_strategies_sandbox(lab_client, monkeypatch, tmp_path):
    import quant_research_engine.gui.strategy_create as sc

    monkeypatch.setattr(sc, "DEFAULT_SANDBOX_DIR", tmp_path / "sandbox")
    resp = lab_client.get("/api/strategies/sandbox")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["strategies"] == []
    assert data["categories"]


def test_lab_api_strategies_create_invalid_yaml(lab_client):
    resp = lab_client.post("/api/strategies/create",
                           json={"mode": "manual", "yaml_text": ": 不是合法yaml"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert data["code"] == "invalid_yaml"


def test_lab_api_validate(lab_client):
    resp = lab_client.post("/api/validate", json={"yaml": "experiment:\n  name: x\n"})
    assert resp.status_code == 200
    assert "valid" in resp.get_json()


def test_lab_api_templates(lab_client):
    assert lab_client.get("/api/templates").status_code == 200
    assert lab_client.post("/api/templates", json={"name": "", "yaml": "x"}).status_code == 400


# --- 8080 主控制台路由零变化（共享注册后仍全量可用） ---


def test_create_app_routes_unchanged():
    from quant_research_engine.gui.app import create_app
    from quant_research_engine.gui.lab import create_lab_app

    full_rules = {r.rule for r in create_app().url_map.iter_rules()}
    lab_rules = {r.rule for r in create_lab_app().url_map.iter_rules()}
    # lab 路由是主控制台的子集（除 8081 专属的结果可视化路由，QRE-GUI-LAB-RESULT-023）
    lab_only = {"/lab/runs/<run_id>", "/api/lab/runs/<run_id>/chart-data",
                "/api/lab/runs/<run_id>/tag-analysis",
                "/api/lab/runs/<run_id>/risk-analysis",  # QRE-GUI-LAB-RESULT-031
                "/lab/runs/<run_id>/symbol/<ts_code>",
                "/api/lab/runs/<run_id>/symbol/<ts_code>/detail",
                "/api/lab/runs",                          # QRE-GUI-CONSOL-040
                "/api/lab/runs/<run_id>/delete"}          # QRE-GUI-CONSOL-040
    assert lab_rules - lab_only <= full_rules
    assert lab_only & full_rules == set()  # 8080 不挂新路由
    # 主控制台专有规律犹在（因子创建/补周期 API 自 QRE-GUI-CONSOL-039 起两应用共享）
    for rule in ("/admin", "/api/admin/overview",
                 "/api/builder/compile", "/api/admin/market-risk", "/compare"):
        assert rule in full_rules
        assert rule not in lab_rules
