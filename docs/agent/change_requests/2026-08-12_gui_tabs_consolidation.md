# Change Request: GUI 首页合并为「新增策略」「新增因子」两选项卡

- 日期：2026-08-12
- 提出人：用户（Product Owner）
- 状态：已批准（ExitPlanMode 审批通过）

## 需求

现有三个子选项卡（因子向导 / 策略构建器 / YAML 编辑器）功能重复、流程割裂，
合并为两个选项卡：

1. **新增策略**：三段垂直流——
   - 顶部：自然语言描述框（DeepSeek 生成 YAML，填入底部预览栏）；
   - 中部：可视化自编辑（选因子、设入出场条件、测试范围），同样生成 YAML
     到底部预览栏（两种方式任选其一）；
   - 底部：可编辑 YAML 预览栏 → 小范围测试 → 通过后用户指定区间测试。
2. **新增因子**：两条路径指引明确——
   - 路径 A：已有指标新增周期/价格源（原向导 step3）；
   - 路径 B：全新指标 NL/手写生成（原 admin 的 fc-create 闭环整体移入）。

## 要点

- 删除 Builder tab（高层 DSL 表单，功能被可视化构建区覆盖）；
  后端 `/api/builder/*` 保留不删。
- admin.html 因子 tab 的 fc-create 子区移除，留跳转链接。
- 后端 API 零新增，全部复用。
- 详见 docs/agent/08_IMPLEMENTATION_BRIEF.md。
