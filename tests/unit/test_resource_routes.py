"""资源库 API 单元测试 — 技能 CRUD / 导入导出 / 工具注册 / 经验导出."""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# 在导入前设置免初始化
os.environ.setdefault("EVOGEN_TEST_MODE", "1")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def mock_db_and_services(monkeypatch, tmp_path):
    """Mock 所有外部依赖."""
    # Mock ConnectionManager
    mock_db = MagicMock()
    mock_db.execute = MagicMock(return_value=MagicMock())
    mock_db.commit = MagicMock()
    mock_db.fetchone = MagicMock(return_value=None)
    mock_db.fetchall = MagicMock(return_value=[])

    monkeypatch.setattr("backend.db.connection.get_db", lambda *a, **kw: mock_db)
    monkeypatch.setattr("backend.db.connection.init_db", lambda *a, **kw: mock_db)

    # Mock Chroma
    monkeypatch.setattr("backend.db.vector_store.get_vector_store", MagicMock())
    monkeypatch.setattr("backend.db.vector_store.VectorStore", MagicMock())

    # Mock embedding provider
    monkeypatch.setattr("backend.memory.engine.get_engine", MagicMock())

    # Use tmp_path for SKILLS_DIR and TOOL_REGISTRY
    from backend.api import resource_routes as rmod
    test_skills = Path(tmp_path / "skills")
    test_skills.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(rmod, "_SKILLS_DIRS", [test_skills])
    monkeypatch.setattr(rmod, "_get_write_dir", lambda: test_skills)
    monkeypatch.setattr(rmod, "_TOOL_REGISTRY_PATH", Path(tmp_path / "tools_registry.json"))

    return mock_db


@pytest.fixture
def client(mock_db_and_services):
    """创建测试客户端."""
    from backend.main import app
    with TestClient(app) as c:
        yield c


# ════════════════════════════════════════════════════════
# 技能 CRUD 测试
# ════════════════════════════════════════════════════════


