"""LWC K 线适配层纯函数合同（CR-2026-10-28 B 路受控试点阶段 1）。

适配层只做「detail JSON 合同 → LWC series/pane 定义」的纯变换，不碰 DOM、
不碰 LightweightCharts 全局，可在 Node 里直接断言。渲染与主题在
`static/chart-core/kline-lwc.js`，由 `symbol.html` 的开关派发。

合同要点（与 docs/agent/23_KLINE_IMPLEMENTATION.md §1.3 一致）：
- `kline.ohlc` 顺序是 **open, close, low, high**，LWC 要 `{open,high,low,close}`；
- 缺失值是 `null`，必须转成 `{time}` 空点而不是 `null`（LWC 会拒）；
- 时间是 `YYYY-MM-DD` 字符串，LWC 直用；同一时间戳重复必须先升序去重，
  否则 `setData` 抛 "data must be asc ordered"。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ADAPTER_JS = (REPO / "src/quant_research_engine/gui/static/chart-core/kline-lwc.js").read_text(
    encoding="utf-8"
)
SYMBOL_TPL = (REPO / "src/quant_research_engine/gui/saas/templates/symbol.html").read_text(
    encoding="utf-8"
)

DETAIL = {
    "kline": {
        # 故意包含：重复日期、null 缺口、乱序 —— 适配层必须全部归一
        "dates": ["2024-01-04", "2024-01-02", "2024-01-03", "2024-01-03", "2024-01-05"],
        "ohlc": [
            [13.0, 12.0, 11.5, 12.8],
            [10.0, 11.0, 9.8, 11.2],
            [11.0, 10.5, 10.2, 11.4],
            [11.5, 12.5, 11.1, 12.6],
            [None, None, None, None],
        ],
        "vols": [1000, 2000, 1500, 2500, None],
    },
    "factors": [
        {"name": "DIF", "col": "macd_12_26_9", "values": [0.1, None, 0.2, 0.25, 0.3],
         "thresholds": [0.0]},
        {"name": "DEA", "col": "macds_12_26_9", "values": [0.05, 0.06, 0.07, 0.08, 0.09],
         "thresholds": [0.0]},
        {"name": "EMA5", "col": "ema_5", "values": [10.0, 10.5, 11.0, 11.5, 12.0]},
    ],
    "orders": [
        {"trade_date": "2024-01-03", "side": "buy", "quantity": 100, "price": 10.5},
        {"trade_date": "2024-01-04", "side": "sell", "quantity": 100, "price": 12.0},
        {"trade_date": "2024-01-02", "side": "buy", "quantity": 50, "price": 11.0},
    ],
}


def _node(script: str) -> None:
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    result = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


_HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const source = %SOURCE%;
// 断言体跑在外层 realm，需要能直接拿到 stub 与适配层导出
const ctxObj = {console, window: {}, QREFactorLayout: {
  // 适配层只依赖 plan() 的 panes/overlays 形状，用与生产一致的假数据
  plan(factors, states, order){
    const panes = [
      {key: 'macd', name: 'MACD', thresholds: [0], series: [
        {name: 'DIF', type: 'line', values: [0.1, null, 0.2, 0.25, 0.3], color: '#6750A4'},
        {name: 'DEA', type: 'line', values: [0.05, 0.06, 0.07, 0.08, 0.09], color: '#E8A33D'},
      ]},
    ];
    const overlays = [{f: {name: 'EMA5', values: [10, null, 11, 11.5, 12]}, name: 'EMA5', color: '#E8A33D'}];
    return {chips: [], overlays, panes, paneCount: panes.length};
  },
  COLORS: {overlay: ['#E8A33D', '#2A9D8F', '#6750A4'], pane: '#6750A4',
           dif: '#6750A4', dea: '#E8A33D', histUp: '#C93A3A', histDown: '#1E8E5A'},
}};
const context = vm.createContext(ctxObj);
vm.runInContext(source, context);
const A = context.window.QRELwcAdapter;
globalThis.QREFactorLayout = ctxObj.QREFactorLayout;
"""


