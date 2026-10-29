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
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SYMBOL_TPL = (
    REPO / "src/quant_research_engine/gui/saas/templates/symbol.html"
).read_text(encoding="utf-8")
REPLAY_JS = (REPO / "src/quant_research_engine/gui/static/replay.js").read_text(encoding="utf-8")
# QRE-KLINE-PANE-OPTION：harness 的 QREFactorLayout 桩直接跑真实源码，
# 避免桩与生产实现漂移（本项目已多次因桩窄于依赖而 VM 全绿、生产炸）
FACTOR_LAYOUT_JS = (
    REPO / "src/quant_research_engine/gui/static/factor-layout.js"
).read_text(encoding="utf-8")
# QRE-PRICE-SCALE（T2）：renderKline 的价格轴/末价标签/图例依赖它，注入真实源码
PRICE_SCALE_JS = (
    REPO / "src/quant_research_engine/gui/static/price-scale.js"
).read_text(encoding="utf-8")


def _node(script: str) -> None:
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    # 写临时文件而不是 `node -e <script>`：本文件有测试把整个 symbol.html
    # （已 107KB+）嵌进脚本，超过 Linux 单参数上限 MAX_ARG_STRLEN(128KB) 会
    # 直接 OSError: Argument list too long。用文件传参没有这个限制。
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(script)
        path = fh.name
    try:
        result = subprocess.run([node, path], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr or result.stdout
    finally:
        os.unlink(path)


def _dispose_source() -> str:
    """klineDisposeEngines（renderKline 的依赖，定义在 klineResizeBound 之前）。

    QRE-SAAS-KLINE-ENGINE-EXCLUSIVE：renderKline 渲染前必须经 klineDisposeEngines
    清掉同一容器上的旧 ECharts 实例，否则新图叠在旧图之上（2026-10-28 线上 bug）。
    R3-4（TV_ROUND3 §5）：LWC 试点整体移除，双引擎互斥退化为单引擎清理。
    """
    match = re.search(
        r"(// QRE-SAAS-KLINE-ENGINE-EXCLUSIVE[\s\S]*?\nfunction klineDisposeEngines\(\)\{[\s\S]*?\n\})",
        SYMBOL_TPL)
    assert match, "未找到 klineDisposeEngines"
    return match.group(1)


def _kline_block() -> str:
    """工具栏/信息条全部落在 klineResizeBound → 重播注释之前的区块内。

    QRE-SAAS-KLINE-ENGINE-EXCLUSIVE：该区块含 renderKline，而 renderKline 依赖
    klineDisposeEngines（定义在 klineResizeBound 之前），必须一并注入 vm。
    """
    match = re.search(r"(let klineResizeBound[\s\S]*?)(?=\n// --- K线级重播)", SYMBOL_TPL)
    assert match, "未找到 K 线静态区块"
    return _dispose_source() + "\n" + match.group(1)


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
    return _dispose_source() + "\n" + match.group(1)


def _media_block(query: str = "max-width:640px") -> str:
    """抽取 @media(query){...} 块内容（花括号配平，块内还有嵌套规则）。"""
    i = SYMBOL_TPL.find("@media(" + query + ")")
    assert i >= 0, f"缺少 {query} 断点"
    j = SYMBOL_TPL.find("{", i)
    depth, k = 0, j
    while k < len(SYMBOL_TPL):
        ch = SYMBOL_TPL[k]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return SYMBOL_TPL[j + 1 : k]
        k += 1
    raise AssertionError("media 块花括号不配平")


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

    def test_narrow_info_bar_no_truncation(self):
        """375 信息区：窄屏 .kline-ohlc 必须换行显示完整 OHLC/因子，不得 ellipsis 截断。"""
        block = _media_block()
        match = re.search(r"\.kline-ohlc\{([^}]*)\}", block)
        assert match, "窄屏断点必须覆盖 .kline-ohlc"
        rule = match.group(1).replace(" ", "")
        assert "white-space:normal" in rule, "窄屏信息区必须允许换行"
        assert "ellipsis" not in rule, "窄屏不得用 ellipsis 截断 OHLC/因子值"
        # 不横向溢出：主容器保留 min-width:0（flex 收缩），不断言固定宽度
        assert "min-width:0" in SYMBOL_TPL.replace(" ", ""), "kline-main 需 min-width:0 防溢出"
        # R-UI-001：不新增灰色小字备注（断点内不得引入 muted 文案规则）
        assert "var(--muted)" not in block, "不得借断点新增灰色小字备注"

    def test_drawing_tools_dom(self):
        """CR-2026-10-27 画线首片：趋势线/水平线/清除入口，样式与 aria/data-tip 合规。"""
        html = SYMBOL_TPL
        for kind, label in (("trend", "趋势线"), ("horizontal", "水平线"), ("clear", "清除画线")):
            button = re.search(r"<button[^>]*id=\"kt-%s\"[^>]*>" % kind, html)
            assert button, f"缺少画线按钮 kt-{kind}"
            tag = button.group(0)
            assert 'class="kline-tool"' in tag, f"kt-{kind} 必须复用 .kline-tool 样式"
            assert f'aria-label="{label}"' in tag, f"kt-{kind} 缺少 aria-label"
            assert "data-tip=" in tag, f"kt-{kind} 缺少 data-tip"
        assert html.count("<svg") >= 8, "8 个工具按钮均需内联 SVG 图标"
        # 工具栏区块不得出现灰色小字备注（R-UI-001）
        block = _tool_helpers()
        assert ".opt" not in block and "font-size:12px" not in block, "工具栏不得新增灰字备注"

    def test_drawing_helpers_declared(self):
        block = _kline_block()
        for fn in ("klinePixelToPoint", "klineDrawingSeries", "klineDrawToggleMode",
                   "klineDrawClear", "klineDrawApply", "klineDrawCancelMode"):
            assert f"function {fn}(" in block, f"缺少画线 helper: {fn}"

    def test_drawing_colors_use_existing_tokens(self):
        block = _kline_block()
        for token in ("#6750A4", "#8B7FBE"):
            assert token in block, f"画线颜色应复用既有 token: {token}"
        for bad in ("#FF0000", "#00FF00", "#0000FF", "rgb(255"):
            assert bad not in block, f"不得引入第四色相: {bad}"

    def test_right_axis_and_padding(self):
        block = _render_kline_source()
        assert "position: 'right'" in block, "价格/量轴必须右置"
        # R3-1（TV_ROUND3 §2）：grid 布局收敛到共享层 paneGrids——原先
        # klineGridSpec 是 paneGrids 的逐行复制第二份，改一处漏一处会漂移
        # （单 pane 高度 25% 就是这样漏过一轮的）。契约随之改为断言
        # 「委派共享层」+「共享层产出右留白」，比数字面量更防漂移。
        assert "QREFactorLayout.paneGrids(" in block, "klineGridSpec 必须委派共享层 paneGrids"
        assert "left: 16, right: 56" in FACTOR_LAYOUT_JS, "右侧标尺留白（共享层唯一实现）"
        # QRE-PRICE-SCALE（T2）：head 轴与轴宽预算必须走共享出口，不各写一份
        assert "klineHeadYAxes(" in block, "主图/量轴必须共用 klineHeadYAxes"
        assert "klineAxisRightPx()" in block, "右留白必须按价格轴标签宽度预算"
        # 逐轴右置由 _FACTOR_SCENARIO 的 option 断言覆盖（比数字面量更强）

    def test_no_forbidden_deps(self):
        """禁的是 CDN/外部**资源**依赖；LWC 是 vendored 本地文件，允许引用其全局名。
        attribution 外链（<a href>）是 Apache-2.0 合规要求，不算资源依赖。"""
        html = SYMBOL_TPL
        for bad in ("cdn.", "unpkg", "jsdelivr"):
            assert bad not in html, "不得引入外部依赖: %s" % bad
        # 资源加载（script src / link href）一律站内相对路径，不得走绝对 URL
        for m in re.finditer(r'<(?:script|link)\b[^>]*?(?:src|href)="([^"]*)"', html):
            url = m.group(1)
            assert not url.startswith(("http://", "https://", "//")), (
                "资源必须站内相对路径，不得走 CDN: " + url)
        # 凡是以路径形式出现的 LightweightCharts，必须指向 vendored 目录；
        # `window.LightweightCharts` 这类全局名引用是允许的（库已本地加载）
        for m in re.finditer(r"[\w./-]*LightweightCharts[\w./-]*", html):
            token = m.group(0)
            if "/" not in token:
                continue
            assert token.startswith("/static/chart-core/vendor/"), (
                "LightweightCharts 资源必须走 vendored 本地路径: " + token)

    def test_factor_contract_kept(self):
        block = _render_kline_source()
        assert "QREFactorLayout.plan(factors, chipStates(), paneOrder())" in block, \
            "renderKline 必须把副图顺序作为 plan 第三参"
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
// 真实 factor-layout.js（window  Shim 后自挂到 globalThis）
globalThis.window = globalThis;
%FACTOR_LAYOUT%
// QRE-PRICE-SCALE（T2）：同样注入**真实源码**——renderKline 的价格轴/末价标签/图例
// 都依赖它，用桩会重蹈"桩窄于依赖 → VM 全绿、生产炸"
%PRICE_SCALE%
const __QFL__ = globalThis.QREFactorLayout;
const __QPS__ = globalThis.QREPriceScale;

function makeEl(sel){
  const e = {
    sel: sel, style: {}, dataset: {}, disabled: false, attrs: {}, listeners: {}, textContent: '',
    firstChild: null, removeChild(){},
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
    // CR-2026-10-27 画线首片：像素→坐标转换与 zrender 点击（测试可注入 __pixel）
    convertFromPixel(finder, px){ return this.__pixel || null; },
    getZr(){
      if (!this.__zr) {
        this.__zr = { on(ev, fn){ (zrHandlers[ev] = zrHandlers[ev] || []).push(fn); } };
      }
      return this.__zr;
    },
    resize(){},
    dispose(){ this.disposed = true; },
    isDisposed(){ return this.disposed; },
    emit(ev, arg){ (this.handlers[ev] || []).forEach(function (fn) { fn(arg); }); },
  };
}

const zrHandlers = {};
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
    // plan 仍用测试夹具（各用例注入）；pane 映射函数一律用真实实现
    QREFactorLayout: Object.assign({}, __QFL__, {
      plan(){ return plan || { chips: [], panes: [], overlays: [] }; },
    }),
    // QRE-PRICE-SCALE（T2）：价格轴规格用真实实现（含 localStorage 里的 mode）
    QREPriceScale: __QPS__,
    QRETheme: { themeChart(){} },
    // CR-2026-10-28：renderKline 读 paneOrder()，harness 必须提供 localStorage
    // CR-2026-10-28：renderKline 读 paneOrder()，harness 提供可用的内存 localStorage
    localStorage: (function () {
      const store = {};
      return {
        getItem(k){ return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; },
        setItem(k, v){ store[k] = String(v); },
        removeItem(k){ delete store[k]; },
      };
    })(),
    chipStates(){ return {}; },
      // QRE-KLINE-PARAM-GRID（T5）：与 symbol.html::klinePlanFactors 同签名；
      // harness 无参数选择，等价于原样返回。参数应用逻辑由
      // tests/test_kline_param_grid.py 覆盖。
      klinePlanFactors(d){ return (d && d.factors) || []; },
    // CR-2026-10-28：setChipState 声明在 chip 区（kline 块之外），由 harness 提供
    setChipState(key, st){
      const ls = h0 && h0.localStorage;
      if (ls) ls.setItem('qre_fct_' + key, st);
    },
    renderFactorChips(){},
    f2(v){ return Number(v).toFixed(2); },
    requestAnimationFrame(fn){ return fn(); },
  };
  const h0 = { get localStorage(){ return ctx.localStorage; } };
  ctx.$ = q;
  return { ctx: vm.createContext(ctx), els: els, wins: winListeners, charts: charts, zrHandlers: zrHandlers };
}
"""

# QRE-KLINE-PANE-OPTION：定义处即注入真实 factor-layout.js，所有使用点自动生效
# （避免漏替换导致 ReferenceError: __FACTOR_LAYOUT__ is not defined）
# 注意：必须注入**原始源码**（不是 json.dumps 的字符串字面量，那不会执行）
_HARNESS = _HARNESS.replace("%FACTOR_LAYOUT%", FACTOR_LAYOUT_JS)
# QRE-PRICE-SCALE（T2）：同上，注入真实 price-scale.js
_HARNESS = _HARNESS.replace("%PRICE_SCALE%", PRICE_SCALE_JS)
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
// symbol.html 真实依赖 replay.js（共享高度 helper QREReplay.klineHeightForPanes）
vm.runInContext(%REPLAY% + '\nglobalThis.QREReplay = window.QREReplay;', h.ctx);
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
// symbol.html 真实依赖 replay.js（共享高度 helper QREReplay.klineHeightForPanes）
vm.runInContext(%REPLAY% + '\nglobalThis.QREReplay = window.QREReplay;', h.ctx);
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
            _HARNESS            + _MAIN_SCENARIO.replace("%SOURCE%", json.dumps(_render_kline_source()))
            .replace("%DATA%", json.dumps(_MAIN_DATA))
            .replace("%EMPTY_BAR%", json.dumps(_EMPTY_BAR_DATA))
            .replace("%REPLAY%", json.dumps(REPLAY_JS))
                    )
        _node(script)

    def test_factor_panes(self):
        script = (
            _HARNESS            + _FACTOR_SCENARIO.replace("%PLAN%", _FACTOR_PLAN_JSON)
            .replace("%SOURCE%", json.dumps(_render_kline_source()))
            .replace("%DATA%", json.dumps(_MAIN_DATA))
            .replace("%REPLAY%", json.dumps(REPLAY_JS))
                    )
        _node(script)

# ---------------------------------------------------------------- 画线首片（CR-2026-10-27）
_DRAW_BLOCK = json.dumps(_kline_block())

_DRAW_PIXEL_SCENARIO = r"""
const h = makeHarness(null);
const source = %DRAW_BLOCK%;
vm.runInContext(source, h.ctx);
const dates = ['2024-01-02', '2024-01-03', '2024-01-04'];
// 正常转换：像素 → 真实日期/价格（类别轴取整到最近一根）
const p1 = vm.runInContext('klinePixelToPoint(null, [10, 20], ' + JSON.stringify(dates) + ')', h.ctx);
assert.equal(p1, null, '无图表实例必须降级 null（不造点）');
const fake = { convertFromPixel(){ return [1.2, 11.55]; } };
Object.assign(h.ctx, { fake: fake });
const p2 = JSON.parse(JSON.stringify(vm.runInContext('klinePixelToPoint(fake, [10, 20], ' + JSON.stringify(dates) + ')', h.ctx)));
assert.deepEqual(p2, { index: 1, date: '2024-01-03', price: 11.55 }, '像素坐标转换为真实日期/价格');
// 越界索引（窗口外/未来）→ null
const out = { convertFromPixel(){ return [5, 11.5]; } };
Object.assign(h.ctx, { out: out });
assert.equal(vm.runInContext('klinePixelToPoint(out, [1, 1], ' + JSON.stringify(dates) + ')', h.ctx), null, '越界索引不得造点');
// 非有限价格 → null
const nanPrice = { convertFromPixel(){ return [1, NaN]; } };
Object.assign(h.ctx, { nanPrice: nanPrice });
assert.equal(vm.runInContext('klinePixelToPoint(nanPrice, [1, 1], ' + JSON.stringify(dates) + ')', h.ctx), null, '缺失价格不得造点');
// 转换抛错 → null
const broken = { convertFromPixel(){ throw new Error('x'); } };
Object.assign(h.ctx, { broken: broken });
assert.equal(vm.runInContext('klinePixelToPoint(broken, [1, 1], ' + JSON.stringify(dates) + ')', h.ctx), null, '转换异常必须降级');
// 空日期轴 → null
assert.equal(vm.runInContext('klinePixelToPoint(fake, [1, 1], [])', h.ctx), null, '无日期轴不得造点');
// 缺 convertFromPixel 的图表 → null
const noConv = {};
Object.assign(h.ctx, { noConv: noConv });
assert.equal(vm.runInContext('klinePixelToPoint(noConv, [1, 1], ' + JSON.stringify(dates) + ')', h.ctx), null, '缺转换能力必须降级');
console.log('draw-pixel-ok');
"""

_DRAW_SERIES_SCENARIO = r"""
const h = makeHarness(null);
const source = %DRAW_BLOCK%;
vm.runInContext(source, h.ctx);
const dates = ['2024-01-02', '2024-01-03', '2024-01-04'];
// 空/非法输入 → 空数组
assert.deepEqual(JSON.parse(JSON.stringify(vm.runInContext('klineDrawingSeries([], ' + JSON.stringify(dates) + ')', h.ctx))), []);
assert.deepEqual(JSON.parse(JSON.stringify(vm.runInContext('klineDrawingSeries(null, ' + JSON.stringify(dates) + ')', h.ctx))), []);
// 水平线：跨首末真实日期，价格为点击真实价格
const hs = JSON.parse(JSON.stringify(vm.runInContext('klineDrawingSeries([{kind: "horizontal", price: 11.5}], ' + JSON.stringify(dates) + ')', h.ctx)));
assert.equal(hs.length, 1);
assert.equal(hs[0].type, 'line');
assert.equal(hs[0].xAxisIndex, 0);
assert.equal(hs[0].yAxisIndex, 0);
assert.deepEqual(hs[0].data, [['2024-01-02', 11.5], ['2024-01-04', 11.5]], '水平线按真实首末日期与价格生成');
// 趋势线：两个真实点
const ts = JSON.parse(JSON.stringify(vm.runInContext('klineDrawingSeries([{kind: "trend", from: {date: "2024-01-02", price: 10}, to: {date: "2024-01-04", price: 12}}], ' + JSON.stringify(dates) + ')', h.ctx)));
assert.equal(ts.length, 1);
assert.deepEqual(ts[0].data, [['2024-01-02', 10], ['2024-01-04', 12]], '趋势线按两次点击的真实坐标生成');
// 缺价格/缺日期的画线跳过，不造点
const mixed = JSON.parse(JSON.stringify(vm.runInContext('klineDrawingSeries([{kind: "horizontal", price: NaN}, {kind: "trend", from: {date: "2024-01-02", price: 1}, to: null}], ' + JSON.stringify(dates) + ')', h.ctx)));
assert.equal(mixed.length, 0, '缺字段画线必须跳过');
console.log('draw-series-ok');
"""

_DRAW_FLOW_SCENARIO = r"""
const h = makeHarness(null);
const source = %DRAW_BLOCK%;
// symbol.html 真实依赖 replay.js（共享高度 helper QREReplay.klineHeightForPanes）
vm.runInContext(%REPLAY% + '\nglobalThis.QREReplay = window.QREReplay;', h.ctx);
vm.runInContext(source, h.ctx);
const d = %DATA%;
vm.runInContext('renderKline(' + JSON.stringify(d) + ')', h.ctx);
const chart = h.charts[h.charts.length - 1];
const dates = d.kline.dates;

