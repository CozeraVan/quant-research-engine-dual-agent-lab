# 46 | Game 项目 Windows 侧任务单（2026-11-12）

> **主 Agent 直接派单，无需用户转述。** Windows agent 读到本文件即可开工。
> 本文件**自包含**：Windows 检出的 `docs/agent/` 只到 38 号，39–45 号未同步到该检出，
> 不要依赖那些文档；本轮需要的口径、边界、验收命令全部写在下面。
> WSL 主仓有同号权威副本：`docs/agent/46_GAME_WINDOWS_TASKS_2026-11-12.md`。

---

## 0. 主 Agent 复核结论（已实测，可直接引用）

被复核对象：分支 `game/windows-dev`，基线 `0eb10e2`，两个提交
`d10cfb1`（Windows 预览链路：本地样本 store + `/game` 启动脚本）、
`f6385d8`（审计按 price_basis 重算 + kv-grid grid 基类 + 样本 tick 精度）。
共 5 个文件：

| 文件 | 变更 |
| --- | --- |
| `scripts/win/game_preview_sample.py` | 新增 260 行，后 +8/-2 |
| `scripts/win/start-game-preview.ps1` | 46 行 |
| `scripts/win/start-game-preview.py` | 44 行 |
| `src/quant_research_engine/game/templates/game.html` | +1 |
| `src/quant_research_engine/game/validation.py` | +34/-3 |

主 Agent 亲自跑过（cwd = Windows 检出根目录，解释器用 WSL 主仓 `.venv`）：

```
.venv/bin/python -m pytest .tmp/game-windows-dev/test_game_fixes.py tests/test_trading_game_*.py -q
→ 34 passed in 3.85s
```

`git diff --check master...HEAD` 干净。

**未由主 Agent 独立重跑**（只看过对方日志/截图，认可但不算主 Agent 证据）：
50/50 浏览器审计、桌面/移动截图、Windows 侧 `test_factor_display_contract.py::TestPanelsAndMetadata`
的 2 个 error（缺 `psql`，环境问题，非本切片引入）。

**唯一阻塞合并的问题：T1。** 其余为规范化与口径显式化。

---

## 1. T1（阻塞项）修样本 vol / amount 单位口径

文件：`scripts/win/game_preview_sample.py:181-182`，现状：

```python
vol = round(rng.uniform(2e6, 9e6) * (1.0 + 0.4 * math.sin(i / 17.0)), 0)
amount = round(vol * (open_ + close) / 2.0, 2)
```

问题：**生产口径 `vol` = 手、`amount` = 千元**；样本按「股 / 元」造，两者单位不一致。
现有测试没有覆盖 `average_price`，所以全绿掩盖了这个错误。合成数据一旦按生产口径消费，
均价会差 100 倍。

要求：
- 先算出股数与元金额，再落到生产单位：`vol = vol_shares / 100`（手）、`amount = amount_yuan / 1000`（千元）
- **随机序列与 tick 精度逻辑保持不变**（`rng.uniform(2e6, 9e6)`、`sin(i/17)` 调制、`f6385d8` 的精度处理都不许改）
- 新增断言：`amount * 10 / vol` 落在当日 `[low, high]` 区间内（逐根校验，不是抽查一根）

验收门槛：断言必须真能红——把 `/1000` 临时去掉，测试要失败；恢复后全绿。回执里贴这次红灯输出。

---

## 2. T2 把 6 项新测试正式并入 `tests/`

现状：新增 6 项测试仍在 `.tmp/game-windows-dev/test_game_fixes.py`（3907 B），未进 `tests/`。
`.tmp/` 是 scratch，不是可复跑的回归资产。

要求：
- 把这 6 项并入 `tests/`（新建 `tests/test_game_windows_fixes.py`，或并入既有 `tests/test_trading_game_*.py`，命名自定，但必须在 `tests/` 下）
- `pytest tests/test_trading_game_*.py` **单独可跑且 ≥ 34 passed**，不再依赖 `.tmp` 路径
- 新文件里的 `read_text()` 一律带 `encoding="utf-8"`（采纳对方自己的建议）
- `tests/` 归属 WSL，本轮只允许**新增本轮 game 相关测试**，不改动其他既有测试

---

## 3. T3 game 状态显式输出 `factor_basis`

