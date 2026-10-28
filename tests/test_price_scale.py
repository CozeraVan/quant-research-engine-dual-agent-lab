"""T2 · QREPriceScale：专业价格格式化框架的测试（TV_ROUND2 §7 T2）。

覆盖任务书 T2 的四条验收与 §4 规格表中的价格轴条目：
- priceScaleMode 0 普通 / 1 对数 / 2 百分比（可见区间首根为基准）/ 3 指数化；
- 自动精度 = minMove（数据比 minMove 更细时以数据为准）；
- 轴宽恒定（固定小数位 + 千分位 + 左对齐固定 margin + 按全量极值预算宽度）；
- 刻度 1-2-5 密度（含与 Python 等价实现逐值交叉验证，防 JS 侧重构漂移）。

纯函数层用 Node vm 跑**真实源码**（不写桩），避免"桩窄于依赖 → VM 全绿、生产炸"。
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PRICE_JS = (REPO / "src/quant_research_engine/gui/static/price-scale.js").read_text(
    encoding="utf-8"
)
SYMBOL_TPL = (
    REPO / "src/quant_research_engine/gui/saas/templates/symbol.html"
).read_text(encoding="utf-8")
REPLAY_JS = (REPO / "src/quant_research_engine/gui/static/replay.js").read_text(
    encoding="utf-8"
)


def _node(script: str) -> None:
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    # 写临时文件而不是 `node -e`：symbol.html 已 107KB+，超过 MAX_ARG_STRLEN(128KB)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(script)
        path = fh.name
    try:
        result = subprocess.run([node, path], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr or result.stdout
    finally:
        os.unlink(path)


_HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const src = %SOURCE%;
%EXTRA%
const ctx = { console, window: {}, module: undefined, exports: undefined,
              localStorage: (typeof lsStub === 'undefined' ? undefined : lsStub) };
vm.runInContext(src, vm.createContext(ctx));
const P = ctx.window.QREPriceScale;
globalThis.P = P;
"""


def _layout(extra: str = "") -> str:
    return _HARNESS.replace("%SOURCE%", json.dumps(PRICE_JS)).replace("%EXTRA%", extra)


# ---------------------------------------------------------------- 精度 = minMove
class TestPrecision:
    def test_precision_from_min_move(self):
        _node(_layout() + r"""
const cases = [[0.01, 2], [0.001, 3], [1, 0], [0.1, 1], [0.05, 2], [2.5, 1], [null, null],
               [0, null], [-1, null], ['', null], ['abc', null], [Infinity, null]];
cases.forEach(([mm, want]) => assert.equal(P.precisionFromMinMove(mm), want,
  'minMove ' + mm + ' → ' + P.precisionFromMinMove(mm) + '，期望 ' + want));
console.log('t2-minmove-ok');
""")

    def test_decimals_tolerates_float_noise(self):
        _node(_layout() + r"""
// 二进制尾差不得把精度放大到 17 位（0.1+0.2 在 IEEE754 下是 0.30000000000000004）
assert.ok(P.decimalsOf(0.1 + 0.2, 8) <= 2, '二进制尾差放大了精度: '
  + P.decimalsOf(0.1 + 0.2, 8));
assert.equal(P.decimalsOf(29.342, 8), 3);
assert.equal(P.decimalsOf(5, 8), 0);
assert.equal(P.decimalsOf(null, 8), 0);
assert.equal(P.decimalsOf(1 / 3, 8), 8, '无限小数截到 cap');
assert.equal(P.decimalsOf(0.012345, 8), 6);
console.log('t2-decimals-ok');
""")

    def test_auto_precision_minmove_is_authoritative(self):
        _node(_layout() + r"""
// minMove 是权威：qfq 复权价带 4~6 位小数也不得抬高轴精度（否则轴宽随复权因子跳动）
assert.equal(P.autoPrecision(0.01, [3, 4, 5]), 2, '整数行情按 A 股 minMove 出 2 位');
assert.equal(P.autoPrecision(0.01, [0.012345, 1.5]), 2, 'minMove 给了就不看数据小数位');
assert.equal(P.autoPrecision(0.001, [3.561]), 3, 'ETF 0.001 → 3 位');
// 未给 minMove 才按数据推断（因子副图口径）
assert.equal(P.autoPrecision(null, [1, 2, 3]), 0, '无 minMove 时纯按数据');
assert.equal(P.autoPrecision(null, [0.000123]), 6);
assert.equal(P.autoPrecision(null, [0.1, 0.25]), 2);
console.log('t2-auto-ok');
""")