// 水平线：一次点击确定价格
h.els['#kt-horizontal'].click();
assert.equal(vm.runInContext('klineDrawState.mode', h.ctx), 'horizontal', '进入水平线模式');
assert.equal(h.els['#kt-horizontal'].attrs['aria-pressed'], 'true', '模式按钮 aria-pressed');
chart.__pixel = [1, 11.5];
h.zrHandlers.click[0]({ offsetX: 10, offsetY: 20 });
assert.equal(vm.runInContext('klineDrawState.lines.length', h.ctx), 1, '点击后生成一条水平线');
assert.equal(vm.runInContext('klineDrawState.mode', h.ctx), null, '水平线一次点击后退出模式');
assert.equal(vm.runInContext('klineDrawState.lines[0].price', h.ctx), 11.5, '价格来自真实坐标转换');
assert.equal(vm.runInContext('klineDrawState.lines[0].date', h.ctx), dates[1], '日期来自真实坐标转换');
const lastOpt = chart.options[chart.options.length - 1];
const drawSeries = lastOpt.series.filter(s => s.name === '画线·水平');
assert.equal(drawSeries.length, 1, '画线进入 ECharts series');
assert.deepEqual(JSON.parse(JSON.stringify(drawSeries[0].data)), [[dates[0], 11.5], [dates[2], 11.5]], '水平线按真实首末日期渲染');
assert.ok(lastOpt.series.some(s => s.name === 'K线'), '基础 K 线序列不被画线替换');

