# Task Handoff

## Task ID

QRE-GUI-POOL-MOM-004 (「聚类动量」页 v3 历史回看：日期选择器 + 事后验证列 + 验证摘要条)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

overview 加 trade_date 参与 fwd 可选日期列表（下拉切换 point-in-time 榜单）；
纯函数 compute_post_returns（post_w = T 后 w 日 fwd_ret 复利，不足窗口→NULL
未满窗口）加「事后3/5/20日」三个可排序列；纯函数 accel_top_summary（加速度
Top10 post_5 均值/中位/胜率 vs 全体，按 pool_type 各一行）渲染摘要条；
detail 加 end_date、members 传选中日期。测试 +11（65 总），全量 1929
passed + 4 skipped。qre-gui 已重启 active；真库：2025-09-05 concept 加速度
Top10 post_5 +0.19% vs 全体 +0.88%（该日无超额，如实呈现）。未 git commit。

---

## Archive: QRE-GUI-POOL-MOM-003 (「聚类动量」页升级 M7 v2 前瞻口径：fwd_ret 主口径 + 事件池统计)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

M7 v2 新列（fwd_ret/fwd_ret_3/5/20/50/next_premium/survive_3/5/win_rate_1）
接入 8080 聚类动量页：速度/加速度/热力/共振全部切 fwd 口径
（compute_acceleration/compute_heat 加 metric 参、resonance 判 fwd），
回看 ret_w 降级对照列；overview 默认展示最近 fwd 已补齐日 + fwd_lag
红色提示（末日 NULL=正常 T+1 滞后）；state 分区 artifact 池加事件 4 列
（has_event 行级标记，对标同花顺涨停复盘）；详情主线 fwd、回看浅色辅线；
声明卡改写。测试 +9（54 总），全量 1918 passed + 4 skipped。qre-gui 已
重启 active；真库实测榜单日 2026-08-31，concept fwd_ret_3 榜首
「昨日打二板以上表现」+15.38%。未 git commit，等用户审批。

---

## Archive: QRE-GUI-POOL-MOM-002 (「聚类动量」页三项优化：池内个股明细 / 表头排序 / 行热力色阶)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

①新 API /api/admin/pool-momentum/members（pool_type/pool_key/trade_date，
后者缺省=最新）：成员 concept=cluster.company_tags 快照、state=当日
daily_tags；`compute_member_metrics` 纯函数即时算 stock_daily（51 日窗口，
复权/vwap/均量比口径与 M7 管线逐位一致——华为概念成员等权 ret_3 与池表值
完全相等、有效成员 770==n_stocks）；名称 reference.stock_basic 降级可选。
②主榜单全部数值列+成员表全列点击排序（▼/▲，None 恒末位，前端
momGenericSort / Python 侧同口径 sort_rows）。③行热力：compute_heat
（ret_w 截面分位 heat∈[-1,1]，红涨绿跌）随窗口切换重算；「长弱短升」
改左侧绿边+加粗避免与热力背景冲突。测试 +21（45 总），全量 1909 passed
+ 4 skipped。qre-gui 已重启 active，curl 实测全 200。未 git commit。

---

## Archive: QRE-GUI-POOL-MOM-001 (8080 管理台新增「聚类动量因子研究」tab：cluster-ashare M7 池动量管线只读展示)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

用户直接指派 demo 只读页。新 `gui/pool_momentum.py`（market_risk.py 同款
只读数据层：_store/_cached TTL 300s/自降级）只读 `cluster.pool_momentum_daily`；
纯逻辑（rank_desc 竞争排名 / compute_acceleration 速度=ret_50 排名·
加速度=ret_50 排名−ret_3 排名·长弱短升=速度后半区且短窗前 10% /
resonance_flag 价量三同正 / sort_by_acceleration）零 DB 可测。
app.py +/api/admin/pool-momentum 与 /api/admin/pool-momentum/detail；
admin.html +「聚类动量」tab（偏差声明卡：concept 池当前快照前视偏差
demo 接受、state 池 point-in-time 无偏差；窗口 3/5/20/50 切换；concept/
state 两榜单含 4 窗 ret + 4 窗 vwap_ret + vol_chg + 速度/短窗排名/加速度/
共振标记；长弱短升高亮；点击池名看 250 日 7 序列 inline SVG，复用
riskSvgLine，零新前端框架）；style.css 纯追加。8081 零改动。
测试 +24（tests/test_gui_pool_momentum.py）；全量 1888 passed + 4 skipped。
qre-gui 已重启 active，/admin 200、两 API 真库实测正常
（2026-09-01：concept 1066 / state 14）。未 git commit，等用户审批。