class TestSkillsCRUD:
    """技能 CRUD 操作."""

    def test_create_skill(self, client, tmp_path):
        """POST /api/v1/resource/skills — 创建技能."""
        resp = client.post("/api/v1/resource/skills", json={
            "name": "Test Skill",
            "description": "A test skill",
            "content": "# Test\n\nThis is a test.",
            "category": "test-cat",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["name"] == "Test Skill"
        assert data["data"]["id"] == "test-skill"

    def test_create_skill_duplicate(self, client):
        """POST /api/v1/resource/skills — 重复创建应返回 409."""
        client.post("/api/v1/resource/skills", json={
            "name": "Test Skill", "description": "", "content": "body"
        })
        resp = client.post("/api/v1/resource/skills", json={
            "name": "Test Skill", "description": "", "content": "body"
        })
        assert resp.status_code == 409

    def test_list_skills(self, client):
        """GET /api/v1/resource/skills — 列出技能."""
        client.post("/api/v1/resource/skills", json={
            "name": "Skill A", "description": "Desc A", "content": "body A"
        })
        client.post("/api/v1/resource/skills", json={
            "name": "Skill B", "description": "Desc B", "content": "body B"
        })
        resp = client.get("/api/v1/resource/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["total"] == 2
        ids = [s["id"] for s in data["data"]["skills"]]
        assert "skill-a" in ids
        assert "skill-b" in ids

    def test_get_skill(self, client):
        """GET /api/v1/resource/skills/{id} — 获取单个技能."""
        client.post("/api/v1/resource/skills", json={
            "name": "Target", "description": "desc", "content": "body"
        })
        resp = client.get("/api/v1/resource/skills/target")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["skill"]["name"] == "Target"
        assert "content" in data["data"]

    def test_get_skill_not_found(self, client):
        """GET /api/v1/resource/skills/{id} — 404."""
        resp = client.get("/api/v1/resource/skills/nonexistent")
        assert resp.status_code == 404

    def test_update_skill(self, client):
        """PUT /api/v1/resource/skills/{id} — 更新技能."""
        client.post("/api/v1/resource/skills", json={
            "name": "Old Name", "description": "old", "content": "old body"
        })
        resp = client.put("/api/v1/resource/skills/old-name", json={
            "name": "New Name",
            "description": "updated desc",
            "content": "new body",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["name"] == "New Name"

        # 验证内容更新
        get_resp = client.get("/api/v1/resource/skills/new-name")
        body = get_resp.json()
        assert "new body" in body["data"]["content"]

    def test_update_skill_partial(self, client):
        """PUT /api/v1/resource/skills/{id} — 部分更新."""
        client.post("/api/v1/resource/skills", json={
            "name": "Partial", "description": "orig", "content": "orig body"
        })
        resp = client.put("/api/v1/resource/skills/partial", json={
            "content": "updated only body",
        })
        assert resp.status_code == 200
        # name still same
        get_resp = client.get("/api/v1/resource/skills/partial")
        body = get_resp.json()
        assert "updated only body" in body["data"]["content"]
        assert body["data"]["skill"]["name"] == "Partial"

    def test_delete_skill(self, client):
        """DELETE /api/v1/resource/skills/{id} — 删除技能."""
        client.post("/api/v1/resource/skills", json={
            "name": "To Delete", "description": "", "content": "bye"
        })
        resp = client.delete("/api/v1/resource/skills/to-delete")
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted"] == "to-delete"

        get_resp = client.get("/api/v1/resource/skills/to-delete")
        assert get_resp.status_code == 404


# ════════════════════════════════════════════════════════
# 工具 API 测试
# ════════════════════════════════════════════════════════


class TestToolsAPI:
    """工具注册表 API."""

    def test_register_tool(self, client):
        """POST /api/v1/resource/tools — 注册工具."""
        resp = client.post("/api/v1/resource/tools", json={
            "name": "my_tool",
            "description": "does things",
            "endpoint": "/api/do",
            "category": "custom",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["name"] == "my_tool"
        assert "id" in data["data"]

    def test_list_tools(self, client):
        """GET /api/v1/resource/tools — 列出工具."""
        client.post("/api/v1/resource/tools", json={
            "name": "tool1", "description": "first tool"
        })
        client.post("/api/v1/resource/tools", json={
            "name": "tool2", "description": "second tool"
        })

        resp = client.get("/api/v1/resource/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        from backend.api.tools_routes import _static_tool_list as _ht
        assert data["data"]["total"] == len(_ht()) + 2  # builtin + 2 user tools

    def test_delete_tool(self, client):
        """DELETE /api/v1/resource/tools/{id} — 删除工具."""
        resp = client.post("/api/v1/resource/tools", json={
            "name": "to_remove", "description": "will be removed"
        })
        tool_id = resp.json()["data"]["id"]

        del_resp = client.delete(f"/api/v1/resource/tools/{tool_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["data"]["deleted"] == tool_id

    def test_delete_tool_not_found(self, client):
        """DELETE /api/v1/resource/tools/{id} — 404."""
        resp = client.delete("/api/v1/resource/tools/ffffffff-ffff-ffff-ffff-ffffffffffff")
        assert resp.status_code == 404


# ════════════════════════════════════════════════════════
# 技能导出测试
# ════════════════════════════════════════════════════════


class TestSkillsExport:
    """技能导出."""

    def test_export_single_skill(self, client):
        """POST /api/v1/resource/skills/export — 导出单个技能."""
        client.post("/api/v1/resource/skills", json={
            "name": "Export Me", "description": "for export", "content": "export body"
        })
        resp = client.post("/api/v1/resource/skills/export", json={
            "skill_ids": ["export-me"]
        })
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert "attachment" in resp.headers.get("content-disposition", "")

    def test_export_multiple(self, client):
        """POST /api/v1/resource/skills/export — 批量导出."""
        client.post("/api/v1/resource/skills", json={
            "name": "Skill X", "description": "", "content": "x"
        })
        client.post("/api/v1/resource/skills", json={
            "name": "Skill Y", "description": "", "content": "y"
        })
        resp = client.post("/api/v1/resource/skills/export", json={
            "skill_ids": ["skill-x", "skill-y"]
        })
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"

    def test_export_empty_list(self, client):
        """POST /api/v1/resource/skills/export — 空列表应返回 400."""
        resp = client.post("/api/v1/resource/skills/export", json={
            "skill_ids": []
        })
        assert resp.status_code == 400

    def test_export_nonexistent(self, client):
        """POST /api/v1/resource/skills/export — 不存在的技能应返回 404."""
        resp = client.post("/api/v1/resource/skills/export", json={
            "skill_ids": ["no-such-skill"]
        })
        assert resp.status_code == 404


# ════════════════════════════════════════════════════════
# 技能导入测试
# ════════════════════════════════════════════════════════


class TestSkillsImport:
    """技能导入."""

    def test_import_md_file(self, client, tmp_path):
        """POST /api/v1/resource/skills/import — 上传 .md 文件."""
        md_content = """---
name: Imported MD
description: From a markdown file
---

# Imported

This was imported."""
        md_file = tmp_path / "test_skill.md"
        md_file.write_text(md_content)

        with open(md_file, "rb") as f:
            resp = client.post(
                "/api/v1/resource/skills/import",
                files={"file": ("test_skill.md", f, "text/markdown")},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "imported-md" in data["data"]["imported"]

    def test_import_json_body(self, client):
        """POST /api/v1/resource/skills/import/json — JSON body 导入."""
        resp = client.post("/api/v1/resource/skills/import/json", json={
            "skills": [
                {"name": "JSON Skill", "description": "json imported", "content": "body"},
                {"name": "JSON Skill 2", "description": "another", "content": "body2"},
            ]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["count"] == 2

    def test_import_json_body_empty(self, client):
        """POST /api/v1/resource/skills/import/json — 空 skills 数组."""
        resp = client.post("/api/v1/resource/skills/import/json", json={})
        assert resp.status_code == 400


# ════════════════════════════════════════════════════════
# _load_recent_messages 测试
# ════════════════════════════════════════════════════════


class TestLoadRecentMessages:
    """对话历史加载."""

    def test_load_recent_messages(self, monkeypatch):
        """验证 _load_recent_messages 返回格式正确."""
        from backend.api.chat_routes import _load_recent_messages

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = [
            {"role": "assistant", "content": "你好！"},
            {"role": "user", "content": "你好"},
        ]
        monkeypatch.setattr("backend.db.connection.get_db", lambda: mock_db)

        history = _load_recent_messages("test-session", max_messages=5)
        assert len(history) == 2
        # 反转后：先用户消息再助手回复（时间升序）
        assert history[0] == {"role": "user", "content": "你好"}
        assert history[1] == {"role": "assistant", "content": "你好！"}
