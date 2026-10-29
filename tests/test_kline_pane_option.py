"""T1 · QRE-KLINE-PANE-OPTION：共享 option 映射层的测试。

覆盖任务书 §7 T1 的四条验收：
① symbol.html / replay.js / game.html 三处都调它；
② 三处对同一份数据的 option diff 为空；
③ 每 pane 满足 yAxis.length === grid.length；
④ §3 判据输出（MACD 三 series yAxisIndex 与 px 相同）。

另加：与 Python 侧等价实现交叉验证 pane 网格布局；不变式被破坏时必须抛错
（宁可炸在开发期，不 silent 错位）。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LAYOUT_JS = (REPO / "src/quant_research_engine/gui/static/factor-layout.js").read_text(
    encoding="utf-8"
)
SYMBOL_TPL = (
    REPO / "src/quant_research_engine/gui/saas/templates/symbol.html"
).read_text(encoding="utf-8")
GAME_TPL = (REPO / "src/quant_research_engine/game/templates/game.html").read_text(
    encoding="utf-8"
)
REPLAY_JS = (REPO / "src/quant_research_engine/gui/static/replay.js").read_text(
    encoding="utf-8"
)

# 同一份测试数据：2 overlay + MACD 三列组 + 1 独立 RSI pane
PANES = [
    {"key": "macd_", "name": "MACD", "thresholds": [0], "series": [
        {"name": "macd_dif", "type": "line", "values": [0.1, 0.5, -0.3, 0.8], "color": "#6750A4"},
        {"name": "macd_dea", "type": "line", "values": [0.05, 0.2, -0.1, 0.4], "color": "#E8A33D"},
        {"name": "macd_hist", "type": "bar", "values": [0.05, 0.3, -0.2, 0.4], "hist": True},
    ]},
    {"key": "rsi_14", "name": "RSI", "thresholds": [30, 70], "series": [
        {"name": "rsi_14", "type": "line", "values": [40, 55, 62, 48], "color": "#6750A4"},
    ]},
]
DATES = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]


def _node(script: str) -> None:
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    with __import__("tempfile").NamedTemporaryFile(
        "w", suffix=".js", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(script)
        path = fh.name
    try:
        result = subprocess.run([node, path], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr or result.stdout
    finally:
        Path(path).unlink(missing_ok=True)


_HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const src = %SOURCE%;
const ctx = { console, window: {}, module: undefined, exports: undefined };
const context = vm.createContext(ctx);
vm.runInContext(src, context);
const L = context.window.QREFactorLayout;
globalThis.L = L;
"""


def _layout() -> str:
    return _HARNESS.replace("%SOURCE%", json.dumps(LAYOUT_JS))


# ---------------------------------------------------------------- 验收①：三处都调它
class TestThreeCallSites:
    def test_symbol_html_calls_shared_exit(self):
        """symbol.html 静态图与重播两条路径都必须调 panesToOption。"""
        assert SYMBOL_TPL.count("QREFactorLayout.panesToOption(") >= 2, (
            "renderKline 与 mountKlineReplay 两条路径都要调 panesToOption"
        )

    def test_game_html_calls_shared_exit(self):
        assert "QREFactorLayout.panesToOption(" in GAME_TPL, "game.html 必须调 panesToOption"
        assert "/static/factor-layout.js" in GAME_TPL, "game.html 必须引入 factor-layout.js"

    def test_replay_js_consumes_shared_grid_index(self):
        """replay.js 本身按调用方 s.grid 位置映射（安全）；其规格由 symbol.html
        经 panesToOption(style:'replay') 生成，故 replay 路径同样单一来源。"""
        assert "xAxisIndex: s.grid || 0, yAxisIndex: s.grid || 0" in REPLAY_JS, (
            "replay.js 的索引映射应保持位置式（不由它算 2+i）"
        )
        assert "style: 'replay'" in SYMBOL_TPL, "symbol 必须用 replay 规格生成 pane series"

    def test_no_manual_pane_index_left(self):
        """三处业务页不得再出现手写 pane 索引（2+i / paneIndex+2 / index-2）。"""
        for name, tpl in (("symbol.html", SYMBOL_TPL), ("game.html", GAME_TPL)):
            for bad in ("yAxisIndex: 2 + i", "xAxisIndex: 2 + i", "yAxisIndex: paneIndex + 2",
                        "xAxisIndex: paneIndex + 2", "gridIndex: 2 + i", "grid: 2 + i",
                        "model.panes[index - 2]"):
                assert bad not in tpl, f"{name} 仍残留手写 pane 索引: {bad}"


