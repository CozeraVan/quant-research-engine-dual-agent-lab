# Implementation Brief

## Task ID

QRE-RISK-RATES-005（FRM 风险管理模块 R5：利率与债券计算内核）

## Created By

KIMI_CODE（用户 2026-08-23 直接指定的任务书；依据已批准 CR
`docs/frm/CR_2026-08-23_risk_derivatives_extension.md` R5 阶段；
R1–R4 已完成）

## Intended Implementer

KIMI_CODE

## Goal

在 `risk/` 包内新增两个纯函数内核（零 DB、零行情依赖，输入为 dict/现金流表）：

1. `risk/rates.py`：复利频率换算（式 16.1–16.5）、PV/FV、spot↔折现因子、
   附息债 bootstrap 零息曲线（线性/对数线性插值）、远期利率（连续式与
   半年复利式 10.5）、par yield（式 16.7/10.4）。
2. `risk/bonds.py`：YTM 反解（scipy brentq）、dirty/clean 与应计利息
   （day count 参数化，默认 actual/actual）、Macaulay/Modified duration、
   yield convexity、effective duration/convexity（±Δr 重定价）、DV01 及
   D↔DV01 换算、组合聚合（DV01 可加、D/C 市值加权、DV01 对冲配比）、
   利率情景冲击（平行移动二阶近似；key-rate 扭转 KR01，ΣKR01=DV01 自检）、
   可转债债底折现（无风险+信用利差，spread duration）。
3. `risk/constants.py` 追加集中参数（day count 默认、曲线插值方式、
   key rate 节点、Δr 扰动 bp、YTM bracket），全部在结果 dict 回显。
4. `pyproject.toml` 补 scipy 显式依赖声明。

## 验收（CR §4 R5 行）

- 书4 Ch9 bootstrap 折现因子例：maturities 0.5/1/1.5/2、coupons
  5.75/5.5/5.875/5.5、prices 102.0426/103.5197/105.5852/106.4136 →
  d = 0.991909/0.980944/0.969406/0.956909（1e-6 容差）。
- par yield 算例（式 16.7/10.4）+ 平价债回验。
- 平坦曲线连续年金债久期/凸性解析解核对。
- DV01↔duration 换算自洽（D = 10,000×DV01/Value）。
- KR01 之和 = DV01。
- 平行移动二阶近似 ΔP=−D·P·Δr+½CP(Δr)² 与直接重定价偏差在容差内。

## 约束

纯函数、零 DB；不改既有 risk 模块行为；PCA 冲击/条款引擎/信用违约模型/
互换期货定价不做。既有 1605 测试保持全绿。

## Validation

`uv run pytest tests/ -x -q`（目标 1605 + 新增全绿）

---

# Implementation Brief (archive: QRE-RISK-GATE-004, R4 晋升闸风险判据)

## Task ID

QRE-RISK-GATE-004（FRM 风险管理模块 R4：晋升全量回测闸加入风险判据）

## Created By

KIMI_CODE（用户 2026-08-22 直接指定的任务书；依据已批准 CR
`docs/frm/CR_2026-08-21_frm_risk_module.md` R4 阶段；R1 = commit 96db59d、
R2 = commit f52c0f4、R3 = commit 6852eaa 已完成，risk_report.json 已随
每个 completed run 自动生成）

## Intended Implementer

KIMI_CODE

## Goal

在晋升全量回测闸（QRE-GUI-PROMO-GATE-001，commit cfb860d）的评估中
增加 FRM 风险维度：

1. **风险判据**：`finalize_promotion_gate` 收尾时读取该 run 的
   `runs/<run_id>/risk_report.json`：
   - 不存在/损坏 → `risk.status = "unavailable"`，不判风险项、不阻断。
   - 存在 → 取 99% ES（历史模拟口径，日收益损失取正）与 99% VaR 回测
     覆盖率 Kupiec LR 检验（5% 显著）：
     - ES99 > 阈值（默认 3%）或覆盖率 LR 被拒绝 → `risk.status = "warning"`。
     - 否则 `risk.status = "ok"`。
2. **闸语义**：主判据（交易≥30 且超额>0）照旧；`risk.status == "warning"`
   时与 failed 同效阻止日更拾取（force 晋升可覆盖），gate json 记录
   risk 详情（独立一节，便于 admin 展示）。
3. **admin GUI**：策略状态表「全量回测闸」列在 risk=warning 时追加
   ⚠ 风险警示徽标，tooltip 显示 ES99 与 VaR 回测结论。
4. **测试**：risk ok / warning（ES 超阈）/ warning（LR 拒绝）/
   unavailable（无 risk_report）四情形 + force 覆盖 + admin 徽标渲染。

## Semantics

- 阈值集中在 `risk/constants.py`：`GATE_ES99_MAX = 0.03`（日收益口径
  99% ES 上限）、`GATE_VAR_CONFIDENCE = 0.99`（VaR 回测取 99% 节，
  与 ES99 同置信）。LR 显著性 5% 沿用 backtest_var 既有 `reject_5pct`。
- ES99 取 `report["tail"]["99pct"]["historical_simulation"]["es"]`
  （经验日收益口径，非参数假设）；VaR 回测取
  `report["var_backtest"]["levels"]["99pct"]["coverage"]["reject_5pct"]`
  （Kupiec 覆盖率 LR；独立性检验不进闸判据，仅报告）。
- 关键字段缺失（老格式 report）→ 该子项不触发 warning，如实记 None。
- gate json 新增一节（不改动既有顶层键语义）：

  ```json
  "risk": {
    "status": "ok | warning | unavailable",
    "es99": 0.0219,
    "es99_threshold": 0.03,
    "var_lr_reject": false,
    "var_confidence": 0.99,
    "reasons": ["es99_exceeds_threshold", "var_lr_rejected"],
    "report_run_id": "rid-gate"
  }
  ```

- `gate_blocks_daily` 扩展：`(gate == "failed" 或 risk.status == "warning")`
  且非 forced → 阻止日更。force 通道照旧评估、不阻断。

## Scope

1. `src/quant_research_engine/risk/constants.py`：+ `GATE_ES99_MAX`、
   `GATE_VAR_CONFIDENCE`。
2. `src/quant_research_engine/gui/risk_report.py`：+
   `evaluate_gate_risk(run_id)`（load_risk_report → risk 判据 dict）。
3. `src/quant_research_engine/gui/strategy_create.py`：
   `finalize_promotion_gate` 写入 `payload["risk"]`（复用 record.run_id；
   run 失败时同路径评估，report 不存在自然落 unavailable）。
4. `src/quant_research_engine/gui/refresh_registry.py`：
   `gate_blocks_daily` 加 risk warning 分支（docstring 同步）。
5. `src/quant_research_engine/gui/templates/admin.html`：闸列追加
   risk=warning 徽标 + tooltip（ES99/VaR 结论）；`static/style.css`
   加 `.gate-risk` 样式。
6. 测试：`tests/test_gui_strategy_create.py`（四情形 + force + gate_blocks_daily
   联动）、`tests/test_gui_admin_strat_tab.py`（徽标字符串断言）。
7. docs/agent 08/10/09/05/04/11 同步。

## Non-Goals

- 不 git commit、不重启 qre-gui.service。
- 不改 risk 包核心计算、不改 refresh 管线取数逻辑、不动 DB。
- 不对存量 gate json 回填 risk 节（下次晋升回测评估自然写入；
  缺失时 admin 不显示徽标，语义=未知不阻断）。

## Validation

- `uv run pytest tests/ -x -q` 全绿（基线 1599）。
- 单测覆盖四情形 + force 覆盖 + admin 徽标。
