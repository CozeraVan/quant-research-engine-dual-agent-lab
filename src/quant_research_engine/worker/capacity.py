"""P0-10 安全调度：峰值预算、在途记账、RSS 早停判定（纯函数，零 IO）。

依据 `docs/agent/35_CAPACITY_MODEL_2026-11-03.md`（P0-10 容量模型重建）：

- **准入记账用实测包络**：未知全市场 heavy 按 item3 实测峰值 13.97 GB 计
  （旧 R2 假设所有 heavy 6 GB，item3 超假设 2.3×；两个 item3 级并发 ≈28 GB
  必 OOM）。轻任务 1.5 GB（smoke/≤5 显式标的）。
- **规划值带余量**：`estimate_peak_budget()` = 包络 × 1.25（未知全市场 ≈17.5 GB），
  用于文档/状态展示与容量推演；准入不重复计余量——余量由 RSS 早停（80% 预算）、
  RLIMIT_AS（12 GB）与 cgroup（生产 qre-saas-worker.service MemoryMax=18G，
  2026-11-03 实测生效）三层提供。
- **在途记账**：`BudgetLedger` 认领前原子预留（reserve→claim→commit/release），
  避免多个「尚未到峰值」的 heavy 同时放行（item3 峰值出现在认领后 40–70 分钟的
  聚合/报告/序列化段，认领瞬间的 MemAvailable 闸门看不见它）。
- **RSS 早停判定**：`rss_watchdog_verdict()` 仅在「超过子进程预算 80% 且持续
  上升」时判终止；高位平台与单次尖峰不误杀。

单位：GB（十进制 1024**3）与 MB（1024**2）按函数参数注明；常量沿用压测文档
的「GB」写法（item3 RSS 峰值 13.97 GB）。
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Iterable

#: 回测子进程内存硬上限默认值（GB）。R-MEM-001 规则 2：单子进程峰值 ≤ 物理 50%
# （本机 23.5 GiB → ≈11.7 GiB，取 12）。原默认 14 已越线（item3 实测 13.97），
# 超限任务允许**可读失败**（MemoryError/早停），禁止以提高上限绕过——尾段分块
# 修复见 CF 后续安排。QRE_WORKER_CHILD_MEM_GB 可覆盖（0/负=不限制）。
DEFAULT_CHILD_MEM_LIMIT_GB = 12.0

#: 规划值余量（35 §2.1）：实测包络 × 1.25。
PEAK_HEADROOM = 1.25

#: 实测包络（交易笔数上限 → worker RSS 峰值 GB）：item2 18,978 笔/6.30、
#: item1 76,511 笔/6.38、item3 504,183 笔/13.97（27_STRESS_TEST §1/§7.5）。
_ENVELOPE: tuple[tuple[int, float], ...] = (
    (19_000, 6.30),
    (80_000, 6.38),
    (504_183, 13.97),
)

#: >50 万笔的外推斜率（B/笔）：item1/item3 两点拟合 17,745 B/笔 ≈ 17.3 KiB/笔。
#: **未验证**（仅 item3 单点之上的方向性外推），只用于规划值，不用于准入。
_EXTRAPOLATION_BYTES_PER_TRADE = 17_745

#: 未知策略（提交时无交易笔数）的最坏实测包络 = item3 峰值。
UNKNOWN_PEAK_GB = _ENVELOPE[-1][1]

#: 准入记账预算（GB，实测包络、不带余量）：轻任务 1.5（R2 既有轻槽预算）；
#: 未知全市场 heavy = 最坏实测 13.97（可被 `QRE_WORKER_HEAVY_ADMISSION_GB` 覆盖）。
def _heavy_admission_gb() -> float:
    """heavy 单任务准入记账值（GB），默认取最坏实测包络 13.97。

    为什么可覆盖（2026-11-07）：CF 全期全量队列 12 个 heavy 任务的 worker cgroup
    峰值只有 **6.05 GiB**（本次开机实测，含 876,042 笔的重交易量任务），远低于
    item3 压测的 13.97 GB。按 13.97 记账时两条重槽互相排斥——
    `在途预算不足（已用 13.97GB + 本任务 13.97GB > worker 预算 15.5GB），暂缓领取`，
    2 路并行名存实亡。按实测值记账（6.5）后 2 × 6.5 = 13 ≤ 15.5 才可能同时放行；
    真正的护栏仍是 cgroup `MemoryMax=18G` + `RLIMIT_AS 12G` + RSS 早停三层。
    非正数或不可解析一律回退默认值，不做静默放行。
    """
    raw = os.environ.get("QRE_WORKER_HEAVY_ADMISSION_GB")
    if raw is None or not str(raw).strip():
        return UNKNOWN_PEAK_GB
    try:
        value = float(raw)
    except ValueError:
        return UNKNOWN_PEAK_GB
    return value if value > 0 else UNKNOWN_PEAK_GB


ADMISSION_BUDGET_GB = {"light": 1.5, "heavy": _heavy_admission_gb()}

#: worker 级在途预算默认值（GB）：23.5 GiB 物理 − PG 峰值 5.4 − 系统/日常 ~2.5
#: ≈ 15.5（35 §2.4；压测实测单 item3 + PG + 系统后 MemAvailable 剩 ~6.3 GB）。
#: QRE_WORKER_BUDGET_GB 可覆盖。含义：在途任务预算总和 + 新任务 ≤ 该值才放行。
DEFAULT_WORKER_BUDGET_GB = 15.5

#: 服务端 classify_job_weight 的轻任务标的数上限镜像（app.py LIGHT_MAX_CODES）。
LIGHT_MAX_CODES = 5

#: RSS 早停：超过子进程预算的该比例且持续上升 → 终止（35 §3.2 第 4 条）。
RSS_EARLY_ABORT_RATIO = 0.8

#: RSS 早停采样间隔（秒）与持续上升判定窗口（样本数）。
RSS_POLL_SECONDS = 30.0
RSS_RISE_WINDOW = 3


def estimate_peak_budget(
    trades: int | None = None,
    *,
    headroom: float = PEAK_HEADROOM,
) -> float:
    """规划峰值预算（GB）：实测包络 × 余量；trades=None（未知）取最坏包络。

    - 测量点内：取不大于 trades 的最高实测档位（回代误差 0，构造使然）；
    - > 504,183 笔：按 17,745 B/笔外推（**未验证**，仅方向性参考）；
    - 返回值保留 1 位小数（7.9 / 8.0 / 17.5），与 35 §2.3 预算表一致。
    """
    if trades is None:
        base = UNKNOWN_PEAK_GB
    else:
        t = max(0, int(trades))
        base = _ENVELOPE[0][1]
        for cap, peak in _ENVELOPE:
            if t <= cap:
                base = peak
                break
        else:
            base = UNKNOWN_PEAK_GB + _EXTRAPOLATION_BYTES_PER_TRADE * (t - _ENVELOPE[-1][0]) / 1024**3
    # 1 位小数：与 35 §2.3 预算表（7.9 / 8.0 / 17.5）逐字一致
    return round(base * headroom, 1)


def peak_tier(trades: int | None) -> str:
    """换手档位：low / mid / high / unknown（trades=None 未知策略）。"""
    if trades is None:
        return "unknown"
    t = max(0, int(trades))
    if t <= _ENVELOPE[0][0]:
        return "low"
    if t <= _ENVELOPE[1][0]:
        return "mid"
    return "high"


def _job_params(job: dict[str, Any]) -> dict[str, Any]:
    params = job.get("params")
    if params is None:
        params = job.get("params_json")
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except (ValueError, TypeError):
            params = {}
    return params if isinstance(params, dict) else {}


def _codes_of(params: dict[str, Any]) -> list[str]:
    codes = params.get("codes") or []
    if isinstance(codes, str):
        codes = [c.strip() for c in codes.split(",") if c.strip()]
    return [c for c in codes if isinstance(c, str) and c]


def job_tier(job: dict[str, Any]) -> str:
    """任务轻重档位（与服务端 classify_job_weight 同口径的 worker 侧镜像）：
    smoke/≤5 显式标的 → light；板块/全市场/多标的 → heavy。"""
    if job.get("kind") == "smoke":
        return "light"
    params = _job_params(job)
    universe = params.get("universe")
    if isinstance(universe, dict) and universe.get("key"):
        return "heavy"
    codes = _codes_of(params)
    if 0 < len(codes) <= LIGHT_MAX_CODES:
        return "light"
    return "heavy"


def job_admission(job: dict[str, Any]) -> tuple[float, str]:
    """(准入预算 GB, 档位)。heavy 未知全市场按实测最坏包络 13.97 GB 记账。"""
    tier = job_tier(job)
    return ADMISSION_BUDGET_GB[tier], tier


class BudgetLedger:
    """worker 在途预算记账（线程安全）。

    生命周期：`try_reserve(key, gb)` 认领前原子预留（占位后才 claim，避免两个
    重槽同时放行）→ claim 成功 `commit(key, actual_gb)` 按任务真实档位定账 →
    任务结束 `release(key)`。预算判定含 1e-9 容差（浮点边界）。
    """

    def __init__(self, budget_gb: float = DEFAULT_WORKER_BUDGET_GB) -> None:
        self._budget_gb = float(budget_gb)
        self._lock = threading.Lock()
        self._entries: dict[str, float] = {}

    @property
    def budget_gb(self) -> float:
        return self._budget_gb

    def inflight_gb(self) -> float:
        with self._lock:
            return sum(self._entries.values())

    def try_reserve(self, key: str, gb: float) -> bool:
        """原子预留：本键旧占位先释放再判定（重试路径不双重计费）。"""
        with self._lock:
            current = self._entries.get(key, 0.0)
            total = sum(self._entries.values()) - current + float(gb)
            if total > self._budget_gb + 1e-9:
                return False
            self._entries[key] = float(gb)
            return True

    def commit(self, key: str, gb: float) -> None:
        """claim 后按任务真实档位定账（重槽领到轻任务时释放多预留）。"""
        with self._lock:
            if key in self._entries:
                self._entries[key] = float(gb)

    def release(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return dict(self._entries)


def rss_watchdog_verdict(
    samples: Iterable[float],
    threshold_mb: float,
    *,
    window: int = RSS_RISE_WINDOW,
) -> bool:
    """RSS 早停判定（MB）：末值**严格超过**阈值、尾部窗口无回落、且至少一段
    严格上升 → True（终止）。高位平台（无严格上升）与单次尖峰（有回落）不误杀；
    样本不足 2 个不判定。
    """
    tail = list(samples)[-window:]
    if len(tail) < 2:
        return False
    if tail[-1] <= threshold_mb:
        return False
    pairs = list(zip(tail, tail[1:]))
    if any(b < a for a, b in pairs):  # 窗口内有回落 → 非持续上升
        return False
    return any(b > a for a, b in pairs)


def early_abort_threshold_mb(child_limit_gb: float = DEFAULT_CHILD_MEM_LIMIT_GB) -> float:
    """早停阈值（MB）= 子进程预算 × 80%（35 §3.2：峰值前拦下，省 30–60 分钟）。"""
    return float(child_limit_gb) * 1024 * RSS_EARLY_ABORT_RATIO