# ---------------------------------------------------------------- 1-2-5 刻度
class TestNiceTicks:
    def test_ladder_is_1_2_5(self):
        _node(_layout() + r"""
const cases = [[3.561, 29.342, 6], [0.0012, 0.0043, 5], [-2.9457, 2.8675, 5],
               [10, 10000, 6], [0, 1, 5], [100, 101, 5], [-5, 5, 4]];
cases.forEach(([lo, hi, tgt]) => {
  const step = P.niceStep(lo, hi, tgt);
  assert.ok(step > 0, 'step 必须为正');
  const mant = step / Math.pow(10, Math.floor(Math.log(step) / Math.LN10));
  assert.ok([1, 2, 5, 10].some(m => Math.abs(mant - m) < 1e-9),
    'step ' + step + ' 不在 1-2-5 阶梯上');
  const ticks = P.niceTicks(lo, hi, tgt);
  assert.ok(ticks.length >= 2, '至少 2 个刻度');
  ticks.forEach(t => {
    assert.ok(t >= lo - step * 1e-6 && t <= hi + step * 1e-6, '刻度越界: ' + t);
  });
  // 相邻刻度间距恒等于 step（密度均匀）
  for (let i = 1; i < ticks.length; i++) {
    assert.ok(Math.abs((ticks[i] - ticks[i - 1]) - step) < step * 1e-6, '刻度间距不均');
  }
});
console.log('t2-ladder-ok');
""")

    def test_nice_ticks_match_python(self):
        """与 Python 等价实现逐值交叉验证（防 JS 侧重构漂移）。"""

        def py_nice_ticks(lo: float, hi: float, target: int = 5) -> list[float]:
            if not (hi > lo):
                return []
            step0 = (hi - lo) / max(2, target)
            mag = 10 ** math.floor(math.log10(step0))
            norm = step0 / mag
            mult = 1 if norm <= 1 else (2 if norm <= 2 else (5 if norm <= 5 else 10))
            step = mult * mag
            start = math.ceil(lo / step - 1e-9) * step
            out, v = [], start
            while v <= hi + step * 1e-6:
                out.append(0 if abs(v) < step * 1e-6 else round(v, 12))
                v += step
                if len(out) > 200:
                    break
            return out

        cases = [[3.561, 29.342, 6], [-2.9457, 2.8675, 5], [0.0012, 0.0043, 5],
                 [10, 10000, 6], [3597.57, 758930.67, 5]]
        expect = {f"{lo}|{hi}|{t}": py_nice_ticks(lo, hi, t) for lo, hi, t in cases}
        _node(_layout() + r"""
const CASES = %CASES%;
const EXPECT = %EXPECT%;
for (const k of Object.keys(EXPECT)) {
  const [lo, hi, t] = k.split('|').map(Number);
  const got = JSON.stringify(P.niceTicks(lo, hi, t));
  const want = JSON.stringify(EXPECT[k]);
  assert.equal(got, want, 'niceTicks 与 Python 不一致: ' + k + '\n  js  ' + got + '\n  py  ' + want);
}
console.log('t2-nice-py-ok');
""".replace("%CASES%", json.dumps(cases)).replace("%EXPECT%", json.dumps(expect)))


