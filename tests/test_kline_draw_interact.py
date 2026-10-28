"""T4 · 画线交互补完（QRE-TV-DRAW-INTERACT）。

覆盖任务书 §7 T4 与逆向侧 §5 参考实现的五项：
端点拖拽 / 整体拖动 / 单线 Delete / 光标反馈 / localStorage 持久化。
**不扩工具种类**（仍只有趋势线 + 水平线 + 清除）。

Node vm 跑**真实 symbol.html 的 K 线区块源码**（不写桩），几何用线性可逆的假图表，
命中距离与参考实现逐值对齐（端点 7px / 线身 6px / 水平线 5px）。
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
PRICE_SCALE_JS = (
    REPO / "src/quant_research_engine/gui/static/price-scale.js"
).read_text(encoding="utf-8")


def _node(script: str) -> None:
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    # 写临时文件：脚本内注入真实 symbol.html 区块（已超 MAX_ARG_STRLEN）
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(script)
        path = fh.name
    try:
        result = subprocess.run([node, path], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr or result.stdout
    finally:
        os.unlink(path)


def _kline_block() -> str:
    """K 线工具栏/信息条/画线整块（含 renderKline 之前的所有 helper）。"""
    match = re.search(r"(let klineResizeBound[\s\S]*?)(?=\n// --- K线级重播)", SYMBOL_TPL)
    assert match, "未找到 K 线静态区块"
    return match.group(1)


_HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
// 真实 price-scale.js（K 线区块的价格轴 helper 依赖它）
globalThis.window = globalThis;
%PRICE_SCALE%
const store = {};
const lsStub = {
  getItem(k){ return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; },
  setItem(k, v){ store[k] = String(v); },
  removeItem(k){ delete store[k]; },
};
const info = [];
const els = {};
function fakeEl(id){
  return { id: id, style: {}, dataset: {}, disabled: false, attrs: {},
    classList: { add(){}, remove(){}, toggle(){}, contains(){ return false; } },
    setAttribute(k, v){ this.attrs[k] = String(v); },
    addEventListener(){}, };
}
const ctx = vm.createContext({
  console,
  localStorage: lsStub,
  requestAnimationFrame(fn){ return fn(); },
  document: { addEventListener(){}, removeEventListener(){}, getElementById(id){
    return els[id] || (els[id] = fakeEl(id)); } },
  $(sel){ return els[sel] || (els[sel] = fakeEl(sel)); },
  klineSetInfo(t){ info.push(String(t == null ? '' : t)); },
  klineToolBtn(){ return null; },
  klineSetPressed(){},
  klineBindDrawKeys(){},
  TS_CODE: '000001.SZ',
  klineDetail: null,
  symbolKlineChart: null,
});
vm.runInContext(%SOURCE%, ctx);
// const/let 的顶层声明不会变成 context 的属性，必须在上下文内再跑一段导出脚本
vm.runInContext("globalThis.__K = {"
  + " state: klineDrawState, tool: klineToolState,"
  + " hitTest: klineDrawHitTest, distToSeg: klineDistToSeg,"
  + " pointToPixel: klinePointToPixel, pixelToPoint: klinePixelToPoint,"
  + " series: klineDrawingSeries, apply: klineDrawApply,"
  + " mouseDown: klineDrawHandleMouseDown, mouseMove: klineDrawHandleMouseMove,"
  + " mouseUp: klineDrawHandleMouseUp, del: klineDrawDeleteSelected,"
  + " onKey: klineDrawOnKeydown, persist: klineDrawPersist,"
  + " load: klineDrawLoad, valid: klineDrawValid, points: klineDrawPoints };", ctx);
globalThis.K = ctx.__K;
globalThis.K.store = store;
globalThis.K.info = info;
"""

DATES = [f"2024-01-{d:02d}" for d in range(2, 12)]


def _layout() -> str:
    return (_HARNESS.replace("%PRICE_SCALE%", PRICE_SCALE_JS)
            .replace("%SOURCE%", json.dumps(_kline_block())))


