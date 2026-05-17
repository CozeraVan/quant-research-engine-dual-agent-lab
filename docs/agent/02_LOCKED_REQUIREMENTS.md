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

## R-DUAL-001: Codex owns planning and review

Status: LOCKED

Codex should produce:

- `08_IMPLEMENTATION_BRIEF.md`
- `10_REVIEW_REPORT.md`

Codex should not do large implementation work unless explicitly requested.

## R-DUAL-002: Claude Code owns implementation

Status: LOCKED

Claude Code should implement from:

- `08_IMPLEMENTATION_BRIEF.md`

Claude Code should not invent architecture beyond the brief unless it first writes a question or blocker.

## R-DUAL-003: Agent state is the source of truth

Status: LOCKED

If chat history and docs disagree, prefer:

1. `11_AGENT_STATE.md`
2. `04_TASK_HANDOFF.md`
3. `08_IMPLEMENTATION_BRIEF.md`
4. `09_CODING_HANDOFF.md`
5. `10_REVIEW_REPORT.md`
6. `git status` / `git log`

## R-GIT-001: Codex owns final git commit and push

Status: LOCKED

By default, final commit and push should be performed by Codex after review passes.

Default policy:

- Claude Code may implement code.
- Codex reviews and proposes final commit message.
- User approves finalization.
- Codex commits and pushes.

If the user wants full automation, they may add standing approval to `11_AGENT_STATE.md`.

## R-GIT-002: No push before review passes

Status: LOCKED

Do not push code until:

- implementation is complete,
- required tests/checks have run or unavailable checks are documented,
- `10_REVIEW_REPORT.md` has no Required Fixes,
- user approval or standing approval exists.
