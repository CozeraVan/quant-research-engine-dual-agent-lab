# 第四入口：外部 AI Agent 工具接口 brainstorm

日期：2026-10-25
状态：用户已确认边界，仅记录研究结论，本阶段不进入开发、不部署。

## 用户意图与边界

第四入口面向用户自行配置的外部 AI Agent。外部 Agent 读取 QRE 的规则、因子库和结果，并自行决定目标函数、参数搜索、股票池、样本外设计和优化循环。QRE 只提供引擎、数据库、校验、任务执行和标准化结果，不评价或干预研究目标。

## 可行性

现有 batch/shared 引擎、因子注册表、worker 队列、资源闸、YAML 安全校验和结果产物可以复用。第四入口主要是鉴权、机器可读发现文档、薄 API 封装、配额与审计，不需要修改回测引擎。外部 Agent 通过 REST + OpenAPI 即可接入，MCP 后置。

## V1 建议范围（估计 12–15 人日）

1. **规则发现**
   - `GET /api/agent/v1/openapi.json`：版本、端点、限额、错误码、轮询建议、引擎能力和 A 股规则。
   - `GET /api/agent/v1/factors`、`/universes`、`/schema/strategy`：复用现有因子目录、中文别名、价格口径、板块与策略结构。
2. **安全校验**
   - `POST /api/agent/v1/validate`：YAML guard、因子存在性/覆盖与 universe 解析，不执行、不计回测配额。SaaS 当前缺少面向 Agent 的 validate 封装，需要补齐。
3. **任务与结果**
   - `POST /api/agent/v1/jobs`：提交 YAML 与参数，强制 Idempotency-Key，返回 job/status/队列信息。
   - `GET /api/agent/v1/jobs/<id>`、`POST /api/agent/v1/jobs/<id>/cancel`。
   - `GET /api/agent/v1/jobs/<id>/result` 与受控 artifacts 下载；复用现有 summary/chart-data/symbols/manifest 等产物。
4. **身份与审计**
   - 新增可吊销 `api_tokens`（hash、prefix、scopes、user_id），不复用浏览器 sessions。
   - jobs 记录 token_id 和用户自定义 labels；QRE 只保存不解释标签。统一响应 envelope、错误码和 IDOR 测试。
5. **资源保护**
   - Agent 独立日配额、每 token 在飞上限、请求限流、429 + Retry-After；与人工回测共队且默认不抢占优先级。
   - 大 universe 必须显式确认；继续执行 yaml_guard、max_codes/max_days、worker 内存闸、硬超时和产物限制。
   - 暴露队列深度/等待建议，外部 Agent 自行退避。容量约束主要来自家里 worker 而非 ECS API。

## 明确不做

- 不做 sweep/parent-child 编排、参数网格、排行榜、目标函数、train/validation/test 约束或显著性强制闸。
- 不做站内 AI 循环、自动股票池、加仓/金字塔、引擎改动、专属 AI UI、MCP。
- 不承诺盈利；过拟合、多重检验、样本外设计和股票池研究由外部 Agent 负责。文档只说明口径、风险和可复用工具。

## 后续可选

MCP 适配（待真实接入需求）、Agent 记录筛选、结果 OSS 直传、机器时配额、站内 AI 研究员复用同一 API。加仓/金字塔需独立引擎 CR，不属于第四入口。

## 验收方向

外部 Agent 能凭独立 Token 发现规则、校验策略、幂等提交、轮询/取消任务并读取标准化结果；用户自定义目标不被 QRE 改写。全量回归、IDOR、配额、限流和审计通过后，再进行小样本真实 Agent 调用验证，禁止直接全量回测。
