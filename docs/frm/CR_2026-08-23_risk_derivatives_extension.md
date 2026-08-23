# CR：风险模块扩展——期权 / 债券 / 利率计算内核（QRE Risk Derivatives Extension）

- 日期：2026-08-23 ｜ 状态：✅ R5–R7 已完成（R5 = commit 5472832；R6/R7 待 git 审批）
- 前置：CR_2026-08-21_frm_risk_module.md（R1–R4 股票风险模块已完成并集成，commit f9be2c1）。该 CR §5 已声明「期权/债券/利率实现不在 R1-R4 范围，未来扩展时单独 CR」——本文档即该扩展。
- 知识来源：`docs/frm/FRM量化风控知识摘要.md` 扩读部分（书3 Ch16/17/19、书4 Ch9–16，公式/参数/页码以该摘要为准）
- 定位：**可复用计算内核，非实盘功能**。服务于未来股票池/组合纳入债券、可转债、期权头寸时的风险计量；当前 DB 仅有股票日线/因子/沪深300基准，期权与债券行情数据缺失，本 CR 全部模块**纯计算、零 DB、零实时行情依赖**，行情接入留待未来数据源（tushare 期权/债券接口）单独 CR。

## 1. 目标

在 `src/quant_research_engine/risk/` 内扩展三个纯函数内核：

1. 利率与固收内核：复利换算、零息曲线 bootstrap 与插值、YTM、久期/凸性/DV01、组合聚合与利率情景冲击。
2. 期权内核：BSM/Black's 定价、隐含波动率反解、CRR 二叉树（美式）、Greeks 全组。
3. 组合层：含衍生品头寸的组合风险汇总（Delta-Gamma-Vega 近似 VaR），并与既有 risk_report 输出合并。

延续既有纪律：risk 包可独立 import（纯函数零 DB）；所有参数集中 `risk/constants.py` 并在结果 dict 回显；分阶段实施、每阶段独立审批；GUI 与晋升闸集成放最后。

## 2. 范围（与 FRM 章节的映射）

### R5 利率与债券内核

| 子模块 | FRM 出处 | 内容 |
|---|---|---|
| 复利与贴现 | 书3 Ch16 式16.1–16.5；书4 Ch10 | 复利频率换算、连续复利互转、PV/FV、spot↔折现因子 |
| 零息曲线 | 书4 Ch9（bootstrap）；书3 Ch16 | 附息债 bootstrap 折现因子 d(t)、线性/对数线性插值、远期利率（连续式 F=(R2T2−R1T1)/(T2−T1)、半年复利式 10.5） |
| 债券定价与收益 | 书4 Ch11 式11.1–11.3；书3 Ch17 | YTM 迭代反解（scipy brentq）、dirty/clean price 与应计利息（day count 参数化，中国惯例 actual/actual 为默认）、年金/永续 |
| 久期/凸性/DV01 | 书4 Ch12 式12.1–12.6；书3 Ch16 式16.8/16.9 | Macaulay/Modified duration、yield convexity、effective duration/convexity（±Δr 重定价，供含权债使用）、DV01 及 D↔DV01 换算 |
| 组合聚合与对冲 | 书4 Ch12 | 组合 DV01 可加、duration/convexity 市值加权、DV01 对冲配比（面值 = 组合DV01/工具每面值DV01） |
| 利率情景冲击 | 书4 Ch12/13 | 平行移动（duration+convexity 二阶近似 ΔP = −D·P·Δr + ½CP(Δr)²）、扭转（key-rate 局部线性 shift、KR01，ΣKR01=DV01 自检）；PCA 因子冲击列为可选项 |
| 可转债（债底） | 书3 Ch16/17 落地提示 | 纯债价值 = 现金流按（无风险+信用利差）折现；spread duration；期权腿接口留给 R6 二叉树 |

### R6 期权内核

| 子模块 | FRM 出处 | 内容 |
|---|---|---|
| BSM / Black's | 书4 Ch15 式15.6–15.13 | 无股息/连续股息 q/离散股息修正（S₀−D）欧式定价；Black's model（期货期权） |
| 隐含波动率 | 书4 Ch15 | 无解析解，brentq 反解（教材惯例 successive bisection） |
| 二叉树 | 书4 Ch14 式14.1–14.7 | CRR u/d/p、欧式+美式 backward induction、含股息 q；树上前两层节点输出 delta；美式 Greeks 数值差分（书4 Ch16 方法） |
| Greeks | 书4 Ch16 式16.1/16.2 + Table 16.2 | Delta/Gamma/Vega/Theta/Rho 全组（含 q 版与期货期权版）；组合 Greeks = 头寸加权求和 |
| Delta-Gamma-Vega VaR | 书4 Ch16 + Ch2 | 组合 P&L 二阶近似 ΔV ≈ Δ·δS + ½Γ(δS)² + vega·δσ，正态/Cornish-Fisher 近似分位；输出的 VaR 序列直接喂给既有 `backtest_var.backtest_var_summary` 复用 HIT/LR 回测框架 |

### R7 组合层与集成

- 混合头寸（股票 + 债券/转债 + 期权）统一风险汇总：股票腿沿用 R1–R4 收益序列法，衍生品腿用 DV01/KR01 与 Greeks 暴露，合并输出到 `risk_report.json` 扩展节（向后兼容，新键可选）。
- GUI run_detail 新增「衍生品风险」卡片组（沿用六组卡片模式）。
- （可选，单独确认）晋升闸扩展：组合 DV01/Greeks 限额判据，仿 R4 模式。

## 3. 架构设计

