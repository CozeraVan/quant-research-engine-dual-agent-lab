# Quant Research Engine

`quant-research-engine` is a reusable research and backtesting framework.

The first implementation target is A-share daily technical-factor research, but the framework should not be designed as an A-share-only or daily-only system. Future market plugins may support funds, forex, crypto, futures, options, intraday bars, tick data, and lower-latency simulation.

## Positioning

This project has two coordinated engines:

- **Evaluation engine**: fast, full-market factor and strategy screening.
- **Portfolio engine**: realistic account-level backtesting and simulated trading validation.

The evaluation engine should help identify effective factors, factor combinations, and strategy families across the full market. The portfolio engine should then validate selected candidates with stricter execution, accounting, costs, risk, and market-rule simulation.

## First Milestone

The first milestone focuses on A-share daily technical factors:

- Read daily bars from `tushare_data.public.stock_daily`.
- Read technical factors from `factors.*` tables produced by `indicators_tushare`.
- Evaluate technical factors and expression strategies across the full A-share market.
- Include rough trading frictions in large-scale screening.
- Validate promising strategies with A-share realistic rules:
  - T+1 sellability
  - price limits
  - suspensions
  - ST/risk-warning handling
  - board-specific rules
  - lot size
  - commission
  - stamp tax
  - transfer fees
  - slippage

## Related Projects

- `quant_ts`: market data download and database loading.
- `indicators_tushare`: technical factor computation and database loading.
- `research-notes`: research ideas, strategy catalog, and factor requirements.
- `strategy-research`: existing event-study prototype and useful reference implementation.

## Design Documents

- [AGENTS.md](AGENTS.md)
- [docs/design/overview.md](docs/design/overview.md)
- [docs/design/architecture_mindmap.md](docs/design/architecture_mindmap.md)
- [docs/modules/module_boundaries.md](docs/modules/module_boundaries.md)
- [docs/modules/ashare_first_market_profile.md](docs/modules/ashare_first_market_profile.md)
- [docs/modules/data_layer.md](docs/modules/data_layer.md)
- [docs/modules/evaluation_layer.md](docs/modules/evaluation_layer.md)
- [docs/modules/portfolio_layer.md](docs/modules/portfolio_layer.md)
- [docs/mvp_plan.md](docs/mvp_plan.md)
- [进度.md](进度.md)

## Report Artifact Checks

Batch and shared-cash backtests write `report_manifest.json` in their output directory. Use it as the stable entry point for downstream scripts instead of parsing Markdown reports.

Newly generated manifests include top-level `"schema_version": 1`. Old manifests without this field remain readable through `qre report-files` and `qre report-audit`.

List selected report files:

```bash
uv run qre report-files outputs/smoke_shared_manifest/report_manifest.json \
  --role window_metrics \
  --window M
```

Audit selected report files for existence and lightweight CSV/JSON structure:

```bash
uv run qre report-audit outputs/smoke_shared_manifest/report_manifest.json \
  --role window_metrics \
  --window M
```

An audit returns exit code `0` only when all matched files exist and pass content validation. Missing files or structural validation issues return exit code `2`.

For expected artifacts, add `--require-match` so the audit also fails when filters match no manifest entries:

```bash
uv run qre report-audit outputs/smoke_batch_rsi2_rolling_audit/report_manifest.json \
  --role rolling_ranked_symbols \
  --group-by board \
  --require-match
```

`report-files` also supports `--require-match` to fail when no manifest entries match the selected filters:

```bash
uv run qre report-files outputs/smoke_shared_manifest/report_manifest.json \
  --role orders \
  --require-match
```

### JSON Output

Both `report-files` and `report-audit` support opt-in `--json` for script-friendly machine-readable output. When `--json` is set, stdout is a single JSON object; stderr behavior and exit codes are preserved.

```bash
# Machine-readable manifest file selection
uv run qre report-files outputs/smoke_shared_manifest/report_manifest.json \
  --role window_metrics \
  --json

# Machine-readable audit summary with issue details
uv run qre report-audit outputs/smoke_shared_manifest/report_manifest.json \
  --role window_metrics \
  --json
```

`report-files --json` emits top-level `schema_version`, `manifest_kind`, `matched_files`, and a `files` array with `key`, `path`, `filename`, `role`, and optional metadata (`symbol`, `window`, `group_by`). `report-audit --json` emits top-level `schema_version`, `manifest_kind`, `matched_files`, `missing_files`, `validation_issues`, `status`, and an `issues` array. `schema_version` is the integer `1` for new manifests and `null` for older manifests that were generated before the field was introduced.

JSON mode can be combined with `--require-match` for strict script gating:

```bash
uv run qre report-files outputs/smoke_shared_manifest/report_manifest.json \
  --role orders \
  --require-match \
  --json

uv run qre report-audit outputs/smoke_batch_rsi2_rolling_audit/report_manifest.json \
  --role rolling_ranked_symbols \
  --group-by board \
  --require-match \
  --json
```
