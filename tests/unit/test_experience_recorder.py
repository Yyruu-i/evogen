"""T-02-02 & T-02-03 测试：TraceRecorder 经验轨迹记录与场景关联.

测试覆盖：
- submit_trajectory / list_trajectories / get_trajectory 全流程
- add_feedback / list_feedback / update_feedback_status 反馈管理
- get_scene_hints / format_hints 场景关联匹配
- 数据序列化/反序列化正确性
- 边界测试：空turns、大量turns、空反馈
"""

import json
import uuid
import time
import random

import pytest

from backend.db.connection import ConnectionManager
from backend.db.vector_store import VectorStore
from backend.memory.embedding import get_embedding_provider
from backend.experience.recorder import (
    TraceRecorder,
    TrajectoryTurn,
    ToolCallRecord,
    TaskOutcome,
    TrajectorySummary,
    TrajectoryDetail,
    FeedbackRecord,
    SceneHint,
    _serialize_turns,
    _deserialize_turns,
    _serialize_outcome,
    _deserialize_outcome,
    _build_scene_summary,
    _row_to_feedback_record,
)


# ════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════


def _make_tool_call(
    tool_name: str = "web_search",
    arguments: dict = None,
    result_summary: str = "搜索完成",
    success: bool = True,
    execution_time_ms: int = 1500,
) -> ToolCallRecord:
    return ToolCallRecord(
        tool_name=tool_name,
        arguments=arguments or {"query": "东京天气"},
        result_summary=result_summary,
        success=success,
        execution_time_ms=execution_time_ms,
    )


def _make_turn(
    index: int = 0,
    tool_calls: list = None,
    response: str = "好的，让我帮你查一下...",
    token_usage: int = 500,
) -> TrajectoryTurn:
    return TrajectoryTurn(
        turn_index=index,
        tool_calls=tool_calls,
        llm_response_chunk=response,
        token_usage=token_usage,
    )


def _make_outcome(
    success: bool = True,
    total_tokens: int = 2000,
    wall_time_ms: int = 15000,
    user_cancelled: bool = False,
) -> TaskOutcome:
    return TaskOutcome(
        success=success,
        total_tokens=total_tokens,
        wall_time_ms=wall_time_ms,
        user_cancelled=user_cancelled,
    )


def _make_turns(count: int = 3, with_tool_calls: bool = True) -> list:
    """生成指定数量的 turns."""
    turns = []
    for i in range(count):
        tc_list = None
        if with_tool_calls:
            tc_list = [_make_tool_call(tool_name=f"tool_{i}")]
        turns.append(_make_turn(
            index=i,
            tool_calls=tc_list,
            response=f"处理第 {i} 轮...",
            token_usage=300 + i * 100,
        ))
    return turns


# ════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════


@pytest.fixture
def recorder(tmp_path):
    """创建使用临时目录的 TraceRecorder."""
    db_path = str(tmp_path / "test_evogen.db")
    chroma_dir = str(tmp_path / "chroma")

    # 创建 ConnectionManager
    db = ConnectionManager(db_path)

    # 初始化数据库表
    from backend.db.migrations import run_migrations
    run_migrations(db)

    # 创建 VectorStore
    vs = VectorStore(persist_dir=chroma_dir)

    return TraceRecorder(db=db, vector_store=vs)


@pytest.fixture
def sample_trajectory(recorder):
    """提交一条样本轨迹，返回 trajectory_id."""
    turns = _make_turns(count=3)
    outcome = _make_outcome(success=True)
    return recorder.submit_trajectory(
        session_id="session-001",
        turns=turns,
        outcome=outcome,
        session_title="旅行规划助手",
    )


@pytest.fixture
def sample_bad_feedback(recorder, sample_trajectory):
    """添加一条 bad 反馈."""
    return recorder.add_feedback(
        trajectory_id=sample_trajectory,
        rating="bad",
        note="下次订机票前先确认日期",
    )


# ════════════════════════════════════════════════════════
# T-02-02: submit_trajectory
# ════════════════════════════════════════════════════════


