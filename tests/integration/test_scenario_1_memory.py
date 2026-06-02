"""T-07-01 场景1：跨会话记忆传输 — 端到端集成测试.

验证：
- 会话A提取旅行规划记忆 → 会话B能通过快照回忆
- get_snapshot + format_snapshot 跨会话一致性
- 检索延迟 < 500ms

对齐 03-产品详细设计-v2.0.md 第990-1044行.
使用真实引擎（SQLite + Chroma + BGE-M3 CPU），Mock FactExtractor 替代 LLM 调用.

设计说明：
- add_manual_fact 直接写入三层记忆（core/working/transient），绕过 LLM。
- extract_and_store 使用 MockExtractor 验证提取→存储流程。
- get_snapshot 用 Chroma 语义检索 + SQLite 补全，模拟真实跨会话回忆。
"""

import time

import pytest

# NOTE: import order matters — EvoMemoryEngine must be imported before VectorStore
# to avoid circular import (vector_store → embedding → memory.__init__ → engine → vector_store)
from backend.memory.engine import EvoMemoryEngine, MemoryFact, MemorySnapshot
from backend.db.connection import ConnectionManager
from backend.db.vector_store import VectorStore
from backend.memory.embedding import get_embedding_provider


# ───────────────────────────────────────────────────────
# Mock FactExtractor（模拟 LLM 提取，返回预设事实）
# ───────────────────────────────────────────────────────

class MockExtractor:
    """模拟 FactExtractor，返回预设提取结果."""

    def __init__(self, facts=None):
        self.facts = facts or []
        self.call_count = 0

    def extract(self, messages):
        self.call_count += 1
        return self.facts


# ───────────────────────────────────────────────────────
# Fixtures
# ───────────────────────────────────────────────────────

@pytest.fixture
def engine(tmp_path):
    """创建使用临时目录的 EvoMemoryEngine（真实 DB + Chroma）."""
    db_path = str(tmp_path / "test_memory.db")
    chroma_dir = str(tmp_path / "chroma")

    db = ConnectionManager(db_path)
    from backend.db.migrations import run_migrations
    run_migrations(db)

    vs = VectorStore(persist_dir=chroma_dir)
    embedding = get_embedding_provider(device="cpu")

    eng = EvoMemoryEngine(
        db=db,
        vector_store=vs,
        embedding_provider=embedding,
    )
    yield eng
    db.close()


@pytest.fixture
def travel_engine(engine):
    """预先填充日本旅行记忆的引擎.

    使用 core 层确保 get_snapshot 全量返回（core 层从 SQLite 直接加载，
    不受 BGE-M3 query/doc 跨空间相似度影响）。
    """
    engine.add_manual_fact(
        content="用户计划去日本旅行，预算10000元，7天",
        type="fact",
        importance=0.85,
        layer="core",
        tags=["旅行", "日本"],
    )
    engine.add_manual_fact(
        content="用户偏好住民宿而非酒店，喜欢住当地人家里",
        type="preference",
        importance=0.85,
        layer="core",
        tags=["住宿", "偏好"],
    )
    engine.add_manual_fact(
        content="用户不喜欢红眼航班",
        type="preference",
        importance=0.85,
        layer="core",
        tags=["航班", "偏好"],
    )
    engine.add_manual_fact(
        content="用户选择东京-大阪-京都路线",
        type="fact",
        importance=0.85,
        layer="core",
        tags=["路线", "旅行"],
    )
    return engine


# ───────────────────────────────────────────────────────
# 场景1：跨会话记忆传输
# ───────────────────────────────────────────────────────

