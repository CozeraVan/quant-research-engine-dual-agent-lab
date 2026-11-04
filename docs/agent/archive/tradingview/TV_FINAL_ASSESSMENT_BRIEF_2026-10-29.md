# TV_FINAL_ASSESSMENT_BRIEF_2026-10-29 · TradingView 化全量成果清单（供逆向侧最终评估）

> **性质**：TV 化（对照 TradingView 的四功能改造）**全轮次汇总**，供逆向 Agent 做**最后一次评估**。
> 它不是新一轮任务书，也不替代任何轮次文档——只是把 ROUND1→ROUND6 + 维护期 + 归档动作
> 的全部成果收敛到一处，免去逐份翻读。
> **读者**：逆向 Agent（评估方）/ 产品负责人。
> **结论**：TV 化已收官（逆向侧 `TV_ROUND6_TASKS` §1 签收，无保留意见），
> 本文档补齐签收之后的 R6-2/R6-1、`TV_MAINT_NOTES` 两条收尾、以及用户裁定的**产物归档**。

---

## 1. 轮次时间线与文档索引

| 轮次 | 日期 | 主题 | 任务书 → 回传 |
|---|---|---|---|
| 首片 | 10-27~28 | K 线 TV 化首片 / 旧 MACD 别名合并同副图 / 重播 TV 化 / 双引擎互斥（修 TV 视图叠加 bug）/ 指标设置与面板管理 / LWC 受控试点 | CR-2026-10-27_* / CR-2026-10-28_* |
| ROUND1 | 10-28 | 圈定范围「① K线 ② 作图 ③ 指标 ④ 回放」+ 明确不做清单；我方反馈 | `TV_FEEDBACK_2026-10-28.md` |
| ROUND2 | 10-29 | T1 共享 pane option 映射层 / T2 价格轴框架 / T3 回放后退+键盘 / T4 画线交互 / T5 参数网格前端 / T6 冻结 LWC | `TV_ROUND2_TASKS_2026-10-29.md` → `TV_ROUND2_ANSWER_2026-10-29.md` |
| ROUND3 | 10-29 | R3-1 MACD 零基线 + pane 25% + `klineGridSpec` 收敛 / R3-2 画线持久化 TDZ bug（自上线从未生效）/ R3-3 参数网格数据侧 / R3-4 移除 LWC / R3-5 双列名收敛 | `TV_ROUND3_TASKS_2026-10-29.md` → `TV_ROUND3_ANSWER_2026-10-29.md` |
| ROUND4 | 10-30 | R4-1 四类「单测绿生产炸」模式全库清扫 / R4-2 一行化验收入口 / R4-3 数据侧核验闭环 / R4-4 周扫机制 | `TV_ROUND4_TASKS_2026-10-29.md` → `TV_ROUND4_ANSWER_2026-10-30.md` |
| ROUND5 | 10-30 | 收官轮：AGENTS.md 两条纪律 + 周扫 systemd timer + 条件②机械化 + 收官报告 + probe 落盘 | `TV_ROUND5_TASKS_2026-10-30.md` → `TV_ROUND5_ANSWER_2026-10-30.md` |
| **签收** | 10-30 | 逆向侧独立核验全部通过，**判定收官、无保留意见** | `TV_ROUND6_TASKS_2026-10-30.md` §1 |
| R6 | 10-29~30 | R6-2 保留期 90→15（用户确认）/ R6-1 周扫日志证据链持久化 | `TV_ROUND6_TASKS_2026-10-30.md` → `TV_ROUND6_ANSWER_2026-10-30.md` §2/§3 |
| 维护备忘 | 10-30 | 复核签收补充：journal 双保险实操验证 + 退场前置动作 | `TV_MAINT_NOTES_2026-10-30.md` → `TV_ROUND6_ANSWER_2026-10-30.md` §4 |
| **归档** | 10-29 | 用户裁定「归档」：496 个旧系产物移出 uploads + 详情页归档回落 | `change_requests/CR-2026-10-29_artifact_archive.md` |

**收官报告**（ROUND5 时点）：`TV_FINAL_REPORT_2026-10-30.md`。
本文档与该报告不重复记分卡细节，只做**增量汇总 + 全量索引**。

---

## 2. 最终记分卡（引自 `TV_ROUND5_TASKS` §7 逆向侧评分，签收维持）

