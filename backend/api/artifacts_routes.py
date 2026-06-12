"""Artifact / 制品 API — 对话产出的代码、图像、文档管理.
持久化到 SQLite artifacts 表，重启后数据不丢失。
"""

import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from backend.auth.dependencies import get_current_user
from backend.db.connection import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


# ── Pydantic models ─────────────────────────────────────────────

class ArtifactOut(BaseModel):
    id: str
    type: str  # code | image | doc
    title: str
    content: str
    language: str | None = None
    session_id: str | None = None
    created_at: str


class ArtifactListResponse(BaseModel):
    artifacts: list[ArtifactOut]
    total: int


# ── SQLite-backed CRUD ──────────────────────────────────────────


def _next_artifact_id() -> str:
    """生成唯一制品 ID."""
    return str(uuid.uuid4())[:12]


def _artifact_title_from_code(code: str, language: str) -> str:
    """从代码内容生成合理的制品标题."""
    ext_map = {
        "python": ".py", "py": ".py",
        "javascript": ".js", "js": ".js",
        "typescript": ".ts", "ts": ".ts",
        "html": ".html",
        "css": ".css",
        "json": ".json",
        "yaml": ".yaml", "yml": ".yaml",
        "sql": ".sql",
        "bash": ".sh", "sh": ".sh",
        "markdown": ".md", "md": ".md",
        "rust": ".rs", "rs": ".rs",
        "go": ".go",
        "java": ".java",
        "cpp": ".cpp", "c++": ".cpp",
        "c": ".c",
    }
    ext = ext_map.get(language, f".{language}" if language else ".txt")
    first_line = code.split("\n", 1)[0].strip()
    if first_line.startswith(("# ", "// ", "/* ")):
        name = first_line.lstrip("#/ *").strip()[:40]
    else:
        name = "code"
    safe_name = re.sub(r"[^\w\u4e00-\u9fff\-_]", "_", name)[:30]
    return f"{safe_name}{ext}"