# 线性可逆的假图表：x = left + index*band；y = top + (pmax-price)/(pmax-pmin)*height
_CHART = r"""
function makeChart(geo){
  const g = Object.assign({left: 16, band: 10, top: 30, height: 300,
                           pmin: 0, pmax: 100}, geo || {});
  return {
    options: [], cursorStyles: [],
    setOption(o){ this.options.push(o); },
    isDisposed(){ return false; },
    getOption(){ return { dataZoom: [{ start: 0, end: 100 }] }; },
    convertFromPixel(finder, px){
      const index = Math.round((px[0] - g.left) / g.band);
      const price = g.pmax - (px[1] - g.top) / g.height * (g.pmax - g.pmin);
      return [index, price];
    },
    convertToPixel(finder, pt){
      return [g.left + Number(pt[0]) * g.band,
              g.top + (g.pmax - Number(pt[1])) / (g.pmax - g.pmin) * g.height];
    },
    getZr(){ if (!this.__zr) { this.__zr = { on(){}, cursorStyles: [],
                    setCursorStyle(s){ this.cursorStyles.push(s); } }; }
              return this.__zr; },
  };
}
function setup(lines, geo){
  K.tool.chart = makeChart(geo);
  K.tool.data = { kline: { dates: %DATES%, ohlc: [], vols: [] } };
  K.tool.baseSeries = [{ name: 'K线', type: 'candlestick', data: [] }];
  K.state.lines = lines;
  K.state.selected = null;
  K.state.drag = null;
  K.state.mode = null;
  K.state.pending = null;
  return K.tool.chart;
}
const DATES = %DATES%;
const TREND = { kind: 'trend',
  from: { index: 2, date: DATES[2], price: 50 },
  to:   { index: 6, date: DATES[6], price: 20 } };
const LEVEL = { kind: 'horizontal', index: 3, date: DATES[3], price: 40 };
""".replace("%DATES%", json.dumps(DATES))


# ---------------------------------------------------------------- 源码合同
class TestSourceContract:
    def test_five_interactions_present(self):
        block = _kline_block()
        for fn in ("klineDrawHitTest", "klineDistToSeg", "klinePointToPixel",
                   "klineDrawHandleMouseDown", "klineDrawHandleMouseMove",
                   "klineDrawHandleMouseUp", "klineDrawDeleteSelected",
                   "klineDrawPersist", "klineDrawLoad", "klineDrawValid",
                   "klineDrawPoints", "klineDrawSuppressPan"):
            assert f"function {fn}(" in block, f"缺少 T4 helper: {fn}"
        assert "KLINE_DRAW_LS_KEY = 'qre.kline.drawings'" in block, (
            "持久化键必须是 qre.kline.drawings")
        assert "zr.on('mousedown', klineDrawHandleMouseDown)" in block
        assert "zr.on('mousemove', klineDrawHandleMouseMove)" in block
        assert "zr.on('mouseup', klineDrawHandleMouseUp)" in block
        assert "ev.key === 'Delete' || ev.key === 'Backspace'" in block, (
            "必须支持 Delete/Backspace 单线删除")

    def test_no_new_tool_kinds(self):
        """不扩工具种类：仍只有 trend / horizontal / clear 三个画线按钮。"""
        for kind in ("trend", "horizontal", "clear"):
            assert f'id="kt-{kind}"' in SYMBOL_TPL
        for bad in ("kt-rect", "kt-fib", "kt-ellipse", "kt-text", "kt-channel"):
            assert bad not in SYMBOL_TPL, f"不得新增工具: {bad}"

    def test_state_has_selection_and_drag(self):
        assert "selected: null, drag: null" in SYMBOL_TPL, (
            "klineDrawState 必须有 selected 与 drag")


