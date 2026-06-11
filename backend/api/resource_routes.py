"""资源库 REST API — 技能 CRUD / 导入导出 / 工具注册 / 经验导出.

端点前缀：/api/v1/resource
"""

import json
import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional
from zipfile import ZipFile

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resource", tags=["resource"])

# ── 配置 ──
# 技能目录：扫描所有 Hermes profile 的 skills 子目录 + 系统级 ~/.hermes/skills
def _resolve_skills_dirs() -> list[Path]:
    """解析所有可能的技能目录，去重排序."""
    candidates = []

    # 1. 所有 Hermes profile 的 skills 目录（glob /root/.hermes/profiles/*/skills）
    profiles_base = Path("/root/.hermes/profiles")
    if profiles_base.exists():
        for profile_dir in sorted(profiles_base.iterdir()):
            if profile_dir.is_dir():
                sd = profile_dir / "skills"
                if sd.is_dir():
                    candidates.append(sd)

    # 2. 当前 HERMES_HOME （如果有且未在 profiles 中覆盖）
    hh = os.environ.get("HERMES_HOME")
    if hh:
        p = Path(hh) / "skills"
        if p not in candidates:
            candidates.append(p)

    # 3. 系统级 ~/.hermes/skills
    candidates.append(Path("/root/.hermes/skills"))
    candidates.append(Path(os.path.expanduser("~/.hermes/skills")))

    # 去重
    seen = set()
    result = []
    for p in candidates:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result

_SKILLS_DIRS: list[Path] = _resolve_skills_dirs()
# 主写入目录：必须使用当前 HERMES_HOME 的 skills（即 backend profile），
# 不能取 _SKILLS_DIRS[0]（按字母序可能是 architect 等只读 profile）
def _get_write_dir() -> Path:
    """每次调用动态计算写入目录 — 避免模块导入时 HERMES_HOME 未设置."""
    hh = os.environ.get("HERMES_HOME")
    if hh:
        d = Path(hh) / "skills"
    else:
        # 回退：在 _SKILLS_DIRS 中找路径含 "backend" 的
        for sd in _SKILLS_DIRS:
            if "backend" in str(sd).lower() and sd.exists():
                d = sd
                break
        else:
            # 再回退：显式构造 backend profile 路径
            d = Path(os.path.expanduser("~/.hermes/profiles/backend/skills"))
            for sd in _SKILLS_DIRS:
                if sd.exists():
                    d = sd
                    break
    d.mkdir(parents=True, exist_ok=True)
    return d

_HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
_TOOL_REGISTRY_PATH = Path(_HERMES_HOME) / "tools_registry.json"

# 确保工具注册表目录存在
_TOOL_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────────────
# 工具注册表（本地 JSON 文件）
# ─────────────────────────────────────────────────────