// 像素无法转换时降级：不造点
h.els['#kt-horizontal'].click();
chart.__pixel = [9, 11.5];  // 越界索引
h.zrHandlers.click[0]({ offsetX: 1, offsetY: 1 });
assert.equal(vm.runInContext('klineDrawState.lines.length', h.ctx), 1, '无法转换不得造点');
assert.equal(vm.runInContext('klineDrawState.mode', h.ctx), 'horizontal', '降级后保持模式可重试');

// 趋势线：两次点击确定起点/终点
h.els['#kt-horizontal'].click();  // 再点一次取消水平线模式
assert.equal(vm.runInContext('klineDrawState.mode', h.ctx), null, '再次点击工具取消模式');
h.els['#kt-trend'].click();
chart.__pixel = [0, 10.0];
h.zrHandlers.click[0]({ offsetX: 1, offsetY: 1 });
assert.equal(vm.runInContext('klineDrawState.pending && klineDrawState.pending.date', h.ctx), dates[0], '第一次点击记起点');
chart.__pixel = [2, 12.0];
h.zrHandlers.click[0]({ offsetX: 2, offsetY: 2 });
assert.equal(vm.runInContext('klineDrawState.lines.length', h.ctx), 2, '第二次点击生成趋势线');
assert.equal(vm.runInContext('klineDrawState.mode', h.ctx), null, '趋势线完成后退出模式');
const trend = JSON.parse(JSON.stringify(vm.runInContext('klineDrawState.lines[1]', h.ctx)));
assert.equal(trend.kind, 'trend');
assert.equal(trend.from.date, dates[0]);
assert.equal(trend.to.date, dates[2]);
const trendOpt = chart.options[chart.options.length - 1];
const trendSeries = trendOpt.series.filter(s => s.name === '画线·趋势');
assert.deepEqual(JSON.parse(JSON.stringify(trendSeries[0].data)), [[dates[0], 10], [dates[2], 12]], '趋势线两个真实点');

