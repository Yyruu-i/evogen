"""Fact Extractor - LLM 事实提取模块.

使用 DeepSeek LLM 从对话消息中提取结构化事实。
支持中文 zero-shot prompt、retry、markdown code block 解析。
"""

import json
import os
import re
import time
from typing import Dict, List, Optional

import httpx
from dotenv import load_dotenv

# 加载 ~/.hermes/.env 中的环境变量
_ENV_PATH = os.path.expanduser("~/.hermes/.env")
if os.path.exists(_ENV_PATH):
    load_dotenv(_ENV_PATH)

# ── 常量 ─────────────────────────────────────────────

MAX_RETRIES = 3
RETRY_DELAY = 1.0  # 秒，指数退避基数

VALID_FACT_TYPES = frozenset({
    "personal_info",      # 个人信息（姓名、年龄、职业等）
    "preference",         # 偏好（喜欢/不喜欢）
    "plan",               # 计划/意图
    "experience",         # 经历/事件
    "relationship",       # 人际关系
    "knowledge",          # 知识/技能
    "health",             # 健康状况
    "location",           # 位置信息
    "habit",              # 习惯/规律
    "other",              # 其他
})

VALID_PRIVACY_LEVELS = frozenset({
    "public",             # 公开
    "internal",           # 内部（仅 Agent 可见）
    "sensitive",          # 敏感
    "secret",             # 机密
})

# ── Zero-shot Prompt ─────────────────────────────────

SYSTEM_PROMPT = """你是一个事实提取专家。你的任务是从用户对话中提取结构化的事实信息。

## 输出格式
你必须输出一个 JSON 数组，每个元素是一个事实对象，格式如下：

```json
[
  {
    "type": "事实类型",
    "content": "简洁的事实描述（中文，一句话）",
    "importance": 0.0-1.0,
    "privacy_level": "隐私级别"
  }
]
```

## 事实类型 (type)
- personal_info: 个人信息（姓名、年龄、性别、职业、联系方式等）
- preference: 偏好（喜欢/不喜欢、兴趣、品味）
- plan: 计划/意图（未来的安排、目标、打算）
- experience: 经历/事件（过去发生的事情）
- relationship: 人际关系（家人、朋友、同事等）
- knowledge: 知识/技能（掌握的技能、了解的知识领域）
- health: 健康状况（身体、心理、医疗）
- location: 位置信息（居住地、工作地、常去的地方）
- habit: 习惯/规律（日常作息、行为模式）
- other: 其他无法归类的信息

## 重要性 (importance)
- 0.0-0.3: 琐碎信息（闲聊、临时话题）
- 0.3-0.6: 一般信息（日常偏好、普通计划）
- 0.6-0.8: 重要信息（个人背景、重要计划、健康信息）
- 0.8-1.0: 核心信息（身份标识、亲密关系、重大事件）

## 隐私级别 (privacy_level)
- public: 可以公开分享的信息
- internal: 仅 Agent 内部使用
- sensitive: 敏感信息，需要谨慎处理
- secret: 机密信息，严格保密

## 规则
1. 只提取对话中明确提到的事实，不要猜测或推断。
2. 每条事实用一句话概括，力求简洁准确。
3. 如果对话中没有可提取的事实，返回空数组 []。
4. 对话可能是中文、英文或中英混合，事实内容统一用中文输出。
5. 对同一主题的多条信息，分别提取为独立的事实条目。
6. importance 必须基于信息对了解用户的价值来判断，而非对话的情绪强度。
"""

USER_PROMPT_TEMPLATE = """请从以下对话中提取事实信息：

{conversation}

请严格按照 JSON 数组格式输出。"""


