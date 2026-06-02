"""EvoGenContextBuilder — 上下文组装增强.

对齐 03-产品详细设计-v2.0.md 第174-180行的上下文组装顺序：

  1. System Prompt（含人格注入 + 技能）
  2. 环境提示
  3. 🆕 工作记忆注入
  4. 🆕 经验提示注入
  5. 会话历史
  6. 当前用户输入
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.memory.engine import EvoMemoryEngine, MemorySnapshot
from backend.experience.recorder import TraceRecorder, SceneHint
from backend.persona.engine import PersonaEngine

logger = logging.getLogger(__name__)


class EvoGenContextBuilder:
    """组装增强后的上下文，对齐设计文档第174-180行顺序.

    不直接修改 Hermes 的 system_prompt.py，而是在 Hermes 调用前
    将增强信息注入到 context_enhancement 字典中。
    """

    def __init__(
        self,
        memory_engine: Optional[EvoMemoryEngine] = None,
        trace_recorder: Optional[TraceRecorder] = None,
        persona_engine: Optional[PersonaEngine] = None,
    ):
        """初始化 EvoGenContextBuilder.

        Args:
            memory_engine: EvoMemoryEngine 实例（可选，用于直接格式化）
            trace_recorder: TraceRecorder 实例（可选，用于直接格式化）
            persona_engine: PersonaEngine 实例（可选，用于 prompt_injection）
        """
        self.memory = memory_engine
        self.tracer = trace_recorder
        self.persona = persona_engine

    def build(
        self,
        system_prompt: str,
        environment: str,
        memory_snapshot: Any,
        experience_hints: Any,
        persona_injection: str,
        history: List[Dict[str, Any]],
        user_input: str,
    ) -> str:
        """按设计文档第174-180行顺序组装增强后的上下文.

        组装顺序：
          1. System Prompt（含人格注入 + 技能）
          2. 环境提示
          3. 🆕 工作记忆注入
          4. 🆕 经验提示注入
          5. 会话历史
          6. 当前用户输入

        Args:
            system_prompt: 系统提示词（已包含人格注入）
            environment: 环境提示文本
            memory_snapshot: MemorySnapshot 对象 或 预格式化的字符串
            experience_hints: List[SceneHint] 对象 或 预格式化的字符串
            persona_injection: 人格注入文本（已在 system_prompt 中或独立）
            history: 会话历史消息列表
            user_input: 当前用户输入文本

        Returns:
            组装后的完整上下文字符串
        """
        sections: List[str] = []

        # 1. System Prompt（含人格注入 + 技能）
        if system_prompt:
            sections.append(system_prompt)

        # 如果人格注入未包含在 system_prompt 中，单独追加
        if persona_injection and persona_injection.strip():
            if persona_injection not in (system_prompt or ""):
                sections.append(persona_injection)

        # 2. 环境提示
        if environment:
            sections.append(environment)

        # 3. 🆕 工作记忆注入
        memory_context = self._format_memory_context(memory_snapshot)
        if memory_context:
            sections.append(memory_context)

        # 4. 🆕 经验提示注入
        experience_context = self._format_experience_context(experience_hints)
        if experience_context:
            sections.append(experience_context)

        # 5. 会话历史
        if history:
            history_text = self._format_history(history)
            if history_text:
                sections.append(history_text)

        # 6. 当前用户输入
        if user_input:
            sections.append(user_input)

        return "\n\n".join(sections)

    def build_context_dict(
        self,
        system_prompt: str,
        environment: str,
        memory_snapshot: Any,
        experience_hints: Any,
        persona_injection: str,
        history: List[Dict[str, Any]],
        user_input: str,
    ) -> Dict[str, Any]:
        """构建 context_enhancement 字典（兼容 evogen_loop 接口）.

        将三段增强信息格式化为字典，供 EvoGenAgentLoop._build_context_enhancement() 使用。

        Args:
            system_prompt: 系统提示词
            environment: 环境提示
            memory_snapshot: MemorySnapshot 或格式化字符串
            experience_hints: SceneHint 列表或格式化字符串
            persona_injection: 人格注入文本
            history: 会话历史
            user_input: 用户输入

        Returns:
            context_enhancement 字典
        """
        return {
            "memory_context": self._format_memory_context(memory_snapshot) or None,
            "persona_injection": persona_injection or None,
            "experience_hints": self._format_experience_context(experience_hints) or None,
            # 以下字段由 Hermes 原生处理，此处仅传递供参考
            "system_prompt": system_prompt,
            "environment": environment,
            "history": history,
            "user_input": user_input,
        }

    # ═══════════════════════════════════════════════════════════
    # 格式化方法
    # ═══════════════════════════════════════════════════════════

    def _format_memory_context(self, memory_snapshot: Any) -> Optional[str]:
        """格式化记忆上下文.

        Args:
            memory_snapshot: MemorySnapshot 对象或预格式化字符串

        Returns:
            格式化后的记忆上下文文本，无数据时返回 None
        """
        if memory_snapshot is None:
            return None

        # 已经是字符串
        if isinstance(memory_snapshot, str):
            return memory_snapshot.strip() or None

        # MemorySnapshot 对象
        if self.memory is not None:
            try:
                formatted = self.memory.format_snapshot(memory_snapshot)
                return formatted.strip() if formatted else None
            except Exception as exc:
                logger.warning("Failed to format memory snapshot: %s", exc)
                return None

        # 没有引擎可用，尝试作为字典格式化
        return self._format_snapshot_fallback(memory_snapshot)

    def _format_experience_context(self, experience_hints: Any) -> Optional[str]:
        """格式化经验上下文.

        Args:
            experience_hints: SceneHint 列表或预格式化字符串

        Returns:
            格式化后的经验上下文文本，无数据时返回 None
        """
        if experience_hints is None:
            return None

        # 已经是字符串
        if isinstance(experience_hints, str):
            return experience_hints.strip() or None

        # 列表类型
        if isinstance(experience_hints, list) and len(experience_hints) == 0:
            return None

        # SceneHint 列表
        if self.tracer is not None:
            try:
                formatted = self.tracer.format_hints(experience_hints)
                return formatted.strip() if formatted else None
            except Exception as exc:
                logger.warning("Failed to format experience hints: %s", exc)
                return None

        # 没有引擎可用，fallback
        return self._format_hints_fallback(experience_hints)

    @staticmethod
    def _format_snapshot_fallback(snapshot: Any) -> Optional[str]:
        """格式化 MemorySnapshot 的 fallback 实现.

        Args:
            snapshot: MemorySnapshot 或类似对象

        Returns:
            格式化文本
        """
        try:
            facts: List[str] = []
            for attr in ("core_facts", "working_facts", "transient_facts"):
                fact_list = getattr(snapshot, attr, [])
                if fact_list:
                    for f in fact_list:
                        content = getattr(f, "content", str(f))
                        facts.append(f"- {content}")
            if facts:
                return "## 关于你的记忆\n" + "\n".join(facts)
        except Exception:
            pass
        return None

    @staticmethod
    def _format_hints_fallback(hints: Any) -> Optional[str]:
        """格式化 SceneHint 列表的 fallback 实现.

        Args:
            hints: SceneHint 列表

        Returns:
            格式化文本
        """
        try:
            if isinstance(hints, list):
                lines = ["## 相关经验提示"]
                for h in hints:
                    if hasattr(h, "summary"):
                        lines.append(f"- {h.summary}")
                    elif isinstance(h, dict):
                        lines.append(f"- {h.get('summary', str(h))}")
                if len(lines) > 1:
                    return "\n".join(lines)
        except Exception:
            pass
        return None

    @staticmethod
    def _format_history(history: List[Dict[str, Any]]) -> str:
        """格式化会话历史为文本.

        Args:
            history: 消息列表 [{"role": ..., "content": ...}, ...]

        Returns:
            格式化文本
        """
        lines: List[str] = []
        for msg in history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if content:
                prefix = {"user": "👤", "assistant": "🤖", "system": "⚙️"}.get(role, "❓")
                lines.append(f"{prefix} {role}: {content[:500]}")
        return "\n".join(lines) if lines else ""