// Esc 取消：进行中的趋势线不落点
h.els['#kt-trend'].click();
chart.__pixel = [1, 11.0];
h.zrHandlers.click[0]({ offsetX: 1, offsetY: 1 });
vm.runInContext('klineDrawOnKeydown({key: "Escape"})', h.ctx);
assert.equal(vm.runInContext('klineDrawState.mode', h.ctx), null, 'Esc 取消模式');
assert.equal(vm.runInContext('klineDrawState.pending', h.ctx), null, 'Esc 清掉未落点起点');
assert.equal(vm.runInContext('klineDrawState.lines.length', h.ctx), 2, 'Esc 不产生新画线');

// 清除画线：清空全部并回到基础序列
h.els['#kt-clear'].click();
assert.equal(vm.runInContext('klineDrawState.lines.length', h.ctx), 0, '清除全部画线');
const cleared = chart.options[chart.options.length - 1];
assert.ok(!cleared.series.some(s => String(s.name).indexOf('画线') === 0), '清除后无画线序列');
assert.ok(cleared.series.some(s => s.name === 'K线'), '清除后基础序列仍在');

// 非画线按键不影响模式
h.els['#kt-trend'].click();
vm.runInContext('klineDrawOnKeydown({key: "a"})', h.ctx);
assert.equal(vm.runInContext('klineDrawState.mode', h.ctx), 'trend', '非 Esc 按键不取消');
console.log('draw-flow-ok');
"""


class TestKlineDrawing:
    """CR-2026-10-27 画线首片：像素→真实坐标、配置生成、交互流、清除。"""

    def test_pixel_to_point_real_coordinates(self):
        _node(_HARNESS         + _DRAW_PIXEL_SCENARIO.replace("%DRAW_BLOCK%", _DRAW_BLOCK))

    def test_drawing_series_configs(self):
        _node(_HARNESS         + _DRAW_SERIES_SCENARIO.replace("%DRAW_BLOCK%", _DRAW_BLOCK))

    def test_drawing_click_flow(self):
        _node(
            _HARNESS            + _DRAW_FLOW_SCENARIO.replace("%DRAW_BLOCK%", _DRAW_BLOCK)
            .replace("%DATA%", json.dumps(_MAIN_DATA))
            .replace("%REPLAY%", json.dumps(REPLAY_JS))
                    )


# --------------------------------------------- 指标设置与面板管理（CR-2026-10-28）
_IND_SCENARIO = r"""
const h = makeHarness(null);
const source = %SOURCE%;
vm.runInContext(%REPLAY% + '\nglobalThis.QREReplay = window.QREReplay;', h.ctx);
vm.runInContext(source, h.ctx);

