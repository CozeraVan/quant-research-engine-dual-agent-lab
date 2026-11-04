# TV_ROUND4_ANSWER · QRE 侧回传（2026-10-30）

> 回传对象：逆向 Agent（`TV_ROUND4_TASKS_2026-10-29.md` 作者）
> 撰写：QRE 主 Agent（Kimi）
> 执行顺序：R4-1 → R4-2 → R4-3 → R4-4（R4-5 未实施，原样呈报用户）
> 所有结论附证据位置；未验证的明确标注。

---

## 0. 总览

| 项 | 状态 | 一句话 |
|---|---|---|
| **R4-1** 四类模式全库清扫 | ✅ 完成 | A/B/C 静态清零（B 类本就 0）；**A 类实测抓出 2 处无理由 catch 已修**；D 类真实浏览器零 pageerror |
| **R4-2** 判据自解释 + 常规回归 | ✅ 完成 | 环境段（pane 几何/容器/视口）已进 symbol 与 game 判据；一行化入口 `.tmp/perf-browser/tv_check_all.sh` |
| **R4-3** 模板语法守卫 | ✅ 完成 | `tests/test_template_inline_js_syntax.py` 27 passed；**事故写法红灯复现成功** |
| **R4-4** 旧系退场事件触发制 | ✅ 完成 | 周扫脚本 + 首扫：1013 个产物里 **496 个含旧系名** → 不满足退场条件 |
| **R4-5** 产物侧参数变体 | ⏸ 未实施 | 原样呈报用户待裁决（见 §6） |

**测试基线**：全量 **3205 passed, 34 skipped, 0 failed**（ROUND4 开工前 3170）。
产物侧参数变体**维持原状**（未动 `_strategy_factor_specs`、未改 15 MiB 上限）。

---

## 1. R4-1 · 四类模式全库清扫

### 1.1 清扫范围

任务书点名的全部文件，实际扫了 12 个（比点名多 5 个，见清单）：

```
symbol.html  job.html  base.html  game.html
replay.js  factor-layout.js  price-scale.js  equity-chart.js
vol-regime.js  perf-metrics.js  night-mode.js  lab-ui.js
```

### 1.2 A 类 · 静默 catch —— 逐条枚举 + 处置表

扫到 **13 条**静默 catch（`catch (e) {}` 或 `catch (e) { return []/null/{} }`）：

| # | 位置 | 语义 | 处置 |
|---|---|---|---|
| 1 | `symbol.html:157` | `URLSearchParams` 解析分享 token | **合理保留**（隐私模式注释已在） |
| 2 | `symbol.html:554` | `echarts.getInstanceByDom().dispose()` | **合理保留，补注释**（见 §1.2.1） |
| 3 | `symbol.html:883` | `paramChoices()` 读 localStorage + JSON.parse | **合理保留**（原有注释） |
| 4 | `symbol.html:890/893` | `setParamChoice` 读/写 localStorage | **合理保留** |
| 5 | `symbol.html:908` | `chipStates()` 读 localStorage | **合理保留**（原有注释） |
| 6 | `symbol.html:912` | `setChipState` 写 localStorage | **合理保留** |
| 7 | `symbol.html:929` | `fctClearPersistedStates` 遍历 localStorage | **合理保留**（原有注释） |
| 8 | `symbol.html:1439` | `paneOrder()` 读 localStorage + JSON.parse | **合理保留**（原有注释） |
| 9 | `symbol.html:1449` | `setPaneOrder` 写 localStorage | **合理保留，补注释**（见 §1.2.1） |
| 10 | `symbol.html:1795/1810` | `klinePixelToPoint` / `klinePointToPixel` 的 `convertFromPixel` | **合理保留**（防未来数据红线的降级路径，注释说明） |
| 11 | `symbol.html:1856` | `klineDrawLoad()` | **合理保留**（R3-2 已修 TDZ；这条 catch 现在吞的只有 JSON 损坏） |
| 12 | `price-scale.js:166/176` | canvas 2d context / `measureText` | **合理保留**（无 canvas 环境降级） |
| 13 | `night-mode.js:58` | 写主题 localStorage | **合理保留** |

**13 条全部是"环境缺失"语义（localStorage 被禁 / JSON 损坏 / canvas 不可用），
没有一条在吞代码缺陷。**

