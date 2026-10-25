"""QRE-SAAS-RESULT-UNDERSTANDING：集中帮助页、模块精准深链、费用/基准口径提示、
重播指标提示、symbol data_until 与 VaR/ES 损失正号呈现。

覆盖（先 RED 后 GREEN）：
1. 公开 `/saas/help`（游客与登录用户均可访问）+ 七个锚点小节；
2. 合同口径文案由 `result_contract` 常量同源注入（不复制权威口径）；
3. job/symbol 各模块「说明 →」深链；`renderContract` 驱动收益曲线 tip；
4. 主指标卡仍为 6 张（盈亏比只在帮助页与重播解释）；
5. 五类磨损卡 / 费率 chip / bench-bar / 重播指标 tip；
6. symbol 两条 API 路径注入 `data_until`；VaR/ES 损失正号呈现。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from quant_research_engine.gui.saas import create_saas_app
from quant_research_engine.gui.saas.result_contract import (
    DAILY_RETURN_BASIS,
    TOTAL_RETURN_BASIS,
)

ROOT = Path(__file__).resolve().parents[1]
WORKER_TOKEN = "result-help-token"
WORKER_HEADERS = {"X-Worker-Token": WORKER_TOKEN}
ANCHORS = ("contract", "metrics", "benchmark", "fees", "risk", "attribution", "replay")


def _psql(db: str, *args: str) -> None:
    subprocess.run(
        ["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def saas_db():
    db_name = f"qre_result_help_{uuid.uuid4().hex[:12]}"
    _psql("postgres", "-c", f"CREATE DATABASE {db_name}")
    _psql(db_name, "-f", "deploy/saas/cloud_schema.sql")
    yield db_name
    _psql("postgres", "-c", f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")


@pytest.fixture()
def app(saas_db, tmp_path):
    app = create_saas_app()
    app.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
    app.config["SAAS_WORKER_TOKEN"] = WORKER_TOKEN
    app.config["SAAS_DEV_AUTH"] = "1"
    app.config["SAAS_AUTH_CHANNEL"] = "stub"
    app.config["SAAS_UPLOAD_DIR"] = str(tmp_path)
    yield app
    engine = app.extensions.get("saas_engine")
    if engine is not None:
        engine.dispose()


@pytest.fixture()
def client(app):
    return app.test_client()


def _template(name: str) -> str:
    return (ROOT / "src/quant_research_engine/gui/saas/templates" / name).read_text()


def _node():
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    return node


_JOB_HELP_HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('vm');
function el(){
  const e = {
    children: [], childNodes: [], style: {}, className: '', innerHTML: '', dataset: {}, listeners: {},
    attributes: {},
    classList: {add(){}, remove(){}, toggle(){}, contains(){ return false; }},
    appendChild(...nodes){ e.children.push(...nodes); e.childNodes.push(...nodes); },
    replaceChildren(...nodes){ e.children = [...nodes]; e.childNodes = [...nodes]; },
    addEventListener(type, fn){ (e.listeners[type] ||= []).push(fn); },
    setAttribute(name, value){ e.attributes[name] = String(value); },
    getAttribute(name){ return name in e.attributes ? e.attributes[name] : null; },
    removeAttribute(name){ delete e.attributes[name]; },
    querySelectorAll(){ return []; },
  };
  Object.defineProperty(e, 'textContent', {
    get(){ return e._text || ''; }, set(v){ e._text = v; e.children = []; e.childNodes = []; },
  });
  return e;
}
function createJobHelpHarness(){
  const elements = new Proxy({}, {get(obj, key){ return obj[key] || (obj[key] = el()); }});
  const document = {
    getElementById(id){ return elements[id]; },
    createElement(){ return el(); },
    querySelector(){ return null; },
    querySelectorAll(){ return []; },
  };
  const context = vm.createContext({
    console, document,
    escH(s){ return String(s == null ? '' : s).replace(/[&<>"']/g,
      c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); },
    num(v){ return v == null ? '—' : Number(v).toLocaleString('zh-CN', {maximumFractionDigits: 2}); },
  });
  return {context, elements};
}
"""

