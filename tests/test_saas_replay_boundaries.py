"""QRE-SAAS-REPLAY-BOUNDARIES：重播边界核验（同日聚合 / orders 事件源 / 多因子布局）。

策略：先用测试证明现有路径，只修真实缺口。全部 Node harness + 纯逻辑 stub，
不触外网、不跑真实回测：
1. replay.js（真实静态文件，vm 加载）：同日同类 >5 混合入场/出场、聚合计数口径
   （去重标的「只」+ 事件「笔」）、展开/收起、seek 回退（无未来事件/重复行）、
   重播重置、destroy→attach 重入、markPoints 无未来事件、末帧指标一致。
2. factor-layout.js（真实静态文件）：0/1/N 因子、均线 overlay、MACD 同面板、
   KDJ 家族、chip 三态与 hidden。
3. symbol.html mountKlineReplay（模板抽取 + 真实 factor-layout + QREReplay 桩）：
   orders 真实价量优先、缺字段不造值、空 orders 才 round trips 兜底、sym 字段。
4. job.html mountReplay（模板抽取）：事件带 sym 与 round trips 价量（有则用、
   无则不造）。
5. lab_result._trade_points：round_trips.csv 有价量列时补足（仅新 run 生效），
   无则不加键（不造值）。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
REPLAY_JS = (REPO / "src/quant_research_engine/gui/static/replay.js").read_text(encoding="utf-8")
FACTOR_LAYOUT_JS = (REPO / "src/quant_research_engine/gui/static/factor-layout.js").read_text(encoding="utf-8")

from quant_research_engine.gui.saas import create_saas_app  # noqa: E402


def _psql(db: str, *args: str) -> None:
    subprocess.run(
        ["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def saas_db():
    db_name = f"qre_replay_bnd_{uuid.uuid4().hex[:12]}"
    _psql("postgres", "-c", f"CREATE DATABASE {db_name}")
    _psql(db_name, "-f", "deploy/saas/cloud_schema.sql")
    yield db_name
    _psql("postgres", "-c", f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")


@pytest.fixture()
def client(saas_db):
    app = create_saas_app()
    app.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
    app.config["SAAS_WORKER_TOKEN"] = "t"
    app.config["SAAS_DEV_AUTH"] = "1"
    app.config["SAAS_AUTH_CHANNEL"] = "stub"
    yield app.test_client()
    engine = app.extensions.get("saas_engine")
    if engine is not None:
        engine.dispose()


def _node(script: str) -> None:
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    result = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


# ---------------------------------------------------------------- replay.js
_REPLAY_HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
function el(){
  return {
    tagName: 'DIV', children: [], childNodes: [], style: {}, className: '', _text: '',
    _innerHTML: '', dataset: {}, listeners: {}, disabled: false, value: '', readOnly: false,
    parentNode: null,
    get innerHTML(){ return this._innerHTML; },
    set innerHTML(v){ this._innerHTML = String(v); if (v === ''){ this.children = []; this.childNodes = []; } },
    get textContent(){ return this._text; },
    set textContent(v){ this._text = String(v); },
    get firstChild(){ return this.childNodes[0] || null; },
    get nextSibling(){
      if (!this.parentNode) return null;
      const i = this.parentNode.childNodes.indexOf(this);
      return this.parentNode.childNodes[i + 1] || null;
    },
    classList: {add(){}, remove(){}, toggle(){}, contains(){ return false; }},
    appendChild(n){ n.parentNode = this; this.children.push(n); this.childNodes.push(n); return n; },
    insertBefore(n, ref){
      n.parentNode = this;
      let i = ref ? this.childNodes.indexOf(ref) : this.childNodes.length;
      if (i < 0) i = this.childNodes.length;
      this.childNodes.splice(i, 0, n); this.children.splice(i, 0, n);
      return n;
    },
    remove(){
      if (!this.parentNode) return;
      const i = this.parentNode.childNodes.indexOf(this);
      if (i >= 0){ this.parentNode.childNodes.splice(i, 1); this.parentNode.children.splice(i, 1); }
      this.parentNode = null;
    },
    addEventListener(type, fn){ (this.listeners[type] ||= []).push(fn); },
    setAttribute(name, value){ this['attr_' + name] = String(value); },
    querySelector(){ return null; },
  };
}
function createReplayHarness(){
  const elements = {};
  const document = {
    createElement(){ return el(); },
    getElementById(id){ return elements[id] || (elements[id] = el()); },
  };
  const setOptions = [];
  const echarts = {
    init(){ return { setOption(o){ setOptions.push(o); }, dispose(){}, resize(){} }; },
    getInstanceByDom(){ return null; },
  };
  const intervals = [];
  const context = vm.createContext({
    console, document, echarts,
    window: { addEventListener(){} },
    requestAnimationFrame(fn){ return fn(); },
    setTimeout(fn){ return 0; },
    clearTimeout(){},
    setInterval(fn){ intervals.push(fn); return intervals.length; },
    clearInterval(){},
  });
  return {
    context, elements, setOptions, intervals,
    el, document,
    mount(){ const m = el(); return m; },
  };
}
function dayRows(eventsEl){
  return eventsEl.children.filter(c => String(c.className || '').indexOf('rp-ev-day') >= 0);
}
function aggButtons(row){
  const out = [];
  (row.children || []).forEach(function (c) {
    if (String(c.className || '').indexOf('rp-ev-agg') >= 0) out.push(c);
  });
  return out;
}
function chips(row){
  const out = [];
  (row.children || []).forEach(function (c) {
    if (String(c.className || '').indexOf('rp-ev-chip') >= 0
        && String(c.className || '').indexOf('rp-ev-agg') < 0) out.push(c);
  });
  return out;
}
"""

