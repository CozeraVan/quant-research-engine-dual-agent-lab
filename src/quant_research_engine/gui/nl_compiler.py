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
from quant_research_engine.gui.factor_correction import (
    format_corrections_note,
    format_unresolved_hint,
)
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

【严禁编造因子名】factor_fields 的列名必须严格来自真实因子库：小写 snake_case，
周期/参数用下划线连接（rsi_14、macd_12_26_9、bbl_20_2_0_2_0），大小写或
分隔符写错（如 rsi14、MACD）都会导致编译失败。只允许使用下面目录中的指标；
拿不准周期时用常用已落库列：\
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
    """System prompt: DSL doc + 真实因子目录快照（有则用）+ indicator catalog +
    常用已落库列 + few-shot examples。

    CR-2026-10-09 第 1 层：注入 configs/factor_catalog_llm.txt 的真实目录
    （factors.<表>.<列> 全量压缩清单），并加硬约束「factor_fields 只能引用
    清单内的表.列，禁止发明」。快照缺失（本地开发未生成）时回退旧口径。"""
    from quant_research_engine.gui.factor_catalog_llm import load_catalog_text
    from quant_research_engine.gui.factor_correction import COMMON_FACTOR_TARGETS
    from quant_research_engine.strategies.compiler import _INDICATOR_CATALOG

    real_catalog = load_catalog_text()
    common_items = "；".join(COMMON_FACTOR_TARGETS)
    if real_catalog is not None:
        catalog_block = (
            "\n真实因子库可用列（factor_fields 的 target 必须逐字引用以下 表.列，"
            "禁止发明或改写字母）：\n" + real_catalog
        )
    else:
        catalog_items = sorted(f"{name}: {category}" for name, (category, _) in _INDICATOR_CATALOG.items())
        catalog_block = "；".join(catalog_items)
    return _DSL_DOC + catalog_block + f"\n常用已落库列：{common_items}\n" + _FEW_SHOT


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
    system_prompt: str | None = None,
) -> str:
    """Call an OpenAI-compatible chat completions endpoint; return content text.

    ``http_post`` is injectable for tests: signature
    ``http_post(url, headers, payload, timeout) -> dict`` (parsed JSON body).
    ``system_prompt`` 缺省用策略编译提示词；其他通道（如因子生成）可注入自己的。
    """
    url = f"{config['base_url']}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config['api_key']}",
    }
    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": system_prompt or build_system_prompt()},
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
    """Build a read-only schema column lookup from the market DB; DB 不可用时
    回退因子目录快照（configs/factor_catalog_llm.json）——ECS 无行情库，
    没有快照兜底纠错/重试层会整个失效（2026-10-10 生产实测发现）。"""
    try:
        from quant_research_engine.data.settings import DatabaseSettings
        from quant_research_engine.data.postgres import PostgresDataStore
        from quant_research_engine.strategies.factor_request_queue import make_schema_column_lookup

        settings = DatabaseSettings(market_db_url=db_url) if db_url else DatabaseSettings.from_env()
        store = PostgresDataStore(settings)
        store.ping()
        return make_schema_column_lookup(store)
    except Exception:
        from quant_research_engine.gui.factor_catalog_llm import catalog_column_lookup

        return catalog_column_lookup()


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


# 校验+自动修复回路（CR-2026-10-09 第 3 层）：缺因子时把缺失名与库内相近
# 候选回喂 LLM 重试，用户无感
MAX_FIX_RETRIES = 2


def _fixup_prompt(description: str, bad_yaml: str, hints: list[dict[str, Any]]) -> str:
    """缺因子重试提示：原始需求 + 上次输出 + 缺失名与库内候选。"""
    lines = [
        "用户需求：" + description,
        "",
        "你上次输出的 YAML 引用了因子库中不存在的列：",
    ]
    for h in hints:
        label = f"{h['table']}.{h['column']}"
        if h.get("suggestions"):
            lines.append(f"- {label}（库内相近候选：{'、'.join(h['suggestions'])}）")
        else:
            lines.append(f"- {label}（库内无相近列，请改用其他已落库因子表达）")
    lines += [
        "",
        "上次输出：",
        bad_yaml,
        "",
        "请只输出修正后的完整 YAML（只改 factor_fields 引用为真实存在的列，其余不变；"
        "禁止编造列名）。",
    ]
    return "\n".join(lines)


