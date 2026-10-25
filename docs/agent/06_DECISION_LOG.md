### 2026-10-25: 自选因子入口改三栏弹窗，select 降级为隐藏数据字段

- Decision: 入口 2（自选因子交易）条件行的「大类 / 子类 / 因子」三个堆叠下拉，改为
  「当前因子选择按钮 + 三栏联动弹窗 + 名称/字段搜索」。原 `.wz-left`/`.wz-rfield`
  select **不删除、不改类名、不改 change 监听**，仅加 `.factor-picker-field` 类并
  `display:none`，继续作为唯一数据字段；按钮只负责显示当前「大类 / 子类 / 因子」
  与打开弹窗，不承载任何策略状态。最终因子选中后走 `syncFactorSelect` 写回隐藏
  select，再 `dispatchEvent(new Event('change', {bubbles:true}))` 复用原 change
  契约（refreshWizard），而不是直接调用刷新函数。
- Rationale: 因子库数百项，一行三个下拉无法浏览定位；但 YAML、`usedFactors()`、
  `readGroup()`、`snapshotWzArea()`、固定值切换、条件快照与策略还原、price basis
  归一都建立在「select.value 即真相」之上，任何并行状态都会造成两处不一致。保留
  隐藏 select 作为唯一值来源，让弹窗成为纯呈现层，契约回归面降到零。弹窗复用
  `FACTOR_OPTIONS`/`factorGroups()`/`factorSubs()` 与既有目录加载结果，不新增 API
  与依赖；样式复用既有 modal 组件与紫色主题变量，无新色相。移动端三栏降单列
  堆叠 + 各自内部滚动，保证 375px 无页面横向溢出。
- Owner: KIMI_CODE

# Decision Log

Use this file for decisions that affect architecture, data, safety, compliance, prompts, schema, deployment, or the development workflow.

### 2026-10-25: SaaS 提示组件 001 否决回退，002 改事件委托

- Decision: 001 用户验收否决，ECS 与本地全部回退且不 push；002 由 Kimi 实施。
  不再使用逐节点绑定 + hover/focus/click 通道状态 + refresh，改为 document
  事件委托 + 单例提示框。mouseover 只显示不 toggle，mouseout/focusout 关闭，
  touch/pen pointerup 才切换，动态重绘节点无需刷新绑定。
- Rationale: 001 文案覆盖不全、交互状态交叉导致重复悬停失效，且 DOM stub
  测试未覆盖真实浏览器可见性。002 必须先在 Chromium 验证连续 3 次悬停、
  指标卡正文、移动端 tap 和动态区间卡，再请求验收；未经明确指令不部署 ECS。
- Owner: KIMI_CODE

### 2026-10-19: P8 panel_factors 日更调度拓扑 + P5 risk pair-aware warmup

- Decision: panel_factors 全体系（P0-P3 基本面链 + P4/P5/P7 + 通道B）不进
  16:40 的 FactorBase 日更进程，而由独立 `panel-factors-daily.timer`
  （Mon..Fri 17:45，minute-csv-ingest 之后）驱动
  `scripts/panel_factors_daily.py`：watermark 幂等（每表 max(trade_date)，
  通道B 取 alpha_125d_000300 非空最大日）、8 步串行且每步独立子进程
  （内存隔离，守 R-MEM-001 23G 红线）、pit_panel→value/quality/growth
  依赖门控（pit 失败跳过下游，价格类步骤照常）、失败汇总退出 1 可安全重跑。
- Decision: `risk.py` 回归族 warmup 从「市场交易日数」（get_warmup_start
  1340 交易日）改为 `_pair_aware_warmup_start`（个股第 1326 行历史日期
  取 max）——回归族窗口按个股最近 1320 个有效 (r,ir) 样本对计数
  （停牌日不占窗），按交易日数供给会让窗口期停牌 >20 日的股票
  （实测 290 只）凑不足对数误产 NaN，增量≠全量。
- Rationale: 验证发现（2026-10-09 抽样 000796.SZ beta_1320d 存量有值、
  短 warmup 复算 NaN）；修复后增量单日全市场复算与存量全量值逐值一致
  （8/8 表 PASS）。已知残留：历史各年 chunk 起点附近的旧口径 NaN 不回填
  （如需修复可对 risk 做修复后全量重跑）。
- 8080 纳管口径：PANEL_FACTOR_TABLES 8 表登记为「日更中」（参与滞后判定
  与健康灯），列级对账清单由 EXPECTED_COLUMNS_SCRIPT 从 indicators 各
  模块权威常量注入；`_is_auto_managed_table` 保留给未来未知面板表的
  pending 通道。
- Owner: KIMI_CODE

### 2026-10-05: shared 模式交易费用拆分列成为引擎口径（CR-2026-10-05）

- Decision: shared（共享资金）模式交易行补齐 6 个费用拆分列
  （entry/exit × commission/stamp_tax/transfer_fee），键名与 vectorized 完全一致；
  lot 级按组件存储并按比例分摊；`calculate_cost_breakdown.total ==
  calculate_cost` 保证 cost 总口径不变；存量产物不回填。
- Rationale: 交易磨损卡佣金/印花税显示 0 的生产 bug；拆分后 full_market_report
  shared_cash 分支与 batch 同口径聚合，_fees_summary 不再把总磨损全算进
  「过户费/其他」。
- Owner: KIMI_CODE（根因已由用户定位确认）

### 2026-10-04: 策略信号监控数据模型——strategy_watches / signal_events（CR-2026-10-04 模块二）

- Decision: 新增 `strategy_watches`（UNIQUE(strategy_id,user_id)；scope_type ∈
  last_run_universe/sector/all_a/custom，scope_payload JSONB 存范围快照）与
  `signal_events`（UNIQUE(watch_id,trade_date,ts_code,signal_type) 防重，扫描重跑幂等）；
  `users.signals_last_read_at` 支撑 header 未读红点；`tier_policies` 加
  `scan_enabled`（默认 true，未来付费收窄开关）与 `max_watches`（默认 20）。
- 信号口径：日线收盘后 T+1 参考（price=收盘参考价），页面统一免责文案；
  明确不做盘中实时/推送渠道（channel 预留）。
- 扫描链路：本机 `deploy/saas/signal_scan.py` 挂 `qre-refresh.service`
  `ExecStartPost=-`（数据刷新完成后触发；失败不影响 refresh）；云端零新端口、
  零公网入站（worker token 出站拉 watches / 回传 signals）。
- Owner: KIMI_CODE（CR-2026-10-04 spec 已经用户批准）

### 2026-10-04: 策略资产化数据模型——strategies 加 entry_mode / wizard_state（CR-2026-10-04 模块一）

- Decision: `strategies` 表新增 `entry_mode TEXT`（nl/wizard/yaml）与
  `wizard_state JSONB`（向导结构化条件快照）。存量推断迁移：nl_text 非空 → nl，
  否则 → yaml（一次性 UPDATE，幂等 WHERE entry_mode IS NULL）。
- 写入链路：`POST /api/saas/strategies` 与 job 提交（api_create_job 的同名 upsert）
  均接收并落库；upsert 时 wizard_state 用 COALESCE 保留旧快照（未传不覆盖）。
- 降级规则：存量 wizard 策略无快照 → 详情页明示降级为 YAML 编辑（spec「风险」节）。
- 运维：懒自愈 ALTER 先查 information_schema（ECS strategies 表 owner 是 postgres，
  与 workers 表同一踩坑），ECS 首次手工 apply cloud_schema.sql 对应段。
- Rationale: 策略库从「一次性提交物」升级为可还原编辑态的资产（按创建入口还原），
  为模块二信号监控提供策略实体锚点。
- Owner: KIMI_CODE（CR-2026-10-04 spec 已经用户批准）

### 2026-08-23: 风向标预警阈值首轮校准观察（M3，初值不动）

- Decision: 预警阈值保留 CR §2 初值（相关 20 日升幅 > +0.10、VaR99 突破
  占比 > 3%），不调整；本记录为回填数据上的首轮观察。
- Observation（2019-01-02→2026-08-20，1,850 个交易日 market 行）：
  red 11 天（0.59%）全部为已知风险事件（2020-02-03/04/28 疫情、
  2024-01-29~02-05 + 2024-02-28 微盘、2024-10-09 国庆后回撤、
  2025-04-07 关税暴跌），选择性佳；amber 219 天（11.8%）。
  单判据频率：corr_change>0.10 占 5.8%（0.10 ≈ 全样本 P95，
  分位数 P50/P90/P95/P99 = −0.006/0.065/0.106/0.202）；
  breach>3% 占 7.2%（3% ≈ P93，P50/P90/P95/P99 =
  0.003/0.022/0.044/0.184）。
- Assessment: red 双超阈频率与质量均合理；amber 略多但作为早期预警
  可接受。若后续觉得 amber 过频，breach 阈值可上调至 4–5%（P95 附近），
  corr 阈值不动。留待 M3 上线后实际使用再定。
- Owner: KIMI_CODE (per CR §2 阈值校准要求)

### 2026-08-23: market_risk_daily 结果表落独立 schema `market_risk`（风向标 M2）

- Decision: 大盘/板块风险风向标结果表建在新 schema `market_risk`
  （表 `market_risk.daily`，PK (trade_date, scope)，行级 ON CONFLICT
  幂等 upsert）；不写 cluster schema。写库通道沿用 cluster 日更同款
  sqlalchemy engine + 单事务；收益口径用 `stock_daily.pct_chg/100`
  （tushare 前收盘口径，与 cluster-ashare tags_daily 一致）。
- Reason: QRE 产出与 cluster-ashare 产物（cluster schema）分空间，
  避免跨项目写对方 schema 的所有权混淆；与「引擎与结果分空间存放」
  既有原则一致；用户 van 已验证 CREATE SCHEMA 权限。
- Alternatives: 写 cluster schema（rejected——所有权混淆）；窗口
  DELETE+INSERT（rejected——结果行少、非千万级长表，行级 upsert 更简单）。
- Impact: 新增一个 schema + 一张表；业务表保持只读；QRE 首次向业务库
  写自有结果表（CR §4 已批准此通道）。
- Owner: KIMI_CODE (per approved CR_2026-08-23_market_risk_barometer §4)

## Format

### 2026-07-19: Record GPU availability (RTX 5070 Ti); defer GPU acceleration

- Decision: The user noted the local PC has an NVIDIA RTX 5070 Ti available for vectorized computation. Recorded as an environment fact. GPU acceleration is deliberately NOT adopted for the current engine/roadmap.
- Reason: Profiling shows the remaining hot paths are (a) per-symbol pandas signal evaluation (~10s/strategy, branchy AST walks on small arrays) and (b) window/rolling analytics (~28s/strategy, sliding-window ops on ~1.3M floats) and (c) a path-dependent event loop (inherently sequential). Small-array workloads are dominated by host↔device transfer overhead; GPU would add heavy dependencies (CuPy/PyTorch/CUDA toolkit) for marginal or negative gains. CPU vectorization + process-pool parallelism already delivers 40.2s/strategy and ~30 min catalog batches.
- Alternatives: adopt CuPy/PyTorch now (rejected — dependency cost and transfer overhead outweigh gains at current data sizes; project avoids heavy deps without explicit approval); Numba/CUDA for the event loop (rejected — path-dependent state machine is not GPU-parallelizable).
- Impact: No code change. GPU is a recorded option for future ML-scale work (e.g. M10.4 clustering phase 2, factor ML, large Monte Carlo) — adoption requires a dedicated dependency decision at that time.
- Owner: KIMI_CODE (user-noted environment fact)

### 2026-07-19: Externalize run outputs to `~/qre-outputs` (QRE-OUTPUTS-EXTERNAL-001)

- Decision: Run outputs (19GB / 3.09M files, ~99.9% of repo bloat) moved out of the project tree to `/home/van/qre-outputs/`; project keeps an `outputs` symlink for path compatibility. `QRE_OUTPUT_DIR` env var added to the batch runner as an override. `.gitignore` pattern changed `outputs/` → `outputs` to cover the symlink. `make clean` retargeted (resets the symlink, never deletes external data). `tests/` stays in the repo (3.8MB, standard pytest/packaging layout — user accepted the recommendation). All 19GB of historical outputs preserved per user decision (no cleanup).
- Reason: User asked to separate engine body, test files, and test result files into different spaces to avoid project bloat. Measurement showed outputs were essentially all of the bloat; tests were negligible.
- Alternatives: move `tests/` out too (rejected — zero bloat benefit, breaks standard tooling); delete stale giant batches (rejected by user — everything preserved); change all CLI defaults to the external path (rejected — symlink + runner env var achieves separation with zero behavior change).
- Impact: Repo working tree no longer carries run artifacts; existing docs/scripts/Makefile paths keep working through the symlink; `outputs/backtests/quick_batch_106/` remains the M10.1 input data at its documented path.
- Owner: KIMI_CODE (user-directed)

### 2026-07-19: Lock small-sample-before-full-scale run rule (R-QRE-009)

- Decision: New locked requirement R-QRE-009: before any full-market or full-history batch run that exercises new or changed engine/pipeline code, validate correctness and measure efficiency on a small sample first; only then proceed to full-scale runs.
- Reason: User standing instruction given together with the M9.1 commit approval. Efficiency surprises should surface on cheap runs, not after an 11-hour batch.
- Alternatives: keep ad-hoc run sizing (rejected — user issued a standing rule).
- Impact: `02_LOCKED_REQUIREMENTS.md` gains R-QRE-009; the M9.1b verification plan already follows it (sample-window equality checks before any catalog-scale run). Recorded as a docs-only follow-up to be committed with the M9.1b slice.
- Owner: KIMI_CODE (user instruction)

### 2026-07-19: Adopt strategy operations roadmap (CR-0003) and vectorized engine slice (M9.1b)

- Decision: Three user feature ideas were brainstormed, feasibility-checked, and adopted with aligned granularity. (1) **M9.1b** (`QRE-VECTORIZED-ENGINE-001`, added to CR-0002): a vectorized trade-level single-symbol engine — full-frame signal evaluation, groupby pre-split, event-level trade loop (loop over trades, not bars), vectorized equity-curve reconstruction, `position_sizing` modes (`full_compound` default = current all-in behavior, `fixed_cash`); must produce metric-identical results vs the existing bar simulator (per-symbol orders/trades/equity/summary parity tests). (2) **CR-0003** created with three slices: **M10.1** strategy-fit analysis & noise filtering (F3) — winner-stock enrichment across board/industry/cap/liquidity buckets with hypergeometric significance, min-trade-count and liquidity noise filters, M/Q-window stability checks, market-wide vs best-class excess ranking; absorbs M9.2 (statistical validation) and M9.3 (aggregate report) from CR-0002. **M10.2** unified runtime parameter overrides + backtest-time universe filtering (F1, CLI-first; GUI deferred). **M10.3** continuous refresh via watermark detection + idempotent full re-run (F2; stateful incremental rejected). **M10.4** optional ML clustering (F3 phase 2) is FUTURE and needs dependency approval. Execution order: M9.1b → M10.1 → M10.2 → M10.3.
- Reason: User wants an efficient engine and gave three feature directions (modular params + visualization, continuous testing, winner-stock clustering). Bar-simulation cost analysis showed ~98% of backtest runtime is the per-symbol `iterrows` loop and O(N×S) frame filtering; the batch engine's semantics (single position, all-in, no intra-hold decisions) make an exactly-equivalent trade-level implementation possible. F3's input data already exists (quick batch `f365c8a07b33`). Enrichment analysis needs zero new dependencies; idempotent re-run is simpler and safer than stateful incremental once M9.1b makes full re-runs cheap.
- Alternatives: stateful incremental refresh (rejected — complex, consistency-risky, and unnecessary after M9.1b); ML clustering immediately (rejected — prove value with dependency-free enrichment first); GUI-first F1 (rejected — CLI parameter overrides first, existing GUI skeleton untouched); keep per-symbol `iterrows` engine as the only implementation (rejected — 50x+ speedup available with identical results).
- Impact: Roadmap gains Milestone 9 (M9.1 DONE, M9.1b READY_FOR_BRIEF, M9.2/M9.3 MERGED into M10.1, M9.4 TODO) and Milestone 10 (M10.1-M10.4). Next implementation slice: M9.1b after the pending M9.1 commit.
- Owner: KIMI_CODE (user-aligned)