# 数据：5 个交易日；第 2 日 6 笔入场（5 个去重标的，000001 两笔）+ 2 笔出场
_REPLAY_SCENARIO = r"""
const h = createReplayHarness();
const source = %SOURCE%;
vm.runInContext(source, h.context);
const QREReplay = h.context.window.QREReplay;
assert.ok(QREReplay && QREReplay.attach, 'replay.js 必须暴露 attach');

const dates = ['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05', '2024-01-08'];
const equity = [100, 101, 103, 102, 106];
const events = [
  {date: '2024-01-03', kind: 'entry', sym: '000001.SZ', symbol: '000001.SZ'},
  {date: '2024-01-03', kind: 'entry', sym: '000001.SZ', symbol: '000001.SZ'},
  {date: '2024-01-03', kind: 'entry', sym: '000002.SZ', symbol: '000002.SZ'},
  {date: '2024-01-03', kind: 'entry', sym: '000003.SZ', symbol: '000003.SZ'},
  {date: '2024-01-03', kind: 'entry', sym: '000004.SZ', symbol: '000004.SZ'},
  {date: '2024-01-03', kind: 'entry', sym: '000005.SZ', symbol: '000005.SZ'},
  {date: '2024-01-03', kind: 'exit', sym: '000002.SZ', symbol: '000002.SZ', pnl: 0.01},
  {date: '2024-01-03', kind: 'exit', sym: '000003.SZ', symbol: '000003.SZ', pnl: -0.02},
  {date: '2024-01-05', kind: 'entry', sym: '000001.SZ', symbol: '000001.SZ', qty: 100, price: 10.5},
];
const trips = [
  {symbol: '000001.SZ', entry_date: '2024-01-03', exit_date: '2024-01-05', net_return: 0.02, quantity: 100, entry_price: 10.0, exit_price: 10.4},
];
const mount = h.mount();
const eventsEl = h.el();
const metricsEl = h.el();
const ctl = QREReplay.attach(mount, {
  dates, events, roundTrips: trips,
  series: [{name: '策略', id: 's', data: equity, raw: equity, mark: true}],
  metricsEl, eventsEl,
});

// 1) 同日混合 >5：聚合头按去重标的计「只」并披露事件「笔」；出场 2 笔走个体 chip
ctl.seek(dates.length - 1);
let rows = dayRows(eventsEl);
assert.equal(rows.length, 2, '两个事件日各一行');
const dayRow = rows.find(r => r.children[0].textContent === '2024-01-03');
assert.ok(dayRow, '聚合日行存在');
const aggs = aggButtons(dayRow);
assert.equal(aggs.length, 1, '仅入场组超过 5 笔需要聚合');
assert.equal(aggs[0].textContent, '当日入场 5 只（6 笔） ▸', '聚合计数口径：去重标的 + 事件笔数');
assert.equal(chips(dayRow).length, 2, '出场 2 笔直接展示个体 chip');

// 2) 展开 / 收起
aggs[0].listeners.click[0]();
assert.equal(aggs[0].textContent, '当日入场 5 只（6 笔） ▾', '展开后箭头翻转');
const det = aggs[0].nextSibling;
assert.ok(det && String(det.className).indexOf('rp-ev-det') >= 0, '展开明细插入聚合按钮之后');
assert.equal(det.children.length, 6, '明细包含全部 6 笔事件（含同标的 2 笔）');
assert.ok(det.children.some(c => (c.textContent || '').indexOf('000001.SZ') >= 0), '明细含标的');
aggs[0].listeners.click[0]();
assert.equal(aggs[0].textContent, '当日入场 5 只（6 笔） ▸', '收起后箭头复位');
assert.ok(!aggs[0].nextSibling || String(aggs[0].nextSibling.className).indexOf('rp-ev-det') < 0, '收起后明细移除');

// 3) seek 回退：无未来事件、无重复行；回退后再前进不重复
ctl.seek(0);
rows = dayRows(eventsEl);
assert.equal(rows.length, 0, '回退到首个事件日之前：不得出现未来事件');
ctl.seek(1);
assert.equal(dayRows(eventsEl).length, 1, '前进到聚合日：一行');
ctl.seek(1);
ctl.seek(4);
rows = dayRows(eventsEl);
assert.equal(rows.length, 2, '重复 seek 同一日不产生重复行');
const texts = rows.map(r => r.children[0].textContent).sort().join(',');
assert.equal(texts, '2024-01-03,2024-01-05', '日期行集合正确');

// 4) 重播：到末尾后播放重置事件流并无重复
ctl.seek(dates.length - 1);
const before = dayRows(eventsEl).length;
ctl.play();
assert.equal(dayRows(eventsEl).length, 0, '重播重置清空事件流');
for (let i = 0; i < dates.length + 2; i += 1) h.intervals[0]();
ctl.pause();
assert.equal(ctl.getCursor(), dates.length - 1, '重播到末帧');
assert.equal(dayRows(eventsEl).length, before, '重播后事件行数一致（无重复）');

// 5) destroy → attach 重入（重复初始化不叠控制条）
ctl.destroy(true);
const ctl2 = QREReplay.attach(mount, {
  dates, events, roundTrips: trips,
  series: [{name: '策略', id: 's', data: equity, raw: equity, mark: true}],
  metricsEl, eventsEl,
});
assert.equal(mount.children.filter(c => String(c.className).indexOf('rp-bar') >= 0).length, 1, '重入不叠加控制条');
ctl2.seek(dates.length - 1);
assert.equal(dayRows(eventsEl).length, before, '重入后事件流正常');

// 6) markPoints 不含未来事件（截断渲染红线）
const last = h.setOptions[h.setOptions.length - 1];
const marked = (last.series || []).filter(s => s.markPoint);
assert.ok(marked.length >= 1, 'mark 系列存在');
marked.forEach(function (s) {
  (s.markPoint.data || []).forEach(function (p) {
    assert.ok(dates.indexOf(p.coord[0]) >= 0 && dates.indexOf(p.coord[0]) <= ctl2.getCursor(),
      'markPoint 不得包含未来事件: ' + p.coord[0]);
  });
});

// 7) 末帧指标一致：累计收益 = 末值/首值 - 1
const m = ctl2.metrics();
assert.ok(Math.abs(m.totalRet - (106 / 100 - 1)) < 1e-12, '末帧累计收益与静态口径一致');
assert.equal(m.positions, 0, '末帧该回合已平仓：当前持仓 0');
assert.equal(m.closedTrips, 1, '已平仓笔数');
ctl2.seek(2);
assert.equal(ctl2.metrics().positions, 1, '帧内持仓期：当前持仓 1 只');

// 8) 空仓快进跳到下一个事件/持仓变化日
ctl2.seek(0);
ctl2.skipFlat();
assert.ok(ctl2.getCursor() > 0, '空仓快进而非常驻当前帧');
console.log('replay-boundaries-ok');
"""


