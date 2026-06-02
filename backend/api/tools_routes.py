"""Tools REST API — 从 Hermes tools 系统获取工具列表."""

import json
import logging
import subprocess
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
        {"name": "browser_navigate", "description": "Navigate to a URL in the browser", "toolset": "browser", "requires_env": [], "parameters": [{"name": "url", "type": "string", "description": "The URL to navigate to", "required": True}]},
        {"name": "browser_click", "description": "Click on an element by ref ID", "toolset": "browser", "requires_env": [], "parameters": [{"name": "ref", "type": "string", "description": "Element reference from snapshot", "required": True}]},
        {"name": "browser_snapshot", "description": "Get accessibility tree snapshot of page", "toolset": "browser", "requires_env": [], "parameters": []},
        {"name": "browser_console", "description": "Get console output or evaluate JS", "toolset": "browser", "requires_env": [], "parameters": [{"name": "expression", "type": "string", "description": "JS expression to evaluate", "required": False}]},
        {"name": "browser_vision", "description": "Screenshot + vision analysis", "toolset": "browser", "requires_env": [], "parameters": [{"name": "question", "type": "string", "description": "What to analyze", "required": True}]},
        {"name": "terminal", "description": "Execute shell commands", "toolset": "terminal", "requires_env": [], "parameters": [{"name": "command", "type": "string", "description": "Shell command", "required": True}, {"name": "background", "type": "boolean", "description": "Run in background", "required": False}]},
        {"name": "read_file", "description": "Read a text file with line numbers", "toolset": "file", "requires_env": [], "parameters": [{"name": "path", "type": "string", "description": "File path", "required": True}]},
        {"name": "write_file", "description": "Write content to a file", "toolset": "file", "requires_env": [], "parameters": [{"name": "path", "type": "string", "description": "File path", "required": True}, {"name": "content", "type": "string", "description": "Content to write", "required": True}]},
        {"name": "search_files", "description": "Search file contents or find files", "toolset": "file", "requires_env": [], "parameters": [{"name": "pattern", "type": "string", "description": "Search pattern", "required": True}]},
        {"name": "patch", "description": "Targeted find-and-replace edits", "toolset": "file", "requires_env": [], "parameters": [{"name": "path", "type": "string", "description": "File path", "required": True}, {"name": "old_string", "type": "string", "description": "Text to find", "required": True}, {"name": "new_string", "type": "string", "description": "Replacement text", "required": True}]},
        {"name": "web_search", "description": "Search the web via DuckDuckGo", "toolset": "web", "requires_env": [], "parameters": [{"name": "query", "type": "string", "description": "Search query", "required": True}]},
        {"name": "web_extract", "description": "Extract content from a URL", "toolset": "web", "requires_env": [], "parameters": [{"name": "url", "type": "string", "description": "URL to extract", "required": True}]},
        {"name": "memory", "description": "Save durable cross-session memory", "toolset": "memory", "requires_env": [], "parameters": [{"name": "action", "type": "string", "description": "add/replace/remove", "required": True}, {"name": "target", "type": "string", "description": "memory/user", "required": True}, {"name": "content", "type": "string", "description": "Entry content", "required": True}]},
        {"name": "session_search", "description": "Search past session transcripts", "toolset": "session_search", "requires_env": [], "parameters": [{"name": "query", "type": "string", "description": "Search query", "required": True}]},
        {"name": "delegate_task", "description": "Spawn subagent for parallel work", "toolset": "delegation", "requires_env": [], "parameters": [{"name": "goal", "type": "string", "description": "What the subagent should do", "required": True}]},
        {"name": "cronjob", "description": "Manage scheduled cron jobs", "toolset": "cronjob", "requires_env": [], "parameters": [{"name": "action", "type": "string", "description": "create/list/update/pause/resume/remove/run", "required": True}]},
        {"name": "execute_code", "description": "Run Python script with tool access", "toolset": "code_execution", "requires_env": [], "parameters": [{"name": "code", "type": "string", "description": "Python code to execute", "required": True}]},
        {"name": "clarify", "description": "Ask user a clarifying question", "toolset": "clarify", "requires_env": [], "parameters": [{"name": "question", "type": "string", "description": "Question to ask", "required": True}]},
        {"name": "send_message", "description": "Send message to connected platform", "toolset": "messaging", "requires_env": [], "parameters": [{"name": "target", "type": "string", "description": "Delivery target", "required": True}, {"name": "message", "type": "string", "description": "Message text", "required": True}]},
        {"name": "todo", "description": "Manage session task list", "toolset": "todo", "requires_env": [], "parameters": [{"name": "todos", "type": "array", "description": "Task items", "required": False}]},
        {"name": "vision_analyze", "description": "Load image for vision analysis", "toolset": "vision", "requires_env": [], "parameters": [{"name": "image_url", "type": "string", "description": "Image URL or path", "required": True}, {"name": "question", "type": "string", "description": "Question about the image", "required": True}]},
        {"name": "text_to_speech", "description": "Convert text to speech audio", "toolset": "tts", "requires_env": [], "parameters": [{"name": "text", "type": "string", "description": "Text to convert", "required": True}]},
        {"name": "skill_view", "description": "Load a skill's full content", "toolset": "skills", "requires_env": [], "parameters": [{"name": "name", "type": "string", "description": "Skill name", "required": True}]},
        {"name": "skill_manage", "description": "Create/update/delete skills", "toolset": "skills", "requires_env": [], "parameters": [{"name": "action", "type": "string", "description": "create/patch/edit/delete...", "required": True}, {"name": "name", "type": "string", "description": "Skill name", "required": True}]},
        {"name": "feishu_doc_read", "description": "Read Feishu document content", "toolset": "feishu_doc", "requires_env": ["FEISHU_APP_ID"], "parameters": [{"name": "doc_token", "type": "string", "description": "Document token", "required": True}]},
        {"name": "feishu_drive_add_comment", "description": "Add comment on Feishu document", "toolset": "feishu_drive", "requires_env": ["FEISHU_APP_ID"], "parameters": [{"name": "file_token", "type": "string", "description": "File token", "required": True}, {"name": "content", "type": "string", "description": "Comment text", "required": True}]},
    ]


# ── In-memory tool storage ──
_tool_counts: dict[str, int] = {}
_custom_tools: list[dict] = []


@router.get("")
async def list_tools(toolset: Optional[str] = None):
    """获取所有可用工具列表."""
    try:
        base_tools = _list_hermes_tools()
    except Exception as e:
        logger.error(f"Failed to list tools: {e}", exc_info=True)
        base_tools = []

    # Merge custom tools (dedup by name)
    base_names = {t["name"] for t in base_tools}
    merged = list(base_tools)
    for ct in _custom_tools:
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
async def add_tool(tool: dict):
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

    # Remove existing custom tool with same name
    global _custom_tools
    _custom_tools = [t for t in _custom_tools if t["name"] != name]
    _custom_tools.append(entry)
    _tool_counts[name] = 0

    return {"ok": True, "data": entry}


@router.delete("/{name}")
async def delete_tool(name: str):
    """删除工具."""
    global _custom_tools
    _custom_tools = [t for t in _custom_tools if t["name"] != name]
    _tool_counts.pop(name, None)
    return {"ok": True}