# ---------------------------------------------------------------- 验收②③：diff 与不变式
class TestSharedOptionMapping:
    def test_three_call_sites_produce_identical_pane_option(self):
        """同一份 panes + 同一份 grids → 三处调用产出的 pane option 必须逐字节相同。

        做法：在 vm 里分别用 ECharts 规格与 replay 规格各跑一次 panesToOption，
        并让 game 也跑 ECharts 规格；比对 ECharts 规格两次输出的 JSON。
        """
        _node(_layout() + r"""
const panes = %PANES%;
const grids = L.paneGrids(panes.length, {showVol: true, showFct: true});
const head = [
  { type: 'value', gridIndex: 0, scale: true, position: 'right' },
  { type: 'value', gridIndex: 1, show: true, position: 'right', name: '量' },
];
// 模拟 symbol.html 的调用
const a = L.panesToOption(panes, {paneBase: 2, grids, dates: %DATES%,
  axisLabelIndex: L.axisLabelIndex(panes.length, {showVol: true, showFct: true}),
  showFct: true, headYAxes: head,
  histColors: {up: '#C93A3A', down: '#1E8E5A'}});
// 模拟 game.html 的调用（head 形状不同，但 pane 部分必须一致）
const b = L.panesToOption(panes, {paneBase: 2, grids, showFct: true,
  headYAxes: [
    {type: 'value', gridIndex: 0, scale: true, splitNumber: 4, name: ''},
    {type: 'value', gridIndex: 1, scale: true, splitNumber: 4, name: ''},
  ],
  histColors: {up: '#8B7FBE', down: '#8B7FBE'}});
// pane 的 yAxis 与 series 必须与 head 形状无关（只差 name/配色由 spec 决定的部分）
const strip = o => JSON.stringify({yAxis: o.yAxis.slice(2), series: o.series});
assert.equal(strip(a), strip(b), 'symbol 与 game 的 pane option 不一致');

// replay 规格：series 的 grid 下标必须与 ECharts 规格的 yAxisIndex 一致
const r = L.panesToOption(panes, {paneBase: 2, grids, style: 'replay', showFct: true,
  headYAxes: [{name: ''}, {name: '量'}],
  histColors: {up: '#C93A3A', down: '#1E8E5A'}});
const ecIdx = a.series.map(s => s.yAxisIndex);
const rpIdx = r.series.map(s => s.grid);
assert.deepEqual(ecIdx, rpIdx, 'replay 规格的 grid 下标与 ECharts 规格的 yAxisIndex 不一致');
assert.deepEqual(r.yAxis.map(y => y.name), ['', '量', 'MACD', 'RSI'], 'replay yAxes 名称不对');

// 不变式：yAxis.length === grid.length，且逐 pane 一一对应
assert.equal(a.yAxis.length, a.grid.length, 'yAxis/grid 数量不等');
for (let i = 0; i < panes.length; i++) {
  assert.equal(a.yAxis[2 + i].gridIndex, 2 + i, 'pane ' + i + ' gridIndex 错位');
  assert.equal(a.grid[2 + i] != null, true, 'pane ' + i + ' 缺 grid');
}
console.log('t1-shared-ok');
""".replace("%PANES%", json.dumps(PANES)).replace("%DATES%", json.dumps(DATES)))

    def test_macd_three_series_share_one_axis(self):
        """验收④：MACD 三 series 必须共用同一 yAxisIndex/gridIndex（§3 判据的静态版）。"""
        _node(_layout() + r"""
const panes = %PANES%;
const o = L.panesToOption(panes, {paneBase: 2,
  grids: L.paneGrids(panes.length, {showVol: true, showFct: true}),
  dates: %DATES%, showFct: true,
  headYAxes: [{type: 'value', gridIndex: 0}, {type: 'value', gridIndex: 1}],
  histColors: {up: '#C93A3A', down: '#1E8E5A'}});
const macd = o.series.filter(s => /^macd_/.test(s.name));
assert.equal(macd.length, 3, 'MACD 应 3 个 series，实际 ' + macd.length);
const idx = [...new Set(macd.map(s => s.yAxisIndex))];
const gidx = [...new Set(macd.map(s => s.gridIndex === undefined ? s.xAxisIndex : s.gridIndex))];
assert.deepEqual(idx, [2], 'MACD 三 series 的 yAxisIndex 必须同为 2，实际 ' + idx);
assert.deepEqual(gidx, [2], 'MACD 三 series 的 gridIndex 必须同为 2，实际 ' + gidx);
// HIST 必须是 bar，DIF/DEA 必须是 line
const byName = {}; macd.forEach(s => { byName[s.name] = s.type; });
assert.equal(byName['macd_hist'], 'bar', 'HIST 必须是柱');
assert.equal(byName['macd_dif'], 'line', 'DIF 必须是线');
assert.equal(byName['macd_dea'], 'line', 'DEA 必须是线');
console.log('t1-macd-ok');
""".replace("%PANES%", json.dumps(PANES)).replace("%DATES%", json.dumps(DATES)))

    def test_invariant_violation_throws(self):
        """headYAxes 数量与 paneBase 不符 → 必须抛错（不 silent 错位）。"""
        _node(_layout() + r"""
const panes = %PANES%;
let threw = 0;
try {
  L.panesToOption(panes, {paneBase: 3,   // 声称前面有 3 个 grid，但只给 2 个 head
    grids: L.paneGrids(panes.length, {showVol: true, showFct: true}),
    showFct: true,
    headYAxes: [{type: 'value', gridIndex: 0}, {type: 'value', gridIndex: 1}]});
} catch (e) {
  threw = 1;
  assert.ok(/QRE-KLINE-PANE-OPTION/.test(e.message),
    '应由 panesToOption 的不变式校验抛错: ' + e.message);
}
assert.equal(threw, 1, 'paneBase 与 headYAxes 不符必须抛错');
console.log('t1-invariant-ok');
""".replace("%PANES%", json.dumps(PANES)))