### 2026-07-18: Switch from dual-agent to single-agent development (Kimi Code)

- Decision: The project workflow changed from the dual-agent setup (Codex = planner/reviewer/git finalizer, Claude Code = implementer) to a single-agent setup where Kimi Code owns the full development cycle — planning (`08_IMPLEMENTATION_BRIEF.md`), implementation, self-review (`10_REVIEW_REPORT.md`), and git finalization after user approval. Task ID: `QRE-SINGLE-AGENT-MIGRATION-001`. All workflow documents were rewritten in place: `AGENTS.md` (single-agent instructions), `CLAUDE.md` (redirect page), `00/01/02/07/11/12` (single-agent wording), `08/09/10` (reset to the migration task), skills under `.agents/skills/` and `.claude/skills/` (de-prefixed and rewritten: `plan-brief`, `implement`, `self-review`, `git-finalize`, `intake-change`, `resume-task`, `update-progress`). Historical logs (`03_ROADMAP.md`, `05_PROGRESS.md`, this file) keep their original Owner attributions as history. New locked requirements R-AGENT-001/002/003 replace R-DUAL-001/002/003; R-GIT-001/002 now assign git execution to Kimi Code gated on self-review pass + explicit user approval. New phase vocabulary: `PLANNING` → `IMPLEMENTING` → `SELF_REVIEW` → `AWAITING_GIT_APPROVAL` → `DONE` / `USER_DIRECTED`.
- Reason: The development environment changed; only one agent (Kimi Code) is available. The user directed that future development flow must live in the `docs/agent/` markdown files as long-term memory rather than in CLI conversation history. A full documentation audit performed for this migration also found the 2026-05-28 closeout wording stale: `01_CURRENT_STATUS.md` claimed "fully frozen, no further work planned" while the strategy catalog batch backtest (106 OK / 5 missing-factor, completed 2026-05-30) was done afterwards and remains uncommitted; `08/10/12` still pointed at the old freeze-audit task. These inconsistencies were corrected in the same pass.
- Alternatives: archive the whole `docs/agent/` tree and start a fresh document set (rejected — history stays attached to the live workflow docs and the diff remains reviewable); keep dual-agent docs unchanged and only add a note (rejected — instruction files describing a two-agent flow would contradict reality); delete `CLAUDE.md` and `.claude/` (rejected — R-CORE-005 spirit; redirect page and rewritten skills preserve continuity).
- Impact: All future sessions start from `AGENTS.md` + `docs/agent/`; `CLAUDE.md` is a redirect page; `12_AGENT_BOARD.md` is deprecated; project directory name `quant-research-engine-dual-agent-lab` is now a known stale label left unchanged to avoid path breakage. Pending user decisions carried forward: (1) git-finalize the uncommitted batch backtest work products, (2) commission upstream factor computation for the 5 blocked strategies, (3) deeper validation batches (quick/full mode).
- Owner: KIMI_CODE (user-directed)

### 2026-05-28: Complete final freeze audit — all closeout tasks finished

- Decision: The final docs-only freeze audit pass (`QRE-DOCS-FINAL-FREEZE-AUDIT-001`) is complete. All active agent docs and the README were re-read and verified internally consistent after the status-label sync pass. One minor inconsistency was found and fixed: `01_CURRENT_STATUS.md` In Progress said "No active work" while the task was still WAITING_CLAUDE_CODE. Terminal labels use "Preserve" consistently, no stale feature-language remains, and zero runtime code changes were made.
- Reason: This is the absolute last docs-only verification pass. The repo is now fully frozen with all documentation closeout tasks complete.
- Alternatives: continue running more docs-only passes (rejected — no further passes are warranted; all docs are verified internally consistent); start new feature work (rejected — no further feature expansion is planned).
- Impact: All agent workflow files (`01`-`12`) now reflect DONE phase. QRE is complete for the current MVP scope. No further work is planned.
- Owner: CLAUDE_CODE

### 2026-05-28: Select final freeze audit as next Claude task

- Decision: The next Claude Code task is `QRE-DOCS-FINAL-FREEZE-AUDIT-001`.
- Reason: The final status-label sync pass is complete, but the repo still benefits from one last docs-only freeze audit to re-verify the maintenance-only wording before the closeout state is left locked.
- Alternatives: start a new runtime feature slice (rejected - no further feature expansion is planned); finalize immediately without a freeze audit (rejected - one last docs-only verification still adds value); reopen producer work in QRE (rejected - producer ownership remains in `quant_ts`).
- Impact: `01/04/05/08/09/11/12` now point to the final freeze audit lane for Claude Code.
- Owner: CLAUDE_CODE


### 2026-05-28: Complete archive-label consistency pass

- Decision: The final docs-only archive-label consistency pass (`QRE-DOCS-ARCHIVE-LABEL-CONSISTENCY-001`) is complete. Three historical Next Step labels in `05_PROGRESS.md` were normalized to "Preserve" for consistency with all other DONE tasks. Stale Problem/Implementation summaries in `04_TASK_HANDOFF.md` were corrected to describe the archive-label pass. All agent docs and the README remain internally consistent with the maintenance-only closeout state.
- Reason: This is the absolute last docs-only normalization pass. The frozen docs were already internally consistent; the only changes needed were to the agent workflow metadata files themselves (normalizing labels, correcting stale summaries).
- Alternatives: leave inconsistent labels in place (rejected — "Preserve" should be used consistently for all DONE-task next steps); skip the pass (rejected — one last normalization still adds value before final lock-down).
- Impact: `01/04/05/09/11/12` now reflect CODEX_REVIEWING phase. All documentation closeout tasks are complete. No further docs-only passes are warranted.
- Owner: CLAUDE_CODE

### 2026-05-28: Select archive-label consistency pass as next Claude task

- Decision: The next Claude Code task is `QRE-DOCS-ARCHIVE-LABEL-CONSISTENCY-001`.
- Reason: The freeze-lock pass is complete, but the repo still benefits from one final docs-only cleanup to normalize terminal labels and preserve-mode wording across the closeout docs.
- Alternatives: start a new runtime feature slice (rejected - no further feature expansion is planned); finalize immediately without a label-consistency pass (rejected - one last docs-only normalization still adds value); reopen producer work in QRE (rejected - producer ownership remains in `quant_ts`).
- Impact: `01/04/05/08/09/11/12` now point to the archive-label consistency lane for Claude Code.
- Owner: CLAUDE_CODE

### 2026-05-28: Complete final maintenance freeze-lock pass

- Decision: The final docs-only maintenance freeze-lock pass (`QRE-DOCS-MAINTENANCE-FREEZE-LOCK-001`) is complete. All active agent docs and the README are re-verified internally consistent with the maintenance-only closeout state. Zero stale feature-language or contradictory status text was found.
- Reason: This is the final freeze-lock check. Every agent doc and the README were re-read and verified. The CLI surface, README examples, and workflow docs remain internally consistent. No further passes are needed.
- Alternatives: skip the freeze-lock pass (rejected — one absolute final check is warranted); widen scope into runtime changes (rejected — no runtime changes allowed).
- Impact: `01/04/05/09/11/12` now reflect CODEX_REVIEWING phase. All documentation closeout tasks are complete. The repo is permanently frozen in maintenance mode.
- Owner: CLAUDE_CODE

### 2026-05-28: Select final maintenance freeze-lock pass as next Claude task

- Decision: The next Claude Code task is `QRE-DOCS-MAINTENANCE-FREEZE-LOCK-001`.
- Reason: The final docs-only maintenance sanity pass is complete, but the repo still benefits from one last freeze-lock pass to keep the frozen maintenance state explicit and catch any stale closeout wording before final lock-down.
- Alternatives: start a new runtime feature slice (rejected - no further feature expansion is planned); finalize immediately without a freeze-lock pass (rejected - one last docs-only check still adds value); reopen producer work in QRE (rejected - producer ownership remains in `quant_ts`).
- Impact: `01/04/05/08/09/11/12` now point to the final maintenance freeze-lock lane for Claude Code.
- Owner: CLAUDE_CODE

### 2026-05-28: Complete final maintenance sanity pass

- Decision: The final docs-only maintenance sanity pass (`QRE-DOCS-FINAL-MAINTENANCE-SANITY-001`) is complete. All active agent docs and the README are confirmed internally consistent with the maintenance-only closeout state. Zero stale feature-language or contradictory status text was found.
- Reason: This was the last docs-only sanity check before the repo is fully frozen. Every agent doc (`01`-`12`) and the README were re-read and verified. The CLI surface (18 commands), README examples, and workflow docs are internally consistent.
- Alternatives: skip the sanity pass (rejected — one last docs-only check adds value before final lock-down); widen scope into runtime changes (rejected — no runtime changes allowed).
- Impact: `01/04/05/09/11/12` now reflect CODEX_REVIEWING phase. All documentation closeout tasks are complete. The repo is fully frozen in maintenance mode.
- Owner: CLAUDE_CODE

### 2026-05-27: Select final maintenance sanity pass as next Claude task

- Decision: The next Claude Code task is `QRE-DOCS-FINAL-MAINTENANCE-SANITY-001`.
- Reason: The README example alignment pass is complete, but the repo still benefits from one final docs-only sanity pass to keep the frozen maintenance state explicit and catch any stale closeout wording before final lock-down.
- Alternatives: start a new runtime feature slice (rejected - no further feature expansion is planned); finalize immediately without a final sanity pass (rejected - one last docs-only check still adds value); reopen producer work in QRE (rejected - producer ownership remains in `quant_ts`).
- Impact: `01/04/05/08/09/11/12` now point to the final maintenance sanity lane for Claude Code.
- Owner: CLAUDE_CODE

### 2026-05-27: Complete README example alignment pass

- Decision: The final README example alignment pass (`QRE-DOCS-README-EXAMPLE-ALIGNMENT-001`) is complete. Every README code block and example was cross-checked against actual `qre --help` output for all 18 CLI subcommands. Zero discrepancies found.
- Reason: This was the last documentation-only task before the repo is fully frozen. Every flag (`--preflight`, `--output-dir`, `--random-baseline-seed`, `--print-summary-md`, `--stop-loss-pct`, `--status-only`, `--status-code`, `--status-summary`, `--validate-contents`, `--check-exists`, `--require-match`, etc.) was verified against current CLI help. All referenced strategy files were confirmed to exist on disk.
- Alternatives: skip the alignment pass (rejected — a final example cross-check still adds value before freeze); widen scope into runtime changes (rejected — no runtime changes allowed).
- Impact: `01/04/05/09/11/12` now reflect CODEX_REVIEWING phase. QRE has no remaining active tasks. The repo reads as maintenance-only with all code blocks verified synchronized.
- Owner: CLAUDE_CODE

### 2026-05-27: Select README example alignment as next Claude task

- Decision: The next Claude Code task is `QRE-DOCS-README-EXAMPLE-ALIGNMENT-001`.
- Reason: The CLI reference sync is already reviewed and accepted, but the repo still benefits from a final docs-only README example alignment pass to keep code blocks and examples synchronized with `qre --help`.
- Alternatives: stop after the reference sync and do nothing further (rejected - the docs can still benefit from one more narrow alignment pass); widen scope into runtime changes (rejected - no runtime changes allowed); reopen producer work in QRE (rejected - producer ownership remains in `quant_ts`).
- Impact: `01/04/05/06/08/09/11/12` now point to the README example alignment lane for Claude Code.
- Owner: CLAUDE_CODE

### 2026-05-27: Complete publication freeze guard

- Decision: The final publication freeze guard (`QRE-DOCS-PUBLICATION-FREEZE-001`) is complete. The README and agent docs remain maintenance-only, and the command surface matches the current CLI (18 commands).
- Reason: This was the last docs-only task before the repo is fully frozen in maintenance mode. A final cross-check of the README command tables against `qre --help` confirmed alignment. The README explicitly states no further feature expansion is planned.
- Alternatives: skip the freeze guard (rejected — a final docs-only confirmation still adds value before freeze); widen scope into runtime changes (rejected — no runtime changes allowed).
- Impact: `01/04/05/06/09/11/12` now reflect CODEX_REVIEWING phase. QRE has no remaining active tasks. The repo reads as maintenance-only with no stale implementation language.
- Owner: CLAUDE_CODE

### 2026-05-27: Select publication freeze guard as next Claude task

- Decision: The next Claude Code task is `QRE-DOCS-PUBLICATION-FREEZE-001`.
- Reason: The publication sanity pass is already reviewed and accepted, but the repo still benefits from one last docs-only freeze guard to ensure the README and agent docs remain maintenance-only and the visible command surface still matches the current CLI.
- Alternatives: start a new runtime feature slice (rejected - no further feature expansion is planned); skip the freeze guard and finalize immediately (rejected - a final docs-only confirmation still adds value before freeze); reopen producer work in QRE (rejected - producer ownership remains in `quant_ts`).
- Impact: `01/04/05/06/08/09/11/12` now point to the publication freeze lane for Claude Code.
- Owner: CLAUDE_CODE

### 2026-05-27: Complete final closeout wording alignment

- Decision: The final closeout wording alignment pass (`QRE-DOCS-CLOSEOUT-FINAL-ALIGNMENT-001`) is complete. Stale wording that implied benchmark-aware regime work was the next implementation slice has been removed from `01_CURRENT_STATUS.md` and `05_PROGRESS.md`.
- Reason: The status docs previously described "next evaluation slice" work as the remaining active task, which was misleading given that all implementation work is finished. The alignment pass removed that stale language so the repo reads as maintenance-only.
- Alternatives: leave the stale wording indefinitely (rejected — the status docs would remain misleading); expand scope beyond documentation (rejected — no runtime changes allowed).
- Impact: `01/04/05/09/11/12` now reflect CODEX_REVIEWING phase. QRE has no remaining active tasks. Agent docs are aligned with maintenance-only closeout.
- Owner: CLAUDE_CODE

### 2026-05-27: Select final closeout alignment as next Claude task

- Decision: The next Claude Code task is `QRE-DOCS-CLOSEOUT-FINAL-ALIGNMENT-001`.
- Reason: `QRE-NEXT-55` is already reviewed and marked PASS, but the active status docs still contain stale wording that implies benchmark-aware regime work is the next implementation slice. The remaining work is a documentation-only cleanup pass to remove that implication.
- Alternatives: start a new runtime feature slice (rejected - no further feature expansion is planned); ignore the stale wording and finalize immediately (rejected - the status docs would remain misleading); reopen producer work in QRE (rejected - producer ownership remains in `quant_ts`).
- Impact: `01/04/05/08/09/11/12` now point to the docs-only closeout alignment lane for Claude Code.
- Owner: CLAUDE_CODE

### 2026-05-27: Complete QRE-NEXT-55 tracker reconciliation

- Decision: The `QRE-NEXT-55` tracker row in `05_PROGRESS.md` is reconciled from `IMPLEMENTED` to `DONE` to match the already-accepted roadmap `M4.9` (real suspension/ST/risk-warning metadata). All agent docs (01/04/05/09/10/11/12) are aligned.
- Reason: The roadmap `M4.9` was already marked DONE with accepted evidence, but the progress tracker row remained in a stale `IMPLEMENTED` state. The fix-back review correctly identified the mismatch. The reconciliation was re-done with thorough updates across all affected files.
- Alternatives: leave the stale `IMPLEMENTED` entry indefinitely (rejected — tracker inconsistency); re-implement the metadata composition adapter (rejected — the code was already accepted and working).
- Impact: `05_PROGRESS.md` row now DONE; agent docs (01/04/09/10/11/12) aligned on CODEX_REVIEWING. QRE has no remaining stale tracker entries or active tasks awaiting implementation.
- Owner: CLAUDE_CODE