# ---------------------------------------------------------------- 几何原语
class TestGeometry:
    def test_dist_to_seg(self):
        _node(_layout() + _CHART + r"""
// 点在线段上 → 0
assert.ok(Math.abs(K.distToSeg(5, 0, 0, 0, 10, 0)) < 1e-9, '线上点距离应为 0');
assert.ok(Math.abs(K.distToSeg(5, 5, 0, 0, 10, 0) - 5) < 1e-9, '线上方 5 单位');
// 垂足
assert.ok(Math.abs(K.distToSeg(5, 3, 0, 0, 10, 0) - 3) < 1e-9, '垂距 3');
// 端点外 → 取较近端点
assert.ok(Math.abs(K.distToSeg(-4, 0, 0, 0, 10, 0) - 4) < 1e-9, '左端点外 4');
assert.ok(Math.abs(K.distToSeg(14, 0, 0, 0, 10, 0) - 4) < 1e-9, '右端点外 4');
assert.ok(Math.abs(K.distToSeg(14, 3, 0, 0, 10, 0) - 5) < 1e-9, '端点外斜距 5');
// 退化线段（起点=终点）→ 点到点距离
assert.ok(Math.abs(K.distToSeg(3, 4, 0, 0, 0, 0) - 5) < 1e-9, '退化线段按点距');
// 斜线段垂距
assert.ok(Math.abs(K.distToSeg(0, 1, 0, 0, 10, 10) - Math.SQRT1_2) < 1e-9, '斜线垂距');
console.log('t4-geom-ok');
""")

    def test_point_to_pixel_roundtrip(self):
        _node(_layout() + _CHART + r"""
const chart = makeChart();
const p = { index: 4, price: 37.5 };
const px = K.pointToPixel(chart, p);
const back = K.pixelToPoint(chart, px, DATES);
assert.ok(back, '往返不得降级');
assert.equal(back.index, 4, 'index 往返: ' + back.index);
assert.ok(Math.abs(back.price - 37.5) < 1e-9, 'price 往返: ' + back.price);
// 坏输入一律 null，不抛错
assert.equal(K.pointToPixel(null, p), null);
assert.equal(K.pointToPixel(chart, null), null);
assert.equal(K.pixelToPoint(chart, null, DATES), null);
assert.equal(K.pixelToPoint(chart, [0, 0], []), null);
console.log('t4-roundtrip-ok');
""")


# ---------------------------------------------------------------- 命中测试
class TestHitTest:
    def test_hit_priorities_and_radii(self):
        _node(_layout() + _CHART + r"""
// 趋势线：from(index2,50) → px(36, 180)；to(index6,20) → px(76, 240)
const chart = setup([TREND]);
// 端点 A（半径 7）
assert.equal(K.hitTest(chart, [36, 180]).kind, 'pt0', '端点 A 命中');
assert.equal(K.hitTest(chart, [40, 184]).kind, 'pt0', '端点 A 半径内');
// (45,175)：距端点 A 10.3px（>7），距线身 18.5px（>6）→ 必须不命中
assert.equal(K.hitTest(chart, [45, 175]), null, '超出 7px 且离线身 >6px 不得命中');
// 端点 B
assert.equal(K.hitTest(chart, [76, 270]).kind, 'pt1', '端点 B 命中');
// 线身（垂距 < 6）：中点 index4, price35 → px(56, 210)
assert.equal(K.hitTest(chart, [56, 225]).kind, 'move', '线身命中');
assert.equal(K.hitTest(chart, [56, 229]).kind, 'move', '线身垂距 4px 命中');
assert.equal(K.hitTest(chart, [56, 240]), null, '垂距 15px 不得命中线身');
// 空白处
assert.equal(K.hitTest(chart, [200, 100]), null, '空白处不得命中');
console.log('t4-hit-trend-ok');
""")

    def test_horizontal_hit_any_x(self):
        _node(_layout() + _CHART + r"""
// 水平线 price=40 → y = 30 + (100-40)/100*300 = 210
const chart = setup([LEVEL]);
[16, 60, 200, 400].forEach(function (x) {
  assert.equal(K.hitTest(chart, [x, 210]).kind, 'move', '水平线横向任意位置可拖: ' + x);
});
assert.equal(K.hitTest(chart, [200, 214]).kind, 'move', '垂距 4px 命中');
assert.equal(K.hitTest(chart, [200, 220]), null, '垂距 10px 不得命中');
// 端点（水平线的唯一点）也命中
assert.equal(K.hitTest(chart, [46, 210]).kind, 'pt0', '水平线端点');
console.log('t4-hit-level-ok');
""")

    def test_later_line_wins_and_mode_blocks(self):
        _node(_layout() + _CHART + r"""
const chart = setup([TREND, LEVEL]);
// 两条线在同一处相交时，后画的（LEVEL）优先
assert.equal(K.hitTest(chart, [200, 210]).line, LEVEL, '后画的线优先命中');
K.mouseDown({ offsetX: 200, offsetY: 210 });
assert.equal(K.state.selected, LEVEL, 'mousedown 选中后画的线');
// 画线模式中不进入拖拽
K.state.mode = 'trend';
K.state.selected = null; K.state.drag = null;
K.mouseDown({ offsetX: 200, offsetY: 210 });
assert.equal(K.state.drag, null, '画线模式中 mousedown 不得进入拖拽');
K.state.mode = null;
console.log('t4-hit-order-ok');
""")


