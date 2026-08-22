# FRM 量化风控知识摘要（2021 FRM Part I 精选章节）

> 来源教材（均位于 `docs/frm/`）：
> - 书4 = `4. Valuation and Risk Models.pdf`（Ch1/Ch2/Ch3/Ch8）
> - 书2 = `2. Quantitative Analysis.pdf`（Ch5/Ch6/Ch12/Ch13）
> - 书1 = `1. Foundations of Risk Management.pdf`（Ch5/Ch6/Ch9）
>
> 页码引用格式：`(书4 Ch1, PDF p18)`。PDF 页码与 TOC 页码一致（已用 书4 Ch1 p12 抽查对齐，无偏移）。
> 说明：抽取文本层完整，无缺失页；但部分数学公式在文本层中被压扁/乱序，本文按教材上下文还原为标准记法，个别无法 100% 确认排版的处以文字说明。任务书中列举的 Cornish-Fisher 调整、Kupiec/Christoffersen 检验名称在所读章节中**未出现**（书2 Ch6 讲的是 HIT/Bernoulli 框架下的 VaR 回测，未点名 Kupiec），如实标注，未做臆造补充。

---

## 书4 Ch1 Measures of Financial Risk（PDF p12–25）

### 核心概念
- Mean-variance framework：用收益的均值与标准差刻画机会集；efficient frontier 是给定风险下期望收益最大的组合集合。引入无风险资产后，efficient frontier 退化为过无风险点、与风险资产前沿相切的直线（CML 雏形），所有投资者持有同一切点组合 M（market portfolio），仅用借贷调节风险敞口。
- 金融收益的实证分布比正态更尖峰厚尾：S&P 500 日收益 2000–2019 日波动 1.187%，≥3σ 实际频率 1.64% vs 正态预测 0.27%（6 倍），≥6σ 实际 0.12% vs 正态 ~0（Table 1.3, p17）。
- VaR：给定时间 horizon 与置信水平 X%，损失分布的 X 分位数；不告诉我们超过 VaR 后损失有多糟。
- Expected Shortfall（ES，又称 C-VaR / tail loss）：损失超过 VaR 条件下的期望损失，是 coherent risk measure，VaR 不是。

### 公式
- 组合期望与方差（两资产）：`μp = w1·μ1 + w2·μ2`；`σp = √(w1²σ1² + w2²σ2² + 2ρ·w1w2σ1σ2)`（式 1.1–1.2）。n 资产：`σp² = ΣiΣj ρij·wi·wj·σi·σj`（式 1.4）。
- 标准正态密度：`f(x) = (1/√(2π))·e^(−x²/2)`（式 1.6）；z-score：`z = (x − μ)/σ`。
- 正态损失分布下（损失均值 μ、标准差 σ，置信水平 X%）：
  - `VaR = μ + σ·U`，U 为标准正态被超过概率为 (1−X) 的点。X=95% → U=1.645；X=99% → U=2.326（注意教材在损失为正号的约定下 U 取正尾点）。
  - `ES = μ + σ·e^(−U²/2) / ((1−X)·√(2π))`（式 1.7）。例：μ=−20, σ=30, X=99%：VaR=49.79，ES=59.96。
- Coherent 四公理（Artzner et al.）：Monotonicity、Translation Invariance（加现金 K 风险减 K）、Homogeneity（规模乘 λ 风险乘 λ）、Subadditivity（合并风险 ≤ 各自风险之和）。ES 满足全部；VaR 不满足 Subadditivity（教材用两份独立保险合约例子：单份 99% VaR=1M，合并后 21M > 2M；ES 则 21.12 < 16.2+16.2）。
- Spectral risk measure：对损失分位 p 赋权 w(p) ∝ `e^(−(1−p)/γ)`，γ 越小风险厌恶越高；coherent ⟺ w(p) 为 p 的非减函数。

### 方法要点
- VaR 三要素：horizon、confidence level、损失分布（收益取负号）。离散/均匀分布下 VaR 直接在累计损失分布上查表，落在区间边界时可取平均。
- ES ≥ VaR 恒成立；监管趋势：FRTB 用 97.5% ES 取代 99% VaR（10 天 horizon）。
- 局限：VaR 忽略尾部形状；均值-方差框架隐含正态或二次效用假设，对厚尾资产系统性低估极端风险。

### 对 A 股日线量化组合的落地提示
- 日线频率下均值相对波动可忽略（S&P 日均收益 0.024% ≈ σ/50，A 股同量级），算 VaR/ES 时可设 μ≈0，但长 horizon（月度以上）必须放回均值。
- A 股收益厚尾且涨跌停截断：正态假设的 VaR 会明显低估尾部，组合层面应直接报告 ES（97.5% 或 99%）而非只看 VaR。
- 构建组合风险预算时用 ES 的 subadditivity 做子组合加总；VaR 加总会高估或低估分散化收益，不可加。

---

## 书4 Ch2 Calculating and Applying VaR（PDF p26–37）

### 核心概念
- 三大 VaR/ES 计算路线：historical simulation（非参数，直接用历史日变动当未来情景）、delta-normal（参数法，线性组合 + 多元正态）、structured Monte Carlo（从假设分布随机抽样生成情景）。
- 线性组合（股票多空组合、远期）ΔP 是风险因子变动的线性函数；含期权的组合非线性，delta 只是小变动近似，gamma 度量曲率。

### 公式
- 时间尺度缩放（平方根规则）：`VaR(T,X) = √T · VaR(1,X)`；`ES(T,X) = √T · ES(1,X)`。前提：日变动独立、零均值、同分布（正态时精确，否则近似）。
- 线性组合：`ΔP = Σi δi·ΔSi`（式 2.2）；改写为 `ΔP = Σi αi·xi`（式 2.4）：价格类因子（股票、汇率）用百分比变动 xi=ΔSi/Si、αi=δi·Si；利率/利差类因子用实际变动 xi=ΔSi、αi=δi。
- Delta-normal：`μp = Σ αiμi`；`σp² = ΣiΣj αiαjρijσiσj`；`VaR = μp + σp·U`；`ES = μp + σp·e^(−U²/2)/((1−X)√(2π))`。常假设 μp=0 → `VaR = σp·U`。
- Delta-gamma 近似：`ΔP ≈ δ·ΔS + ½·γ·(ΔS)²`（式 2.3；Taylor 展开）；多因子（无 cross-gamma）：`ΔP ≈ Σ δiΔSi + ½ Σ γi(ΔSi)²`。

### 方法要点
- Historical simulation 流程：取最近 501 天数据 → 500 个日变动情景 → 逐情景重估组合 → 损失从大到小排序 → 99% VaR = 第 5 大损失（5/500=1%）；ES = 比 VaR 更差的损失之平均（例：4 笔均值 5.8M）。非整数分位可插值。价格类因子按比例变动回放，利率/利差按绝对变动回放。
- Full revaluation 慢时用 Greeks（delta / delta-gamma）加速；MC 中对应 partial simulation。
- Stressed VaR/ES：从对当前组合最不利的 12 个月历史时期取情景（典型 250 个情景），而非紧挨着的近期；其余计算相同。
- Delta-normal 局限：非线性组合误差大（ATM 期权 gamma 高，delta 严重失真；ITM 近似远期则较准）；对 delta-neutral 组合，残余风险主要是曲率风险，delta-normal 完全漏掉；二次（gamma）模型无解析解。
- Monte Carlo：可对任意分布抽样（不限正态），用 percentile-to-percentile 变换把多元正态样本映射到非正态边际（Gaussian copula，Hull & White 1998）；1000 次试验下 99% VaR=第 10 差损失，ES=更差 9 笔均值。缺点：计算密集。
- Correlation breakdown：压力期波动率与相关性同升（"in stressed markets all correlations go to one" 是夸张但方向真实）；算尾部风险应估压力态相关性而非常态。
- Worst-case scenario（WCS）分析：用 MC 统计 N 期重复试验中的最差结果分布；通常过于悲观，不应替代 VaR/ES。

### 对 A 股日线量化组合的落地提示
- 纯股票多头/多空组合是线性组合：historical simulation 直接对持仓用日收益序列重放即可，工程成本最低，且自动携带肥尾与相关结构——作为基线实现首选。
- 样本量：500 情景下 99% VaR 由第 5 大损失决定，统计噪声大；A 股个股历史短、停牌多，建议 ≥2 年（~500 交易日）起步，99% 置信水平下对尾部估计保持谨慎，可配合插值。
- 涨跌停处理：历史回放时涨跌停日的收益是被截断的（真实"意愿"波动更大），跌停日无法卖出意味着实际损失可能大于当日收盘损失——回测 VaR 时对连续跌停品种要单独加压。
- delta-normal 作为快速日频监控可用（`VaR = σp·U`），σp 用 EWMA/GARCH 更新（见 Ch3）；√T 规则在 A 股有涨跌停和 T+1 的情境下偏乐观，长 horizon 慎用。

---

## 书4 Ch3 Measuring and Monitoring Volatility（PDF p38–51）

### 核心概念
- 收益偏离正态的三方式：厚尾、非对称、参数随时间不稳定；时变波动率（随机波动）足以产生厚尾——conditionally normal（每日条件正态、σ 时变）叠加出 unconditionally 厚尾分布。
- Regime switching：波动率跳变（如 1%→3%）而非缓变，使基于缓变假设的模型突然失效。
- EWMA 与 GARCH(1,1) 是监测条件波动率的两个标准工具；GARCH 比 EWMA 多了向长期方差的 mean reversion。

### 公式
- 日收益定义：`r_i = (S_i − S_{i−1})/S_{i−1}`（风险管理惯例；ln 收益在日频下几乎等价）。
- 等权波动率（最大似然形式，两个简化：m−1→m、均值→0）：`σn² = (1/m)·Σ_{i=1..m} r²_{n−i}`（式 3.1），variance rate = 均方收益。波动率估计的标准误 ≈ `σ̂/√(2(m−1))`（m=10、σ̂=1.08% → 标准误 0.25%，置信区间很宽）。
- **EWMA**：`σn² = λ·σ²_{n−1} + (1−λ)·r²_{n−1}`（式 3.2）。k 天前权重 = λ^k·(1−λ)。RiskMetrics 推荐 **λ=0.94**（日频、跨市场通用）。λ 过高（0.995）反应迟钝，过低（0.5）估计本身过噪。最优 λ 可用"预测 vs 后续 20–30 天实现波动"最小误差或最大似然选取。只需存储最新方差估计，递归更新。
- 加权 historical simulation：情景按距今远近赋指数权重（教材示例约 λ=0.99，明显高于 EWMA 的 0.94）；排序后累计权重跨过 (1−X) 处即 VaR，ES 按尾部权重归一化加权平均。stressed VaR 不应加权（压力期内各日等权）。
- MDE（multivariate density estimation）：按"与今天相似度"赋权，距离度量 `Σi a_i·(X_i − X_i*)²`，X 为条件变量（如利率水平、GDP 增速）。
- **GARCH(1,1)**：`σn² = ω + α·r²_{n−1} + β·σ²_{n−1}`（式 3.4），其中 `ω = γ·V_L`，`α+β+γ=1`，`V_L = ω/(1−α−β)` 为长期平均方差率。示例：ω=0.000003, α=0.12, β=0.87 → γ=0.01, V_L=0.0003（长期日波动 1.732%）。GARCH(p,q)：p 个滞后平方收益 + q 个滞后方差；(1,1) 最常用。EWMA 是 γ=0, α=1−λ, β=λ 的特例。两者都是 AR(1) 类模型。
- Mean reversion 下的长期方差外推：`E[σ²_{n+t}] = V_L + (α+β)^t·(σ²_n − V_L)`；T 日波动用 T 日平均期望方差开根（而非 √T·当前 σ）。当前 σ 高于长期均值时 √T 规则高估 VaR，反之低估。
- 隐含波动率：年化为惯例，日化 ÷√252（20%/年 ≈ 1.26%/日）；前瞻性强于历史法；VIX = 30 天 S&P 500 期权隐含波动指数（常态 10–20，2008.10 达 80，2020.03 再度飙升）。
- 协方差 EWMA：`cov_n = λ·cov_{n−1} + (1−λ)·x_{n−1}·y_{n−1}`（式 3.5），λ 应与方差更新一致（如 0.94）；相关系数 = cov/(σx·σy)。GARCH 亦可更新协方差但多维一致性处理复杂。