### 2026-05-27: Send QRE-NEXT-55 tracker reconciliation back for fix

- Decision: The `QRE-NEXT-55` review did not pass because the progress row still reads `IMPLEMENTED` and the agent-state documents still describe the task as pending reconciliation.
- Reason: The closeout workflow must not advance to a new task until the tracker row and state files are coherent.
- Alternatives: mark the task complete anyway (rejected — evidence shows the mismatch remains); open a new task before fixing the current one (rejected — this would compound the state inconsistency).
- Impact: `10_REVIEW_REPORT.md` now requests changes; `11_AGENT_STATE.md`, `04_TASK_HANDOFF.md`, `05_PROGRESS.md`, `09_CODING_HANDOFF.md`, and `12_AGENT_BOARD.md` now point Claude Code back at the tracker reconciliation fix.
- Owner: CODEX


### 2026-05-27: Complete backtest-smoke truthiness reconciliation

- Decision: The backtest-smoke truthiness entry in the tracker is reconciled from IMPLEMENTED to DONE. The truthiness fix (`_try_backtest_smoke()` executing real `BatchBacktestEngine` runs) was already implemented and accepted in code long ago; the tracker entry was simply stale.
- Reason: The lingering `IMPLEMENTED` status caused inconsistency with the rest of the tracker (all other tasks were DONE or properly classified). The reconciliation closes the last remaining tracker gap before finalization.
- Alternatives: leave the entry in IMPLEMENTED indefinitely (rejected — tracker inconsistency); re-implement the truthiness fix (rejected — the fix was already accepted and working).
- Impact: `05_PROGRESS.md` entry now DONE; agent docs (01/04/09/11/12) aligned. QRE has no remaining active tasks.
- Owner: CLAUDE_CODE

### 2026-05-27: Select backtest-smoke truthiness reconciliation as next Claude task

- Decision: The next Claude Code task is `QRE-STRATEGY-ENTRY-BACKTEST-SMOKE-TRUTHINESS-001`.
- Reason: The publication-readiness audit is complete, and the remaining visible implementation-shaped gap in the tracker is the backtest-smoke truthiness entry, which should be reconciled against the current CLI and review state before the repo is finalized.
- Alternatives: start a new runtime feature slice (rejected - no further feature expansion is planned); ignore the lingering IMPLEMENTED entry and finalize immediately (rejected - progress docs would remain inconsistent); reopen producer work in QRE (rejected - producer ownership remains with `quant_ts`).
- Impact: `01/04/05/08/09/11/12` now point to the truthiness reconciliation lane for Claude Code.
- Owner: CLAUDE_CODE

### 2026-05-27: Select publication-readiness doc audit as next Claude task

- Decision: The next Claude Code task is `QRE-DOCS-PUBLICATION-READINESS-001`.
- Reason: The README closeout pass is complete, and the remaining safe work is a final documentation audit to ensure the README and agent docs are fully publication-ready and still match the finalized CLI and artifact surface.
- Alternatives: start another runtime feature slice (rejected - no further feature expansion is planned); skip the final audit and finalize immediately (rejected - the docs should get one last consistency pass before publication); move producer work back into QRE (rejected - producer ownership remains with `quant_ts`).
- Impact: `01/04/05/08/09/11/12` now point to the publication-readiness docs audit lane for Claude Code.
- Owner: CLAUDE_CODE

### 2026-05-26: Wire benchmark series into standard eval frame assembly

- Decision: Thread benchmark series loading into `ResearchFrameAssembler.build()`, eval-smoke, eval-config, and research-run CLI paths so `benchmark_close`/`benchmark_return` columns reach the evaluation frame through standard assembly rather than requiring caller-side manual injection.
- Reason: The benchmark-aware regime precedence (002) relies on `benchmark_close`/`benchmark_return` being present in the evaluation frame, but these columns were only available when callers manually injected them. Wiring benchmark loading into the standard assembly path makes the regime precedence reachable through all normal eval entry points.
- Alternatives: Leave benchmark injection as a caller responsibility (rejected — breaks the regime priority chain for standard CLI/research-run workflows); add a separate benchmark loading phase outside the assembler (rejected — duplicates logic and increases caller complexity).
- Impact: `ResearchFrameAssembler.build()` now accepts `benchmark_table`, `benchmark_code`, `benchmark_value_column`; `ResearchRunRequest` carries benchmark fields; `qre eval-smoke`, `eval-config`, and `research-run` all accept `--benchmark-table`/`--benchmark-code`/`--benchmark-value-column`; 9 new tests; 922 total passed. Regime derivation logic unchanged.
- Owner: CLAUDE_CODE

### 2026-05-26: Implement deterministic regime classification from cross-sectional market data

- Decision: Derive regime labels (bull/bear/neutral) from cross-sectional median daily return rolling mean rather than requiring an external benchmark series.
- Reason: The evaluation frame already contains per-symbol daily close prices. Using the cross-sectional median return avoids external data dependencies while producing deterministic, reproducible labels. A rolling mean smooths daily noise. The brief explicitly allowed falling back to a market proxy derived from cross-sectional price movement when no benchmark column is present in-frame.
- Alternatives: Require an explicit benchmark close column in the frame (rejected — would require upstream schema changes and data loading work); use a fixed market-cap-weighted index (rejected — adds external dependency); skip regime classification entirely (rejected — user explicitly requested it).
- Impact: `EvaluationResult` now carries `regime_summary`; `write_evaluation_output()` exports `regime_summary.csv`; `report_manifest.py` registers the `regime_summary` role; 7 new tests; 907 total passed. Existing evaluation outputs unchanged.
- Owner: CLAUDE_CODE

### 2026-05-26: Implement benchmark-aware regime source preference

- Decision: `_derive_regime_labels()` now checks for explicit benchmark/market columns before falling back to the cross-sectional median close. Column precedence: `benchmark_close` → `benchmark_return` → cross-sectional median close.
- Reason: The evaluation frame may carry a `benchmark_close` or `benchmark_return` column when upstream assembly joins benchmark index data. When present, that explicit series is a stronger market-state signal than the cross-sectional proxy. When absent, the existing deterministic fallback preserves current behavior.
- Alternatives: Always require explicit benchmark (rejected — would break existing frames without benchmark data); use a fixed column name convention (rejected — `benchmark_close`/`benchmark_return` are already the natural names in the existing data model); skip the enhancement (rejected — the brief explicitly requested it).
- Impact: `_derive_regime_labels()` changed (3-branch precedence); `regime_summary` schema, CLI stdout, and manifest role unchanged; 7 new tests; 914 total passed. Cross-sectional fallback behavior preserved unchanged.
- Owner: CLAUDE_CODE

### 2026-05-26: Select benchmark-aware regime source preference as next Claude task

- Decision: The next Claude Code task is `QRE-EVAL-BENCHMARK-AWARE-REGIME-SUMMARY-002`.
- Reason: The current regime implementation is accepted, but the next low-risk improvement is to prefer explicit benchmark or market series columns when they are already present in the evaluation frame, with the existing cross-sectional fallback preserved.
- Alternatives: leave the current fallback-only regime helper as-is (rejected - the brief already allows a stronger explicit-series preference when available); jump to unrelated portfolio/report work (rejected - the current evaluation slice is the nearest consumer-side refinement).
- Impact: `01/03/04/05/08/09/11/12` now point to the benchmark-aware regime source-preference slice for Claude Code.
- Owner: CLAUDE_CODE

### 2026-05-26: Select benchmark series wiring into evaluation frames as next Claude task

- Decision: The next Claude Code task is `QRE-EVAL-BENCHMARK-SERIES-WIRING-003`.
- Reason: Benchmark-aware regime precedence is now accepted, but the standard eval/research-run entry points still do not thread benchmark bars into the evaluation frame. Wiring benchmark series through the normal path is the smallest remaining step that makes the new precedence reachable without changing the regime logic again.
- Alternatives: change the regime helper again (rejected - the precedence logic is already correct and reviewed); jump to unrelated portfolio work (rejected - the evaluation path is the immediate consumer-side gap); require producer changes in `quant_ts` (rejected - the needed benchmark series already exist on the read side).
- Impact: `01/03/04/05/08/09/11/12` now point to the benchmark-series wiring slice for Claude Code.
- Owner: CLAUDE_CODE

### 2026-05-26: Require benchmark manifest provenance and paired-argument validation for the wiring slice

- Decision: The benchmark-series wiring slice must record `benchmark_table`, `benchmark_code`, and `benchmark_value_column` in the eval and research-run manifests, and must reject half-specified benchmark CLI inputs.
- Reason: The benchmark frame wiring is correct, but the current implementation is not fully reproducible from saved artifacts and can silently accept invalid benchmark input combinations.
- Alternatives: leave the manifest fields implicit (rejected - reproducibility gap); keep silent no-op behavior for half-specified benchmark args (rejected - misleading and inconsistent with the existing paired-arg pattern used by other benchmark-aware commands).
- Impact: `01/03/04/05/08/09/11/12` now reflect the required fix pass for `QRE-EVAL-BENCHMARK-SERIES-WIRING-003`.
- Owner: CODEX

### 2026-05-26: Complete benchmark series wiring fix pass

- Decision: Record benchmark params in eval and research-run manifests, and reject half-specified benchmark CLI args.
- Reason: Codex review found that benchmark inputs were not persisted in run manifests and half-specified args were silently ignored. Both gaps compromise reproducibility and CLI usability.
- Alternatives: defer manifest fields (rejected — reproducibility gap); keep silent no-op for half-specified args (rejected — misleading UX).
- Impact: `write_evaluation_output()` now records `benchmark_table`/`benchmark_code`/`benchmark_value_column` in the eval `run_manifest.json`; `_write_research_manifest()` records them in `research_run_manifest.json`; eval-smoke, eval-config, and research-run handlers reject mismatched `--benchmark-table`/`--benchmark-code` with exit code 2; 10 new tests; 932 total passed. Regime logic unchanged.
- Owner: CLAUDE_CODE

### 2026-05-26: Select as-of metadata snapshot wiring as next Claude task

- Decision: The next Claude Code task is `QRE-REFERENCE-ASOF-METADATA-SNAPSHOT-001`.
- Reason: The remaining read-side gap is that metadata loaders still default to the latest available snapshot in some paths. Wiring an optional as-of date through metadata loading aligns metadata with the run date without changing producer ownership or benchmark/regime logic.
- Alternatives: keep latest-snapshot behavior forever (rejected - leaves run-date lookahead risk); move the work into `quant_ts` (rejected - the task is consumer-side and read-only); widen the slice into unrelated portfolio logic (rejected - unnecessary scope).
- Impact: `01/03/04/05/08/09/11/12` now point to the as-of metadata snapshot wiring slice for Claude Code. All direct backtest entry points are now wired and the slice is complete.
- Owner: CLAUDE_CODE

### 2026-05-26: Implement as-of metadata snapshot wiring

- Decision: Thread an optional `as_of` date through all read-side metadata loaders so consumers can request snapshots aligned with a specific date. SQL `MAX(trade_date)` subqueries are capped at the as-of date via `AND trade_date <= :as_of_date`, preserving the latest-snapshot fallback when as-of is omitted.
- Reason: Cross-sectional metadata (daily_basic market cap/liquidity, index_weight membership, security status flags) should reflect the state known at the run date rather than the latest available state, which can introduce lookahead when running historical evaluations.
- Alternatives: keep latest-snapshot as the only mode (rejected — leaves run-date lookahead risk); push the work into `quant_ts` (rejected — this is a read-side consumer concern, not a producer change); add a new denormalized snapshot table (rejected — the SQL subquery pattern is simpler and avoids schema changes).
- Impact: `ReferenceDataStore.load_security_metadata()` and all internal PostgreSQL loaders accept `as_of`; `ResearchFrameAssembler.build()`, `PreflightRequest`, and `ResearchRunRequest` carry `metadata_as_of`; `--metadata-as-of` CLI arg on eval-config, preflight, and research-run; 9 new tests; 941 total passed. Latest-snapshot behavior preserved unchanged when as-of is omitted.
- Owner: CLAUDE_CODE

### YYYY-MM-DD: Decision title

- Decision:
- Reason:
- Alternatives:
- Impact:
- Owner:

### 2026-05-26: Select portfolio baseline comparison as next Claude task

- Decision: The next Claude Code task is `QRE-PORTFOLIO-BASELINE-COMPARISON-001`.
- Reason: Strategy-report comparison fields still need to be wired consistently for buy-and-hold and benchmark-relative outputs, while the existing report schemas already reserve the required fields.
- Alternatives: jump to real regime classification (rejected - the user explicitly asked for strategy comparison next); broaden into new producer work (rejected - ownership remains in `quant_ts`); redesign report schemas (rejected - unnecessary churn).
- Impact: `01/03/04/05/08/09/11/12` now point to the portfolio baseline-comparison slice for Claude Code.
- Owner: CLAUDE_CODE

### 2026-05-25: Accept benchmark membership fix pass

- Decision: Accept the benchmark membership and industry normalization slice after the fix pass and Codex re-review.
- Reason: The real `reference.index_weight.con_code` schema is now handled correctly, `PreflightRunner` threads benchmark context, and the full test suite passes.
- Alternatives: keep the slice in fix mode (rejected - verification passed and no blocking findings remain); defer acceptance until git finalization (rejected - acceptance can be recorded independently from finalization).
- Impact: `01/03/04/05/09/10/11/12` now reflect `USER_ACCEPTANCE` / PASS status for the benchmark membership slice.
- Owner: CODEX

### 2026-05-25: Require benchmark schema alignment and preflight threading fix

- Decision: The benchmark membership slice stays in `CLAUDE_FIXING` until Claude Code aligns the `reference.index_weight` loader with the real `con_code` schema and threads `benchmark_code` through preflight metadata loading.
- Reason: Codex review found two production-path gaps that the current tests do not cover: the `quant_ts` source schema does not expose `ts_code`, and the preflight metadata path does not receive benchmark context.
- Alternatives: accept the current implementation as-is (rejected - the benchmark path would remain broken in production); defer the fix to a later slice (rejected - the issue is directly within the current task scope).
- Impact: `08/09/10/11/12/04/05/03/01` are updated to reflect `CLAUDE_FIXING`; Claude Code now owns the required fix pass.
- Owner: CODEX

### 2026-05-25: Assign QRE reference read-side wiring to Claude Code

- Decision: The next QRE implementation task is `QRE-REFERENCE-READ-SIDE-WIRING-001`, assigned to Claude Code under the Codex planner/reviewer workflow.
- Reason: The Tushare permission/download blocker has been resolved in `quant_ts`; populated `reference.*` tables now unblock QRE read-side benchmark and security-status metadata wiring. QRE should integrate those tables as a read-only consumer rather than restoring producer code.
- Alternatives: implement directly in Codex (rejected — user requested Codex remain planner/reviewer and Claude Code handle concrete coding); keep tasks blocked (rejected — source tables now exist); add a denormalized table requirement first (rejected — QRE can compose a latest-available snapshot read-side without expanding `quant_ts` scope).
- Impact: `08/09/10/11/12/04/05/03/01` switched to the QRE read-side integration lane. The task is intentionally narrow: benchmark/reference engine routing and composed `reference.*` metadata adapter only.
- Owner: CLAUDE_CODE

### 2026-05-25: Assign benchmark membership and industry adapters to Claude Code

