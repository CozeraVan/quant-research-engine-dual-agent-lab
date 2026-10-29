"""收益曲线共享层：`static/equity-chart.js` 的纯函数行为 + 双模板接入合同。

QRE-EQUITY-CHART：job.html 与 symbol.html 原先各自内联一套 ECharts 收益曲线
（前者「策略 + 单基准 + 回撤」，后者「策略净值(元) + 买入持有% + 各基准% + 双 y 轴」，
基准还全部同色）。收敛到共享模块后必须锁定三件事：

1. 归一化与回撤口径与后端 / pandas 一致（含空值、0 基、单点等边界）；
2. 图表选项的结构合同（单 y 轴、回撤副网格高度、图例默认态、基准配色）；
3. 两模板都引入并调用该模块，且模板里不再残留旧的硬编码网格/双轴/`基准·` 前缀。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
EQ_JS = (REPO / "src/quant_research_engine/gui/static/equity-chart.js").read_text(
    encoding="utf-8"
)
JOB_TPL = (REPO / "src/quant_research_engine/gui/saas/templates/job.html").read_text(
    encoding="utf-8"
)
SYMBOL_TPL = (
    REPO / "src/quant_research_engine/gui/saas/templates/symbol.html"
).read_text(encoding="utf-8")
REPLAY_JS = (REPO / "src/quant_research_engine/gui/static/replay.js").read_text(
    encoding="utf-8"
)

# symbol.html 的 K 线图合法使用 yAxisIndex: 1（成交量副轴），
# 因此「收益曲线不得双 y 轴」只能对 renderEquity 这一段断言。
SYMBOL_EQUITY = SYMBOL_TPL[
    SYMBOL_TPL.index("function renderEquity(d){"):SYMBOL_TPL.index(
        "function renderWear(d){"
    )
]


def _node(script: str) -> str:
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    result = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout


# 模块在 vm 沙箱里执行，产出的对象/数组属于另一个 realm，node:assert/strict 的
# deepEqual 会因原型不同而报 "same structure but not reference-equal"；
# 统一用 JSON 往返搬回宿主 realm 再比。
HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
// 浏览器同构：window 必须指向全局自身（test_vol_regime 踩过的坑）
const sandbox = {};
sandbox.window = sandbox;
const ctx = vm.createContext(sandbox);
vm.runInContext(%SRC%, ctx);
const R = ctx.QREEquityChart;
assert.ok(R, 'QREEquityChart 未导出');
const plain = v => JSON.parse(JSON.stringify(v));
const eq = (a, b, msg) => assert.deepStrictEqual(plain(a), b, msg);
const near = (a, b, eps, msg) => assert.ok(Math.abs(a - b) <= eps,
  (msg || '数值不符') + ': 实得 ' + a + ' 期望 ' + b);
"""


def _run(scenario: str) -> None:
    _node(HARNESS.replace("%SRC%", json.dumps(EQ_JS)) + scenario)


class TestToPct:
    def test_normalizes_by_first_finite_value(self):
        _run(r"""
const out = R.toPct([10, 11, 9, 10]);
assert.equal(out.length, 4);
near(out[0], 0, 1e-12);
near(out[1], 10, 1e-12);
near(out[2], -10, 1e-12);
near(out[3], 0, 1e-12);
console.log('toPct-basic-ok');
""")

    def test_nulls_preserved_and_skipped_for_base(self):
        _run(r"""
const out = R.toPct([null, 100, null, 105]);
assert.equal(out.length, 4);
assert.equal(out[0], null);
assert.equal(out[1], 0);
assert.equal(out[2], null);
near(out[3], 5, 1e-12, '基准必须是首个非空值');
console.log('toPct-null-ok');
""")

    def test_zero_or_missing_base_yields_all_null(self):
        _run(r"""
[[0, 1, 2], [null, null], []].forEach(arr => {
  const out = R.toPct(arr);
  assert.equal(out.length, arr.length);
  out.forEach(v => assert.equal(v, null, '基为 0/缺失必须全 null: ' + JSON.stringify(arr)));
});
eq(R.toPct(null), []);
eq(R.toPct(undefined), []);
console.log('toPct-degenerate-ok');
""")

    def test_single_point_is_zero(self):
        _run(r"""
eq(R.toPct([42]), [0]);
console.log('toPct-single-ok');
""")

    def test_non_finite_entries_are_null(self):
        _run(r"""
const out = R.toPct([100, NaN, Infinity, 110]);
assert.equal(out[1], null);
assert.equal(out[2], null);
near(out[3], 10, 1e-12, 'Infinity 不得污染结果');
console.log('toPct-finite-ok');
""")

    def test_bench_pct_is_to_pct(self):
        _run(r"""
const out = R.benchPct([100, 120]);
near(out[0], 0, 1e-12);
near(out[1], 20, 1e-12);
eq(R.benchPct([]), []);
console.log('benchPct-alias-ok');
""")


