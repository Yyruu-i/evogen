""""Tools REST API — 从 Hermes tools 系统获取工具列表 + 工具仓库版本管理."""

import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolParam(BaseModel):
    name: str
    type: str
    description: str = ""
    required: bool = False


class ToolDef(BaseModel):
    name: str
    description: str
    parameters: list[ToolParam] = []
    toolset: str = ""
    requires_env: list[str] = []
    call_count: int = 0
    enabled: bool = True


def _list_hermes_tools() -> list[dict]:
    """调用 hermes CLI 获取工具列表，失败时返回空列表."""
    try:
        result = subprocess.run(
            ["hermes", "tools", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if isinstance(data, dict) and "tools" in data:
                return data["tools"]
            if isinstance(data, list):
                return data
    except FileNotFoundError:
        logger.info("hermes CLI not found, using static tool list")
    except (json.JSONDecodeError, subprocess.TimeoutExpired) as e:
        logger.warning(f"Failed to get tools from hermes CLI: {e}")

    # Fallback: static tool list from Hermes toolset definitions
    return _static_tool_list()


def _static_tool_list() -> list[dict]:
    """Static tool list when hermes CLI is not available."""
    return [
        {"name": "browser_navigate", "description": "在浏览器中导航到指定URL", "toolset": "browser", "requires_env": [], "parameters": [{"name": "url", "type": "string", "description": "目标URL", "required": True}]},
        {"name": "browser_click", "description": "通过元素引用ID点击元素", "toolset": "browser", "requires_env": [], "parameters": [{"name": "ref", "type": "string", "description": "元素引用ID", "required": True}]},
        {"name": "browser_snapshot", "description": "获取页面无障碍树快照", "toolset": "browser", "requires_env": [], "parameters": []},
        {"name": "browser_console", "description": "获取控制台输出或执行JS代码", "toolset": "browser", "requires_env": [], "parameters": [{"name": "expression", "type": "string", "description": "要执行的JS表达式", "required": False}]},
        {"name": "browser_vision", "description": "页面截图并进行视觉分析", "toolset": "browser", "requires_env": [], "parameters": [{"name": "question", "type": "string", "description": "分析问题", "required": True}]},
        {"name": "terminal", "description": "执行Shell命令", "toolset": "terminal", "requires_env": [], "parameters": [{"name": "command", "type": "string", "description": "Shell命令", "required": True}, {"name": "background", "type": "boolean", "description": "是否后台运行", "required": False}]},
        {"name": "read_file", "description": "读取文本文件（带行号）", "toolset": "file", "requires_env": [], "parameters": [{"name": "path", "type": "string", "description": "文件路径", "required": True}]},
        {"name": "write_file", "description": "写入内容到文件", "toolset": "file", "requires_env": [], "parameters": [{"name": "path", "type": "string", "description": "文件路径", "required": True}, {"name": "content", "type": "string", "description": "写入内容", "required": True}]},
        {"name": "search_files", "description": "搜索文件内容或查找文件", "toolset": "file", "requires_env": [], "parameters": [{"name": "pattern", "type": "string", "description": "搜索模式", "required": True}]},
        {"name": "patch", "description": "精准查找替换编辑文件", "toolset": "file", "requires_env": [], "parameters": [{"name": "path", "type": "string", "description": "文件路径", "required": True}, {"name": "old_string", "type": "string", "description": "查找文本", "required": True}, {"name": "new_string", "type": "string", "description": "替换文本", "required": True}]},
        {"name": "web_search", "description": "通过DuckDuckGo搜索互联网", "toolset": "web", "requires_env": [], "parameters": [{"name": "query", "type": "string", "description": "搜索关键词", "required": True}]},
        {"name": "web_extract", "description": "提取URL页面内容", "toolset": "web", "requires_env": [], "parameters": [{"name": "url", "type": "string", "description": "要提取的URL", "required": True}]},
        {"name": "memory", "description": "保存跨会话持久记忆", "toolset": "memory", "requires_env": [], "parameters": [{"name": "action", "type": "string", "description": "add/replace/remove", "required": True}, {"name": "target", "type": "string", "description": "memory/user", "required": True}, {"name": "content", "type": "string", "description": "条目内容", "required": True}]},
        {"name": "session_search", "description": "搜索历史会话记录", "toolset": "session_search", "requires_env": [], "parameters": [{"name": "query", "type": "string", "description": "搜索关键词", "required": True}]},
        {"name": "delegate_task", "description": "派生子智能体并行工作", "toolset": "delegation", "requires_env": [], "parameters": [{"name": "goal", "type": "string", "description": "子智能体任务目标", "required": True}]},
        {"name": "cronjob", "description": "管理定时计划任务", "toolset": "cronjob", "requires_env": [], "parameters": [{"name": "action", "type": "string", "description": "create/list/update/pause/resume/remove/run", "required": True}]},
        {"name": "execute_code", "description": "运行Python脚本（可用工具API）", "toolset": "code_execution", "requires_env": [], "parameters": [{"name": "code", "type": "string", "description": "要执行的Python代码", "required": True}]},
        {"name": "clarify", "description": "向用户提出澄清问题", "toolset": "clarify", "requires_env": [], "parameters": [{"name": "question", "type": "string", "description": "要问的问题", "required": True}]},
        {"name": "send_message", "description": "发送消息到已连接平台", "toolset": "messaging", "requires_env": [], "parameters": [{"name": "target", "type": "string", "description": "目标接收方", "required": True}, {"name": "message", "type": "string", "description": "消息内容", "required": True}]},
        {"name": "todo", "description": "管理当前会话任务列表", "toolset": "todo", "requires_env": [], "parameters": [{"name": "todos", "type": "array", "description": "任务项", "required": False}]},
        {"name": "vision_analyze", "description": "加载图片进行视觉分析", "toolset": "vision", "requires_env": [], "parameters": [{"name": "image_url", "type": "string", "description": "图片URL或路径", "required": True}, {"name": "question", "type": "string", "description": "关于图片的问题", "required": True}]},
        {"name": "text_to_speech", "description": "将文本转换为语音音频", "toolset": "tts", "requires_env": [], "parameters": [{"name": "text", "type": "string", "description": "要转换的文本", "required": True}]},
        {"name": "skill_view", "description": "加载技能完整内容", "toolset": "skills", "requires_env": [], "parameters": [{"name": "name", "type": "string", "description": "技能名称", "required": True}]},
        {"name": "skill_manage", "description": "创建/更新/删除技能", "toolset": "skills", "requires_env": [], "parameters": [{"name": "action", "type": "string", "description": "create/patch/edit/delete...", "required": True}, {"name": "name", "type": "string", "description": "技能名称", "required": True}]},
        {"name": "feishu_doc_read", "description": "读取飞书文档内容", "toolset": "feishu_doc", "requires_env": ["FEISHU_APP_ID"], "parameters": [{"name": "doc_token", "type": "string", "description": "文档token", "required": True}]},
        {"name": "feishu_drive_add_comment", "description": "在飞书文档中添加评论", "toolset": "feishu_drive", "requires_env": ["FEISHU_APP_ID"], "parameters": [{"name": "file_token", "type": "string", "description": "文件token", "required": True}, {"name": "content", "type": "string", "description": "评论内容", "required": True}]},
        # ── 安全扫描工具 ──
        {"name": "port_scan", "description": "端口扫描 — 使用 nmap 扫描目标 IP/域名的开放端口和服务", "toolset": "security", "requires_env": [], "priority": 1, "fallback": "vuln_scan", "parameters": [{"name": "target", "type": "string", "description": "目标 IP 或域名", "required": True}, {"name": "ports", "type": "string", "description": "端口范围，如 22,80,443 或 1-1000（默认 1-1000）", "required": False}, {"name": "arguments", "type": "string", "description": "额外 nmap 参数，如 -sV（版本检测） -sC（默认脚本）", "required": False}]},
        {"name": "vuln_scan", "description": "漏洞扫描 — 使用 Nuclei 对目标进行漏洞检测", "toolset": "security", "requires_env": [], "priority": 2, "fallback": "port_scan", "parameters": [{"name": "target", "type": "string", "description": "目标 URL 或 IP", "required": True}, {"name": "severity", "type": "string", "description": "严重级别过滤，如 critical,high,medium（默认 critical,high）", "required": False}, {"name": "templates", "type": "string", "description": "指定 Nuclei 模板路径或类型", "required": False}]},
    ]


# ── In-memory tool storage ──
_tool_counts: dict[str, int] = {}
_custom_tools: dict[str, list[dict]] = {}  # user_id -> tools


@router.get("")
async def list_tools(toolset: Optional[str] = None, user_id: str = Depends(get_current_user)):
    """获取所有可用工具列表."""
    try:
        base_tools = _list_hermes_tools()
    except Exception as e:
        logger.error(f"Failed to list tools: {e}", exc_info=True)
        base_tools = []

    # Merge custom tools (dedup by name)
    user_tools = _custom_tools.get(user_id, [])
    base_names = {t["name"] for t in base_tools}
    merged = list(base_tools)
    for ct in user_tools:
        if ct["name"] not in base_names:
            merged.append(ct)

    # Apply toolset filter
    if toolset:
        merged = [t for t in merged if t.get("toolset") == toolset]

    # Merge call counts
    for t in merged:
        t["call_count"] = _tool_counts.get(t["name"], 0)

    return {
        "ok": True,
        "data": {
            "tools": merged,
            "total": len(merged),
        },
    }


@router.post("")
@router.post("")
async def add_tool(tool: dict, user_id: str = Depends(get_current_user)):
    """注册新工具."""
    name = tool.get("name", "").strip()
    if not name:
        raise HTTPException(400, "工具名称为必填项")

    # Build tool entry
    entry = {
        "name": name,
        "description": tool.get("description", ""),
        "parameters": tool.get("parameters", []),
        "toolset": tool.get("toolset", ""),
        "requires_env": tool.get("requires_env", []),
        "command": tool.get("command", ""),
        "enabled": True,
    }

    # Remove existing custom tool with same name (per-user)
    user_tools = _custom_tools.setdefault(user_id, [])
    user_tools[:] = [t for t in user_tools if t["name"] != name]
    user_tools.append(entry)
    _tool_counts[name] = 0

    return {"ok": True, "data": entry}


@router.delete("/{name}")
async def delete_tool(name: str, user_id: str = Depends(get_current_user)):
    """删除工具."""
    user_tools = _custom_tools.get(user_id, [])
    user_tools[:] = [t for t in user_tools if t["name"] != name]
    _tool_counts.pop(name, None)
    return {"ok": True}


# ── 智能更新能力（工具仓库版本管理）──

_TOOLS_REPO_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "tools_repo.json",
)
_TOOLS_REPO: dict = {
    "version": "1.0.0",
    "tools": [],
    "changelog": [],
    "created_at": datetime.now(timezone.utc).isoformat(),
    "updated_at": datetime.now(timezone.utc).isoformat(),
}
_TOOLS_BACKUP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "tools_backups",
)