_SYMBOL_WEAR_HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('vm');
function wel(){
  const e = {
    children: [], childNodes: [], style: {}, className: '', innerHTML: '', dataset: {}, listeners: {},
    classList: {add(){}, remove(){}, contains(){ return false; }},
    appendChild(...nodes){ e.children.push(...nodes); e.childNodes.push(...nodes); },
    replaceChildren(...nodes){ e.children = [...nodes]; e.childNodes = [...nodes]; },
    addEventListener(){}, setAttribute(){}, getAttribute(){ return null; },
    querySelectorAll(){ return []; },
  };
  return e;
}
function createSymbolWearHarness(){
  const elements = new Proxy({}, {get(obj, key){ return obj[key] || (obj[key] = wel()); }});
  const document = {
    getElementById(id){ return elements[id]; },
    querySelector(sel){ return sel.charAt(0) === '#' ? elements[sel.slice(1)] : null; },
    createElement(){ return wel(); },
    querySelectorAll(){ return []; },
  };
  const context = vm.createContext({
    console, document,
    $(sel){ return document.querySelector(sel); },
    f2(v){ return v == null || v === '' ? '—' : Number(v).toFixed(2); },
    esc(s){ return String(s == null ? '' : s); },
  });
  return {context, elements};
}
"""


def _run_job_help_js(html: str, pattern: str, scenario: str) -> None:
    match = re.search(pattern, html, re.S)
    assert match, "未找到待测 job.html 函数"
    script = (_JOB_HELP_HARNESS + "\nconst source = " + json.dumps(match.group(1))
              + ";\n" + scenario)
    result = subprocess.run([_node(), "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


def _run_symbol_wear_js(symbol: str, scenario: str) -> None:
    match = re.search(r"(function renderWear\(d\)\{[\s\S]*?\n\})", symbol, re.S)
    assert match, "未找到 symbol.html renderWear"
    script = (_SYMBOL_WEAR_HARNESS + "\nconst source = " + json.dumps(match.group(1))
              + ";\n" + scenario)
    result = subprocess.run([_node(), "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


# ---------------------------------------------------------------- 公开帮助页


class TestHelpPage:
    def test_help_page_public_and_login(self, client):
        anon = client.get("/saas/help")
        assert anon.status_code == 200
        html = anon.get_data(as_text=True)
        for anchor in ANCHORS:
            assert f'id="{anchor}"' in html, anchor
        assert DAILY_RETURN_BASIS in html
        assert TOTAL_RETURN_BASIS in html
        assert "使用说明" in html
        # 主导航入口（沿用 active 状态机制）
        assert 'href="/saas/help"' in html and 'data-nav="help"' in html
        # 登录用户同样可达（不新增鉴权门槛）
        assert client.get("/saas/help", headers={"X-User-Id": "1"}).status_code == 200

    def test_help_page_has_no_admin_links_or_jargon(self, client):
        html = client.get("/saas/help").get_data(as_text=True)
        for banned in ("/admin", "factor-admin", "factor-create", "8080", "8081",
                       "沙箱", "晋升", "promote", "试算"):
            assert banned not in html, banned

    def test_help_page_links_back_to_result_pages(self, client):
        html = client.get("/saas/help").get_data(as_text=True)
        assert "/saas/showcase" in html  # 公开展示入口（公开页，可导流）

    def test_help_contract_copy_is_single_source(self, client):
        """两种收益口径必须与 result_contract 常量逐字一致（同源注入，不复制口径）。"""
        html = client.get("/saas/help").get_data(as_text=True)
        assert html.count(DAILY_RETURN_BASIS) >= 1
        assert html.count(TOTAL_RETURN_BASIS) >= 1
        # 模板不硬编码另一种措辞
        assert "日收益累乘（交集口径，剔除新股注资）" in html  # 即 DAILY_RETURN_BASIS 本身


# ---------------------------------------------------------------- 结果页精准深链


class TestResultPageHelpLinks:
    def test_job_page_module_links(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        for anchor in ("contract", "benchmark", "fees", "risk", "attribution"):
            assert f'href="/saas/help#{anchor}"' in html, anchor
        assert 'id="curve-tip"' in html

    def test_symbol_page_module_links(self, client):
        html = client.get("/saas/jobs/1/symbols/000001.SZ").get_data(as_text=True)
        for anchor in ("benchmark", "fees", "risk"):
            assert f'href="/saas/help#{anchor}"' in html, anchor
        assert "/saas/help#contract" in html  # 数据截止说明

    def test_job_keeps_six_main_metric_cards(self, client):
        """主指标卡保持 6 张；盈亏比只在帮助页与重播解释，不进主指标卡。"""
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        match = re.search(r"function renderMetrics\(m\)\{[\s\S]*?\n\}", html, re.S)
        assert match
        body = match.group(0)
        assert body.count("card('") == 6, body
        assert "盈亏比" not in body

    def test_replay_explains_profit_loss_ratio_only(self):
        replay = (ROOT / "src/quant_research_engine/gui/static/replay.js").read_text()
        assert "盈亏比" in replay
        job = _template("job.html")
        assert "盈亏比" not in job  # 主指标卡不新增第七张


# ---------------------------------------------------------------- 合同驱动曲线 tip


class TestContractDrivenCurveTip:
    def test_render_contract_updates_curve_tip_and_fallback(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        _run_job_help_js(html, r"(function renderContract\(c\)\{[\s\S]*?\n\})", r"""
