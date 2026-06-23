"""Agent Chat SSE 端点 — 流式 LLM 对话（集成联网搜索 + 浏览器工具调用 + 自主规划多智能体协作）."""

import asyncio
import base64
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.auth.dependencies import get_current_user

# 联网搜索模块
from backend.api.web_search import (
    build_search_augmented_prompt,
    extract_urls,
    fetch_jina,
    format_page_content,
    format_search_results,
    search_tavily,
    should_search,
)

# 制品自动写入
from backend.api.artifacts_routes import (
    extract_artifacts_from_text,
    store_artifact,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])

# LLM 配置
LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
LLM_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")


def _get_current_model() -> str:
    """获取当前使用的模型（优先从运行时配置读取）。"""
    try:
        from backend.api.system_routes import get_config_value
        runtime_model = get_config_value("llm_model", LLM_MODEL)
        if runtime_model:
            return str(runtime_model)
    except Exception:
        pass
    return LLM_MODEL

# ── Browser 工具定义 (OpenAI function-calling 格式) ──

BROWSER_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "打开指定的网页 URL。当用户说'打开XX网站'、'帮我看XX网页'、'访问XX'时使用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要打开的完整 URL，如 https://www.baidu.com",
                    }
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_snapshot",
            "description": "获取当前页面的可交互元素快照（按钮、链接、输入框等）。通常配合 browser_navigate 后使用，以便了解页面结构后执行点击/填写操作。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "截取当前页面的截图。当用户说'截图'、'帮我看看页面长什么样'时使用此工具。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "点击页面上的指定元素。需先从 browser_snapshot 获取元素的 ref ID。",
            "parameters": {
                "type": "object",
                "properties": {
                    "ref": {
                        "type": "string",
                        "description": "元素引用 ID，如 @e5，从 browser_snapshot 结果中获取",
                    }
                },
                "required": ["ref"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_fill",
            "description": "在输入框中填写文本。需先从 browser_snapshot 获取输入框的 ref ID。",
            "parameters": {
                "type": "object",
                "properties": {
                    "ref": {
                        "type": "string",
                        "description": "输入框的引用 ID，如 @e3",
                    },
                    "text": {
                        "type": "string",
                        "description": "要填写的文本内容",
                    },
                },
                "required": ["ref", "text"],
            },
        },
    },
]

# 全部工具（可后续扩展 terminal、web_search 等）
ALL_TOOLS: list[dict] = BROWSER_TOOLS + [
    {
        "type": "function",
        "function": {
            "name": "port_scan",
            "description": "端口扫描 — 使用 nmap 扫描目标 IP/域名的开放端口和服务",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "目标 IP 或域名"},
                    "ports": {"type": "string", "description": "端口范围，如 22,80,443 或 1-1000（默认 1-1000）"},
                    "arguments": {"type": "string", "description": "额外 nmap 参数，如 -sV（版本检测） -sC（默认脚本）"},
                },
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "vuln_scan",
            "description": "漏洞扫描 — 使用 Nuclei 对目标进行漏洞检测",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "目标 URL 或 IP"},
                    "severity": {"type": "string", "description": "严重级别过滤，如 critical,high,medium（默认 critical,high）"},
                    "templates": {"type": "string", "description": "指定 Nuclei 模板路径或类型"},
                },
                "required": ["target"],
            },
        },
    },
]

# ── 工具调用限制 ──

MAX_TOOL_ITERATIONS = 8  # 最多工具调用轮数，防止死循环（单个工具循环内）
# 总轮次限制通过 config.max_agent_rounds 配置（对话+工具调用总和）

# ── 自主规划与多智能体协作 ──

SUBTASK_DETECTION_PROMPT = """你是一个任务规划专家。请分析用户请求，判断它是否是一个复杂任务。

复杂任务的判断标准：任务需要 2 个或更多不同领域的子任务才能完成，且这些子任务可以并行执行。
例如：
- "帮我开发一个登录功能" → 需要"设计数据库"、"编写后端API"、"开发前端页面"、"编写测试" → 复杂任务
- "帮我查一下今天的天气" → 简单任务
- "帮我写一个 Python 脚本解析 CSV 文件并生成报告" → 复杂任务（解析+生成报告可拆分）

如果是复杂任务，请输出 JSON 格式：
{"is_complex": true, "task_title": "任务标题", "subtasks": [{"id": 1, "name": "子任务名", "description": "子任务描述"}, ...]}

如果是简单任务，请输出：
{"is_complex": false}

只输出 JSON，不要输出其他内容。"""


