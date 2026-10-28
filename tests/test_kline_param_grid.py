"""T5 · 指标参数网格（QRE-KLINE-PARAM-GRID）。

覆盖任务书 §7 T5：
- 参数网格预计算的**前端部分**：识别 family + params，按用户选择过滤因子集合，
  再交给既有 plan() 归组——只切列、不重算、不连库；
- 切参数 < 100ms 重渲染（真实浏览器实测）；
- 同一产物切 3 组参数，因子值与离线重算一致（真实浏览器实测）；
- 不破坏复权口径（只切换预计算列）。

后端宽表是否加列**不在本轮实施范围**（派单纪律：不改后端 Python 与数据库），
方案与成本见 CR 文档 §5。

Node vm 跑**真实 factor-layout.js 源码**（不写桩）。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LAYOUT_JS = (REPO / "src/quant_research_engine/gui/static/factor-layout.js").read_text(
    encoding="utf-8"
)
SYMBOL_TPL = (
    REPO / "src/quant_research_engine/gui/saas/templates/symbol.html"
).read_text(encoding="utf-8")


def _node(script: str) -> None:
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
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
const ctx = { console, window: {}, module: undefined, exports: undefined };
vm.runInContext(src, vm.createContext(ctx));
const L = ctx.window.QREFactorLayout;
globalThis.L = L;
"""


def _layout() -> str:
    return _HARNESS.replace("%SOURCE%", json.dumps(LAYOUT_JS))


# 4 组 MACD + 4 组 RSI + 1 组 BOLL + 2 个 overlay（与因子表真实列名一致）
FACTORS = [
    {"name": "EMA12", "col": "ema_12", "table": "factors.stock_daily_overlap_close",
     "display": {"chart_type": "overlay", "panel_id": "overlay:ema_12"},
     "values": [1, 2, 3]},
    {"name": "MACD", "col": "macd_12_26_9", "table": "factors.stock_daily_momentum_close",
     "display": {"chart_type": "pane", "panel_id": "macd:12_26_9", "role": "main"},
     "values": [0.1, 0.2, 0.3]},
    {"name": "MACDS", "col": "macds_12_26_9", "table": "factors.stock_daily_momentum_close",
     "display": {"chart_type": "pane", "panel_id": "macd:12_26_9", "role": "signal"},
     "values": [0.05, 0.1, 0.15]},
    {"name": "MACDH", "col": "macdh_12_26_9", "table": "factors.stock_daily_momentum_close",
     "display": {"chart_type": "pane", "panel_id": "macd:12_26_9", "role": "hist",
                 "series_type": "bar"},
     "values": [0.05, 0.1, 0.15]},
    {"name": "MACD2", "col": "macd_15_35_10", "table": "factors.stock_daily_momentum_close",
     "display": {"chart_type": "pane", "panel_id": "macd:15_35_10", "role": "main"},
     "values": [0.2, 0.3, 0.4]},
    {"name": "MACD2S", "col": "macds_15_35_10", "table": "factors.stock_daily_momentum_close",
     "display": {"chart_type": "pane", "panel_id": "macd:15_35_10", "role": "signal"},
     "values": [0.1, 0.15, 0.2]},
    {"name": "MACD3", "col": "macd_24_52_18", "table": "factors.stock_daily_momentum_close",
     "display": {"chart_type": "pane", "panel_id": "macd:24_52_18", "role": "main"},
     "values": [0.3, 0.4, 0.5]},
    {"name": "RSI", "col": "rsi_6", "table": "factors.stock_daily_momentum_close",
     "display": {"chart_type": "pane", "panel_id": "pane:rsi_6"},
     "values": [40, 50, 60]},
    {"name": "RSI2", "col": "rsi_14", "table": "factors.stock_daily_momentum_close",
     "display": {"chart_type": "pane", "panel_id": "pane:rsi_14"},
     "values": [45, 55, 65]},
    {"name": "RSI3", "col": "rsi_24", "table": "factors.stock_daily_momentum_close",
     "display": {"chart_type": "pane", "panel_id": "pane:rsi_24"},
     "values": [48, 58, 68]},
    {"name": "BOLL", "col": "boll_20_2", "table": "factors.stock_daily_overlap_close",
     "display": {"chart_type": "pane", "panel_id": "pane:boll_20_2"},
     "values": [10, 11, 12]},
]


