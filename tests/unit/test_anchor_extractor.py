"""T-03-01 & T-03-02 测试：AnchorExtractor + MemoryAwareCompressor.

测试覆盖：
- 锚点提取：当前 session 相关/无关消息区分
- 锚点数量限制（>5 取 importance 最高的 5 条）
- 空快照/空消息边界情况
- importance 排序验证
- MemoryAwareCompressor 锚点保护行为
"""

from typing import Any, Dict, List, Optional

import pytest

from backend.memory.engine import MemoryFact, MemorySnapshot
from backend.memory.anchor_extractor import AnchorExtractor, MAX_ANCHORS
from backend.compaction.integration import MemoryAwareCompressor


# ════════════════════════════════════════════════════════
# 测试用 Fact 工厂
# ════════════════════════════════════════════════════════


def _make_fact(
    fact_id: str = "f1",
    content: str = "用户喜欢 Python",
    layer: str = "working",
    importance: float = 0.7,
    source_session_id: Optional[str] = "session-1",
    source_interaction_id: Optional[str] = "0",
) -> MemoryFact:
    return MemoryFact(
        id=fact_id,
        type="preference",
        content=content,
        importance=importance,
        layer=layer,
        source_session_id=source_session_id,
        source_interaction_id=source_interaction_id,
    )


def _make_messages(count: int = 5) -> List[Dict[str, Any]]:
    """创建模拟消息列表."""
    messages: List[Dict[str, Any]] = []
    for i in range(count):
        messages.append({
            "role": "user" if i % 2 == 1 else "assistant",
            "content": f"消息内容 {i}",
            "message_id": str(i),
        })
    return messages


# ════════════════════════════════════════════════════════
# T-03-01：AnchorExtractor 测试
# ════════════════════════════════════════════════════════


