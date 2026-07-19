.PHONY: help install test smoke gui clean generate-strategies preflight-check backtest-smoke backtest-full

# Quant Research Engine — Makefile

help:  ## 显示可用命令 (默认)
	@echo "Quant Research Engine — 可用命令:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

install:  ## 安装依赖 (uv sync)
	uv sync

test:  ## 运行完整测试套件
	uv run pytest -q

smoke:  ## 运行策略冒烟测试并显示详情
	uv run qre strategy-smoke
	uv run qre smoke-files --details

gui:  ## 启动本地浏览器控制台
	uv run qre gui

# ---------------------------------------------------------------------------
# Strategy Catalog
# ---------------------------------------------------------------------------

generate-strategies:  ## 生成策略目录 YAML 文件
	uv run python scripts/generate_strategy_yamls.py

preflight-check:  ## 检查所有策略的因子可用性 (需要数据库)
	uv run python scripts/batch_preflight_check.py --output-json outputs/preflight_check_report.json

preflight-check-ready:  ## 仅显示通过预检的策略
	uv run python scripts/batch_preflight_check.py --ready-only

# ---------------------------------------------------------------------------
# Batch Backtest
# ---------------------------------------------------------------------------

JOBS ?= 4  ## 并行 worker 数 (可用 JOBS=8 覆盖)

backtest-smoke:  ## 对所有策略运行快速冒烟回测 (2个月窗口)
	uv run python scripts/batch_backtest_runner.py --mode smoke --skip-preflight

backtest-quick:  ## 对所有策略运行1年回测 (并行+精简产物)
	uv run python scripts/batch_backtest_runner.py --mode quick --jobs $(JOBS) --compact --skip-preflight --resume

backtest-full:  ## 对所有策略运行全量回测 (2015-2025, 并行+精简产物)
	uv run python scripts/batch_backtest_runner.py --mode full --jobs $(JOBS) --compact --skip-preflight --resume

backtest-category:  ## 对指定类别运行回测 (使用 CATEGORY=trend_following)
	uv run python scripts/batch_backtest_runner.py --category $(CATEGORY) --skip-preflight

backtest-resume:  ## 续跑未完成的策略
	uv run python scripts/batch_backtest_runner.py --mode smoke --skip-preflight --resume

backtest-dry:  ## 列出策略不执行
	uv run python scripts/batch_backtest_runner.py --dry-run

clean:  ## 清理输出和缓存文件
	@echo "将删除 outputs/ 目录和 __pycache__ 文件"
	@read -p "确认? [y/N] " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		rm -rf outputs/; \
		find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
		find . -type f -name '*.pyc' -delete; \
		echo "已清理."; \
	else \
		echo "已取消."; \
	fi