class TestDrawdown:
    def test_matches_pandas_cummax(self):
        equity = [1.0, 1.1, None, 0.95, 1.2, 1.15, 1.3, 1.0]
        # pandas: (s / s.cummax() - 1) * 100，NaN 位置保持 NaN、峰值继续沿用
        expected = [0.0, 0.0, None, -13.636363636363647, 0.0,
                    -4.166666666666674, 0.0, -23.076923076923084]
        _run(r"""
const equity = %EQ%;
const expected = %EXP%;
const out = R.drawdownPct(equity);
assert.equal(out.length, expected.length);
expected.forEach((e, i) => {
  if (e === null) { assert.equal(out[i], null, 'i=' + i + ' 应为 null'); return; }
  near(out[i], e, 1e-9, 'i=' + i);
});
console.log('dd-pandas-ok');
""".replace("%EQ%", json.dumps(equity)).replace("%EXP%", json.dumps(expected)))

    def test_never_positive_and_zero_equity_is_null(self):
        _run(r"""
const out = R.drawdownPct([100, 120, 120, 60, 0, -5, 130]);
out.forEach(v => { if (v != null) assert.ok(v <= 0, '回撤必须 ≤ 0: ' + v); });
assert.equal(out[1], 0, '新高处回撤应为 0');
assert.equal(out[3], -50);
assert.equal(out[4], null, '净值为 0 不制造 -100% 假值');
assert.equal(out[5], null, '负净值必须为 null');
assert.equal(out[6], 0, '再创新高回撤归零');
console.log('dd-sign-ok');
""")

    def test_degenerate_inputs(self):
        _run(r"""
eq(R.drawdownPct([]), []);
eq(R.drawdownPct(null), []);
eq(R.drawdownPct([5]), [0]);
console.log('dd-degenerate-ok');
""")


class TestColorAndLegend:
    def test_bench_colors_follow_style_book(self):
        _run(r"""
const expect = {
  '000001.SH': '#B7A6E8', '000300.SH': '#2A9D8F', '399001.SZ': '#E8A33D',
  '000905.SH': '#4A3A78', '399006.SZ': '#9A93A6', '000852.SH': '#6750A4',
};
Object.keys(expect).forEach(code => {
  assert.equal(R.BENCH_COLORS[code], expect[code], code + ' 配色漂移');
});
assert.equal(R.STRATEGY_COLOR, '#6750A4');
assert.equal(R.DD_COLOR, '#d43030');
// 未列出的 code 按序循环取色，越界也要能取到
assert.equal(R.benchColor('999999.SH', 0), '#B7A6E8');
assert.equal(R.benchColor('999999.SH', 6), '#B7A6E8');
assert.equal(R.benchColor('000300.SH', 5), '#2A9D8F', '已知 code 优先于序号');
console.log('color-ok');
""")

    def test_legend_defaults_to_first_bench_only(self):
        _run(r"""
const benches = {'000300.SH': {name: '沪深300', closes: [1, 2]},
                 '000001.SH': {name: '上证指数', closes: [1, 2]}};
const sel = R.legendSelectedFor(benches, null);
assert.equal(sel['沪深300'], false);
assert.equal(sel['上证指数'], true, '默认必须只开上证指数');
const all = R.legendSelectedFor(benches, Object.keys(benches));
assert.equal(all['沪深300'], true);
assert.equal(all['上证指数'], true);
// 没有上证指数时退回首个基准
const other = R.legendSelectedFor({'000300.SH': {name: '沪深300'}}, null);
assert.equal(other['沪深300'], true);
console.log('legend-ok');
""")