def store_artifact(
    artifact_type: str,
    title: str,
    content: str,
    *,
    language: str | None = None,
    session_id: str | None = None,
    user_id: str = "default",
) -> str:
    """写入制品到 SQLite artifacts 表，返回 artifact id."""
    now = datetime.now(timezone.utc).isoformat()
    artifact_id = _next_artifact_id()
    db = get_db()
    db.execute(
        """INSERT INTO artifacts (id, user_id, type, title, content, language, session_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (artifact_id, user_id, artifact_type, title, content, language, session_id, now),
    )
    db.commit()
    logger.info(
        "Artifact stored: %s type=%s session=%s title=%s user=%s",
        artifact_id, artifact_type, session_id, title, user_id,
    )
    return artifact_id


def extract_artifacts_from_text(text: str, session_id: str, user_id: str = "default") -> int:
    """从文本中自动提取制品（代码块、文档、表格）并写入 SQLite.

    返回提取的制品数量.
    """
    count = 0

    # ── 1. 提取围栏代码块: ```language\n...\n``` ──
    code_block_re = re.compile(
        r"```(\w+)?\s*\n(.*?)```",
        re.DOTALL,
    )
    for match in code_block_re.finditer(text):
        lang = (match.group(1) or "").strip().lower()
        code = match.group(2).strip()
        if len(code) < 10:
            continue
        title = _artifact_title_from_code(code, lang)
        store_artifact(
            "code", title, code,
            language=lang or "text",
            session_id=session_id,
            user_id=user_id,
        )
        count += 1

    # ── 2. 提取 Markdown 文档段：有 # 或 ## 标题且有实质内容 ──
    doc_section_re = re.compile(
        r"(?:^|\n)(#{1,3})\s+(.+?)\n((?:(?!#{1,3}\s).+\n?)+)",
        re.MULTILINE,
    )
    for match in doc_section_re.finditer(text):
        title = match.group(2).strip()
        body_text = match.group(3).strip()
        if len(body_text) < 60 or "```" in body_text:
            continue
        store_artifact(
            "doc", title, body_text,
            language="markdown",
            session_id=session_id,
            user_id=user_id,
        )
        count += 1

    # ── 3. 提取表格（markdown table）──
    table_re = re.compile(
        r"(\|[^\n]+\|\s*\n\|[\s\-:|]+\|\s*\n(?:\|[^\n]+\|\s*\n?)+)",
    )
    for match in table_re.finditer(text):
        table_text = match.group(1).strip()
        if len(table_text) < 30:
            continue
        before = text[: match.start()].rsplit("\n", 2)
        table_title = "数据表"
        for line in reversed(before[-3:]):
            line = line.strip()
            if line.startswith("#"):
                table_title = line.lstrip("#").strip()
                break
            elif line and not line.startswith("|") and len(line) < 60:
                table_title = line.strip()
                break
        store_artifact(
            "doc", table_title, table_text,
            language="markdown",
            session_id=session_id,
            user_id=user_id,
        )
        count += 1

    return count


def _row_to_dict(row) -> dict:
    """将 SQLite Row 转为字典."""
    return {
        "id": row["id"],
        "type": row["type"],
        "title": row["title"],
        "content": row["content"],
        "language": row["language"],
        "session_id": row["session_id"],
        "user_id": row["user_id"],
        "created_at": row["created_at"],
    }


def _seed_demo(user_id: str = "default"):
    """种子数据：模拟对话产出的制品（仅当用户无制品时写入）."""
    db = get_db()
    count = db.execute(
        "SELECT COUNT(*) as cnt FROM artifacts WHERE user_id = ?", (user_id,)
    ).fetchone()
    if count and count["cnt"] > 0:
        return
    now = datetime.now(timezone.utc).isoformat()
    demos = [
        ("a1", "code", "app.py", '"""FastAPI 应用入口."""\n\nfrom fastapi import FastAPI\nfrom fastapi.middleware.cors import CORSMiddleware\n\napp = FastAPI(title="EvoGen API")\n\napp.add_middleware(\n    CORSMiddleware,\n    allow_origins=["*"],\n    allow_methods=["*"],\n    allow_headers=["*"],\n)\n\n@app.get("/health")\nasync def health():\n    return {"status": "ok", "version": "1.0.0"}\n\n@app.get("/api/v1/stats")\nasync def stats():\n    return {"users": 42, "sessions": 128}', "python", None),
        ("a2", "code", "config.ts", 'const config = {\n  api: {\n    baseUrl: "/api/v1",\n    timeout: 30000,\n    retry: 3,\n  },\n  features: {\n    chat: true,\n    memory: true,\n    artifacts: true,\n    darkMode: true,\n  },\n  limits: {\n    maxTokens: 4096,\n    maxFileSize: 10 * 1024 * 1024,\n    rateLimit: 100,\n  },\n} as const;\n\nexport default config;', "typescript", None),
        ("a3", "doc", "架构设计.md", "# EvoGen 系统架构\n\n## 核心模块\n\n- **Agent 引擎**：LLM 驱动的任务执行\n- **记忆系统**：三层记忆（瞬态/工作/核心）\n- **经验闭环**：轨迹记录 + 反馈优化\n- **人格引擎**：动态属性 + 偏好学习\n\n## 数据流\n\n```\n用户输入 → GateWay → Agent Loop → LLM\n                ↓           ↓\n            Memory      Experience\n```\n\n## 部署拓扑\n\n- 前端：Vite + React SPA\n- 后端：FastAPI + SQLite\n- LLM：DeepSeek API", "markdown", None),
        ("a4", "image", "architecture.svg", "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='200' viewBox='0 0 400 200'%3E%3Crect width='400' height='200' fill='%231a1a2e'/%3E%3Ccircle cx='80' cy='100' r='40' fill='%23ff6b6b' opacity='0.8'/%3E%3Crect x='150' y='60' width='120' height='80' rx='8' fill='%23b8c0ff' opacity='0.7'/%3E%3Cpolygon points='330,60 380,100 330,140' fill='%2351cf66' opacity='0.6'/%3E%3Ctext x='200' y='180' text-anchor='middle' fill='%23888' font-size='12'%3EEvoGen Architecture%3C/text%3E%3C/svg%3E", None, None),
    ]
    for a_id, a_type, a_title, a_content, a_lang, a_session in demos:
        db.execute(
            """INSERT OR IGNORE INTO artifacts (id, user_id, type, title, content, language, session_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (a_id, user_id, a_type, a_title, a_content, a_lang, a_session, now),
        )
    db.commit()
    logger.info("Seeded %d demo artifacts for user=%s", len(demos), user_id)


# ── Routes ──────────────────────────────────────────────────────

@router.get("")
async def list_artifacts(
    type: str = Query("", description="Filter by type: code, image, doc"),
    session_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_current_user),
):
    """列出所有制品（SQLite 持久化）."""
    db = get_db()
    params = [user_id]
    where = ["user_id = ?"]

    if type:
        where.append("type = ?")
        params.append(type)
    if session_id:
        where.append("session_id = ?")
        params.append(session_id)

    where_clause = " AND ".join(where)
    count_row = db.execute(
        f"SELECT COUNT(*) as cnt FROM artifacts WHERE {where_clause}", params
    ).fetchone()
    total = count_row["cnt"] if count_row else 0

    rows = db.execute(
        f"SELECT * FROM artifacts WHERE {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()

    return {
        "ok": True,
        "data": {
            "artifacts": [
                ArtifactOut(
                    id=r["id"],
                    type=r["type"],
                    title=r["title"],
                    content=r["content"],
                    language=r["language"],
                    session_id=r["session_id"],
                    created_at=r["created_at"],
                )
                for r in rows
            ],
            "total": total,
        },
    }


@router.get("/{artifact_id}")
async def get_artifact(artifact_id: str, user_id: str = Depends(get_current_user)):
    """获取单个制品详情."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM artifacts WHERE id = ? AND user_id = ?",
        (artifact_id, user_id),
    ).fetchone()
    if not row:
        return {"ok": False, "error": "Artifact not found"}
    return {
        "ok": True,
        "data": ArtifactOut(
            id=row["id"],
            type=row["type"],
            title=row["title"],
            content=row["content"],
            language=row["language"],
            session_id=row["session_id"],
            created_at=row["created_at"],
        ),
    }


@router.delete("/{artifact_id}")
async def delete_artifact(artifact_id: str, user_id: str = Depends(get_current_user)):
    """删除制品."""
    db = get_db()
    row = db.execute(
        "SELECT id, type, title FROM artifacts WHERE id = ? AND user_id = ?",
        (artifact_id, user_id),
    ).fetchone()
    if not row:
        return {"ok": False, "error": "Artifact not found"}
    db.execute("DELETE FROM artifacts WHERE id = ? AND user_id = ?", (artifact_id, user_id))
    db.commit()
    logger.info("Artifact deleted: %s type=%s title=%s", artifact_id, row["type"], row["title"])
    return {"ok": True, "data": {"deleted": artifact_id}}