class TestAnchorExtractor:
    """AnchorExtractor 单元测试."""

    # ── 基本功能 ──

    def test_extract_current_session_anchors(self):
        """锚点提取：当前 session 的事实 → 返回对应消息索引."""
        extractor = AnchorExtractor(max_anchors=5)
        messages = _make_messages(5)

        snapshot = MemorySnapshot(
            core_facts=[
                _make_fact(
                    "f1",
                    importance=0.8,
                    source_session_id="session-1",
                    source_interaction_id="1",
                ),
            ],
            working_facts=[
                _make_fact(
                    "f2",
                    importance=0.6,
                    source_session_id="session-1",
                    source_interaction_id="3",
                ),
            ],
        )

        indices = extractor.extract(
            session_id="session-1",
            memory_snapshot=snapshot,
            messages=messages,
        )

        assert set(indices) == {1, 3}

    def test_exclude_other_session_facts(self):
        """锚点提取：其他 session 的事实不被标记."""
        extractor = AnchorExtractor(max_anchors=5)
        messages = _make_messages(5)

        snapshot = MemorySnapshot(
            core_facts=[
                _make_fact(
                    "f1",
                    source_session_id="session-2",  # 不同 session
                    source_interaction_id="1",
                ),
            ],
            working_facts=[
                _make_fact(
                    "f2",
                    source_session_id="session-1",
                    source_interaction_id="3",
                ),
            ],
        )

        indices = extractor.extract(
            session_id="session-1",
            memory_snapshot=snapshot,
            messages=messages,
        )

        # 只有 f2（session-1）被标记
        assert indices == [3]

    def test_exclude_transient_layer(self):
        """锚点提取：transient 层记忆不被标记（对齐设计文档第186行）."""
        extractor = AnchorExtractor(max_anchors=5)
        messages = _make_messages(5)

        snapshot = MemorySnapshot(
            core_facts=[],
            working_facts=[],
            transient_facts=[
                _make_fact(
                    "f1",
                    layer="transient",
                    source_session_id="session-1",
                    source_interaction_id="1",
                ),
            ],
        )

        indices = extractor.extract(
            session_id="session-1",
            memory_snapshot=snapshot,
            messages=messages,
        )

        assert indices == []

    def test_max_anchors_limit(self):
        """锚点数量限制：>5 条 → 取 importance 最高的 5 条."""
        extractor = AnchorExtractor(max_anchors=5)
        messages = _make_messages(10)

        # 创建 8 条同一 session 的 core_facts，importance 递增
        facts = []
        for i in range(8):
            facts.append(
                _make_fact(
                    f"f{i}",
                    importance=0.5 + i * 0.05,  # 0.50, 0.55, ..., 0.85
                    source_session_id="session-1",
                    source_interaction_id=str(i),
                )
            )

        snapshot = MemorySnapshot(
            core_facts=facts,
            working_facts=[],
        )

        indices = extractor.extract(
            session_id="session-1",
            memory_snapshot=snapshot,
            messages=messages,
        )

        # 最多 5 条
        assert len(indices) == 5
        # 应该是 importance 最高的 5 条：索引 7, 6, 5, 4, 3
        assert indices == [7, 6, 5, 4, 3]

    def test_importance_ordering(self):
        """importance 排序验证：高重要性优先."""
        extractor = AnchorExtractor(max_anchors=3)
        messages = _make_messages(6)

        snapshot = MemorySnapshot(
            core_facts=[
                _make_fact("f1", importance=0.5, source_interaction_id="1"),
                _make_fact("f2", importance=0.9, source_interaction_id="2"),
                _make_fact("f3", importance=0.3, source_interaction_id="3"),
                _make_fact("f4", importance=0.7, source_interaction_id="4"),
            ],
        )

        indices = extractor.extract(
            session_id="session-1",
            memory_snapshot=snapshot,
            messages=messages,
        )

        # 按 importance: f2(0.9), f4(0.7), f1(0.5)
        assert indices == [2, 4, 1]

    # ── 边界情况 ──

    def test_empty_snapshot(self):
        """空快照 → 返回空列表."""
        extractor = AnchorExtractor()
        messages = _make_messages(5)

        snapshot = MemorySnapshot(
            core_facts=[],
            working_facts=[],
            transient_facts=[],
        )

        indices = extractor.extract(
            session_id="session-1",
            memory_snapshot=snapshot,
            messages=messages,
        )

        assert indices == []

    def test_empty_messages(self):
        """空消息列表 → 返回空列表."""
        extractor = AnchorExtractor()

        snapshot = MemorySnapshot(
            core_facts=[
                _make_fact("f1", source_interaction_id="0"),
            ],
        )

        indices = extractor.extract(
            session_id="session-1",
            memory_snapshot=snapshot,
            messages=[],
        )

        assert indices == []

    def test_snapshot_none(self):
        """None 快照 → 返回空列表（不抛异常）."""
        extractor = AnchorExtractor()

        indices = extractor.extract(
            session_id="session-1",
            memory_snapshot=None,  # type: ignore[arg-type]
            messages=_make_messages(3),
        )

        assert indices == []

    def test_source_interaction_id_out_of_range(self):
        """source_interaction_id 超出消息范围 → 该条被跳过."""
        extractor = AnchorExtractor(max_anchors=5)
        messages = _make_messages(3)  # 只有 0, 1, 2

        snapshot = MemorySnapshot(
            core_facts=[
                _make_fact("f1", source_interaction_id="1"),   # 有效
                _make_fact("f2", source_interaction_id="99"),  # 超出范围
            ],
        )

        indices = extractor.extract(
            session_id="session-1",
            memory_snapshot=snapshot,
            messages=messages,
        )

        # 只有 f1 被标记
        assert indices == [1]

    def test_source_interaction_id_none(self):
        """source_interaction_id 为 None → 不标记."""
        extractor = AnchorExtractor(max_anchors=5)
        messages = _make_messages(5)

        snapshot = MemorySnapshot(
            core_facts=[
                _make_fact("f1", source_interaction_id=None),
                _make_fact("f2", source_interaction_id="2"),
            ],
        )

        indices = extractor.extract(
            session_id="session-1",
            memory_snapshot=snapshot,
            messages=messages,
        )

        assert indices == [2]

    def test_duplicate_indices_deduplicated(self):
        """多条事实指向同一消息 → 索引去重."""
        extractor = AnchorExtractor(max_anchors=5)
        messages = _make_messages(5)

        snapshot = MemorySnapshot(
            core_facts=[
                _make_fact("f1", importance=0.9, source_interaction_id="2"),
                _make_fact("f2", importance=0.7, source_interaction_id="2"),  # 同一个索引
            ],
        )

        indices = extractor.extract(
            session_id="session-1",
            memory_snapshot=snapshot,
            messages=messages,
        )

        # 去重后只有 [2]
        assert indices == [2]

    def test_resolve_by_message_id_field(self):
        """通过 message_id 字段解析 source_interaction_id."""
        extractor = AnchorExtractor(max_anchors=5)
        messages = [
            {"role": "user", "content": "hello", "message_id": "msg-abc"},
            {"role": "assistant", "content": "hi", "message_id": "msg-def"},
            {"role": "user", "content": "ok", "message_id": "msg-ghi"},
        ]

        snapshot = MemorySnapshot(
            core_facts=[
                _make_fact("f1", source_interaction_id="msg-def"),  # 匹配 message_id
            ],
        )

        indices = extractor.extract(
            session_id="session-1",
            memory_snapshot=snapshot,
            messages=messages,
        )

        assert indices == [1]

    def test_custom_max_anchors(self):
        """自定义 max_anchors."""
        extractor = AnchorExtractor(max_anchors=3)
        messages = _make_messages(8)

        facts = []
        for i in range(6):
            facts.append(
                _make_fact(
                    f"f{i}",
                    importance=0.5 + i * 0.05,
                    source_interaction_id=str(i),
                )
            )

        snapshot = MemorySnapshot(core_facts=facts, working_facts=[])

        indices = extractor.extract(
            session_id="session-1",
            memory_snapshot=snapshot,
            messages=messages,
        )

        assert len(indices) == 3
        assert indices == [5, 4, 3]  # importance 最高 3 条：5, 4, 3


