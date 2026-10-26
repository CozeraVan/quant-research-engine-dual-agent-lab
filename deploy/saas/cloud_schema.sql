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

-- CR-2026-10-04 模块一（策略资产化）：创建入口模式 + 向导结构化快照。
-- entry_mode: nl / wizard / yaml；存量推断 nl_text 非空→nl，否则→yaml。
-- 应用层亦懒自愈（先查 information_schema 再 ALTER，ECS 表 owner 为 postgres 须手工 apply）。
ALTER TABLE strategies ADD COLUMN IF NOT EXISTS entry_mode TEXT;
ALTER TABLE strategies ADD COLUMN IF NOT EXISTS wizard_state JSONB;
UPDATE strategies SET entry_mode =
    CASE WHEN nl_text IS NOT NULL AND btrim(nl_text) <> '' THEN 'nl' ELSE 'yaml' END
WHERE entry_mode IS NULL;

-- QRE-SAAS-RESULT-ACTIONS（2026-10-05）：提交回测建行但默认不入库（in_library=false），
-- 显式保存/建 watch 才进策略库；存量行 backfill true（仅列不存在时执行一次，
-- 重复 apply 不得把后来未保存的行翻回 true）。
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='strategies' AND column_name='in_library') THEN
        ALTER TABLE strategies ADD COLUMN in_library BOOL NOT NULL DEFAULT false;
        UPDATE strategies SET in_library = true;
    END IF;