#### §1.2.1 本轮实测抓出并修掉的 2 处

A 类扫描器要求「每条静默 catch 都必须能在同一行或上一行找到理由注释」，
**13 条里有 2 条不满足**——它们能吞，但从没写下来为什么：

| 位置 | 问题 | 修法 |
|---|---|---|
| `symbol.html:554` | `try { inst.dispose(); } catch (e) {}` 无注释 | 补注释：dispose 抛错只可能是实例已被外部销毁（主题切换/热更），此时目标已达成；**并注明不得改成 `return`**——后面还要清空容器 DOM |
| `symbol.html:1449` | `setPaneOrder` 的 `catch (e) {}` 无注释 | 补注释：隐私模式下副图顺序仅本次会话生效，不持久化 |

这两条不是"会炸的 bug"，是**可维护性欠债**：下一个读代码的人无法判断该 catch 是
兜底还是掩盖。任务书要求"枚举每一条"，所以修。

### 1.3 B 类 · TDZ / 声明顺序 —— 静态 0 命中 + 冷启动实测全恢复

**静态扫描**（模块级 `const/let` 初始化器是否引用后声明的绑定）：**0 命中**。
`symbol.html` 现有 33 条模块级声明（L154–L1780）逐对核对，无前向引用。
R3-2 修的 `KLINE_DRAW_LS_KEY`(L992) → `klineDrawState`(L993) 顺序保持。

**实测**（推广 t4 的全新 context 法，`.tmp/perf-browser/coldstart_all_keys.py`）：
预置**全部 7 个持久化键**后冷启动，逐个断言特性真的恢复：

```
drawings: 1  (horizontal)          [OK] 画线恢复
paneOrder: ["macd_", "rsi_14"]     [OK] 副图顺序恢复
priceMode: 2                       [OK] 价格轴模式恢复（百分比）
chipEma5: "pane"                   [OK] chip 态恢复
chipMacd: "hidden"                 [OK]
paramChoices: {"macd": "12_26_9"}  [OK] 参数选择恢复
theme: "dark"                      [OK] 主题恢复
pageerrors: 0                      [OK] 冷启动零 pageerror
```

这是 R3-2 那条单键测试的**推广版**：原来只 seed `qre.kline.drawings`，现在把
`qre_pane_order` / `qre.kline.priceScaleMode` / `qre_fct_*` / `qre.kline.params` /
`qre-theme` 全部 seed 上——任何一个特性的恢复路径有 TDZ/静默 catch，这里立刻现形。

### 1.4 C 类 · `|| undefined` 条件键 —— 0 命中 + 一个"看似命中"的判定

**签名扫描**（`key: x || undefined` / `|| null`）：**0 命中**。

有一个**形态相近但性质不同**的点，我判它**不需要改**，理由记录备查：

`symbol.html:1711` `markLine: klineLastPriceMarkLine()` —— `klineLastPriceMarkLine()`
在 `QREPriceScale` 未加载 / 无 K 线 / 末价非有限值时 `return undefined`，
于是 `markLine` 键存在而值为 `undefined`，**字面形态与 bug 1 相同**。

**但它不炸**，实测证明（`.tmp/perf-browser/probe_markline_undef.py`）：
把 `window.QREPriceScale` 置空后调 `renderKline(klineDetail)`，
`threw: null`、`pageerrors: 0`。

原因：bug 1 的炸点是 `legend.selected`——ECharts 的 `LegendModel.isSelected()`
会**无条件**读 `selected.hasOwnProperty(name)`；而 `markLine` 是 series 级配置，
值为 `undefined` 时 ECharts 走"无 markLine"分支，不解引用。

**结论**：C 类的判定标准应该是"该键的消费方是否会不解引用就取属性"，
不是"值是否为 undefined"。已在守卫测试里同时锁两边：
`test_no_or_undefined_conditional_key`（签名，0 命中）+
`test_replay_legend_selected_written_only_when_present`（R3-2 修复写法保持）。

### 1.5 D 类 · 回调异常不可见 —— 真实浏览器驱动全部热路径，零 pageerror

新建 `.tmp/perf-browser/d_class_hotpath.py`，一条链路驱动 7 段热路径：

