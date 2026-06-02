"""TraceRecorder - 经验轨迹记录与场景关联匹配.

Phase 2 T-02-02 + T-02-03: 封装经验轨迹记录、反馈管理、场景关联匹配。
对齐 03-产品详细设计-v2.0.md 第466-571行。
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.db.connection import ConnectionManager, get_db
from backend.db.vector_store import VectorStore, get_vector_store
from backend.memory.embedding import get_embedding_provider

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════
# 数据结构（严格对齐设计文档）
# ════════════════════════════════════════════════════════


@dataclass
class ToolCallRecord:
    """工具调用记录."""
    tool_name: str
    arguments: Dict[str, Any]
    result_summary: str              # 压缩后的工具结果摘要
    success: bool
    execution_time_ms: int


@dataclass
class TrajectoryTurn:
    """轨迹轮次."""
    turn_index: int
    tool_calls: Optional[List[ToolCallRecord]] = None
    llm_response_chunk: Optional[str] = None
    token_usage: int = 0


@dataclass
class TaskOutcome:
    """任务结果."""
    success: bool
    total_tokens: int = 0
    wall_time_ms: int = 0
    user_cancelled: bool = False


@dataclass
class TrajectorySummary:
    """轨迹摘要."""
    id: str
    session_id: str
    session_title: Optional[str]
    created_at: str
    turn_count: int
    success: bool
    feedback_count: int
    last_feedback_at: Optional[str]


@dataclass
class TrajectoryDetail:
    """轨迹详情."""
    id: str
    session_id: str
    session_title: Optional[str]
    turns: List[TrajectoryTurn]
    outcome: TaskOutcome
    created_at: str
    feedback: List['FeedbackRecord']


@dataclass
class FeedbackRecord:
    """反馈记录."""
    id: str
    trajectory_id: str
    rating: str          # "good" | "neutral" | "bad"
    note: Optional[str]
    status: str          # "pending" | "reviewed" | "applied" | "dismissed"
    created_at: str
    reviewed_at: Optional[str]


@dataclass
class SceneHint:
    """场景提示."""
    trajectory_id: str
    summary: str                     # 可读的场景提示
    relevant_feedback: Optional[str] # 关联的用户反馈
    similarity_score: float


# ════════════════════════════════════════════════════════
# JSON 序列化/反序列化辅助
# ════════════════════════════════════════════════════════

def _serialize_turns(turns: List[TrajectoryTurn]) -> str:
    """序列化 turns 列表为 JSON 字符串."""
    data = []
    for turn in turns:
        turn_dict = {
            "turn_index": turn.turn_index,
            "llm_response_chunk": turn.llm_response_chunk,
            "token_usage": turn.token_usage,
        }
        if turn.tool_calls:
            turn_dict["tool_calls"] = [
                {
                    "tool_name": tc.tool_name,
                    "arguments": tc.arguments,
                    "result_summary": tc.result_summary,
                    "success": tc.success,
                    "execution_time_ms": tc.execution_time_ms,
                }
                for tc in turn.tool_calls
            ]
        else:
            turn_dict["tool_calls"] = None
        data.append(turn_dict)
    return json.dumps(data, ensure_ascii=False)


def _deserialize_turns(turns_json: str) -> List[TrajectoryTurn]:
    """反序列化 JSON 字符串为 turns 列表."""
    data = json.loads(turns_json)
    turns = []
    for item in data:
        tool_calls = None
        if item.get("tool_calls"):
            tool_calls = [
                ToolCallRecord(
                    tool_name=tc["tool_name"],
                    arguments=tc["arguments"],
                    result_summary=tc["result_summary"],
                    success=tc["success"],
                    execution_time_ms=tc["execution_time_ms"],
                )
                for tc in item["tool_calls"]
            ]
        turns.append(TrajectoryTurn(
            turn_index=item["turn_index"],
            tool_calls=tool_calls,
            llm_response_chunk=item.get("llm_response_chunk"),
            token_usage=item.get("token_usage", 0),
        ))
    return turns


def _serialize_outcome(outcome: TaskOutcome) -> str:
    """序列化 outcome 为 JSON 字符串."""
    return json.dumps({
        "success": outcome.success,
        "total_tokens": outcome.total_tokens,
        "wall_time_ms": outcome.wall_time_ms,
        "user_cancelled": outcome.user_cancelled,
    }, ensure_ascii=False)


def _deserialize_outcome(outcome_json: str) -> TaskOutcome:
    """反序列化 JSON 字符串为 TaskOutcome."""
    data = json.loads(outcome_json)
    return TaskOutcome(
        success=data["success"],
        total_tokens=data.get("total_tokens", 0),
        wall_time_ms=data.get("wall_time_ms", 0),
        user_cancelled=data.get("user_cancelled", False),
    )


def _row_to_feedback_record(row) -> FeedbackRecord:
    """将 sqlite3.Row 转换为 FeedbackRecord."""
    return FeedbackRecord(
        id=row["id"],
        trajectory_id=row["trajectory_id"],
        rating=row["rating"],
        note=row["note"],
        status=row["status"],
        created_at=row["created_at"],
        reviewed_at=row["reviewed_at"],
    )


# ════════════════════════════════════════════════════════
# TraceRecorder
# ════════════════════════════════════════════════════════


class TraceRecorder:
    """经验轨迹记录器.

    封装经验轨迹的提交、查询、反馈管理，以及基于向量相似度的场景关联匹配。

    用法:
        recorder = TraceRecorder(db=db, vector_store=vs)
        trajectory_id = recorder.submit_trajectory(session_id, turns, outcome)
        hints = recorder.get_scene_hints(session_id, "帮我规划旅行")
    """

    SIMILARITY_THRESHOLD = 0.6  # 场景匹配最低相似度阈值

    def __init__(
        self,
        db: Optional[ConnectionManager] = None,
        vector_store: Optional[VectorStore] = None,
    ):
        """初始化 TraceRecorder.

        Args:
            db: SQLite 连接管理器，默认使用全局单例
            vector_store: Chroma 向量存储，默认使用全局单例
        """
        self._db = db or get_db()
        self._vector_store = vector_store or get_vector_store()
        self._embedding = get_embedding_provider()

    # ── T-02-02: 核心方法 ─────────────────────────

    def submit_trajectory(
        self,
        session_id: str,
        turns: List[TrajectoryTurn],
        outcome: TaskOutcome,
        session_title: Optional[str] = None,
    ) -> str:
        """提交任务执行轨迹.

        Args:
            session_id: 会话 ID
            turns: 轨迹轮次列表
            outcome: 任务结果
            session_title: 会话标题（可选）

        Returns:
            轨迹 ID (UUID)
        """
        trajectory_id = str(uuid.uuid4())
        turns_json = _serialize_turns(turns)
        outcome_json = _serialize_outcome(outcome)

        # 生成场景摘要: 第一条用户消息 + 任务结果拼接
        summary = _build_scene_summary(turns, outcome, session_title)

        # 写入 SQLite
        self._db.execute(
            """INSERT INTO experience_trajectories
               (id, session_id, session_title, turns_json, outcome_json)
               VALUES (?, ?, ?, ?, ?)""",
            (trajectory_id, session_id, session_title, turns_json, outcome_json),
        )
        self._db.commit()

        # 写入 Chroma (向量检索)
        try:
            self._vector_store.add_experience(
                trajectory_id=trajectory_id,
                summary=summary,
                metadata={
                    "session_id": session_id,
                    "success": outcome.success,
                    "turn_count": len(turns),
                },
            )
        except Exception as e:
            logger.warning(f"Failed to add experience embedding: {e}")

        logger.info(
            f"Trajectory submitted: id={trajectory_id}, "
            f"turns={len(turns)}, success={outcome.success}"
        )
        return trajectory_id

    def list_trajectories(
        self,
        limit: int = 50,
        offset: int = 0,
        with_feedback_only: bool = False,
    ) -> List[TrajectorySummary]:
        """列出任务轨迹摘要.

        Args:
            limit: 返回数量上限
            offset: 分页偏移
            with_feedback_only: 仅返回有反馈的轨迹

        Returns:
            轨迹摘要列表
        """
        if with_feedback_only:
            sql = """
                SELECT
                    t.id, t.session_id, t.session_title, t.created_at,
                    t.turns_json, t.outcome_json,
                    COUNT(f.id) as feedback_count,
                    MAX(f.created_at) as last_feedback_at
                FROM experience_trajectories t
                INNER JOIN experience_feedback f ON f.trajectory_id = t.id
                GROUP BY t.id
                ORDER BY t.created_at DESC
                LIMIT ? OFFSET ?
            """
        else:
            sql = """
                SELECT
                    t.id, t.session_id, t.session_title, t.created_at,
                    t.turns_json, t.outcome_json,
                    COUNT(f.id) as feedback_count,
                    MAX(f.created_at) as last_feedback_at
                FROM experience_trajectories t
                LEFT JOIN experience_feedback f ON f.trajectory_id = t.id
                GROUP BY t.id
                ORDER BY t.created_at DESC
                LIMIT ? OFFSET ?
            """

        rows = self._db.execute(sql, (limit, offset)).fetchall()

        summaries = []
        for row in rows:
            outcome = _deserialize_outcome(row["outcome_json"])
            turns_data = json.loads(row["turns_json"])
            summaries.append(TrajectorySummary(
                id=row["id"],
                session_id=row["session_id"],
                session_title=row["session_title"],
                created_at=row["created_at"],
                turn_count=len(turns_data),
                success=outcome.success,
                feedback_count=row["feedback_count"],
                last_feedback_at=row["last_feedback_at"],
            ))

        return summaries

    def get_trajectory(self, trajectory_id: str) -> Optional[TrajectoryDetail]:
        """获取单条轨迹详情，包含完整 turns + outcome + feedback.

        Args:
            trajectory_id: 轨迹 ID

        Returns:
            轨迹详情，不存在时返回 None
        """
        row = self._db.execute(
            """SELECT id, session_id, session_title, turns_json, outcome_json, created_at
               FROM experience_trajectories WHERE id = ?""",
            (trajectory_id,),
        ).fetchone()

        if row is None:
            return None

        turns = _deserialize_turns(row["turns_json"])
        outcome = _deserialize_outcome(row["outcome_json"])

        # 查询关联反馈
        feedback_rows = self._db.execute(
            """SELECT id, trajectory_id, rating, note, status, created_at, reviewed_at
               FROM experience_feedback WHERE trajectory_id = ?
               ORDER BY created_at DESC""",
            (trajectory_id,),
        ).fetchall()

        feedback = [_row_to_feedback_record(fr) for fr in feedback_rows]

        return TrajectoryDetail(
            id=row["id"],
            session_id=row["session_id"],
            session_title=row["session_title"],
            turns=turns,
            outcome=outcome,
            created_at=row["created_at"],
            feedback=feedback,
        )

    # ── 反馈管理 ─────────────────────────────────

    def add_feedback(
        self,
        trajectory_id: str,
        rating: str,
        note: Optional[str] = None,
    ) -> FeedbackRecord:
        """添加用户反馈.

        Args:
            trajectory_id: 关联的轨迹 ID
            rating: "good" | "neutral" | "bad"
            note: 用户备注（如 "下次应该先确认再操作"）

        Returns:
            生成的 FeedbackRecord

        Raises:
            ValueError: rating 不合法或 trajectory 不存在
        """
        if rating not in ("good", "neutral", "bad"):
            raise ValueError(f"Invalid rating: {rating}, must be good/neutral/bad")

        # 验证轨迹存在
        exists = self._db.execute(
            "SELECT 1 FROM experience_trajectories WHERE id = ?",
            (trajectory_id,),
        ).fetchone()
        if not exists:
            raise ValueError(f"Trajectory not found: {trajectory_id}")

        feedback_id = str(uuid.uuid4())
        self._db.execute(
            """INSERT INTO experience_feedback
               (id, trajectory_id, rating, note, status)
               VALUES (?, ?, ?, ?, 'pending')""",
            (feedback_id, trajectory_id, rating, note),
        )
        self._db.commit()

        row = self._db.execute(
            "SELECT * FROM experience_feedback WHERE id = ?",
            (feedback_id,),
        ).fetchone()

        logger.info(f"Feedback added: id={feedback_id}, trajectory={trajectory_id}, rating={rating}")
        return _row_to_feedback_record(row)

    def list_feedback(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[FeedbackRecord]:
        """列出反馈记录.

        Args:
            status: 按状态筛选 (pending/reviewed/applied/dismissed)，None 返回全部
            limit: 返回数量上限

        Returns:
            反馈记录列表
        """
        if status:
            rows = self._db.execute(
                """SELECT id, trajectory_id, rating, note, status, created_at, reviewed_at
                   FROM experience_feedback
                   WHERE status = ?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (status, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                """SELECT id, trajectory_id, rating, note, status, created_at, reviewed_at
                   FROM experience_feedback
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()

        return [_row_to_feedback_record(r) for r in rows]

    def update_feedback_status(self, feedback_id: str, status: str) -> None:
        """更新反馈状态.

        状态流转: pending → reviewed → applied/dismissed
        自动记录 reviewed_at 时间戳。

        Args:
            feedback_id: 反馈 ID
            status: 新状态 (reviewed/applied/dismissed)

        Raises:
            ValueError: 状态不合法或反馈不存在
        """
        if status not in ("reviewed", "applied", "dismissed"):
            raise ValueError(f"Invalid status: {status}, must be reviewed/applied/dismissed")

        # 验证反馈存在
        existing = self._db.execute(
            "SELECT id, status FROM experience_feedback WHERE id = ?",
            (feedback_id,),
        ).fetchone()
        if not existing:
            raise ValueError(f"Feedback not found: {feedback_id}")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._db.execute(
            """UPDATE experience_feedback
               SET status = ?, reviewed_at = ?
               WHERE id = ?""",
            (status, now, feedback_id),
        )
        self._db.commit()

        logger.info(f"Feedback status updated: {feedback_id} → {status}")

    # ── T-02-03: 场景关联匹配 ────────────────────

    def get_scene_hints(
        self,
        session_id: str,
        current_message: str,
        top_k: int = 5,
    ) -> List[SceneHint]:
        """获取当前消息相关的历史经验场景提示.

        算法：
        1. 对 current_message 生成 embedding
        2. Chroma 检索 evo_experience_scenes（相似历史场景）
        3. 排除当前 session 自身的轨迹
        4. 关联反馈查询：对于每个匹配的 trajectory，查 SQLite feedback WHERE rating='bad'
        5. 只返回 similarity > 0.6 的场景

        Args:
            session_id: 当前会话 ID（用于排除自身）
            current_message: 当前用户消息
            top_k: 返回最大数量

        Returns:
            场景提示列表，按相似度降序
        """
        # 1. Chroma 检索相似场景
        raw_results = self._vector_store.search_experiences(
            query=current_message,
            n_results=top_k * 2,  # 多取一些，后续过滤
        )

        hints = []
        for result in raw_results:
            similarity = result["similarity"]

            # 5. 只返回 similarity > 0.6 的场景
            if similarity <= self.SIMILARITY_THRESHOLD:
                continue

            trajectory_id = result["id"]
            metadata = result.get("metadata", {})

            # 3. 排除当前 session 自身的轨迹
            if metadata.get("session_id") == session_id:
                continue

            summary = result.get("content", metadata.get("summary", ""))

            # 4. 关联反馈查询：查找 rating='bad' 的反馈
            bad_feedback_rows = self._db.execute(
                """SELECT note FROM experience_feedback
                   WHERE trajectory_id = ? AND rating = 'bad'
                   ORDER BY created_at DESC
                   LIMIT 1""",
                (trajectory_id,),
            ).fetchall()

            relevant_feedback = bad_feedback_rows[0]["note"] if bad_feedback_rows else None

            hints.append(SceneHint(
                trajectory_id=trajectory_id,
                summary=summary,
                relevant_feedback=relevant_feedback,
                similarity_score=round(similarity, 4),
            ))

            if len(hints) >= top_k:
                break

        # 按相似度降序排列
        hints.sort(key=lambda h: h.similarity_score, reverse=True)
        return hints

    def format_hints(self, hints: List[SceneHint]) -> str:
        """格式化场景提示为自然语言中文上下文注入文本.

        Args:
            hints: 场景提示列表

        Returns:
            格式化后的中文自然语言文本，无提示时返回空字符串
        """
        if not hints:
            return ""

        lines = ["## 相关经验提示"]
        for hint in hints:
            if hint.relevant_feedback:
                lines.append(f"- 在上次「{hint.summary}」中，你提醒我：{hint.relevant_feedback}")
            else:
                lines.append(f"- 相关历史场景：{hint.summary}（相似度 {hint.similarity_score:.0%}）")
        return "\n".join(lines)


# ════════════════════════════════════════════════════════
# 辅助函数
# ════════════════════════════════════════════════════════

def _build_scene_summary(
    turns: List[TrajectoryTurn],
    outcome: TaskOutcome,
    session_title: Optional[str] = None,
) -> str:
    """自动生成场景摘要：取第一条用户消息 + 任务结果.

    摘要格式: "[session_title] 用户需求摘要 → 结果: 成功/失败"

    Args:
        turns: 轨迹轮次
        outcome: 任务结果
        session_title: 会话标题

    Returns:
        场景摘要字符串
    """
    # 尝试从首个 turn 的 LLM 响应中提取用户意图摘要
    first_user_msg = ""
    if turns and turns[0].llm_response_chunk:
        # llm_response_chunk 可能包含用户消息的上下文，取前80字
        first_user_msg = turns[0].llm_response_chunk[:80]

    result_str = "成功" if outcome.success else "失败"
    if outcome.user_cancelled:
        result_str = "用户取消"

    if session_title:
        return f"{session_title}: {first_user_msg} → {result_str}"
    else:
        return f"{first_user_msg} → {result_str}"


def get_trace_recorder(
    db: Optional[ConnectionManager] = None,
    vector_store: Optional[VectorStore] = None,
) -> TraceRecorder:
    """获取全局 TraceRecorder 实例（工厂函数）."""
    return TraceRecorder(db=db, vector_store=vector_store)


# 全局单例
_trace_recorder: Optional[TraceRecorder] = None


def get_recorder(
    db: Optional[ConnectionManager] = None,
    vector_store: Optional[VectorStore] = None,
) -> TraceRecorder:
    """获取全局 TraceRecorder 单例."""
    global _trace_recorder
    if _trace_recorder is None:
        _trace_recorder = TraceRecorder(db=db, vector_store=vector_store)
    return _trace_recorder