- Decision: The next QRE implementation task is `QRE-BENCHMARK-MEMBERSHIP-INDUSTRY-ADAPTERS-001`, assigned to Claude Code under the Codex planner/reviewer workflow.
- Reason: The market-cap/liquidity slice is reviewed and complete. The next remaining non-deferred read-side gap is benchmark membership plus industry grouping normalization so grouped evaluation and portfolio outputs can use stable cross-sectional columns backed by `reference.index_weight` and the existing industry passthrough.
- Alternatives: jump to real regime classification (rejected — broader and not grounded in the current benchmark/industry grouping foundation); continue expanding Tushare producer work in QRE (rejected — ownership stays in `quant_ts`).
- Impact: `08/09/10/11/12/04/05/03/01` switched to the benchmark membership / industry adapter lane. The new slice stays read-only and remains strictly on the QRE consumer side.
- Owner: CLAUDE_CODE

### 2026-05-25: Assign market-cap/liquidity metadata standardization to Claude Code

- Decision: The next QRE implementation task is `QRE-REFERENCE-MARKET-CAP-LIQUIDITY-METADATA-001`, assigned to Claude Code under the Codex planner/reviewer workflow.
- Reason: The benchmark/reference wiring slice is reviewed and complete. The next remaining non-deferred data-layer gap is standardizing market-cap and liquidity metadata from `reference.daily_basic` so grouped evaluation and portfolio outputs can use consistent cross-sectional columns.
- Alternatives: jump to benchmark membership or regime classification (rejected — those are broader and depend on the same grouping foundation); continue expanding Tushare producer work in QRE (rejected — ownership stays in `quant_ts`).
- Impact: `08/09/10/11/12/04/05/03/01` switched to the market-cap/liquidity metadata lane. The new slice stays read-only and remains strictly on the QRE consumer side.
- Owner: CLAUDE_CODE

### 2026-05-24: Select preflight missing-factor shape audit as next Claude task

- Decision: The next Claude Code task is `QRE-RESEARCH-RUN-PREFLIGHT-MISSING-FACTOR-SHAPE-AUDIT-001`.
- Reason: The preflight shape audit is now PASS, but `missing_factor_requests[]` entries are still only list-checked and can carry malformed handoff payloads. This is the last narrow audit gap in the research-run preflight contract.
- Alternatives: move to blocked benchmark/security metadata work (rejected — source tables remain unconfirmed); widen the current preflight slice to unrelated fields (rejected — unnecessary risk and scope creep).
- Impact: `01/03/04/05/08/09/11/12` switched to the missing-factor audit implementation lane.
- Owner: CLAUDE_CODE

### 2026-05-25: Add QRE-owned reference-data ingestion scaffold

- Decision: Implement a small QRE-owned scaffold for benchmark/reference data planning and future Tushare sync, using explicit `reference.*` target schemas and env-only credentials.
- Reason: QRE now needs real benchmark/index and security-status reference data for benchmark comparison, preflight filters, and metadata diagnostics. The user will resolve higher Tushare permissions tomorrow, so the safe current step is to standardize data requirements and entry points without performing real downloads.
- Alternatives: Defer all work until permissions are available (rejected — schema and planning can be completed now); copy the neighboring `quant_ts` configuration directly (rejected — it contains hardcoded credentials and dynamic schema drift risks); hand off to Claude Code (rejected — scope stayed small enough for Codex to complete directly).
- Impact: Added `qre reference-data list/schema/plan/sync`, `scripts/sync_reference_data.py`, `docs/modules/reference_data_ingestion.md`, and tests for catalog/schema/planning behavior. Real sync remains gated by `QRE_TUSHARE_TOKEN`/`TUSHARE_TOKEN` and `QRE_REFERENCE_DB_URL`/`QRE_MARKET_DB_URL`.
- Owner: CODEX

### 2026-05-25: Move reference-data ingestion ownership to quant_ts

- Decision: Tushare reference-data download and PostgreSQL ingestion belong in sibling `quant_ts`, not QRE.
- Reason: User clarified `quant_ts` is the Tushare database download/local-ingestion project, while QRE should remain the backtest engine.
- Alternatives: Keep QRE-owned scaffold (rejected — violates project responsibility split); modify existing `quant_ts` daily scheduler directly (rejected — unnecessary risk to the stable daily task).
- Impact: Added standalone reference-data handler, sync CLI, permission smoke, and docs under `../quant_ts`; removed QRE producer module/scripts/tests/CLI command; QRE docs now point to `quant_ts` for data production.
- Owner: CODEX

### 2026-05-24: Implement preflight missing-factor shape audit

- Decision: Validated `missing_factor_requests[]` item object shape in `_validate_preflight_report()` with required fields `strategy_id`, `alias`, `indicator`, `expected_table`, `expected_column`, `date_range`, `reason`, `required`.
- Reason: The preflight audit already checked `missing_factor_requests` is a list, but still accepted malformed items. The missing-factor handoff payload has a stable object shape that should be checked at the audit boundary.
- Alternatives: skip item validation (rejected — audit would remain incomplete); validate every emitted field in `MissingFactorRequest.to_dict()` (rejected — brief explicitly scoped to core fields only).
- Impact: New issue codes `invalid_preflight_report_missing_factor_request` and `missing_preflight_report_missing_factor_field`; 14 new tests; 863 total passed. Combined with the prior status/checks shape audit, the full preflight report content contract is now structurally validated.
- Owner: CLAUDE_CODE

### 2026-05-24: Select preflight report shape audit as next Claude task

- Decision: The next Claude Code task is `QRE-RESEARCH-RUN-PREFLIGHT-REPORT-SHAPE-AUDIT-001`.
- Reason: Research-run preflight report auditing now checks root JSON shape, but it still accepts unsupported status values and malformed `checks[]` items. This is a narrow unblocked audit-hardening step that does not depend on external benchmark or security-status data.
- Alternatives: Move to blocked benchmark/security metadata tasks (rejected — source tables remain unconfirmed); validate every preflight field in one slice (rejected — too broad and would risk breaking historical/minimal payloads).
- Impact: `08/09/10/11/12/04/05/03/01` switched to preflight report shape audit implementation lane.
- Owner: CODEX

---

### 2026-05-24: Select research-run audit usage docs as next Claude task

- Decision: The next Claude Code task is `QRE-RESEARCH-RUN-AUDIT-USAGE-DOCS-001`.
- Reason: The research-run report-manifest audit contract is now implemented and regression-tested, but README/module docs still show only minimal top-level audit usage and do not fully document role-level audit commands or selector isolation.
- Alternatives: Move directly to blocked real benchmark/security metadata work (rejected — source data remains unconfirmed); add more runtime audit hardening before documenting (rejected — current root research-run audit contract is already coherent and tested).
- Impact: `08/09/10/11/12/04/05/03/01` switched to a documentation-only implementation lane for Claude Code.
- Owner: CODEX

---

### 2026-05-23: Full-market report charts with matplotlib Agg backend

- Decision: Generate equity curve and drawdown charts as standalone PNGs using matplotlib Agg backend and embed them in the Excel workbook via openpyxl `Image`.
- Reason: The full-market report had no visual chart outputs despite having equity and drawdown CSV data. matplotlib Agg works without a display server, and openpyxl image embedding keeps everything in one workbook.
- Alternatives: Use plotly or altair (rejected — unnecessary new dependency); generate only standalone files (rejected — embedded workbook is more user-friendly); use interactive matplotlib backends (rejected — Agg is correct for headless/CI environments).
- Impact: `generate_equity_curve_chart()` and `generate_drawdown_chart()` added to `full_market_report.py`; `write_full_market_excel()` signature extended with keyword-only chart parameters; both batch and shared_cash branches generate charts; `equity_curve_chart` and `drawdown_curve_chart` manifest roles registered; 10 new tests; 529 pass.
- Owner: CLAUDE_CODE (acting planner/implementer/reviewer — Codex unavailable)

---

### 2026-05-23: Shared-cash full-market report engine_mode pattern

- Decision: Add `engine_mode: str = "batch"` parameter to all 6 full-market report builders and the entry point, with shared-cash branches reading flat DataFrames instead of `dict[str, SingleSymbolBacktestResult]`.
- Reason: `BatchBacktestResult` and `SharedCashBacktestResult` have fundamentally different internal structures (per-symbol dict vs flat DataFrames with `symbol` columns). An `engine_mode` parameter preserves all batch paths unchanged while adding parallel shared-cash paths. This is cleaner than coercing shared-cash results into batch-shaped containers or duplicating the entire module.
- Alternatives: Duplicate `full_market_report.py` for shared-cash (rejected — too much code duplication); coerce `SharedCashBacktestResult` into a batch-shaped wrapper (rejected — adds indirection and risks subtle type mismatches); make shared-cash the only mode (rejected — breaks batch workflow).
- Impact: `build_trades_ledger`, `build_round_trips`, `build_symbol_performance`, `build_full_market_equity_curve`, `build_strategy_performance`, and `write_full_market_report` all accept `engine_mode`. Key `full_market_equity_curve` used to avoid collision with shared-cash's existing `equity_curve` entry. `_shared_manifest_role()` and `_shared_report_paths()` updated for 9 full-market artifact roles. 19 new tests; 519 pass.
- Owner: CLAUDE_CODE (acting planner/implementer — Codex unavailable)

---

### 2026-05-23: Research-run manifest integrated into report manifest system

- Decision: Integrate `research_run_manifest.json` into the report manifest system by adding standard run_manifest fields to the orchestrator output, registering `research_run_manifest` in `_RUN_MANIFEST_KINDS`, and adding content validation parity test coverage.
- Reason: The research-run orchestrator emitted a `research_run_manifest.json` but it was not discoverable through `qre report-files` or `qre report-audit` because the kind was not registered. This is the smallest possible fix that closes the gap without changing the manifest schema or audit tooling.
- Alternatives: Leave the manifest undiscoverable; add a separate discovery command just for research-run manifests. Rejected because the existing report-manifest system already handles run_manifest validation and discovery for portfolio and evaluation manifests.
- Impact: `_write_research_manifest()` now emits `schema_version`, `kind`, `command`, `strategy_path`, `artifacts`; `_RUN_MANIFEST_KINDS` includes `research_run_manifest`; 3 manifest tests updated, 1 new validation test added; 477 tests pass (up from 476).
- Owner: CLAUDE_CODE (acting planner/implementer/reviewer — Codex unavailable)

---

### 2026-05-23: Research-run CLI orchestrator implemented and self-reviewed

- Decision: Implement `QRE-RESEARCH-RUN-ORCHESTRATION-001` (`qre research-run` CLI command) and self-review PASS, closing the "Larger research-run bundles beyond run-level identifier linkage" known gap.
- Reason: The 22-flag smoke discovery status enrichment series is complete and the largest remaining known gap is research-run orchestration. This bundles preflight → eval-config → backtest under one command with a common `--run-id` and `research_run_manifest.json`, using the same direct-engine-call pattern as the GUI.
- Alternatives: Continue only with per-command `--run-id` linkage; add a broader DAG-based pipeline; wait for Codex planning.
- Impact: New `src/quant_research_engine/orchestration/research_run.py` module (~200 lines), `qre research-run` CLI command with 16 arguments, 10 new tests (7 unit + 3 CLI), 476 total pass. Stale roadmap entries (M7.x, M8.1, M8.3, M8.10) synced to DONE. Agent docs updated for git finalization.
- Owner: CLAUDE_CODE (acting planner/implementer/reviewer — Codex unavailable)

---

### 2026-05-23: Accept status-pass-count and complete smoke discovery status enrichment series

- Decision: Mark `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-PASS-COUNT-001` as PASS and complete the smoke discovery status enrichment series.
- Reason: Claude Code (acting reviewer, Codex unavailable) validated implementation end-to-end (114 smoke-files, 466 full suite). All 22 status enrichment flags are now complete: quiet, status-only, status-file, status-format, status-reason, status-code, status-meta, status-summary, status-fail-key, status-fail-stage, status-timestamp, status-output-dir, status-manifest-path, status-manifest-exists, status-artifact-count, status-strategy-count, status-fail-count, status-skip-count, status-pass-count, check-exists, list-missing, require-match, details, output-file, latest.
- Alternatives: Keep series open for additional status fields.
- Impact: `10/04/05/11/12/06` updated for review PASS and git finalization. Next major work direction TBD by user.
- Owner: CLAUDE_CODE (acting reviewer — Codex unavailable)

---

### 2026-05-22: Accept status-skip-count and select smoke-files status-pass-count as next Claude task

- Decision: Mark `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-SKIP-COUNT-001` as PASS and assign `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-PASS-COUNT-001` next.
- Reason: skip-count sanity check is complete; next status-only automation gap is direct passed-strategy count.
- Alternatives: infer pass count downstream from total/fail/skip fields.
- Impact: `08/09/11/12/04/05/03` switched to status-pass-count implementation lane.
- Owner: CODEX

---

### 2026-05-22: Accept status-fail-count and select smoke-files status-skip-count as next Claude task

- Decision: Mark `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-FAIL-COUNT-001` as PASS and assign `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-SKIP-COUNT-001` next.
- Reason: fail-count sanity check is complete; next status-only automation gap is direct skipped-strategy count.
- Alternatives: infer skipped counts downstream from detailed stage outputs.
- Impact: `08/09/11/12/04/05/03` switched to status-skip-count implementation lane.
- Owner: CODEX

---

### 2026-05-22: Accept status-strategy-count and select smoke-files status-fail-count as next Claude task

- Decision: Mark `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-STRATEGY-COUNT-001` as PASS and assign `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-FAIL-COUNT-001` next.
- Reason: strategy-count sanity check is complete; next status-only automation gap is direct failing-strategy count.
- Alternatives: infer failing-strategy count downstream from detailed strategy statuses.
- Impact: `08/09/11/12/04/05/03` switched to status-fail-count implementation lane.
- Owner: CODEX

---

### 2026-05-22: Accept status-artifact-count and select smoke-files status-strategy-count as next Claude task

- Decision: Mark `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-ARTIFACT-COUNT-001` as PASS and assign `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-STRATEGY-COUNT-001` next.
- Reason: artifact-count sanity check is complete; next status-only automation gap is direct strategy total count.
- Alternatives: infer strategy total downstream from full JSON output instead of compact status payload.
- Impact: `08/09/11/12/04/05/03` switched to status-strategy-count implementation lane.
- Owner: CODEX

---

### 2026-05-22: Accept status-manifest-exists and select smoke-files status-artifact-count as next Claude task

- Decision: Mark `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-MANIFEST-EXISTS-001` as PASS and assign `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-ARTIFACT-COUNT-001` next.
- Reason: manifest existence branching is complete; next CI sanity-check gap is direct artifact total count in status-only outputs.
- Alternatives: keep separate status fields only and recompute artifact totals downstream.
- Impact: `08/09/11/12/04/05/03` switched to status-artifact-count implementation lane.
- Owner: CODEX

---

### 2026-05-22: Accept status-manifest-path and select smoke-files status-manifest-exists as next Claude task

- Decision: Mark `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-MANIFEST-PATH-001` as PASS and assign `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-MANIFEST-EXISTS-001` next.
- Reason: manifest-path traceability is complete; next automation gap is a direct manifest existence boolean for CI branch logic.
- Alternatives: keep manifest-path only and force downstream existence checks.
- Impact: `08/09/11/12/04/05/03` switched to status-manifest-exists implementation lane.
- Owner: CODEX

---

### 2026-05-22: Accept status-output-dir and select smoke-files status-manifest-path as next Claude task

- Decision: Mark `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-OUTPUT-DIR-001` as PASS and assign `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-MANIFEST-PATH-001` next.
- Reason: output-dir traceability is complete; next CI/audit gap is direct manifest-file path visibility in status-only outputs.
- Alternatives: keep output-dir only and require manifest path reconstruction downstream.
- Impact: `08/09/11/12/04/05/03` switched to status-manifest-path implementation lane.
- Owner: CODEX

---

### 2026-05-22: Accept status-timestamp and select smoke-files status-output-dir as next Claude task