def test_adapter_ohlc_reorder_and_dedupe_and_sort() -> None:
    """OHLC 合同序 open/close/low/high → LWC open/high/low/close；日期升序去重。"""
    _node(_HARNESS.replace("%SOURCE%", json.dumps(ADAPTER_JS)) + r"""
const bars = A.toCandles(DETAIL().kline);
assert.equal(bars.length, 4, '重复日期必须去重（5 条 → 4 条）');
assert.equal(JSON.stringify(bars.map(b => b.time)),
  '["2024-01-02","2024-01-03","2024-01-04","2024-01-05"]', '必须按时间升序');
const b2 = bars[0];   // 01-02 ← ohlc[1]
assert.equal(b2.open, 10, 'open = ohlc[0]');
assert.equal(b2.close, 11, 'close = ohlc[1]');
assert.equal(b2.low, 9.8, 'low = ohlc[2]');
assert.equal(b2.high, 11.2, 'high = ohlc[3]');
const b3 = bars[1];   // 01-03 ← ohlc[3]（重复日后写覆盖，不是 ohlc[2]）
assert.equal(b3.open, 11.5, '重复日期必须取后出现的那一行');
// 全 null 的那根 → {time} 空点，不得出现 null 字段
const b4 = bars[3];
assert.equal(JSON.stringify(Object.keys(b4)), '["time"]', '缺口必须是 {time} 空点');
assert.equal(b4.open, undefined);
console.log('candles-ok');
""".replace("DETAIL()", json.dumps(DETAIL)))


def test_adapter_volume_and_overlay_and_histogram() -> None:
    """成交量/均线 overlay/因子副图的空点与颜色口径。"""
    _node(_HARNESS.replace("%SOURCE%", json.dumps(ADAPTER_JS)) + r"""
const k = DETAIL().kline;
const vol = A.toVolume(k);
assert.equal(vol.length, 4, '成交量与 K 线同长');
assert.equal(JSON.stringify(vol.map(v => v.time)),
  '["2024-01-02","2024-01-03","2024-01-04","2024-01-05"]');
assert.equal(vol[0].value, 2000, '01-02 成交量');
assert.equal(vol[1].value, 2500, '01-03 成交量（重复日后写覆盖）');
assert.equal(vol[2].value, 1000, '01-04 成交量');
assert.equal(JSON.stringify(Object.keys(vol[3])), '["time"]', '01-05 缺口成交量为 {time} 空点');

const plan = QREFactorLayout.plan([], {}, []);
// values 与 dates **按原始下标**对齐，不是按排序后顺序：
//   dates  = [01-04, 01-02, 01-03, 01-03, 01-05]  (idx 0..4)
//   values = [10,    null,  11,    11.5,  12  ]
// 去重升序后 01-02→idx1(null) 01-03→idx3(11.5) 01-04→idx0(10) 01-05→idx4(12)
const ov = A.toLineSeries(plan.overlays[0].f.values, k.dates);
assert.equal(ov.length, 4, 'overlay 与 K 线同长');
assert.equal(JSON.stringify(Object.keys(ov[0])), '["time"]', '01-02 overlay 缺口是 {time} 空点');
assert.equal(ov[1].value, 11.5, '01-03 overlay 值（重复日取后一个下标）');
assert.equal(ov[2].value, 10, '01-04 overlay 值');
assert.equal(ov[3].value, 12, '01-05 overlay 值仍按日期对齐');

// MACD 柱逐点 color：正红负绿（与 K 线涨跌同色）
const hist = A.toHistogram([0.1, -0.2, 0.0], ['2024-01-02', '2024-01-03', '2024-01-04']);
assert.equal(hist[0].color, A.THEME.histUp, '正柱用 histUp');
assert.equal(hist[1].color, A.THEME.histDown, '负柱用 histDown');
assert.equal(hist[2].color, A.THEME.histUp, '零值按正柱（>=0）');
console.log('volume-overlay-hist-ok');
""".replace("DETAIL()", json.dumps(DETAIL)))


