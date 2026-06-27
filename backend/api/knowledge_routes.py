"""知识库 API — 文档上传/搜索/管理（用户隔离）."""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# ── 数据库存储（用户隔离） ──

_KNOWLEDGE_TABLE = "knowledge_entries"


def _ensure_table():
    """确保知识库表存在."""
    from backend.db.connection import get_db
    db = get_db()
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS {_KNOWLEDGE_TABLE} (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            content TEXT NOT NULL,
            source TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    db.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_knowledge_user
        ON {_KNOWLEDGE_TABLE}(user_id)
    """)
    db.commit()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Pydantic models ──

class UploadRequest(BaseModel):
    content: str
    source: str = ""


class SearchRequest(BaseModel):
    query: str
    limit: int = 20


class DeleteRequest(BaseModel):
    id: str


# ── Routes ──

@router.get("")
async def list_knowledge(user_id: str = Depends(get_current_user)):
    """列出当前用户的知识库条目."""
    _ensure_table()
    from backend.db.connection import get_db
    db = get_db()
    rows = db.execute(f"""
        SELECT id, content, source, created_at
        FROM {_KNOWLEDGE_TABLE}
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 100
    """, (user_id,)).fetchall()
    entries = [dict(r) for r in rows]
    return {"entries": entries, "total": len(entries)}


@router.post("/search")
async def search_knowledge(req: SearchRequest, user_id: str = Depends(get_current_user)):
    """搜索当前用户的知识库（基于关键词匹配）。"""
    _ensure_table()
    query = req.query.strip()
    if not query:
        return {"results": []}
    from backend.db.connection import get_db
    db = get_db()
    # SQLite FTS5 全文搜索（先用 LIKE 兜底）
    like_pattern = f"%{query}%"
    rows = db.execute(f"""
        SELECT id, content, source, created_at
        FROM {_KNOWLEDGE_TABLE}
        WHERE user_id = ? AND (content LIKE ? OR source LIKE ?)
        ORDER BY created_at DESC
        LIMIT ?
    """, (user_id, like_pattern, like_pattern, req.limit)).fetchall()
    results = [dict(r) for r in rows]
    return {"results": results}


@router.post("/upload")
async def upload_knowledge(req: UploadRequest, user_id: str = Depends(get_current_user)):
    """上传内容到知识库（用户隔离）。"""
    _ensure_table()
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="内容不能为空")
    entry_id = str(uuid.uuid4())
    now = _utcnow()
    from backend.db.connection import get_db
    db = get_db()
    db.execute(f"""
        INSERT INTO {_KNOWLEDGE_TABLE} (id, user_id, content, source, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (entry_id, user_id, req.content.strip(), req.source, now, now))
    db.commit()
    logger.info(f"Knowledge entry created: {entry_id} (user={user_id})")
    return {"ok": True, "id": entry_id}


@router.post("/delete")
async def delete_knowledge(req: DeleteRequest, user_id: str = Depends(get_current_user)):
    """删除知识库条目（仅限自己的）。"""
    _ensure_table()
    from backend.db.connection import get_db
    db = get_db()
    # 验证归属（用户隔离）
    row = db.execute(f"""
        SELECT user_id FROM {_KNOWLEDGE_TABLE}
        WHERE id = ?
    """, (req.id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="条目不存在")
    if row["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="无权删除他人条目")
    db.execute(f"DELETE FROM {_KNOWLEDGE_TABLE} WHERE id = ?", (req.id,))
    db.commit()
    return {"ok": True}
