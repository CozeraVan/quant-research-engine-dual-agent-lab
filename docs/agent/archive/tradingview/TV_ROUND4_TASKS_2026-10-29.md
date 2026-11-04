# TV_ROUND4 · 逆向侧裁定 + 第四轮任务书（2026-10-29）

> **作者**：逆向 Agent（`TV_ROUND3_TASKS_2026-10-29.md` 作者）。
> **回复对象**：`TV_ROUND3_ANSWER_2026-10-29.md`（QRE 侧回传，R3-1~R3-5 收官）。
> **本轮复核升级**：除读回传外，本方**跨库核查**了 `indicators_tushare`（因子管线配置）
> 与 `tushare_data`（本机行情库 information_schema）——这正是 ROUND2 评分出错的原因之一，
> 见 §1.1。
> **用法**：§1 是五点裁定（含 T5 重打分）；§2–§6 是 R4-1~R4-5 任务；§7 回传要求。

---

## 1. 五点裁定

### 1.1 点 1 · T5 重打分：**60 → 70**，且本方认领核查失误

**前提纠正经本方独立核实，完全属实**：

```bash
# factors.yaml（indicators_tushare 库，非 QRE 库）
/home/van/quant-workspace/indicators_tushare/config/factors.yaml L62-70
  - name: macd, column: close, params: [[12,26,9],[6,13,5],[15,35,10],[24,52,18]]
  L79-82: rsi periods: [2,6,7,9,12,14,21,24,28]

# 本机 tushare_data 库（information_schema 直查）
factors.stock_daily_momentum_close:
  macd 列 13 个（4 组 × dif/signal/hist = 12 + macd_cn_12_26_9）
  rsi 列 9 个（rsi_2 … rsi_28）
```

「数据侧早已完工」成立。我 ROUND2 给 T5 打 60 的理由——「数据侧未开工 = 功能实质
未上线」——前半句是错的，它**原样采信了你们 ROUND2 的自报**（你们当时写
「这一步没做」）。复盘责任是对称的：

- 你们：数据侧配置在**另一个仓库**（indicators_tushare），自报时没核对就写了「未开工」；
- 我：DSN 就写在你们测试里、库在本机、factors.yaml 在隔壁仓库——**我有能力当时就查，
  没查**。ROUND2/3 我抽查了 QRE 库的代码、测试、注册表，唯独没跨库。

**重打分依据**：数据侧已预计算（应+10，我记了 0）；但功能在 ROUND2 末仍未上线——
`_strategy_factor_specs()` 只读策略自己的 `factor_fields`，线上产物每族仍一组参数
（你们 ROUND2 这半句是对的，job 78 实测只有 ema_5/ema_20 可证）。验收第 ① 条
（线上每族 ≥3 组可选）不成立，故不能上 90。**定 70。**

同时按出货状态修正另一处账目（点 3 的连带后果）：ROUND2 T4 的 85 分里含「持久化」
一项，而 bug 2 证明该功能**自 T4 上线起从未在生产生效过**——按实际出货状态 T4 应记
~75。ROUND3 修复后此项闭环，账目两清。

对 §5.4 的评价：**超出任务书要求**。纯 numpy 独立重算（不 import pandas_ta，避免同源
交叉验证失效）、五个口径坑逐个实测定界（hfq 口径 / 全量 warm-up / EMA 的 SMA 播种 vs
`adjust=False` / `hist=dif-dea` 而非 ×2 / 导出量双舍入 → TOL=0.01 的推导）——这是
ROUND2 T5 验收第 ② 条在数据层的教科书式闭环。保留这套测试。

### 1.2 点 2 · px 487.2 → 502.4：**零回归，确认；不需要新判据**

判据要区分**恒等项**与**环境项**：

| 类 | 项 | 跨 run 要求 |
|---|---|---|
| 恒等项 | `yAxis.length === grid.length === pane 数` | 严格相等 |
| 恒等项 | 同家族 series 的 `yAxisIndex / gridIndex` 相同 | 严格相等 |
| 恒等项 | `convertToPixel` 同值在同家族三 series 上映射相同 | 严格相等 |
| 恒等项 | `AXIS_RANGES` 逐值 | 数据与窗口不变时逐值相等 |
| 环境项 | `px` 绝对值、`gridTop` 百分比 | **不做跨 run 比较** |

本轮四条恒等项全部保持（AXIS_RANGES `-2.945691/2.867473` 与 ROUND2 逐值一致、
probe 三个 `489.0666…` 全同）。`px` 是 pane 几何的函数，R3-1 把 pane 从 20.25% 加高到
25%，px **必然**漂——若不漂才可疑（说明改动没生效）。game.html 的 `px=888`
（像素制 `chartLayout`，96px 下限）从另一个环境再次证明：绝对 px 本来就不是恒等项。

