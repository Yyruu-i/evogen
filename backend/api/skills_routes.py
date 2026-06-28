""""Skills REST API — 从 Hermes skills 目录扫描真实技能列表 + 技能市场（浏览/安装/评分/评论）."""

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter, Depends, HTTPException

from backend.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/skills", tags=["skills"])

# ── 技能目录配置 ──
# 扫描策略：HERMES_HOME/skills + 所有 profile 的 skills + 系统级路径
_HERMES_HOME = os.environ.get("HERMES_HOME", "/root/.hermes")
_SKILLS_DIRS: list[Path] = []

def _add_skills_dir(path: str) -> None:
    p = Path(path)
    if p.is_dir() and p not in _SKILLS_DIRS:
        _SKILLS_DIRS.append(p)

# 1. 当前 HERMES_HOME/skills
_add_skills_dir(f"{_HERMES_HOME}/skills")

# 2. 所有 profile 的 skills 目录
_profiles_base = Path(f"{_HERMES_HOME}/profiles")
if _profiles_base.is_dir():
    for _pd in _profiles_base.iterdir():
        if _pd.is_dir():
            _add_skills_dir(str(_pd / "skills"))

# 3. 系统级路径（兜底）
_add_skills_dir("/root/.hermes/skills")
_add_skills_dir(os.path.expanduser("~/.hermes/skills"))

# ── 分类中文映射 ──
_CATEGORY_LABELS: dict[str, str] = {
    "apple": "Apple",
    "autonomous-ai-agents": "AI 代理",
    "creative": "创作",
    "data-science": "数据科学",
    "devops": "运维",
    "diagramming": "图表",
    "dogfood": "测试",
    "domain": "域名",
    "email": "邮件",
    "gaming": "游戏",
    "gifs": "GIF",
    "github": "GitHub",
    "inference-sh": "推理",
    "mcp": "MCP",
    "media": "媒体",
    "mlops": "MLOps",
    "note-taking": "笔记",
    "productivity": "效率",
    "red-teaming": "安全测试",
    "research": "研究",
    "smart-home": "智能家居",
    "social-media": "社交媒体",
    "software-development": "开发",
    "yuanbao": "元宝",
}


def _parse_skill_frontmatter(file_path: Path) -> Optional[dict]:
    """解析 SKILL.md 的 YAML frontmatter.

    返回 {name, description, tags, category, version, author} 或 None.
    """
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to read {file_path}: {e}")
        return None

    # 提取 YAML frontmatter（--- ... ---）
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        logger.debug(f"No frontmatter in {file_path}")
        return None

    try:
        fm = yaml.safe_load(match.group(1))
    except yaml.YAMLError as e:
        logger.warning(f"YAML parse error in {file_path}: {e}")
        return None

    if not isinstance(fm, dict):
        return None

    # 提取 metadata.hermes.tags
    tags: list[str] = []
    hermes_meta = fm.get("metadata", {}).get("hermes", {})
    if isinstance(hermes_meta, dict):
        raw_tags = hermes_meta.get("tags", [])
        if isinstance(raw_tags, list):
            tags = [str(t) for t in raw_tags]

    # 技能所属分类：优先取 frontmatter，回退到路径推断
    category = fm.get("category", "")
    if not category:
        # 路径结构: .../skills/[{user_id}/]{category}/{skill}/SKILL.md
        parts = file_path.parts
        try:
            idx = parts.index("skills")
            after = parts[idx + 1:]
            # 跳过 UUID / user_xxx / default 等 user-id 段
            uuid_re = re.compile(
                r"^(default|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|user_[a-z0-9_]+)$"
            )
            # 过滤掉可能的 user_id 段，只保留真正分类名
            filtered = [seg for seg in after[:-2] if not uuid_re.match(seg)]
            if filtered:
                category = filtered[-1]  # 取最后一个分类段
        except (ValueError, IndexError):
            pass

    return {
        "name": fm.get("name", file_path.parent.name),
        "description": fm.get("description", ""),
        "tags": tags,
        "category": category,
        "version": fm.get("version", "1.0.0"),
        "author": fm.get("author", ""),
        "scope": fm.get("scope", ""),
        "user_id": fm.get("user_id", ""),
    }


