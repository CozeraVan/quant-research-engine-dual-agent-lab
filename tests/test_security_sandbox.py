"""QRE-SAAS-005 安全测试：策略 YAML/表达式 AST 白名单 + Docker 沙箱。

- schema/表达式校验：纯函数，正反例（注入 payload 全拒）。
- Docker 沙箱：禁网/内存上限/超时强杀/只读文件系统/正常计算。
  无 docker 的环境（CI）自动 skip（shutil.which + docker info 判定）。
  镜像优先用 qre-factor-sandbox:3.12，无则回退 python:3.12-slim
  （沙箱语义相同，只是少了 pandas；测试代码只用 stdlib）。
"""

from __future__ import annotations

import os

import pytest

from quant_research_engine.security.yaml_guard import (
    check_factor_limits,
    validate_expression,
    validate_strategy_yaml,
)
from quant_research_engine.worker import sandbox


class TestExpressionGuard:
    @pytest.mark.parametrize("expr", [
        "close <= bb_lower",
        "(close > 5) & (vol > 1000)",
        "close > open and rsi_14 < 30 or not suspended",
        "close.shift(1) > close",
        "close.rolling(20).mean() > open * 1.05",
        "(close / pre_close - 1) * 100 > 9.5",
        "amount >= 1000000 and close == 10.5",
    ])
    def test_legit_expressions_pass(self, expr):
        assert validate_expression(expr) == []

    def test_allowed_names_enforced(self):
        assert validate_expression("close > 0", {"close"}) == []
        issues = validate_expression("rsi_99 > 0", {"close"})
        assert issues and "未知列名" in issues[0]

    @pytest.mark.parametrize("expr", [
        "__import__('os')",                     # 裸函数 + 下划线标识符 + 字符串常量
        "().__class__",                          # dunder 属性
        "close.to_csv('/etc/passwd')",           # 非白名单方法 + 字符串常量
        "close.values",                          # 裸属性访问
        "close.values.__class__.__mro__",        # dunder 逃逸链
        "close.system('id')",                    # 非白名单方法
        "open('x')",                             # 裸函数调用
        "[c for c in close]",                    # 推导式
        "close[0]",                              # 下标
        "lambda x: x",                           # lambda
        "'abc'",                                 # 字符串常量
        "close if close > 1 else open",          # IfExp 不在白名单
        "_secret > 1",                           # 下划线开头标识符
    ])
    def test_injection_payloads_rejected(self, expr):
        assert validate_expression(expr), f"应拒绝: {expr}"


_VALID_YAML = """\
experiment:
  name: demo
data:
  market_fields: [open, close, pre_close, vol]
  factor_fields:
    bb_lower: factors.stock_daily_volatility_close.bbl_20_2_0_2_0
signal:
  entry: (close <= bb_lower)
  exit: (close >= bb_lower)
evaluation:
  forward_return_horizons: [1, 3, 5]
holding:
  max_holding_days: 20
risk:
  stop_loss_pct: 0.08
"""


class TestStrategyYamlGuard:
    def test_valid_yaml_passes(self):
        verdict = validate_strategy_yaml(_VALID_YAML)
        assert verdict["ok"], verdict["issues"]
        assert "bb_lower" in verdict["names"]

    def test_expression_injection_rejected(self):
        bad = _VALID_YAML.replace("(close <= bb_lower)", "close.__class__.__bases__")
        verdict = validate_strategy_yaml(bad)
        assert not verdict["ok"]
        assert any("signal.entry" in i for i in verdict["issues"])

    def test_unknown_top_level_key_rejected(self):
        verdict = validate_strategy_yaml(_VALID_YAML + "\nmalicious:\n  run: x\n")
        assert not verdict["ok"]

    def test_undeclared_column_rejected(self):
        bad = _VALID_YAML.replace("(close <= bb_lower)", "(close <= secret_col)")
        verdict = validate_strategy_yaml(bad)
        assert not verdict["ok"]
        assert any("secret_col" in i for i in verdict["issues"])

    def test_bad_factor_target_rejected(self):
        bad = _VALID_YAML.replace(
            "factors.stock_daily_volatility_close.bbl_20_2_0_2_0",
            "factors.stock_daily_volatility_close.bbl_20_2_0_2_0; DROP TABLE users--",
        )
        verdict = validate_strategy_yaml(bad)
        assert not verdict["ok"]

    def test_type_checks(self):
        bad = _VALID_YAML.replace("max_holding_days: 20", "max_holding_days: -5")
        assert not validate_strategy_yaml(bad)["ok"]
        bad = _VALID_YAML.replace("stop_loss_pct: 0.08", "stop_loss_pct: 2.0")
        assert not validate_strategy_yaml(bad)["ok"]
        bad = _VALID_YAML.replace("forward_return_horizons: [1, 3, 5]",
                                  "forward_return_horizons: [9999]")
        assert not validate_strategy_yaml(bad)["ok"]

    def test_oversize_rejected(self):
        assert not validate_strategy_yaml("experiment: {" + "a" * 200_000)["ok"]