---

## Archive: QRE-GUI-LAB-RESULT-030 (B 层关键词换代：jieba 碎片词 → 东财+同花顺概念板块成分；8080 总览加「概念标签源」卡片)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

跨仓任务（cluster-ashare 改造 + 本仓消费/展示）：①cluster-ashare 新
`src/tags_lb_concept.py`（东财 akshare + 同花顺自带分页抓取双源采集，
layer='B' source='em_concept'/'ths_concept'，upsert 幂等 + 失败板块
extra_passes 补抓），`scripts/drop_lb_jieba.py` 删除旧 NLP B 层
（97,838 行 + 5,206 字典行，已执行），`tags_lb.py` 标 DEPRECATED，
`run_mvp1 build-tags` 周更接线（deploy 注释同步）。②本仓 admin.py 新
`overview_concept_tags`（B 层 source 分布，自降级），app.py 总览 payload
加 concept_tags，admin.html 加「概念标签源（B 层）」卡片。③8081 归因端
零改动验证：tag-analysis B 层已显示真概念词（华为概念/CPO概念/PCB 等）。
测试：本仓 1840 passed + 4 skipped（+7）；cluster-ashare 204 passed（+12）。
遗留：东财接口当日长时段断连，504 板块入库 290，网络恢复后重跑幂等补齐
（方法见 cluster-ashare README 已知限制）。

---

## Archive: QRE-GUI-LAB-PORT-017 (回测台新端口移植：新增策略 + 回测管理两页面 → 独立 Flask 应用 @8081)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

纯移植，零优化/美化/功能增删。新 `gui/strategy_lab_routes.py`::
`register_strategy_lab_routes(app)` 共享注册（create_app 尾部调用，
路由表与 git HEAD 逐条相等 59/59）；新 `gui/lab.py`（create_lab_app /
launch_lab_gui）+ `templates/lab.html`（「新增策略」自 index.html
strategy tab、「回测管理」自 admin.html onboard tab 脚本精确切片，
含排序 JS/搜索/toggle/删除/gate 徽标，附 /runs 页面）。CLI：
`qre gui --lab`（默认 8081，--port 优先）；`qre gui` 不变。systemd：
`deploy/hardened/qre-gui-lab.service`（端口 8081、
SyslogIdentifier=qre-gui-lab）已 sudo 安装 enable --now
（enabled/active）。测试 `tests/test_gui_lab.py` +12；全量
`uv run pytest -q` → 1807 passed + 4 skipped（基线 1795 + 12）。
冒烟：8081 / 双 tab、/api/admin/refresh stopped 118/118（与 8080
一致）、/admin/strategy/<id> 200；8080 / 与 /admin 200。两个 service
均已重启。无 CR（纯移植无设计决策）。未 commit。详见
09_CODING_HANDOFF.md 顶部、05_PROGRESS.md 顶部。
上一任务：QRE-GUI-SORT-016 / QRE-GUI-DERIV-FRESH-015（见 05/09）。

---

## Archive: QRE-DERIV-ADAPTER-013 (衍生品数据适配层：yc_curve/cb/opt 三个只读 loader + 示例管道，CR D1.5/D2.2/D3.2)

## Task Note

