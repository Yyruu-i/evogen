"""EvoGen FastAPI 入口."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import router as api_router
from backend.api.auth_routes import router as auth_router
from backend.api.ws_routes import router as ws_router
from backend.config import config
from backend.db import init_db

# 配置日志
logging.basicConfig(
    level=getattr(logging, config.log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理."""
    # 启动时
    logger.info("🚀 EvoGen Backend starting...")
    logger.info(f"  Database: {config.db_path}")
    logger.info(f"  Chroma:   {config.chroma_persist_dir}")
    logger.info(f"  LLM:      {config.llm_provider}/{config.llm_model}")

    # 初始化数据库
    try:
        db = init_db()
        logger.info("  Database: ✅ migration complete")
    except Exception as e:
        logger.error(f"  Database: ❌ migration failed: {e}")
        raise

    yield

    # 关闭时
    logger.info("👋 EvoGen Backend shutting down...")


app = FastAPI(
    title="EvoGen API",
    description="进化型 Agent 后端服务",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(api_router)
app.include_router(auth_router, prefix="/api/v1")  # auth 路由前缀
app.include_router(ws_router, prefix="/api/v1")  # WebSocket 路由前缀


@app.get("/health")
async def health_check():
    """健康检查端点."""
    return {
        "status": "ok",
        "version": "0.2.0",
        "llm": f"{config.llm_provider}/{config.llm_model}",
        "embedding": f"{config.embedding_model}({config.embedding_dim}d)",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=config.api_host,
        port=config.api_port,
        reload=config.api_reload,
    )