END $$;

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
    weight_class  TEXT NOT NULL DEFAULT 'heavy',  -- R2 任务分级：light=小范围 / heavy=全市场
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
-- R2 多租户弹性调度（2026-10-03）：任务轻重分级列（老库自愈；应用启动亦幂等 ALTER）
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS weight_class TEXT NOT NULL DEFAULT 'heavy';
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_idem
    ON jobs (user_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
-- QRE-SAAS-D1D2（内测三级权限，2026-09-20）：密码登录临时方案 + 游客匿名提交
-- users 加密码哈希与层级；jobs/strategies 的 user_id 可空（游客不落 users 行，
-- 用 jobs.guest_key 归属，每日清理任务删除次日以前的游客记录）。
-- QRE-SAAS-ACCESS-HARDENING-001（2026-10-25）：guest_key 改由随机会话 Cookie 派生
-- （sha256("gsess:"+sid+salt)，HttpOnly/SameSite=Lax，缺失时应用自动签发），不再
-- 按 IP——同 Wi-Fi 游客结果互不可见；历史 sha256(IP+salt) 行在新会话首次创建任务
-- 时一次性迁移到该会话（幂等 UPDATE，无 schema 变更）。
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
    -- QRE-SAAS-RESULT-CONTRACT-001（P0-1B）：结果合同——版本 / data_until /
    -- 两种收益口径（日收益累乘曲线 vs 初始资金加权总收益）/ 验证状态。
    -- 新回传结果由 SaaS 接收层注入；历史行留空，按应用层显式例外表归类
    -- （58/66 verified、74 未验证），禁止按时间猜测。
    result_contract JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_results_user ON results (user_id, created_at DESC);
ALTER TABLE results ALTER COLUMN user_id DROP NOT NULL;  -- QRE-SAAS-D1D2：游客结果行
-- 老库幂等自愈（应用层亦懒 ALTER；ECS 上 results 表 owner 是 postgres，需 DBA apply）
ALTER TABLE results ADD COLUMN IF NOT EXISTS result_contract JSONB;

-- QRE-SAAS-ADMIN-E1E3（后台管理，2026-09-27）：
-- users 加管理角色与账号状态（role/status 取值由应用层校验，与 tier CHECK 同表风格
-- 不再加约束，避免历史库升级顺序坑）；workers 表落账 worker 心跳（claim/heartbeat 时
-- upsert，在线判定 = last_heartbeat_at 距今 < 3 分钟，应用层计算）。
ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user';
ALTER TABLE users ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';
CREATE TABLE IF NOT EXISTS workers (
    name              TEXT PRIMARY KEY,           -- worker_id
    capacity          INT,                        -- 并发能力上报（可空，预留）
    first_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- R3 切片1（2026-10-03）：worker 实时状态快照（槽位占用/内存水位 JSONB；
-- 旧 worker 不上报则为 NULL，管理台降级；应用层亦懒自愈 ALTER）
ALTER TABLE workers ADD COLUMN IF NOT EXISTS status JSONB;
ALTER TABLE workers ADD COLUMN IF NOT EXISTS status_at TIMESTAMPTZ;

-- R3 切片2（2026-10-04）：worker 期望资源配置（槽位数/内存闸门），管理台编辑、
-- status 响应回带 worker 比对；version 每次修改 +1（worker 侧据此识别新配置）。
CREATE TABLE IF NOT EXISTS worker_configs (
    worker_id                  TEXT PRIMARY KEY,
    desired_light_slots        INT,
    desired_heavy_slots        INT,
    desired_light_min_avail_mb INT,
    desired_heavy_min_avail_mb INT,
    version                    INT NOT NULL DEFAULT 1,
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                 TEXT
);

-- CR-2026-10-04 模块二（策略信号监控 + 站内信号中心）：
-- strategy_watches 每用户每策略一行（UNIQUE(strategy_id,user_id)）；
-- signal_events 唯一约束兜底扫描重跑幂等；users.signals_last_read_at 未读红点；
-- tier_policies 加 scan_enabled/max_watches（内测期默认全开/20）。
CREATE TABLE IF NOT EXISTS strategy_watches (
    id            BIGSERIAL PRIMARY KEY,
    strategy_id   BIGINT NOT NULL REFERENCES strategies(id),
    user_id       BIGINT NOT NULL REFERENCES users(id),
    scope_type    TEXT NOT NULL DEFAULT 'last_run_universe',
    scope_payload JSONB,
    enabled       BOOL NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_watches_strategy_user
    ON strategy_watches (strategy_id, user_id);
CREATE TABLE IF NOT EXISTS signal_events (
    id          BIGSERIAL PRIMARY KEY,
    watch_id    BIGINT NOT NULL REFERENCES strategy_watches(id),
    trade_date  DATE NOT NULL,
    ts_code     TEXT NOT NULL,
    signal_type TEXT NOT NULL,                -- entry / exit
    price       NUMERIC,                      -- 收盘参考价（T+1 参考，非成交价）
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_signals_unique
    ON signal_events (watch_id, trade_date, ts_code, signal_type);
ALTER TABLE users ADD COLUMN IF NOT EXISTS signals_last_read_at TIMESTAMPTZ;

-- QRE-SAAS-FEEDBACK-FACTOR-REQ（2026-09-27）：
-- ① factor_requests 补 formula/purpose（用户主动描述因子定义与用途，辅助人工审核）；
-- ② 新 feedback 表：内测意见反馈，仅登录用户可提交（游客不可，见 06 决策日志），
--    user_id 必填；page 记录提交来源页面路径，contact 为用户自愿留的联系方式。
ALTER TABLE factor_requests ADD COLUMN IF NOT EXISTS formula TEXT;
ALTER TABLE factor_requests ADD COLUMN IF NOT EXISTS purpose TEXT;
CREATE TABLE IF NOT EXISTS feedback (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(id),
    content    TEXT NOT NULL,                     -- 反馈/改进建议正文
    page       TEXT,                              -- 提交来源页面路径（可空）
    contact    TEXT,                              -- 用户自愿留的联系方式（可空）
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback (created_at DESC);

-- 经典策略公开白名单与增量日更：纳入权威 schema，避免新库依赖懒建表时序。
CREATE TABLE IF NOT EXISTS showcase (
    job_id     BIGINT PRIMARY KEY REFERENCES jobs(id),
    title      TEXT NOT NULL,
    subtitle   TEXT,
    sort_order INT NOT NULL DEFAULT 0,
    is_active  BOOL NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS showcase_daily (
    job_id       BIGINT NOT NULL REFERENCES jobs(id),
    trade_date   DATE NOT NULL,
    daily_return DOUBLE PRECISION NOT NULL,
    equity       DOUBLE PRECISION,
    n_positions  INT,
    n_entries    INT,
    n_exits      INT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (job_id, trade_date)
);

-- QRE-SAAS-READONLY-SHARE（P1，2026-10-26）：登录用户把本人已完成结果分享为
-- 可撤销的只读链接。token 用 secrets.token_urlsafe(32)，库中只存完整
-- SHA-256(token + salt) 哈希（token_hash 64 位十六进制）；无明文/前缀/guest_key/
-- last_used 字段，明文只在创建响应出现一次。job 删除由 CASCADE 清理孤儿分享
-- （游客每日清理 jobs 时自动生效，无需改清理逻辑）。
-- 应用层按 information_schema + 进程 guard 懒自愈建表；生产发布前必须由
-- postgres 幂等 apply 本文件，避免表 owner/权限问题（同 results.result_contract）。
CREATE TABLE IF NOT EXISTS share_links (
    id         BIGSERIAL PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,                -- 完整 sha256(token+salt)，不明文
    job_id     BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    owner_id   BIGINT NOT NULL REFERENCES users(id),
    expires_at TIMESTAMPTZ,                         -- NULL=永久；仅接受 1/7/30 天或 NULL
    revoked_at TIMESTAMPTZ,                         -- 撤销后立即失效
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_share_links_job ON share_links (job_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_share_links_owner ON share_links (owner_id, created_at DESC);
-- postgres 建表时应用角色不是 owner：CRUD 与 BIGSERIAL 序列权限都必须显式授予。
-- 角色不存在于本地临时库时跳过，保证测试库可重复 apply。
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aguhuice') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON share_links TO aguhuice;
        GRANT USAGE, SELECT ON SEQUENCE share_links_id_seq TO aguhuice;
    END IF;
END $$;

-- QRE-SAAS-NL-A2A3（2026-10-26）：持久限频与版本化编译缓存（两表均无序列）。
-- nl_rate_limits：PG 原子计数替代 /tmp 文件计数，跨 worker/重启可靠。
--   scope=guest_daily（游客每日 10 次，原 403/code=guest_nl_limit 不变）/
--   member_minute（会员每分钟 6 次防突发，每日仍不限，超限 429）；admin 不计数。
--   计数语义：单条 INSERT ... ON CONFLICT DO UPDATE ... WHERE hits < limit RETURNING，
--   已达上限不递增，多 worker/并发不突破。
CREATE TABLE IF NOT EXISTS nl_rate_limits (
    scope        TEXT NOT NULL,
    subject_hash TEXT NOT NULL,                  -- 不落原始 IP：guest=sha256(guest:ip:salt) 截断；member=sha256("nl:user:"+uid+salt) 截断
    window_start TIMESTAMPTZ NOT NULL,           -- guest_daily=当日零点；member_minute=当前 UTC 分钟
    hits         INT NOT NULL DEFAULT 0,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, subject_hash, window_start)
);
-- nl_compile_cache：相同输入复用已通过校验的编译结果，命中不调用 LLM 也不占配额。
--   cache_key = sha256(规范化描述 + model + 规范化 base_url + 完整 build_system_prompt
--   哈希 + NL_COMPILER_CACHE_VERSION)，prompt 天然覆盖文案与因子目录变化，后处理
--   变化须手动 bump 版本。只存 ok=true 的完整结果（result JSONB，不写 cache_hit）；
--   失败/not_configured 不缓存；不明文存任何 API key。
CREATE TABLE IF NOT EXISTS nl_compile_cache (
    cache_key     TEXT PRIMARY KEY,
    description   TEXT NOT NULL,                 -- 规范化后的描述（展示/排查用）
    result        JSONB NOT NULL,                -- ok=true 的完整编译结果
    model         TEXT NOT NULL,
    prompt_hash   TEXT NOT NULL,                 -- 完整 system prompt 的 sha256
    cache_version TEXT NOT NULL,                 -- 编译缓存版本（后处理变化手动 bump）
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_hit_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    hit_count     INT NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_nl_compile_cache_last_hit ON nl_compile_cache (last_hit_at);
-- 同 share_links 模式：postgres 建表时应用角色不是 owner，CRUD 必须显式授予；
-- 角色不存在于本地临时库时跳过，保证测试库可重复 apply。
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aguhuice') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON nl_rate_limits TO aguhuice;
        GRANT SELECT, INSERT, UPDATE, DELETE ON nl_compile_cache TO aguhuice;
    END IF;
END $$;

-- QRE-AUTH-MEMBERSHIP（A2，2026-09-27，18 号设计文档 §3）：
-- Authing 身份层接入。authing_id = OIDC sub（唯一，首登自动建档）；
-- avatar_url 同步 Authing 资料；member_since/member_expire_at 为会员制预留字段
-- （收费模式未定，只入库不生效）。email+password_hash 保留作降级登录通道。
ALTER TABLE users ADD COLUMN IF NOT EXISTS authing_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_authing ON users (authing_id) WHERE authing_id IS NOT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS member_since TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS member_expire_at TIMESTAMPTZ;

-- QRE-SAAS-TIER-POLICIES（N1b/N1c，2026-10-03）：角色权限参数化。
-- daily_full_limit=每日全量回测次数（0=不限）；max_codes=标的数上限（0=不限）；
-- max_days=回测区间天数上限（0=不限）。阶梯留空：新增付费等级只需插新行。
CREATE TABLE IF NOT EXISTS tier_policies (
    tier             TEXT PRIMARY KEY,
    daily_full_limit INT NOT NULL,
    max_codes        INT NOT NULL DEFAULT 0,
    max_days         INT NOT NULL DEFAULT 0,
    max_factor_fields INT NOT NULL DEFAULT 20,
    max_factor_tables INT NOT NULL DEFAULT 3,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 老库自愈（应用启动时也会幂等执行同样的 ALTER）
ALTER TABLE tier_policies ADD COLUMN IF NOT EXISTS max_factor_fields INT NOT NULL DEFAULT 20;
ALTER TABLE tier_policies ADD COLUMN IF NOT EXISTS max_factor_tables INT NOT NULL DEFAULT 3;
-- CR-2026-10-04 模块二：信号扫描开关与 watch 上限（须在 tier_policies 建表之后）
ALTER TABLE tier_policies ADD COLUMN IF NOT EXISTS scan_enabled BOOL NOT NULL DEFAULT true;
ALTER TABLE tier_policies ADD COLUMN IF NOT EXISTS max_watches INT NOT NULL DEFAULT 20;
INSERT INTO tier_policies (tier, daily_full_limit, max_codes, max_days, max_factor_fields, max_factor_tables) VALUES
    ('guest',  1, 10, 3657, 20, 3),
    ('member', 0, 0, 0, 20, 3),
    ('paid',   0, 0, 0, 20, 3)
ON CONFLICT (tier) DO NOTHING;

COMMIT;