### 方法要点
- 等权窗口的两难：m 大（250）不敏感、含陈旧数据；m 小（10–20）噪声大且大收益进出窗口会造成波动率跳变。EWMA 解决此问题。
- 条件正态 + 当前 σ̂（如 2%）优于用历史厚尾分布或恒定 1% 假设。
- 均值回复对可交易价格不适用（否则存在套利），但对波动率、利率合理。

### 对 A 股日线量化组合的落地提示
- 日频组合风险监控直接用 EWMA(λ=0.94) 更新个股与组合方差/协方差矩阵——O(1) 递归、无需存历史窗口，适合每日盘后批处理。
- 需要 5/10 日 VaR 时用 GARCH(1,1) 的均值回复公式修正，而非裸 √T：A 股波动聚类显著，暴涨期 √T 会高估后续风险（波动将回落），平静期反之。
- A 股无个股期权，隐含波动率缺失；可用 50ETF/300ETF 期权隐含波动率作为市场层面前瞻 σ，与组合 EWMA 估计对照。
- 协方差矩阵用同一 λ=0.94 的 EWMA 协方差 + 相关系数分解维护；注意涨跌停日 r 被截断会低估当日 r²，EWMA 输入会系统性偏小（可考虑对触及涨跌停的收益做标记或放大处理）。

---

## 书4 Ch8 Stress Testing（PDF p110–125）

### 核心概念
- Stress testing：评估"极端但 plausible"情景下机构资本与流动性是否存活的**前瞻性**工具；VaR/ES 是后顾的分布度量，压力测试回答 "What if"，不给出概率分布。
- Stressed VaR/ES：以"重演某个 12 个月压力期"为条件的条件损失分布度量，属于 historical stress testing；horizon 短（1–10 天）。Stress testing horizon 长（3 个月–2 年，甚至数十年），评估整个压力期重演。
- Reverse stress testing：反向搜索"什么样的情景组合会让机构失败"。

### 公式/规则
- Basel 规则：stressed VaR/ES 必须基于对当前组合显著不利的 **12 个月**期间。
- 情景放大做法（把历史压力期所有因子变动 ×2/×3）是近似——因子间关系非线性且压力期相关性上升，不能简单线性放大。

### 方法要点
- 情景三类来源（p112–113）：① historical scenarios（2008 危机、1987.10.19 单日 −22.3σ、1998 俄罗斯违约 flight-to-quality 等；价格类按比例变动、利率类按绝对变动回放）；② stress key variables（利率 +200bp、波动率 +100%、股指 −25%、失业率 +4%、GDP −2% 等）；③ ad hoc scenarios（反映当前环境、无历史先例的事件，如英国脱欧公投；由 3–5 人多背景委员会头脑风暴）。
- 模型构建：情景只指定少数 core variables，其余 peripheral variables 用模型（如回归）推出——关键是估计**压力态下**的变量关系而非正常态（相关性升高、回收率下降）；信用损失可用评级机构历年违约率数据对 GDP/失业率建模再放大。
- Knock-on effects：二阶效应（对手方反应放大冲击：房价跌→策略性违约→供给增加→加速下跌；flight to quality；银行间惜贷）。
- 监管：CCAR（资产 >500 亿美元银行，baseline/adverse/severely adverse + 内部情景，需交资本计划）；DFAST（100–500 亿，无需资本计划）；每个情景含 28 个变量。测试失败 → 补充资本 + 限制分红。
- 治理：董事会定框架与风险偏好，高管执行并随环境调整情景（不能机械重复同一套情景），独立验证 + 内审；压力测试无法像 VaR 那样回测（极端事件无频率基准）。
- Basel 委员会总结的危机前压力测试缺陷（p117–118）：高管不参与、机械执行、缺乏 enterprise-wide 聚合、忽略 knock-on effects、情景太温和太短、低估相关性、过度依赖历史、忽略新产品/新敞口、忽略流动性冲击。

### 对 A 股日线量化组合的落地提示
- 直接可用的情景库：2015.6–2016.2 股灾（千股跌停+流动性枯竭）、2018 年单边熊市、2020.2 疫情跳空、2024 年初微盘流动性危机。用历史情景法逐日回放组合净值。
- A 股特有的情景设计：连续跌停无法卖出（流动性 knock-on）、st 股 ±5% 与主板 ±10%/创业科创 ±20% 的混合限制、停牌复牌跳空。压力测试要模拟"想卖卖不掉"的持仓冻结，而不仅是价格冲击。
- 反向压力测试对应到组合层面：搜索"回撤达到清盘线/止损线"所需的最小情景恶化倍数，作为仓位上限约束。
- 情景应随组合暴露变化（持仓集中在小盘/单一行业时，压力情景也要针对性调整），不做机械重复。

---

## 书2 Ch5 Sample Moments（PDF p74–93）

### 核心概念
- 用样本矩估总体矩：sample analog 原则（把 E[·] 换成样本平均 (1/n)Σ）。均值估计量在 iid 下是 BLUE（Best Linear Unbiased Estimator）、无偏、一致（LLN），大样本近似正态（CLT）。
- 金融收益四阶矩刻画的两个 stylized facts：负偏（股票/债券/原油）与厚尾（峰度 >3）；频率越低（月/季）越接近正态。
- 分位数统计（median、IQR）对异常值稳健，矩统计不稳健。

### 公式
- 样本均值 `μ̂ = (1/n)ΣX_i`；无偏（Bias=0）；`V[μ̂] = σ²/n`；standard error = `σ/√n`（随 n 减小；标准差不随 n 变）。
- 样本方差 `σ̂² = (1/n)Σ(X_i−μ̂)²`：有偏，`E[σ̂²] = ((n−1)/n)·σ²`；无偏版 `s² = (1/(n−1))Σ(X_i−μ̂)²`。惯例 n>30 用 σ̂²。标准差估计量因开根号总有偏，大样本可忽略。
- 年化：均值线性放大（日×252，或按市场惯例 245/260；周×52；月×12），标准差乘 `√scale`（日 σ×√252）。log 收益可加：`r_T = Σ r_t`，n 期均值 nμ、方差 nσ²（需收益间不相关）。
- 偏度：`skew(X) = E[(X−μ)³]/σ³`，估计 `ŝ = μ̂3/σ̂³`，`μ̂3 = (1/n)Σ(x_i−μ̂)³`。峰度：`k = E[(X−μ)⁴]/σ⁴`，估计 `k̂ = μ̂4/σ̂⁴`。正态 k=3；excess kurtosis = k−3（注意软件口径）。偏度/峰度不需年化。
- 中位数：排序后奇数取 `x_{(n+1)/2}`，偶数取两中点均值；α 分位数取排序位置 αn（非整数取相邻平均，软件间插值方法不同）。`IQR = q75 − q25`。
- 协方差 `σ̂xy = (1/n)Σ(x_i−μ̂x)(y_i−μ̂y)`（除 n−1 无偏）；相关 `ρ̂ = σ̂xy/(σ̂x·σ̂y)`；样本相关即使成分无偏也仍有偏（非线性变换不保无偏）。
- LLN（Kolmogorov）：`μ̂_n → μ` a.s.（一致性）。CLT（Lindeberg–Lévy）：`√n(μ̂−μ) →d N(0, σ²)`，实用近似 `μ̂ ~ N(μ, σ²/n)`；偏态数据 n≈40 已较好。
- Coskewness：`s(X,X,Y) = E[(X−μx)²(Y−μy)]/(σx²·σy)` 两种；Cokurtosis 三种（(2,2) 型度量两序列波动联动，`k(X,X,Y,Y)=E[(X−μx)²(Y−μy)²]/(σx²σy²)`）；二元正态时对称 cokurtosis ∈[1,3]、随 |ρ| 增大。

### 方法要点
- 估计量 vs 估计值（estimator/estimate）；无偏不必最优（方差可能大）；一致性要求偏差与方差都随 n→0。
- 实证锚点（Table 5.1，1989–2018）：股票日收益 kurtosis 6.39、skew −0.20；原油 kurtosis 12.78；债券接近正态。相关性随频率变化（日频由流动性噪音主导，月频更反映宏观共振）。

### 对 A 股日线量化组合的落地提示
- A 股一年 ~243 交易日，年化用 252 或 243 需在项目内统一（教材：惯例随市场而异，关键是自洽）。
- 均值估计极不可靠（标准误 σ/√n），波动率估计所需样本远小于均值——策略评估应以波动/回撤类指标为主，均值类（年化收益）给置信区间。
- 因子收益分布检查：报告 skew/kurtosis（用样本 analog 公式）+ median/IQR 稳健对照；A 股个股厚尾比美股更甚，分位数指标更可信。
- 估计组合相关矩阵时注意频率效应与涨跌停截断：跌停日收益截断会低估协方差。

---

## 书2 Ch6 Hypothesis Testing（PDF p94–111）

### 核心概念
- 假设检验 = 问"若原假设为真，观察到这份数据的概率多大"。六要素：null、alternative、test statistic、size（α，Type I 错误概率）、critical value、decision rule。
- Type II 错误概率 β；power = 1−β，取决于样本量、真值与 H0 的距离、size。
- VaR 模型回测转化为对 HIT 序列均值/独立性的检验。
- Multiple testing：同一数据上反复检验会使实际 Type I 错误率远超名义 α。

### 公式
- 均值检验统计量：`T = (μ̂ − μ0)/(σ̂/√n) ~ N(0,1)`（式 6.1，CLT 渐近）。n≤30 用 Student's t_{n−1} + 无偏方差 s²。
- 常用临界值：双侧 10%/5%/1% → ±1.645/±1.96/±2.57；单侧 5% → 1.645（下尾 −1.645），单侧 1% → −2.32/2.32。
- 双侧置信区间：`[μ̂ − c_α·σ̂/√n,  μ̂ + c_α·σ̂/√n]`（式 6.4）；单侧为半无穷区间。
- p-value：双侧 `2·(1 − Φ(|T|))`（式 6.5）；单侧下尾 Φ(T)、上尾 1−Φ(T)。p<α → 拒绝。
- 两均值相等检验（配对、可相关）：令 Z = X−Y，检验 μz=0；`T = (μ̂x−μ̂y)/√((σ̂x² + σ̂y² − 2σ̂xy)/n)`——正相关降低差值方差。
- **VaR 回测**：`HIT_t = I[L_t > VaR_t]`；p-VaR 定义 `Pr(L > VaR) = 1 − p`（式 6.6）。well-specified 模型的 HIT ~ iid Bernoulli(1−p)。Null：`E[HIT_t] = 1−p`（95% VaR → 5%）。三种检验方法（教材仅给名称/思路，未点名 Kupiec/Christoffersen）：① violations 次数的精确分布；② 违约频率均值的渐近 CLT 检验；③ 基于 Bernoulli 的 likelihood ratio 检验。独立性检验：若模型正确 `Pr(连续两次 HIT) = (1−p)²`，可检验 `H0: E[HIT_t·HIT_{t+1}] = (1−p)²`。
- 多重检验：n 个独立检验名义 5%，至少一个假阳性概率 `1 − 0.95^n`（n=10 → 40.1%，n=100 → 99.4%）。校正：Bonferroni / Holm-Bonferroni（简单但保守、power 低），FDR / FWER 控制（更复杂）。