def _scan_skills(user_id: str = "default") -> list[dict]:
    """扫描所有 SKILL.md 文件，构建技能列表，按首次创建时间升序.

    合并内置技能（全局）和用户自定义技能（per-user 目录）。
    """
    skills: list[dict] = []

    # 用户自定义技能目录
    user_skills_dir = Path(os.path.expanduser(f"~/.hermes/skills/{user_id}"))

    # 收集所有 SKILL.md 路径（id → {path, mtime, scope}），取最新 mtime
    skill_files: dict[str, dict] = {}
    # 内置技能（全局）
    for skills_dir in _SKILLS_DIRS:
        for md_path in sorted(skills_dir.rglob("SKILL.md")):
            # 跳过用户目录下的（处理方式不同）
            if str(md_path).startswith(str(user_skills_dir)):
                continue
            skill_id = md_path.parent.name
            mtime = md_path.stat().st_mtime
            # 读取 frontmatter 判断是否属于其他用户
            fm = _parse_skill_frontmatter(md_path)
            if fm and fm.get("scope") == "user" and fm.get("user_id") and fm["user_id"] != user_id:
                continue  # 其他用户的技能，跳过
            if skill_id not in skill_files or mtime > skill_files[skill_id]["mtime"]:
                skill_files[skill_id] = {"path": md_path, "mtime": mtime, "scope": "builtin"}

    # 用户自定义技能
    if user_skills_dir.is_dir():
        for md_path in sorted(user_skills_dir.rglob("SKILL.md")):
            skill_id = md_path.parent.name
            mtime = md_path.stat().st_mtime
            # 用户技能覆盖同名内置技能
            skill_files[skill_id] = {"path": md_path, "mtime": mtime, "scope": "user"}

    for skill_id, info in skill_files.items():
        md_path = info["path"]
        fm = _parse_skill_frontmatter(md_path)
        if fm is None:
            continue

        # 使用最新的文件修改时间作为创建时间
        created_at = datetime.fromtimestamp(info["mtime"], tz=timezone.utc).isoformat()

        # 分类中文标签
        category_label = _CATEGORY_LABELS.get(fm["category"], fm["category"])

        skills.append({
            "id": skill_id,
            "name": fm["name"],
            "description": fm["description"],
            "tags": fm["tags"],
            "category": category_label or fm["category"],
            "source": "local",
            "scope": info.get("scope", "builtin"),
            "user_id": fm.get("user_id", ""),
            "version": _version_int(fm.get("version", "1.0.0")),
            "use_count": 0,
            "success_rate": 0.0,
            "created_at": created_at,
        })

    # 按创建时间降序（最新的在前）
    skills.sort(key=lambda s: s["created_at"], reverse=True)
    return skills


def _version_int(version_str: str) -> int:
    """将 semver 字符串转为整数版本号（主版本 * 100 + 次版本）."""
    try:
        # YAML 可能将 version: 2 解析为 int, version: 1.0 解析为 float
        if isinstance(version_str, (int, float)):
            return int(version_str)
        parts = version_str.split(".")
        return int(parts[0]) * 100 + int(parts[1]) if len(parts) > 1 else int(parts[0])
    except (ValueError, IndexError, AttributeError):
        return 1


@router.get("")
async def list_skills(user_id: str = Depends(get_current_user)):
    """获取所有技能列表（从 Hermes skills 目录实时扫描，合并内置+用户自定义）."""
    try:
        skills = _scan_skills(user_id=user_id)
    except Exception as e:
        logger.error(f"Failed to scan skills: {e}", exc_info=True)
        skills = []

    return {
        "ok": True,
        "data": {
            "skills": skills,
            "total": len(skills),
        },
    }


@router.post("")
async def create_skill(skill_data: dict, user_id: str = Depends(get_current_user)):
    """创建新技能（写入 per-user SKILL.md 文件）."""
    name = skill_data.get("name", "").strip()
    if not name:
        return {"ok": False, "error": "技能名称为必填项"}

    category = skill_data.get("category", "uncategorized").strip() or "uncategorized"
    description = skill_data.get("description", "").strip()
    markdown_body = skill_data.get("markdown", "").strip()

    # 生成安全的目录名
    dir_name = re.sub(r"[^\w\-]", "-", name.lower()).strip("-") or "skill"

    # 写入到 ~/.hermes/skills/<user_id>/<category>/<dir_name>/SKILL.md（per-user 隔离）
    target_dir = Path(os.path.expanduser(f"~/.hermes/skills/{user_id}/{category}/{dir_name}"))
    target_dir.mkdir(parents=True, exist_ok=True)

    yaml_front = (
        f"---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f"category: {category}\n"
        f"scope: user\n"
        f"user_id: {user_id}\n"
        f"version: 1.0.0\n"
        f"---\n\n"
    )
    content = yaml_front + (markdown_body or f"# {name}\n\n{description}\n")
    (target_dir / "SKILL.md").write_text(content, encoding="utf-8")

    return {"ok": True, "data": {"id": dir_name, "name": name}}