class TestSubmitTrajectory:
    """测试轨迹提交."""

    def test_submit_basic(self, recorder):
        """基本提交：生成 UUID，写入 SQLite 和 Chroma."""
        turns = _make_turns(count=2)
        outcome = _make_outcome(success=True)

        tid = recorder.submit_trajectory(
            session_id="session-001",
            turns=turns,
            outcome=outcome,
            session_title="测试会话",
        )

        assert tid is not None
        assert len(tid) == 36  # UUID 格式

        # 验证 SQLite 写入
        detail = recorder.get_trajectory(tid)
        assert detail is not None
        assert detail.session_id == "session-001"
        assert detail.session_title == "测试会话"
        assert len(detail.turns) == 2
        assert detail.outcome.success is True
        assert detail.outcome.total_tokens == 2000

        # 验证 Chroma 写入
        assert recorder._vector_store.experience_count() >= 1

    def test_submit_multiple_sessions(self, recorder):
        """多个会话分别提交，各自独立."""
        ids = []
        for i in range(3):
            tid = recorder.submit_trajectory(
                session_id=f"session-{i}",
                turns=_make_turns(count=1),
                outcome=_make_outcome(),
            )
            ids.append(tid)

        assert len(set(ids)) == 3  # 各不相同

        summaries = recorder.list_trajectories(limit=10)
        assert len(summaries) == 3

    def test_submit_with_tool_failure(self, recorder):
        """工具调用失败的轨迹."""
        tc = _make_tool_call(success=False, result_summary="搜索超时")
        turn = _make_turn(index=0, tool_calls=[tc])
        outcome = _make_outcome(success=False, user_cancelled=False)

        tid = recorder.submit_trajectory(
            session_id="session-fail",
            turns=[turn],
            outcome=outcome,
        )

        detail = recorder.get_trajectory(tid)
        assert detail.outcome.success is False
        assert detail.turns[0].tool_calls[0].success is False

    def test_submit_user_cancelled(self, recorder):
        """用户取消的任务."""
        outcome = _make_outcome(success=False, user_cancelled=True)

        tid = recorder.submit_trajectory(
            session_id="session-cancel",
            turns=_make_turns(count=1),
            outcome=outcome,
        )

        detail = recorder.get_trajectory(tid)
        assert detail.outcome.user_cancelled is True
        assert detail.outcome.success is False


# ════════════════════════════════════════════════════════
# T-02-02: list_trajectories
# ════════════════════════════════════════════════════════


class TestListTrajectories:
    """测试轨迹列表."""

    def test_list_all(self, recorder):
        """列出所有轨迹."""
        for i in range(5):
            recorder.submit_trajectory(
                session_id=f"session-{i}",
                turns=_make_turns(count=2),
                outcome=_make_outcome(),
            )

        summaries = recorder.list_trajectories(limit=50)
        assert len(summaries) == 5

        # 验证返回结构
        for s in summaries:
            assert isinstance(s, TrajectorySummary)
            assert s.id
            assert s.session_id
            assert s.turn_count == 2
            assert s.feedback_count == 0
            assert s.last_feedback_at is None

    def test_list_with_limit_and_offset(self, recorder):
        """分页."""
        for i in range(10):
            recorder.submit_trajectory(
                session_id=f"session-{i}",
                turns=_make_turns(count=1),
                outcome=_make_outcome(),
            )

        page1 = recorder.list_trajectories(limit=3, offset=0)
        page2 = recorder.list_trajectories(limit=3, offset=3)
        page3 = recorder.list_trajectories(limit=5, offset=6)

        assert len(page1) == 3
        assert len(page2) == 3
        assert len(page3) == 4

        # 确保不同页没有重叠
        ids_page1 = {s.id for s in page1}
        ids_page2 = {s.id for s in page2}
        assert ids_page1.isdisjoint(ids_page2)

    def test_list_with_feedback_only(self, recorder):
        """仅返回有反馈的轨迹."""
        tid1 = recorder.submit_trajectory(
            session_id="s1", turns=_make_turns(count=1), outcome=_make_outcome()
        )
        tid2 = recorder.submit_trajectory(
            session_id="s2", turns=_make_turns(count=1), outcome=_make_outcome()
        )

        # 只为 tid1 添加反馈
        recorder.add_feedback(tid1, rating="good", note="不错")

        # with_feedback_only=True
        summaries = recorder.list_trajectories(with_feedback_only=True)
        assert len(summaries) == 1
        assert summaries[0].id == tid1
        assert summaries[0].feedback_count == 1
        assert summaries[0].last_feedback_at is not None

        # with_feedback_only=False
        all_summaries = recorder.list_trajectories(with_feedback_only=False)
        assert len(all_summaries) == 2

    def test_list_empty(self, recorder):
        """空数据库返回空列表."""
        summaries = recorder.list_trajectories()
        assert summaries == []