### 方法要点
- 不拒绝 ≠ null 为真（只是证据不足）；大样本下任何微小偏差都统计显著——需结合 practical significance（经济量级）。
- size 选择权衡两类错误的成本；power 随 n 与真值偏离度上升。

### 对 A 股日线量化组合的落地提示
- 策略/因子收益显著性：对日超额收益序列做 `T = μ̂/(σ̂/√n)` 检验；但 A 股单策略样本常只有 2–3 年（~500–750 日），t 检验结论要附置信区间与经济量级判断。
- **这是量化过拟合的核心警示**：在同一回测集上筛了上百个因子/参数后"显著"的结果大概率是假阳性（1−0.95^100≈99.4%）。工程上：留样本外区间、记录测试次数、用 Bonferroni/FDR 校正或直接提高显著性门槛。
- VaR 回测落地：每日比对实现损失与 1 日 VaR 产生 HIT 序列，检验违约率是否 ≈1−p 及 HIT 是否独立（A 股波动聚类强，HIT 聚集——独立性检验往往比无条件的覆盖率检验先挂）。
- 两策略收益差检验用配对差值法（自动利用两者正相关缩小标准误），比各自单独检验 power 高。

---

## 书2 Ch12 Measuring Returns, Volatility, and Correlation（PDF p224–235）

### 核心概念
- Simple return 与 log return 的换算与各自适用场景；波动率的时间缩放；正态性检验（Jarque-Bera）与幂律尾部；相关 ≠ 依赖，Spearman/Kendall 度量非线性依赖。

### 公式
- `R_t = (P_t − P_{t−1})/P_{t−1}`（simple）；`r_t = lnP_t − lnP_{t−1}`（log）。换算 `1 + R_t = e^{r_t}`（式 12.5）。多期：simple 用连乘 `1+R_T = Π(1+R_t)`，log 用求和。log < simple 恒成立；±12% 内误差 <0.85%。simple return 截面可加（组合收益 = 权重加权），log return 不可。
- 缩放：均值、方差随 horizon 线性，σ 随 `√h`；年化 `σ_annual = √252·σ_daily`（式 12.7），月频 ×√12。前提：收益无序列相关。
- 收益模型：`r_t = μ + σ·ε_t`，ε iid（常设 N(0,1)）。
- **Jarque-Bera**：`JB = (T−1)·[Ŝ²/6 + (k̂−3)²/24] ~ χ²(2)`（式 12.11）；临界值 5%→5.99、1%→9.21；p = 1−F_χ²(JB)。实证：S&P 500 日收益 skew −0.74、kurtosis 23.79，JB 强拒绝正态；低频（季）更接近正态。
- 幂律尾部：`P(X > x) = k·x^(−α)`；Student's t 是典型代表；ln(尾概率) 对 x 作图：正态为二次（快速衰减），t 为线性（慢衰减→厚尾）。4σ 损失：正态 0.003%，标准化 t4 为 0.24%（80 倍）。
- Spearman rank correlation：`ρS = Cov(Rank_X, Rank_Y)/√(V[Rank_X]V[Rank_Y])`；秩互异时 `ρS = 1 − 6·Σ(Rank_Xi − Rank_Yi)²/(n(n²−1))`（式 12.13）。并列取平均秩。对异常值稳健、对任意单调增变换不变。
- Kendall's τ：`τ = (nc − nd)/(nc + nd + nt)`（式 12.14），nc/nd/nt = concordant/discordant/tie 对数；同样单调变换不变；正态下 τ 比 ρ 更接近 0，符号相同、绝对值更小时**不构成**非线性证据。
- 相关矩阵必须 positive definite（任何线性组合方差 ≥0）；两种结构化：equicorrelation（所有 ρij=ρ）与 factor structure（`ρij = γi·γj`，|γ|≤1，对应单因子/CAPM 型相关）。

### 方法要点
- VIX 类隐含波动率前瞻但只对有流动期权市场的资产可得；BSM 隐含波动率因恒定波动假设在不同行权价/期限间不一致。
- Pearson 只测线性依赖；共同异方差（vol 同涨同落）是非线性依赖，Pearson 抓不到。ρ 与 ρS 差异大 ⇒ 显著非线性。

### 对 A 股日线量化组合的落地提示
- 日频因子/组合计算统一用 log return（可加性，便于多期聚合与波动建模）；但**组合净值与绩效归因必须用 simple return**（截面可加）。大单日涨跌幅（涨停附近 ±10%/±20%）两者差异不可忽略。
- 上线前对策略日收益跑 JB 检验记录 skew/kurtosis——A 股日频收益几乎必然拒绝正态，这是选 ES/历史模拟而非参数正态 VaR 的实证依据。
- 横截面选股因子的 IC 建议同时报 Pearson 与 Spearman（rank IC 对极端收益稳健，业界惯例即 rank IC）；两者背离提示因子收益关系非线性。
- 组合相关矩阵用于优化器前检查正定性，因子数多时用因子结构压缩（`ρij=γiγj`）。

---

## 书2 Ch13 Simulation and Bootstrapping（PDF p236–251）

### 核心概念
- Monte Carlo：从完整设定的 DGP 抽样逼近 E[g(X)]；bootstrapping：不设定 DGP，直接对观测数据重抽样。误差都 ∝ 1/√b。
- iid bootstrap 破坏时间依赖；circular block bootstrap（CBB）保留波动聚类等序列依赖。

### 公式
- MC 期望逼近：`E[g(X)] ≈ (1/b)·Σ_{i=1..b} g(x_i)`（式 13.1）；标准误 `σ̂_g/√b`，`σ̂²_g = (1/b)Σ(g_i − ḡ)²`（式 13.3）。抽样误差 ∝ 1/√n（n 翻倍 4 倍 → 误差减半）。
- 逆变换采样：U~Uniform(0,1) → `F_X⁻¹(U) ~ F_X`；PRNG 由 seed 初始化，同 seed 完全复现（监管合规、分布式组合模拟共用因子序列）。
- Antithetic variates：成对取 (U, 1−U)，正态下即 (x, −x)；标准误变为 `σ_g·√(1+ρ)/√b`（式 13.8，ρ<0 才有效，g 需单调）。期权例：ρ=−43%，标准误降 ~25%，等效多 78% 样本。
- Control variates：选均值 0 且与目标相关的 h(X)，回归 `g(x_i) = α + β·h(x_i) + ν_i`（式 13.9）取最优 β；例：用 BSM 解析价做 put 控制变量估 call，ρ=−44%，两者结合标准误降 33%（等效 +125% 样本）。
- iid bootstrap：从 {1..n} 有放回抽 m 个下标构造样本；`E[g(X)] ≈ (1/b)Σ_j(1/m)Σ_i g(x*_{ji})`（式 13.10）。
- CBB：块长 q，块内连续、块间有放回、越界回绕（circular）；块长经验法则 `q ≈ √n`（示例：13,000 日观测用 126，约半年）。
- Bootstrap VaR（式 13.11：`argmin_VaR Pr(L>VaR) = 1−p`）：以 252 个 bootstrapped 日 log 收益求和得 1 年收益，b=100,000 次，取经验 (1−p) 分位。CBB 比 iid 给出更厚的左尾（0.1% VaR：53.5% vs 44.1%）——iid 重抽样把高低波动期"均衡化"，低估了连续高波动路径的概率。

### 方法要点
- MC 最大风险是 DGP 误设（分布、动态、参数估计错）；bootstrap 最大风险是"现在必须像过去"（2008.10 用含平静期的数据 bootstrap → 乐观）。
- 两者都有 Black Swan 问题：bootstrap 尤其严重——无法生成样本中没出现过的情形；好的参数模型至少允许超过历史的冲击。
- 复杂 DGP 下 MC 计算成本高；有解析解就优先解析解。

### 对 A 股日线量化组合的落地提示
- 回测显著性/净值路径不确定性：对策略日收益序列做 CBB（块长 ~√T，如 3 年数据取 ~√750≈27 天，约一个月）重抽样，得到年化收益/最大回撤的分布而非点估计——A 股波动聚类极强，禁用 iid bootstrap。
- 涨跌停与停牌造成的数据缺口：bootstrap 前需决定缺失日处理口径（剔除/置零/顺延），CBB 块会携带这些特征，抽样结果更真实。
- 固定随机种子、记录 b 与标准误作为回测报告要件（教材强调可复现性与监管合规）。
- 任何基于历史重放/重抽样的结论都外推不出"未曾发生的跌停连锁"，需与 Ch8 的假设性压力情景互补。

---

## 书1 Ch5 Modern Portfolio Theory and CAPM（PDF p84–95）

### 核心概念
- MPT：理性投资者在均值-方差空间选组合，分散化可消除个股 specific risk；efficient frontier。CAPM：均衡下只有 systematic risk（β）获得补偿。
- MPT 实证痛点（Box 5.1）：均值-方差最优组合对输入**极度敏感**，且预期收益估计误差的影响 ≥ 方差/协方差估计误差的 **10 倍**（Best & Grauer 1991；Chopra & Ziemba 1993）。
- 危机后资产间相关性升高且不稳定（Israelsen：美股-美债相关 2006=0.21 → 2008=0.46 → 2010=−0.38），催生 risk-regime 切换的配置方法。

### 公式
- Beta：`β_i = cov(R_i, R_M)/σ²_M = ρ_{iM}·σ_i/σ_M`（式 5.1）；`Σ x_i·cov(R_i,R_M) = σ²_M`（式 5.2），市场组合 β=1。
- CAPM：`E(R_i) = r + β_i·[E(R_M) − r]`（式 5.3）。
- CML：`E(R_p) = r + [(E(R_M) − r)/σ_M]·σ_p`（式 5.4）；two-fund separation：无风险资产 + 市场组合。
- 市场模型（β 的估计）：`R_it − r_t = α_i + β_i·(R_Mt − r_t) + ε_it`（式 5.5，时序回归；raw beta 未调整，可向均值调整得 adjusted beta）。
- 绩效指标：
  - Sharpe：`SPI = (E(R_i) − r)/σ_i`
  - Treynor：`TPI = (E(R_i) − r)/β_i`（适用于充分分散组合）
  - Jensen's alpha：上式回归截距 α_i
  - Sortino：`SR = (R_p − T)/√(E[min(0, R_pt − T)²])`，分母为 downside deviation，T = MAR（可设无风险或 hurdle rate）
  - Tracking error：`TE = std(R_p − R_b)`（active return 的标准差）；Information ratio：`IR = 平均 active return / TE`
- 杠杆β调整：`Unlevered β = Levered β / [1 + (1−tax)·(D/E)]`。

### 方法要点
- CAPM 实证支持弱（存在市场外因子）；CML 用 σ 度量风险（组合），SML 用 β 度量风险（个股）。
- β>1 激进、<1 防御；估计 β 只是统计估计量，应给置信区间。
- TPI 与 JPI 在 β>0 时同号一致，但组合排名可不同。