新 `src/quant_research_engine/data/derivatives.py`（只读适配层，QRE 唯一读
derivatives schema 的代码）：`load_zero_curve`（yc_curve 即期 8 节点，
yield%÷100 视为年复利→连续复利近似披露；当日无数据取 ≤trade_date 最近日，
`latest_curve_date` 披露实际日期）、`load_cb_terms`/`cb_cashflows`/
`cb_bond_floor`（现金流近似：常数票息/期限取整付息网格/面值到期无赎回
溢价/利差默认 100bp → convertible_bond_floor + cb_daily.bond_value 对比）、
`load_option_chain`（settle JOIN opt_basic，T=actual/365，r=0.25y 节点，
逐合约 implied_vol，平值隐波断言 (1%,150%)）。已知缺口：库内无 ETF 日线
（510050.SH 不在 stock_daily/index_daily），标的价缺失时须传
`underlying_price`，示例脚本用平值 put-call parity 反推（披露）。
示例 `scripts/derivatives_adapter_smoke.py` + 测试
`tests/test_data_derivatives.py` 15 个（纯函数 11 + DB 冒烟 4 无库 skip）。
冒烟 2026-08-21：曲线 1.164%–2.110%；5 只存续转债债底 99.14–101.74 vs
bond_value 105.4–111.2（差异主因到期赎回溢价未含，可解释已披露 CR §11）；
50ETF 平值 K=3.0 call/put IV 13.67%。全量 1795 绿 + 4 skipped
（基线 1784 + 11 净增）。未 commit、未重启 qre-gui。详见
09_CODING_HANDOFF.md 顶部、05_PROGRESS.md 顶部、CR §11。
上一任务：QRE-GUI-DERIV-CARD-012 / QRE-RISK-GUIDE-011（见 05/09）。

---

# Task Handoff (archive: QRE-RISK-BAROMETER-M3-010)

## Task ID

QRE-RISK-BAROMETER-M3-010 (大盘/板块风险风向标 M3：日更 timer 接入 + GUI 风向标页 + 阈值首轮校准观察)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

M3（CR 末阶段，CR 状态改「✅ M1–M3 已完成」）：deploy/hardened/
qre-barometer.{service,timer}（Mon..Fri 18:30、Persistent、hardened 护栏、
默认最近交易日单日模式，未 sudo）；`qre barometer` CLI；admin TIMER_UNITS
+ install_hint + daily_jobs PIPELINES 登记；/admin 新「大盘风险」tab——
新 `gui/market_risk.py::market_risk_overview`（只读 market_risk.daily、
_cached 300s、分区降级）+ 路由 /api/admin/market-risk + 仪表盘红黄绿灯/
五序列 inline SVG/行业+动态簇热力表/预警双判据详情（复用现有样式，零新
前端框架）；阈值首轮校准观察入 06（red 11/1850=0.59% 全为已知风险事件，
初值保留）。真库冒烟 ok（2026-08-20 总分 63.3 green）。1778 tests green
（+14）。未 commit、未重启 qre-gui、未装 timer（sudo 留主代理/用户）。
细节见 `09_CODING_HANDOFF.md` 顶部。上一任务：QRE-RISK-BAROMETER-M2-009
（M2 装配+回填，1764 green，b0713d7）。

# Task Handoff (archive: QRE-RISK-BAROMETER-M2-009, 风向标 M2 数据装配与回填)

## Task ID

QRE-RISK-BAROMETER-M2-009 (大盘/板块风险风向标 M2：数据装配 + 历史回填 + market_risk_daily 产出)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

M2 在 M1（commit 64addd7，1754 绿）上落地：新 `risk/barometer_job.py`
（risk 包唯一读写 DB 层，业务表只读）——pct_chg/100 收益面板 +
total_mv 市值 + stock_basic.industry 行业 + cluster.daily_tags 当日簇
（<5 跳过）→ M1 纯函数 → 独立 schema `market_risk.daily` 表
（PK (trade_date, scope)，ON CONFLICT 幂等 upsert）+ JSON 产物
outputs/market_risk/<date>.json；年分块 + 312 交易日 buffer。真实回填
2019-01-02→2026-08-20 完成：220,034 行 / 1,850 日 × 120 scope，~21min。
方向性验证全过：2020-02-03 red（突破 85.2% P100）、2024-02 微盘连续 red
（总分 P99–100）、常态 green；全样本 red 11 天均为已知风险事件。
簇分数 M2 不算（成员逐日变动，披露）。1764 tests green（+10）。
未 commit、未重启 qre-gui。细节见 `09_CODING_HANDOFF.md` 顶部。
上一任务：QRE-RISK-BAROMETER-M1-008（M1 纯函数内核，1754 green，已提交 64addd7）。

