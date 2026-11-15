# 视频 Agent 本地回测结果直读

基址：`http://127.0.0.1:8081`。无需 ECS、公网账号、登录 token 或人工复制数据。

## 发现结果

```bash
curl -s http://127.0.0.1:8081/api/lab/runs
```

每个 run 都带 `run_id`、策略名、状态、区间、超额收益及 `links`。只处理 `status=completed` 且有 `output_dir` 的记录。

## 读取一个结果

```bash
RUN_ID=20261114T051744140231
curl -s "http://127.0.0.1:8081/api/lab/runs/$RUN_ID"
```

`run.output_dir` 是本地产物目录；`links` 给出结果页面、图表、风险、归因和个股详情 URL。需要下载完整参数时使用：

```bash
curl -s "http://127.0.0.1:8081/api/saas/jobs/$RUN_ID/params"
```

## 页面与个股

- 结果页：`/lab/runs/<run_id>`
- 个股列表：`/lab/runs/<run_id>/symbols`
- 个股详情：`/lab/runs/<run_id>/symbol/<ts_code>`
- 个股 JSON：`/api/results/<run_id>/symbols/<ts_code>`

结果页与个股页直接复用公网 SaaS 模板、静态图表和重播组件。归因标签不存在时接口返回 404，个股列表仍从本地 round_trips 构建，不应转向公网补数据。

证据：真实 run `20261114T051744140231` 的结果、列表、个股、参数接口均通过；浏览器三页零 pageerror，截图在 `.tmp/local-video-browser/`。