要求：game 状态里显式返回 `factor_basis="qfq_anchor_v1"`，值**引用常量**而不是字面量：

```python
from quant_research_engine.factor_basis import FACTOR_BASIS_QFQ_ANCHOR_V1
```

（常量定义在 `factor_basis.py:30`；契约见 `docs/agent/23_KLINE_IMPLEMENTATION.md` §4a，
该文档 Windows 检出里有。审计脚本 `deploy/saas/scan-factor-basis.sh` 归 WSL，不要改。）

审计与前端**沿用现有 `price_basis` 逻辑**，不新增换算层、不新造第二套 `qfq_anchor` 实现。

---

## 4. T4 `average_price` 维持 `skipped`，禁止冒充前复权均价

口径（本文件即登记，回答对方第 4 个问题）：

- **原始口径**：`average_price = amount × 10 / vol`（`amount` 千元 → 元，`vol` 手 → 股）；
  上游若提供原生 `vwap`，**优先用 `vwap`**
- **展示口径**：需再乘 `adj_factor / 锚点`（锚点 = 最后一根可用 `adj_factor`）

为什么现在不能就地算：`core/models.py:35` 的 `Bar` **没有复权比率字段**；
`game/data.py` 的 `bars_from_rows()` 只缩放 OHLC / pre_close，**volume / amount 保持原值**。
因此在前复权 `Bar` 上算 `amount*10/volume` 得到的是**原始均价**，不是前复权均价。

要求：保持 `skipped`，并在代码注释里写明「等 WSL 补齐输入后启用」。
**禁止**用前复权 `Bar.amount × 10 / volume` 冒充前复权均价。
启用条件：`Bar` 携带复权比率，或上游透传原生 `vwap` + 锚点。

---

## 5. T5 真实数据验收（不阻塞，等 WSL 交付）

WSL 后续提供 3–5 只**脱敏真实快照**，走**同一个 `SampleGameStore` 六方法接口**，
不向 `qre_ui_dev` 导整库、不直连生产行情库。
快照到位后做一次真实数据回合验收（双视口 + 审计），届时主 Agent 另行派单。

开局数据量参考：warmup 250 + game 1250 = 1500 根 K 线，候选上限 20，已剔除 `920%.BJ` 脏数据。

---

## 6. 对「需 WSL 补充的接口」四问的裁定（已定，不重开讨论）

1. **预览行情样本**：现阶段合成样本够用，本轮不阻塞。真实脱敏快照由 WSL 后补，接口不变（见 T5）。
2. **`/game` 接入方式**：本地预览继续用独立 `create_game_app`；**公网走 SaaS 挂载蓝图**——
   蓝图与 game API 归 Windows，注册 / 鉴权 / 部署归 WSL。CLI `game` 子命令仅作开发运维入口。
   若 `web.py` 重构落在 `game/` 内，由 Windows 执行。
3. **`factor_basis` 呈现合同**：游戏现有实现（`qfq_anchor` + 族白名单）**已满足** `qfq_anchor_v1`，
   只需显式返回该字段并复用常量（T3），**不再造换算层**。
4. **`average_price` 公式**：**已登记**，见 T4；当前 `skipped` 是正确行为，不是缺陷。

---

## 7. 工作边界（硬约束）

- 只改 `game/`（含其 templates）与 `scripts/win/*`；`tests/` 仅新增本轮 game 测试
- **不碰** SaaS 注册 / 鉴权 / 部署（`gui/**/*.py`、`deploy/`）、不碰生产库、不跑全市场回测
- **不 push、不自行合 master**；分支固定 `game/windows-dev`
- 静默失败四纪律：catch 必须带理由注释；条件键缺就不写键；模块级 `const/let` 不得 TDZ 前向引用；
  **引用的证据必须真实落盘**
- UI：不新增灰色小字备注（`.opt` / muted 说明），解释走 `tip-trigger` + `data-tip` + `LabUI.helpTips`；
  **红涨绿跌**；复用 `factor-layout.js` 与 `card-class.css`，不另起图表框架
- 预览端口固定 8091（8080/8081 被 WSL 转发占用）；`.ps1` 存 UTF-8 BOM，`.sh` 存 LF

---

## 8. 回执要求（缺项视为未完成）