// 1) paneOrder 持久化：读 → 写 → 非法值降级
assert.equal(vm.runInContext('JSON.stringify(paneOrder())', h.ctx), '[]', '缺省为空数组');
vm.runInContext('setPaneOrder(["macd", "rsi"])', h.ctx);
assert.equal(vm.runInContext('paneOrder()', h.ctx).join(','), 'macd,rsi', '写入后可读回');
vm.runInContext('setPaneOrder(["macd", 123, null, "", "macd", "rsi"])', h.ctx);
assert.equal(vm.runInContext('paneOrder()', h.ctx).join(','), 'macd,rsi', '非字符串/空串/重复键被过滤');
// localStorage 不可用 / 内容损坏 → 空数组，不抛错
Object.assign(h.ctx, { localStorage: { getItem(){ throw new Error('blocked'); },
  setItem(){ throw new Error('blocked'); }, removeItem(){} } });
assert.equal(vm.runInContext('JSON.stringify(paneOrder())', h.ctx), '[]', 'localStorage 抛错时降级空数组');
vm.runInContext('setPaneOrder(["x"])', h.ctx);
Object.assign(h.ctx, { localStorage: { getItem(){ return '{bad json'; },
  setItem(){}, removeItem(){} } });
assert.equal(vm.runInContext('JSON.stringify(paneOrder())', h.ctx), '[]', '损坏 JSON 降级空数组');

