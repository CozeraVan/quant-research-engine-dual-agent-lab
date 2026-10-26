"""QRE-SAAS-PUBLIC-BETA-OPS：公测运营/反馈闭环验收数据播种。

专用临时库 qre_public_beta_audit（不跑回测、不碰线上库）。登录用户任务由
验收脚本以 Bearer 走真实 POST /api/jobs 提交，再由 worker 协议端点
（claim/fail/result/meta）驱动状态——不启动真实 worker、不跑真实回测。

同时播种：他人 completed 任务（权限用例）、已完成任务的结果数据（结果页渲染）、
失败任务（失败恢复用例）、游客 queued 任务（排队用例）、多类型/状态反馈
（管理台筛选与流转用例）、管理员账号（管理台用例）。种子信息写入 seed.json
供 browser_audit.py 消费。
"""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = "qre_public_beta_audit"
WORKER_TOKEN = "public-beta-ops-token"
LOGIN_PHONE = "22644212509"      # 登录会员（user 1）
OTHER_PHONE = "22644212508"      # 他人会员（user 2）
ADMIN_PHONE = "22644212507"      # 管理员（user 9）

VALID_YAML = (
    "experiment:\n  name: audit\ndata:\n  market_fields: [close]\n"
    "signal:\n  entry: close > 0\n  exit: close < 0\n"
    "evaluation:\n  forward_return_horizons: [1, 3, 5, 10, 20]\n  quantiles: 5\n"
    "holding:\n  max_holding_days: 20\n"
)


