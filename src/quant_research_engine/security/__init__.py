"""安全防线包（CR-0004 M2 / QRE-SAAS-005）。

- yaml_guard：策略 YAML 严格 schema 校验 + 信号表达式 AST 白名单校验
  （公网 NL 入口的前置闸；引擎执行前强制）。
- worker/sandbox.py：新因子 Python 代码的 Docker 隔离执行器。
"""
