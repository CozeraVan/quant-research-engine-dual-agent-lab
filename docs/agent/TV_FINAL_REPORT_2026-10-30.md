# TV_FINAL_REPORT_2026-10-30 · TradingView 化收官报告

> **性质**：TV 化（对照 TradingView 的四功能改造）收官交付。
> **读者**：产品负责人 / 后续维护者 / 逆向 Agent。
> **范围**：ROUND1 圈定的「① K线呈现 ② 作图 ③ 指标 ④ 回放」+ 明确不做清单。
> **结论**：**收官**。ROUND1 范围内无工程欠账；剩余缺口全部为有意偏离或用户裁决。

---

## 1. 最终记分卡

口径直接引用 `docs/agent/TV_ROUND5_TASKS_2026-10-30.md` §7（逆向侧评分）。

| 功能 | ROUND1 基线 | 现在 | 依据（改动锚点） |
|---|---|---|---|
| **① K线呈现** | 70%（功能 85 / 视觉 55） | **95%** | **T1** 共享 option 映射层（三处调用点 + `assertPaneInvariant` 不变式 + 零手写 pane 索引）；**T2** 四态价格轴（普通/对数/百分比/指数化）+ 1-2-5 刻度 + 恒定轴宽 + 末价标签背景块 + 十字光标 1px 虚线；**R3-1** MACD 零基线 + 单 pane 高度 20.25%→25% + `klineGridSpec` 收敛为 `paneGrids` 委派壳（消灭会漂移的第二份实现）；**R4-1** 四类「单测绿生产炸」模式清扫。**剩余**：顶 8px / 底 26px 留白近似（逆向侧已接受） |
| **② 作图** | 8% | **90%**（2 工具边界内） | **T4** 全套交互：端点拖拽（7px 命中半径）/ 整体拖动 / 单线 Delete / 光标反馈 + `localStorage` 持久化；**R3-2** 修复「持久化自上线起从未在生产生效」的 TDZ bug 并用真实浏览器冷启动验证；重播态画线禁用纪律保持。**边界**：只做趋势线 + 水平线两条，不扩工具种类（逆向侧 §5 裁定） |
| **③ 指标** | 90% | **95%** | 895 列宽表 + `QRE-FACTOR-DISPLAY-CONTRACT` display 合同（chart_type/panel_id/role/series_type/axis/precision/color/price_basis/render_order）；**R3-5** 双列名入口层收敛（旧系 `macd_dif/dea/hist` 别名映射新系 canonical，防 NL 断链）；**R4-3** 数据侧核验闭环（纯 numpy 独立重算，4 组 MACD 参数 × 3 列 × 4244 根全量历史，全部落在 DB 2 位小数舍入界内）。**参数网格前端就绪、休眠为用户裁决 A** |
| **④ 回放** | 85% | **95%** | **T3** 单步后退 + 键盘（空格播放/暂停、←/→ 单步、快进）；**R3-2** 真实浏览器 **前进 100 + 后退 100 次光标 0→100→0，八项指标漂移 < 1e-9**；防未来数据实测（x 轴末根 = 当前帧日期） |
| **⑤ 协议层** | N/A | **N/A（定案）** | 不接 tradingview.com；ws `~m~<len>~m~` 分帧事实已由双方更正归档（我方原引用的错误结论已作废） |

**ROUND1 范围判定：收官。剩余缺口全部为有意偏离或用户裁决，无工程欠账。**

---

## 2. 偏离清单（全部是有意决策，逐条附理由）

| # | 偏离 | 理由 | 裁定方 |
|---|---|---|---|
| 1 | **蜡烛涨跌色用 A 股红涨绿跌**（`#C93A3A`/`#1E8E5A`），未用 TV 国际默认青红 | A 股回测查看器，红涨绿跌是该市场正确语义（TV 自己也随 locale 翻转）；全站涨跌语义统一 | 逆向侧裁定通过（ROUND3 §1.3），ROUND3 及以后有效 |
| 2 | **画布/面板底色交给主题层**，未硬编码 TV 深色 | 硬编码会与夜间模式架构冲突；主题层是正确架构 | 逆向侧裁定通过 |
| 3 | **只做 2 种画线工具**（趋势线/水平线），不做 94 工具 | 「半成品比没有更伤信任」；两条做完整（拖拽/删除/持久化/光标反馈全有）比九十四条半吊子值钱 | 逆向侧 §5 主动收窄 |
| 4 | **参数网格休眠**（前端就绪、数据侧已完工、产物侧不下发变体） | 用户裁决「R3-3 保持灵活性」= 选 A。事实：`SYMBOL_DETAILS_MAX_BYTES = 15 MiB` 已打满（job 78 实测 17M 已截断），加 3 组 MACD 变体使产物体积约翻倍、个股覆盖数减半——与「稳定性第一」冲突 | **用户裁决 A** |
| 5 | **LWC 已移除**（非冻结） | T6 先冻结入口，R3-4 按「解冻从 git 历史找回比养着 400KB 死码便宜」整体删除。实测省 219,208 B ≈ 214 KiB 传输 + 276 行死代码 | 逆向侧推荐并采纳 |
| 6 | **Pine 解析器不做** | ROUND1 明确不做清单 | ROUND1 |
| 7 | **TV datafeed 协议不接** | 不接 tradingview.com；`~m~` 分帧事实已归档 | ROUND1 |
| 8 | **顶 8px / 底 26px 留白近似** | 未改既有布局；逆向侧接受不再要求精确 | 逆向侧 |

