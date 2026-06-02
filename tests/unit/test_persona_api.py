"""T-04-04 测试：人格 REST API 端点.

使用 FastAPI TestClient + 注入 PersonaEngine 进行集成测试。
覆盖所有 6 个端点的正常和边界情况。
"""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.db.connection import ConnectionManager
from backend.db.migrations import run_migrations
from backend.persona.dao import PersonaDAO
from backend.persona.engine import PersonaEngine


# ════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════


@pytest.fixture
def engine(tmp_path):
    """创建使用临时数据库的 PersonaEngine."""
    db_path = str(tmp_path / "test_persona_api_evogen.db")
    db = ConnectionManager(db_path)
    run_migrations(db)

    # 注入临时 DB
    import backend.persona.dao as dao_mod
    old_get_db = dao_mod.get_db
    dao_mod.get_db = lambda: db

    try:
        dao = PersonaDAO()
        eng = PersonaEngine(dao=dao)
        yield eng
    finally:
        dao_mod.get_db = old_get_db


@pytest.fixture
def client(engine):
    """FastAPI TestClient，通过 patch 注入测试 engine."""
    from backend.main import app

    with patch("backend.api.persona_routes._get_engine", return_value=engine):
        with TestClient(app) as c:
            yield c


# ════════════════════════════════════════════════════════
# GET /api/v1/persona/attributes
# ════════════════════════════════════════════════════════