# ════════════════════════════════════════════════════════
# T-03-02：MemoryAwareCompressor 测试
# ════════════════════════════════════════════════════════


class TestMemoryAwareCompressor:
    """MemoryAwareCompressor 单元测试."""

    def test_compress_preserves_anchors(self):
        """锚点消息在压缩后保留原文."""
        compressor = MemoryAwareCompressor(
            hermes_compressor=None,  # 不用真实 Hermes compressor
            max_anchors=5,
        )
        messages = _make_messages(5)

        snapshot = MemorySnapshot(
            core_facts=[
                _make_fact("f1", importance=0.9, source_interaction_id="1"),
            ],
        )

        result = compressor.compress(
            session_id="session-1",
            messages=messages,
            memory_snapshot=snapshot,
        )

        # 锚点消息（索引 1）保留原文
        anchor_msgs = [m for m in result if m.get("_evogen_anchor")]
        assert len(anchor_msgs) == 1
        assert anchor_msgs[0]["content"] == "消息内容 1"

    def test_compress_no_snapshot_delegates(self):
        """无快照 → 委托给 Hermes compressor（不崩溃）."""
        compressor = MemoryAwareCompressor(hermes_compressor=None)
        messages = _make_messages(5)

        result = compressor.compress(
            session_id="session-1",
            messages=messages,
            memory_snapshot=None,
        )

        # 透传模式：消息完整返回
        assert len(result) == len(messages)

    def test_compress_empty_messages(self):
        """空消息列表 → 原样返回."""
        compressor = MemoryAwareCompressor()

        snapshot = MemorySnapshot(
            core_facts=[_make_fact("f1", source_interaction_id="0")],
        )

        result = compressor.compress(
            session_id="session-1",
            messages=[],
            memory_snapshot=snapshot,
        )

        assert result == []

    def test_extract_anchors_convenience(self):
        """extract_anchors 便捷方法返回锚点消息."""
        compressor = MemoryAwareCompressor(hermes_compressor=None, max_anchors=5)
        messages = _make_messages(5)

        snapshot = MemorySnapshot(
            core_facts=[
                _make_fact("f1", importance=0.9, source_interaction_id="2"),
            ],
        )

        anchors = compressor.extract_anchors(
            session_id="session-1",
            memory_snapshot=snapshot,
            messages=messages,
        )

        assert len(anchors) == 1
        assert anchors[0]["_evogen_anchor"] is True
        assert anchors[0]["content"] == "消息内容 2"

    def test_compress_no_anchors_delegates(self):
        """无锚点 → 正常委托压缩."""
        compressor = MemoryAwareCompressor(hermes_compressor=None)
        messages = _make_messages(5)

        # 快照中没有匹配当前 session 的记忆
        snapshot = MemorySnapshot(
            core_facts=[
                _make_fact("f1", source_session_id="other-session"),
            ],
        )

        result = compressor.compress(
            session_id="session-1",
            messages=messages,
            memory_snapshot=snapshot,
        )

        # 透传模式：消息完整返回
        assert len(result) == len(messages)

    def test_compress_with_mock_hermes_compressor(self):
        """使用 mock Hermes compressor 验证完整流程."""
        class MockHermesCompressor:
            def __init__(self):
                self.compress_called = False
                self.last_messages = None

            def compress(
                self,
                messages,
                current_tokens=None,
                focus_topic=None,
            ):
                self.compress_called = True
                self.last_messages = messages
                # Mock: 对每条消息添加 "[compressed]" 前缀
                result = []
                for msg in messages:
                    new_msg = dict(msg)
                    new_msg["content"] = f"[compressed] {msg['content']}"
                    result.append(new_msg)
                return result

        mock = MockHermesCompressor()
        compressor = MemoryAwareCompressor(
            hermes_compressor=mock,
            max_anchors=5,
        )

        messages = _make_messages(5)

        snapshot = MemorySnapshot(
            core_facts=[
                _make_fact("f1", importance=0.9, source_interaction_id="2"),
            ],
        )

        result = compressor.compress(
            session_id="session-1",
            messages=messages,
            memory_snapshot=snapshot,
        )

        # Hermes compressor 被调用
        assert mock.compress_called
        # 传给 Hermes 的消息不包含锚点消息（索引 2）
        hermes_msgs = mock.last_messages
        hermes_contents = [m["content"] for m in hermes_msgs]
        assert "消息内容 2" not in hermes_contents

        # 结果中锚点消息保留原文
        anchor_msgs = [m for m in result if m.get("_evogen_anchor")]
        assert len(anchor_msgs) == 1
        assert anchor_msgs[0]["content"] == "消息内容 2"
        assert "[compressed]" not in anchor_msgs[0]["content"]


