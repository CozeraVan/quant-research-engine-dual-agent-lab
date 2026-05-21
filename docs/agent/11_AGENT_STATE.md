# Agent State

This file is the source of truth for dual-agent workflow recovery.

## Current Task ID

QRE-DATA-REAL-SUSPENSION-ST-RISK-WARNING-METADATA-001

## Current Phase

BLOCKED

## Current Owner

CODEX

## Last Completed Step

Claude Code investigated the upstream data environment for `QRE-DATA-REAL-SUSPENSION-ST-RISK-WARNING-METADATA-001` and confirmed that no security-status metadata table exists in the local `tushare_data` database. The reusable Tushare source scaffold and canonical snapshot contract now exist in `src/quant_research_engine/data/tushare_security.py`, but the real metadata task remains blocked on source availability.

## Next Required Step

Codex should keep `M4.9` blocked until an upstream security-status table is confirmed. The reusable source scaffold is available for future bulk ingestion work.

## Git State

- Current branch: `master`
- Last accepted implementation commit: `2da15bb`, `Preserve window_size and group_by selector parity under JSON strict mode`
- Working tree contains code + tests + agent doc updates for the blocked real-metadata task and the reusable Tushare source scaffold.
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
