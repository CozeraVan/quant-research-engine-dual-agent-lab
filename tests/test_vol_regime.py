"""波动率状态文案：`static/vol-regime.js` 的纯函数行为 + 双模板接入合同。

QRE-VOL-REGIME：job.html 与 lab_result.html 的波动率状态文案曾各写一份，一处用
`data-tip`、一处用 `.opt` 灰字，且直接打印英文枚举（`当前波动状态 mid`）。收敛到
共享模块后必须锁定两件事：

1. 文案生成**永不**输出 `undefined` / `NaN` / `null`（旧产物没有
   `regime_thresholds` 字段，这是最容易踩的路径）；
2. 两模板都引入并调用该模块，且模板里不再残留英文枚举拼接。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
VOL_JS = (REPO / "src/quant_research_engine/gui/static/vol-regime.js").read_text(
    encoding="utf-8"
)
JOB_TPL = (
    REPO / "src/quant_research_engine/gui/saas/templates/job.html"
).read_text(encoding="utf-8")
LAB_TPL = (
    REPO / "src/quant_research_engine/gui/templates/lab_result.html"
).read_text(encoding="utf-8")

# 任务书 §A4 给出的真实切点（risk_report job 58 的 thresholds_annual）
TH = {"low_below": 0.18344, "high_at_or_above": 0.202309}
TOFIXED18_3 = f"{TH['low_below'] * 100:.1f}"  # '18.3'
TOFIXED20_2 = f"{TH['high_at_or_above'] * 100:.1f}"  # '20.2'


def _node(script: str) -> None:
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    result = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
// 浏览器同构：window 必须指向全局自身，否则 `root.QREVolRegime = api` 落在一个
// 普通对象上，vm 内 `typeof QREVolRegime` 恒为 undefined（test_perf_metrics 踩过）。
const sandbox = {};
sandbox.window = sandbox;
const ctx = vm.createContext(sandbox);
vm.runInContext(%SRC%, ctx);
const R = ctx.QREVolRegime;
assert.ok(R, 'QREVolRegime 未导出');
"""

_NO_BAD = r"""
function noBad(s, tag) {
  ['undefined', 'NaN', 'null'].forEach(bad => {
    assert.equal(s.indexOf(bad) < 0, true, tag + ' 出现 ' + bad + ': ' + s);
  });
}
"""


def _run(scenario: str) -> None:
    _node(HARNESS.replace("%SRC%", json.dumps(VOL_JS)) + _NO_BAD + scenario)


class TestLabel:
    def test_three_known_states(self):
        _run(r"""
assert.equal(R.label('low'), '低波动');
assert.equal(R.label('mid'), '中波动');
assert.equal(R.label('high'), '高波动');
console.log('label-ok');
""")

    def test_unknown_or_missing_returns_empty(self):
        _run(r"""
[undefined, null, '', 'extreme', 0].forEach(v => {
  const out = R.label(v);
  assert.equal(typeof out, 'string', 'label 必须恒返回字符串: ' + v);
  assert.equal(out, '', '未知状态必须返回空串: ' + v);
});
console.log('label-unknown-ok');
""")


