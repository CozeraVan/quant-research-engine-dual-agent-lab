"""QRE-TV-KLINE-REPLAY-LAYOUT：K 线重播 TV 化（CR-2026-10-27）。

覆盖五条验收面：
1. 重播图表与静态 TV 同构：主图/量/因子副图右侧标尺、底部时间轴、x 轴全联动、
   grid 右侧留白 56；不得回到左侧大边距。
2. 顶部信息区 `#kline-ohlc` 显示当前帧 OHLC/量/涨跌/可见因子值；缺失 `—`；无未来数据。
3. 控制语义与接管合同不变（chartEl + destroy(keepDom)，单一 K 线模块）。
4. 退出重播恢复静态 TV 视图（工具栏复原、静态全量数据回填）。
5. `replay.js` 最小增量：`yAxes[].position` 与 `opts.axisPointer` 透传；job.html
   默认路径（不传 position/axisPointer）逐字节等价，不得回归。

全部 Node harness + 真实 `replay.js` / 真实 `factor-layout.js` / 模板抽取，
不触外网、不跑回测。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SYMBOL_TPL = (
    REPO / "src/quant_research_engine/gui/saas/templates/symbol.html"
).read_text(encoding="utf-8")
FACTOR_LAYOUT_PATH = REPO / "src/quant_research_engine/gui/static/factor-layout.js"
REPLAY_PATH = REPO / "src/quant_research_engine/gui/static/replay.js"
REPLAY_JS = REPLAY_PATH.read_text(encoding="utf-8")
FACTOR_LAYOUT_JS = FACTOR_LAYOUT_PATH.read_text(encoding="utf-8")


def _node(script: str) -> None:
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    result = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


def _mount_body() -> str:
    match = re.search(r"function mountKlineReplay\(d\)\{[\s\S]*?\n\}", SYMBOL_TPL)
    assert match, "未找到 mountKlineReplay"
    return match.group(0)


def _init_kline_replay_body() -> str:
    match = re.search(r"function initKlineReplay\(d\)\{[\s\S]*?\n\}", SYMBOL_TPL)
    assert match, "未找到 initKlineReplay"
    return match.group(0)


def _symbol_source() -> str:
    """K 线静态 helper + renderKline + initKlineReplay + mountKlineReplay 全量抽取。

    `mountKlineReplay` 现在复用 `klineGridSpec/klineAxisLabelIndex/klineInfoHTML/klineSetInfo`，
    必须连同其定义一起注入 vm；这些函数体内的 DOM/echarts 只在调用时求值，定义阶段安全。
    """
    # 末段允许出现 load() 之前的其它语句（如 qre:themechange 监听），
    # 只要锚点是「klineResizeBound 起 → load() 前」即可。
    match = re.search(r"(let klineResizeBound = false;[\s\S]*?)\nload\(\);", SYMBOL_TPL)
    assert match, "未找到 K 线/重播源码块"
    # QRE-SAAS-KLINE-ENGINE-EXCLUSIVE：renderKline 依赖 klineDisposeEngines 清同一
    # 容器上的旧 ECharts 实例；该定义在 klineResizeBound 之前，必须一并注入 vm。
    # R3-4（TV_ROUND3 §5）：LWC 试点整体移除，这里是单引擎清理。
    dispose = re.search(
        r"(// QRE-SAAS-KLINE-ENGINE-EXCLUSIVE[\s\S]*?\nfunction klineDisposeEngines\(\)\{[\s\S]*?\n\})",
        SYMBOL_TPL,
    )
    assert dispose, "未找到 klineDisposeEngines"
    return dispose.group(1) + "\n" + match.group(1)


# ---------------------------------------------------------------- 源码合同
class TestSourceContract:

    def test_replay_reuses_static_layout_spec(self):
        body = _mount_body()
        # QRE-PRICE-SCALE（T2）：重播与静态图共用 klineGrids（右留白按价格轴标签
        # 宽度预算，≥56），不再各自写一份 grid 规格
        assert "klineGrids(panes.length)" in body, (
            "重播必须复用静态 grid 规格（klineGrids → klineGridSpec + 轴宽预算）"
        )
        assert "klineGridSpec(KLINE_TOOL_VIS.vol, paneCount, KLINE_TOOL_VIS.fct)" in SYMBOL_TPL, (
            "klineGrids 必须仍由 klineGridSpec 生成布局"
        )
        assert "klineAxisLabelIndex(panes.length, true, true)" in body, (
            "时间轴只挂最后一个可见格"
        )
        assert "left: 60" not in body and "right: 20" not in body, (
            "不得保留旧的左侧大边距 grid"
        )
        # QRE-KLINE-PANE-OPTION（T1）：因子副图 yAxes 改由 factor-layout.panesToOption
        # 生成（其 paneYAxes 对 replay 规格固定 position:'right'），模板内只剩主图/量两轴。
        assert body.count("position: 'right'") >= 2, "主图/量右侧标尺"
        assert "panesToOption(panes, {" in body and "paneBase: 2" in body, (
            "因子副图 yAxes 走共享出口（索引与 position 由 paneYAxes 生成）"
        )

    def test_replay_info_uses_static_info_bar(self):
        body = _mount_body()
        assert "klineSetInfo(klineInfoHTML(" in body, (
            "重播帧要写顶部信息区 #kline-ohlc（当前帧口径）"
        )
        assert "axisPointer" in body, "重播要开 x 轴全联动"

    def test_replay_js_minimal_passthrough(self):
        assert "y.position" in REPLAY_JS, "replay.js 需透传 yAxes[].position"
        assert "opts.axisPointer" in REPLAY_JS, "replay.js 需透传 axisPointer（可选）"


# ---------------------------------------------------------------- Node harness
_HARNESS = r"""
const fs = require('node:fs');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const FACTOR_LAYOUT_JS = fs.readFileSync(%FACTOR_LAYOUT_PATH%, 'utf8');
const REPLAY_JS = fs.readFileSync(%REPLAY_PATH%, 'utf8');

