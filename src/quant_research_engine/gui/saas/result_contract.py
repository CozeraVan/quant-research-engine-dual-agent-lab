"""QRE-SAAS-RESULT-CONTRACT-001：结果合同（版本 / 数据快照 / 收益口径 / 验证状态）。

背景（`docs/agent/08_IMPLEMENTATION_BRIEF.md` P0-1B）：
同一页面长期并存两种都已剔除新股注资、但加权方式不同的收益口径——
① 收益曲线：日收益累乘（交集口径，cumret）；
② 总收益率：初始资金加权（Σfinal/Σinitial−1，与成交净盈亏/profit_factor 勾稽）。
数值可以有差，历史上被误读成「曲线和总收益矛盾」。同时 faf9629 修正前的大部分
历史产物数值不可信，P0-1A 又只排除了 price_basis 疑点，并未验证收益口径。

本模块是唯一权威：每个结果都必须能回答「哪个合同版本、数据截止到哪天、
两种口径分别是什么、验证状态如何」。分类只认**显式合同**与**显式例外表**，
禁止按 created_at / 当前时间动态猜测（否则「新结果自动算旧」会随部署时间漂移）。
"""

from __future__ import annotations

from typing import Any

# 当前结果合同版本。口径或验证规则变化时递增，历史行保持原版本号不变。
RESULT_CONTRACT_VERSION = "2026-10-25.1"

# 两种收益口径的权威文案（页面标签 / data-tip / API 同源，避免多处措辞漂移）
DAILY_RETURN_BASIS = "日收益累乘（交集口径，剔除新股注资）"
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

# 徽标 data-tip：一次讲清两种口径为什么可以不一致（页面与 API 同源）
CONTRACT_TIP_TEMPLATE = (
    "收益曲线 = {daily}；总收益率 = {total}。"
    "两者都已剔除新股注资，但加权方式不同（曲线按日复利、总收益按初始资金加权），"
    "数值可以有差，方向应一致。数据截止 {data_until}。"
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
        contract.setdefault("daily_return_basis", DAILY_RETURN_BASIS)
        contract.setdefault("total_return_basis", TOTAL_RETURN_BASIS)
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