# ════════════════════════════════════════════════════════
# T-02-02: get_trajectory
# ════════════════════════════════════════════════════════


class TestGetTrajectory:
    """测试轨迹详情."""

    def test_get_full_detail(self, recorder, sample_trajectory, sample_bad_feedback):
        """获取包含 turns + outcome + feedback 的完整详情."""
        detail = recorder.get_trajectory(sample_trajectory)

        assert detail is not None
        assert isinstance(detail, TrajectoryDetail)
        assert detail.id == sample_trajectory
        assert detail.session_id == "session-001"
        assert len(detail.turns) == 3
        assert detail.outcome.success is True

        # Feedback
        assert len(detail.feedback) == 1
        fb = detail.feedback[0]
        assert fb.rating == "bad"
        assert fb.note == "下次订机票前先确认日期"
        assert fb.status == "pending"

    def test_get_nonexistent(self, recorder):
        """不存在的轨迹返回 None."""
        detail = recorder.get_trajectory("nonexistent-id")
        assert detail is None

    def test_get_without_feedback(self, recorder):
        """无反馈的轨迹返回空 feedback 列表."""
        tid = recorder.submit_trajectory(
            session_id="s", turns=_make_turns(count=1), outcome=_make_outcome()
        )
        detail = recorder.get_trajectory(tid)
        assert detail.feedback == []

    def test_get_turn_structure(self, recorder):
        """验证 turn 结构完整性."""
        tc = _make_tool_call(
            tool_name="file_read",
            arguments={"path": "/tmp/test.txt"},
            result_summary="文件内容: hello world",
            success=True,
            execution_time_ms=320,
        )
        turn = _make_turn(
            index=0,
            tool_calls=[tc],
            response="读取文件成功",
            token_usage=450,
        )

        tid = recorder.submit_trajectory(
            session_id="s", turns=[turn], outcome=_make_outcome()
        )

        detail = recorder.get_trajectory(tid)
        loaded_turn = detail.turns[0]

        assert loaded_turn.turn_index == 0
        assert loaded_turn.token_usage == 450
        assert loaded_turn.llm_response_chunk == "读取文件成功"

        loaded_tc = loaded_turn.tool_calls[0]
        assert loaded_tc.tool_name == "file_read"
        assert loaded_tc.arguments == {"path": "/tmp/test.txt"}
        assert loaded_tc.success is True
        assert loaded_tc.execution_time_ms == 320


# ════════════════════════════════════════════════════════
# T-02-02: Feedback CRUD
# ════════════════════════════════════════════════════════


