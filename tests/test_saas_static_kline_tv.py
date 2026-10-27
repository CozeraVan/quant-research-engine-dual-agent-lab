"""QRE-TV-STATIC-KLINE-LAYOUT：静态日 K 的 TradingView 化首片（CR-2026-10-27）。

覆盖六条硬要求里可由源码 + Node 桩核验的部分：
1. 右侧价格标尺（grid 右留白 + yAxis position right）、x 全联动（axisPointer/dataZoom 不变）。
2. 顶部信息区 `#kline-ohlc`：初始为末根、悬停当日 OHLC/量/涨跌幅/因子值、缺失 `—`、
   不用未来数据（涨跌幅只用前一根收盘）。
3. 缩放/重置：滚轮由 ECharts inside dataZoom 承担；按钮走 dispatchAction，只动 dataZoom 窗口。
4. 左侧紧凑工具栏：5 个按钮（内联 SVG + 可见文字 + aria）、≥44px、focus-visible、
   375 断点收窄文案；按钮 disabled 由数据/因子可用性决定。
5. 因子 display 合同与 chip 三态不变（仍走 QREFactorLayout.plan + renderFactorChips）。
6. 重播可接管：进入重播禁用工具栏并清空信息区（防未来数据泄漏）。

全部 Node harness + 纯逻辑桩，不触外网、不跑回测。
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


def _node(script: str) -> None:
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    result = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


def _kline_block() -> str:
    """工具栏/信息条全部落在 klineResizeBound → 重播注释之前的区块内。"""
    match = re.search(r"(let klineResizeBound[\s\S]*?)(?=\n// --- K线级重播)", SYMBOL_TPL)
    assert match, "未找到 K 线静态区块"
    return match.group(1)


def _tool_helpers() -> str:
    """工具栏/信息条/布局规格区块：不含 renderKline 里既有的行情配色。"""
    match = re.search(
        r"(let klineResizeBound = false;[\s\S]*?)(?=\nfunction renderKline\(d\)\{)", SYMBOL_TPL
    )
    assert match, "未找到 K 线工具栏区块"
    return match.group(1)


def _render_kline_source() -> str:
    match = re.search(
        r"(let klineResizeBound = false;[\s\S]*?\nfunction renderKline\(d\)\{[\s\S]*?\n\})",
        SYMBOL_TPL,
    )
    assert match, "未找到 renderKline 及其声明"
    return match.group(1)


# ---------------------------------------------------------------- 源码合同
class TestSourceContract:

    def test_toolbar_dom(self):
        html = SYMBOL_TPL
        assert 'id="kline-tools"' in html
        assert 'role="toolbar"' in html
        assert 'aria-label="K线工具栏"' in html
        for kind in ("zoom-in", "zoom-out", "reset", "vol", "fct"):
            assert 'id="kt-%s"' % kind in html, "缺少工具栏按钮 kt-%s" % kind
        assert html.count("<svg") >= 5, "5 个按钮均需内联 SVG 图标"
        assert html.count('aria-hidden="true"') >= 5
        assert html.count('focusable="false"') >= 5
        assert html.count("data-tip=") >= 5, "图标按钮需要 data-tip 说明，不能写灰字备注"
        assert 'aria-pressed="true"' in html, "量/因子按钮需要 aria-pressed 初值"
        assert 'aria-label="放大"' in html and 'aria-label="重置"' in html

    def test_info_bar_dom(self):
        html = SYMBOL_TPL
        assert 'id="kline-ohlc"' in html
        assert 'aria-live="polite"' in html

    def test_single_chart_module(self):
        assert SYMBOL_TPL.count('id="chart-kline"') == 1, "不得出现第二个同内容 K 线模块"
        assert SYMBOL_TPL.count("echarts.init(") == 2, "实例数不变（静态 + 重播各一）"

    def test_style_and_a11y(self):
        block = _tool_helpers()
        html = SYMBOL_TPL
        assert ".kline-tools" in html and ".kline-tool" in html and ".kline-ohlc" in html
        assert "min-height:44px" in html or "min-height: 44px" in html
        assert ":focus-visible" in html
        assert "@media(max-width:640px)" in html or "@media (max-width:640px)" in html
        assert "var(--line)" in html and "var(--card)" in html
        # 工具栏/信息条只用主题 token，不引入第四色相
        for token in ("#C93A3A", "#1E8E5A", "#6750A4", "#8B7FBE", "#B7A6E8", "#d43030", "#1a9e4b"):
            assert token not in block, "工具栏不使用自造颜色: %s" % token
        # 红涨绿跌的既有行情配色不得被这次改动带走
        assert "color: '#C93A3A', color0: '#1E8E5A'" in _render_kline_source()
        assert "color: '#d43030'" in _render_kline_source()
        assert "color: '#1a9e4b'" in _render_kline_source()

    def test_right_axis_and_padding(self):
        block = _render_kline_source()
        assert block.count("position: 'right'") >= 3, "主图/量/因子面板都要右侧标尺"
        assert "left: 16, right: 56" in block, "右侧标尺留白"
        assert "position: 'right'" in SYMBOL_TPL

    def test_no_forbidden_deps(self):
        html = SYMBOL_TPL
        for bad in ("cdn.", "unpkg", "jsdelivr", "LightweightCharts"):
            assert bad not in html, "不得引入外部依赖: %s" % bad

    def test_factor_contract_kept(self):
        block = _render_kline_source()
        assert "QREFactorLayout.plan(factors, chipStates())" in block
        assert "renderFactorChips(plan, d)" in block
        assert "yAxisIndex: 0" in block
        assert "xAxisIndex: 'all'" in block
        assert "FCT_LS_PREFIX" in SYMBOL_TPL

    def test_replay_disables_tools(self):
        match = re.search(r"function initKlineReplay\(d\)\{[\s\S]*?\n\}\n", SYMBOL_TPL)
        assert match, "未找到 initKlineReplay"
        body = match.group(0)
        assert "setKlineToolsEnabled(false)" in body, "进入重播要禁用工具栏（防未来数据）"
        assert body.index("setKlineToolsEnabled(false)") < body.index("mountKlineReplay(klineData)")
        # 重播组件本身不动（接管容器合同）
        assert "chartEl: el" in SYMBOL_TPL or "mountKlineReplay" in SYMBOL_TPL


# ---------------------------------------------------------------- Node harness
_HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');

function makeEl(sel){
  const e = {
    sel: sel, style: {}, dataset: {}, disabled: false, attrs: {}, listeners: {}, textContent: '',
    classList: { add(){}, remove(){}, toggle(){}, contains(){ return false; } },
    setAttribute(k, v){ e.attrs[k] = String(v); },
    addEventListener(t, fn){ (e.listeners[t] = e.listeners[t] || []).push(fn); },
    click(){ (e.listeners.click || []).forEach(function (fn) { fn({}); }); },
  };
  let html = '';
  Object.defineProperty(e, 'innerHTML', {
    get(){ return html; }, set(v){ html = String(v); }, configurable: true,
  });
  return e;
}

function makeChart(){
  return {
    disposed: false, options: [], actions: [], handlers: {}, legend: {},
    option: { grid: [], xAxis: [], yAxis: [], dataZoom: [{ start: 0, end: 100 }] },
    setOption(o){ this.options.push(o); Object.assign(this.option, o); },
    getOption(){ return this.option; },
    on(ev, fn){ (this.handlers[ev] = this.handlers[ev] || []).push(fn); },
    dispatchAction(a){
      this.actions.push(a);
      if (a.type === 'dataZoom') this.option.dataZoom = [{ start: a.start, end: a.end }];
      if (a.type === 'legendSelect') this.legend[a.name] = true;
      if (a.type === 'legendUnSelect') this.legend[a.name] = false;
    },
    resize(){},
    dispose(){ this.disposed = true; },
    isDisposed(){ return this.disposed; },
    emit(ev, arg){ (this.handlers[ev] || []).forEach(function (fn) { fn(arg); }); },
  };
}

function makeHarness(plan){
  const els = {}, winListeners = {}, charts = [];
  function q(sel){ if (!els[sel]) els[sel] = makeEl(sel); return els[sel]; }
  const ctx = {
    console: console,
    document: { querySelector(sel){ return q(sel); } },
    window: { addEventListener(t, fn){ (winListeners[t] = winListeners[t] || []).push(fn); } },
    echarts: {
      init(){ const c = makeChart(); charts.push(c); return c; },
      getInstanceByDom(){
        const live = charts.filter(function (c) { return !c.disposed; });
        return live.length ? live[live.length - 1] : null;
      },
    },
    QREFactorLayout: {
      plan(){ return plan || { chips: [], panes: [], overlays: [] }; },
      COLORS: { histUp: '#C93A3A', histDown: '#1E8E5A' },
    },
    QRETheme: { themeChart(){} },
    chipStates(){ return {}; },
    renderFactorChips(){},
    f2(v){ return Number(v).toFixed(2); },
    requestAnimationFrame(fn){ return fn(); },
  };
  ctx.$ = q;
  return { ctx: vm.createContext(ctx), els: els, wins: winListeners, charts: charts };
}
"""