- Decision: Mark `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-TIMESTAMP-001` as PASS and assign `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-OUTPUT-DIR-001` next.
- Reason: timestamp traceability is complete; next CI audit gap is direct resolved output-dir visibility in status-only outputs.
- Alternatives: keep status outputs time-aware only and require separate path discovery commands.
- Impact: `08/09/11/12/04/05/03` switched to status-output-dir implementation lane.
- Owner: CODEX

---

### 2026-05-22: Accept status-fail-stage and select smoke-files status-timestamp as next Claude task

- Decision: Mark `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-FAIL-STAGE-001` as PASS and assign `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-TIMESTAMP-001` next.
- Reason: fail-stage localization is complete; the next CI traceability gap is stable run timestamp in status-only outputs.
- Alternatives: stop at fail diagnostics only and rely on external logs for timing.
- Impact: `08/09/11/12/04/05/03` switched to status-timestamp implementation lane.
- Owner: CODEX

---

### 2026-05-22: Accept status-fail-key and select smoke-files status-fail-stage as next Claude task

- Decision: Mark `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-FAIL-KEY-001` as PASS and assign `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-FAIL-STAGE-001` next.
- Reason: fail-key localization is complete; the next CI diagnosis gap is immediate failing stage visibility.
- Alternatives: stop at failing strategy-id only, without stage-level key.
- Impact: `08/09/11/12/04/05/03` switched to status-fail-stage implementation lane.
- Owner: CODEX

---

### 2026-05-22: Accept status-summary and select smoke-files status-fail-key as next Claude task

- Decision: Mark `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-SUMMARY-001` as PASS and assign `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-FAIL-KEY-001` next.
- Reason: status summary counts are complete; next CI parsing gap is immediate failing strategy-id localization.
- Alternatives: stop at counts-only payload or jump to unrelated larger feature slices.
- Impact: `08/09/11/12/04/05/03` switched to status-fail-key implementation lane.
- Owner: CODEX

---

### 2026-05-22: Accept status-meta and select smoke-files status-summary as next Claude task

- Decision: Mark `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-META-001` as PASS and assign `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-SUMMARY-001` next.
- Reason: metadata enrichment is complete; the next CI automation gap is compact strategy counts in status-only outputs.
- Alternatives: stop at metadata-only status payload; jump to unrelated larger feature slices.
- Impact: `08/09/11/12/04/05/03` switched to status-summary implementation lane.
- Owner: CODEX

---


### 2026-05-22: Select smoke-files status-meta mode as next Claude task

- Decision: The next Claude Code task is `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-META-001` (`qre smoke-files --status-meta`).
- Reason: status-code mode is complete; next automation gap is compact metadata fields in status-only outputs for downstream parsers.
- Alternatives: move to larger orchestration features before finalizing smoke-files status ergonomics.
- Impact: `08/09/11/12/04/05` switched to status-meta task; scope remains CLI + tests + docs.
- Owner: CODEX

---

### 2026-05-22: Select smoke-files status-code mode as next Claude task

- Decision: The next Claude Code task is `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-CODE-001` (`qre smoke-files --status-code`).
- Reason: status-reason mode is complete; next automation gap is stable numeric status payloads for CI gates.
- Alternatives: move to larger orchestration features before finalizing smoke-files status ergonomics.
- Impact: `08/09/11/12/04/05` switched to status-code task; scope remains CLI + tests + docs.
- Owner: CODEX

---

### 2026-05-22: Select smoke-files status-reason mode as next Claude task

- Decision: The next Claude Code task is `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-REASON-001` (`qre smoke-files --status-reason`).
- Reason: status-format mode is complete; next automation gap is optional compact failure reason in status-only payloads.
- Alternatives: move to larger orchestration features before finalizing smoke-files status payload ergonomics.
- Impact: `08/09/11/12/04/05` switched to status-reason task; scope remains CLI + tests + docs.
- Owner: CODEX

---

### 2026-05-22: Select smoke-files status-format mode as next Claude task

- Decision: The next Claude Code task is `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-FORMAT-001` (`qre smoke-files --status-format`).
- Reason: status-file mode is complete; next automation gap is explicit status payload format selection for status-only workflows.
- Alternatives: move to larger orchestration features before finishing smoke-files status contract ergonomics.
- Impact: `08/09/11/12/04/05` switched to status-format task; scope remains CLI + tests + docs.
- Owner: CODEX

---

### 2026-05-22: Select smoke-files status-file mode as next Claude task

- Decision: The next Claude Code task is `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-FILE-001` (`qre smoke-files --status-file`).
- Reason: status-only mode is complete; next automation gap is persisted status payload for CI and workflow handoff.
- Alternatives: move to larger orchestration features before finishing smoke-files output contract ergonomics.
- Impact: `08/09/11/12/04/05` switched to status-file task; scope remains CLI + tests + docs.
- Owner: CODEX

---

### 2026-05-22: Select smoke-files status-only mode as next Claude task

- Decision: The next Claude Code task is `QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-ONLY-001` (`qre smoke-files --status-only`).
- Reason: Quiet mode is complete; next automation gap is compact status-only payloads for lightweight orchestration.
- Alternatives: move to larger orchestration features before finishing smoke-files output contract ergonomics.
- Impact: `08/09/11/12/04/05` switched to status-only task; scope remains CLI + tests + docs.
- Owner: CODEX

---

### 2026-05-22: Select smoke-files quiet mode as next Claude task

- Decision: The next Claude Code task is `QRE-STRATEGY-SMOKE-DISCOVERY-QUIET-001` (`qre smoke-files --quiet`).
- Reason: list-missing is complete; next automation gap is a no-stdout mode that keeps exit-code contracts.
- Alternatives: move to larger orchestration features before tightening CLI automation ergonomics.
- Impact: `08/09/11/12/04/05` switched to quiet-mode task; scope remains CLI + tests + docs.
- Owner: CODEX

---

### 2026-05-22: Select smoke-files require-match strict mode as next Claude task

- Decision: The next Claude Code task is `QRE-STRATEGY-SMOKE-DISCOVERY-REQUIRE-MATCH-001` (`qre smoke-files --require-match`).
- Reason: Check-exists is complete; next workflow gap is strict failure signaling for selector no-match cases.
- Alternatives: Move to larger orchestration features before tightening smoke-files selector semantics.
- Impact: `08/09/11/12/04/05` switched to the new strict-filter task; scope remains CLI + tests + docs.
- Owner: CODEX

---

### 2026-05-22: Select smoke-files artifact existence audit as next Claude task

- Decision: The next Claude Code task is `QRE-STRATEGY-SMOKE-DISCOVERY-CHECK-EXISTS-001` (`qre smoke-files --check-exists`).
- Reason: Output export is complete; next practical gap is fast artifact existence validation directly on smoke discovery output.
- Alternatives: Move immediately to broader run orchestration or unrelated strategy features.
- Impact: `08/09/11/12/04/05` switched to the new task. Scope remains CLI + tests + docs with no strategy semantics changes.
- Owner: CODEX

---

### 2026-05-22: Re-queue smoke-files output export task

- Decision: Keep `QRE-STRATEGY-SMOKE-DISCOVERY-OUTPUT-EXPORT-001` active and re-assign to Claude Code.
- Reason: Codex review confirmed active requirement (`--output-file`) is not in CLI yet; previous handoff accidentally reflected older details task.
- Alternatives: Start a new downstream task before fixing export gap.
- Impact: `08/09/10/11/12` were synchronized to one active task; Claude must complete output export before new feature slices.
- Owner: CODEX

---

### Initial: Use dual-agent workflow

- Decision: This project uses Codex as Planner/Reviewer/Git Finalizer and Claude Code as Implementer.
- Reason: This separates planning, implementation, review, and final git operations.
- Alternatives: Single-agent coding; manual-only workflow.
- Impact: All tasks should pass through `08_IMPLEMENTATION_BRIEF.md`, `09_CODING_HANDOFF.md`, `10_REVIEW_REPORT.md`, and `11_AGENT_STATE.md`.
- Owner: USER

### 2026-05-17: Scope project memory to quant-research-engine

- Decision: The authoritative `docs/agent` system describes only the current `quant-research-engine` directory and not the larger `quant-workspace` program.
- Reason: The user explicitly corrected the focus to this independent backtesting-engine experiment.
- Alternatives: Preserve broader workspace status in QRE docs.
- Impact: Upstream projects such as `quant_ts` and `indicators_tushare` are referenced only as data producers.
- Owner: USER/CODEX

### 2026-05-17: Treat QRE as read-only consumer of upstream data

- Decision: QRE should read market, factor, metadata, benchmark, and reference data. It should not write upstream database state during standard evaluation/backtest flows.
- Reason: Existing docs and code position QRE above `quant_ts` and `indicators_tushare`; indicators are produced upstream.
- Alternatives: Let QRE repair or recompute data.
- Impact: Future QRE tasks should avoid database writes unless explicitly authorized in a brief.
- Owner: CODEX

### 2026-05-17: Do not compute indicators inside QRE

- Decision: Evaluation and portfolio engines must consume declared factor columns from `factors.*` tables instead of recomputing technical indicators.
- Reason: Old docs repeatedly state that `indicators_tushare` owns technical factor generation.
- Alternatives: Add engine-local indicator implementations.
- Impact: New strategies must declare factor inputs; data layer loads them from configured tables.
- Owner: CODEX

### 2026-05-17: Select failed-order diagnostics as next Claude task

- Decision: The next recommended Claude Code task is richer shared-cash failed-order diagnostics, not real index benchmark wiring.
- Reason: Benchmark/index wiring depends on confirming real index table availability and schema. Failed-order diagnostics is self-contained and directly improves portfolio realism.
- Alternatives: Start real index wiring immediately; start evaluation grouping/regime work.
- Impact: `08_IMPLEMENTATION_BRIEF.md` is prepared for failed-order diagnostics. Real index wiring is marked blocked pending data-source confirmation.
- Owner: CODEX, pending USER approval

### 2026-05-19: Select portfolio run-manifest reproducibility as next Claude task

- Decision: The next Claude Code task is a portfolio backtest run manifest for reproducible research runs.
- Reason: Run-level reproducibility is self-contained, does not require new data-source confirmation, and builds directly on the completed report-manifest and audit work.
- Alternatives: Start real index benchmark wiring immediately; start evaluation grouping/regime work.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes a run-manifest workflow for single, batch, and shared backtests. `M5.5` is marked ready for Claude Code.
- Owner: CODEX

### 2026-05-19: Select evaluation metadata group summaries as next Claude task

- Decision: The next Claude Code task is grouped evaluation summaries over existing research-frame metadata columns.
- Reason: This advances roadmap M3.5 without requiring new upstream data-source confirmation, benchmark wiring, or database schema changes.
- Alternatives: Start real index benchmark wiring immediately; start real suspension/ST/risk-warning metadata.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `EvaluationRequest.group_by`, `EvaluationResult.group_summary`, and `qre eval-config --group-by ...`.
- Owner: CODEX

### 2026-05-19: Select eval-config output artifacts as next Claude task

- Decision: The next Claude Code task is durable output artifacts and manifests for `qre eval-config`.
- Reason: Evaluation grouping is complete, but evaluation runs still only print to stdout. Output artifacts are a self-contained reproducibility step and reuse existing report-manifest patterns.
- Alternatives: Start real index benchmark wiring; start real suspension/ST/risk-warning metadata.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `eval-config --output-dir`, `evaluation_report_manifest`, and `evaluation_run_manifest`.
- Owner: CODEX

### 2026-05-19: Select evaluation random-baseline comparison as next Claude task

- Decision: The next Claude Code task is deterministic random-baseline comparison for evaluation output quality.
- Reason: It advances evaluation realism without waiting on a confirmed benchmark table/schema, and it can be scoped without upstream data-source changes.
- Alternatives: Start real index benchmark wiring immediately; start real suspension/ST/risk-warning metadata.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-EVAL-RANDOM-BASELINE-COMPARISON-001` and keeps real index benchmark wiring marked blocked.
- Owner: CODEX, pending USER approval

### 2026-05-20: Select real metadata adapters as next Claude task

- Decision: The next Claude Code task is real status/industry/membership metadata adapters for security metadata loading.
- Reason: This advances data realism without needing benchmark table confirmation and uses the existing read-only metadata merge path.
- Alternatives: Jump straight to real index benchmark wiring; start regime grouping before the metadata source is clarified.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-DATA-REAL-METADATA-ADAPTERS-001`. Real index benchmark wiring remains blocked until table/schema confirmation.
- Owner: CODEX

### 2026-05-20: Select batch metadata group-by passthrough as next Claude task

- Decision: The next Claude Code task is to let `backtest-batch --group-by` use optional metadata columns that already flow through the data layer.
- Reason: The previous task preserves upstream metadata columns, but `BatchBacktestEngine` still copies only a fixed metadata whitelist into its summary, so portfolio grouped reports cannot use new columns such as liquidity buckets or membership flags.
- Alternatives: Wire real index benchmark data first; standardize time-varying status tables first.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-PORTFOLIO-BATCH-METADATA-GROUPBY-001`. Real index benchmark wiring and time-varying status tables remain blocked by source confirmation.
- Owner: CODEX

### 2026-05-20: Select shared-cash metadata output passthrough as next Claude task

- Decision: The next Claude Code task is request-driven metadata passthrough for shared-cash order, trade, and failed-order output rows.
- Reason: Batch reports can now group by optional metadata columns, but shared-cash outputs still do not carry requested metadata into row-level artifacts. This is a small prerequisite for later shared-cash attribution without inventing per-symbol shared-cash report semantics.
- Alternatives: Add shared-cash group-by reports immediately; wire real index benchmark data first; implement time-varying suspension/ST/risk-warning metadata first.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-SHARED-CASH-METADATA-OUTPUTS-001`. Shared-cash group attribution remains future work, while real benchmark and time-varying status tasks remain blocked by source confirmation.
- Owner: CODEX

### 2026-05-20: Select shared-cash metadata group summaries as next Claude task

- Decision: The next Claude Code task is grouped shared-cash order, trade, and failed-order summaries over requested metadata columns.
- Reason: Shared-cash row outputs now carry requested metadata safely, so grouped diagnostics can be built without new data-source assumptions or portfolio-math changes.
- Alternatives: Start real index benchmark wiring; implement time-varying suspension/ST/risk-warning metadata; attempt shared-cash return attribution by metadata group.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-SHARED-CASH-METADATA-GROUP-SUMMARY-001`. Return attribution and exposure-level group performance remain future work.
- Owner: CODEX

### 2026-05-20: Select evaluation factor decay summary as next Claude task

- Decision: The next Claude Code task is factor decay summaries for evaluation outputs.
- Reason: Factor decay is a documented evaluation gap, can be computed from existing IC/Rank IC by horizon, and does not require benchmark tables or new data sources.
- Alternatives: Start real index benchmark wiring; implement real regime classification; start time-varying suspension/ST metadata.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-EVAL-FACTOR-DECAY-SUMMARY-001`. Benchmark and real regime work remain blocked by source confirmation.
- Owner: CODEX

### 2026-05-20: Select run-ID manifest linkage as next Claude task

- Decision: The next Claude Code task is optional `--run-id` metadata for preflight, evaluation, and portfolio durable outputs.
- Reason: This advances multi-stage research-run reproducibility without adding a new orchestrator, data source, or database write path.
- Alternatives: Start real index benchmark wiring; build a full research-run pipeline command; implement real regime classification.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-RUN-ID-MANIFEST-LINKAGE-001`. Larger orchestration remains future work, while benchmark and real regime work remain blocked by source confirmation.
- Owner: CODEX

### 2026-05-20: Select run-manifest content validation as next Claude task

- Decision: The next Claude Code task is stricter `run_manifest` JSON validation through existing report audit tooling.
- Reason: Durable outputs now expose run-level IDs, but `run_manifest` content validation still only checks that the file is a JSON object. A focused validation step improves reproducibility checks without new data dependencies.
- Alternatives: Build a full research-run orchestrator; start real benchmark wiring; implement real regime classification.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-RUN-MANIFEST-CONTENT-VALIDATION-001`. Report manifest file-entry schema should remain unchanged.
- Owner: CODEX

