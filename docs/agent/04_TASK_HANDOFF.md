# Task Handoff

## Task ID

QRE-RISK-RATES-005 (FRM 风险管理模块 R5：利率与债券计算内核)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

R5 在 R1–R4 已完成的 risk 包上落地利率与债券计算内核（依据已批准 CR
`docs/frm/CR_2026-08-23_risk_derivatives_extension.md` R5 阶段，纯函数
零 DB 零行情）：新增 `risk/rates.py`（式 16.1–16.5 复利换算、PV/FV、
spot↔折现因子、书4 Ch9 附息债 bootstrap 零息曲线、线性/对数线性插值、
远期利率连续式与式 10.5、par yield 式 16.7/10.4）与 `risk/bonds.py`
（YTM brentq、actual/actual 与 30/360 应计利息、式 12.6 久期凸性、
式 12.1/12.3 effective duration/convexity、DV01 与 D↔DV01 换算、
组合聚合与 DV01 对冲配比、式 12.4 平行移动二阶近似、书4 Ch13 KR01
含 ΣKR01=DV01 自检、书3 Ch16/17 转债债底折现与 spread duration）；
`risk/constants.py` 追加集中参数（day count/插值/key rate 节点/Δr bp/
YTM bracket，全部结果 dict 回显）；`pyproject.toml` 补 scipy 显式依赖。
教材数值全复现：bootstrap d=0.991909/0.980944/0.969406/0.956909、
par yield 2.2103%、平坦曲线年金解析解 P/D/C、DV01↔D 自洽、
ΣKR01=DV01、+100bp 二阶近似 vs 重定价 rel 1.9e-5。1657 tests green
（+52）。既有 risk 模块零行为改动。未 commit、未重启 qre-gui（用户
约束）。细节见 `09_CODING_HANDOFF.md` 顶部。上一任务：
QRE-RISK-GATE-004（R4 晋升闸风险判据，1605 green，待审批）。

# Task Handoff (archive: QRE-RISK-GATE-004, R4 晋升闸风险判据)

## Task ID

QRE-RISK-GATE-004 (FRM 风险管理模块 R4：晋升全量回测闸加入风险判据)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

R4 在 R3（risk_report.json 随 completed run 自动生成）上给晋升全量回测闸
（QRE-GUI-PROMO-GATE-001，commit cfb860d）加风险维度：`risk/constants.py`
集中阈值（`GATE_ES99_MAX=0.03`、`GATE_VAR_CONFIDENCE=0.99`）；
`gui/risk_report.py::evaluate_gate_risk(run_id)` 读该 run 的
risk_report.json——99% ES（历史模拟日收益口径）> 3% 或 99% 覆盖率
Kupiec LR `reject_5pct` → `risk.status=warning`；report 缺失/损坏 →
unavailable 不阻断；`strategy_create.finalize_promotion_gate` 写 gate json
新 `risk` 节，主判据照旧；`refresh_registry.gate_blocks_daily` 扩展为
failed 或 risk=warning 且非 forced 即阻止日更（force 通道照评估不阻断）；
admin.html 闸列 warning 追加「⚠ 风险警示」徽标（tooltip ES99 + VaR 回测
结论）+ style.css `.gate-risk`。1605 tests green（+6 净增：四情形 + force
覆盖 + 徽标渲染）。存量 gate json 无 risk 节行为不变。未 commit、未重启
qre-gui（用户约束）。细节见 `09_CODING_HANDOFF.md` 顶部。上一任务：
QRE-RISK-INTEGRATION-003（R3 集成，1599 green，commit 6852eaa）。

# Task Handoff (archive: QRE-RISK-CORE-002, R2 VaR 回测/压力测试/Bootstrap)

## Task ID

QRE-RISK-CORE-002 (FRM 风险管理模块 R2：VaR 回测 + 压力测试 + Bootstrap 推断)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

R2 在 R1（commit 96db59d）上落地三模块 + 报告扩展，公式以 FRM 知识摘要
为准：`backtest_var.py`（书2 Ch6：HIT 序列、覆盖率 Bernoulli LR + 精确
二项、独立性 Christoffersen 转移矩阵 LR——摘要未点名，注释标注出处
差异、多重检验假阳性 1−(1−α)ⁿ、backtest_var_summary 统一 dict）；
`stress.py`（书4 Ch8：A 股四历史情景库、回放=累计损失/峰谷/Peak/VaR +
相关性崩溃提示、reverse stress β 穿透反查市场冲击分位/σ 倍数）；
`inference.py`（书2 Ch13：arch CircularBlockBootstrap 块长 √n 给年化
收益/夏普/最大回撤算置信区间 + iid 对照 + MC 标准误 σ/√b）；`report.py`
升 R2（var_backtest 默认开用 EWMA μ=0 VaR、stress/bootstrap config 可选
开启）。46 个新测试全为已知答案核对（LR 手算 4.13085、转移计数手算、
情景回放手算 −0.119179/0.05/2.5、reverse β=2 穿透、bootstrap 固定 seed
CI 含真值 + MC 标准误核对、AR(1) 下 iid 低估 CBB）。1578 tests green
（+46 净增）。未 commit、未重启 qre-gui（用户约束）。细节见
`09_CODING_HANDOFF.md` 顶部。上一任务：QRE-RISK-CORE-001（R1 核心包，
1532 green，commit 96db59d）。