function makeEl(sel){
  const e = {
    sel: sel, style: {}, dataset: {}, disabled: false, attrs: {}, listeners: {},
    textContent: '', className: '', children: [], childNodes: [], parentNode: null,
    value: '', readOnly: false,
    classList: { add(){}, remove(){}, toggle(){}, contains(){ return false; } },
    setAttribute(k, v){ e.attrs[k] = String(v); },
    addEventListener(t, fn){ (e.listeners[t] = e.listeners[t] || []).push(fn); },
    click(){ (e.listeners.click || []).forEach(function (fn) { fn({}); }); },
    appendChild(n){
      n.parentNode = e; e.children.push(n); e.childNodes.push(n); return n;
    },
    insertBefore(n, ref){
      n.parentNode = e;
      let i = ref ? e.childNodes.indexOf(ref) : e.childNodes.length;
      if (i < 0) i = e.childNodes.length;
      e.childNodes.splice(i, 0, n); e.children.splice(i, 0, n); return n;
    },
    insertAdjacentHTML(){},
    remove(){
      if (!e.parentNode) return;
      const i = e.parentNode.childNodes.indexOf(e);
      if (i >= 0){ e.parentNode.childNodes.splice(i, 1); e.parentNode.children.splice(i, 1); }
      e.parentNode = null;
    },
    removeChild(n){
      const i = e.childNodes.indexOf(n);
      if (i >= 0){ e.childNodes.splice(i, 1); e.children.splice(i, 1); }
      return n;
    },
    querySelector(){ return null; },
    get firstChild(){ return e.childNodes[0] || null; },
    get nextSibling(){
      if (!e.parentNode) return null;
      const i = e.parentNode.childNodes.indexOf(e);
      return e.parentNode.childNodes[i + 1] || null;
    },
  };
  let html = '';
  Object.defineProperty(e, 'innerHTML', {
    get(){ return html; }, set(v){ html = String(v); }, configurable: true,
  });
  return e;
}