def _load_tools_registry() -> dict:
    """加载工具注册表."""
    if _TOOL_REGISTRY_PATH.exists():
        try:
            return json.loads(_TOOL_REGISTRY_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("Corrupt tools_registry.json, resetting")
    return {"tools": {}}


def _save_tools_registry(registry: dict) -> None:
    """保存工具注册表."""
    _TOOL_REGISTRY_PATH.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _write_file_sync(path: Path, content: str) -> None:
    """写入文件并强制 fsync 到磁盘，确保数据真实落盘."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())


# ════════════════════════════════════════════════════════


class CreateSkillRequest(BaseModel):
    name: str = Field(..., description="技能名称")
    description: str = Field("", description="技能描述")
    content: str = Field(..., description="SKILL.md 内容")
    category: str = Field("", description="分类目录名")


class UpdateSkillRequest(BaseModel):
    name: Optional[str] = Field(None, description="技能名称")
    description: Optional[str] = Field(None, description="技能描述")
    content: Optional[str] = Field(None, description="SKILL.md 内容")
    category: Optional[str] = Field(None, description="分类目录名")


class ExportSkillsRequest(BaseModel):
    skill_ids: list[str] = Field(..., description="要导出的技能 ID 列表")


class ImportSkillsRequest(BaseModel):
    """用于解析导入的 JSON 元数据（文件上传走 UploadFile）."""


class RegisterToolRequest(BaseModel):
    name: str = Field(..., description="工具名称")
    description: str = Field(..., description="工具描述")
    endpoint: str = Field("", description="工具端点/命令")
    category: str = Field("", description="工具分类")
    parameters: dict = Field(default_factory=dict, description="参数 schema")


class ExportExperienceRequest(BaseModel):
    trajectory_ids: Optional[list[str]] = Field(None, description="要导出的轨迹 ID（None=全部）")
    format: str = Field("json", description="导出格式: json / zip")


# ════════════════════════════════════════════════════════
# 辅助函数
# ════════════════════════════════════════════════════════


def _list_all_skill_ids() -> list[str]:
    """列出所有已安装的技能 ID（目录名），扫描所有技能目录."""
    ids = set()
    for sd in _SKILLS_DIRS:
        if not sd.exists():
            continue
        for md in sd.rglob("SKILL.md"):
            if md.is_file():
                ids.add(md.parent.name)
    return sorted(ids)


def _skill_dir(skill_id: str) -> Path:
    """返回技能目录路径（扫描所有技能目录）.

    搜索策略：遍历所有 _SKILLS_DIRS，rglob 扫描 SKILL.md，匹配父目录名。
    """
    for sd in _SKILLS_DIRS:
        if not sd.exists():
            continue
        for md in sd.rglob("SKILL.md"):
            if md.is_file() and md.parent.name == skill_id:
                return md.parent
    raise HTTPException(status_code=404, detail={"ok": False, "error": f"Skill not found: {skill_id}"})


def _parse_frontmatter(md_content: str) -> dict:
    """从 SKILL.md 内容中解析 YAML frontmatter."""
    if not md_content.startswith("---"):
        return {}
    parts = md_content.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}


def _build_skill_md(name: str, description: str, category: str, content: str) -> str:
    """构建带 frontmatter 的 SKILL.md."""
    fm = {
        "name": name,
        "description": description,
        "version": "1.0.0",
    }
    if category:
        fm["category"] = category
    fm_yaml = yaml.dump(fm, allow_unicode=True, default_flow_style=False).strip()
    return f"---\n{fm_yaml}\n---\n\n{content}"


def _skill_to_dict(skill_id: str, md_path: Path, scope: str = "builtin") -> dict:
    """将技能文件转为 API 友好字典."""
    content = md_path.read_text(encoding="utf-8")
    fm = _parse_frontmatter(content)
    mtime = md_path.stat().st_mtime
    created_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    return {
        "id": skill_id,
        "name": fm.get("name", skill_id),
        "description": fm.get("description", ""),
        "category": fm.get("category", ""),
        "version": fm.get("version", "1.0.0"),
        "scope": scope,
        "created_at": created_at,
        "file_size": len(content),
    }


# ════════════════════════════════════════════════════════
# GET /api/v1/resource/skills — 列出技能
# ════════════════════════════════════════════════════════


@router.get("/skills")
async def list_resource_skills(user_id: str = Depends(get_current_user)):
    """列出所有技能目录下的技能（多源扫描，去重，按用户隔离）."""
    seen: set[str] = set()
    skills = []
    for sd in _SKILLS_DIRS:
        if not sd.exists():
            continue
        for md in sd.rglob("SKILL.md"):
            if not md.is_file():
                continue
            skill_id = md.parent.name
            if skill_id in seen:
                continue

            # 用户隔离：检查技能路径是否属于其他用户的子目录
            # 路径如 ~/.hermes/skills/{user_id}/... 表示用户自定义技能
            is_user_skill = False
            try:
                rel = md.parent.relative_to(sd)
                parts = rel.parts
                if len(parts) >= 2 and parts[0] != user_id:
                    # 该技能属于其他用户的子目录，跳过
                    continue
                if len(parts) >= 2 and parts[0] == user_id:
                    is_user_skill = True
            except ValueError:
                pass

            seen.add(skill_id)
            scope = "user" if is_user_skill else "builtin"
            skills.append(_skill_to_dict(skill_id, md, scope=scope))
    return {"ok": True, "data": {"skills": skills, "total": len(skills)}}


# ════════════════════════════════════════════════════════
# GET /api/v1/resource/skills/{skill_id} — 获取单个技能
# ════════════════════════════════════════════════════════


@router.get("/skills/{skill_id}")
async def get_resource_skill(skill_id: str, user_id: str = Depends(get_current_user)):
    """获取单个技能的完整内容."""
    skill_dir = _skill_dir(skill_id)
    md_file = skill_dir / "SKILL.md"
    content = md_file.read_text(encoding="utf-8")
    # 确定 scope：检查是否在用户子目录下
    scope = "builtin"
    try:
        write_dir = _get_write_dir()
        md_file.resolve().relative_to((write_dir / user_id).resolve())
        scope = "user"
    except ValueError:
        pass
    return {"ok": True, "data": {"skill": _skill_to_dict(skill_id, md_file, scope=scope), "content": content}}


# ════════════════════════════════════════════════════════
# POST /api/v1/resource/skills  — 创建技能
# ════════════════════════════════════════════════════════


@router.post("/skills", status_code=201)
async def create_resource_skill(request: CreateSkillRequest, user_id: str = Depends(get_current_user)):
    """创建新技能 — 在用户专属目录下创建 ~/.hermes/skills/{user_id}/SKILL.md."""
    # 生成安全 ID
    skill_id = request.name.lower().replace(" ", "-").replace("_", "-")

    # 确定目标目录（用户隔离：所有自定义技能写入 ~/.hermes/skills/{user_id}/...）
    write_dir = _get_write_dir()
    user_skills_base = write_dir / user_id
    if request.category:
        target_dir = user_skills_base / request.category / skill_id
    else:
        target_dir = user_skills_base / skill_id

    if target_dir.exists():
        raise HTTPException(
            status_code=409,
            detail={"ok": False, "error": f"Skill already exists: {skill_id}"},
        )

    target_dir.mkdir(parents=True, exist_ok=False)

    md_content = _build_skill_md(
        name=request.name,
        description=request.description,
        category=request.category,
        content=request.content,
    )

    md_file = target_dir / "SKILL.md"
    _write_file_sync(md_file, md_content)

    logger.info(f"Skill created: {skill_id} at {target_dir}")
    return {
        "ok": True,
        "data": _skill_to_dict(skill_id, md_file, scope="user"),
    }


# ════════════════════════════════════════════════════════
# PUT /api/v1/resource/skills/{skill_id} — 更新技能
# ════════════════════════════════════════════════════════


@router.put("/skills/{skill_id}")
async def update_resource_skill(skill_id: str, request: UpdateSkillRequest, user_id: str = Depends(get_current_user)):
    """更新技能 — 可更新 name/description/content/category.

    如果更新 category，会移动目录。
    """
    skill_dir = _skill_dir(skill_id)
    md_file = skill_dir / "SKILL.md"

    # 读取现有内容 + frontmatter
    current_content = md_file.read_text(encoding="utf-8")
    fm = _parse_frontmatter(current_content)

    # 提取 body（frontmatter 之后的内容，保留原始空白）
    body = ""
    if current_content.startswith("---"):
        parts = current_content.split("---", 2)
        if len(parts) >= 3:
            body = parts[2]  # 不去 strip，保留正文原有格式

    new_name = request.name if request.name is not None else fm.get("name", skill_id)
    new_desc = request.description if request.description is not None else fm.get("description", "")
    new_category = request.category if request.category is not None else fm.get("category", "")
    new_body = request.content if request.content is not None else body

    # 处理改名 / 改分类 → 目录移动
    new_skill_id = new_name.lower().replace(" ", "-").replace("_", "-")
    write_dir = _get_write_dir()
    user_skills_base = write_dir / user_id
    if new_category:
        new_target_dir = user_skills_base / new_category / new_skill_id
    else:
        new_target_dir = user_skills_base / new_skill_id

    if new_target_dir != skill_dir:
        if new_target_dir.exists():
            raise HTTPException(
                status_code=409,
                detail={"ok": False, "error": f"Target skill already exists: {new_skill_id}"},
            )
        new_target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(skill_dir), str(new_target_dir))
        md_file = new_target_dir / "SKILL.md"
        skill_id = new_skill_id

    # 写入新内容（使用 fsync 确保落盘）
    new_md = _build_skill_md(new_name, new_desc, new_category, new_body)
    _write_file_sync(md_file, new_md)

    logger.info(f"Skill updated: {skill_id}")
    return {"ok": True, "data": _skill_to_dict(skill_id, md_file, scope="user")}


# ════════════════════════════════════════════════════════
# DELETE /api/v1/resource/skills/{skill_id} — 删除技能
# ════════════════════════════════════════════════════════


class BatchDeleteRequest(BaseModel):
    skill_ids: list[str] = Field(..., description="要删除的技能 ID 列表")


def _delete_skill_by_id(skill_id: str, user_id: str = "default") -> bool:
    """删除用户的技能 — 仅从用户专属目录删除。返回是否成功."""
    write_dir = _get_write_dir()
    user_base = write_dir / user_id

    # 扫描用户目录及其子目录
    if user_base.exists():
        for md in user_base.rglob("SKILL.md"):
            if md.is_file() and md.parent.name == skill_id:
                shutil.rmtree(str(md.parent))
                logger.info(f"Skill deleted: {skill_id} from user={user_id}")
                return True
    return False


@router.delete("/skills/{skill_id}")
async def delete_resource_skill(skill_id: str, user_id: str = Depends(get_current_user)):
    """删除技能 — 移除整个技能目录（仅限用户自有技能）."""
    if not _delete_skill_by_id(skill_id, user_id=user_id):
        raise HTTPException(status_code=404, detail={"ok": False, "error": f"Skill not found: {skill_id}"})
    return {"ok": True, "data": {"deleted": skill_id}}


@router.post("/skills/batch-delete")
async def batch_delete_resource_skills(request: BatchDeleteRequest, user_id: str = Depends(get_current_user)):
    """批量删除技能.

    请求体: {"skill_ids": ["skill-a", "skill-b", ...]}
    返回: {"ok": true, "data": {"deleted": [...], "not_found": [...], "total": N}}
    """
    deleted: list[str] = []
    not_found: list[str] = []
    for sid in request.skill_ids:
        if _delete_skill_by_id(sid, user_id=user_id):
            deleted.append(sid)
        else:
            not_found.append(sid)
    logger.info(f"Batch delete: {len(deleted)} deleted, {len(not_found)} not found")
    return {
        "ok": True,
        "data": {"deleted": deleted, "not_found": not_found, "total": len(request.skill_ids)},
    }


# ════════════════════════════════════════════════════════
# POST /api/v1/resource/skills/export — 导出技能
# ════════════════════════════════════════════════════════


@router.post("/skills/export")
async def export_resource_skills(request: ExportSkillsRequest):
    """导出技能 — 单个/批量打包为 ZIP 下载.

    请求体: {"skill_ids": ["skill-a", "skill-b"]}
    返回: ZIP 文件流
    """
    if not request.skill_ids:
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "error": "skill_ids is required"},
        )

    # 验证所有技能存在
    skill_dirs: list[tuple[str, Path]] = []
    for sid in request.skill_ids:
        skill_dirs.append((sid, _skill_dir(sid)))

    # 打包 ZIP
    zip_buffer = BytesIO()
    with ZipFile(zip_buffer, "w") as zf:
        for sid, sdir in skill_dirs:
            for file_path in sdir.rglob("*"):
                if file_path.is_file():
                    arcname = f"{sid}/{file_path.relative_to(sdir)}"
                    zf.write(file_path, arcname)

    zip_buffer.seek(0)
    filename = f"skills-export-{len(request.skill_ids)}-{uuid.uuid4().hex[:8]}.zip"

    logger.info(f"Skills exported: {request.skill_ids}")
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ════════════════════════════════════════════════════════
# POST /api/v1/resource/skills/import — 导入技能
# ════════════════════════════════════════════════════════


@router.post("/skills/import")
async def import_resource_skills(file: UploadFile):
    """导入技能 — 上传 .md 或 .json(批量) 或 .zip.

    文件类型检测：
    - .md: 单个技能，从文件名推断 skill_id，从内容解析 frontmatter
    - .json: 批量导入 [{name, description, content, category?}, ...]
    - .zip: 解压后按目录结构导入
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail={"ok": False, "error": "No file provided"})

    raw = await file.read()
    filename = file.filename.lower()
    imported: list[str] = []

    if filename.endswith(".zip"):
        # ZIP 批量导入
        zip_buffer = BytesIO(raw)
        with ZipFile(zip_buffer, "r") as zf:
            for member in zf.namelist():
                if member.endswith("/") or "__MACOSX" in member:
                    continue
                parts = member.split("/")
                if len(parts) < 2:
                    continue
                skill_id = parts[0]
                rel_path = "/".join(parts[1:])
                target = _get_write_dir() / skill_id / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(member))
                if skill_id not in imported:
                    imported.append(skill_id)

    elif filename.endswith(".json"):
        # JSON 批量导入
        data = json.loads(raw.decode("utf-8"))
        if isinstance(data, dict):
            data = [data]
        for item in data:
            skill_id = item["name"].lower().replace(" ", "-").replace("_", "-")
            category = item.get("category", "")
            if category:
                target_dir = _get_write_dir() / category / skill_id
            else:
                target_dir = _get_write_dir() / skill_id
            target_dir.mkdir(parents=True, exist_ok=True)
            md_content = _build_skill_md(
                name=item["name"],
                description=item.get("description", ""),
                category=category,
                content=item.get("content", ""),
            )
            _write_file_sync(target_dir / "SKILL.md", md_content)
            imported.append(skill_id)

    elif filename.endswith(".md"):
        # 单个 .md 导入
        content = raw.decode("utf-8")
        fm = _parse_frontmatter(content)
        name = fm.get("name", file.filename.replace(".md", ""))
        skill_id = name.lower().replace(" ", "-").replace("_", "-")
        category = fm.get("category", "")
        if category:
            target_dir = _get_write_dir() / category / skill_id
        else:
            target_dir = _get_write_dir() / skill_id
        target_dir.mkdir(parents=True, exist_ok=True)
        _write_file_sync(target_dir / "SKILL.md", content)
        imported.append(skill_id)

    else:
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "error": f"Unsupported file type: {file.filename}. Supported: .md, .json, .zip"},
        )

    logger.info(f"Skills imported: {imported}")
    return {"ok": True, "data": {"imported": imported, "count": len(imported)}}