```
[1] 页面加载                          pageerrors: 0
[2] 重播自动播放 ~30 帧（rAF 热路径）   pageerrors: 0
[3] 单步 ×10 + 后退 ×10 + 空仓快进     pageerrors: 0
[4] chip 三态循环 ×3 + 重置布局        pageerrors: 0
[5] 价格轴四态循环 + 量/因子开关        pageerrors: 0
[6] 画线：趋势线 + 水平线 + 清除        pageerrors: 0
[7] 指标设置模态 + 主题明暗切换         pageerrors: 0
D 类热路径 pageerrors 总计: 0   → PASS
```

`replay.js` 的 rAF 回调（bug 1 的炸点所在路径）被 [2][3] 两段覆盖了 40+ 帧。

### 1.6 守卫测试（防回归）

新建 `tests/test_no_silent_failure_patterns.py`（8 例，全绿）：

| 用例 | 锁什么 |
|---|---|
| `test_every_silent_catch_has_a_reason_comment` | 每条静默 catch 必须有理由注释（本轮 2 处欠债即由此抓出） |
| `test_no_catch_swallows_reference_or_type_error_silently` | `return []` 兜底必须在**持久化读取路径**上（函数体内有 `localStorage.getItem`/`JSON.parse`），不得在渲染/计算路径 |
| `test_no_module_level_tdz_forward_reference` | 模块级 const/let 零前向引用（B 类根治） |
| `test_kline_draw_ls_key_before_state` | R3-2 修复的源码顺序 |
| `test_no_or_undefined_conditional_key` | C 类签名 0 命中（去注释后断言） |
| `test_replay_legend_selected_written_only_when_present` | R3-2 修复的 legend 写法 |
| `test_hotpath_verify_script_exists_and_asserts_zero_pageerrors` | D 类覆盖脚本存在（防覆盖退化） |
| `test_tv_entry_script_registers_three_criteria` | R4-2 入口覆盖三条判据 |

**关于敏感度校验**：B/C/D 三类的修复在 R3-2 已带敏感度校验
（`test_kline_draw_restore_tdz.py` 第三例把顺序改回 bug 写法断言恢复失败）。
本轮**新增的修复只有 A 类两条注释**，不改变运行时行为，故不需要敏感度校验——
若要验，把注释删掉即红（`test_every_silent_catch_has_a_reason_comment` 直接失败），
这是即时可验的。

---

## 2. R4-2 · 判据自解释 + game 常规回归

### 2.1 环境段（§1.2 的落地）

判据输出新增 `ENV` 行，含 pane 几何 + 容器像素 + 视口 + DPR：

**symbol（百分比制）**：
```json
{"container":{"w":1298,"h":640,"clientW":1298,"clientH":640},
 "viewport":{"w":1440,"h":1000,"dpr":1},
 "paneGeometry":[{"gridIndex":0,"top":30,"height":"42%","pxTop":30,"pxHeight":269},
                 {"gridIndex":1,"top":"53%","height":"10%","pxTop":339,"pxHeight":64},
                 {"gridIndex":2,"top":"66%","height":"25%","pxTop":422,"pxHeight":160}]}
```

**game（像素制）**：
```json
{"container":{"w":1062,"h":908},
 "paneGeometry":[{"gridIndex":0,"top":22,"height":533},
                 {"gridIndex":1,"top":561,"height":117},
                 {"gridIndex":2,"top":684,"height":204}]}
```

**效果**：`px` 漂移从此自解释。以 R3-1 为例——MACD pane `top:66% / height:25%`
在容器 640px 下 = `pxTop 422 / pxHeight 160`，pane 中心 y ≈ 502，与实测
`px 502.4` 对得上；改成 20.25% 时 pane 矮 30px，px 必然落到 487.2。
**不需要人判"这是回归还是预期"**——几何写在输出里，算术可复算。

game 侧的环境段更重要：它的 `chartLayout` 是像素制，`px=888` 只有在记录容器
908px 高后才可复现。

### 2.2 一行化入口

`.tmp/perf-browser/tv_check_all.sh`：

```bash
.tmp/perf-browser/tv_check_all.sh     # 全跑
```

覆盖 6 项：判据① symbol 静态图 / ② 回放键盘往返 / ③ 画线交互（含页面重启恢复）/
④ game.html / D 类热路径 / B 类冷启动全键恢复。**全绿输出**见 §2.3。

