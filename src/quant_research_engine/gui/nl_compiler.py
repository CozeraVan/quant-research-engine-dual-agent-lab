"""自然语言 → 策略 YAML 编译器（GUI 通道 C, QRE-GUI-WORKBENCH-P2-001）。

配置完全走环境变量（OpenAI 兼容 chat completions 协议）：
  QRE_NL_LLM_BASE_URL / QRE_NL_LLM_API_KEY / QRE_NL_LLM_MODEL

未配置时返回中文"未配置 LLM"错误，UI 降级提示使用通道 A/B。
安全闸：编译结果绝不自动执行，只填充到 YAML 编辑器由用户确认后提交。
HTTP 层使用 stdlib urllib（项目无 requests 依赖，不新增）。
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Any, Callable

from quant_research_engine.gui.engine import validate_yaml
from quant_research_engine.strategies.factor_request_queue import (
    DEFAULT_QUEUE_PATH,
    build_requests_for_strategy,
    find_missing_factor_columns,
    load_queue,
    save_queue,
    upsert_requests,
)
from quant_research_engine.strategies.spec import StrategySpec

ENV_BASE_URL = "QRE_NL_LLM_BASE_URL"
ENV_API_KEY = "QRE_NL_LLM_API_KEY"
ENV_MODEL = "QRE_NL_LLM_MODEL"

LLM_TIMEOUT_SECONDS = 60

NOT_CONFIGURED_ERROR = (
    "未配置 LLM：请设置环境变量 QRE_NL_LLM_BASE_URL / QRE_NL_LLM_API_KEY / "
    "QRE_NL_LLM_MODEL 后重启控制台；或改用通道 A（选择已有策略）/ 通道 B（可视化构建器）"
)


def nl_config(env: dict[str, str] | None = None) -> dict[str, str] | None:
    """Read LLM config from the environment; None when not fully configured."""
    env = env if env is not None else os.environ
    base_url = (env.get(ENV_BASE_URL) or "").strip().rstrip("/")
    api_key = (env.get(ENV_API_KEY) or "").strip()
    model = (env.get(ENV_MODEL) or "").strip()
    if not (base_url and api_key and model):
        return None
    return {"base_url": base_url, "api_key": api_key, "model": model}


# ---------------------------------------------------------------------------
# prompt construction
# ---------------------------------------------------------------------------

_DSL_DOC = """\
你是一名量化策略编译器。用户用中文描述一个 A 股日线选股/择时策略，
你必须将其编译为如下低层策略 DSL 的 YAML，且只输出 YAML，不要任何解释、注释或 Markdown 围栏。

DSL 结构（低层 StrategySpec）：
- experiment: {name: 策略英文ID, market_profile: ashare_daily_default, frequency: daily}
- data:
    market_fields: [open, high, low, close, pre_close, vol, amount]  # 内置行情别名，可直接用于表达式
    factor_fields: {逻辑别名: factors.<表>.<列>}  # 每个用到的技术指标一行
- signal:
    entry: 布尔表达式（入场）
    exit: 布尔表达式（离场，可选）
- holding: {max_holding_days: 整数}
- risk: {stop_loss_pct: 小数或 null, take_profit_pct: 小数或 null, trailing_stop_pct: 小数或 null}  # 用户没提就省略或 null
- universe: {exclude_st: true, exclude_suspended: true, exclude_risk_warning: true, min_listing_days: 120}
- evaluation: {forward_return_horizons: [1, 3, 5, 10, 20], quantiles: 5}

信号表达式语法（安全子集）：
- 操作数：因子/行情别名、数值常量
- 比较：< > <= >= == != ；布尔：and or not ；算术：+ - * / ；括号
- 不支持函数调用、不支持跨周期引用（如"上穿/下穿"请改写为当周期比较，例如
  "20 日均线上穿 120 日均线"写成 (sma_20 > sma_120)，并明白这是当日状态而非穿越事件）

因子命名约定：factors.stock_daily_<类别>_<价格源>.<指标>_<周期>（部分指标含参数后缀）。
价格源 source 通常为 close。可用指标目录（名称: 类别）：\
"""

_FEW_SHOT = """
示例 1：
用户：RSI(14) 跌破 30 后站回 30 买入，RSI 大于 60 卖出，持有最多 5 天，止损 -8%
输出：
experiment:
  name: nl_rsi14_oversold_reversal
  market_profile: ashare_daily_default
  frequency: daily
data:
  market_fields: [open, high, low, close, pre_close, vol, amount]
  factor_fields:
    rsi_14: factors.stock_daily_momentum_close.rsi_14
universe:
  exclude_st: true
  exclude_suspended: true
  exclude_risk_warning: true
  min_listing_days: 120
signal:
  entry: rsi_14 > 30
  exit: rsi_14 > 60
holding:
  max_holding_days: 5
risk:
  stop_loss_pct: 0.08
evaluation:
  forward_return_horizons: [1, 3, 5, 10, 20]
  quantiles: 5

示例 2：
用户：收盘价跌破 20 日布林下轨买入，回到中轨卖出，最多持有 20 天
输出：
experiment:
  name: nl_bollinger_lower_reversion
  market_profile: ashare_daily_default
  frequency: daily
data:
  market_fields: [open, high, low, close, pre_close, vol, amount]
  factor_fields:
    bb_lower: factors.stock_daily_volatility_close.bbl_20_2_0_2_0
    bb_middle: factors.stock_daily_volatility_close.bbm_20_2_0_2_0