class TestFactorLimits:
    """因子资源配额闸（2026-10-03）：单策略 ≤20 因子、≤3 张因子表。"""

    def _yaml_with_factors(self, fields: dict[str, str]) -> str:
        lines = "\n".join(f"    {k}: {v}" for k, v in fields.items())
        first = next(iter(fields))
        return (
            "experiment:\n  name: demo\ndata:\n  market_fields: [close]\n"
            f"  factor_fields:\n{lines}\n"
            f"signal:\n  entry: {first} > 0\n"
        )

    def test_too_many_factors_rejected(self):
        fields = {f"f{i}": "factors.stock_daily_momentum_close.rsi_14" for i in range(21)}
        verdict = validate_strategy_yaml(self._yaml_with_factors(fields))
        assert not verdict["ok"]
        assert any("因子数量超限" in i for i in verdict["issues"])

    def test_too_many_tables_rejected(self):
        fields = {
            "a": "factors.stock_daily_momentum_close.rsi_14",
            "b": "factors.stock_daily_volatility_close.bbl_20_2_0_2_0",
            "c": "factors.stock_daily_overlap_close.ma_20",
            "d": "factors.stock_daily_volume_close.obv",
        }
        verdict = validate_strategy_yaml(self._yaml_with_factors(fields))
        assert not verdict["ok"]
        assert any("因子来源表超限" in i for i in verdict["issues"])

    def test_at_limit_passes(self):
        fields = {
            "a": "factors.stock_daily_momentum_close.rsi_14",
            "b": "factors.stock_daily_volatility_close.bbl_20_2_0_2_0",
            "c": "factors.stock_daily_overlap_close.ma_20",
        }
        verdict = validate_strategy_yaml(self._yaml_with_factors(fields))
        assert verdict["ok"], verdict["issues"]

    def test_check_factor_limits_lenient(self):
        assert check_factor_limits("not: [valid") == []
        assert check_factor_limits("just a string") == []
        fields = {f"f{i}": "factors.stock_daily_momentum_close.rsi_14" for i in range(25)}
        assert check_factor_limits(self._yaml_with_factors(fields))


# --- Docker 沙箱（无 docker 环境 skip） ---

_PREFIX = ["sudo", "-n", "docker"] if os.environ.get("SANDBOX_DOCKER_SUDO") == "1" else ["docker"]
# 本机 van 未加入 docker 组时回退 sudo -n
if not sandbox.docker_available(_PREFIX) and sandbox.docker_available(["sudo", "-n", "docker"]):
    _PREFIX = ["sudo", "-n", "docker"]

_DOCKER_OK = sandbox.docker_available(_PREFIX)
if _DOCKER_OK and sandbox.image_available(sandbox.DEFAULT_IMAGE, _PREFIX):
    _IMAGE = sandbox.DEFAULT_IMAGE
elif _DOCKER_OK and sandbox.image_available("python:3.12-slim", _PREFIX):
    _IMAGE = "python:3.12-slim"
else:
    _IMAGE = None

pytestmark_docker = pytest.mark.skipif(
    not _DOCKER_OK or _IMAGE is None,
    reason="docker 不可用或无沙箱镜像（qre-factor-sandbox:3.12 / python:3.12-slim）",
)


@pytest.mark.skipif(not _DOCKER_OK or _IMAGE is None,
                    reason="docker 不可用或无沙箱镜像")
class TestDockerSandbox:
    def _run(self, code, timeout=60):
        return sandbox.run_sandboxed(code, image=_IMAGE, timeout=timeout, prefix=_PREFIX)

    def test_normal_compute(self):
        result = self._run("print(sum(i * i for i in range(1000)))")
        assert result["ok"] and result["exit_code"] == 0
        assert result["stdout"].strip() == str(sum(i * i for i in range(1000)))

    def test_network_blocked(self):
        result = self._run(
            "import socket\n"
            "try:\n"
            "    socket.create_connection(('8.8.8.8', 53), timeout=3)\n"
            "    print('NET_OK')\n"
            "except OSError:\n"
            "    print('NET_BLOCKED')\n"
        )
        assert result["ok"] and "NET_BLOCKED" in result["stdout"]

    def test_readonly_rootfs(self):
        result = self._run(
            "try:\n"
            "    open('/etc/pwned', 'w').write('x')\n"
            "    print('WRITE_OK')\n"
            "except OSError:\n"
            "    print('WRITE_BLOCKED')\n"
        )
        assert result["ok"] and "WRITE_BLOCKED" in result["stdout"]

    def test_memory_limit_kills(self):
        result = self._run("x = bytearray(2 * 1024**3)\nprint(len(x))", timeout=90)
        assert not result["ok"]  # 512m 上限下进程被杀/异常

    def test_timeout_kills(self):
        result = self._run("import time\ntime.sleep(300)\nprint('done')", timeout=10)
        assert result["timed_out"] and not result["ok"]

    def test_mounted_workdir_readonly(self):
        # /work 以 :ro 挂载，沙箱内篡改输入文件必须失败
        result = self._run(
            "try:\n"
            "    open('/work/main.py', 'w').write('pwn')\n"
            "    print('WORK_WRITE_OK')\n"
            "except OSError:\n"
            "    print('WORK_WRITE_BLOCKED')\n"
        )
        assert result["ok"] and "WORK_WRITE_BLOCKED" in result["stdout"]