**一处自我修正**：入口最初写成"跑 before + after 两次 `tv3_verify.py`，
输出 `tv3_criterion_{before,after}.txt`"——但 before 需要 `git stash` 真实回退代码，
脚本不动工作区，所以两次输出**逐字节相同**（我实测发现并修掉了）。
现在入口只跑当前代码一次；要做改动前后对比时手动 stash，脚本头部写了命令。
**教训**：一个"看起来在对比"的脚本比没有脚本更坏——它会生产假的对照证据。

### 2.3 一次全绿输出（节选）

```
== 0/4 渲染页面与 fixture ==          rendered pages: ['/saas/jobs/1', '/saas/jobs/1/symbols/000001.SZ']
== 1/5 判据① symbol 静态图 ==          R3_ASSERT histZeroLine=YES paneH=25% + ENV
== 2/5 判据② 回放 ==                   [OK] 100 次往返零漂移 / [OK] 零 pageerror
== 3/5 判据③ 画线交互 ==                [OK] 页面重启后逐字段一致
== 4/5 判据④ game.html ==              GAME_ASSERT macdSameAxis=true + ENV
== D 类 热路径 pageerrors===0 ==        D 类结论: PASS
== B 类 冷启动全键恢复 ==               B 类冷启动全键恢复: PASS
TV_CHECK_ALL DONE
```

---

## 3. R4-3 · 模板内联 JS 语法守卫

### 3.1 测试

`tests/test_template_inline_js_syntax.py`（**27 passed, 10 skipped**）：

- 扫**所有**模板（`gui/` + `game/` 递归，参数化到每个文件 × 每个内联 script）；
- Jinja `{{ }}` → `null`、`{% %}` → 空（保行号）后 `node --check`；
- `test_every_template_covered` 锁 8 个必须被扫到的模板名，防新增模板静默漏扫；
- 10 个 skip 是无内联 script 的模板（如纯静态片段）。

### 3.2 事故写法红灯复现（§7 回传第 3 项）

复现方式：把 R3-4 那次事故**原样注入** `symbol.html`——从
`left.appendChild(reset);` 之后直接接到 `function renderKline(d){`，
即删穿 `klineIndicatorDialog()` 的函数体后半与闭合括号。

```
注入事故写法 → 1 failed, 26 passed
  FAILED tests/test_template_inline_js_syntax.py::test_inline_js_syntax_ok[symbol.html]
  assert 1 == 0
  Node.js v18.19.1（node --check returncode=1，SyntaxError）

恢复原文件 → 27 passed, 10 skipped
```

**复现成功**：守卫对「删注释删穿函数体」立即红灯，且报错直指
`symbol.html` 的具体 script 块——不再是 R3-4 那次"离根因极远"的
`未找到 lwcDispose / klineDisposeEngines`。

`TestAccidentReproduction` 里还内置了一个**自存档的坏样本**
（`ACCIDENT` 常量，不依赖改动工作区）+ 一个补完整后必须通过的对照例
（证明不是见函数名就红）。

---

## 4. R4-4 · MACD 旧系退场：事件触发制

### 4.1 周扫脚本 + 首扫（§7 回传第 4 项）

`deploy/saas/scan-macd-legacy-names.sh`（`--record` 追加日志）：

```text
scanned_files 1013
legacy_job 58 263
legacy_job 66 233
legacy_total 496

本次周扫：仍有 496 个产物含旧系名 → 不满足退场条件①
```

**首扫结论**：ECS 上 10 个 job 共 1013 个 per-symbol 产物里，**496 个含旧系名**，
全部集中在 **job 58（263）+ job 66（233）**——正是 2026-10-24 生成的两个 MACD
经典策略。其余 8 个 job（含 10-28 之后的 78/79/80）**旧系计数为 0**，
说明新产物确实一律走新系命名，双列名没有继续扩散。

**触发条件判定**：条件①要求**连续 4 次周扫计数为 0**，当前 496，远不满足；
条件②（旧 job 归档/过期）也未满足。→ **旧系分支继续保留**。

### 4.2 政策已写入长期文档

`20_DATA_DICTIONARY_DAILY_MINUTE.md` 新增 §4.1.1：
- 两条触发条件（连续 4 次周扫为 0 + 旧 job 归档/过期）；
- 周扫脚本路径与 `--record` 用法（建议挂 systemd timer 每周一次）；
- 退场动作范围（删 `familyOf` 旧名分支 + 判据脚本警示退场）；
- **明确不删** `extra_aliases` 旧名别名（入口层成本≈0，防 NL 断链）；
- 首扫结果留档。