# ---------------------------------------------------------------- 变体识别
class TestParamVariants:
    def test_family_and_params_detection(self):
        _node(_layout() + r"""
const k = L.paramKeyOf;
// MACD 三元组（新列名）
assert.deepEqual(
  ['macd', '12_26_9'].map((_, i) => [k({col: 'macd_12_26_9'}).family, k({col: 'macd_12_26_9'}).params][i]),
  ['macd', '12_26_9']);
assert.equal(k({col: 'macds_15_35_10'}).family, 'macd');
assert.equal(k({col: 'macds_15_35_10'}).params, '15_35_10');
assert.equal(k({col: 'macdh_24_52_18'}).params, '24_52_18');
// MACD 旧列名（无参数后缀）
assert.equal(k({name: 'macd_dif'}).family, 'macd');
assert.equal(k({name: 'macd_dif'}).params, '');
assert.equal(k({name: 'MACD DEA'}).family, 'macd');
assert.equal(k({name: 'macd_histogram'}).family, 'macd');
// RSI / MA / EMA / KDJ
assert.equal(k({col: 'rsi_14'}).family, 'rsi');
assert.equal(k({col: 'rsi_14'}).params, '14');
assert.equal(k({col: 'sma_5'}).family, 'ma', 'sma 与 ma 同族');
assert.equal(k({col: 'ma_5'}).family, 'ma');
assert.equal(k({col: 'ema_12'}).family, 'ema');
assert.equal(k({col: 'kdj_9_3'}).params, '9_3');
// BOLL：上中下轨道列同族，参数只取前两组
assert.equal(k({col: 'boll_20_2'}).family, 'boll');
assert.equal(k({col: 'boll_20_2'}).params, '20_2');
assert.equal(k({col: 'bbl_20_2_0_2_0'}).family, 'boll');
assert.equal(k({col: 'bbl_20_2_0_2_0'}).params, '20_2');
assert.equal(k({col: 'bbu_50_2_5'}).params, '50_2');
// 非参数化因子 → null（不得误判成变体）
assert.equal(k({col: 'close'}), null);
assert.equal(k({col: 'vwap_d'}), null);
assert.equal(k({col: 'alpha001'}), null);
assert.equal(k({name: 'MACD'}), null, '裸 MACD 无参数后缀 → 不算变体');
assert.equal(k(null), null);
assert.equal(k({}), null);
console.log('t5-key-ok');
""")

    def test_variants_listing(self):
        _node(_layout() + r"""
const fams = L.paramVariants(%FACTORS%);
const byFam = {};
fams.forEach(f => { byFam[f.family] = f; });
assert.equal(JSON.stringify(Object.keys(byFam).sort()),
             JSON.stringify(['boll', 'ema', 'macd', 'rsi']));
// MACD 4 组参数、按首次出现顺序
assert.equal(JSON.stringify(byFam.macd.variants.map(v => v.params)),
             JSON.stringify(['12_26_9', '15_35_10', '24_52_18']));
assert.equal(JSON.stringify(byFam.macd.variants[0].cols),
             JSON.stringify(['macd_12_26_9', 'macds_12_26_9', 'macdh_12_26_9']));
assert.equal(byFam.macd.variants[0].count, 3, '三元组三列');
// RSI 3 组
assert.equal(JSON.stringify(byFam.rsi.variants.map(v => v.params)),
             JSON.stringify(['6', '14', '24']));
// BOLL 只有一组 → 仍然列出（由调用方决定是否给选择器）
assert.equal(byFam.boll.variants.length, 1);
// EMA 只有一组
assert.equal(byFam.ema.variants.length, 1);
// 空/坏输入不得炸
assert.equal(L.paramVariants([]).length, 0);
assert.equal(L.paramVariants(null).length, 0);
console.log('t5-variants-ok');
""".replace("%FACTORS%", json.dumps(FACTORS)))