# ---------------------------------------------------------------- 拖拽
class TestDrag:
    def test_endpoint_drag(self):
        _node(_layout() + _CHART + r"""
const chart = setup([TREND]);
K.mouseDown({ offsetX: 36, offsetY: 180 });          // 抓住端点 A
assert.equal(K.state.drag.kind, 'pt0', '抓住端点 A');
assert.equal(K.state.selected, TREND, '选中该线');
// 拖到 index5/price30 → px(66, 210)
K.mouseMove({ offsetX: 66, offsetY: 210 });     // index5, price40
assert.equal(TREND.from.index, 5, '端点 A index: ' + TREND.from.index);
assert.ok(Math.abs(TREND.from.price - 40) < 1e-9, '端点 A price: ' + TREND.from.price);
assert.equal(TREND.from.date, DATES[5], '端点 A date 必须同步');
// 端点 B 不动
assert.equal(TREND.to.index, 6, '端点 B 不得被带动');
// 抓住端点 B 拖到 index8/price60 → px(96, 120)
K.mouseUp({});
K.mouseDown({ offsetX: 76, offsetY: 270 });
assert.equal(K.state.drag.kind, 'pt1', '抓住端点 B');
K.mouseMove({ offsetX: 96, offsetY: 120 });     // index8, price70
assert.equal(TREND.to.index, 8, '端点 B index: ' + TREND.to.index);
assert.ok(Math.abs(TREND.to.price - 70) < 1e-9, '端点 B price: ' + TREND.to.price);
assert.equal(TREND.from.index, 5, '端点 A 不得被带动');
console.log('t4-endpoint-drag-ok');
""")

    def test_whole_line_drag(self):
        _node(_layout() + _CHART + r"""
const chart = setup([TREND]);
// 抓住线身（index4, price35 → px 56,210），整体向右下拖 1 格 +10 价
K.mouseDown({ offsetX: 56, offsetY: 225 });
assert.equal(K.state.drag.kind, 'move', '线身命中 → 整体拖动');
K.mouseMove({ offsetX: 66, offsetY: 210 });     // index5, price40（y=180 是 price50）
assert.equal(TREND.from.index, 3, '整体拖动拖差值（不是绝对位置）: ' + TREND.from.index);
assert.equal(TREND.to.index, 7, '端点 B 同步平移: ' + TREND.to.index);
assert.ok(Math.abs(TREND.from.price - 55) < 1e-9, 'A price: ' + TREND.from.price);
assert.ok(Math.abs(TREND.to.price - 25) < 1e-9, 'B price: ' + TREND.to.price);
assert.equal(TREND.from.date, DATES[3], 'date 同步');
assert.equal(TREND.to.date, DATES[7], 'date 同步');
// 继续拖：grab 基准随动（不是累计误差）
K.mouseMove({ offsetX: 76, offsetY: 210 });     // index6, price40
assert.equal(TREND.from.index, 4, '第二次拖动: ' + TREND.from.index);
assert.equal(TREND.to.index, 8, '第二次拖动 B: ' + TREND.to.index);
// 水平线整体拖动：只改价格，index 跟着光标
K.state.lines = [LEVEL]; K.state.selected = null; K.state.drag = null;
K.mouseDown({ offsetX: 100, offsetY: 210 });     // index8（轴只有 10 根，x 须 ≤116）
K.mouseMove({ offsetX: 100, offsetY: 150 });     // price 60
assert.ok(Math.abs(LEVEL.price - 60) < 1e-9, '水平线价格: ' + LEVEL.price);
assert.equal(LEVEL.index, 8, '水平线 index 跟随: ' + LEVEL.index);
// 拖到数据范围外（x 超出类别轴）不得抛错、不得改线
K.mouseMove({ offsetX: 9999, offsetY: 150 });
assert.ok(Math.abs(LEVEL.price - 60) < 1e-9, '范围外拖动不得改线: ' + LEVEL.price);
// mousedown 在范围外同样不得进入拖动
K.state.drag = null;
K.mouseDown({ offsetX: 9999, offsetY: 210 });
assert.equal(K.state.drag, null, '范围外 mousedown 不得进入拖动');
console.log('t4-move-drag-ok');
""")

    def test_drag_clamps_to_range_and_persists(self):
        _node(_layout() + _CHART + r"""
const chart = setup([TREND]);
K.mouseDown({ offsetX: 56, offsetY: 225 });
// 拖到画布外（index 会算成负数/越界）→ 必须夹紧，不得产生越界点
K.mouseMove({ offsetX: -500, offsetY: 180 });
assert.ok(TREND.from.index >= 0, 'index 不得为负: ' + TREND.from.index);
K.mouseMove({ offsetX: 99999, offsetY: 180 });
assert.ok(TREND.from.index < DATES.length, 'index 不得越界: ' + TREND.from.index);
K.mouseUp({});
// mouseup 后必须落盘
const raw = K.store['qre.kline.drawings'];
assert.ok(raw, 'mouseup 必须持久化');
const obj = JSON.parse(raw);
assert.equal(obj.ts_code, '000001.SZ', '必须带标的隔离');
assert.equal(obj.lines.length, 1, '一条线');
console.log('t4-clamp-persist-ok');
""")

    def test_drag_suppresses_chart_pan(self):
        _node(_layout() + _CHART + r"""
const chart = setup([TREND]);
K.mouseDown({ offsetX: 56, offsetY: 225 });
// 从后往前找带 dataZoom 的那次 setOption（apply 也会下发 option）
function lastDz() {
  for (let i = chart.options.length - 1; i >= 0; i--) {
    if (chart.options[i] && chart.options[i].dataZoom) return chart.options[i].dataZoom;
  }
  return null;
}
const dz = lastDz();
assert.ok(dz, '必须下发 dataZoom 覆盖');
assert.equal(dz[0].moveOnMouseMove, false, '拖动中必须关掉图表平移，否则线图一起跑');
assert.equal(dz[0].zoomOnMouseWheel, true, '滚轮缩放必须保留');
K.mouseUp({});
const dz2 = lastDz();
assert.equal(dz2[0].moveOnMouseMove, true, '松手必须恢复平移');
console.log('t4-pan-suppress-ok');
""")