class TestOption:
    def test_with_drawdown_uses_two_grids_and_single_y_axis(self):
        _run(r"""
const o = R.option({
  dates: ['2024-01-02', '2024-01-03', '2024-01-04'],
  strategyPct: [0, 1, -1],
  benches: {'000001.SH': {name: '上证指数', closes: [100, 101, 100]}},
  benchmarks: {'000001.SH': {name: '上证指数'}},
  drawdownPct: [0, 0, -1],
});
assert.equal(o.grid.length, 2);
eq(o.grid[1], {left: 68, right: 20, top: '70%', height: '16%'});
assert.equal(o.grid[0].height, '52%');
assert.equal(o.yAxis.length, 2);
assert.equal(o.yAxis[0].name, '累计收益率%');
assert.equal(o.yAxis[1].gridIndex, 1, '副轴只能给回撤网格用');
eq(o.xAxis.map(x => x.gridIndex), [0, 1]);
assert.equal(o.xAxis[0].axisLabel.show, false, '上格横轴标签必须隐藏');
assert.equal(o.dataZoom.length, 2);
eq(o.dataZoom[1].xAxisIndex, [0, 1]);
eq(o.tooltip.axisPointer.link, [{xAxisIndex: 'all'}]);
eq(o.series.map(s => s.name), ['策略', '上证指数', '回撤']);
assert.equal(o.series[0].color, '#6750A4');
assert.equal(o.series[0].lineStyle.width, 2);
assert.equal(o.series[1].lineStyle.type, 'dashed');
assert.equal(o.series[1].lineStyle.width, 1.2);
assert.equal(o.series[2].xAxisIndex, 1);
assert.equal(o.series[2].yAxisIndex, 1);
assert.equal(o.series[2].color, '#d43030');
eq(o.legend.data, ['策略', '上证指数', '回撤']);
console.log('option-dd-ok');
""")

    def test_without_drawdown_uses_full_height(self):
        _run(r"""
const o = R.option({dates: ['a', 'b'], strategyPct: [0, 2], benches: {}});
assert.equal(o.grid.length, 1);
eq(o.grid[0], {left: 68, right: 20, top: 30, height: '72%'});
assert.equal(o.yAxis.length, 1);
assert.equal(o.xAxis.length, 1);
eq(o.dataZoom[0].xAxisIndex, [0]);
eq(o.series.map(s => s.name), ['策略']);
console.log('option-nodd-ok');
""")

    def test_hold_line_and_array_benches(self):
        _run(r"""
const o = R.option({
  dates: ['a', 'b', 'c'], strategyPct: [0, 1, 2],
  benches: [{code: '000300.SH', name: '沪深300', pct: [0, 0.5, 1]}],
  holdPct: [0, 1.5, 3],
});
eq(o.series.map(s => s.name), ['策略', '沪深300', '买入持有']);
const hold = o.series[2];
assert.equal(hold.color, '#6750A4');
assert.equal(hold.lineStyle.type, 'dashed');
assert.equal(hold.lineStyle.width, 1.2);
eq(o.legend.data, ['策略', '沪深300', '买入持有']);
// 无数据的基准不进序列也不进图例（只在按钮条里显示「暂无数据」）
const empty = R.option({dates: ['a'], strategyPct: [0], benches: {'000001.SH': {name: '上证指数'}}});
eq(empty.series.map(s => s.name), ['策略']);
eq(empty.legend.data, ['策略']);
console.log('option-hold-ok');
""")

    def test_replay_spec_aligns_with_static_chart(self):
        _run(r"""
const spec = R.replaySpec({
  strategyPct: [0, 1], strategyRaw: [1, 1.01],
  benches: {'000001.SH': {name: '上证指数', closes: [100, 101]}},
  drawdownPct: [0, 0],
});
eq(spec.series.map(s => s.name), ['策略', '上证指数', '回撤']);
assert.equal(spec.series[0].color, '#6750A4');
assert.equal(spec.series[1].dashed, true);
eq(spec.grids[1], {left: 68, right: 20, top: '70%', height: '16%'});
eq(spec.yAxes, [{name: '累计收益率%'}, {name: '回撤%', max: 0}]);
assert.equal(spec.hasDD, true);
assert.equal(spec.legendSelected['上证指数'], true);
const flat = R.replaySpec({strategyPct: [0], benches: {}});
assert.equal(flat.hasDD, false);
eq(flat.grids, [{left: 68, right: 20, top: 30, height: '72%'}]);
console.log('replay-spec-ok');
""")