// 2) movePane：按当前可见副图键上移/下移，越界不动
const store = {};
Object.assign(h.ctx, { localStorage: { getItem(k){ return store[k] == null ? null : store[k]; },
  setItem(k, v){ store[k] = String(v); }, removeItem(k){ delete store[k]; } } });
// stub 必须遵守 paneOrder（否则测的是假顺序）：列出的前置，未列出的按 a/b/c 相对序置后
const ALL_KEYS = ['a', 'b', 'c'];
Object.assign(h.ctx, { QREFactorLayout: Object.assign(Object.create(null), __QFL__, {
  plan(factors, states, order){
    const ord = (order || []).filter(k => ALL_KEYS.indexOf(k) >= 0);
    const rest = ALL_KEYS.filter(k => ord.indexOf(k) < 0);
    const keys = ord.concat(rest);
    return { panes: keys.map(k => ({key: k})), chips: keys.map(k => ({key: k})) };
  }, COLORS: {},
}) });
vm.runInContext('setPaneOrder(["a", "b", "c"])', h.ctx);
vm.runInContext('movePane("c", -1)', h.ctx);
assert.equal(vm.runInContext('paneOrder()', h.ctx).join(','), 'a,c,b', 'c 上移一位');
vm.runInContext('movePane("a", -1)', h.ctx);
assert.equal(vm.runInContext('paneOrder()', h.ctx).join(','), 'a,c,b', '已在首位：越界不动');
vm.runInContext('movePane("c", 1)', h.ctx);
assert.equal(vm.runInContext('paneOrder()', h.ctx).join(','), 'a,b,c', 'c 下移一位');
vm.runInContext('movePane("c", 1)', h.ctx);
assert.equal(vm.runInContext('paneOrder()', h.ctx).join(','), 'a,b,c', '已在末位：越界不动');
vm.runInContext('movePane("a", 1)', h.ctx);
assert.equal(vm.runInContext('paneOrder()', h.ctx).join(','), 'b,a,c', 'a 下移一位');
vm.runInContext('movePane("nope", -1)', h.ctx);
assert.equal(vm.runInContext('paneOrder()', h.ctx).join(','), 'b,a,c', '未知键不动');

