"""P0-10 安全调度：峰值预算 / 在途记账 / RSS 早停看门狗（纯函数与合成轨迹）。

依据 `docs/agent/35_CAPACITY_MODEL_2026-11-03.md`：
- 准入记账用**实测包络**（未知全市场 = item3 实测 13.97 GB；轻任务 1.5 GB），
  不再假设所有 heavy 都是 6 GB（item3 超假设 2.3×）；
- 规划值 `estimate_peak_budget()` 带 1.25 余量（未知全市场 ≈17.5 GB），用于
  文档/状态展示；准入不重复计余量（余量由 RSS 早停 + RLIMIT_AS + cgroup 提供）；
- 在途记账 `BudgetLedger`：认领前原子预留，避免多个「未到峰值」的 heavy
  同时放行（item3 峰值在认领后 40–70 分钟的聚合/报告段）；
- RSS 早停 `rss_watchdog_verdict()`：超过子进程预算 80% **且持续上升**才终止，
  平台/单次尖峰不误杀。
"""

from __future__ import annotations

import pytest

from quant_research_engine.worker.capacity import (
    ADMISSION_BUDGET_GB,
    DEFAULT_WORKER_BUDGET_GB,
    PEAK_HEADROOM,
    BudgetLedger,
    _heavy_admission_gb,
    estimate_peak_budget,
    job_admission,
    peak_tier,
    rss_watchdog_verdict,
)


class TestHeavyAdmissionOverride:
    """`QRE_WORKER_HEAVY_ADMISSION_GB` 覆盖（2026-11-07 CF 2 路并行放行）。

    实测：CF 队列 12 个 heavy 任务 cgroup 峰值仅 6.05 GiB（含 876,042 笔），
    按 item3 最坏包络 13.97 记账会让两条重槽互斥（13.97×2 > 15.5 预算）。
    """

    def test_env_override_lets_two_heavy_slots_reserve(self, monkeypatch):
        monkeypatch.setenv("QRE_WORKER_HEAVY_ADMISSION_GB", "6.5")
        heavy = _heavy_admission_gb()
        assert heavy == pytest.approx(6.5)
        ledger = BudgetLedger(DEFAULT_WORKER_BUDGET_GB)
        assert ledger.try_reserve("heavy-1", heavy) is True
        assert ledger.try_reserve("heavy-2", heavy) is True
        assert ledger.inflight_gb() == pytest.approx(13.0)

    def test_worst_case_envelope_still_blocks_two_heavy_slots(self, monkeypatch):
        """不设覆盖时必须保持原行为：13.97×2 超出 15.5 预算，第二槽被挡。"""
        monkeypatch.delenv("QRE_WORKER_HEAVY_ADMISSION_GB", raising=False)
        heavy = _heavy_admission_gb()
        assert heavy == pytest.approx(13.97)
        ledger = BudgetLedger(DEFAULT_WORKER_BUDGET_GB)
        assert ledger.try_reserve("heavy-1", heavy) is True
        assert ledger.try_reserve("heavy-2", heavy) is False

    @pytest.mark.parametrize("raw", ["", "  ", "abc", "0", "-3.5"])
    def test_invalid_override_falls_back_to_default(self, monkeypatch, raw):
        monkeypatch.setenv("QRE_WORKER_HEAVY_ADMISSION_GB", raw)
        assert _heavy_admission_gb() == pytest.approx(13.97)


