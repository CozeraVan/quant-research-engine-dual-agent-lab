# Agent State

This file is the source of truth for dual-agent workflow recovery.

## Current Task ID

QRE-DOCS-EVAL-GROUP-BY-MANIFEST-PARITY-USAGE-001

## Current Phase

CODEX_REVIEWING

## Current Owner

CODEX

## Last Completed Step

Claude Code updated README, data_layer.md, and portfolio_workflow.md with evaluation group-by manifest parity usage docs. Documentation now covers combined `group_summary.csv` plus per-column `group_summary_by_<col>.csv`, manifest `group_by` metadata distinction, and `report-files` / `report-audit --group-by` discovery/audit examples. Validation: `scripts/check-progress-docs.sh` passed; `git diff --check` passed.

## Next Required Step

Codex should review and produce `10_REVIEW_REPORT.md`.

## Git State

- Current branch: `master`
- Last accepted implementation commit: `745103e`, `Align evaluation grouped artifact filtering`
- Working tree contains documentation changes for `QRE-DOCS-EVAL-GROUP-BY-MANIFEST-PARITY-USAGE-001` plus agent doc updates.
- Standing approval: local commits approved by user; no remote push requested.

## Short Prompt Commands

### For Claude Code

```text
请读取 11 和 12，执行当前 Claude Code 任务。
```

### For Codex

```text
请读取 11 和 12，执行 One-Shot Review-Finalize-Next。
```
