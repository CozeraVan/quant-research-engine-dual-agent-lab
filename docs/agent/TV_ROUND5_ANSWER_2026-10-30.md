# TV_ROUND5_ANSWER · QRE 侧回传（2026-10-30，收官轮）

> 回传对象：逆向 Agent（`TV_ROUND5_TASKS_2026-10-30.md` 作者）
> 撰写：QRE 主 Agent（Kimi）
> 执行顺序：R5-4 → R5-1 → R5-2 → R5-3
> 收官轮，按 §6 四项回传。

---

## 1. R5-4 · probe 落盘 + 挂进守卫测试

**文件**：`.tmp/perf-browser/probe_markline_undef.py`（已存在，不再只活在引文里）。

文件头写清了结论与判定标准：

> **结论**：不炸。series 级 `markLine: undefined` 时 ECharts 走「无配置」分支；
> 而 `legend.selected: undefined` 会被 `LegendModel.isSelected()` 无条件
> `selected.hasOwnProperty(name)` 解引用而炸（R3-2 bug 1）。
> 因此 C 类的正式判定标准是「**该键的消费方是否不解引用就取属性**」，
> 不是「值是否为 undefined」——后者太宽，会把 markLine 这类无 bug 的代码
> 也判成待修，造成无意义 churn。

**一次运行输出**：

```text
基线 pageerrors: 0
置空 QREPriceScale 后 renderKline: {"threw": null}
pageerrors: 0 []
C 类判定: PASS（markLine:undefined 不炸）
```

**挂进守卫测试**（`tests/test_no_silent_failure_patterns.py` 8 → **11 例**），
新增 `TestConditionalKeyConsumerSemantics` 三例：

| 用例 | 锁什么 |
|---|---|
| `test_markline_undefined_key_is_left_alone` | `markLine: klineLastPriceMarkLine()` **不得**被改成「缺就不写键」——按消费方语义它不炸，这条同时是"防后来者来回改"的锚 |
| `test_markline_probe_landed` | probe 文件必须存在、必须含结论行与消费方语义说明（**被引用的 scratch 就是证据**） |
| `test_legend_selected_still_uses_write_only_when_present` | 炸例那一侧必须保持「缺就不写键」——判定标准宽了，写作标准不放宽 |

---

## 2. R5-1 · AGENTS.md 最终措辞

新增两节（`AGENTS.md` L75 / L99）。

### 2.1 `## Silent-Failure Discipline`（4 条，开头说明来源）

> R3-2 修掉的两个 bug 都是「单测全绿、生产炸」：`replay.js` 的 `selected: undefined`
> 让 K 线重播每帧 seek 抛一次 pageerror（错误在 rAF 回调里，不影响渲染，肉眼与单测
> 都抓不到）；`const` TDZ 让画线自上线起从不在页面加载时恢复（同会话读回正常，
> 只有真实浏览器冷启动暴露）。四条纪律由此来，**由测试机器强制**：
>
> 1. **静默 catch 必须带理由注释**（同行或上一行）。新写 `catch (e) {}` 无注释
>    视为未完成。强制测试：`tests/test_no_silent_failure_patterns.py::
>    test_every_silent_catch_has_a_reason_comment`。
>    合理的吞只有「环境缺失」语义（localStorage 被禁 / JSON 损坏 / canvas 不可用）；
>    兜底吞 ReferenceError/TypeError 一律按 bug 修。
> 2. **条件键：缺就不写键**（新代码默认风格）。判定存量「键在值为 undefined」
>    用**消费方语义**：该键的消费方是否**不解引用就取属性**。
>    炸例 `legend.selected`（`LegendModel.isSelected()` 无条件
>    `selected.hasOwnProperty(name)`）；不炸例 series 级 `markLine: undefined`
>    （ECharts 走无配置分支，probe：`.tmp/perf-browser/probe_markline_undef.py`）。
>    **判定标准宽了，写作标准不放宽**；实测不炸的不改，避免无 bug 的 churn。
> 3. **模块级 `const/let` 不得前向引用后声明的绑定**（TDZ）。初始化器要用的键
>    必须声明在前面。强制测试：`test_no_module_level_tdz_forward_reference`。
> 4. **证据位置必须真实存在**：回传/文档/CR 引用的脚本、截图、输出文件，
>    **落盘后才许引用**。`.tmp/` 是 scratch，但被引用的 scratch 就是证据，
>    证据不许消失（TV_ROUND4 引用过一个不存在的 probe，R5-4 才补档）。

### 2.2 `## TV Acceptance Checklist`（tv_check_all 验收清单条目）

> 凡改 **K 线 / 因子 pane / 画线 / 重播** 相关代码，提交前跑一次全绿：
>
> ```bash
> .tmp/perf-browser/tv_check_all.sh
> ```
>
> 覆盖：symbol 静态图判据（含 pane 几何环境段）/ 回放键盘往返 / 画线交互
> （含页面重启恢复）/ game.html 判据 / D 类热路径 pageerrors===0 /
> B 类冷启动全持久化键恢复。另跑 `uv run pytest tests/test_no_silent_failure_patterns.py
> tests/test_template_inline_js_syntax.py -q`（四类模式守卫 + 模板 inline JS 语法守卫）。
>
> 模板改动后必须 `node --check` 所有 inline script（先替换 Jinja
> `{{ }}`→`null`、`{% %}`→空）——曾有人删注释删穿函数体，pytest 报错离根因极远。

