"""自然语言 → 策略 YAML 编译器（GUI 通道 C, QRE-GUI-WORKBENCH-P2-001）。

配置完全走环境变量（OpenAI 兼容 chat completions 协议）：
  QRE_NL_LLM_BASE_URL / QRE_NL_LLM_API_KEY / QRE_NL_LLM_MODEL

未配置时返回中文"未配置 LLM"错误，UI 降级提示使用通道 A/B。
安全闸：编译结果绝不自动执行，只填充到 YAML 编辑器由用户确认后提交。
HTTP 层使用 stdlib urllib（项目无 requests 依赖，不新增）。

CR-2026-11-03（NL 语义优化与转义项目）：编译链增加「穿越语义硬闸」——
用户文本含上穿/下穿/金叉/死叉而 entry/exit 完全没有 ``.shift(1)`` 时，先回喂
LLM 修复，仍不达标就返回 ``code=semantic_cross_missing`` 明确报错，
**绝不静默降级成当日状态**（旧口径正是这样把金叉死叉编译成长开/长平的）。
语义判定、canonical 术语表与 canonical YAML 规范化见 ``gui/nl_semantics.py``。
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
- holding: {max_holding_days: 整数；用户未说明时由系统统一设为 0（不限持仓天数）}
- risk: {stop_loss_pct: 小数或 null, take_profit_pct: 小数或 null, trailing_stop_pct: 小数或 null}  # 用户没提就省略或 null
- universe: {exclude_st: true, exclude_suspended: true, exclude_risk_warning: true, min_listing_days: 120}
- evaluation: {forward_return_horizons: [1, 3, 5, 10, 20], quantiles: 5}

信号表达式语法（安全子集）：
- 操作数：因子/行情别名、数值常量
- 比较：< > <= >= == != ；布尔：and or not ；算术：+ - * / ；括号
- 方法链：.shift(n) 引用上一周期、.rolling(N).max()/min()/mean() 等滚动统计
  （裸函数调用如 rolling_max(close, N) 非法，会被安全闸拒绝）

**穿越语义（最高优先，CR-2026-11-03）**：
- 「大于/小于/高于/低于」= 当日状态，直接写 (A > B)，**禁止加 .shift(1)**；
- 「上穿/下穿/金叉/死叉」= 穿越事件（只在穿越当日触发一次），**必须用 .shift(1)**：
  上穿：(A > B) and (A.shift(1) <= B.shift(1))
  下穿：(A < B) and (A.shift(1) >= B.shift(1))
- MACD 金叉 = DIF 上穿 DEA；死叉 = DIF 下穿 DEA
  （DIF=macd_12_26_9，DEA/信号线=macds_12_26_9）
- 把穿越事件写成没有 .shift(1) 的当日状态是**错误编译**（信号会持续为真、
  重复触发），用户文本一旦出现上穿/下穿/金叉/死叉，对应条件就必须带 .shift(1)。

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

示例 3（穿越事件：上穿/下穿必须带 .shift(1)）：
用户：SMA5 上穿 SMA200 买入，下穿 SMA200 卖出，不设止损
输出：
experiment:
  name: nl_sma5_cross_sma200
  market_profile: ashare_daily_default
  frequency: daily
data:
  market_fields: [open, high, low, close, pre_close, vol, amount]
  factor_fields:
    sma_5: factors.stock_daily_overlap_close.sma_5
    sma_200: factors.stock_daily_overlap_close.sma_200
universe:
  exclude_st: true
  exclude_suspended: true
  exclude_risk_warning: true
  min_listing_days: 120
signal:
  entry: (sma_5 > sma_200) and (sma_5.shift(1) <= sma_200.shift(1))
  exit: (sma_5 < sma_200) and (sma_5.shift(1) >= sma_200.shift(1))
holding:
  max_holding_days: 0
evaluation:
  forward_return_horizons: [1, 3, 5, 10, 20]
  quantiles: 5

示例 4（MACD 金叉/死叉 = DIF 穿越 DEA）：
用户：MACD 金叉买入，死叉卖出
输出：
experiment:
  name: nl_macd_golden_dead_cross
  market_profile: ashare_daily_default
  frequency: daily
data:
  market_fields: [open, high, low, close, pre_close, vol, amount]
  factor_fields:
    dif: factors.stock_daily_momentum_close.macd_12_26_9
    dea: factors.stock_daily_momentum_close.macds_12_26_9
universe:
  exclude_st: true
  exclude_suspended: true
  exclude_risk_warning: true
  min_listing_days: 120
signal:
  entry: (dif > dea) and (dif.shift(1) <= dea.shift(1))
  exit: (dif < dea) and (dif.shift(1) >= dea.shift(1))
holding:
  max_holding_days: 0
evaluation:
  forward_return_horizons: [1, 3, 5, 10, 20]
  quantiles: 5
"""


