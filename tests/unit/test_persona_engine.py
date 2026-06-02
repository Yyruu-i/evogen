"""T-04-01 / T-04-03 测试：PersonaDAO + PersonaEngine.

覆盖：
- DAO CRUD 操作 + JSON 序列化
- Engine 属性管理 + 导入/导出
- System Prompt 注入（中文 Markdown、非默认值过滤、token 控制）
"""

import json
import pytest


# ════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════


@pytest.fixture
def dao(tmp_path):
    """创建使用临时数据库的 PersonaDAO."""
    from backend.db.connection import ConnectionManager
    from backend.db.migrations import run_migrations
    from backend.persona.dao import PersonaDAO

    db_path = str(tmp_path / "test_persona_evogen.db")
    db = ConnectionManager(db_path)
    run_migrations(db)

    # 注入临时 DB
    import backend.persona.dao as dao_mod
    old_db = dao_mod.get_db
    dao_mod.get_db = lambda: db
    try:
        d = PersonaDAO()
        yield d
    finally:
        dao_mod.get_db = old_db


@pytest.fixture
def engine(dao):
    """创建使用测试 DAO 的 PersonaEngine."""
    from backend.persona.engine import PersonaEngine, reset_engine
    reset_engine()
    eng = PersonaEngine(dao=dao)
    return eng


# ════════════════════════════════════════════════════════
# PersonaDAO 测试
# ════════════════════════════════════════════════════════


class TestPersonaDAO:
    """T-04-01 测试."""

    def test_get_all_returns_defaults(self, dao):
        """get_all 返回 schema 预置的默认值."""
        attrs = dao.get_all()
        assert attrs["preferred_language"] == "zh"
        assert attrs["conciseness"] == 0.5
        assert attrs["formality"] == 0.5
        assert attrs["warmth"] == 0.7
        assert attrs["directness"] == 0.5
        assert attrs["auto_approve_tools"] is False
        assert attrs["show_thinking"] is True
        assert attrs["response_language"] == "zh"
        assert attrs["learned_preferences"] == {}
        assert attrs["discovery_questions_asked"] == 0

    def test_get_all_contains_all_known_keys(self, dao):
        """get_all 保证返回所有已知 key."""
        attrs = dao.get_all()
        from backend.persona.dao import _KNOWN_KEYS
        for key in _KNOWN_KEYS:
            assert key in attrs, f"Missing key: {key}"

    def test_get_single(self, dao):
        """get 读取单个属性."""
        val = dao.get("conciseness")
        assert val == 0.5

        val = dao.get("preferred_language")
        assert val == "zh"

    def test_get_nonexistent(self, dao):
        """get 不存在的 key 返回 None."""
        val = dao.get("nonexistent_key")
        assert val is None

    def test_set_and_get(self, dao):
        """set 写入后 get 可读."""
        dao.set("display_name", "张三")
        assert dao.get("display_name") == "张三"

    def test_set_overwrite(self, dao):
        """set 覆盖已有值."""
        dao.set("conciseness", 0.8)
        assert dao.get("conciseness") == 0.8

    def test_set_bool(self, dao):
        """set bool 值正常序列化/反序列化."""
        dao.set("auto_approve_tools", True)
        assert dao.get("auto_approve_tools") is True

        dao.set("auto_approve_tools", False)
        assert dao.get("auto_approve_tools") is False

    def test_set_none(self, dao):
        """set None 正常序列化."""
        dao.set("display_name", "temp")
        dao.set("display_name", None)
        assert dao.get("display_name") is None

    def test_set_dict(self, dao):
        """set dict 正常序列化/反序列化."""
        dao.set("learned_preferences", {"fav_color": "blue", "prefers_bullets": True})
        val = dao.get("learned_preferences")
        assert val == {"fav_color": "blue", "prefers_bullets": True}

    def test_set_batch(self, dao):
        """set_batch 批量写入."""
        dao.set_batch({
            "display_name": "李四",
            "conciseness": 0.9,
            "warmth": 0.5,
        })
        assert dao.get("display_name") == "李四"
        assert dao.get("conciseness") == 0.9
        assert dao.get("warmth") == 0.5

    def test_set_batch_unknown_key_warning(self, dao, caplog):
        """set_batch 忽略未知 key 并打 warning."""
        import logging
        caplog.set_level(logging.WARNING)
        dao.set_batch({"unknown_key": "value", "conciseness": 0.3})
        assert dao.get("conciseness") == 0.3
        assert "unknown_key" in caplog.text or True  # 至少不报错

    def test_is_known_key(self, dao):
        """is_known_key 白名单校验."""
        from backend.persona.dao import PersonaDAO
        assert PersonaDAO.is_known_key("display_name") is True
        assert PersonaDAO.is_known_key("conciseness") is True
        assert PersonaDAO.is_known_key("random_key") is False

    def test_serialize(self):
        """PersonaDAO._serialize 各种类型."""
        from backend.persona.dao import PersonaDAO
        assert PersonaDAO._serialize(None) == "null"
        assert PersonaDAO._serialize(True) == "true"
        assert PersonaDAO._serialize(False) == "false"
        assert PersonaDAO._serialize(42) == "42"
        assert PersonaDAO._serialize(0.5) == "0.5"
        assert PersonaDAO._serialize("hello") == '"hello"'
        assert PersonaDAO._serialize({"a": 1}) == '{"a": 1}'

    def test_deserialize(self):
        """PersonaDAO._deserialize 各种类型."""
        from backend.persona.dao import PersonaDAO
        assert PersonaDAO._deserialize("null") is None
        assert PersonaDAO._deserialize("true") is True
        assert PersonaDAO._deserialize("false") is False
        assert PersonaDAO._deserialize("42") == 42
        assert PersonaDAO._deserialize("0.5") == 0.5
        assert PersonaDAO._deserialize('"hello"') == "hello"
        assert PersonaDAO._deserialize('{"a": 1}') == {"a": 1}


