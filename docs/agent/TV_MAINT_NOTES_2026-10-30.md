# TV_MAINT_NOTES · 收官签收补充 + 维护备忘（2026-10-30）

> **作者**：逆向 Agent。**性质**：TV_ROUND6_ANSWER 复核后的签收补充——**不是新一轮任务书**
> （TV 线已收官，本文件只含两个 15 分钟级动作 + 一个 2026-11-08 窗口的产品决策框架）。
> **回复对象**：`TV_ROUND6_ANSWER_2026-10-30.md`。

---

## 1. ROUND6 复核结论（逆向侧独立核验）

| 声明 | 本方核验 | 判定 |
|---|---|---|
| R6-1 仓库内日志 | `deploy/saas/macd-legacy-scan.log` 存在，3 条历史头，尾条 `retention_days 15` | ✅ |
| R6-1 `.tmp` 清空 | `.tmp/macd*` 不存在 | ✅ |
| R6-1 gitignore negation | `git add -n` 可加、`git status` 显示未跟踪非忽略——**negation 生效**（注：`git check-ignore -v` 对 negation 命中也会退出 0 并打印 `!` 行，脚本化判定用 `git add -n` 才是地面真相；他们用 check-ignore 复验结论碰巧正确） | ✅ |
| R6-1 守卫测试 | 18 passed（本方复跑 0.06s）| ✅（见 §2 说明） |
| R6-1 journal 双保险 | unit `StandardOutput/StandardError=journal` 已改；**但改后服务从未被 systemd 跑过**（timer LAST 仍为 10-29 13:32，早于改动；journal 现存仅该次的生命周期条目，无脚本输出） | ⚠️ **配置就位、实操未验** |
| R6-2 保留期 15 | `/etc` unit `Environment=…=15`、`systemctl show` 同、脚本默认 `:-15`、实跑 `retention_days 15`、数据字典 L188/L201 + FINAL_REPORT §4.3 同步 | ✅ 全链路 |
| R6-2 timer | enabled，NEXT 2026-11-02 03:17，ExecStart 带 `--record` | ✅ |

**总判定：R6-1/R6-2 完成属实，TV 线收官签收维持。**

## 2. 测试数 11→18 的说明（非 TV 线变更）

多出的 4 例是 `TestNightModePause`——属**并行主线任务**（2026-10-30 用户决定
aguhuice.com 暂停夜间模式、一律浅色；四入口夹 light + `NIGHT_MODE_ENABLED=false`
总开关 + base.html 防闪同步 + probe 落盘），加在了同一个守卫文件里。
TV_ROUND6_ANSWER 的「18 passed」数字准确，只是未注明其中 4 例来自并行任务。
**非报告完整性问题**，记录在案即可。

## 3. 两个 15 分钟级动作（谁在 TV 维护态谁做，无需成立新轮次）

1. **journal 双保险实操验证**（§1 ⚠️ 项的闭环）：
   `sudo systemctl start qre-macd-legacy-scan.service`（oneshot，约 13s，
   ExecStart 自带 `--record`，会如实追加第 4 条仓库日志——无害），
   然后 `sudo journalctl -u qre-macd-legacy-scan.service --no-pager | tail`
   应出现**脚本输出**（scanned_files / legacy_total …），而不只是生命周期行。
   把这两条输出回传或在 11-02 timer 首跑后核验即可。
2. **数据字典 §4.1.1 补一句退场前置动作**（见 §4 的澄清）：
   现行条件①的机械实现是 `legacy_total == 0`——**job 58/66 的 496 个产物
   不从 ECS 消失，它永远不为 0**。15 天过期只满足条件②，不触发任何清理。
   §4.1.1 应写明：2026-11-08 之后若要走退场，需**用户批准后归档/删除**
   job 58/66 的 `_symbol_details`（归档优于删除——挪出扫描路径即满足①，
   数据可找回）；清理后连续 4 次周扫为 0 才删 `familyOf` 旧名分支。

## 4. 2026-11-08 窗口的产品决策框架（给用户，agent 不拍板）

保留期 15 天到点后，真正要决定的是「旧 job 的处置」，三个选项：

| 选项 | 代价 | 效果 |
|---|---|---|
| **永久保留分支**（零动作） | `familyOf` 旧名分支 ~30 行代码 + 双列名认知成本 | job 58/66 永远正确渲染；**推荐默认** |
| **归档退场** | 归档 496 个产物（用户批准）+ 等 4 次周扫 | 分支删除、代码简化；旧 job 个股详情页失去（或降级为每列一窗） |
| **重跑旧 job** | 重新计算；**回测窗口会延伸到当前数据，结果与 10-24 存档不同** | 新系命名产物；若要保留 10-24 原结果此路不通 |

逆向侧意见：**默认选 1**。30 行代码的持有成本远低于处置旧数据的决策成本；
真要清理 ECS 空间时再走 2（归档不删）。

---

*本文件是 TV 线最后一份逆向侧文档。TV 化收官状态：全部签收，无未决工程项；
维护动作见 `TV_ROUND6_TASKS_2026-10-30.md` §4 + 本文件 §3。*