### 对 A 股日线量化组合的落地提示
- SPI/Sortino/IR 是日线组合报表标配：IR 的基准用中证全指或沪深300；A 股做空受限，Sortino 比 Sharpe 更贴合"只厌恶下侧波动"的实际。
- β 估计用日收益对市场指数时序回归，窗口 1–2 年；注意 A 股涨跌停截断会压缩极端日协方差从而低估高波动股的 β。
- 直接照搬 Markowitz 优化在 A 股危险：预期收益（因子 IC 转收益）的估计误差被 Box 5.1 证明是最致命的输入——实务上应收缩均值输入（shrinkage）或用风险预算/最小方差等对均值不敏感的目标。
- 相关性 regime 不稳定 → 定期（如季度）重估协方差矩阵，或按 EWMA 自适应（书4 Ch3）。

---

## 书1 Ch6 APT and Multifactor Models（PDF p96–103）

### 核心概念
- APT（Ross 1976）：期望收益是多个系统性因子的线性函数，只假设无套利 + 分散化消除特异性风险，不指定因子是哪些；CAPM 是其单因子特例。
- 三类因子模型（Connor）：macroeconomic（Chen-Roll-Ross）、fundamental（Fama-French）、statistical（PCA）。

### 公式
- APT 收益生成：`R_i = E(R_i) + β_{i1}[I_1 − E(I_1)] + … + β_{iK}[I_K − E(I_K)] + ε_i`（式 6.1，`I_k−E(I_k)` 为 surprise factor）。
- 无套利定价结果（充分分散组合）：`E(R_p) = E(R_z) + Σ_k β_{pk}·[E(I_k) − E(R_z)]`（式 6.2，R_z 为 zero-beta/无风险收益）。
- Fama-French 三因子：`E(R_p) − r = α_p + β_{p,M}[E(R_M)−r] + β_{p,smb}·E(SMB) + β_{p,hml}·E(HML)`（式 6.3）；对应时序回归式 6.4。SMB=小市值−大市值收益差；HML=高−低 book-to-market 收益差（HML 斜率是相对困境的代理）。五因子（2015）+ RMW（盈利 robust−weak）、CMA（投资 conservative−aggressive），加入后 HML 冗余。Carhart（1997）加动量 MOM（上月 winner−loser）。
- Chen-Roll-Ross 宏观因子：长短期利差、预期/未预期通胀、工业产出、高低信用级利差。Burmeister 等：信心、利率期限、通胀、商业周期、市场时机五风险。
- 因子对冲：对每个因子取相反暴露使组合 β=0（zero-beta）；可只对冲部分因子保留目标暴露；因子数要 parsimonious。

### 方法要点
- 因子对冲的权衡：再平衡太疏 → tracking error；太频 → 交易成本侵蚀。
- 模型风险：因子模型不能捕捉非线性、假设平稳性而分布随时间漂移、压力期失效（2007–09 多数 market-neutral 基金亏损）。
- ETF 可作为可交易因子载体做暴露对冲（SPDR 九行业例，把 ~125,000 个方差估计降到 ~5,000）。

### 对 A 股日线量化组合的落地提示
- A 股多因子风控映射：市场（中证全指）、SMB、HML 直接适用且 SMB 在 A 股效应强；行业中性化 + 风格（size/价值/动量）暴露监控是组合风控的第一层。
- 用因子模型压缩协方差矩阵（个股 ~5000 只全协方差不可估），与书2 Ch12 的 factor structure `ρij=γiγj` 一致。
- 对冲工具现实约束：A 股个股做空难，因子对冲主要靠股指期货（IF/IC/IM）对冲市场 β 与部分 size 暴露（IM 对应小盘），残余风格暴露靠调仓而非衍生品。
- 警惕因子拥挤：同一批公开因子被大量量化产品使用时，其"正常关系"会在赎回/去杠杆时失效——衔接 Ch9 的 LTCM 教训。

---

## 书1 Ch9 Learning from Financial Disasters（PDF p134–151，略读提炼：与策略失效相关的教训）

### 与量化策略失效直接相关的案例与教训
- **Niederhoffer 卖裸深度虚值 put（p140）**：策略假设"单日跌 >5% 罕见"（正态下几乎不可能），1997.10 单日跌 >7% → 保证金追缴 → 强制平仓清零。教训：① 厚尾市场里"长期小赚 + 小概率巨亏"的结构不是免费午餐；② 尾部风险不会因多年未发生而消失。
- **LTCM（p140–142）**：relative-value/收敛策略 + 25:1 杠杆。失效链条：俄罗斯违约 → flight to quality → 相关性与波动率飙升、"正常"价差发散、流动性蒸发 → 看似分散的组合表现得像单一集中持仓，market-neutral 变成方向性暴露（且是错的一侧）→ margin call 螺旋。其 VaR 体系三大缺陷：① 10 天 horizon 太短（经济资本 horizon 应是"有序平仓/危机展开所需时间"）；② 静态 VaR 不含流动性风险；③ 相关/波动偏离只能靠压力测试捕捉（最弱环节）。10 日 VaR 估 3.2 亿美元，实际亏损超 10 亿。讽刺的是策略中期方向是对的——接管银行后来大赚：**死在路径上，不是死在方向上**。
- **Metallgesellschaft（p138–139）**：rolling hedge 用短期限期货对冲长期固定价格供货合同。backwardation→contango 切换使移仓从盈利变亏损，叠加现货大跌 → 13 亿美元期货保证金现金流压力；经济上对冲了，现金流/会计上没对冲（P&L hedge ≠ cash-flow hedge），母公司强平把浮亏变实亏。教训：评估策略要同时看经济敞口与现金流/保证金路径；曲线形态（curve risk）与基差（basis risk）是独立风险源。
- **Lehman / Northern Rock / Continental Illinois（p136–138）**：funding liquidity 风险——用短期批发资金（repo/CD）支持长期非流动性资产，信心消失 → 融资渠道同步冻结（"地理分散"的融资渠道在危机时同步关闭）。ALM 权衡：负债久期短于资产 → 利率风险小但融资流动性风险大；流动性缓冲有成本。
- **模型风险通论（p139–140）**：模型风险来自用错模型、错误设定、数据不足/估计量错误；最常见也最危险的是**底层假设错误**（如假设平坦利率曲线而实际不稳定）。

### 对 A 股日线量化组合的落地提示
- 逐条映射成策略红线：① 任何"卖尾部"型收益结构（高胜率小赔率）必须用 ES/压力测试单独限额；② 杠杆上限按"最差路径"而非"终点方向"设定——A 股 T+1 + 跌停无法平仓，持仓路径上的流动性风险比美股更高；③ VaR horizon 应按 A 股极端情景下的实际可平仓天数设定（连续跌停品种可能 3–5 天无法退出），而非教科书 1 日/10 日；④ 组合"分散"假象检查：按行业/风格/流动性分组做相关性压力情景（相关性→1），而不是相信常态相关矩阵；⑤ 回测同时输出 P&L 曲线与资金占用/保证金路径，防止"经济对冲、现金流失血"。

---

## 附：读取情况说明
- 三本 PDF 文本层完整，全部指定页码范围（书4 p12–25/26–37/38–51/110–125；书2 p74–93/94–111/224–235/236–251；书1 p84–95/96–103/134–151）均成功抽取，无缺页。
- 书1 PDF 含"更多课程资料加微信"水印文字，已忽略。
- 公式均按教材上下文还原为标准记法；书4 Ch2 的正态 VaR/ES 与书4 Ch1 式 1.7 一致，书2 Ch6 的 VaR 回测未出现 Kupiec/Christoffersen 命名（只有 HIT/Bernoulli 框架与 LR 检验思路），Cornish-Fisher 调整在本批章节中未出现。


---

# 扩读部分：期权 / 债券 / 利率章节（第二批）

> 第二批章节：书3《Financial Markets and Products.pdf》Ch4/7/8/10/12/13/14/16/17/19/20；书4《Valuation and Risk Models.pdf》Ch9–16。格式同前。页码引用均为 PDF 页码（书3 TOC 页码与 PDF 页码一致，已用 Ch10 p136 抽查对齐；书3 TOC 中 Ch11 页码印刷有误，Ch10 实际结束于 p159）。「落地提示」兼顾股票日线量化与期权/债券/利率扩展。

---

## 书3 Ch4 Introduction to Derivatives（PDF p58–69）

### 核心概念
- 衍生品按 payoff 形态分线性（forward/futures，价值与标的价格线性相关）与非线性（option，权利非义务，payoff 非线性）两类。
- 三类交易者：hedger（有敞口、用衍生品降风险）、speculator（无敞口、衍生品=杠杆）、arbitrageur（利用定价不一致）。

### 公式
- 远期 payoff（每单位标的，K=交割价，S_T=到期标的价格）：多头 `S_T − K`；空头 `K − S_T`。
- 期权 payoff：long call `max(S_T−K, 0)`；short call `−max(S_T−K, 0)`；long put `max(K−S_T, 0)`；short put `−max(K−S_T, 0)`。
- 组合恒等式（K=远期价）：short forward + long call = long put；short forward + short put = short call（put-call parity 的雏形）。

### 方法要点
- Exchange-traded（标准化合约、CCP 清算、几乎无信用风险）vs OTC（可定制、有对手方风险；危机后监管：SEF 平台交易、CCP 集中清算、集中报告）。
- 期权与远期的对冲差异：远期零成本锁定价格；期权付 premium 买保护、保留上行。
- 衍生品风险案例：交易员从 hedge/arbitrage 滑向投机（Rusnak/Leeson/Kerviel/Adoboli），教训是管控与授权。

### 落地提示
- A 股日线组合可用的衍生品工具箱：股指期货（IF/IC/IM，线性）、ETF 期权（50ETF/300ETF 期权，非线性）。线性工具做 β 对冲，期权做尾部保险，二者成本结构完全不同（期货只付基差，期权付 premium）。
- 期权买方最大亏损=premium 的结构适合给组合买"跌停无法卖出"情形的尾部保护。

---

## 书3 Ch7 Futures Markets（PDF p96–107）

### 核心概念
- 期货=交易所标准化的远期：CCP 做市、每日结算（variation margin）、初始保证金 + default fund、可反向平仓，交割极少发生。
- 期货价格随交割期临近收敛于现货价（convergence，由交割套利保证）。

### 公式/规则
- 无独立定价公式（定价见书3 Ch10）。关键度量：open interest（未平仓净合约数，long=short 恒等）、trading volume。
- Normal market：期货价随期限上升（如黄金）；inverted market：随期限下降（如原油）。

### 方法要点
- 合约规格要点：标的等级/合约规模/交割地点/交割月，交割选择权几乎总在空头方（short position 选择交割什么、何时交割）。
- 价格限制（limit up/down 触发当日停板）与持仓限额；settlement price 用于每日结算。
- 现金交割（如 S&P 500 期货以交割月第三个周五开盘价结算）vs 实物交割。
- Hedge accounting（FAS 133/ASC 815、IFRS 9）：满足有效性可将对冲损益与被对冲项目同期确认，降低报表波动。
- Forward vs futures 对照：OTC vs 交易所、到期一次结算 vs 每日结算、通常交割 vs 通常平仓、有信用风险 vs 几乎无。

### 落地提示
- A 股股指期货（CFFEX）现金交割、每日无负债结算，机制与本章一致；backtest 股指期货对冲时用 settlement price 序列，注意交割日 rolling 规则。
- 期货收敛性意味着：用近月合约对冲时基差（spot−futures）随到期日收敛到 0，移仓需在对冲到期前完成（衔接 Ch8 的"选对冲月后第一个到期月"规则）。
- 中国期货同样有涨跌停板与持仓限额，极端行情下对冲侧也可能被封板——回测要给对冲腿也加成交约束。

---

## 书3 Ch8 Using Futures for Hedging（PDF p108–121）

