"""T-03-01：压缩锚点提取机制.

AnchorExtractor 从 MemorySnapshot 中识别当前会话产生的核心/工作记忆，
将这些记忆的 source 消息标记为「锚点」，在压缩时优先保留原文。

对齐设计文档 03-产品详细设计-v2.0.md 第182-186行.
"""

import logging
from typing import Any, Dict, List, Optional

from backend.memory.engine import MemoryFact, MemorySnapshot

logger = logging.getLogger(__name__)

# 最大锚点数量（对齐设计文档第186行）
MAX_ANCHORS = 5


class AnchorExtractor:
    """记忆感知锚点提取器.

    从 MemorySnapshot 中识别当前会话产生的记忆事实，
    返回对应消息在 messages 列表中的索引位置。
    这些索引位置的消息应在压缩时优先保留原文。
    """

    def __init__(self, max_anchors: int = MAX_ANCHORS):
        """初始化锚点提取器.

        Args:
            max_anchors: 最大锚点数量，默认 5.
        """
        self.max_anchors = max_anchors

    def extract(
        self,
        session_id: str,
        memory_snapshot: MemorySnapshot,
        messages: List[Dict[str, Any]],
    ) -> List[int]:
        """提取锚点消息索引列表.

        核心逻辑（对齐设计文档第182-186行）：
        1. 从 MemorySnapshot 获取 core_facts + working_facts
        2. 对每条记忆，检查 source_session_id == 当前 session_id
        3. 尝试将 source_interaction_id 映射为消息索引
        4. 若锚点过多（>max_anchors），取 importance 最高的 max_anchors 条
        5. 仅标记 layer=working 或 layer=core 的记忆来源

        Args:
            session_id: 当前会话 ID.
            memory_snapshot: MemorySnapshot 对象（含 core_facts + working_facts）.
            messages: 会话消息列表，格式 [{"role": "...", "content": "..."}, ...].

        Returns:
            锚点消息的索引列表（在 messages 中的整数位置），
            按 importance 降序排列，最多 max_anchors 个。
        """
        if not memory_snapshot:
            return []

        if not messages:
            return []

        # ── 1. 收集当前会话的工作/核心记忆 ──
        candidate_facts: List[MemoryFact] = []
        for fact in memory_snapshot.core_facts + memory_snapshot.working_facts:
            # 仅标记 layer=working 或 layer=core（对齐设计文档第186行）
            if fact.layer not in ("working", "core"):
                continue
            # 只保留 source_session_id == 当前 session_id 的记忆
            if fact.source_session_id != session_id:
                continue
            candidate_facts.append(fact)

        if not candidate_facts:
            logger.debug(
                "AnchorExtractor: no candidate facts for session=%s", session_id
            )
            return []

        # ── 2. 映射 source_interaction_id → 消息索引 ──
        anchor_indices: List[int] = []
        for fact in candidate_facts:
            msg_idx = self._resolve_message_index(fact, messages)
            if msg_idx is not None and 0 <= msg_idx < len(messages):
                anchor_indices.append(msg_idx)
            else:
                logger.debug(
                    "AnchorExtractor: cannot resolve message index for fact=%s "
                    "source_interaction_id=%s",
                    fact.id,
                    fact.source_interaction_id,
                )

        if not anchor_indices:
            return []

        # ── 3. 按 importance 降序排列，取 top max_anchors ──
        # 构建 (index, importance) 对，按 importance 降序排序
        def _get_importance(idx: int) -> float:
            for fact in candidate_facts:
                if self._resolve_message_index(fact, messages) == idx:
                    return fact.importance
            return 0.0

        # 去重并排序
        unique_indices = list(dict.fromkeys(anchor_indices))  # 保序去重
        indexed = [(idx, _get_importance(idx)) for idx in unique_indices]
        indexed.sort(key=lambda x: x[1], reverse=True)

        result = [idx for idx, _ in indexed[: self.max_anchors]]

        logger.info(
            "AnchorExtractor: extracted %d anchors (from %d candidates) "
            "for session=%s, indices=%s",
            len(result),
            len(candidate_facts),
            session_id,
            result,
        )
        return result

    # ══════════════════════════════════════════════════
    # 内部方法
    # ══════════════════════════════════════════════════

    @staticmethod
    def _resolve_message_index(
        fact: MemoryFact,
        messages: List[Dict[str, Any]],
    ) -> Optional[int]:
        """将 MemoryFact 的 source_interaction_id 解析为消息索引.

        解析策略（按优先级）：
        1. source_interaction_id 是纯数字字符串 → 直接转为 int 索引
        2. source_interaction_id 是 UUID/字符串 → 在 messages 中搜索匹配
           content 或 metadata 中的消息 ID
        3. 若 source_interaction_id 为 None → 尝试通过 content 相似度匹配
           （当前版本：返回 None，留待后续增强）

        Args:
            fact: MemoryFact 对象.
            messages: 消息列表.

        Returns:
            消息索引（整数），或 None（无法解析时）.
        """
        sid = fact.source_interaction_id

        # 策略1：纯数字字符串 → 整数索引
        if sid is not None:
            try:
                idx = int(sid)
                if 0 <= idx < len(messages):
                    return idx
            except (ValueError, TypeError):
                pass

        # 策略2：非数字字符串 → 在 messages 中搜索匹配
        if sid is not None and isinstance(sid, str):
            for i, msg in enumerate(messages):
                # 检查消息内的 message_id / id 字段
                if msg.get("message_id") == sid or msg.get("id") == sid:
                    return i
                # 检查 content 是否包含该 ID（宽松匹配）
                content = str(msg.get("content", ""))
                if sid in content:
                    return i

        # 策略3：source_interaction_id 为 None → 返回 None
        return None