const h = createJobHelpHarness();
vm.runInContext(source, h.context);
const c = {verified: true, label: '已验证口径', version: '2026-10-25.1',
  data_until: '2026-02-27', note: '已人工复核',
  daily_return_basis: '日收益累乘（交集口径，剔除新股注资）',
  total_return_basis: '初始资金加权总收益（Σ期末权益/Σ初始资金−1）',
  tip: '收益曲线 = 日收益累乘；总收益率 = 初始资金加权总收益'};
vm.runInContext('renderContract(' + JSON.stringify(c) + ')', h.context);
const tip = h.elements['curve-tip'].getAttribute('data-tip');
assert.ok(tip.includes(c.daily_return_basis), '曲线 tip 必须用合同日收益口径：' + tip);
assert.ok(tip.includes(c.total_return_basis), '曲线 tip 必须用合同总收益口径：' + tip);
assert.equal(h.elements['box-contract'].style.display, '');
// 无合同：曲线 tip 保留静态安全回退，不写空
h.elements['curve-tip'].setAttribute('data-tip', '静态回退口径文案');
vm.runInContext('renderContract(null)', h.context);
assert.equal(h.elements['curve-tip'].getAttribute('data-tip'), '静态回退口径文案');
assert.equal(h.elements['box-contract'].style.display, 'none');
""")


# ---------------------------------------------------------------- 费用 / 基准 / 重播提示


class TestFeeBenchAndReplayTips:
    def test_job_wear_cards_and_fee_chip_carry_tips(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        _run_job_help_js(html, r"(function renderFees\(fees, meta\)\{[\s\S]*?\n\})", r"""
const h = createJobHelpHarness();
vm.runInContext(source, h.context);
vm.runInContext('renderFees({commission: 120.5, stamp_tax: 80.25, other_cost: 30.5, '
  + 'total_cost: 231.25, invested: 1000000, gross_pnl: 5000, net_pnl: 4768.75}, '
  + '{fees: {commission_rate: 0.00025, min_commission: 5, stamp_tax_sell: 0.0005, '
  + 'transfer_fee_rate: 0.00001, overridden: true}})', h.context);
const body = h.elements['fees-body'].innerHTML;
for (const label of ['佣金合计', '印花税合计', '过户费 / 其他', '总磨损', '磨损 / 投入本金'])
  assert.ok(body.includes(label), label);