# Task Handoff (archive: QRE-RISK-BAROMETER-M1-008, 风向标 M1 纯函数内核)

## Task ID

QRE-RISK-BAROMETER-M1-008 (大盘/板块风险风向标 M1：cross_section + barometer 纯函数内核)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

M1 在 R7（1724 绿）上落地（依据已批准 CR
`docs/frm/CR_2026-08-23_market_risk_barometer.md` §5 M1 阶段）：新
`risk/cross_section.py`（纯函数零 DB、向量化——EWMA 方差面板与单列口径
atol 1e-15 一致、截面波动率中位/90 分位、等权/市值加权离散度、滚动 60 日
平均两两相关等权 + w_i·w_j 偶权近似、VaR 突破计数/占比严格 r<−VaR 同
HIT 口径、cross_sectional_summary 一把梭 σ forecast shift(1) 防前视）；
新 `risk/barometer.py`（组合法封装 100% 复用 volatility/tail 出 EWMA σ
与 VaR/ES 95/99、252 日滚动分位分数 warmup 降级 None、红/黄/绿预警
双判据、build_barometer 全市场+板块统一 dict、分组映射调用方传入不感知
来源）；`risk/constants.py` 加 BAROMETER_CORR_WINDOW=60 /
BAROMETER_SCORE_WINDOW=252 / ALERT_CORR_LOOKBACK=20 / ALERT_CORR_JUMP
=0.10 / ALERT_BREACH_RATIO_MAX=0.03 / BREACH_CONFIDENCE=0.99 /
CROSS_SECTION_SIGMA_QUANTILE=0.90 全回显。1754 tests green（+30：
cross_section 17 + barometer 13）。未 commit、未重启 qre-gui（用户约束）。
细节见 `09_CODING_HANDOFF.md` 顶部。上一任务：QRE-RISK-PORTFOLIO-007
（R7 组合层汇总，1724 green，待审批）。

# Task Handoff (archive: QRE-RISK-PORTFOLIO-007, R7 组合层汇总)

## Task ID

QRE-RISK-PORTFOLIO-007 (FRM 风险管理模块 R7：组合层汇总 + risk_report 扩展 + GUI 卡片 + 可选闸扩展)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

R7 在 R6（期权内核 + DGV-VaR，1696 绿）上落地组合层与集成（依据已批准 CR
`docs/frm/CR_2026-08-23_risk_derivatives_extension.md` R7 阶段，CR 状态已改
「R5–R7 已完成」）：新 `risk/portfolio.py`（纯函数零 DB，
`summarize_mixed_portfolio`——股票腿沿用 R1–R4 收益序列法
performance_summary + EWMA VaR/ES 参照、债券/转债腿 DV01 可加/D·C 市值
加权 + 可选 KR01 按节点加总、期权腿组合 Greeks 加权求和、config 显式给
dgv.spot_shock_sd 才计算 DGV-VaR；仅股票输入退化为仅 equity 节）；
`risk/report.py` config 显式传入非空 bond_positions/option_positions/bond_kr01
才追加 `portfolio` 节（meta.sections 回显）+ markdown 渲染「组合与衍生品风险」；
GUI `_risk_display` + run_detail.html 追加「衍生品风险（组合层）」卡片
（有节才显示）；`risk/constants.py` 加 GATE_DV01_MAX/GATE_GREEKS_MAX
（默认 None=不启用），`evaluate_gate_risk` 启用时追加组合 DV01/Greeks 限额
判据，默认关闭时返回与 R4 逐键一致。1724 tests green（+28：portfolio 14 +
report 7 + gui 7）。默认 run 产物零变化，老格式 report 三处（markdown/GUI/
闸）健壮性专项测试覆盖。未 commit、未重启 qre-gui（用户约束）。细节见
`09_CODING_HANDOFF.md` 顶部。上一任务：QRE-RISK-OPTIONS-006（R6 期权内核，
1696 green，待审批）。

# Task Handoff (archive: QRE-RISK-OPTIONS-006, R6 期权内核 + DGV-VaR)

## Task ID

