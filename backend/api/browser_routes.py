"""GUI Agent Browser API — Playwright 浏览器自动化 REST 端点.

供 Agent 在对话中调用：打开网页 → 快照 → 点击 → 填表 → 截图.
"""

from __future__ import annotations

import base64
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.tools import get_browser_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools/browser", tags=["browser-agent"])


# ── 请求模型 ──────────────────────────────────────


class NavigateRequest(BaseModel):
    url: str = Field(..., description="要打开的 URL")
    wait_until: str = Field(
        default="domcontentloaded",
        description="等待策略: domcontentloaded|load|networkidle",
    )


class ElementRequest(BaseModel):
    ref: str = Field(..., description="元素引用 ID（来自快照，如 @e5）")


class FillRequest(BaseModel):
    ref: str = Field(..., description="输入框引用 ID")
    text: str = Field(..., description="要填入的文本")


class EvaluateRequest(BaseModel):
    expression: str = Field(..., description="JavaScript 表达式")


# ── 响应模型 ──────────────────────────────────────


@router.post("/navigate")
async def browser_navigate(req: NavigateRequest):
    """打开指定网页.

    返回页面 title 和当前 URL.
    """
    agent = get_browser_agent()
    result = await agent.navigate(req.url)
    if not result.success:
        raise HTTPException(status_code=500, detail={"ok": False, "error": result.error})
    return {
        "ok": True,
        "data": {"url": result.url, "title": result.title},
    }


@router.get("/snapshot")
async def browser_snapshot():
    """获取当前页面的可访问性树快照.

    返回所有可交互元素（按钮/链接/输入框等）及其 ref ID，
    后续 click/fill 操作使用这些 ref 定位元素.
    """
    agent = get_browser_agent()
    snap = await agent.snapshot()
    elements = [
        {"ref": e.ref, "role": e.role, "name": e.name, "value": e.value}
        for e in snap.elements
    ]
    return {
        "ok": True,
        "data": {
            "url": snap.url,
            "title": snap.title,
            "elements": elements,
            "element_count": len(elements),
            "text_preview": snap.text_preview,
        },
    }


@router.post("/click")
async def browser_click(req: ElementRequest):
    """点击页面元素（通过 ref 定位）.

    使用 snapshot 返回的 ref 引用.
    """
    agent = get_browser_agent()
    result = await agent.click(req.ref)
    if not result.success:
        raise HTTPException(status_code=500, detail={"ok": False, "error": result.error})
    return {
        "ok": True,
        "data": {"url": result.url, "title": result.title, "clicked": req.ref},
    }


@router.post("/fill")
async def browser_fill(req: FillRequest):
    """向输入框填写文本.

    使用 snapshot 返回的 ref 引用定位输入框.
    """
    agent = get_browser_agent()
    result = await agent.fill(req.ref, req.text)
    if not result.success:
        raise HTTPException(status_code=500, detail={"ok": False, "error": result.error})
    return {
        "ok": True,
        "data": {"url": result.url, "filled": req.ref, "text_length": len(req.text)},
    }


@router.get("/screenshot")
async def browser_screenshot(full_page: bool = False):
    """截取当前页面截图，返回 base64 PNG."""
    agent = get_browser_agent()
    try:
        png_bytes = await agent.screenshot(full_page=full_page)
        b64 = base64.b64encode(png_bytes).decode("utf-8")
        return {
            "ok": True,
            "data": {
                "format": "png",
                "base64": b64,
                "size_bytes": len(png_bytes),
                "url": await agent.current_url(),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail={"ok": False, "error": str(e)})


@router.post("/evaluate")
async def browser_evaluate(req: EvaluateRequest):
    """在页面执行 JavaScript 并返回结果."""
    agent = get_browser_agent()
    try:
        result = await agent.evaluate(req.expression)
        return {"ok": True, "data": {"result": result, "expression": req.expression}}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"ok": False, "error": str(e)})


@router.get("/console")
async def browser_console():
    """获取浏览器控制台输出."""
    agent = get_browser_agent()
    output = await agent.console()
    return {"ok": True, "data": {"output": output}}


@router.get("/status")
async def browser_status():
    """获取浏览器引擎状态."""
    agent = get_browser_agent()
    try:
        url = await agent.current_url() if agent._started else "(not started)"
    except Exception:
        url = "(error)"
    return {
        "ok": True,
        "data": {
            "started": agent._started,
            "current_url": url,
            "headless": agent._headless,
            "playwright_available": _check_playwright(),
        },
    }


def _check_playwright() -> bool:
    """检查 Playwright + Chromium 是否已安装."""
    try:
        from playwright.async_api import async_playwright
        return True
    except ImportError:
        return False


@router.post("/stop")
async def browser_stop():
    """关闭浏览器（测试/清理用）."""
    agent = get_browser_agent()
    await agent.stop()
    return {"ok": True, "data": {"stopped": True}}