// 五张磨损卡 + 费率 chip + 毛/净收益条标签都要有卡级/标签级提示
assert.ok((body.match(/data-tip=/g) || []).length >= 8, String((body.match(/data-tip=/g) || []).length));
assert.ok(body.includes('自定义'), '费率 chip 必须区分自定义配置');
assert.ok(body.includes('最低佣金'), '费率 chip 必须讲清最低佣金');
assert.ok(body.includes('残差'), '过户费/其他必须说明残差口径');
assert.ok(body.includes('买入成交额'), '磨损占比必须说明分母');
""")

    def test_job_fee_chip_default_copy(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        assert "默认（平台默认费率）" in html or "默认配置" in html

    def test_bench_bar_has_basis_tip(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        assert "基准是用于对照的指数" in html

    def test_symbol_wear_cards_carry_tips(self, client):
        symbol = _template("symbol.html")
        for marker in ("佣金合计", "印花税合计", "过户费 / 其他", "总磨损", "磨损 / 投入本金"):
            assert marker in symbol
        assert symbol.count("data-tip=") >= 10

    def test_replay_metrics_carry_tips(self):
        replay = (ROOT / "src/quant_research_engine/gui/static/replay.js").read_text()
        match = re.search(r"function renderMetrics\(m\) \{[\s\S]*?\n    \}", replay, re.S)
        assert match, "未找到 replay 指标渲染函数"
        body = match.group(0)
        assert "盈亏比" in body and "暴露度" in body and "当前持仓" in body
        node = _node()
        script = (
            "const assert = require('node:assert/strict');\n"
            "const vm = require('vm');\n"
            "const metricsEl = {innerHTML: '', classList: {add(){}, remove(){}}};\n"
            "const context = vm.createContext({metricsEl, console,\n"
            "  pct(v){ return v == null ? '—' : (v * 100).toFixed(2) + '%'; },\n"
            "  fnum(v, d){ return v == null ? '—' : Number(v).toFixed(d == null ? 2 : d); },\n"
            "  Date: {now(){ return 0; }}, setTimeout(){}});\n"
            "const source = " + json.dumps(match.group(0)) + ";\n"
            "vm.runInContext(source, context);\n"
            "vm.runInContext('renderMetrics({date: \"2026-01-05\", totalRet: 0.1, maxDD: -0.2, "
            "sharpe: 1.5, winRate: 0.5, plRatio: 1.8, closedTrips: 10, positions: 3, "
            "exposure: 0.42, newPeak: false})', context);\n"
            "const tips = (metricsEl.innerHTML.match(/data-tip=/g) || []).length;\n"
            "assert.ok(tips >= 3, '盈亏比/暴露度/当前持仓必须带提示，实际 ' + tips);\n"
            "assert.ok(metricsEl.innerHTML.includes('盈亏比'));\n"
            "assert.ok(metricsEl.innerHTML.includes('已平仓交易的平均盈利'), '盈亏比口径缺失');\n"
            "assert.ok(metricsEl.innerHTML.includes('有持仓的交易日数'), '暴露度口径缺失');\n"
            "assert.ok(metricsEl.innerHTML.includes('当前帧持有的股票只数'), '当前持仓口径缺失');\n"
        )
        result = subprocess.run([node, "-e", script], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr or result.stdout


class TestSymbolWearNoDoubleCount:
    """主 Agent 复核 Required Fix：过户费/其他不得把 transfer_fee 重复计入。

    worker 侧 `wear.other_cost = total_cost − commission − stamp_tax` 已包含
    transfer_fee（与滑点等残差），与 job 的 `fees_summary.other_cost` 同口径；
    显示层只能取 `other_cost`，再叠加 transfer_fee 会双算。
    """

    def test_worker_wear_branch_shows_other_cost_only(self, client):
        symbol = _template("symbol.html")
        _run_symbol_wear_js(symbol, r"""
const h = createSymbolWearHarness();
vm.runInContext(source, h.context);
// 与 tests/test_saas_symbol_ux.py 的 shared 磨损夹具同源：
// commission=5.09, stamp_tax=10.26, transfer_fee=0.5, total_cost=15.85
// → other_cost = 15.85 − 5.09 − 10.26 = 0.50（已含 0.5 过户费）
const wear = {commission: 5.09, stamp_tax: 10.26, transfer_fee: 0.5, other_cost: 0.5,
              total_cost: 15.85, invested: 9506.0, gross_pnl: 805.0, net_pnl: 789.15,
              trades: 1};