class TestDescribe:
    def test_with_thresholds_shows_cut_points(self):
        _run(r"""
const out = R.describe({latest_regime: 'mid', regime_thresholds: %TH%});
assert.equal(out.indexOf('中波动') >= 0, true, '缺中文状态: ' + out);
assert.equal(out.indexOf(%LO%) >= 0, true, '缺下切点 %LO%: ' + out);
assert.equal(out.indexOf(%HI%) >= 0, true, '缺上切点 %HI%: ' + out);
noBad(out, 'describe-full');
console.log(out);
""".replace("%TH%", json.dumps(TH))
             .replace("%LO%", json.dumps(TOFIXED18_3 + '%'))
             .replace("%HI%", json.dumps(TOFIXED20_2 + '%')))

    def test_low_and_high_states_still_carry_thresholds(self):
        _run(r"""
['low', 'high'].forEach(k => {
  const out = R.describe({latest_regime: k, regime_thresholds: %TH%});
  assert.equal(out.indexOf(R.label(k)) >= 0, true, k + ' 状态缺失: ' + out);
  assert.equal(out.indexOf(%HI%) >= 0, true, k + ' 阈值缺失: ' + out);
  noBad(out, 'describe-' + k);
});
console.log('describe-states-ok');
""".replace("%TH%", json.dumps(TH))
             .replace("%HI%", json.dumps(TOFIXED20_2 + '%')))

    def test_old_artifact_without_thresholds_degrades(self):
        """旧产物：只有 latest_regime，必须只报状态，不得出现 undefined/NaN/null。"""
        _run(r"""
const out = R.describe({latest_regime: 'mid'});
assert.equal(out, '当前：中波动', '无阈值必须只报状态: ' + out);
noBad(out, 'describe-old');
// 显式 null / 缺键 / 非 number 都不能触发 NaN
const cases = [
  {latest_regime: 'mid', regime_thresholds: null},
  {latest_regime: 'mid', regime_thresholds: {}},
  {latest_regime: 'mid', regime_thresholds: {low_below: null, high_at_or_above: null}},
  {latest_regime: 'mid', regime_thresholds: {low_below: '0.18', high_at_or_above: '0.20'}},
  {latest_regime: 'mid', regime_thresholds: {low_below: 0.18}},
];
cases.forEach(c => { const s = R.describe(c); noBad(s, 'describe-degrade'); });
console.log('describe-old-ok');
""")

    def test_missing_inputs_return_empty_string(self):
        _run(r"""
assert.equal(R.describe(null), '');
assert.equal(R.describe(undefined), '');
assert.equal(R.describe({}), '');
assert.equal(R.describe({latest_regime: 'extreme'}), '');
assert.equal(R.describe({regime_thresholds: %TH%}), '', '无状态时不得只剩阈值');
console.log('describe-empty-ok');
""".replace("%TH%", json.dumps(TH)))


class TestTipText:
    def test_contains_all_sections(self):
        _run(r"""
const out = R.tipText({
  ewma_annual: 0.221, garch_annual: 0.228,
  regime_counts: {low: 1356, mid: 1356, high: 1356},
  latest_regime: 'mid', regime_thresholds: %TH%,
});
assert.equal(out.indexOf('EWMA 年化波动 22.1%') >= 0, true, '缺 EWMA: ' + out);
assert.equal(out.indexOf('GARCH 年化波动 22.8%') >= 0, true, '缺 GARCH: ' + out);
assert.equal(out.indexOf('当前状态 中波动') >= 0, true, '缺中文状态: ' + out);
assert.equal(out.indexOf('1356') >= 0, true, '计数应降级到 tip: ' + out);
assert.equal(out.indexOf('当前波动状态 mid') >= 0, false, '不得残留英文枚举: ' + out);
noBad(out, 'tip-full');
console.log(out);
""".replace("%TH%", json.dumps(TH)))

    def test_skips_null_values(self):
        _run(r"""
const out = R.tipText({ewma_annual: null, garch_annual: 0.228,
                       latest_regime: 'low'});
assert.equal(out.indexOf('EWMA') >= 0, false, 'null 字段应跳过: ' + out);
assert.equal(out.indexOf('GARCH') >= 0, true, '非空字段应保留: ' + out);
noBad(out, 'tip-partial');
assert.equal(R.tipText(null), '');
assert.equal(R.tipText({}), '');
// 空 regime_counts 不得产出 "样本天数：" 尾巴
assert.equal(R.tipText({regime_counts: {}}).indexOf('样本天数') >= 0, false);
console.log('tip-partial-ok');
""")

    def test_percent_precision_is_one_decimal(self):
        _run(r"""
const out = R.tipText({ewma_annual: %LO%});
assert.equal(out, 'EWMA 年化波动 %LOPCT%', '精度必须一位小数: ' + out);
console.log('precision-ok');
""".replace("%LO%", json.dumps(TH["low_below"]))
             .replace("%LOPCT%", TOFIXED18_3 + '%'))


