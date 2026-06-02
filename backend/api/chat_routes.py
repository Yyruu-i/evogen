"""Agent Chat SSE 端点 — 流式 LLM 对话（集成联网搜索）."""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])

# LLM 配置
LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
LLM_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")


class ChatRequest(BaseModel):
    message: str
    session: str | None = None


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_session(session_id: str | None) -> tuple[str, bool]:
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
        "INSERT INTO sessions (id, title, source, created_at, updated_at, message_count, token_estimate) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (new_id, "新对话", "web", now, now, 0, 0),
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
    parts.append("你是 EvoGen，一个智能助手。请用中文简洁回复。")

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


async def _llm_stream_generator(message: str, session_id: str):
    """调用 DeepSeek LLM 流式 API，逐 chunk 输出 SSE."""
    session_id, is_new = _ensure_session(session_id)

    # 保存用户消息
    _save_message(session_id, "user", message)

    # 为首条消息更新会话标题（取前 18 字）
    if is_new:
        title = message.strip()[:18]
        if len(message.strip()) > 18:
            title += "…"
        from backend.db.connection import get_db
        get_db().execute("UPDATE sessions SET title=? WHERE id=?", (title, session_id))
        get_db().commit()

    yield f"data: {json.dumps({'status': 'started', 'session': session_id, 'is_new': is_new})}\n\n"

    # ── 联网搜索 / 网页抓取 ──
    search_context = ""
    msg_urls = extract_urls(message)
    msg_should_search = should_search(message)

    if msg_urls:
        for url in msg_urls[:3]:  # 最多抓取 3 个链接
            try:
                logger.info(f"Fetching URL with Jina: {url[:80]}")
                page_content = await fetch_jina(url)
                # 存入对话记录
                formatted = format_page_content(page_content, url)
                _save_message(session_id, "system", formatted)
                # 累积搜索上下文（给 LLM 用完整内容）
                search_context += f"\n\n### 网页: {url}\n{page_content}"
            except Exception as e:
                logger.warning(f"Jina fetch failed for {url}: {e}")
                _save_message(session_id, "system", f"⚠️ 无法抓取网页: {url}")

    if msg_should_search and not msg_urls:
        try:
            logger.info(f"Tavily search triggered for: {message[:80]}")
            results = await search_tavily(message)
            formatted = format_search_results(results, message)
            # 存入对话记录
            _save_message(session_id, "system", formatted)
            # 累积搜索上下文
            search_context += "\n\n### 搜索结果\n" + formatted
        except Exception as e:
            logger.warning(f"Tavily search failed: {e}")

    # 如果同时有 URL 和搜索关键词，两条路径都会触发
    if msg_should_search and msg_urls:
        try:
            logger.info(f"Tavily search (alongside URLs) for: {message[:80]}")
            results = await search_tavily(message)
            formatted = format_search_results(results, message)
            _save_message(session_id, "system", formatted)
            search_context += "\n\n### 搜索结果\n" + formatted
        except Exception as e:
            logger.warning(f"Tavily search (alongside URLs) failed: {e}")

    if not LLM_API_KEY:
        yield f"data: {json.dumps({'chunk': '⚠️ 未配置 LLM API Key。请在 ~/.hermes/.env 中设置 DEEPSEEK_API_KEY。'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    # ── 构建 system prompt（包含人格 + 记忆 + 搜索上下文） ──
    system_prompt = await _build_system_prompt(session_id, message)
    system_prompt = build_search_augmented_prompt(system_prompt, message, search_context)

    # ── 加载对话历史上下文（多轮对话关联修复） ──
    recent_history = _load_recent_messages(session_id, max_messages=20)
    # 构建完整 messages 数组：system + 历史 + 当前用户消息
    llm_messages = [{"role": "system", "content": system_prompt}]
    llm_messages.extend(recent_history)
    llm_messages.append({"role": "user", "content": message})

    url = f"{LLM_BASE_URL.rstrip('/')}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": llm_messages,
        "temperature": 0.7,
        "max_tokens": 4096,
        "stream": True,
    }

    full_response = ""

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    logger.error(f"LLM API error: {response.status_code} {error_text[:300]}")
                    yield f"data: {json.dumps({'chunk': f'❌ LLM 调用失败 (HTTP {response.status_code})'})}\n\n"
                    yield "data: [DONE]\n\n"
                    return

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                yield f"data: {json.dumps({'chunk': content})}\n\n"
                        except json.JSONDecodeError:
                            continue

        except httpx.RequestError as e:
            logger.error(f"LLM request failed: {e}")
            yield f"data: {json.dumps({'chunk': f'❌ 网络请求失败: {str(e)[:100]}'})}\n\n"
        except Exception as e:
            logger.error(f"LLM stream error: {e}")
            yield f"data: {json.dumps({'chunk': f'❌ 流式处理异常: {str(e)[:100]}'})}\n\n"

    # 保存助手回复
    if full_response:
        _save_message(session_id, "assistant", full_response)

    # ── 记录经验轨迹 (Fix 3) ──
    if full_response:
        await _record_experience(session_id, message, full_response)

    yield "data: [DONE]\n\n"


@router.post("/chat")
async def chat_sse(request: ChatRequest):
    """SSE 流式对话端点."""
    return StreamingResponse(
        _llm_stream_generator(request.message, request.session),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
