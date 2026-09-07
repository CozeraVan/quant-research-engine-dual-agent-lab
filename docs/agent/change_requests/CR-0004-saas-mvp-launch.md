# CR-0004: 8081 SaaS MVP 上线（A股回测，aguhuice.com）

## 1. Background

2026-09-07 与用户对齐：将 8081（gui/lab*.py，当前本地单机的日线级量化回测台）作为正式产品上线。域名 `aguhuice.com` 已购（阿里云，实名认证中）；服务器为阿里云 ECS 2C2G / Ubuntu 24.04 / 40GB ESSD / 3Mbps（¥99/年）。个人主体备案（无公司执照），第一阶段免费工具站，收费阶段再注册个体工商户。

关键架构决策（已与用户对齐，2026-09-05 ~ 09-07）：

- **数据不出家门**：日线+因子大库（~123 GB）留在本地 PC 的 WSL PG，静态快照（MVP 无日更）；
- **云只放用户资产**：ECS 上小 PG（用户、策略 YAML、任务、结果元数据，<2 GB）；
- **家用 PC 当 Worker**：出站轮询云端任务队列 → 本地读库跑回测 → 结果 POST 回云端，无需公网入站；
- 旧机 2060+8700 作为后续 Worker 扩容选项，本阶段不动。

## 2. Goal

普通用户能用自然语言或向导描述一个 A 股日线策略，提交回测，查看并保存结果——以最小功能集完成公网可访问的 MVP。

## 3. User Scenario

用户想验证自己构想的策略能否在 A 股盈利、或策略在哪些股票上有超额收益：登录 → 自然语言/快速向导描述策略（NL 走 DeepSeek/Kimi 编译为 YAML）→ 小样本试算 → 提交全量回测（排队）→ 查看图表化结果页 → 保存/下载历史报告。

## 4. Scope

### In Scope

- **M1 代码改造**：8081 裁剪为四功能（写策略 / 提交回测 / 结果呈现 / 历史记录）；回测任务队列化（提交→Worker 轮询→结果回传）；云小库 schema（users / strategies / jobs / results）；本地 PG 只读账号（`GRANT SELECT`）供 Worker 使用。
- **M2 安全**：NL 生成代码沙箱（容器隔离 + 限时 + 禁网 + 资源上限）；手机号验证码登录；接口限流。
- **M3 链路打通**：Worker 拉任务端到端（云端下单→本地计算→结果回传→前端可见）。
- **M4 部署上线**：备案通过后部署至 aguhuice.com，邀 10–20 人内测。

### Out of Scope

- 策略日更/持续更新（MVP 省略，数据为静态快照，页面标注数据截止日期）
- 分时回测、聚类动量嵌入、小程序、支付收费
- 8080 管理台（保持内网工具，不上线）
- GPU 加速（回测为 CPU/IO 密集）

## 5. Affected Requirements

- 新增 SaaS 部署要求，与既有本地开发流程并行；8081 既有功能（NL 编译、快速向导、结果页图表）以"云端服务化"方式复用，不改变引擎核心口径。

## 6. Protected Requirements

- Read `docs/agent/02_LOCKED_REQUIREMENTS.md`
- 引擎回测口径（交易对记账、含成本）不得为上线而简化；8081 冻结的页面观感基准（RSI 基准 run）保持可比。

## 7. Suggested Tasks

| Task ID | Task | Priority | Status |
|---|---|---|---|
| QRE-SAAS-001 | 云小库 schema + 迁移脚本（users/strategies/jobs/results） | High | TODO |
| QRE-SAAS-002 | 任务队列：云侧任务表 + Worker 轮询协议（拉任务/回传结果/心跳） | High | TODO |
| QRE-SAAS-003 | 本地 PG 只读账号 + Worker 侧连接改造 | High | TODO |
| QRE-SAAS-004 | 8081 四功能裁剪 + 任务状态前端（排队/运行/完成/失败） | High | TODO |
| QRE-SAAS-005 | NL 沙箱加固（容器/限时/禁网/资源上限） | High | TODO |
| QRE-SAAS-006 | 登录鉴权（手机号验证码）+ 接口限流 | Medium | TODO |
| QRE-SAAS-007 | 部署脚本 + 服务器初始化清单（安全组 22/80/443、fail2ban、Docker） | Medium | TODO |

## 8. Acceptance Criteria

- [ ] 用户从注册到拿到一份全市场回测报告全链路在公网可用
- [ ] 云端不存储任何 K线/因子明细数据
- [ ] 家用 PC 宕机仅导致任务排队，用户数据零丢失
- [ ] NL 生成代码在沙箱内执行，无法触网/越权

## 9. Risks

- 备案审核时长不可控（2–3 周），期间以 IP+非常用端口内测；
- 金融类目内容边界：纯工具定位，不荐股、不晒收益排行；
- 家用 PC 稳定性（断电/断网/WSL 重启）→ 任务可重试 + 结果上云对冲。

## 10. Implementation Notes

- 成本模型锚点：全市场 2 年回测 ≈ 12 分钟单核 ≈ ¥0.01–0.03/次；云月成本 ¥100–230；
- 引擎实测基准：MACD 500 股 × 2 年 = 66 秒（2026-09-01，QRE-GUI-CONSOL-041）。

## 11. Proposed Agent State Transition

- Next Phase: `IMPLEMENTING`
- Next Owner: `KIMI_CODE`
