"""QRE-FACTOR-BASIS-CONTRACT：因子复权口径硬契约测试。

契约三条（详见 `src/quant_research_engine/factor_basis.py` docstring）：
  1. 生成侧必须带**已登记**口径，带不上就报错，不许静默省略；
  2. 读取侧缺失/未登记一律拒发，且打 WARNING 留痕；
  3. 运维侧 `deploy/saas/scan-factor-basis.sh` 全量审计 live + 归档产物。

本文件锁第 1 条的**静态不变量**（常量单一来源、白名单判定）与第 3 条的资产在位；
第 2 条的端到端行为在 `tests/test_gui_saas.py::TestSymbolDetailRefresh`。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from quant_research_engine.factor_basis import (
    FACTOR_BASIS_QFQ_ANCHOR_V1,
    KNOWN_BASES,
    basis_reason,
    is_known_basis,
)

REPO = Path(__file__).resolve().parents[1]


class TestBasisValidator:
    @pytest.mark.parametrize("value,expected", [
        (None, "missing"),
        ("", "missing"),
        (123, "non-string:int"),
        ([], "non-string:list"),
        ("qfq_anchor_v2", "unknown:qfq_anchor_v2"),
        ("QFQ_ANCHOR_V1", "unknown:QFQ_ANCHOR_V1"),   # 大小写敏感，别静默放过
        (" qfq_anchor_v1", "unknown: qfq_anchor_v1"),  # 前后空格也不认
    ])
    def test_rejects_anything_not_registered(self, value, expected):
        assert basis_reason(value) == expected
        assert is_known_basis(value) is False

    def test_accepts_registered_basis(self):
        assert basis_reason(FACTOR_BASIS_QFQ_ANCHOR_V1) is None
        assert is_known_basis(FACTOR_BASIS_QFQ_ANCHOR_V1) is True

    def test_known_bases_is_not_empty_and_frozen(self):
        """白名单空 = 所有产物都会被拒发（自我 DoS）；可变 = 运行时能被改松。"""
        assert FACTOR_BASIS_QFQ_ANCHOR_V1 in KNOWN_BASES
        assert isinstance(KNOWN_BASES, frozenset)
        with pytest.raises(AttributeError):
            KNOWN_BASES.add("qfq_anchor_v2")  # type: ignore[attr-defined]


class TestSingleSourceOfTruth:
    """常量只许有一处定义：别处再出现字面量就会漂移（这类漂移已害过我们一次）。"""

    def test_lab_result_reexports_the_same_object(self):
        from quant_research_engine.gui import lab_result

        assert lab_result.FACTOR_BASIS_QFQ_ANCHOR_V1 is FACTOR_BASIS_QFQ_ANCHOR_V1

    def test_no_other_module_hardcodes_the_basis_literal(self):
        """全仓扫字面量：只允许契约模块与 lab_result 的 re-export 行出现。"""
        offenders = []
        for path in sorted((REPO / "src").rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            if '"qfq_anchor_v1"' not in text and "'qfq_anchor_v1'" not in text:
                continue
            rel = path.relative_to(REPO).as_posix()
            if rel in (
                "src/quant_research_engine/factor_basis.py",       # 定义处
                "src/quant_research_engine/gui/lab_result.py",     # re-export 行
            ):
                continue
            offenders.append(rel)
        assert not offenders, f"这些文件硬编码了复权口径字面量，改成引用契约模块：{offenders}"


class TestAuditScriptAsset:
    """契约第 3 条的审计脚本必须落盘且真的会判失败（防「脚本在但永远退 0」）。"""

    SCRIPT = "deploy/saas/scan-factor-basis.sh"

    def test_script_exists_and_is_executable(self):
        path = REPO / self.SCRIPT
        assert path.is_file(), f"{self.SCRIPT} 缺失"
        assert path.stat().st_mode & 0o111, "审计脚本必须可执行"

    def test_script_scans_both_live_and_archive(self):
        body = (REPO / self.SCRIPT).read_text(encoding="utf-8")
        assert "/srv/aguhuice/uploads" in body, "必须扫 live 产物"
        assert "/srv/aguhuice/archive" in body, "必须扫归档产物（归档≠下线，同样要审计）"
        assert "bad_total" in body, "必须统计坏产物数"

    def test_script_fails_nonzero_on_bad_artifacts(self):
        """最后一行必须是坏产物数判定——否则审计永远"通过"，比没有审计更糟。"""
        body = (REPO / self.SCRIPT).read_text(encoding="utf-8").strip()
        assert body.endswith('[ "${BAD_TOTAL:-0}" = "0" ]'), (
            "审计脚本必须以坏产物数作为退出码，发现问题必须非零退出"
        )

    def test_log_lands_in_repo_not_scratch(self):
        """审计日志同 MACD 周扫：落仓库内持久路径，不许放 .tmp（R6-1 的教训）。"""
        body = (REPO / self.SCRIPT).read_text(encoding="utf-8")
        assert "deploy/saas/factor-basis-scan.log" in body
        assert ".tmp/" not in body, "审计日志不许落在 .tmp（scratch 会被清）"