1. 分支名 + 每个 commit 的一句话摘要 + 文件清单
2. `pytest tests/test_trading_game_*.py -q` 的**真实数字**（单独跑，不带 `.tmp`）
3. T1 断言的**红灯证据**（去掉 `/1000` 后失败的输出）+ 恢复后绿灯
4. 50/50 浏览器审计**复跑**日志（`.tmp/game-windows-dev/browser-audit.log`）
5. 桌面 1280×900 + 移动 375×812 截图，落 `.tmp/ui-review/`，路径写进回执
6. `git diff --check` 结果
7. 邻接回归数字；环境性 error（缺 `psql`）如实单列，不要混进 passed

---

## 9. 集成方式（主 Agent 执行，需用户授权后）

Windows 分支基线 `0eb10e2` 偏旧，主仓 master 已到 `999c24f`。
集成时由主 Agent 把 `d10cfb1`、`f6385d8` **cherry-pick 到当前 master**，不合并旧基线。
Windows 侧**不要 rebase master**（master 含 Windows 非法文件名，checkout 会失败）。

---

## 10. WSL 侧待办（不派给 Windows，主 Agent 自己跟）

- `tests/` 中既有 `read_text()` 补 `encoding="utf-8"`
- 生成并交付 3–5 只脱敏真实快照（同 store 接口）
- SaaS 蓝图注册 / 鉴权 / 部署
- 补齐 `average_price` 输入（`Bar` 复权比率或原生 `vwap` 透传），到位后解除 T4 的 `skipped`

## 11. 主 Agent 裁定（2026-11-12 第二轮回传）

本节回应 Windows 第二轮回传的三条待裁定 + 一项待交付。裁定全文见 `22_TRADING_GAME.md` §16；本节是 Windows 侧执行所需的契约摘要。**本轮纯文档：未改业务代码、未合入 master、未部署 ECS、未提交。**

### 11.1 三条裁定结论

1. **22 号基线可配置 → 同意修订，默认不变。** 白名单 `game_bars ∈ {250, 750, 1250}`、`initial_cash ∈ {100000, 500000, 1000000, 5000000}`；默认仍 `1250 / 1,000,000`，故既有验收结论不作废、不需重跑。非默认配置属额外用例，验收记录须写明 `game_bars` / `initial_cash` / `seed`。白名单是服务端最终闸（22 号 §5），前端下拉只是便利，篡改请求体必须被拒。
2. **S3 播放/暂停/单步/倍速 → 计入第一阶段验收。** 依据 22 号 §8 阶段 1 L149 本就是设计项，属还欠账。守 V1.1 回合制：单根收束动画不自动进入下一回合；2026-11-14 用户人工测试后批准显式连播例外，允许跨日自动推进，每天仍真实结算；倍速同时调节单根动画与连播节奏。
3. **`_state` 三字段 → 按「只增不改」接受，下游知会如下。**

| 字段 | 类型 / 单位 | 口径 | 边界 |
|---|---|---|---|
| `initial_cash` | float，元 | 取自白名单，默认 `1_000_000.0` | 透传 `DailyGameEngine(initial_cash=...)`；破产线 `equity < initial_cash * 0.10` |
| `return_pct` | **小数比率，非百分数** | `engine.equity / engine.initial_cash - 1.0`，含摩擦 | `initial_cash == 0` 返回 `0.0`；前端乘 100 展示 |
| `max_drawdown` | 小数比率，**恒 >= 0** | 遍历 `equity_curve`：`peak = max(peak, v)`、`dd = max(dd, (peak - v) / peak)` | 只统计已结算日；峰值序列首点 = `initial_cash` |

- **符号纪律**：`max_drawdown` 后端恒非负；Windows 侧 `game/templates/game.html:293` 用 `-Math.abs(state.max_drawdown)` 自行转负显示，**后端不得改符号**。
- **向后兼容**：主仓尚无 `return_pct` / `max_drawdown`（grep 无命中），三键属**契约预告**，随白名单一并 cherry-pick 进 master 才生效。下游（SaaS 结果页 / 审计脚本 / 旧快照 JSON）**缺键不抛错、按可选读取**。

### 11.2 T5 交付契约（WSL 认领）

WSL 产 **3–5 只**脱敏真实快照，与 `scripts/win/game_preview_sample.py` 的 `SampleGameStore`（L230 起）同构，零数据库连接即可被现有五年驱动脚本直接复用。契约 = 1 个类属性 + 6 个方法：