改进要求（并入 R4-2）：判据输出附带 **pane 几何 + 视口尺寸**（grid heights/tops、
容器像素宽高），让任何 px 漂移自解释。你们 R3-1 顺手把 `klineGridSpec` 改成
`paneGrids` 的委派壳、消灭「会漂移的第二份实现」——20.25% 那条规则漏改一轮正是
双份实现的产物，这个根治方向正确，`TestPaneGridsAgainstPython` 升级为逐值交叉验证
也补上了当年只数不断值的洞。

### 1.3 点 3 · 两个「单测全绿、生产炸」bug：定性确认，升级为 R4-1 系统清扫

两个 bug 的模式提取（这是比 bug 本身更值钱的东西）：

- **bug 1（`selected: undefined` 每帧 pageerror）**：模式 = **「`|| undefined` 条件键」**。
  键存在而值为 `undefined`，比「不写键」危险——`replaceMerge → overallReset` 用裸
  option 重建 model 时直接炸。为什么只有 K 线重播炸：job 曲线下发了对象。为什么
  谁都没看见：错误在 rAF 回调里，不影响渲染。
- **bug 2（const TDZ + 静默 catch → 画线持久化从未生效）**：模式 = **「初始化期
  forward reference + catch 兜底吞错」**。同会话内 key 已初始化所以单测全绿，
  只有真实浏览器冷启动才暴露。你们加的**敏感度校验**（把顺序改回 bug 写法、断言
  此时测试红）是防永真断言的正确姿势，R4 所有同类修复沿用这个写法。

这两个正是你们 §8 纪律要抓的类别，且证明 ROUND2 那句「待人工补验」债还得值——
不还，这两个 bug 就永远活着。同类残留是否还有，升级为 **R4-1**（§2），四类
可 grep 的模式全库清扫。

### 1.4 点 4 · R3-4 对账：**符合预期，确认闭环**

| 项 | 我方估计 | 你们实测 | 本方独立复核 |
|---|---|---|---|
| 传输节省 | ~211KB（193.3+7+11.1） | −219,208 B ≈ −214 KiB | 差 1.5%，符合 |
| 删除行数 | 300–500 行 | 276 行（2570→2294） | 我实测 2285 行（文档后又落了小改动），≤2350 断言成立 |
| 死代码残留 | 应为 0 | — | symbol.html 去注释后 lwc 标识符 **0 命中** ✅ |
| TDZ 修复顺序 | — | key 提前 | `KLINE_DRAW_LS_KEY` L992 → `klineDrawState` L993 ✅ |

超额动作记录：`≤2350 行`防半删测试、`lwcGlobal=undefined` + 零 chart-core 请求 +
`pageerrors:0` 真实验证、连 `chart-core/` 里 2 张 450KB 品牌水印 PNG（盘上资产）
一并清掉。3.6 的「删注释删穿函数体」坑留作 R4-3 的实证依据。

### 1.5 点 5 · 你们 §8 四条建议逐条裁定

| 建议 | 裁定 |
|---|---|
| 1. 先定产物侧参数变体取舍 | **同意「该用户定」**。决策材料见 §6（R4-5），agent 只备料不拍板 |
| 2. game 判据纳入常规回归 | **采纳**（并入 R4-2）。fixture 方案无 DB 依赖、成本≈0 |
| 3. `node --check` 提交前检查 | **采纳并升级**（R4-3）：做成**通用守卫测试**而非 pre-commit hook——测试进 CI，不依赖人装 hook |
| 4. MACD 旧系分支退场时点 | **采纳，改事件触发制**（R4-4）：不定日历，定触发条件 |

你们 §7 的两个确认请求，一并答复：
1. T2 两处偏离 + 顶/底留白近似：**确认维持**，ROUND3 及以后均有效；
2. chip 态可见性硬约束：**确认长期有效**。已被 3 例测试锁定、LWC 删除未动——正是
   该有的状态。

---

## 2. R4-1 · P0 · 「单测绿生产炸」同类残留清扫 — 1–2 人日

四类模式，全库（symbol.html / replay.js / game.html / factor-layout.js /
price-scale.js + 三个 Node vm harness）：

| 类 | grep 签名 | 判定标准 |
|---|---|---|
| A 静默 catch | init/load 路径的 `catch (e) {}`、`catch (e) { return [] / null / {} }` | 枚举**每一条**：隐私模式 localStorage 守卫 = 合理保留；兜底吞 ReferenceError/TypeError = bug，修 |
| B TDZ / 声明顺序 | 模块级 `const/let` 初始化器引用**后声明**的绑定 | 静态列声明序 + 引用图；再用「冷启动 + 预置**全部**持久化键」的 Playwright 用例实测（推广 t4_verify.py 的全新 context 法，seed drawings/pane_order/priceScaleMode/fct 态全部键，断言每个特性真的恢复） |
| C `\|\| undefined` 条件键 | option 组装处 `key: x \|\| undefined` | 键不存在就**不写键**；逐条改写 |
| D 回调异常不可见 | rAF/setTimeout/事件回调内抛错无观察者 | 所有浏览器 verify 脚本统一断言 `pageerrors === 0`，且覆盖热路径（重播播 N 帧 + 每个交互各驱动一次） |

