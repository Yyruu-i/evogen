"""记忆容量管理单元测试 — 统计、上限、自动归档、清理策略."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("EVOGEN_TEST_MODE", "1")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def mock_db_and_services(monkeypatch, tmp_path):
    """Mock 所有外部依赖."""
    mock_db = MagicMock()
    mock_db.execute = MagicMock(return_value=MagicMock())
    mock_db.commit = MagicMock()
    mock_db.fetchone = MagicMock(return_value=None)
    mock_db.fetchall = MagicMock(return_value=[])

    monkeypatch.setattr("backend.db.connection.get_db", lambda *a, **kw: mock_db)
    monkeypatch.setattr("backend.db.connection.init_db", lambda *a, **kw: mock_db)
    monkeypatch.setattr("backend.db.vector_store.get_vector_store", MagicMock())
    monkeypatch.setattr("backend.db.vector_store.VectorStore", MagicMock())
    monkeypatch.setattr("backend.memory.engine.get_engine", MagicMock())
    return mock_db


@pytest.fixture
def client(mock_db_and_services):
    from backend.main import app
    with TestClient(app) as c:
        yield c


# ════════════════════════════════════════════════════════
# MemoryStats 序列化
# ════════════════════════════════════════════════════════


class TestMemoryStatsSerialization:
    def test_stats_to_dict_includes_capacity_fields(self):
        from backend.api.memory_routes import _stats_to_dict
        from backend.memory.engine import MemoryStats

        stats = MemoryStats(
            total_facts=500,
            by_layer={"core": 50, "working": 300, "transient": 150},
            by_type={"fact": 300, "preference": 100, "procedure": 100},
            archive_count=20,
            capacity_limit=10000,
            storage_estimate_bytes=1024000,
            usage_percent=5.0,
            archived_by_age_count=10,
            archived_by_importance_count=10,
        )
        d = _stats_to_dict(stats)
        assert d["total_facts"] == 500
        assert d["archive_count"] == 20
        assert d["capacity_limit"] == 10000
        assert d["storage_estimate_bytes"] == 1024000
        assert d["usage_percent"] == 5.0
        assert d["archived_by_age_count"] == 10


# ════════════════════════════════════════════════════════
# Engine 容量方法
# ════════════════════════════════════════════════════════


class TestCapacityEngine:
    def test_get_capacity_limit_default(self, mock_db_and_services):
        """默认容量上限 10000."""
        from backend.memory.engine import EvoMemoryEngine

        mock_db = mock_db_and_services
        mock_db.execute.return_value.fetchone.return_value = None  # 无配置

        engine = EvoMemoryEngine(db=mock_db)
        assert engine._get_capacity_limit() == 10000

    def test_get_capacity_limit_from_db(self, mock_db_and_services):
        """从 DB 读取已保存的容量上限."""
        from backend.memory.engine import EvoMemoryEngine

        mock_db = mock_db_and_services
        mock_db.execute.return_value.fetchone.return_value = {
            "value_json": "5000"
        }

        engine = EvoMemoryEngine(db=mock_db)
        assert engine._get_capacity_limit() == 5000

    def test_set_capacity_limit_rejects_too_low(self, mock_db_and_services):
        """容量上限不能低于 100."""
        from backend.memory.engine import EvoMemoryEngine

        engine = EvoMemoryEngine(db=mock_db_and_services)
        with pytest.raises(ValueError, match="at least 100"):
            engine.set_capacity_limit(50)

    def test_set_capacity_limit_ok(self, mock_db_and_services):
        """设置容量上限成功."""
        from backend.memory.engine import EvoMemoryEngine

        engine = EvoMemoryEngine(db=mock_db_and_services)
        result = engine.set_capacity_limit(5000)
        assert result == 5000
        mock_db_and_services.commit.assert_called()

    def test_auto_archive_not_needed(self, mock_db_and_services):
        """未超上限时不触发归档."""
        from backend.memory.engine import EvoMemoryEngine

        mock_db = mock_db_and_services

        # _get_capacity_limit: select → {"value_json": "10000"}
        r1 = MagicMock()
        r1.fetchone.return_value = {"value_json": "10000"}
        # total_active: COUNT(*) → indexable (500,)
        r2 = MagicMock()
        r2.fetchone.return_value = [500]
        mock_db.execute.side_effect = [r1, r2]

        engine = EvoMemoryEngine(db=mock_db)
        result = engine.auto_archive_if_over_limit()
        assert result == 0

    def test_auto_archive_triggers(self, mock_db_and_services):
        """超上限时触发自动归档."""
        from backend.memory.engine import EvoMemoryEngine

        mock_db = mock_db_and_services

        # _get_capacity_limit → {"value_json": "100"}
        r1 = MagicMock()
        r1.fetchone.return_value = {"value_json": "100"}
        # total_active → [150] (indexable)
        r2 = MagicMock()
        r2.fetchone.return_value = [150]
        # phase1: fetchall → 空
        r3 = MagicMock()
        r3.fetchall.return_value = []
        # phase2: fetchall → 3 条
        r4 = MagicMock()
        r4.fetchall.return_value = [{"id": "f1"}, {"id": "f2"}, {"id": "f3"}]
        # _archive_fact x3: each calls execute() for UPDATE
        r5 = MagicMock()
        r6 = MagicMock()
        r7 = MagicMock()
        mock_db.execute.side_effect = [r1, r2, r3, r4, r5, r6, r7]

        engine = EvoMemoryEngine(db=mock_db)
        result = engine.auto_archive_if_over_limit()
        assert result == 3

    def test_cleanup_by_age(self, mock_db_and_services):
        """按时间清理."""
        from backend.memory.engine import EvoMemoryEngine

        mock_db = mock_db_and_services
        mock_db.execute.return_value.fetchall.return_value = [
            {"id": "old1"}, {"id": "old2"}
        ]

        engine = EvoMemoryEngine(db=mock_db)
        count = engine.cleanup_by_age(days=30, dry_run=False)
        assert count == 2
        mock_db.commit.assert_called()

    def test_cleanup_by_age_dry_run(self, mock_db_and_services):
        """按时间清理预览."""
        from backend.memory.engine import EvoMemoryEngine

        mock_db = mock_db_and_services
        mock_db.execute.return_value.fetchall.return_value = [
            {"id": "old1"}, {"id": "old2"}
        ]

        engine = EvoMemoryEngine(db=mock_db)
        count = engine.cleanup_by_age(days=30, dry_run=True)
        assert count == 2
        # dry_run 不应 commit
        mock_db.commit.assert_not_called()

    def test_cleanup_by_importance(self, mock_db_and_services):
        """按重要性清理."""
        from backend.memory.engine import EvoMemoryEngine

        mock_db = mock_db_and_services
        mock_db.execute.return_value.fetchall.return_value = [
            {"id": "low1"}, {"id": "low2"}, {"id": "low3"}
        ]

        engine = EvoMemoryEngine(db=mock_db)
        count = engine.cleanup_by_importance(threshold=0.2, dry_run=False)
        assert count == 3


class TestCapacityAPI:
    def test_get_capacity(self, client, monkeypatch):
        """GET /api/v1/memory/capacity."""
        from backend.memory.engine import MemoryStats

        mock_engine = MagicMock()
        mock_engine.get_capacity_info.return_value = MemoryStats(
            total_facts=500,
            by_layer={"core": 50, "working": 300, "transient": 150},
            by_type={"fact": 400, "preference": 100},
            archive_count=20,
            capacity_limit=10000,
            storage_estimate_bytes=500000,
            usage_percent=5.0,
        )
        monkeypatch.setattr("backend.api.memory_routes._get_engine", lambda: mock_engine)

        resp = client.get("/api/v1/memory/capacity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["total_facts"] == 500
        assert data["data"]["usage_percent"] == 5.0
        assert data["data"]["capacity_limit"] == 10000

    def test_set_capacity_limit(self, client, monkeypatch):
        """PUT /api/v1/memory/capacity/limit."""
        mock_engine = MagicMock()
        mock_engine.set_capacity_limit.return_value = 5000
        monkeypatch.setattr("backend.api.memory_routes._get_engine", lambda: mock_engine)

        resp = client.put("/api/v1/memory/capacity/limit", json={"limit": 5000})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["capacity_limit"] == 5000

    def test_set_capacity_limit_rejects_low(self, client):
        """容量上限拒绝 <100."""
        resp = client.put("/api/v1/memory/capacity/limit", json={"limit": 50})
        assert resp.status_code == 400

    def test_cleanup_by_age(self, client, monkeypatch):
        """POST /api/v1/memory/capacity/cleanup age."""
        mock_engine = MagicMock()
        mock_engine.cleanup_by_age.return_value = 10
        monkeypatch.setattr("backend.api.memory_routes._get_engine", lambda: mock_engine)

        resp = client.post("/api/v1/memory/capacity/cleanup", json={
            "strategy": "age", "days": 30, "dry_run": False
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["archived"] == 10

    def test_cleanup_by_importance(self, client, monkeypatch):
        """POST /api/v1/memory/capacity/cleanup importance."""
        mock_engine = MagicMock()
        mock_engine.cleanup_by_importance.return_value = 5
        monkeypatch.setattr("backend.api.memory_routes._get_engine", lambda: mock_engine)

        resp = client.post("/api/v1/memory/capacity/cleanup", json={
            "strategy": "importance", "importance_threshold": 0.1, "dry_run": False
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["archived"] == 5

    def test_cleanup_auto(self, client, monkeypatch):
        """POST /api/v1/memory/capacity/cleanup auto."""
        mock_engine = MagicMock()
        mock_engine.auto_archive_if_over_limit.return_value = 0
        monkeypatch.setattr("backend.api.memory_routes._get_engine", lambda: mock_engine)

        resp = client.post("/api/v1/memory/capacity/cleanup", json={
            "strategy": "auto", "dry_run": False
        })
        assert resp.status_code == 200

    def test_cleanup_auto_dry_run(self, client, monkeypatch):
        """POST /api/v1/memory/capacity/cleanup auto preview."""
        from backend.memory.engine import MemoryStats

        mock_engine = MagicMock()
        mock_engine.get_capacity_info.return_value = MemoryStats(
            total_facts=500, archive_count=0, capacity_limit=10000, usage_percent=5.0
        )
        monkeypatch.setattr("backend.api.memory_routes._get_engine", lambda: mock_engine)

        resp = client.post("/api/v1/memory/capacity/cleanup", json={
            "strategy": "auto", "dry_run": True
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["dry_run"] is True

    def test_cleanup_invalid_strategy(self, client):
        """无效策略返回 400."""
        resp = client.post("/api/v1/memory/capacity/cleanup", json={
            "strategy": "invalid"
        })
        assert resp.status_code == 400