class TestReplayCoreBoundaries:
    def test_same_day_aggregation_expand_seek_replay(self):
        _node(_REPLAY_HARNESS
               + _REPLAY_SCENARIO.replace("%SOURCE%", json.dumps(REPLAY_JS)))


# ---------------------------------------------------------------- factor-layout.js
_FACTOR_SCENARIO = r"""
const h = createReplayHarness();
vm.runInContext(%FACTOR%, h.context);
const plan = h.context.window.QREFactorLayout.plan;

// 0 因子：无面板无 overlay
let p = plan([], {});
assert.equal(p.paneCount, 0);
assert.equal(p.overlays.length, 0);
assert.equal(p.chips.length, 0);

// 1 均线因子：overlay 上主图
p = plan([{name: 'EMA5', col: 'ema_5', values: [1, 2, 3]}], {});
assert.equal(p.overlays.length, 1, '均线类默认 overlay');
assert.equal(p.paneCount, 0);
assert.equal(JSON.stringify(p.chips[0].states), JSON.stringify(['overlay', 'pane', 'hidden']), 'overlay chip 三态');

// MACD 三元组同面板（DIF+DEA+HIST）
p = plan([
  {name: 'DIF', col: 'macd_12_26_9', values: [1]},
  {name: 'DEA', col: 'macds_12_26_9', values: [1]},
  {name: 'HIST', col: 'macdh_12_26_9', values: [1]},
], {});
assert.equal(p.paneCount, 1, 'MACD 三元组合并单面板');
assert.equal(p.panes[0].series.length, 3, 'DIF/DEA/HIST 同面板');
assert.ok(p.panes[0].series.some(s => s.hist), 'HIST 为柱');
assert.equal(JSON.stringify(p.chips[0].states), JSON.stringify(['pane', 'hidden']), 'MACD chip 只循环 pane/hidden');

// KDJ 家族单面板多线
p = plan([
  {name: 'K', col: 'k_9_3', values: [1]},
  {name: 'D', col: 'd_9_3', values: [1]},
  {name: 'J', col: 'j_9_3', values: [1]},
], {});
assert.equal(p.paneCount, 1, 'KDJ 家族合并');
assert.equal(p.panes[0].series.length, 3);

// 混合：均线 overlay + MACD 面板 + 普通因子独立面板
p = plan([
  {name: 'EMA5', col: 'ema_5', values: [1]},
  {name: 'DIF', col: 'macd_12_26_9', values: [1]},
  {name: 'DEA', col: 'macds_12_26_9', values: [1]},
  {name: 'RSI', col: 'rsi_14', values: [1]},
], {});
assert.equal(p.overlays.length, 1);
assert.equal(p.paneCount, 2, 'MACD 面板 + RSI 独立面板');

// chip 状态：hidden 排除；overlay 可切 pane
p = plan([{name: 'EMA5', col: 'ema_5', values: [1]}], {ema_5: 'hidden'});
assert.equal(p.overlays.length, 0);
assert.equal(p.paneCount, 0);
p = plan([{name: 'EMA5', col: 'ema_5', values: [1]}], {ema_5: 'pane'});
assert.equal(p.overlays.length, 0);
assert.equal(p.paneCount, 1, 'overlay 切 pane 后进副图');
console.log('factor-layout-ok');
"""


