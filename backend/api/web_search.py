"""联网搜索集成 — Tavily 搜索 + Jina Reader 网页抓取.

检测用户消息中的搜索关键词或网页链接：
- 搜索关键词（搜索/最新/查一下等）→ 调 Tavily API → 返回结果注入 LLM 汇总
- 网页链接 → 调 Jina Reader 抓取全文 → 注入 LLM 总结
- 搜索结果和网页内容同步存入对话记录（system 角色消息）
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ═════════════════════════════════════════════════════
# API Key 读取 — 优先 os.getenv，回退到硬编码路径
# ═════════════════════════════════════════════════════


def _read_env_file(env_path: str) -> dict[str, str]:
    """从 .env 文件中解析 key=value 对."""
    result: dict[str, str] = {}
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if value:
                        result[key] = value
    except FileNotFoundError:
        logger.debug(f"Env file not found: {env_path}")
    return result


def _get_tavily_key() -> str:
    """读取 Tavily API Key，优先环境变量，回退到 ~/.hermes/.env."""
    key = os.getenv("TAVILY_API_KEY", "")
    if key:
        logger.debug("TAVILY_API_KEY loaded from environment")
        return key
    # Fallback: 硬编码读取 ~/.hermes/.env
    env_path = os.path.expanduser("~/.hermes/.env")
    logger.info(f"TAVILY_API_KEY not in env, reading from {env_path}")
    env_vars = _read_env_file(env_path)
    key = env_vars.get("TAVILY_API_KEY", "")
    if key:
        logger.debug("TAVILY_API_KEY loaded from .env file")
    return key


def _get_jina_key() -> str:
    """读取 Jina API Key，优先环境变量，回退到 ~/.hermes/mcp.json."""
    key = os.getenv("JINA_API_KEY", "")
    if key:
        logger.debug("JINA_API_KEY loaded from environment")
        return key
    # Fallback: 硬编码读取 ~/.hermes/mcp.json
    mcp_path = os.path.expanduser("~/.hermes/mcp.json")
    logger.info(f"JINA_API_KEY not in env, reading from {mcp_path}")
    try:
        with open(mcp_path) as f:
            mcp_config = json.load(f)
        servers = mcp_config.get("mcpServers", {})
        jina = servers.get("jina-reader", {})
        headers = jina.get("headers", {})
        auth = headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            key = auth[7:]
            logger.debug("JINA_API_KEY loaded from mcp.json")
    except (FileNotFoundError, json.JSONDecodeError, KeyError, AttributeError) as e:
        logger.warning(f"Failed to read Jina key from mcp.json: {e}")
    return key


TAVILY_API_KEY: str = _get_tavily_key()
JINA_API_KEY: str = _get_jina_key()

TAVILY_API_URL: str = "https://api.tavily.com/search"
JINA_READER_URL: str = "https://r.jina.ai"

# ═════════════════════════════════════════════════════
# 关键词 / URL 检测
# ═════════════════════════════════════════════════════

# 触发搜索的关键词正则（覆盖常见信息获取场景）
_SEARCH_KEYWORDS_RE = re.compile(
    r"(搜索|搜一下|搜一搜|搜搜|最新|查一下|查一查|查查|帮我查|帮我搜|帮我找|查找|检索|查资料|网搜"
    r"|新闻|今天|最近|发生了什么|热点|最新消息|实时|最新资讯|当前|现在"
    r"|趋势|动态|进展|事件|热门|快讯|发生了什么|最新报道|最新数据"
    r"|有什么消息|有什么新闻|查一查|查下|看一下|看下|搜下)",
)

# URL 正则（http/https）
_URL_RE = re.compile(r"https?://[^\s\u4e00-\u9fff，。！？、；：""''（）【】《》\n]+")


def should_search(message: str) -> bool:
    """检查消息是否包含搜索触发词."""
    return bool(_SEARCH_KEYWORDS_RE.search(message))


def extract_urls(message: str) -> list[str]:
    """从消息中提取所有 http/https URL."""
    return _URL_RE.findall(message)


# ═════════════════════════════════════════════════════
# Tavily 搜索
# ═════════════════════════════════════════════════════


async def search_tavily(query: str, max_results: int = 5) -> list[dict]:
    """调用 Tavily Search API 搜索，返回结果列表.

    Args:
        query: 搜索查询词
        max_results: 最大返回结果数（1-10）

    Returns:
        搜索结果列表，每项含 {'title', 'url', 'content', 'score'}
    """
    if not TAVILY_API_KEY:
        raise RuntimeError("TAVILY_API_KEY 未配置")

    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_answer": False,
        "include_raw_content": False,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(TAVILY_API_URL, json=payload)
        response.raise_for_status()
        data = response.json()

    results = data.get("results", [])
    logger.info(f"Tavily search returned {len(results)} results for query: {query[:50]}")
    return results


def format_search_results(results: list[dict], query: str) -> str:
    """格式化搜索结果为可读文本，用于存入对话记录."""
    if not results:
        return f"🔍 搜索「{query}」未找到相关结果。"

    lines = [f"🔍 搜索「{query}」的结果：\n"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "无标题")
        url = r.get("url", "")
        content = r.get("content", "")
        lines.append(f"**{i}. {title}**")
        lines.append(f"   {url}")
        if content:
            lines.append(f"   {content[:300]}")
        lines.append("")
    return "\n".join(lines)


# ═════════════════════════════════════════════════════
# Jina Reader 网页抓取
# ═════════════════════════════════════════════════════


async def fetch_jina(url: str, max_chars: int = 8000) -> str:
    """调用 Jina Reader API 抓取网页全文.

    Args:
        url: 目标网页 URL
        max_chars: 最大返回字符数

    Returns:
        网页的纯文本内容
    """
    if not JINA_API_KEY:
        raise RuntimeError("JINA_API_KEY 未配置")

    reader_url = f"{JINA_READER_URL}/{url}"
    headers = {
        "Authorization": f"Bearer {JINA_API_KEY}",
        "Accept": "text/plain",
        "X-Return-Format": "markdown",
    }

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        response = await client.get(reader_url, headers=headers)
        response.raise_for_status()
        content = response.text

    if len(content) > max_chars:
        content = content[:max_chars] + "\n\n...(内容已截断)"

    logger.info(f"Jina fetched {len(content)} chars from {url[:80]}")
    return content


def format_page_content(content: str, url: str) -> str:
    """格式化网页内容为可读文本，用于存入对话记录."""
    preview = content[:500]
    more = "\n...(已截取前500字预览)" if len(content) > 500 else ""
    return f"🌐 网页内容（{url}）：\n\n{preview}{more}"


# ═════════════════════════════════════════════════════
# LLM 汇总 — 将原始数据转为用户可读的回复
# ═════════════════════════════════════════════════════


def build_search_augmented_prompt(
    base_system_prompt: str,
    user_message: str,
    search_context: str,
) -> str:
    """构建带搜索/网页上下文的增强 system prompt.

    在基础 system prompt 后追加搜索/网页内容，
    并指示 LLM 基于这些信息回复用户。
    """
    if not search_context.strip():
        return base_system_prompt

    augmentation = (
        "\n\n---\n"
        "## 联网搜索结果 / 网页内容\n\n"
        f"{search_context}\n\n"
        "---\n"
        "请基于以上从网络获取的最新信息，用中文简洁地回答用户的问题。"
        "在回复中标注信息来源（引用网页标题或 URL）。"
    )
    return base_system_prompt + augmentation