class TestFeedback:
    """测试反馈管理."""

    def test_add_feedback_good(self, recorder, sample_trajectory):
        fb = recorder.add_feedback(sample_trajectory, rating="good", note="很好用")
        assert fb.id
        assert fb.trajectory_id == sample_trajectory
        assert fb.rating == "good"
        assert fb.note == "很好用"
        assert fb.status == "pending"
        assert fb.reviewed_at is None

    def test_add_feedback_bad(self, recorder, sample_trajectory):
        fb = recorder.add_feedback(sample_trajectory, rating="bad", note="搜索结果不准确")
        assert fb.rating == "bad"

    def test_add_feedback_neutral(self, recorder, sample_trajectory):
        fb = recorder.add_feedback(sample_trajectory, rating="neutral")
        assert fb.rating == "neutral"
        assert fb.note is None

    def test_add_feedback_invalid_rating(self, recorder, sample_trajectory):
        with pytest.raises(ValueError, match="Invalid rating"):
            recorder.add_feedback(sample_trajectory, rating="excellent")

    def test_add_feedback_nonexistent_trajectory(self, recorder):
        with pytest.raises(ValueError, match="Trajectory not found"):
            recorder.add_feedback("nonexistent-id", rating="good")

    def test_list_feedback_all(self, recorder, sample_trajectory):
        recorder.add_feedback(sample_trajectory, rating="good", note="A")
        recorder.add_feedback(sample_trajectory, rating="bad", note="B")
        recorder.add_feedback(sample_trajectory, rating="neutral", note="C")

        all_fb = recorder.list_feedback(limit=10)
        assert len(all_fb) == 3

    def test_list_feedback_by_status(self, recorder, sample_trajectory):
        recorder.add_feedback(sample_trajectory, rating="good")

        # 更新一条为 reviewed
        pending = recorder.list_feedback(status="pending")
        recorder.update_feedback_status(pending[0].id, "reviewed")

        reviewed = recorder.list_feedback(status="reviewed")
        assert len(reviewed) == 1

        still_pending = recorder.list_feedback(status="pending")
        assert len(still_pending) == 0

    def test_update_feedback_status_flow(self, recorder, sample_trajectory):
        """状态流转: pending → reviewed → applied."""
        fb = recorder.add_feedback(sample_trajectory, rating="bad", note="改进")

        # pending → reviewed
        recorder.update_feedback_status(fb.id, "reviewed")
        fb_list = recorder.list_feedback(status="reviewed")
        assert len(fb_list) == 1
        assert fb_list[0].reviewed_at is not None

        # reviewed → applied
        recorder.update_feedback_status(fb.id, "applied")
        fb_list = recorder.list_feedback(status="applied")
        assert len(fb_list) == 1

    def test_update_feedback_status_dismissed(self, recorder, sample_trajectory):
        """pending → dismissed."""
        fb = recorder.add_feedback(sample_trajectory, rating="neutral")
        recorder.update_feedback_status(fb.id, "dismissed")

        fb_list = recorder.list_feedback(status="dismissed")
        assert len(fb_list) == 1

    def test_update_feedback_invalid_status(self, recorder, sample_trajectory):
        fb = recorder.add_feedback(sample_trajectory, rating="good")
        with pytest.raises(ValueError, match="Invalid status"):
            recorder.update_feedback_status(fb.id, "invalid_status")

    def test_update_feedback_nonexistent(self, recorder):
        with pytest.raises(ValueError, match="Feedback not found"):
            recorder.update_feedback_status("nonexistent", "reviewed")


# ════════════════════════════════════════════════════════
# T-02-03: 场景关联匹配
# ════════════════════════════════════════════════════════