def test_adapter_markers_and_thresholds() -> None:
    """买卖 marker 红买绿卖、按日期归位；阈值线只挂 pane 第一条 line。"""
    _node(_HARNESS.replace("%SOURCE%", json.dumps(ADAPTER_JS)) + r"""
const mk = A.toMarkers(DETAIL().orders, A.THEME);
assert.equal(mk.length, 3, '三笔订单三个 marker');
assert.equal(JSON.stringify(mk.map(m => m.time)), '["2024-01-02","2024-01-03","2024-01-04"]', '按日期升序');
const buy = mk.filter(m => m.shape === 'arrowUp');
const sell = mk.filter(m => m.shape === 'arrowDown');
assert.equal(buy.length, 2);
assert.equal(sell.length, 1);
assert.equal(buy[0].color, A.THEME.up, '买入用阳线红');
assert.equal(sell[0].color, A.THEME.down, '卖出用阴线绿');
assert.equal(buy[0].position, 'belowBar');
assert.equal(sell[0].position, 'aboveBar');

const plan = QREFactorLayout.plan([], {}, []);
const thr = A.thresholdLines(plan.panes[0]);
assert.equal(thr.length, 1, 'MACD 一个 0 轴阈值');
assert.equal(thr[0].price, 0);
assert.equal(thr[0].lineStyle, 2, '虚线');
console.log('markers-thresholds-ok');
""".replace("DETAIL()", json.dumps(DETAIL)))


def test_adapter_theme_and_height() -> None:
    """主题双套（红绿色相恒定 + 暗色提亮紫系）；高度公式与 replay.js 同源。"""
    _node(_HARNESS.replace("%SOURCE%", json.dumps(ADAPTER_JS)) + r"""
const light = A.theme(false), dark = A.theme(true);
assert.equal(light.up, '#C93A3A'); assert.equal(light.down, '#1E8E5A');
assert.equal(dark.up, '#FF7A7A'); assert.equal(dark.down, '#4FD69A');
assert.equal(light.histUp, light.up, 'MACD 柱与 K 线同色（浅色）');
assert.equal(dark.histUp, dark.up, 'MACD 柱与 K 线同色（暗色）');
assert.equal(light.background, '#FFFFFF'); assert.equal(dark.background, '#2E236C');
assert.equal(light.dif, '#6750A4'); assert.equal(dark.dif, '#9B84D8', '暗色紫系提亮');
assert.equal(light.dea, '#E8A33D'); assert.equal(dark.dea, '#E8A33D', 'DEA 两主题一致');
assert.equal(light.threshold, '#8B7FBE'); assert.equal(dark.threshold, '#A78BE0');

// CR-2026-10-29 C3.2：与 replay.js::klineHeightForPanes 同源，整体 +60px
assert.equal(A.klineHeight(0), 520, '无副图 520');
assert.equal(A.klineHeight(1), 640, '1 副图 480+160');
assert.equal(A.klineHeight(3), 960, '3 副图 480+480');
console.log('theme-height-ok');
""".replace("DETAIL()", json.dumps(DETAIL)))


