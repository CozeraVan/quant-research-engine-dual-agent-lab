"""QRE-SAAS M3：Worker 客户端包（家用 PC 出站轮询云端任务队列）。

- client.py：CloudClient——云端 /api/saas/worker/* 三接口封装（stdlib urllib，
  无新依赖；venv 无 requests），超时 + 指数退避有限重试。
- runner.py：执行一个 leased job——复用 gui.engine.run_backtest 既有引擎链路
  （与 8081 批量回测同一条路径，不 fork），结果用 gui.lab_result.build_lab_chart_data
  组装回传 payload。
- daemon.py：主循环（轮询 lease → runner → heartbeat → result 回传），
  异常兜底不死，SIGTERM 优雅退出。
"""
