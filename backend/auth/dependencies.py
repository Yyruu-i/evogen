"""FastAPI 认证依赖 — get_current_user.

用于所有需要认证的端点，通过 Depends(get_current_user) 注入。
无 token 时返回 "default"（向后兼容、测试模式）。
"""

import logging

from fastapi import Header, HTTPException

from backend.auth import decode_token

logger = logging.getLogger(__name__)


async def get_current_user(
    authorization: str = Header(None),
) -> str:
    """从 Authorization header 提取并验证 JWT token，返回 user_id.

    无 token 时返回 "default"（向后兼容、未登录/测试模式）。
    有效 token 时返回其 user_id（数据隔离生效）。

    Header 格式: "Bearer <token>"

    Returns:
        user_id: str

    Raises:
        HTTPException(401): token 格式正确但无效/过期。
    """
    # 无 Authorization header → 返回默认用户（向后兼容）
    if not authorization:
        return "default"

    # 提取 Bearer token
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"ok": False, "error": "缺少或无效的 Authorization header (需要 Bearer token)"},
        )

    token = authorization[len("Bearer "):]

    if not token:
        return "default"

    # 解码验证
    try:
        payload = decode_token(token)
    except Exception as e:
        logger.warning(f"Token validation failed: {e}")
        raise HTTPException(
            status_code=401,
            detail={"ok": False, "error": f"Token 无效或已过期: {str(e)}"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail={"ok": False, "error": "Token 缺少 sub 字段"},
        )

    return user_id