// 3) hidePane：把该面板所有 chip 置 hidden（MACD 三线同键只写一次）
store['qre_fct_a'] = 'pane';
assert.equal(vm.runInContext('hidePane("a")', h.ctx), true, '存在的面板键必须返回 true');
assert.equal(store['qre_fct_a'], 'hidden', 'hidePane 必须写 hidden');
assert.equal(vm.runInContext('hidePane("nope")', h.ctx), false, '未知键不得写入');

// 4) renderKline 必须把 paneOrder 透传给 plan（第三参）
const seen = [];
Object.assign(h.ctx, { QREFactorLayout: Object.assign(Object.create(null), __QFL__, {
  plan(factors, states, order){ seen.push(order && order.slice ? order.slice() : order);
    return { chips: [], overlays: [], panes: [] }; },
  COLORS: { histUp: '#C93A3A', histDown: '#1E8E5A' },
}) });
vm.runInContext('setPaneOrder(["macd"])', h.ctx);
const d = {kline: {dates: ['2024-01-02'], ohlc: [[1, 1, 1, 1]], vols: [1]}, factors: [], orders: []};
vm.runInContext('renderKline(' + JSON.stringify(d) + ')', h.ctx);
assert.equal(seen.length, 1, 'renderKline 必须调用一次 plan');
assert.equal(seen[0].join(','), 'macd', 'paneOrder 必须作为 plan 第三参透传');
console.log('ind-flow-ok');
"""

_IND_SOURCE_CONTRACT = r"""
const assert = require('node:assert/strict');
const html = %HTML%;
// 工具栏入口：复用 .kline-tool 样式与 aria/data-tip 约定（R-UI-001：无灰字备注）
const btn = html.match(/<button[^>]*id="kt-ind"[^>]*>/);
assert.ok(btn, '缺少指标设置按钮 kt-ind');
assert.ok(btn[0].indexOf('class="kline-tool"') >= 0, 'kt-ind 必须复用 .kline-tool');
assert.ok(btn[0].indexOf('aria-label="指标"') >= 0, 'kt-ind 缺 aria-label');
assert.ok(btn[0].indexOf('data-tip=') >= 0, 'kt-ind 缺 data-tip');
assert.ok(html.indexOf('<svg') >= 0, '需要内联 SVG 图标');
// helper 声明
for (const fn of ['paneOrder', 'setPaneOrder', 'movePane', 'hidePane', 'klineIndicatorDialog']) {
  assert.ok(html.indexOf('function ' + fn + '(') >= 0, '缺少 helper: ' + fn);
}
// plan 第三参透传
assert.ok(html.indexOf('QREFactorLayout.plan(factors, chipStates(), paneOrder())') >= 0,
  'renderKline 必须把 paneOrder 作为 plan 第三参');
