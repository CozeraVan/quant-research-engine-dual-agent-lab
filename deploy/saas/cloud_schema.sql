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

-- QRE-JOB-API（A2，2026-09-19）：jobs 表对齐 17_JOB_PROTOCOL.md。
-- 幂等：列存在性检查 + IF NOT EXISTS，可重复执行。
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name='jobs' AND column_name='lease_expires') THEN
    ALTER TABLE jobs RENAME COLUMN lease_expires TO lease_expires_at;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name='jobs' AND column_name='error') THEN
    ALTER TABLE jobs RENAME COLUMN error TO error_message;
  END IF;
END $$;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS progress SMALLINT NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS progress_message TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS cancel_requested BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS error_class TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS idempotency_key TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS parent_job_id BIGINT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS upload_token TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_idem
    ON jobs (user_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
-- QRE-SAAS-D1D2（内测三级权限，2026-09-20）：密码登录临时方案 + 游客匿名提交
-- users 加密码哈希与层级；jobs/strategies 的 user_id 可空（游客不落 users 行，
-- 用 jobs.guest_key=sha256(IP+salt) 归属，每日清理任务删除次日以前的游客记录）。
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS tier TEXT NOT NULL DEFAULT 'member'
    CHECK (tier IN ('guest','member','paid'));
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS guest_key TEXT;
ALTER TABLE jobs ALTER COLUMN user_id DROP NOT NULL;
ALTER TABLE strategies ALTER COLUMN user_id DROP NOT NULL;
CREATE INDEX IF NOT EXISTS idx_jobs_guest ON jobs (guest_key, created_at DESC)
    WHERE guest_key IS NOT NULL;

-- 状态枚举对齐协议：done → completed，新增 uploading/expired/canceled
-- 注意顺序：先删旧 CHECK 再 UPDATE（旧 CHECK 不允许 completed）。
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;
UPDATE jobs SET status = 'completed' WHERE status = 'done';
UPDATE jobs SET status = 'canceled' WHERE status = 'cancelled';
ALTER TABLE jobs ADD CONSTRAINT jobs_status_check
    CHECK (status IN ('queued','leased','running','uploading','completed','failed','expired','canceled'));

-- 缺因子申请（QRE-SAAS-007）：用户不直接增/改因子；缺因子时提交申请，
-- 运营方按需求热度人工审核后离线计算入库（8080 管理台审核界面为后续任务）。
CREATE TABLE IF NOT EXISTS factor_requests (
    id             BIGSERIAL PRIMARY KEY,
    user_id        BIGINT NOT NULL REFERENCES users(id),
    strategy_name  TEXT,                          -- 触发申请的策略名（可空）
    factors        JSONB NOT NULL,                -- 缺失因子名数组 ["rsi_14", ...]
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','approved','rejected')),
    note           TEXT,                          -- 审核备注（入库说明/拒绝原因）
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_factor_requests_user ON factor_requests (user_id, created_at DESC);

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
ALTER TABLE results ALTER COLUMN user_id DROP NOT NULL;  -- QRE-SAAS-D1D2：游客结果行

COMMIT;