# ---------------------------------------------------------------- 与 Python 交叉验证
class TestPaneGridsAgainstPython:
    """paneGrids 的百分比布局与 Python 等价实现逐值一致（防 JS 侧重构漂移）。"""

    def test_pane_grids_match_python(self):
        # Python 侧按共享层 paneGrids 逐行转写（R3-1 起它是唯一实现；
        # symbol.html::klineGridSpec 只是签名适配壳）
        def py_pane_grids(n: int, show_vol: bool = True, show_fct: bool = True):
            f_on = bool(show_fct) and n > 0
            hide = {"left": 16, "right": 56, "top": 0, "height": 1}
            grids = [{"left": 16, "right": 56, "top": 30,
                      "height": "42%" if (f_on and show_vol) else
                                ("50%" if f_on else ("58%" if show_vol else "78%"))}]
            if not show_vol:
                grids.append(dict(hide))
            elif f_on:
                grids.append({"left": 16, "right": 56, "top": "53%", "height": "10%"})
            else:
                grids.append({"left": 16, "right": 56, "top": "74%", "height": "14%"})
            f_top = 66 if (f_on and show_vol) else 58
            step = (93 - f_top) / n if n else 0
            # R3-1（TV_ROUND3 §2）：恰好 1 个因子 pane 时 25%，多 pane 仍 step*0.75
            pane_h = 25 if n == 1 else step * 0.75
            for i in range(n):
                grids.append({"left": 16, "right": 56,
                              "top": _pct(f_top + i * step),
                              "height": _pct(pane_h)} if f_on else dict(hide))
            return grids

        def _pct(v: float) -> str:
            # 与 JS `x + '%'` 同形：最短往返表示 + 去尾 ".0"
            # （66.0→'66%'、8.75→'8.75%'、69.66666666666667 原样）
            s = repr(float(v))
            return (s[:-2] if s.endswith(".0") else s) + "%"

        cases = [[n, sv, sf] for n in (0, 1, 2, 3) for sv in (True, False)
                 for sf in (True, False)]
        # 键必须与 JS 侧 c[0]+'|'+c[1]+'|'+c[2] 一致：Python 的 True 序列化是小写 true
        expected = {f"{n}|{str(sv).lower()}|{str(sf).lower()}": py_pane_grids(n, sv, sf)
                    for n, sv, sf in cases}
        # Python 侧算期望 → 注入 JS → JS 逐值比对，不一致即抛错（真交叉验证）
        _node(_layout() + r"""
const expected = %EXPECTED%;
const cases = %CASES%;
cases.forEach(function (c) {
  const key = c[0] + '|' + c[1] + '|' + c[2];
  const got = JSON.stringify(L.paneGrids(c[0], {showVol: c[1], showFct: c[2]}));
  const want = JSON.stringify(expected[key]);
  if (got !== want) {
    throw new Error('paneGrids 漂移 ' + key + '\n  got  ' + got + '\n  want ' + want);
  }
});
console.log('GRIDS-OK');
""".replace("%CASES%", json.dumps(cases)).replace("%EXPECTED%", json.dumps(expected)))

    def test_axis_label_index_matches_python(self):
        def py_label_idx(n, show_vol=True, show_fct=True):
            if show_fct and n > 0:
                return 1 + n
            if show_vol:
                return 1
            return 0

        cases = [[n, sv, sf] for n in (0, 1, 2) for sv in (True, False) for sf in (True, False)]
        # JS 侧键是 true/false 字面量，expect 也在 JS 侧构造，避免 Python True/False 串不匹配
        expect_js = "{" + ",".join(
            f"'{n}|{str(sv).lower()}|{str(sf).lower()}':{py_label_idx(n, sv, sf)}"
            for n, sv, sf in cases
        ) + "}"
        _node(_layout() + r"""
const cases = %CASES%;
const out = {};
cases.forEach(([n, sv, sf]) => {
  out[n + '|' + sv + '|' + sf] = L.axisLabelIndex(n, {showVol: sv, showFct: sf});
});
const expect = %EXPECT%;
for (const k of Object.keys(expect)) {
  assert.equal(out[k], expect[k], 'axisLabelIndex 不符: ' + k
    + ' 期望 ' + expect[k] + ' 实际 ' + out[k]);
}
console.log('t1-labelidx-ok');
""".replace("%CASES%", json.dumps(cases)).replace("%EXPECT%", expect_js))


