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
    # 两个 tab 标记（QRE-SAAS-011：「新增因子」tab 已删；QRE-LAB-UI-LANDING-R5：卡片上方重复 tab 按钮删除，切换改由顶部导航 data-tab-link 承担）
    assert 'data-tab-link="strategy"' in html
    assert "新增策略" in html
    assert 'data-tab-link="onboard"' in html
    assert "回测记录" in html
    assert 'data-tab="factor"' not in html
    assert "新增因子" not in html
    # 新增策略 tab 关键交互（自 index.html strategy tab 移植）
    assert 'id="tab-strategy"' in html
    assert 'id="btn-nl-compile"' in html
    assert 'id="btn-save-sandbox"' not in html  # QRE-SAAS-011：一键回测，不再有单独「存入沙箱」
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
    # QRE-LAB-UI-LANDING：记录表「股票数量」列 + 删除二次确认弹层
    assert "股票数量" in html
    assert 'id="run-del-mask"' in html and "确认删除" in html
    # R5：超额收益列（可排序）+ 整行点击 + 查看结果胶囊链接 + 向导内嵌预览框删除
    assert "超额收益" in html and 'data-k="excess_return"' in html and 'data-k="created_at"' in html
    assert "row-link" in html and "view-link" in html
    assert 'id="wz-yaml-preview"' not in html
    assert "excess_return" in html  # /api/lab/runs 字段（后端 _excess_return_of 聚合）
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


def test_lab_html_no_store(lab_client):
    """缺陷修复回归：HTML 页面禁缓存（浏览器启发式缓存曾让用户拿到中间态页面）。"""
    for path in ("/", "/lab/runs/ghost"):
        resp = lab_client.get(path)
        assert "no-store" in resp.headers.get("Cache-Control", "")
    # 静态资源不受影响（Flask 默认 no-cache 即可）
    resp = lab_client.get("/static/lab-theme.css")
    assert resp.status_code == 200
    assert "no-store" not in resp.headers.get("Cache-Control", "")


# --- 新增因子 tab（QRE-GUI-CONSOL-039：自 8080 index.html 平移，三路径保留） ---