| 功能 | ROUND1 基线 | 现在 | 关键锚点 |
|---|---|---|---|
| ① K线呈现 | 70%（功能 85 / 视觉 55） | **95%** | T1 共享 option 映射层（三处调用点 + `assertPaneInvariant` 不变式 + 零手写 pane 索引）；T2 四态价格轴（普通/对数/百分比/指数化）+ 1-2-5 刻度 + 恒定轴宽 + 末价标签背景块 + 十字光标 1px 虚线；R3-1 MACD 零基线 + 单 pane 20.25%→25% + `klineGridSpec` 收敛为 `paneGrids` 委派壳；R4-1 四类静默失败模式清扫 |
| ② 作图 | 8% | **90%**（2 工具边界内） | T4 端点拖拽（7px 命中半径）/ 整体拖动 / 单线 Delete / 光标反馈 + `localStorage` 持久化；R3-2 修复「持久化自上线起从未在生产生效」的 TDZ bug 并真实浏览器冷启动验证 |
| ③ 指标 | 90% | **95%** | 895 列宽表 + `QRE-FACTOR-DISPLAY-CONTRACT` display 合同（chart_type/panel_id/role/series_type/axis/precision/color/price_basis/render_order）；R3-5 双列名入口层收敛；R4-3 数据侧核验闭环（纯 numpy 独立重算，4 组 MACD 参数 × 3 列 × 4244 根全量历史，全部落在 DB 2 位小数舍入界内） |
| ④ 回放 | 85% | **95%** | T3 单步后退 + 键盘（空格/←/→/快进）；R3-2 真实浏览器**前进 100 + 后退 100，八项指标漂移 < 1e-9**；防未来数据实测 |
| ⑤ 协议层 | N/A | **N/A（定案）** | 不接 tradingview.com；ws `~m~<len>~m~` 分帧事实已由双方更正归档（我方原引用的错误结论已作废） |

---

## 3. 偏离清单（全部有意决策，逐条附理由与裁定方）

| # | 偏离 | 理由 | 裁定方 |
|---|---|---|---|
| 1 | 蜡烛涨跌色用 A 股红涨绿跌（`#C93A3A`/`#1E8E5A`），未用 TV 国际默认青红 | A 股回测查看器的正确语义；全站涨跌语义统一 | 逆向侧（ROUND3 §1.3） |
| 2 | 画布/面板底色交给主题层，未硬编码 TV 深色 | 硬编码与夜间模式架构冲突 | 逆向侧 |
| 3 | 只做 2 种画线工具（趋势线/水平线），不做 94 工具 | 「半成品比没有更伤信任」；两条做完整比九十四条半吊子值钱 | 逆向侧 §5 主动收窄 |
| 4 | 参数网格休眠（前端就绪、数据侧完工、产物侧不下发变体） | `SYMBOL_DETAILS_MAX_BYTES = 15 MiB` 已打满（job 78 实测 17M 已截断），加 3 组 MACD 变体使产物体积约翻倍、个股覆盖减半，与「稳定性第一」冲突 | **用户裁决 A** |
| 5 | LWC 整体移除（先 T6 冻结入口，再 R3-4 删除） | 「解冻从 git 历史找回比养着 400KB 死码便宜」；实测省 219,208 B ≈ 214 KiB 传输 + 276 行死代码 | 逆向侧推荐并采纳 |
| 6 | Pine 解析器不做 | ROUND1 明确不做清单 | ROUND1 |
| 7 | TV datafeed 协议不接 | 不接 tradingview.com；`~m~` 分帧事实已归档 | ROUND1 |
| 8 | 顶 8px / 底 26px 留白近似 | 未改既有布局；逆向侧接受不再要求精确 | 逆向侧 |

---

## 4. 代码资产清单（TV 线触碰的文件，`git ls-files` 现状）

**图表核心**
- `src/quant_research_engine/gui/static/factor-layout.js` —— 指标→pane 布局 + `familyOf` 列名归并（含旧系 MACD 分支，**见 §7 遗留**）
- `src/quant_research_engine/gui/static/price-scale.js` —— T2 四态价格轴
- `src/quant_research_engine/gui/static/replay.js` —— T3 回放（后退/键盘/100 往返零漂移）+ 画线持久化（R3-2 TDZ 修复处）
- `src/quant_research_engine/gui/static/equity-chart.js`、`perf-metrics.js`、`vol-regime.js`、`card-fx.js`、`card-class.css`、`lab-theme.css`、`lab-ui.js`、`night-mode.js` / `night-mode.css`、`help-nav.js`

**模板**
- `gui/saas/templates/`：`symbol.html`（个股 K 线主场景）、`job.html`（策略回测详情）、`showcase.html`（经典策略公开展示）、`new.html`、`profile.html`、`dashboard.html`、`help.html`、`base.html`、`strategy.html`、`_records_body.html` / `_records_scripts.html`
- `gui/templates/lab_result.html`、`lab_symbol.html`
- `game/templates/game.html` + `game/factors.py`（《我不是股神》同判据：`macdSameAxis=true`、DIF/DEA/HIST 同轴、px 全 888）

