# CR-2026-11-16 · MCP CLI 短信登录

## 范围

- 新增 `qre-mcp-login`：手机号 → 发码 → 验证码 → 会话 → 30 天 Agent token。
- 凭证原子保存为 `${XDG_CONFIG_HOME:-~/.config}/qre/mcp.json`（0600），可用环境变量覆盖路径。
- `qre-mcp` 和 `qre-mcp-export` 环境 token 优先，否则自动读凭证。
- `--logout` 用保存的会话吊销 Agent token 并删除本机文件；不保存短信码/密码。

## 边界

复用既有登录和 token API，无新后端路由、schema、权限或配额；不实现 OAuth 2.1。真实短信输入由用户本人完成，本轮仅模拟上游验收，不声称真实短信已测。

## 验证

143 项 MCP/登录/导出/Agent/页面/模板测试通过，14 skipped；CLI help 和 ECS 部署通过，无回测。
