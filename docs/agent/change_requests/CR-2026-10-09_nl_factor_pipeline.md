# CR-2026-10-09 NL 编译因子名四层防线（MACD signal 编造 bug）

状态：已实现（用户报告的紧急 bug，四层方案用户已批准）

## 问题

NL 输入「日线 MACD(12,26,9)，金叉买死叉卖」→ LLM 凭记忆写
`factors.stock_daily_momentum_close.macd_signal_12_26_9`（库内实为
`macds_12_26_9`）→ 运行报缺因子。根因：LLM 没有真实因子目录。

## 四层方案（全部落地）

1. **治本——真实目录注入 prompt**：`gui/factor_catalog_llm.py` 把 factors schema
   全量列压缩成 prompt 清单（`macd@{12_26_9|6_13_5}` 分组格式，559 列 → 12 行），
   快照落 `configs/factor_catalog_llm.txt`（入仓库，ECS 无库可用）；
   生成脚本 `scripts/gen_factor_catalog_llm.py`（因子库更新后跑一次）；
   `build_system_prompt` 有快照用真实目录 + 硬约束「只可引用清单内表.列」，
   缺失回退旧 indicator catalog 口径。
2. **别名字典**：`configs/factor_aliases.json`（signal/dea→s、hist→h、
   macd_signal→macds 等）；`factor_correction.auto_fix_column` 新增第 0 层
   别名变体命中（归一化后唯一候选才替换，保守原则不变）。
3. **校验+自动修复回路**：`compile_nl` 重构为循环——LLM 输出 → 校验+纠错 →
   缺因子则 `_fixup_prompt`（原始需求+上次 YAML+缺失名与候选）回喂重试，
   最多 `MAX_FIX_RETRIES=2` 次，用户无感；`fix_attempts` 字段透出重试次数。
   YAML 结构错误不回喂（与因子无关）。
4. **兜底报错**：重试耗尽仍缺 → 缺失因子 + 库内相近候选 + 常用清单 +
   「申请新因子」入口指引（`format_unresolved_hint` 补指引行；前端既有
   missing_factors → 申请弹层链路不变）。

## 测试

`tests/test_nl_factor_pipeline.py` +12：压缩分组/目录渲染/快照读写/prompt 注入断言；
别名表加载/变体/macd_signal→macds 精确案例/无歧义不动；回路一轮别名修复不重试/
回喂恢复（第二轮 prompt 含缺失名）/重试耗尽友好报错+入队；fixup 文案格式。
