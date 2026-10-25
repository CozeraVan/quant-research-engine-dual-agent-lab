# 因子语义注册表与中英文别名设计

日期：2026-10-25
状态：用户已确认统一注册表方向；先评审设计，后续由 Step 5 实施。数据库标准字段不改名。

## 目标

建立单一因子语义来源，使自选因子界面适合中文用户，同时让自然语言中的常见中英文指标名、别名和参数准确映射到真实 canonical `schema.table.column`，不再依赖模型猜测。

## 核心原则

- canonical 仍是数据库、YAML、回测和因子申请的唯一字段标识。
- 展示与解析共用注册表：中文名为主，canonical 作辅助对照。
- 确定性解析优先于 LLM；不把所有别名注入 Prompt，避免 Token 膨胀。
- 价格口径显式保留。同名但未说明口径时默认收盘价并给提示；典型价/均价由用户明确指定。
- 无法唯一消歧时给候选，不自动错配。

## 注册表

新增版本化 `configs/factor_registry.json` 与只读加载层 `gui/factor_registry.py`。

每个因子条目包含：`table`、`column`、`zh`、`price_basis`、`family`、`params`、`output`、`aliases`、`common`。另设 `market_fields` 描述 open/high/low/close/pre_close/vol/amount 等行情字段及中文别名；表级信息描述类别和价格口径。

采用“规则生成 + 特殊条目人工维护”：MACD/EMA/RSI 等族与参数可生成中文名，特殊财务、Alpha 和中文习惯名人工补充；别名优先覆盖常用指标。未维护条目回退 canonical 并进入覆盖报告，不伪造中文翻译。

加载层统一别名归一化：英文小写、全角转半角、去除空格/下划线/连字符和中文标点；建立 normalized alias → canonical 候选列表。

## 自然语言解析

解析顺序：

1. 完整 canonical 精确命中。
2. 归一化别名唯一命中。
3. family + params 结构化匹配，如 MACD(12,26,9)、20 日 EMA。
4. 同名多候选：未说明价格口径时按 close → typical_price → average_price 选择并输出提示；其他歧义返回候选。

MACD 用 `output` 区分 DIF（macd）、DEA/信号线（macds）、柱（macdh）；金叉使用 DIF 上穿 DEA。未给 MACD 参数时默认 12,26,9 并提示。行情字段由 `market_fields` 单独识别，不混入 `factor_fields`。

完整别名在编译前后由程序解析，LLM Prompt 只保留 canonical 目录和少量常用示例。注册表精确别名取代现有子串替换的优先级；旧 `factor_aliases.json` 暂时作为兼容兜底，后续删除。`COMMON_FACTOR_TARGETS` 改由注册表派生，消除手写漂移。

## 自选因子与 metadata

`sync_saas_metadata.py` 在现有 item 上增量输出 `zh`、`canonical`、`price_basis`、`aliases`，`/api/saas/factors` 不变。旧数据缺字段时前端回退现有 label。

弹窗按钮、三栏和搜索结果以中文名为主，显示必要的价格口径；辅助文本保留 canonical。搜索匹配中文名、canonical、全部别名和族名。隐藏 select、YAML、条件快照、固定值和策略还原契约不变。

## 同步与防漂移

- `gen_factor_catalog_llm.py` 与 `sync_saas_metadata.py` 共用注册表，继续走现有 ECS 文件同步流程。
- 新增校验：注册表 canonical 必须存在于目录快照；别名不得指向不存在字段；重复别名必须形成候选而非静默覆盖；新增字段未注册时输出覆盖告警。
- 校验接入测试与因子入库流程。旧目录和 YAML 完全兼容，不迁移数据库。

## 实施阶段

1. 注册表、加载/归一化/校验、常用字段与别名数据。
2. metadata 与自选因子中文展示和中英文搜索。
3. NL 确定性解析、提示与兼容纠错，ECS 目录同步。
4. 单元/集成回归、真实浏览器、NL 小样本编译验证；先做小样本，不运行全量回测。

## 验收

- 中文用户能识别并搜索常见指标，canonical 可对照；同名字段口径可见。
- MACD 快慢线/柱、DEA/信号线、中文别名和常见周期能准确映射。
- 同名未指定口径默认 close 并提示；其他歧义返回候选。
- 旧 YAML、弹窗值、快照和策略还原不回归；新增字段漏注册会被校验发现。
- 不增加全量别名 Prompt 开销，不改变 canonical 和回测结果。
