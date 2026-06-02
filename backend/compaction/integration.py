"""T-03-02：Compaction 集成 — MemoryAwareCompressor.

不直接修改 Hermes 源码，使用 wrapper 模式包装 Hermes 的 ContextCompressor，
添加记忆锚点感知能力。

对齐设计文档 03-产品详细设计-v2.0.md 第182-186行，以及
架构师注入点方案.md 第五章（Compaction 模块改造方案）.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from backend.memory.anchor_extractor import AnchorExtractor
from backend.memory.engine import MemorySnapshot

logger = logging.getLogger(__name__)


class MemoryAwareCompressor:
    """记忆感知压缩器 — 包装 Hermes ContextCompressor.

    在 Hermes 压缩前提取锚点消息，确保关键记忆来源在压缩后不被丢失。

    使用模式::

        from backend.compaction.integration import MemoryAwareCompressor
        from backend.memory.anchor_extractor import AnchorExtractor

        anchor_extractor = AnchorExtractor(max_anchors=5)
        compressor = MemoryAwareCompressor(
            hermes_compressor=agent.context_compressor,
            anchor_extractor=anchor_extractor,
        )
        compressed = compressor.compress(
            session_id="...", messages=messages,
            target_ratio=0.5, memory_snapshot=snapshot,
        )
    """

    def __init__(
        self,
        hermes_compressor: Any = None,
        anchor_extractor: Optional[AnchorExtractor] = None,
        max_anchors: int = 5,
    ):
        """初始化记忆感知压缩器.

        Args:
            hermes_compressor: Hermes 的 ContextCompressor 实例.
                None 表示仅做锚点保留（不调用 Hermes 压缩），
                适用于测试或渐进式集成.
            anchor_extractor: AnchorExtractor 实例.
                None 则使用默认配置.
            max_anchors: 最大锚点数量（传递给 AnchorExtractor）.
        """
        self._hermes_compressor = hermes_compressor
        self._anchor_extractor = anchor_extractor or AnchorExtractor(
            max_anchors=max_anchors
        )

    @property
    def anchor_extractor(self) -> AnchorExtractor:
        """获取内部锚点提取器."""
        return self._anchor_extractor

    def compress(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        target_ratio: float = 0.5,
        memory_snapshot: Optional[MemorySnapshot] = None,
        focus_topic: Optional[str] = None,
        current_tokens: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """压缩会话消息，保护锚点消息不被截断/摘要.

        流程：
        1. 提取锚点消息索引
        2. 将消息分为「锚点消息」和「可压缩消息」两组
        3. 可压缩消息正常走 Hermes 压缩
        4. 重新组装：锚点消息保留原文，压缩结果插入到正确位置
        5. 返回完整消息列表

        Args:
            session_id: 当前会话 ID.
            messages: 原始消息列表.
            target_ratio: 目标压缩比例（0-1），用于锚点预算分配.
            memory_snapshot: MemorySnapshot 对象.
            focus_topic: 可选的聚焦主题.
            current_tokens: 当前 token 估算值.

        Returns:
            压缩后的消息列表，锚点消息保留原文.
        """
        # ── 边界情况：无快照或空消息 ──
        if not messages:
            return messages

        if memory_snapshot is None:
            logger.debug("MemoryAwareCompressor: no memory_snapshot, delegating")
            return self._delegate_compress(messages, current_tokens, focus_topic)

        # ── 1. 提取锚点消息索引 ──
        anchor_indices = self._anchor_extractor.extract(
            session_id=session_id,
            memory_snapshot=memory_snapshot,
            messages=messages,
        )

        if not anchor_indices:
            logger.debug(
                "MemoryAwareCompressor: no anchors found for session=%s, "
                "delegating to normal compression",
                session_id,
            )
            return self._delegate_compress(messages, current_tokens, focus_topic)

        # ── 2. 分离锚点消息和可压缩消息 ──
        anchor_set = set(anchor_indices)
        anchor_messages: List[Tuple[int, Dict[str, Any]]] = []
        compressible_messages: List[Dict[str, Any]] = []

        for i, msg in enumerate(messages):
            if i in anchor_set:
                anchor_messages.append((i, msg))
            else:
                compressible_messages.append(msg)

        # 保护 system message（索引 0 永远不被压缩，但可能在锚点列表中）
        has_system = (
            messages
            and messages[0].get("role") == "system"
            and 0 not in anchor_set
        )

        logger.info(
            "MemoryAwareCompressor: %d anchors preserved, %d messages compressible "
            "(session=%s)",
            len(anchor_messages),
            len(compressible_messages),
            session_id,
        )

        # ── 3. 压缩可压缩消息 ──
        if compressible_messages:
            compressed = self._delegate_compress(
                compressible_messages, current_tokens, focus_topic
            )
        else:
            compressed = []

        # ── 4. 重新组装 ──
        result = self._reassemble(
            anchor_messages=anchor_messages,
            compressed=compressed,
            original_count=len(messages),
            has_system=has_system,
        )

        logger.info(
            "MemoryAwareCompressor: reassembled %d → %d messages "
            "(anchors=%d, compressed=%d)",
            len(messages),
            len(result),
            len(anchor_messages),
            len(compressed),
        )
        return result

    # ══════════════════════════════════════════════════
    # 内部方法
    # ══════════════════════════════════════════════════

    def _delegate_compress(
        self,
        messages: List[Dict[str, Any]],
        current_tokens: Optional[int] = None,
        focus_topic: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """委托给 Hermes ContextCompressor 执行压缩.

        若未配置 Hermes compressor，返回原消息列表（透传模式）.
        """
        if self._hermes_compressor is None:
            logger.debug(
                "MemoryAwareCompressor: no hermes_compressor configured, passing through"
            )
            return messages

        try:
            result = self._hermes_compressor.compress(
                messages,
                current_tokens=current_tokens,
                focus_topic=focus_topic,
            )
            return result
        except Exception as e:
            logger.error(
                "MemoryAwareCompressor: hermes_compressor.compress() failed: %s", e,
                exc_info=True,
            )
            # 压缩失败时回退到原消息
            return messages

    @staticmethod
    def _reassemble(
        anchor_messages: List[Tuple[int, Dict[str, Any]]],
        compressed: List[Dict[str, Any]],
        original_count: int,
        has_system: bool = False,
    ) -> List[Dict[str, Any]]:
        """重新组装消息列表：锚点消息保留原文，其余用压缩结果填充.

        策略：
        - 若 system message 不在锚点中，将其放在最前面
        - 锚点消息严格按其原始索引位置插入
        - 压缩结果填充剩余位置

        Args:
            anchor_messages: (原始索引, 消息) 列表.
            compressed: 压缩后的非锚点消息.
            original_count: 原始消息总数（用于确定输出长度）.
            has_system: 是否有未在锚点中的 system 消息.

        Returns:
            重新组装后的消息列表.
        """
        if not anchor_messages:
            return compressed

        # 锚点按原始索引排序
        anchor_messages.sort(key=lambda x: x[0])

        # 构建结果：分步插入
        result: List[Dict[str, Any]] = []

        # 处理 system message（如果存在且不在锚点中）
        if has_system and compressed and compressed[0].get("role") == "system":
            result.append(compressed[0])
            compressed = compressed[1:]

        # 锚点插入 + 普通消息填充
        compressed_idx = 0
        for anchor_idx, anchor_msg in anchor_messages:
            # 填充锚点之前的普通消息
            while compressed_idx < len(compressed) and (
                not result or len(result) <= anchor_idx
            ):
                result.append(compressed[compressed_idx])
                compressed_idx += 1
            # 插入锚点消息（带锚点标记）
            anchor_marked = dict(anchor_msg)
            anchor_marked["_evogen_anchor"] = True
            result.append(anchor_marked)

        # 追加剩余压缩消息
        result.extend(compressed[compressed_idx:])

        return result

    def extract_anchors(
        self,
        session_id: str,
        memory_snapshot: MemorySnapshot,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """便捷方法：直接返回锚点消息列表（而非索引）.

        Args:
            session_id: 当前会话 ID.
            memory_snapshot: MemorySnapshot 对象.
            messages: 原始消息列表.

        Returns:
            锚点消息字典列表（已标记 _evogen_anchor=True），
            按 importance 降序排列.
        """
        indices = self._anchor_extractor.extract(
            session_id=session_id,
            memory_snapshot=memory_snapshot,
            messages=messages,
        )
        result = []
        for idx in indices:
            msg = dict(messages[idx])
            msg["_evogen_anchor"] = True
            result.append(msg)
        return result
