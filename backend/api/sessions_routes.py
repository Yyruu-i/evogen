"""Sessions REST API — 会话列表 CRUD."""

import logging
from typing import Optional

from fastapi import APIRouter, Query

from backend.db.connection import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _row_to_session(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "source": row["source"],
        "profile": row["profile"],
        "metadata": row["metadata_json"],
        "message_count": row["message_count"],
        "token_estimate": row["token_estimate"],
        "active_memory_snapshot_id": row["active_memory_snapshot_id"],
        "active_persona_id": row["active_persona_id"],
    }


def _row_to_message(row) -> dict:
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "role": row["role"],
        "content": row["content"],
        "tool_calls_json": row["tool_calls_json"],
        "tool_call_id": row["tool_call_id"],
        "timestamp": row["timestamp"],
        "token_count": row["token_count"],
    }


@router.get("")
async def list_sessions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    source: Optional[str] = None,
):
    """获取会话列表（按更新时间倒序）."""
    db = get_db()
    if source:
        rows = db.execute(
            "SELECT * FROM sessions WHERE source=? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (source, limit, offset),
        ).fetchall()
        total = db.execute("SELECT COUNT(*) as cnt FROM sessions WHERE source=?", (source,)).fetchone()["cnt"]
    else:
        rows = db.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        total = db.execute("SELECT COUNT(*) as cnt FROM sessions").fetchone()["cnt"]

    return {
        "ok": True,
        "data": {
            "sessions": [_row_to_session(r) for r in rows],
            "total": total,
        },
    }


@router.get("/{session_id}")
async def get_session(session_id: str):
    """获取单个会话详情."""
    db = get_db()
    row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not row:
        return {"ok": False, "error": "Session not found"}
    return {"ok": True, "data": _row_to_session(row)}


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """删除会话及其消息."""
    db = get_db()
    db.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
    db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
    db.commit()
    return {"ok": True, "data": {"deleted_id": session_id}}


@router.get("/{session_id}/messages")
async def list_messages(
    session_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """获取会话消息列表."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM messages WHERE session_id=? ORDER BY id ASC LIMIT ? OFFSET ?",
        (session_id, limit, offset),
    ).fetchall()
    return {
        "ok": True,
        "data": {
            "messages": [_row_to_message(r) for r in rows],
        },
    }


@router.post("/search")
async def search_sessions(query: str, limit: int = Query(20, ge=1, le=100)):
    """搜索会话（标题模糊匹配）."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM sessions WHERE title LIKE ? ORDER BY updated_at DESC LIMIT ?",
        (f"%{query}%", limit),
    ).fetchall()
    return {
        "ok": True,
        "data": {
            "results": [_row_to_session(r) for r in rows],
        },
    }