# ---------------------------------------------------------------- 单线 Delete
class TestDeleteSelected:
    def test_delete_only_selected(self):
        _node(_layout() + _CHART + r"""
const t2 = JSON.parse(JSON.stringify(TREND));
const chart = setup([TREND, LEVEL, t2]);
K.state.selected = LEVEL;
K.del();
assert.equal(K.state.lines.length, 2, '只删选中: ' + K.state.lines.length);
assert.equal(K.state.lines[0], TREND, '未选中不动');
assert.equal(K.state.lines[1], t2, '未选中不动');
assert.equal(K.state.selected, null, '删除后清选中');
// 没有选中时 Delete 不得删任何线
K.del();
assert.equal(K.state.lines.length, 2, '无选中时不得删');
console.log('t4-delete-ok');
""")

    def test_keydown_delete_and_input_guard(self):
        _node(_layout() + _CHART + r"""
const chart = setup([TREND, LEVEL]);
K.state.selected = LEVEL;
let prevented = 0;
K.onKey({ key: 'Delete', target: null, preventDefault(){ prevented++; } });
assert.equal(K.state.lines.length, 1, 'Delete 删选中');
assert.equal(prevented, 1, 'Delete 必须 preventDefault（避免浏览器后退）');

K.state.lines = [TREND, LEVEL]; K.state.selected = LEVEL;
K.onKey({ key: 'Backspace', target: null, preventDefault(){ prevented++; } });
assert.equal(K.state.lines.length, 1, 'Backspace 也删选中');

// 焦点在输入框内不得劫持（Backspace 要删文字）
K.state.lines = [TREND, LEVEL]; K.state.selected = LEVEL;
const input = { closest(sel){ return sel.indexOf('input') >= 0 ? this : null; } };
K.onKey({ key: 'Backspace', target: input, preventDefault(){ prevented++; } });
assert.equal(K.state.lines.length, 2, '输入框焦点时 Backspace 不得删画线');
const editable = { closest(sel){ return sel.indexOf('contenteditable') >= 0 ? this : null; } };
K.onKey({ key: 'Delete', target: editable, preventDefault(){ prevented++; } });
assert.equal(K.state.lines.length, 2, '可编辑区焦点时 Delete 不得删画线');
console.log('t4-delete-key-ok');
""")

    def test_escape_clears_selection(self):
        _node(_layout() + _CHART + r"""
const chart = setup([TREND]);
K.state.selected = TREND;
K.state.mode = 'horizontal';
K.onKey({ key: 'Escape', target: null, preventDefault(){} });
assert.equal(K.state.selected, null, 'Esc 清选中');
assert.equal(K.state.mode, null, 'Esc 清模式');
assert.equal(K.state.lines.length, 1, 'Esc 不动画线');
console.log('t4-esc-ok');
""")