**后端 / 数据侧**
- `gui/saas/app.py` —— R6 归档回落 `QRE-SAAS-ARTIFACT-ARCHIVE`（`_symbol_detail_dirs` / `_find_symbol_detail`）
- `gui/lab_result.py`、`gui/factor_registry.py`、`gui/engine.py`、`worker/runner.py`、`risk/report.py`
- `configs/factor_registry.json` —— R3-5 旧系别名入口层收敛（**明确不删**：防 NL 断链）

**运维**
- `deploy/saas/scan-macd-legacy-names.sh`（周扫 + 两条退场条件机械判定）
- `deploy/systemd/qre-macd-legacy-scan.{service,timer}`（每周一 03:17，`Environment=LEGACY_RETENTION_DAYS=15`，stdout 走 journal）
- `deploy/saas/macd-legacy-scan.log`（R6-1 证据链，仓库内持久 + `.gitignore` negation）

**已移除（勿再找）**：`gui/static/chart-core/kline-lwc.js` + `chart-core/vendor/lightweight-charts.*`（R3-4 整体删除，仅存守卫测试 `test_lwc_kline_removed.py` 与历史文档）。

---

## 5. 验证资产与当前数字

### 5.1 判据脚本（真实浏览器，Chromium via Playwright/CDP）

| 资产 | 锁什么 |
|---|---|
| `.tmp/perf-browser/tv3_verify.py` | MACD 同坐标系：`yAxis==grid`、三 series 同索引、probe 同 y 映射、`AXIS_RANGES` 逐值 + 零基线 `[{yAxis:0}] silent/dashed/1` + pane 25% + **环境段**（pane 几何/容器/视口/DPR） |
| `.tmp/perf-browser/t3_verify.py` | 回放：后退夹紧、键盘四焦点不劫持、100 往返八指标零漂移、防未来数据 |
| `.tmp/perf-browser/t4_verify.py` | 画线：端点拖拽只动被抓端点、整体拖动同差平移、单线 Delete、重启逐字段恢复 |
| `.tmp/perf-browser/tv3_game_verify.py` | game.html 同判据（静态 fixture，零 DB 依赖） |
| `.tmp/perf-browser/probe_markline_undef.py` | C 类消费方语义实证（`markLine: undefined` 不炸） |
| `.tmp/perf-browser/verify_night_pause.py` | 夜间模式暂停四入口全落 light |
| **`.tmp/perf-browser/tv_check_all.sh`** | **一行化入口**：以上全部 + D 类热路径（7 段 pageerrors===0）+ B 类冷启动（7 键全恢复） |

### 5.2 守卫测试（当前实数，2026-10-29 复跑）

| 文件 | 例数 | 锁什么 |
|---|---|---|
| `test_no_silent_failure_patterns.py` | **18** | 四类「单测绿生产炸」模式 + 消费方语义 + probe 落盘 + 夜间模式暂停 4 例 + **归档证据链 3 例** |
| `test_template_inline_js_syntax.py` | **27**（+10 skip） | 模板内联 JS `node --check`；含「删注释删穿函数体」事故的自档案坏样本与红灯复现 |
| `test_kline_draw_restore_tdz.py` | **3** | R3-2 TDZ 修复 + 敏感度校验（改回 bug 写法必须恢复失败） |
| `test_kline_pane_option.py` | **16** | T1 共享层 + R3-1 零基线/25% + 与 Python 等价实现逐值交叉验证 |
| `test_lwc_kline_removed.py` | **11** | LWC 资产不被引用/加载、模板行数防半删、单引擎路径完整 |
| `test_price_scale.py` | **15** | T2 价格轴四态 + 1-2-5 + 恒定轴宽 + 末价标签 |
| `test_factor_param_variants_data.py` | 2 | R4-3 MACD 4 组参数变体在库 + 纯 numpy 独立重算逐值一致 |
| `test_saas_symbol_ux.py::TestSymbolDetailArchiveFallback` | **4** | 归档回落：缺省归档根 / 显式覆盖 / live 优先 / 两者皆无仍 404+can_generate |

合计 **90 passed, 10 skipped**（上述 7 个文件一次跑出）。

### 5.3 全量测试演进

| 时点 | 结果 |
|---|---|
| ROUND5 收官报告 | 3208 passed, 34 skipped |
| R6-1/R6-2 后 | 3221 passed, 34 skipped |
| 归档落地后（当前） | **3225 passed, 34 skipped** |

---

## 6. 稳态机制（收官后长期有效）

1. **每轮 TV 相关改动提交前**（已进 `AGENTS.md` · TV Acceptance Checklist）：
   `.tmp/perf-browser/tv_check_all.sh` + 两个守卫测试文件；改模板另需 `node --check` 所有 inline script。
