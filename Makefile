.PHONY: help install test smoke gui clean

# Quant Research Engine — Makefile

help:  ## 显示可用命令 (默认)
	@echo "Quant Research Engine — 可用命令:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## 安装依赖 (uv sync)
	uv sync

test:  ## 运行完整测试套件
	uv run pytest -q

smoke:  ## 运行策略冒烟测试并显示详情
	uv run qre strategy-smoke
	uv run qre smoke-files --details

gui:  ## 启动本地浏览器控制台
	uv run qre gui

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
