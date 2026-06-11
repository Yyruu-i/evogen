"""经验管理 REST API 端点（对齐设计文档第1366-1385行）.

统一响应格式：{"ok": true, "data": {...}} 或 {"ok": false, "error": "..."}
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from backend.auth.dependencies import get_current_user

from backend.experience.recorder import (
    TraceRecorder,
    TrajectorySummary,
    TrajectoryDetail,
    FeedbackRecord,
    get_recorder,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/experience", tags=["experience"])


# ════════════════════════════════════════════════════════
# 请求体模型
# ════════════════════════════════════════════════════════

class AddFeedbackRequest(BaseModel):
    """POST /experience/feedback 请求体."""
    trajectory_id: str = Field(..., description="关联的轨迹 ID")
    rating: str = Field(..., description="评分: good/neutral/bad")
    note: Optional[str] = Field(None, description="用户备注")


class UpdateFeedbackStatusRequest(BaseModel):
    """PUT /experience/feedback/:id/status 请求体."""
    status: str = Field(..., description="新状态: reviewed/applied/dismissed")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in ("reviewed", "applied", "dismissed"):
            raise ValueError(f"Invalid status: {v}, must be reviewed/applied/dismissed")
        return v


# ════════════════════════════════════════════════════════
# 辅助：获取 recorder 实例 + 序列化
# ════════════════════════════════════════════════════════

def _get_recorder() -> TraceRecorder:
    """获取全局 TraceRecorder 单例（测试时可 monkeypatch）."""
    return get_recorder()


def _summary_to_dict(s: TrajectorySummary) -> dict:
    """序列化 TrajectorySummary 为 API 友好字典，时间使用真实会话时间."""
    # 查找关联 session 的真实创建时间
    session_time = s.created_at  # 默认回退到轨迹创建时间
    try:
        from backend.db.connection import get_db
        db = get_db()
        row = db.execute(
            "SELECT created_at FROM sessions WHERE id = ?",
            (s.session_id,),
        ).fetchone()
        if row:
            session_time = row["created_at"]
    except Exception:
        pass

    return {
        "id": s.id,
        "session_id": s.session_id,
        "session_title": s.session_title,
        "created_at": session_time,
        "turn_count": s.turn_count,
        "success": s.success,
        "feedback_count": s.feedback_count,
        "last_feedback_at": s.last_feedback_at,
    }


def _turn_to_dict(turn) -> dict:
    """序列化 TrajectoryTurn 为字典."""
    result = {
        "turn_index": turn.turn_index,
        "llm_response_chunk": turn.llm_response_chunk,
        "token_usage": turn.token_usage,
    }
    if turn.tool_calls:
        result["tool_calls"] = [
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
        result["tool_calls"] = None
    return result


def _outcome_to_dict(outcome) -> dict:
    """序列化 TaskOutcome 为字典."""
    return {
        "success": outcome.success,
        "total_tokens": outcome.total_tokens,
        "wall_time_ms": outcome.wall_time_ms,
        "user_cancelled": outcome.user_cancelled,
    }


def _feedback_to_dict(fb: FeedbackRecord) -> dict:
    """序列化 FeedbackRecord 为 API 友好字典."""
    return {
        "id": fb.id,
        "trajectory_id": fb.trajectory_id,
        "rating": fb.rating,
        "note": fb.note,
        "status": fb.status,
        "created_at": fb.created_at,
        "reviewed_at": fb.reviewed_at,
    }


def _detail_to_dict(d: TrajectoryDetail) -> dict:
    """序列化 TrajectoryDetail 为 API 友好字典，时间使用真实会话时间."""
    session_time = d.created_at
    try:
        from backend.db.connection import get_db
        db = get_db()
        row = db.execute(
            "SELECT created_at FROM sessions WHERE id = ?",
            (d.session_id,),
        ).fetchone()
        if row:
            session_time = row["created_at"]
    except Exception:
        pass

    return {
        "id": d.id,
        "session_id": d.session_id,
        "session_title": d.session_title,
        "turns": [_turn_to_dict(t) for t in d.turns],
        "outcome": _outcome_to_dict(d.outcome),
        "created_at": session_time,
        "feedback": [_feedback_to_dict(f) for f in d.feedback],
    }


# ════════════════════════════════════════════════════════
# GET /api/v1/experience/trajectories — 轨迹列表
# ════════════════════════════════════════════════════════

@router.get("/trajectories")
async def list_trajectories(
    limit: int = Query(50, ge=1, le=500, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    with_feedback_only: bool = Query(False, description="仅返回有反馈的轨迹"),
    success: Optional[bool] = Query(None, description="按任务成功/失败筛选"),
    user_id: str = Depends(get_current_user),
):
    """列出经验轨迹摘要.

    支持分页（limit/offset）、仅反馈筛选、成功状态筛选。
    """
    recorder = _get_recorder()

    try:
        # TraceRecorder.list_trajectories 不原生支持 success 筛选，
        # 若有 success 参数则多取一些后手动过滤。
        if success is not None:
            fetch_limit = min(limit * 3 + offset, 500)
        else:
            fetch_limit = limit

        summaries = recorder.list_trajectories(
            limit=fetch_limit,
            offset=offset,
            with_feedback_only=with_feedback_only,
            user_id=user_id,
        )

        # 手动按 success 过滤
        if success is not None:
            summaries = [s for s in summaries if s.success == success]
            # 重新切片
            total = len(summaries)
            summaries = summaries[:limit]
        else:
            # 获取总数（粗略估算：再查一次大范围）
            all_summaries = recorder.list_trajectories(
                limit=10000, offset=0,
                with_feedback_only=with_feedback_only,
                user_id=user_id,
            )
            total = len(all_summaries)

        return {
            "ok": True,
            "data": {
                "trajectories": [_summary_to_dict(s) for s in summaries],
                "total": total,
                "limit": limit,
                "offset": offset,
            },
        }
    except Exception as e:
        logger.error(f"list_trajectories failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"ok": False, "error": str(e)})


# ════════════════════════════════════════════════════════
# GET /api/v1/experience/trajectories/{id} — 轨迹详情
# ════════════════════════════════════════════════════════

@router.get("/trajectories/{trajectory_id}")
async def get_trajectory(trajectory_id: str, user_id: str = Depends(get_current_user)):
    """获取单条轨迹详情，包含完整 turns + outcome + feedback."""
    recorder = _get_recorder()

    try:
        detail = recorder.get_trajectory(trajectory_id, user_id=user_id)
        if detail is None:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "error": f"Trajectory not found: {trajectory_id}"},
            )
        return {"ok": True, "data": _detail_to_dict(detail)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_trajectory failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"ok": False, "error": str(e)})


# ════════════════════════════════════════════════════════
# GET /api/v1/experience/feedback — 反馈列表
# ════════════════════════════════════════════════════════

@router.get("/feedback")
async def list_feedback(
    status: Optional[str] = Query(None, description="按状态筛选: pending/reviewed/applied/dismissed"),
    limit: int = Query(50, ge=1, le=500, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    user_id: str = Depends(get_current_user),
):
    """列出反馈记录，支持按状态筛选和分页."""
    recorder = _get_recorder()

    try:
        # TraceRecorder.list_feedback 不原生支持 offset，
        # 多取一些后手动切片。
        fetch_limit = min(limit + offset, 500)
        feedback_list = recorder.list_feedback(status=status, limit=fetch_limit, user_id=user_id)

        total = len(feedback_list)
        feedback_list = feedback_list[offset : offset + limit]

        return {
            "ok": True,
            "data": {
                "feedback": [_feedback_to_dict(fb) for fb in feedback_list],
                "total": total,
                "limit": limit,
                "offset": offset,
            },
        }
    except Exception as e:
        logger.error(f"list_feedback failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"ok": False, "error": str(e)})


# ════════════════════════════════════════════════════════
# POST /api/v1/experience/feedback — 添加反馈
# ════════════════════════════════════════════════════════

@router.post("/feedback", status_code=201)
async def add_feedback(request: AddFeedbackRequest):
    """添加用户反馈.

    Request body: {trajectory_id, rating, note?}
    """
    recorder = _get_recorder()

    try:
        fb = recorder.add_feedback(
            trajectory_id=request.trajectory_id,
            rating=request.rating,
            note=request.note,
        )
        return {"ok": True, "data": _feedback_to_dict(fb)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"ok": False, "error": str(e)})
    except Exception as e:
        logger.error(f"add_feedback failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"ok": False, "error": str(e)})


# ════════════════════════════════════════════════════════
# PUT /api/v1/experience/feedback/{id}/status — 更新反馈状态
# ════════════════════════════════════════════════════════

@router.put("/feedback/{feedback_id}/status")
async def update_feedback_status(feedback_id: str, request: UpdateFeedbackStatusRequest, user_id: str = Depends(get_current_user)):
    """更新反馈状态.

    Request body: {status: "reviewed"|"applied"|"dismissed"}
    状态流转: pending → reviewed → applied/dismissed
    自动记录 reviewed_at 时间戳。
    """
    recorder = _get_recorder()

    try:
        recorder.update_feedback_status(feedback_id, request.status)

        # update_feedback_status 不返回更新后的记录，需再次查询
        # 从全部反馈中查找（最多查 500 条）
        all_fb = recorder.list_feedback(limit=500, user_id=user_id)
        updated = next((fb for fb in all_fb if fb.id == feedback_id), None)
        if updated is None:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "error": f"Feedback not found: {feedback_id}"},
            )

        return {"ok": True, "data": _feedback_to_dict(updated)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"ok": False, "error": str(e)})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"update_feedback_status failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"ok": False, "error": str(e)})