class TestGaugeModel:
    """R4-2.5：`#chart-risk-vol` 从「一行文字 + display:none」改成阈值标尺。

    gaugeModel 只做几何：把三档切点映射到 0–100% 的横轴位置，返回纯数值结构，
    格式化（`18.3%`）留给模板。所有输出必须是有限数，旧产物路径不得出现
    undefined/NaN/null（任务书 §2.5 硬约束）。
    """

    def test_threshold_mode_builds_full_track(self):
        _run(r"""
const vol = {ewma_annual: 0.057031, garch_annual: 0.062379,
             regime_thresholds: %TH%};
const g = R.gaugeModel(vol);
assert.ok(g, '有阈值时 gaugeModel 不得返回 null');
assert.equal(g.mode, 'threshold');
assert.equal(g.degraded, false);
assert.equal(g.segments.length, 3);
assert.equal(g.segments.map(s => s.key).join(','), 'low,mid,high');
assert.equal(g.domain >= %HI%, true, 'domain 必须覆盖高阈值: ' + g.domain);
// 三段首尾相接、总宽 100%
assert.equal(Math.abs(g.segments[0].leftPct) < 1e-9, true, '第一段必须从 0 起');
assert.equal(Math.abs(g.segments[0].leftPct + g.segments[0].widthPct - g.segments[1].leftPct) < 1e-9, true);
assert.equal(Math.abs(g.segments[1].leftPct + g.segments[1].widthPct - g.segments[2].leftPct) < 1e-9, true);
const sum = g.segments.reduce((a, s) => a + s.widthPct, 0);
assert.equal(Math.abs(sum - 100) < 1e-9, true, '三段总宽必须 100%: ' + sum);
// 切点映射到横轴
assert.equal(Math.abs(g.segments[1].leftPct - %LO% / g.domain * 100) < 1e-9, true);
// 两个口径各一枚游标
assert.equal(g.marks.map(m => m.key).join(','), 'ewma,garch');
assert.equal(Math.abs(g.marks[0].xPct - 0.057031 / g.domain * 100) < 1e-9, true);
assert.equal(Math.abs(g.marks[1].xPct - 0.062379 / g.domain * 100) < 1e-9, true);
assert.equal(g.ticks.length, 4);
assert.equal(Math.abs(g.ticks[3].leftPct - 100) < 1e-9, true);
noBad(JSON.stringify(g), 'gauge-threshold');
console.log('gauge-threshold ' + g.mode + ' ' + g.domain);
""".replace("%TH%", json.dumps(TH))
             .replace("%LO%", json.dumps(TH["low_below"]))
             .replace("%HI%", json.dumps(TH["high_at_or_above"])))

    def test_old_artifact_degrades_to_relative(self):
        """job 58 实况：regime_thresholds 为 null，绝对轴没有参照。"""
        _run(r"""
const g = R.gaugeModel({ewma_annual: 0.057031, garch_annual: 0.062379,
                        regime_counts: {low: 1356, mid: 1356, high: 1356},
                        latest_regime: 'mid', regime_thresholds: null});
assert.ok(g, '无阈值但有口径值时必须降级而非 null');
assert.equal(g.mode, 'relative');
assert.equal(g.degraded, true);
assert.equal(g.segments.length, 0, '降级态不得画三段轨');
assert.equal(g.ticks.length, 0);
assert.equal(g.marks.length, 2);
assert.equal(g.marks[1].xPct, 100, '较大口径必须占满参照长度: ' + g.marks[1].xPct);
assert.equal(Math.abs(g.marks[0].xPct - 0.057031 / 0.062379 * 100) < 1e-9, true);
noBad(JSON.stringify(g), 'gauge-relative');
console.log('gauge-relative-ok');
""")

    def test_invalid_thresholds_degrade_to_relative(self):
        """hi<=lo / lo 为 0 / 字符串 / 只给一半 / 空对象——全部降级，不得出 NaN。"""
        _run(r"""
const cases = [
  {low_below: 0.3, high_at_or_above: 0.2},
  {low_below: 0, high_at_or_above: 0.2},
  {low_below: '0.18', high_at_or_above: '0.20'},
  {low_below: 0.18},
  {},
];
cases.forEach(th => {
  const g = R.gaugeModel({ewma_annual: 0.057031, garch_annual: 0.062379,
                          regime_thresholds: th});
  assert.ok(g, '口径值仍在时不得返回 null: ' + JSON.stringify(th));
  assert.equal(g.mode, 'relative', '非法阈值必须降级: ' + JSON.stringify(th));
  assert.equal(g.degraded, true);
  noBad(JSON.stringify(g), 'gauge-degrade');
});
console.log('gauge-degrade-ok');
""")

    def test_single_series_still_renders(self):
        _run(r"""
const g = R.gaugeModel({garch_annual: 0.062379});
assert.ok(g);
assert.equal(g.marks.length, 1);
assert.equal(g.marks[0].key, 'garch');
assert.equal(g.marks[0].xPct, 100);
noBad(JSON.stringify(g), 'gauge-single');
// 只有阈值、两个口径都缺：仍可画三段轨，游标为空
const t = R.gaugeModel({regime_thresholds: %TH%});
assert.ok(t, '只有阈值时也应画轨');
assert.equal(t.mode, 'threshold');
assert.equal(t.marks.length, 0);
noBad(JSON.stringify(t), 'gauge-threshold-only');
console.log('gauge-single-ok');
""".replace("%TH%", json.dumps(TH)))

    def test_null_when_nothing_to_draw(self):
        _run(r"""
[null, undefined, {}, {latest_regime: 'mid'},
 {ewma_annual: null, garch_annual: 'x'},
 {ewma_annual: 0, garch_annual: 0}].forEach(v => {
  assert.equal(R.gaugeModel(v), null, '无可画数据必须返回 null: ' +
               JSON.stringify(v));
});
console.log('gauge-null-ok');
""")