_MAIN_DATA = {
    "kline": {
        "dates": ["2024-01-02", "2024-01-03", "2024-01-04"],
        "ohlc": [
            [12.0, 12.5, 11.8, 12.6],
            [12.5, 12.0, 11.9, 12.7],
            [12.0, 11.5, 11.4, 12.1],
        ],
        "vols": [100000, 200000, 300000],
    },
    "factors": [],
    "orders": [],
}

_FACTOR_PLAN_JSON = json.dumps({
    "chips": [],
    "overlays": [
        {"f": {"name": "EMA5", "values": [10.0, 11.0, 12.0]}, "name": "EMA5", "color": "#6750A4"},
    ],
    "panes": [
        {"key": "macd", "name": "MACD", "thresholds": [0], "series": [
            {"name": "DIF", "type": "line", "values": [0.1, 0.2, 0.3], "color": "#6750A4"},
            {"name": "DEA", "type": "line", "values": [0.05, 0.15, 0.25], "color": "#8B7FBE"},
        ]},
    ],
})

_MAIN_SCENARIO = r"""
const h = makeHarness(null);
const source = %SOURCE%;
vm.runInContext(source, h.ctx);
const d = %DATA%;
vm.runInContext('renderKline(' + JSON.stringify(d) + ')', h.ctx);

const info = h.els['#kline-ohlc'];
assert.ok(info, '信息条元素存在');
// 1) 默认展示末根，含 OHLC / 量 / 相对前一收盘的涨跌幅
assert.ok(info.innerHTML.indexOf('2024-01-04') >= 0, '默认末根日期: ' + info.innerHTML);
assert.ok(info.innerHTML.indexOf('开 12.00') >= 0, '开盘');
assert.ok(info.innerHTML.indexOf('高 12.10') >= 0, '最高');
assert.ok(info.innerHTML.indexOf('低 11.40') >= 0, '最低');
assert.ok(info.innerHTML.indexOf('收 11.50') >= 0, '收盘');
assert.ok(info.innerHTML.indexOf('-4.17%') >= 0, '涨跌幅相对前一交易日收盘: ' + info.innerHTML);
assert.ok(info.innerHTML.indexOf('量 30.00 万') >= 0, '成交量');
assert.ok(info.innerHTML.indexOf('NaN') < 0 && info.innerHTML.indexOf('undefined') < 0);

// 2) 首根没有前收盘 → 涨跌缺失用 —
const first = vm.runInContext('klineInfoHTML(' + JSON.stringify(d) + ', null, 0)', h.ctx);
assert.ok(first.indexOf('涨跌 —') >= 0, '首根涨跌缺失: ' + first);
assert.ok(first.indexOf('NaN') < 0 && first.indexOf('undefined') < 0);

// 3) 越界 / null / 无该根 → 单 — 占位
const empty = vm.runInContext('klineInfoHTML(' + JSON.stringify(d) + ', null, null)', h.ctx);
assert.equal(empty, '<span class="k-dim">—</span>');
assert.equal(vm.runInContext('klineInfoHTML(' + JSON.stringify(d) + ', null, 99)', h.ctx),
  '<span class="k-dim">—</span>');
const noBar = %EMPTY_BAR%;
assert.equal(vm.runInContext('klineInfoHTML(' + JSON.stringify(noBar) + ', null, 0)', h.ctx),
  '<span class="k-dim">—</span>');

// 4) 悬停联动：数字索引 / 日期字符串 / 越界回落末根 / 移出图表回末根
const chart = h.charts[h.charts.length - 1];
assert.ok(chart.handlers.updateAxisPointer, '注册 updateAxisPointer');
chart.emit('updateAxisPointer', { axesInfo: [{ value: 1 }] });
assert.ok(info.innerHTML.indexOf('2024-01-03') >= 0, '数字索引悬停: ' + info.innerHTML);
assert.ok(info.innerHTML.indexOf('收 12.00') >= 0);
chart.emit('updateAxisPointer', { axesInfo: [{ value: '2024-01-02' }] });
assert.ok(info.innerHTML.indexOf('2024-01-02') >= 0, '日期字符串悬停: ' + info.innerHTML);
chart.emit('updateAxisPointer', { axesInfo: [{ value: 99 }] });
assert.ok(info.innerHTML.indexOf('2024-01-04') >= 0, '越界回落末根: ' + info.innerHTML);
chart.emit('updateAxisPointer', {});
assert.ok(info.innerHTML.indexOf('2024-01-04') >= 0, '无 axesInfo 回末根');
chart.emit('globalout', {});
assert.ok(info.innerHTML.indexOf('2024-01-04') >= 0, '移出图表回末根');

// 5) 缩放只动 dataZoom 窗口
vm.runInContext('klineZoom(chart, 0.7)', Object.assign(h.ctx, { chart: chart }));
let z = chart.actions[chart.actions.length - 1];
assert.equal(z.type, 'dataZoom');
assert.ok(Math.abs(z.start - 15) < 1e-9 && Math.abs(z.end - 85) < 1e-9, '放大到 15/85');
vm.runInContext('klineZoom(chart, 1.4)', h.ctx);
z = chart.actions[chart.actions.length - 1];
assert.ok(Math.abs(z.start - 1) < 1e-9 && Math.abs(z.end - 99) < 1e-9, '缩小到 1/99');
vm.runInContext('klineResetZoom(chart)', h.ctx);
z = chart.actions[chart.actions.length - 1];
assert.equal(z.start, 0); assert.equal(z.end, 100);
// 最小窗口 2%：左端不越界
chart.option.dataZoom = [{ start: 0, end: 1 }];
vm.runInContext('klineZoom(chart, 0.7)', h.ctx);
z = chart.actions[chart.actions.length - 1];
assert.equal(z.start, 0); assert.equal(z.end - z.start, 2);
// 右端不越界
chart.option.dataZoom = [{ start: 98, end: 100 }];
vm.runInContext('klineZoom(chart, 0.7)', h.ctx);
z = chart.actions[chart.actions.length - 1];
assert.ok(z.end <= 100 && z.end - z.start === 2, '右端钳制');

// 6) 工具栏点击生效
chart.option.dataZoom = [{ start: 0, end: 100 }];
h.els['#kt-zoom-in'].click();
z = chart.actions[chart.actions.length - 1];
assert.ok(Math.abs(z.start - 15) < 1e-9, '点击放大触发 dispatchAction');
h.els['#kt-zoom-out'].click();
assert.equal(chart.actions[chart.actions.length - 1].type, 'dataZoom');

// 7) 无因子：fct 按钮禁用，vol/zoom 可用
assert.equal(h.els['#kt-fct'].disabled, true, '无因子时因子按钮禁用');
assert.equal(h.els['#kt-vol'].disabled, false);
assert.equal(h.els['#kt-vol'].attrs['aria-pressed'], 'true');

// 8) 关闭成交量：量面板收成隐藏格 + legend 隐藏，时间轴落到主图
h.els['#kt-vol'].click();
assert.equal(chart.legend['成交量'], false, 'legendUnSelect 成交量');
assert.equal(chart.option.grid[1].height, 1, '量面板隐藏');
assert.equal(chart.option.yAxis[1].show, false);
assert.equal(chart.option.xAxis[0].axisLabel.show, true, '时间轴落到最后一个可见格');
assert.equal(h.els['#kt-vol'].attrs['aria-pressed'], 'false');
// 一键重置恢复
h.els['#kt-reset'].click();
assert.equal(chart.option.grid[1].top, '74%');
assert.equal(chart.option.yAxis[1].show, true);
assert.equal(chart.option.xAxis[1].axisLabel.show, true);
assert.equal(chart.legend['成交量'], true);
assert.equal(h.els['#kt-vol'].attrs['aria-pressed'], 'true');
assert.equal(chart.option.dataZoom[0].start, 0);

// 9) 二次渲染不重复绑 window.resize（ResizeObserver 缺席时的兜底）
vm.runInContext('renderKline(' + JSON.stringify(d) + ')', h.ctx);
assert.equal((h.wins.resize || []).length, 1, 'window.resize 只绑一次');
assert.equal(info.innerHTML.indexOf('2024-01-04') >= 0, true, '重渲染后信息条回到末根');
console.log('static-kline-main-ok');
"""