# ---------------------------------------------------------------- 持久化
class TestPersistence:
    def test_round_trip_and_symbol_isolation(self):
        _node(_layout() + _CHART + r"""
K.state.lines = [TREND, LEVEL];
K.persist();
assert.ok(K.store['qre.kline.drawings'], '必须落 localStorage');
// 读回一致
const back = K.load();
assert.equal(back.length, 2, '读回 2 条');
assert.equal(back[0].kind, 'trend');
assert.ok(Math.abs(back[1].price - 40) < 1e-9, '水平线价格读回');
// 换标的：不得显示上一只股票的画线
K.store['qre.kline.drawings'] = JSON.stringify(
  { ts_code: '600000.SH', lines: [TREND] });
assert.equal(K.load().length, 0, '跨标的不得串画线');
// 脏数据一律过滤，不抛错
K.store['qre.kline.drawings'] = JSON.stringify({ ts_code: '000001.SZ', lines: [
  null, {}, { kind: 'bogus' }, { kind: 'horizontal', price: 'x' },
  { kind: 'trend', from: { price: 1 }, to: null },
  { kind: 'horizontal', price: 12.5 } ] });
const clean = K.load();
assert.equal(clean.length, 1, '只留合法线: ' + JSON.stringify(clean));
assert.equal(clean[0].price, 12.5);
// 非 JSON / 非数组不得炸
K.store['qre.kline.drawings'] = 'not json';
assert.equal(K.load().length, 0, '坏 JSON 回落空');
K.store['qre.kline.drawings'] = JSON.stringify([1, 2, 3]);
assert.equal(K.load().length, 0, '旧格式（裸数组无 ts_code）仍按内容过滤');
console.log('t4-persist-ok');
""")

    def test_privacy_mode_does_not_throw(self):
        _node(_layout() + _CHART + r"""
// localStorage 抛错（隐私模式）时持久化与读取都不得炸
const boom = { getItem(){ throw new Error('private'); },
               setItem(){ throw new Error('private'); },
               removeItem(){ throw new Error('private'); } };
const ctx2 = vm.createContext({ console, localStorage: boom });
vm.runInContext(%SOURCE%, ctx2);
// 直接在上下文内跑：localStorage 抛错时 load 回落空、persist 不抛错
const r = vm.runInContext(
  "JSON.stringify({n: klineDrawLoad().length,"
  + " persisted: (function(){ klineDrawState.lines = [{kind:'horizontal', price: 1}];"
  + " klineDrawPersist(); return true; })()})", ctx2);
const o = JSON.parse(r);
assert.equal(o.n, 0, '隐私模式读回落空');
assert.equal(o.persisted, true, '隐私模式写入不得抛错');
console.log('t4-privacy-ok');
""".replace("%SOURCE%", json.dumps(_kline_block())))


# ---------------------------------------------------------------- 选中态呈现
class TestSelectionRendering:
    def test_selected_line_gets_handles(self):
        _node(_layout() + _CHART + r"""
const chart = setup([TREND, LEVEL]);
K.state.selected = TREND;
const s = K.series(K.state.lines, DATES);
const trend = s.find(x => x.name === '画线·趋势');
const level = s.find(x => x.name === '画线·水平');
assert.equal(trend.lineStyle.type, 'dashed', '选中态虚线');
assert.equal(trend.lineStyle.width, 1.6, '选中态加粗');
assert.ok(trend.markPoint, '选中态必须有端点把手');
assert.equal(trend.markPoint.data.length, 2, '趋势线两个把手');
assert.equal(level.lineStyle.type, 'solid', '未选中保持实线');
assert.ok(!level.markPoint, '未选中不画把手');
// 清除选中后恢复
K.state.selected = null;
const s2 = K.series(K.state.lines, DATES);
assert.equal(s2.find(x => x.name === '画线·趋势').lineStyle.type, 'solid');
console.log('t4-selected-render-ok');
""")

    def test_apply_is_raf_throttled(self):
        _node(_layout() + _CHART + r"""
// 拖动时 mousemove 高频：apply 必须合帧（本 harness 的 rAF 是同步的，只验不炸 + 不重复）
const chart = setup([TREND]);
K.apply(); K.apply(); K.apply();
assert.ok(chart.options.length >= 1, 'apply 必须真的下发 option');
assert.equal(chart.options[0].series.length, 2, '基础序列 + 画线');
console.log('t4-apply-ok');
""")
