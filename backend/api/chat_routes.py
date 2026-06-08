"""Agent Chat SSE 端点 — 流式 LLM 对话（集成联网搜索 + 浏览器工具调用）."""

import asyncio
import base64
import json
import logging
import os
import re
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
ALL_TOOLS: list[dict] = BROWSER_TOOLS

# ── 工具调用限制 ──

MAX_TOOL_ITERATIONS = 8  # 最多工具调用轮数，防止死循环


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
        row = db.execute("SELECT id FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row:
            return session_id, False
    # 创建新会话
    new_id = str(uuid.uuid4())
    now = _utcnow_iso()
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


async def _build_system_prompt(session_id: str, user_message: str) -> str:
    """构建完整的 system prompt，注入人格 + 记忆上下文."""
    parts: list[str] = []

    # 基础 system prompt
    parts.append(
        "你是 EvoGen，一个智能助手。请用中文简洁回复。\n\n"
        "## 对话上下文规则\n"
        "用户可能使用省略主语/宾语的短句（如'地址'、'在哪'、'价格呢'），"
        "你必须关联前几轮对话历史来理解省略的部分。"
        "如果上几轮在讨论某家医院，用户说'地址'就是在问那家医院的地址。"
    )

    # ── 人格注入 (Fix 1) ──
    try:
        from backend.persona.engine import get_engine as get_persona_engine
        persona_engine = get_persona_engine()
        persona_injection = await persona_engine.get_prompt_injection()
        if persona_injection:
            parts.append("\n" + persona_injection)
            logger.debug("Persona injection added to system prompt")
    except Exception as e:
        logger.warning(f"Failed to inject persona: {e}")

    # ── 记忆注入 (Fix 2) ──
    try:
        from backend.memory.engine import get_engine as get_memory_engine
        memory_engine = get_memory_engine()
        snapshot = memory_engine.get_snapshot(session_id, user_message)
        memory_text = memory_engine.format_snapshot(snapshot)
        if memory_text:
            parts.append("\n" + memory_text)
            logger.debug("Memory snapshot injected into system prompt")
    except Exception as e:
        logger.warning(f"Failed to inject memory snapshot: {e}")

    return "\n".join(parts)


async def _record_experience(session_id: str, user_message: str, assistant_response: str):
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
        )
        logger.debug(f"Experience trajectory recorded for session={session_id} title='{session_title}'")

        # 异步提取记忆事实
        try:
            memory_engine = get_memory_engine()
            memory_engine.extract_and_store(session_id, user_message, assistant_response)
            logger.debug(f"Memory facts extracted for session={session_id}")
        except Exception as e:
            logger.warning(f"Failed to extract memory facts: {e}")

        # ── 自动提取用户偏好 (Fix 3) ──
        _auto_extract_preferences(user_message, assistant_response)

    except Exception as e:
        logger.warning(f"Failed to record experience: {e}")


def _auto_extract_preferences(user_message: str, assistant_response: str):
    """从对话中自动提取用户偏好并写入 persona 偏好表.

    识别模式如「我喜欢…」「我习惯…」「我偏好…」「我最讨厌…」等。
    合并写入 learned_preferences JSON 字段，保留已有偏好。
    """
    import re

    try:
        from backend.persona.engine import get_engine as get_persona_engine
        persona = get_persona_engine()

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


async def _execute_tool(tool_name: str, arguments: dict, session_id: str) -> str:
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
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 4096,
    }
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
            return {"content": msg.get("content"), "tool_calls": tool_calls}

        return {"content": msg.get("content", ""), "tool_calls": None}


# ════════════════════════════════════════════════════════
# 核心：工具调用循环 + 流式输出
# ════════════════════════════════════════════════════════


async def _tool_loop_stream_generator(
    llm_messages: list[dict],
    session_id: str,
    original_message: str,
    search_context: str,
):
    """工具调用循环：反复调用 LLM → 执行工具 → 追加结果，直到 LLM 返回纯文本.

    所有工具调用自动允许（auto-approve），无需用户确认。
    工具执行进度通过 SSE 事件输出给前端。
    """
    iteration = 0
    full_text_response = ""

    while iteration < MAX_TOOL_ITERATIONS:
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
                tool_result = await _execute_tool(tool_name, tool_args, session_id)

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
        await _record_experience(session_id, original_message, full_text_response)

        # ── 自动提取制品（代码块 / 文档 / 表格）──
        try:
            artifact_count = extract_artifacts_from_text(full_text_response, session_id)
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
        yield f"data: {json.dumps({'chunk': '⚠️ 未配置 LLM API Key。请在 ~/.hermes/.env 中设置 DEEPSEEK_API_KEY。'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    # ── 构建 system prompt（含人格 + 记忆 + 搜索上下文 + 工具说明） ──
    system_prompt = await _build_system_prompt(session_id, message)
    system_prompt = build_search_augmented_prompt(system_prompt, message, search_context)

    # 注入工具使用说明
    system_prompt += (
        "\n\n## 可用工具\n"
        "你可以使用浏览器工具来打开网页、截图、点击元素、填写表单。\n"
        "当用户说'打开XX网站'、'帮我搜索'、'截图'等时，直接调用对应工具。\n"
        "所有工具操作自动执行，无需向用户确认。\n"
    )

    # ── 构建对话消息列表 ──
    llm_messages: list[dict] = [{"role": "system", "content": system_prompt}]
    llm_messages.extend(recent_history)
    llm_messages.append({"role": "user", "content": message})

    # ── 进入工具调用循环 ──
    async for sse_event in _tool_loop_stream_generator(
        llm_messages, session_id, message, search_context
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