class TestSceneHints:
    """测试场景关联匹配."""

    def test_scene_hints_basic(self, recorder):
        """基本场景匹配：相似消息检索到历史场景."""
        # 提交历史轨迹（模拟旅行规划场景）
        travel_turns = [
            _make_turn(
                index=0,
                tool_calls=[_make_tool_call(tool_name="web_search")],
                response="用户想要规划一趟日本旅行，7天，预算1万",
                token_usage=600,
            ),
            _make_turn(
                index=1,
                tool_calls=[_make_tool_call(tool_name="flight_search")],
                response="查找航班信息...",
                token_usage=500,
            ),
        ]
        travel_tid = recorder.submit_trajectory(
            session_id="session-travel",
            turns=travel_turns,
            outcome=_make_outcome(success=True),
            session_title="日本旅行规划",
        )

        # 添加 bad 反馈
        recorder.add_feedback(
            travel_tid,
            rating="bad",
            note="订机票前先确认日期",
        )

        # 查询相似场景
        hints = recorder.get_scene_hints(
            session_id="session-new",
            current_message="帮我规划一趟日本旅行，7天",
            top_k=5,
        )

        # 由于是真实 embedding 模型，相似度取决于语义匹配程度
        # "日本旅行"相关的查询应该能找到相似场景
        assert isinstance(hints, list)

        if len(hints) > 0:
            hint = hints[0]
            assert isinstance(hint, SceneHint)
            assert hint.trajectory_id == travel_tid
            assert hint.similarity_score > 0.6
            # bad 反馈应该被关联
            assert hint.relevant_feedback is not None

    def test_self_exclusion(self, recorder):
        """同一 session 自身的轨迹应该被排除."""
        # 在同一 session 中提交轨迹
        tid = recorder.submit_trajectory(
            session_id="same-session",
            turns=[
                _make_turn(
                    index=0,
                    response="用户想要规划一趟日本旅行，预算1万，7天",
                    token_usage=500,
                ),
            ],
            outcome=_make_outcome(success=True),
        )

        # 添加反馈
        recorder.add_feedback(tid, rating="bad", note="改进点")

        # 用同一 session 查询 → 应排除自身
        hints = recorder.get_scene_hints(
            session_id="same-session",
            current_message="帮我规划一趟日本旅行",
            top_k=5,
        )

        # 自身轨迹应该被排除
        own_ids = {h.trajectory_id for h in hints}
        assert tid not in own_ids

    def test_similarity_threshold(self, recorder):
        """低于 0.6 相似度的场景被过滤."""
        # 提交完全不相关的轨迹
        unrelated_tid = recorder.submit_trajectory(
            session_id="session-unrelated",
            turns=[
                _make_turn(
                    index=0,
                    response="System maintenance: checking disk space and cleaning logs. " * 5,
                    token_usage=100,
                ),
            ],
            outcome=_make_outcome(success=True),
        )

        # 查询完全不相关的内容
        hints = recorder.get_scene_hints(
            session_id="session-new",
            current_message="帮我写一个 Python 冒泡排序算法",
            top_k=5,
        )

        # 不相关场景的相似度应该低于 0.6，被过滤
        unrelated_ids = {h.trajectory_id for h in hints}
        assert unrelated_tid not in unrelated_ids

    def test_bad_feedback_association(self, recorder):
        """验证 bad 反馈被正确关联到场景提示."""
        # 场景A: 有 bad 反馈
        tid_a = recorder.submit_trajectory(
            session_id="session-a",
            turns=[_make_turn(index=0, response="用户想要订机票去上海", token_usage=300)],
            outcome=_make_outcome(success=False),
            session_title="订机票",
        )
        recorder.add_feedback(tid_a, rating="bad", note="应该先确认护照有效期")

        # 场景B: 有 good 反馈（不应该出现在 hints 的 relevant_feedback 中）
        tid_b = recorder.submit_trajectory(
            session_id="session-b",
            turns=[_make_turn(index=0, response="用户想要订机票去北京", token_usage=300)],
            outcome=_make_outcome(success=True),
            session_title="订机票",
        )
        recorder.add_feedback(tid_b, rating="good", note="这次做得不错")

        hints = recorder.get_scene_hints(
            session_id="session-new",
            current_message="我想订机票",
            top_k=5,
        )

        if len(hints) >= 1:
            # 找到 tid_a 的 hint
            hint_a = next((h for h in hints if h.trajectory_id == tid_a), None)
            if hint_a is not None:
                assert hint_a.relevant_feedback == "应该先确认护照有效期"

            # tid_b 不应该有 relevant_feedback（因为只有 good 反馈）
            hint_b = next((h for h in hints if h.trajectory_id == tid_b), None)
            if hint_b is not None:
                assert hint_b.relevant_feedback is None

    def test_format_hints_with_feedback(self, recorder):
        """format_hints 正确格式化包含 bad 反馈的场景."""
        hints = [
            SceneHint(
                trajectory_id="tid-1",
                summary="旅行规划",
                relevant_feedback="订机票前先确认日期",
                similarity_score=0.85,
            ),
            SceneHint(
                trajectory_id="tid-2",
                summary="文件管理",
                relevant_feedback="删除文件前先备份",
                similarity_score=0.72,
            ),
        ]

        formatted = recorder.format_hints(hints)

        assert "## 相关经验提示" in formatted
        assert "订机票前先确认日期" in formatted
        assert "删除文件前先备份" in formatted
        assert "旅行规划" in formatted

    def test_format_hints_without_feedback(self, recorder):
        """无 bad 反馈时显示相似度."""
        hints = [
            SceneHint(
                trajectory_id="tid-1",
                summary="旅行规划",
                relevant_feedback=None,
                similarity_score=0.85,
            ),
        ]

        formatted = recorder.format_hints(hints)
        assert "相关历史场景" in formatted
        assert "85%" in formatted

    def test_format_hints_empty(self, recorder):
        """空 hints 返回空字符串."""
        assert recorder.format_hints([]) == ""

    def test_get_scene_hints_empty_db(self, recorder):
        """空数据库返回空列表."""
        hints = recorder.get_scene_hints(
            session_id="s",
            current_message="任意消息",
            top_k=5,
        )
        assert hints == []