class TestEstimatePeakBudget:
    """包络模型（35 §2.1）：测量点取实测、×1.25 余量、外推标注未验证。"""

    def test_unknown_trades_uses_worst_measured_envelope(self):
        """未知策略（提交时无交易笔数）→ 最坏实测包络 × 余量 ≈ 17.5 GB。"""
        assert estimate_peak_budget(None) == pytest.approx(17.5, abs=0.01)
        assert estimate_peak_budget() == pytest.approx(17.5, abs=0.01)

    def test_measured_points_back_substitution(self):
        """三个测量点回代：≤2 万笔 7.9 / ≤8 万笔 8.0 / ≤50 万笔 17.5（35 §2.3 表）。"""
        assert estimate_peak_budget(0) == pytest.approx(7.9, abs=0.01)
        assert estimate_peak_budget(18_978) == pytest.approx(7.9, abs=0.01)   # item2
        assert estimate_peak_budget(76_511) == pytest.approx(8.0, abs=0.01)   # item1
        assert estimate_peak_budget(504_183) == pytest.approx(17.5, abs=0.01)  # item3

    def test_envelope_boundaries(self):
        """阶梯边界：19000/19001、80000/80001 翻转取上档（档位上限即实测笔数档）。"""
        assert estimate_peak_budget(19_000) == pytest.approx(7.9, abs=0.01)
        assert estimate_peak_budget(19_001) == pytest.approx(8.0, abs=0.01)
        assert estimate_peak_budget(80_000) == pytest.approx(8.0, abs=0.01)
        assert estimate_peak_budget(80_001) == pytest.approx(17.5, abs=0.01)

    def test_monotonic_non_decreasing(self):
        values = [estimate_peak_budget(t) for t in (0, 5_000, 19_000, 50_000,
                                                    76_511, 200_000, 504_183)]
        assert values == sorted(values)

    def test_extrapolation_beyond_measured_is_flagged_higher(self):
        """>50 万笔为未验证外推（斜率 17.7KB/笔）：只保证 ≥ 最坏实测档、量级合理。"""
        v = estimate_peak_budget(600_000)
        assert v > estimate_peak_budget(504_183)
        expected = (13.97 + 17_745 * (600_000 - 504_183) / 1024**3) * PEAK_HEADROOM
        assert v == pytest.approx(round(expected, 1), abs=0.01)

    def test_negative_trades_treated_as_zero(self):
        assert estimate_peak_budget(-5) == estimate_peak_budget(0)


class TestPeakTier:
    def test_tiers(self):
        assert peak_tier(0) == "low"
        assert peak_tier(19_000) == "low"
        assert peak_tier(19_001) == "mid"
        assert peak_tier(80_000) == "mid"
        assert peak_tier(80_001) == "high"
        assert peak_tier(504_183) == "high"
        assert peak_tier(None) == "unknown"


class TestJobAdmission:
    """worker 侧任务分级（与服务端 classify_job_weight 同口径的纯函数镜像）。"""

    def test_smoke_is_light(self):
        gb, tier = job_admission({"kind": "smoke", "params": {}})
        assert tier == "light" and gb == ADMISSION_BUDGET_GB["light"]

    def test_small_explicit_codes_is_light(self):
        gb, tier = job_admission({"kind": "full", "params": {"codes": ["000001.SZ"]}})
        assert tier == "light"

    def test_full_market_without_codes_is_heavy_unknown(self):
        gb, tier = job_admission({"kind": "full", "params": {}})
        assert tier == "heavy"
        # 准入用实测包络（13.97），不是 6GB 旧假设，也不是带余量的规划值
        assert gb == ADMISSION_BUDGET_GB["heavy"] == pytest.approx(13.97, abs=0.01)

    def test_many_codes_is_heavy(self):
        gb, tier = job_admission({"kind": "full",
                                  "params": {"codes": [f"{i:06d}.SZ" for i in range(50)]}})
        assert tier == "heavy" and gb == pytest.approx(13.97, abs=0.01)

    def test_universe_group_is_heavy(self):
        gb, tier = job_admission({"kind": "full",
                                  "params": {"universe": {"group": "sw", "key": "bank"}}})
        assert tier == "heavy"

    def test_params_json_string_and_legacy_params_key(self):
        import json
        gb, tier = job_admission({"kind": "full",
                                  "params_json": json.dumps({"codes": ["000001.SZ", "600000.SH"]})})
        assert tier == "light"
        gb2, tier2 = job_admission({"kind": "full", "params": {"codes": ["a", "b", "c",
                                                                         "d", "e", "f"]}})
        assert tier2 == "heavy"


