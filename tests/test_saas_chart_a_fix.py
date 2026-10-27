"""QRE-TV-CHART-A-FIX：ECharts 增强路两个痛点修复的边界核验。

1. replay.js：`visibleWindow` 纯函数契约（首帧 / 中间 / 末尾 / size>n / 越界）；
   `renderFrame` 只渲染可见窗口（xAxis + series 同窗口），事件标记不越窗口、
   不泄露未来；指标仍走全量序列（口径不变）。
2. symbol.html：`renderKline` 的容器尺寸监听——有 ResizeObserver 时观察一次、
   回调用 getInstanceByDom 取当前实例（重播接管后作用于重播实例）、不重复 observe、
   不再退化成 window.resize；无 ResizeObserver 时保留 window.resize 兜底且只绑一次。

全部 Node harness + 纯逻辑 stub，不触外网、不跑真实回测。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
REPLAY_JS = (REPO / "src/quant_research_engine/gui/static/replay.js").read_text(encoding="utf-8")
SYMBOL_TPL = (REPO / "src/quant_research_engine/gui/saas/templates/symbol.html").read_text(encoding="utf-8")


def _node(script: str) -> None:
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    result = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


# ---------------------------------------------------------------- 通用 harness
_HARNESS = r"""
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
function createHarness(){
  const elements = {};
  const document = {
    createElement(){ return el(); },
    getElementById(id){ return elements[id] || (elements[id] = el()); },
  };
  const setOptions = [];
  const chart = { setOption(o){ setOptions.push(o); }, dispose(){}, resize(){} };
  const echarts = {
    init(){ return chart; },
    getInstanceByDom(){ return null; },
  };
  const windowListeners = {};
  const window = {
    addEventListener(type, fn){ (windowListeners[type] ||= []).push(fn); },
    removeEventListener(type, fn){
      const arr = windowListeners[type] || [];
      const i = arr.indexOf(fn);
      if (i >= 0) arr.splice(i, 1);
    },
  };
  const context = vm.createContext({
    console, document, echarts, window, chart,
    requestAnimationFrame(fn){ return fn(); },
    setTimeout(fn){ return 0; },
    clearTimeout(){},
    setInterval(fn){ return 0; },
    clearInterval(){},
  });
  return { context, elements, setOptions, chart, windowListeners, el, document, mount(){ return el(); } };
}
"""


# ---------------------------------------------------------------- visibleWindow
_VISIBLE_WINDOW_SCENARIO = r"""
const h = createHarness();
const source = %SOURCE%;
vm.runInContext(source, h.context);
const core = h.context.window.QREReplay.core;
assert.ok(typeof core.visibleWindow === 'function', 'core.visibleWindow 必须存在');
const vw = core.visibleWindow;
function eq(got, start, end, label){
  assert.equal(got.start, start, label + ' start');
  assert.equal(got.end, end, label + ' end');
}
// 首帧：窗口未满，从头到 cursor
eq(vw(0, 5, 240), 0, 1, '首帧');
// 中间：窗口未满
eq(vw(2, 5, 240), 0, 3, '中间未满');
// 末尾：窗口已满，起点右移
eq(vw(4, 5, 240), 0, 5, '末尾未满');
// 长序列：end = cursor + 1，start = end - size
eq(vw(300, 400, 240), 61, 301, '长序列中间');
eq(vw(399, 400, 240), 160, 400, '长序列末帧');
// 空序列
eq(vw(0, 0, 240), 0, 0, '空序列');
// cursor 越界：clamp 到 [0, n-1]
eq(vw(-3, 5, 240), 0, 1, '负 cursor');
eq(vw(99, 5, 240), 0, 5, '超大 cursor');
// size <= 0 视为全量
eq(vw(4, 5, 0), 0, 5, 'size=0 全量');
eq(vw(300, 400, -1), 0, 301, 'size<0 全量');
// size > n
eq(vw(300, 400, 1000), 0, 301, 'size>n');
// 默认 size = 240
eq(vw(300, 400), 61, 301, '默认 size');
console.log('visibleWindow-ok');
"""


class TestVisibleWindow:
    def test_contract(self):
        _node(_HARNESS + _VISIBLE_WINDOW_SCENARIO.replace("%SOURCE%", json.dumps(REPLAY_JS)))


# ---------------------------------------------------------------- 窗口渲染
_WINDOW_RENDER_SCENARIO = r"""
const h = createHarness();
const source = %SOURCE%;
vm.runInContext(source, h.context);
const QREReplay = h.context.window.QREReplay;
const N = 400;
const dates = [];
for (let i = 0; i < N; i += 1) dates.push('2024-' + String(Math.floor(i / 28) + 1).padStart(2, '0') + '-' + String(i % 28 + 1).padStart(2, '0'));
dates.sort();
// 去重保序（上面生成可能重复，用序号重造）
const real = [];
for (let i = 0; i < N; i += 1) real.push(new Date(Date.UTC(2020, 0, 1) + i * 86400000).toISOString().slice(0, 10));
const equity = real.map(function (_, i) { return 100 + i; });
const events = [
  {date: real[5], kind: 'entry', sym: 'A', symbol: 'A'},
  {date: real[199], kind: 'entry', sym: 'B', symbol: 'B'},
  {date: real[399], kind: 'exit', sym: 'B', symbol: 'B'},
];
const mount = h.mount();
const ctl = QREReplay.attach(mount, {
  dates: real, events,
  series: [{name: '策略', id: 's', data: equity, raw: equity, mark: true}],
  initialCursor: 250,
});
function last(){ return h.setOptions[h.setOptions.length - 1]; }
// 1) 默认窗口 240：末帧 xAxis / series 同窗口，且不含未来
let opt = last();
const xs = opt.xAxis[0].data;
assert.equal(xs.length, 240, '默认窗口 240 点');
assert.equal(xs[xs.length - 1], real[250], '窗口右端 = cursor');
assert.equal(xs[0], real[11], '窗口左端 = cursor + 1 - 240');
const s0 = opt.series[0].data;
assert.equal(s0.length, 240, 'series 数据与 xAxis 同窗口');
assert.equal(s0[0], equity[11], 'series 首个值对应窗口起点');
assert.equal(s0[s0.length - 1], equity[250], 'series 末值对应 cursor');
// 2) 事件标记：只落在窗口内，且不越 cursor
const marked = opt.series.filter(function (s) { return s.markPoint; });
assert.equal(marked.length, 1, 'mark 系列存在');
marked[0].markPoint.data.forEach(function (p) {
  const i = real.indexOf(p.coord[0]);
  assert.ok(i >= 11 && i <= 250, 'markPoint 必须在可见窗口内: ' + p.coord[0]);
});
assert.ok(marked[0].markPoint.data.some(function (p) { return p.value === '入' && p.coord[0] === real[199]; }), '窗口内事件保留');
// 3) 指标仍走全量：累计收益 = 末值 / 首值 - 1
const m = ctl.metrics();
assert.ok(Math.abs(m.totalRet - (equity[250] / equity[0] - 1)) < 1e-12, '指标口径为全量序列');
// 4) 后退：窗口随之缩短并回到起点，无未来
ctl.seek(10);
opt = last();
assert.equal(opt.xAxis[0].data.length, 11, '后退到未满窗口：长度 = cursor + 1');
assert.equal(opt.xAxis[0].data[opt.xAxis[0].data.length - 1], real[10], '后退后窗口右端 = cursor');
const back = opt.series.filter(function (s) { return s.markPoint; })[0];
back.markPoint.data.forEach(function (p) {
  assert.ok(real.indexOf(p.coord[0]) >= 0 && real.indexOf(p.coord[0]) <= 10, '后退不得残留未来标记');
});
// 5) windowSize 覆盖
const ctl2 = QREReplay.attach(h.mount(), {
  dates: real, events,
  series: [{name: '策略', id: 's', data: equity, raw: equity}],
  initialCursor: 250, windowSize: 60,
});
opt = last();
assert.equal(opt.xAxis[0].data.length, 60, 'windowSize 可覆盖默认窗口');
assert.equal(opt.xAxis[0].data[0], real[191], 'windowSize 生效后左端正确');
ctl2.destroy(false);
console.log('window-render-ok');
"""


class TestWindowRender:
    def test_windowed_frames(self):
        _node(_HARNESS + _WINDOW_RENDER_SCENARIO.replace("%SOURCE%", json.dumps(REPLAY_JS)))


# ---------------------------------------------------------------- resize 归属
_RESIZE_OWNERSHIP_SCENARIO = r"""
const h = createHarness();
const source = %SOURCE%;
vm.runInContext(source, h.context);
const QREReplay = h.context.window.QREReplay;
const dates = ['2024-01-02', '2024-01-03'];
const opts = { dates, series: [{name: 's', id: 's', data: [1, 2], raw: [1, 2]}] };
// 自建容器：组件自己绑 resize，destroy 时解绑
const a = QREReplay.attach(h.mount(), Object.assign({}, opts));
assert.equal((h.windowListeners.resize || []).length, 1, '自建容器时组件绑定 window.resize');
a.destroy(false);
assert.equal((h.windowListeners.resize || []).length, 0, 'destroy 移除 window.resize 监听');
// 接管模式：不绑（宿主页负责）
h.windowListeners.resize = [];
const chartEl = h.el();
h.context.echarts.getInstanceByDom = function () { return null; };
QREReplay.attach(h.mount(), Object.assign({}, opts, {chartEl}));
assert.equal((h.windowListeners.resize || []).length, 0, '接管模式不重复绑定 window.resize');
console.log('resize-ownership-ok');
"""


class TestResizeOwnership:
    def test_own_vs_handoff(self):
        _node(_HARNESS + _RESIZE_OWNERSHIP_SCENARIO.replace("%SOURCE%", json.dumps(REPLAY_JS)))


# ---------------------------------------------------------------- symbol.html
_RENDER_KLINE_STUBS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
function makeHarness(opts){
  const listeners = {};
  const wins = [];
  const dom = {};
  const chart = {
    disposed: false, resizes: 0,
    setOption(){}, getOption(){ return {}; },
    resize(){ this.resizes += 1; },
    dispose(){ this.disposed = true; },
    isDisposed(){ return this.disposed; },
  };
  const $ = function (sel) { return dom[sel] || (dom[sel] = { style: {}, dataset: {}, classList: {add(){}, remove(){}} }); };
  const echarts = {
    init(){ chart.disposed = false; return chart; },
    getInstanceByDom(el){ return chart.disposed ? null : chart; },
  };
  const ctx = {
    console, chart, $, echarts, dom,
    window: { addEventListener(type, fn){ (listeners[type] ||= []).push(fn); wins.push(type); } },
    QREFactorLayout: { plan(){ return { panes: [], overlays: [] }; }, COLORS: {} },
    chipStates(){ return {}; },
    renderFactorChips(){},
    f2(v){ return Number(v).toFixed(2); },
    document: { querySelector(){ return null; } },
    requestAnimationFrame(fn){ return fn(); },
  };
  if (opts.observer){
    ctx.ResizeObserver = class {
      constructor(cb){ this.cb = cb; this.observed = []; ctx.observerInstances.push(this); }
      observe(el){ this.observed.push(el); }
      disconnect(){}
    };
    ctx.observerInstances = [];
  }
  return { ctx: vm.createContext(ctx), listeners, wins, chart, dom };
}
"""