# ---------------------------------------------------------------- 源码合同
class TestSourceContract:
    def test_shared_module_exports(self):
        for fn in ("paneGrids", "axisLabelIndex", "paneYAxes", "paneSeries",
                   "panesToOption", "paneGridIndex", "assertPaneInvariant"):
            assert re.search(rf"\b{fn}\b", LAYOUT_JS), f"factor-layout.js 缺导出 {fn}"

    def test_no_business_page_writes_pane_index(self):
        """除 factor-layout.js 外，任何文件都不得再出现 pane 索引算术。"""
        for name, path in (
            ("symbol.html", REPO / "src/quant_research_engine/gui/saas/templates/symbol.html"),
            ("game.html", REPO / "src/quant_research_engine/game/templates/game.html"),
            ("replay.js", REPO / "src/quant_research_engine/gui/static/replay.js"),
            ("job.html", REPO / "src/quant_research_engine/gui/saas/templates/job.html"),
        ):
            text = path.read_text(encoding="utf-8")
            for bad in ("yAxisIndex: 2 + i", "xAxisIndex: 2 + i",
                        "yAxisIndex: paneIndex + 2", "xAxisIndex: paneIndex + 2",
                        "grid: 2 + i", "gridIndex: 2 + i"):
                assert bad not in text, f"{name} 仍手写 pane 索引: {bad}"