def _validate_and_correct(
    raw: str,
    lookup: Callable[[str], set[str]],
) -> dict[str, Any]:
    """一次输出的处理：剥围栏 → YAML 校验 → factor_correction 纠错 → 缺失判定。

    返回 {ok, error?, yaml, mapping?, corrections, unresolved, missing}。
    """
    yaml_text = strip_yaml_fence(raw)
    validation = validate_yaml(yaml_text)
    if not validation["valid"]:
        return {
            "ok": False, "fatal": True, "yaml": yaml_text,
            "error": f"LLM 输出的 YAML 未通过策略规格校验：{validation['error']}。可编辑下方草稿修正后使用。",
            "code": "invalid_yaml", "corrections": [], "unresolved": [], "missing": [],
        }
    import yaml as _yaml

    from quant_research_engine.gui.factor_correction import correct_factor_fields

    mapping = _yaml.safe_load(yaml_text)
    report = correct_factor_fields(mapping, lookup)
    corrections = report["corrections"]
    unresolved = report["unresolved"]
    if corrections:
        yaml_text = _yaml.safe_dump(mapping, allow_unicode=True, sort_keys=False)
        revalidation = validate_yaml(yaml_text)
        if not revalidation["valid"]:  # 兜底：纠错产物异常则退回原 YAML 与原名
            yaml_text = strip_yaml_fence(raw)
            mapping = _yaml.safe_load(yaml_text)
            report = correct_factor_fields(mapping, lookup)
            corrections = []
            unresolved = report["unresolved"]
    spec = StrategySpec.from_mapping(mapping)
    missing = find_missing_factor_columns(spec, lookup)
    return {"ok": not missing, "yaml": yaml_text, "corrections": corrections,
            "unresolved": unresolved, "missing": missing}


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
      {"ok": True, "yaml": str, "warnings": [str, ...], "corrections": 可选,
       "fix_attempts": 可选（修复重试次数，>0 表示走了回喂回路）}
      {"ok": False, "code": "not_configured", "error": 中文}
      {"ok": False, "code": "llm_error"|"invalid_yaml"|"missing_factors",
       "error": 中文（含候选因子提示）, "yaml": 可选草稿,
       "missing_factors": [...], "suggestions": [...], "corrections": 可选}

    四层防线（CR-2026-10-09）：①真实因子目录注入 prompt；②别名字典归一；
    ③缺因子回喂 LLM 重试（最多 MAX_FIX_RETRIES 次，用户无感）；④兜底报错
    附候选与申请新增因子指引。
    """
    description = (description or "").strip()
    if not description:
        return {"ok": False, "code": "empty", "error": "请先用自然语言描述策略"}

    config = nl_config(env)
    if config is None:
        return {"ok": False, "code": "not_configured", "error": NOT_CONFIGURED_ERROR}

    lookup = column_lookup if column_lookup is not None else _default_column_lookup(db_url)
    warnings: list[str] = []
    if lookup is None:
        warnings.append("因子库不可用，跳过因子存在性检查（提交回测时仍会校验）")

    # 修复回路：LLM 输出 → 校验+纠错 → 缺因子则回喂重试（仅 lookup 可用时）
    prompt = description
    fix_attempts = 0
    outcome: dict[str, Any] | None = None
    for attempt in range(1 + (MAX_FIX_RETRIES if lookup is not None else 0)):
        try:
            raw = call_llm(prompt, config, http_post=http_post)
        except Exception as exc:
            return {"ok": False, "code": "llm_error", "error": f"LLM 调用失败：{exc}"}
        outcome = _validate_and_correct(raw, lookup) if lookup is not None else None
        if lookup is None:
            yaml_text = strip_yaml_fence(raw)
            validation = validate_yaml(yaml_text)
            if not validation["valid"]:
                return {
                    "ok": False, "code": "invalid_yaml", "yaml": yaml_text,
                    "error": f"LLM 输出的 YAML 未通过策略规格校验：{validation['error']}。可编辑下方草稿修正后使用。",
                }
            outcome = {"ok": True, "yaml": yaml_text, "corrections": [], "unresolved": [], "missing": []}
            break
        assert outcome is not None
        if outcome.get("fatal"):  # YAML 结构错误不回喂重试（与因子无关）
            return {"ok": False, "code": outcome["code"], "error": outcome["error"],
                    "yaml": outcome["yaml"]}
        if outcome["ok"]:
            break
        if attempt < MAX_FIX_RETRIES:
            fix_attempts += 1
            prompt = _fixup_prompt(description, outcome["yaml"], outcome["unresolved"])

    assert outcome is not None
    yaml_text = outcome["yaml"]
    corrections = outcome["corrections"]
    unresolved_hints = outcome["unresolved"]
    missing = outcome["missing"]

    if missing:
        import yaml as _yaml

        spec = StrategySpec.from_mapping(_yaml.safe_load(yaml_text))
        try:
            _enqueue_missing_factors(spec, missing, queue_path=queue_path or DEFAULT_QUEUE_PATH)
        except OSError:
            pass  # 队列文件不可写（如 ECS 权限）不阻塞报错主流程
        names = "、".join(f"{f.logical_name}({f.qualified_table}.{f.source_column})" for f in missing)
        error = f"该策略已搁置：缺因子 {names}，已加入补因子队列通知 indicators_tushare 项目。"
        if unresolved_hints:
            error += "\n" + format_unresolved_hint(unresolved_hints)
        if corrections:
            error += "\n" + format_corrections_note(corrections)
        result: dict[str, Any] = {
            "ok": False,
            "code": "missing_factors",
            "error": error,
            "yaml": yaml_text,
            "missing_factors": [f.logical_name for f in missing],
            "suggestions": unresolved_hints,
        }
        if corrections:
            result["corrections"] = corrections
        if fix_attempts:
            result["fix_attempts"] = fix_attempts
        return result

    result = {"ok": True, "yaml": yaml_text}
    if corrections:
        warnings.append(format_corrections_note(corrections))
        result["corrections"] = corrections
    if fix_attempts:
        result["fix_attempts"] = fix_attempts
        warnings.append(f"因子引用经 {fix_attempts} 轮自动修正后通过校验")
    if warnings:
        result["warnings"] = warnings
    return result
