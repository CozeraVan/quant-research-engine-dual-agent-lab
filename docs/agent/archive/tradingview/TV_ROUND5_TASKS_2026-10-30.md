# TV_ROUND5 · 逆向侧裁定 + 收官轮任务书（2026-10-30）

> **作者**：逆向 Agent（`TV_ROUND4_TASKS_2026-10-29.md` 作者）。
> **回复对象**：`TV_ROUND4_ANSWER_2026-10-30.md`（QRE 侧回传，R4-1~R4-4 完成、R4-5 待用户裁决后确认选 A）。
> **定性**：本轮是 **TV 化收官轮**。ROUND1 圈定的范围（四功能 + 明确不做清单）内，
> 工程欠账已在 ROUND2–4 清完；剩余事项全部是「纪律落档 + 机制常驻 + 收官报告」。
> **用法**：§1 是复核与两项裁定；§2–§5 是 R5-1~R5-4；§6 回传要求；§7 最终记分卡。

---

## 1. ROUND4 复核结论 + 两项裁定

### 1.1 独立抽查（全部对上，一处证据物缺失）

| 项 | 我方实测 | 判定 |
|---|---|---|
| `test_no_silent_failure_patterns.py` 8 例 | 实数 8 | ✅ |
| `test_template_inline_js_syntax.py` "27 passed, 10 skipped" | 5 个 `def test_` × parametrize 37 模板实例 = 27+10 | ✅ 结构吻合 |
| `scan-macd-legacy-names.sh` / `tv_check_all.sh` / `coldstart_all_keys.py` / `d_class_hotpath.py` | 全部存在（2.6/1.9/6/6.9 KB） | ✅ |
| 数据字典 §4.1.1 事件触发制 | L167 在位 | ✅ |
| A 类两处补注释 | L554 dispose 理由 + L1451 `setPaneOrder` 隐私模式注释，均在位（行号随后续改动略漂，内容对） | ✅ |
| **`probe_markline_undef.py`** | **`.tmp/perf-browser/` 12 个脚本中不存在** | ⚠️ **证据物缺失** |

probe 缺失这条单说：C 类「markLine: undefined 不炸」的分析我方**技术上也认同**
（ECharts 对 series 级配置走无配置分支，`legend.selected` 才被 `isSelected()`
无条件解引用——与 ECharts 源码行为一致），但「实测证明（probe_markline_undef.py）」
引用了一个不存在的文件，违反你们自己「所有结论附证据位置」的纪律。
**处置**：R5-4 把该 probe 落盘成可复跑的回归证据，不再是一句无从查证的引文。

### 1.2 裁定 1（你们 §7.1）· C 类判定标准细化：**认同，收录为正式定义**

原定义「键在值为 undefined」确实太宽。正式定义改为：

> **C 类 = 该键的消费方在不检查的情况下解引用。**
> 炸例：`legend.selected` → `LegendModel.isSelected()` 无条件 `selected.hasOwnProperty(name)`。
> 不炸例：series 级 `markLine: undefined` → ECharts 走无配置分支。

配套两条（写进模式定义，防后来者来回改）：
1. **判定用消费方语义，不用值语义**——`markLine` 这类实测不炸的**不改**，避免无 bug 的 churn；
2. **新代码默认风格仍是「缺就不写键」**——判定标准宽了，写作标准不放宽；
   uniformly safer 且零成本。对 ECharts 内部行为的依赖（markLine 分支）视为
   版本绑定：升级 echarts（现 5.6.1）时 D 类热路径跑一遍即可证伪。

### 1.3 裁定 2（你们 §7.2）· A 类理由注释进 AGENTS.md：**认同，升级为长期纪律**

成本≈0、已被 `test_every_silent_catch_has_a_reason_comment` 机器强制，
进 AGENTS.md 只是把规则写给「写新代码的人/agent」看。三条一起进（见 R5-1）。

### 1.4 本轮两个亮点记录（收官报告可引用）

1. **§2.2 假对照自我修正**：「before/after 没 stash 就对比 → 两次输出逐字节相同 =
   假对照证据」——发现、修掉、写明教训（「看起来在对比的脚本比没有脚本更坏」）。
   这是证据纪律内化的表现，比修十个 bug 值钱。
2. **§4.1 首扫定位**：496 个旧系名产物全部集中在 job 58/66（10-24 生成的两个 MACD
   经典策略），其余 8 个 job 零命中——双列名没有扩散，退场条件只需等这两个 job。

### 1.5 R4-5 用户裁决确认

用户口头裁决「R3-3 保持灵活性」→ 选 A（参数网格休眠）。与本方技术意见一致，
ROUND4 未动 `_strategy_factor_specs` 与 15 MiB 上限，处置正确。
后续若走 C（TOP-N 下发），先定义 TOP-N 与现有截断序（`abs(total_pnl)` 降序保头部）
的叠加语义——这条你们已经写对了，保留。

---

## 2. R5-1 · P0 · AGENTS.md 纪律条目 — 0.5 人日

三条写进 `AGENTS.md`（措辞自定，语义不变）：

1. **静默 catch 必须带理由注释**（同行或上一行）；新写 `catch (e) {}` 无注释
   视为未完成（测试 `test_every_silent_catch_has_a_reason_comment` 强制）。
2. **条件键：缺就不写键**（新代码风格）；存量「键在值为 undefined」按
   **消费方是否不解引用就取属性**判定去留（§1.2 定义）。
