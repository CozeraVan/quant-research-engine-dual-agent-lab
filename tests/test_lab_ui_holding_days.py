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
        # 区间收益：首值为 0/缺失不制造 Infinity；-100% 不除零
        for name, tpl in (("symbol", SYMBOL_TPL), ("job", JOB_TPL)):
            assert "baseA === 0" in tpl, f"{name} sliceRetPct 缺少 -100% 保护"
            assert "1 + sRet <= 0" in tpl, f"{name} 年化缺少负基数保护"
        assert "ev[0]" in SYMBOL_TPL and "ev[0]" in JOB_TPL
        assert "base > 0" in LAB_RESULT_PY
        assert "TypeError" in LAB_RESULT_PY


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
