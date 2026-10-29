# CR-2026-10-29 · R3-5 MACD 双列名收敛（registry 别名 + 文档定调）

> 任务书：`docs/agent/TV_ROUND3_TASKS_2026-10-29.md` §6
> 优先级 P2，0.5 人日。实施：Kimi。
> 任务书自己把这轮定性为「**文档性收敛**，防未来误判」——本 CR 按这个定性做，
> 没有为了"看起来做了更多"而去做回刷。

---

## 1. 问题：两套列名并存，且都还在用

| 系 | 列名 | 产物形态 | 谁在用 |
|---|---|---|---|
| **新系（现行）** | `macd_12_26_9` / `macds_12_26_9` / `macdh_12_26_9` | `col` + `display` 合同齐全 | 2026-10-28 之后的新产物、游戏页 `MACD` 常量 |
| **旧系（存量）** | `macd_dif` / `macd_dea` / `macd_hist` | **只有 `name`，`col=None`、`display=None`** | job 58/66/74/78 等 2026-10-28 前完成的回测 |

前端呈现层**已经不分裂**：`factor-layout.js::familyOf` 对两套都归组到一个 MACD
面板——TV_ROUND2 §3 判据用生产 job 58 真实产物证实过（三 series 同
`yAxisIndex/gridIndex`、同像素映射、`px 476.4` 三者相等）。

**真正没收敛的是入口层**：NL 描述与因子选择只认注册表，旧名不在注册表里，
用户用 `macd_dif` 描述就解析不到。

## 2. 做了什么

### 2.1 注册表别名（`configs/factor_registry.json` + 生成器同步）

`extra_aliases` 新增 6 条，把旧名/中文俗称映射到新系 canonical：

| 输入 | 解析到 | output |
|---|---|---|
| `macd_dif` | `factors.stock_daily_momentum_close.macd_12_26_9` | `dif` |
| `macd_dea` | `factors.stock_daily_momentum_close.macds_12_26_9` | `signal` |
| `macd_hist` | `factors.stock_daily_momentum_close.macdh_12_26_9` | `hist` |
| `macd柱` | `…macdh_12_26_9` | `hist` |
| `macd快线` | `…macd_12_26_9` | `dif` |
| `macd慢线` | `…macds_12_26_9` | `signal` |

两处同步改（防止下次重新生成时被覆盖回旧值）：
- `configs/factor_registry.json` 的 `extra_aliases`（8 → 14 条）
- `scripts/gen_factor_registry.py::EXTRA_ALIASES`（同一份数据，带注释说明为什么）

实测解析（`load_registry().resolve(...)`）：
```
'macd_dif'  -> unique, factors.stock_daily_momentum_close.macd_12_26_9,  output=dif
'macd_dea'  -> unique, factors.stock_daily_momentum_close.macds_12_26_9, output=signal
'macd_hist' -> unique, factors.stock_daily_momentum_close.macdh_12_26_9, output=hist
```
大小写/分隔符不敏感（`MACD_DIF` / `macd dif` / `macd-dif` 同样命中）。
`validate_registry(snapshot, registry=reg)` → **0 issues**。

### 2.2 文档定调（`20_DATA_DICTIONARY_DAILY_MINUTE.md` 新增 §4.1）

明确记录四件事，避免未来反复讨论：
1. 两套列名对照表 + 各自产物形态；
2. **不回刷旧产物**（job 58/66 保持原样）——价值低，且会改变已验证的历史结果；
3. **前端呈现层不分裂**（`familyOf` 两套都归组，已有判据证据）；
4. **新产物一律新系命名**，旧名仅作兼容，不新增旧系因子。

并给"写判据/验证脚本的 agent"一条硬提醒：**拉产物后先打印 `col`/`name` 确认是哪一套**，
用错会得出"归组失败"的错误结论。

### 2.3 判据脚本文件头声明

`.tmp/perf-browser/` 下三个判据/验证脚本的文件头都加了双列名警示：
`macd_criterion.py`、`tv3_verify.py`、`tv3_game_verify.py`。
其中 game 脚本还记了一个具体现场：它的因子值取自旧系列名，但游戏页 `MACD` 常量
写死新系 canonical，所以 catalog fixture 必须把新系 canonical 映射到旧系 column
才能选中。

## 3. 明确不做（及理由）

| 项 | 为什么不做 |
|---|---|
| 回刷 job 58/66/74/78 的产物 | 任务书明确"不回刷"；且会改变已验证的历史结果，收益近零 |
| 给旧名建独立 display 合同条目（`chart_type`/`panel_id` 等） | 旧系列在当前库里**没有对应表**（产物只留了 name）。建条目要么编一个不存在的 table（破坏注册表"列必须存在于快照"的不变式），要么把旧名塞进新表（会让因子选择器出现选不到的因子）。旧产物的呈现已由 `familyOf` 兜住，不需要注册表参与 |
| 删掉 `familyOf` 的旧名分支 | 旧产物还在线上跑，删了旧产物立刻回退成"MACD 三列各一个面板" |

## 4. 测试

`tests/test_factor_registry.py::TestMacdDualNamingAliases`（9 例，新增）：

- 6 例参数化：`macd_dif`/`macd_dea`/`macd_hist` 及大小写/分隔符变体解析到正确
  canonical，且 `status == 'unique'`；
- 1 例：三个 output 角色必须分别是 `dif`/`signal`/`hist`（错一个画出来就是三条同色线）；
- 1 例：中文俗称（`macd柱`/`macd快线`/`macd慢线`）；
- 1 例：生成器 `EXTRA_ALIASES` 与 `configs/factor_registry.json` **不得漂移**
  （这条是防"改了 JSON、下次重新生成被覆盖"）。

`tests/test_factor_registry.py` 40 → **49 passed**；
`tests/test_factor_display_contract.py` 19 passed；注册表校验 0 issues。

未 commit / 未 push / 未部署 ECS（按派单约束）。