### 核心概念
- Short hedge（未来将卖出资产→做空期货）锁定卖出价；long hedge（未来将买入→做多）锁定买入价。对冲的目的是降低结果的不确定性，不是提高利润。
- Basis risk：对冲平仓时 基差 = 现货价 − 期货价 的不确定性；交叉对冲（cross hedging）时用最小方差对冲比。

### 公式
- 基差定义：`Basis = S_t − F_t`（被对冲资产现货 − 期货）。空头/多头对冲的净价格均为 `F_0 + b_t`（b_t=平仓时基差）；对冲效果的不确定性全部来自 b_t。
- 最小方差对冲比：由 ΔS = a + b·ΔF + ε 回归，`h* = ρ·(σS/σF)`（式 8.1）；hedge effectiveness = 回归 R² = ρ²。
- 最优合约数：`N* = h*·Q_A/Q_F`（式 8.2，Q_A=被对冲数量，Q_F=一张期货的标的数量）。
- Tailing the hedge（每日结算下的日频版）：`h = ρ·(σ̂S/σ̂F)`（日收益率的 std 与相关），`N* = h·V_A/V_F`（式 8.3–8.4，V_A=S·Q_A，V_F=F·Q_F）。
- 股指对冲：`N* = β·V_A/V_F`（完全对冲）；调整 β：β>β* 时做空 `(β−β*)·V_A/V_F` 张，反之做多 `(β*−β)·V_A/V_F` 张。

### 方法要点
- 选合约规则：对冲到期之后第一个交割月的合约（避免交割月流动性/基差异常）。
- Stack and roll：缺乏长期限流动合约时，滚动使用短期合约拼出长期对冲；风险在每次移仓的新旧价差不确定 + 现金流错配（Metallgesellschaft 案例：期货每日亏损要现金，被对冲敞口收益在未来）。
- 期货对冲锁定的是 F_0 而非当前现货价 S_0。

### 落地提示
- 股指期货对冲 A 股组合的核心公式就是 `N* = β·V_A/V_F`：IF（沪深300）对冲大盘组合、IC（中证500）/IM（中证1000）对冲中小盘组合；V_F = 指数点位 × 合约乘数。
- β 不稳定（A 股组合相对指数的 β 随风格漂移），用滚动窗口或 EWMA 日频更新 β 并定期再平衡对冲腿；tailing 视角下日频 β 估计即可。
- 基差风险在 A 股显著（股指期货长期贴水/升水切换）：对冲成本 = 基差收敛路径，回测必须用真实期货连续合约序列而非指数点位近似。
- 长期对冲靠移仓（季度月合约滚动），需在回测中显式建模移仓日价差损益。

---

## 书3 Ch10 Pricing Financial Forwards and Futures（PDF p136–159）

### 核心概念
- 投资性资产的远期/期货价格由无套利（持有成本）决定；期货价 ≈ 远期价（利率恒定或可预测时严格相等；正相关于利率时期货价略高）。
- 远期价格 ≠ 远期合约价值：签约时合约价值为零，之后随标的价格漂移。

### 公式（R=年化无风险利率，年度复利记法；连续复利替换见下注）
- 无收益资产：`F = S(1+R)^T`（式 10.1；连续复利 `F = S·e^{RT}`）。
- 已知现金收益（现值 I）：`F = (S−I)(1+R)^T`（式 10.2）。
- 已知收益率 Q：`F = S·((1+R)/(1+Q))^T`（式 10.3；连续复利 `F = S·e^{(R−Q)T}`）。
- 远期合约价值（签约价 K、当前远期价 F、剩余期限 T）：多头 `V = (F−K)/(1+R)^T`（式 10.4），空头 `V = (K−F)/(1+R)^T`；展开形式：无收益 `V = S − K(1+R)^{−T}`（式 10.6）；已知收益 `V = S − I − K(1+R)^{−T}`（式 10.7）；收益率 `V = S(1+Q)^{−T} − K(1+R)^{−T}`（式 10.8）。
- 抛补利率平价：`F = S·(1+R_USD)^T/(1+R_GBP)^T`（式 10.9，外币利率=Q 的特例）。
- 股指期货：`F = S·((1+R)/(1+Q))^T`，Q=指数股息率。

### 方法要点
- 套利论证双向：F 过高→买现货+空远期；F 过低→卖空现货+多远期。借贷利率差（如 5.1%/5.0%）使无套利区间有厚度。
- 期货 vs 远期价格差异源于标的收益与利率的相关性（正相关→期货略优、价格略高）；Eurodollar 期货例外需 convexity adjustment（见 Ch19）。
- 指数套利（index arbitrage / program trading）：期货价偏离理论值时买/卖一篮子股票 + 反向期货；1987 黑色星期一因交易拥堵失效。
- 做空机制：借券卖出、期间股息由空方支付、借券费通常 <50bp/年。

### 落地提示
- 股指期货理论基差 = S·((1+R)/(1+Q))^T − S ≈ S·(R−Q)·T：A 股股息率低（~2%）、R 用 Shibor/逆回购利率；实际贴水常大于理论值（对冲需求不平衡），不能机械用公式值当"公允基差"。
- 可转债场景：正股远期定价用式 10.2（已知分红）。
- 实现要点：T 用实际天数/365（或 252 交易日口径需与波动率口径一致）；连续复利版公式在代码里更简洁（`F = S*exp((R−Q)*T)`）。

---

## 书3 Ch12 Options Markets（PDF p160–171）

### 核心概念
- 期权市场微观结构：CBOE 合约规格（1 张=100 股、到期月第三个周五、行权价间距规则）、moneyness（ITM/ATM/OTM）、intrinsic value。
- 与远期/期货的本质区别：买方付 premium 获得权利，卖方收 premium 承担义务并交保证金。

### 公式
- 四种头寸 payoff（S=到期价，K=行权价）：long call `max(S−K,0)`；short call `min(K−S,0)`；long put `max(K−S,0)`；short put `min(S−K,0)`。
- Intrinsic value：call `max(S_0−K,0)`；put `max(K−S_0,0)`。
- CBOE 卖方保证金：short call = 100% 权利金 + max(20%×股价 − OTM 额, 10%×股价)；short put 把 10%×股价换成 10%×行权价；指数期权把 20% 降为 15%。

### 方法要点
- 现金分红不调整期权条款（>10% 特大分红例外）；股票拆分/股票股息调整行权价与合约数保持双方头寸等价。
- 欧式 vs 美式：个股期权美式（OCC 随机指派行权），指数期权多为欧式现金结算；美式需二叉树等数值法定价。
- Warrants/可转债/员工期权：行权时公司增发新股（稀释），与交易所期权不同。
- Covered call 免保证金（有现货履约保障）。

### 落地提示
- 中国 ETF 期权（50ETF/300ETF/500ETF/创业板等）为欧式、实物交割、合约单位 10000 份，规则与 CBOE 类似；做组合保险时按名义本金/合约单位换算张数。
- 卖方保证金思路可直接用于评估组合卖期权策略的资金占用；A 股期权卖方保证金公式逻辑相同（权利金 + max 条款）。
- 分红对期权价格的影响（除息日股价下调）在 A 股 300ETF 分红季必须处理。

---

## 书3 Ch13 Properties of Options（PDF p172–183）

### 核心概念
- 不依赖定价模型的期权价格上下界与 put-call parity；美式 call（无股息）不应提前行权，美式 put 可能应提前行权。
- 影响期权价格六因素：标的价格、行权价、无风险利率、波动率、期限、股息。

### 公式（PV 为按无风险利率折现）
- Call 下界：无股息 `c ≥ max(S − PV(K), 0)`（式 13.1，欧美式同）；有股息（欧式）`c ≥ max(S − PV(K) − PV(Divs), 0)`（式 13.2）。上界：S。
- Put 下界：欧式 `p ≥ max(PV(K) − S, 0)`（式 13.3）；美式 `P ≥ max(K − S, 0)`。上界：欧式 PV(K)，美式 K。
- **Put-call parity**（欧式、同 K 同 T）：`c + PV(K) + PV(Divs) = p + S`（式 13.4）；无股息简化为 `c + PV(K) = p + S`。
- 远期价格形式：`c + PV(K) = p + PV(F)`（式 13.5），即 `c − p = PV(F − K)`；由此 `c ≥ PV(F) − PV(K)`、`p ≥ PV(K) − PV(F)`。
- 美式 call 提前行权判定：股息 < `K − K*`（K*=K 折现到下一除息日的现值）时在除息日行权必不最优；反之深 ITM 时在除息日前行权可能最优。

### 方法要点
- 无股息美式 call 不提前行权的两个理由：延迟支付行权价赚利息 + 保留"股价跌破 K 不行权"的保险（时间价值）；想变现应卖出期权而非行权。
- 美式 put 提前行权权衡：早收行权价赚利息 vs 放弃股价回升的 optionality；股价极低时倾向于立即行权。
- Parity 只严格适用于欧式；美式只有不等式关系。
- 用远期价格表达可推广到任何标的（避免估计股息/收益），实务上用市场远期价插值。

### 落地提示
- Put-call parity 是期权数据清洗/套利监控的第一工具：A 股 ETF 期权可用 `c − p = S·e^{−qT} − K·e^{−rT}`（连续股息版）检查合成期货与 50ETF/300ETF 的偏离。
- 可转债估值中的期权腿边界条件同理；A 股可转债兼具美式转股 + 赎回/回售条款，超出本章解析范围，需树/网格法。
- 美式 put 类权利（如可转债回售条款）必须用数值法，不能套欧式公式。

---

## 书3 Ch14 Trading Strategies（PDF p184–195）

### 核心概念
- 单期权+标的（protective put、covered call、PPN）、spreads（同类型期权）、combinations（call+put）三大类期权组合；理论上足够密的一组行权价可合成任意连续 payoff。

### 公式（put-call parity `p + S = c + PV(K)` 式 14.1 的四种变形对应四种合成）
- Protective put = long put + long 资产 ≡ long call + PV(K)。
- Covered call = long 资产 + short call ≡ short put + PV(K)。
- Bull spread（买 K1 call、卖 K2 call，K1<K2）：payoff 区间 `0 / S_T−K1 / K2−K1`；成本 c1−c2。用 put 实现时 cost 关系：`c1−c2 = p1−p2 + PV(K2)−PV(K1)`（式 14.5）。
- Bear spread（买 K2 put、卖 K1 put）：payoff `K2−K1 / K2−S_T / 0`。
- Box spread = bull spread(calls) + bear spread(puts)，payoff 恒为 `K2−K1`，成本应 = `PV(K2−K1)`（偏离即无风险借贷套利；必须用欧式期权）。
- Butterfly spread（买 K1、K3 call 各 1，卖 2 个 K2=(K1+K3)/2 call）：payoff 尖峰（K2 处最大 K2−K1）；成本为正 → `c1 + c3 > 2c2`（call 价格对行权价凸）。Put 与 call 实现成本相同：`c1+c3−2c2 = p1+p3−2p2`。
- Calendar spread：卖短期限 call + 买长期限 call（同 K）；在短期限到期日的 payoff 形似 butterfly，价格接近 K 时小赚。
- Straddle = 同 K 同 T 的 long call + long put，V 形 payoff；需价格移动超过 c+p 才盈利。Strangle = 虚值 put(K1) + 虚值 call(K2)，成本更低但需更大波动。

### 方法要点
- PPN（principal protected note）= 零息债 + 看涨期权；可行条件：期权成本 ≤ 本金 − 零息债现价，标的有收益时才可能 full participation。
- 蝶式的"尖峰"思想：任意连续 payoff 可用密集 butterfly 组合逼近（payoff 工程）。
- 其他变体：diagonal spread（不同 K 不同 T）、strip（2 put+1 call，看跌倾向）、strap（2 call+1 put）。