```python
settings = SimpleNamespace(tables=SimpleNamespace(market_daily_table="public.stock_daily"))  # L233
def __init__(self, seed: int = SAMPLE_SEED) -> None                                       # L235
def qualified_table(self, name: str) -> str                                               # L239 → return name
def latest_trade_date(self) -> date                                                       # L242 → self._days[-1]
def list_symbols_with_bars(self, start: date, end: date) -> list[str]                      # L245 区间不相交返回 []
def load_raw_bars(self, symbol: str, start: date, end: date) -> list[dict]                 # L250 按 start <= trade_date <= end 过滤
def load_factor_history(self, symbols, requests, start: date, end: date) -> pd.DataFrame   # L253
```

`load_factor_history` 语义：列 = `["ts_code", "trade_date"] + 各 req.logical_name`（去重）；行形如 `{"ts_code": sym, "trade_date": pd.Timestamp(day)}`；未预置的 canonical 填 `float("nan")`，**不抛异常**；有值 `round(value, 4)`。

交付约束：

- **每只 1500 根** = `warmup_bars 250 + game_bars 1250`。`GameSession`（Windows 侧 `game/session.py:24`）以 `required = warmup_bars + game_bars` 校验，不足抛 `GameRuleError("历史数据不足：至少需要 {required} 根 K 线")`。非默认 `game_bars` 由 Windows 侧按 `warmup_bars + game_bars` 自行截取。
- 脱敏：匿名代码（`B` / `X00001B` 风格，22 号 §2 L39-40）；日期整体偏移，**保持交易日相对间隔与序列长度**；复权锚点一局内固定（L43）。真实名称/代码/日期不出现在交付物中。
- 取数：候选上限 20 只、已剔除 `920%.BJ`；**不向 `qre_ui_dev` 导整库、不直连生产行情库**。
- **路径状态**：拟建 `scripts/game/export_snapshot.py` 与 `data/game_snapshots/`，**尚未创建**（本轮实测无匹配）。落盘后回填真实路径与文件名再通知 Windows 复跑；在此之前 T5 仍为「等待 WSL 交付」。

### 11.3 一并认领 §10 的两项 tests 待办（归 WSL）

- 6 项测试从 `.tmp/game-windows-dev/test_game_fixes.py` 对齐入库为 `tests/test_game_windows_fixes.py`。
- 既有 tests 的 `read_text()` 补 `encoding="utf-8"`。
- `average_price` 上游输入补齐后才有条件解除 T4 的 `skipped`，本轮不动；当前 `skipped` 是正确行为，禁止用前复权 `Bar.amount×10/volume` 冒充前复权均价。---

## 12. 下一轮派单（2026-11-12 第三轮，Windows 执行）

裁定已批准并提交（纯文档 commit，见 `05_PROGRESS.md` 2026-11-12 小节）。本节是 Windows 侧第三轮的**唯一派单来源**，与 §7 边界、§8 回执共同生效。分支固定 `game/windows-dev`，**不 push、不合 master、不 rebase master**。

### 12.1 任务清单（按优先级）

| 编号 | 任务 | 交付判据 | 优先级 |
|---|---|---|---|
| **W1** | T1 样本单位修正（§1）：`scripts/win/game_preview_sample.py` 的 `vol` 改「手」、`amount` 改「千元」——先按股数/元金额生成，再 `vol/100`、`amount/1000`；随机序列与 tick 精度逻辑不许动 | 新增逐根断言 `amount*10/vol ∈ [low, high]`；**必须给红灯证据**（临时去掉 `/1000` 后该断言失败的真实输出）+ 绿灯输出 | **P0，唯一阻塞 cherry-pick** |
| **W2** | T3 显式返回口径（§3）：game 状态返回 `factor_basis=FACTOR_BASIS_QFQ_ANCHOR_V1`，`from quant_research_engine.factor_basis import FACTOR_BASIS_QFQ_ANCHOR_V1` 引用常量 | 沿用现有 `price_basis` 逻辑，**不新增换算层**；测试断言字面值等于 `qfq_anchor_v1` | P1 |
| **W3** | 开局白名单落地（§11.1 第 1 条）：前端下拉给 `game_bars` 三档 / `initial_cash` 四档，默认 1250 / 1,000,000；**服务端为最终闸** | 新增测试证明篡改请求体被服务端拒绝（至少 `game_bars=999`、`initial_cash=1` 两例），前端下拉不作为唯一防线；默认路径回归仍过 | P1 |
| **W4** | 回合制守卫实测（§11.1 第 2 条）：播放 / 暂停 / 单步 / 倍速逐项实测 | 证据证明**单根收束动画不自动进入下一回合**；显式连播允许跨日且每天真实结算，倍速同时调节单根动画与连播节奏 | P1 |
| **W5** | T5 预备（§11.2）：把现有五年驱动脚本改成**可传入快照路径 / store 来源**（参数或环境变量），保留合成样本为默认 | 脚本能在不改代码的前提下切换到外部 store；本轮仍用合成样本跑通一次并给日志 | P2 |

