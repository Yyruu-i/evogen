"""Memory WebSocket 事件类型定义.

对齐 03-产品详细设计-v2.0.md 第57行 MEMORY_EVENT 帧：
  {"type": "event", "event": "memory", "payload": {"action": "created", "fact": {...}}}

使用观察者模式，不直接依赖 Hermes WebSocket（Phase 5 集成时才挂载）。
"""

from dataclasses import dataclass, asdict, field
from typing import Any, Callable, Dict, List, Optional

from backend.memory.engine import MemoryFact


# ══════════════════════════════════════════════════
# 事件类型
# ══════════════════════════════════════════════════


@dataclass
class MemoryEvent:
    """记忆变更事件.

    Attributes:
        action: 操作类型 — "created" | "updated" | "deleted" | "reinforced"
        fact: 关联的 MemoryFact 对象
    """

    action: str
    fact: MemoryFact
    metadata: Dict[str, Any] = field(default_factory=dict)

    VALID_ACTIONS = {"created", "updated", "deleted", "reinforced"}

    def __post_init__(self):
        if self.action not in self.VALID_ACTIONS:
            raise ValueError(
                f"Invalid action '{self.action}', must be one of {self.VALID_ACTIONS}"
            )

    def to_payload(self) -> Dict[str, Any]:
        """生成设计文档对齐的 payload 格式.

        Returns:
            {"action": "created", "fact": {...}, "metadata": {...}}
        """
        fact_dict = _fact_to_dict(self.fact)
        return {
            "action": self.action,
            "fact": fact_dict,
            "metadata": self.metadata,
        }

    def to_ws_frame(self) -> Dict[str, Any]:
        """生成完整的 WebSocket 帧（对齐设计文档第57行）.

        Returns:
            {"type": "event", "event": "memory", "payload": {...}}
        """
        return {
            "type": "event",
            "event": "memory",
            "payload": self.to_payload(),
        }


# ══════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════


def _fact_to_dict(fact: MemoryFact) -> Dict[str, Any]:
    """将 MemoryFact 转为可 JSON 序列化的字典."""
    return {
        "id": fact.id,
        "type": fact.type,
        "content": fact.content,
        "importance": fact.importance,
        "weight": fact.weight,
        "layer": fact.layer,
        "source_session_id": fact.source_session_id,
        "source_interaction_id": fact.source_interaction_id,
        "privacy_level": fact.privacy_level,
        "tags": fact.tags,
        "created_at": fact.created_at,
        "updated_at": fact.updated_at,
        "last_accessed_at": fact.last_accessed_at,
        "similarity": fact.similarity,
    }