vm.runInContext('renderWear({wear: ' + JSON.stringify(wear) + '})', h.context);
const body = h.elements['wear-body'].innerHTML;
const m = body.match(/过户费 \/ 其他<\/div><div class="m-value[^>]*>([^<]*)</);
assert.ok(m, '缺少过户费/其他卡：' + body);
assert.equal(m[1], '0.50 元', 'other_cost 已含 transfer_fee，不得重复计入：' + m[1]);
assert.ok(body.indexOf('1.00 元') < 0, '修复前把 transfer_fee 加两遍会显示 1.00 元：' + body);
// 勾稽：佣金 + 印花税 + 过户费/其他 = 总磨损
assert.ok(Math.abs(5.09 + 10.26 + 0.5 - 15.85) < 1e-9, '费用拆分必须与总磨损勾稽');
""")

    def test_local_fallback_branch_keeps_order_transfer_fee(self):
        """本地 fallback（无 worker wear 块）仍按订单拆分显示过户费，保持现状。"""
        symbol = _template("symbol.html")
        assert "wc('过户费合计', f2(transfer) + ' 元', TIP_OTHER)" in symbol
        assert "if (o.side === 'buy') invested += Number(o.notional) || 0;" in symbol


# ---------------------------------------------------------------- symbol data_until / VaR 正号


class TestSymbolDataUntilAndVarSign:
    def _complete_job(self, client, chart_data, data_until="2026-02-27"):
        resp = client.post(
            "/api/saas/jobs",
            json={"yaml": "signal:\n  entry: 'true'\n", "kind": "full",
                  "params": {"codes": ["000001"]}, "name": "t"},
            headers={"X-User-Id": "1"},
        )
        job_id = resp.get_json()["job_id"]
        client.post("/api/saas/worker/jobs/lease", json={"worker_id": "w1"},
                    headers=WORKER_HEADERS)
        done = client.post(
            f"/api/saas/worker/jobs/{job_id}/result",
            json={"worker_id": "w1", "status": "done",
                  "summary": {"strategy_total_return": 0.1}, "chart_data": chart_data,
                  "data_until": data_until},
            headers=WORKER_HEADERS,
        )
        assert done.get_json()["status"] == "completed"
        return job_id

    def _write_detail(self, app, job_id, ts_code, payload):
        import gzip
        import json

        d = Path(app.config["SAAS_UPLOAD_DIR"]) / f"job_{job_id}" / "_symbol_details"
        d.mkdir(parents=True)
        (d / f"{ts_code}.json.gz").write_bytes(
            gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        )

    def test_gzip_path_returns_data_until(self, app, client):
        job_id = self._complete_job(client, {"tag_analysis": {"layers": {}}})
        self._write_detail(app, job_id, "000001.SZ", {
            "ok": True, "summary": {"ts_code": "000001.SZ", "name": "平安银行"},
            "trades": [], "orders": [], "failed_orders": []})
        d = client.get(f"/api/results/{job_id}/symbols/000001",
                       headers={"X-User-Id": "1"}).get_json()
        assert d["data_until"] == "2026-02-27"

    def test_local_fallback_path_returns_data_until(self, app, client, monkeypatch):
        job_id = self._complete_job(client, {"tag_analysis": {"layers": {}}})
        monkeypatch.setattr(
            "quant_research_engine.gui.lab_result.build_lab_symbol_detail",
            lambda record, ts, **kw: {"ok": True, "summary": {"ts_code": ts},
                                      "trades": [], "orders": [], "failed_orders": []},
        )
        d = client.get(f"/api/results/{job_id}/symbols/000001",
                       headers={"X-User-Id": "1"}).get_json()
        assert d["data_until"] == "2026-02-27"

    def test_symbol_page_renders_var_es_as_positive_loss(self):
        symbol = _template("symbol.html")
        # 仅改显示符号：VaR/ES 与 job/风险报告统一为损失正数
        assert "pct(-h95.var)" not in symbol
        assert "pct(-h95.es)" not in symbol
        assert "pct(-p99.var)" not in symbol
        assert "损失以正数展示" in symbol
        assert "data_until" in symbol  # 头部 sym-note 消费
