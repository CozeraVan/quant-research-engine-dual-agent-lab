# Agent State

This file is the source of truth for dual-agent workflow recovery.

## Current Phase

WAITING_CLAUDE_CODE

## Current Owner

CLAUDE_CODE

## Current Task

`QRE-BENCHMARK-MEMBERSHIP-INDUSTRY-ADAPTERS-001`

## Last Completed Step

Codex finalized the next brief and handed off the implementation slice:

- `reference.index_weight` is the intended source for benchmark membership enrichment.
- Industry metadata should be normalized into a stable grouping column without mutating the raw passthrough.
- `08_IMPLEMENTATION_BRIEF.md`, `09_CODING_HANDOFF.md`, `11_AGENT_STATE.md`, and `12_AGENT_BOARD.md` were updated for the new task.
- `docs/modules/data_layer.md`, `docs/modules/portfolio_layer.md`, `docs/modules/portfolio_workflow.md`, and `docs/modules/portfolio_agent.md` are being aligned to the new slice.

## Git State

- Current branch: `master`
- Last finalized commit: `9e00f0a`
- Working tree: modified across QRE plus sibling `quant_ts` files from the reference-data migration/backfill work.
- Remote push: not requested.
- Do not revert unrelated dirty files.

## Latest Validation Evidence

Current planning evidence:

- `../quant_ts/REFERENCE_DATA.md` lists `reference.index_weight` as the benchmark membership source.
- `../quant_ts/handlers/reference_data_handler.py` defines the `index_weight` reference dataset for read-only ingestion ownership in the sibling project.
- `scripts/check-progress-docs.sh` will be rerun after the doc sync completes.

## Required Claude Code Task

Implement `QRE-BENCHMARK-MEMBERSHIP-INDUSTRY-ADAPTERS-001` exactly from `08_IMPLEMENTATION_BRIEF.md`.

Minimum required behavior:

- benchmark membership enrichment uses the latest available `reference.index_weight` snapshot when benchmark context is available;
- `industry_group` is a stable normalized grouping column;
- explicit `QRE_SECURITY_METADATA_TABLE` behavior remains first priority;
- missing benchmark membership data keeps the previous metadata behavior intact;
- QRE remains read-only and does not add Tushare producer code.

## Completion Estimate

For the current MVP scope, QRE remains roughly 90%+ complete. The current non-deferred read-side gap is benchmark membership and industry classification standardization. Future enhancements such as real regime grouping and deeper as-of metadata should not be included in this slice.

## Short Prompt Commands

### For Codex

```text
请读取 11 和 12。当前新任务已准备好，请按 08/09/11/12 的内容推进 Claude Code。Codex 继续只做规划/复审/最终化，不恢复 Tushare 下载/入库代码。
```

### For Claude Code

```text
请读取 08、09、11、12，并实现 QRE-BENCHMARK-MEMBERSHIP-INDUSTRY-ADAPTERS-001。只做 QRE 读侧：接入 reference.index_weight 的最新 benchmark membership，并把 industry 标准化成稳定 grouping 列。不要修改 quant_ts，不要添加 Tushare 下载/入库逻辑。完成后更新 09 并等待 Codex 复审。
```
