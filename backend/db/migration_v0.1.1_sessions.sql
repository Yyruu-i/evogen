-- v0.1.1: Add sessions + messages tables (idempotent)
-- For databases where v0.1.0_initial_schema was applied before these tables
-- were added to schema.sql, this migration creates them independently.

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