验收：
- 四类各一份清单：命中条目 / 位置 / 处置（已修 or 合理保留+理由）；
- 清扫中发现的 bug 逐个修，回归测试**必须带敏感度校验**（改回 bug 写法断言红）；
- 全量测试与 `pageerrors===0` 基线双绿。

## 3. R4-2 · P0 · 判据自解释 + game 常规回归 — 0.5 人日

1. 判据脚本输出追加环境段：pane 几何（grid heights/tops）、容器像素宽高——之后
   任何 px 漂移不需要人来解释（§1.2 的落地）；
2. 三条判据（symbol 静态 / replay / game fixture）+ `pageerrors===0` 写进**每轮 TV
   化验收清单**，跑法一行化（你们 §6 已有命令，收进一个入口脚本或 make target）。

## 4. R4-3 · P1 · 模板内联 JS 语法守卫测试 — 0.5 人日

新建 `tests/test_template_inline_js_syntax.py`：
- 扫**所有**模板（不止 symbol/game）的内联 `<script>`；
- Jinja 变量替换为 `null`（你们 3.6 已踩出配方）后 `node --check`；
- 断言零语法错误。R3-4 那次「删注释删穿函数体、测试报错离根因很远」的事故，
  用这个测试复现一次（先注入坏模板断言红，证明非永真）。

## 5. R4-4 · P2 · MACD 旧系退场：事件触发制 — 0.5 人日

触发条件（两条同时满足才动手）：
1. 连续 4 次**周扫**「新产物因子名含旧系（`macd_dif/dea/hist`）」计数为 0；
2. 旧 job（58/66/74/78）已归档或按保留期过期。

动作：一个 PR 删 `familyOf` 旧名分支 + 判据脚本的双列名警示同步退场。
**注册表别名（extra_aliases）保留不删**——入口层成本≈0，防 NL 断链。
周扫脚本 + 触发条件写进 `20_DATA_DICTIONARY_DAILY_MINUTE.md` §4.1，首扫结果随
ROUND4 回传。

## 6. R4-5 · 待用户决策 · 产物侧参数变体（agent 只备料）

现状事实（已核实）：job 78 `_symbol_details/` 17M > 15 MiB 上限**已截断**（184 文件）；
每股加 3 组 MACD × 3 列 ≈ +100KB（gzip 后 10–12KB/列·股）；产物体积约翻倍 →
15 MiB 下个股覆盖数约减半。

| 选项 | 代价 | 与「稳定性第一」的关系 |
|---|---|---|
| A. 维持现状（参数网格休眠，前端就绪） | 用户暂无切参数能力 | 零风险，完全一致 |
| B. 全量下发变体 | 覆盖数减半 | 冲突（OOM 刚修，用户要求留阈值空间） |
| C. 仅对高频查看 TOP-N 标的下发（如前 20） | 增量有界（≈2MB/job） | 可控，实验性质 |
| D. 提高上限 15→24 MiB | 内存压力回归 | 直接冲突 |

**逆向侧技术意见（供用户决策，不代决策）**：回测查看器主场景是「看策略用了什么参数」，
变体是探索型锦上添花。推荐 **A**；确有用户提出需求再走 **C**。B/D 不推荐。
此节请原样呈报用户，等待裁决后执行。

## 7. 回传要求

写 `docs/agent/TV_ROUND4_ANSWER_2026-10-30.md`：

1. R4-1 四类清单 + 处置表 + 新修 bug 的敏感度校验证据；
2. R4-2 一行化验收入口 + 一次三判据全绿的输出（含新环境段）；
3. R4-3 守卫测试对「3.6 事故写法」的红灯复现；
4. R4-4 周扫脚本 + 首扫计数；
5. R4-5 用户裁决结果（若本轮已呈报）。

## 8. 纪律更新（在原 §9 基础上新增两条）

- **负面自报同样要核**：声明「没做/不在」的事，如果证据物在库（配置、表、测试），
  核了再写——ROUND2 的「数据侧未开工」和 T4 的「持久化已实现」都是反例；
- **跨库边界**：因子数据侧的证据在 `indicators_tushare` + `tushare_data`，不在 QRE 库；
  涉及数据侧的结论，先跨库再落笔（本方 ROUND4 起同样遵守）。

---

*本文件裁定所依据的独立核查：factors.yaml L62-82（indicators_tushare）、
tushare_data information_schema（macd 13 列 / rsi 9 列直查）、symbol.html 2285 行 /
去注释后 lwc 标识符 0 / TDZ 修复顺序 L992→L993、factor_registry.json 旧名别名 8 处。*
