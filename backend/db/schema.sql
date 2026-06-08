-- ═══════════════════════════════════════════════════
-- EvoGen Schema: MVP 新增表
-- ═══════════════════════════════════════════════════

-- ═══════════════════════════════════════════════════
-- 会话表（前后端联调必需）
-- ═══════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS sessions (
    id                      TEXT PRIMARY KEY,
    title                   TEXT NOT NULL DEFAULT '新对话',
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now')),
    source                  TEXT NOT NULL DEFAULT 'web',
    profile                 TEXT,
    metadata_json           TEXT,
    message_count           INTEGER NOT NULL DEFAULT 0,
    token_estimate          INTEGER NOT NULL DEFAULT 0,
    active_memory_snapshot_id TEXT,
    active_persona_id       TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id              TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role                    TEXT NOT NULL CHECK(role IN ('user','assistant','tool','system')),
    content                 TEXT NOT NULL,
    tool_calls_json         TEXT,
    tool_call_id            TEXT,
    timestamp               TEXT NOT NULL DEFAULT (datetime('now')),
    token_count             INTEGER
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

-- ═══════════════════════════════════════════════════
-- 🆕 MVP 新增表：进化记忆
-- ═══════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS memory_facts (
    id                      TEXT PRIMARY KEY,
    type                    TEXT NOT NULL CHECK(type IN ('preference','fact','procedure','relationship')),
    content                 TEXT NOT NULL,
    chroma_id               TEXT NOT NULL UNIQUE,
    importance              REAL NOT NULL DEFAULT 0.5 CHECK(importance >= 0 AND importance <= 1),
    weight                  REAL NOT NULL DEFAULT 1.0,
    layer                   TEXT NOT NULL DEFAULT 'working' CHECK(layer IN ('transient','working','core','archive')),
    source_session_id       TEXT,
    source_interaction_id   TEXT,
    privacy_level           TEXT NOT NULL DEFAULT 'private' CHECK(privacy_level IN ('public','private','sensitive')),
    tags_json               TEXT,
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now')),
    last_accessed_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_memory_layer ON memory_facts(layer);
CREATE INDEX IF NOT EXISTS idx_memory_type ON memory_facts(type);
CREATE INDEX IF NOT EXISTS idx_memory_importance ON memory_facts(importance DESC);
CREATE INDEX IF NOT EXISTS idx_memory_accessed ON memory_facts(last_accessed_at);
CREATE INDEX IF NOT EXISTS idx_memory_chroma ON memory_facts(chroma_id);

-- ═══════════════════════════════════════════════════
-- 🆕 MVP 新增表：经验记录
-- ═══════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS experience_trajectories (
    id                      TEXT PRIMARY KEY,
    session_id              TEXT NOT NULL,
    session_title           TEXT,
    turns_json              TEXT NOT NULL,
    outcome_json            TEXT NOT NULL,
    created_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_trajectory_session ON experience_trajectories(session_id);
CREATE INDEX IF NOT EXISTS idx_trajectory_created ON experience_trajectories(created_at DESC);

CREATE TABLE IF NOT EXISTS experience_feedback (
    id                      TEXT PRIMARY KEY,
    trajectory_id           TEXT NOT NULL REFERENCES experience_trajectories(id) ON DELETE CASCADE,
    rating                  TEXT NOT NULL CHECK(rating IN ('good','neutral','bad')),
    note                    TEXT,
    status                  TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','reviewed','applied','dismissed')),
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    reviewed_at             TEXT
);

CREATE INDEX IF NOT EXISTS idx_feedback_trajectory ON experience_feedback(trajectory_id);
CREATE INDEX IF NOT EXISTS idx_feedback_status ON experience_feedback(status);

-- ═══════════════════════════════════════════════════
-- 🆕 MVP 新增表：人格属性
-- ═══════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS persona_attributes (
    key                     TEXT PRIMARY KEY,
    value_json              TEXT NOT NULL,
    updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 预置12条默认值
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

-- ═══════════════════════════════════════════════════
-- 🆕 MVP 新增表：记忆快照关联（可选，用于调试）
-- ═══════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS memory_snapshots (
    id                      TEXT PRIMARY KEY,
    session_id              TEXT NOT NULL,
    fact_ids_json           TEXT NOT NULL,       -- JSON array of fact IDs
    generated_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_snapshot_session ON memory_snapshots(session_id);

-- ═══════════════════════════════════════════════════
-- 🆕 v0.2.0: 用户认证表
-- ═══════════════════════════════════════════════════

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
