# Implementation Brief

## Task ID

QRE-SAAS-HELP-COPY-001

## Created By

KIMI_CODE + Step 5（2026-10-25；设计经用户确认；Step 5 独立实施，主 Agent 复核）

## 背景与目标

SaaS 全站约 15 个模板存在约 45 处灰色说明。用户要求先盘点再治理：删除重复文案，将模块功能说明移至标题问号，将指标口径移至指标卡悬停；移动端必须可点击访问。权威设计见 `docs/superpowers/specs/2026-10-25-saas-help-copy-design.md`。

## 实施步骤

1. 在共享 `LabUI` 与 `lab-theme.css` 实现统一 help-tip：桌面 hover、键盘 focus、触屏 tap、Esc/外部关闭、边界防溢出、reduced-motion、ARIA 与幂等绑定。
2. 按盘点清单逐页删除或精简重复说明；保留权限、错误、状态、表单约束、空态、截断和免责声明。模块与指标说明分别绑定到标题和整卡，补齐 job/symbol 收益与 FRM 指标口径。
3. 新增组件行为与必要文案保留测试，更新受影响模板断言；不改变 API、业务数据、回测行为和布局。
4. 更新 12 号 UI 规范、06 决策及 04/05/09/10/11 长期文档。先本地验收，不 push、不部署 ECS。

## Validation

- 先运行新增/修改测试确认 RED，再实现至 GREEN。
- `uv run python -m pytest tests/test_gui_saas.py tests/test_gui_saas_pages.py tests/test_saas_authing.py tests/test_gui_lab.py tests/test_saas_symbol_ux.py -q`。
- 渲染相关 Jinja 模板并逐段用 Node 解析内联脚本。
- 本地 staging 桌面及 375px 检查 new/job/symbol/records/showcase 的说明交互与零横滚。
- `bash scripts/check-progress-docs.sh`、`bash scripts/git-finalize-check.sh`、`git diff --check`。
- 不运行真实全量回测；用户验收前不 push。实现提交信息另行出示并获授权。