def test_lab_factor_tab_removed(lab_client):
    """QRE-SAAS-011：「新增因子」tab 及其全部交互已删；缺因子走申请弹窗。"""
    resp = lab_client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    for marker in ('id="tab-factor"', 'id="fc-code"', 'id="fc-promote"',
                   'id="wz-admin-submit"', "wzGotoFactorAdmin",
                   "/api/factor-create/smoke/", 'data-tab="factor"'):
        assert marker not in html, marker
    # 缺因子申请弹窗（NL 编译 missing_factors 时弹出）
    assert 'id="factor-modal"' in html
    assert "提交因子需求" in html and "换个策略" in html
    assert "/api/lab/factor-requests" in html


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
    # QRE-LAB-UI-LANDING-R3（18080 定稿）：向导内高级选项折叠整块移除（止损/止盈/移动止损/持仓/组合器），
    # AND/OR 收进两级条件组（组内切换器 + 组间 divider 切换器）
    assert 'data-section="wz-advanced"' not in html
    assert 'id="sec-wz-advanced"' not in html
    assert "cond-groups" in html and "cond-group" in html  # 类名（JS 构建）
    assert 'data-addgroup="entry"' in html and 'data-addgroup="exit"' in html
    assert "添加条件组" in html
    assert "更复杂的逻辑组合，可切换到自然语言或 YAML 入口直接描述" in html
    # 一键回测（QRE-LAB-UI-LANDING：三入口汇聚到底部预览栏 + 唯一「运行回测」流水线按钮；
    # 各入口内的最终动作按钮已删，后端流程不变）
    assert 'id="btn-save-smoke"' not in html
    assert 'id="wz-save-smoke"' not in html
    assert "去高级 YAML 修改详情" not in html
    assert 'id="btn-run-main"' in html            # 唯一主按钮
    assert 'id="preview-card"' in html            # 策略代码预览栏（唯一 YAML 真相源，在参数区之后）
    assert 'id="pv-view"' in html and "pv-line" in html  # 行号 + 语法高亮合并视图（1:1 移植）
    # 缺陷修复：编辑代码提升为预览栏头部主按钮（实心紫），复制为次按钮
    # 预览栏按钮以 18080 定稿为准：编辑代码为次级 btn-sm（回退 R2 的主按钮化），复制同级
    assert 'class="btn-sm" id="pv-edit-toggle">编辑代码<' in html
    assert 'class="btn-sm" id="btn-copy-yaml"' in html
    assert 'id="pv-edit-hint"' not in html
    # lab-ui.js 不用 defer：保证先于内联脚本就绪（消除 LabUI 时序隐患）
    assert '<script src="/static/lab-ui.js"></script>' in html
    assert "把一个想法，变成可验证的策略" in html          # 设计稿 hero
    assert html.index('id="preview-card"') > html.index('回测参数 Parameters')
    assert 'id="strategy-yaml"' in html           # 编辑器本体在预览栏
    # 三入口并列卡 + PCB 排线连接层
    assert 'id="entryGrid"' in html
    assert 'class="entry-card entry-tab selected active" data-entry-tab="nl"' in html
    assert 'id="pcb-stage"' in html and "lab-theme.css" in html and "lab-ui.js" in html
    # 流水线三步（校验 → 冒烟 → 全量），冒烟文案为用户本轮批准口径
    assert "校验 / 编译策略代码" in html
    assert "冒烟测试：随机 1 只股票 × 短期区间（自动）" in html
    assert "完整回测（全量标的 × 选定区间）" in html
    # 策略 ID 公共项在参数区第一行；日历选择器替换日期输入
    assert 'id="param-sname"' in html
    assert html.index('id="param-sname"') < html.index('回测区间 <span class="req">')
    assert 'id="cal-pop"' in html and "attachCalendar" in html
    assert "startBacktest" in html  # 旧函数保留兼容（流水线复用 saveToSandbox/waitForCheck）
    # 可见文案去术语（沙箱/晋升不出现；「冒烟」按 QRE-LAB-UI-LANDING 用户批准文案放行）
    import re as _re
    visible = _re.sub(r"<!--.*?-->", "", html, flags=_re.S)
    visible = _re.sub(r"<script>.*?</script>", "", visible, flags=_re.S)
    for word in ("沙箱", "晋升"):
        assert word not in visible, word
    # 回测参数：必选仅回测区间与标的范围；其余收进折叠的高级参数
    assert '回测区间 <span class="req">*</span>' in html
    assert '标的范围 <span class="req">*</span>' in html
    assert 'id="scope-all"' in html and 'name="param-scope"' in html  # QRE-SAAS-012：标的范围改单选
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
    # 取反按 18080 定稿从向导移除（引擎 ast.Not 能力保留，仅向导 UI 不再暴露）
    assert "wz-not" not in html and "取反" not in html
    # 预检开关移除（冒烟固定后台自动）；最大持仓天数迁移到通用高级参数
    assert 'id="param-precheck"' not in html
    assert 'id="param-holding"' in html and "最大持仓天数" in html
    assert "precheck: false" in html  # ③步全真全量（预检截断已由冒烟承担）


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
                "/api/lab/runs/<run_id>/delete",          # QRE-GUI-CONSOL-040
                "/api/lab/factor-requests",             # QRE-SAAS-011（缺因子申请，JSONL）
                "/api/lab/universes",                     # QRE-SAAS-012（标的范围归类）
                "/api/lab/universes/members",
                "/lab/runs/<run_id>/symbols"}               # QRE-LAB-UI-LANDING（个股明细列表）
    assert lab_rules - lab_only <= full_rules
    assert lab_only & full_rules == set()  # 8080 不挂新路由
    # 主控制台专有规律犹在（因子创建/补周期 API 自 QRE-GUI-CONSOL-039 起两应用共享）
    for rule in ("/admin", "/api/admin/overview",
                 "/api/builder/compile", "/api/admin/market-risk", "/compare"):
        assert rule in full_rules
        assert rule not in lab_rules