# ---------------------------------------------------------------- 值格式化
class TestFormatValue:
    def test_four_modes_and_thousands(self):
        _node(_layout() + r"""
// mode 0 普通：固定 2 位 + 千分位
assert.equal(P.formatValue(1234.5, {mode: 0, precision: 2}), '1,234.50');
assert.equal(P.formatValue(-1234.5, {mode: 0, precision: 2}), '-1,234.50');
assert.equal(P.formatValue(3.5, {mode: 0, minMove: 0.01}), '3.50');
assert.equal(P.formatValue(3.5, {mode: 0, precision: 2, thousands: false}), '3.50');
// mode 1 对数：轴类型不同，值格式化与普通一致
assert.equal(P.formatValue(1234.5, {mode: 1, precision: 2}), '1,234.50');
// mode 2 百分比：以基准首根为 0%
assert.equal(P.formatValue(110, {mode: 2, base: 100, precision: 2}), '10.00%');
assert.equal(P.formatValue(90, {mode: 2, base: 100, precision: 2}), '-10.00%');
assert.equal(P.formatValue(1234.5, {mode: 2, base: 100, precision: 2}), '1,134.50%');
// mode 3 指数化：首根 = 100
assert.equal(P.formatValue(110, {mode: 3, base: 100, precision: 2}), '110.00');
assert.equal(P.formatValue(55, {mode: 3, base: 100, precision: 2}), '55.00');
// base 可以是函数（可见区间首根，随缩放变化）
let base = 100;
assert.equal(P.formatValue(110, {mode: 2, base: () => base, precision: 2}), '10.00%');
base = 50;
assert.equal(P.formatValue(110, {mode: 2, base: () => base, precision: 2}), '120.00%');
// 缺失/异常一律 '—'，不造值
assert.equal(P.formatValue(null, {mode: 0}), '—');
assert.equal(P.formatValue('', {mode: 0}), '—');
assert.equal(P.formatValue(NaN, {mode: 0}), '—');
assert.equal(P.formatValue(Infinity, {mode: 0}), '—');
assert.equal(P.formatValue(110, {mode: 2, base: 0, precision: 2}), '—');
assert.equal(P.formatValue(110, {mode: 2, base: null, precision: 2}), '—');
assert.equal(P.formatValue(110, {mode: 3, base: 'x', precision: 2}), '—');
// 非法 mode 回落普通
assert.equal(P.formatValue(3.5, {mode: 99, precision: 2}), '3.50');
assert.equal(P.formatValue(3.5, {mode: -1, precision: 2}), '3.50');
console.log('t2-format-ok');
""")

    def test_axis_width_is_constant_across_windows(self):
        """轴宽按全量极值预算：任何可见窗口的最长标签都不得超出该宽度。"""
        _node(_layout() + r"""
// 价格跨 3 个数量级（0.5 → 5 → 5000）
const full = [];
for (let i = 0; i < 400; i++) full.push(0.5 * Math.pow(10, i / 130));
[0, 2, 3].forEach(mode => {
  const W = P.axisWidthPx(full, {mode: mode, precision: 2});
  assert.ok(W >= 40 && W <= 140, '轴宽越界: ' + W);
  const check = (win) => {
    const labels = P.candidateLabels(win, {mode: mode, precision: 2});
    const w = P.labelsWidthPx(labels);
    assert.ok(w.px <= W, 'mode ' + mode + ' 窗口最宽标签 ' + w.px + 'px 超出预算轴宽 '
      + W + 'px: ' + labels);
  };
  for (let s = 0; s < 400; s += 17) {
    for (const len of [5, 30, 120, 400]) {
      const win = full.slice(s, Math.min(400, s + len));
      if (!win.length) continue;
      check(win);
    }
  }
  // 同一份全量数据重复计算必须稳定（不随调用次序抖动）
  assert.equal(P.axisWidthPx(full, {mode: mode, precision: 2}), W);
});
console.log('t2-width-ok');
""")