def _parse_json_from_response(text: str) -> List[Dict]:
    """从 LLM 响应中解析 JSON 数组。

    支持：
    - 纯 JSON 数组
    - Markdown code block (```json ... ```)
    - Markdown code block without language tag (``` ... ```)
    """
    text = text.strip()

    # 尝试直接解析
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # 尝试从 markdown code block 中提取
    # 匹配 ```json ... ``` 或 ``` ... ```
    patterns = [
        r'```json\s*\n?(.*?)\n?```',
        r'```\s*\n?(.*?)\n?```',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            try:
                data = json.loads(match.strip())
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                continue

    # 最后尝试查找 JSON 数组模式 [...]
    array_pattern = r'\[\s*\{.*?\}\s*\]'
    matches = re.findall(array_pattern, text, re.DOTALL)
    for match in matches:
        try:
            data = json.loads(match)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            continue

    raise ValueError(f"无法从 LLM 响应中解析 JSON 数组: {text[:200]}...")


class FactExtractor:
    """基于 LLM 的事实提取器。

    使用 DeepSeek API（httpx）进行对话事实提取。
    支持自动重试和 markdown code block 解析。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        """初始化 FactExtractor。

        Args:
            api_key: DeepSeek API 密钥，默认从环境变量 DEEPSEEK_API_KEY 读取
            base_url: API 基础 URL，默认从环境变量 DEEPSEEK_BASE_URL 读取，
                      如果未设置则使用 https://api.deepseek.com
            model: 模型名称，默认 deepseek-chat
        """
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = base_url or os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        )
        self.model = model or os.getenv("LLM_MODEL", "deepseek-chat")

        if not self.api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY 未设置。请在 ~/.hermes/.env 中配置。"
            )

        self._client = httpx.Client(timeout=60.0)

    def __del__(self):
        """清理 httpx client."""
        if hasattr(self, "_client"):
            self._client.close()

    # ── 公共方法 ─────────────────────────────────────

    def extract(self, messages: List[Dict[str, str]]) -> List[Dict]:
        """从对话消息中提取事实。

        Args:
            messages: 对话消息列表，每条消息包含 role 和 content 字段。
                     例: [{"role": "user", "content": "..."}, ...]

        Returns:
            提取的事实列表，每条事实包含 type, content, importance, privacy_level。

        Raises:
            RuntimeError: 在重试次数耗尽后仍无法获取有效结果。
        """
        # 构建对话文本
        conversation = self._format_conversation(messages)

        # 构建完整 prompt
        prompt = USER_PROMPT_TEMPLATE.format(conversation=conversation)

        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                raw_response = self._call_llm(prompt)
                facts = _parse_json_from_response(raw_response)
                validated = self._validate(facts)
                return validated
            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    delay = RETRY_DELAY * (2 ** (attempt - 1))
                    time.sleep(delay)
                continue

        raise RuntimeError(
            f"事实提取失败（已重试 {MAX_RETRIES} 次）: {last_error}"
        )

    def generate_confirmation_question(self, fact: Dict) -> str:
        """根据事实生成确认问题。

        Args:
            fact: 事实字典，至少包含 type 和 content 字段。

        Returns:
            确认问题的中文字符串。
        """
        content = fact.get("content", "")
        fact_type = fact.get("type", "")

        if not content:
            return "这条信息是否准确？"

        # 根据事实类型生成不同的确认模板
        templates = {
            "personal_info": f"我了解到：{content}，对吗？",
            "preference": f"你似乎{'喜欢' if '喜欢' in content else '偏好'}：{content}，是这样吗？",
            "plan": f"你计划：{content}，我理解得对吗？",
            "experience": f"你经历过：{content}，没错吧？",
            "relationship": f"你提到：{content}，我记对了吗？",
            "knowledge": f"你掌握：{content}，对吗？",
            "health": f"关于你的健康状况：{content}，是这样吗？",
            "location": f"你的位置信息：{content}，对吗？",
            "habit": f"你的习惯：{content}，我理解得对吗？",
        }

        return templates.get(fact_type, f"我了解到：{content}，对吗？")

    # ── 私有方法 ─────────────────────────────────────

    @staticmethod
    def _format_conversation(messages: List[Dict[str, str]]) -> str:
        """将消息列表格式化为对话文本。"""
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "user":
                lines.append(f"用户：{content}")
            elif role == "assistant":
                lines.append(f"助手：{content}")
            else:
                lines.append(f"{role}：{content}")
        return "\n".join(lines)

    def _call_llm(self, prompt: str) -> str:
        """调用 DeepSeek API。

        Args:
            prompt: 用户 prompt 文本。

        Returns:
            LLM 响应的文本内容。
        """
        url = f"{self.base_url.rstrip('/')}/v1/chat/completions"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 2048,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = self._client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"DeepSeek API 返回错误 (HTTP {e.response.status_code}): "
                f"{e.response.text[:300]}"
            ) from e
        except httpx.RequestError as e:
            raise RuntimeError(f"DeepSeek API 请求失败: {e}") from e

    @staticmethod
    def _validate(facts: List[Dict]) -> List[Dict]:
        """验证和清洗提取的事实。

        Args:
            facts: 待验证的事实列表。

        Returns:
            验证通过的事实列表。
        """
        if not isinstance(facts, list):
            raise ValueError(f"事实必须是列表，收到: {type(facts)}")

        validated = []
        for i, fact in enumerate(facts):
            if not isinstance(fact, dict):
                continue

            # 必填字段检查
            content = fact.get("content", "").strip()
            fact_type = fact.get("type", "").strip()
            importance = fact.get("importance", 0.5)
            privacy_level = fact.get("privacy_level", "internal").strip()

            if not content:
                continue

            # 类型校验
            if fact_type not in VALID_FACT_TYPES:
                fact_type = "other"

            # importance 范围校验
            try:
                importance = float(importance)
            except (TypeError, ValueError):
                importance = 0.5
            importance = max(0.0, min(1.0, importance))

            # 隐私级别校验
            if privacy_level not in VALID_PRIVACY_LEVELS:
                privacy_level = "internal"

            validated.append({
                "type": fact_type,
                "content": content,
                "importance": round(importance, 2),
                "privacy_level": privacy_level,
            })

        return validated


# ── 便捷函数 ─────────────────────────────────────────

_extractor: Optional[FactExtractor] = None


def get_extractor() -> FactExtractor:
    """获取全局 FactExtractor 单例。"""
    global _extractor
    if _extractor is None:
        _extractor = FactExtractor()
    return _extractor


def extract_facts(messages: List[Dict[str, str]]) -> List[Dict]:
    """便捷函数：从对话中提取事实。"""
    return get_extractor().extract(messages)