class TestGetAttributes:

    def test_get_defaults(self, client):
        """获取默认人格属性."""
        resp = client.get("/api/v1/persona/attributes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        attrs = body["data"]["attributes"]
        assert attrs["preferred_language"] == "zh"
        assert attrs["conciseness"] == 0.5
        assert attrs["warmth"] == 0.7
        assert attrs["auto_approve_tools"] is False

    def test_contains_all_keys(self, client):
        """响应包含所有已知 key."""
        resp = client.get("/api/v1/persona/attributes")
        body = resp.json()
        attrs = body["data"]["attributes"]
        expected_keys = {
            "display_name", "preferred_language", "timezone",
            "conciseness", "formality", "warmth", "directness",
            "auto_approve_tools", "show_thinking", "response_language",
            "learned_preferences", "discovery_questions_asked",
        }
        for key in expected_keys:
            assert key in attrs, f"Missing key: {key}"


# ════════════════════════════════════════════════════════
# PUT /api/v1/persona/attributes  — 批量更新
# ════════════════════════════════════════════════════════


class TestSetAttributesBatch:

    def test_batch_update(self, client):
        """批量更新多个属性."""
        resp = client.put(
            "/api/v1/persona/attributes",
            json={
                "display_name": "批量用户",
                "conciseness": 0.9,
                "warmth": 0.3,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        attrs = body["data"]["attributes"]
        assert attrs["display_name"] == "批量用户"
        assert attrs["conciseness"] == 0.9
        assert attrs["warmth"] == 0.3

        persona = body["data"]["persona"]
        assert persona["display_name"] == "批量用户"

        # 确认持久化
        resp2 = client.get("/api/v1/persona/attributes")
        attrs2 = resp2.json()["data"]["attributes"]
        assert attrs2["display_name"] == "批量用户"

    def test_empty_body(self, client):
        """空请求体返回 400."""
        resp = client.put("/api/v1/persona/attributes", json={})
        assert resp.status_code == 400
        body = resp.json()
        assert body["detail"]["ok"] is False

    def test_unknown_keys_ignored(self, client):
        """未知 key 被忽略但不报错."""
        resp = client.put(
            "/api/v1/persona/attributes",
            json={"bad_key": "value", "conciseness": 0.2},
        )
        assert resp.status_code == 200
        attrs = resp.json()["data"]["attributes"]
        assert attrs["conciseness"] == 0.2
        # bad_key 不存在于 attributes 中
        assert "bad_key" not in attrs


# ════════════════════════════════════════════════════════
# PUT /api/v1/persona/attributes/{key}  — 单个更新
# ════════════════════════════════════════════════════════


class TestUpdateAttribute:

    def test_update_single(self, client):
        """更新单个属性."""
        resp = client.put(
            "/api/v1/persona/attributes/display_name",
            json={"value": "单个用户"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["key"] == "display_name"
        assert body["data"]["value"] == "单个用户"

    def test_update_numeric(self, client):
        """更新数值属性."""
        resp = client.put(
            "/api/v1/persona/attributes/conciseness",
            json={"value": 0.95},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["value"] == 0.95

    def test_update_bool(self, client):
        """更新布尔属性."""
        resp = client.put(
            "/api/v1/persona/attributes/auto_approve_tools",
            json={"value": True},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["value"] is True

    def test_update_none(self, client):
        """更新为 None."""
        # 先设置为某个值
        client.put("/api/v1/persona/attributes/display_name", json={"value": "temp"})
        # 再清空
        resp = client.put(
            "/api/v1/persona/attributes/display_name",
            json={"value": None},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["value"] is None

    def test_update_missing_value(self, client):
        """缺少 value 字段返回 400."""
        resp = client.put(
            "/api/v1/persona/attributes/conciseness",
            json={},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["ok"] is False

    def test_update_unknown_key(self, client):
        """更新未知 key 返回 400."""
        resp = client.put(
            "/api/v1/persona/attributes/bad_key",
            json={"value": "test"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["ok"] is False


# ════════════════════════════════════════════════════════
# GET /api/v1/persona/export
# ════════════════════════════════════════════════════════


class TestExportPersona:

    def test_export_default(self, client):
        """导出默认人格 JSON."""
        resp = client.get("/api/v1/persona/export")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = json.loads(body["data"]["json"])
        assert "conciseness" in data
        assert data["conciseness"] == 0.5

    def test_export_after_changes(self, client):
        """更新后导出反映变更."""
        client.put("/api/v1/persona/attributes/display_name", json={"value": "导出用户"})
        client.put("/api/v1/persona/attributes/conciseness", json={"value": 0.88})

        resp = client.get("/api/v1/persona/export")
        data = json.loads(resp.json()["data"]["json"])
        assert data["display_name"] == "导出用户"
        assert data["conciseness"] == 0.88

    def test_export_is_valid_json(self, client):
        """导出的是合法 JSON."""
        resp = client.get("/api/v1/persona/export")
        json_str = resp.json()["data"]["json"]
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)


# ════════════════════════════════════════════════════════
# POST /api/v1/persona/import
# ════════════════════════════════════════════════════════


class TestImportPersona:

    def test_import_valid_json(self, client):
        """导入合法 JSON."""
        json_str = json.dumps({
            "display_name": "导入用户",
            "conciseness": 0.75,
            "warmth": 0.4,
        })
        resp = client.post("/api/v1/persona/import", json={"json_str": json_str})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        attrs = body["data"]["attributes"]
        assert attrs["display_name"] == "导入用户"
        assert attrs["conciseness"] == 0.75
        assert attrs["warmth"] == 0.4

    def test_import_missing_json_str(self, client):
        """缺少 json_str 返回 400."""
        resp = client.post("/api/v1/persona/import", json={})
        assert resp.status_code == 400
        assert resp.json()["detail"]["ok"] is False

    def test_import_invalid_json(self, client):
        """无效 JSON 返回 400."""
        resp = client.post("/api/v1/persona/import", json={"json_str": "not json {{{"})
        assert resp.status_code == 400
        assert resp.json()["detail"]["ok"] is False

    def test_import_json_array(self, client):
        """JSON 数组返回 400."""
        resp = client.post("/api/v1/persona/import", json={"json_str": "[1,2,3]"})
        assert resp.status_code == 400
        assert resp.json()["detail"]["ok"] is False

    def test_import_whitelist_filtering(self, client):
        """导入时过滤未知 key."""
        json_str = json.dumps({
            "display_name": "合法用户",
            "evil_key": "恶意数据",
            "conciseness": 0.6,
        })
        resp = client.post("/api/v1/persona/import", json={"json_str": json_str})
        assert resp.status_code == 200
        attrs = resp.json()["data"]["attributes"]
        assert attrs["display_name"] == "合法用户"
        assert attrs["conciseness"] == 0.6
        assert "evil_key" not in attrs

    def test_import_no_valid_keys(self, client):
        """全是未知 key 返回 400."""
        resp = client.post("/api/v1/persona/import", json={"json_str": '{"x":1,"y":2}'})
        assert resp.status_code == 400
        assert resp.json()["detail"]["ok"] is False

    def test_roundtrip(self, client):
        """导出再导入，数据保持一致."""
        # 先修改一些属性
        client.put("/api/v1/persona/attributes/display_name", json={"value": "往返"})
        client.put("/api/v1/persona/attributes/conciseness", json={"value": 0.7})

        # 导出
        export_resp = client.get("/api/v1/persona/export")
        json_str = export_resp.json()["data"]["json"]

        # 改点别的
        client.put("/api/v1/persona/attributes/display_name", json={"value": "临时"})

        # 导入之前导出的
        import_resp = client.post("/api/v1/persona/import", json={"json_str": json_str})
        assert import_resp.status_code == 200
        attrs = import_resp.json()["data"]["attributes"]
        assert attrs["display_name"] == "往返"
        assert attrs["conciseness"] == 0.7


# ════════════════════════════════════════════════════════
# GET /api/v1/persona/preview-prompt
# ════════════════════════════════════════════════════════


class TestPreviewPrompt:

    def test_default_returns_empty(self, client):
        """默认全部属性时返回空 prompt."""
        resp = client.get("/api/v1/persona/preview-prompt")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["prompt_injection"] == ""

    def test_after_changes_returns_content(self, client):
        """修改属性后返回非空 prompt."""
        client.put("/api/v1/persona/attributes/display_name", json={"value": "小明"})
        client.put("/api/v1/persona/attributes/conciseness", json={"value": 0.95})

        resp = client.get("/api/v1/persona/preview-prompt")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        prompt = body["data"]["prompt_injection"]
        assert "小明" in prompt
        assert "## 用户偏好" in prompt

    def test_format_is_markdown(self, client):
        """prompt 是 Markdown 格式."""
        client.put("/api/v1/persona/attributes/display_name", json={"value": "测试"})

        resp = client.get("/api/v1/persona/preview-prompt")
        prompt = resp.json()["data"]["prompt_injection"]
        # 以 ## 开头
        assert prompt.startswith("##")
        # 包含列表项
        assert "\n- " in prompt

    def test_no_default_values_leaked(self, client):
        """默认值不出现在 prompt 中."""
        client.put("/api/v1/persona/attributes/display_name", json={"value": "用户A"})

        resp = client.get("/api/v1/persona/preview-prompt")
        prompt = resp.json()["data"]["prompt_injection"]
        # 默认的 zh 语言不应出现
        assert "偏好语言" not in prompt
        # 默认的 show_thinking=True 不应出现
        assert "显示思考过程" not in prompt


# ════════════════════════════════════════════════════════
# 统一响应格式验证
# ════════════════════════════════════════════════════════


class TestResponseFormat:

    def test_success_has_ok_true(self, client):
        """所有成功响应包含 ok: true."""
        # attributes
        resp = client.get("/api/v1/persona/attributes")
        assert resp.json()["ok"] is True

        # export
        resp = client.get("/api/v1/persona/export")
        assert resp.json()["ok"] is True

        # preview-prompt
        resp = client.get("/api/v1/persona/preview-prompt")
        assert resp.json()["ok"] is True

        # batch update
        resp = client.put("/api/v1/persona/attributes", json={"conciseness": 0.3})
        assert resp.json()["ok"] is True

        # single update
        resp = client.put("/api/v1/persona/attributes/warmth", json={"value": 0.8})
        assert resp.json()["ok"] is True

        # import
        resp = client.post("/api/v1/persona/import", json={
            "json_str": '{"display_name": "格式测试"}'
        })
        assert resp.json()["ok"] is True

    def test_error_has_ok_false_in_detail(self, client):
        """错误响应在 detail 中包含 ok: false."""
        resp = client.put("/api/v1/persona/attributes/bad_key", json={"value": "x"})
        assert resp.status_code == 400
        assert resp.json()["detail"]["ok"] is False
        assert "error" in resp.json()["detail"]

        resp = client.post("/api/v1/persona/import", json={})
        assert resp.status_code == 400
        assert resp.json()["detail"]["ok"] is False

    def test_validation_error_format(self, client):
        """Pydantic 验证错误的格式."""
        # 尝试访问不存在的路径
        resp = client.get("/api/v1/persona/nonexistent")
        assert resp.status_code == 404