# ---------------------------------------------------------------- ECharts 规格
class TestAxisSpecs:
    def test_price_axis_spec(self):
        _node(_layout() + r"""
const vals = [3.56, 4.2, 5.0, 29.34];
const ax = P.priceAxisSpec({values: vals, mode: 0, gridIndex: 0});
assert.equal(ax.type, 'value', '普通模式必须是 value 轴');
assert.equal(ax.position, 'right', '价格轴必须右置');
assert.equal(ax.gridIndex, 0);
assert.equal(ax.splitLine.show, true, '水平网格线必须画');
assert.ok(ax.axisLabel.width >= 40, '轴宽必须有预算');
assert.equal(ax.axisLabel.align, 'left', '标签左对齐 → 左边缘恒定');
assert.equal(ax.axisLabel.margin, 6, '右轴前 6px');
assert.equal(ax.axisLabel.formatter(1234.5), '1,234.50');
assert.equal(ax.axisLabel.formatter(3.561), '3.56');
// 数据小数位更多时，minMove 仍是权威（0.001 → 3 位）
const fine = P.priceAxisSpec({values: [3.561, 4.2, 29.342], mode: 0, gridIndex: 0,
                              minMove: 0.001});
assert.equal(fine.axisLabel.formatter(29.342), '29.342');

// mode 1 对数：正值数据 → log 轴
const log = P.priceAxisSpec({values: vals, mode: 1, gridIndex: 0});
assert.equal(log.type, 'log', '对数模式必须是 log 轴');
// 含非正值时不得用 log（ECharts log 轴要求 > 0），回落 value
const bad = P.priceAxisSpec({values: [-1, 2, 3], mode: 1, gridIndex: 0});
assert.equal(bad.type, 'value', '非正数据必须回落 value 轴');

// mode 2/3：formatter 走 base（可见区间首根）
const pct = P.priceAxisSpec({values: vals, mode: 2, base: 4.2, gridIndex: 0});
assert.equal(pct.type, 'value');
assert.equal(pct.axisLabel.formatter(4.62), '10.00%');
const idx = P.priceAxisSpec({values: vals, mode: 3, base: 4.2, gridIndex: 0});
assert.equal(idx.axisLabel.formatter(4.2), '100.00');
console.log('t2-axis-ok');
""")

    def test_last_price_mark_line(self):
        _node(_layout() + r"""
const ml = P.lastPriceMarkLine(29.342, {mode: 0, precision: 2, color: '#6750A4'});
assert.equal(ml.data.length, 1);
assert.ok(Math.abs(ml.data[0].yAxis - 29.342) < 1e-9, '末价标签必须挂在末根收盘上');
assert.equal(ml.label.backgroundColor, '#6750A4', '末价标签必须带背景块');
assert.equal(ml.label.position, 'end');
assert.equal(ml.label.formatter(), '29.34');
assert.equal(ml.silent, true, '末价标签不得吃鼠标事件');
// 百分比模式下标签随基准变化
let base = 26;
const ml2 = P.lastPriceMarkLine(29.342, {mode: 2, base: () => base, precision: 2});
assert.equal(ml2.label.formatter(), '12.85%');
base = 29.342;
assert.equal(ml2.label.formatter(), '0.00%');
console.log('t2-lastprice-ok');
""")

    def test_crosshair_and_legend_spec(self):
        _node(_layout() + r"""
const ch = P.crosshairSpec({});
assert.equal(ch.lineStyle.type, 'dashed', '十字光标必须 1px 虚线');
assert.equal(ch.crossStyle.type, 'dashed');
assert.equal(ch.lineStyle.width, 1);
assert.ok(ch.label.backgroundColor, '价格/时间标签必须带背景块');
assert.equal(JSON.stringify(ch.link), '[{"xAxisIndex":"all"}]', 'x 轴必须全联动');

const lg = P.legendSpec({data: ['K线', '成交量'], selected: {'K线': true},
                         formatter: n => n + ' 1.00'});
assert.equal(lg.icon, 'circle', '图例必须是圆点');
assert.equal(lg.itemWidth, 8);
assert.equal(lg.top, 0);
assert.equal(lg.left, 0);
assert.equal(lg.formatter('K线'), 'K线 1.00');

const ca = P.categoryAxisSpec({data: ['2024-01-02'], gridIndex: 0});
assert.equal(ca.splitLine.show, false, '类别轴不得画竖网格线');
console.log('t2-cross-legend-ok');
""")


