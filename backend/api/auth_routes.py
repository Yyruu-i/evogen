"""认证 REST API — 注册 / 登录 / 当前用户信息.

端点前缀：/api/v1/auth
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from passlib.hash import bcrypt
from pydantic import BaseModel, EmailStr

from backend.auth import create_token
from backend.auth.dependencies import get_current_user
from backend.db.connection import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ── 请求体模型 ──────────────────────────────────────


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    created_at: str


# ── 辅助 ────────────────────────────────────────────


def _hash_password(password: str) -> str:
    """使用 bcrypt 哈希密码."""
    return bcrypt.hash(password)


def _verify_password(password: str, password_hash: str) -> bool:
    """验证密码."""
    return bcrypt.verify(password, password_hash)


def _user_row_to_dict(row) -> UserResponse:
    """将数据库行转为用户字典."""
    return UserResponse(
        id=row["id"],
        username=row["username"],
        email=row["email"],
        created_at=row["created_at"],
    )


# ── 端点 ────────────────────────────────────────────


@router.post("/register", status_code=201)
async def register(request: RegisterRequest):
    """用户注册.

    请求体: {username, email, password}
    返回: {token, user: {id, username, email}}
    """
    db = get_db()

    # 校验 username 唯一性
    existing = db.execute(
        "SELECT id FROM users WHERE username = ?", (request.username,)
    ).fetchone()
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"ok": False, "error": "用户名已被注册"},
        )

    # 校验 email 唯一性
    existing = db.execute(
        "SELECT id FROM users WHERE email = ?", (request.email,)
    ).fetchone()
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"ok": False, "error": "邮箱已被注册"},
        )

    # 创建用户
    user_id = str(uuid.uuid4())
    password_hash = _hash_password(request.password)

    db.execute(
        """INSERT INTO users (id, username, email, password_hash)
           VALUES (?, ?, ?, ?)""",
        (user_id, request.username, request.email, password_hash),
    )
    db.commit()

    # 生成 token
    token = create_token({"sub": user_id})

    # 查询完整用户信息
    row = db.execute(
        "SELECT id, username, email, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()

    logger.info(f"User registered: {request.username} ({user_id})")
    return {
        "ok": True,
        "data": {
            "token": token,
            "user": _user_row_to_dict(row),
        },
    }


@router.post("/login")
async def login(request: LoginRequest):
    """用户登录.

    请求体: {username, password}
    返回: {token, user: {id, username, email}}
    """
    db = get_db()

    row = db.execute(
        "SELECT id, username, email, password_hash, created_at FROM users WHERE username = ?",
        (request.username,),
    ).fetchone()

    if not row:
        raise HTTPException(
            status_code=401,
            detail={"ok": False, "error": "用户名或密码错误"},
        )

    if not _verify_password(request.password, row["password_hash"]):
        raise HTTPException(
            status_code=401,
            detail={"ok": False, "error": "用户名或密码错误"},
        )

    token = create_token({"sub": row["id"]})

    logger.info(f"User logged in: {request.username} ({row['id']})")
    return {
        "ok": True,
        "data": {
            "token": token,
            "user": _user_row_to_dict(row),
        },
    }


@router.get("/me")
async def get_me(user_id: str = Depends(get_current_user)):
    """获取当前用户信息（需要认证）.

    Header: Authorization: Bearer <token>
    返回: {id, username, email, created_at}
    """
    db = get_db()

    row = db.execute(
        "SELECT id, username, email, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()

    if not row:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "error": "用户不存在"},
        )

    return {"ok": True, "data": _user_row_to_dict(row)}