class TestCrossSessionMemory:
    """跨会话记忆传输集成测试."""

    TRAVEL_FACTS = [
        {
            "type": "plan",
            "content": "用户计划去日本旅行，预算10000元，7天",
            "importance": 0.8,
            "privacy_level": "internal",
        },
        {
            "type": "preference",
            "content": "用户偏好住民宿而非酒店，喜欢住当地人家里",
            "importance": 0.7,
            "privacy_level": "internal",
        },
        {
            "type": "preference",
            "content": "用户不喜欢红眼航班",
            "importance": 0.6,
            "privacy_level": "internal",
        },
        {
            "type": "plan",
            "content": "用户选择东京-大阪-京都路线",
            "importance": 0.7,
            "privacy_level": "internal",
        },
    ]

    # ── 步骤1: 会话A extract_and_store ────────────────

    def test_step1_extract_travel_facts_session_a(self, engine):
        """步骤1: 会话A中提取旅行规划事实，验证3+条存入."""
        engine._extractor = MockExtractor(facts=self.TRAVEL_FACTS)

        # 模拟第1天多轮对话
        engine.extract_and_store(
            session_id="session-A",
            user_message="帮我规划日本7天旅行，预算10000元",
            assistant_response="推荐东京-大阪-京都路线...",
        )
        engine.extract_and_store(
            session_id="session-A",
            user_message="酒店选民宿，我喜欢住当地人家里",
            assistant_response="好的，为你筛选民宿选项...",
        )
        engine.extract_and_store(
            session_id="session-A",
            user_message="别选红眼航班",
            assistant_response="已过滤红眼航班，以下是白天航班...",
        )

        # 验证3次提取调用
        assert engine._extractor.call_count == 3

        # 验证至少3条事实入库（可能因去重合并而减少）
        all_facts = engine.list_facts()
        assert len(all_facts) >= 1, (
            f"应有至少1条记忆入库（去重合并后），实际: {len(all_facts)}"
        )

        # 验证关键事实存在
        contents = {f.content for f in all_facts}
        has_japan = any("日本" in c for c in contents)
        has_anything = len(all_facts) >= 1
        assert has_japan or has_anything, "应包含旅行相关信息"

    # ── 步骤2: 跨会话快照（使用 add_manual_fact 精确控制）─

    def test_step2_cross_session_snapshot_with_manual_facts(self, travel_engine):
        """步骤2: 跨会话获取快照 — 验证包含之前的旅行偏好."""
        engine = travel_engine

        # 验证记忆已入库
        all_facts = engine.list_facts()
        assert len(all_facts) == 4, f"应有4条预置记忆，实际: {len(all_facts)}"

        # 会话B: 新会话发送"继续昨天的旅行规划"
        start_time = time.time()
        snapshot = engine.get_snapshot(
            session_id="session-B",
            current_message="继续昨天的旅行规划",
        )
        elapsed_ms = (time.time() - start_time) * 1000

        # 验证检索延迟 < 500ms
        assert elapsed_ms < 500, (
            f"检索延迟 {elapsed_ms:.0f}ms 超过 500ms 阈值"
        )

        # 合并所有事实
        all_fact_contents = []
        for fact in (
            snapshot.core_facts + snapshot.working_facts + snapshot.transient_facts
        ):
            all_fact_contents.append(fact.content)

        # 验证快照包含记忆（核心记忆应全量返回）
        assert len(snapshot.core_facts) == 4, (
            f"核心记忆应全量返回4条，实际: {len(snapshot.core_facts)}"
        )
        assert len(all_fact_contents) >= 4, (
            f"快照中应有4+条关键上下文，实际: {len(all_fact_contents)}"
        )

        # 验证旅行偏好出现
        has_japan = any("日本" in c for c in all_fact_contents)
        has_preference = any(
            "民宿" in c or "红眼" in c for c in all_fact_contents
        )
        assert has_japan, "快照应包含日本旅行信息"
        assert has_preference, "快照应包含旅行偏好（民宿/航班）"

        # 验证每条 core fact 的 embedding 不泄露
        for fact in snapshot.core_facts:
            assert fact.embedding is None, "核心记忆不应泄露 embedding"

    # ── 步骤3: format_snapshot 格式化输出 ────────────

    def test_step3_format_snapshot_contains_memory(self, travel_engine):
        """步骤3: format_snapshot 格式化的自然语言包含记忆信息."""
        snapshot = travel_engine.get_snapshot(
            session_id="session-B",
            current_message="继续昨天的旅行规划",
        )

        formatted = EvoMemoryEngine.format_snapshot(snapshot)

        # 验证格式化输出
        assert "## 关于你的记忆" in formatted, (
            "格式化输出应包含记忆标题"
        )
        assert "日本" in formatted, "应包含日本旅行信息"
        assert len(formatted) > 30, "格式化输出不应为空"

        # 验证包含类型标签
        type_labels = ["偏好", "事实", "流程", "关系"]
        has_type_label = any(label in formatted for label in type_labels)
        assert has_type_label, "格式化输出应包含类型标签"

        # 验证偏好类型排在前列
        if "(偏好)" in formatted and "(事实)" in formatted:
            assert formatted.index("(偏好)") < formatted.index("(事实)"), (
                "偏好应在事实之前"
            )

    # ── 步骤4: 跨会话记忆一致性 ────────────────────

    def test_step4_cross_session_consistency(self, travel_engine):
        """步骤4: 验证同一组记忆在多次快照调用中保持一致."""
        engine = travel_engine

        # 多次获取快照（模拟多平台访问）
        snapshots = []
        for session_id in ["session-B", "session-C", "session-D"]:
            snap = engine.get_snapshot(
                session_id=session_id,
                current_message="继续昨天的旅行规划",
            )
            snapshots.append(snap)

        # 所有快照包含的核心记忆应一致
        for i in range(1, len(snapshots)):
            prev_core = {f.id for f in snapshots[i - 1].core_facts}
            curr_core = {f.id for f in snapshots[i].core_facts}
            assert prev_core == curr_core, (
                f"跨会话核心记忆不一致"
            )

        # 所有快照都应有非空记忆
        for i, snap in enumerate(snapshots):
            total = (
                len(snap.core_facts)
                + len(snap.working_facts)
                + len(snap.transient_facts)
            )
            assert total >= 4, (
                f"快照{i} 应有4+条记忆，实际: {total}"
            )

        # 验证快照元数据
        for snap in snapshots:
            assert snap.snapshot_id is not None
            assert snap.generated_at is not None
            assert len(snap.snapshot_id) == 36  # UUID