QRE-RISK-OPTIONS-006 (FRM 风险管理模块 R6：期权计算内核 + DGV-VaR)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

R6 在 R5（commit 5472832）上落地期权内核与 DGV-VaR 适配器（依据已批准
CR `docs/frm/CR_2026-08-23_risk_derivatives_extension.md` R6 阶段，纯函数
零 DB 零行情）：新增 `risk/options.py`（BSM 式 15.6–15.9 无股息/q/离散
股息 S₀−D、Black's 式 15.12/15.13、隐波 brentq（IV_BRACKET）、CRR
式 14.4–14.7 欧式+美式含 q、第一层 delta、美式 Greeks 数值差分、
Greeks 全组 Table 16.2 含 q 版与期货期权版 rho=−f·T、组合 Greeks
加权求和）与 `risk/derivatives_var.py`（ΔV ≈ Δ·δS+½Γ(δS)²+vega·δσ、
非中心卡方累积量解析矩、正态/Cornish-Fisher 分位 VaR、VaR 序列对接
backtest_var.backtest_var_summary 复用 HIT/LR）；`risk/constants.py`
追加 IV_BRACKET/DEFAULT_TREE_STEPS=50/GREEK_SHOCK_*，全部结果 dict
回显。教材数值全复现：BSM 例 d1=0.2001/c=8.3069/p=7.9715+parity、
隐波 7.00→25.14%、美式 put 节点值 3.058/0.494/5.699（欧式 2.838）+
收敛 3.082/3.067/3.059/3.055（参数 S=29,K=30,r=3%,σ=25%,T=1 经教材
原文 p193 核对）、PDE 恒等式 1e-10、纯 gamma 解析二阶矩 Var=½Γ²sS⁴、
CF-VaR 对 MC rel 5%、VaR 序列回测违约率 ≈1% 不拒绝。1696 tests
green（+39）。既有 risk 模块零行为改动。未 commit、未重启 qre-gui
（用户约束）。细节见 `09_CODING_HANDOFF.md` 顶部。上一任务：
QRE-RISK-RATES-005（R5 利率与债券内核，1657 green，待审批）。

# Task Handoff (archive: QRE-RISK-RATES-005, R5 利率与债券内核)

## Task ID

QRE-RISK-RATES-005 (FRM 风险管理模块 R5：利率与债券计算内核)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

R5 在 R1–R4 已完成的 risk 包上落地利率与债券计算内核（依据已批准 CR
`docs/frm/CR_2026-08-23_risk_derivatives_extension.md` R5 阶段，纯函数
零 DB 零行情）：新增 `risk/rates.py`（式 16.1–16.5 复利换算、PV/FV、
spot↔折现因子、书4 Ch9 附息债 bootstrap 零息曲线、线性/对数线性插值、
远期利率连续式与式 10.5、par yield 式 16.7/10.4）与 `risk/bonds.py`
（YTM brentq、actual/actual 与 30/360 应计利息、式 12.6 久期凸性、
式 12.1/12.3 effective duration/convexity、DV01 与 D↔DV01 换算、
组合聚合与 DV01 对冲配比、式 12.4 平行移动二阶近似、书4 Ch13 KR01
含 ΣKR01=DV01 自检、书3 Ch16/17 转债债底折现与 spread duration）；
`risk/constants.py` 追加集中参数（day count/插值/key rate 节点/Δr bp/
YTM bracket，全部结果 dict 回显）；`pyproject.toml` 补 scipy 显式依赖。
教材数值全复现：bootstrap d=0.991909/0.980944/0.969406/0.956909、
par yield 2.2103%、平坦曲线年金解析解 P/D/C、DV01↔D 自洽、
ΣKR01=DV01、+100bp 二阶近似 vs 重定价 rel 1.9e-5。1657 tests green
（+52）。既有 risk 模块零行为改动。未 commit、未重启 qre-gui（用户
约束）。细节见 `09_CODING_HANDOFF.md` 顶部。上一任务：
QRE-RISK-GATE-004（R4 晋升闸风险判据，1605 green，待审批）。

# Task Handoff (archive: QRE-RISK-GATE-004, R4 晋升闸风险判据)

## Task ID

