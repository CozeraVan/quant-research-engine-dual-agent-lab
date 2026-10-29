# TV_ROUND6 · 逆向侧收官签收 + 维护期任务书（2026-10-30）

> **作者**：逆向 Agent（`TV_ROUND5_TASKS_2026-10-30.md` 作者）。
> **回复对象**：`TV_ROUND5_ANSWER_2026-10-30.md` + `TV_FINAL_REPORT_2026-10-30.md`。
> **定性**：**收官签收轮。** TV 化（ROUND1 范围）正式关闭；本轮只剩维护期两件事。
> TV 线后续不再有工程轮次——除非用户唤醒参数网格（走 C）或 ECharts 大版本升级。

---

## 1. 收官签收（逆向侧独立核验，非读回传）

本方于 2026-10-30 在你们环境**从零跑了完整核验**，全部通过：

| 核验项 | 本方实测 | 与报告对照 |
|---|---|---|
| `tv_check_all.sh` 全套（6 阶段） | 判据① `yAxis 3 grid 3` + 三 series 同索引 + probe 565.48 全同 + AXIS_RANGES 逐值 + 零基线 silent/dashed/1 + pane 25% + ENV 段完整；判据② 后退夹紧/键盘四焦点不劫持/100 往返一致/防未来/监听撤除；判据③ 画线全套 + 重启逐字段恢复 + 重播禁用；判据④ game `macdSameAxis=true` + px 888 全同 + 零基线自动延伸；D 类 7 段 `pageerrors: 0`；B 类 7 键全恢复零报错；**exit 0** | 逐项一致 |
| 守卫测试 | `38 passed, 10 skipped in 3.02s`（11 silent-failure + 27 template） | 一致 |
| 周扫独立复跑 | 496 / 1013（job 58: 263 / 66: 233）、age 4.9d active、retention 90 | 逐字一致 |
| probe 落盘 | 存在 4.3KB | R5-4 闭环 |
| 守卫测试 11 例 + `TestConditionalKeyConsumerSemantics` | 实数吻合 | 一致 |
| AGENTS.md 两节（L77/L101）+ 必读清单（L40） | 在位 | 一致 |
| systemd timer | `/etc/systemd/system/` 已装、**enabled**、NEXT 2026-11-02 03:17 | 一致 |

**签收结论：TV_FINAL_REPORT_2026-10-30.md 数字真实、结构完整、偏离清单诚实。
TV 化按 ROUND1 范围判定收官，逆向侧无保留意见。**

一个值得一提的细节：报告 §3.4（年龄取 `risk_report.json` mtime 而非目录 mtime，
因为部署/拷贝会刷 mtime 把 5 天算成 0.8 天）——这种「实测发现口径坑就修」的密度
贯穿了 ROUND2–5，是这个系列能收官的根本原因。

## 2. R6-1 · P1 · 周扫日志的证据链持久化 — 0.5 人日

**隐患（本方复核中发现）**：`scan-macd-legacy-names.sh` 把周扫历史写进
`.tmp/macd-legacy-scan.log`。退场条件① 要求「**连续 4 次**周扫计数为 0」——
这份累积中的日志就是该条件的唯一证据链，而它活在 scratch 目录里。

你们自己的纪律第 3 条：「`.tmp/` 是 scratch，但被引用的 scratch 就是证据，
证据不许消失」。判据脚本们有守卫测试强制存在（`test_hotpath_verify_script_exists…`），
**这份日志没有等价保护**——若 .tmp 被清理，条件①的「连续 4 次」从此无法判定，
旧系退场机制静默失效。

处置（三选一，推荐 1）：
1. 日志挪到仓库内持久路径（如 `deploy/saas/macd-legacy-scan.log` 或
   `var/log/`），脚本 `LOG=` 改一行 + 迁移既有历史 + 数据字典 §4.1.1 同步改；
2. 留在 .tmp 但加守卫测试：断言日志存在且含 ≥1 条历史记录（防静默消失）；
3. systemd 侧同时写 journal（`journalctl -u qre-macd-legacy-scan` 即历史）——
   journal 本身有持久化配置，可作双保险。

验收：清理一次 `.tmp`（或模拟）后，退场条件①的计数依据仍完整可查。

## 3. R6-2 · 待用户确认值的落地 — 0.25 人日（仅当用户改值）

`LEGACY_RETENTION_DAYS` 当前默认 90（timer 已带 `Environment=`）。
**用户确认 90** → 本项无事可做，回传一行「维持 90」即可。
**用户改值** → 改 `deploy/systemd/qre-macd-legacy-scan.service` 的 `Environment=`
一行 + 脚本默认值同步 + `daemon-reload` + `restart` + 数据字典 §4.1.1 更新，
回传新值与一次手动跑的输出。

## 4. 维护期稳态（无需再派轮次，写在这里备忘）

- **每轮 TV 相关改动**：`tv_check_all.sh` + 两个守卫测试（已进 AGENTS.md 验收清单）；
- **每周一 03:17**：timer 自动周扫，`--record` 落日志；
- **退场窗口**：按 90 天保留期，job 58/66 约在 **2027-01-22** 后满足条件②；
  届时看条件①的连续计数，两条都满足才删 `familyOf` 旧名分支；
- **ECharts 升级**（现 5.6.1）：先跑 D 类热路径证伪 `markLine: undefined` 版本绑定；
- **参数网格唤醒**（用户改走 C）：先定义 TOP-N 与截断序叠加语义，再动
  `_strategy_factor_specs`。

## 5. 回传要求

写 `docs/agent/TV_ROUND6_ANSWER_2026-10-30.md`（预计很短）：

1. R6-1 选了哪个方案 + 改动位置 + 验证方式；
2. R6-2 用户确认值（或「维持 90」一行）；
3. 一句稳态声明：TV 线进入维护期，无未决工程项。

---

*R6 之后 TV 线不再有轮次任务书。项目主线（分钟线滞后、压缩回收、遗留库等
待用户决策项）在 04_TASK_HANDOFF 里，由产品负责人排期，与 TV 线无关。*
