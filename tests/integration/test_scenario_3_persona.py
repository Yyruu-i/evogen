"""T-07-01 场景3：跨平台人格一致性 — 端到端集成测试.

验证：
- get_active_persona 跨不同 profile 返回相同属性
- get_prompt_injection 包含设置的属性
- get_prompt_injection 格式正确（中文 Markdown）
- import_persona + export_persona round-trip

对齐 03-产品详细设计-v2.0.md 第1080-1121行.
使用真实引擎（PersonaEngine + PersonaDAO + SQLite）.
"""

import json

import pytest

from backend.persona.engine import Persona, PersonaEngine


# ───────────────────────────────────────────────────────
# Fixtures
# ───────────────────────────────────────────────────────

@pytest.fixture
def engine(tmp_path):
    """创建使用临时数据库的 PersonaEngine."""
    from backend.db.connection import ConnectionManager
    from backend.db.migrations import run_migrations
    from backend.persona.dao import PersonaDAO
    from backend.persona.engine import reset_engine

    db_path = str(tmp_path / "test_persona.db")
    db = ConnectionManager(db_path)
    run_migrations(db)

    # 注入临时 DB 到 PersonaDAO
    import backend.persona.dao as dao_mod
    old_get_db = dao_mod.get_db
    dao_mod.get_db = lambda: db

    try:
        reset_engine()
        dao = PersonaDAO()
        eng = PersonaEngine(dao=dao)
        yield eng
    finally:
        dao_mod.get_db = old_get_db
        db.close()


# ───────────────────────────────────────────────────────
# 场景3：跨平台人格一致性
# ───────────────────────────────────────────────────────