def _load_tools_repo():
    """加载持久化的工具仓库状态."""
    global _TOOLS_REPO
    try:
        if os.path.exists(_TOOLS_REPO_FILE):
            with open(_TOOLS_REPO_FILE, "r") as f:
                _TOOLS_REPO = json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load tools repo: {e}")


def _save_tools_repo():
    """持久化工具仓库状态."""
    try:
        os.makedirs(os.path.dirname(_TOOLS_REPO_FILE), exist_ok=True)
        with open(_TOOLS_REPO_FILE, "w") as f:
            json.dump(_TOOLS_REPO, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save tools repo: {e}")


def _backup_current_repo():
    """备份当前仓库状态用于回滚."""
    try:
        os.makedirs(_TOOLS_BACKUP_DIR, exist_ok=True)
        version = _TOOLS_REPO.get("version", "0.0.0")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(_TOOLS_BACKUP_DIR, f"tools_v{version}_{timestamp}.json")
        with open(backup_file, "w") as f:
            json.dump(_TOOLS_REPO, f, ensure_ascii=False, indent=2)
        logger.info(f"Tools repo backed up to {backup_file}")
        return backup_file
    except Exception as e:
        logger.warning(f"Failed to backup tools repo: {e}")
        return None


# 启动时加载
_load_tools_repo()


@router.get("/repo/status")
async def get_tools_repo_status():
    """获取工具仓库状态（版本号、工具数量、更新时间等）."""
    return {
        "ok": True,
        "data": {
            "version": _TOOLS_REPO.get("version", "1.0.0"),
            "tool_count": len(_TOOLS_REPO.get("tools", [])),
            "changelog_count": len(_TOOLS_REPO.get("changelog", [])),
            "updated_at": _TOOLS_REPO.get("updated_at", ""),
            "backup_dir": _TOOLS_BACKUP_DIR,
        },
    }


@router.post("/repo/update")
async def update_tools_repo(update_data: dict):
    """更新工具仓库：批量下发更新包，增量更新.

    支持两种更新模式：
    1. 全量更新: {"mode": "full", "tools": [...], "version": "1.1.0", "changelog": [...]}
    2. 增量更新: {"mode": "incremental", "changes": [{"action": "add|update|remove", "tool": {...}}], "version": "1.1.0"}
    """
    mode = update_data.get("mode", "full")
    new_version = update_data.get("version", "")

    if not new_version:
        return {"ok": False, "error": "缺少版本号"}

    # 比较版本号，确认是否需要更新
    current_version = _TOOLS_REPO.get("version", "0.0.0")
    if _version_compare(new_version, current_version) <= 0:
        return {"ok": False, "error": f"版本 {new_version} 不高于当前版本 {current_version}，无需更新"}

    # 备份当前状态
    _backup_current_repo()

    # 全量更新
    if mode == "full":
        tools = update_data.get("tools", [])
        if not tools:
            return {"ok": False, "error": "全量更新需要提供 tools 列表"}
        _TOOLS_REPO["tools"] = tools
        _TOOLS_REPO["version"] = new_version

    # 增量更新
    elif mode == "incremental":
        changes = update_data.get("changes", [])
        if not changes:
            return {"ok": False, "error": "增量更新需要提供 changes 列表"}

        existing_tools = {t["name"]: t for t in _TOOLS_REPO.get("tools", [])}
        for change in changes:
            action = change.get("action", "")
            tool = change.get("tool", {})

            if action == "add":
                name = tool.get("name", "")
                if name and name not in existing_tools:
                    _TOOLS_REPO["tools"].append(tool)
                    existing_tools[name] = tool
            elif action == "update":
                name = tool.get("name", "")
                if name and name in existing_tools:
                    # 仅更新提供的字段（增量更新）
                    existing_tools[name].update(tool)
            elif action == "remove":
                name = tool.get("name", "")
                _TOOLS_REPO["tools"] = [t for t in _TOOLS_REPO["tools"] if t.get("name") != name]

        _TOOLS_REPO["version"] = new_version

    else:
        return {"ok": False, "error": f"未知更新模式: {mode}"}

    # 记录变更日志
    changelog_entry = {
        "version": new_version,
        "previous_version": current_version,
        "mode": mode,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "changes": update_data.get("changelog", update_data.get("changes", [])),
    }
    _TOOLS_REPO.setdefault("changelog", []).append(changelog_entry)
    _TOOLS_REPO["updated_at"] = datetime.now(timezone.utc).isoformat()

    _save_tools_repo()

    return {
        "ok": True,
        "data": {
            "version": new_version,
            "previous_version": current_version,
            "mode": mode,
            "tool_count": len(_TOOLS_REPO["tools"]),
            "changelog": changelog_entry,
        },
    }


@router.get("/repo/changelog")
async def get_tools_changelog(limit: int = 10):
    """获取工具版本更新日志."""
    logs = _TOOLS_REPO.get("changelog", [])
    logs = logs[-limit:]
    return {"ok": True, "data": {"entries": logs, "total": len(logs)}}


@router.get("/repo/backups")
async def list_tools_backups():
    """列出可用的备份版本."""
    backups = []
    try:
        os.makedirs(_TOOLS_BACKUP_DIR, exist_ok=True)
        for f in sorted(os.listdir(_TOOLS_BACKUP_DIR), reverse=True):
            if f.endswith(".json"):
                path = os.path.join(_TOOLS_BACKUP_DIR, f)
                size = os.path.getsize(path)
                backups.append({"file": f, "size": size, "path": path})
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "data": {"backups": backups, "total": len(backups)}}


