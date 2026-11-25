"""QRE-SAAS-RESULT-CONTRACT-001：结果合同（版本 / 数据快照 / 收益口径 / 验证状态）。

背景（`docs/agent/08_IMPLEMENTATION_BRIEF.md` P0-1B）：
历史页面曾并存交集日收益累乘与初始资金加权两套收益，导致同一结果数值分裂。
2026-11-25 起统一为预留初始资金账户：总指标、曲线、区间卡与重播严格同源。

本模块是唯一权威：每个结果都必须能回答「哪个合同版本、数据截止到哪天、
两种口径分别是什么、验证状态如何」。分类只认**显式合同**与**显式例外表**，
禁止按 created_at / 当前时间动态猜测（否则「新结果自动算旧」会随部署时间漂移）。
"""

from __future__ import annotations

from typing import Any

# 当前结果合同版本。口径或验证规则变化时递增，历史行保持原版本号不变。
RESULT_CONTRACT_VERSION = "2026-11-25.1"

# 页面唯一的收益口径：总指标、曲线、区间卡与重播共用同一账户净值序列。
DAILY_RETURN_BASIS = "初始资金账户净值（Σ账户权益/Σ初始资金）"
TOTAL_RETURN_BASIS = "初始资金加权总收益（Σ期末权益/Σ初始资金−1）"

VERIFICATION_VERIFIED = "verified"
VERIFICATION_UNVERIFIED = "unverified"

# 未带 result_contract 列值的历史结果版本标记（不是日期，不参与比较）
LEGACY_VERSION = "legacy"

# 历史结果显式例外表：job_id → (验证状态, 依据)。
# 只收录人工核定项；新增/变更必须同步 docs/agent/06_DECISION_LOG.md。
# 58/66：2026-10-19 已按收益口径修正后的产物重算并人工复核（QRE-INJECTION-FIX-BACKFILL）。
# 74：只做过 price_basis 只读核查（订单为原始价尺度），收益口径未修正、未复核，
#     不得因 price_basis 通过就标 verified。
LEGACY_RESULT_CONTRACTS: dict[int, tuple[str, str]] = {
    58: (VERIFICATION_VERIFIED,
         "2026-10-19 已按收益口径修正后产物重算并人工复核（数值与 Σfinal/Σinitial−1 勾稽）"),
    66: (VERIFICATION_VERIFIED,
         "2026-10-19 已按收益口径修正后产物重算并人工复核（−14.76% 与净盈亏/profit_factor 自洽）"),
    74: (VERIFICATION_UNVERIFIED,
         "仅完成 price_basis 只读核查（订单为原始价尺度），收益口径未修正未复核，不用于公开展示"),
}

# 未在例外表内的历史结果默认判定
LEGACY_DEFAULT_NOTE = "历史结果未带结果合同，按旧口径/未验证处理，不用于公开展示"

LABELS = {
    VERIFICATION_VERIFIED: "已验证口径",
    VERIFICATION_UNVERIFIED: "旧口径·未验证",
}

# 徽标 data-tip：明确总指标与曲线使用同一初始资金账户口径。
CONTRACT_TIP_TEMPLATE = (
    "收益曲线 = {daily}；总收益率 = {total}。"
    "每只股票从回测起点预留初始资金，上市前持有现金，期末结转最终权益；"
    "总指标、曲线、区间卡与重播同源。数据截止 {data_until}。"
)


def build_result_contract(
    *,
    data_until: Any = None,
    verification: str = VERIFICATION_VERIFIED,
    note: str | None = None,
    version: str = RESULT_CONTRACT_VERSION,
) -> dict[str, Any]:
    """构造一条新结果的结果合同（worker 回传接收层注入，不改 worker 与引擎）。"""
    return {
        "version": version,
        "data_until": data_until,
        "daily_return_basis": DAILY_RETURN_BASIS,
        "total_return_basis": TOTAL_RETURN_BASIS,
        "verification": verification,
        "note": note or "",
    }


def resolve_result_contract(
    job_id: int,
    stored: Any = None,
    data_until: Any = None,
) -> dict[str, Any]:
    """把某 job 的结果归类成合同。

    优先显式存储的 result_contract（新回传结果自带当前版本）；
    没有/损坏时按 LEGACY_RESULT_CONTRACTS 显式例外表判定，再落到默认未验证。
    job_id 与已存合同是唯一输入——没有任何时间参数。
    """
    if isinstance(stored, dict) and stored.get("version"):
        contract = dict(stored)
        # 旧合同可能携带已废弃的交集口径；展示层统一使用当前同源口径。
        contract["daily_return_basis"] = DAILY_RETURN_BASIS
        contract["total_return_basis"] = TOTAL_RETURN_BASIS
        verification = contract.get("verification")
        if verification not in (VERIFICATION_VERIFIED, VERIFICATION_UNVERIFIED):
            verification = VERIFICATION_UNVERIFIED
        contract["verification"] = verification
        if contract.get("data_until") is None:
            contract["data_until"] = data_until
        contract.setdefault("note", "")
        return contract
    verification, note = LEGACY_RESULT_CONTRACTS.get(int(job_id),
                                                     (VERIFICATION_UNVERIFIED, LEGACY_DEFAULT_NOTE))
    return {
        "version": LEGACY_VERSION,
        "data_until": data_until,
        "daily_return_basis": DAILY_RETURN_BASIS,
        "total_return_basis": TOTAL_RETURN_BASIS,
        "verification": verification,
        "note": note,
    }


def is_verified(job_id: int, stored: Any = None) -> bool:
    """该结果是否可公开（经典策略展示只放行 verified）。"""
    return resolve_result_contract(job_id, stored)["verification"] == VERIFICATION_VERIFIED


def contract_view(job_id: int, stored: Any = None, data_until: Any = None) -> dict[str, Any]:
    """API / 前端直接消费的合同视图（含布尔、可见标签与合并后的口径说明）。"""
    contract = resolve_result_contract(job_id, stored, data_until)
    verified = contract["verification"] == VERIFICATION_VERIFIED
    return {
        "version": contract["version"],
        "data_until": contract.get("data_until"),
        "verification": contract["verification"],
        "verified": verified,
        "label": LABELS[contract["verification"]],
        "note": contract.get("note", ""),
        "daily_return_basis": contract["daily_return_basis"],
        "total_return_basis": contract["total_return_basis"],
        "tip": CONTRACT_TIP_TEMPLATE.format(
            daily=contract["daily_return_basis"],
            total=contract["total_return_basis"],
            data_until=contract.get("data_until") or "未声明",
        ),
    }