class TestCrossPlatformPersona:
    """跨平台人格一致性集成测试."""

    # ── 步骤1: 设置人格属性 ──────────────────────────

    @pytest.mark.asyncio
    async def test_step1_set_persona_attributes(self, engine):
        """步骤1: 设置 conciseness=0.8, display_name='小明'."""
        persona = await engine.update_attribute("conciseness", 0.8)
        assert persona.conciseness == 0.8

        persona = await engine.update_attribute("display_name", "小明")
        assert persona.display_name == "小明"

        # 验证持久化
        persona = await engine.get_active_persona()
        assert persona.conciseness == 0.8
        assert persona.display_name == "小明"

    # ── 步骤2: 跨 profile 一致性 ─────────────────────

    @pytest.mark.asyncio
    async def test_step2_cross_profile_consistency(self, engine):
        """步骤2: 验证 get_active_persona 跨不同 profile（session）返回相同属性."""
        await engine.set_attributes({
            "display_name": "小明",
            "conciseness": 0.8,
            "warmth": 0.9,
        })

        # 模拟不同平台（用不同 session 参数模拟）
        p1 = await engine.get_active_persona(session="feishu")
        p2 = await engine.get_active_persona(session="telegram")
        p3 = await engine.get_active_persona(session="cli")

        # 跨平台属性必须一致
        assert p1.display_name == p2.display_name == p3.display_name == "小明", (
            "display_name 跨平台应一致"
        )
        assert p1.conciseness == p2.conciseness == p3.conciseness == 0.8, (
            "conciseness 跨平台应一致"
        )
        assert p1.warmth == p2.warmth == p3.warmth == 0.9, (
            "warmth 跨平台应一致"
        )

        # 默认值也应一致
        assert p1.formality == p2.formality == 0.5
        assert p1.auto_approve_tools == p2.auto_approve_tools == False

    # ── 步骤3: get_prompt_injection 包含设置的属性 ────

    @pytest.mark.asyncio
    async def test_step3_prompt_injection_includes_attributes(self, engine):
        """步骤3: get_prompt_injection 包含 conciseness 和 display_name."""
        await engine.set_attributes({
            "display_name": "小明",
            "conciseness": 0.8,
        })

        prompt = await engine.get_prompt_injection()

        # 验证包含标题
        assert "## 用户偏好" in prompt, "应包含标题"

        # 验证 display_name
        assert "称呼：小明" in prompt, "应包含用户称呼"

        # 验证 conciseness=0.8 → "极简"（0.6 < 0.8 < 1.01 区间映射为"极简"）
        assert "回复风格" in prompt, "应包含回复风格"
        assert "极简" in prompt, "conciseness=0.8 应对应'极简'"

        # 默认值不应出现
        assert "回复语言" not in prompt, "默认语言 zh 不应出现"
        assert "显示思考过程" not in prompt, "默认 True 不应出现"

    # ── 步骤4: 验证 prompt 格式正确 ──────────────────

    @pytest.mark.asyncio
    async def test_step4_prompt_format_correct(self, engine):
        """步骤4: get_prompt_injection 输出格式正确 — 中文 Markdown 列表."""
        await engine.set_attributes({
            "display_name": "小明",
            "conciseness": 0.8,
            "formality": 0.2,
            "auto_approve_tools": True,
        })

        prompt = await engine.get_prompt_injection()

        # 格式验证
        assert prompt.startswith("##"), "应以 Markdown H2 标题开头"
        assert "用户偏好" in prompt, "标题应为'用户偏好'"

        # 列表项验证
        lines = prompt.split("\n")
        list_items = [l for l in lines if l.startswith("- ")]
        assert len(list_items) >= 2, (
            f"应有至少2个列表项，实际: {len(list_items)}"
        )

        # 每个列表项格式为 "- key：value"
        for item in list_items:
            assert "：" in item or ":" in item, (
                f"列表项 '{item[:30]}' 应包含分隔符"
            )

        # Token 限制验证
        assert len(prompt) <= 2100, (
            f"prompt 长度 {len(prompt)} 超过 2100 字符限制"
        )

    # ── 步骤5: import/export round-trip ───────────────

    @pytest.mark.asyncio
    async def test_step5_import_export_roundtrip(self, engine):
        """步骤5: 验证 import_persona + export_persona round-trip 数据一致性."""
        # 设置初始属性
        await engine.set_attributes({
            "display_name": "小明",
            "conciseness": 0.8,
            "warmth": 0.9,
            "formality": 0.3,
            "timezone": "Asia/Shanghai",
        })

        # 导出
        exported = await engine.export_persona()
        assert isinstance(exported, str)
        export_data = json.loads(exported)

        # 验证导出数据完整性
        assert export_data["display_name"] == "小明"
        assert export_data["conciseness"] == 0.8
        assert export_data["warmth"] == 0.9
        assert export_data["timezone"] == "Asia/Shanghai"

        # 重置为不同值
        await engine.set_attributes({
            "display_name": "临时用户",
            "conciseness": 0.5,
            "warmth": 0.7,
        })

        # 导入之前导出的数据
        persona = await engine.import_persona(exported)

        # 验证 round-trip 一致性
        assert persona.display_name == "小明", (
            f"round-trip display_name: 期望'小明', 实际'{persona.display_name}'"
        )
        assert persona.conciseness == 0.8, (
            f"round-trip conciseness: 期望0.8, 实际{persona.conciseness}"
        )
        assert persona.warmth == 0.9, (
            f"round-trip warmth: 期望0.9, 实际{persona.warmth}"
        )
        assert persona.formality == 0.3, (
            f"round-trip formality: 期望0.3, 实际{persona.formality}"
        )
        assert persona.timezone == "Asia/Shanghai", (
            f"round-trip timezone: 期望'Asia/Shanghai', 实际'{persona.timezone}'"
        )

    # ── 步骤6: 多次导入/导出保持一致性 ──────────────

    @pytest.mark.asyncio
    async def test_step6_multiple_roundtrips(self, engine):
        """步骤6: 多次 import/export 循环不丢失数据."""
        original = {
            "display_name": "小明",
            "conciseness": 0.8,
            "warmth": 0.9,
            "preferred_language": "zh",
        }
        await engine.set_attributes(original)

        for i in range(3):
            exported = await engine.export_persona()
            # 重置
            await engine.set_attributes({"display_name": f"temp_{i}", "conciseness": 0.5})
            # 重新导入
            persona = await engine.import_persona(exported)

            assert persona.display_name == "小明", f"第{i+1}次 round-trip display_name 丢失"
            assert persona.conciseness == 0.8, f"第{i+1}次 round-trip conciseness 丢失"
            assert persona.warmth == 0.9, f"第{i+1}次 round-trip warmth 丢失"

    # ── 步骤7: 批量属性操作 ──────────────────────────

    @pytest.mark.asyncio
    async def test_step7_bulk_attribute_operations(self, engine):
        """步骤7: set_attributes 批量设置 + get_attributes 批量读取."""
        attrs = {
            "display_name": "小明",
            "conciseness": 0.8,
            "formality": 0.2,
            "warmth": 0.9,
            "directness": 0.7,
            "timezone": "Asia/Shanghai",
            "preferred_language": "zh",
            "response_language": "zh",
        }
        persona = await engine.set_attributes(attrs)

        # 验证所有属性已设置
        assert persona.display_name == "小明"
        assert persona.conciseness == 0.8
        assert persona.formality == 0.2
        assert persona.warmth == 0.9
        assert persona.directness == 0.7
        assert persona.timezone == "Asia/Shanghai"

        # get_attributes 返回完整字典
        all_attrs = await engine.get_attributes()
        assert isinstance(all_attrs, dict)
        for key in ["display_name", "conciseness", "warmth", "timezone"]:
            assert key in all_attrs, f"get_attributes 应包含 '{key}'"

        # 验证 System Prompt 注入包含多个已设置属性
        prompt = await engine.get_prompt_injection()
        assert "称呼：小明" in prompt
        assert "极简" in prompt  # conciseness=0.8 → "极简"
        assert "非常随意" in prompt  # formality=0.2
        assert "非常热情" in prompt  # warmth=0.9
        assert "直接" in prompt  # directness=0.7
        assert "Asia/Shanghai" in prompt  # timezone