### 落地提示
- A 股 ETF 期权可直接落地：covered call 增强（持有 ETF + 卖虚值 call，牺牲涨跌停以上尾部换权利金，适合低波动环境）、protective put（对组合跌停风险买保险）、bull spread 降低方向性做多成本。
- Box spread 套利监控可反推市场隐含无风险利率。
- 注意组合策略的保证金占用与双边流动性（部分虚值合约挂单稀疏），回测按各腿实际盘口而非理论价。

---

## 书3 Ch16 Properties of Interest Rates（PDF p208–225）

### 核心概念
- 利率族谱：Treasury rate（政府债）、Libor（估计制、已被淘汰）、SOFR/SONIA（隔夜交易制替代）、repo rate（抵押隔夜）、联邦基金利率（无抵押隔夜）。衍生品定价的"无风险利率"用 OIS 曲线，不用国债（免税+免资本占用致其人为偏低）。
- 期限结构理论：expectations theory（远期=预期未来即期）、liquidity preference theory（远期系统性高于预期即期，解释曲线常态向上）。

### 公式
- 复利频率 m 的终值：`FV = A(1+R/m)^{mT}`（式 16.1）；频率换算 `R2 = m2·[(1+R1/m1)^{m1/m2} − 1]`（式 16.2）。
- 连续复利：`FV = A·e^{RT}`（式 16.3）；换算 `Rc = m·ln(1+Rm/m)`、`Rm = m·(e^{Rc/m} − 1)`（式 16.4/16.5）。
- 现值：`PV = A(1+R/m)^{−mT}`；连续 `PV = A·e^{−RT}`。
- Bond yield y：使 Σ 现金流 PV = 市场价的单一折现率（迭代求解）；par yield c：使价格=面值的票息，`c = (100 − 100·d)·m/A`（式 16.7，A=年金因子，d=到期折现因子）。
- 远期利率（T1→T2，连续复利）：`F = (R2·T2 − R1·T1)/(T2 − T1)`；半年复利先求增长因子比 V2/V1 再解 `(1+F/2)^{2(T2−T1)} = V2/V1`。
- **FRA 结算额**（期初结算，折现用实现浮动利率 R）：收浮动付固定方 `= (R − R_K)·τ·L/(1 + R·τ)`（式 16.10）。FRA 估值（假设远期实现）：`V = PV[(R_F − R_K)·τ·L/(1 + R_F·τ)]`。
- Bootstrap：由短到长递推零息利率（债券价格方程解出下一个零息点）。
- Duration（yield-based）：`ΔB = −D·B·Δy`（式 16.8）；Macaulay duration = 现金流时间的 PV 加权平均（连续复利 y 下）；`Modified D = Macaulay D/(1+y/m)`；`Dollar duration D$ = Modified D × B`，`ΔB = −D$·Δy`。
- Convexity：权重 × t² 之和；`ΔB = −D·B·Δy + ½·C·B·(Δy)²`（式 16.9）；`Modified C = C/(1+y/m)²`。

### 方法要点
- 惯例：利率报价的复利频率通常跟随支付频率；美债 actual/actual、美国公司债 30/360、货币市场 actual/360。
- Duration 只适用于收益率曲线小幅平移；大移动或非平移需 convexity 修正/另寻方法。
- 远期利率可由"借短投长"锁定（金融机构按即期利率借贷时）。

### 落地提示
- 利率债/固收扩展的地基：零息曲线 bootstrap、久期/凸性计算可直接用于国债/政金债组合的利率风险监控；中国债券惯例 actual/actual，代码里 day count 必须参数化。
- 可转债 = 信用债 + 期权，纯债价值部分用本章贴现框架（折现率=同评级信用债收益率），期权部分用书4 Ch14/15。
- 利率类因子的数据准备：中债收益率曲线 → 零息/远期曲线 → carry & roll-down 类因子（衔接书4 Ch11）。

---

## 书3 Ch17 Corporate Bonds（PDF p226–237）

### 核心概念
- 公司债价格 = 无风险基准 + credit spread；yield 升→价格跌。信用风险两分：default risk（评级衡量）与 credit spread risk（市场对信用定价的变化，压力期 flight to quality 利差飙升）。
- 债的分类：发行人/期限/利率结构（fixed/floating/zero）/抵押（mortgage bond、collateral trust、ETC、debenture、subordinated）。

### 公式
- Accrued interest（30/360 公司债惯例）：`AI = coupon × days/360`；`Dirty = Clean + AI`。
- Issuer default rate = 违约发行人数/发行人数；dollar default rate = 违约面值/总面值。
- Recovery rate = 违约后数日债券价格/面值；`LGD = 1 − Recovery`。
- **Expected loss rate = PD × (1 − Recovery)**；`Expected return = Risk-free + Credit spread − Expected loss rate`。实证（Hull 2018，约 7 年期）：Aaa 利差 0.78%/损失率 0.02%；Baa 1.69%/0.25%；B 5.23%/3.40%；Caa 11.46%/7.50%——利差 > 期望损失，差额随评级下降而扩大（系统性风险补偿，非流动性补偿可解释）。
- Spread duration ≈ 利差 +100bp 时价格的百分比跌幅。

### 方法要点
- Indenture 与 covenants（negative/positive/financial）、trustee 制度；提前偿还机制：call provision、make-whole call（PV 按国债+spread 折现）、sinking fund、tender offer。
- 回收率特征：均值 ~38%、双峰分布（由偿付顺序造成）、与违约率负相关、衰退期更低、重资产行业更高。
- 债券非系统性风险难分散：股票 30 只够，债券需数千只（违约是小概率大损失）。

### 落地提示
- 信用债/可转债组合的信用风险入门框架：`预期损失 = PD×LGD`、利差既补偿违约也补偿系统性风险——回测信用下沉策略时不能用"利差−历史违约损失"直接当 alpha。
- 可转债债底估值需信用利差数据；A 股可转债发行人多为中小盘、隐含评级不高，spread duration 思路可用于衡量转债债底对信用利差的敏感度。
- 事件风险（杠杆激增损害债权人）在 A 股对应：大股东质押、定增摊薄等事件对转债/信用债的冲击。

---

## 书3 Ch19 Interest Rate Futures（PDF p254–269）

### 核心概念
- 短期利率期货（Eurodollar/SOFR，100−R 报价）与长期国债期货（conversion factor + cheapest-to-deliver）两大体系；由期货利率推远期利率必须做 convexity adjustment。
- Duration-based hedging 用期货对冲利率敞口。

### 公式
- Day count：美债 actual/actual、公司债 30/360、货币市场（T-bill/Libor）actual/360。
- T-bill 报价换算：`Q = (360/n)(100 − C)` ⟺ `C = 100 − (n/360)·Q`（Q 为贴现率报价，bid quote 高于 ask quote 因它是利率）。
- 国债期货空方交割收入 `= S·f + A`（S=期货结算价，f=conversion factor，A=应计利息）；conversion factor ≈ 面值 1 美元债券在收益率 6%（半年复利）下的 hypothetical clean price（期限从交割月首日起算、向下取整到 3 个月/1 个月）。
- Cheapest-to-deliver：使 `Q − S·f` 最小的可交割债；收益率 >6% 时低票息长久期债偏 CTD，<6% 时高票息短久期偏 CTD；向上曲线利于长久期 CTD。
- 国债期货理论价（CTD 已知）：`F = (S − I)·e^{RT}`（式 19.1，S=CTD dirty price，I=期内票息 PV）；quoted futures price = clean futures price / f。
- Eurodollar：结算价 = `100 − R`（R=90 天 Libor，actual/360）；1bp = USD 25/张（≈100 万美元 3 个月利息的 1bp）；SOFR 三月合约 R = `Π(1+d_i·r_i) − 1`（隔夜利率逐日复利）。
- **Convexity adjustment**（Ho-Lee）：`Forward rate = Futures rate − 0.5·σ²·T·(T+0.25)`（式 19.2，σ=短期利率一年变动 std，T=期货到期年数；两利率都需转成 actual/actual 连续复利）。由即期+远期推新即期：`R2 = [F·(T2−T1) + R1·T1]/T2`（式 19.3），用于 Eurodollar 拼接延长 Libor 零息曲线。
- **Duration-based hedge**：合约数 `N* = E_V/E_F`（E_V=敞口每 bp 价值变动 = B·D·0.0001，E_F=一张期货每 bp 价值变动，债券期货 `E_F ≈ 期货价 × CTD久期 × 0.0001`）；负值=做空。例：500 万、久期 12 的债券组合，E_V=6000，E_F=165.2 → 空 36 张。

### 方法要点
- Eurodollar vs FRA 两差异：每日结算 vs 到期一次结算；期初结算 vs 期末付息——这正是 convexity adjustment 的来源，长到期（>2 年）不可忽略。
- Duration 对冲仅防小幅平移，且假设敞口利率与期货标的利率完全相关、CTD 已知。
- Wild card play 等交割期权使期货价格略低于理论值（对空方有利的选择权）。

### 落地提示
- 中国对应物：国债期货（TF/T/TS，中金所）同样有 conversion factor 与 CTD 机制——利率债组合对冲、基差交易可直接套用本章框架（注意中国转换因子按 3% 名义票息而非 6%）。
- 国债期货久期对冲公式 `N* = (B·D_B)/(F·D_F)` 可直接实现；滚动数据需处理 CTD 切换。
- 利率曲线构建：货币市场利率 + 利率互换/Eurodollar 式期货拼曲线的 bootstrap 思路，可用于构建人民币 FR007 互换曲线。

---

## 书3 Ch20 Swaps（PDF p270–285）

### 核心概念
- 利率互换：固定 vs 浮动（名义本金不交换）；货币互换：两币种利息+期初期末本金交换。互换把资产/负债在固定↔浮动、币种间转换。
- 估值三视角：债券组合差、FRA/远期组合、与"当前平价互换"比较。

### 公式
- OIS 浮动端每期利率：`R = Π(1 + d_i·r_i) − 1`（r_i=第 i 营业日隔夜利率，d_i=适用天数）。
- 互换利率 = bid/ask 均值；互换估值（收固定 X%、当前同期限平价利率 Y%）：**V = 剩余期限 (X−Y)% 名义本金的年金现值**（付固定则为 (Y−X)% 年金）。
- 由互换报价反推 Libor 远期：令第 k 期交换的现值（按无风险利率折现、(R_swap − F_k) 差额）累加=0 解出 F_k。
- 即期由远期复合：`1 + R = Π(1 + F_k/2)`（半年复利例）。
- 货币互换估值（债券法）：`V = B_X − S_0·B_Y`（B_X/B_Y 为两腿各自币种债券价值，S_0 为即期汇率）；远期法：每次交换净额按利率平价远期汇率折算本币再折现，两法结果一致。
- 利率平价远期汇率：`F_t = S_0·(1+R_X)^t/(1+R_Y)^t`。

### 方法要点
- Comparative advantage 论证（固浮两市场利差差 0.6% 可三方分润）及其批评：浮动端 spread 随信用变化，"锁定固定利率"是幻觉。
- 危机后：折现用 OIS 曲线；Libor 多曲线体系（1m/3m/6m/12m 各一条零息曲线，短期限曲线更低）。
- 信用风险：金融机构间标准化互换 CCP 清算；双边清算需 initial+variation margin；对非金融企业无抵押敞口需计入 CVA/DVA。
- 其他互换：equity swap（总回报换固定/浮动）、commodity swap、volatility swap（实现波动 vs 固定波动×名义本金）、CDS。