---

## 3. 资产清单（各自锁什么、怎么跑）

### 3.1 判据三件套 + 入口

| 资产 | 锁什么 | 怎么跑 |
|---|---|---|
| `.tmp/perf-browser/tv3_verify.py` | MACD 同坐标系判据（恒等项：`yAxis==grid`、三 series 同索引、probe 同 y 映射、`AXIS_RANGES` 逐值）+ R3-1 零基线与 25% + **环境段**（pane 几何/容器/视口/DPR） | `.tmp/browser-venv/bin/python .tmp/perf-browser/tv3_verify.py after` |
| `.tmp/perf-browser/t3_verify.py` | 回放：后退夹紧、键盘不劫持输入框/模态、**100 次往返八指标零漂移**、防未来数据 | `.tmp/browser-venv/bin/python .tmp/perf-browser/t3_verify.py` |
| `.tmp/perf-browser/t4_verify.py` | 画线：端点拖拽只动被抓端点、整体拖动同差平移、单线 Delete、光标反馈、**页面重启后逐字段恢复** | `.tmp/browser-venv/bin/python .tmp/perf-browser/t4_verify.py` |
| `.tmp/perf-browser/tv3_game_verify.py` | game.html 同判据（静态 fixture，无 DB 依赖，成本≈0） | `.tmp/browser-venv/bin/python .tmp/perf-browser/tv3_game_verify.py` |
| `.tmp/perf-browser/probe_markline_undef.py` | C 类消费方语义的实证：`markLine: undefined` 不炸（置空 `QREPriceScale` 后 `renderKline` threw=null、pageerrors=0） | `.tmp/browser-venv/bin/python .tmp/perf-browser/probe_markline_undef.py` |
| **`.tmp/perf-browser/tv_check_all.sh`** | **一行化入口**：上面全部 + D 类热路径 + B 类冷启动全键恢复 | `.tmp/perf-browser/tv_check_all.sh` |

### 3.2 守卫测试

| 测试 | 例数 | 锁什么 |
|---|---|---|
| `tests/test_no_silent_failure_patterns.py` | **11** | 四类「单测绿生产炸」模式：A 静默 catch 必须有理由注释且只在持久化读取路径 `return []`；B 模块级 const/let 零 TDZ 前向引用 + R3-2 修复顺序；C 无 `|| undefined` 条件键 + **消费方语义**（`markLine` 不许改、`legend.selected` 必须缺就不写键）+ probe 必须落盘；D 覆盖脚本存在 |
| `tests/test_template_inline_js_syntax.py` | **27**（+10 skip） | 所有模板内联 JS `node --check`；含 R3-4「删注释删穿函数体」事故的**自档案坏样本**与红灯复现 |
| `tests/test_kline_draw_restore_tdz.py` | **3** | R3-2 TDZ 修复 + **敏感度校验**（改回 bug 写法必须恢复失败） |
| `tests/test_kline_pane_option.py` | **16** | T1 共享层 + R3-1 零基线/25% + 与 Python 等价实现**逐值**交叉验证 |
| `tests/test_kline_param_grid.py` | — | T5 参数网格：单参数组时逐字节原样返回（存量产物零影响） |
| `tests/test_lwc_kline_removed.py` | **11** | R3-4：LWC 资产不被引用/加载、模板 ≤2350 行防半删、单引擎路径完整 |
| `tests/test_factor_param_variants_data.py` | **2** | R4-3：MACD 4 组参数变体在库 + 纯 numpy 独立重算逐值一致 |
| `tests/test_price_scale.py` | **15** | T2 价格轴四态 + 1-2-5 + 恒定轴宽 + 末价标签 |

---

## 4. 稳态机制

### 4.1 每轮 TV 相关改动，提交前跑什么

已写进 `AGENTS.md` 的 **TV Acceptance Checklist**：

```bash
.tmp/perf-browser/tv_check_all.sh
uv run pytest tests/test_no_silent_failure_patterns.py tests/test_template_inline_js_syntax.py -q
```

