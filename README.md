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

### Run Identity Linkage

Durable output commands accept an optional `--run-id` to link artifacts across preflight, evaluation, and portfolio runs. The identifier is stored as a string (or `null`) in JSON outputs and run manifests. It does not enable cross-command orchestration; it is metadata that helps scripts and audits correlate files later.

Supported commands:

```bash
# Preflight with run identity
uv run qre preflight strategy.yaml --output-json result.json --run-id research-run-42

# Evaluation with run identity
uv run qre eval-config strategy.yaml --output-dir outputs/eval --run-id research-run-42

# Portfolio backtests with run identity
uv run qre backtest-single strategy.yaml --output-dir outputs/single --run-id research-run-42
uv run qre backtest-batch strategy.yaml --output-dir outputs/batch --run-id research-run-42
uv run qre backtest-shared strategy.yaml --output-dir outputs/shared --run-id research-run-42
```

Where `run_id` is written:

| Command | Output |
|---|---|
| `qre preflight --output-json` | top-level `"run_id"` in the JSON file |
| `qre eval-config --output-dir` | `"run_id"` in `run_manifest.json` |
| `qre backtest-* --output-dir` | `"run_id"` in `run_manifest.json` |

When `--run-id` is omitted, `run_id` is stored as `null`. No run ID defaults to a timestamp, environment value, or generated string.

### Run Manifest Audit

`qre report-audit` can validate `run_manifest.json` content through `--role run_manifest`. This checks required fields, types, and supported kinds beyond basic JSON parseability.

```bash
# Audit a specific run manifest
uv run qre report-audit outputs/eval/report_manifest.json --role run_manifest

# Machine-readable run-manifest audit
uv run qre report-audit outputs/eval/report_manifest.json --role run_manifest --json
```

Validated run-manifest fields:

| Field | Required type | Nullable |
|---|---|---|
| `schema_version` | integer `1` | no |
| `kind` | string | no |
| `run_id` | string | yes |
| `command` | string | no |
| `strategy_path` | string | no |
| `artifacts` | list of strings | no |

Supported run-manifest kinds:

- `evaluation_run_manifest`
- `portfolio_backtest_run_manifest`

Missing fields produce audit issues with code `missing_run_manifest_field`. Type errors and present-null non-nullable fields produce `invalid_run_manifest_field`. Run-manifest validation exit codes follow the same `0`/`2` convention as other audit roles.

This audit validates artifact structure only. It does not assess factor effectiveness, strategy quality, or benchmark-relative performance.
