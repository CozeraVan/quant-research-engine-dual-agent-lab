# Agent State

This file is the source of truth for dual-agent workflow recovery.

## Current Phase

USER_ACCEPTANCE

## Current Owner

USER

## Last Completed Step

Claude Code implemented `QRE-RESEARCH-RUN-AUDIT-USAGE-DOCS-001`, and Codex reviewed it with PASS.

Changes:
- README section 10 expanded with role-specific audit examples (run_manifest, preflight_report, eval_report_manifest, backtest_report_manifest)
- portfolio_workflow.md: new research-run audit contract subsection
- portfolio_layer.md: new report-manifest audit pointer section
- No runtime/schema/test changes. Full suite unchanged at 836 passed.

Codex should finalize this reviewed documentation slice locally, then open the next narrow implementation brief.

## Git State

- Current branch: `master`
- Last finalized commit: `a027d69` (lock research-run audit role selector parity; next local commit pending for audit usage docs)
- Last handoff checkpoint: `796b1ad` (research-run audit usage documentation brief)
- Standing approval: local commits approved by user; no remote push requested.
- Working tree: modified (documentation slice reviewed; local commit pending)
- Remote push: not requested.

## Latest Validation Evidence

- `uv run pytest -q` -> 836 passed, 2 warnings in 11.80s
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> clean
- `rg` research-run role coverage: README 18 matches, portfolio_workflow.md 14 matches, portfolio_layer.md 1 match

## Short Prompt Commands

### For Codex

```text
请读取 11 和 12，提交已通过 review 的本轮文档同步，然后为 Claude Code 打开下一轮 implementation brief。
```

### For Claude Code

```text
请读取 11 和 12，等待 Codex 打开下一轮任务。
```