# ---------------------------------------------------------------- 切换过滤
class TestApplyParamChoices:
    def test_switch_keeps_only_chosen_variant(self):
        _node(_layout() + r"""
const F = %FACTORS%;
// 选 MACD 15_35_10 + RSI 24
const out = L.applyParamChoices(F, {macd: '15_35_10', rsi: '24'});
const cols = out.map(f => f.col || f.name);
assert.ok(cols.indexOf('macd_15_35_10') >= 0, '选中组必须保留');
assert.ok(cols.indexOf('macds_15_35_10') >= 0);
assert.equal(cols.indexOf('macd_12_26_9'), -1, '未选中的 MACD 组必须滤掉');
assert.equal(cols.indexOf('macd_24_52_18'), -1);
assert.equal(cols.indexOf('macdh_12_26_9'), -1);
assert.ok(cols.indexOf('rsi_24') >= 0, 'RSI 选中组保留');
assert.equal(cols.indexOf('rsi_6'), -1, 'RSI 未选中组滤掉');
assert.equal(cols.indexOf('rsi_14'), -1);
// 非参数化因子与单组家族全部保留
assert.ok(cols.indexOf('ema_12') >= 0, 'overlay 必须保留');
assert.ok(cols.indexOf('boll_20_2') >= 0, '单参数组家族必须保留');
// 过完过滤仍能正确归组：MACD 只剩一组 → 一个面板
const plan = L.plan(out, {}, []);
const macdPanes = plan.panes.filter(p => /macd/i.test(p.name));
assert.equal(macdPanes.length, 1, '切换后 MACD 应只有一个面板: '
  + JSON.stringify(plan.panes.map(p => p.name)));
assert.equal(macdPanes[0].series.length, 2, 'DIF+DEA（该组没有 hist 列）');
console.log('t5-switch-ok');
""".replace("%FACTORS%", json.dumps(FACTORS)))

    def test_identity_when_no_choice(self):
        """没有选择时必须逐字节返回入参——存量产物零影响。"""
        _node(_layout() + r"""
const F = %FACTORS%;
assert.equal(L.applyParamChoices(F, {}), F, '空选择必须原样返回同一对象');
assert.equal(L.applyParamChoices(F, null), F);
assert.equal(L.applyParamChoices(F, undefined), F);
assert.equal(L.applyParamChoices(F, 'x'), F);
assert.equal(L.applyParamChoices(F, []), F);
assert.equal(L.applyParamChoices(F, {macd: 'nope'}), F, '未知参数不得丢面板');
assert.equal(L.applyParamChoices(F, {nofamily: '1'}), F, '未知家族不得丢面板');
assert.equal(L.applyParamChoices([], {macd: '12_26_9'}).length, 0);
// 单参数组家族给选择也不生效（没得选）
const single = [{name: 'RSI', col: 'rsi_14', values: [1]}];
assert.equal(L.applyParamChoices(single, {rsi: '6'}), single);
console.log('t5-identity-ok');
""".replace("%FACTORS%", json.dumps(FACTORS)))

    def test_dirty_choices_do_not_break_plan(self):
        _node(_layout() + r"""
const F = %FACTORS%;
[null, undefined, 0, '', 'x', {}, [], {macd: 1}, {macd: null}].forEach(c => {
  const out = L.applyParamChoices(F, c);
  assert.ok(Array.isArray(out), '坏选择不得炸: ' + JSON.stringify(c));
  const plan = L.plan(out, {}, []);
  assert.ok(plan.panes.length >= 1, '坏选择后仍要有面板');
});
console.log('t5-dirty-ok');
""".replace("%FACTORS%", json.dumps(FACTORS)))


# ---------------------------------------------------------------- 源码合同
class TestSourceContract:
    def test_layout_exports(self):
        for fn in ("paramKeyOf", "paramVariants", "applyParamChoices"):
            assert f"{fn}:" in LAYOUT_JS, f"factor-layout.js 缺导出 {fn}"

    def test_symbol_wires_param_grid(self):
        assert "PARAM_LS_KEY = 'qre.kline.params'" in SYMBOL_TPL, (
            "参数选择必须持久化到 qre.kline.params")
        assert "function klinePlanFactors(" in SYMBOL_TPL, (
            "必须有统一的因子集合出口")
        assert "applyParamChoices(factors, paramChoices())" in SYMBOL_TPL, (
            "必须经共享层过滤，不自己写一套")
        assert "QREFactorLayout.paramVariants(" in SYMBOL_TPL, (
            "指标对话框必须展示参数变体")
        # 不得有人绕过 klinePlanFactors 直接把原始 factors 喂给 plan()
        assert "plan(d.factors" not in SYMBOL_TPL, "不得绕过参数选择直接传 d.factors"
        assert "klineDetail && klineDetail.factors || [], chipStates()" not in SYMBOL_TPL, (
            "不得绕过参数选择直接传 klineDetail.factors")
        # 所有 plan() 调用点的因子集合都必须源自 klinePlanFactors
        import re

        n_plan = len(re.findall(r"QREFactorLayout\.plan\(", SYMBOL_TPL))
        n_src = SYMBOL_TPL.count("klinePlanFactors(")
        assert n_src >= n_plan, (
            "klinePlanFactors 调用点(%s)不得少于 plan() 调用点(%s)" % (n_src, n_plan))

    def test_no_manual_pane_index(self):
        for bad in ("yAxisIndex: 2 + i", "xAxisIndex: 2 + i", "gridIndex: 2 + i"):
            assert bad not in SYMBOL_TPL, f"symbol.html 仍手写 pane 索引: {bad}"

    def test_reset_clears_param_choices(self):
        assert "k === PARAM_LS_KEY" in SYMBOL_TPL, (
            "「恢复默认」必须同时清空参数选择")