def build_system_prompt() -> str:
    """System prompt: DSL doc + 真实因子目录快照（有则用）+ indicator catalog +
    中文语义字典 + 常用已落库列 + few-shot examples。

    CR-2026-10-09 第 1 层：注入 configs/factor_catalog_llm.txt 的真实目录
    （factors.<表>.<列> 全量压缩清单），并加硬约束「factor_fields 只能引用
    清单内的表.列，禁止发明」。快照缺失（本地开发未生成）时回退旧口径。
    CR-2026-11-03：注入中文语义字典（金叉/死叉/快线/慢线/均线/回调/支撑/放量…），
    让中文股票语义确定性地落到表达式，而不是靠模型猜。"""
    from quant_research_engine.gui.factor_catalog_llm import load_catalog_text
    from quant_research_engine.gui.factor_correction import COMMON_FACTOR_TARGETS
    from quant_research_engine.gui.nl_semantics import render_semantic_dictionary
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
    return (
        _DSL_DOC
        + render_semantic_dictionary()
        + catalog_block
        + f"\n常用已落库列：{common_items}\n"
        + _FEW_SHOT
    )


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


def _fixup_prompt(description: str, bad_yaml: str, hints: list[dict[str, Any]],
                  semantic_issues: list[dict[str, Any]] | None = None) -> str:
    """缺因子重试提示：原始需求 + 上次输出 + 缺失名与库内候选。

    ``semantic_issues`` 非空时同时回喂穿越语义问题（CR-2026-11-03：因子与语义
    可以同一轮回喂，避免「修好因子又丢 shift(1)」的拉锯）。
    """
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
    if semantic_issues:
        lines += ["", "同时存在语义错误："]
        for issue in semantic_issues:
            lines.append(f"- {issue.get('message', '')}")
            if issue.get("hint"):
                lines.append(f"  正确写法：{issue['hint']}")
    lines += [
        "",
        "上次输出：",
        bad_yaml,
        "",
        "请只输出修正后的完整 YAML（只改 factor_fields 引用为真实存在的列"
        + ("，并按上述正确写法修好 signal.entry/exit 的穿越条件" if semantic_issues else "")
        + "；其余不变；禁止编造列名）。",
    ]
    return "\n".join(lines)


def _with_default_holding(yaml_text: str, description: str) -> str:
    """未明确持仓期限时统一为 0，覆盖模型自行补出的天数。"""
    import re
    import yaml as _yaml

    mapping = _yaml.safe_load(yaml_text)
    if not isinstance(mapping, dict):
        return yaml_text
    has_instruction = bool(re.search(
        r"持仓|持有|持股|最长|最多|至多|不超过|不得超过|\d+\s*(?:个)?(?:交易日|天|日|周|月|年)后(?:卖出|离场|平仓)",
        description or "",
    ))
    holding = mapping.get("holding")
    if isinstance(holding, dict) and holding.get("max_holding_days") is not None and not has_instruction:
        return re.sub(r"(?m)^(\s*max_holding_days\s*:\s*).*$", r"\g<1>0", yaml_text, count=1)
    if holding is None:
        mapping["holding"] = {"max_holding_days": 0}
    elif isinstance(holding, dict) and holding.get("max_holding_days") is None:
        holding["max_holding_days"] = 0
    else:
        return yaml_text
    return _yaml.safe_dump(mapping, allow_unicode=True, sort_keys=False)


