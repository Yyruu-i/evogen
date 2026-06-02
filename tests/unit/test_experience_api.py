"""T-02-05 测试：经验 REST API 端点.

使用 FastAPI TestClient + 注入 TraceRecorder 实例进行集成测试。
覆盖所有 5 个端点的正常和边界情况。
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.db.connection import ConnectionManager
from backend.db.vector_store import VectorStore
from backend.db.migrations import run_migrations
from backend.experience.recorder import TraceRecorder


# ════════════════════════════════════════════════════════
# Helpers（复用 test_experience_recorder 的工厂函数）
# ════════════════════════════════════════════════════════

from tests.unit.test_experience_recorder import (
    _make_tool_call,
    _make_turn,
    _make_outcome,
    _make_turns,
)


# ════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════


@pytest.fixture
def recorder(tmp_path):
    """创建使用临时目录的 TraceRecorder."""
    db_path = str(tmp_path / "test_api_evogen.db")
    chroma_dir = str(tmp_path / "chroma_api")

    db = ConnectionManager(db_path)
    run_migrations(db)

    vs = VectorStore(persist_dir=chroma_dir)

    return TraceRecorder(db=db, vector_store=vs)


@pytest.fixture
def client(recorder):
    """创建 TestClient，注入 recorder 实例."""
    from backend.main import app

    # 注入 recorder 实例，替代全局单例
    with patch(
        "backend.api.experience_routes._get_recorder",
        return_value=recorder,
    ):
        with TestClient(app) as tc:
            yield tc


@pytest.fixture
def sample_trajectory(recorder):
    """提交一条轨迹，返回 trajectory_id."""
    turns = _make_turns(count=3)
    outcome = _make_outcome(success=True)
    return recorder.submit_trajectory(
        session_id="session-001",
        turns=turns,
        outcome=outcome,
        session_title="旅行规划助手",
    )


@pytest.fixture
def sample_feedback(recorder, sample_trajectory):
    """添加一条反馈，返回 FeedbackRecord."""
    return recorder.add_feedback(
        trajectory_id=sample_trajectory,
        rating="bad",
        note="下次订机票前先确认日期",
    )


# ════════════════════════════════════════════════════════
# GET /api/v1/experience/trajectories
# ════════════════════════════════════════════════════════


class TestListTrajectories:

    def test_list_empty(self, client):
        """空数据库返回空列表."""
        resp = client.get("/api/v1/experience/trajectories")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["trajectories"] == []
        assert data["data"]["total"] == 0

    def test_list_basic(self, client, sample_trajectory):
        """列出所有轨迹."""
        resp = client.get("/api/v1/experience/trajectories")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert len(data["data"]["trajectories"]) == 1
        assert data["data"]["total"] == 1

        t = data["data"]["trajectories"][0]
        assert t["id"] == sample_trajectory
        assert t["session_id"] == "session-001"
        assert t["session_title"] == "旅行规划助手"
        assert t["turn_count"] == 3
        assert t["success"] is True
        assert t["feedback_count"] == 0

    def test_list_pagination(self, client, recorder):
        """分页测试."""
        for i in range(5):
            recorder.submit_trajectory(
                session_id=f"s-{i}",
                turns=_make_turns(count=1),
                outcome=_make_outcome(),
            )

        # 第一页
        resp = client.get("/api/v1/experience/trajectories?limit=2&offset=0")
        data = resp.json()
        assert data["ok"] is True
        assert len(data["data"]["trajectories"]) == 2

        # 第二页
        resp = client.get("/api/v1/experience/trajectories?limit=2&offset=2")
        data = resp.json()
        assert len(data["data"]["trajectories"]) == 2

        # 第三页（剩 1 条）
        resp = client.get("/api/v1/experience/trajectories?limit=2&offset=4")
        data = resp.json()
        assert len(data["data"]["trajectories"]) == 1

    def test_list_with_feedback_only(self, client, recorder, sample_trajectory):
        """仅返回有反馈的轨迹."""
        # 再提交一条无反馈的轨迹
        recorder.submit_trajectory(
            session_id="s-no-fb",
            turns=_make_turns(count=1),
            outcome=_make_outcome(),
        )
        # 为 sample_trajectory 添加反馈
        recorder.add_feedback(sample_trajectory, rating="good")

        resp = client.get("/api/v1/experience/trajectories?with_feedback_only=true")
        data = resp.json()
        assert data["ok"] is True
        assert len(data["data"]["trajectories"]) == 1
        assert data["data"]["trajectories"][0]["id"] == sample_trajectory

    def test_list_filter_success(self, client, recorder):
        """按 success 筛选."""
        recorder.submit_trajectory(
            session_id="s-success", turns=_make_turns(count=1),
            outcome=_make_outcome(success=True),
        )
        recorder.submit_trajectory(
            session_id="s-fail", turns=_make_turns(count=1),
            outcome=_make_outcome(success=False),
        )

        # 筛选成功的
        resp = client.get("/api/v1/experience/trajectories?success=true")
        data = resp.json()
        assert data["ok"] is True
        assert len(data["data"]["trajectories"]) >= 1
        for t in data["data"]["trajectories"]:
            assert t["success"] is True

        # 筛选失败的
        resp = client.get("/api/v1/experience/trajectories?success=false")
        data = resp.json()
        assert data["ok"] is True
        for t in data["data"]["trajectories"]:
            assert t["success"] is False


# ════════════════════════════════════════════════════════
# GET /api/v1/experience/trajectories/{id}
# ════════════════════════════════════════════════════════


class TestGetTrajectory:

    def test_get_detail(self, client, sample_trajectory, sample_feedback):
        """获取包含 turns + outcome + feedback 的完整详情."""
        resp = client.get(f"/api/v1/experience/trajectories/{sample_trajectory}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

        d = data["data"]
        assert d["id"] == sample_trajectory
        assert d["session_id"] == "session-001"
        assert len(d["turns"]) == 3
        assert d["outcome"]["success"] is True
        assert d["outcome"]["total_tokens"] == 2000
        assert len(d["feedback"]) == 1
        assert d["feedback"][0]["rating"] == "bad"
        assert d["feedback"][0]["note"] == "下次订机票前先确认日期"

    def test_get_nonexistent(self, client):
        """不存在的轨迹返回 404."""
        resp = client.get("/api/v1/experience/trajectories/nonexistent-id")
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["ok"] is False
        assert "not found" in data["detail"]["error"].lower()

    def test_get_turn_structure(self, client, recorder):
        """验证 turn 结构（含 tool_calls）完整序列化."""
        tc = _make_tool_call(
            tool_name="file_read",
            arguments={"path": "/tmp/test.txt"},
            result_summary="文件内容: hello",
            success=True,
            execution_time_ms=320,
        )
        turn = _make_turn(
            index=0, tool_calls=[tc],
            response="读取文件成功", token_usage=450,
        )
        tid = recorder.submit_trajectory(
            session_id="s", turns=[turn], outcome=_make_outcome(),
        )

        resp = client.get(f"/api/v1/experience/trajectories/{tid}")
        data = resp.json()
        assert data["ok"] is True
        t = data["data"]["turns"][0]
        assert t["turn_index"] == 0
        assert t["token_usage"] == 450
        assert t["llm_response_chunk"] == "读取文件成功"
        assert len(t["tool_calls"]) == 1
        tc_out = t["tool_calls"][0]
        assert tc_out["tool_name"] == "file_read"
        assert tc_out["arguments"] == {"path": "/tmp/test.txt"}
        assert tc_out["success"] is True


# ════════════════════════════════════════════════════════
# GET /api/v1/experience/feedback
# ════════════════════════════════════════════════════════


class TestListFeedback:

    def test_list_empty(self, client):
        """空数据库返回空列表."""
        resp = client.get("/api/v1/experience/feedback")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["feedback"] == []
        assert data["data"]["total"] == 0

    def test_list_all(self, client, sample_trajectory, sample_feedback):
        """列出所有反馈."""
        recorder_internal = None
        # 需要访问 recorder 添加更多反馈，从 patch 中获取
        resp = client.get("/api/v1/experience/feedback")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert len(data["data"]["feedback"]) >= 1

        fb = data["data"]["feedback"][0]
        assert fb["rating"] == "bad"
        assert fb["note"] == "下次订机票前先确认日期"
        assert fb["status"] == "pending"
        assert fb["trajectory_id"] == sample_trajectory

    def test_list_by_status(self, client, recorder, sample_trajectory):
        """按状态筛选."""
        recorder.add_feedback(sample_trajectory, rating="good")
        fb_list = recorder.list_feedback(limit=10)
        recorder.update_feedback_status(fb_list[0].id, "reviewed")

        resp = client.get("/api/v1/experience/feedback?status=reviewed")
        data = resp.json()
        assert data["ok"] is True
        assert len(data["data"]["feedback"]) >= 1
        for fb in data["data"]["feedback"]:
            if fb["id"] == fb_list[0].id:
                assert fb["status"] == "reviewed"

    def test_list_pagination(self, client, recorder, sample_trajectory):
        """分页测试."""
        for i in range(3):
            recorder.add_feedback(sample_trajectory, rating="neutral", note=f"note-{i}")

        resp = client.get("/api/v1/experience/feedback?limit=2&offset=0")
        data = resp.json()
        assert data["ok"] is True
        assert len(data["data"]["feedback"]) == 2

        resp = client.get("/api/v1/experience/feedback?limit=2&offset=2")
        data = resp.json()
        assert len(data["data"]["feedback"]) >= 1


# ════════════════════════════════════════════════════════
# POST /api/v1/experience/feedback
# ════════════════════════════════════════════════════════


class TestAddFeedback:

    def test_add_good(self, client, sample_trajectory):
        """添加好评."""
        resp = client.post(
            "/api/v1/experience/feedback",
            json={"trajectory_id": sample_trajectory, "rating": "good", "note": "很好用"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["ok"] is True
        fb = data["data"]
        assert fb["trajectory_id"] == sample_trajectory
        assert fb["rating"] == "good"
        assert fb["note"] == "很好用"
        assert fb["status"] == "pending"
        assert fb["id"]

    def test_add_bad(self, client, sample_trajectory):
        """添加差评."""
        resp = client.post(
            "/api/v1/experience/feedback",
            json={"trajectory_id": sample_trajectory, "rating": "bad"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["rating"] == "bad"
        assert data["data"]["note"] is None

    def test_add_neutral(self, client, sample_trajectory):
        """添加中性评价."""
        resp = client.post(
            "/api/v1/experience/feedback",
            json={"trajectory_id": sample_trajectory, "rating": "neutral"},
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["rating"] == "neutral"

    def test_add_invalid_rating(self, client, sample_trajectory):
        """非法 rating 返回 422 (Pydantic validation) 或 400."""
        resp = client.post(
            "/api/v1/experience/feedback",
            json={"trajectory_id": sample_trajectory, "rating": "excellent"},
        )
        # Pydantic 验证会返回 422，但 TraceRecorder 层也做了验证
        assert resp.status_code in (400, 422)

    def test_add_nonexistent_trajectory(self, client):
        """不存在的 trajectory_id 返回 400."""
        resp = client.post(
            "/api/v1/experience/feedback",
            json={"trajectory_id": "nonexistent-id", "rating": "good"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["detail"]["ok"] is False
        assert "not found" in data["detail"]["error"].lower()

    def test_add_missing_fields(self, client):
        """缺少必填字段返回 422."""
        resp = client.post(
            "/api/v1/experience/feedback",
            json={"rating": "good"},
        )
        assert resp.status_code == 422


# ════════════════════════════════════════════════════════
# PUT /api/v1/experience/feedback/{id}/status
# ════════════════════════════════════════════════════════


class TestUpdateFeedbackStatus:

    def test_update_to_reviewed(self, client, sample_feedback):
        """pending → reviewed."""
        resp = client.put(
            f"/api/v1/experience/feedback/{sample_feedback.id}/status",
            json={"status": "reviewed"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["status"] == "reviewed"
        assert data["data"]["reviewed_at"] is not None

    def test_update_to_applied(self, client, sample_feedback):
        """pending → reviewed → applied（完整流转）."""
        # 先 reviewed
        client.put(
            f"/api/v1/experience/feedback/{sample_feedback.id}/status",
            json={"status": "reviewed"},
        )
        # 再 applied
        resp = client.put(
            f"/api/v1/experience/feedback/{sample_feedback.id}/status",
            json={"status": "applied"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "applied"

    def test_update_to_dismissed(self, client, sample_feedback):
        """pending → dismissed."""
        resp = client.put(
            f"/api/v1/experience/feedback/{sample_feedback.id}/status",
            json={"status": "dismissed"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "dismissed"

    def test_update_invalid_status(self, client, sample_feedback):
        """非法 status 返回 422."""
        resp = client.put(
            f"/api/v1/experience/feedback/{sample_feedback.id}/status",
            json={"status": "invalid_status"},
        )
        assert resp.status_code == 422

    def test_update_nonexistent(self, client):
        """不存在的 feedback_id 返回 400."""
        resp = client.put(
            "/api/v1/experience/feedback/nonexistent-id/status",
            json={"status": "reviewed"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["detail"]["ok"] is False
        assert "not found" in data["detail"]["error"].lower()


# ════════════════════════════════════════════════════════
# 统一响应格式验证
# ════════════════════════════════════════════════════════


class TestResponseFormat:

    def test_success_response_has_ok_true(self, client):
        """成功响应格式：{"ok": true, "data": {...}}."""
        resp = client.get("/api/v1/experience/trajectories")
        assert resp.status_code == 200
        body = resp.json()
        assert "ok" in body
        assert body["ok"] is True
        assert "data" in body

    def test_error_response_has_ok_false(self, client):
        """错误响应格式：{"ok": false, "error": "..."}."""
        resp = client.get("/api/v1/experience/trajectories/nonexistent")
        assert resp.status_code == 404
        # FastAPI HTTPException detail 会在 response body 的 detail 字段
        body = resp.json()
        assert "detail" in body
        assert body["detail"]["ok"] is False
        assert "error" in body["detail"]

    def test_validation_error_format(self, client):
        """Pydantic 验证错误的格式."""
        resp = client.post(
            "/api/v1/experience/feedback",
            json={"trajectory_id": "some-id"},
        )
        assert resp.status_code == 422
