"""Tools REST API — 从 Hermes tools 系统获取工具列表."""

import json
import logging
import subprocess
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
        {"name": "port_scan", "description": "端口扫描 — 使用 nmap 扫描目标 IP/域名的开放端口和服务", "toolset": "security", "requires_env": [], "parameters": [{"name": "target", "type": "string", "description": "目标 IP 或域名", "required": True}, {"name": "ports", "type": "string", "description": "端口范围，如 22,80,443 或 1-1000（默认 1-1000）", "required": False}, {"name": "arguments", "type": "string", "description": "额外 nmap 参数，如 -sV（版本检测） -sC（默认脚本）", "required": False}]},
        {"name": "vuln_scan", "description": "漏洞扫描 — 使用 Nuclei 对目标进行漏洞检测", "toolset": "security", "requires_env": [], "parameters": [{"name": "target", "type": "string", "description": "目标 URL 或 IP", "required": True}, {"name": "severity", "type": "string", "description": "严重级别过滤，如 critical,high,medium（默认 critical,high）", "required": False}, {"name": "templates", "type": "string", "description": "指定 Nuclei 模板路径或类型", "required": False}]},
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