@router.post("/batch/delete")
async def batch_delete_skills(payload: dict, user_id: str = Depends(get_current_user)):
    """批量删除技能 — 仅允许删除用户自定义技能，内置技能（scope=builtin）禁止删除."""
    import shutil
    ids: list[str] = payload.get("ids", [])
    if not ids:
        return {"ok": False, "error": "ids 为空"}
    deleted = 0
    forbidden: list[str] = []
    not_found: list[str] = []
    user_skills_dir = Path(os.path.expanduser(f"~/.hermes/skills/{user_id}"))

    def _check_scope(md_path: Path) -> str:
        """读取 SKILL.md frontmatter 中的 scope 字段."""
        try:
            raw = md_path.read_text(encoding="utf-8")
            m = re.match(r"^---\s*\n(.*?)\n---", raw, re.DOTALL)
            if m:
                fm = yaml.safe_load(m.group(1)) or {}
                return fm.get("scope", "")
        except Exception:
            pass
        return ""

    for sid in ids:
        found = False
        # 1. 检查用户目录（优先，允许删除）
        if user_skills_dir.is_dir():
            for candidate in user_skills_dir.rglob(sid):
                if candidate.is_dir() and (candidate / "SKILL.md").exists():
                    md_file = candidate / "SKILL.md"
                    scope = _check_scope(md_file)
                    if scope == "builtin":
                        forbidden.append(sid)
                    else:
                        shutil.rmtree(candidate)
                        deleted += 1
                    found = True
                    break
        if found:
            continue

        # 2. 检查全局目录（内置技能，禁止删除）
        for skills_dir in _SKILLS_DIRS:
            for candidate in skills_dir.rglob(sid):
                if candidate.is_dir() and (candidate / "SKILL.md").exists():
                    scope = _check_scope(candidate / "SKILL.md")
                    forbidden.append(sid)
                    found = True
                    break
            if found:
                break

        if not found:
            not_found.append(sid)

    result = {"deleted": deleted, "not_found": not_found}
    if forbidden:
        result["forbidden"] = forbidden
    return {"ok": True, "data": result}


# ── 技能市场（浏览/安装/评分/评论）──

# 内置市场技能列表
_MARKET_SKILLS = [
    {
        "id": "code-review-assistant",
        "name": "代码审查助手",
        "description": "自动审查 Pull Request 代码，检测潜在 bug、安全漏洞和代码风格问题。支持 Python、JavaScript、TypeScript、Go 等主流语言。",
        "category": "开发",
        "author": "EvoGen Team",
        "version": "1.2.0",
        "install_count": 1423,
        "rating": 4.7,
        "tags": ["code-review", "python", "javascript", "security"],
        "updated_at": "2026-06-15T00:00:00Z",
    },
    {
        "id": "security-audit",
        "name": "安全审计专家",
        "description": "对代码仓库进行自动化安全审计，检测 OWASP Top 10 漏洞、敏感信息泄露、依赖安全问题等。",
        "category": "安全测试",
        "author": "EvoGen Team",
        "version": "2.0.1",
        "install_count": 987,
        "rating": 4.5,
        "tags": ["security", "audit", "owasp", "dependency"],
        "updated_at": "2026-06-10T00:00:00Z",
    },
    {
        "id": "log-analysis",
        "name": "日志分析器",
        "description": "分析服务器日志文件，自动识别异常模式、错误趋势和性能瓶颈。支持 Nginx、Apache、系统日志等格式。",
        "category": "运维",
        "author": "Community",
        "version": "1.0.3",
        "install_count": 756,
        "rating": 4.2,
        "tags": ["logging", "monitoring", "devops"],
        "updated_at": "2026-05-28T00:00:00Z",
    },
    {
        "id": "api-doc-generator",
        "name": "API 文档生成器",
        "description": "基于 FastAPI 路由定义自动生成 OpenAPI/Swagger 文档，支持自定义描述和中英文切换。",
        "category": "开发",
        "author": "EvoGen Team",
        "version": "1.5.0",
        "install_count": 2145,
        "rating": 4.8,
        "tags": ["api", "documentation", "fastapi", "openapi"],
        "updated_at": "2026-06-20T00:00:00Z",
    },
    {
        "id": "database-optimizer",
        "name": "数据库优化顾问",
        "description": "分析 SQL 查询性能，推荐索引策略和查询优化方案。支持 MySQL、PostgreSQL、SQLite。",
        "category": "数据科学",
        "author": "Community",
        "version": "0.9.0",
        "install_count": 532,
        "rating": 3.9,
        "tags": ["database", "sql", "optimization"],
        "updated_at": "2026-05-15T00:00:00Z",
    },
    {
        "id": "docker-deploy",
        "name": "Docker 部署助手",
        "description": "自动生成 Dockerfile 和 docker-compose.yml，辅助配置容器部署策略和环境变量管理。",
        "category": "运维",
        "author": "EvoGen Team",
        "version": "2.1.0",
        "install_count": 1876,
        "rating": 4.6,
        "tags": ["docker", "deployment", "devops"],
        "updated_at": "2026-06-18T00:00:00Z",
    },
]