async def _detect_complex_task(message: str) -> dict:
    """使用 LLM 检测是否是复杂任务，返回拆解结果."""
    url = f"{LLM_BASE_URL.rstrip('/')}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _get_current_model(),
        "messages": [
            {"role": "system", "content": SUBTASK_DETECTION_PROMPT},
            {"role": "user", "content": message},
        ],
        "temperature": 0.1,
        "max_tokens": 1024,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                return {"is_complex": False}
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            # 提取 JSON
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return result
    except Exception as e:
        logger.warning(f"Task decomposition failed: {e}")
    return {"is_complex": False}


async def _execute_subtask(subtask: dict, user_message: str, session_id: str, user_id: str) -> str:
    """通过 Hermes CLI 调用子 Agent 执行子任务."""
    prompt = f"""你是一个专门负责子任务 "{subtask['name']}" 的 Agent。
子任务描述：{subtask['description']}
原始用户请求：{user_message}

请专注于完成分配给您的子任务，输出完整的结果。不要输出多余的元数据信息。"""
    
    try:
        result = subprocess.run(
            ["hermes", "chat", "--message", prompt, "--max-turns", "5", "--json"],
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ},
        )
        if result.returncode == 0:
            try:
                output = json.loads(result.stdout)
                content = output.get("response", result.stdout)
            except json.JSONDecodeError:
                content = result.stdout
        else:
            content = f"⚠️ 子任务执行异常: {result.stderr[:500]}"
    except subprocess.TimeoutExpired:
        content = f"⚠️ 子任务执行超时（120秒）"
    except FileNotFoundError:
        # 没有 hermes CLI，使用 LLM 直接回复作为子任务结果
        content = await _call_llm_for_subtask(prompt)
    except Exception as e:
        content = f"⚠️ 子任务执行失败: {str(e)[:200]}"

    return f"## 子任务 {subtask['id']}: {subtask['name']}\n\n{content.strip()[:2000]}"


async def _call_llm_for_subtask(prompt: str) -> str:
    """后备方案：直接调用 LLM 作为子任务执行."""
    url = f"{LLM_BASE_URL.rstrip('/')}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _get_current_model(),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 2048,
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"Subtask LLM call failed: {e}")
    return "（子任务执行失败）"


