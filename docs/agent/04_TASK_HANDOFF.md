# Task Handoff

## Current Task

QRE-RESEARCH-RUN-STAGE-ARTIFACT-PARITY-001: Make `qre research-run` persist and link stage-scoped preflight, evaluation, and backtest artifacts.

## Task ID

QRE-RESEARCH-RUN-STAGE-ARTIFACT-PARITY-001

## Current Status

READY_FOR_IMPLEMENTATION. User approved the brief after reading `11_AGENT_STATE.md` and `12_AGENT_BOARD.md`; Claude Code should implement from `08_IMPLEMENTATION_BRIEF.md`.

## Current Owner

CLAUDE_CODE

## Problem Summary

`qre research-run` is documented as a complete preflight -> eval -> backtest bundle, but the current implementation does not persist evaluation artifacts from the orchestrator and writes backtest outputs directly into the run root. This weakens report discovery/audit parity and makes the documented `eval/report_manifest.json` and `backtest/report_manifest.json` layout inaccurate.

## Handoff To Claude Code

Read:

- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Implement only the brief. Preserve locked requirements and avoid unrelated architecture rewrites.

## Expected Return To Codex

After implementation, update:

- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

Then set the state so Codex can review.
