"""T-00-04 测试：LLM 事实提取器."""

import os
from dotenv import load_dotenv

# 加载 Hermes 环境变量（含 DEEPSEEK_API_KEY）
# 注意：Hermes 可能重定向 HOME，需要尝试多个路径；load_dotenv(override=False)
# 默认不覆盖已存在变量，所以优先加载优先级低的，最后加载包含 API key 的
for _candidate in (
    os.path.join(os.path.expanduser("~"), ".hermes"),
    os.environ.get("HERMES_HOME", ""),
    "/root/.hermes",
):
    _env = os.path.join(_candidate, ".env")
    if os.path.exists(_env):
        load_dotenv(_env)

import pytest
from backend.memory.extractor import FactExtractor, _parse_json_from_response, get_extractor


# ════════════════════════════════════════════════════════
# 单元测试（不调 LLM，纯本地逻辑）
# ════════════════════════════════════════════════════════

class TestParseJSON:
    """JSON 解析测试."""

    def test_pure_json_array(self):
        """正常 JSON 数组."""
        result = _parse_json_from_response('[{"type":"preference","content":"test","importance":0.5,"privacy_level":"internal"}]')
        assert len(result) == 1
        assert result[0]["content"] == "test"

    def test_markdown_code_block(self):
        """Markdown code block 包裹."""
        text = '```json\n[{"type":"preference","content":"test","importance":0.8}]\n```'
        result = _parse_json_from_response(text)
        assert len(result) == 1
        assert result[0]["importance"] == 0.8

    def test_plain_code_block(self):
        """无语言标记的 code block."""
        text = '```\n[{"type":"fact","content":"hello"}]\n```'
        result = _parse_json_from_response(text)
        assert len(result) == 1

    def test_empty_array(self):
        """空数组."""
        result = _parse_json_from_response('[]')
        assert result == []

    def test_array_in_text(self):
        """JSON 数组嵌在普通文本中."""
        text = '好的，以下是提取的事实：\n[{"type":"preference","content":"test"}]\n以上是全部。'
        result = _parse_json_from_response(text)
        assert len(result) == 1

    def test_invalid_json_raises(self):
        """无效 JSON 抛出异常."""
        with pytest.raises(ValueError):
            _parse_json_from_response('这不是 JSON')


class TestValidate:
    """事实校验测试."""

    def test_valid_fact(self):
        """合法事实通过."""
        facts = [{"type": "preference", "content": "喝咖啡不加糖", "importance": 0.7, "privacy_level": "internal"}]
        validated = FactExtractor._validate(facts)
        assert len(validated) == 1
        assert validated[0]["content"] == "喝咖啡不加糖"

    def test_invalid_type_fallback(self):
        """非法 type 回退到 other."""
        facts = [{"type": "invalid_type", "content": "test"}]
        validated = FactExtractor._validate(facts)
        assert validated[0]["type"] == "other"

    def test_importance_clamp(self):
        """importance 范围钳制."""
        facts = [{"type": "preference", "content": "test", "importance": 1.5}]
        validated = FactExtractor._validate(facts)
        assert validated[0]["importance"] == 1.0

        facts = [{"type": "preference", "content": "test", "importance": -0.5}]
        validated = FactExtractor._validate(facts)
        assert validated[0]["importance"] == 0.0

    def test_empty_content_filtered(self):
        """空 content 被过滤."""
        facts = [{"type": "preference", "content": ""}]
        validated = FactExtractor._validate(facts)
        assert validated == []

    def test_invalid_privacy_fallback(self):
        """非法 privacy_level 回退."""
        facts = [{"type": "preference", "content": "test", "privacy_level": "top_secret"}]
        validated = FactExtractor._validate(facts)
        assert validated[0]["privacy_level"] == "internal"

    def test_non_list_input(self):
        """非列表输入抛异常."""
        with pytest.raises(ValueError):
            FactExtractor._validate({"not": "a list"})

    def test_round_importance(self):
        """importance 四舍五入."""
        facts = [{"type": "preference", "content": "test", "importance": 0.789}]
        validated = FactExtractor._validate(facts)
        assert validated[0]["importance"] == 0.79


class TestConfirmationQuestion:
    """确认问题生成测试."""

    def test_preference_question(self):
        extractor = get_extractor()
        q = extractor.generate_confirmation_question({"type": "preference", "content": "喝咖啡"})
        assert "喝咖啡" in q

    def test_empty_content(self):
        extractor = get_extractor()
        q = extractor.generate_confirmation_question({"type": "other", "content": ""})
        assert len(q) > 0

    def test_personal_info(self):
        extractor = get_extractor()
        q = extractor.generate_confirmation_question({"type": "personal_info", "content": "用户叫小明"})
        assert "小明" in q


# ════════════════════════════════════════════════════════
# 集成测试（调 LLM，网络依赖）
# ════════════════════════════════════════════════════════

