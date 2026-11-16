# CR-2026-11-16 · MCP 回测结果本地紧凑导出

## 目标

Agent CLI 在回测完成后可把核心产物保存到用户电脑，降低远程读取依赖。首版不改变云端 TTL、不自动删除产物，不影响网页查看和分享。

## 实现

- `qre-mcp-export <job_id> --output <目录>`，复用 Agent token 和受控产物下载。
- 默认 10 个核心产物 + result.json + local_manifest.json；不下载逐股目录、图片、Excel。
- 单文件 32MiB 上限、文件名白名单、SHA-256 校验、partial 失败清理、原子改名、不覆盖既有目录。
- 不把 Base64 大文件塞入 MCP JSON；由用户本机 Agent 调用导出命令。

## 权限合同调整

原 `_load_agent_job` 只允许本 token 的 job 或人工 job，导致同账号换新 token 无法导出旧结果。现统一为账号级归属：同账号有效 token 可读全部历史任务，其他账号仍 404。9090 新增“结果可见范围”，读取 `JOB_RESULT_VISIBILITY` 常量，与执行策略同源。

## 验证

- 119 项 MCP/导出/Agent/路由/模板测试通过，13 skipped。
- job360 真实导出 12 文件，复制到本机 `.tmp/mcp-export-job360/job_360/`，逐文件大小/hash 复核通过。
- 导出专用 token id=3 已吊销，远端临时凭证和导出副本清理；无新回测、无云端删除。