def test_lab_factor_requests_api(lab_client, monkeypatch, tmp_path):
    """QRE-SAAS-011：缺因子申请落 JSONL（不连库、不写因子表）。"""
    import json

    from quant_research_engine.gui import lab as lab_mod

    target = tmp_path / "factor_requests.jsonl"
    monkeypatch.setattr(lab_mod, "FACTOR_REQUESTS_PATH", target)
    resp = lab_client.post("/api/lab/factor-requests",
                           json={"factors": ["rsi_99", " foo_1 ", "rsi_99"], "strategy_name": "s1"})
    assert resp.status_code == 200 and resp.get_json()["ok"]
    record = json.loads(target.read_text(encoding="utf-8").strip())
    assert record["factors"] == ["foo_1", "rsi_99"]  # 去重 + 排序
    assert record["strategy_name"] == "s1"
    assert lab_client.post("/api/lab/factor-requests", json={"factors": []}).status_code == 400


# --- QRE-SAAS-012：标的范围富化（板块/概念归类） ---

_FAKE_GROUPS = {
    "ok": True,
    "groups": [
        {"group": "sw1", "label": "申万一级行业", "items": [{"key": "电子", "count": 618}]},
        {"group": "ths", "label": "同花顺概念", "items": [{"key": "华为概念", "count": 770}]},
    ],
}


def test_lab_universes_api(lab_client, monkeypatch):
    monkeypatch.setattr("quant_research_engine.gui.universe.list_universes",
                        lambda db_url=None: _FAKE_GROUPS)
    monkeypatch.setattr("quant_research_engine.gui.universe.universe_members",
                        lambda group, key, db_url=None: ["000001.SZ", "600000.SH"])
    # 路由在 create_lab_app 里 from-import，需重建 app 让补丁生效
    from quant_research_engine.gui.lab import create_lab_app

    client = create_lab_app().test_client()
    resp = client.get("/api/lab/universes")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] and data["groups"][0]["items"][0]["count"] == 618
    resp = client.get("/api/lab/universes/members?group=sw1&key=电子")
    assert resp.get_json()["codes"] == ["000001.SZ", "600000.SH"]


def test_lab_universes_unknown_group_404(lab_client):
    from quant_research_engine.gui.lab import create_lab_app

    client = create_lab_app().test_client()
    resp = client.get("/api/lab/universes/members?group=bogus&key=x")
    assert resp.status_code == 404


def test_lab_scope_controls_present(lab_client):
    html = lab_client.get("/").data.decode("utf-8")
    assert 'id="scope-all"' in html and 'id="scope-group"' in html and 'id="scope-codes"' in html
    assert 'id="univ-group"' in html and 'id="univ-key-list"' in html
    assert "resolveScopeCodes" in html and "/api/lab/universes/members" in html
    assert "范围较大" in html  # 大范围护栏文案
    assert "param-all-market" not in html  # 旧 checkbox 已移除


def test_universe_members_sql_mapping(monkeypatch):
    """universe_members 的组→SQL 映射（fake engine，不依赖真实库）。"""
    from quant_research_engine.gui import universe as u

    queries = []

    class FakeConn:
        def execute(self, stmt, params=None):
            queries.append((str(stmt), params))
            return self

        def fetchall(self):
            return [("000001.SZ",), ("600000.SH",)]

        def __enter__(self): return self
        def __exit__(self, *a): return False

    class FakeEngine:
        def connect(self): return FakeConn()

    monkeypatch.setattr(u, "_engine", lambda db_url=None: FakeEngine())
    codes = u.universe_members("sw1", "电子")
    assert codes == ["000001.SZ", "600000.SH"]
    stmt, params = queries[0]
    assert "申万L1:" in params["tag"] and params["tag"] == "申万L1:电子"
    assert params["layer"] == "A"

    codes = u.universe_members("industry", "半导体")
    stmt, params = queries[-1]
    assert "reference.stock_basic" in stmt

    import pytest
    with pytest.raises(KeyError):
        u.universe_members("bogus", "x")
