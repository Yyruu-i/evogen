"""T-04-02 / T-04-03  PersonaEngine — 统一人格引擎.

对齐设计文档第589-651行：
- 跨 profile 共享同一数据源（MVP）
- 提供属性 CRUD、导入/导出、System Prompt 注入
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional

from backend.persona.dao import PersonaDAO

logger = logging.getLogger(__name__)

# ── 默认值（与 schema.sql 预置值一致） ──
_DEFAULTS: Dict[str, Any] = {
    "display_name": None,
    "preferred_language": "zh",
    "timezone": None,
    "conciseness": 0.5,
    "formality": 0.5,
    "warmth": 0.7,
    "directness": 0.5,
    "auto_approve_tools": False,
    "show_thinking": True,
    "response_language": "zh",
    "learned_preferences": {},
    "discovery_questions_asked": 0,
}

# ── 属性中文标签（用于 prompt 注入） ──
_ATTR_LABELS: Dict[str, str] = {
    "display_name": "称呼",
    "preferred_language": "偏好语言",
    "timezone": "时区",
    "conciseness": "回复简洁度",
    "formality": "正式程度",
    "warmth": "友好程度",
    "directness": "直接程度",
    "auto_approve_tools": "自动批准工具",
    "show_thinking": "显示思考过程",
    "response_language": "回复语言",
    "learned_preferences": "学习到的偏好",
}

# ── 简洁度/正式度 可读化 ──
_CONCISENESS_MAP = {
    (0.0, 0.3): "非常详细",
    (0.3, 0.6): "适中",
    (0.6, 0.8): "简洁",
    (0.8, 1.01): "极简",
}
_FORMALITY_MAP = {
    (0.0, 0.3): "非常随意",
    (0.3, 0.6): "适中",
    (0.6, 0.8): "正式",
    (0.8, 1.01): "非常正式",
}
_WARMTH_MAP = {
    (0.0, 0.3): "冷静客观",
    (0.3, 0.6): "适中",
    (0.6, 0.8): "友好温暖",
    (0.8, 1.01): "非常热情",
}
_DIRECTNESS_MAP = {
    (0.0, 0.3): "委婉含蓄",
    (0.3, 0.6): "适中",
    (0.6, 0.8): "直接",
    (0.8, 1.01): "非常直接",
}


def _range_label(value: float, mapping: dict) -> str:
    """根据数值返回可读标签."""
    for (lo, hi), label in mapping.items():
        if lo <= value < hi:
            return label
    return str(value)


# ───────────────────────────────────────────────────────
# Persona 数据结构（对齐设计文档第627-651行）
# ───────────────────────────────────────────────────────


@dataclass
class Persona:
    """统一人格数据结构."""

    # 基础属性
    display_name: Optional[str] = None
    preferred_language: str = "zh"
    timezone: Optional[str] = None

    # 回复风格
    conciseness: float = 0.5           # 0-1 简洁程度
    formality: float = 0.5             # 0-1 正式程度
    warmth: float = 0.7                # 0-1 友好程度
    directness: float = 0.5            # 0-1 直接程度

    # 功能偏好
    auto_approve_tools: bool = False
    show_thinking: bool = True
    response_language: str = "zh"

    # 学习到的偏好
    learned_preferences: Dict[str, Any] = field(default_factory=dict)

    # 元数据
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    discovery_questions_asked: int = 0


# ───────────────────────────────────────────────────────
# PersonaEngine
# ───────────────────────────────────────────────────────


class PersonaEngine:
    """统一人格引擎 — 管理 agent 行为策略.

    方法签名对齐设计文档第592-615行，所有方法均为 async。
    MVP 阶段：跨 profile 共享同一数据源。
    """

    def __init__(self, dao: Optional[PersonaDAO] = None):
        self._dao = dao or PersonaDAO()

    @property
    def dao(self) -> PersonaDAO:
        return self._dao

    # ── 构建 Persona ─────────────────────────────

    def _build_persona(self, attrs: Dict[str, Any]) -> Persona:
        """从属性字典构建 Persona 对象，缺失字段使用默认值."""
        return Persona(
            display_name=attrs.get("display_name", _DEFAULTS["display_name"]),
            preferred_language=attrs.get("preferred_language", _DEFAULTS["preferred_language"]),
            timezone=attrs.get("timezone", _DEFAULTS["timezone"]),
            conciseness=float(attrs.get("conciseness", _DEFAULTS["conciseness"])),
            formality=float(attrs.get("formality", _DEFAULTS["formality"])),
            warmth=float(attrs.get("warmth", _DEFAULTS["warmth"])),
            directness=float(attrs.get("directness", _DEFAULTS["directness"])),
            auto_approve_tools=bool(attrs.get("auto_approve_tools", _DEFAULTS["auto_approve_tools"])),
            show_thinking=bool(attrs.get("show_thinking", _DEFAULTS["show_thinking"])),
            response_language=str(attrs.get("response_language", _DEFAULTS["response_language"])),
            learned_preferences=attrs.get("learned_preferences", _DEFAULTS["learned_preferences"]) or {},
            discovery_questions_asked=int(attrs.get("discovery_questions_asked", _DEFAULTS["discovery_questions_asked"])),
        )

    # ── 公开接口 ─────────────────────────────────

    async def get_active_persona(self, session=None) -> Persona:
        """获取当前会话的行为策略.

        MVP：跨 profile 读取相同的 persona 配置，session 参数保留但忽略。
        """
        attrs = self._dao.get_all()
        return self._build_persona(attrs)

    async def update_attribute(self, key: str, value: Any) -> Persona:
        """更新单个人格属性.

        例如：用户说「回复简洁点」→ update_attribute("conciseness", 0.9)
        """
        if not PersonaDAO.is_known_key(key):
            raise ValueError(f"Unknown persona attribute: '{key}'")
        self._dao.set(key, value)
        return await self.get_active_persona()

    async def get_attributes(self) -> Dict[str, Any]:
        """获取所有当前属性（包含默认值填充）."""
        return self._dao.get_all()

    async def set_attributes(self, attrs: Dict[str, Any]) -> Persona:
        """批量设置属性."""
        self._dao.set_batch(attrs)
        return await self.get_active_persona()

    async def export_persona(self) -> str:
        """导出人格配置为 JSON 字符串（用于备份/分享）."""
        attrs = self._dao.get_all()
        # 只导出非默认值 + 始终导出关键字段
        export_data = {}
        for key, value in attrs.items():
            if key not in ("created_at", "updated_at"):
                export_data[key] = value
        return json.dumps(export_data, ensure_ascii=False, indent=2)

    async def import_persona(self, json_str: str) -> Persona:
        """从 JSON 导入人格配置（白名单校验）.

        - 只允许导入已知 key
        - 类型会做基本兼容（如 "0.8" → 0.8）
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")

        if not isinstance(data, dict):
            raise ValueError("Persona JSON must be a JSON object (dict)")

        # 白名单过滤
        filtered: Dict[str, Any] = {}
        for key, value in data.items():
            if PersonaDAO.is_known_key(key):
                filtered[key] = value
            else:
                logger.warning(f"import_persona: ignoring unknown key '{key}'")

        if not filtered:
            raise ValueError("No valid persona attributes found in JSON")

        self._dao.set_batch(filtered)
        return await self.get_active_persona()

    # ── System Prompt 注入（T-04-03） ──────────

    async def get_prompt_injection(self) -> str:
        """生成 System Prompt 注入片段.

        格式：中文 Markdown
        只输出已设置且非默认值的属性（display_name 和 learned_preferences 特殊处理）
        控制在 500 tokens 以内。

        对齐设计文档第612-615行：
        ## 用户偏好
        - 称呼：张三
        - 回复风格：简洁直接
        """
        attrs = self._dao.get_all()
        lines: list[str] = []

        # 1) 基础信息
        display_name = attrs.get("display_name")
        if display_name:
            lines.append(f"- 称呼：{display_name}")

        lang = attrs.get("preferred_language")
        if lang and lang != _DEFAULTS["preferred_language"]:
            lang_label = {"zh": "中文", "en": "English", "ja": "日本語"}.get(lang, lang)
            lines.append(f"- 偏好语言：{lang_label}")

        tz = attrs.get("timezone")
        if tz and tz != _DEFAULTS["timezone"]:
            lines.append(f"- 时区：{tz}")

        # 2) 回复风格（合并为一行，更自然）
        conciseness = float(attrs.get("conciseness", _DEFAULTS["conciseness"]))
        formality_val = float(attrs.get("formality", _DEFAULTS["formality"]))
        warmth_val = float(attrs.get("warmth", _DEFAULTS["warmth"]))
        directness_val = float(attrs.get("directness", _DEFAULTS["directness"]))

        style_parts = []
        if conciseness != _DEFAULTS["conciseness"]:
            style_parts.append(_range_label(conciseness, _CONCISENESS_MAP))
        if formality_val != _DEFAULTS["formality"]:
            style_parts.append(_range_label(formality_val, _FORMALITY_MAP))
        if warmth_val != _DEFAULTS["warmth"]:
            style_parts.append(_range_label(warmth_val, _WARMTH_MAP))
        if directness_val != _DEFAULTS["directness"]:
            style_parts.append(_range_label(directness_val, _DIRECTNESS_MAP))

        if style_parts:
            lines.append(f"- 回复风格：{'、'.join(style_parts)}")

        # 3) 功能偏好
        response_lang = attrs.get("response_language")
        if response_lang and response_lang != _DEFAULTS["response_language"]:
            lang_label = {"zh": "中文", "en": "English", "ja": "日本語"}.get(response_lang, response_lang)
            lines.append(f"- 回复语言：{lang_label}")

        show_thinking = attrs.get("show_thinking")
        if show_thinking is not None and bool(show_thinking) != _DEFAULTS["show_thinking"]:
            if bool(show_thinking):
                lines.append("- 显示思考过程：是")
            else:
                lines.append("- 显示思考过程：否")

        auto_approve = attrs.get("auto_approve_tools")
        if auto_approve is not None and bool(auto_approve) != _DEFAULTS["auto_approve_tools"]:
            if bool(auto_approve):
                lines.append("- 自动批准工具：是")

        # 4) 学习到的偏好
        learned = attrs.get("learned_preferences")
        if learned and learned != _DEFAULTS["learned_preferences"] and isinstance(learned, dict):
            for pref_key, pref_val in learned.items():
                if len("\n".join(lines)) < 400:  # 粗略 token 限制
                    lines.append(f"- {pref_key}：{pref_val}")

        if not lines:
            return ""  # 没有非默认属性，不注入

        # 构建最终输出
        header = "## 用户偏好"
        body = "\n".join(lines)

        # 粗略控制 500 tokens（约 750 中文字符或 2000 英文字符）
        full = f"{header}\n{body}"
        if len(full) > 2000:
            full = full[:1997] + "..."

        return full


# ── 全局单例 ───────────────────────────────────────────

_engine: Optional[PersonaEngine] = None


def get_engine() -> PersonaEngine:
    """获取全局 PersonaEngine 单例."""
    global _engine
    if _engine is None:
        _engine = PersonaEngine()
    return _engine


def reset_engine():
    """重置引擎单例（测试用）."""
    global _engine
    _engine = None