function makeChart(){
  return {
    disposed: false, options: [], actions: [], handlers: {},
    setOption(o){ this.options.push(o); },
    getOption(){ return this.options[this.options.length - 1] || {}; },
    on(ev, fn){ (this.handlers[ev] = this.handlers[ev] || []).push(fn); },
    dispatchAction(a){ this.actions.push(a); },
    resize(){},
    dispose(){ this.disposed = true; },
    isDisposed(){ return this.disposed; },
  };
}

function makeHarness(){
  const els = {}, charts = [];
  function get(id){ if (!els[id]) els[id] = makeEl('#' + id); return els[id]; }
  const document = {
    createElement(){ return makeEl('el'); },
    getElementById(id){ return get(id); },
    querySelector(sel){ return get(String(sel).replace(/^#/, '')); },
    // CR-2026-10-28 B 路：symbol.html 末尾注册 qre:themechange 监听（night-mode.js
    // 的 CustomEvent 不开 bubbles，必须监听 document）
    addEventListener(){}, removeEventListener(){},
  };
  const ctx = {
    console: console, document,
    window: { addEventListener(){} },
    requestAnimationFrame(fn){ return fn(); },
    setTimeout(fn){ return 0; },
    clearTimeout(){},
    setInterval(fn){ return 0; },
    clearInterval(){},
    echarts: {
      init(){ const c = makeChart(); charts.push(c); return c; },
      getInstanceByDom(){
        const live = charts.filter(function (c) { return !c.disposed; });
        return live.length ? live[live.length - 1] : null;
      },
    },
    QRETheme: { themeChart(){} },
    renderFactorChips(){},
    chipStates(){ return {}; },
      // QRE-KLINE-PARAM-GRID（T5）：与 symbol.html::klinePlanFactors 同签名；
      // harness 无参数选择，等价于原样返回。参数应用逻辑由
      // tests/test_kline_param_grid.py 覆盖。
      klinePlanFactors(d){ return (d && d.factors) || []; },
    f2(v){ return v == null || v === '' ? '—' : Number(v).toFixed(2); },
    card(label, value, cls){ return '<card data-cls="' + (cls || '') + '">' + label + ':' + value + '</card>'; },
    cls(){ return ''; },
  };
  ctx.$ = function (selector) { return document.getElementById(String(selector).replace(/^#/, '')); };
  const sandbox = vm.createContext(ctx);
  // replay.js / factor-layout.js 挂在 window 上，页面代码走裸全局名
  vm.runInContext(FACTOR_LAYOUT_JS, sandbox);
  vm.runInContext(REPLAY_JS, sandbox);
  vm.runInContext(
    'globalThis.QREFactorLayout = window.QREFactorLayout;' +
    'globalThis.QREReplay = window.QREReplay;',
    sandbox,
  );
  return { ctx: sandbox, els, charts, get };
}

const DETAIL = %DETAIL%;
"""

_DETAIL = {
    "kline": {
        "dates": ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09"],
        "ohlc": [
            [10.0, 10.5, 9.9, 10.6],
            [10.5, 10.8, 10.4, 10.9],
            [10.8, 11.0, 10.7, 11.1],
            [11.0, 10.9, 10.8, 11.2],
            [10.9, 11.2, 10.8, 11.3],
            [11.2, 11.3, 11.0, 11.5],
        ],
        "vols": [100000, 200000, 300000, 250000, 150000, 120000],
    },
    "factors": [
        {"name": "EMA5", "col": "ema_5", "values": [None, 10.4, 10.6, 10.8, 11.0, 11.2]},
        {"name": "DIF", "col": "macd_12_26_9", "values": [0.10, 0.12, 0.15, None, 0.20, 0.25]},
        {"name": "DEA", "col": "macds_12_26_9", "values": [0.08, 0.10, 0.12, 0.14, 0.17, 0.21]},
        {"name": "HIST", "col": "macdh_12_26_9", "values": [0.04, 0.04, 0.06, -0.02, 0.06, 0.08]},
    ],
    "trades": [
        {"symbol": "000001.SZ", "entry_date": "2024-01-03", "exit_date": "2024-01-05",
         "net_return": 0.02, "quantity": 100, "entry_price": 10.5, "exit_price": 11.0},
    ],
    "summary": {"ts_code": "000001.SZ"},
    "orders": [
        {"trade_date": "2024-01-03", "side": "buy", "quantity": 100, "price": 10.5},
        {"trade_date": "2024-01-05", "side": "sell", "quantity": 100, "price": 11.0},
    ],
}

_PAGE_SCENARIO = r"""
const h = makeHarness();
const source = %SOURCE%;
vm.runInContext(source + '\nglobalThis.__mountKlineReplay = mountKlineReplay;'
  + '\nglobalThis.__initKlineReplay = initKlineReplay;', h.ctx);
const ctl = vm.runInContext('__mountKlineReplay(' + JSON.stringify(DETAIL) + ')', h.ctx);
const chart = h.charts[h.charts.length - 1];
const opt = chart.options[chart.options.length - 1];

// 1) 布局与静态 TV 同构：三格全部右侧 56 留白、右侧标尺、时间轴只挂末格
assert.equal(opt.grid.length, 3, '主图 + 量 + MACD 面板');
assert.ok(opt.grid.every(g => g.right === 56), '每格右侧留白 56 给价格标尺');
assert.ok(opt.grid.every(g => g.left === 16), '不得回到左侧大边距');
assert.equal(opt.yAxis.length, 3);
assert.ok(opt.yAxis.every(y => y.position === 'right'), '主图/量/因子全部右侧标尺');
assert.equal(opt.yAxis[1].axisLabel.formatter(20000), '2万', '量轴万手格式');
assert.equal(opt.xAxis.filter(a => a.axisLabel.show).length, 1, '时间轴只挂一格');
assert.equal(opt.xAxis[2].axisLabel.show, true, '时间轴挂在最后可见格');
assert.ok(opt.xAxis.every(a => a.gridIndex !== undefined), 'x 轴逐格联动');
assert.equal(opt.axisPointer.link[0].xAxisIndex, 'all', 'x 轴全联动');

// 2) 信息区：初始为起播帧（近 2 年起播 → 首根），缺失值 `—`
const info0 = h.get('kline-ohlc').innerHTML;
assert.ok(info0.indexOf('2024-01-02') >= 0, '初始信息区为起播帧日期');
assert.ok(info0.indexOf('开 10.00') >= 0 && info0.indexOf('收 10.50') >= 0, '当前帧 OHLC');
assert.ok(info0.indexOf('量 10.00 万') >= 0, '当前帧成交量');
assert.ok(info0.indexOf('EMA5 —') >= 0, '缺失因子显示 —');
assert.ok(info0.indexOf('DIF 0.10') >= 0, '可见 pane 因子值');
assert.ok(info0.indexOf('涨跌 —') >= 0, '首根无前收盘 → 涨跌 —');
assert.ok(info0.indexOf('2024-01-03') < 0, '初始帧不得显示未来日期');
assert.ok(info0.indexOf('NaN') < 0 && info0.indexOf('undefined') < 0, '信息区不得出现 NaN/undefined');

// 3) 单步到第 3 帧：信息区随帧更新，仍无未来
ctl.seek(2);
const info2 = h.get('kline-ohlc').innerHTML;
assert.ok(info2.indexOf('2024-01-04') >= 0, '单步后信息区跟随当前帧');
assert.ok(info2.indexOf('2024-01-05') < 0, '当前帧之后（未来）不得出现在信息区');
assert.ok(info2.indexOf('EMA5 10.60') >= 0, 'overlay 因子按帧取值');
assert.ok(info2.indexOf('DIF 0.15') >= 0, 'pane 因子按帧取值');
assert.ok(info2.indexOf('涨跌 1.85%') >= 0, '涨跌相对前一交易日收盘（ohlc 次序 open/close/low/high）');
const opt2 = chart.options[chart.options.length - 1];
assert.equal(opt2.xAxis[0].data.length, 3, '图表窗口也截断到当前帧');
assert.ok(opt2.xAxis[0].data.indexOf('2024-01-05') < 0, '图表 x 轴不得含未来日期');

// 4) 接管合同：单一图表实例、chartEl 为 #chart-kline
assert.equal(h.charts.length, 1, '重播接管原容器，不新建第二个 K 线实例');

console.log('replay-tv-frame-ok');
"""

_EXIT_SCENARIO = r"""
const h = makeHarness();
const source = %SOURCE%;
vm.runInContext(source + '\nglobalThis.__initKlineReplay = initKlineReplay;', h.ctx);
vm.runInContext('__initKlineReplay(' + JSON.stringify(DETAIL) + ')', h.ctx);
// CR-2026-10-27 画线首片：进入重播前若处于画线模式，接管必须取消并禁用按钮
vm.runInContext("klineDrawState.mode = 'trend'; klineDrawState.pending = {date: '2024-01-02', price: 10, index: 0};", h.ctx);
h.get('btn-kreplay').click();
assert.equal(h.charts.length, 1, '进入重播接管静态实例');
assert.equal(vm.runInContext('klineDrawState.mode', h.ctx), null, '重播接管取消画线模式');
assert.equal(vm.runInContext('klineDrawState.pending', h.ctx), null, '重播接管清掉未落点起点');
assert.equal(h.get('kt-trend').disabled, true, '重播中禁用画线按钮');
assert.equal(h.get('kt-horizontal').disabled, true, '重播中禁用水平线按钮');
assert.equal(h.get('kt-clear').disabled, true, '重播中禁用清除按钮');
assert.ok(h.get('kline-ohlc').innerHTML.indexOf('2024-01-02') >= 0, '重播帧写入顶部信息区');
h.get('btn-kreplay-exit').click();
assert.ok(h.charts[0].disposed, '退出重播销毁重播实例（destroy(keepDom)）');
assert.equal(h.charts.length, 2, '退出后重建静态实例');
const staticOpt = h.charts[1].options[h.charts[1].options.length - 1];
assert.equal(staticOpt.xAxis[0].data.length, 6, '静态视图恢复全量 K 线');
assert.ok(staticOpt.grid.every(g => g.right === 56), '静态 TV 布局（右侧标尺留白）');
assert.ok(staticOpt.yAxis.every(y => y.position === 'right'), '静态 TV 右侧标尺');
assert.ok(h.get('kline-ohlc').innerHTML.indexOf('2024-01-09') >= 0, '信息区回静态末根');
assert.equal(h.get('kt-vol').disabled, false, '工具栏复原');
assert.equal(h.get('kt-vol').attrs['aria-pressed'], 'true', '量按钮 aria-pressed 复原');
assert.equal(h.get('kt-trend').disabled, false, '退出重播恢复画线按钮');
// 画线不进入重播帧：重播 option 无画线序列
const replayOpt = h.charts[0].options[h.charts[0].options.length - 1];
assert.ok(!replayOpt.series.some(s => String(s.name).indexOf('画线') === 0), '画线不得进入重播帧');
assert.ok(h.get('kreplay-info').classList, '信息卡容器保留');
// 高度：静态重建走同一 helper（1 副图 → 640px）
assert.equal(h.get('chart-kline').style.height, '640px', '静态重建高度与重播一致');
console.log('replay-tv-exit-ok');
"""

_JOB_DEFAULT_SCENARIO = r"""
const h = makeHarness();
const QREReplay = h.ctx.window.QREReplay;
const dates = ['2024-01-02', '2024-01-03', '2024-01-04'];
const equity = [100, 101, 103];
const mount = h.get('rp-mount');
const ctl = QREReplay.attach(mount, {
  dates, events: [], roundTrips: [],
  series: [{name: '策略', id: 's', data: equity, raw: equity, mark: true}],
});
const chart = h.charts[h.charts.length - 1];
const opt = chart.options[chart.options.length - 1];
// job.html 默认路径：不传 position / axisPointer，输出必须与旧版逐字节等价
assert.equal(opt.yAxis.length, 1);
assert.equal(opt.yAxis[0].position, undefined, 'job 默认不加 position');
assert.equal(opt.yAxis[0].axisLabel.formatter, '{value}%', 'job 默认收益率口径');
assert.equal('axisPointer' in opt, false, 'job 默认不加 axisPointer');
assert.equal(opt.grid[0].right, 20, 'job 默认 grid 不变');
// CR-2026-10-27 清理：job 默认路径 tooltip 仍统一加 %（标量口径逐字节不变）
assert.equal(opt.tooltip.valueFormatter(5.2), '5.20%', 'job 默认 tooltip 百分比口径');
assert.equal(opt.tooltip.valueFormatter(null), '—', 'job 默认 tooltip 缺失值');
console.log('replay-job-default-ok');
"""


def _harness(detail: str = "null") -> str:
    return (
        _HARNESS.replace("%FACTOR_LAYOUT_PATH%", json.dumps(str(FACTOR_LAYOUT_PATH)))
        .replace("%REPLAY_PATH%", json.dumps(str(REPLAY_PATH)))
        .replace("%DETAIL%", detail)
    )


def _run(scenario: str, detail: str = "null") -> None:
    _node(_harness(detail) + scenario)


# ---------------------------------------------------------------- tooltip 口径清理（CR-2026-10-27）
_TOOLTIP_SCENARIO = r"""
const h = makeHarness();
const source = %SOURCE%;
vm.runInContext(source + '\nglobalThis.__mountKlineReplay = mountKlineReplay;', h.ctx);
const ctl = vm.runInContext('__mountKlineReplay(' + JSON.stringify(DETAIL) + ')', h.ctx);
const chart = h.charts[h.charts.length - 1];
const opt = chart.options[chart.options.length - 1];

// 1) K 线重播 tooltip 不得统一加 %
assert.equal(opt.tooltip.valueFormatter(19.7), '19.70', '价格/因子不得加 %');
assert.equal(opt.tooltip.valueFormatter(0.15), '0.15', '因子按原值');
assert.equal(opt.tooltip.valueFormatter(null), '—', '缺失值');

// 2) candlestick 数组值：显示 OHLC，不得出现 NaN%
const k = opt.tooltip.valueFormatter([10.0, 10.5, 9.9, 10.6]);
assert.ok(k.indexOf('NaN') < 0 && k.indexOf('%') < 0, 'candlestick 值不得出现 NaN/%');
assert.ok(k.indexOf('开') >= 0 && k.indexOf('收') >= 0 && k.indexOf('低') >= 0 && k.indexOf('高') >= 0, 'K 线显示 OHLC 标签');
assert.ok(k.indexOf('10.00') >= 0 && k.indexOf('10.50') >= 0 && k.indexOf('9.90') >= 0 && k.indexOf('10.60') >= 0, 'K 线 OHLC 数值完整');

// 3) 成交量：series 级 valueFormatter 显示万手（优先于全局）
const vol = opt.series[1];
assert.equal(vol.name, '成交量');
assert.equal(typeof vol.tooltip.valueFormatter, 'function', '成交量 series 需自带 tooltip formatter');
assert.equal(vol.tooltip.valueFormatter(200000), '20.00 万', '成交量按万显示');

// 4) 因子线序列走全局原值口径
const ema = opt.series.filter(s => s.name === 'EMA5')[0];
assert.equal(opt.tooltip.valueFormatter(11.2), '11.20', '因子原值');
assert.ok(ema, 'EMA5 overlay 序列存在');

console.log('replay-tooltip-ok');
"""

_HEIGHT_SCENARIO = r"""
const h = makeHarness();
const source = %SOURCE%;
vm.runInContext(source + '\nglobalThis.__mountKlineReplay = mountKlineReplay;', h.ctx);
const QREReplay = h.ctx.window.QREReplay;
// 1) 共享 helper 公式：无副图 520，有副图 480 + panes*160（CR-2026-10-29 整体 +60px）
assert.equal(QREReplay.klineHeightForPanes(0), 520, '无副图 520px');
assert.equal(QREReplay.klineHeightForPanes(1), 640, '1 副图 640px');
assert.equal(QREReplay.klineHeightForPanes(3), 960, '3 副图 960px');
assert.equal(QREReplay.core.klineHeightForPanes(0), 520, 'core 也暴露同一 helper');
// 2) 重播容器用同一公式（DETAIL：1 个 MACD 合并副图 → 640px）
const ctl = vm.runInContext('__mountKlineReplay(' + JSON.stringify(DETAIL) + ')', h.ctx);
assert.equal(h.get('chart-kline').style.height, '640px', '重播容器高度走共享 helper');
console.log('replay-height-ok');
"""


class TestReplayFrameLayout:
    def test_replay_frame_right_axis_info_bar_no_future(self):
        _run(
            _PAGE_SCENARIO.replace("%SOURCE%", json.dumps(_symbol_source())),
            json.dumps(_DETAIL, ensure_ascii=False),
        )

    def test_exit_restores_static_tv_view(self):
        _run(
            _EXIT_SCENARIO.replace("%SOURCE%", json.dumps(_symbol_source())),
            json.dumps(_DETAIL, ensure_ascii=False),
        )

    def test_job_default_path_unchanged(self):
        _run(_JOB_DEFAULT_SCENARIO)


# ---------------------------------------------------------------- tooltip 口径与高度（CR-2026-10-27 清理）
class TestTooltipUnitCleanup:
    """重播 tooltip 按序列类型显示单位，不再统一加 %。"""

    def test_kline_replay_tooltip_units(self):
        _run(
            _TOOLTIP_SCENARIO.replace("%SOURCE%", json.dumps(_symbol_source())),
            json.dumps(_DETAIL, ensure_ascii=False),
        )

    def test_replay_tooltip_percent_switch(self):
        assert "tooltipPercent" in REPLAY_JS, "replay.js 需支持 tooltipPercent 开关"
        body = _mount_body()
        assert "tooltipPercent: false" in body, "K 线重播必须显式关闭百分比口径"

    def test_volume_series_has_own_formatter(self):
        body = _mount_body()
        assert "valueFormatter" in body, "成交量 series 需自带万手 formatter"
        assert "10000" in body, "成交量按万换算"

    def test_height_helper_shared(self):
        assert "klineHeightForPanes" in REPLAY_JS, "replay.js 需提供共享高度 helper"
        body = _symbol_source()
        assert body.count("klineHeightForPanes(") >= 2, (
            "静态 renderKline 与重播 mountKlineReplay 必须共用同一 helper"
        )
        assert "420 + panes.length * 160" not in SYMBOL_TPL, "symbol.html 不得再保留内联高度公式"
        assert "520px" not in _mount_body(), "重播不得再写死 K 线高度"

    def test_replay_height_matches_static_formula(self):
        _run(
            _HEIGHT_SCENARIO.replace("%SOURCE%", json.dumps(_symbol_source())),
            json.dumps(_DETAIL, ensure_ascii=False),
        )


# ---------------------------------------------------------------- 重播灰字备注清理（R-UI-001）
class TestReplayNoteCleanup:
    """R-UI-001：K 线重播不得带 .opt 灰字备注；必要口径迁到 #btn-kreplay data-tip。"""

    def test_no_gray_note_in_kline_replay(self):
        assert "kreplay-note" not in SYMBOL_TPL, "不得再动态插入 kreplay-note 灰字备注"
        body = _init_kline_replay_body()
        assert 'class="opt"' not in body, "initKlineReplay 不得插入 .opt 灰字备注"
        assert "insertAdjacentHTML" not in body, "重播入口不得再动态插备注段落"

    def test_btn_kreplay_carries_data_tip(self):
        match = re.search(r"<button[^>]*id=\"btn-kreplay\"[^>]*>", SYMBOL_TPL)
        assert match, "未找到 #btn-kreplay 按钮"
        button = match.group(0)
        assert "data-tip=" in button, "必要口径必须迁到 data-tip（LabUI.helpTips 机制）"
        for key in ("信", "入/出", "信号日", "T+1", "毛口径", "不构成投资建议"):
            assert key in button, f"data-tip 缺少关键口径: {key}"