### 落地提示
- 人民币利率互换（FR007/Shibor3M）估值可直接用"年金差"法；曲线构建用 OIS 思路（FR007 互换）做无风险折现。
- 量化组合的类互换工具：股指期货多空组合≈equity swap（指数收益 vs 资金成本）；收益互换（券商 PB 业务）正是 A 股场外 equity swap。
- Volatility swap 的概念可用于评估"卖波动率"策略（期权组合）的公允定价锚：实现波动 vs 隐含波动。

---

## 书4 Ch9 Pricing Conventions, Discounting, and Arbitrage（PDF p126–137）

### 核心概念
- Discount factor 是固定收益的统一语言；law of one price：相同现金流必须同价，否则存在套利；STRIPS 把附息国债拆成零息证券（C-STRIPS 票息 / P-STRIPS 本金）。

### 公式
- T-bill 报价：`Q = (360/n)(100 − C)` ⟺ `C = 100 − Q·n/360`（式 9.1；n=到期日历天数）。
- 国债应计利息（actual/actual）：`AI = c·(t/T)`（式 9.2，c=半年票息，t=上个付息日至结算日天数，T=付息区间天数）；`Dirty = Clean + AI`，T+1 结算。
- 附息债 bootstrap 折现因子：由最短债 d(1)=价格/到期现金流起，逐个解 `Σ 已Coupon×d(已知) + 到期现金流×d(k) =  dirty price`（示例 d = 0.991909/0.980944/0.969406/0.956909）。
- 复制组合定价：从最长现金流往回倒推各债券持仓（与 bootstrap 顺序相反），复制成本 vs 市价差即潜在套利（LTCM 的 convergence arbitrage 即此思路）。

### 方法要点
- Law of one price 的例外来自流动性/税收等非现金流因素：流动性差的债券价格更低——convergence trade 买低流动性卖高流动性，正常期收敛获利，危机期（flight to quality）价差发散+杠杆=灭顶（LTCM）。
- Clean price 只反映利率变动，dirty price 锯齿上行后付息日回落（图 9.1）。

### 落地提示
- 中国国债/政金债数据多为 clean price 报价，估值引擎必须先转 dirty price（actual/actual）再折现；这是固收模块第一个易错点。
- 折现因子 bootstrap 代码 = 后续一切债券/互换/转债债底定价的基础设施，建议直接实现为 d(t) 查表+插值函数。
- "复制组合价差"思路可用于转债债底 vs 同期限信用债的相对价值监控；LTCM 教训落地：相对价值信号必须配杠杆与保证金路径约束（见书1 Ch9）。

---

## 书4 Ch10 Interest Rates（PDF p138–149）

### 核心概念
- Spot/zero rate、forward rate、par rate 三位一体；互换市场天然定义 par rate（swap rate = 平价债券票息）。
- 期限结构向上时：par < spot < forward；向下时反之。

### 公式
- 复利换算：`R2 = m2·[(1+R1/m1)^{m1/m2} − 1]`；连续复利 `A·e^{RT}` / `A·e^{−RT}`；`Rc = m·ln(1+Rm/m)`、`Rm = m(e^{Rc/m}−1)`。
- Spot↔折现因子：半年复利 `d(t) = (1+r(t)/2)^{−2t}`；连续 `d(t) = e^{−r(t)t}`。
- Par rate：`p = 200·(1 − d(T))/A(T)`（式 10.4，A(T)=Σd(t_i) 年金因子，半年付息、面值 100）；附息债价值 `V = 100 + (c − p)/2·A(T)`。
- 远期利率：半年复利 `f = [(1+R2/2)^{2(T+0.5)}/(1+R1/2)^{2T}] − 1`（半年期利率，年化×2，式 10.5）；连续复利精确 `F = (R2T2 − R1T1)/(T2 − T1)`；即期由远期复合 `(1+R/2)^{2N} = Π(1+f_i/2)`（式 10.6）。
- FRA 价值 = PV[(R − F)·本金]：R>F 为正。

### 方法要点
- 利率期限结构不变时债券价格随时间漂移方向：coupon > 末期远期利率则价格跌（债券"变老"损失高票息）。
- 交易策略：预期实现利率 < 远期 → 借短投长（买长债）；反之买短债。
- Flattening/steepening 定义（bull/bear flattener 等）与对应交易（陡化：空长债+多短债）。
- OIS：几何平均隔夜利率换固定；OIS 利率 < 互换利率，作无风险折现曲线。

### 落地提示
- Spot/forward/par 关系是债券因子（carry、roll-down）计算的基础；A 股量化扩展到利率债时，中债即期曲线→远期曲线→carry 因子是标准流水线。
- 曲线形态交易（陡峭/平坦化）在国债期货上可落地：多 TF 空 T 或反之，按 DV01 配比。

---

## 书4 Ch11 Bond Yields and Return Calculations（PDF p150–161）

### 核心概念
- 实现收益（含票息再投资）的 gross/net（扣融资成本）口径；spread = 加到所有远期利率上使理论价=买价的常数；YTM 是单一折现率；coupon effect 使 YTM 不是可靠的相对价值指标；P&L 可分解为 carry roll-down + rate change + spread change。

### 公式
- Gross realized return：`R = (V_end − V_0 + 票息含再投资)/V_0`；net 版分子再减融资成本。
- Spread s：解 `Σ CF_i/Π_j(1 + (f_j + s)/2) = P_market`（迭代）。
- YTM（刚付息后）：`P = Σ_{i=1}^{2T} (c/2)/(1+y/2)^i + 100/(1+y/2)^{2T}`（式 11.1）；非付息日用 dirty price、幂次为 2t_i（式 11.2）。
- 年金：`V = (c/y)·[1 − (1+y/2)^{−2T}]`（式 11.3）；perpetuity `V = c/y`。
- Carry roll-down（远期实现假设）：任意债券下期总回报 = 当期短期利率，故 `CRD = 短期利率 × V_0`；分解为 cash-carry（票息）+ price-change（ rolldown 价差）。备选假设：期限结构不变 / yield 不变 / 自定义预期。
- P&L 分解：终值+票息−初值 = carry roll-down + rate changes（实现曲线 vs 假设曲线）+ spread changes。

### 方法要点
- YTM 性质：y=coupon 时平价；y<coupon 溢价且随时间回落；y>coupon 折价回升；平坦曲线下 y=该水平对所有期限。
- Coupon effect：同期限不同票息的正确定价债券 YTM 不同（向上曲线：票息越高 YTM 越低）——比较债券贵贱应用 spread 而非 YTM。
- 日本惯例 simple yield：`y = c/p + (100−p)/(p·T)`。

### 落地提示
- Carry roll-down 是固收类策略的核心收益预测：国债期货/现券多头的"持有收益"分解为票息 + 骑乘（roll-down 沿曲线下滑获益），A 股量化若加利率债/转债资产，这是首选因子族。
- "远期实现 ⇒ 所有债券回报相同"意味着：做债券相对价值本质是押注"实现利率 ≠ 远期"或 spread 收敛。
- 实现净收益口径（含融资成本）对应 A 股两融/期货杠杆策略的收益计算。

---

## 书4 Ch12 Applying Duration, Convexity and DV01（PDF p162–175）

### 核心概念
- 单因子（平行移动）风险度量三件套：DV01（绝对额）、effective duration（百分比）、effective convexity（duration 的变化率）；组合层面 DV01 可加、duration/convexity 按市值加权平均。
- Barbell vs bullet：同 duration 下 barbell convexity 更高（平移时占优），但非平移或正常向上凸形曲线下 bullet 收益更高——不存在免费午餐。

### 公式
- `DV01 = −ΔP/Δr`（Δr 以 bp 计，平行移动；收益率版/即期版/远期版定义分别记 yield-based DV01、DVDZ、DVDF，数值差别很小）；精确式 `DV01 = −dP/dr`。
- 对冲：使对冲工具 DV01 = −组合 DV01；所需头寸面值 = 组合 DV01/工具每面值 DV01。
- Effective duration：`D = −(ΔP/P)/Δr`（式 12.1，即 `ΔP = −D·P·Δr` 式 12.2；利率用小数时例值 2.56）。DV01 对冲换算：债券头寸 `P = −V·D_V/D_P`。
- Effective convexity：`C = (P+ + P− − 2P)/(P·(Δr)²)`（式 12.3；P± 为曲线 ±Δr 平移后的价格）。
- 价格变动估计：`ΔP = −D·P·Δr + ½·C·P·(Δr)²`（式 12.4，Taylor 二阶）。
- Duration+convexity 联合对冲：解 `V·D_V + P1·D1 + P2·D2 = 0`、`V·C_V + P1·C1 + P2·C2 = 0`（式 12.5）。
- Yield-based：`Macaulay D = (1/P)·Σ t_i·c_i·e^{−y·t_i}`（式 12.6，连续复利 y）；`Modified D = Macaulay D/(1+y/m)`；`Yield convexity C = (1/P)·Σ t_i²·c_i·e^{−y·t_i}`；`Modified C = C/(1+y/m)²`。
- 组合：`DV01_P = Σ DV01_i`；`D_P = Σ (V_i/V)·D_i`；`C_P = Σ (V_i/V)·C_i`。
- Duration↔DV01 换算：`D = 10,000 × DV01/Value`（利率小数口径）。

### 方法要点
- Callable/puttable 债不能忽略期权特征算 duration：正确做法是利率 ±1bp 重定价（含行权概率变化）再算有效久期。
- 久期对冲只对小幅平移有效；duration+convexity 可覆盖较大平移，但对非平移（见 Ch13）仍暴露。
- 凸性为正时实际价格变动总优于 duration 预测（duration 高估跌幅、低估涨幅）。

### 落地提示
- 这是固收组合风控的核心实现公式集：可转债/利率债仓位的利率风险监控直接按 `ΔP ≈ −D·P·Δy + ½CP(Δy)²` 实现；组合层面市值加权。
- 转债含权（赎回/回售/下修）→ 用 effective duration（价格对利率 ±扰动重估）而非解析久期。
- A 股国债期货对冲利率债组合的配比公式即 Ch12 的 DV01 对冲（= 书3 Ch19 的 duration-based hedge）。

---

## 书4 Ch13 Modeling Non-Parallel Term Structure Shifts and Hedging（PDF p176–187）

### 核心概念
- 非平行移动的多因子风险框架：PCA（前 3 因子=水平/斜率/弓形，解释 85%/95%/97.6% 方差）、key rate（KR01）、bucket、forward-bucket '01——都是把 DV01 拆成可加的分量。
- 监管（FRTB/ISDA SIMM）要求银行计算 10 个关键利率（3m–30y）的 KR01 并结合波动率与相关性算 VaR/ES。

### 公式
- PCA 分解：利率日变动 `Δr_j = Σ_i a_i·f_{ij}`（f=因子载荷，a=因子得分；因子不相关；因子重要性=得分标准差）。
- KR01：单个关键利率的局部线性 shift（两端线性渐减到相邻关键利率）对组合价值的影响；`DV01 = Σ KR01_i`。
- 组合日波动（关键利率框架）：`σ_P² = Σ_i Σ_j ρ_{ij}·σ_i·σ_j·KR01_i·KR01_j`（式 13.2）；一般形式 exposures w_i：`σ_P² = Σ w_i²σ_i² + 2Σ_{i<j}ρ_{ij}σ_iσ_j w_i w_j`（式 13.3）。
- PCA 版（因子不相关）：`σ_P = √(Σ σ_i²·f_i²)`，f_i=组合对 1 单位因子 i 的价值变动；进而正态假设下 VaR/ES 直接可得（例：10 日 99% VaR = √10·N⁻¹(0.99)·σ_P）。
- 即期由半年远期复合：`(1+0.5R)^{2N} = Π(1+0.5f_t)`（式 13.4）。
- Duration 化：`Duration 度量 = 10,000 × ('01 度量)/组合价值`；forward bucket 01 总和=DV01。

