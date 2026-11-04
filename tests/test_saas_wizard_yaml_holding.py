"""经典策略公网冒烟回归（2026-11-03）：向导生成的 YAML 必须自带合法 holding 节。

背景：118 策略 100 股×两年公网冒烟 14 个失败全部是 wizard 入口可表达策略，错误统一为
`RuntimeError: 回测失败：holding section is required`。根因：`new.html` 的
`refreshWizard()` 生成 experiment/data/universe/signal/evaluation 五节，**没有 holding**；
而 `strategies/spec.py::_mapping` 要求 holding 节必须存在（引擎硬约束），统一 params 的
max_holding_days 只覆盖运行期、不弥补 YAML 结构缺失。

本测试用 node vm 跑**真实模板里的生成器函数**（condExpression/readGroup/usedFactors/
setYaml/applyName/refreshWizard 均从 new.html 抽取，不打桩生成逻辑），断言：
1. 默认（UI 输入框默认 20）生成 `holding.max_holding_days: 20`，且过
   `security.yaml_guard.validate_strategy_yaml` 真实安全闸；
2. 持仓输入清空（=不限）生成 `max_holding_days: 0`（协议 0=不限），仍过闸；
3. `applyName()`（提交路径的 holding 注入）对已含 holding 的向导 YAML 幂等，不重复注入；
4. 向导默认值与服务端 `build_strategy_yaml` 的 holding_days 默认值一致（单源，不发明第二套）。
"""

from __future__ import annotations

import inspect
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from quant_research_engine.gui.factor_wizard import build_strategy_yaml
from quant_research_engine.security.yaml_guard import validate_strategy_yaml

NEW_HTML = Path("src/quant_research_engine/gui/saas/templates/new.html")

#: 从 new.html 抽取的真实函数（函数体以行首 `}` 结束；保持与线上逐字一致）
_EXTRACTED_FUNCTIONS = (
    "condExpression", "readGroup", "usedFactors", "maybeAutoName",
    "setYaml", "applyName", "refreshWizard",
)

_HARNESS = r"""
const vm = require('node:vm');
const assert = require('node:assert/strict');

function makeRow(left, op, right, isFixed){
  const q = (sel) => {
    if (sel === '.wz-left') return {value: left};
    if (sel === '.wz-op') return {value: op};
    if (sel === '.wz-isfixed') return {checked: !!isFixed};
    if (sel === '.wz-rnum') return {value: isFixed ? String(right) : ''};
    if (sel === '.wz-rfield') return {value: isFixed ? '' : right};
    return {};
  };
  return {querySelector: q, querySelectorAll: () => []};
}
function makeGroup(rows, comb){
  return {
    querySelector: (sel) => sel === '.comb-toggle' ? {dataset: {comb}} : {},
    querySelectorAll: (sel) => sel === '.wz-cond' ? rows : [],
  };
}

function run(scenario){
  const holdingValue = scenario.holding;          // '#p-holding' 输入框当前值
  const entryRow = makeRow('ema_5', 'crosses_above', 'ema_200', false);
  const exitRow = makeRow('ema_5', 'crosses_below', 'ema_200', false);
  const fixedRow = makeRow('close', '>', 0, true); // 常量右值条件行（覆盖 isNum 分支）
  // withFixed：常量行并入 entry 组（与真实页面「追加条件行」同构）
  const entryGroup = makeGroup(scenario.withFixed ? [entryRow, fixedRow] : [entryRow], 'and');
  const exitGroup = makeGroup([exitRow], 'and');

  const elements = {
    '#p-holding': {value: holdingValue},
    '#p-sname': {value: 'wizard_strategy'},
    '#yaml-editor': {value: ''},
  };
  const document = {
    querySelector(sel){ return elements[sel] || null; },
    querySelectorAll(sel){
      if (sel === '#wz-entry .cond-group') return [entryGroup];
      if (sel === '#wz-exit .cond-group') return [exitGroup];
      // usedFactors 走文档级 .wz-cond 汇总（真实页面同理）
      if (sel === '.wz-cond') return scenario.withFixed ? [entryRow, fixedRow, exitRow] : [entryRow, exitRow];
      return [];
    },
  };
  const sandbox = {
    console, document,
    ALIAS_TARGET: {
      ema_5: 'factors.stock_daily_overlap_close.ema_5',
      ema_200: 'factors.stock_daily_overlap_typical_price.ema_200',
      // close 是内置行情字段（market_fields），不属于因子目录 ALIAS_TARGET——
      // 与真实页面口径一致：向导只把目录因子写进 factor_fields
    },
    userNamed: true,            // 跳过 maybeAutoName 的自动命名（不影响生成结构）
    refreshPreview(){},         // 预览渲染与 YAML 生成无关
  };
  sandbox.window = sandbox;     // window.__libBackfillOnce 读取点
  vm.createContext(sandbox);
  vm.runInContext(scenario.sources, sandbox);
  vm.runInContext('refreshWizard()', sandbox);
  const yamlText = vm.runInContext('strategyYaml', sandbox);
  assert.ok(yamlText && yamlText.indexOf('experiment:') >= 0, 'refreshWizard 未生成 YAML');
  const applied = vm.runInContext(
    'applyName(' + JSON.stringify(yamlText) + ')', sandbox);
  return {yaml: yamlText, applied: applied};
}

const scenario = JSON.parse(process.argv[1]);
const out = run(scenario);
process.stdout.write(JSON.stringify(out));
"""