@router.post("/repo/rollback/{version}")
async def rollback_tools(version: str):
    """按需回滚到指定版本.

    从 backup 目录中查找匹配的备份文件并恢复。
    也支持回滚到版本号。
    """
    # 查找匹配版本号的备份
    try:
        os.makedirs(_TOOLS_BACKUP_DIR, exist_ok=True)
        target_file = None
        for f in sorted(os.listdir(_TOOLS_BACKUP_DIR), reverse=True):
            if f.endswith(".json") and version in f:
                target_file = os.path.join(_TOOLS_BACKUP_DIR, f)
                break

        if not target_file:
            return {"ok": False, "error": f"未找到版本 {version} 的备份"}

        with open(target_file, "r") as f:
            backup_data = json.load(f)

        # 备份当前状态
        _backup_current_repo()

        # 回滚
        current_version = _TOOLS_REPO.get("version", "0.0.0")
        _TOOLS_REPO.clear()
        _TOOLS_REPO.update(backup_data)
        _TOOLS_REPO["updated_at"] = datetime.now(timezone.utc).isoformat()

        changelog_entry = {
            "version": _TOOLS_REPO["version"],
            "previous_version": current_version,
            "mode": "rollback",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "changes": [f"从 {current_version} 回滚到 {_TOOLS_REPO['version']}"],
        }
        _TOOLS_REPO.setdefault("changelog", []).append(changelog_entry)

        _save_tools_repo()

        return {
            "ok": True,
            "data": {
                "version": _TOOLS_REPO["version"],
                "previous_version": current_version,
                "tool_count": len(_TOOLS_REPO.get("tools", [])),
            },
        }

    except Exception as e:
        return {"ok": False, "error": f"回滚失败: {e}"}