@pytest.mark.integration
class TestExtractIntegration:
    """LLM 事实提取集成测试."""

    @pytest.fixture
    def extractor(self):
        return get_extractor()

    def test_travel_planning(self, extractor):
        """场景1：旅行规划."""
        msgs = [
            {"role": "user", "content": "帮我规划一趟日本旅行，7天，预算1万"},
            {"role": "assistant", "content": "好的，我帮你规划。推荐东京-大阪-京都路线。"},
            {"role": "user", "content": "酒店选便宜的民宿就好，我比较喜欢住当地人家里"},
            {"role": "user", "content": "别选红眼航班，太累了"},
        ]
        facts = extractor.extract(msgs)
        assert len(facts) >= 2, f"旅行规划应提取≥2条事实，实际: {len(facts)}"
        # 检查关键信息
        contents = [f["content"] for f in facts]
        combined = " ".join(contents)
        assert any(kw in combined for kw in ["日本", "旅行", "东京", "大阪", "京都"]), f"缺少目的地: {combined}"
        assert any(kw in combined for kw in ["民宿", "酒店", "航班", "预算"]), f"缺少偏好: {combined}"

    def test_work_consultation(self, extractor):
        """场景2：工作咨询."""
        msgs = [
            {"role": "user", "content": "我是Python后端开发，主要用FastAPI和PostgreSQL"},
            {"role": "assistant", "content": "明白了，你的技术栈很清晰。"},
        ]
        facts = extractor.extract(msgs)
        assert len(facts) >= 1, f"应提取≥1条，实际: {len(facts)}"
        contents = " ".join([f["content"] for f in facts])
        assert any(kw in contents for kw in ["Python", "后端", "FastAPI", "开发"])

    def test_greeting_no_facts(self, extractor):
        """场景3：寒暄——无事实."""
        msgs = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮你的？"},
            {"role": "user", "content": "今天天气不错"},
        ]
        facts = extractor.extract(msgs)
        # 寒暄不应提取到有价值事实
        assert len(facts) <= 1, f"寒暄不应提取事实，实际: {len(facts)}"

    def test_health_sensitive(self, extractor):
        """场景4：健康信息——标记敏感."""
        msgs = [
            {"role": "user", "content": "我最近失眠严重，每晚只能睡3-4个小时"},
            {"role": "assistant", "content": "听起来很辛苦，建议你去看医生。"},
        ]
        facts = extractor.extract(msgs)
        assert len(facts) >= 1
        # 健康信息应标记为 sensitive
        privacy_levels = [f.get("privacy_level", "") for f in facts]
        assert any("sensitive" in p for p in privacy_levels), f"健康信息应敏感: {privacy_levels}"

    def test_relationship(self, extractor):
        """场景5：人际关系."""
        msgs = [
            {"role": "user", "content": "我老婆叫小红，有两个孩子，一个5岁一个8岁"},
        ]
        facts = extractor.extract(msgs)
        assert len(facts) >= 2, f"应提取≥2条，实际: {len(facts)}"

    def test_learning_plan(self, extractor):
        """场景6：学习计划."""
        msgs = [
            {"role": "user", "content": "我想学Rust语言，计划每天花1小时，3个月内入门"},
        ]
        facts = extractor.extract(msgs)
        assert len(facts) >= 1

    def test_diet_allergy(self, extractor):
        """场景7：饮食过敏."""
        msgs = [
            {"role": "user", "content": "我花生过敏，绝对不能吃任何含花生的东西"},
        ]
        facts = extractor.extract(msgs)
        assert len(facts) >= 1
        # 过敏信息 importance 应该很高
        if facts:
            assert facts[0]["importance"] >= 0.6, f"过敏信息重要性应高: {facts[0]['importance']}"

    def test_coding_question_no_facts(self, extractor):
        """场景8：编程问题——无个人事实."""
        msgs = [
            {"role": "user", "content": "Python的asyncio和gevent有什么区别？"},
            {"role": "assistant", "content": "asyncio是Python标准库的异步框架..."},
        ]
        facts = extractor.extract(msgs)
        # 纯技术问题不应提取个人事实
        assert len(facts) <= 1

    def test_mixed_language(self, extractor):
        """场景9：中英混合."""
        msgs = [
            {"role": "user", "content": "I love drinking coffee without sugar, 这是我的习惯"},
        ]
        facts = extractor.extract(msgs)
        assert len(facts) >= 1
        contents = " ".join([f["content"] for f in facts])
        assert "咖啡" in contents or "coffee" in contents.lower()

    def test_empty_info(self, extractor):
        """场景10：景点咨询——无可记忆信息."""
        msgs = [
            {"role": "user", "content": "故宫几点开门？"},
            {"role": "assistant", "content": "故宫上午8:30开门。"},
        ]
        facts = extractor.extract(msgs)
        # 咨询景点信息不应提取为个人事实
        assert len(facts) <= 1