### 方法要点
- 对冲：n 个风险源需 n 个工具解 n 元线性方程组（式 13.1 示例）；PCA 对冲（3 因子）比 3 个 key rate 覆盖更全。
- Par yield 版 key rate：shift 定义为 par yield 变动，可直接用平价债对冲；互换交易员等价地用 swap rate。
- Bucket 法（商业银行 ALM 常用）：每个 bucket 资产负债的 '01 大致相等即视为对冲良好；forward bucket 适合互换/swaption（远期组合）。
- 早期远期利率影响更多现金流 → 其 bucket 01 更大。

### 落地提示
- PCA 三因子（level/slope/bow）是利率风险归因与压力情景设计的标准工具：对中债收益率日变动跑 PCA，可得到 A 股债券组合的"利率 VaR"与因子暴露。
- 关键利率久期（KR01）是转债/债券组合报告的进阶指标，对冲用国债期货（TS/TF/T 对应短中长关键利率）解方程组。
- 该章把书4 Ch2 的 delta-normal VaR 落到利率组合：exposures×协方差矩阵 → 正态 VaR/ES，实现路径清晰。

---

## 书4 Ch14 Binomial Trees（PDF p188–199）

### 核心概念
- Cox-Ross-Rubinstein 二叉树：无套利复制 + 风险中性定价；步数增加时欧式期权价格收敛到 BSM；美式期权每节点比较行权/不行权。
- 风险中性定价原理：假设所有资产期望收益=无风险利率来算衍生品价格，结果在真实世界同样正确。

### 公式
- 单步：`f = e^{−rΔt}·[p·f_u + (1−p)·f_d]`（式 14.4），风险中性上行概率 `p = (e^{rΔt} − d)/(u − d)`（式 14.5）。
- CRR 参数：`u = e^{σ√Δt}`，`d = e^{−σ√Δt}`（式 14.6，匹配方差 σ²Δt）。
- Delta：`Δ = (f_u − f_d)/(S·u − S·d)`（式 14.1，复制组合中每股对冲股数）。
- 连续股息率 q：`p = (e^{(r−q)Δt} − d)/(u − d)`（式 14.7）；股指 q=股息率；外汇 q=rf（外币利率）`p = (e^{(r−rf)Δt} − d)/(u − d)`；期货 q=r（`p = (1 − d)/(u − d)`）。
- 美式：每节点取 `max(行权价值, 持有价值)` 回滚（backward induction）。
- 实务步数 ≥30–50；20/50/100/500 步示例值 3.082/3.067/3.059/3.055（收敛）。

### 方法要点
- Girsanov 定理：风险中性世界与真实世界波动率相同 → 可用历史数据估 σ 用于定价。
- 期权的真实世界期望收益可正可负（put 负系统性风险→期望收益<无风险），但定价与真实概率无关。
- 树同时给出 delta 等 Greeks（用前两层节点）。

### 落地提示
- 二叉树是 A 股可转债定价的落地首选框架（含赎回/回售/下修条款可在节点上加规则），也是美式 ETF 期权估值工具。
- 实现参数：Δt = 剩余交易日/252；σ 用 EWMA/GARCH（书4 Ch3）或隐含波动率（书4 Ch15）；r 用 FR007 互换曲线。
- 期货期权（股指期货期权）用 q=r 版公式即可。

---

## 书4 Ch15 The Black-Scholes-Merton Model（PDF p200–213）

### 核心概念
- 假设：短期收益正态（μ、σ 恒定）→ 股价对数正态；无摩擦、连续交易、恒定无风险利率、无股息、欧式。
- 期权价格 = 风险中性期望 payoff 按无风险利率折现；隐含波动率反解市场价格，volatility smile/skew/surface 证明市场并不严格满足 BSM 假设。

### 公式
- 对数正态性质：`E(S_T) = S_0·e^{μT}`（式 15.1）；`E[ln S_T] = ln S_0 + (μ − σ²/2)T`（式 15.2）；`SD[ln S_T] = σ√T`（式 15.3）；`E(ln S_T) ≠ ln E(S_T)`。连续复利实现收益 `R ~ N(μ − σ²/2, σ²/T)`（式 15.5）。
- **BSM（无股息）**：`c = S_0·N(d1) − K·e^{−rT}·N(d2)`（式 15.6）；`p = K·e^{−rT}·N(−d2) − S_0·N(−d1)`（式 15.7）；`d1 = [ln(S_0/K) + (r + σ²/2)T]/(σ√T)`；`d2 = d1 − σ√T`。数值例：S=56,K=60,r=5%,σ=30%,T=1.5 → d1=0.2001, d2=−0.1674, c=8.3069, p=7.9715（满足 parity）。
- 连续股息率 q：`c = S_0·e^{−qT}N(d1) − K·e^{−rT}N(d2)`，`d1 = [ln(S_0/K) + (r − q + σ²/2)T]/(σ√T)`（式 15.8/15.9）。外汇：q=rf（式 15.10/15.11）。**Black's model（期货期权）**：`c = e^{−rT}[F_0·N(d1) − K·N(d2)]`，`d1 = [ln(F_0/K) + σ²T/2]/(σ√T)`（式 15.12/15.13）。
- 离散股息：把 S_0 换成 `S_0 − D`（D=期内股息 PV）代入无股息公式。
- 美式 call 不提前行权条件（离散股息）：第 i 个除息日 `D_i < K[1 − e^{−r(t_{i+1}−t_i)}]`，最后除息日 `D_n < K[1 − e^{−r(T−t_n)}]`；满足则可按欧式估值。
- 波动率估计：u_i = ln(S_i/S_{i−1}) 的标准差 s，年化 `σ̂ = s/√τ`（τ=观测间隔年数）；标准误 ≈ σ̂/√(2n)。除息日价格变动应剔除样本。时间按交易日计（252 天/年）。
- 隐含波动率：无解析解，successive bisection 迭代（例：市价 7.00 → σ_implied=25.14%）。
- Warrants 稀释成本：每股成本 = `N/(N+M)` × 期权价格（N=现有股数，M=权证数）。

### 方法要点
- BSM 假设下任何对冲策略的期望对冲成本现值 = BSM 理论价；好对冲策略的标志是成本恒接近理论价。
- Vol smile：外汇双侧翘（对称微笑）、股票左高右低（skew）；交易员用波动率曲面插值报价，实质是用 BSM 当"换算器"而非真信其假设。
- 远期/期货价与欧式现货期权等价（同 K 同 T）：用 Black's model 可绕过股息估计。

### 落地提示
- 直接实现三件套：BSM（ETF 期权）、Black's model（股指期货期权）、离散股息修正（300ETF 分红）。希腊字母计算 σ 用隐含波动率（见书4 Ch16 惯例）。
- 隐含波动率反解是期权数据管线必备；A 股 50ETF 期权 skew 明显，定价/信号不能用单一 σ。
- 波动率估计的交易日口径（A 股 ~243 交易日/年）与年化系数必须全局统一。
- 转债的期权腿可用 BSM 近似快速估值（忽略条款），精确估值回到二叉树。

---

## 书4 Ch16 Option Sensitivity Measures: The "Greeks"（PDF p214–229）

### 核心概念
- Greeks 是衍生品组合的风险限额语言；delta 每日再平衡可行（标的市场交易便宜），gamma/vega 只能靠其他期权调整（成本高）。
- Stop-loss、裸卖、全对冲等朴素策略都不是好对冲：delta 对冲（"买高卖低"）的期望成本=BSM 理论价。

### 公式（无股息欧式；σ 取隐含波动率；N′(x)=e^{−x²/2}/√(2π)）
- Delta：`Δ(call) = N(d1)`（式 16.1）；`Δ(put) = N(d1) − 1`。
- Vega（call/put 同）：`vega = S_0·√T·N′(d1)`（σ 用小数；每 1% 波动率变动 ≈ vega×0.01）。
- Gamma（call/put 同）：`gamma = N′(d1)/(S_0·σ·√T)`；delta 中性组合 `ΔV ≈ ½·gamma·(ΔS)²`。
- Theta：`θ(call) = −S_0·N′(d1)·σ/(2√T) − r·K·e^{−rT}·N(d2)`；`θ(put) = −S_0·N′(d1)·σ/(2√T) + r·K·e^{−rT}·N(−d2)`。
- Rho：`ρ(call) = K·T·e^{−rT}·N(d2)`；`ρ(put) = −K·T·e^{−rT}·N(−d2)`。
- **BSM PDE 关系**：`θ + r·S·Δ + ½·σ²·S²·Γ = r·f`（式 16.2）——delta 中性时 θ 与 Γ 反号互含信息。
- 含股息率 q 的希腊字母表（Table 16.2）：`Δ_c = e^{−qT}N(d1)`、`Δ_p = e^{−qT}[N(d1)−1]`；`vega = S_0√T·N′(d1)e^{−qT}`；`gamma = N′(d1)e^{−qT}/(S_0σ√T)`；theta 加 ±qS·N(±d1)e^{−qT} 项；期货期权 rho = −f·T。
- 组合 Greeks = 各头寸加权和（数量×单值求和）。
- 美式期权 Greeks：由二叉树数值差分（delta 用第一层两节点；gamma 用第二层两个 delta 差；theta 用隔层中节点时间差；vega/rho 微扰重建树）。
- Portfolio insurance（合成 put）：按拟创建 put 的 delta 动态卖出一部分组合（例：δ=−0.236 → 卖 23.6% 组合）；1987 黑色星期一暴露其缺陷（卖出互相强化+成交拥堵）。

### 方法要点
- Vega/gamma 对近价期权最大；vega 随期限增加、gamma 随期限减小；对冲 gamma+vega 需两个期权解二元方程，再用标的补 delta。
- 限额示例口径：delta 限额以标的等值金额表示、vega 以每 1% 波动率的金额、gamma 以每 1 美元价格变动的 delta 数。
- 二阶 Greeks：vanna（∂Δ/∂σ）、charm（∂Δ/∂t）、vomma（∂vega/∂σ），本质是 Taylor 展开的交叉项。

### 落地提示
- 若未来做 ETF 期权卖方/套利策略， Greeks 限额体系（delta 日调、gamma/vega 限额+机会式对冲）可直接照搬；组合 Greeks 聚合代码简单（加权求和）。
- `θ+ rSΔ + ½σ²S²Γ = rf` 可用作期权定价/对冲代码的自检恒等式。
- Portfolio insurance 教训对 A 股格外现实：跌停+流动性枯竭时动态复制 put 会失效（卖不出），合成保护策略必须叠加流动性情景测试（呼应书4 Ch8 与书1 Ch9）。
- 股指期权的 delta 对冲腿可用股指期货（流动性好、成本低），注意期货基差变动引入的额外噪声。

---

## 附：第二批读取情况说明
- 书3、书4 文本层完整，本批全部指定页码范围均成功抽取，无缺页；页码抽查（书3 Ch10 p136 标题对齐）无偏移。
- 书3 TOC 中 Ch11 起始页印刷为 p24（显然错误），Ch10 实际范围为 p136–159（至 Ch12 p160 前），已按此抽取。
- 书3 含"持续更新通知微信"水印文字，已忽略。
- 公式均按教材上下文还原标准记法；书3 Ch19 的 duration-based hedge 公式编号在原文中引用为"式 19.3"处实际指合约数公式 N*=E_V/E_F（原文编号有串行），本摘要按含义记录。
