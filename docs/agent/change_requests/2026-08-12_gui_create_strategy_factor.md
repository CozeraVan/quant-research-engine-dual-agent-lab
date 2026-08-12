# Change Request: GUI 新增策略/因子（手写 + DeepSeek LLM 生成）

- 日期：2026-08-12
- 提出人：用户（Product Owner）
- 状态：已批准（计划经 ExitPlanMode 审批通过）
- 关联：`docs/agent/08_IMPLEMENTATION_BRIEF.md`

## 需求

QRE GUI 的新增交易策略与新增交易因子板块，支持：

1. 用户手写（YAML / Python 因子代码）。
2. 调用 DeepSeek API（OpenAI 兼容协议）自动生成符合本系统规范的代码，
   实现新策略的回测与新因子的计算入库。

## 硬性要求（用户明确）

1. **先查重**：生成/创建前先检查数据库中是否已存在同名策略或同列因子。
2. **沙箱先行**：新增物不立即加入日更或全量测试；先在测试文件夹生成临时
   代码做小范围单股票冒烟测试；语法无错、回测结果正常输出后，才进行全量
   回测，并默认将新策略加入 dashboard。

## 设计要点（摘自已批准计划）

- 骨架：查重 → 沙箱（outputs/sandbox/ 与 indicators_tushare/sandbox/）→
  单股冒烟 → 用户确认晋升 → 全量回测/因子入库 → dashboard 可见。
- LLM 配置：QRE `.env` 增加 `QRE_NL_LLM_BASE_URL=https://api.deepseek.com`、
  `QRE_NL_LLM_API_KEY`（用户提供）、`QRE_NL_LLM_MODEL=deepseek-v4-flash`。
- 策略 NL 通道复用现有 `gui/nl_compiler.py`（OpenAI 兼容，DeepSeek 即配即用）。
- 因子 LLM 生成第一版仅支持模板型指标（FactorBase 子类，pandas_ta 已有函数，
  单序列/HLC 输入）；复杂自定义逻辑走人工通道。
- 安全闸：LLM 生成物一律"草稿 → 用户确认 → 沙箱 → 再确认晋升"，不自动执行。
- 跨项目写权限仅限：indicators `sandbox/`、`factors/<name>_factor.py` 新文件、
  `config/factors.yaml` 追加。QRE 对业务 DB 只读红线不变。

## 验收标准

1. GUI 手写 YAML → 沙箱冒烟 → 晋升 → dashboard 策略 tab 可见。
2. GUI NL 描述（DeepSeek）→ 策略 YAML 草稿 → 同上闭环。
3. GUI NL/手写 → 因子冒烟 → 晋升 → factors.yaml 有条目、backfill 成功、
   因子 tab 对账绿。
4. 重名策略/已存在因子被正确拦截。
5. 测试全绿，文档同步。