def _validate_and_correct(
    raw: str,
    lookup: Callable[[str], set[str]] | None,
    description: str,
) -> dict[str, Any]:
    """一次输出的处理：剥围栏 → YAML 校验 → 因子纠错 → 穿越语义校验 → canonical 化。

    返回 {ok, error?, yaml, mapping?, corrections, unresolved, missing, semantic_issues}。
    ``lookup`` 为 None 时跳过因子存在性（仅在调用方拿不到任何目录时发生）。
    """
    from quant_research_engine.gui.nl_semantics import (
        canonical_yaml_text,
        cross_semantic_issues,
    )

    yaml_text = _with_default_holding(strip_yaml_fence(raw), description)
    import yaml as _yaml

    validation = validate_yaml(yaml_text)
    if not validation["valid"]:
        return {
            "ok": False, "fatal": True, "yaml": yaml_text,
            "error": f"LLM 输出的 YAML 未通过策略规格校验：{validation['error']}。可编辑下方草稿修正后使用。",
            "code": "invalid_yaml", "corrections": [], "unresolved": [], "missing": [],
            "semantic_issues": [],
        }
    from quant_research_engine.gui.factor_correction import correct_factor_fields

    mapping = _yaml.safe_load(yaml_text)
    semantic_issues = cross_semantic_issues(mapping, description)
    if lookup is None:
        return {
            "ok": not semantic_issues, "yaml": canonical_yaml_text(mapping), "mapping": mapping,
            "corrections": [], "unresolved": [], "missing": [],
            "semantic_issues": semantic_issues,
        }

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
            semantic_issues = cross_semantic_issues(mapping, description)
    spec = StrategySpec.from_mapping(mapping)
    missing = find_missing_factor_columns(spec, lookup)
    return {
        "ok": not missing and not semantic_issues,
        "yaml": canonical_yaml_text(mapping),
        "mapping": mapping,
        "corrections": corrections,
        "unresolved": unresolved,
        "missing": missing,
        "semantic_issues": semantic_issues,
    }


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
      {"ok": False, "code": "llm_error"|"invalid_yaml"|"missing_factors"|"semantic_cross_missing",
       "error": 中文（含候选因子提示）, "yaml": 可选草稿,
       "missing_factors": [...], "suggestions": [...], "corrections": 可选}

    五层防线（CR-2026-10-09 + CR-2026-11-03）：①真实因子目录注入 prompt；
    ②别名字典归一；③缺因子/穿越语义回喂 LLM 重试（最多 MAX_FIX_RETRIES 次，
    用户无感）；④兜底报错附候选与申请新增因子指引；⑤穿越语义硬闸——用户说了
    上穿/下穿/金叉/死叉而产物没有 .shift(1) 时，重试后仍不合法就明确报错，
    **绝不静默降级成当日状态**。
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

    # 修复回路：LLM 输出 → 校验+纠错+语义闸 → 缺因子/语义降级则回喂重试。
    # 语义闸不依赖因子库，lookup 缺失时同样生效。
    prompt = description
    fix_attempts = 0
    outcome: dict[str, Any] | None = None
    for attempt in range(1 + MAX_FIX_RETRIES):
        try:
            raw = call_llm(prompt, config, http_post=http_post)
        except Exception as exc:
            return {"ok": False, "code": "llm_error", "error": f"LLM 调用失败：{exc}"}
        outcome = _validate_and_correct(raw, lookup, description)
        assert outcome is not None
        if outcome.get("fatal"):  # YAML 结构错误不回喂重试（与因子无关）
            return {"ok": False, "code": outcome["code"], "error": outcome["error"],
                    "yaml": outcome["yaml"]}
        if outcome["ok"]:
            break
        if attempt < MAX_FIX_RETRIES:
            fix_attempts += 1
            if outcome.get("missing"):
                prompt = _fixup_prompt(description, outcome["yaml"], outcome["unresolved"],
                                       outcome.get("semantic_issues"))
            else:
                from quant_research_engine.gui.nl_semantics import cross_fix_prompt

                prompt = cross_fix_prompt(description, outcome["yaml"],
                                          outcome.get("semantic_issues"))

    assert outcome is not None
    yaml_text = outcome["yaml"]
    corrections = outcome["corrections"]
    unresolved_hints = outcome["unresolved"]
    missing = outcome["missing"]
    semantic_issues = outcome.get("semantic_issues") or []

    if semantic_issues:
        # CR-2026-11-03 语义硬闸：用户说了穿越、产物没有 .shift(1)，重试后仍不
        # 合法 → 明确报错并给出 canonical 写法。绝不允许静默降级成当日状态。
        from quant_research_engine.gui.nl_semantics import format_semantic_error

        result: dict[str, Any] = {
            "ok": False,
            "code": "semantic_cross_missing",
            "error": format_semantic_error(semantic_issues),
            "yaml": yaml_text,
            "semantic_issues": semantic_issues,
        }
        if fix_attempts:
            result["fix_attempts"] = fix_attempts
            result["warnings"] = [f"穿越语义经 {fix_attempts} 轮自动修正仍未达标，已停止并报告"]
        if warnings:
            result["warnings"] = list(warnings) + list(result.get("warnings") or [])
        return result

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
