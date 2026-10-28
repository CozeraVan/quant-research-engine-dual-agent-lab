"""持仓期年化分母修复（2026-10-27）。

历史 bug：`持仓期年化收益` 用 equity 日期条目数当年化分母。equity_curve 日期稀疏时
（停牌/无成交/数据缺口），分母被压成极少条目，`(1+收益)^(252/分母)` 会爆出 e+35 假值。

修复：新增 `LabUI.tradingDaysHeldInRange()`，按 entry→exit 的自然日并集计算持仓
交易日（剔周末近似），可见区间外不计入；SaaS job/symbol 两个区间卡改用该分母。

全部 Node vm + 源码合同，不触外网、不跑回测。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LAB_UI_JS = (REPO / "src/quant_research_engine/gui/static/lab-ui.js").read_text(encoding="utf-8")
LAB_RESULT_PY = (REPO / "src/quant_research_engine/gui/lab_result.py").read_text(encoding="utf-8")
SYMBOL_TPL = (REPO / "src/quant_research_engine/gui/saas/templates/symbol.html").read_text(encoding="utf-8")
JOB_TPL = (REPO / "src/quant_research_engine/gui/saas/templates/job.html").read_text(encoding="utf-8")


def _node(script: str) -> None:
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    result = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


class TestSourceContract:
    def test_helper_defined(self):
        assert "LabUI.tradingDaysHeldInRange = function" in LAB_UI_JS

    def test_templates_use_helper(self):
        for name, tpl in (("symbol", SYMBOL_TPL), ("job", JOB_TPL)):
            assert "LabUI.tradingDaysHeldInRange" in tpl, f"{name} 必须使用实际持仓交易日分母"
        # 旧口径：直接用 held 当年化分母，必须移除
        assert not re.search(r"252\s*/\s*held\b", SYMBOL_TPL)
        assert not re.search(r"252\s*/\s*held\b", JOB_TPL)

    def test_zero_and_negative_base_guards(self):
        # 区间收益：首值为 0/缺失不制造 Infinity
        for name, tpl in (("symbol", SYMBOL_TPL), ("job", JOB_TPL)):
            assert "baseA === 0" in tpl, f"{name} sliceRetPct 缺少 -100% 保护"
        assert "ev[0]" in SYMBOL_TPL and "ev[0]" in JOB_TPL
        assert "base > 0" in LAB_RESULT_PY
        assert "TypeError" in LAB_RESULT_PY
        # 年化的负基数/-100%/非有限防护 2026-10-28 起收敛到 helper 单点
        assert "if (base <= 0) return null;" in LAB_UI_JS, "holdingAnnualized 缺少负基数保护"
        assert "!isFinite(Number(sRet))" in LAB_UI_JS, "holdingAnnualized 缺非有限保护"
        assert "days < LabUI.ANNUAL_MIN_TRADING_DAYS" in LAB_UI_JS, "holdingAnnualized 缺年化下限"
        for name, tpl in (("symbol", SYMBOL_TPL), ("job", JOB_TPL)):
            assert "Math.pow(1 + sRet" not in tpl, f"{name} 不得再自带年化公式（须走 helper）"


_SCENARIO = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const source = %SOURCE%;
const context = vm.createContext({console, window: {}});
vm.runInContext(source, context);
const fn = context.window.LabUI.tradingDaysHeldInRange;
assert.ok(typeof fn === 'function', 'LabUI.tradingDaysHeldInRange 必须存在');

// 920832.BJ 复现场景：equity 日期稀疏，2016 年只有 7 个条目
const dates = ['2015-05-22','2015-05-28','2016-01-06','2016-03-31','2016-09-23','2016-09-28','2016-12-12','2016-12-15'];
const dateIdx = {}; dates.forEach((d,i)=>{dateIdx[d]=i;});
const trades = [
  {entry_date:'2016-01-06', exit_date:'2016-03-31'},
  {entry_date:'2016-09-23', exit_date:'2016-09-28'},
  {entry_date:'2016-12-12', exit_date:'2016-12-15'},
];

// 全区间：三段持仓自然日并集 = 62 + 4 + 4 = 70 个交易日（剔周末近似）
assert.equal(fn(dates, dateIdx, trades, 0, dates.length-1), 70, '全区间持仓交易日');

// 可见区间裁到第二段：只剩 2016-09-23 → 2016-09-28 = 4 个交易日
assert.equal(fn(dates, dateIdx, trades, 4, 5), 4, '可见区间裁剪');

// 可见区间只覆盖第二、三段：4 + 4 = 8
assert.equal(fn(dates, dateIdx, trades, 4, 7), 8, '区间并集不重复计数');

// 无交易/无退出/越界安全
assert.equal(fn(dates, dateIdx, [], 0, 7), 0, '无交易');
assert.equal(fn(dates, dateIdx, [{entry_date:'2016-09-23'}], 0, 7), 1, '无退出按单日');
assert.equal(fn(dates, dateIdx, [{entry_date:'2099-01-01', exit_date:'2099-01-05'}], 0, 7), 0, '越权交易不计入');

// 年化分母不再是 6（稀疏条目数），70 天下 529% 收益年化仍在有限区间
const sRet = 5.293506;
const ann = Math.pow(1 + sRet, 252 / 70) - 1;
assert.ok(Number.isFinite(ann) && ann > 0 && ann < 1e6, '年化值必须有限且不再爆表: ' + ann);
console.log('holding-days-ok');
"""


