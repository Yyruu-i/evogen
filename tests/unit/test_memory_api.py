"""T-01-05 测试：记忆 REST API 端点.

使用 FastAPI TestClient 测试所有 7 个端点。
测试覆盖：正常流程 + 错误码（404/400） + 语义搜索。
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════


@pytest.fixture
def engine(tmp_path):
    """创建使用临时目录的 EvoMemoryEngine."""
    from backend.db.connection import ConnectionManager
    from backend.db.migrations import run_migrations
    from backend.db.vector_store import VectorStore
    from backend.memory.embedding import get_embedding_provider
    from backend.memory.engine import EvoMemoryEngine

    db_path = str(tmp_path / "test_api_evogen.db")
    chroma_dir = str(tmp_path / "chroma_api")

    db = ConnectionManager(db_path)
    run_migrations(db)
    vs = VectorStore(persist_dir=chroma_dir)
    embedding = get_embedding_provider(device="cpu")

    eng = EvoMemoryEngine(db=db, vector_store=vs, embedding_provider=embedding)
    return eng


@pytest.fixture
def client(engine):
    """FastAPI TestClient，通过 patch 注入测试 engine."""
    from backend.main import app

    # Patch the routes module's cached reference
    with patch("backend.api.memory_routes.get_engine", return_value=engine):
        with TestClient(app) as c:
            yield c


# ════════════════════════════════════════════════════════
# Helper: seed data
# ════════════════════════════════════════════════════════


def _seed_fact(
    client,
    content="用户喜欢喝咖啡",
    fact_type="preference",
    importance=0.8,
    layer="working",
):
    """通过 API 添加一条事实并返回响应."""
    return client.post(
        "/api/v1/memory/facts",
        json={
            "content": content,
            "type": fact_type,
            "importance": importance,
            "layer": layer,
        },
    )


# ════════════════════════════════════════════════════════
# GET /api/v1/memory/facts — 列表查询
# ════════════════════════════════════════════════════════


class TestListFacts:
    """测试 GET /api/v1/memory/facts."""

    def test_list_empty(self, client):
        """空数据库返回空列表."""
        resp = client.get("/api/v1/memory/facts")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["facts"] == []
        assert body["data"]["total"] == 0

    def test_list_with_data(self, client):
        """有数据时正常分页返回."""
        _seed_fact(client, "事实1", "fact")
        _seed_fact(client, "事实2", "preference")

        resp = client.get("/api/v1/memory/facts")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert len(body["data"]["facts"]) == 2
        assert body["data"]["total"] == 2

    def test_list_filter_by_layer(self, client):
        """按 layer 筛选."""
        _seed_fact(client, "working事实", "fact", layer="working")
        _seed_fact(client, "core事实", "preference", layer="core")

        # 只查 working
        resp = client.get("/api/v1/memory/facts?layer=working")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]["facts"]) == 1
        assert body["data"]["facts"][0]["content"] == "working事实"

    def test_list_filter_by_type(self, client):
        """按 type 筛选."""
        _seed_fact(client, "偏好项", "preference")
        _seed_fact(client, "事实项", "fact")

        resp = client.get("/api/v1/memory/facts?type=preference")
        body = resp.json()
        assert len(body["data"]["facts"]) == 1
        assert body["data"]["facts"][0]["type"] == "preference"

    def test_list_pagination(self, client):
        """分页参数正确."""
        for i in range(5):
            _seed_fact(client, f"事实{i}", "fact")

        # page 1
        resp = client.get("/api/v1/memory/facts?limit=2&offset=0")
        body = resp.json()
        assert len(body["data"]["facts"]) == 2
        assert body["data"]["limit"] == 2
        assert body["data"]["offset"] == 0
        assert body["data"]["total"] == 5

        # page 3
        resp = client.get("/api/v1/memory/facts?limit=2&offset=4")
        body = resp.json()
        assert len(body["data"]["facts"]) == 1

    def test_list_with_q_triggers_semantic_search(self, client):
        """GET /facts?q=xxx 触发语义搜索."""
        _seed_fact(client, "用户喜欢喝咖啡不加糖", "preference", importance=0.8)
        _seed_fact(client, "用户喜欢打篮球", "fact", importance=0.5)

        resp = client.get("/api/v1/memory/facts?q=咖啡")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        # 语义搜索应返回结果
        assert len(body["data"]["facts"]) >= 1
        # 咖啡相关的应该排在前面
        contents = [f["content"] for f in body["data"]["facts"]]
        assert any("咖啡" in c for c in contents)

    def test_list_invalid_limit(self, client):
        """limit 超限被拒绝."""
        resp = client.get("/api/v1/memory/facts?limit=1000")
        assert resp.status_code == 422  # FastAPI validation error


# ════════════════════════════════════════════════════════
# GET /api/v1/memory/facts/{id} — 单条查询
# ════════════════════════════════════════════════════════


class TestGetFact:
    """测试 GET /api/v1/memory/facts/{id}."""

    def test_get_existing(self, client):
        """获取存在的 fact."""
        resp = _seed_fact(client, "测试事实", "fact")
        fact_id = resp.json()["data"]["id"]

        resp = client.get(f"/api/v1/memory/facts/{fact_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["content"] == "测试事实"
        assert body["data"]["id"] == fact_id

    def test_get_not_found(self, client):
        """获取不存在的 fact 返回 404."""
        resp = client.get("/api/v1/memory/facts/nonexistent-id")
        assert resp.status_code == 404
        body = resp.json()
        assert body["detail"]["ok"] is False
        assert "not found" in body["detail"]["error"].lower()


# ════════════════════════════════════════════════════════
# POST /api/v1/memory/facts — 手动添加
# ════════════════════════════════════════════════════════


class TestCreateFact:
    """测试 POST /api/v1/memory/facts."""

    def test_create_success(self, client):
        """成功创建."""
        resp = client.post(
            "/api/v1/memory/facts",
            json={
                "content": "用户喜欢喝茶",
                "type": "preference",
                "importance": 0.7,
                "layer": "working",
                "tags": ["饮品"],
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["content"] == "用户喜欢喝茶"
        assert body["data"]["type"] == "preference"
        assert body["data"]["importance"] == 0.7
        assert body["data"]["layer"] == "working"
        assert body["data"]["tags"] == ["饮品"]
        assert "id" in body["data"]

    def test_create_defaults(self, client):
        """默认值."""
        resp = client.post(
            "/api/v1/memory/facts",
            json={"content": "默认值测试", "type": "fact"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["data"]["importance"] == 0.5
        assert body["data"]["layer"] == "working"
        assert body["data"]["privacy_level"] == "private"

    def test_create_missing_content(self, client):
        """缺少 content 返回 400."""
        resp = client.post(
            "/api/v1/memory/facts",
            json={"type": "fact"},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["detail"]["ok"] is False
        assert "content" in body["detail"]["error"].lower()

    def test_create_invalid_type(self, client):
        """无效 type 返回 400."""
        resp = client.post(
            "/api/v1/memory/facts",
            json={"content": "测试", "type": "invalid_type"},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["detail"]["ok"] is False


# ════════════════════════════════════════════════════════
# PUT /api/v1/memory/facts/{id} — 更新
# ════════════════════════════════════════════════════════


class TestUpdateFact:
    """测试 PUT /api/v1/memory/facts/{id}."""

    def test_update_success(self, client):
        """成功更新."""
        resp = _seed_fact(client, "原始内容", "fact")
        fact_id = resp.json()["data"]["id"]

        resp = client.put(
            f"/api/v1/memory/facts/{fact_id}",
            json={"content": "更新后的内容", "importance": 0.9},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["content"] == "更新后的内容"
        assert body["data"]["importance"] == 0.9

    def test_update_not_found(self, client):
        """更新不存在的 fact 返回 404."""
        resp = client.put(
            "/api/v1/memory/facts/nonexistent",
            json={"content": "更新"},
        )
        assert resp.status_code == 404
        body = resp.json()
        assert body["detail"]["ok"] is False


# ════════════════════════════════════════════════════════
# DELETE /api/v1/memory/facts/{id} — 删除
# ════════════════════════════════════════════════════════


class TestDeleteFact:
    """测试 DELETE /api/v1/memory/facts/{id}."""

    def test_delete_success(self, client):
        """成功删除."""
        resp = _seed_fact(client, "待删除", "fact")
        fact_id = resp.json()["data"]["id"]

        resp = client.delete(f"/api/v1/memory/facts/{fact_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["deleted_id"] == fact_id

        # 确认已删除
        resp = client.get(f"/api/v1/memory/facts/{fact_id}")
        assert resp.status_code == 404

    def test_delete_not_found(self, client):
        """删除不存在的 fact 返回 404."""
        resp = client.delete("/api/v1/memory/facts/nonexistent")
        assert resp.status_code == 404
        body = resp.json()
        assert body["detail"]["ok"] is False


# ════════════════════════════════════════════════════════
# GET /api/v1/memory/stats — 统计信息
# ════════════════════════════════════════════════════════


class TestGetStats:
    """测试 GET /api/v1/memory/stats."""

    def test_stats_empty(self, client):
        """空数据库统计."""
        resp = client.get("/api/v1/memory/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["total_facts"] == 0
        assert body["data"]["by_layer"] == {}
        assert body["data"]["by_type"] == {}

    def test_stats_with_data(self, client):
        """有数据时的统计."""
        _seed_fact(client, "事实1", "preference", layer="working")
        _seed_fact(client, "事实2", "fact", layer="core")
        _seed_fact(client, "事实3", "fact", layer="transient")

        resp = client.get("/api/v1/memory/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["total_facts"] == 3
        assert body["data"]["by_layer"]["working"] == 1
        assert body["data"]["by_layer"]["core"] == 1
        assert body["data"]["by_layer"]["transient"] == 1
        assert body["data"]["by_type"]["preference"] == 1
        assert body["data"]["by_type"]["fact"] == 2


# ════════════════════════════════════════════════════════
# POST /api/v1/memory/facts/{id}/reinforce — 强化记忆
# ════════════════════════════════════════════════════════


class TestReinforceFact:
    """测试 POST /api/v1/memory/facts/{id}/reinforce."""

    def test_reinforce_success(self, client):
        """成功强化."""
        resp = _seed_fact(client, "强化测试", "fact", importance=0.5)
        fact_id = resp.json()["data"]["id"]

        resp = client.post(
            f"/api/v1/memory/facts/{fact_id}/reinforce",
            json={"amount": 0.2},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["importance"] == 0.7
        assert body["data"]["weight"] == 1.2

    def test_reinforce_default_amount(self, client):
        """默认 amount=0.1."""
        resp = _seed_fact(client, "默认强化", "fact", importance=0.5)
        fact_id = resp.json()["data"]["id"]

        # 不传 body
        resp = client.post(f"/api/v1/memory/facts/{fact_id}/reinforce")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["importance"] == 0.6
        assert body["data"]["weight"] == 1.1

    def test_reinforce_not_found(self, client):
        """强化不存在的 fact 返回 404."""
        resp = client.post("/api/v1/memory/facts/nonexistent/reinforce")
        assert resp.status_code == 404
        body = resp.json()
        assert body["detail"]["ok"] is False


# ════════════════════════════════════════════════════════
# 响应格式一致性测试
# ════════════════════════════════════════════════════════


class TestResponseFormat:
    """测试统一响应格式."""

    def test_all_success_responses_have_ok_true(self, client):
        """所有成功响应包含 ok: true."""
        # stats
        resp = client.get("/api/v1/memory/stats")
        assert resp.json()["ok"] is True

        # facts list
        resp = client.get("/api/v1/memory/facts")
        assert resp.json()["ok"] is True

        # create
        resp = client.post("/api/v1/memory/facts", json={"content": "格式测试", "type": "fact"})
        assert resp.json()["ok"] is True
        fact_id = resp.json()["data"]["id"]

        # get
        resp = client.get(f"/api/v1/memory/facts/{fact_id}")
        assert resp.json()["ok"] is True

        # update
        resp = client.put(f"/api/v1/memory/facts/{fact_id}", json={"importance": 0.9})
        assert resp.json()["ok"] is True

        # reinforce
        resp = client.post(f"/api/v1/memory/facts/{fact_id}/reinforce")
        assert resp.json()["ok"] is True

        # delete
        resp = client.delete(f"/api/v1/memory/facts/{fact_id}")
        assert resp.json()["ok"] is True

    def test_error_responses_have_detail(self, client):
        """错误响应在 detail 中包含 ok: false."""
        resp = client.get("/api/v1/memory/facts/nonexistent")
        assert resp.status_code == 404
        assert resp.json()["detail"]["ok"] is False
        assert "error" in resp.json()["detail"]

        resp = client.post("/api/v1/memory/facts", json={"type": "fact"})
        assert resp.status_code == 400
        assert resp.json()["detail"]["ok"] is False
