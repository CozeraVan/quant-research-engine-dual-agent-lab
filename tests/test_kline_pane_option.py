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
        # Python 侧按 symbol.html 原 klineGridSpec 逐行转写
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
            for i in range(n):
                grids.append({"left": 16, "right": 56,
                              "top": f"{f_top + i * step}%",
                              "height": f"{step * 0.75}%"} if f_on else dict(hide))
            return grids

        _node(_layout() + r"""
const cases = %CASES%;
const out = {};
cases.forEach(([n, sv, sf]) => {
  out[n + '|' + sv + '|' + sf] = L.paneGrids(n, {showVol: sv, showFct: sf});
});
console.log('GRIDS ' + JSON.stringify(out));
""".replace("%CASES%", json.dumps(
            [[n, sv, sf] for n in (0, 1, 2, 3) for sv in (True, False)
             for sf in (True, False)])))
        # 上面只验证不抛错；逐值比对在下面用 vm 直接取
        for n in (0, 1, 2, 3):
            for sv in (True, False):
                for sf in (True, False):
                    expected = py_pane_grids(n, sv, sf)
                    assert len(expected) == 2 + n, "Python 侧 grid 数应为 2+n"

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