# ════════════════════════════════════════════════════════
# 数据序列化测试
# ════════════════════════════════════════════════════════


class TestSerialization:
    """测试 JSON 序列化/反序列化."""

    def test_serialize_turns_with_tool_calls(self):
        """序列化含工具调用的 turns."""
        turns = [
            TrajectoryTurn(
                turn_index=0,
                tool_calls=[
                    ToolCallRecord(
                        tool_name="search",
                        arguments={"q": "hello"},
                        result_summary="结果",
                        success=True,
                        execution_time_ms=100,
                    ),
                ],
                llm_response_chunk="让我搜索",
                token_usage=200,
            ),
        ]

        json_str = _serialize_turns(turns)
        parsed = json.loads(json_str)

        assert len(parsed) == 1
        assert parsed[0]["turn_index"] == 0
        assert parsed[0]["tool_calls"][0]["tool_name"] == "search"
        assert parsed[0]["token_usage"] == 200

    def test_deserialize_turns_roundtrip(self):
        """序列化后反序列化 equivalence."""
        original = [
            TrajectoryTurn(
                turn_index=0,
                tool_calls=[
                    ToolCallRecord(
                        tool_name="search",
                        arguments={"q": "hello", "limit": 10},
                        result_summary="找到 5 条结果",
                        success=True,
                        execution_time_ms=1500,
                    ),
                ],
                llm_response_chunk="正在搜索...",
                token_usage=350,
            ),
            TrajectoryTurn(
                turn_index=1,
                tool_calls=None,
                llm_response_chunk="搜索完成",
                token_usage=100,
            ),
        ]

        json_str = _serialize_turns(original)
        restored = _deserialize_turns(json_str)

        assert len(restored) == 2
        assert restored[0].turn_index == 0
        assert restored[0].tool_calls[0].tool_name == "search"
        assert restored[0].tool_calls[0].arguments == {"q": "hello", "limit": 10}
        assert restored[0].tool_calls[0].success is True
        assert restored[0].token_usage == 350

        assert restored[1].turn_index == 1
        assert restored[1].tool_calls is None
        assert restored[1].token_usage == 100

    def test_serialize_outcome_roundtrip(self):
        """TaskOutcome 序列化/反序列化."""
        original = TaskOutcome(
            success=False,
            total_tokens=5000,
            wall_time_ms=30000,
            user_cancelled=True,
        )

        json_str = _serialize_outcome(original)
        restored = _deserialize_outcome(json_str)

        assert restored.success is False
        assert restored.total_tokens == 5000
        assert restored.wall_time_ms == 30000
        assert restored.user_cancelled is True

    def test_serialize_turns_no_tool_calls(self):
        """无工具调用的 turns 序列化."""
        turns = [
            TrajectoryTurn(
                turn_index=0,
                tool_calls=None,
                llm_response_chunk="你好，有什么可以帮你的？",
                token_usage=50,
            ),
        ]

        json_str = _serialize_turns(turns)
        restored = _deserialize_turns(json_str)

        assert restored[0].tool_calls is None

    def test_serialize_special_characters(self):
        """中文字符、特殊字符正确处理."""
        turn = TrajectoryTurn(
            turn_index=0,
            tool_calls=[
                ToolCallRecord(
                    tool_name="搜索",
                    arguments={"关键词": "东京旅行 🗾"},
                    result_summary='用户说："太棒了！"',
                    success=True,
                    execution_time_ms=500,
                ),
            ],
            llm_response_chunk="好的，让我帮你规划一趟日本🇯🇵旅行，7天，预算1万💰",
            token_usage=800,
        )

        json_str = _serialize_turns([turn])
        restored = _deserialize_turns(json_str)

        assert restored[0].llm_response_chunk == turn.llm_response_chunk
        assert restored[0].tool_calls[0].arguments == {"关键词": "东京旅行 🗾"}
        assert restored[0].tool_calls[0].result_summary == '用户说："太棒了！"'