class TestBudgetLedger:
    """在途记账：原子预留 → claim → 按真实档位定账 → 释放。"""

    def test_single_unknown_heavy_admitted_then_second_blocked(self):
        ledger = BudgetLedger(DEFAULT_WORKER_BUDGET_GB)
        assert ledger.try_reserve("heavy-1", ADMISSION_BUDGET_GB["heavy"]) is True
        # 第二个未知全市场 heavy：13.97+13.97 > 15.5 → 阻断（35：两个 item3 级必 OOM）
        assert ledger.try_reserve("heavy-2", ADMISSION_BUDGET_GB["heavy"]) is False

    def test_light_admitted_alongside_one_heavy(self):
        ledger = BudgetLedger(DEFAULT_WORKER_BUDGET_GB)
        assert ledger.try_reserve("heavy-1", ADMISSION_BUDGET_GB["heavy"]) is True
        # 13.97 + 1.5 = 15.47 ≤ 15.5：恰好再容一个轻任务（35 §2.4）
        assert ledger.try_reserve("light-1", ADMISSION_BUDGET_GB["light"]) is True
        # 第二个轻任务越线
        assert ledger.try_reserve("light-2", ADMISSION_BUDGET_GB["light"]) is False

    def test_release_frees_budget(self):
        ledger = BudgetLedger(DEFAULT_WORKER_BUDGET_GB)
        assert ledger.try_reserve("heavy-1", ADMISSION_BUDGET_GB["heavy"]) is True
        ledger.release("heavy-1")
        assert ledger.try_reserve("heavy-2", ADMISSION_BUDGET_GB["heavy"]) is True

    def test_commit_adjusts_reservation(self):
        """claim 后按任务真实档位定账（重槽领到轻任务时释放多预留）。"""
        ledger = BudgetLedger(DEFAULT_WORKER_BUDGET_GB)
        assert ledger.try_reserve("heavy-1", ADMISSION_BUDGET_GB["heavy"]) is True
        ledger.commit("heavy-1", ADMISSION_BUDGET_GB["light"])
        assert ledger.inflight_gb() == pytest.approx(1.5, abs=0.01)
        # 定账为轻任务后，另一个 heavy 也能进（1.5+13.97 ≤ 15.5）
        assert ledger.try_reserve("heavy-2", ADMISSION_BUDGET_GB["heavy"]) is True

    def test_exact_boundary_admitted(self):
        ledger = BudgetLedger(15.5)
        assert ledger.try_reserve("a", 13.97) is True
        assert ledger.try_reserve("b", 1.53) is True   # 15.50 恰好等于预算
        assert ledger.try_reserve("c", 0.01) is False

    def test_duplicate_key_reserve_replaces(self):
        ledger = BudgetLedger(15.5)
        assert ledger.try_reserve("heavy-1", 13.97) is True
        # 同键再预留（重试路径）：先释放旧占位再判定，不双重计费
        assert ledger.try_reserve("heavy-1", 1.5) is True
        assert ledger.inflight_gb() == pytest.approx(1.5, abs=0.01)

    def test_release_unknown_key_is_noop(self):
        ledger = BudgetLedger(15.5)
        ledger.release("nope")
        assert ledger.inflight_gb() == 0.0


class TestRssWatchdogVerdict:
    """RSS 早停：超 80% 预算且持续上升才终止；平台/单次尖峰不误杀。"""

    THRESHOLD = 0.8 * 12 * 1024  # 9830.4 MB（12GB 子进程预算的 80%）

    def test_rising_through_threshold_aborts(self):
        samples = [8000, 9500, 10000, 10500]
        assert rss_watchdog_verdict(samples, self.THRESHOLD) is True

    def test_slow_rise_crossing_threshold_aborts(self):
        samples = [9000, 9600, 9900, 10200]
        assert rss_watchdog_verdict(samples, self.THRESHOLD) is True

    def test_plateau_above_threshold_not_killed(self):
        """高位平台（稳态聚合结构）：不终止。"""
        samples = [9500, 9900, 9950, 9950, 9950]
        assert rss_watchdog_verdict(samples, self.THRESHOLD) is False

    def test_single_spike_not_killed(self):
        samples = [8000, 10500, 9000]
        assert rss_watchdog_verdict(samples, self.THRESHOLD) is False

    def test_below_threshold_rising_not_killed(self):
        samples = [5000, 6000, 7000]
        assert rss_watchdog_verdict(samples, self.THRESHOLD) is False

    def test_exactly_at_threshold_not_killed(self):
        samples = [9000, 9800, 9830, 9830]
        assert rss_watchdog_verdict(samples, self.THRESHOLD) is False

    def test_needs_minimum_samples(self):
        assert rss_watchdog_verdict([10500], self.THRESHOLD) is False
        assert rss_watchdog_verdict([], self.THRESHOLD) is False

    def test_two_rising_samples_above_threshold_abort(self):
        """连续两档上升且末值超阈值即够（不需要三档）。"""
        assert rss_watchdog_verdict([9900, 10100], self.THRESHOLD) is True