2. **每周一 03:17**：`qre-macd-legacy-scan.timer` 自动周扫（`Persistent=true` 补跑），
   `--record` 追加到仓库内 `deploy/saas/macd-legacy-scan.log`，stdout/stderr 走 journal（双保险）。
3. **退场两条条件**（均可机械判定）：① 连续 4 次 `--record` 周扫计数为 0；
   ② 所有含旧系 job 过期（`LEGACY_RETENTION_DAYS=15`，用户确认）或已归档。
4. **三条 AGENTS.md 纪律**：静默 catch 必须带理由注释 / 条件键缺就不写键（存量按消费方语义，
   `markLine` 不许改）/ 证据位置必须真实存在。

---

## 7. 签收之后的增量（本文档重点）

### 7.1 R6-2 · 保留期 90 → **15 天**（用户 2026-10-30 确认）

service `Environment=` + 脚本 4 处默认 + 三份文档同步；`/etc/systemd/system` 的 unit 是副本，
**必须覆盖后才 daemon-reload**（只改仓库文件时 `systemctl show` 仍显示 90，实测踩到）。
退场窗口 2027-01-22 → **2026-11-08**。

### 7.2 R6-1 · 周扫日志证据链持久化

`LOG=` 从 `.tmp/` 挪到仓库内 `deploy/saas/macd-legacy-scan.log`（`.gitignore` negation；
**negation 行尾不能带 `#` 注释**，git 会把注释吃进 pattern，`git check-ignore` 复验才发现），
unit `StandardOutput/Error` 改 `journal`（原 `append:.tmp` 使 journal 无条目）。
守卫测试 3 例锁存在/内容/路径。**journal 实操验证通过**（`systemctl start` 后
`journalctl` 出现脚本输出；上一 boot 只有生命周期行，反向证明改动必要）。

### 7.3 产物归档（用户裁定「归档」，2026-10-29 执行）

- `uploads/job_{58,66}/_symbol_details`（263 + 233 个 gzip，45MB）→ `/srv/aguhuice/archive/…`；
- 配套 `QRE-SAAS-ARTIFACT-ARCHIVE`：详情页查找 **live → 归档**（58/66 是公开展示的经典策略，
  归档 ≠ 下线）；
- **归档后周扫：`scanned_files 1013 → 517`、`legacy_total 0`、条件② 满足**；
  详情页抽样 12+12 只全部 `200 / ok:true`，`/saas/showcase` 等 200。

---

## 8. 未决项与待裁决（供评估报告点名）

| # | 项 | 状态 | 决策方 |
|---|---|---|---|
| 1 | **`familyOf` 旧名分支退场**：条件① 需连续 4 次 `--record` 周扫为 0，预计 **2026-11-02/09/16/23** 四次，**11-23 之后**才可删 | 等时间表 | 产品负责人 |
| 2 | **退场后置风险**：归档产物因子名仍是旧系，靠 `familyOf` 旧名分支才能与 `macd_12_26_9` 组合流成同一副图；**直接删会让 58/66 详情页退回「三指标各自独立副图」**。三选一：展示层保留窄化映射 / 一次性改写归档 gzip 因子名 / 重跑 58/66 | **删分支前必须处理** | 产品负责人 |
| 3 | 参数网格休眠（用户裁决 A 维持） | 休眠 | 用户 |
| 4 | 波动率 `threshold` 绝对轴模式未做真实浏览器验证（fixture 是旧产物形态，只验到 relative 降级路径） | 需新跑一次回测产出带 `thresholds_annual` 的产物后线上目视 | 工程项 |
| 5 | `12_UI_STYLE_GUIDE.md` 字号基线过期（文档 H1 30/正文 15/表格 13.5，实际 32/19/16） | 待同步 | 工程项 |
| 6 | 项目主线（分钟线滞后、压缩回收、遗留库） | 用户明示**本轮不做分钟线**，其余未排期 | 产品负责人 |

---

## 9. 如何复核（评估方可直接跑）

```bash
# 判据三件套 + D/B 两类（真实浏览器）
.tmp/perf-browser/tv_check_all.sh

# 守卫测试（TV 相关 7 个文件）
uv run pytest tests/test_no_silent_failure_patterns.py tests/test_template_inline_js_syntax.py \
  tests/test_kline_draw_restore_tdz.py tests/test_kline_pane_option.py \
  tests/test_lwc_kline_removed.py tests/test_price_scale.py \
  tests/test_saas_symbol_ux.py -q -p no:randomly

# 周扫（两条退场条件机械判定，含归档状态）
deploy/saas/scan-macd-legacy-names.sh

# 全量
uv run pytest -q -p no:randomly
```

---

*本文档由 Kimi 主 Agent 汇总，2026-10-29。所有数字均为当日实跑，可复现。*
