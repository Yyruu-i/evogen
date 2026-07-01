"""Sessions REST API — 会话列表 CRUD."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from backend.auth.dependencies import get_current_user
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
    limit: int = Query(200, ge=1, le=9999),
    offset: int = Query(0, ge=0),
    source: Optional[str] = None,
    user_id: str = Depends(get_current_user),
):
    """获取会话列表（按更新时间倒序）."""
    db = get_db()
    if source:
        rows = db.execute(
            "SELECT * FROM sessions WHERE user_id=? AND source=? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (user_id, source, limit, offset),
        ).fetchall()
        total = db.execute("SELECT COUNT(*) as cnt FROM sessions WHERE user_id=? AND source=?", (user_id, source,)).fetchone()["cnt"]
    else:
        rows = db.execute(
            "SELECT * FROM sessions WHERE user_id=? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        ).fetchall()
        total = db.execute("SELECT COUNT(*) as cnt FROM sessions WHERE user_id=?", (user_id,)).fetchone()["cnt"]

    return {
        "ok": True,
        "data": {
            "sessions": [_row_to_session(r) for r in rows],
            "total": total,
        },
    }


@router.get("/{session_id}")
async def get_session(session_id: str, user_id: str = Depends(get_current_user)):
    """获取单个会话详情."""
    db = get_db()
    row = db.execute("SELECT * FROM sessions WHERE id=? AND user_id=?", (session_id, user_id)).fetchone()
    if not row:
        return {"ok": False, "error": "Session not found"}
    return {"ok": True, "data": _row_to_session(row)}


@router.delete("/{session_id}")
async def delete_session(session_id: str, user_id: str = Depends(get_current_user)):
    """删除会话及其消息."""
    db = get_db()
    db.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
    db.execute("DELETE FROM sessions WHERE id=? AND user_id=?", (session_id, user_id))
    db.commit()
    return {"ok": True, "data": {"deleted_id": session_id}}


@router.get("/{session_id}/messages")
async def list_messages(
    session_id: str,
    limit: int = Query(500, ge=1, le=9999),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_current_user),
):
    """获取会话消息列表."""
    db = get_db()
    # Verify session belongs to user
    session = db.execute("SELECT 1 FROM sessions WHERE id=? AND user_id=?", (session_id, user_id)).fetchone()
    if not session:
        return {"ok": False, "error": "Session not found"}
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
async def search_sessions(query: str, limit: int = Query(20, ge=1, le=100), user_id: str = Depends(get_current_user)):
    """搜索会话（标题模糊匹配）."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM sessions WHERE user_id=? AND title LIKE ? ORDER BY updated_at DESC LIMIT ?",
        (user_id, f"%{query}%", limit),
    ).fetchall()
    return {
        "ok": True,
        "data": {
            "results": [_row_to_session(r) for r in rows],
        },
    }