### 12.2 明确不派给 Windows（归 WSL，见 §10 / §11.3）

- T2：6 项测试从 `.tmp/game-windows-dev/test_game_fixes.py` 入库 `tests/`——**WSL 做**。Windows 只需**保留该文件不删、保持可读**。
- 既有 `tests/` 的 `read_text()` 补 `encoding="utf-8"`——WSL 做。
- T5 脱敏真实快照生产（`scripts/game/export_snapshot.py`、`data/game_snapshots/` **尚未创建**）——WSL 做。
- SaaS 蓝图注册 / 鉴权 / 部署，`average_price` 上游输入补齐——WSL 做。

### 12.3 本轮硬约束（重申，违反即退回）

- 只改 `game/`（含 `game/templates/`）与 `scripts/win/*`；不碰 `gui/**/*.py`、`deploy/`、生产库；不跑全市场回测。
- **不得**为了拿真实数据去连生产行情库或往 `qre_ui_dev` 导数据；W5 只做「可切换」的接口改造。
- `_state` 三字段口径按 §11.1 表格，**后端 `max_drawdown` 恒非负**，负号只在前端转；`return_pct` 是小数比率，前端乘 100。
- UI：禁灰色小字（走 `tip-trigger` + `data-tip` + `LabUI.helpTips`）、红涨绿跌、复用 `factor-layout.js` 与 `card-class.css`。
- 预览端口固定 **8091**（8080/8081 被 WSL localhost 转发占用）；`.ps1` UTF-8 带 BOM、`.sh` LF。
- 静默失败四纪律照旧：不吞异常、不伪造成功、环境缺失如实单列、证据落盘。

### 12.4 回执（§8 七项 + 两项新增）

§8 七项全部照给，另加：

8. **W3 拒绝篡改的测试输出**（真实 pytest 行，含被拒用例名与断言）。
9. **W4 回合制证据**：日志或截图序列路径 + 单根动画不自动进回合、显式连播逐日真实结算的结论。

若某项在上一轮已部分完成，**如实说明现状与增量**，不要重述为「本轮新做」。

## 13. WSL T5/T2 交付完成（2026-11-14）

- T5 已落盘：`scripts/game/export_snapshot.py`、离线 `scripts/game/snapshot_store.py`、`data/game_snapshots/{manifest.json,x00001b.json,x00002b.json,x00003b.json}`。三只各 1500 根，匿名代码、日期统一偏移 3650 天、无真实代码/名称/日期；候选上限 20，已排除 920%.BJ。Store 与 SampleGameStore 六方法同构，可供五年驱动 `--store-source file.py:Class` 使用。
- T2 已入库：`tests/test_game_windows_fixes.py` 六项（按契约在本机重写，未读取 Windows scratch）；`tests/test_trading_game_web.py` 的 `read_text` 已补 UTF-8。补真快照测试 `tests/test_game_snapshot_store.py`。
- 本机修复：`game/validation.py` 不再用 close 重算 typical_price 口径；`game.html` 显式 `.kv-grid{display:grid}`。两文件已部署 ECS（qre-saas active，HTTP 200）。
- 验证：`uv run pytest tests/test_trading_game_*.py tests/test_game_windows_fixes.py tests/test_game_snapshot_store.py -q` → **37 passed**。真实 X00003B 可建 1500 根会话并加载因子；BOLL 逐点 0 mismatch。EMA 长周期在 1500 根截断面存在种子差异，文档与测试已明确，不伪称全因子零误报。
- Windows 下一步：用 `scripts/game/snapshot_store.py` + `data/game_snapshots/` 复跑五年驱动和双视口审计。未 commit/push。


