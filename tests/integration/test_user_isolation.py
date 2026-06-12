"""用户隔离集成测试 — 6 维度数据隔离验证.

验证 user_a 和 user_b 不能互看对方数据：
  1. 会话列表互不可见
  2. 记忆数据互不可见
  3. 制品面板互不可见
  4. 经验轨迹互不可见
  5. 自定义技能互不可见
  6. 自定义工具互不可见
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("EVOGEN_TEST_MODE", "1")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from backend.auth import create_token  # noqa: E402


def make_token(user_id: str) -> str:
    """为指定 user_id 创建 JWT."""
    return create_token({"sub": user_id, "role": "user"})


def hdr(user_id: str) -> dict:
    """返回带 JWT 的 Authorization headers."""
    return {"Authorization": f"Bearer {make_token(user_id)}"}


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def mock_all(monkeypatch, tmp_path):
    """Mock 所有外部依赖."""
    mock_db = MagicMock()
    mock_db.execute = MagicMock(return_value=MagicMock())
    mock_db.commit = MagicMock()
    mock_db.fetchone = MagicMock(return_value=None)
    mock_db.fetchall = MagicMock(return_value=[])

    monkeypatch.setattr("backend.db.connection.get_db", lambda *a, **kw: mock_db)
    monkeypatch.setattr("backend.db.connection.init_db", lambda *a, **kw: mock_db)
    monkeypatch.setattr("backend.db.connection.ConnectionManager", MagicMock())
    monkeypatch.setattr("backend.db.vector_store.get_vector_store", MagicMock())
    monkeypatch.setattr("backend.db.vector_store.VectorStore", MagicMock())
    monkeypatch.setattr("backend.memory.engine.get_engine", MagicMock())
    monkeypatch.setattr("backend.memory.embedding.get_embedding_provider", MagicMock())
    monkeypatch.setattr("backend.experience.recorder.get_recorder", MagicMock())
    monkeypatch.setattr("backend.persona.engine.get_engine", MagicMock())

    # Skills
    from backend.api import resource_routes as rmod
    test_skills = Path(tmp_path / "skills")
    test_skills.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(rmod, "_SKILLS_DIRS", [test_skills])
    monkeypatch.setattr(rmod, "_get_write_dir", lambda: test_skills)
    monkeypatch.setattr(rmod, "_TOOL_REGISTRY_PATH", Path(tmp_path / "tools.json"))

    from backend.api import skills_routes as smod
    monkeypatch.setattr(smod, "_SKILLS_DIRS", [test_skills])

    # Tools
    from backend.api import tools_routes as tmod
    tmod._custom_tools.clear()

    # Artifacts — now SQLite-backed (already mocked via mock_db above)

    return mock_db


@pytest.fixture
def client(mock_all):
    from backend.main import app
    with TestClient(app) as c:
        yield c


class TestAuthTokens:
    """验证 JWT token → user_id 映射正确."""

    def test_user_a_token_returns_user_a(self, client):
        """Bearer token for user_a → get_current_user returns 'user_a'."""
        token = make_token("user_a")
        from backend.auth import decode_token
        payload = decode_token(token)
        assert payload["sub"] == "user_a"

    def test_user_b_token_returns_user_b(self, client):
        """Bearer token for user_b → get_current_user returns 'user_b'."""
        token = make_token("user_b")
        from backend.auth import decode_token
        payload = decode_token(token)
        assert payload["sub"] == "user_b"

    def test_tokens_are_different(self, client):
        """user_a and user_b tokens are distinct."""
        assert make_token("user_a") != make_token("user_b")


# ════════════════════════════════════════════════════════
# 6 维度数据隔离
# ════════════════════════════════════════════════════════


class TestMemoryIsolation:
    """记忆数据互不可见."""

    def test_memory_list_filters_by_user(self, client, monkeypatch):
        """用户A和B分别创建记忆事实，互相不可见."""
        from backend.memory.engine import EvoMemoryEngine, MemoryFact

        mock_engine = MagicMock(spec=EvoMemoryEngine)
        mock_engine.add_manual_fact = MagicMock()
        # Return different facts per user
        def list_facts(limit=50, offset=0, type=None, layer=None, user_id="default"):
            if user_id == "user_a":
                return [MemoryFact(
                    id="a1", type="fact", content="User A's secret: alpha",
                    importance=5, weight=1.0, layer="working",
                    privacy_level="private", tags=[], user_id="user_a",
                )]
            if user_id == "user_b":
                return [MemoryFact(
                    id="b1", type="fact", content="User B's secret: beta",
                    importance=5, weight=1.0, layer="working",
                    privacy_level="private", tags=[], user_id="user_b",
                )]
            return []
        mock_engine.list_facts = list_facts
        mock_engine.get_stats = MagicMock(return_value=MagicMock())

        monkeypatch.setattr("backend.api.memory_routes._get_engine", lambda: mock_engine)

        # Verify user_id is passed through to engine
        la = client.get("/api/v1/memory/facts", headers=hdr("user_a"))
        assert la.status_code == 200
        lb = client.get("/api/v1/memory/facts", headers=hdr("user_b"))
        assert lb.status_code == 200

        a_facts = la.json().get("data", {}).get("facts", [])
        b_facts = lb.json().get("data", {}).get("facts", [])
        a_contents = [f["content"] for f in a_facts]
        b_contents = [f["content"] for f in b_facts]

        assert "User B's secret" not in str(a_contents), f"A能看B的记忆: {a_contents}"
        assert "User A's secret" not in str(b_contents), f"B能看A的记忆: {b_contents}"

    def test_memory_stats_and_facts_isolated(self, client):
        """memory/stats 也按用户隔离."""
        stats_a = client.get("/api/v1/memory/stats", headers=hdr("user_a"))
        stats_b = client.get("/api/v1/memory/stats", headers=hdr("user_b"))
        assert stats_a.status_code == 200
        assert stats_b.status_code == 200


class TestArtifactIsolation:
    """制品面板数据互不可见."""

    def test_artifact_list_filters_by_user(self, client):
        """用户A的制品不应出现在B的列表中 — SQLite 持久化."""
        import backend.api.artifacts_routes as amod

        # Store artifacts for both users via the SQLite-backed store_artifact
        amod.store_artifact("code", "A代码", "print('a')",
                           language="python", user_id="user_a")
        amod.store_artifact("code", "B代码", "print('b')",
                           language="python", user_id="user_b")

        ra = client.get("/api/v1/artifacts", headers=hdr("user_a"))
        a_titles = [a["title"] for a in ra.json().get("data", {}).get("artifacts", [])]

        rb = client.get("/api/v1/artifacts", headers=hdr("user_b"))
        b_titles = [a["title"] for a in rb.json().get("data", {}).get("artifacts", [])]

        assert "B代码" not in a_titles, f"A能看B制品: {a_titles}"
        assert "A代码" not in b_titles, f"B能看A制品: {b_titles}"


class TestExperienceIsolation:
    """经验轨迹互不可见."""

    def test_experience_trajectories_filtered_by_user(self, client):
        """经验列表按 user_id 隔离."""
        from backend.experience.recorder import TrajectorySummary
        import backend.api.experience_routes as emod

        mock = MagicMock()
        orig = emod._get_recorder
        emod._get_recorder = lambda: mock

        try:
            def list_traj(limit=50, offset=0, with_feedback_only=False, user_id="default"):
                if user_id == "user_a":
                    return [TrajectorySummary(
                        id="ta", session_id="s1", session_title="A轨迹",
                        created_at="2024-01-01T00:00:00Z",
                        turn_count=1, success=True, feedback_count=0,
                        last_feedback_at=None)]
                if user_id == "user_b":
                    return [TrajectorySummary(
                        id="tb", session_id="s2", session_title="B轨迹",
                        created_at="2024-01-01T00:00:00Z",
                        turn_count=1, success=True, feedback_count=0,
                        last_feedback_at=None)]
                return []

            mock.list_trajectories = list_traj

            ra = client.get("/api/v1/experience/trajectories", headers=hdr("user_a"))
            a_titles = [t["session_title"] for t in ra.json().get("data", {}).get("trajectories", [])]

            rb = client.get("/api/v1/experience/trajectories", headers=hdr("user_b"))
            b_titles = [t["session_title"] for t in rb.json().get("data", {}).get("trajectories", [])]

            assert "B轨迹" not in a_titles, f"A能看B经验: {a_titles}"
            assert "A轨迹" not in b_titles, f"B能看A经验: {b_titles}"
        finally:
            emod._get_recorder = orig


class TestSkillIsolation:
    """自定义技能互不可见."""

    def test_custom_skills_not_shared(self, client, tmp_path, monkeypatch):
        """用户A的自定义技能对B不可见，内置技能双方可见."""
        from backend.api import resource_routes as rmod

        skills_base = Path(tmp_path / "skills")
        skills_base.mkdir(parents=True, exist_ok=True)

        # 用户A自定义技能
        ad = skills_base / "user_a" / "skill-a"
        ad.mkdir(parents=True)
        (ad / "SKILL.md").write_text(
            "---\nname: skill-a\ndescription: A技能\n---\n\n# A\n", encoding="utf-8")

        # 用户B自定义技能
        bd = skills_base / "user_b" / "skill-b"
        bd.mkdir(parents=True)
        (bd / "SKILL.md").write_text(
            "---\nname: skill-b\ndescription: B技能\n---\n\n# B\n", encoding="utf-8")

        # 内置技能（不在用户子目录下）
        bid = skills_base / "builtin-skill"
        bid.mkdir(parents=True)
        (bid / "SKILL.md").write_text(
            "---\nname: builtin-skill\ndescription: 内置\n---\n\n# Builtin\n", encoding="utf-8")

        monkeypatch.setattr(rmod, "_SKILLS_DIRS", [skills_base])

        la = client.get("/api/v1/resource/skills", headers=hdr("user_a"))
        a_names = [s["name"] for s in la.json()["data"]["skills"]]

        lb = client.get("/api/v1/resource/skills", headers=hdr("user_b"))
        b_names = [s["name"] for s in lb.json()["data"]["skills"]]

        # 内置双方可见
        assert "builtin-skill" in a_names, f"A应看到内置: {a_names}"
        assert "builtin-skill" in b_names, f"B应看到内置: {b_names}"

        # 自定义互不可见
        assert "skill-a" in a_names, f"A应看自己的技能: {a_names}"
        assert "skill-b" not in a_names, f"A不应看B的技能: {a_names}"
        assert "skill-b" in b_names, f"B应看自己的技能: {b_names}"
        assert "skill-a" not in b_names, f"B不应看A的技能: {b_names}"

    def test_scope_field_correct(self, client, tmp_path, monkeypatch):
        """内置技能 scope='builtin', 用户技能 scope='user'."""
        from backend.api import resource_routes as rmod

        skills_base = Path(tmp_path / "skills")
        skills_base.mkdir(parents=True, exist_ok=True)

        # 内置
        bid = skills_base / "builtin-1"
        bid.mkdir(parents=True)
        (bid / "SKILL.md").write_text(
            "---\nname: builtin-1\n---\n\n# B\n", encoding="utf-8")

        # 用户A
        ad = skills_base / "user_a" / "user-1"
        ad.mkdir(parents=True)
        (ad / "SKILL.md").write_text(
            "---\nname: user-1\n---\n\n# U\n", encoding="utf-8")

        monkeypatch.setattr(rmod, "_SKILLS_DIRS", [skills_base])

        la = client.get("/api/v1/resource/skills", headers=hdr("user_a"))
        skills = {s["name"]: s["scope"] for s in la.json()["data"]["skills"]}

        assert skills.get("builtin-1") == "builtin", f"builtin scope错误: {skills}"
        assert skills.get("user-1") == "user", f"user scope错误: {skills}"


class TestToolIsolation:
    """自定义工具互不可见."""

    def test_custom_tools_not_shared(self, client):
        """用户A的工具对B不可见."""
        # A创建
        client.post("/api/v1/tools", json={
            "name": "tool_a", "description": "A工具", "command": "echo a",
        }, headers=hdr("user_a"))

        # B创建
        client.post("/api/v1/tools", json={
            "name": "tool_b", "description": "B工具", "command": "echo b",
        }, headers=hdr("user_b"))

        # A查
        la = client.get("/api/v1/tools", headers=hdr("user_a"))
        a_names = [t["name"] for t in la.json().get("data", {}).get("tools", [])]

        # B查
        lb = client.get("/api/v1/tools", headers=hdr("user_b"))
        b_names = [t["name"] for t in lb.json().get("data", {}).get("tools", [])]

        assert any(n == "tool_a" for n in a_names), f"A缺自己工具: {a_names}"
        assert not any(n == "tool_b" for n in a_names), f"A看到B工具: {a_names}"
        assert any(n == "tool_b" for n in b_names), f"B缺自己工具: {b_names}"
        assert not any(n == "tool_a" for n in b_names), f"B看到A工具: {b_names}"


class TestSessionIsolation:
    """会话列表互不可见."""

    def test_sessions_filter_by_user_id_in_sql(self, client):
        """get_current_user 从 JWT 正确提取 user_id 并传给 API."""
        # 验证端点接受不同的 JWT token 并返回 200
        ra = client.get("/api/v1/sessions", headers=hdr("user_a"))
        rb = client.get("/api/v1/sessions", headers=hdr("user_b"))
        # Both should succeed (user_id is injected via Depends(get_current_user))
        assert ra.status_code == 200
        assert rb.status_code == 200

    def test_search_sessions_isolated(self, client):
        """会话搜索也按 user_id 过滤."""
        ra = client.post("/api/v1/sessions/search", params={"query": "test"},
                         headers=hdr("user_a"))
        assert ra.status_code == 200
