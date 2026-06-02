"""T-04-04 人格 REST API 端点（对齐设计文档第1387-1410行）.

统一响应格式：{"ok": true, "data": {...}} 或 {"ok": false, "error": "..."}
"""

import logging

from fastapi import APIRouter, HTTPException

from backend.persona.engine import PersonaEngine, get_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/persona", tags=["persona"])


# ════════════════════════════════════════════════════════
# 辅助
# ════════════════════════════════════════════════════════


def _get_engine() -> PersonaEngine:
    """获取全局引擎实例（测试时可 monkeypatch）."""
    return get_engine()


def _persona_to_dict(persona) -> dict:
    """将 Persona 对象序列化为 API 友好字典."""
    from dataclasses import asdict
    return asdict(persona)


# ════════════════════════════════════════════════════════
# GET /api/v1/persona/attributes
# ════════════════════════════════════════════════════════


@router.get("/attributes")
async def get_attributes():
    """获取所有当前人格属性.

    响应：{"ok": true, "data": {"attributes": {...}}}
    """
    engine = _get_engine()
    try:
        attrs = await engine.get_attributes()
        return {"ok": True, "data": {"attributes": attrs}}
    except Exception as e:
        logger.error(f"get_attributes failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"ok": False, "error": str(e)})


# ════════════════════════════════════════════════════════
# PUT /api/v1/persona/attributes  — 批量更新
# ════════════════════════════════════════════════════════


@router.put("/attributes")
async def set_attributes_batch(request: dict):
    """批量更新人格属性.

    请求体：{key: value, ...}（扁平 JSON 对象）
    响应：{"ok": true, "data": {"attributes": {...}}}
    """
    engine = _get_engine()
    try:
        # 过滤掉辅助字段
        attrs = {k: v for k, v in request.items() if not k.startswith("_")}
        if not attrs:
            raise HTTPException(
                status_code=400,
                detail={"ok": False, "error": "No attributes provided"},
            )

        persona = await engine.set_attributes(attrs)
        return {
            "ok": True,
            "data": {"attributes": await engine.get_attributes(), "persona": _persona_to_dict(persona)},
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"set_attributes_batch failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"ok": False, "error": str(e)})


# ════════════════════════════════════════════════════════
# PUT /api/v1/persona/attributes/{key}  — 单个更新
# ════════════════════════════════════════════════════════


@router.put("/attributes/{key}")
async def update_attribute(key: str, request: dict):
    """更新单个属性.

    请求体：{"value": any}
    响应：{"ok": true, "data": {"key": "...", "value": ...}}
    """
    engine = _get_engine()
    try:
        value = request.get("value")
        # 支持 value 为 None / 0 / False 的情况
        if "value" not in request:
            raise HTTPException(
                status_code=400,
                detail={"ok": False, "error": "Missing 'value' in request body"},
            )

        persona = await engine.update_attribute(key, value)
        all_attrs = await engine.get_attributes()
        return {
            "ok": True,
            "data": {
                "key": key,
                "value": all_attrs.get(key),
                "persona": _persona_to_dict(persona),
            },
        }
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "error": str(e)},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"update_attribute failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"ok": False, "error": str(e)})


# ════════════════════════════════════════════════════════
# GET /api/v1/persona/export
# ════════════════════════════════════════════════════════


@router.get("/export")
async def export_persona():
    """导出人格配置为 JSON 字符串.

    响应：{"ok": true, "data": {"json": "..."}}
    """
    engine = _get_engine()
    try:
        json_str = await engine.export_persona()
        return {"ok": True, "data": {"json": json_str}}
    except Exception as e:
        logger.error(f"export_persona failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"ok": False, "error": str(e)})


# ════════════════════════════════════════════════════════
# POST /api/v1/persona/import
# ════════════════════════════════════════════════════════


@router.post("/import")
async def import_persona(request: dict):
    """从 JSON 导入人格配置.

    请求体：{"json_str": "..."}
    响应：{"ok": true, "data": {"attributes": {...}}}
    """
    engine = _get_engine()
    try:
        json_str = request.get("json_str")
        if not json_str:
            raise HTTPException(
                status_code=400,
                detail={"ok": False, "error": "Missing 'json_str' in request body"},
            )

        persona = await engine.import_persona(json_str)
        return {
            "ok": True,
            "data": {
                "attributes": await engine.get_attributes(),
                "persona": _persona_to_dict(persona),
            },
        }
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "error": str(e)},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"import_persona failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"ok": False, "error": str(e)})


# ════════════════════════════════════════════════════════
# GET /api/v1/persona/preview-prompt
# ════════════════════════════════════════════════════════


@router.get("/preview-prompt")
async def preview_prompt():
    """预览当前人格的 System Prompt 注入片段.

    响应：{"ok": true, "data": {"prompt_injection": "..."}}
    """
    engine = _get_engine()
    try:
        prompt = await engine.get_prompt_injection()
        return {"ok": True, "data": {"prompt_injection": prompt}}
    except Exception as e:
        logger.error(f"preview_prompt failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"ok": False, "error": str(e)})