# ════════════════════════════════════════════════════════
# POST /api/v1/resource/skills/import/json — JSON 批量导入
# ════════════════════════════════════════════════════════


@router.post("/skills/import/json")
async def import_resource_skills_json(request: dict):
    """通过 JSON body 批量导入技能.

    请求体: {"skills": [{"name": "...", "description": "...", "content": "..."}, ...]}
    """
    items = request.get("skills", [])
    if not items:
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "error": "Missing 'skills' array in request body"},
        )

    imported: list[str] = []
    for item in items:
        name = item.get("name", "unnamed")
        skill_id = name.lower().replace(" ", "-").replace("_", "-")
        category = item.get("category", "")
        if category:
            target_dir = _get_write_dir() / category / skill_id
        else:
            target_dir = _get_write_dir() / skill_id
        target_dir.mkdir(parents=True, exist_ok=True)
        md_content = _build_skill_md(
            name=name,
            description=item.get("description", ""),
            category=category,
            content=item.get("content", ""),
        )
        _write_file_sync(target_dir / "SKILL.md", md_content)
        imported.append(skill_id)

    return {"ok": True, "data": {"imported": imported, "count": len(imported)}}


# ════════════════════════════════════════════════════════
# GET /api/v1/resource/tools — 列出工具
# ════════════════════════════════════════════════════════