class TestFactorLayoutPlan:
    def test_zero_one_many_factors_overlay_macd_chip(self):
        _node(_REPLAY_HARNESS + "\nconst source = "
               + json.dumps(FACTOR_LAYOUT_JS) + ";\n"
               + _FACTOR_SCENARIO.replace("%FACTOR%", "source"))


# ---------------------------------------------------------------- symbol.html 事件源
_SYMBOL_EVENT_SCENARIO = r"""
const h = createReplayHarness();
vm.runInContext(%FACTOR%, h.context);   // 真实 QREFactorLayout
const QREReplay = {
  attach(mountEl, opts){ h.attached = opts; return {destroy(){}}; },
};
h.attached = null;
const context = vm.createContext({
  console,
  document: { getElementById(id){ return h.document.getElementById(id); }, createElement(){ return h.el(); }, querySelector(){ return null; } },
  window: { addEventListener(){} },
  $ (selector){ return h.document.getElementById(String(selector).replace('#', '')); },
  QREReplay, QREFactorLayout: h.context.window.QREFactorLayout,
  card(label, value){ return label + ':' + value; },
  cls(){ return ''; },
  f2(v){ return v == null || v === '' ? '—' : Number(v).toFixed(2); },
  chipStates(){ return {}; },
  requestAnimationFrame(fn){ return fn(); },
});
const source = %SOURCE%;
vm.runInContext(source, context);

const dates = ['2024-01-02', '2024-01-03', '2024-01-04'];
const ohlc = [[10, 10.5, 9.9, 10.2], [10.2, 10.8, 10.1, 10.6], [10.6, 11, 10.5, 10.9]];
const detail = {
  kline: {dates, ohlc, vols: [100, 200, 300]},
  factors: [],
  trades: [{symbol: '000001.SZ', entry_date: '2024-01-02', exit_date: '2024-01-03', net_return: 0.02, quantity: 100, entry_price: 10.0, exit_price: 10.4}],
  summary: {ts_code: '000001.SZ'},
  orders: [
    {trade_date: '2024-01-02', side: 'buy', quantity: 100, price: 10.0},
    {trade_date: '2024-01-03', side: 'sell', quantity: 100, price: 10.4},
  ],
};
vm.runInContext('mountKlineReplay(' + JSON.stringify(detail) + ')', context);
let ev = h.attached.events;
assert.equal(ev.length, 2, 'orders 优先：2 笔订单事件');
assert.ok(ev.every(e => e.sym === '000001.SZ'), '事件带真实标的 sym');
assert.equal(ev[0].kind, 'entry');
assert.equal(ev[0].qty, 100);
assert.equal(ev[0].price, 10.0);
assert.equal(ev[0].symbol, '买', 'chip 首段为买卖方向（价量由组件拼装，见 replay 核心用例）');
assert.equal(ev[1].kind, 'exit');
assert.equal(ev[1].price, 10.4);

// 缺字段不造值：quantity/price 缺失时显示「—」，price 不下发假值
h.attached = null;
const detailMissing = JSON.parse(JSON.stringify(detail));
detailMissing.orders = [{trade_date: '2024-01-02', side: 'buy'}, {trade_date: '2024-01-04', side: 'sell', quantity: 50}];
vm.runInContext('mountKlineReplay(' + JSON.stringify(detailMissing) + ')', context);
ev = h.attached.events;
assert.equal(ev.length, 2);
assert.equal(ev[0].qty, undefined, '缺 quantity 不造值');
assert.equal(ev[0].price, undefined, '缺 price 不造值');
assert.equal(ev[0].symbol, '买', '缺 quantity/price 时 chip 只有方向（不造值、不显示假数）');
assert.equal(ev[1].qty, 50);

// 空 orders 才 round trips 兜底
h.attached = null;
const detailNoOrders = JSON.parse(JSON.stringify(detail));
detailNoOrders.orders = [];
vm.runInContext('mountKlineReplay(' + JSON.stringify(detailNoOrders) + ')', context);
ev = h.attached.events;
assert.equal(ev.length, 2, '空 orders 走 round trips 兜底（entry+exit）');
assert.equal(ev[0].kind, 'entry');
assert.equal(ev[0].price, 10.0, '兜底用 round trips 真实 entry_price');
assert.equal(ev[1].kind, 'exit');
assert.equal(ev[1].price, 10.4, '兜底用 round trips 真实 exit_price');
assert.equal(ev[1].pnl, 0.02, '兜底带净收益率');

// 多因子布局：0/1/N 与动态高度（接管原容器，不新建 K 线模块）
h.attached = null;
vm.runInContext('mountKlineReplay(' + JSON.stringify(detail) + ')', context);
assert.equal(h.attached.chartEl, h.document.getElementById('chart-kline'), '重播接管原 K 线容器');
assert.equal(h.attached.series.filter(s => s.grid === 0 && s.mark).length, 1, 'K 线主图唯一（无第二套）');
const gridCount = h.attached.grids.length;
h.attached = null;
const detailFactors = JSON.parse(JSON.stringify(detail));
detailFactors.factors = [
  {name: 'EMA5', col: 'ema_5', values: [1, 2, 3]},
  {name: 'DIF', col: 'macd_12_26_9', values: [1, 2, 3]},
  {name: 'DEA', col: 'macds_12_26_9', values: [1, 2, 3]},
  {name: 'HIST', col: 'macdh_12_26_9', values: [1, 2, 3]},
];
vm.runInContext('mountKlineReplay(' + JSON.stringify(detailFactors) + ')', context);
assert.equal(h.attached.grids.length, gridCount + 1, 'overlay 不增 grid；MACD 面板 +1');
assert.ok(h.attached.series.some(s => s.extra && s.extra.itemStyle), 'MACD 柱透传 extra（正红负绿 itemStyle）');
assert.equal(h.attached.series.filter(s => s.grid === 0).length, 2, 'overlay 上主图（K线+EMA，不增 grid）');
assert.ok(h.attached.series.filter(s => s.grid === 2).length === 3, 'MACD 三线落在因子面板 grid');
console.log('symbol-events-ok');
"""


