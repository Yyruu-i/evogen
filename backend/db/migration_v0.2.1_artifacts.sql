-- v0.2.1: Drop old artifacts table and recreate with correct column names
DROP TABLE IF EXISTS artifacts;

CREATE TABLE IF NOT EXISTS artifacts (
    id                      TEXT PRIMARY KEY,
    user_id                 TEXT NOT NULL,
    type                    TEXT NOT NULL CHECK(type IN ('code','image','doc')),
    title                   TEXT NOT NULL,
    content                 TEXT NOT NULL,
    language                TEXT,
    session_id              TEXT,
    created_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_artifacts_user ON artifacts(user_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_type ON artifacts(type);
CREATE INDEX IF NOT EXISTS idx_artifacts_session ON artifacts(session_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_created ON artifacts(created_at DESC);
