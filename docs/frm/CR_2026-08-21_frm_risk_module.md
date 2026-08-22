# CR：FRM 风险管理模块（QRE Risk Module）

- 日期：2026-08-21 ｜ 状态：✅ 用户批准开工（2026-08-21）
- **最终目标（用户明确）**：风险管理不仅套用至 QRE 量化交易回测，还要服务后续的**股票池项目**（cluster-ashare 聚类分析/因子挖掘）——risk 包因此必须设计为**可独立 import 的通用库**（不依赖 QRE 内部状态），cluster-ashare 侧后续直接复用。
- 知识来源：`docs/frm/FRM量化风控知识摘要.md`（FRM Part I 四册精读，公式/参数以该摘要为准，页码可回查）

## 1. 目标

为 QRE 回测引擎增加**风险管理分析层**：对任意策略回测产物（逐日收益序列/净值曲线）自动计算 FRM 标准风险指标，输出到回测报告与 dashboard，并可选接入晋升闸。覆盖 A 股日线股票量化场景；剔除银行/信用/操作风险等与股票量化无关的内容。

## 2. 范围（与 FRM 章节的映射）

| 模块 | FRM 出处 | 内容 |
|---|---|---|
| R1 尾部风险度量 | 书4 Ch1/Ch2；书2 Ch5 | VaR（历史模拟/参数法/EWMA 参数法三口径）、ES（Expected Shortfall，coherent）、偏度/峰度、Jarque-Bera 正态检验、√T 缩放规则（注明局限） |
| R1 波动率建模 | 书4 Ch3 | EWMA（RiskMetrics λ=0.94）、GARCH(1,1)（含长期方差 V_L=ω/(1−α−β) 外推）、波动率 regime 标记 |
| R1 收益分布与依赖 | 书2 Ch12 | simple/log 收益换算、Spearman/Kendall 秩相关（尾部/非线性依赖）、相关矩阵正定性检查 |
| R2 VaR 回测 | 书2 Ch6 | HIT 序列（I_t = 1{L_t > VaR}）、覆盖率 Bernoulli/LR 检验、独立性检验、多重检验假阳性警示 |
| R2 压力测试 | 书4 Ch8 | 历史情景回放（2015 股灾、2018 单边熊、2020 疫情、2024 小微盘流动性危机，窗口参数化）、核心/外围变量、reverse stress testing（给定亏损阈值反查所需市场冲击）、相关性崩溃提示 |
| R2 Bootstrap 推断 | 书2 Ch13 | Circular Block Bootstrap（块长 √n，保留波动聚类）给回测指标（收益/夏普/回撤）算置信区间；MC 标准误 σ/√b |
| R3 绩效风险指标 | 书1 Ch5 | Sharpe/Treynor/Sortino/Information Ratio/Jensen's α（与既有引擎指标对齐，缺则补） |

LTCM/Niederhoffer 等灾难案例（书1 Ch9）作为**红线条款**写进模块文档（相关性→1、流动性螺旋、杠杆路径），不做成功能。

## 3. 架构设计

- 新包 `src/quant_research_engine/risk/`：`tail.py`（VaR/ES/矩/JB）、`volatility.py`（EWMA/GARCH）、`dependence.py`（秩相关/正定性）、`backtest_var.py`（HIT/LR/独立性）、`stress.py`（情景回放/reverse）、`inference.py`（CBB bootstrap）、`performance.py`（绩效指标）、`report.py`（统一风险报告渲染）。
- 输入：回测产物的逐日收益序列（从既有 run 产物读取，不改动回测引擎本体）；纯函数 + pandas。
- 输出：`risk_report.json`（机读，供闸/前端）+ 报告 markdown 节（人读）。
- 集成点：
  - R3a 回测完成钩子自动生成风险分析节（追加到既有回测报告）
  - R3b GUI 回测详情页新增「风险分析」区
  - R4（可选，单独审批）：晋升闸加风险判据（如 99% ES 或回撤超阈值 → 警示/不通过）

## 4. Roadmap

| 阶段 | 内容 | 验收 |
|---|---|---|
| R0 | 本 CR + 设计对齐 | 用户批准 |
| R1 | risk 包核心（tail/volatility/dependence/performance），全纯函数单测（手算核对 + 教材例题复现） | pytest 绿 + 教材数值例题复现 |
| R2 | backtest_var / stress / inference（HIT-LR、历史情景库、CBB） | pytest 绿 + 合成数据已知答案核对 |
| R3 | 集成：回测报告风险节 + GUI 展示区 | 对 catalog 现有策略跑出真实风险报告并人工抽检 |
| R4 | （可选）晋升闸风险判据 | 单独 CR 审批 |

约束：A 股口径——交易日年化 252、涨跌停截断在收益序列中天然体现（不另做调整）、T+1 口径沿用引擎现状；所有参数（置信水平 95/99、λ=0.94、情景窗口、CBB 块长）集中常量定义并在报告披露。

## 5. 不做（明确排除）

银行监管（Basel 资本计量）、信用评级/违约模型、操作风险、OCR 扫描版 Part II 教材（成本高收益低，如后续需要另议）。
期权/债券/利率章节**已完成精读**（见 §6），公式入库备用；其实现（可转债、股指期货对冲、国债期货、Greeks 限额等）不在 R1-R4 范围，未来扩展时单独 CR。

## 6. 教材覆盖更新（2026-08-21 扩读）

知识摘要已扩至 32 章（`docs/frm/FRM量化风控知识摘要.md`，82KB）：新增书3 衍生品/期货/期权/利率/债券/互换 11 章 + 书4 定价惯例/利率/债券收益/久期凸性DV01/非平行移动/二叉树/BSM/Greeks 8 章，公式精确记录，供未来期权债券利率扩展直接引用。

## 7. GitHub 调研结论（少造轮子）

- 未发现权威的「FRM 教材全量复现」项目；最贴近的参考实现是 [tancredeg/var-backtesting](https://github.com/tancredeg/var-backtesting)（VaR/ES 五口径 + Kupiec/Christoffersen + Basel 三区 + 压力情景，README 的坑位提示有价值：MLE ν 需三参数联合优化、rolling VaR 必须 shift(1) 防前视、α+β<1 协方差平稳约束）。其工程结构不适合我们（单文件 notebook 型 portfolio 项目），**复用其方法论与校验基准，不复用代码**。
- 依赖决策（新增两个成熟库，避免自造 GARCH/bootstrap 轮子）：
  - `arch`：GARCH(1,1)（含 Student-t 创新）、EWMA/RiskMetrics、`arch.bootstrap.CircularBlockBootstrap`（CBB 直接现成）
  - `scipy.stats`：Jarque-Bera、Spearman/Kendall、正态分布分位数
  - VaR/ES（历史模拟/参数法）、Kupiec/Christoffersen LR 检验、HIT 序列、压力情景回放：公式简单（各 ≤50 行）且需贴合 A 股口径，**自实现**并用教材例题 + var-backtesting 的公开结果交叉校验。