class TestTemplateContract:
    def test_module_exists_with_required_members(self):
        for member in ("BENCH_COLORS", "STRATEGY_COLOR", "DD_COLOR", "toPct",
                       "drawdownPct", "benchPct", "option"):
            assert member in EQ_JS, f"equity-chart.js 缺导出 {member}"
        assert "root.QREEquityChart" in EQ_JS

    def test_both_templates_load_shared_module(self):
        for name, tpl in (("job.html", JOB_TPL), ("symbol.html", SYMBOL_TPL)):
            assert "/static/equity-chart.js" in tpl, f"{name} 未引入 /static/equity-chart.js"

    def test_both_templates_call_option(self):
        for name, tpl in (("job.html", JOB_TPL), ("symbol.html", SYMBOL_TPL)):
            assert "QREEquityChart.option(" in tpl, f"{name} 未调用 QREEquityChart.option"

    def test_no_legacy_inline_series_or_grid_left(self):
        assert "grid: hasDD ?" not in JOB_TPL, "job.html 仍内联回撤网格判断"
        assert "'基准·' +" not in JOB_TPL, "job.html 仍拼接旧基准序列名"
        assert "策略净值(元)" not in SYMBOL_TPL, "symbol.html 仍是净值(元) 口径"
        assert "yAxisIndex: 1" not in SYMBOL_EQUITY, "收益曲线仍保留双 y 轴"

    def test_symbol_page_has_bench_bar_and_drawdown(self):
        assert 'id="bench-bar"' in SYMBOL_TPL, "symbol.html 缺基准多选条 #bench-bar"
        assert "QREEquityChart.drawdownPct(" in SYMBOL_TPL, "symbol.html 未计算回撤"

    def test_bench_bar_is_multi_select_with_aria_pressed(self):
        for name, tpl in (("job.html", JOB_TPL), ("symbol.html", SYMBOL_TPL)):
            assert "legendToggleSelect" in tpl, f"{name} 基准按钮未联动图例"
            assert "aria-pressed" in tpl, f"{name} 基准按钮缺 aria-pressed"

    def test_bench_bar_label_is_not_grey_small_text(self):
        # AGENTS.md 规则 13：解释说明走 tip-trigger + data-tip，不得用 .opt 灰字
        for name, tpl in (("job.html", JOB_TPL), ("symbol.html", SYMBOL_TPL)):
            assert 'class="opt" tabindex="0" data-tip="基准是用于对照' not in tpl, (
                f"{name} 基准说明仍用 .opt 灰字"
            )

    def test_replay_passes_legend_selection(self):
        assert "legendSelected: spec.legendSelected" in JOB_TPL, "job.html 重播未传图例默认态"
        assert "if (opts.legendSelected) legend.selected = opts.legendSelected" in REPLAY_JS, (
            "replay.js 未按 legendSelected 有无不落地 selected 键"
        )

    def test_replay_legend_never_passes_selected_undefined(self):
        """QRE-REPLAY-LEGEND-SELECTED（R3-2）：不得写 `selected: undefined`。

        setOption 带 replaceMerge 时 ECharts 走 overallReset，用裸 option 重建
        legend model；`selected` 缺省不填默认值 → LegendModel.isSelected 里
        `undefined.hasOwnProperty(name)` 抛错。K 线重播不下发 legendSelected，
        旧写法每帧 seek 炸一次 pageerror（真实浏览器实测，R3-2 修）。
        """
        # 去掉注释再断言：注释里为了说明问题会引用这个写法本身
        code = re.sub(r"/\*.*?\*/", "", REPLAY_JS, flags=re.S)
        code = re.sub(r"//[^\n]*", "", code)
        assert "selected: opts.legendSelected || undefined" not in code, (
            "replay.js 又写回了 selected: undefined（K 线重播会每帧抛 pageerror）"
        )
        assert "selected: undefined" not in code, "replay.js 不得出现 selected: undefined"