_RENDER_KLINE_OBSERVER_SCENARIO = r"""
const h = makeHarness({observer: true});
const source = %SOURCE%;
vm.runInContext(source, h.ctx);
const d = {
  kline: { dates: ['2024-01-02', '2024-01-03'], ohlc: [[1, 2, 3, 4], [1, 2, 3, 4]], vols: [10, 20] },
  factors: [],
};
vm.runInContext('renderKline(' + JSON.stringify(d) + ')', h.ctx);
assert.equal(h.ctx.observerInstances.length, 1, '有 ResizeObserver 时创建单个观察者');
const ob = h.ctx.observerInstances[0];
assert.equal(ob.observed.length, 1, '观察 #chart-kline 一次');
assert.equal(ob.observed[0], h.dom['#chart-kline'], '观察的容器是 #chart-kline');
assert.equal(h.wins.filter(function (t) { return t === 'resize'; }).length, 0, '有 ResizeObserver 时不绑 window.resize');

// 回调按当前实例 resize（此处为静态实例）
ob.cb();
assert.equal(h.chart.resizes, 1, '观察回调触发实例 resize');

// 重播接管：旧实例被销毁、新实例 init —— 回调必须打到新实例
h.chart.dispose();
h.ctx.echarts.init(null);  // 重播建新实例（同一 chart 桩模拟，disposed 复位）
ob.cb();
assert.equal(h.chart.resizes, 2, '重播接管后回调仍作用于当前实例');
assert.equal(h.ctx.echarts.getInstanceByDom(h.dom['#chart-kline']), h.chart, '取到的实例与容器一致');

// 二次 renderKline（chip 切换 / 退出重播重建）：不重复 observe、不新建观察者
vm.runInContext('renderKline(' + JSON.stringify(d) + ')', h.ctx);
assert.equal(h.ctx.observerInstances.length, 1, '二次渲染不新建观察者（去重）');
assert.equal(ob.observed.length, 1, '二次渲染不重复 observe');
assert.equal(h.wins.filter(function (t) { return t === 'resize'; }).length, 0, '仍不绑 window.resize');

// 已 dispose 的实例不 resize（不持有旧实例）
h.chart.dispose();
h.ctx.echarts.getInstanceByDom = function () { return null; };
const before = h.chart.resizes;
ob.cb();
assert.equal(h.chart.resizes, before, '无存活实例时回调不 resize');
console.log('observer-ok');
"""