- 新文件（均纯函数，pandas/numpy/scipy）：
  - `risk/rates.py`：复利换算、折现因子、零息曲线 bootstrap/插值、远期利率。
  - `risk/bonds.py`：YTM、dirty/clean、久期/凸性/DV01、组合聚合、情景冲击（平行/扭转/KR01）、转债债底。
  - `risk/options.py`：BSM/Black's、隐波反解、CRR 二叉树、Greeks、组合 Greeks。
  - `risk/derivatives_var.py`：Delta-Gamma-Vega 近似 VaR，对接 backtest_var。
  - `risk/report.py`：R7 追加衍生品节渲染；`risk/constants.py` 追加参数（day count 默认、曲线插值方式、二叉树默认步数、key rate 节点、Δr 扰动 bp、隐波 bracket 等）。
- 依赖：**仅需 numpy/scipy**（`scipy.optimize.brentq`、`scipy.stats.norm`），arch 已有但本扩展不需要。注意：`risk/constants.py` 已 import scipy 但 `pyproject.toml` 未显式声明，R5 顺手补上 `scipy` 依赖声明。
- 输入约定：曲线/头寸以简单 dict/DataFrame 传入（如 zero curve = 期限→利率，债券 = 现金流表，期权头寸 = S/K/T/σ/r/q/类型/数量），不定义 DB schema。
- 自检恒等式（写入单测，教材背书）：put-call parity（式14.1 变形）；BSM PDE `θ + rSΔ + ½σ²S²Γ = rf`（式16.2）；ΣKR01 = DV01；二叉树步数↑收敛到 BSM。

## 4. Roadmap 与验收

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| R0 | 本 CR 批准 | 用户批准 |
| R5 | rates.py + bonds.py（利率/债券内核，含转债债底） | pytest 绿；教材数值复现：书4 Ch9 bootstrap 折现因子例（d=0.991909/0.980944/0.969406/0.956909）；par yield 式16.7/10.4 算例；久期/凸性对手算已知债券（平坦曲线年金债解析解）；DV01↔duration 换算自洽；KR01 之和=DV01 |
| R6 | options.py + derivatives_var.py（期权内核） | pytest 绿；BSM 对教材解析例：S=56,K=60,r=5%,σ=30%,T=1.5 → d1=0.2001, d2=−0.1674, c=8.3069, p=7.9715（含 parity 自检）；隐波反解对教材例（市价 7.00 → σ≈25.14%）；二叉树收敛例 20/50/100/500 步 → 3.082/3.067/3.059/3.055（美式 put 对教材节点值）；Greeks 对 BSM PDE 恒等式；DGV-VaR 在 delta 中性纯 gamma 组合上对解析二阶矩核对 |
| R7 | 组合汇总 + risk_report 扩展 + GUI 卡片 +（可选）闸扩展 | 合成混合组合端到端报告人工抽检；GUI 截图核对；闸扩展单独确认后实施 |

约束：年化 252 与 A 股口径沿用 constants.py 现状；day count 默认 actual/actual（中国债券惯例）但参数化；利率情景与关键利率节点集中常量并披露。

## 5. 数据可得性评估（明确声明）

- 当前 DB 只有股票日线/因子/沪深300基准；**期权与债券行情数据缺失**。
- 本 CR 全部模块为纯计算内核：输入为调用方给定的曲线/头寸参数，不读 DB、不接实时行情、不定义数据表。
- 行情接入（tushare 期权/债券接口、中债收益率曲线、FR007 互换曲线、50ETF 期权链）留待未来数据源 CR，届时本内核的函数签名即为其消费接口。

## 6. 不做（明确排除）

- 随机波动率模型（Heston 等）、波动率曲面拟合/插值、蒙特卡洛美式定价、Longstaff-Schwartz LSM——未来如需另议。
- 完整可转债条款定价（赎回/回售/下修在二叉树节点上加规则）：R5/R6 只提供债底折现与通用美式树框架，条款引擎单独 CR。
- 信用风险计量（PD/LGD 模型、CDS、CVA/DVA）：仅按书3 Ch17 把 spread duration 作为敏感度指标实现，不建违约模型。
- 互换/利率期货定价与 CTD 机制（书3 Ch19/20）、FRTB 全量 10 关键利率监管口径 KR01 VaR——公式已在摘要入库，实现留待有对应持仓/数据时。
- 奇异期权、delta 对冲回测模拟器、保证金/杠杆路径约束（LTCM 红线仍按 R1-R4 仅作文档条款）。

## 7. 关键取舍

1. **转债只做到「债底 + 通用美式树」两截，不做条款引擎**。赎回/回售/下修条款定价复杂度高且当前无转债行情，R5/R6 各交付一半可独立验收的能力，条款引擎留单独 CR——避免单阶段膨胀。
2. **DGV-VaR 定位为「适配器」而非新 VaR 引擎**：只生成 VaR 序列/分位数，统计回测完全复用 R2 的 `backtest_var_summary`，零重复造轮子。
3. **依赖锁死在 numpy/scipy**：YTM 与隐波反解都用 `scipy.optimize.brentq`，不引入 QuantLib 等重型库；同时修复 `pyproject.toml` 缺 scipy 显式声明的问题。
4. **KR01 纳入 R5、PCA 列可选**：KR01 有 ΣKR01=DV01 的强自检性质、对冲实用；PCA 需要历史利率变动数据（当前缺失），作为可选项不阻塞阶段验收。
5. **行情接入显式排除并写成契约**：内核输入为纯参数（曲线 dict/现金流表），未来 tushare 数据源 CR 直接以本内核签名为消费接口，避免「先接数据再算」的耦合返工。
