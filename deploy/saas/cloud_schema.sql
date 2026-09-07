-- 云小库 schema（CR-0004 / QRE-SAAS-001）
-- 部署目标：阿里云 ECS 2C2G 本机 PG（或 SQLite 兼容期先用 PG）
-- 只存用户资产：账户、策略、任务、结果元数据。严禁落任何 K线/因子明细。
-- 应用方式：psql -d aguhuice -f cloud_schema.sql（幂等，可重复执行）

BEGIN;

-- 用户：验证码登录（email 或手机号，QRE-SAAS-006）
CREATE TABLE IF NOT EXISTS users (
    id            BIGSERIAL PRIMARY KEY,
    phone         TEXT NOT NULL UNIQUE,
    nickname      TEXT,
    quota_daily   INT NOT NULL DEFAULT 10,        -- 每日回测次数配额
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);
-- QRE-SAAS-006 幂等迁移：支持邮箱登录（phone 可空 + email 列 + sessions 表）
ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE users ALTER COLUMN phone DROP NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users (email) WHERE email IS NOT NULL;

-- 登录 session（无 Redis：直接用 PG，30 天有效，token=secrets.token_urlsafe(32)）
CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,                  -- bearer token
    user_id    BIGINT NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);

-- 短信/邮箱验证码（5 分钟有效，一次性）
-- phone 列保留原名以避免破坏既有调用，实际存 channel 目标（手机号或邮箱地址）；
-- channel 列区分通道（sms/email）
CREATE TABLE IF NOT EXISTS sms_codes (
    id         BIGSERIAL PRIMARY KEY,
    phone      TEXT NOT NULL,
    code_hash  TEXT NOT NULL,                     -- 只存哈希，不存明文
    expires_at TIMESTAMPTZ NOT NULL,
    used_at    TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE sms_codes ADD COLUMN IF NOT EXISTS channel TEXT NOT NULL DEFAULT 'sms';
CREATE INDEX IF NOT EXISTS idx_sms_codes_phone ON sms_codes (phone, created_at DESC);

-- 策略：NL 原文 + 编译后 YAML（纠错/人工修改后的最终版）
CREATE TABLE IF NOT EXISTS strategies (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id),
    name        TEXT NOT NULL,
    nl_text     TEXT,                             -- 自然语言原文（可空=向导/YAML 直写）
    yaml        TEXT NOT NULL,                    -- 最终回测 YAML
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_strategies_user ON strategies (user_id, updated_at DESC);

-- 回测任务：状态机 queued → leased → running → done / failed
-- lease 过期（Worker 宕机）自动回队重试，见 worker_jobs 视图
CREATE TABLE IF NOT EXISTS jobs (
    id            BIGSERIAL PRIMARY KEY,
    user_id       BIGINT NOT NULL REFERENCES users(id),
    strategy_id   BIGINT NOT NULL REFERENCES strategies(id),
    kind          TEXT NOT NULL DEFAULT 'full',   -- smoke=小样本试算 / full=全量回测
    status        TEXT NOT NULL DEFAULT 'queued'
                  CHECK (status IN ('queued','leased','running','done','failed','cancelled')),
    params        JSONB NOT NULL DEFAULT '{}',    -- 回测区间/资金/成本/股票池等覆盖参数
    priority      INT NOT NULL DEFAULT 0,         -- 未来付费用户优先队列预留
    attempts      INT NOT NULL DEFAULT 0,
    max_attempts  INT NOT NULL DEFAULT 2,
    leased_by     TEXT,                           -- Worker 标识
    lease_expires TIMESTAMPTZ,                    -- 心跳租约到期时间
    error         TEXT,                           -- failed 时的原因（用户可读）
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ
);
-- Worker 认领查询的主路径：按状态+优先级取最旧任务
CREATE INDEX IF NOT EXISTS idx_jobs_pick ON jobs (status, priority DESC, created_at)
    WHERE status = 'queued';
CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs (user_id, created_at DESC);

-- 结果：报告元数据 + 前端图表所需 JSON；大文件（Excel/CSV 明细）放 OSS
CREATE TABLE IF NOT EXISTS results (
    id          BIGSERIAL PRIMARY KEY,
    job_id      BIGINT NOT NULL UNIQUE REFERENCES jobs(id),
    user_id     BIGINT NOT NULL REFERENCES users(id),
    summary     JSONB NOT NULL,                   -- 核心指标：总收益/年化/超额/回撤/胜率/夏普…
    chart_data  JSONB NOT NULL,                   -- 净值曲线/回撤/热力图/归因等前端直接可用
    artifacts   JSONB NOT NULL DEFAULT '[]',      -- [{kind:'excel',oss_key:...,size:...}]
    data_until  DATE,                             -- 数据截止日期（静态快照声明）
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_results_user ON results (user_id, created_at DESC);

COMMIT;
