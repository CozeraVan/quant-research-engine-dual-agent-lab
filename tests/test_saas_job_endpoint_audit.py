"""P0-8：结果/任务端点 IDOR 普查合同。

这个测试不重复跑权限矩阵（那是 `tests/test_saas_access_hardening.py` 的职责），
而是锁定「所有带 `<int:job_id>` 的 GET 路由」清单：未来新增job_id GET 端点
必须显意接入本清单并补权限回归，防止无声扩大攻击面。
"""

from __future__ import annotations

from quant_research_engine.gui.saas import create_saas_app

EXPECTED_JOB_ID_GET_ROUTES = {
    "/saas/jobs/<int:job_id>",
    "/saas/jobs/<int:job_id>/symbols",
    "/saas/jobs/<int:job_id>/symbols/<ts_code>",
    "/api/jobs/<int:job_id>",
    "/api/saas/jobs/<int:job_id>",
    "/api/results/<int:job_id>/summary",
    "/api/results/<int:job_id>/chart-data",
    "/api/results/<int:job_id>/tag-analysis",
    "/api/results/<int:job_id>/risk-analysis",
    "/api/results/<int:job_id>/symbols",
    "/api/results/<int:job_id>/symbols/<ts_code>",
    "/api/results/<int:job_id>/symbols/<ts_code>/gen-status",
    # AGENT-API M5（2026-11-03）：外部 Agent 结果/产物读取。三条均走
    # agent_api._load_agent_job 的令牌归属校验（本令牌创建的 job 或同属主人工 job），
    # 他人/不存在一律 404 同体；artifacts 另加文件名白名单 + 路径限定 job 目录。
    "/api/agent/v1/jobs/<int:job_id>/result",
    "/api/agent/v1/jobs/<int:job_id>/result/chart-data",
    "/api/agent/v1/jobs/<int:job_id>/artifacts/<path:name>",
}


def test_job_id_get_routes_are_frozen() -> None:
    app = create_saas_app()
    routes = {
        rule.rule
        for rule in app.url_map.iter_rules()
        if "<int:job_id>" in rule.rule and "GET" in rule.methods
    }
    assert routes == EXPECTED_JOB_ID_GET_ROUTES, (
        f"unexpected job_id GET routes: {sorted(routes ^ EXPECTED_JOB_ID_GET_ROUTES)}"
    )
