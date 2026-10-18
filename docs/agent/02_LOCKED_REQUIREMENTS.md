# Locked Requirements

Locked requirements must not be removed, weakened, or silently changed.

## R-CORE-001: Preserve existing working behavior

Status: LOCKED

Do not remove working features unless explicitly requested.

## R-CORE-002: No unrelated rewrites

Status: LOCKED

Do not rewrite unrelated modules while implementing a focused task.

## R-CORE-003: Changes must be verifiable

Status: LOCKED

Every meaningful code change should have a validation path:

- tests
- lint
- typecheck
- manual verification
- documented reason why validation is unavailable

## R-CORE-004: Protect user secrets

Status: LOCKED

Do not read, print, commit, or push secrets.

Protected examples:

- `.env`
- `.env.*`
- API keys
- database credentials
- SSH keys
- cloud credentials
- personal tokens

## R-CORE-005: Preserve project memory files

Status: LOCKED

Do not delete the agent workflow files unless explicitly requested:

- `CLAUDE.md`
- `AGENTS.md`
- `docs/agent/*`

## R-QRE-001: Project scope is current quant-research-engine only

Status: LOCKED

Do not expand planning or implementation into the larger `quant-workspace` program unless the user explicitly asks. Treat `quant_ts` and `indicators_tushare` as upstream data producers.

## R-QRE-002: Engine must not compute technical indicators internally

Status: LOCKED

Backtests and evaluations consume factor columns declared by strategy specs and loaded from `factors.*` tables. Do not add hidden indicator recomputation inside data, evaluation, or portfolio engines.

## R-QRE-003: No future-function leakage or lookahead bias

Status: LOCKED

Signals must use data available at the signal date. A-share daily execution defaults to signal on `t` and earliest execution on `t+1`. Portfolio simulation must not use future bars to decide current orders, exits, weights, or risk controls.

## R-QRE-004: Keep market rules in market profiles

Status: LOCKED

A-share costs, slippage, lot sizing, price limits, T+1 sellability, board rules, and future market-specific behavior must stay in market/profile/rule layers rather than strategy logic.

## R-QRE-005: Data access must be read-only unless explicitly approved

Status: LOCKED

QRE reads market, factor, metadata, benchmark, and reference data. It must not write to upstream databases during evaluation, preflight, or backtest work unless a future brief explicitly authorizes it.

## R-QRE-006: Do not hardcode credentials

Status: LOCKED

Use environment variables such as `QRE_MARKET_DB_URL` and compatible `SR_*` fallbacks. Do not add passwords or local secrets to code or docs.

## R-QRE-007: Preserve report artifacts and manifest contracts

Status: LOCKED

Batch and shared-cash report outputs must remain discoverable through `report_manifest.json`. Do not break `qre report-files` or `qre report-audit` behavior without an explicit migration plan.

## R-QRE-008: Smoke outputs are not research conclusions

Status: LOCKED

Small-window examples and DB smokes validate plumbing only. Do not document them as evidence that a factor or strategy is effective.

## R-QRE-009: Small-sample validation before full-scale runs

Status: LOCKED

Before launching any full-market or full-history batch run that exercises new or changed engine/pipeline code, first validate correctness and measure efficiency on a small sample (a few symbols and a short window). Only after the small-sample run passes and its cost is measured may the full-scale run proceed. (User standing instruction, 2026-07-19.)

## R-AGENT-001: Single agent owns the full development cycle

Status: LOCKED

Kimi Code is the sole development agent and should produce:

- `08_IMPLEMENTATION_BRIEF.md` (planning)
- implementation per the brief
- `10_REVIEW_REPORT.md` (self-review)

The same agent plans and implements, so self-review must actively check the implementation against the brief and the LOCKED requirements rather than rubber-stamping it.

## R-AGENT-002: Markdown docs are the only long-term memory

Status: LOCKED

The `docs/agent/` markdown files are the project's only authoritative long-term memory. Chat/CLI conversation history is not a source of truth.

- Every meaningful change must be recorded in the relevant `docs/agent/` files in the same work session.
- A new session starts by reading `11_AGENT_STATE.md`, `04_TASK_HANDOFF.md`, and `05_PROGRESS.md`, not by asking what happened in chat.

## R-AGENT-003: Agent state docs are the source of truth

Status: LOCKED

If chat history and docs disagree, prefer:

1. `11_AGENT_STATE.md`
2. `04_TASK_HANDOFF.md`
3. `08_IMPLEMENTATION_BRIEF.md`
4. `09_CODING_HANDOFF.md`
5. `10_REVIEW_REPORT.md`
6. `git status` / `git log`

## R-GIT-001: Kimi Code executes git finalization after user approval

Status: LOCKED

Kimi Code performs final commit (and push, if a remote exists and was requested) only after review passes and the user approves.

Default policy:

- Kimi Code implements and self-reviews code.
- Kimi Code proposes the final commit message.
- User approves finalization.
- Kimi Code commits (and pushes if applicable).

If the user wants full automation, they may add standing approval to `11_AGENT_STATE.md`.

## R-GIT-002: No commit before review passes

Status: LOCKED

Do not commit code until:

- implementation is complete,
- required tests/checks have run or unavailable checks are documented,
- `10_REVIEW_REPORT.md` has no Required Fixes,
- user approval or standing approval exists.

## R-MEM-001: 内存红线——任何全市场计算必须分块，任何长跑子进程必须有内存配额

Status: LOCKED

背景：2026-10-18 job#71（全市场全期回测）子进程峰值 22.6GB 被全局 OOM 连杀三次，拖垮 worker 全部槽位（详见 06 号文档同日决策）。此类事故一律不得重现。

规则：

1. 任何「全市场 × 全历史」量级的计算（回测、评估、因子计算、导出）**必须分块/流式**，禁止一次性物化全量面板到内存；新增此类代码路径时，峰值内存必须有实测数据。
2. 单个子进程峰值内存预算 **≤ 物理内存 50%**（当前 23G 机器即 ≤12G）；worker 回测子进程强制 RLIMIT_AS（`QRE_WORKER_CHILD_MEM_GB`，默认 14G），超限必须抛可读「任务超出资源配额」错误，禁止裸 OOM -9。
3. systemd 服务的 `MemoryMax` **不得超过物理内存的 80%**，使 cgroup 先于全局 OOM killer 生效；改机器内存配置后必须同步复核该值。
4. DataFrame 装载纪律：禁用 `StringDtype(python)` 存高基数代码列（用 category）；metadata 只 merge 实际请求列；禁止 `iterrows()` 建逐行 Python 对象索引。
5. 信号输入因子列保持 float64（精度硬约束，float32 可能翻转近交叉信号）；降内存只能靠分块/裁剪/编码，不许牺牲计算精度。
