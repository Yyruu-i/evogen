"""EvoGen API Module - REST API 路由."""

from fastapi import APIRouter

from backend.api.memory_routes import router as memory_router
from backend.api.experience_routes import router as experience_router
from backend.api.persona_routes import router as persona_router
from backend.api.chat_routes import router as chat_router
from backend.api.skills_routes import router as skills_router
from backend.api.sessions_routes import router as sessions_router
from backend.api.auth_routes import router as auth_router

from backend.api.artifacts_routes import router as artifacts_router
from backend.api.tools_routes import router as tools_router
from backend.api.resource_routes import router as resource_router
from backend.api.system_routes import router as system_router
from backend.api.browser_routes import router as browser_router
from backend.api.knowledge_routes import router as knowledge_router
from backend.api.report_routes import router as report_router
from backend.api.expert_routes import router as expert_router

router = APIRouter(prefix="/api/v1")

# 注册子路由
router.include_router(chat_router)
router.include_router(sessions_router)
router.include_router(memory_router)
router.include_router(experience_router)
router.include_router(persona_router)
router.include_router(skills_router)
router.include_router(artifacts_router)
router.include_router(tools_router)
router.include_router(resource_router)
router.include_router(system_router)
router.include_router(browser_router)
router.include_router(auth_router)
router.include_router(knowledge_router)
router.include_router(report_router)
router.include_router(expert_router)

__all__ = ["router"]