### 2026-05-20: Select run-manifest audit usage docs as next Claude task

- Decision: The next Claude Code task is user-facing documentation for optional `--run-id` linkage and run-manifest audit usage.
- Reason: The CLI and audit validation now support run IDs and stricter run-manifest checks, but README/module docs do not yet explain the current workflow.
- Alternatives: Start another validation feature; build a full research-run orchestrator; start real benchmark wiring.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-DOCS-RUN-MANIFEST-AUDIT-USAGE-001`. This is documentation-only and should avoid legacy archived docs.
- Owner: CODEX

### 2026-05-20: Select evaluation artifact usage docs as next Claude task

- Decision: The next Claude Code task is user-facing documentation for evaluation artifacts and diagnostics.
- Reason: Evaluation artifacts, metadata grouping, random baselines, and factor decay are implemented, but README/module docs do not yet clearly explain the current artifact set and report roles.
- Alternatives: Start another reporting validation feature; start real benchmark wiring; build a broader research-run orchestrator.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-DOCS-EVAL-ARTIFACTS-USAGE-001`. This is documentation-only and should avoid legacy archived docs.
- Owner: CODEX

### 2026-05-20: Select metadata grouping usage docs as next Claude task

- Decision: The next Claude Code task is user-facing documentation for metadata grouping and passthrough usage across evaluation, batch backtest, and shared-cash outputs.
- Reason: Metadata-aware grouping features are implemented, but current docs do not yet show how `--group-by`, `--metadata-columns`, and report-manifest role filters fit together across the CLI surfaces.
- Alternatives: Start real benchmark wiring; start time-varying suspension/ST metadata; build a larger research-run orchestrator.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-DOCS-METADATA-GROUPING-USAGE-001`. This is documentation-only and should avoid legacy archived docs.
- Owner: CODEX

### 2026-05-20: Select evaluation group-by manifest parity as next Claude task

- Decision: The next Claude Code task is evaluation grouped-artifact manifest parity for per-column discovery and `--group-by` filtering.
- Reason: Evaluation outputs currently write a combined `group_summary.csv`, but batch and shared outputs already expose per-group-column manifest metadata that works cleanly with `report-files` and `report-audit --group-by`. Aligning evaluation artifact emission closes that workflow gap without needing new external data sources.
- Alternatives: Start real benchmark wiring; start time-varying suspension/ST metadata; build a larger research-run orchestrator.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-EVAL-GROUP-BY-MANIFEST-PARITY-001`. Existing `group_summary.csv` compatibility should be preserved while adding per-column grouped artifact entries.
- Owner: CODEX

### 2026-05-20: Select evaluation group-by parity docs as next Claude task

- Decision: The next Claude Code task is user-facing documentation for evaluation per-column grouped artifacts and `--group-by` discovery/audit parity.
- Reason: The code now emits `group_summary_by_<col>.csv` files and supports evaluation `report-files` / `report-audit --group-by`, but current docs still describe only the combined evaluation grouped artifact.
- Alternatives: Start real benchmark wiring; start time-varying suspension/ST metadata; jump to a larger research-run orchestration feature.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-DOCS-EVAL-GROUP-BY-MANIFEST-PARITY-USAGE-001`. This is documentation-only and should avoid legacy archived docs.
- Owner: CODEX

### 2026-05-21: Select grouped-artifact group_by audit consistency as next Claude task

- Decision: The next Claude Code task is audit hardening for manifest `group_by` metadata versus grouped CSV contents.
- Reason: Evaluation and shared grouped artifacts now support per-column manifest filtering, but `ReportManifest.validate_contents()` still checks only required columns. A file can claim manifest `group_by=board` while containing mismatched grouped rows and still pass audit.
- Alternatives: Start real benchmark wiring; start time-varying suspension/ST metadata; jump to larger run-bundle orchestration.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-REPORT-GROUP-BY-CONTENT-CONSISTENCY-001`. The task should stay inside report-manifest validation and targeted CLI/tests without changing manifest schema version.
- Owner: CODEX

### 2026-05-21: Select batch grouped-artifact group_by header consistency as next Claude task

- Decision: The next Claude Code task is audit hardening for batch grouped-artifact manifest `group_by` metadata versus batch CSV header columns.
- Reason: Batch grouped artifacts still pass audit when manifest `group_by=board` points at a CSV whose header uses another column such as `sector`, because current validation checks only required summary/ranking columns. This is now the remaining obvious manifest/content consistency gap on the reporting path.
- Alternatives: Start real benchmark wiring; start time-varying suspension/ST metadata; jump to a larger run-bundle orchestration feature.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-REPORT-BATCH-GROUP-BY-HEADER-CONSISTENCY-001`. The task should stay inside report-manifest validation and targeted CLI/tests without changing manifest schema version.
- Owner: CODEX

### 2026-05-21: Select rolling window_size filter parity as next Claude task

- Decision: The next Claude Code task is report-manifest and CLI parity for rolling-artifact `window_size` metadata.
- Reason: Batch and shared manifest writers already emit `window_size` on rolling entries, but `ReportFile`, `ReportManifest`, `qre report-files`, and `qre report-audit` still cannot filter or surface that metadata. The gap is self-contained and stays on the reporting/reproducibility path.
- Alternatives: Start real benchmark wiring; start time-varying suspension/ST metadata; jump to a larger run-bundle orchestration feature.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-REPORT-ROLLING-WINDOW-SIZE-FILTER-PARITY-001`. The task should stay inside report-manifest parsing/filtering, CLI plumbing, and targeted tests without changing manifest schema version or output-generation logic.
- Owner: CODEX

### 2026-05-21: Select rolling window_size usage docs as next Claude task

- Decision: The next Claude Code task is user-facing documentation for rolling-artifact `window_size` report filtering.
- Reason: The CLI and manifest helpers now support `--window-size` and additive `window_size` JSON metadata, but README and portfolio docs still describe report-file optional metadata as only `symbol`, `window`, and `group_by`, and they do not explain when to use `--window-size` instead of `--window`.
- Alternatives: Start real benchmark wiring; start time-varying suspension/ST metadata; jump to a larger run-bundle orchestration feature.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-DOCS-ROLLING-WINDOW-SIZE-FILTER-USAGE-001`. This is documentation-only and should avoid legacy archived docs.
- Owner: CODEX

### 2026-05-21: Select CLI regression coverage for invalid window_size metadata as next Claude task

- Decision: The next Claude Code task is CLI regression coverage for malformed manifest file entries that use invalid `window_size` types.
- Reason: `ReportManifest.from_path()` already rejects string and boolean `window_size` values, but the `report-files` / `report-audit` command boundary is not yet covered in `tests/test_cli.py`. This is the remaining narrow regression gap after the feature and docs landed.
- Alternatives: Start real benchmark wiring; start time-varying suspension/ST metadata; jump to a larger run-bundle orchestration feature.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-CLI-WINDOW-SIZE-METADATA-TYPE-REGRESSION-001`. The task should stay test-focused and avoid runtime changes unless the current CLI error surface is inconsistent.
- Owner: CODEX

### 2026-05-21: Select CLI strict/JSON parity for window_size filters as next Claude task

- Decision: The next Claude Code task is focused CLI regression coverage for `--window-size` when combined with `--require-match` and `--json`.
- Reason: Basic `--window-size` filter coverage and malformed-metadata boundary coverage already exist, and generic strict/json selector coverage exists for other filters, but the `window_size` selector itself still lacks locked no-match and JSON-path parity at both `report-files` and `report-audit` boundaries.
- Alternatives: Start real benchmark wiring; start time-varying suspension/ST metadata; widen the task into runtime CLI refactoring.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-CLI-WINDOW-SIZE-STRICT-JSON-PARITY-001`. The task should stay test-focused and avoid runtime changes unless a narrow command-surface bug is exposed.
- Owner: CODEX

### 2026-05-21: Select CLI strict/JSON parity for window_size plus group_by as next Claude task

- Decision: The next Claude Code task is focused CLI regression coverage for `--window-size` when combined with `--group-by`, `--json`, and `--require-match`.
- Reason: Independent `--window-size` and `--group-by` selector coverage already exists, but their intersection is still untested. Locking the combined selector behavior extends the reporting parity without touching runtime code.
- Alternatives: Start real benchmark wiring; start time-varying suspension/ST metadata; widen the task into parser or manifest refactoring.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-CLI-WINDOW-SIZE-GROUP-BY-PARITY-001`. The task should stay test-focused and avoid runtime changes unless a concrete selector bug appears.
- Owner: CODEX

### 2026-05-21: Choose a local browser console as the first GUI form

- Decision: The first GUI release will be a local browser-based console launched by `qre gui`.
- Reason: The existing engine already runs in Python, and a local web console is the simplest cross-platform way to expose strategy editing, run controls, and artifact inspection without building a desktop app.
- Alternatives: Native desktop packaging; a remote web app; keep the workflow CLI-only.
- Impact: The GUI task should use server-rendered pages or similarly lightweight browser UI, and it should stay focused on the existing engine contract rather than adding heavy front-end machinery.
- Owner: USER/CODEX

### 2026-05-21: Make YAML text the first-class strategy editing surface

- Decision: The GUI will treat strategy YAML as the primary input, with inline text editing and file upload/save support.
- Reason: The engine already accepts YAML strategy specs. A form-only builder would duplicate the strategy contract and slow the first release.
- Alternatives: Drag-and-drop strategy composition; form-generated strategies; code editor as the only input.
- Impact: Claude Code should implement validation and save/reopen flows around YAML text, not a separate visual strategy language.
- Owner: USER/CODEX

### 2026-05-21: Keep run history local on disk for v1

- Decision: Version 1 of the GUI will store run history in the local filesystem, not PostgreSQL.
- Reason: The engine already writes durable output directories and report manifests. Keeping history local first reduces implementation risk and keeps the first release cross-platform.
- Alternatives: Write history directly to PostgreSQL; add distributed job storage; keep history ephemeral only.
- Impact: The GUI should persist run requests, strategy snapshots, status, logs, and artifact pointers under the repository outputs directory, with PostgreSQL migration deferred.
- Owner: USER/CODEX

### 2026-05-27: Select QRE-NEXT-55 tracker reconciliation as next Claude task

- Decision: The next Claude Code task is to reconcile the stale `QRE-NEXT-55` progress entry for real suspension/ST/risk-warning metadata.
- Reason: Roadmap item M4.9 is already marked DONE, but the progress tracker still shows the corresponding row as IMPLEMENTED. Closeout should remove the stale mismatch without re-opening runtime scope.
- Alternatives: Leave the stale row in place (rejected - inconsistent tracker); reopen runtime work on status metadata (rejected - already accepted and no further feature expansion is planned).
- Impact: `08_IMPLEMENTATION_BRIEF.md` now scopes documentation-only reconciliation for `QRE-NEXT-55`. Claude should update tracker and handoff docs only.
- Owner: CODEX

### 2026-05-21: Prefer direct module execution with CLI fallback in the GUI

- Decision: The GUI will call the existing Python backtest modules directly by default and keep the `qre` CLI as a fallback execution path.
- Reason: Direct module execution is faster and easier to inspect during local development, while the CLI fallback preserves a stable escape hatch if the module boundary needs debugging.
- Alternatives: CLI-only orchestration; subprocess-only execution; build a separate job queue first.
- Impact: Claude Code should wire the GUI around the existing engine APIs, but keep a CLI fallback option in the run controls and error handling.
- Owner: USER/CODEX

### 2026-05-21: Select real suspension/ST/risk-warning metadata as next Claude task