def test_trading_days_held_in_range():
    _node(_SCENARIO.replace("%SOURCE%", __import__("json").dumps(LAB_UI_JS)))


# ---------------------------------------------------------------- 年化下限（2026-10-28）
# 920556.BJ（job#66）复现：3 笔交易全部集中在 2015-03~05，持仓暴露度 1.05%
# （24 / 2295 交易日），区间收益 945.61%。原公式
#   (1+9.456117)^(252/24) - 1 = 5.05e10 → 页面显示 5051142288902.57%
# 「持仓期年化」的本意是「在场期间的单位时间收益率」，但持仓不足一个完整年度时
# (1+收益)^(252/持仓日) 属于外推，指数会把收益放大到失真。修法是加年化下限：
# 持仓交易日不足 252（一个完整年度）时不给年化值，改显示「—」并说明原因。
_ANNUAL_SCENARIO = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const source = %SOURCE%;
const context = vm.createContext({console, window: {}});
vm.runInContext(source, context);
const LabUI = context.window.LabUI;
const ann = LabUI.holdingAnnualized;
const note = LabUI.holdingAnnualNote;
assert.ok(typeof ann === 'function', 'LabUI.holdingAnnualized 必须存在');
assert.ok(typeof note === 'function', 'LabUI.holdingAnnualNote 必须存在');
assert.equal(LabUI.ANNUAL_MIN_TRADING_DAYS, 252, '年化下限 = 一个完整年度');

// 1) 920556.BJ 复现：24 天 +945.61% 必须被抑制
assert.equal(ann(9.456117, 24), null, '持仓不足一年不得给年化值');
assert.ok(note(24).indexOf('年化不成立') >= 0, '必须给出原因: ' + note(24));
assert.ok(note(24).indexOf('24') >= 0 && note(24).indexOf('252') >= 0, '原因需带具体天数');

// 2) 边界：恰好 252 天起可年化
assert.ok(Math.abs(ann(0.3, 252) - 0.3) < 1e-12, '252 天 +30% → 30%');
assert.ok(ann(0.3, 251) === null, '251 天仍不足一年');
assert.ok(ann(0.3, 253) !== null, '253 天可年化');
assert.equal(note(252), '', '达到下限不追加原因');
assert.equal(note(300), '', '超过下限不追加原因');

// 3) 长期持仓的正常年化仍然正确
const v = ann(0.3, 504);   // 两年 +30% → (1.3)^0.5 - 1
assert.ok(Math.abs(v - (Math.pow(1.3, 0.5) - 1)) < 1e-12, '504 天 +30% → 几何年化: ' + v);

// 4) 非法输入一律 null，不抛错不产生 NaN/Infinity
assert.equal(ann(null, 300), null, 'sRet 缺失');
assert.equal(ann(undefined, 300), null, 'sRet undefined');
assert.equal(ann(NaN, 300), null, 'sRet NaN');
assert.equal(ann(Infinity, 300), null, 'sRet Infinity');
assert.equal(ann(-1, 300), null, '本金亏光（-100%）');
assert.equal(ann(-2, 300), null, '超额亏损（负基数）');
assert.equal(ann(0.3, 0), null, '零持仓日');
assert.equal(ann(0.3, null), null, '持仓日缺失');
assert.equal(ann(0.3, NaN), null, '持仓日 NaN');

// 5) 达到下限后的极大收益仍须有限（不爆表）
const big = ann(100, 252);   // 一年 +10000%
assert.ok(Number.isFinite(big) && big === 100, '一年 +10000% → +10000%: ' + big);
console.log('annual-floor-ok');
"""


class TestAnnualFloor:
    """持仓期年化下限：持仓不足一个完整年度时不年化（920556.BJ 爆表修复）。"""

    def test_holding_annualized_floor(self):
        _node(_ANNUAL_SCENARIO.replace("%SOURCE%", __import__("json").dumps(LAB_UI_JS)))

    def test_templates_use_helper(self):
        for name, tpl in (("symbol", SYMBOL_TPL), ("job", JOB_TPL)):
            assert "LabUI.holdingAnnualized" in tpl, f"{name} 必须改用年化下限 helper"
            # 旧公式（无下限的裸 Math.pow）必须移除
            assert not re.search(r"Math\.pow\(1\s*\+\s*sRet\s*,\s*252\s*/\s*heldDays\)", tpl), (
                f"{name} 仍在用无下限的年化公式")
            assert "LabUI.holdingAnnualNote" in tpl, f"{name} 必须输出年化不成立的原因"

    def test_tip_mentions_floor(self):
        """tooltip 必须说明年化下限，否则用户看到「—」不知道原因。"""
        for name, tpl in (("symbol", SYMBOL_TPL), ("job", JOB_TPL)):
            assert "252" in tpl, f"{name} 年化说明需带 252 交易日口径"