def _extract(html: str, pattern: str, what: str) -> str:
    match = re.search(pattern, html, re.S)
    assert match, f"未找到 {what}"
    return match.group(1)


class TestSymbolReplayEventSource:
    def test_orders_priority_and_factor_layout(self, client):
        html = client.get("/saas/jobs/1/symbols/000001").get_data(as_text=True)
        source = _extract(html, r"(function mountKlineReplay\(d\)\{[\s\S]*?\n\})\nload\(\);", "mountKlineReplay")
        _node(_REPLAY_HARNESS
               + _SYMBOL_EVENT_SCENARIO.replace("%FACTOR%", json.dumps(FACTOR_LAYOUT_JS))
                                       .replace("%SOURCE%", json.dumps(source)))


# ---------------------------------------------------------------- job.html 事件源
_JOB_EVENT_SCENARIO = r"""
const h = createReplayHarness();
h.attached = null;
const context = vm.createContext({
  console,
  document: { getElementById(id){ return h.document.getElementById(id); }, createElement(){ return h.el(); } },
  window: { addEventListener(){} },
  QREReplay: { attach(mountEl, opts){ h.attached = opts; return {destroy(){}}; } },
  curBench: null,
  stratRet(){ return []; },
  toRet(){ return []; },
  requestAnimationFrame(fn){ return fn(); },
});
const source = %SOURCE%;
vm.runInContext(source, context);

const points = [
  {symbol: '000001.SZ', entry_date: '2024-01-02', exit_date: '2024-01-03', net_return: 0.02,
   quantity: 100, entry_price: 10.0, exit_price: 10.4},
  {symbol: '000002.SZ', entry_date: '2024-01-02', exit_date: '2024-01-04', net_return: -0.01},
];
vm.runInContext('mountReplay(' + JSON.stringify({
  dates: ['2024-01-02', '2024-01-03', '2024-01-04'],
  equity: [100, 102, 101], cumret: [0, 0.02, 0.01],
  trades: {points},
}) + ')', context);
const ev = h.attached.events;
assert.equal(ev.length, 4, 'entry+exit 各两笔');
assert.ok(ev.every(e => e.sym === e.symbol), 'job 事件带 sym（与 symbol 同源口径）');
const rich = ev.filter(e => e.qty != null);
assert.equal(rich.length, 2, 'round trips 有价量字段时补足到事件');
assert.equal(rich[0].qty, 100);
assert.equal(rich[0].price, 10.0);
assert.equal(rich[0].symbol, '000001.SZ', 'chip 首段为标的（价量由组件拼装）');
const poor = ev.filter(e => e.qty == null);
assert.equal(poor.length, 2, '旧数据（无价量字段）不造值');
assert.equal(poor[0].symbol, '000002.SZ', '无价量时退回纯标的文案');
console.log('job-events-ok');
"""