@router.get("/tools")
async def list_resource_tools(user_id: str = Depends(get_current_user)):
    """列出当前用户的工具注册表."""
    registry = _load_tools_registry()
    all_tools = registry.get("tools", {})
    user_tools = list(all_tools.get(user_id, {}).values())
    return {"ok": True, "data": {"tools": user_tools, "total": len(user_tools)}}


# ════════════════════════════════════════════════════════
# POST /api/v1/resource/tools — 注册新工具
# ════════════════════════════════════════════════════════


@router.post("/tools", status_code=201)
async def register_resource_tool(request: RegisterToolRequest, user_id: str = Depends(get_current_user)):
    """注册新工具到用户专属工具注册表."""
    registry = _load_tools_registry()
    all_tools = registry.setdefault("tools", {})
    user_tools = all_tools.setdefault(user_id, {})

    tool_id = str(uuid.uuid4())
    tool_entry = {
        "id": tool_id,
        "name": request.name,
        "description": request.description,
        "endpoint": request.endpoint,
        "category": request.category,
        "parameters": request.parameters,
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    user_tools[tool_id] = tool_entry
    _save_tools_registry(registry)

    logger.info(f"Tool registered: {request.name} (id={tool_id}, user={user_id})")
    return {"ok": True, "data": tool_entry}


# ════════════════════════════════════════════════════════
# DELETE /api/v1/resource/tools/{tool_id} — 删除工具
# ════════════════════════════════════════════════════════


@router.delete("/tools/{tool_id}")
async def delete_resource_tool(tool_id: str, user_id: str = Depends(get_current_user)):
    """从当前用户的工具注册表中删除工具."""
    registry = _load_tools_registry()
    all_tools = registry.get("tools", {})
    user_tools = all_tools.get(user_id, {})

    if tool_id not in user_tools:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "error": f"Tool not found: {tool_id}"},
        )

    deleted = user_tools.pop(tool_id)
    _save_tools_registry(registry)

    logger.info(f"Tool deleted: {deleted['name']} (id={tool_id}, user={user_id})")
    return {"ok": True, "data": {"deleted": tool_id}}


