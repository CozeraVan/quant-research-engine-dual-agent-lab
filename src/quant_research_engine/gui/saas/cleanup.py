"""游客回测记录每日清理（15 号文档 D 阶段定稿：游客记录次日清空）。

删除 created_at < 当日的游客记录（jobs.user_id IS NULL）及其
results 行、strategies 行（user_id IS NULL）与产物目录 job_<id>/。
幂等：可重复执行。

用法：SAAS_DB_URL=... SAAS_UPLOAD_DIR=... python -m quant_research_engine.gui.saas.cleanup
ECS 由 qre-saas-guest-cleanup.timer 每日 04:00 触发。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from sqlalchemy import create_engine, text


def cleanup_guest_jobs(db_url: str, upload_root: str | Path) -> dict[str, int]:
    engine = create_engine(db_url)
    root = Path(upload_root)
    removed_dirs = 0
    with engine.begin() as conn:
        stale = conn.execute(
            text("SELECT id FROM jobs WHERE user_id IS NULL AND created_at::date < now()::date")
        ).scalars().all()
        for job_id in stale:
            job_dir = root / f"job_{job_id}"
            if job_dir.is_dir():
                shutil.rmtree(job_dir)
                removed_dirs += 1
        conn.execute(
            text("DELETE FROM results WHERE job_id = ANY(:ids)"), {"ids": stale}
        )
        conn.execute(
            text("DELETE FROM jobs WHERE user_id IS NULL AND created_at::date < now()::date")
        )
        conn.execute(text("DELETE FROM strategies WHERE user_id IS NULL AND id NOT IN (SELECT strategy_id FROM jobs)"))
    engine.dispose()  # 释放连接（测试 fixture 拆库/定时任务退出都要求无悬挂连接）
    return {"jobs": len(stale), "dirs": removed_dirs}


def main() -> None:
    db_url = os.environ["SAAS_DB_URL"]
    upload_root = os.environ.get("SAAS_UPLOAD_DIR", "outputs/saas_uploads")
    result = cleanup_guest_jobs(db_url, upload_root)
    print(f"[guest-cleanup] 清除游客 job {result['jobs']} 条、产物目录 {result['dirs']} 个", flush=True)


if __name__ == "__main__":
    main()
