"""Artifact / 制品 API — 对话产出的代码、图像、文档管理."""

import logging
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
            "title": "architecture.png",
            "content": "data:image/svg+xml;base64,",
            "language": None,
            "session_id": None,
            "created_at": now,
        },
    ]


_seed_demo()


# ── Routes ──────────────────────────────────────────────────────

@router.get("")
async def list_artifacts(
    type: str | None = Query(None, description="Filter by type: code, image, doc"),
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
