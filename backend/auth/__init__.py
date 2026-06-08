"""JWT 工具函数 — Token 创建与验证.

使用 PyJWT + HS256 算法，默认过期时间 24 小时。
密钥从环境变量 JWT_SECRET_KEY 读取，默认值仅用于开发。
"""

import os
import logging
from datetime import datetime, timedelta, timezone

import jwt

logger = logging.getLogger(__name__)

# ── 配置 ─────────────────────────────────────────────

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "evo-gen-secret-change-me")
ALGORITHM = "HS256"
DEFAULT_EXPIRE_HOURS = 24


# ── 公开 API ─────────────────────────────────────────


def create_token(token_data: dict, expires_delta: timedelta | None = None) -> str:
    """创建 JWT token.

    Args:
        token_data: 要编码的数据（必须包含 "sub": user_id）。
        expires_delta: 过期时间增量，默认 24 小时。

    Returns:
        JWT 字符串。
    """
    payload = token_data.copy()
    now = datetime.now(timezone.utc)

    if expires_delta is None:
        expires_delta = timedelta(hours=DEFAULT_EXPIRE_HOURS)

    payload["exp"] = now + expires_delta
    payload["iat"] = now

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token


def decode_token(token: str) -> dict:
    """解码并验证 JWT token.

    Args:
        token: JWT 字符串。

    Returns:
        解码后的 payload dict（包含 sub, exp 等字段）。

    Raises:
        jwt.ExpiredSignatureError: token 已过期。
        jwt.InvalidTokenError: token 无效。
    """
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return payload
