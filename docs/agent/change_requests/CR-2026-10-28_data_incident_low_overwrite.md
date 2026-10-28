# CR-2026-10-28 数据事故：stock_daily.low 全市场误覆盖与恢复

> 这是一次**由主 Agent 操作失误造成的事故**记录。保留全文作为纪律教训，
> 不是因为结果好，而是因为过程和教训必须可复查。

## 事故

任务：清洗 26 只 `920xxx.BJ`（新三板-era）的上游坏 tick，共 79 行
（`low < 0.2×close`）。用户已批准（「都做，请先开始修这个bug」）。

执行的 SQL：

```sql
-- 错误：漏掉了起限定作用的 low < 0.2*close 守卫
UPDATE stock_daily SET low = LEAST(open, close)
WHERE close > 0 AND low > 0 AND low < LEAST(open, close);
```

`low < min(open, close)` 描述的是「当天跌到开盘价与收盘价之下」——**最普通的
正常行情**，全市场命中 **13,292,037 行**，而不是预期的 79 行。另有一条
`UPDATE ... SET open = close WHERE open < 0.2*close` 影响 38 行（这条作用域正确）。

**污染面**：`stock_daily` 共 14,872,765 行，`low` 13,292,072 行失值、
`open` 38 行失值。`high`/`close`/`vol`/`amount` 未触碰（事后用重拉数据交叉验证，
1,580,772 行未污染样本上 4 列偏差均为 0）。

## 为什么会发生

1. **条件写错**：做 A 类分析时同时用了 `low < 0.2*close` 和 `low < LEAST(open,close)`
   两个约束，写 UPDATE 时漏了前者。
2. **执行前跑了计数但没对账**：`SELECT count(*) ... WHERE low < LEAST(open,close)`
   返回 13,292,037，**这个数字被打印出来了**，但当时心里已经把该条件认定成
   「坏行行为」，于是 1329 万不但没报警，反而像是确认。
3. **跳过了项目既有的安全范式**：`quant_ts/rebuild_daily_raw.py` 的做法是写影子表
   `stock_daily_raw` + 审计表 + 「验收通过后由人工执行换名」。本次直接 UPDATE 生产表。
4. **无备份可用**：`archive_mode=off`（无 PITR）、本地无 `tushare_data` dump、
   ECS 上的 dump 是 SaaS 库不是行情库。动手前查过，但查完之后仍然直接改了。

## 恢复过程

1. **备份**：先把 79 行坏 tick 全字段备份到 `_repair_bak_20261028_ticks` + CSV。
2. **重拉**：Tushare `pro.daily(ts_code=...)` 按 symbol 全量重拉，落影子表
   `stock_daily_repair_20261028`。5779/5779 成功、0 失败、16,907,061 行，耗时 69 分钟。
   - 先验证：重拉值与我备份的 79 行**逐列一致**（证明 Tushare 是权威源）；
     20 只股票 76,602 行上 `high/close/vol/amount` 与现有数据 **100% 吻合**
     （证明污染仅限 open/low）。
3. **回写**：`UPDATE stock_daily d SET open=s.open, low=s.low FROM shadow s ...`
   影响 **13,292,072 行**——与污染行数精确相等。
4. **清洗**（正确作用域）：`open` 38 行、`low` 79 行，与预期量级一致。

## 恢复后校验

| 检查 | 结果 |
| --- | --- |
| 回写影响行数 | 13,292,072（= 污染行数） |
| 清洗 open / low | 38 / 79（= 坏 tick 行数） |
| 清洗后 `open<0.2*close` / `low<0.2*close` | 0 / 0 |
| 全市场 OHLC 不变量违反 | 0 |
| 未污染样本上 high/close/vol/amount 与 Tushare 偏差 | 0 |
| 未污染样本上 low 与 Tushare 偏差 | 79（即已知坏 tick，已被清洗） |
| 未污染样本上 pre_close/change/pct_chg 偏差 | 225 / 1,580,772（0.014%，上游 revision） |

**残留风险（如实记录）**：被污染的 1329 万行原值已不可恢复，现值为 Tushare 当前值。
用未污染样本估计上游 revision 率约 0.005%（low）~0.014%（pre_change 系），
即最多约数百行的 `low` 可能是「Tushare 现行值」而非「库内原值」。Tushare 是权威源，
该替换可接受，但**不是零差异**。

## 教训（已写入 AGENTS.md 级纪律）

1. **任何生产表 UPDATE，执行前必须跑与 WHERE 完全相同的 `SELECT count(*)`，
   并与已知量级对账；差一个数量级即中止。**
2. **数据修复一律先影子表 + 人工换名**，参考 `rebuild_daily_raw.py`，不直接改生产表。
3. **条件里的每个守卫都要在最终 SQL 里出现**；从分析到落地要逐字核对，不能凭记忆缩减。
4. 「我已经备份了」不等于「可以安全改」——本次备份只覆盖了 79 行，而改动是 1329 万行；
   备份范围必须覆盖改动范围。