# ════════════════════════════════════════════════════════
# POST /api/v1/resource/experience/export — 经验导出
# ════════════════════════════════════════════════════════


@router.post("/experience/export")
async def export_resource_experience(request: ExportExperienceRequest):
    """导出经验轨迹为 JSON 或 ZIP.

    请求体: {"trajectory_ids": ["id1","id2"], "format": "json"}
    如果 trajectory_ids 为空，导出全部。
    """
    from backend.experience.recorder import get_recorder

    recorder = get_recorder()

    # 确定要导出的轨迹
    if request.trajectory_ids:
        trajectory_ids = request.trajectory_ids
    else:
        summaries = recorder.list_trajectories(limit=10000)
        trajectory_ids = [s.id for s in summaries]

    if not trajectory_ids:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "error": "No trajectories found"},
        )

    # 获取详情
    details = []
    for tid in trajectory_ids:
        detail = recorder.get_trajectory(tid)
        if detail is None:
            continue
        details.append({
            "id": detail.id,
            "session_id": detail.session_id,
            "session_title": detail.session_title,
            "turns": [
                {
                    "turn_index": t.turn_index,
                    "llm_response_chunk": t.llm_response_chunk,
                    "token_usage": t.token_usage,
                }
                for t in detail.turns
            ],
            "outcome": {
                "success": detail.outcome.success,
                "total_tokens": detail.outcome.total_tokens,
                "wall_time_ms": detail.outcome.wall_time_ms,
                "user_cancelled": detail.outcome.user_cancelled,
            },
            "created_at": detail.created_at,
            "feedback": [
                {
                    "id": fb.id,
                    "rating": fb.rating,
                    "note": fb.note,
                    "status": fb.status,
                    "created_at": fb.created_at,
                }
                for fb in detail.feedback
            ],
        })

    if request.format == "json":
        export_json = json.dumps({"trajectories": details}, ensure_ascii=False, indent=2)
        return {
            "ok": True,
            "data": {
                "exported_count": len(details),
                "json": export_json,
            },
        }

    elif request.format == "zip":
        zip_buffer = BytesIO()
        with ZipFile(zip_buffer, "w") as zf:
            # 整体 JSON
            zf.writestr(
                "trajectories.json",
                json.dumps({"trajectories": details}, ensure_ascii=False, indent=2),
            )
            # 每个轨迹一个文件
            for d in details:
                zf.writestr(
                    f"trajectories/{d['id']}.json",
                    json.dumps(d, ensure_ascii=False, indent=2),
                )

        zip_buffer.seek(0)
        filename = f"experience-export-{len(details)}-{uuid.uuid4().hex[:8]}.zip"
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    else:
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "error": f"Unsupported format: {request.format}. Use json or zip"},
        )
