# Implementation Brief

## Task ID

QRE-SAAS-RESULT-CONTRACT-001（P0-1B 结果合同版本、口径标签与旧结果隔离）

## Created By

KIMI_CODE 布置，Step 5 实施（2026-10-25，用户批准按统一 Todo 推进）

## 背景

P0-1A 已排除 worker price_basis 错误：实际进程 QRE_PRICE_BASIS=raw，job74 订单为原始价，无需重跑。剩余风险是收益口径并存、历史结果未验证、经典策略展示边界不清。不得大规模回填或重跑历史任务。

## 目标与边界

1. 为新结果增加显式 `result_contract` 元数据：合同版本、数据快照（data_until）、收益曲线口径（日收益累乘）与总收益口径（初始资金加权）及验证状态。新结果标为当前版本。
2. 回测详情用简短可见标签和现有 data-tip 解释两种指标，不再让曲线与总收益看似矛盾；保持现有数值不变。
3. 历史结果不删除、不重跑，按合同版本标为“旧口径/未验证”。已人工修正的 58/66 可作为 verified 例外；74 未经收益口径修正，不得因 price_basis 核查通过就标为已验证。
4. 经典策略公开展示只允许 verified；未验证项仅取消公开可见，不删除白名单、任务或产物。私人历史结果仍归本人可见并带标签。
5. 不改回测引擎、历史收益值、权限语义或 worker；不运行真实全量回测，不 commit/push/部署，待主 Agent 与用户验收后决定。

## Implementation Guidance

- 优先在结果汇总/worker 回传层注入合同元数据，API 增量返回，避免大范围数据库迁移。历史分类必须由显式版本映射/例外表决定，不能靠当前日期动态猜测。
- 版本和例外规则写代码常量与文档，禁止“当前时间之后自动变旧”的逻辑。
- 前端标签复用现有 badge/data-tip；页面摘要、曲线提示和经典策略说明保持一致。

## Validation

- TDD：新结果合同字段、历史分类、58/66 verified 例外、74 未验证、showcase 过滤、私人结果仍按原权限可见、两种收益口径提示。
- 相关 SaaS 与全量回归；真实 Chromium 桌面/移动检查标签、提示和经典策略展示，不创建回测。
- 更新 04/05/06/09/10/11/14 与必要的 16/17 文档；详细报告和浏览器证据存 `.tmp/result-contract/`。
- 最后运行 `scripts/check-progress-docs.sh`、`scripts/git-finalize-check.sh`、`git diff --check`。

## 实施记录（2026-10-25 Kimi，未 commit/push/ECS）

**新增单一权威模块** `src/quant_research_engine/gui/saas/result_contract.py`：
`RESULT_CONTRACT_VERSION="2026-10-25.1"`、两种收益口径文案
（`DAILY_RETURN_BASIS` 日收益累乘 / `TOTAL_RETURN_BASIS` 初始资金加权总收益）、
验证状态枚举、**显式例外表** `LEGACY_RESULT_CONTRACTS`（58/66→verified 附复核依据，
74→unverified）、默认未验证，以及 `build_result_contract` / `resolve_result_contract` /
`is_verified` / `contract_view`。分类入参只有 job_id 与已存合同，**无任何时间参数**
（测试用 `inspect.signature` 锁死），不存在「当前时间之后自动变旧」。

**注入点**（不改 worker / 引擎）：`app.py` 的 `api_result_meta` 与
`api_report_result_legacy` 在写入 results 时附带 `result_contract`
（`_ensure_result_contract_column` 先查 information_schema 再幂等 ALTER；
ALTER 失败降级为不写该列、读取侧按例外表解析——缺列方向安全，永不误放行 verified）。
`cloud_schema.sql` 加 `results.result_contract JSONB` + 老库幂等 ALTER。

**API 增量**：`/api/results/<id>/summary`、`/api/results`、`/api/saas/showcase`、
`/api/saas/console/showcase` 均只增 `result_contract` 字段，原有字段与数值不变。

**公开展示**：`/api/saas/showcase` 与 showcase 公开只读通道（`_load_job_public`）只放行
verified；未验证项从公开可见消失，但 `showcase` 白名单行、job、产物一律不动，
所有者本人仍按原权限可见（他人/匿名得到与未挂白名单相同的 404/401）。

**前端**（复用现有 badge + `data-tip`，无新色相/新 CSS）：`job.html` 结果区合同徽标
（已验证口径=绿 / 旧口径·未验证=红）+ 合同版本与数据截止附注 + 两种口径 tip；
`showcase.html` 页头与每行已验证徽标和口径说明；`_records_scripts.html`
（工作台/个人信息共用）已完成行追加合同标签。

**验证**：`tests/test_saas_result_contract.py` 21 例（先 RED 后 GREEN）+
`tests/test_gui_saas_pages.py` +2 例 JS harness；相关套件 180 passed + 1 skipped；
全量 `pytest tests/ --ignore=tests/data_test` → **2559 passed + 5 skipped**（基线 2536+5）。
真实 Chromium 桌面 1280 / 移动 375 各 3 页通过（showcase 只列 verified、74 不公开、
徽标与口径提示可见、零 JS error、零横向溢出），证据 `.tmp/result-contract/`
（report.md / browser-evidence.json / 6 张截图 / seed.py / browser_audit.py）。
详细报告：`.tmp/result-contract/report.md`。
