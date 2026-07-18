# Implementation Brief

## Task ID

QRE-SINGLE-AGENT-MIGRATION-001

## Created By

KIMI_CODE (single agent; user-directed task)

## Intended Implementer

KIMI_CODE

## Goal

Migrate the project's development workflow documentation from the retired dual-agent setup (Codex + Claude Code) to single-agent development under Kimi Code, and make `docs/agent/` markdown files the authoritative long-term memory for all future development. A full documentation audit was performed first; stale or contradictory status claims found during the audit are corrected in the same pass.

## Scope

1. Rewrite `AGENTS.md` as the single-agent project instruction entry point.
2. Reduce `CLAUDE.md` to a redirect page pointing at `AGENTS.md` (file preserved per R-CORE-005).
3. Update `docs/agent/00_PRODUCT_VISION.md`, `01_CURRENT_STATUS.md`, `02_LOCKED_REQUIREMENTS.md`, `07_RECOVERY_PROTOCOL.md`, `11_AGENT_STATE.md` to the single-agent model.
4. Correct the stale "fully frozen, no further work" closeout wording in `01_CURRENT_STATUS.md`; record the completed-but-uncommitted strategy catalog batch backtest as the actual repository state.
5. Add a workflow-superseded banner to `03_ROADMAP.md`; append the migration tracker row to `05_PROGRESS.md`; prepend the mode-switch decision to `06_DECISION_LOG.md`.
6. Reset `08_IMPLEMENTATION_BRIEF.md`, `09_CODING_HANDOFF.md`, `10_REVIEW_REPORT.md` to this task; deprecate `12_AGENT_BOARD.md`.
7. Rewrite the seven skills in `.agents/skills/` and `.claude/skills/` (identical copies) as single-agent flows, dropping the `codex-`/`claude-` prefixes: `plan-brief`, `implement`, `self-review`, `git-finalize`, `intake-change`, `resume-task`, `update-progress`.
8. Update `README.md` workflow references and the `docs/strategy_entry/README.md` audience sentence.
9. Update `docs/agent/change_requests/CR-0000-template.md` state-transition wording.

## Required Behavior

- Preserve historical logs (`03/05/06` bodies, `docs/legacy/`, archived root trackers) unchanged except the explicitly listed banner/append/prepend additions.
- No runtime code, tests, strategy YAMLs, or outputs change.
- The new phase vocabulary is `PLANNING` → `IMPLEMENTING` → `SELF_REVIEW` → `AWAITING_GIT_APPROVAL` → `DONE` / `USER_DIRECTED`.
- Git finalization of any work (including this task) requires self-review pass plus explicit user approval.

## Non-Goals

- Do not commit the previously uncompleted batch backtest work products; that is a separate pending user decision.
- Do not rename the project directory (`dual-agent-lab` label is stale but paths must not break).
- Do not delete `CLAUDE.md`, `12_AGENT_BOARD.md`, or any historical document.
- Do not touch `quant_ts` or `indicators_tushare`.
- Do not perform `git commit` / `git push` without explicit user approval.

## Expected Tests

Documentation-only task:

```bash
scripts/check-progress-docs.sh
git diff --check
bash -n scripts/*.sh .claude/hooks/*.sh
grep -rn "Codex\|CLAUDE_CODE\|dual-agent" --include='*.md' .   # remaining hits must be historical only
```

## Validation Commands

```bash
scripts/check-progress-docs.sh
git diff --check
bash -n scripts/agent-status.sh scripts/check-progress-docs.sh scripts/git-finalize-check.sh .claude/hooks/progress-gate.sh
```

## Acceptance Criteria

- No active workflow document describes the dual-agent flow as current practice.
- `docs/agent/` alone suffices to reconstruct project state: engine feature-complete, batch backtest done and uncommitted, three pending user decisions.
- Historical content is preserved; remaining Codex/Claude mentions are historical attributions or archive banners only.
- All validation commands pass.