def _psql(db: str, *args: str) -> None:
    subprocess.run(["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
                   check=True, capture_output=True, text=True)


def _one(sql: str) -> str:
    out = subprocess.run(["psql", f"postgresql:///{DB}", "-tAc", sql],
                         check=True, capture_output=True, text=True)
    return out.stdout.strip()


def main() -> None:
    subprocess.run(["psql", "postgresql:///postgres", "-v", "ON_ERROR_STOP=1",
                    "-c", f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)"],
                   check=True, capture_output=True)
    subprocess.run(["psql", "postgresql:///postgres", "-v", "ON_ERROR_STOP=1",
                    "-c", f"CREATE DATABASE {DB}"], check=True, capture_output=True)
    _psql(DB, "-f", "deploy/saas/cloud_schema.sql")

    _psql(DB, "-c",
          "INSERT INTO users (id, phone, tier, role) VALUES "
          f"(1, '{LOGIN_PHONE}', 'member', 'user'), "
          f"(2, '{OTHER_PHONE}', 'member', 'user'), "
          f"(9, '{ADMIN_PHONE}', 'member', 'admin') "
          "ON CONFLICT (id) DO NOTHING")
    _psql(DB, "-c", "INSERT INTO strategies (user_id, name, yaml) VALUES "
                    "(1, '本人策略', 'y'), (2, '他人策略', 'y')")
    # 已完成任务（本人/他人）：结果数据供结果页与权限用例
    for uid, name, hours in ((1, "本人策略", 5), (2, "他人策略", 6)):
        _psql(DB, "-c",
              "INSERT INTO jobs (user_id, strategy_id, kind, status, params, created_at, "
              "started_at, finished_at) SELECT :uid, s.id, 'full', 'completed', "
              "'{\"start\": \"2026-09-01\", \"end\": \"2026-09-30\", "
              "\"codes\": [\"000001.SZ\"]}'::jsonb, "
              f"now() - interval '{hours} hours', "
              f"now() - interval '{hours} hours' + interval '12 seconds', "
              f"now() - interval '{hours} hours' + interval '132 seconds' "
              "FROM strategies s WHERE s.name = :name"
              .replace(":uid", str(uid)).replace(":name", f"'{name}'"))
    chart = json.dumps({
        "dates": [f"2026-09-{d:02d}" for d in range(1, 31)],
        "equity": [round(200000 * (1 + 0.002 * i), 2) for i in range(30)],
        "cumret": [round(0.002 * i, 6) for i in range(30)],
        "drawdown_pct": [0.0] * 30,
        "benchmarks": {},
        "metrics": {"total_return": 0.06, "excess_return": 0.01, "sharpe": 1.1,
                    "annual_return": 0.72, "max_drawdown": -0.05, "win_rate": 0.6,
                    "buy_hold_return": 0.05, "date_start": "2026-09-01",
                    "date_end": "2026-09-30"},
        "trades": {"points": [{"symbol": "000001.SZ", "entry_date": "2026-09-03",
                               "exit_date": "2026-09-10", "net_return": 0.02}],
                   "sampled": False},
        "brief": {"name": "审计策略"},
        "meta": {"strategy_name": "审计策略", "date_start": "2026-09-01",
                 "date_end": "2026-09-30", "n_codes": 1, "initial_cash": 200000},
    }, ensure_ascii=False).replace("'", "''")
    for name in ("本人策略", "他人策略"):
        _psql(DB, "-c",
              "INSERT INTO results (job_id, user_id, summary, chart_data, data_until) "
              "SELECT j.id, j.user_id, "
              "'{\"strategy_total_return\": 0.06}'::jsonb, "
              f"'{chart}'::jsonb, '2026-09-30' "
              "FROM jobs j JOIN strategies s ON s.id = j.strategy_id "
              f"WHERE s.name = '{name}' AND NOT EXISTS "
              "(SELECT 1 FROM results r WHERE r.job_id = j.id)")
    # 失败任务（本人，已失败）：失败恢复用例由浏览器提交新任务后走 worker 协议，
    # 这里另留一条历史 failed 供运营失败原因口径
    _psql(DB, "-c",
          "INSERT INTO jobs (user_id, strategy_id, kind, status, params, error_class, "
          "error_message, created_at, finished_at) SELECT 1, s.id, 'full', 'failed', '{}', "
          "'engine_error', '历史失败样例', now() - interval '2 hours', "
          "now() - interval '2 hours' FROM strategies s WHERE s.name = '本人策略'")
    # 游客 queued 任务（排队展示）
    _psql(DB, "-c",
          "INSERT INTO jobs (user_id, strategy_id, kind, status, params, guest_key, "
          "created_at) SELECT NULL, s.id, 'full', 'queued', '{}', 'audit-guest-key', "
          "now() - interval '30 minutes' FROM strategies s WHERE s.name = '本人策略'")
    # 反馈：多类型/状态（管理台筛选与流转）
    _psql(DB, "-c",
          "INSERT INTO feedback (user_id, content, category, status, page, created_at) VALUES "
          "(1, '登录后结果页打不开', 'bug', 'open', '/saas/jobs/1', now() - interval '3 hours'), "
          "(2, '希望能记住上次的区间', 'experience', 'doing', '/saas/new', now() - interval '2 hours'), "
          "(1, '想要 OBV 因子', 'factor', 'done', '/saas/new', now() - interval '1 hours'), "
          "(2, '其他杂项', 'other', 'open', '/saas/', now() - interval '40 minutes')")
    # NL 编译事件（运营口径：上线起统计；成功/失败/命中各一）
    _psql(DB, "-c",
          "INSERT INTO nl_compile_events (ok, cache_hit, error_class, scope, created_at) VALUES "
          "(true, false, NULL, 'guest', now() - interval '3 hours'), "
          "(true, true, NULL, 'guest', now() - interval '2 hours'), "
          "(false, false, 'missing_factors', 'member', now() - interval '1 hours')")

    (HERE / "seed.json").write_text(json.dumps({
        "db": DB, "worker_token": WORKER_TOKEN,
        "login_phone": LOGIN_PHONE, "other_phone": OTHER_PHONE,
        "admin_phone": ADMIN_PHONE, "valid_yaml": VALID_YAML,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"seed ok: db={DB}")


if __name__ == "__main__":
    main()