QRE-RISK-GATE-004 (FRM 风险管理模块 R4：晋升全量回测闸加入风险判据)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

R4 在 R3（risk_report.json 随 completed run 自动生成）上给晋升全量回测闸
（QRE-GUI-PROMO-GATE-001，commit cfb860d）加风险维度：`risk/constants.py`
集中阈值（`GATE_ES99_MAX=0.03`、`GATE_VAR_CONFIDENCE=0.99`）；
`gui/risk_report.py::evaluate_gate_risk(run_id)` 读该 run 的
risk_report.json——99% ES（历史模拟日收益口径）> 3% 或 99% 覆盖率
Kupiec LR `reject_5pct` → `risk.status=warning`；report 缺失/损坏 →
unavailable 不阻断；`strategy_create.finalize_promotion_gate` 写 gate json
新 `risk` 节，主判据照旧；`refresh_registry.gate_blocks_daily` 扩展为
failed 或 risk=warning 且非 forced 即阻止日更（force 通道照评估不阻断）；
admin.html 闸列 warning 追加「⚠ 风险警示」徽标（tooltip ES99 + VaR 回测
结论）+ style.css `.gate-risk`。1605 tests green（+6 净增：四情形 + force
覆盖 + 徽标渲染）。存量 gate json 无 risk 节行为不变。未 commit、未重启
qre-gui（用户约束）。细节见 `09_CODING_HANDOFF.md` 顶部。上一任务：
QRE-RISK-INTEGRATION-003（R3 集成，1599 green，commit 6852eaa）。

# Task Handoff (archive: QRE-RISK-CORE-002, R2 VaR 回测/压力测试/Bootstrap)

## Task ID

QRE-RISK-CORE-002 (FRM 风险管理模块 R2：VaR 回测 + 压力测试 + Bootstrap 推断)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

R2 在 R1（commit 96db59d）上落地三模块 + 报告扩展，公式以 FRM 知识摘要
为准：`backtest_var.py`（书2 Ch6：HIT 序列、覆盖率 Bernoulli LR + 精确
二项、独立性 Christoffersen 转移矩阵 LR——摘要未点名，注释标注出处
差异、多重检验假阳性 1−(1−α)ⁿ、backtest_var_summary 统一 dict）；
`stress.py`（书4 Ch8：A 股四历史情景库、回放=累计损失/峰谷/Peak/VaR +
相关性崩溃提示、reverse stress β 穿透反查市场冲击分位/σ 倍数）；
`inference.py`（书2 Ch13：arch CircularBlockBootstrap 块长 √n 给年化
收益/夏普/最大回撤算置信区间 + iid 对照 + MC 标准误 σ/√b）；`report.py`
升 R2（var_backtest 默认开用 EWMA μ=0 VaR、stress/bootstrap config 可选
开启）。46 个新测试全为已知答案核对（LR 手算 4.13085、转移计数手算、
情景回放手算 −0.119179/0.05/2.5、reverse β=2 穿透、bootstrap 固定 seed
CI 含真值 + MC 标准误核对、AR(1) 下 iid 低估 CBB）。1578 tests green
（+46 净增）。未 commit、未重启 qre-gui（用户约束）。细节见
`09_CODING_HANDOFF.md` 顶部。上一任务：QRE-RISK-CORE-001（R1 核心包，
1532 green，commit 96db59d）。

# Task Handoff (archive)

## Task ID

QRE-GUI-CREATE-GAPS-001 (新增策略/因子闭环四缺口)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

GUI「新增策略/新增因子」全链路四缺口补齐：①策略冒烟状态闭环——
engine._execute_and_finalize 终态钩子回写 `<name>.smoke.json`
（completed/failed + 关键指标 + finished_at，原子写），run 标记改由
run_backtest(mark=...) 预合并，list_sandbox 自愈滞留 running；前端沙箱列表
三色渲染 + 失败原因摘要 + 轮询刷新。②晋升状态闸——promote /
promote_factor 加 `force`，sidecar 非 completed → 409 smoke_not_passed，
force=true 管理员通道响应注明。③因子冒烟 120s 同步阻塞改异步——
start_smoke_job 复用 daily_jobs.start_script_job（lock_key=factor-smoke:<name>），
POST 即返 job_id + GET /api/factor-create/smoke/<job_id> 轮询 + 前端轮询，
120s 超时与 JSON 解析口径不变。④删 style.css .p3c-hidden 死代码。
1437 tests green（+20 净增）。未重启 qre-gui（用户约束），真实 E2E 待重启。
细节见 `09_CODING_HANDOFF.md` 顶部。