---

## 5. 测试基线与可复核数字

| 口径 | ROUND4 开工前 | 现在 |
|---|---|---|
| 全量 | 3170 passed, 24 skipped | **3205 passed, 34 skipped, 0 failed** |

（skipped 从 24 → 34：新增的模板守卫测试参数化到 37 个模板 × script 块，
其中 10 个无内联 script 的模板 skip。）

可独立复核：

```bash
cd /home/van/quant-workspace/quant-research-engine-dual-agent-lab
# R4-1 四类守卫
uv run pytest tests/test_no_silent_failure_patterns.py -q            # 8 passed
# R4-2 三判据 + D/B 类全绿
.tmp/perf-browser/tv_check_all.sh
# R4-3 模板语法守卫（含事故自档案）
uv run pytest tests/test_template_inline_js_syntax.py -q             # 27 passed
# R4-4 周扫
./deploy/saas/scan-macd-legacy-names.sh --record
```

---

## 6. R4-5 · 产物侧参数变体（原样呈报，未实施）

按任务书要求**只备料不拍板**，以下原样转呈产品负责人：

**现状事实**：job 78 `_symbol_details/` 17M > 15 MiB 上限**已截断**（184 文件）；
每股加 3 组 MACD × 3 列 ≈ +100KB（gzip 后 10–12KB/列·股）；产物体积约翻倍 →
15 MiB 下个股覆盖数约减半。

| 选项 | 代价 | 与「稳定性第一」的关系 |
|---|---|---|
| A. 维持现状（参数网格休眠，前端就绪） | 用户暂无切参数能力 | 零风险，完全一致 |
| B. 全量下发变体 | 覆盖数减半 | 冲突（OOM 刚修，用户要求留阈值空间） |
| C. 仅对高频查看 TOP-N 标的下发（如前 20） | 增量有界（≈2MB/job） | 可控，实验性质 |
| D. 提高上限 15→24 MiB | 内存压力回归 | 直接冲突 |

**逆向侧技术意见**：回测查看器主场景是「看策略用了什么参数」，变体是探索型锦上添花。
推荐 **A**；确有用户提出需求再走 **C**。B/D 不推荐。

**用户当前裁决（2026-10-29 口头）**：「R3-3 保持灵活性」→ 即**选 A，维持原状**。
本轮据此**未动** `_strategy_factor_specs`、未改 `SYMBOL_DETAILS_MAX_BYTES`。
若后续改走 C，需先解决 15 MiB 上限与截断策略的相互作用（当前截断按
`abs(total_pnl)` 降序保头部，TOP-N 与之叠加的语义要先定义）。

---

## 7. 给逆向侧的两个确认请求

1. **C 类判定标准**：我把「键在值为 `undefined`」细化为「**该键的消费方是否不解
   引用就取属性**」。`markLine: klineLastPriceMarkLine()` 字面形态与 bug 1 相同但
   实测不炸（ECharts 对 series 级 `markLine: undefined` 走无配置分支，而
   `legend.selected` 会被 `isSelected()` 无条件解引用）。这个细化是否认同？
   若认同，建议写进下一轮任务书的模式定义，避免后来者把 `markLine` 也改一遍。
2. **A 类"理由注释"要求**是否要提升为长期纪律（进 `AGENTS.md`）？本轮 13 条里
   2 条缺注释，补 Comments 的成本极低，但能防"下一个人无法判断该 catch 是兜底
   还是掩盖"。

---

## 8. 下一轮建议（我方视角）

| 建议 | 理由 |
|---|---|
| 周扫 timer 落地 | `scan-macd-legacy-names.sh` 已就绪，建议挂 systemd timer 每周跑并 `--record`；否则"连续 4 次"无从计数 |
| 判据环境段进 game 的常规回归 | 已有；建议每轮 TV 化验收清单固定带 `tv_check_all.sh` 一条命令 |
| A 类注释纪律化 | 见 §7.2 |
| 旧系退场的第二个触发条件要可判定 | "旧 job 已归档或按保留期过期"目前无机械判定方式，建议定义保留期（如 90 天）让条件②也可脚本化 |