# ---------------------------------------------------------------- R3-1 视觉闭环
class TestR3MacdZeroBaseline:
    """R3-1（TV_ROUND3 §2）：MACD「同一把尺」视觉自证。

    用户原始投诉 = MACD 三线看起来各自坐标系。逆向侧已裁定**不拆独立轴**
    （TV 原版也是三线共轴共量程），剩余差距是三个视觉项，本类锁其中两个代码项：
    ① HIST 家族 pane 画零基线（静态 option + 重播规格都要有）；
    ② 恰好 1 个因子 pane 时高度 20.25% → 25%。
    """

    def test_single_pane_height_is_25_percent(self):
        _node(_layout() + r"""
const one = L.paneGrids(1, {showVol: true, showFct: true});
const pane = one[one.length - 1];
if (pane.height !== '25%') throw new Error('单 pane 高度应为 25%，实际 ' + pane.height);
// 多 pane 不得被顺手改动（避免互相挤压）
const three = L.paneGrids(3, {showVol: true, showFct: true});
const h3 = three[three.length - 1].height;
if (h3 !== '6.75%') throw new Error('3 pane 高度应仍为 6.75%，实际 ' + h3);
console.log('R3-PANE-H-OK');
""")

    def test_hist_series_gets_zero_baseline_static(self):
        _node(_layout() + r"""
const panes = %PANES%;
const opt = L.panesToOption(panes, {paneBase: 2, dates: %DATES%, headYAxes: [{}, {}]});
const hist = opt.series.filter(function (s) { return s.type === 'bar'; });
if (hist.length !== 1) throw new Error('应有 1 个 HIST 系列，实际 ' + hist.length);
const ml = hist[0].markLine;
if (!ml) throw new Error('HIST 系列缺零基线 markLine');
if (ml.silent !== true) throw new Error('零基线必须 silent（不吞鼠标事件）');
if (ml.symbol !== 'none') throw new Error('零基线 symbol 应为 none');
if (ml.lineStyle.type !== 'dashed') throw new Error('零基线应为虚线');
if (JSON.stringify(ml.data) !== JSON.stringify([{yAxis: 0}])) {
  throw new Error('零基线 data 应为 [{yAxis:0}]，实际 ' + JSON.stringify(ml.data));
}
// 阈值线仍只挂同面板第一条线（不被零基线顶替）
const dif = opt.series.filter(function (s) { return s.name === 'macd_dif'; })[0];
if (!dif.markLine) throw new Error('MACD 阈值线丢失');
console.log('R3-ZERO-STATIC-OK');
""".replace("%PANES%", json.dumps(PANES)).replace("%DATES%", json.dumps(DATES)))

    def test_hist_series_flagged_in_replay_spec(self):
        """重播规格的 HIST 必须带 hist 标记，调用方 markLineFor 才能分流。"""
        _node(_layout() + r"""
const panes = %PANES%;
const opt = L.panesToOption(panes, {paneBase: 2, style: 'replay', dates: %DATES%});
const hist = opt.series.filter(function (s) { return s.hist === true; });
if (hist.length !== 1) throw new Error('replay 规格应有 1 个 hist 标记系列');
if (hist[0].type !== 'bar') throw new Error('hist 标记系列应为 bar');
// 非 HIST 系列不得被误打标（否则末价标签会被零基线顶掉）
const others = opt.series.filter(function (s) { return s.hist === true && s.type !== 'bar'; });
if (others.length) throw new Error('非 bar 系列被误打 hist 标记');
console.log('R3-ZERO-REPLAY-OK');
""".replace("%PANES%", json.dumps(PANES)).replace("%DATES%", json.dumps(DATES)))

    def test_symbol_html_markline_for_splits_hist_and_price(self):
        """symbol.html 的 markLineFor 必须按 series 分流：HIST→零基线，价格→末价标签。"""
        block = SYMBOL_TPL
        assert "if (s.hist) {" in block, "markLineFor 必须先分流 HIST 系列"
        assert "data: [{ yAxis: 0 }]" in block, "重播路径的零基线 data 缺失"
        # 末价标签逻辑必须仍在（不得被零基线分支顶掉）
        assert "QREPriceScale.lastPriceMarkLine(" in block, "末价标签逻辑丢失"

    def test_kline_grid_spec_delegates_to_shared_layer(self):
        """R3-1 收敛：klineGridSpec 不再保留逐行复制的第二份布局实现。"""
        m = re.search(r"function klineGridSpec\(showVol, paneCount, showFct\)\{(.*?)\n\}",
                      SYMBOL_TPL, re.S)
        assert m, "klineGridSpec 未找到"
        body = m.group(1)
        assert "QREFactorLayout.paneGrids(" in body, "klineGridSpec 必须委派共享层 paneGrids"
        assert "left: 16" not in body, "klineGridSpec 不得再内联布局字面量（会漂移）"
        # 共享层必须真的是唯一实现
        assert LAYOUT_JS.count("function paneGrids(") == 1
        assert "step * 0.75" in LAYOUT_JS and "25" in LAYOUT_JS