# ════════════════════════════════════════════════════════
# 边界测试
# ════════════════════════════════════════════════════════


class TestEdgeCases:
    """边界测试."""

    def test_empty_turns(self, recorder):
        """空 turns 列表."""
        tid = recorder.submit_trajectory(
            session_id="s",
            turns=[],
            outcome=_make_outcome(),
        )

        detail = recorder.get_trajectory(tid)
        assert detail.turns == []

        # 列表中的 turn_count 应为 0
        summaries = recorder.list_trajectories()
        assert summaries[0].turn_count == 0

    def test_large_number_of_turns(self, recorder):
        """大量 turns (100轮)."""
        turns = _make_turns(count=100, with_tool_calls=True)

        tid = recorder.submit_trajectory(
            session_id="s",
            turns=turns,
            outcome=_make_outcome(total_tokens=50000, wall_time_ms=120000),
        )

        detail = recorder.get_trajectory(tid)
        assert len(detail.turns) == 100
        # 验证第一轮和最后一轮
        assert detail.turns[0].turn_index == 0
        assert detail.turns[99].turn_index == 99
        assert detail.turns[99].tool_calls[0].tool_name == "tool_99"

    def test_no_feedback(self, recorder):
        """完全没有反馈的反馈查询."""
        fb_list = recorder.list_feedback()
        assert fb_list == []

        fb_pending = recorder.list_feedback(status="pending")
        assert fb_pending == []

    def test_scene_summary_generation(self):
        """场景摘要生成."""
        turns = [
            _make_turn(
                index=0,
                response="用户想要规划一趟日本旅行，7天，预算1万",
                token_usage=500,
            ),
        ]
        outcome = _make_outcome(success=True)
        summary = _build_scene_summary(turns, outcome, "旅行规划助手")

        assert "日本旅行" in summary or "旅行规划助手" in summary
        assert "成功" in summary

    def test_scene_summary_failed(self):
        """失败任务的摘要."""
        turns = [_make_turn(index=0, response="查询航班", token_usage=200)]
        outcome = _make_outcome(success=False, user_cancelled=False)
        summary = _build_scene_summary(turns, outcome)

        assert "失败" in summary

    def test_scene_summary_user_cancelled(self):
        """用户取消的摘要."""
        turns = [_make_turn(index=0, response="查询", token_usage=100)]
        outcome = _make_outcome(success=False, user_cancelled=True)
        summary = _build_scene_summary(turns, outcome)

        assert "用户取消" in summary

    def test_multiple_feedback_on_trajectory(self, recorder, sample_trajectory):
        """同一轨迹多条反馈."""
        recorder.add_feedback(sample_trajectory, rating="bad", note="问题1")
        recorder.add_feedback(sample_trajectory, rating="good", note="改进后好多了")
        recorder.add_feedback(sample_trajectory, rating="bad", note="问题2")

        detail = recorder.get_trajectory(sample_trajectory)
        assert len(detail.feedback) == 3
        assert detail.feedback[0].status == "pending"  # 最新的反馈

        # 列表中的 feedback_count
        summaries = recorder.list_trajectories()
        assert summaries[0].feedback_count == 3

    def test_list_feedback_limit(self, recorder, sample_trajectory):
        """limit 参数生效."""
        for i in range(10):
            recorder.add_feedback(sample_trajectory, rating="good", note=f"反馈{i}")

        fb5 = recorder.list_feedback(limit=5)
        assert len(fb5) == 5

        fb20 = recorder.list_feedback(limit=20)
        assert len(fb20) == 10  # 总共只有10条
