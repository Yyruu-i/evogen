"""Skills REST API — 从 Hermes skills 目录扫描真实技能列表."""

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter, Depends

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

    # 技能所属分类：文件路径中 skills/ 之后的第一个目录名
    category = ""
    path_str = str(file_path)
    m = re.search(r"/skills/([^/]+)/", path_str)
    if m:
        category = m.group(1)

    return {
        "name": fm.get("name", file_path.parent.name),
        "description": fm.get("description", ""),
        "tags": tags,
        "category": category,
        "version": fm.get("version", "1.0.0"),
        "author": fm.get("author", ""),
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
        parts = version_str.split(".")
        return int(parts[0]) * 100 + int(parts[1]) if len(parts) > 1 else int(parts[0])
    except (ValueError, IndexError):
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
        return {"ok": False, "error": "技能不存在或为内置技能，不可编辑"}

    name = skill_data.get("name", "").strip()
    description = skill_data.get("description", "").strip()
    markdown_body = skill_data.get("markdown", "").strip()
    category = skill_data.get("category", "").strip()

    # Parse existing to preserve other frontmatter
    existing = _parse_skill_frontmatter(md_path) or {}
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
    content = yaml_front + (markdown_body or f"# {name}\n\n{description}\n")
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


@router.post("/batch/delete")
async def batch_delete_skills(payload: dict):
    """批量删除技能."""
    import shutil
    ids: list[str] = payload.get("ids", [])
    if not ids:
        return {"ok": False, "error": "ids 为空"}
    deleted = 0
    for sid in ids:
        for skills_dir in _SKILLS_DIRS:
            for candidate in skills_dir.rglob(sid):
                if candidate.is_dir() and (candidate / "SKILL.md").exists():
                    shutil.rmtree(candidate)
                    deleted += 1
                    break
            else:
                continue
            break
    return {"ok": True, "data": {"deleted": deleted}}
