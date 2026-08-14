# Review Report

## Task ID

QRE-EVAL-ALPHA191-001 (Alpha191 赚钱效应评估管线 + GUI 路径 C 登记)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- 逐条对齐任务书：CLI 参数齐全（--start/--end/--factors/--top/--output，另加
  --batch-size/--db-url 两个无害扩展）；默认近 2 年；分批 10 因子取数批后
  del+gc；leaderboard 列与排序（|mean_rank_ic| 降序）符合规格。
- 引擎/catalog/assembler 零改动：alpha191 表走既有 FactorFieldRequest
  三段式寻址，无需 factors.yaml 纳管适配（任务书预警的装配坑不存在）。
- 口径选择均有出处并在 docstring 注明：signal_expression="close > 0" 占位
  （本评估不看事件流）；quantile=1 最低组/5 最高组（引擎 qcut 语义），
  top_minus_bottom=Q5−Q1 与 rank IC 同号为方向一致；ICIR 用与引擎同公式的
  日频 rank IC 重算 std（引擎只输出均值/胜率）。
- 偏离（已登记）：①★ 胜率采用方向一致率（负 IC 因子取 1−正向占比），对
  任务书字面「胜率≥0.55」的解释性扩展；②用户指定冒烟窗口 2025-08-01~
  2026-08-13 因回填仅完成 2010→2013+日更当日而无因子数据，改用已覆盖窗口
  2012-08-01~2013-08-13 验证（3 因子 234 交易日，alpha001/alpha006 ★）。
- 测试：`uv run pytest tests/ -x -q` → 1398 passed（6 净增：合成面板端到端
  正 IC/★、排序、日频 IC、失败行、CLI mock 写 CSV、参数校验）。
- 上游发现（不属本任务范围，未处理）：alpha006 回填段逐日仅 ~3 个 distinct
  值 → qcut 分层塌陷、top_minus_bottom NaN 为正确表象；建议 indicators 侧
  核查 alpha006 公式。
- GUI 改动为纯文案（h2 + 路径 C 一条），无 JS/路由变更；无测试断言引用旧
  文案（grep 确认）。

## Required Fixes

无。

---

# Review Report (archive: QRE-GUI-UIUX-001, GUI 全站 UI/UX 优化：Data-Dense Dashboard 浅色风格)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- 方案逐条对齐用户指定设计变量：:root 集中定义 --bg/--card/--border/--text/
  --muted/--primary/--primary-hover/--ok/--warn/--err，全站引用，无散落硬编码
  hex（admin.html 三处内联 #a80 已替换为 .health-yellow）。
- 按钮分级落实：每屏/卡片唯一 primary（运行回测 / 生成代码 / 对比 / 放大全范围），
  次要操作 .btn-ghost，危险操作 .btn-danger-outline 描边红无实底。
- 约束遵守：所有元素 id、JS 事件绑定、API、表单字段、中文文案未动；
  「引擎输出，非投资建议」提示保留；health-*/.ok/.err 类名不变仅换色值。
- 验证：`uv run pytest tests/ -x -q` 1391 passed 全绿（无断言改动）；
  临时实例 curl / 与 /admin 均 200 且含新 class；进程已杀、端口已释放。
- 无 Required Fixes。

## Required Fixes

无。

# Review Report (archive: QRE-GUI-HOME-REFACTOR-001, GUI 首页三 tab → 两 tab 重构)

## Task ID

QRE-GUI-HOME-REFACTOR-001 (GUI 首页三 tab → 两 tab 重构)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- 结构与用户批准方案逐条对齐：两 tab、三段垂直流、路径 A/B、fc-create 迁入、
  admin 留跳转链接、tab-builder 与 b-* JS 全删、/api/builder/* 与 app.py 未动。
- 元素 ID 全部保留（wz-*/nl-*/param-*/fc-*/sandbox-*），JS 逻辑逐段平移，
  仅两处行为改动（均为方案要求）：wz-fill-editor 同页填入 + 滚动；NL 缺因子
  跳「新增因子」tab 路径 A 预填。rerun_yaml 回填改同页滚动。
- 自审修复点：①fc JS 迁入时 pollFcJob 原调用 admin 专属的 loadFactorStatus()，
  已移除该调用（loadFcSandbox 保留）；②高级参数区用既有 section-toggle/collapsed
  机制实现默认折叠，无需新 CSS；③node --check 双模板内联 JS 通过。
- 测试 1391 绿；存在性断言已更新为新结构（两 tab、fc-create 在首页、admin 无
  fc-create、tab-builder 不存在）。无真实回测/backfill 执行（standing instruction）。

## Behavior Verified

见 09_CODING_HANDOFF.md 顶部 Validation Output（临时 GUI curl 抽查）。

# Review Report (archive)

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