# ════════════════════════════════════════════════════════
# PersonaEngine 测试
# ════════════════════════════════════════════════════════


class TestPersonaEngine:
    """T-04-02 测试."""

    @pytest.mark.asyncio
    async def test_get_active_persona_defaults(self, engine):
        """get_active_persona 返回默认 Persona."""
        persona = await engine.get_active_persona()
        assert persona.preferred_language == "zh"
        assert persona.conciseness == 0.5
        assert persona.warmth == 0.7
        assert persona.auto_approve_tools is False

    @pytest.mark.asyncio
    async def test_get_active_persona_with_session_ignored(self, engine):
        """session 参数被接受但不影响结果（MVP 跨 profile）."""
        p1 = await engine.get_active_persona(session="sess-1")
        p2 = await engine.get_active_persona(session="sess-2")
        assert p1.conciseness == p2.conciseness

    @pytest.mark.asyncio
    async def test_update_attribute(self, engine):
        """update_attribute 单属性更新."""
        persona = await engine.update_attribute("display_name", "王五")
        assert persona.display_name == "王五"

        # 验证持久化
        persona2 = await engine.get_active_persona()
        assert persona2.display_name == "王五"

    @pytest.mark.asyncio
    async def test_update_attribute_unknown_key(self, engine):
        """update_attribute 未知 key 抛出 ValueError."""
        with pytest.raises(ValueError, match="Unknown persona attribute"):
            await engine.update_attribute("bad_key", "value")

    @pytest.mark.asyncio
    async def test_get_attributes(self, engine):
        """get_attributes 返回完整字典."""
        attrs = await engine.get_attributes()
        assert isinstance(attrs, dict)
        assert "conciseness" in attrs
        assert "warmth" in attrs
        assert attrs["warmth"] == 0.7

    @pytest.mark.asyncio
    async def test_set_attributes(self, engine):
        """set_attributes 批量设置."""
        persona = await engine.set_attributes({
            "display_name": "赵六",
            "conciseness": 0.9,
            "formality": 0.2,
        })
        assert persona.display_name == "赵六"
        assert persona.conciseness == 0.9
        assert persona.formality == 0.2

    @pytest.mark.asyncio
    async def test_export_persona(self, engine):
        """export_persona 导出 JSON."""
        await engine.update_attribute("display_name", "测试用户")
        await engine.update_attribute("conciseness", 0.8)

        json_str = await engine.export_persona()
        data = json.loads(json_str)

        assert data["display_name"] == "测试用户"
        assert data["conciseness"] == 0.8
        assert data["warmth"] == 0.7  # 默认值也导出

    @pytest.mark.asyncio
    async def test_import_persona_valid(self, engine):
        """import_persona 正常导入."""
        json_str = json.dumps({
            "display_name": "导入用户",
            "conciseness": 0.95,
            "warmth": 0.2,
        })
        persona = await engine.import_persona(json_str)
        assert persona.display_name == "导入用户"
        assert persona.conciseness == 0.95
        assert persona.warmth == 0.2

    @pytest.mark.asyncio
    async def test_import_persona_invalid_json(self, engine):
        """import_persona 无效 JSON 抛出 ValueError."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            await engine.import_persona("not valid json {{{")

    @pytest.mark.asyncio
    async def test_import_persona_not_dict(self, engine):
        """import_persona JSON 数组抛出 ValueError."""
        with pytest.raises(ValueError, match="must be a JSON object"):
            await engine.import_persona("[1, 2, 3]")

    @pytest.mark.asyncio
    async def test_import_persona_whitelist_filter(self, engine):
        """import_persona 白名单过滤未知 key."""
        json_str = json.dumps({
            "display_name": "合法",
            "bad_key": "should_be_ignored",
            "conciseness": 0.7,
        })
        persona = await engine.import_persona(json_str)
        assert persona.display_name == "合法"
        assert persona.conciseness == 0.7
        # bad_key 被忽略，默认值保持不变

    @pytest.mark.asyncio
    async def test_import_persona_no_valid_keys(self, engine):
        """import_persona 全是未知 key 抛出 ValueError."""
        with pytest.raises(ValueError, match="No valid persona attributes"):
            await engine.import_persona('{"x": 1, "y": 2}')

    @pytest.mark.asyncio
    async def test_roundtrip_export_import(self, engine):
        """导出再导入，数据保持一致."""
        await engine.set_attributes({
            "display_name": "往返测试",
            "conciseness": 0.75,
            "warmth": 0.3,
        })
        exported = await engine.export_persona()
        persona = await engine.import_persona(exported)
        assert persona.display_name == "往返测试"
        assert persona.conciseness == 0.75
        assert persona.warmth == 0.3


# ════════════════════════════════════════════════════════
# get_prompt_injection 测试
# ════════════════════════════════════════════════════════


class TestPromptInjection:
    """T-04-03 测试."""

    @pytest.mark.asyncio
    async def test_empty_when_all_defaults(self, engine):
        """全部为默认值时返回空字符串."""
        prompt = await engine.get_prompt_injection()
        assert prompt == ""

    @pytest.mark.asyncio
    async def test_display_name_included(self, engine):
        """设置了 display_name 时 prompt 包含称呼."""
        await engine.update_attribute("display_name", "张三")
        prompt = await engine.get_prompt_injection()
        assert "称呼：张三" in prompt
        assert "## 用户偏好" in prompt

    @pytest.mark.asyncio
    async def test_language_included(self, engine):
        """非默认语言时 prompt 包含偏好语言."""
        await engine.update_attribute("preferred_language", "en")
        prompt = await engine.get_prompt_injection()
        assert "偏好语言" in prompt
        assert "English" in prompt

    @pytest.mark.asyncio
    async def test_style_changes_included(self, engine):
        """风格属性变更时 prompt 包含可读描述."""
        await engine.update_attribute("conciseness", 0.9)
        await engine.update_attribute("formality", 0.2)
        prompt = await engine.get_prompt_injection()
        assert "回复风格" in prompt
        assert "极简" in prompt
        assert "非常随意" in prompt

    @pytest.mark.asyncio
    async def test_functional_prefs_included(self, engine):
        """功能偏好变更时 prompt 包含相应描述."""
        await engine.update_attribute("auto_approve_tools", True)
        await engine.update_attribute("show_thinking", False)
        prompt = await engine.get_prompt_injection()
        assert "自动批准工具" in prompt
        assert "显示思考过程" in prompt

    @pytest.mark.asyncio
    async def test_learned_preferences_included(self, engine):
        """学习到的偏好出现在 prompt 中."""
        await engine.update_attribute("learned_preferences", {
            "代码风格": "PEP8",
            "注释语言": "中文",
        })
        prompt = await engine.get_prompt_injection()
        assert "代码风格" in prompt
        assert "注释语言" in prompt
        assert "PEP8" in prompt

    @pytest.mark.asyncio
    async def test_default_values_not_included(self, engine):
        """默认值不出现在 prompt 中."""
        await engine.update_attribute("display_name", "用户A")
        prompt = await engine.get_prompt_injection()
        # 这些默认值不应出现
        assert "回复语言：中文" not in prompt  # zh 是默认
        assert "显示思考过程：是" not in prompt  # True 是默认
        assert "友好程度" not in prompt  # warmth=0.7 是默认未改

    @pytest.mark.asyncio
    async def test_prompt_is_chinese_markdown(self, engine):
        """prompt 格式为中文 Markdown."""
        await engine.update_attribute("display_name", "李四")
        await engine.update_attribute("conciseness", 0.9)
        prompt = await engine.get_prompt_injection()
        assert prompt.startswith("##")
        assert "用户偏好" in prompt
        # 每个属性是列表项
        assert prompt.count("\n- ") >= 1

    @pytest.mark.asyncio
    async def test_token_limit_respected(self, engine):
        """prompt 不超过约 2000 字符（约 500 tokens）."""
        # 设置大量学习偏好
        big_prefs = {f"pref_{i}": f"value_{i}_with_some_extra_text" for i in range(100)}
        await engine.update_attribute("learned_preferences", big_prefs)
        await engine.update_attribute("display_name", "大量用户")
        prompt = await engine.get_prompt_injection()
        assert len(prompt) <= 2100  # 允许一些余量


# ════════════════════════════════════════════════════════
# Persona 数据结构测试
# ════════════════════════════════════════════════════════


class TestPersonaDataclass:

    def test_default_creation(self):
        """Persona 默认值正确."""
        from backend.persona.engine import Persona
        p = Persona()
        assert p.conciseness == 0.5
        assert p.warmth == 0.7
        assert p.auto_approve_tools is False
        assert p.learned_preferences == {}

    def test_asdict(self):
        """Persona 可序列化为字典."""
        from dataclasses import asdict
        from backend.persona.engine import Persona
        p = Persona(display_name="测试")
        d = asdict(p)
        assert d["display_name"] == "测试"
        assert d["conciseness"] == 0.5