# ---------------------------------------------------------------- 源码合同
class TestLwcSourceContract:
    def test_echarts_path_untouched(self):
        """ECharts 路径必须逐字节保留作回滚实现（既有 harness 断言依赖）。"""
        assert SYMBOL_TPL.count("echarts.init(") == 2, "实例数不变（静态 + 重播各一）"
        assert "color: '#C93A3A', color0: '#1E8E5A'" in SYMBOL_TPL
        assert "QREFactorLayout.plan(factors, chipStates(), paneOrder())" in SYMBOL_TPL

    def test_lwc_frozen_no_switch_entry(self):
        """QRE-KLINE-LWC-FROZEN（T6）：引擎切换入口已冻结移除。

        逆向侧 §4 决策：① LWC 5.x 的 pane 撑不住动态因子 pane；
        ② "像 TV"的差距 80% 在样式规格不在引擎。故移除用户可见入口，
        LWC 代码退化为休眠/防御态，阶段 3（重播 LWC adapter）不做。
        """
        assert "试用 TradingView 图表" not in SYMBOL_TPL, "不得再暴露 LWC 切换按钮"
        assert "切回 ECharts" not in SYMBOL_TPL, "不得再暴露引擎切换按钮"
        # 休眠资产与代码保留（klineDisposeEngines 仍依赖它做防御）
        assert "/static/chart-core/vendor/lightweight-charts.standalone.production.js" in SYMBOL_TPL
        assert "/static/chart-core/kline-lwc.js" in SYMBOL_TPL
        assert 'id="kline-legend"' in SYMBOL_TPL, "LWC 图例 DOM 保留（休眠）"
        assert 'id="kline-attrib"' in SYMBOL_TPL, "attribution 行保留（休眠）"
        # klineEngine() 必须恒返回 echarts，并一次性清理存量 lwc 选择
        assert "localStorage.removeItem(KLINE_ENGINE_LS_KEY)" in SYMBOL_TPL, (
            "必须一次性收回存量用户可能已切到 lwc 的 localStorage 值"
        )
        assert "return 'echarts';" in SYMBOL_TPL, "冻结期 klineEngine() 恒返回 echarts"

    def test_vendor_assets_present(self):
        vendor = REPO / "src/quant_research_engine/gui/static/chart-core/vendor"
        assert (vendor / "lightweight-charts.standalone.production.js").is_file()
        assert (vendor / "LICENSE.lightweight-charts.txt").is_file(), "Apache-2.0 许可必须随包分发"
        assert (vendor / "brand-mark-white.png").is_file(), "深底反白品牌水印"
        assert (vendor / "brand-mark-color.png").is_file(), "浅底彩色品牌水印"

    def test_adapter_exports(self):
        for fn in ("toCandles", "toVolume", "toLineSeries", "toHistogram", "toMarkers",
                   "thresholdLines", "theme", "klineHeight", "THEME"):
            assert re.search(rf"\b{fn}\b", ADAPTER_JS), f"适配层缺少导出: {fn}"


