# Implementation Brief

## Task ID

QRE-SAAS-HELP-COPY-002（Kimi 重做；001 已被用户否决并回退）

## Created By

KIMI_CODE（2026-10-25；用户要求不再交由 Step 5 实施）

## 根因与目标

001 覆盖文案不全，逐节点多通道状态和 refresh 导致提示不稳定，且部署前没有真实浏览器验证。002 改为事件委托 + 单例提示框：桌面每次 mouseover 都 show、mouseout hide；focusin/out 支持键盘；touch/pen pointerup 才 toggle；动态节点无需 refresh。模块标题用 SVG 问号，指标卡整卡用 `data-tip`。

## 实施步骤

1. 新建真实浏览器测试，先证明旧版连续悬停和指标提示缺失；再实现共享组件与样式。
2. 全量处理 new/job/symbol 及其他 SaaS 模板：删除重复说明、模块口径入问号、指标口径入整卡，动态状态/权限/错误/截断/免责保持可见。
3. 指标解释以实际计算口径为准，不改 API、数值、数据库或业务逻辑。
4. 隔离安装浏览器工具，使用本地 staging 既有数据，桌面 1280 与移动 375 实测连续三次悬停、焦点、触摸、正文和溢出。
5. 完成自动化回归、长期文档和静态检查；未经用户明确指令不部署 ECS，不 push，commit 单独批准。

## Validation

- 真实 Chromium：同一目标连续 3 次悬停均有完整正文；指标卡、动态区间卡、focus/Esc/touch/外部点击通过。
- new/job/symbol/profile/showcase 桌面与 375px 无 JS error、无新增横向溢出。
- `uv run python -m pytest tests/test_gui_saas.py tests/test_gui_saas_pages.py tests/test_saas_authing.py tests/test_gui_lab.py tests/test_saas_symbol_ux.py -q` 及全量测试。
- 渲染模板内联脚本 Node 解析；`scripts/check-progress-docs.sh`、`scripts/git-finalize-check.sh`、`git diff --check`。
- 不运行真实全量回测；不得以单元测试代替真实浏览器验收。
