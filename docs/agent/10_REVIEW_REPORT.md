# Review Report

## Task ID

QRE-ADMIN-STRAT-INCREMENTAL-FIX-001 (策略状态 tab 增量结果合并)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- 合并语义符合确诊结论：增量只在 mtime 更新时接管新鲜字段；全量指标永不取增量
  （增量 summary_metrics 本就无这些键，merged 时显式附 full_metrics_as_of 防伪）。
- 自审修复点：①缓存键初版不含增量根会串键，已纳入（clear_strategy_result_cache
  同步）；②app.py 下载路由白名单原仅 backtests，增量 artifact_dir 会被 400，
  已扩双根；③增量源无 date_start，admin.html 区间列与 detail 页均做容错显示。
- 向后兼容：原返回键（metrics/source_file/artifact_dir/mtime）语义不变，
  仅批次存在时行为与旧版一致（source="batch"）；旧 13 条 strat_tab 测试未改仍绿。
- 测试 7 条新用例（仅增量/merged/批次更新/缺 watermark/缓存隔离/overview 行），
  全量 1391 绿。state.json 整读约 1MB 仅取 watermark，equity_curve.csv 不读。

## Behavior Verified

见 09_CODING_HANDOFF.md 顶部 Validation Output（真实 mr03a：date_end=2026-08-11
增量 + full_metrics_as_of=2026-07-27，source=merged）。

# Review Report (archive)

## Task ID

QRE-GUI-FACTOR-CREATE-P2-001 (GUI 新因子创建闭环 P2)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- 安全闸链完整：nl-generate 只回填不执行；check/smoke/promote 三关各自独立；
  promote 有 pgrep 时机闸 + 目标文件存在闸 + 二次 AST 检查 + 写失败回滚。
- 自审修复点：①AST dunder 初版全禁误伤 `super().__init__`，改 12 项逃逸通道黑名单；
  ②白名单初版漏了必需的 `core.factor_base` from-import；③pgrep -f 会匹配
  调用方 shell 的命令行造成自匹配误报，过滤含 "pgrep" 的行；④查重初版只查
  参数交集，真实 E2E 中 roc（已注册 params [null]）漏网——加"同名指标一律拒绝
  并引导 factor-admin 通道"规则（registry 按 indicator_name 去重，重复类互覆）。
- 测试 42 条注入式 + Flask client；全量 1385 绿。不真连 DB、不真跑 backfill。
- 真实 E2E（真实 DeepSeek + 真实 DB + 真实 GUI server）：vidya 生成 → 查重过 →
  冒烟过（600519.SH 400 行 vidya_20）→ 晋升 job 20260812T030850074330 起成功
  （validate→backfill --categories overlap --execute，后台）。backfill 前核实
  `plan --baseline-ref HEAD --categories overlap` = noop 且无 admin 任务在跑，
  故 backfill 范围严格只有 vidya_20 一列。

## Behavior Verified

见 09_CODING_HANDOFF.md 顶部 Validation Output 与真实 E2E 段。

# Review Report (archive)

## Task ID

QRE-REPORT-CN-001 (report layer: localization, strategy intro, blank filling, 2dp)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- All four user requirements verified on the final full-market run (batch `133a95e11050`): Chinese labels throughout xlsx/HTML; strategy intro block at report top (entry/exit/holding/stops/universe/execution); previously-blank fields filled (strategy_name, strategy_id, strategy_family, 开始日期 2010-01-04, 结束日期 2026-07-24, 股票数量, 交易笔数); 0.00/0.00% cell formats; NaN→`-`.
- Self-review catch fixed: Performance-sheet dates were still blank after the subagent pass (engine summary doesn't carry them) — added run_request backfill in both batch and shared branches, re-verified filled on the final run.
- Contract discipline: sheet names, file names, CSV headers and CSV values unchanged (machine contracts); localization/formatting confined to xlsx cell layer and HTML strings. Full suite 1160 green (19 new localization tests).
- Metadata composition is honest about gaps: `industry_group` stays `-`/unknown until upstream populates `reference.stock_basic`; board from ts_code derivation; cap/liquidity buckets from daily_basic.
- matplotlib chart text stays English (no guaranteed CJK font in environment — documented limitation, charts are auxiliary).
- `sharpe` is formatted as a ratio (0.00%) per the token list — flagged by the implementer; semantically not a percentage but display is consistent (0.00% of a Sharpe value still reads fine at 2dp; noted for user review).

## Behavior Verified

- Final run: 2/2 OK (pt02b 1899s, cb01b 2067s), trades pt02b 1,835 / cb01b 2,027 (latest week included, watermark 2026-07-24); universe correctly drops 4,079 post-2009-09 IPOs + 35 suspended.
- `qre report-audit` → 0 issues; `scripts/check-progress-docs.sh` → passed; `git diff --check` → clean (re-run before commit).
- 1160 tests green.

## Residual Risks

- None material for the report layer. Follow-ups noted: chart-text localization needs a CJK font check; industry_group depends on upstream stock_basic population.

## Next Step

Phase → `AWAITING_GIT_APPROVAL`. Proposed commit message presented to the user; commit only after explicit approval.
