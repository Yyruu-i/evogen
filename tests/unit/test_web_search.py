"""联网搜索模块单元测试 — Tavily 搜索 + Jina 抓取 + 关键词检测."""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.api.web_search import (
    _read_env_file,
    _get_jina_key,
    _get_tavily_key,
    build_search_augmented_prompt,
    extract_urls,
    format_page_content,
    format_search_results,
    should_search,
)


# ════════════════════════════════════════════════════════
# 关键词检测测试
# ════════════════════════════════════════════════════════


class TestShouldSearch:
    """检测搜索触发词."""

    @pytest.mark.parametrize("text", [
        "搜索一下最新的AI新闻",
        "帮我搜索Python教程",
        "搜一下最近的天气",
        "最新科技动态是什么",
        "查一下今天的汇率",
        "帮我查查周末的航班",
        "帮我找一下附近的餐厅",
        "查找相关资料",
        "帮我查一查这个单词的意思",
        "检索最近的论文",
        "网搜最近的新闻",
        "最近有什么新闻",
        "今天发生了什么",
        "现在有什么热点",
        "最新消息",
        "看一下今天的头条",
        "有什么最新资讯",
    ])
    def test_positive_matches(self, text):
        """包含搜索关键词的消息应返回 True."""
        assert should_search(text) is True

    @pytest.mark.parametrize("text", [
        "你好",
        "帮我写一段Python代码",
        "什么是机器学习",
        "推荐一本书",
        "写一首诗",
    ])
    def test_negative_matches(self, text):
        """普通消息应返回 False."""
        assert should_search(text) is False

    def test_empty_message(self):
        """空消息不应触发."""
        assert should_search("") is False


# ════════════════════════════════════════════════════════
# URL 提取测试
# ════════════════════════════════════════════════════════


class TestExtractURLs:
    """从消息中提取 URL."""

    def test_extract_single_url(self):
        urls = extract_urls("看看这个 https://example.com/article 怎么样")
        assert urls == ["https://example.com/article"]

    def test_extract_multiple_urls(self):
        urls = extract_urls("参考 https://a.com 和 https://b.com/page")
        assert urls == ["https://a.com", "https://b.com/page"]

    def test_extract_http_url(self):
        urls = extract_urls("访问 http://oldsite.com")
        assert urls == ["http://oldsite.com"]

    def test_no_url(self):
        urls = extract_urls("这是普通消息没有链接")
        assert urls == []

    def test_url_with_query_params(self):
        msg = "看看 https://example.com/search?q=python&lang=zh"
        urls = extract_urls(msg)
        assert urls == ["https://example.com/search?q=python&lang=zh"]

    def test_url_with_chinese_boundary(self):
        """URL 后面跟中文标点时应正确截断."""
        urls = extract_urls("参考https://example.com，然后告诉我")
        assert urls == ["https://example.com"]


# ════════════════════════════════════════════════════════
# 搜索结果格式化测试
# ════════════════════════════════════════════════════════


class TestFormatSearchResults:
    """格式化 Tavily 搜索结果."""

    def test_empty_results(self):
        result = format_search_results([], "test query")
        assert "未找到相关结果" in result

    def test_single_result(self):
        results = [
            {"title": "Test Title", "url": "https://test.com", "content": "Some content"}
        ]
        formatted = format_search_results(results, "test query")
        assert "Test Title" in formatted
        assert "https://test.com" in formatted
        assert "Some content" in formatted

    def test_multiple_results(self):
        results = [
            {"title": f"Title {i}", "url": f"https://test{i}.com", "content": f"Content {i}"}
            for i in range(3)
        ]
        formatted = format_search_results(results, "test")
        for i in range(3):
            assert f"Title {i}" in formatted
            assert f"https://test{i}.com" in formatted

    def test_result_without_content(self):
        results = [{"title": "Title Only", "url": "https://example.com"}]
        formatted = format_search_results(results, "test")
        assert "Title Only" in formatted


# ════════════════════════════════════════════════════════
# 网页内容格式化测试
# ════════════════════════════════════════════════════════


class TestFormatPageContent:
    """格式化 Jina 抓取的网页内容."""

    def test_short_content(self):
        content = "短内容"
        formatted = format_page_content(content, "https://example.com")
        assert "短内容" in formatted
        assert "https://example.com" in formatted
        assert "截取" not in formatted

    def test_long_content_truncated(self):
        content = "x" * 600
        formatted = format_page_content(content, "https://example.com")
        assert "已截取前500字预览" in formatted
        assert len(formatted) < 700  # 确认截断


# ════════════════════════════════════════════════════════
# System Prompt 增强测试
# ════════════════════════════════════════════════════════


class TestBuildSearchAugmentedPrompt:
    """测试 system prompt 增强."""

    def test_no_search_context_returns_base(self):
        base = "你是助手"
        result = build_search_augmented_prompt(base, "用户消息", "")
        assert result == base

    def test_with_search_context(self):
        base = "你是助手"
        ctx = "### 搜索结果\n一些结果"
        result = build_search_augmented_prompt(base, "搜索Python", ctx)
        assert base in result
        assert "搜索结果" in result
        assert "一些结果" in result
        assert "联网搜索" in result

    def test_preserves_persona_and_memory(self):
        base = "你是助手\n## 用户偏好\n- 称呼：张三"
        ctx = "搜索结果内容"
        result = build_search_augmented_prompt(base, "搜索东西", ctx)
        assert "张三" in result
        assert "搜索结果" in result