def _fn_source(html: str, name: str) -> str:
    match = re.search(rf"^function {name}\(.*?^\}}", html, re.S | re.M)
    assert match, f"new.html 中未找到函数 {name}"
    return match.group(0)


@pytest.fixture(scope="module")
def wizard_sources() -> str:
    html = NEW_HTML.read_text(encoding="utf-8")
    # $ / $$ 是行内 const（非 function 声明），按真实模板行抽取，避免测试自带一份选择器实现
    selectors = "\n".join(
        re.search(rf"^{line}$", html, re.M).group(0)
        for line in (r"const \$ = \(s, r\) => \(r \|\| document\)\.querySelector\(s\);",
                     r"const \$\$ = \(s, r\) => Array\.prototype\.slice\.call\(\(r \|\| document\)\.querySelectorAll\(s\)\);")
    )
    return selectors + "\n" + "\n".join(_fn_source(html, name) for name in _EXTRACTED_FUNCTIONS)


def _node() -> str | None:
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    return node


def _run_wizard(wizard_sources: str, *, holding: str, with_fixed: bool = False) -> dict:
    node = _node()
    if not node:
        pytest.skip("node 不可用")
    scenario = json.dumps({"sources": wizard_sources, "holding": holding,
                           "withFixed": with_fixed})
    proc = subprocess.run([node, "-e", _HARNESS, scenario],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"node 执行失败：{proc.stderr}"
    return json.loads(proc.stdout)


class TestWizardYamlHolding:
    def test_default_generated_yaml_has_holding_and_passes_guard(self, wizard_sources):
        """回归根因：默认参数（UI 默认 20）下向导 YAML 必须含 holding 且过安全闸。"""
        out = _run_wizard(wizard_sources, holding="20")
        parsed = yaml.safe_load(out["yaml"])
        assert parsed["holding"] == {"max_holding_days": 20}
        assert validate_strategy_yaml(out["yaml"])["ok"] is True
        # 穿越语义不被 holding 修复破坏（P0-9 前真实交叉表达式；readGroup 逐条件括号）
        assert parsed["signal"]["entry"] == (
            "((ema_5 > ema_200) and (ema_5.shift(1) <= ema_200.shift(1)))")
        assert parsed["signal"]["exit"] == (
            "((ema_5 < ema_200) and (ema_5.shift(1) >= ema_200.shift(1)))")

    def test_empty_holding_input_generates_unlimited_zero_and_passes_guard(self, wizard_sources):
        """持仓输入清空 = 不限（协议 0），YAML 仍必须有 holding 节（引擎硬约束）。"""
        out = _run_wizard(wizard_sources, holding="")
        parsed = yaml.safe_load(out["yaml"])
        assert parsed["holding"] == {"max_holding_days": 0}
        assert validate_strategy_yaml(out["yaml"])["ok"] is True

    def test_constant_right_value_condition_still_valid(self, wizard_sources):
        """常量右值条件（close > 0）+ holding 共存，过安全闸。"""
        out = _run_wizard(wizard_sources, holding="20", with_fixed=True)
        parsed = yaml.safe_load(out["yaml"])
        assert parsed["holding"]["max_holding_days"] == 20
        assert "close > 0" in parsed["signal"]["entry"]
        assert validate_strategy_yaml(out["yaml"])["ok"] is True

    def test_apply_name_does_not_duplicate_holding(self, wizard_sources):
        """提交路径 applyName() 的 holding 注入对向导 YAML 必须幂等（不出现两节）。"""
        out = _run_wizard(wizard_sources, holding="20")
        applied = yaml.safe_load(out["applied"])
        assert applied["holding"] == {"max_holding_days": 20}
        assert out["applied"].count("holding:") == 1
        assert validate_strategy_yaml(out["applied"])["ok"] is True

    def test_wizard_default_matches_server_generator_default(self):
        """单源锁定：UI 输入框默认值 == 服务端 build_strategy_yaml 的 holding_days 默认值，
        不允许两套默认值漂移（本次 14 个失败的本质就是浏览器生成器缺节）。"""
        html = NEW_HTML.read_text(encoding="utf-8")
        m = re.search(r'id="p-holding"[^>]*value="(\d+)"', html)
        assert m, "未找到 #p-holding 输入框默认值"
        ui_default = int(m.group(1))
        server_default = inspect.signature(build_strategy_yaml).parameters["holding_days"].default
        assert ui_default == server_default == 20

    def test_server_generator_yaml_passes_guard_with_holding(self):
        """服务端同源生成器（stress driver 实际走的路径）保持 holding 且过闸。"""
        yaml_text = build_strategy_yaml(
            name="wizard_strategy",
            factor_fields={"ema_5": "factors.stock_daily_overlap_close.ema_5",
                           "ema_200": "factors.stock_daily_overlap_typical_price.ema_200"},
            entry_expression="(ema_5 > ema_200) and (ema_5.shift(1) <= ema_200.shift(1))",
            exit_expression="(ema_5 < ema_200) and (ema_5.shift(1) >= ema_200.shift(1))",
        )
        parsed = yaml.safe_load(yaml_text)
        assert parsed["holding"] == {"max_holding_days": 20}
        assert validate_strategy_yaml(yaml_text)["ok"] is True


import yaml  # noqa: E402  （放在类后避免遮挡顶部导入分组阅读）