- Decision: The next Claude Code task is real suspension/ST/risk-warning metadata for the security metadata loader.
- Reason: `load_security_metadata()` still falls back to static `False` flags when no confirmed upstream table is available. Preflight and portfolio realism already consume these flags, so this is the next data-layer realism gap after the CLI reporting work.
- Alternatives: Jump to benchmark/index wiring; expand into broader regime grouping; invent a schema without confirming the source table.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-DATA-REAL-SUSPENSION-ST-RISK-WARNING-METADATA-001`. Claude should confirm the upstream table/schema first and write a blocker if no confirmed table exists.
- Owner: CODEX

### 2026-05-21: Use Tushare suspend_d as the first available security-status smoke source

- Decision: The first concrete security-status smoke path should use Tushare `suspend_d`, while `stock_st` and `stk_alert` remain future tasks gated by account permissions.
- Reason: The configured Tushare credential can fetch `stock_basic` and `suspend_d`, but not `stock_st` or `stk_alert`. That lets us validate the downloader shape now without pretending the full metadata set is available.
- Alternatives: Wait for higher permissions on `stock_st`/`stk_alert`; postpone all smoke work until the full upstream table exists.
- Impact: A small read-only smoke utility can be used to validate `suspend_d` samples now. ST and risk-warning remain explicit TODO items, not implicit fallbacks.
- Owner: CODEX

### 2026-05-21: Add a Tushare security-status smoke harness

- Decision: Add a local read-only smoke utility for `stock_basic`, `suspend_d`, `stock_st`, and `stk_alert` so the team can probe source availability before bulk ingestion work.
- Reason: The available Tushare credential can validate `stock_basic` and `suspend_d`, while `stock_st` and `stk_alert` remain permission-blocked. That makes a manual smoke harness the right near-term step.
- Alternatives: Wait for full permissions; start a bulk ingester without source verification; keep the blocker as prose only.
- Impact: `scripts/tushare_security_smoke.py` now exists as a repeatable source-shape probe. It should stay read-only and avoid mutating PostgreSQL.
- Owner: CODEX

### 2026-05-21: Real suspension/ST/risk-warning metadata blocked — no source table

- Decision: Claude Code confirmed no security-status metadata table exists in the local `tushare_data` database. The data layer adapter code is already complete, so this is purely a data-availability blocker.
- Reason: Investigation found only `stock_daily` (market data without status flags) and `stock_holder_number` in the public schema. No `QRE_SECURITY_METADATA_TABLE` env var is configured. The existing adapter code (`_load_security_metadata_table`, `_normalize_security_metadata`) already handles all needed columns and passthrough fields.
- Alternatives: Invent a synthetic status table (rejected — violates "do not invent schemas" constraint); implement time-varying status from `stock_daily` patterns (rejected — no status data exists in that table); mark as blocked and wait for upstream.
- Impact: Task `QRE-DATA-REAL-SUSPENSION-ST-RISK-WARNING-METADATA-001` and roadmap item `M4.9` are blocked. To unblock, provide a table name via `QRE_SECURITY_METADATA_TABLE` with columns: `ts_code` (required), plus any of `list_date`, `board`, `is_st`, `is_risk_warning`, `is_suspended`.
- Owner: CLAUDE_CODE (investigation), CODEX (review and next steps)

### 2026-05-21: Canonical Tushare security snapshot contract completed

- Decision: Accept the reusable Tushare security snapshot contract implementation in `src/quant_research_engine/data/tushare_security.py` and finalize it locally.
- Reason: The source scaffold now provides a canonical snapshot shape, deterministic board inference, passthrough preservation, and read-only probe behavior that aligns with the existing PostgreSQL metadata normalization contract. Validation passed, and no locked requirements were violated.
- Alternatives: Request more changes to the contract helper; merge the snapshot contract into the blocked real-metadata task; leave the work in review despite green validation.
- Impact: `QRE-DATA-TUSHARE-SECURITY-SNAPSHOT-CONTRACT-001` is complete. The next active state returns to the still-blocked real metadata task `QRE-DATA-REAL-SUSPENSION-ST-RISK-WARNING-METADATA-001`.
- Owner: CODEX

### 2026-05-21: Extract a reusable Tushare security source adapter

- Decision: Move Tushare security probing into `src/quant_research_engine/data/tushare_security.py` and keep the smoke script as a thin wrapper.
- Reason: The same read-only Tushare probes will be reused for future bulk ingestion, source-shape checks, and endpoint-specific debugging. Centralizing the calls avoids duplicating endpoint names, fields, and formatting logic across scripts or future loaders.
- Alternatives: Leave the logic only in `scripts/tushare_security_smoke.py`; wire the code directly into the blocked data-layer task; introduce a broader ingestion framework before the source boundary is settled.
- Impact: The smoke path stays read-only, but the source boundary is now reusable for later bulk loading. The blocker on real security-status metadata remains unchanged.
- Owner: CODEX

### 2026-05-21: Keep the Tushare smoke harness as a thin CLI shell

- Decision: The smoke harness should only parse arguments, read the configured Tushare credential from the environment, and print results. It should not own endpoint definitions or frame formatting.
- Reason: The CLI shell is easier to keep stable if all Tushare-specific behavior lives in one importable data module. That also makes the smoke path easier to test without network access.
- Alternatives: Keep endpoint logic inside the script; add a separate command layer before the source adapter exists.
- Impact: `scripts/tushare_security_smoke.py` now delegates to the shared source adapter and remains safe to run in read-only environments.
- Owner: CODEX

### 2026-05-21: Allow strategy-level exit expressions for daily-bar backtests

- Decision: Strategy YAML may now carry `signal.exit`, and the portfolio engines interpret it as a next-bar exit trigger so strategies can model explicit sell rules without lookahead.
- Reason: The EMA200 + Bollinger strategy needs a true upper-band exit rule in addition to risk controls. The existing engines already supported entry expressions and stop controls, but not a strategy-scoped exit signal.
- Alternatives: Encode upper-band exits as a fixed-holding workaround; add an ad hoc CLI-only override; leave exits to stop controls alone.
- Impact: `StrategySpec`, single-symbol backtests, batch backtests, and shared-cash backtests all accept the exit expression; the user-requested EMA200 + Bollinger backtest now runs end-to-end on the existing data model.
- Validation: `uv run pytest tests/test_strategy_spec.py tests/test_portfolio_single_symbol.py tests/test_portfolio_shared.py -q` → 46 passed in 1.01s; chunked full-market backtest over `2010-01-04` to `2026-05-20` completed across 5,522 symbols.
- Owner: CODEX

## Open / To Confirm

All previously open items have been resolved:

- **Real index table for benchmark wiring** → Resolved by M4.8 (2026-05-25). Benchmark engine routes through `reference.index_daily` with `con_code` schema. CLI accepts `--benchmark-table`/`--benchmark-code`/`--benchmark-value-column` with paired-arg validation.
- **Suspension/ST/risk-warning source table** → Resolved by M4.9 (2026-05-27). `load_security_metadata()` composes from `reference.stock_basic`, `reference.stock_suspend`, `reference.stock_st`, `reference.stock_risk_warning`.
- **Legacy docs archiving** → Resolved by DOC-3 (2026-05-17). Legacy planning docs archived with notes; `docs/agent/` is the authoritative source.
- **Multi-stage research-run bundles** → Resolved by M8.42 (2026-05-23). `qre research-run` chains preflight→eval→backtest under one `--run-id` with `research_run_manifest.json`.

No open questions remain.

### 2026-05-21: Define QRE as the strategy IO contract and reporting engine

- Decision: QRE should standardize strategy entry, factor availability validation, backtest execution, and full-market report outputs. It should not rewrite external strategy repositories or compute indicators internally.
- Reason: The long-term workflow spans multiple projects. `research-notes` / `strategy-research` own strategy knowledge, `indicators_tushare` owns technical indicator calculation and period expansion, and QRE owns the executable contract between strategy ideas, factor availability, backtests, and reports.
- Alternatives: Put all classic strategy definitions directly into QRE; make the GUI own strategy semantics; let users continue hand-writing low-level `factors.table.column` YAML. These were rejected because they would make strategy expansion slower and keep the current YAML/debug bottleneck.
- Impact: `docs/superpowers/specs/2026-05-21-strategy-io-contract-design.md` defines the first strategy IO contract. Entry strategy work is documentation-first, and future implementation should compile that standard into current QRE backtest tasks.
- Owner: USER/CODEX

### 2026-05-21: Use MT5 plus TradingView as the full-market QRE report baseline

- Decision: QRE report output should combine the provided MT5 workbook and TradingView strategy tester screenshots, then add A-share research fields. Reports should be full-market artifacts with `symbol` columns, not one report per stock.
- Reason: QRE normally backtests thousands of A-share symbols in one run. MT5 contributes detailed transaction/result-accounting structure, while TradingView contributes benchmark comparison, risk-adjusted metrics, trade analysis, capital usage, run-up, and drawdown sections. A unified transaction ledger, round-trip table, symbol performance table, strategy summary, equity curve, and manifest are better suited to later GUI display, ranking, clustering, and group analysis.
- Alternatives: Keep only current engineering artifacts; generate one report per symbol; build visual reports before stabilizing the file contract. These were rejected because they do not support broad research comparison cleanly.
- Impact: Task `QRE-REPORT-MT5-TV-FULL-MARKET-001` should produce `backtest_report.xlsx`, `trades_ledger.csv`, `round_trips.csv`, `symbol_performance.csv`, `strategy_performance.json`, `equity_curve.csv`, `drawdown_curve.csv`, `trade_analysis.json`, `capital_usage.json`, and manifest roles for report discovery/audit.
- Owner: USER/CODEX

### 2026-05-21: Send full-market report bundle implementation to Claude Code

- Decision: The next Claude Code implementation task is `QRE-REPORT-MT5-TV-FULL-MARKET-001`.
- Reason: The user approved moving from brainstorm/design into normal dual-agent workflow for the report-output contract. This is the highest-value QRE engine improvement before returning to strategy-entry standardization because it defines the final research-facing output of a backtest.
- Alternatives: Start the strategy-entry compiler first; continue only documenting strategy-entry rules; implement GUI form controls first. These remain future work because a stable report output contract is needed for GUI display and downstream research comparison.
- Impact: `08_IMPLEMENTATION_BRIEF.md`, `11_AGENT_STATE.md`, and `12_AGENT_BOARD.md` now route implementation to Claude Code. Codex will review after Claude writes `09_CODING_HANDOFF.md`.
- Owner: CODEX

### 2026-05-21: Start strategy-entry contract docs implementation as the next slice

- Decision: The next active task is `QRE-STRATEGY-ENTRY-CONTRACT-DOCS-001`, assigned to Claude Code.
- Reason: Full-market report output has been finalized locally. The next bottleneck identified by the user is strategy authoring complexity and non-standard entry structure. Documentation-first standardization is the fastest low-risk step before runtime compiler work.
- Alternatives: Start compiler/preflight runtime changes immediately; start GUI parameter expansion first. These were deferred because authoring contract docs must be stable first.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now defines a docs-focused deliverable under `docs/strategy_entry/` with examples and missing-factor request schema; `11_AGENT_STATE.md` and `12_AGENT_BOARD.md` route execution to Claude Code.
- Owner: CODEX

### 2026-05-21: Finalize strategy-entry contract docs before compiler work

- Decision: Accept and finalize `QRE-STRATEGY-ENTRY-CONTRACT-DOCS-001` as complete after review pass.
- Reason: The delivered docs provide the required authoring contract modules and three strategy-family examples while preserving project boundaries. This reduces strategy writing/debug churn before runtime compiler changes.
- Alternatives: Keep docs task open and mix in compiler implementation immediately. Rejected to avoid coupling documentation baseline with runtime behavior changes.
- Impact: `docs/strategy_entry/` becomes the baseline contract for follow-up tasks, and next slice should focus on operational missing-factor handoff and compiler/preflight linkage.
- Owner: CODEX

### 2026-05-21: Start operational missing-factor handoff standardization

- Decision: Activate `QRE-FACTOR-MISSING-HANDOFF-STANDARD-001` as the next implementation slice.
- Reason: Strategy-entry docs are complete; the next practical bottleneck is converting missing-factor definitions into stable, durable, machine-readable handoff artifacts and lifecycle steps.
- Alternatives: Jump directly to compiler runtime work; start GUI controls first. Deferred to avoid coupling multiple moving parts before request workflow is stable.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now scopes artifact emission (`missing_factor_requests.json`), lifecycle semantics (`pending/fulfilled/blocked`), and targeted tests; execution routed to Claude Code.
- Owner: CODEX

### 2026-05-21: Finalize missing-factor handoff standard before compiler linkage

- Decision: Accept and finalize `QRE-FACTOR-MISSING-HANDOFF-STANDARD-001` after review pass.
- Reason: The implementation delivers durable missing-factor request output, deterministic empty-case behavior, CLI status reporting, and regression coverage without widening into compiler/runtime scope.
- Alternatives: Start compiler linkage in the same slice. Rejected to keep the handoff contract stable and independently verifiable first.
- Impact: `missing_factor_requests.json` output is now operational baseline; next slice should focus on compiler/preflight linkage from high-level strategy entry format to current executable spec.
- Owner: CODEX

### 2026-05-21: Start high-level strategy entry compiler/preflight linkage

- Decision: Activate `QRE-STRATEGY-ENTRY-COMPILER-PREFLIGHT-LINKAGE-001` as the next implementation slice.
- Reason: Strategy-entry docs and missing-factor handoff are now both stable; the next bottleneck is executable linkage from high-level entry format into current preflight/runtime-compatible low-level spec.
- Alternatives: Expand GUI parameters first; jump to advanced runtime compiler. Deferred to keep the linkage layer small, testable, and backward-compatible.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now scopes parser/linkage/CLI/test work while preserving existing low-level workflow and report behavior.
- Owner: CODEX

### 2026-05-22: Finalize high-level entry compiler/preflight linkage after runtime fix

- Decision: Accept and finalize `QRE-STRATEGY-ENTRY-COMPILER-PREFLIGHT-LINKAGE-001` after the alias-expression runtime compatibility fix.
- Reason: The blocking incompatibility between compiler-emitted expressions and the existing signal evaluator was resolved, and end-to-end compatibility tests now validate the compile-to-runtime path.
- Alternatives: Keep task open for additional crossover/runtime enhancements. Deferred to keep this slice focused on baseline linkage correctness.
- Impact: High-level strategy entries now have a runnable bridge into current preflight/runtime-compatible low-level `StrategySpec` flow via `qre compile`.
- Owner: CODEX

### 2026-05-22: Start three-strategy standardized entry smoke validation

- Decision: Start `QRE-STRATEGY-ENTRY-THREE-SMOKE-001` as the next Claude Code implementation task.
- Reason: The strategy-entry docs, missing-factor handoff, and compiler linkage are complete; the immediate next value is reproducible end-to-end evidence across three canonical strategy families.
- Alternatives: Expand compiler/runtime features first; start GUI parameterization first. Deferred until validation evidence is produced.
- Impact: Claude Code now owns smoke validation for RSI2, EMA200+Bollinger, and MACD workflows with output artifacts under `outputs/strategy-entry-smoke/` and a consolidated report at `docs/strategy_entry/three_strategy_smoke_report.md`.
- Owner: CODEX

### 2026-05-22: Finalize three-strategy smoke baseline and start runner automation

- Decision: Finalize `QRE-STRATEGY-ENTRY-THREE-SMOKE-001` and launch `QRE-STRATEGY-ENTRY-SMOKE-RUNNER-AUTOMATION-001` as the next Claude task.
- Reason: Baseline smoke evidence is complete and review passes; the next bottleneck is repeatability and operator friction from multi-command manual execution.
- Alternatives: Start DB-dependent deeper smoke immediately; expand compiler/runtime crossover semantics first.
- Impact: New implementation focuses on one-command smoke execution and deterministic `smoke_summary.json` output while preserving no-DB skip semantics.
- Owner: CODEX

### 2026-05-22: Escalate to overnight strategy-entry pipeline hardening package

- Decision: Upgrade next lane to `QRE-STRATEGY-ENTRY-PIPELINE-HARDENING-001` for long-running overnight implementation.
- Reason: User requested a heavier background task window; packaging orchestration, summary schema, CLI integration, and targeted tests/docs in one slice maximizes unattended progress.
- Alternatives: Keep only narrow runner automation; pause for next-day manual sequencing.
- Impact: `08_IMPLEMENTATION_BRIEF.md`, `11_AGENT_STATE.md`, and `12_AGENT_BOARD.md` now point to the heavy A→D delivery package for Claude Code.
- Owner: CODEX

### 2026-05-22: Route blocking truthiness fix after hardening review

- Decision: Mark `QRE-STRATEGY-ENTRY-PIPELINE-HARDENING-001` as `REQUEST_CHANGES` and open focused fix task `QRE-STRATEGY-ENTRY-BACKTEST-SMOKE-TRUTHINESS-001`.
- Reason: `backtest_smoke` can currently be marked `pass` without executing real backtest work when DB is available.
- Alternatives: Finalize as-is and defer semantics fix. Rejected due to misleading evidence risk in summary outputs.
- Impact: New brief requires real execution-backed backtest status, with tests and handoff updates before re-review.
- Owner: CODEX


### 2026-05-22: Finalize backtest-smoke truthiness and open artifact-parity slice

- Decision: Accept `QRE-STRATEGY-ENTRY-BACKTEST-SMOKE-TRUTHINESS-001` and start `QRE-STRATEGY-SMOKE-ARTIFACT-PARITY-001`.
- Reason: Backtest-smoke status is now execution-backed; next bottleneck is richer reusable artifacts and clearer summary/CLI visibility for DB-enabled smoke runs.
- Alternatives: Stop after truthiness fix and defer all enhancements. Deferred to keep overnight progress momentum.
- Impact: New brief targets additive artifact/summary improvements while preserving no-DB and truthiness semantics.
- Owner: CODEX


### 2026-05-22: Finalize smoke artifact parity and open manifest/audit slice

- Decision: Accept `QRE-STRATEGY-SMOKE-ARTIFACT-PARITY-001` and start `QRE-STRATEGY-SMOKE-MANIFEST-AUDIT-001`.
- Reason: Smoke artifacts and stage timing visibility are now stable; next bottleneck is manifest-level discoverability and audit parity for smoke outputs.
- Alternatives: Pause after parity improvements. Deferred to keep reproducibility workflow convergent with existing report-manifest patterns.
- Impact: New brief adds deterministic `smoke_report_manifest.json` generation, CLI visibility, and targeted tests/docs.
- Owner: CODEX


### 2026-05-22: Finalize smoke manifest/audit and open filter-parity regression slice

- Decision: Accept `QRE-STRATEGY-SMOKE-MANIFEST-AUDIT-001` and start `QRE-STRATEGY-SMOKE-MANIFEST-FILTER-PARITY-001`.
- Reason: Manifest emission is complete; next reliability gap is selector-behavior regression locking for `report-files`/`report-audit` on smoke roles/symbol filters.
- Alternatives: Pause after manifest emission and defer regression hardening. Deferred to keep CLI behavior stable under future changes.
- Impact: New brief focuses on targeted tests first, with runtime changes only if tests reveal a defect.
- Owner: CODEX


### 2026-05-22: Finalize smoke manifest filter parity and open discovery CLI slice

- Decision: Accept `QRE-STRATEGY-SMOKE-MANIFEST-FILTER-PARITY-001` and start `QRE-STRATEGY-SMOKE-DISCOVERY-CLI-001`.
- Reason: Filter parity is now regression-locked; next operator pain is fast discovery of latest smoke outputs without chaining multiple commands.
- Alternatives: Stop after regression locks and defer UX improvements. Deferred to reduce manual inspection overhead in ongoing strategy research cycles.
- Impact: New brief adds a read-only smoke discovery command with optional JSON and role/strategy selectors.
- Owner: CODEX


### 2026-05-22: Finalize smoke discovery baseline and open latest-run ergonomics slice

- Decision: Accept `QRE-STRATEGY-SMOKE-DISCOVERY-CLI-001` and start `QRE-STRATEGY-SMOKE-DISCOVERY-LATEST-001`.
- Reason: Discovery CLI baseline is stable; the remaining UX gap is automatic latest-run resolution when users omit `--output-dir`.
- Alternatives: Keep manual output-dir-only flow. Deferred to reduce operational friction in repetitive smoke inspections.
- Impact: New brief adds latest-run resolution, explicit `--latest`, and resolved-directory visibility with targeted CLI tests.
- Owner: CODEX


### 2026-05-22: Finalize latest-run discovery and open stability-hardening slice

- Decision: Accept `QRE-STRATEGY-SMOKE-DISCOVERY-LATEST-001` and start `QRE-STRATEGY-SMOKE-DISCOVERY-STABILITY-001`.
- Reason: Latest discovery works; remaining UX risk is nondeterministic listing/count presentation across manifest and fallback paths.
- Alternatives: Stop after latest discovery and defer stability locks. Deferred to keep smoke-file outputs predictable for automation and review tooling.
- Impact: New brief adds deterministic ordering, `source_mode` exposure, and parity regression tests.
- Owner: CODEX


### 2026-05-22: Finalize discovery stability and open details-view slice

- Decision: Accept `QRE-STRATEGY-SMOKE-DISCOVERY-STABILITY-001` and start `QRE-STRATEGY-SMOKE-DISCOVERY-DETAILS-001`.
- Reason: Discovery outputs are now stable and deterministic; next UX gap is explicit per-strategy details rendering without requiring manual JSON parsing.
- Alternatives: Stop after stability hardening. Deferred to improve operator throughput during repeated smoke triage.
- Impact: New brief adds `--details` mode with selector-safe behavior and targeted CLI regression coverage.
- Owner: CODEX


### 2026-09-18: 端口 8080/8081 同包部署的边界确认

- Decision: 明确 8080 管理台与 8081 lab 同属单一包 `quant_research_engine`（`gui/` 下 admin.py 与 lab.py 两个 Flask 入口），同一 git 版本，引擎层（portfolio/、strategies/、data/）单例共享，不存在版本分叉风险。约定：(a) 引擎层任何改动两端同时生效，全量测试基线即兼容保障；(b) 8080 = 管理台（因子管理/PG 状态卡/聚类动量等，保持管理风格不动），8081 = 面向普通用户的 lab，UI 改动先在 18080 设计稿验证再移植 8081；(c) 未来 SaaS 化时 8081 的 Web 层与引擎经 job/worker 协议解耦（ECS + 家里 worker），8080 管理台留在本地不对外；(d) qre-outputs（22G 产物）与代码仓分离原则继续保持，产物不进仓。
- Reason: 两端长期并行演进，曾出现「8081 改动是否影响 8080」的反复确认成本；白纸黑字固化边界可消除歧义，也为 SaaS 化解耦（15 号文档）定调。
- Alternatives: 拆成两个包/两个仓库。否决——引擎单例共享是核心价值，拆包只会引入版本同步成本而无收益。
- Impact: 引擎层改动无需双端协调评审，测试基线兜底；UI 改动有明确验证顺序（18080 → 8081）；SaaS 化路线（job/worker 解耦）与本约定一致。
- Owner: KIMI_CODE（用户 2026-09-18 确认）


### 2026-09-27: SaaS 后台管理（E1-E3）的路由前缀与最小可行裁剪

- Decision: 后台管理路由用 `/saas/console` + `/api/saas/console/*`，不用设计文档 15 号原写的 `/api/admin/*`；users 表只加 `role`/`status` 两列（不加 CHECK 约束，取值应用层校验）；E3 只做 worker 在线状态 + 失败任务查看/重试/取消，指令下发与家里 PG 状态卡（经 worker 上报）留作后续。
- Reason: 12 号文档 §7 禁链纪律（断言测试 TestNoAdminLinks）禁止 SaaS 页面出现 `/admin` 字样且含 HTML/JS 注释——管理台导航入口需经 base.html 公共 JS 注入，与 `/admin` 前缀天然冲突；`/console` 前缀两全。users 加 CHECK 约束在旧库升级时需 DO 块判存（tier 列当年踩过顺序坑），role/status 语义简单，应用层校验足够。指令下发需要 worker 协议加指令通道，超出 E 阶段「能手动 SQL 顶着」的内测定位。
- Alternatives: ①保留 /api/admin 前缀并豁免禁链断言——否决，纪律刚重写过且有两处撞线教训；②workers 表加 CHECK/心跳走 Redis——否决，纯 PG 是既定内测选型（17 号协议 §7）。
- Impact: 管理端测试管理员账号 = 先注册再 `UPDATE users SET role='admin'`；未来若上正式管理台域名再议 /admin 命名。禁用账号的语义：登录 403 + 既有 session 立即失效（_current_user_id 的 status 过滤）。
- Owner: KIMI_CODE


### 2026-09-27: SaaS 管理台从公网撤下，改 SSH 隧道访问（方案 A）

- Decision: `/saas/console` 与 `/api/saas/console/*` 在 nginx 层直接 return 404（仓库 deploy/landing/nginx-aguhuice.conf 管理，已同步线上）；gunicorn 仍只听 127.0.0.1:8090 不动，管理员经 `deploy/saas/admin-tunnel.sh`（ssh -N -L 9090:127.0.0.1:8090）访问 http://localhost:9090/saas/console。base.html 不再注入顶栏「管理台」入口（公网点了也是 404，入口无意义）。附加项：ECS 每日 pg_dump aguhuice 存 /srv/aguhuice/backups/ 保留 7 天（root cron 03:17），本地 WSL cron 04:23 经 deploy/saas/pull-ecs-backup.sh scp 拉取最新 dump 到 ~/quant-workspace/backups/ecs-aguhuice/（拉取模式，ECS 无反向访问）。
- Reason: 管理台只面向管理员一人，公网暴露面纯负担（_require_admin 之外多一层纵深）；SSH 密钥本已是运维必备，隧道零新增攻击面、零新增组件。备份是用户批准的同批附加项——此前 PG 无任何离线副本。
- Alternatives: ①nginx 层 IP 白名单——否决，管理员出口 IP 不固定；②保留公网 + 强化鉴权——否决，攻击面仍在；③管理台下线只靠 SQL——否决，五 tab 运维效率已经验证过价值。
- Impact: 公网 console 路径一律 404（页面与 API 同测验证），/saas/new 等正常页面回归 200；tests/test_gui_saas_console.py 顶栏入口断言反转为「不注入」；运维速查见 16 号文档第 5 节。隧道内仍走 _require_admin 鉴权（双保险）。
- Owner: KIMI_CODE（用户 2026-09-27 拍板方案 A）


### 2026-09-27: 公网股票代码显示脱敏 + worker per-symbol 产物回传通道（QRE-SAAS-SYMBOL-UX）

- Decision: ①公网用户可见页面的股票代码一律不显示 .SZ/.SH/.BJ 后缀（不暴露数据源代码体系）——内部存储/API 载荷保持带后缀原样，仅前端渲染层剥离（base.html 公共 dispCode()）；输入侧反向后缀补全规范化（60/68→SH、00/30→SZ、4/8/920→BJ，非法代码友好 400），规范化在提交落库前完成。②公网个股详情（K线/买卖点/因子/收益曲线/磨损）走「worker 回传 per-symbol 产物」：worker 本地有行情库，回测后对实际触发交易的个股逐个生成 build_lab_symbol_detail 同形态 JSON，gzip 写 `_symbol_details/<ts_code>.json.gz` 随既有 result/meta + result/files 通道上传（15MB 上限、按 |总净盈亏| 降序截断、清单内优先），ECS 落盘（SAAS_UPLOAD_DIR/job_<id>/）后 api_result_symbol_detail 读文件渲染；基准指数序列不随个股重复回传（复用任务级 chart_data.benchmarks 按个股净值日期对齐注入）；产物缺失回退本地实时查库（staging 行为不变）。
- Reason: ECS 无行情库是既定架构（15 号文档），个股详情的 K线/因子只能来自 worker；复用既有两步回传协议与落盘目录零新增通道。截断+gzip 后单股 ~10-40KB，实测 2 股任务总上传 32 文件 / 数百 KB，远低于 20MB 清单上限，量级可接受故按批准方案直接实现。
- Alternatives: ①ECS 建行情只读副本——否决，123GB 库上 2C2G/40G 盘不可行；②结果 jsonb 内嵌 per-symbol 明细——否决，results.chart_data 会爆到 MB 级拖垮列表查询；③按需回传（用户点详情才触发 worker 补传）——留作后续增强，当前任务完成即全量备齐更简单可靠。
- Impact: worker runner 新增 build_symbol_detail_files/_fill_excess_return；saas app 个股详情端点支持无后缀代码解析（resolve_ts_code：先按本任务实际交易个股精确匹配再按号段推断）；结果删除（DELETE /api/results/<id>）连带清理 _symbol_details 目录（既有 job_dir 整删覆盖）；17 号协议 §3.3 files 清单语义不变（子目录相对路径已支持）。
- Owner: KIMI_CODE

### 2026-09-27: 意见反馈仅登录用户可提交（QRE-SAAS-FEEDBACK-FACTOR-REQ）

- Decision: 内测意见反馈（新表 feedback）**仅登录用户可提交**，游客 POST /api/saas/feedback 返回 401 并在页面显示登录引导卡；不做游客 IP 限流提交。防滥用改为单用户每日 20 条上限（429）。因子申请沿用既有口径（本就登录限定，24h 同因子集合去重）。
- Reason: 反馈需要可跟进、可回复的账号主体，游客匿名反馈无法闭环且易被刷；游客的核心诉求（免登录试用）已由游客回测通道覆盖，反馈不属于试用刚需。登录限定下无需引入 IP 记列与限流逻辑，schema 最小。
- Alternatives: ①游客按 guest_key/IP 限流提交——否决，无法跟进回复且多一条匿名滥用面；②完全放开——否决，无防护。
- Impact: feedback.user_id NOT NULL；反馈页/申请页对游客显示登录引导卡而非表单；06 本条即「按现有鉴权体系决定」的拍板记录。
- Owner: KIMI_CODE

### 2026-10-18: 回测引擎 OOM 根治与内存红线立法（job#71 事故复盘）

- Decision: ①引擎 shared 模式引入 `assembler.build_chunked` 按股分块（500 股/块）装载/合并/释放，`_prepare_frame` 重写为 groupby 行位置切片就地计算，删除 `_symbol_bar_indices` 的 iterrows 全量索引（原 ~5GB）；②worker 子进程 RLIMIT_AS 默认 14G（`QRE_WORKER_CHILD_MEM_GB` 可配，含 VSZ 守卫），超限抛「任务超出资源配额」；③qre-saas-worker.service MemoryMax 26G→18G（线上已生效）；④内存纪律写入 02 号文档 R-MEM-001（LOCKED）。实测峰值 22.6GB→3.96GB，全市场全期 2.5h→32min，新旧代码产物逐字节一致，2343 tests passed。
- Reason: 事故根因是多点叠加——StringDtype(python) 高基数列、富 metadata 全量 merge、4× frame 拷贝、iterrows 建 2200 万条 Python 对象索引、MemoryMax 高于物理内存导致 cgroup 失效。任何单点修复都挡不住下一次，必须工程修复 + 配额兜底 + 规则立法三层一起做。
- Alternatives: ①float32 全面降内存——否决，ema 近交叉值在 float32 相对误差下可能翻转信号，违反结果口径一致硬约束；②只调 MemoryMax 不改引擎——否决，治标，且 22.6G vs 23G 物理内存无解；③垂直扩容加内存——否决，2G ECS 的前车之鉴证明资源永远会被数据量吃掉，必须先有分块架构。
- Impact: 全市场全期回测从"碰运气能跑"变为确定性可跑且更快；后续所有全市场量级代码路径受 R-MEM-001 约束；job#71 可安全重提（worker 已带新码完成 job#72）。
- Owner: KIMI_CODE

### 2026-10-19: batch 聚合收益口径立法——新股注入不计收益，strategy_total_return 用资金加权聚合（QRE-BATCH-IPO-INJECTION）

- Decision: ①batch 全市场净值曲线 daily_return 只由「上一交易日已在市」股票的权益变动贡献（交集口径：Σ_{昨∩今} e_t / Σ_{昨∩今} e_{t-1} − 1），中途上市新股的 initial_cash 注入视为外部现金流、当日收益贡献为 0；cumulative_return 由该日收益累乘；total_equity 水平值不变（仍含注入，真实资金口径）。②batch 模式 strategy_total_return = Σfinal_equity/Σinitial_cash − 1（summary 的 initial_cash/final_equity 列直算，缺列回退修正后曲线），与 profit_factor/已平仓净盈亏可勾稽。③`summarize_equity_curve` 优先使用曲线自带 daily_return/cumulative_return 列。④buy_hold_return（per-symbol 均值）不经过聚合曲线、不受注入影响，维持不动；shared_cash 分支不动。
- Reason: 旧口径把 4063 次新股 10 万注入计为收益，job#66 曲线报 +220.3% 而真实 −14.76%，正反两策略「双盈利」假象同源于此。交集口径是「注入=外部现金流」的标准做法；strategy_total_return 选资金加权聚合而非曲线累乘，是因为它与 profit_factor/净盈亏直接勾稽，且与 buy_hold（等权 per-symbol 均值，initial_cash 一致时两口径相等）可比。
- Alternatives: ①把注入从 total_equity 水平值也剔除——否决，水平值应反映真实资金规模，且回撤/资金占用等模块消费水平值；②strategy_total_return 直接用修正后曲线累乘值——否决，日复利等权口径含再平衡溢价（job#66：+9.29% vs 资金加权 −14.76%），不与 profit_factor 勾稽；③按个股真实上市日重建历史曲线回填旧产物——留作后续，本次只修计算口径，历史产物标记不可信。
- Impact: 修复前所有 batch 全量回测的 total_return/收益日历不可信（05_PROGRESS 2026-10-19 条已标注）；equity_curve.csv 列结构不变，前端零改动；历史 job 重跑报告生成即可得修正口径。
- Owner: KIMI_CODE

## 2026-10-20 快照 vs 持续跟踪的四层分工（showcase 架构决策）

**背景**：经典策略 showcase 日更上线后，管理员回测记录（快照）与展示页（活体）口径统一问题；及「日更跟踪」是否推广到全部用户记录。

**决策**（用户拍板）：
1. 新增经典策略工作流 = 「全站回测池 → 管理员策展」：console showcase 添加入口接受任何已完成 job_id（含其他用户/游客任务），不为 showcase 单建生产通道。
2. 回测记录保持**不可变快照**语义（实验报告），不随日更延伸；showcase = 快照基线 + showcase_daily 增量行的活体产品。记录列表加「经典策略·跟踪中 →」徽章作为快照到活体的窗口。
3. 「净值持续跟踪」**不**默认推广到全部用户记录：全市场逐票状态机成本高、探索性回测无此需求、且信号监控（strategy_watches）已覆盖操作提醒诉求。未来作为**付费功能** opt-in 开放，复用 showcase_roller 架构（记入 19 付费矩阵第 6 项升级方向）。
4. 四层分工：回测记录=快照（所有人）/ 信号监控=操作提醒（已上线）/ 净值持续跟踪=付费 opt-in（未来）/ 经典策略=管理员策展公开门面（已上线）。

**备选否决**：直接延伸用户原始 job 的结果数据（混入不可变结果语义，且成本高）——否决。