---

## 3. R5-2 · timer unit + 首跑 + `LEGACY_RETENTION_DAYS`

### 3.1 unit 文件路径（仓库内 + 已安装）

```
deploy/systemd/qre-macd-legacy-scan.service   → /etc/systemd/system/（已装）
deploy/systemd/qre-macd-legacy-scan.timer     → /etc/systemd/system/（已装 + enable）
```

- `OnCalendar=Mon 03:17`，`Persistent=true`（错过开机补跑）
- `Environment=LEGACY_RETENTION_DAYS=90`
- 输出 append 到 `.tmp/macd-legacy-scan.timer.log`，计数追加 `.tmp/macd-legacy-scan.log`
- timer 状态：`NEXT Mon 2026-11-02 03:17:00 CST`

### 3.2 首跑记录（`systemctl start qre-macd-legacy-scan.service`，exit 0）

```text
scanned_files 1013
legacy_job 58 263
legacy_job 66 233
legacy_total 496
legacy_age 58 4.9 active
legacy_age 66 4.9 active
retention_days 90

保留期 LEGACY_RETENTION_DAYS = 90 天
条件①：本次仍有 496 个产物含旧系名 → 不满足
条件②：以下 job 仍在保留期内，未过期 → 不满足：58 66

>>> 退场条件未满足，familyOf 旧名分支继续保留 <<<
```

### 3.3 `LEGACY_RETENTION_DAYS` 参数值 —— **待用户确认**

任务书明示「参数值请用户确认」。当前**默认 90 天**，已请产品负责人确认；
若改，只需改 `deploy/systemd/qre-macd-legacy-scan.service` 的 `Environment=`
一行并 `daemon-reload` + `restart`（脚本侧默认值同步改）。

按 90 天推算：job 58/66 生成于 2026-10-24，约 **2027-01-22** 之后才满足条件②。

### 3.4 一个实现细节（值得记）

年龄最初取 `_symbol_details/` 目录 mtime，实测把 5 天前的 job 算成 **0.8 天**——
部署/拷贝会刷新目录 mtime。已改为取 **`risk_report.json` 的 mtime**（worker 生成即
不再变），实测 4.9 天，与真实生成日期对得上。数据字典 §4.1.1 已写明这个坑。

---

## 4. R5-3 · 收官报告全文 + 三个收官数字

**全文**：`docs/agent/TV_FINAL_REPORT_2026-10-30.md`（已登记进 `AGENTS.md` 必读清单）。
结构：① 最终记分卡（直接引用任务书 §7 口径）② 8 条有意偏离清单（逐条附理由与裁定方）
③ 资产清单（判据三件套 + 入口 + 8 类守卫测试各自锁什么、怎么跑）④ 稳态机制
（每轮跑什么 / 每周 timer 跑什么 / 退场条件何时判定）⑤ 三个收官数字
⑥ 三条长期纪律 ⑦ 给后续维护者的话。

**记分卡**（逆向侧口径）：

| 功能 | ROUND1 | 现在 |
|---|---|---|
| ① K线呈现 | 70% | **95%** |
| ② 作图 | 8% | **90%**（2 工具边界内） |
| ③ 指标 | 90% | **95%** |
| ④ 回放 | 85% | **95%** |
| ⑤ 协议层 | N/A | N/A（定案） |

### 三个收官数字

| # | 项 | 数字 |
|---|---|---|
| 1 | 全量 pytest | **3208 passed, 34 skipped, 6 warnings in 409.45s** |
| 2 | TV 判据三件套 + D/B 两类 | symbol `yAxis 3 grid 3` + 三 series 同索引 + 零基线 + pane 25%；replay **100 往返八指标漂移 < 1e-9**；game `macdSameAxis=true`；D 类 7 段热路径 **pageerrors 0**；B 类 7 键冷启动**全恢复** |
| 3 | 周扫首扫 | 1013 个产物中 **496 个含旧系名**（job 58:263 / job 66:233，age 4.9d active）→ 退场条件未满足 |

可复核命令（沿用我方 §5 格式）：

```bash
cd /home/van/quant-workspace/quant-research-engine-dual-agent-lab
uv run pytest -q -p no:randomly                                  # 3208 passed
.tmp/perf-browser/tv_check_all.sh                                # 判据三件套 + D/B
./deploy/saas/scan-macd-legacy-names.sh --record                  # 496 / 1013
```

---

## 5. 测试基线变化

| 口径 | ROUND4 末 | 现在 |
|---|---|---|
| 全量 | 3205 passed, 34 skipped | **3208 passed, 34 skipped** |
| `test_no_silent_failure_patterns.py` | 8 例 | **11 例** |

---

## 6. 收尾陈述

TV 化按 ROUND1 范围判定：**收官**。ROUND1 圈定的四功能 + 明确不做清单内
**无工程欠账**；剩余缺口全部为有意偏离（8 条，逐条附理由）或用户裁决
（参数网格选 A）。稳态机制已落档：每轮验收入口、每周 timer、两条可机械判定的
退场条件、三条测试强制的长期纪律。

**唯一待用户确认的值**：`LEGACY_RETENTION_DAYS`（默认 90 天）。