_RENDER_KLINE_FALLBACK_SCENARIO = r"""
const h = makeHarness({observer: false});
const source = %SOURCE%;
vm.runInContext(source, h.ctx);
const d = {
  kline: { dates: ['2024-01-02', '2024-01-03'], ohlc: [[1, 2, 3, 4], [1, 2, 3, 4]], vols: [10, 20] },
  factors: [],
};
vm.runInContext('renderKline(' + JSON.stringify(d) + ')', h.ctx);
const resize = h.listeners.resize || [];
assert.equal(resize.length, 1, '无 ResizeObserver 时回退 window.resize');
resize[0]();
assert.equal(h.chart.resizes, 1, '兜底监听 resize 当前实例');

vm.runInContext('renderKline(' + JSON.stringify(d) + ')', h.ctx);
assert.equal((h.listeners.resize || []).length, 1, '二次渲染不重复绑定 window.resize');
console.log('fallback-ok');
"""


def _render_kline_source() -> str:
    match = re.search(
        r"(let klineResizeBound = false;[\s\S]*?\nfunction renderKline\(d\)\{[\s\S]*?\n\})",
        SYMBOL_TPL,
    )
    assert match, "未找到 renderKline 及其声明"
    return match.group(1)


class TestSymbolKlineResize:
    def test_resize_observer(self):
        _node(_RENDER_KLINE_STUBS
               + _RENDER_KLINE_OBSERVER_SCENARIO.replace("%SOURCE%", json.dumps(_render_kline_source())))

    def test_window_resize_fallback(self):
        _node(_RENDER_KLINE_STUBS
               + _RENDER_KLINE_FALLBACK_SCENARIO.replace("%SOURCE%", json.dumps(_render_kline_source())))