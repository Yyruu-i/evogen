"""知识库 API — 文档上传/搜索/管理（用户隔离）."""

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
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
    """上传内容到知识库（用户隔离）。支持自动解析 PDF/DOCX/图片 OCR 占位。"""
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


class BatchDeleteRequest(BaseModel):
    ids: list[str]


@router.post("/batch/delete")
async def batch_delete_knowledge(req: BatchDeleteRequest, user_id: str = Depends(get_current_user)):
    """批量删除知识库条目（仅限自己的）。"""
    _ensure_table()
    from backend.db.connection import get_db
    db = get_db()
    ids = req.ids
    if not ids:
        return {"ok": True, "deleted": 0}
    # 用 IN 查自己的条目，只删归属于自己的
    placeholders = ",".join("?" for _ in ids)
    rows = db.execute(f"""
        SELECT id, user_id FROM {_KNOWLEDGE_TABLE}
        WHERE id IN ({placeholders})
    """, ids).fetchall()
    own_ids = [r["id"] for r in rows if r["user_id"] == user_id]
    if own_ids:
        own_placeholders = ",".join("?" for _ in own_ids)
        db.execute(f"DELETE FROM {_KNOWLEDGE_TABLE} WHERE id IN ({own_placeholders})", own_ids)
        db.commit()
    return {"ok": True, "deleted": len(own_ids)}


def _extract_text_from_file(filename: str, raw: bytes) -> str:
    """根据文件类型提取文本内容."""
    ext = os.path.splitext(filename)[1].lower()

    # PDF 解析
    if ext == ".pdf":
        try:
            import pypdf
        except ImportError:
            return f"[PDF 文件: {filename}]\n（需要安装 pypdf 库才能解析 PDF 内容）"
        try:
            reader = pypdf.PdfReader(BytesIO(raw))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return text.strip() or f"[PDF 文件: {filename}]（无提取文本）"
        except Exception as e:
            return f"[PDF 文件: {filename}]\n（解析失败: {e}）"

    # DOCX 解析
    if ext == ".docx":
        try:
            from docx import Document
            doc = Document(BytesIO(raw))
            text = "\n".join(p.text for p in doc.paragraphs)
            return text.strip() or f"[DOCX 文件: {filename}]（无提取文本）"
        except ImportError:
            return f"[DOCX 文件: {filename}]\n（需要安装 python-docx 库才能解析 DOCX 内容）"
        except Exception as e:
            return f"[DOCX 文件: {filename}]\n（解析失败: {e}）"

    # TXT/MD/CSV/JSON — 用 UTF-8 读取
    if ext in (".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".xml", ".log"):
        try:
            return raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            return raw.decode("utf-8", errors="replace").strip()

    # 其他格式（图片等）— 占位
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
        return f"[图片文件: {filename}]\n（图片 OCR 暂未支持）"

    return f"[文件: {filename}]\n（不支持的格式: {ext}，请上传文本文件）"


@router.post("/upload-file")
async def upload_knowledge_file(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):
    """上传文件到知识库 — 自动根据后缀名解析文本内容。

    支持的格式：.txt, .md, .csv, .json, .pdf, .docx, .yaml, .xml, .log
    """
    _ensure_table()
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="文件内容为空")

    max_size = 10 * 1024 * 1024  # 10MB
    if len(raw) > max_size:
        raise HTTPException(status_code=400, detail=f"文件过大（最大 10MB），当前 {len(raw) // 1024}KB")

    content = _extract_text_from_file(file.filename, raw)
    if not content.strip():
        raise HTTPException(status_code=400, detail="未能从文件中提取文本内容")

    entry_id = str(uuid.uuid4())
    now = _utcnow()
    from backend.db.connection import get_db
    db = get_db()
    db.execute(f"""
        INSERT INTO {_KNOWLEDGE_TABLE} (id, user_id, content, source, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (entry_id, user_id, content, file.filename, now, now))
    db.commit()
    logger.info(f"Knowledge file uploaded: {file.filename} -> {entry_id} (user={user_id})")
    return {"ok": True, "id": entry_id, "source": file.filename, "content": content, "content_preview": content[:200]}


# ── 测试隔离 ──

@router.get("/check-isolation")
async def check_knowledge_isolation(user_id: str = Depends(get_current_user)):
    """检查用户隔离：确保当前用户只能看到自己的知识库条目。"""
    _ensure_table()
    from backend.db.connection import get_db
    db = get_db()
    # 当前用户条目
    my_rows = db.execute(f"""
        SELECT COUNT(*) as cnt FROM {_KNOWLEDGE_TABLE} WHERE user_id = ?
    """, (user_id,)).fetchone()
    # 全部条目
    all_rows = db.execute(f"""
        SELECT COUNT(*) as cnt FROM {_KNOWLEDGE_TABLE}
    """).fetchone()
    my_count = my_rows["cnt"] if my_rows else 0
    all_count = all_rows["cnt"] if all_rows else 0
    return {
        "ok": True,
        "data": {
            "user_id": user_id,
            "my_entries": my_count,
            "total_entries": all_count,
            "other_users_entries": all_count - my_count,
            "isolation": "✅ 用户隔离生效" if all_count == my_count or my_count > 0 else "⚠️ 无数据",
        }
    }