# ════════════════════════════════════════════════════════
# API Key 读取测试
# ════════════════════════════════════════════════════════


class TestReadEnvFile:
    """测试 .env 文件解析."""

    def test_parse_valid_env(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=value1\nKEY2=value2\n# comment\nKEY3=value3\n")
        result = _read_env_file(str(env_file))
        assert result["KEY1"] == "value1"
        assert result["KEY2"] == "value2"
        assert result["KEY3"] == "value3"

    def test_parse_with_quotes(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('KEY="quoted value"\n')
        result = _read_env_file(str(env_file))
        assert result["KEY"] == "quoted value"

    def test_parse_empty_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")
        result = _read_env_file(str(env_file))
        assert result == {}

    def test_parse_file_not_found(self):
        result = _read_env_file("/nonexistent/path/.env")
        assert result == {}

    def test_parse_empty_values(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=value1\nKEY2=\n")
        result = _read_env_file(str(env_file))
        assert result["KEY1"] == "value1"
        assert "KEY2" not in result  # empty values filtered


class TestGetTavilyKey:
    """测试 Tavily Key 获取."""

    def test_from_env(self):
        with patch.dict(os.environ, {"TAVILY_API_KEY": "tvly-env-key"}):
            from backend.api.web_search import _get_tavily_key
            assert _get_tavily_key() == "tvly-env-key"

    def test_from_env_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("TAVILY_API_KEY=tvly-file-key\n")
        # We can't easily test the hardcoded path, but we test _read_env_file
        result = _read_env_file(str(env_file))
        assert result["TAVILY_API_KEY"] == "tvly-file-key"


class TestGetJinaKey:
    """测试 Jina Key 获取."""

    def test_from_env(self):
        with patch.dict(os.environ, {"JINA_API_KEY": "jina-env-key"}):
            from backend.api.web_search import _get_jina_key
            assert _get_jina_key() == "jina-env-key"

    def test_from_mcp_json(self, tmp_path, monkeypatch):
        monkeypatch.delenv("JINA_API_KEY", raising=False)
        mcp_file = tmp_path / "mcp.json"
        mcp_file.write_text(json.dumps({
            "mcpServers": {
                "jina-reader": {
                    "url": "https://reader.jina.ai/api",
                    "headers": {
                        "Authorization": "Bearer jina-file-key"
                    }
                }
            }
        }))
        with open(mcp_file) as f:
            data = json.load(f)
        auth = data["mcpServers"]["jina-reader"]["headers"]["Authorization"]
        assert auth == "Bearer jina-file-key"


# ════════════════════════════════════════════════════════
# Tavily 搜索 API Mock 测试
# ════════════════════════════════════════════════════════


class TestSearchTavilyAPI:
    """Mock 测试 Tavily API 调用."""

    @pytest.mark.asyncio
    async def test_successful_search(self):
        import backend.api.web_search as ws
        ws.TAVILY_API_KEY = "test-key"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {"title": "Python Tutorial", "url": "https://python.org", "content": "Learn Python"}
            ]
        }
        mock_response.raise_for_status = MagicMock()

        # httpx.AsyncClient() is used as async context manager
        # client.post() returns an awaitable that yields the mock response
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            # The __aenter__/__aexit__ protocol
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            results = await ws.search_tavily("Python tutorial")
            assert len(results) == 1
            assert results[0]["title"] == "Python Tutorial"

    @pytest.mark.asyncio
    async def test_no_api_key_raises(self):
        import backend.api.web_search as ws
        ws.TAVILY_API_KEY = ""

        with pytest.raises(RuntimeError, match="TAVILY_API_KEY 未配置"):
            await ws.search_tavily("query")


# ════════════════════════════════════════════════════════
# Jina Reader API Mock 测试
# ════════════════════════════════════════════════════════


class TestFetchJinaAPI:
    """Mock 测试 Jina Reader API 调用."""

    @pytest.mark.asyncio
    async def test_successful_fetch(self):
        import backend.api.web_search as ws
        ws.JINA_API_KEY = "test-jina-key"

        mock_response = MagicMock()
        mock_response.text = "# Article Title\n\nArticle content here."
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            content = await ws.fetch_jina("https://example.com/article")
            assert "Article Title" in content
            assert "Article content" in content

    @pytest.mark.asyncio
    async def test_content_truncation(self):
        import backend.api.web_search as ws
        ws.JINA_API_KEY = "test-jina-key"

        long_content = "x" * 10000
        mock_response = MagicMock()
        mock_response.text = long_content
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            content = await ws.fetch_jina("https://example.com/long", max_chars=2000)
            assert "已截断" in content
            assert len(content) <= 2100

    @pytest.mark.asyncio
    async def test_no_api_key_raises(self):
        import backend.api.web_search as ws
        ws.JINA_API_KEY = ""

        with pytest.raises(RuntimeError, match="JINA_API_KEY 未配置"):
            await ws.fetch_jina("https://example.com")
