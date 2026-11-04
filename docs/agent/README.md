# QRE 文档与模块索引

本文件是长期文档的唯一入口。当前状态优先于历史记录；历史文档保留原文，不与现行合同混用。

## 当前权威文档

| 主题 | 入口 |
|---|---|
| 当前状态与交接 | `11_AGENT_STATE.md`、`30_WEEKLY_HANDOFF_2026-11-03.md` |
| 产品与约束 | `00_PRODUCT_VISION.md`、`02_LOCKED_REQUIREMENTS.md`、`14_LAUNCH_ROADMAP.md` |
| 开发闭环 | `04_TASK_HANDOFF.md`、`05_PROGRESS.md`、`08_IMPLEMENTATION_BRIEF.md`、`09_CODING_HANDOFF.md`、`10_REVIEW_REPORT.md` |
| UI 与 K 线 | `12_UI_STYLE_GUIDE.md`、`23_KLINE_IMPLEMENTATION.md`、`33_WINDOWS_UI_AGENT_GUIDE.md` |
| 数据与因子 | `20_DATA_DICTIONARY_DAILY_MINUTE.md`、`21_FACTOR_LIBRARY_PLAN.md` |
| 回测指标与容量 | `24_PERF_METRICS_CONTRACT.md`、`27_STRESS_TEST_2026-11-02.md`、`31_RESOURCE_MODEL_2026-11-03.md`、`35_CAPACITY_MODEL_2026-11-03.md` |
| 经典策略 | `34_CLASSIC_CATALOG_PUBLIC_SMOKE_2026-11-03.md`、`36_CLASSIC_FULLSCALE_AUTO_RUNBOOK_2026-11-03.md`、`classic_catalog/` |
| 部署与上云 | `16_ECS_DEPLOYMENT.md`、`28_CLOUD_MIGRATION_RUNBOOK_2026-11-02.md`、`32_CLOUD_FULLSTACK_PREP_2026-11-03.md` |
| 用户与商业化 | `15_SAAS_SYSTEMS_DESIGN.md`、`18_AUTH_MEMBERSHIP_DESIGN.md`、`19_MONETIZATION_MATRIX.md` |

## 模块边界

- **主线引擎**：`src/quant_research_engine/` 中除 `gui/`、`game/` 外的计算、数据、策略与 worker；测试在 `tests/`，运行产物只在 `outputs/` 或 `.tmp/`。
- **Web UI**：`src/quant_research_engine/gui/`；因 Flask 打包与模板加载依赖保留在 Python 包内，不在运行期间物理迁移。Windows 只通过独立 clone 修改此边界。
- **游戏**：`src/quant_research_engine/game/`，文档为 `22_TRADING_GAME.md`，不属于主线回测。
- **短视频辅助**：`docs/auxiliary/video/`；只保存演示输入与视频制作资料，不是回测执行合同。
- **研究资料**：`docs/frm/` 的 PDF 是外部参考资料，不是缓存，不能按临时文件删除。

## 历史归档

- `archive/tradingview/`：已收官的 TradingView 任务书、回传与最终报告。正文中的旧路径保留作历史记录，实际文件以本目录为准。
- `change_requests/`：变更的历史审计记录；是否仍有效以当前状态文档为准。
- `../legacy/`：双 Agent 时代及更早资料，不参与当前开发决策。

## 清理纪律

可删除：`.pytest_cache/`、`__pycache__/`、`.pyc`、IDE 缓存。不可按缓存删除：虚拟环境、Playwright 浏览器、TV 验收证据、测试数据、回测产物和参考 PDF。CF 队列运行期间不得移动 `scripts/classic_catalog/`、`.tmp/classic-catalog-fullscale/` 或 worker 文件。
