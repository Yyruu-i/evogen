"""EvoGenAgentLoop — Phase 5 Agent Loop 集成.

Wrapper 模式包装 Hermes 的 run_conversation()，不直接修改 Hermes 源码。
在 Agent Loop 的 4 个注入点执行 EvoGen 引擎操作：

  Phase A: 预加载（Loop 启动前）  → memory snapshot + persona + experience hints
  Phase B: 上下文增强              → 三段引擎信息注入 context_enhancement
  Phase C: 调用 Hermes 循环       → 委托原始 hermes_loop_fn
  Phase D: 异步后处理（不阻塞）   → memory extraction + trajectory recording

对齐架构师注入点方案.md + 03-产品详细设计-v2.0.md 第208-255行.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from backend.memory.engine import EvoMemoryEngine
from backend.experience.recorder import TraceRecorder, TaskOutcome
from backend.persona.engine import PersonaEngine

logger = logging.getLogger(__name__)


class EvoGenAgentLoop:
    """Wrapper around Hermes Agent Loop with EvoGen injections.

    用 wrapper 模式包装 Hermes 的 run_conversation()，在 Agent Loop 的
    四个阶段注入 EvoGen 引擎操作。

    Usage:
        loop = EvoGenAgentLoop(memory_engine, trace_recorder, persona_engine)
        response = await loop.run(
            session=session,
            user_message=user_msg,
            hermes_loop_fn=hermes_run_conversation,
        )
    """

    def __init__(
        self,
        memory_engine: EvoMemoryEngine,
        trace_recorder: TraceRecorder,
        persona_engine: PersonaEngine,
    ):
        """初始化 EvoGenAgentLoop.

        Args:
            memory_engine: EvoMemoryEngine 实例
            trace_recorder: TraceRecorder 实例
            persona_engine: PersonaEngine 实例
        """
        self.memory = memory_engine
        self.tracer = trace_recorder
        self.persona = persona_engine

    async def run(
        self,
        session: Any,
        user_message: Any,
        hermes_loop_fn: Callable[..., Any],
        *,
        graceful_degradation: bool = True,
    ) -> Any:
        """Wrapper around Hermes Agent Loop with EvoGen injections.

        Args:
            session: 会话对象（需有 .id 属性）
            user_message: 用户消息对象（需有 .content 属性）
            hermes_loop_fn: Hermes 原始 run_conversation 函数（或兼容包装）
            graceful_degradation: True 时引擎失败不抛异常，优雅降级

        Returns:
            Hermes loop 的原始返回值（通常包含 final_response 等字段）
        """
        # ═══════════════════════════════════════════════════════════
        # PHASE A: 预加载（Agent Loop 启动前）
        # 对齐架构师方案注入点 A (L417-L421)
        # ═══════════════════════════════════════════════════════════

        memory_snapshot = await self._safe_load(
            "memory snapshot",
            self.memory.get_snapshot(session.id, user_message.content),
            graceful_degradation,
        )

        persona = await self._safe_load(
            "persona",
            self.persona.get_active_persona(session),
            graceful_degradation,
        )

        experience_hints = await self._safe_load(
            "experience hints",
            self.tracer.get_scene_hints(session.id, user_message.content),
            graceful_degradation,
        )

        # ═══════════════════════════════════════════════════════════
        # PHASE B: 上下文增强（注入 System Prompt）
        # 对齐架构师方案注入点 B (system_prompt.py L278)
        # ═══════════════════════════════════════════════════════════

        context_enhancement = self._build_context_enhancement(
            memory_snapshot=memory_snapshot,
            persona=persona,
            experience_hints=experience_hints,
        )

        # ═══════════════════════════════════════════════════════════
        # PHASE C: 调用 Hermes 原始循环
        # ═══════════════════════════════════════════════════════════

        response, trajectory_turns = await hermes_loop_fn(
            session, user_message, context_enhancement
        )

        # ═══════════════════════════════════════════════════════════
        # PHASE D: 异步后处理（不阻塞主响应）
        # 对齐架构师方案注入点 C (L3979 之后)
        # ═══════════════════════════════════════════════════════════

        # 构建 outcome 对象用于轨迹记录
        outcome = self._build_outcome(response)

        try:
            asyncio.ensure_future(
                self._async_extract_and_store(
                    session.id, user_message.content, response
                )
            )
        except Exception as exc:
            logger.warning(
                "Failed to schedule memory extraction for session %s: %s",
                session.id, exc,
            )

        try:
            asyncio.ensure_future(
                self._async_submit_trajectory(
                    session.id, trajectory_turns, outcome
                )
            )
        except Exception as exc:
            logger.warning(
                "Failed to schedule trajectory recording for session %s: %s",
                session.id, exc,
            )

        return response

    # ═══════════════════════════════════════════════════════════════
    # 内部方法
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    async def _safe_load(
        label: str,
        coro: Any,
        graceful: bool,
    ) -> Any:
        """安全执行协程，graceful 模式下失败时返回 None 并记录日志.

        Args:
            label: 操作标签（用于日志）
            coro: 协程对象
            graceful: True 时吞异常

        Returns:
            协程结果，或 None（graceful 降级时）
        """
        try:
            return await coro
        except Exception as exc:
            logger.warning(
                "EvoGen %s load failed (graceful=%s): %s",
                label, graceful, exc,
            )
            if graceful:
                return None
            raise

    def _build_context_enhancement(
        self,
        memory_snapshot: Any,
        persona: Any,
        experience_hints: Any,
    ) -> Dict[str, Optional[str]]:
        """将三段引擎信息组装为 context_enhancement 字典.

        顺序对齐设计文档第174-180行：
        1. System Prompt（含人格注入 + 技能）
        2. 环境提示
        3. 工作记忆注入
        4. 经验提示注入
        5. 会话历史（由 Hermes 处理）
        6. 当前用户输入（由 Hermes 处理）

        Args:
            memory_snapshot: EvoMemoryEngine.get_snapshot() 的返回值
            persona: PersonaEngine.get_active_persona() 的返回值
            experience_hints: TraceRecorder.get_scene_hints() 的返回值

        Returns:
            {
                "memory_context": str | None,
                "persona_injection": str | None,
                "experience_hints": str | None,
            }
        """
        result: Dict[str, Optional[str]] = {
            "memory_context": None,
            "persona_injection": None,
            "experience_hints": None,
        }

        # 工作记忆注入
        if memory_snapshot is not None:
            try:
                formatted = self.memory.format_snapshot(memory_snapshot)
                if formatted and formatted.strip():
                    result["memory_context"] = formatted
            except Exception as exc:
                logger.warning("Failed to format memory snapshot: %s", exc)

        # 人格注入（persona 对象上的 get_prompt_injection）
        if persona is not None:
            try:
                # PersonaEngine.get_prompt_injection() 是 async 方法
                # 但这里 persona 是已经获取到的 Persona 对象
                # 我们直接使用 persona 对象的属性来生成注入文本
                injection = self._persona_to_injection(persona)
                if injection:
                    result["persona_injection"] = injection
            except Exception as exc:
                logger.warning("Failed to build persona injection: %s", exc)

        # 经验提示注入
        if experience_hints is not None:
            try:
                formatted = self.tracer.format_hints(experience_hints)
                if formatted and formatted.strip():
                    result["experience_hints"] = formatted
            except Exception as exc:
                logger.warning("Failed to format experience hints: %s", exc)

        return result

    @staticmethod
    def _persona_to_injection(persona: Any) -> str:
        """从 Persona 对象生成注入文本.

        注意：PersonaEngine.get_prompt_injection() 是 async 方法，
        但我们已经在 get_active_persona() 时拿到了 Persona 对象。
        这里基于 Persona 数据直接生成注入文本。

        Args:
            persona: Persona 数据类实例

        Returns:
            格式化的人格注入文本，无有效数据时返回空字符串
        """
        lines: List[str] = []

        display_name = getattr(persona, "display_name", None)
        if display_name:
            lines.append(f"- 称呼：{display_name}")

        conciseness = getattr(persona, "conciseness", 0.5)
        formality = getattr(persona, "formality", 0.5)
        warmth = getattr(persona, "warmth", 0.7)
        directness = getattr(persona, "directness", 0.5)

        style_parts = []
        if conciseness > 0.6:
            style_parts.append("简洁")
        elif conciseness < 0.3:
            style_parts.append("详细")
        if formality > 0.6:
            style_parts.append("正式")
        if warmth > 0.6:
            style_parts.append("友好")
        if directness > 0.6:
            style_parts.append("直接")

        if style_parts:
            lines.append(f"- 回复风格：{'、'.join(style_parts)}")

        response_lang = getattr(persona, "response_language", "zh")
        if response_lang and response_lang != "zh":
            lang_label = {"zh": "中文", "en": "English", "ja": "日本語"}.get(
                response_lang, response_lang
            )
            lines.append(f"- 回复语言：{lang_label}")

        learned = getattr(persona, "learned_preferences", None)
        if learned and isinstance(learned, dict) and learned:
            for pref_key, pref_val in learned.items():
                lines.append(f"- {pref_key}：{pref_val}")

        if not lines:
            return ""

        header = "## 用户偏好"
        body = "\n".join(lines)
        return f"{header}\n{body}"

    @staticmethod
    def _build_outcome(response: Any) -> TaskOutcome:
        """从 Hermes 响应构建 TaskOutcome 对象.

        Args:
            response: Hermes loop 返回值（dict，含 final_response, api_calls 等字段）

        Returns:
            TaskOutcome 实例
        """
        if isinstance(response, dict):
            return TaskOutcome(
                success=response.get("completed", False)
                and not response.get("interrupted", False),
                total_tokens=response.get("total_tokens", 0),
                user_cancelled=response.get("interrupted", False),
            )

        # 非 dict 响应（如纯字符串）
        return TaskOutcome(success=True)

    async def _async_extract_and_store(
        self,
        session_id: str,
        user_message: str,
        response: Any,
    ) -> None:
        """异步提取并存储记忆.

        异常内部捕获，绝不影响主流程。

        Args:
            session_id: 会话 ID
            user_message: 用户消息文本
            response: Hermes 响应
        """
        try:
            # 提取响应文本
            final_response = (
                response.get("final_response", "")
                if isinstance(response, dict)
                else str(response)
            )

            self.memory.extract_and_store(
                session_id, user_message, final_response
            )
            logger.debug(
                "EvoGen memory extraction completed for session %s", session_id
            )
        except Exception as exc:
            logger.warning(
                "EvoGen memory extraction failed for session %s: %s",
                session_id, exc,
                exc_info=True,
            )

    async def _async_submit_trajectory(
        self,
        session_id: str,
        trajectory_turns: Any,
        outcome: TaskOutcome,
    ) -> None:
        """异步提交任务轨迹.

        异常内部捕获，绝不影响主流程。

        Args:
            session_id: 会话 ID
            trajectory_turns: 轨迹轮次列表
            outcome: TaskOutcome 对象
        """
        try:
            from backend.experience.recorder import TrajectoryTurn

            # 确保 trajectory_turns 是 List[TrajectoryTurn]
            if trajectory_turns is None:
                turns: List[TrajectoryTurn] = []
            elif isinstance(trajectory_turns, list):
                turns = trajectory_turns
            else:
                turns = []

            self.tracer.submit_trajectory(
                session_id=session_id,
                turns=turns,
                outcome=outcome,
            )
            logger.debug(
                "EvoGen trajectory recorded for session %s (turns=%d)",
                session_id, len(turns),
            )
        except Exception as exc:
            logger.warning(
                "EvoGen trajectory recording failed for session %s: %s",
                session_id, exc,
                exc_info=True,
            )
