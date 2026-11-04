# TV_ROUND6_ANSWER · 收官签收回传 + R6-2 保留期落地（2026-10-30）

> **作者**：Kimi（主 Agent，TV_ROUND6_TASKS_2026-10-30.md 的执行方）。
> **回复对象**：`TV_ROUND6_TASKS_2026-10-30.md`（逆向侧收官签收轮 + 维护期任务书）。
> **结论先行**：R6-1 **已完成**（方案 1 仓库内持久日志 + 方案 3 journal 双保险）；
> R6-2 **已完成并验证**（用户 2026-10-30 将 `LEGACY_RETENTION_DAYS`
> 由 90 天下调为 **15 天**）。

---

## 0. 对收官签收的回应

收到逆向侧独立核验结论（`tv_check_all.sh` 六阶段 / 守卫测试 38 passed /
周扫独立复跑 496 / probe 落盘 / AGENTS.md 两节 / timer enabled 全部逐项一致），
**TV 化（ROUND1 范围）正式关闭，无保留意见**——本方认同该结论，
`TV_FINAL_REPORT_2026-10-30.md` 的数字与偏离清单维持原样。

---

## 1. R6-1 · 周扫日志证据链持久化 —— **已完成（方案 1 + 3 的组合）**

**隐患确认（与逆向侧判断一致，且本方复核后认为优先级被 R6-2 进一步抬高）**：
`.tmp/macd-legacy-scan.log` 是退场条件①「连续 4 次周扫计数为 0」的**唯一**证据链，
活在 scratch 目录，无守卫测试保护。保留期从 90 天缩到 15 天后，
条件② 约 2026-11-08 即满足，**条件① 的连续计数从此成为退场的唯一关键路径**——
日志一旦丢失，退场判定静默失效，且无人会察觉。

**采取的方案：任务书方案 1（仓库内持久路径）为主 + 方案 3（journal 双保险）**。

方案 3 单用原本**不成立**：unit 里 `StandardOutput=append:<file>` 把输出只送文件，
实测 `journalctl -u qre-macd-legacy-scan` **无任何条目**。本轮把 unit 的
`StandardOutput`/`StandardError` 改为 `journal`（默认值），journal 侧才真正有历史。

| # | 改动 | 位置 |
|---|---|---|
| 1 | `LOG=` 从 `.tmp/macd-legacy-scan.log` 改到**仓库内** `deploy/saas/macd-legacy-scan.log`，脚本头注释写清「这是条件①的唯一证据链，不许放 .tmp」 | `deploy/saas/scan-macd-legacy-names.sh` L26 + 头部注释 |
| 2 | `.gitignore` 加显式 negation `!deploy/saas/macd-legacy-scan.log`（`*.log` 会忽略它；**注意 negation 行尾不能带 `#` 注释**——git 不支持行尾注释，会把注释吃进 pattern，第一版就踩了这个坑，`git check-ignore` 复验才发现） | `.gitignore` L20-21 |
| 3 | 既有历史 2 条一次性迁移到新路径；`.tmp/macd-legacy-scan.log` 与 `.tmp/macd-legacy-scan.timer.log` 删除（内容为证据日志子集，无信息损失） | 一次性 |
| 4 | unit `StandardOutput`/`StandardError`：`append:.tmp/…timer.log` → `journal` | `deploy/systemd/qre-macd-legacy-scan.service` L15-17 |
| 5 | 守卫测试 `TestLegacyScanEvidenceLogPersistent`（3 例）：日志存在且含 ≥1 条 `=== ` 历史头 / `.gitignore` negation 在位 / 脚本 `LOG=` 指向仓库内且不含 `.tmp` / unit stdout 为 journal 且无 `.tmp` 路径 | `tests/test_no_silent_failure_patterns.py` |

**验证（任务书要求的「清理一次 .tmp 后计数依据仍完整可查」）**：

```
$ deploy/saas/scan-macd-legacy-names.sh --record
… retention_days 15 …
已追加到 /home/van/quant-workspace/quant-research-engine-dual-agent-lab/deploy/saas/macd-legacy-scan.log

$ ls .tmp/macd*        # .tmp 下已无任何 macd 日志
ls: cannot access '.tmp/macd*': No such file or directory

$ uv run pytest tests/test_no_silent_failure_patterns.py -q -p no:randomly
18 passed in 0.29s
```

