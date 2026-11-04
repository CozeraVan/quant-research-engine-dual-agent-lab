# 38 · Windows UI Agent 任务书：个人中心改版

- 日期：2026-11-04
- 分派方：主 Agent（Kimi，WSL）；执行方：Windows UI Agent
- 前置：登录系统已自建并移除 Authing；会员接口 `GET /api/saas/membership` 可用
- 性质：**纯 UI/UX + 前端交互**。不改 Python 后端、不部署、不 push master
- 分支：`ui/profile-center`（基于最新 master；**等 DeepSeek 的个人中心轮询 bug 修复合并后再开工**，避免 profile.html 冲突）

## 0. 路径与边界

工作根 `D:\workzone\webui`，只动：
- `src/quant_research_engine/gui/saas/templates/`（重点 `profile.html`、`base.html`）
- `src/quant_research_engine/gui/static/`（CSS/JS）

预览 `scripts/win/start-ui-preview.ps1` → http://127.0.0.1:8091/saas/；验收 `scripts/win/ui-smoke.py` 双视口零 JS 错误零横向溢出。

## 1. 需求（用户原话拆解）

### T1 顶部 header 改造
- 顶栏的「个人信息」改名为 **「个人中心」**
- 点击「个人中心」不再是直接跳页，而是**下拉菜单**
- **「退出登录」按钮移到下拉菜单最下方**（不再裸露在顶栏）
- 下拉菜单项即个人中心子页面入口（见 T2）

### T2 个人中心 = 下拉菜单 + 子页面结构
- 子页面/区块分为：**个人信息**、**回测策略库**
- 进入个人中心后，用**左侧边栏**导航（格式复用「使用说明」页的侧边栏样式），右侧为内容区
- 移动端侧边栏折叠为顶部 tab 或汉堡菜单

### T3 会员权益对比表移除
- **删除「会员权益对比」div**（当前 profile 页那张 tier 对比表）
- 代码不要物理删除到不可恢复：可整体注释或移到独立片段模板，**未来付费页面会复用**
- 把 **「个人信息」（账号资料）+「当前权限」（tier、配额、跟踪上限等）** 放进「个人信息」子页面
- 权限数据优先用 `GET /api/saas/membership`（含 tier_label、daily_full、watches、scan_enabled），不要硬编码

### T4 三个列表进入个人中心子页面，固定高度 + 分页
按此顺序排进个人中心子页面（侧边栏导航项）：
1. **我的策略库**
2. **回测记录**
3. **我的分享**

要求：
- 每个列表 div **固定高度**（统一高度，不随条目数撑长页面）
- 条目超出固定高度时**分页管理**（页码/上一页下一页），不要出现整页无限滚动
- 空态、加载态、失败态沿用现有样式规范

### T5 整体风格
- 沿用白底磨砂玻璃卡、统一小卡（白底紫框）、大字号宽间距规范
- 侧边栏样式与「使用说明」页一致（同色系、同圆角、同激活态）
- 不做夜间模式入口

## 2. 交付

1. 在 `ui/profile-center` 分支 commit 并 push（**不 push master**）
2. `ui-smoke.py` 全绿 + 个人中心各子页面双视口截图（`.tmp/ui-review/`）
3. 回传：改动文件清单、截图路径、需要后端配合的接口清单（如有）
4. 主 Agent 复核 → 合并 master → 统一部署 ECS