# 用户评论存储（内存 + 简单文件持久化）
_MARKET_REVIEWS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "market_reviews.json"
)
_market_reviews: dict[str, list[dict]] = {}  # skill_id -> [reviews]


def _load_market_reviews():
    """启动时加载持久化的评论."""
    global _market_reviews
    try:
        if os.path.exists(_MARKET_REVIEWS_FILE):
            with open(_MARKET_REVIEWS_FILE, "r") as f:
                _market_reviews = json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load market reviews: {e}")


def _save_market_reviews():
    """持久化评论到文件."""
    try:
        os.makedirs(os.path.dirname(_MARKET_REVIEWS_FILE), exist_ok=True)
        with open(_MARKET_REVIEWS_FILE, "w") as f:
            json.dump(_market_reviews, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save market reviews: {e}")


# 启动时加载
_load_market_reviews()


@router.get("/market")
async def list_market_skills(category: Optional[str] = None, search: Optional[str] = None):
    """获取技能市场技能列表，支持分类筛选和关键词搜索."""
    skills = _MARKET_SKILLS

    if category:
        skills = [s for s in skills if s["category"] == category]

    if search:
        q = search.lower()
        skills = [
            s for s in skills
            if q in s["name"].lower() or q in s["description"].lower() or q in s["author"].lower()
        ]

    # 注入评论数量
    result = []
    for s in skills:
        s_copy = dict(s)
        s_copy["review_count"] = len(_market_reviews.get(s["id"], []))
        result.append(s_copy)

    return {"ok": True, "data": {"skills": result, "total": len(result)}}


@router.post("/market/{skill_id}/install")
async def install_market_skill(skill_id: str, user_id: str = Depends(get_current_user)):
    """从技能市场安装技能到本地."""
    skill = next((s for s in _MARKET_SKILLS if s["id"] == skill_id), None)
    if not skill:
        raise HTTPException(status_code=404, detail={"ok": False, "error": "技能不存在"})

    # 写入本地技能目录
    target_dir = Path(os.path.expanduser(f"~/.hermes/skills/{user_id}/market/{skill_id}"))
    target_dir.mkdir(parents=True, exist_ok=True)

    frontmatter = (
        f"---\n"
        f"name: {skill['name']}\n"
        f"description: {skill['description']}\n"
        f"category: {skill['category']}\n"
        f"scope: user\n"
        f"user_id: {user_id}\n"
        f"version: {skill['version']}\n"
        f"author: {skill['author']}\n"
        f"source: market\n"
        f"---\n\n"
        f"# {skill['name']}\n\n{skill['description']}\n\n"
        f"> 来自技能市场，作者: {skill['author']}\n"
    )
    (target_dir / "SKILL.md").write_text(frontmatter, encoding="utf-8")

    return {"ok": True, "data": {"id": skill_id, "name": skill["name"]}}


@router.get("/market/{skill_id}/reviews")
async def get_market_skill_reviews(skill_id: str):
    """获取技能市场的评论列表."""
    reviews = _market_reviews.get(skill_id, [])
    # 计算评分
    rating = 0.0
    if reviews:
        rating = sum(r["rating"] for r in reviews) / len(reviews)
    return {
        "ok": True,
        "data": {
            "reviews": reviews,
            "total": len(reviews),
            "average_rating": round(rating, 1),
        },
    }


@router.post("/market/{skill_id}/reviews")
async def add_market_skill_review(
    skill_id: str, review_data: dict, user_id: str = Depends(get_current_user)
):
    """添加技能评论和评分."""
    skill = next((s for s in _MARKET_SKILLS if s["id"] == skill_id), None)
    if not skill:
        raise HTTPException(status_code=404, detail={"ok": False, "error": "技能不存在"})

    rating = review_data.get("rating", 5)
    comment = review_data.get("comment", "").strip()

    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail={"ok": False, "error": "评分应在 1~5 之间"})

    review = {
        "id": str(len(_market_reviews.get(skill_id, [])) + 1),
        "user_id": user_id,
        "rating": rating,
        "comment": comment or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    _market_reviews.setdefault(skill_id, []).append(review)
    _save_market_reviews()

    return {"ok": True, "data": review}


@router.get("/{skill_id}")
async def get_skill(skill_id: str, user_id: str = Depends(get_current_user)):
    """获取单个技能完整内容（含 Markdown 正文）."""
    user_skills_dir = Path(os.path.expanduser(f"~/.hermes/skills/{user_id}"))
    md_path = None
    # 先查用户目录
    if user_skills_dir.is_dir():
        for candidate in user_skills_dir.rglob(f"{skill_id}/SKILL.md"):
            md_path = candidate
            break
    # 再查全局目录
    if not md_path:
        for skills_dir in _SKILLS_DIRS:
            for candidate in skills_dir.rglob(f"{skill_id}/SKILL.md"):
                md_path = candidate
                break
            if md_path:
                break
    if not md_path:
        raise HTTPException(status_code=404, detail={"ok": False, "error": "技能不存在"})
    content = md_path.read_text(encoding="utf-8")
    fm = _parse_skill_frontmatter(md_path) or {}
    body = ""
    parts = content.split("---", 2)
    if len(parts) >= 3:
        body = parts[2].lstrip("\n")
    return {"ok": True, "data": {"content": body, "frontmatter": fm}}


@router.put("/{skill_id}")
async def update_skill(skill_id: str, skill_data: dict, user_id: str = Depends(get_current_user)):
    """更新技能 SKILL.md（仅允许编辑用户自己的技能）."""
    # 先检查是否为用户自定义技能（per-user 目录）
    user_skills_dir = Path(os.path.expanduser(f"~/.hermes/skills/{user_id}"))
    md_path = None
    if user_skills_dir.is_dir():
        for candidate in user_skills_dir.rglob(f"{skill_id}/SKILL.md"):
            md_path = candidate
            break

    if not md_path:
        raise HTTPException(status_code=403, detail={"ok": False, "error": "技能不存在或为内置技能，不可编辑"})

    # 二次校验：读取 frontmatter scope，内置技能（scope≠user）禁止编辑
    fm_check = _parse_skill_frontmatter(md_path) or {}
    if fm_check.get("scope") != "user":
        raise HTTPException(status_code=403, detail={"ok": False, "error": "内置技能不可编辑，仅用户自定义技能（scope=user）可编辑"})

    name = skill_data.get("name", "").strip()
    description = skill_data.get("description", "").strip()
    markdown_body = skill_data.get("markdown", "").strip()
    category = skill_data.get("category", "").strip()

    # Parse existing to preserve other frontmatter and body
    existing = _parse_skill_frontmatter(md_path) or {}

    # Extract existing body (everything after frontmatter)
    existing_body = ""
    try:
        raw = md_path.read_text(encoding="utf-8")
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            existing_body = parts[2].lstrip("\n")
    except Exception:
        pass

    yaml_front = (
        f"---\n"
        f"name: {name or existing.get('name', '')}\n"
        f"description: {description or existing.get('description', '')}\n"
        f"category: {category or existing.get('category', '')}\n"
        f"scope: user\n"
        f"user_id: {user_id}\n"
        f"version: 1.0.0\n"
        f"---\n\n"
    )
    content = yaml_front + (markdown_body or existing_body or f"# {name}\n\n{description}\n")
    md_path.write_text(content, encoding="utf-8")

    return {"ok": True, "data": {"id": skill_id, "name": name}}


@router.delete("/{skill_id}")
async def delete_skill(skill_id: str, user_id: str = Depends(get_current_user)):
    """删除技能（仅允许删除用户自己的技能）."""
    import shutil
    # 只允许删除 per-user 目录下的技能
    user_skills_dir = Path(os.path.expanduser(f"~/.hermes/skills/{user_id}"))
    if user_skills_dir.is_dir():
        for candidate in user_skills_dir.rglob(skill_id):
            if candidate.is_dir() and (candidate / "SKILL.md").exists():
                shutil.rmtree(candidate)
                return {"ok": True}
    return {"ok": False, "error": "技能不存在或为内置技能，不可删除"}
