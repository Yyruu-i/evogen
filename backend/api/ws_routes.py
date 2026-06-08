"""WebSocket 端点 — 实时通信（auth token 验证 + agent 消息流式转发）.

端点: ws://host:port/api/v1/ws
协议: JSON 帧 {type, method, params, id}
- connect: 验证 Bearer token
- agent: 流式 LLM 对话（复用 chat_routes 逻辑）
"""

import asyncio
import json
import logging

from fastapi import WebSocket, APIRouter, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


async def _handle_connect(ws: WebSocket, data: dict) -> str | None:
    """处理 connect 帧，验证 token 并返回 user_id.

    帧格式: {"type": "req", "method": "connect", "params": {"token": "..."}}

    Returns:
        user_id 如果验证成功；否则发送错误帧并返回 None。
    """
    params = data.get("params", {})
    token = params.get("token", "")

    if not token:
        await ws.send_json({
            "type": "res",
            "method": "connect",
            "ok": False,
            "error": "缺少 token",
            "id": data.get("id"),
        })
        return None

    try:
        from backend.auth import decode_token
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Token 缺少 sub 字段")

        await ws.send_json({
            "type": "res",
            "method": "connect",
            "ok": True,
            "data": {"user_id": user_id},
            "id": data.get("id"),
        })
        return user_id

    except Exception as e:
        logger.warning(f"WebSocket connect auth failed: {e}")
        await ws.send_json({
            "type": "res",
            "method": "connect",
            "ok": False,
            "error": f"Token 无效: {str(e)}",
            "id": data.get("id"),
        })
        return None


async def _handle_agent(ws: WebSocket, data: dict, user_id: str):
    """处理 agent 帧，流式调用 LLM 并逐 chunk 推送给客户端.

    帧格式: {"type": "req", "method": "agent", "params": {"message": "...", "session": "..."}}

    响应: 流式 {"type": "event", "event": "chunk", "data": {"chunk": "..."}, "id": ...}
          最后发送 {"type": "res", "method": "agent", "ok": true, "id": ...}
    """
    params = data.get("params", {})
    message = params.get("message", "")
    session = params.get("session")

    if not message:
        await ws.send_json({
            "type": "res",
            "method": "agent",
            "ok": False,
            "error": "缺少 message",
            "id": data.get("id"),
        })
        return

    try:
        from backend.api.chat_routes import _llm_stream_generator

        full_text = ""
        async for sse_event in _llm_stream_generator(message, session):
            if isinstance(sse_event, str):
                line = sse_event.strip()
                if not line or not line.startswith("data: "):
                    continue

                data_str = line[len("data: "):]
                if data_str == "[DONE]":
                    continue

                try:
                    payload = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                if "chunk" in payload:
                    chunk = payload["chunk"]
                    full_text += chunk
                    await ws.send_json({
                        "type": "event",
                        "event": "chunk",
                        "data": {"chunk": chunk},
                        "id": data.get("id"),
                    })
                elif "status" in payload:
                    await ws.send_json({
                        "type": "event",
                        "event": "status",
                        "data": payload,
                        "id": data.get("id"),
                    })

        await ws.send_json({
            "type": "res",
            "method": "agent",
            "ok": True,
            "data": {"full_text": full_text},
            "id": data.get("id"),
        })

    except Exception as e:
        logger.error(f"Agent WS handler failed: {e}", exc_info=True)
        await ws.send_json({
            "type": "res",
            "method": "agent",
            "ok": False,
            "error": str(e),
            "id": data.get("id"),
        })


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket 端点.

    接受 JSON 帧:
    - connect: {"type": "req", "method": "connect", "params": {"token": "..."}}
    - agent: {"type": "req", "method": "agent", "params": {"message": "...", "session": "..."}}
    """
    await ws.accept()

    user_id: str | None = None
    authenticated = False

    try:
        while True:
            raw = await ws.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({
                    "type": "res",
                    "ok": False,
                    "error": "无效的 JSON",
                })
                continue

            msg_type = data.get("type", "")
            method = data.get("method", "")

            # 所有请求必须先认证
            if method == "connect":
                user_id = await _handle_connect(ws, data)
                if user_id:
                    authenticated = True
                continue

            if not authenticated:
                await ws.send_json({
                    "type": "res",
                    "method": method,
                    "ok": False,
                    "error": "请先发送 connect 帧进行认证",
                    "id": data.get("id"),
                })
                continue

            if method == "agent":
                await _handle_agent(ws, data, user_id)
            else:
                await ws.send_json({
                    "type": "res",
                    "method": method,
                    "ok": False,
                    "error": f"未知方法: {method}",
                    "id": data.get("id"),
                })

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: user_id={user_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