即：`.tmp` 已清空，条件① 的计数依据（仓库内日志 + journal）完整可查。

---

## 2. R6-2 · `LEGACY_RETENTION_DAYS` 90 → 15 —— **已完成并验证**

### 2.1 用户确认值

**15 天**（2026-10-30，用户在原默认 90 天下调）。含义不变：含旧系 MACD 列名的
job 产物，自 `risk_report.json` mtime 起超过 15 天即视为「已过期」，
退场条件② 随之可满足。

### 2.2 改动位置（4 处，全部落地）

| 文件 | 行 | 改动 |
|---|---|---|
| `deploy/systemd/qre-macd-legacy-scan.service` | L11 | `Environment=LEGACY_RETENTION_DAYS=90` → **15** |
| `deploy/saas/scan-macd-legacy-names.sh` | L19/L27 | 注释：默认 15（用户 2026-10-30 确认），删「待用户确认」 |
| 同上 | L28 | `LEGACY_RETENTION_DAYS="${LEGACY_RETENTION_DAYS:-90}"` → **:-15** |
| 同上 | L57/L78 | 远端 Python 兜底默认 `"90"` → **"15"**（两处） |
| `docs/agent/20_DATA_DICTIONARY_DAILY_MINUTE.md` | §4.1.1 | 保留期 15 天 + 退场窗口 2027-01-22 → **2026-11-08** |
| `docs/agent/TV_FINAL_REPORT_2026-10-30.md` | §4.3 | 同同步，并标注「由本报告成文时的 90 天下调」 |
| `docs/agent/11_AGENT_STATE.md` | R5-2 行 / 待确认段 / 待办③ | 「待用户确认 90」→「已确认 15」 |

### 2.3 生效验证（`systemctl` + 手动跑）

`/etc/systemd/system/` 下的 unit 是副本，**必须同步覆盖后才 daemon-reload**
（第一轮只改仓库文件 + `daemon-reload`，`systemctl show` 仍显示 90，已发现并修正）：

```
$ systemctl show qre-macd-legacy-scan.service -p Environment
Environment=LEGACY_RETENTION_DAYS=15

$ systemctl list-timers qre-macd-legacy-scan.timer
NEXT                        LEFT     LAST                        PASSED UNIT                       ACTIVATES
Mon 2026-11-02 03:17:00 CST 3 days   Thu 2026-10-29 13:32:00 CST    -     qre-macd-legacy-scan.timer qre-macd-legacy-scan.service
```

手动跑一次（未 `--record`，不污染条件① 证据日志）：

```
$ deploy/saas/scan-macd-legacy-names.sh
scanned_files 1013
legacy_job 58 263
legacy_job 66 233
legacy_total 496
legacy_age 58 4.9 active
legacy_age 66 4.9 active
retention_days 15

保留期 LEGACY_RETENTION_DAYS = 15 天
条件①：本次仍有 496 个产物含旧系名 → 不满足
条件②：以下 job 仍在保留期内，未过期 → 不满足：58 66
>>> 退场条件未满足，familyOf 旧名分支继续保留 <<<
```

### 2.4 退场窗口重算

job 58/66 生成于 **2026-10-24**（首扫年龄 4.9 天 @ 2026-10-29），
按 15 天保留期 → **2026-11-08 之后**条件② 可满足（原 90 天为 2027-01-22，提前 75 天）。
届时只需条件① 连续 4 次为 0，即可删 `factor-layout.js::familyOf` 旧名分支。

---

## 3. 稳态声明

TV 线进入**维护期**：R6 之后不再有轮次任务书，无未决工程项。
维护动作仅剩：每轮 TV 改动跑 `tv_check_all.sh` + 两个守卫测试（已进 AGENTS.md）、
每周一 03:17 timer 自动周扫、2026-11-08 后关注退场窗口。

**本方挂起项**：无（R6-1 已随 R6-2 一并落地，见 §1）。

---

## 4. 收尾动作回传（TV_MAINT_NOTES_2026-10-30 两条）

### 4.1 journal 双保险实操验证 —— **通过**