_FACTOR_SCENARIO = r"""
const h = makeHarness(%PLAN%);
const source = %SOURCE%;
vm.runInContext(source, h.ctx);
const d = %DATA%;
vm.runInContext('renderKline(' + JSON.stringify(d) + ')', h.ctx);
const chart = h.charts[h.charts.length - 1];

// 有因子：主图 42% + 量 53%/10% + 面板 66%
assert.equal(chart.option.grid.length, 3, '主图 + 量 + 1 面板');
assert.equal(chart.option.grid[0].height, '42%');
assert.equal(chart.option.grid[1].top, '53%');
assert.equal(chart.option.grid[2].top, '66%');
// 时间轴只在最后一个格
assert.equal(chart.option.xAxis[0].axisLabel.show, false);
assert.equal(chart.option.xAxis[2].axisLabel.show, true);
assert.equal(chart.option.yAxis[2].show, true);
assert.equal(chart.option.yAxis[0].position, 'right');
assert.equal(chart.option.yAxis[1].position, 'right');
assert.equal(chart.option.yAxis[2].position, 'right');
// 因子值进信息条
const info = h.els['#kline-ohlc'];
assert.ok(info.innerHTML.indexOf('EMA5 12.00') >= 0, 'overlay 当日值: ' + info.innerHTML);
assert.ok(info.innerHTML.indexOf('DIF 0.30') >= 0, 'pane 当日值: ' + info.innerHTML);
assert.ok(info.innerHTML.indexOf('DEA 0.25') >= 0);
assert.equal(h.els['#kt-fct'].disabled, false, '有因子时因子按钮可用');

// 关闭全部因子：面板隐藏 + 时间轴上移到量格
h.els['#kt-fct'].click();
assert.equal(chart.option.grid[2].height, 1, '面板格隐藏');
assert.equal(chart.option.xAxis[1].axisLabel.show, true);
assert.equal(chart.option.yAxis[2].show, false);
assert.equal(chart.legend['EMA5'], false);
assert.equal(chart.legend['DIF'], false);
assert.equal(h.els['#kt-fct'].attrs['aria-pressed'], 'false');
// 再开回来
h.els['#kt-fct'].click();
assert.equal(chart.option.grid[2].top, '66%');
assert.equal(chart.legend['EMA5'], true);
assert.equal(h.els['#kt-fct'].attrs['aria-pressed'], 'true');
console.log('static-kline-factor-ok');
"""

_EMPTY_BAR_DATA = {"kline": {"dates": ["2024-01-02"], "ohlc": [None], "vols": [None]}}


class TestStaticKlineBehavior:

    def test_info_and_tools(self):
        script = (
            _HARNESS
            + _MAIN_SCENARIO.replace("%SOURCE%", json.dumps(_render_kline_source()))
            .replace("%DATA%", json.dumps(_MAIN_DATA))
            .replace("%EMPTY_BAR%", json.dumps(_EMPTY_BAR_DATA))
        )
        _node(script)

    def test_factor_panes(self):
        script = (
            _HARNESS
            + _FACTOR_SCENARIO.replace("%PLAN%", _FACTOR_PLAN_JSON)
            .replace("%SOURCE%", json.dumps(_render_kline_source()))
            .replace("%DATA%", json.dumps(_MAIN_DATA))
        )
        _node(script)