## 14. average_price 输入补齐（2026-11-14）

- `core.models.Bar` 新增可选 `adjustment_ratio` 与 `average_price` 属性；`game/data.py::bars_from_rows` 逐根写入 `adj_factor/锚点`。
- `game/validation.py` 对 `*_average_price` 表按 `amount×10/vol×adjustment_ratio` 审计，typical_price 等非登记口径仍 skipped。
- 回归：游戏 38 passed（含 average_price 复权与 3 只真实快照）；已部署 ECS。
- Windows 可用 Bar.average_price 解除 T4 skipped。SaaS 蓝图仍待 Windows 最新 game/web 可访问提交与生产行情连接裁定，不能拿旧版重复实现。


## 15. Windows 三因子问题裁定与修复（2026-11-14）

1. **末段单点 mismatch**：snapshot 无重复日期，raw bars/factors 一一对齐，复权比率正确；bbm/bbu/ema_5 在 idx1493 是上游因子单点异常，不是 export 对齐或复权错误。不得修改原始值，后续应标记 source_anomaly。
2. **EMA 暖机种子差**：`validation.py` 现对 EMA 豁免 4×span 暖机段，之后任何单点异常仍计数；注入末段异常与 39 项游戏回归通过。EMA250 末段差属于全历史种子 vs 窗口 SMA 种子的良性衰减。
3. **因子内容缺口**：export 改为完整 `factor_catalog()`，三只各 1500 根，含 typical_price、风险、流动性真实值；3 个含 `%` 的上游列名不受 FactorFieldRequest 支持，manifest 显式 skipped。新快照约 160MB，已同步 `D:\workzone\webui\data\game_snapshots\` 并覆盖旧版；V1 备份在 WSL `.tmp/game_snapshots_v1_backup/`。
- 验证：39 passed；typical EMA、beta、amount_ma 各 1500 非空值；已部署。


### 15.1 末段异常上游实证（2026-11-14）

- X00001B 源为 `600789.SH`（异常原始日 2026-11-05），X00002B 源为 `002551.SZ`（同日）。库内原值与快照一致，排除 export 错位。
- 对同一原始 close×adj_factor 全历史重算：600789 ema_5 DB=20.86 / 重算=20.9837，bbm DB=22.00 / 重算=21.8601，bbu DB=24.51 / 重算=24.2067；002551 bbm DB=26.39 / 重算=26.2212，bbu DB=29.06 / 重算=28.8472。异常确属上游因子生成口径/数据，不改快照。


### 15.2 average_price 审计分支修正（2026-11-14）

- Windows 回传五年驱动 28/27/0、样本 30629 项 0 mismatch、浏览器 97/97、ui-smoke PASS、average_price 逐根校验通过。
- 同步修正审计分支：`*_average_price` 不再把 VWAP 直接当最终因子值，而是先求 VWAP，再调用对应 EMA/BOLL 公式；未登记 MACD 公式仍 skipped，不制造误报。
- 修复前真实 average_price MACD 审计 13500/13500 误报，修复后未登记项不再错误比较；游戏 39 passed。已部署并同步 Windows validation.py。
- 其余两项：glob 5 个失败需 Windows 原始输出才能逐项裁定；idx1493 已确认上游异常，保持源值不改。


### 15.3 Windows glob 5 项失败逐项裁定（2026-11-14）

1. `price_basis:164`：暖机后应 1480，测试已改为 1496−16；原断言过期。
2/3. typical_price：不再整体 continue，现按 `(high+low+close)/3` 重算；真实快照 typical EMA checked=1480、mismatch=0，异常仍计数。
4. 旧 mock catalog 缺 table 键：审计改 `item.get("table", "")`，未登记/未知/未支持公式统一写 `canonicals[canonical].skipped=true`，不再 KeyError。
5. `AVERAGE_PRICE_RAW_FORMULA`：Bar 已有复权比率，旧「保持 skipped」前提过期；average_price 先 VWAP 后公式，未登记公式 skipped。Windows 测试应更新而非恢复常量。
- 测试集合差异：WSL 跑 `test_trading_game_*.py + test_game_windows_fixes.py + test_game_snapshot_store.py` 共 39 项；Windows glob 46 项还含其扩展用例，不应用数量直接判冲突。
- validation.py 与更新测试已同步 Windows，39 passed；已部署。