```
$ sudo systemctl start qre-macd-legacy-scan.service      # oneshot，自带 --record
Result=success / ExecMainStatus=0                        # 墙钟约 11s

$ sudo journalctl -u qre-macd-legacy-scan.service --no-pager | tail
Oct 29 15:00:40 … scan-macd-legacy-names.sh[15134]: scanned_files 1013
Oct 29 15:00:40 … scan-macd-legacy-names.sh[15134]: legacy_job 58 263
Oct 29 15:00:40 … scan-macd-legacy-names.sh[15134]: legacy_job 66 233
Oct 29 15:00:40 … scan-macd-legacy-names.sh[15134]: legacy_total 496
Oct 29 15:00:40 … scan-macd-legacy-names.sh[15134]: legacy_age 58 4.9 active
Oct 29 15:00:40 … scan-macd-legacy-names.sh[15134]: legacy_age 66 4.9 active
Oct 29 15:00:40 … scan-macd-legacy-names.sh[15134]: retention_days 15
Oct 29 15:00:40 … scan-macd-legacy-names.sh[15134]: >>> 退场条件未满足，familyOf 旧名分支继续保留 <<<
```

**脚本输出（非仅生命周期行）已在 journal 中**，双保险成立。
一个值得记的对照：同一 unit 在**上一个 boot**（13:32）的 journal 记录**只有**
`Starting/Finished` 两行生命周期——那正是 `StandardOutput=append:.tmp` 时期的产物，
反向证明了 R6-1 改 `journal` 是必要的，不是形式主义。
该次 `systemctl start` 也按设计往仓库内证据日志追加了一条（`=== 2026-10-29T07:00:40Z ===`）。

### 4.2 数据字典 §4.1.1 补退场前置动作 —— **已补**

新增段落「**退场前置动作（2026-11-08 窗口，产品决策，agent 不拍板）**」：
`legacy_total==0` 不是等来的——它要求 job 58/66 的 **496 个含旧系名产物被实际归档或删除
（归档优于删除）**；15 天过期**只满足条件②**，产物文件仍在 ECS 上，周扫照样读到旧列名，
条件① 计数不会归零。正确顺序：**先归档/清理这 496 个产物 → 再连续 4 次周扫计数为 0 →
才删 `familyOf` 旧名分支**。

### 4.3 2026-11-08 窗口的产品决策 —— **用户已裁定：归档，并已执行**

三个选项（归档退场 / 保留分支 / 重跑旧 job 换成新系产物）呈报后，
用户 2026-10-29 裁定**归档**，本方当日执行完毕：

- `mv` `/srv/aguhuice/uploads/job_{58,66}/_symbol_details`（263 + 233 个 gzip，45MB）
  → `/srv/aguhuice/archive/job_{58,66}/_symbol_details`（同文件系统，秒级可回退）；
  配套 `QRE-SAAS-ARTIFACT-ARCHIVE`：详情页查找顺序改 **live → 归档**
  （归档根缺省 `upload_root` 兄弟目录 `archive/`，`SAAS_ARCHIVE_DIR` 可覆盖），
  因为 58/66 是公开展示的经典策略，归档 ≠ 下线；
- 归档后周扫：`scanned_files 1013 → 517`、**`legacy_total 0`**、条件② 满足；
  详情页抽样 12 + 12 只全部 `200 / ok:true`，`/saas/showcase` 等 200；
- **退场时间表**：条件① 只计 `--record` 落盘的周扫（临时手动跑不计入），
  4 个零预计落在 **2026-11-02 / 11-09 / 11-16 / 11-23**，**11-23 之后**才可删
  `familyOf` 旧名分支；
- **退场后置风险**（删分支前必须处理）：归档产物因子名仍是旧系，靠 `familyOf`
  旧名分支才能与 `macd_12_26_9` 组合流成同一副图；直接删会让 58/66 详情页退回
  「三指标各自独立副图」。三选一（展示层窄化映射 / 改写归档 gzip 因子名 / 重跑）
  待产品负责人定，详见 `change_requests/CR-2026-10-29_artifact_archive.md`。

---

*本文件由 Kimi 主 Agent 撰写；step5 未参与本轮（R6-2 为单行参数 + 文档同步）。*
