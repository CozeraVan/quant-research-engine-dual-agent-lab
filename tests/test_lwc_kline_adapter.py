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

assert.equal(A.klineHeight(0), 460, '无副图 460');
assert.equal(A.klineHeight(1), 580, '1 副图 420+160');
assert.equal(A.klineHeight(3), 900, '3 副图 420+480');
console.log('theme-height-ok');
""".replace("DETAIL()", json.dumps(DETAIL)))


# ---------------------------------------------------------------- 源码合同
class TestLwcSourceContract:
    def test_echarts_path_untouched(self):
        """ECharts 路径必须逐字节保留作回滚实现（既有 harness 断言依赖）。"""
        assert SYMBOL_TPL.count("echarts.init(") == 2, "实例数不变（静态 + 重播各一）"
        assert "color: '#C93A3A', color0: '#1E8E5A'" in SYMBOL_TPL
        assert "QREFactorLayout.plan(factors, chipStates(), paneOrder())" in SYMBOL_TPL

    def test_dual_engine_switch_and_dom(self):
        """双引擎开关 + 图例/attribution DOM + 两个 script src。"""
        assert "/static/chart-core/vendor/lightweight-charts.standalone.production.js" in SYMBOL_TPL
        assert "/static/chart-core/kline-lwc.js" in SYMBOL_TPL
        assert 'id="kline-legend"' in SYMBOL_TPL, "LWC 无图例，需要 DOM 图例"
        assert 'id="kline-attrib"' in SYMBOL_TPL, "attribution 行（品牌水印 + TradingView 链接）"
        assert "qre.kline.engine" in SYMBOL_TPL, "引擎开关 localStorage 键"
        assert "https://www.tradingview.com/" in SYMBOL_TPL, "attribution 链接"

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
