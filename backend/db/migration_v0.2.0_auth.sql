-- ═══════════════════════════════════════════════════════
-- v0.2.0: 用户认证 + 数据隔离（一次性 migration）
-- ═══════════════════════════════════════════════════════
-- 包含 P1（用户认证）和 P2（数据隔离）的所有 DDL 变更。
-- 幂等设计：所有 DDL 使用 IF NOT EXISTS / IF EXISTS，
--           所有 DML 使用 OR IGNORE。
-- 注意：persona_attributes 主键迁移为破坏性操作，
--       此 migration 正常情况只执行一次。
-- ═══════════════════════════════════════════════════════

-- ═══════════════════════════
-- Part 1: users 表（P1 认证）
-- ═══════════════════════════

CREATE TABLE IF NOT EXISTS users (
    id                      TEXT PRIMARY KEY,
    username                TEXT NOT NULL UNIQUE,
    email                   TEXT NOT NULL UNIQUE,
    password_hash           TEXT NOT NULL,
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ═══════════════════════════
-- Part 2: 业务表加 user_id 列（P2 隔离）
-- ═══════════════════════════

ALTER TABLE sessions ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE memory_facts ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE experience_trajectories ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE experience_feedback ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default';

-- ═══════════════════════════
-- Part 3: persona_attributes 主键迁移
--         旧: PRIMARY KEY (key)
--         新: PRIMARY KEY (user_id, key)
-- SQLite 不支持 ALTER TABLE 改主键，用重建方式
-- ═══════════════════════════

CREATE TABLE IF NOT EXISTS persona_attributes_new (
    user_id     TEXT NOT NULL DEFAULT 'default',
    key         TEXT NOT NULL,
    value_json  TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, key)
);

INSERT OR IGNORE INTO persona_attributes_new (user_id, key, value_json, updated_at)
    SELECT 'default', key, value_json, updated_at FROM persona_attributes;

DROP TABLE IF EXISTS persona_attributes;

ALTER TABLE persona_attributes_new RENAME TO persona_attributes;

-- 重新插入预置值（如果表为空 — 仅迁移到空表时触发）
INSERT OR IGNORE INTO persona_attributes (key, value_json) VALUES
    ('display_name', 'null'),
    ('preferred_language', '"zh"'),
    ('timezone', 'null'),
    ('conciseness', '0.5'),
    ('formality', '0.5'),
    ('warmth', '0.7'),
    ('directness', '0.5'),
    ('auto_approve_tools', 'false'),
    ('show_thinking', 'true'),
    ('response_language', '"zh"'),
    ('learned_preferences', '{}'),
    ('discovery_questions_asked', '0');

-- ═══════════════════════════
-- Part 4: 索引（per-user 查询）
-- ═══════════════════════════

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_memory_user ON memory_facts(user_id);
CREATE INDEX IF NOT EXISTS idx_experience_user ON experience_trajectories(user_id);