# ── 智能版本更新 ──


def _get_git_version() -> str:
    """获取当前 Git 版本的 tag 或 commit hash."""
    try:
        r = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            capture_output=True, text=True, timeout=5,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _check_remote_version() -> dict:
    """检查远程仓库最新版本信息."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        # 获取远程 tags — 注入 Windows/WSL 代理环境变量以兼容 TUN 模式
        env = os.environ.copy()
        for var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
            if var in env and env[var]:
                break
        else:
            # 常见 Clash/V2ray 代理端口，仅用于 git，不影响其他请求
            for port in (7897, 7890, 10809, 1080, 7891):
                test_env = env.copy()
                test_env["https_proxy"] = f"http://127.0.0.1:{port}"
                test_env["http_proxy"] = f"http://127.0.0.1:{port}"
                try:
                    r = subprocess.run(
                        ["git", "ls-remote", "--tags", "origin"],
                        capture_output=True, text=True, timeout=5,
                        cwd=project_root, env=test_env,
                    )
                    if r.returncode == 0 and r.stdout.strip():
                        env = test_env
                        break
                except subprocess.TimeoutExpired:
                    continue
        r = subprocess.run(
            ["git", "ls-remote", "--tags", "origin"],
            capture_output=True, text=True, timeout=10,
            cwd=project_root, env=env,
        )
        if r.returncode != 0:
            err_msg = r.stderr.strip()[:100] if r.stderr.strip() else "连接远程仓库超时（10s）"
            return {"available": False, "error": f"检查更新失败: {err_msg}"}
        # 解析最新 tag
        tags = []
        for line in r.stdout.strip().split("\n"):
            if line:
                parts = line.split("/")
                tag = parts[-1] if parts else ""
                if tag:
                    tags.append(tag)
        tags.sort(key=lambda t: (
            [int(x) for x in t.replace("v", "").split(".") if x.isdigit()]
            if t.replace("v", "").split(".") and all(x.isdigit() for x in t.replace("v", "").split("."))
            else [0]
        ), reverse=True)
        latest_tag = tags[-1] if tags else ""
        current = _get_git_version()
        return {
            "available": bool(latest_tag) and latest_tag != current,
            "current_version": current,
            "latest_version": latest_tag,
            "error": None,
        }
    except Exception as e:
        return {"available": False, "error": str(e)}


@router.post("/update")
async def trigger_update():
    """检查工具版本并执行更新（git pull + 刷新工具列表）.

    返回更新前后的版本号对比和变更日志。
    """
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    before = _get_git_version()

    # 检查远程是否有更新
    remote_info = _check_remote_version()
    if remote_info.get("error"):
        return {"ok": False, "error": remote_info["error"]}
    if not remote_info.get("available"):
        return {
            "ok": True,
            "data": {
                "updated": False,
                "message": "当前已是最新版本",
                "before": before,
                "after": before,
                "changelog": [],
            },
        }

    try:
        # 执行 git pull
        r = subprocess.run(
            ["git", "pull", "origin", "master"],
            capture_output=True, text=True, timeout=30,
            cwd=project_root,
        )
        if r.returncode != 0:
            return {"ok": False, "error": f"更新失败: {r.stderr[:300]}"}

        after = _get_git_version()

        # 获取更新日志（最近的 commit 记录）
        log_r = subprocess.run(
            ["git", "log", f"{before}..{after}", "--oneline", "--no-decorate"],
            capture_output=True, text=True, timeout=5,
            cwd=project_root,
        )
        changelog = []
        if log_r.returncode == 0 and log_r.stdout.strip():
            changelog = [line.strip() for line in log_r.stdout.strip().split("\n") if line.strip()]

        # 刷新工具列表（重新加载 hermes tools）
        # 清理静态变量缓存，下次调用会重新获取
        _TOOLS_REPO.pop("_tools_cache", None)

        return {
            "ok": True,
            "data": {
                "updated": True,
                "message": f"更新成功: {before} → {after}",
                "before": before,
                "after": after,
                "changelog": changelog,
                "git_output": r.stdout[:1000],
            },
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "更新超时（30秒），请稍后重试"}
    except Exception as e:
        return {"ok": False, "error": f"更新异常: {e}"}


def _version_compare(v1: str, v2: str) -> int:
    """比较两个语义版本号。v1 > v2 返回正数，v1 < v2 返回负数."""
    try:
        p1 = [int(x) for x in v1.replace("v", "").split(".")]
        p2 = [int(x) for x in v2.replace("v", "").split(".")]
        # 补齐到相同长度
        while len(p1) < len(p2):
            p1.append(0)
        while len(p2) < len(p1):
            p2.append(0)
        for a, b in zip(p1, p2):
            if a != b:
                return a - b
        return 0
    except (ValueError, AttributeError):
        return 0 if v1 == v2 else (1 if v1 > v2 else -1)