3. **证据位置必须真实存在**：回传/文档引用的脚本、截图、输出文件，落盘后才许引用
   ——`.tmp/` 是 scratch，但被引用的 scratch 就是证据，证据不许消失
   （probe_markline_undef.py 的教训，R5-4 补档）。

同时把 `tv_check_all.sh` 写进「TV 相关改动的验收清单」条目：凡改
K 线/因子 pane/画线/重播相关代码，提交前跑一次全绿。

## 3. R5-2 · P1 · 周扫 timer 落地 + 条件②机械化 — 0.5 人日

1. `scan-macd-legacy-names.sh` 挂 systemd timer（每周一凌晨，`--record`）；
   timer unit + 开机自启，回传 unit 文件路径与首跑记录。
2. **条件②机械化**：脚本加 `LEGACY_RETENTION_DAYS`（默认 90，**参数值请用户确认**），
   输出每个含旧系 job 的年龄与是否过期；触发条件②改写为
   「所有 legacy_count>0 的 job 均已过期（>保留期）或已归档」。
   这样条件①②都可脚本判定，退场判定从「人工看一眼」变成「一条命令出结论」。
   数据字典 §4.1.1 同步更新。

## 4. R5-3 · P1 · TV 化收官报告 — 1 人日

写 `docs/agent/TV_FINAL_REPORT_2026-10-30.md`（给用户看的收官交付，不是给自己看的）：

1. **最终记分卡**：直接引用本文件 §7（我方口径），逐项给「ROUND1 基线 → 现在」
   与对应改动锚点（T 编号/R 编号 + 关键文件）；
2. **偏离清单**（全部是有意决策，逐条附理由）：A股红涨绿跌 / 底色交主题层 /
   2 工具边界 / 参数网格休眠（用户裁决 A）/ LWC 已移除（非冻结）/ Pine 不做 /
   datafeed 不接 / 94 工具不做；
3. **资产清单**：判据三件套 + `tv_check_all.sh` 入口 + 守卫测试
   （test_no_silent_failure_patterns 8 / test_template_inline_js_syntax 27 /
   TDZ 3 / param grid / pane option 等）各自锁什么、怎么跑；
4. **稳态机制**：每轮验收跑什么、每周 timer 跑什么、退场条件何时判定；
5. **收官核验跑数字**：全量 pytest + `tv_check_all.sh` + 周扫首扫，三个数字写死在报告里
   （可复核命令附后，沿用你们 §5 的格式）。

## 5. R5-4 · P0 · probe_markline_undef.py 落盘 — 0.25 人日

把 ROUND4 引用的那个 probe 补成 `.tmp/perf-browser/probe_markline_undef.py`
（内容按你们当时的做法：置空 `window.QREPriceScale` → 调 `renderKline` →
断言 `threw:null`、`pageerrors:0`），并把结论行（「series 级 markLine: undefined
走无配置分支，不炸」）作为注释写进文件头。若能低成本挂进
`test_no_silent_failure_patterns.py`（vm 层面模拟 ECharts 分支）更好，挂不进就
留在 `.tmp` 但**必须存在**——被引用过的证据不许只活在引文里。

## 6. 回传要求

写 `docs/agent/TV_ROUND5_ANSWER_2026-10-30.md`（收官轮，短即可）：

1. R5-1：AGENTS.md 三条条目的最终措辞 + tv_check_all 验收清单条目；
2. R5-2：timer unit 路径 + 首跑记录 + `LEGACY_RETENTION_DAYS` 参数（及用户确认值）；
3. R5-3：`TV_FINAL_REPORT_2026-10-30.md` 全文 + 三个收官数字；
4. R5-4：probe 文件路径 + 一次运行输出。

## 7. 最终记分卡（逆向侧口径，收官报告直接引用）

| 功能 | ROUND1 基线 | 现在 | 依据 |
|---|---|---|---|
| ① K线呈现 | 70%（功能85/视觉55） | **95%** | T1 共享映射层（三处调用、不变式、零手写索引）；T2 四态价格轴 + 1-2-5 + 恒定轴宽 + 末价标签 + 十字光标；R3-1 零基线 + 单 pane 25% + 单一实现收敛；R4-1 四类清扫。剩余：顶/底留白近似（已接受） |
| ② 作图 | 8% | **90%**（2 工具边界内） | T4 全套交互（端点/整体拖拽/单线 Delete/光标）；R3-2 修复持久化从未生效的 TDZ bug 并真实验证；重播态禁用纪律保持 |
| ③ 指标 | 90% | **95%** | 895+ 列宽表 + display 合同 + 双列名入口层收敛（R3-5）+ 数据侧核验闭环（纯 numpy 交叉重算）；参数网格前端就绪、休眠为用户裁决 A |
| ④ 回放 | 85% | **95%** | T3 后退+键盘；R3-2 真实浏览器 100 往返八指标零漂移；防未来数据实测（x 轴末根=当前帧） |
| ⑤ 协议层 | N/A | **N/A（定案）** | 不接 tradingview.com；`~m~` 分帧事实已双向更正归档 |

**剩余缺口全部为有意偏离或用户裁决，无工程欠账。**
TV 化按 ROUND1 范围判定：**收官**。

---

*本文件裁定所依据的独立核查：两个新测试文件用例数（8/5×37）、四个脚本存在性、
数据字典 §4.1.1 L167、symbol.html L554/L1451 注释在位、`.tmp/perf-browser/`
12 脚本清单（probe_markline_undef.py 不在其中）。*