# ════════════════════════════════════════════════════════
# 集成场景测试
# ════════════════════════════════════════════════════════


class TestAnchorCompactionIntegration:
    """AnchorExtractor + MemoryAwareCompressor 集成场景."""

    def test_full_flow_multiple_sessions(self):
        """多会话记忆混合场景：只标记当前会话锚点."""
        extractor = AnchorExtractor(max_anchors=5)
        messages = _make_messages(10)

        snapshot = MemorySnapshot(
            core_facts=[
                # 当前会话
                _make_fact("f1", importance=0.9, source_session_id="s1",
                          source_interaction_id="2"),
                _make_fact("f2", importance=0.7, source_session_id="s1",
                          source_interaction_id="5"),
                # 其他会话（不标记）
                _make_fact("f3", importance=0.8, source_session_id="s2",
                          source_interaction_id="3"),
                _make_fact("f4", importance=0.95, source_session_id="s3",
                          source_interaction_id="1"),
            ],
        )

        indices = extractor.extract(
            session_id="s1",
            memory_snapshot=snapshot,
            messages=messages,
        )

        # 只有 s1 的事实被标记
        assert sorted(indices) == [2, 5]

    def test_mixed_layer_filtering(self):
        """混合 layer 过滤：只取 core + working."""
        extractor = AnchorExtractor(max_anchors=5)
        messages = _make_messages(5)

        snapshot = MemorySnapshot(
            core_facts=[
                _make_fact("f1", layer="core", importance=0.9,
                          source_interaction_id="1"),
            ],
            working_facts=[
                _make_fact("f2", layer="working", importance=0.7,
                          source_interaction_id="2"),
            ],
            transient_facts=[
                _make_fact("f3", layer="transient", importance=0.8,
                          source_interaction_id="3"),
            ],
        )

        indices = extractor.extract(
            session_id="session-1",
            memory_snapshot=snapshot,
            messages=messages,
        )

        # core(1) + working(2) 都取，transient(3) 不取
        assert sorted(indices) == [1, 2]

    def test_importance_tie_breaker(self):
        """importance 相同时保持源顺序稳定."""
        extractor = AnchorExtractor(max_anchors=3)
        messages = _make_messages(6)

        snapshot = MemorySnapshot(
            core_facts=[
                _make_fact("f1", importance=0.5, source_interaction_id="2"),
                _make_fact("f2", importance=0.5, source_interaction_id="4"),
                _make_fact("f3", importance=0.5, source_interaction_id="1"),
                _make_fact("f4", importance=0.5, source_interaction_id="5"),
            ],
        )

        indices = extractor.extract(
            session_id="session-1",
            memory_snapshot=snapshot,
            messages=messages,
        )

        # 只取 3 条（importance 相同，按出现顺序稳定）
        assert len(indices) == 3