# ---------------------------------------------------------------- 模式持久化
class TestModePersistence:
    def test_mode_round_trip_and_cycle(self):
        # localStorage 必须注入 **vm 上下文**（宿主 globalThis 对 vm 内代码不可见）
        stub = ("\nconst store = {};\n"
                "const lsStub = {\n"
                "  getItem: k => (Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null),\n"
                "  setItem: (k, v) => { store[k] = String(v); },\n"
                "  removeItem: k => { delete store[k]; },\n"
                "};\n")
        _node(_layout(stub) + r"""
assert.equal(P.readMode(), 0, '缺省普通模式');
[0, 1, 2, 3].forEach(m => {
  assert.equal(P.setMode(m), m);
  assert.equal(P.readMode(), m, 'mode ' + m + ' 必须可持久化');
  assert.equal(lsStub.getItem('qre.kline.priceScaleMode'), String(m), '必须落 localStorage');
});
assert.equal(P.setMode(99), 0, '非法 mode 回落 0');
assert.equal(P.readMode(), 0);
assert.equal(P.setMode('2'), 2, '字符串 mode 必须可解析');
assert.equal(P.readMode(), 2);
// 隐私模式（localStorage 抛错）不得炸，只回落默认态
lsStub.setItem = () => { throw new Error('private mode'); };
assert.equal(P.readMode(), 2, '读失败时回落上次内存值/默认');
assert.equal(P.setMode(1), 1, '写失败不抛错');
// 循环 0→1→2→3→0
let m = 0;
const seq = [];
for (let i = 0; i < 5; i++) { m = P.nextMode(m); seq.push(m); }
assert.deepEqual(seq, [1, 2, 3, 0, 1], '模式循环顺序错误: ' + seq);
console.log('t2-mode-ok');
""")


# ---------------------------------------------------------------- 源码合同
class TestSourceContract:
    def test_module_exports(self):
        for fn in ("modeOf", "precisionFromMinMove", "autoPrecision", "niceTicks",
                   "formatValue", "axisWidthPx", "axisLabelSpec", "priceAxisSpec",
                   "lastPriceMarkLine", "crosshairSpec", "legendSpec",
                   "categoryAxisSpec", "readMode", "setMode", "nextMode"):
            assert f"{fn}:" in PRICE_JS, f"price-scale.js 缺导出 {fn}"

    def test_symbol_html_wires_price_scale(self):
        assert "/static/price-scale.js" in SYMBOL_TPL, "symbol.html 必须引入 price-scale.js"
        assert "QREPriceScale.priceAxisSpec(" in SYMBOL_TPL, "主图价格轴必须走共享规格"
        assert "QREPriceScale.lastPriceMarkLine(" in SYMBOL_TPL, "必须有末价标签"
        assert "QREPriceScale.crosshairSpec(" in SYMBOL_TPL, "十字光标必须走共享规格"
        assert "QREPriceScale.legendSpec(" in SYMBOL_TPL, "图例必须走共享规格"
        assert "kt-pscale" in SYMBOL_TPL, "必须有价格轴模式入口"

    def test_replay_js_consumes_axis_label_spec(self):
        """重播的 yAxis 必须能接 axisLabel（对象或函数），不自己拼格式化。"""
        assert "y.axisLabel" in REPLAY_JS, "replay.js 必须支持调用方下发的 axisLabel"

    def test_no_manual_pane_index_in_symbol(self):
        for bad in ("yAxisIndex: 2 + i", "xAxisIndex: 2 + i", "gridIndex: 2 + i",
                    "grid: 2 + i", "yAxisIndex: paneIndex + 2"):
            assert bad not in SYMBOL_TPL, f"symbol.html 仍手写 pane 索引: {bad}"