class TestTemplateContract:
    def test_both_templates_load_shared_module(self):
        for name, tpl in (("job.html", JOB_TPL), ("lab_result.html", LAB_TPL)):
            assert "/static/vol-regime.js" in tpl, f"{name} 未引入 /static/vol-regime.js"

    def test_both_templates_use_describe(self):
        for name, tpl in (("job.html", JOB_TPL), ("lab_result.html", LAB_TPL)):
            assert "QREVolRegime.describe(" in tpl, f"{name} 未调用 QREVolRegime.describe"
            assert "QREVolRegime.tipText(" in tpl, f"{name} 未调用 QREVolRegime.tipText"
            assert "chart-risk-vol-state" in tpl, f"{name} 缺可见状态行 #chart-risk-vol-state"

    def test_no_english_regime_concatenation_left(self):
        for name, tpl in (("job.html", JOB_TPL), ("lab_result.html", LAB_TPL)):
            assert "'当前波动状态 ' + vol.latest_regime" not in tpl, (
                f"{name} 仍拼接英文波动状态枚举")
            assert "'当前波动状态 ' +" not in tpl, f"{name} 仍拼接英文波动状态枚举"

    def test_view_passes_thresholds_through(self):
        """A2 声称后端已完成，但前端拿到的是裁剪视图——视图层必须透传阈值。"""
        src = (REPO / "src/quant_research_engine/gui/lab_result.py").read_text(
            encoding="utf-8")
        assert '"regime_thresholds"' in src, (
            "build_lab_risk_view 未透传 regime threshold，模板将永远拿不到阈值")

    def test_job_template_draws_gauge_instead_of_hiding(self):
        """R4-2.5：容器不再直接 display:none，改由 gaugeModel 出 DOM。"""
        assert "QREVolRegime.gaugeModel(" in JOB_TPL, "job.html 未调用 gaugeModel"
        assert "vol-gauge" in JOB_TPL, "job.html 未生成标尺 DOM"
        assert "QRE-VOL-REGIME-NO-BARCHART" not in JOB_TPL, (
            "旧的「删掉柱状图就 display:none」注释仍在——这一列又被清空了")
        assert "QRE-VOL-REGIME-GAUGE" in JOB_TPL, "job.html 缺本项设计说明注释"
        # 不得把三等分柱状图改回来：regime_counts 的三桶不再上主视图
        assert "regime_counts" not in JOB_TPL.split("function renderRiskVol")[1].split(
            "function renderRiskStress")[0], "renderRiskVol 又去读 regime_counts 了"