universe:
  exclude_st: true
  exclude_suspended: true
  exclude_risk_warning: true
  min_listing_days: 120
signal:
  entry: (close <= bb_lower)
  exit: (close >= bb_middle)
holding:
  max_holding_days: 20
evaluation:
  forward_return_horizons: [1, 3, 5, 10, 20]
  quantiles: 5
"""


def build_system_prompt() -> str:
    """System prompt: DSL doc + indicator catalog + few-shot examples."""
    from quant_research_engine.strategies.compiler import _INDICATOR_CATALOG

    catalog_items = sorted(f"{name}: {category}" for name, (category, _) in _INDICATOR_CATALOG.items())
    return _DSL_DOC + "；".join(catalog_items) + "\n" + _FEW_SHOT


# ---------------------------------------------------------------------------
# output processing
# ---------------------------------------------------------------------------


def strip_yaml_fence(text: str) -> str:
    """Remove ```yaml / ``` fences and surrounding prose-free whitespace."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # drop opening fence line (``` or ```yaml)
        lines = lines[1:]
        # drop trailing fence if present
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def call_llm(
    description: str,
    config: dict[str, str],
    *,
    http_post: Callable[..., Any] | None = None,
    timeout: int = LLM_TIMEOUT_SECONDS,
) -> str:
    """Call an OpenAI-compatible chat completions endpoint; return content text.

    ``http_post`` is injectable for tests: signature
    ``http_post(url, headers, payload, timeout) -> dict`` (parsed JSON body).
    """
    url = f"{config['base_url']}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config['api_key']}",
    }
    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": description},
        ],
        "temperature": 0.2,
    }

    if http_post is not None:
        body = http_post(url, headers, payload, timeout)
    else:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))

    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"LLM 响应格式异常: {exc}") from exc


# ---------------------------------------------------------------------------
# factor existence check (复用 missing-factor 队列机制)
# ---------------------------------------------------------------------------


def _default_column_lookup(db_url: str | None = None) -> Callable[[str], set[str]] | None:
    """Build a read-only schema column lookup from the market DB; None if unavailable."""
    try:
        from quant_research_engine.data.settings import DatabaseSettings
        from quant_research_engine.data.postgres import PostgresDataStore
        from quant_research_engine.strategies.factor_request_queue import make_schema_column_lookup

        settings = DatabaseSettings(market_db_url=db_url) if db_url else DatabaseSettings.from_env()
        store = PostgresDataStore(settings)
        store.ping()
        return make_schema_column_lookup(store)
    except Exception:
        return None


def _enqueue_missing_factors(
    spec: StrategySpec,
    missing: list,
    *,
    queue_path: Path,
) -> None:
    requests = build_requests_for_strategy(
        spec,
        missing,
        strategy_id=spec.name,
        start="",
        end="",
    )
    entries = load_queue(queue_path)
    upsert_requests(entries, requests)
    save_queue(queue_path, entries)


# ---------------------------------------------------------------------------
# main entry
# ---------------------------------------------------------------------------


def compile_nl(
    description: str,
    *,
    http_post: Callable[..., Any] | None = None,
    column_lookup: Callable[[str], set[str]] | None = None,
    queue_path: Path | None = None,
    db_url: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Compile a natural-language strategy description to a low-level YAML.

    Returns one of:
      {"ok": True, "yaml": str, "warnings": [str, ...]}
      {"ok": False, "code": "not_configured", "error": 中文}
      {"ok": False, "code": "llm_error"|"invalid_yaml"|"missing_factors",
       "error": 中文, "yaml": 可选草稿, "missing_factors": [...]}
    """
    description = (description or "").strip()
    if not description:
        return {"ok": False, "code": "empty", "error": "请先用自然语言描述策略"}

    config = nl_config(env)
    if config is None:
        return {"ok": False, "code": "not_configured", "error": NOT_CONFIGURED_ERROR}

    try:
        raw = call_llm(description, config, http_post=http_post)
    except Exception as exc:
        return {"ok": False, "code": "llm_error", "error": f"LLM 调用失败：{exc}"}

    yaml_text = strip_yaml_fence(raw)

    validation = validate_yaml(yaml_text)
    if not validation["valid"]:
        return {
            "ok": False,
            "code": "invalid_yaml",
            "error": f"LLM 输出的 YAML 未通过策略规格校验：{validation['error']}。可编辑下方草稿修正后使用。",
            "yaml": yaml_text,
        }

    # 因子存在性检查（DB 不可用时跳过并提示）
    warnings: list[str] = []
    lookup = column_lookup if column_lookup is not None else _default_column_lookup(db_url)
    if lookup is None:
        warnings.append("因子库不可用，跳过因子存在性检查（提交回测时仍会校验）")
    else:
        import yaml as _yaml

        spec = StrategySpec.from_mapping(_yaml.safe_load(yaml_text))
        missing = find_missing_factor_columns(spec, lookup)
        if missing:
            _enqueue_missing_factors(spec, missing, queue_path=queue_path or DEFAULT_QUEUE_PATH)
            names = "、".join(f"{f.logical_name}({f.qualified_table}.{f.source_column})" for f in missing)
            return {
                "ok": False,
                "code": "missing_factors",
                "error": f"该策略已搁置：缺因子 {names}，已加入补因子队列通知 indicators_tushare 项目。",
                "yaml": yaml_text,
                "missing_factors": [f.logical_name for f in missing],
            }

    result: dict[str, Any] = {"ok": True, "yaml": yaml_text}
    if warnings:
        result["warnings"] = warnings
    return result
