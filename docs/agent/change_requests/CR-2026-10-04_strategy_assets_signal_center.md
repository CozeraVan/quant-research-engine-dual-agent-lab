# CR-2026-10-04 策略资产化 + 策略信号监控

状态：已获用户批准设计（2026-10-04 brainstorming 四项决策对齐）
来源：用户提出「我的策略库卡片意义不明」+「以策略为基准的选股池/信号推送（未来付费主模式）」

## 决策记录（用户已选）

1. 策略库形态：**策略详情页型**（非行内操作型）。
2. 再编辑交互：按策略的创建入口还原编辑态（NL→原文本框；向导→结构化条件；YAML→代码编辑器）。
   用户明确：一般不会跨入口改同一策略。
3. 信号推送渠道一期：**站内信号中心**（header 未读红点；预留 channel 字段，邮件/微信后置）。
4. 扫描范围：**跟随策略**——默认「最近回测范围」（如实测 500 只随机股），可切换板块/全A/自定义列表。
5. 开放范围：内测全员开放；`tier_policies.scan_enabled` 开关预留付费收窄能力。

## 模块一：策略库 → 策略资产

### 数据层

`strategies` 表新增（懒自愈 ALTER 模式，cloud_schema.sql 同步）：

- `entry_mode` TEXT：nl / wizard / yaml；存量推断（nl_text 非空→nl，否则→yaml）
- `wizard_state` JSONB：向导结构化条件快照（入场/出场条件组、风控参数），
  仅 wizard 入口写入；存量 wizard 策略无快照则降级 YAML 入口再编辑

保存接口 `POST /api/saas/strategies` 与 job 提交时的策略 upsert 均接收并落 `entry_mode`/`wizard_state`。
前端三入口在保存/提交时上报自己的模式与（向导的）状态快照。

### 页面层

- 个人信息页策略库列表：每行 = 名称 + 入口标签（自然语言/自选因子/策略代码）+ 回测次数 +
  最近使用 + 进入详情；保留现有重命名/删除。
- 新页面 `/saas/strategies/<id>`：
  1. **源文件卡**：按 entry_mode 还原对应编辑态
     - nl：原始自然语言大文本框（可改，改动后需重新编译生成 YAML）
     - wizard：恢复快照的条件组 UI（只读还原 + 跳转新建页编辑）
     - yaml：YAML 代码编辑器
  2. **历史回测列表**：该策略全部 job（状态/区间/标的数/收益率/超额，跳结果页）
  3. **操作区**：保存修改（同名 upsert）、另存为新策略、载入复测
     （跳 `/saas/new?strategy=<id>` 预填，用户换标的/区间直接跑——回填机制已存在）
  4. **信号监控卡**（模块二入口）

## 模块二：策略信号监控（站内信号中心）

### 数据层（新表，懒自愈 + cloud_schema.sql）

- `strategy_watches`：id, strategy_id FK, user_id, scope_type
  （last_run_universe / sector / all_a / custom）, scope_payload JSONB
  （板块名或股票列表；last_run_universe 存最近一次 job 的实际标的列表快照）,
  enabled BOOL, created_at, updated_at
- `signal_events`：id, watch_id FK, trade_date DATE, ts_code TEXT,
  signal_type TEXT（entry/exit）, price NUMERIC（收盘参考价）, created_at；
  UNIQUE(watch_id, trade_date, ts_code, signal_type) 防重
- `users.signals_last_read_at` TIMESTAMPTZ（未读红点）
- `tier_policies.scan_enabled` BOOL 默认 true（未来付费收窄）

### 链路（复用现有架构，零新端口、零公网入站）

1. 本机每日数据刷新管线（qre-refresh.timer）完成后，追加触发
   `deploy/saas/signal_scan.py`（或 refresh 脚本尾钩）：
   - GET ECS `/api/worker/watches`（X-Worker-Token）：拉全部 enabled watch + 策略 yaml
   - 按 scope 解析股票池；用本地因子库计算最新交易日 entry/exit 信号
     （表达式求值复用引擎 evaluation.signals 同一套 AST 白名单求值器，不引入新逻辑）
   - POST `/api/worker/signals` 批量回传（幂等，唯一约束兜底重跑安全）
2. ECS 页面「信号中心」`/saas/signals`：按日期/策略/信号类型/股票筛选，
   分页表格；header 红点 = 存在 signals_last_read_at 之后的 signal_events
   （归属该用户的 watch）。进入页面即更新 last_read。
3. 策略详情页「信号监控卡」：开关 + 范围选择（默认最近回测范围快照，
   按钮切换板块/全A/自定义）+ 最近 7 日信号数预览。

### 权限与配额

- 全接口要求登录；`scan_enabled` 读 tier_policies（内测期全 true）。
- 每用户 watch 上限暂 20（防滥用，tier_policies 加 max_watches 可调）。
- 扫描脚本单线程跑在数据刷新后，因子已预计算，5000 股 × 数十策略量级分钟级可完成；
  失败记日志不影响次日（幂等重跑）。

### 明确不做（本期）

- 邮件/微信/短信推送（预留 channel 设计）
- 分时盘中实时信号（等分时数据源落地）
- 变体/版本管理体系
- 信号→自动交易

## 测试要点

- strategies 新列：保存/回填/存量推断/向导快照往返
- watches CRUD + 上限 + 权限（他人策略 404）
- 扫描脚本：假数据小池信号计算正确性、幂等重跑、空信号
- 信号中心：筛选/分页/未读红点/last_read 更新
- `-k saas` 全绿基线 208

## 风险

- 存量 wizard 策略无快照 → 降级 YAML 编辑（UI 明示）
- 扫描耗时随 watch 数增长 → 先单线程+上限，超阈值再优化
- 信号口径 = 日线收盘后 T+1 参考，不构成投资建议（页面加免责）
