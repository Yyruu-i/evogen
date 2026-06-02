"""Artifact / 制品 API — 对话产出的代码、图像、文档管理."""

import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from pydantic import BaseModel

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


# ── In-memory store (later → SQLite) ────────────────────────────

_artifacts: list[dict] = []


def _next_artifact_id() -> str:
    """生成唯一制品 ID."""
    return str(uuid.uuid4())[:12]


def store_artifact(
    artifact_type: str,
    title: str,
    content: str,
    *,
    language: str | None = None,
    session_id: str | None = None,
) -> str:
    """写入制品到内存存储，返回 artifact id.

    同时广播到前端（如果 WebSocket 已连接）。
    """
    now = datetime.now(timezone.utc).isoformat()
    artifact_id = _next_artifact_id()
    entry = {
        "id": artifact_id,
        "type": artifact_type,
        "title": title,
        "content": content,
        "language": language,
        "session_id": session_id,
        "created_at": now,
    }
    _artifacts.append(entry)
    logger.info(
        "Artifact stored: %s type=%s session=%s title=%s",
        artifact_id, artifact_type, session_id, title,
    )
    return artifact_id


def extract_artifacts_from_text(text: str, session_id: str) -> int:
    """从文本中自动提取制品（代码块、文档、表格）并写入存储.

    返回提取的制品数量.
    """
    count = 0

    # ── 1. 提取围栏代码块: ```language\\n...\\n``` ──
    code_block_re = re.compile(
        r"```(\w+)?\s*\n(.*?)```",
        re.DOTALL,
    )
    for match in code_block_re.finditer(text):
        lang = (match.group(1) or "").strip().lower()
        code = match.group(2).strip()
        if len(code) < 10:  # 跳过太短的
            continue
        title = _artifact_title_from_code(code, lang)
        store_artifact(
            "code", title, code,
            language=lang or "text",
            session_id=session_id,
        )
        count += 1

    # ── 2. 提取 Markdown 文档段：有 # 或 ## 标题且有实质内容 ──
    doc_section_re = re.compile(
        r"(?:^|\n)(#{1,3})\s+(.+?)\n((?:(?!#{1,3}\s).+\n?)+)",
        re.MULTILINE,
    )
    for match in doc_section_re.finditer(text):
        title = match.group(2).strip()
        body = match.group(3).strip()
        # 跳过太短的、或已经被代码块捕获的
        if len(body) < 60 or "```" in body:
            continue
        store_artifact(
            "doc", title, body,
            language="markdown",
            session_id=session_id,
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
        # 尝试从表格前面找标题
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
        )
        count += 1

    return count


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
    # 尝试从第一行注释提取名称
    first_line = code.split("\n", 1)[0].strip()
    if first_line.startswith(("# ", "// ", "/* ")):
        name = first_line.lstrip("#/ *").strip()[:40]
    else:
        name = "code"
    # 清理文件名
    safe_name = re.sub(r"[^\w\u4e00-\u9fff\-_]", "_", name)[:30]
    return f"{safe_name}{ext}"


def _seed_demo():
    """种子数据：模拟对话产出的制品."""
    global _artifacts
    if _artifacts:
        return
    now = datetime.now(timezone.utc).isoformat()
    _artifacts = [
        {
            "id": "a1",
            "type": "code",
            "title": "app.py",
            "content": '"""FastAPI 应用入口."""\n\nfrom fastapi import FastAPI\nfrom fastapi.middleware.cors import CORSMiddleware\n\napp = FastAPI(title="EvoGen API")\n\napp.add_middleware(\n    CORSMiddleware,\n    allow_origins=["*"],\n    allow_methods=["*"],\n    allow_headers=["*"],\n)\n\n@app.get("/health")\nasync def health():\n    return {"status": "ok", "version": "1.0.0"}\n\n@app.get("/api/v1/stats")\nasync def stats():\n    return {"users": 42, "sessions": 128}',
            "language": "python",
            "session_id": None,
            "created_at": now,
        },
        {
            "id": "a2",
            "type": "code",
            "title": "config.ts",
            "content": 'const config = {\n  api: {\n    baseUrl: "/api/v1",\n    timeout: 30000,\n    retry: 3,\n  },\n  features: {\n    chat: true,\n    memory: true,\n    artifacts: true,\n    darkMode: true,\n  },\n  limits: {\n    maxTokens: 4096,\n    maxFileSize: 10 * 1024 * 1024, // 10MB\n    rateLimit: 100, // requests/min\n  },\n} as const;\n\nexport default config;',
            "language": "typescript",
            "session_id": None,
            "created_at": now,
        },
        {
            "id": "a3",
            "type": "doc",
            "title": "架构设计.md",
            "content": "# EvoGen 系统架构\n\n## 核心模块\n\n- **Agent 引擎**：LLM 驱动的任务执行\n- **记忆系统**：三层记忆（瞬态/工作/核心）\n- **经验闭环**：轨迹记录 + 反馈优化\n- **人格引擎**：动态属性 + 偏好学习\n\n## 数据流\n\n```\n用户输入 → GateWay → Agent Loop → LLM\n                ↓           ↓\n            Memory      Experience\n```\n\n## 部署拓扑\n\n- 前端：Vite + React SPA\n- 后端：FastAPI + SQLite\n- LLM：DeepSeek API",
            "language": "markdown",
            "session_id": None,
            "created_at": now,
        },
        {
            "id": "a4",
            "type": "image",
            "title": "architecture.svg",
            "content": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='200' viewBox='0 0 400 200'%3E%3Crect width='400' height='200' fill='%231a1a2e'/%3E%3Ccircle cx='80' cy='100' r='40' fill='%23ff6b6b' opacity='0.8'/%3E%3Crect x='150' y='60' width='120' height='80' rx='8' fill='%23b8c0ff' opacity='0.7'/%3E%3Cpolygon points='330,60 380,100 330,140' fill='%2351cf66' opacity='0.6'/%3E%3Ctext x='200' y='180' text-anchor='middle' fill='%23888' font-size='12'%3EEvoGen Architecture%3C/text%3E%3C/svg%3E",
            "language": None,
            "session_id": None,
            "created_at": now,
        },
    ]


_seed_demo()


# ── Routes ──────────────────────────────────────────────────────

@router.get("")
async def list_artifacts(
    type: str = Query("code", description="Filter by type: code, image, doc"),
    session_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """列出所有制品."""
    filtered = _artifacts
    if type:
        filtered = [a for a in filtered if a["type"] == type]
    if session_id:
        filtered = [a for a in filtered if a.get("session_id") == session_id]

    total = len(filtered)
    page = filtered[offset : offset + limit]

    return {
        "ok": True,
        "data": {
            "artifacts": [
                ArtifactOut(
                    id=a["id"],
                    type=a["type"],
                    title=a["title"],
                    content=a["content"],
                    language=a.get("language"),
                    session_id=a.get("session_id"),
                    created_at=a["created_at"],
                )
                for a in page
            ],
            "total": total,
        },
    }


@router.get("/{artifact_id}")
async def get_artifact(artifact_id: str):
    """获取单个制品详情."""
    for a in _artifacts:
        if a["id"] == artifact_id:
            return {
                "ok": True,
                "data": ArtifactOut(
                    id=a["id"],
                    type=a["type"],
                    title=a["title"],
                    content=a["content"],
                    language=a.get("language"),
                    session_id=a.get("session_id"),
                    created_at=a["created_at"],
                ),
            }
    return {"ok": False, "error": "Artifact not found"}