class TestJobReplayEventSource:
    def test_round_trip_price_quantity_enrichment(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        source = _extract(html, r"(function mountReplay\(d\)\{[\s\S]*?\n\})\n", "mountReplay")
        _node(_REPLAY_HARNESS
               + _JOB_EVENT_SCENARIO.replace("%SOURCE%", json.dumps(source)))


# ---------------------------------------------------------------- _trade_points  enrichment
class TestTradePointsPriceFields:
    def _record(self, td: str, columns: list[str], rows: list[list]) -> dict:
        import csv

        path = Path(td) / "round_trips.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(rows)
        return {"artifacts": {"round_trips.csv": str(path)}}

    def test_price_fields_included_when_present(self, tmp_path):
        from quant_research_engine.gui.lab_result import _trade_points

        record = self._record(str(tmp_path),
                              ["symbol", "entry_date", "exit_date", "net_return",
                               "quantity", "entry_price", "exit_price"],
                              [["000001.SZ", "2024-01-02", "2024-01-03", "0.02", "100", "10.123", "10.4"]])
        result = _trade_points(record)
        point = result["points"][0]
        assert point["quantity"] == 100
        assert point["entry_price"] == 10.123
        assert point["exit_price"] == 10.4

    def test_no_price_keys_when_absent(self, tmp_path):
        from quant_research_engine.gui.lab_result import _trade_points

        record = self._record(str(tmp_path),
                              ["symbol", "entry_date", "exit_date", "net_return"],
                              [["000001.SZ", "2024-01-02", "2024-01-03", "0.02"]])
        result = _trade_points(record)
        point = result["points"][0]
        for key in ("quantity", "entry_price", "exit_price"):
            assert key not in point, f"缺列不得造值: {key}"

    def test_partial_price_fields(self, tmp_path):
        from quant_research_engine.gui.lab_result import _trade_points

        record = self._record(str(tmp_path),
                              ["symbol", "entry_date", "exit_date", "net_return", "quantity"],
                              [["000001.SZ", "2024-01-02", "2024-01-03", "0.02", "100"]])
        result = _trade_points(record)
        point = result["points"][0]
        assert point["quantity"] == 100
        assert "entry_price" not in point and "exit_price" not in point
