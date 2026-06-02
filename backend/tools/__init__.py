"""GUI Agent Browser Automation — Playwright-based browser manipulation.

Exposes browser actions as a singleton service that tools can call.
The agent invokes these via tool endpoints when users ask to navigate,
click, fill forms, or capture pages.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────────────


@dataclass
class SnapshotElement:
    """页面元素快照."""
    ref: str          # e.g. "@e5"
    role: str         # button / link / textbox / ...
    name: str = ""
    value: str = ""
    description: str = ""


@dataclass
class BrowserSnapshot:
    """页面快照."""
    url: str = ""
    title: str = ""
    elements: list[SnapshotElement] = field(default_factory=list)
    text_preview: str = ""


@dataclass
class ActionResult:
    """操作结果."""
    success: bool = True
    error: str = ""
    url: str = ""
    title: str = ""
    screenshot_b64: str = ""  # base64 PNG
    snapshot: Optional[BrowserSnapshot] = None
    console_output: str = ""


# ─────────────────────────────────────────────────────
# BrowserAgent — Playwright 浏览器自动化引擎
# ─────────────────────────────────────────────────────


class BrowserAgent:
    """Playwright 驱动的浏览器自动化引擎.

    特性：
    - 懒启动：首次操作时自动启动浏览器
    - 单例模式：整个进程共享一个浏览器实例
    - headless 模式：无 GUI（可配置）
    - 页面快照：可访问性树 + 截图
    - 表单填充：支持 input/textarea/select
    """

    _instance: Optional["BrowserAgent"] = None

    def __init__(self, headless: bool = True):
        self._headless = headless
        self._browser: Any = None
        self._page: Any = None
        self._context: Any = None
        self._started = False
        self._ref_map: dict[str, Any] = {}  # ref → Playwright element handle

    @classmethod
    def get_instance(cls, headless: bool = True) -> "BrowserAgent":
        if cls._instance is None:
            cls._instance = cls(headless=headless)
        return cls._instance

    # ── 生命周期 ─────────────────────────────────

    async def start(self) -> None:
        """启动浏览器."""
        if self._started:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            )

        # 确保 Playwright 能找到 Chromium（不受 HOME 重定向影响）
        import os as _os
        _cache = "/root/.cache/ms-playwright"
        if _os.path.exists(_cache) and "PLAYWRIGHT_BROWSERS_PATH" not in _os.environ:
            _os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _cache

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=self._headless,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._page = await self._context.new_page()
        self._started = True
        logger.info("BrowserAgent started (headless=%s)", self._headless)

    async def stop(self) -> None:
        """关闭浏览器."""
        if not self._started:
            return
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
        except Exception as e:
            logger.warning("Error stopping browser: %s", e)
        finally:
            self._started = False
            self._page = None
            self._context = None
            self._browser = None
            self._ref_map.clear()
            logger.info("BrowserAgent stopped")

    async def _ensure_started(self) -> None:
        if not self._started:
            await self.start()

    # ── 核心操作 ─────────────────────────────────

    async def navigate(self, url: str) -> ActionResult:
        """导航到 URL."""
        await self._ensure_started()
        try:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            resp = await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self._ref_map.clear()
            title = await self._page.title()
            logger.info("BrowserAgent navigated to %s (status=%s)", url, resp.status if resp else "?")
            return ActionResult(success=True, url=self._page.url, title=title)
        except Exception as e:
            logger.error("BrowserAgent navigate failed: %s", e)
            return ActionResult(success=False, error=str(e))

    async def snapshot(self) -> BrowserSnapshot:
        """获取页面可访问性树快照."""
        await self._ensure_started()
        self._ref_map.clear()

        try:
            url = self._page.url
            title = await self._page.title()
            elements: list[SnapshotElement] = []
            text_parts: list[str] = []

            # 方法1: accessibility 快照（可能在某些 Playwright 版本中不可用）
            snapshot_data = None
            try:
                if hasattr(self._page, "accessibility"):
                    snapshot_data = await self._page.accessibility.snapshot()
            except Exception:
                pass

            if snapshot_data:
                self._walk_a11y_tree(snapshot_data, elements, text_parts, depth=0)

            # 方法2: 如果 accessibility 返回为空，用 DOM 查询回退
            if not elements:
                elems = await self._page.evaluate("""() => {
                    const interactive = 'a,button,input,select,textarea,[role]';
                    const els = document.querySelectorAll(interactive);
                    return Array.from(els).slice(0, 100).map((el, i) => ({
                        ref: '@e' + i,
                        role: el.tagName.toLowerCase(),
                        name: (el.textContent || el.getAttribute('placeholder') || el.getAttribute('aria-label') || '').trim().slice(0, 60),
                        value: el.value || '',
                        description: el.getAttribute('aria-label') || '',
                    }));
                }""")
                for e in elems:
                    elem = SnapshotElement(
                        ref=e["ref"], role=e["role"], name=e["name"],
                        value=e.get("value", ""), description=e.get("description", ""),
                    )
                    elements.append(elem)
                    self._ref_map[elem.ref] = {"role": e["role"], "name": e["name"], "value": e.get("value", "")}
                    text_parts.append(f"{elem.ref} [{elem.role}] {elem.name[:60]}")

            return BrowserSnapshot(
                url=url,
                title=title,
                elements=elements,
                text_preview="\n".join(text_parts[:80]),
            )
        except Exception as e:
            logger.error("BrowserAgent snapshot failed: %s", e)
            return BrowserSnapshot(url=self._page.url, title=self._page.url, elements=[])

    def _walk_a11y_tree(
        self,
        node: dict,
        elements: list[SnapshotElement],
        text_parts: list[str],
        depth: int,
        max_depth: int = 12,
    ) -> None:
        """递归遍历可访问性树，收集可交互元素."""
        if depth > max_depth:
            return

        role = node.get("role", "").lower()
        name = node.get("name", "").strip()
        value = node.get("value", "")
        description = node.get("description", "")
        children = node.get("children", [])

        # 只收集可交互元素
        interactive_roles = {
            "button", "link", "textbox", "searchbox", "combobox",
            "listbox", "menuitem", "option", "radio", "checkbox",
            "switch", "tab", "slider", "spinbutton", "menuitemcheckbox",
            "menuitemradio", "treeitem", "gridcell",
        }

        if role in interactive_roles or name:
            ref = f"@e{len(elements)}"
            elem = SnapshotElement(
                ref=ref,
                role=role,
                name=name or description or value,
                value=value,
                description=description,
            )
            elements.append(elem)
            # 缓存 ref → a11y node 关系，点击/填充时用于定位
            self._ref_map[ref] = {"role": role, "name": name, "value": value}

            # 文本预览
            label = name or f"[{role}]"
            indent = "  " * min(depth, 4)
            text_parts.append(f"{indent}{ref} {label}")

        for child in children:
            self._walk_a11y_tree(child, elements, text_parts, depth + 1, max_depth)

    async def click(self, ref: str) -> ActionResult:
        """点击指定 ref 的元素."""
        await self._ensure_started()
        try:
            info = self._ref_map.get(ref)
            if not info:
                # 尝试从当前页面重新快照
                snap = await self.snapshot()
                info = self._ref_map.get(ref)
                if not info:
                    return ActionResult(success=False, error=f"Element not found: {ref}. Call snapshot first.")

            # 通过 role + name 定位元素
            selector = self._build_selector(info["role"], info["name"])
            await self._page.click(selector, timeout=10000)
            await self._page.wait_for_load_state("domcontentloaded", timeout=10000)
            title = await self._page.title()

            logger.info("BrowserAgent clicked %s", ref)
            return ActionResult(success=True, url=self._page.url, title=title)
        except Exception as e:
            logger.error("BrowserAgent click failed: %s", e)
            return ActionResult(success=False, error=str(e))

    async def fill(self, ref: str, text: str) -> ActionResult:
        """向指定 ref 的输入框填写文本."""
        await self._ensure_started()
        try:
            info = self._ref_map.get(ref)
            if not info:
                snap = await self.snapshot()
                info = self._ref_map.get(ref)
                if not info:
                    return ActionResult(success=False, error=f"Element not found: {ref}")

            selector = self._build_selector(info["role"], info["name"])
            await self._page.fill(selector, text, timeout=10000)

            logger.info("BrowserAgent filled %s = '%s'", ref, text[:50])
            return ActionResult(success=True, url=self._page.url)
        except Exception as e:
            logger.error("BrowserAgent fill failed: %s", e)
            return ActionResult(success=False, error=str(e))

    async def screenshot(self, full_page: bool = False) -> bytes:
        """截取页面截图，返回 PNG bytes."""
        await self._ensure_started()
        return await self._page.screenshot(full_page=full_page, type="png")

    async def console(self) -> str:
        """获取控制台输出."""
        await self._ensure_started()
        return ""  # Playwright 不持久化控制台，需用 page.on("console") 收集

    async def evaluate(self, expression: str) -> str:
        """在页面执行 JavaScript 并返回结果."""
        await self._ensure_started()
        try:
            result = await self._page.evaluate(expression)
            return str(result) if result is not None else "undefined"
        except Exception as e:
            return f"Error: {e}"

    async def current_url(self) -> str:
        await self._ensure_started()
        return self._page.url

    # ── Helpers ─────────────────────────────────

    @staticmethod
    def _build_selector(role: str, name: str) -> str:
        """根据 accessibility role + name 构建 Playwright selector."""
        name = name.strip().replace('"', '\\"')
        # 优先用 role selector
        role_map = {
            "button": "button",
            "link": "a",
            "textbox": "input,textarea,[contenteditable]",
            "searchbox": "input[type='search']",
            "combobox": "select,[role='combobox']",
            "checkbox": "input[type='checkbox']",
            "radio": "input[type='radio']",
        }
        tag = role_map.get(role, role)

        if name:
            # 组合: tag + text/placeholder/aria-label
            return (
                f'{tag}:has-text("{name}"), '
                f'{tag}[placeholder*="{name}"], '
                f'[aria-label*="{name}"]'
            )
        return tag


# ─────────────────────────────────────────────────────
# 全局单例
# ─────────────────────────────────────────────────────

_agent: Optional[BrowserAgent] = None


def get_browser_agent() -> BrowserAgent:
    """获取全局 BrowserAgent 实例."""
    global _agent
    if _agent is None:
        _agent = BrowserAgent.get_instance()
    return _agent
