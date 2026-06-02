"""记忆管理 REST API 端点（对齐设计文档第1335-1362行）.

统一响应格式：{"ok": true, "data": {...}} 或 {"ok": false, "error": "..."}
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.memory.engine import EvoMemoryEngine, MemoryFact, MemoryStats, get_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


# ════════════════════════════════════════════════════════
# 辅助：获取引擎实例
# ════════════════════════════════════════════════════════


def _get_engine() -> EvoMemoryEngine:
    """获取全局记忆引擎（测试时可 monkeypatch）."""
    return get_engine()


# ════════════════════════════════════════════════════════
# 事实序列化
# ════════════════════════════════════════════════════════


def _fact_to_dict(fact: MemoryFact) -> dict:
    """将 MemoryFact 序列化为 API 友好字典."""
    return {
        "id": fact.id,
        "type": fact.type,
        "content": fact.content,
        "importance": fact.importance,
        "weight": fact.weight,
        "layer": fact.layer,
        "source_session_id": fact.source_session_id,
        "source_interaction_id": fact.source_interaction_id,
        "privacy_level": fact.privacy_level,
        "tags": fact.tags,
        "created_at": fact.created_at,
        "updated_at": fact.updated_at,
        "last_accessed_at": fact.last_accessed_at,
        "similarity": fact.similarity,
    }


def _stats_to_dict(stats: MemoryStats) -> dict:
    """将 MemoryStats 序列化为 API 友好字典."""
    return {
        "total_facts": stats.total_facts,
        "by_layer": stats.by_layer,
        "by_type": stats.by_type,
        "last_extraction_at": stats.last_extraction_at,
        "total_vector_bytes": stats.total_vector_bytes,
    }


# ════════════════════════════════════════════════════════
# GET /api/v1/memory/facts — 列表查询
# ════════════════════════════════════════════════════════


@router.get("/facts")
async def list_facts(
    layer: Optional[str] = Query(None, description="按层级筛选: transient|working|core|all"),
    type: Optional[str] = Query(None, description="按类型筛选: preference|fact|procedure|relationship"),
    limit: int = Query(50, ge=1, le=500, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    q: Optional[str] = Query(None, description="语义搜索关键词，触发向量检索"),
):
    """列表查询记忆事实，支持 layer/type/limit/offset 筛选和 q 语义搜索."""
    engine = _get_engine()

    try:
        if q:
            # 语义搜索模式：忽略 layer/type 筛选，直接向量检索
            top_k = min(limit, 50)
            facts = engine.search_memories(q, top_k=top_k)
            # 手动分页
            total = len(facts)
            facts = facts[offset : offset + limit]
        else:
            facts = engine.list_facts(layer=layer, type=type, limit=limit, offset=offset)
            # 获取总数（简化：用 list_facts 无分页查询）
            all_facts = engine.list_facts(layer=layer, type=type, limit=10000, offset=0)
            total = len(all_facts)

        return {
            "ok": True,
            "data": {
                "facts": [_fact_to_dict(f) for f in facts],
                "total": total,
                "limit": limit,
                "offset": offset,
            },
        }
    except Exception as e:
        logger.error(f"list_facts failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"ok": False, "error": str(e)})


# ════════════════════════════════════════════════════════
# GET /api/v1/memory/facts/{id} — 单条查询
# ════════════════════════════════════════════════════════


@router.get("/facts/{fact_id}")
async def get_fact(fact_id: str):
    """获取单条记忆事实."""
    engine = _get_engine()

    fact = engine._get_fact_by_id(fact_id)
    if fact is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "error": f"Fact not found: {fact_id}"},
        )

    return {"ok": True, "data": _fact_to_dict(fact)}


# ════════════════════════════════════════════════════════
# POST /api/v1/memory/facts — 手动添加
# ════════════════════════════════════════════════════════


@router.post("/facts", status_code=201)
async def create_fact(request: dict):
    """手动添加记忆事实.

    Request body: {content, type, importance?, layer?, tags?, privacy_level?}
    """
    engine = _get_engine()

    content = request.get("content")
    if not content:
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "error": "content is required"},
        )

    fact_type = request.get("type", "fact")
    if fact_type not in ("preference", "fact", "procedure", "relationship"):
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "error": f"Invalid type: {fact_type}"},
        )

    try:
        fact = engine.add_manual_fact(
            content=content,
            type=fact_type,
            importance=float(request.get("importance", 0.5)),
            layer=request.get("layer", "working"),
            tags=request.get("tags", []),
            privacy_level=request.get("privacy_level", "private"),
        )
        return {"ok": True, "data": _fact_to_dict(fact)}
    except Exception as e:
        logger.error(f"create_fact failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"ok": False, "error": str(e)})


# ════════════════════════════════════════════════════════
# PUT /api/v1/memory/facts/{id} — 更新
# ════════════════════════════════════════════════════════


@router.put("/facts/{fact_id}")
async def update_fact(fact_id: str, request: dict):
    """更新记忆事实，支持部分字段更新.

    Request body: {content?, type?, importance?, layer?, tags?, privacy_level?}
    """
    engine = _get_engine()

    try:
        fact = engine.update_fact(fact_id, **request)
        return {"ok": True, "data": _fact_to_dict(fact)}
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "error": str(e)},
        )
    except Exception as e:
        logger.error(f"update_fact failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"ok": False, "error": str(e)})


# ════════════════════════════════════════════════════════
# DELETE /api/v1/memory/facts/{id} — 删除
# ════════════════════════════════════════════════════════


@router.delete("/facts/{fact_id}")
async def delete_fact(fact_id: str):
    """删除记忆事实."""
    engine = _get_engine()

    # 先检查是否存在
    existing = engine._get_fact_by_id(fact_id)
    if existing is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "error": f"Fact not found: {fact_id}"},
        )

    try:
        engine.delete_fact(fact_id)
        return {"ok": True, "data": {"deleted_id": fact_id}}
    except Exception as e:
        logger.error(f"delete_fact failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"ok": False, "error": str(e)})


# ════════════════════════════════════════════════════════
# GET /api/v1/memory/stats — 统计信息
# ════════════════════════════════════════════════════════


@router.get("/stats")
async def get_stats():
    """获取记忆统计信息."""
    engine = _get_engine()

    try:
        stats = engine.get_stats()
        return {"ok": True, "data": _stats_to_dict(stats)}
    except Exception as e:
        logger.error(f"get_stats failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"ok": False, "error": str(e)})


# ════════════════════════════════════════════════════════
# POST /api/v1/memory/facts/{id}/reinforce — 强化记忆
# ════════════════════════════════════════════════════════


@router.post("/facts/{fact_id}/reinforce")
async def reinforce_fact(fact_id: str, request: Optional[dict] = None):
    """强化记忆（增加权重和重要性）.

    Request body (optional): {amount: float}
    """
    engine = _get_engine()
    amount = float((request or {}).get("amount", 0.1))

    try:
        fact = engine.reinforce(fact_id, amount=amount)
        return {"ok": True, "data": _fact_to_dict(fact)}
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "error": str(e)},
        )
    except Exception as e:
        logger.error(f"reinforce_fact failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"ok": False, "error": str(e)})