# Task Handoff (archive)

## Task ID

QRE-M5C-MINED-FACTOR-STRAT-001 (M5c：因子工厂 Top3 因子 → QRE 正式策略闭环验证)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

cluster-ashare M5c 联动任务：cluster.mined_factors Top3（MF_001/002/003）
转译为 cs07a/b/c（strategies/catalog/cross_sectional/），经沙箱→冒烟→晋升→
全市场近 1 年回测（批次 b21f1008ec98）→ report-audit 全通过。
截面分位语义由 cluster-ashare 物化表 cluster.mined_factor_flags 承载，
QRE 零代码改动。回测结论：近 1 年未复现 M3b 超额（超额 -11.1~-11.6%），
建议三因子转「衰减观察」——状态调整与是否 commit 均待用户审批。
细节见 `09_CODING_HANDOFF.md` 顶部。

## Task ID

QRE-STRATEGY-FIT-ANALYSIS-001 (M10.1, CR-0003 F3 phase 1)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

This handoff now covers QRE-CONTINUOUS-REFRESH-001 (M10.3). Summary: watermark-gated continuous refresh — `orchestration/refresh.py` + `scripts/refresh_batch.py` (check-only/force/rolling window), per-strategy delta report with manifest/audit parity, systemd user units documented (not installed); small-sample e2e passed; no full-scale execution per standing instruction.

## Current Owner

KIMI_CODE

## Problem Summary

The quick batch (106 strategies × 5,292 symbols × 2024) ranks strategies only by market-wide returns, which buries strategies with strong class-specific edge (user's example: 3% market-wide / 12% best-class). This slice adds the strategy-fit analysis layer: winner-stock enrichment across board/industry/cap/liquidity classes, noise filtering, and multiple-testing-adjusted rankings — reading existing batch artifacts only, no new backtest runs (user instruction 2026-07-19).

## Implementation Summary

Planning only so far (per approved roadmap order M9.1b → M10.1 → M10.2 → M10.3):

1. New `analysis/strategy_fit.py`: batch loading, read-only metadata join (class columns are absent from batch summary.csv — documented gap), configurable noise filters (min trades / min class size / NaN), **significance-tier winner selection** (exact binomial test on per-symbol win rate vs p=0.5 at 90%/99%/99.9% + magnitude gates — user refinement replacing top-10%), strategy-level meta-test vs false-positive expectation, hypergeometric enrichment (pure Python), BH-FDR adjustment, `class_edge` flagging.
2. `scripts/strategy_fit_report.py` command writing summary/classes/markdown report + `report_manifest.json` (new kind, `qre report-audit`-compatible).
3. Runner `--metadata-columns` passthrough so future batches embed class columns (optional for v1).
4. v1 explicitly excludes time-window stability (needs a per-symbol monthly-returns artifact — follow-up v1.1 recorded in CR-0003).

Previous task `QRE-VECTORIZED-ENGINE-001` (M9.1b) finalized in commit `c86441b` (42.8× speedup, metric-identical).

## Standing User Instructions

- No full-scale backtest runs until the core engine work is mostly complete (2026-07-19). Small-sample-first (R-QRE-009) applies to the future full-history (M9.4) runs.
- This slice complies: it executes zero backtests (reads existing CSV/JSON artifacts + one read-only metadata query).

## Hard Constraints

- No new dependencies; pure Python statistics (hypergeometric via `math.comb`, BH-FDR).
- Deterministic outputs; manifest audit parity (R-QRE-007); read-only DB access only (R-QRE-005).

## Validation Evidence

```bash
uv run pytest -q → 1045 passed
real batch: 106 analyzed / 5 skipped; metadata 5,256 symbols
qre report-audit outputs/strategy_fit/f365c8a07b33/report_manifest.json --require-match → status=ok, 0 issues
```