// 工具栏禁用集合包含 ind（重播时防未来数据）
assert.ok(/KLINE_TOOL_KINDS\s*=\s*\[[^\]]*'ind'[^\]]*\]/.test(html), 'KLINE_TOOL_KINDS 必须包含 ind');
// R-UI-001：指标面板不得新增灰色小字备注
const mask = html.indexOf('.ind-mask');
assert.ok(mask >= 0, '缺少指标面板样式 .ind-mask');
const css = html.slice(mask, mask + 1600);
assert.ok(css.indexOf('var(--card)') >= 0 && css.indexOf('var(--line)') >= 0, '指标面板必须复用主题 token');
assert.ok(css.indexOf('.opt') < 0, '指标面板不得引入 .opt 灰字备注');
console.log('ind-contract-ok');
"""


class TestIndicatorSettings:
    """CR-2026-10-28 指标设置与面板管理：持久化、排序、收起、DOM 合同。"""

    def test_source_contract(self):
        _node(_IND_SOURCE_CONTRACT.replace("%HTML%", json.dumps(SYMBOL_TPL)))

    def test_pane_order_and_management_flow(self):
        _node(_HARNESS               + _IND_SCENARIO.replace("%SOURCE%", json.dumps(_render_kline_source()))
              .replace("%REPLAY%", json.dumps(REPLAY_JS))
            )