async def _run_subtasks_concurrent(subtasks: list[dict], original_message: str, session_id: str, user_id: str) -> str:
    """并发执行所有子任务，汇总结果."""
    tasks = [
        _execute_subtask(st, original_message, session_id, user_id)
        for st in subtasks
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    parts = ["# 自主规划执行结果", f"## 原始请求\n{original_message}\n"]
    for i, st in enumerate(subtasks):
        r = results[i]
        if isinstance(r, Exception):
            r = f"⚠️ 子任务异常: {str(r)[:200]}"
        parts.append(r)

    return "\n\n---\n\n".join(parts)


async def _generate_summary(original_message: str, subtask_results: str) -> str:
    """由主 LLM 汇总子任务结果为最终回复."""
    url = f"{LLM_BASE_URL.rstrip('/')}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    prompt = f"""你是一个项目管理专家。以下是用户请求和各子任务的执行结果，请将它们整合成一份清晰、完整的最终回复。

用户原始请求：{original_message}

各子任务执行结果：
{subtask_results}

请对以上结果进行汇总，以连贯的叙述方式呈现，不要保留"子任务X"的标记格式。用中文回复。"""
    payload = {
        "model": _get_current_model(),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 4096,
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"Summary generation failed: {e}")
    return "（汇总生成失败）"


class ChatRequest(BaseModel):
    message: str
    session: str | None = None


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_session(session_id: str | None, user_id: str = "default") -> tuple[str, bool]:
    """确保会话存在，返回 (session_id, is_new)."""
    from backend.db.connection import get_db
    db = get_db()
    if session_id:
        row = db.execute(
            "SELECT id FROM sessions WHERE id=? AND user_id=?", (session_id, user_id),
        ).fetchone()
        if row:
            return session_id, False
        # session_id 不存在或属于其他用户 → 以当前用户身份创建此 session_id
    # 创建新会话
    new_id = session_id if session_id else str(uuid.uuid4())
    now = _utcnow_iso()
    try:
        db.execute(
            "INSERT INTO sessions (id, title, source, user_id, created_at, updated_at, message_count, token_estimate) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (new_id, "新对话", "web", user_id, now, now, 0, 0),
        )
        db.commit()
    except Exception:
        # ID collision (rare): fall back to UUID
        new_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO sessions (id, title, source, user_id, created_at, updated_at, message_count, token_estimate) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (new_id, "新对话", "web", user_id, now, now, 0, 0),
        )
        db.commit()
    return new_id, True


def _save_message(session_id: str, role: str, content: str):
    """保存消息到数据库."""
    from backend.db.connection import get_db
    db = get_db()
    now = _utcnow_iso()
    db.execute(
        "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (session_id, role, content, now),
    )
    db.execute(
        "UPDATE sessions SET updated_at=?, message_count=message_count+1 WHERE id=?",
        (now, session_id),
    )
    db.commit()


async def _build_system_prompt(session_id: str, user_message: str, user_id: str) -> str:
    """构建完整的 system prompt，注入人格 + 记忆上下文."""
    parts: list[str] = []

    # 基础 system prompt
    parts.append(
        "你是 EvoGen，一个智能助手。请用中文简洁回复。\n\n"
        "## 对话上下文规则\n"
        "用户可能使用省略主语/宾语的短句（如'地址'、'在哪'、'价格呢'），"
        "你必须关联前几轮对话历史来理解省略的部分。"
        "如果上几轮在讨论某家医院，用户说'地址'就是在问那家医院的地址。\n"
    )

    # ── 人格注入 (Fix 1) ──
    try:
        from backend.persona.engine import get_engine as get_persona_engine
        persona_engine = get_persona_engine(user_id=user_id)
        persona_injection = await persona_engine.get_prompt_injection()
        if persona_injection:
            parts.append("\n" + persona_injection)
            logger.debug(f"Persona injection added to system prompt for user={user_id}")
    except Exception as e:
        logger.warning(f"Failed to inject persona: {e}")

    # ── 记忆注入 (Fix 2) ──
    try:
        from backend.memory.engine import get_engine as get_memory_engine
        memory_engine = get_memory_engine()
        snapshot = memory_engine.get_snapshot(session_id, user_message, user_id=user_id)
        memory_text = memory_engine.format_snapshot(snapshot)
        if memory_text:
            parts.append("\n" + memory_text)
            logger.debug("Memory snapshot injected into system prompt")
    except Exception as e:
        logger.warning(f"Failed to inject memory snapshot: {e}")

    return "\n".join(parts)


async def _record_experience(session_id: str, user_message: str, assistant_response: str, user_id: str = "default"):
    """记录对话经验轨迹 + 自动提取偏好 (Fix 3)."""
    try:
        from backend.experience.recorder import (
            TrajectoryTurn,
            TaskOutcome,
            get_recorder,
        )
        from backend.memory.engine import get_engine as get_memory_engine

        # 提交轨迹，标题取自用户消息前 30 字 (Fix 1)
        turns = [
            TrajectoryTurn(
                turn_index=0,
                llm_response_chunk=user_message[:200],
            ),
            TrajectoryTurn(
                turn_index=1,
                llm_response_chunk=assistant_response[:200],
            ),
        ]
        outcome = TaskOutcome(
            success=True,
            wall_time_ms=0,
        )

        session_title = user_message.strip()[:30]
        if len(user_message.strip()) > 30:
            session_title += "…"

        recorder = get_recorder()
        recorder.submit_trajectory(
            session_id=session_id,
            turns=turns,
            outcome=outcome,
            session_title=session_title,
            user_id=user_id,
        )
        logger.debug(f"Experience trajectory recorded for session={session_id} title='{session_title}'")

        # 异步提取记忆事实
        try:
            memory_engine = get_memory_engine()
            memory_engine.extract_and_store(session_id, user_message, assistant_response, user_id=user_id)
            logger.debug(f"Memory facts extracted for session={session_id}")
        except Exception as e:
            logger.warning(f"Failed to extract memory facts: {e}")

        # ── 自动提取用户偏好 (Fix 3) ──
        _auto_extract_preferences(user_message, assistant_response, user_id=user_id)

    except Exception as e:
        logger.warning(f"Failed to record experience: {e}")


def _auto_extract_preferences(user_message: str, assistant_response: str, user_id: str = "default"):
    """从对话中自动提取用户偏好并写入 persona 偏好表.

    识别模式如「我喜欢…」「我习惯…」「我偏好…」「我最讨厌…」等.
    合并写入 learned_preferences JSON 字段，保留已有偏好.
    """
    import re

    try:
        from backend.persona.engine import get_engine as get_persona_engine
        persona = get_persona_engine(user_id=user_id)

        # 在用户消息中匹配偏好表达
        combined = user_message + "\n" + assistant_response
        patterns = {
            "喜欢": re.compile(r"我[也最很]?喜欢(.+?)(?:[，。！？\n]|$)"),
            "不喜欢": re.compile(r"我[也最很]?不喜欢(.+?)(?:[，。！？\n]|$)"),
            "讨厌": re.compile(r"我[也最很]?讨厌(.+?)(?:[，。！？\n]|$)"),
            "习惯": re.compile(r"我[也]?习惯(.+?)(?:[，。！？\n]|$)"),
            "偏好": re.compile(r"我[也]?偏好(.+?)(?:[，。！？\n]|$)"),
            "希望": re.compile(r"我[也]?希望(.+?)(?:[，。！？\n]|$)"),
        }

        new_prefs: dict[str, str] = {}
        for label, pat in patterns.items():
            matches = pat.findall(combined)
            for m in matches:
                cleaned = m.strip().rstrip("。，！？、,.")
                if len(cleaned) >= 2 and len(cleaned) <= 30:
                    new_prefs[label] = cleaned

        if not new_prefs:
            return

        # 合并已有偏好
        try:
            current_attrs = persona.dao.get_all()
        except Exception:
            current_attrs = {}

        existing = current_attrs.get("learned_preferences", {})
        if not isinstance(existing, dict):
            existing = {}

        existing.update(new_prefs)

        persona.dao.set("learned_preferences", existing)
        logger.debug(f"Auto-extracted preferences: {new_prefs}")

    except Exception as e:
        logger.warning(f"Failed to auto-extract preferences: {e}")


def _load_recent_messages(session_id: str, max_messages: int = 20) -> list[dict]:
    """加载会话最近 N 条消息作为对话历史上下文.

    解决多轮对话上下文关联断裂：AI 看到历史对话后能推断省略的主语/宾语。
    返回 [{"role": ..., "content": ...}, ...] 按时间升序排列。
    """
    from backend.db.connection import get_db
    db = get_db()
    rows = db.execute(
        """SELECT role, content FROM messages
           WHERE session_id = ? AND role IN ('user', 'assistant')
           ORDER BY id DESC LIMIT ?""",
        (session_id, max_messages),
    ).fetchall()
    # 反转回时间升序
    return [
        {"role": r["role"], "content": r["content"]}
        for r in reversed(rows)
    ]


# ════════════════════════════════════════════════════════
# 工具执行器
# ════════════════════════════════════════════════════════


def _run_mcp_tool(script_path: str, method: str, arguments: dict) -> str:
    """执行 MCP 子进程工具，返回格式化结果文本."""
    import subprocess
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full_path = os.path.join(project_root, script_path)

    if not os.path.exists(full_path):
        return f"❌ MCP 脚本不存在: {full_path}"

    try:
        payload = json.dumps(arguments)
        result = subprocess.run(
            ["python3", full_path, method, payload],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            return f"⚠️ MCP 工具执行异常 (exit={result.returncode}): {result.stderr[:500]}"

        # 解析 JSON-RPC 响应
        output = json.loads(result.stdout)
        inner = output.get("result", {})
        success = inner.get("success", False)
        data = inner.get("data", {})
        error = inner.get("error")

        if not success:
            return f"❌ {error or '执行失败'}"

        # 格式化输出
        lines = ["✅ 工具执行成功"]
        if data.get("raw_command"):
            lines.append(f"命令: {data['raw_command']}")

        if method == "port_scan":
            lines.append(f"目标: {data.get('target', '未知')}")
            if data.get("hostname"):
                lines.append(f"主机名: {data['hostname']}")
            if data.get("os_guess"):
                lines.append(f"OS: {data['os_guess']}")
            open_ports = data.get("open_ports", [])
            lines.append(f"开放端口: {len(open_ports)} 个")
            for p in open_ports[:10]:
                lines.append(f"  · {p['port']}/{p['protocol']}  {p['service']} [{p['state']}]")
            if len(open_ports) > 10:
                lines.append(f"  ... 还有 {len(open_ports) - 10} 个端口")
            if data.get("summary"):
                lines.append(f"摘要: {data['summary']}")

        elif method == "vuln_scan":
            findings = data.get("findings", [])
            lines.append(f"发现漏洞: {data.get('total_findings', 0)} 个")
            for f in findings[:10]:
                lines.append(f"  · [{f['severity'].upper()}] {f['name']} — {f.get('matched_at', '')}")
            if len(findings) > 10:
                lines.append(f"  ... 还有 {len(findings) - 10} 个漏洞")
            if data.get("warnings"):
                lines.append(f"警告: {data['warnings'][:200]}")

        return "\n".join(lines)

    except json.JSONDecodeError:
        return f"⚠️ MCP 响应解析失败: {result.stdout[:500]}"
    except subprocess.TimeoutExpired:
        return "⚠️ MCP 工具执行超时（300秒）"
    except Exception as e:
        return f"⚠️ MCP 工具异常: {str(e)[:200]}"


async def _execute_tool(tool_name: str, arguments: dict, session_id: str, user_id: str = "default") -> str:
    """执行浏览器工具调用，返回结果文本。所有操作自动允许，无需用户确认。"""
    from backend.tools import get_browser_agent

    agent = get_browser_agent()

    try:
        if tool_name == "browser_navigate":
            url = arguments.get("url", "")
            if not url:
                return "错误：缺少 url 参数"
            result = await agent.navigate(url)
            if result.success:
                snap = await agent.snapshot()
                elems = "\n".join(
                    f"  [{e.ref}] {e.role}: {e.name or e.description}"
                    for e in snap.elements[:30]
                )
                return (
                    f"✅ 已打开 {result.url}\n"
                    f"标题: {snap.title}\n"
                    f"页面可交互元素 ({len(snap.elements)} 个):\n{elems}"
                )
            return f"❌ 打开失败: {result.error}"

        elif tool_name == "browser_snapshot":
            snap = await agent.snapshot()
            elems = "\n".join(
                f"  [{e.ref}] {e.role}: {e.name or e.description}"
                for e in snap.elements[:50]
            )
            return (
                f"📄 当前页面: {snap.title}\n"
                f"URL: {snap.url}\n"
                f"可交互元素 ({len(snap.elements)} 个):\n{elems}"
            )

        elif tool_name == "browser_screenshot":
            png_bytes = await agent.screenshot()
            fd, path = tempfile.mkstemp(suffix=".png", prefix="browser_ss_")
            os.write(fd, png_bytes)
            os.close(fd)
            snap = await agent.snapshot()

            # ── 自动写入制品（图像 Tab）──
            b64_data = base64.b64encode(png_bytes).decode()
            artifact_id = store_artifact(
                "image",
                f"截图_{snap.title or '页面'}",
                f"data:image/png;base64,{b64_data}",
                session_id=session_id,
                user_id=user_id,
            )
            logger.info("Screenshot artifact stored: %s", artifact_id)

            return (
                f"📸 截图已保存（制品 #{artifact_id[-6:]})\\n"
                f"路径: {path}\\n"
                f"大小: {len(png_bytes)} bytes\\n"
                f"页面标题: {snap.title}"
            )

        elif tool_name == "browser_click":
            ref = arguments.get("ref", "")
            if not ref:
                return "错误：缺少 ref 参数"
            result = await agent.click(ref)
            if result.success:
                snap = await agent.snapshot()
                return f"✅ 已点击 {ref}。当前页面: {snap.title}"
            return f"❌ 点击失败: {result.error}"

        elif tool_name == "browser_fill":
            ref = arguments.get("ref", "")
            text = arguments.get("text", "")
            if not ref:
                return "错误：缺少 ref 参数"
            result = await agent.fill(ref, text)
            if result.success:
                return f"✅ 已在 {ref} 填入 '{text}'"
            return f"❌ 填写失败: {result.error}"

        # ── 安全扫描工具（MCP 子进程调用）──
        elif tool_name == "port_scan":
            return _run_mcp_tool("scripts/mcp_nmap_server.py", "port_scan", arguments)

        elif tool_name == "vuln_scan":
            return _run_mcp_tool("scripts/mcp_nuclei_server.py", "vuln_scan", arguments)

        else:
            return f"未知工具: {tool_name}"

    except Exception as e:
        logger.error(f"Tool execution failed: {tool_name} {e}", exc_info=True)
        return f"工具执行异常: {str(e)[:200]}"


# ════════════════════════════════════════════════════════
# LLM 调用（非流式，用于工具调用循环）
# ════════════════════════════════════════════════════════


async def _call_llm_nonstream(
    messages: list[dict],
    tools: list[dict] | None = None,
) -> dict:
    """调用 DeepSeek LLM（非流式），返回完整响应 dict.

    返回格式: {"content": str|None, "tool_calls": list|None}
    """
    url = f"{LLM_BASE_URL.rstrip('/')}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload: dict = {
        "model": _get_current_model(),
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 4096,
    }
    # 尝试获取 reasoning（DeepSeek R1 等模型支持）
    payload["reasoning_model"] = True  # 暗示需要 reasoning
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            error_text = resp.text[:500]
            logger.error(f"LLM API error: {resp.status_code} {error_text}")
            return {"content": f"❌ LLM 调用失败 (HTTP {resp.status_code})", "tool_calls": None}

        data = resp.json()
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        # 提取 reasoning_content（DeepSeek R1 等模型返回）
        reasoning = msg.get("reasoning_content") or choice.get("reasoning_content") or ""

        # 检查 tool_calls
        raw_tool_calls = msg.get("tool_calls")
        if raw_tool_calls:
            tool_calls = []
            for tc in raw_tool_calls:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments", "{}"))
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append({
                    "id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "arguments": args,
                })
            return {"content": msg.get("content"), "tool_calls": tool_calls, "reasoning": reasoning}

        return {"content": msg.get("content", ""), "tool_calls": None, "reasoning": reasoning}


# ════════════════════════════════════════════════════════
# 核心：工具调用循环 + 流式输出
# ════════════════════════════════════════════════════════


async def _tool_loop_stream_generator(
    llm_messages: list[dict],
    session_id: str,
    original_message: str,
    search_context: str,
    user_id: str = "default",
):
    """工具调用循环：反复调用 LLM → 执行工具 → 追加结果，直到 LLM 返回纯文本.

    所有工具调用自动允许（auto-approve），无需用户确认。
    工具执行进度通过 SSE 事件输出给前端。
    """
    iteration = 0
    full_text_response = ""
    max_rounds = MAX_TOOL_ITERATIONS
    # 读取运行时配置的总轮次上限（每个工具迭代轮数限制）
    try:
        from backend.api.system_routes import get_config_value
        max_rounds = min(get_config_value("max_agent_rounds", 90) or 90, 200)
    except Exception:
        pass

    while iteration < max_rounds:
        iteration += 1

        # 调用 LLM（非流式，带工具定义）
        result = await _call_llm_nonstream(llm_messages, tools=ALL_TOOLS)

        # ── 情况 1：有 tool_calls → 执行工具 ──
        if result.get("tool_calls"):
            for tc in result["tool_calls"]:
                tool_name = tc["name"]
                tool_args = tc["arguments"]
                tool_call_id = tc.get("id", f"call_{iteration}")

                logger.info(
                    "Tool call #%d: %s args=%s", iteration, tool_name, tool_args
                )

                # 通知前端：开始执行工具
                yield f"data: {json.dumps({'status': 'tool_start', 'tool': tool_name, 'args': tool_args})}\n\n"

                # 执行工具
                tool_result = await _execute_tool(tool_name, tool_args, session_id, user_id=user_id)

                # 保存工具调用和结果到数据库
                _save_message(session_id, "system",
                    f"🔧 调用工具: {tool_name}({json.dumps(tool_args, ensure_ascii=False)})\n结果: {tool_result[:500]}")

                # 通知前端：工具执行完成
                yield f"data: {json.dumps({'status': 'tool_result', 'tool': tool_name, 'result': tool_result[:300]})}\n\n"

                # 将工具调用和结果追加到 messages
                llm_messages.append({
                    "role": "assistant",
                    "content": result.get("content") or "",
                    "tool_calls": [{
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(tool_args, ensure_ascii=False),
                        },
                    }],
                })
                llm_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": tool_result,
                })

            # 工具执行完，继续下一轮 LLM 调用
            continue

        # ── 情况 2：纯文本响应 → 流式输出 ──
        text = result.get("content") or ""
        full_text_response = text
        reasoning = result.get("reasoning") or ""

        # 如果有 reasoning_content，先发送推理过程（思考模式）
        if reasoning:
            yield f"data: {json.dumps({'status': 'reasoning', 'reasoning': reasoning})}\\n\\n"
            # 短暂延迟，确保前端有时间渲染思考区域
            await asyncio.sleep(0.05)

        if text:
            # 流式输出文本（逐字输出模拟流式体验）
            # 按句子分割逐块发送，避免过于细碎
            chunk_size = 20
            for i in range(0, len(text), chunk_size):
                chunk = text[i:i + chunk_size]
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                await asyncio.sleep(0.01)  # 微小延迟模拟流式

        break  # 工具循环结束

    else:
        # 达到最大迭代次数仍未得到纯文本
        full_text_response = "⚠️ 工具调用达到最大轮数，请简化您的请求。"
        yield f"data: {json.dumps({'chunk': full_text_response})}\n\n"

    # 保存助手回复并记录经验
    if full_text_response:
        _save_message(session_id, "assistant", full_text_response)
        await _record_experience(session_id, original_message, full_text_response, user_id=user_id)

        # ── 自动提取制品（代码块 / 文档 / 表格）──
        try:
            artifact_count = extract_artifacts_from_text(full_text_response, session_id, user_id=user_id)
            if artifact_count:
                logger.info(f"Auto-extracted {artifact_count} artifact(s) from LLM response")
                yield f"data: {json.dumps({'status': 'artifact_extracted', 'count': artifact_count})}\n\n"
        except Exception as e:
            logger.warning(f"Artifact extraction failed: {e}")

    yield "data: [DONE]\n\n"


async def _llm_stream_generator(message: str, session_id: str, user_id: str = "default"):
    """主入口：处理用户消息，管理联网搜索 + 浏览器工具调用 + LLM 对话.

    流程：
    1. 初始化会话 & 保存用户消息
    2. 联网搜索（如触发）
    3. 构建 system prompt + 历史上下文
    4. 工具调用循环（LLM 可自主调用浏览器工具）
    5. 流式输出最终回复
    """
    session_id, is_new = _ensure_session(session_id, user_id=user_id)

    # ⚠️ 必须在保存用户消息前加载历史，避免当前消息自重复
    recent_history = _load_recent_messages(session_id, max_messages=20)

    # 保存用户消息
    _save_message(session_id, "user", message)

    # 为首条消息更新会话标题
    if is_new:
        title = message.strip()[:18]
        if len(message.strip()) > 18:
            title += "…"
        from backend.db.connection import get_db
        get_db().execute("UPDATE sessions SET title=? WHERE id=?", (title, session_id))
        get_db().commit()

    yield f"data: {json.dumps({'status': 'started', 'session': session_id, 'is_new': is_new})}\n\n"

    # ── 联网搜索 / 网页抓取（保持不变） ──
    search_context = ""
    msg_urls = extract_urls(message)
    msg_should_search = should_search(message)

    if msg_urls:
        for url in msg_urls[:3]:
            try:
                logger.info(f"Fetching URL with Jina: {url[:80]}")
                page_content = await fetch_jina(url)
                formatted = format_page_content(page_content, url)
                _save_message(session_id, "system", formatted)
                search_context += f"\n\n### 网页: {url}\n{page_content}"
            except Exception as e:
                logger.warning(f"Jina fetch failed for {url}: {e}")
                _save_message(session_id, "system", f"⚠️ 无法抓取网页: {url}")

    if msg_should_search and not msg_urls:
        try:
            logger.info(f"Tavily search triggered for: {message[:80]}")
            results = await search_tavily(message)
            formatted = format_search_results(results, message)
            _save_message(session_id, "system", formatted)
            search_context += "\n\n### 搜索结果\n" + formatted
        except Exception as e:
            logger.warning(f"Tavily search failed: {e}")

    if msg_should_search and msg_urls:
        try:
            results = await search_tavily(message)
            formatted = format_search_results(results, message)
            _save_message(session_id, "system", formatted)
            search_context += "\n\n### 搜索结果\n" + formatted
        except Exception as e:
            logger.warning(f"Tavily search failed: {e}")

    if not LLM_API_KEY:
        yield f"data: {json.dumps({'chunk': '⚠️ 未配置 LLM API Key。请在 ~/.hermes/.env 中设置 DEEPSEEK_API_KEY。'})}\\n\\n"
        yield "data: [DONE]\\n\\n"
        return

    # ── 自主规划与多智能体协作（复杂任务检测） ──
    # 只在首个用户消息（无历史对话）或明确的新任务时触发
    should_decompose = not recent_history
    if should_decompose:
        yield f"data: {json.dumps({'status': 'decomposing', 'message': '正在分析任务复杂度…'})}\\n\\n"
        task_plan = await _detect_complex_task(message)
        if task_plan.get("is_complex") and len(task_plan.get("subtasks", [])) >= 2:
            subtasks = task_plan["subtasks"]
            task_title = task_plan.get("task_title", "复杂任务")
            yield f"data: {json.dumps({'status': 'task_plan', 'task_title': task_title, 'subtasks': [{'id': s['id'], 'name': s['name']} for s in subtasks]})}\\n\\n"

            # 保存系统消息
            _save_message(session_id, "system",
                f"📋 已识别复杂任务「{task_title}」，拆解为 {len(subtasks)} 个子任务：{'、'.join(s['name'] for s in subtasks)}")

            # 通知前端：开始并行执行
            yield f"data: {json.dumps({'status': 'executing_subtasks', 'subtasks': [s['name'] for s in subtasks]})}\\n\\n"

            # 并行执行子任务
            subtask_results = await _run_subtasks_concurrent(subtasks, message, session_id, user_id)

            # 保存执行结果
            _save_message(session_id, "system", subtask_results[:500])

            # 通知前端：开始汇总
            yield f"data: {json.dumps({'status': 'summarizing', 'message': '正在汇总子任务结果…'})}\\n\\n"

            # 汇总结果
            summary = await _generate_summary(message, subtask_results)

            # 流式输出汇总结果
            _save_message(session_id, "assistant", summary)
            await _record_experience(session_id, message, summary, user_id=user_id)

            # 流式输出
            for i in range(0, len(summary), 30):
                yield f"data: {json.dumps({'chunk': summary[i:i+30]})}\\n\\n"
                await asyncio.sleep(0.005)
            yield "data: [DONE]\\n\\n"
            return
        else:
            yield f"data: {json.dumps({'status': 'skip_decompose', 'message': '简单任务，直接处理'})}\\n\\n"

    # ── 构建 system prompt（含人格 + 记忆 + 搜索上下文 + 工具说明） ──
    system_prompt = await _build_system_prompt(session_id, message, user_id)
    system_prompt = build_search_augmented_prompt(system_prompt, message, search_context)

    # ── 注入工具使用说明
    system_prompt += (
        "\n\n## 可用工具\n"
        "你可以使用浏览器工具来打开网页、截图、点击元素、填写表单。\n"
        "当用户说'打开XX网站'、'帮我搜索'、'截图'等时，直接调用对应工具。\n"
        "所有工具操作自动执行，无需向用户确认。\n"
    )

    # ── 漏洞知识库检索 ──
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from scripts.import_cve_knowledge import search_local, format_knowledge_for_prompt
        kb_results = search_local(message, limit=3)
        kb_text = format_knowledge_for_prompt(kb_results)
        if kb_text:
            system_prompt += kb_text
            logger.debug(f"CVE knowledge base injected ({len(kb_results)} entries)")
    except Exception as e:
        logger.debug(f"CVE knowledge base skipped: {e}")

    # ── 构建对话消息列表 ──
    llm_messages: list[dict] = [{"role": "system", "content": system_prompt}]
    llm_messages.extend(recent_history)
    llm_messages.append({"role": "user", "content": message})

    # ── 进入工具调用循环 ──
    async for sse_event in _tool_loop_stream_generator(
        llm_messages, session_id, message, search_context, user_id=user_id
    ):
        yield sse_event


@router.post("/chat")
async def agent_chat(request: ChatRequest, req: Request, user_id: str = Depends(get_current_user)):
    """SSE 流式对话端点."""
    return StreamingResponse(
        _llm_stream_generator(request.message, request.session, user_id=user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