# Task Handoff (archive)

## Task ID

QRE-GUI-CREATE-GAPS-001 (新增策略/因子闭环四缺口)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

GUI「新增策略/新增因子」全链路四缺口补齐：①策略冒烟状态闭环——
engine._execute_and_finalize 终态钩子回写 `<name>.smoke.json`
（completed/failed + 关键指标 + finished_at，原子写），run 标记改由
run_backtest(mark=...) 预合并，list_sandbox 自愈滞留 running；前端沙箱列表
三色渲染 + 失败原因摘要 + 轮询刷新。②晋升状态闸——promote /
promote_factor 加 `force`，sidecar 非 completed → 409 smoke_not_passed，
force=true 管理员通道响应注明。③因子冒烟 120s 同步阻塞改异步——
start_smoke_job 复用 daily_jobs.start_script_job（lock_key=factor-smoke:<name>），
POST 即返 job_id + GET /api/factor-create/smoke/<job_id> 轮询 + 前端轮询，
120s 超时与 JSON 解析口径不变。④删 style.css .p3c-hidden 死代码。
1437 tests green（+20 净增）。未重启 qre-gui（用户约束），真实 E2E 待重启。
细节见 `09_CODING_HANDOFF.md` 顶部。

# Task Handoff (archive)

## Task ID

QRE-M5C-MINED-FACTOR-STRAT-001 (M5c：因子工厂 Top3 因子 → QRE 正式策略闭环验证)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

cluster-ashare M5c 联动任务：cluster.mined_factors Top3（MF_001/002/003）
转译为 cs07a/b/c（strategies/catalog/cross_sectional/），经沙箱→冒烟→晋升→
全市场近 1 年回测（批次 b21f1008ec98）→ report-audit 全通过。
截面分位语义由 cluster-ashare 物化表 cluster.mined_factor_flags 承载，
QRE 零代码改动。回测结论：近 1 年未复现 M3b 超额（超额 -11.1~-11.6%），
建议三因子转「衰减观察」——状态调整与是否 commit 均待用户审批。
细节见 `09_CODING_HANDOFF.md` 顶部。

## Task ID

QRE-STRATEGY-FIT-ANALYSIS-001 (M10.1, CR-0003 F3 phase 1)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

This handoff now covers QRE-CONTINUOUS-REFRESH-001 (M10.3). Summary: watermark-gated continuous refresh — `orchestration/refresh.py` + `scripts/refresh_batch.py` (check-only/force/rolling window), per-strategy delta report with manifest/audit parity, systemd user units documented (not installed); small-sample e2e passed; no full-scale execution per standing instruction.

## Current Owner

KIMI_CODE

## Problem Summary

The quick batch (106 strategies × 5,292 symbols × 2024) ranks strategies only by market-wide returns, which buries strategies with strong class-specific edge (user's example: 3% market-wide / 12% best-class). This slice adds the strategy-fit analysis layer: winner-stock enrichment across board/industry/cap/liquidity classes, noise filtering, and multiple-testing-adjusted rankings — reading existing batch artifacts only, no new backtest runs (user instruction 2026-07-19).

## Implementation Summary

Planning only so far (per approved roadmap order M9.1b → M10.1 → M10.2 → M10.3):

1. New `analysis/strategy_fit.py`: batch loading, read-only metadata join (class columns are absent from batch summary.csv — documented gap), configurable noise filters (min trades / min class size / NaN), **significance-tier winner selection** (exact binomial test on per-symbol win rate vs p=0.5 at 90%/99%/99.9% + magnitude gates — user refinement replacing top-10%), strategy-level meta-test vs false-positive expectation, hypergeometric enrichment (pure Python), BH-FDR adjustment, `class_edge` flagging.
2. `scripts/strategy_fit_report.py` command writing summary/classes/markdown report + `report_manifest.json` (new kind, `qre report-audit`-compatible).
3. Runner `--metadata-columns` passthrough so future batches embed class columns (optional for v1).
4. v1 explicitly excludes time-window stability (needs a per-symbol monthly-returns artifact — follow-up v1.1 recorded in CR-0003).

Previous task `QRE-VECTORIZED-ENGINE-001` (M9.1b) finalized in commit `c86441b` (42.8× speedup, metric-identical).

## Standing User Instructions

- No full-scale backtest runs until the core engine work is mostly complete (2026-07-19). Small-sample-first (R-QRE-009) applies to the future full-history (M9.4) runs.
- This slice complies: it executes zero backtests (reads existing CSV/JSON artifacts + one read-only metadata query).

## Hard Constraints

- No new dependencies; pure Python statistics (hypergeometric via `math.comb`, BH-FDR).
- Deterministic outputs; manifest audit parity (R-QRE-007); read-only DB access only (R-QRE-005).

## Validation Evidence

```bash
uv run pytest -q → 1045 passed
real batch: 106 analyzed / 5 skipped; metadata 5,256 symbols
qre report-audit outputs/strategy_fit/f365c8a07b33/report_manifest.json --require-match → status=ok, 0 issues
```