触发条件：凡改 **K 线 / 因子 pane / 画线 / 重播** 相关代码。
模板改动后另需 `node --check` 所有 inline script（先替换 Jinja）。

### 4.2 每周 timer 跑什么

`qre-macd-legacy-scan.timer`（已安装到 `/etc/systemd/system/` 并 enable）
每周一 03:17 跑 `deploy/saas/scan-macd-legacy-names.sh --record`，
输出 append 到 `.tmp/macd-legacy-scan.timer.log`，计数追加到
`.tmp/macd-legacy-scan.log`。`Persistent=true`，错过开机补跑。

### 4.3 退场条件何时判定

`familyOf` 旧系 MACD 分支的退场，**两条条件均由周扫脚本机械判定**：

1. 连续 4 次周扫旧系计数为 0；
2. 所有含旧系的 job 均已过期（`> LEGACY_RETENTION_DAYS`，默认 **90 天**）或已归档。

当前状态（2026-10-30 首跑）：496 个产物含旧系名（job 58: 263 / job 66: 233，
年龄 4.9 天，`active`）→ **两条均不满足，旧系分支继续保留**。
按 90 天保留期，这两个 job 约在 2027-01-22 之后才满足条件②。

---

## 5. 收官核验跑数字（2026-10-30）

三个数字，可复核命令附后。

### 5.1 全量测试

```
3208 passed, 34 skipped, 6 warnings in 409.45s
```

```bash
uv run pytest -q -p no:randomly
```

### 5.2 TV 判据三件套（+ D/B 两类）

```
symbol 静态图 : yAxis 3 grid 3；三 series 同 yAxisIndex:2/gridIndex:2；
                probe 三者同 y 映射；AXIS_RANGES -2.945691/2.867473；
                HIST 零基线 [{yAxis:0}] silent/dashed/1；
                pane 高度 25%（paneGeometry pxHeight 160 @ 容器 640px）
replay        : 前进 100 + 后退 100 → 光标 0→100→0，八指标漂移 < 1e-9；零 pageerror
game.html     : yAxisLen 3 == gridLen 3；DIF/DEA/HIST 同 yAxisIndex 2、px 全 888；
                macdSameAxis=true；零基线自动延伸；容器 1062×908 已记录
D 类热路径    : 7 段（加载/播放30帧/单步后退快进/chip三态/价格轴四态/画线/模态+主题）
                pageerrors 总计 0
B 类冷启动    : 预置全部 7 个持久化键，画线/副图顺序/价格轴模式/chip态/参数选择/主题
                逐个断言恢复，零 pageerror
```

```bash
.tmp/perf-browser/tv_check_all.sh
```

### 5.3 周扫首扫

```
scanned_files 1013
legacy_job 58 263
legacy_job 66 233
legacy_total 496
legacy_age 58 4.9 active
legacy_age 66 4.9 active
retention_days 90
>>> 退场条件未满足，familyOf 旧名分支继续保留 <<<
```

```bash
./deploy/saas/scan-macd-legacy-names.sh --record
```

---

## 6. 三条长期纪律（已进 `AGENTS.md`）

由 R3-2 两个「单测全绿、生产炸」真 bug 提炼，**测试机器强制**：

1. **静默 catch 必须带理由注释**（同行或上一行）；新写无注释的 `catch (e) {}`
   视为未完成。合理吞只有「环境缺失」语义。
2. **条件键：缺就不写键**（新代码风格）；存量按**消费方是否不解引用就取属性**
   判定去留（炸例 `legend.selected`，不炸例 series 级 `markLine`）。
   **判定标准宽了，写作标准不放宽。**
3. **证据位置必须真实存在**：回传/文档/CR 引用的脚本、截图、输出文件，
   落盘后才许引用。`.tmp/` 是 scratch，但被引用的 scratch 就是证据。

---

## 7. 给后续维护者的话

- **改 K 线/factor pane/画线/重播前，先跑 `tv_check_all.sh` 建立基线**；
  改完再跑一次，两边输出 diff 只看**恒等项**（`yAxis==grid`、同家族 series 索引、
  probe 同 y 映射、`AXIS_RANGES`），**`px` 绝对值是环境项**——环境段会告诉你几何。
- **ECharts 升级时**（现 5.6.1）：D 类热路径跑一遍即可证伪「`markLine: undefined`
  不炸」这条版本绑定假设；`legend.selected` 那条与版本无关（我们自己缺就不写键）。
- **参数网格若要唤醒**（用户改走 C）：先定义 TOP-N 与现有截断序
  （`abs(total_pnl)` 降序保头部）的叠加语义，再动 `_strategy_factor_specs`。