# ---------------------------------------------------------------- 双引擎互斥
class TestKlineEngineExclusive:
    """QRE-SAAS-KLINE-ENGINE-EXCLUSIVE：#chart-kline 同时只能挂一个引擎实例。

    2026-10-28 线上 bug（用户验收时发现）：在个股详情里切到 TradingView 视图后，
    新图叠在旧 ECharts 图之上。根因：`renderKlineLwc()` 只调 `lwcDispose()`
    （只摘 LWC 自己的 DOM），从不清 ECharts 实例——`LWC.createChart(el)` 往同一个
    容器里再插一套 canvas，两个图就叠在一起。反向（lwc → echarts）当时只因为引擎
    开关处理器里手工补了一次 `lwcDispose()` 才没暴露。
    """

    DISPOSE_PATTERN = r"(let lwcChart = null[\s\S]*?)\n// 品牌水印随主题换图"

    def _dispose_src(self) -> str:
        m = re.search(self.DISPOSE_PATTERN, SYMBOL_TPL)
        assert m, "未找到 lwcDispose / klineDisposeEngines 源码区"
        return m.group(1)

    def test_dispose_tears_down_both_engines(self):
        """klineDisposeEngines 必须同时清 ECharts 实例、LWC 实例与容器残留节点。"""
        _node(r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const source = %SOURCE%;
// 容器里预先放两个"旧 canvas"节点：无论 getInstanceByDom 是否认得出实例，
// 清空后都不准残留——叠加 bug 的直接表现就是旧 canvas 还在。
const kids = [{tag: 'canvas'}, {tag: 'canvas'}];
const container = {
  get firstChild(){ return kids[0] || null; },
  removeChild(){ kids.shift(); },
};
let echartsDisposed = 0;
const echartsStub = {
  getInstanceByDom(el){ return el === container ? {dispose(){ echartsDisposed += 1; }} : null; },
};
const lwcChartStub = {
  unsubscribeCrosshairMove(){ throw new Error('不应抛错'); },
  remove(){ this.removed = (this.removed || 0) + 1; },
};
const ctx = {
  // 浏览器里 window.echarts 就是全局 echarts；vm 里没有这层代理，两边都要给
  console, echarts: echartsStub, window: {echarts: echartsStub}, __chartStub: lwcChartStub,
  $(sel){ return sel === '#chart-kline' ? container : null; },
  symbolKlineChart: {dispose(){ throw new Error('旧实例必须经 getInstanceByDom 走，不得留裸引用'); }},
};
const context = vm.createContext(ctx);
vm.runInContext(source, context);

// 场景 1：ECharts 静态图在场 → 切到 LWC 前必须 dispose 它并清空容器
vm.runInContext('klineDisposeEngines();', context);
assert.equal(echartsDisposed, 1, 'ECharts 实例必须被 dispose');
assert.equal(kids.length, 0, '容器必须清空，旧 canvas 不得残留');
assert.equal(context.symbolKlineChart, null, '旧 echarts 实例引用必须清掉');

// 场景 2：LWC 图在场 → 切回 ECharts 前必须 remove 它
// 注意：lwcChart 是源码里的 let 绑定（全局词法环境，不是 global 对象属性），
// 只能再用 runInContext 读，不能走 context.lwcChart
vm.runInContext('lwcChart = __chartStub; klineDisposeEngines();', context);
assert.equal(lwcChartStub.removed, 1, 'LWC 实例必须被 remove');
assert.equal(vm.runInContext('lwcChart === null', context), true, 'lwcChart 引用必须清掉');
""".replace("%SOURCE%", json.dumps(self._dispose_src())))

    def test_both_render_paths_and_switch_use_exclusive_dispose(self):
        """两个渲染入口与引擎开关都必须走 klineDisposeEngines，不得只清自己那侧。"""
        # renderKlineLwc：原来只调 lwcDispose()，是本次 bug 的直接根因
        lwc_body = re.search(
            r"function renderKlineLwc\(d\)\{[\s\S]*?\n\}", SYMBOL_TPL
        )
        assert lwc_body, "未找到 renderKlineLwc"
        assert "klineDisposeEngines()" in lwc_body.group(0), (
            "renderKlineLwc 必须清双引擎，否则 echarts → lwc 会叠加"
        )
        # renderKline：原来只 dispose echarts，反向切换会残留 LWC
        ec_body = re.search(r"function renderKline\(d\)\{[\s\S]*?\n\}", SYMBOL_TPL)
        assert ec_body, "未找到 renderKline"
        assert "klineDisposeEngines()" in ec_body.group(0), (
            "renderKline 必须清双引擎，否则 lwc → echarts 会叠加"
        )
        # 引擎开关处理器
        # T6 冻结：引擎开关处理器已移除，不得再有 setKlineEngine 调用点
        assert "setKlineEngine(" not in SYMBOL_TPL.replace(
            "function setKlineEngine(v){", ""), (
            "冻结期不得再有调用 setKlineEngine 的入口"
        )
        # 双引擎各自的旧调用点不得残留（replay 接管前的 lwcDispose 仍允许：
        # 重播恒为 echarts，只可能叠 LWC）
        # T6 冻结引擎开关后剩 3 处：定义 + renderKline + renderKlineLwc
        # （原第 4 处是引擎开关处理器，入口已按逆向侧 §4 决策移除）
        assert SYMBOL_TPL.count("klineDisposeEngines()") >= 3, (
            "定义 + 两个渲染入口至少 3 处"
        )


# ---------------------------------------------------------------- 图例开关回归
class TestLwcLegendToggle:
    """QRE-SAAS-LWC-LEGEND-TOGGLE：LWC DOM 图例的两个真 bug 回归。

    2026-10-28 用户实测（TradingView 视图下）：
    ① 成交量/买卖点默认开，点一次藏起来后再也点不回来——
       旧写法 `setChipState(key, on ? 'hidden' : (states[key] || 'pane'))` 在已隐藏时
       取到的 states[key] 就是 'hidden'，等于又设回 hidden，死锁。
    ② 技术因子点「取消显示」后该选项从图例里彻底消失，无法再选——
       旧写法从 plan.overlays/plan.panes 建图例，而 plan() 对 hidden 组直接 return，
       不进这两个数组，于是没有 pill 可点。
    """

    def _legend_src(self) -> str:
        m = re.search(r"function lwcRenderLegend\(plan, d\)\{[\s\S]*?\n\}", SYMBOL_TPL)
        assert m, "未找到 lwcRenderLegend"
        return m.group(0)

    def test_pill_restores_with_explicit_state_not_stale_hidden(self):
        """源码合同：点击显隐必须用传入的 restore 态，不得回读可能已是 hidden 的旧状态。"""
        src = self._legend_src()
        assert "setChipState(key, hiddenNow ? restore : 'hidden');" in src, (
            "必须实时读状态 + 显式 restore 态；回读创建时捕获的 on/states 会卡死"
        )
        assert "const hiddenNow = chipStates()[key] === 'hidden';" in src, (
            "点击时必须实时读当前状态，不得用闭包捕获的 on"
        )
        assert "states[key] || 'pane'" not in src, "旧死锁写法不得残留"
        # 三个可切换 pill 都必须传 restore
        for key in ("'__vol__'", "'__marks__'"):
            assert f"{key}, false, 'on'" in src, f"{key} 必须传 restore='on'"
        assert src.count(", false, c.states[0])") >= 2, (
            "overlay 与 pane chip 都必须传 restore=c.states[0]"
        )

    def test_legend_built_from_chips_not_visible_series(self):
        """源码合同：图例必须从 plan.chips 建（含隐藏组），不能从 overlays/panes 建。"""
        src = self._legend_src()
        assert "const chips = (plan && plan.chips) || [];" in src, "必须取 plan.chips"
        assert "(plan.overlays || []).forEach" not in src, (
            "不得从 plan.overlays 建图例——隐藏组不在其中，pill 会消失"
        )
        assert "(plan.panes || []).forEach" not in src, "不得从 plan.panes 建图例，同理"
        # 副图行显隐判据必须是「有 pane 类 chip」而非「有可见 pane」
        assert "const paneChips = chips.filter" in src, "副图行必须按 chip 数决定显隐"

    def test_toggle_roundtrip_in_vm(self):
        """Node vm 跑真实 lwcRenderLegend：藏 → 再点 → 必须回来，且 pill 不消失。"""
        _node(r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const src = %SRC%;
const store = {};
const els = {};
function makeEl(id){
  const e = {
    id, style: {}, children: [], childNodes: [], listeners: {}, attrs: {}, dataset: {}, _text: '',
    set innerHTML(v){ e._html = String(v); e.children = []; e.childNodes = []; },
    get innerHTML(){ return e._html || ''; },
    appendChild(n){
      e.children.push(n); e.childNodes.push(n);
      // 文本节点：真实 DOM 里 textContent 会拼接子文本节点
      if (n && typeof n.__text === 'string') e._text += n.__text;
      return n;
    },
    addEventListener(t, fn){ (e.listeners[t] = e.listeners[t] || []).push(fn); },
    setAttribute(k, v){ e.attrs[k] = String(v); },
    getAttribute(k){ return e.attrs[k] == null ? null : e.attrs[k]; },
  };
  Object.defineProperty(e, 'textContent', {
    get(){ return e._text; },
    set(v){ e._text = String(v); },
  });
  return e;
}
const document = {
  createElement(){ return makeEl('new'); },
  createTextNode(v){ return {__text: String(v)}; },
  getElementById(id){ return els[id] || (els[id] = makeEl(id)); },
};
const PLAN = {chips: [
  {key: 'ema_5', label: 'EMA5', kind: 'overlay', state: 'overlay', states: ['overlay', 'pane', 'hidden']},
  {key: 'ema_200', label: 'EMA200', kind: 'overlay', state: 'overlay', states: ['overlay', 'pane', 'hidden']},
  {key: 'macd_12_26_9', label: 'MACD', kind: 'pane', state: 'pane', states: ['pane', 'hidden']},
], overlays: [], panes: []};
const context = vm.createContext({
  console, document, PLAN,
  $(sel){ return document.getElementById(String(sel).replace(/^#/, '')); },
  chipStates(){
    const s = {};
    for (const k of Object.keys(store)) {
      if (k.indexOf('qre_fct_') === 0) s[k.slice('qre_fct_'.length)] = store[k];
    }
    return s;
  },
  setChipState(key, st){ store['qre_fct_' + key] = st; },
  klineEngine(){ return 'lwc'; },
  klineIsDark(){ return false; },
  kreplayCtl: null,
  klineData: null,
  renderKlineLwc(){},
  QRELwcAdapter: {
    theme(){ return {volume: '#B7A6E8', up: '#d43030'}; },
    lineColor(c){ return c; },
  },
  QREFactorLayout: {COLORS: {overlay: ['#E8A33D'], pane: '#6750A4'}},
});
vm.runInContext(src, context);

function render(){ vm.runInContext('lwcRenderLegend(PLAN, {})', context); }
// 叶子 pill：main/sub 两个 span 的 children 里，带 listeners 的即可切换项
function pills(){
  const box = els['kline-legend'];
  const out = [];
  box.children.forEach(function (row){
    row.children.forEach(function (b){
      if (b.className.indexOf('lg-static') < 0) out.push(b);
    });
  });
  return out;
}
function findPill(label){
  return pills().filter(function (b){ return b.textContent === label; })[0] || null;
}

render();
assert.equal(pills().length, 5, '初始 5 个可切换 pill，实际 ' + pills().length);
assert.ok(findPill('成交量'), '成交量 pill 必须在');
assert.ok(findPill('EMA5'), 'EMA5 pill 必须在');
assert.ok(findPill('MACD'), 'MACD pill 必须在');

// ① 成交量：藏 → pill 不消失 → 再点必须回来
assert.equal(findPill('成交量').getAttribute('aria-pressed'), 'true', '成交量默认开');
findPill('成交量').listeners.click[0]();
assert.equal(store['qre_fct___vol__'], 'hidden', '点击后必须写入 hidden');
render();
assert.ok(findPill('成交量'), '藏了之后 pill 不得消失');
assert.equal(findPill('成交量').getAttribute('aria-pressed'), 'false', '藏了之后 aria-pressed=false');
findPill('成交量').listeners.click[0]();
assert.notEqual(store['qre_fct___vol__'], 'hidden',
  '再点一次必须离开 hidden，实际 = ' + store['qre_fct___vol__']);
render();
assert.equal(findPill('成交量').getAttribute('aria-pressed'), 'true', '再点后必须重新显示');

// ② 技术因子：MACD 藏了之后 pill 还在，且能点回来
findPill('MACD').listeners.click[0]();
assert.equal(store['qre_fct_macd_12_26_9'], 'hidden', 'MACD 必须写入 hidden');
render();
assert.ok(findPill('MACD'), 'MACD 藏了之后 pill 不得从图例消失');
assert.equal(findPill('MACD').getAttribute('aria-pressed'), 'false');
findPill('MACD').listeners.click[0]();
assert.equal(store['qre_fct_macd_12_26_9'], 'pane',
  '再点必须回到第一个非隐藏态 pane，实际 = ' + store['qre_fct_macd_12_26_9']);
render();
assert.equal(findPill('MACD').getAttribute('aria-pressed'), 'true');

// ③ overlay chip 的 restore 态是 overlay（不是 pane）
findPill('EMA5').listeners.click[0]();
assert.equal(store['qre_fct_ema_5'], 'hidden');
render();   // 生产里由 renderKlineLwc 内部重建图例
findPill('EMA5').listeners.click[0]();
assert.equal(store['qre_fct_ema_5'], 'overlay',
  'overlay 组再点必须回 overlay，实际 = ' + store['qre_fct_ema_5']);

// ③b 不重建图例也能正确往返（实时读状态，陈旧闭包不会又写回 hidden）
for (const k of Object.keys(store)) delete store[k];
render();
const stale = findPill('成交量');
stale.listeners.click[0]();                    // 显 → 藏
assert.equal(store['qre_fct___vol__'], 'hidden');
stale.listeners.click[0]();                    // 同一个陈旧 pill 再点 → 必须回来
assert.notEqual(store['qre_fct___vol__'], 'hidden',
  '陈旧 pill 再点也必须离开 hidden，实际 = ' + store['qre_fct___vol__']);

// ④ 全部 pane chip 都藏了，副图行仍要保留（否则无处点回）
for (const k of Object.keys(store)) delete store[k];
store['qre_fct_macd_12_26_9'] = 'hidden';
render();
assert.ok(findPill('MACD'), '唯一 pane 被藏后副图行与 pill 仍须存在');

console.log('lwc-legend-toggle-ok');
""".replace("%SRC%", json.dumps(self._legend_src())))
