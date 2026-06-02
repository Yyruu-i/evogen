"""T-04-01 PersonaDAO — 人格属性数据访问层.

使用 persona_attributes 表（key/value_json 模型），
自动处理 JSON 序列化/反序列化。
"""

import json
import logging
from typing import Any, Dict, Optional

from backend.db.connection import get_db

logger = logging.getLogger(__name__)

# ── 已知属性白名单（用于校验） ──
_KNOWN_KEYS: set = {
    "display_name",
    "preferred_language",
    "timezone",
    "conciseness",
    "formality",
    "warmth",
    "directness",
    "auto_approve_tools",
    "show_thinking",
    "response_language",
    "learned_preferences",
    "discovery_questions_asked",
}


class PersonaDAO:
    """人格属性持久化 DAO — 无状态，每次调用从数据库读写."""

    def __init__(self):
        self._db = get_db()

    # ── 序列化辅助 ──────────────────────────────────

    @staticmethod
    def _serialize(value: Any) -> str:
        """将 Python 值序列化为 JSON 字符串.

        - None/null → 'null'
        - bool → 'true'/'false'
        - int/float → '123'/'0.5'
        - str → '"...",' (JSON 字符串)
        - dict/list → JSON
        """
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            # 整数和浮点数直接转字符串即可被 JSON 解析
            return json.dumps(value)
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _deserialize(value_json: str) -> Any:
        """将 JSON 字符串反序列化为 Python 值."""
        if value_json is None:
            return None
        return json.loads(value_json)

    # ── CRUD ────────────────────────────────────────

    def get_all(self) -> Dict[str, Any]:
        """读取所有属性，返回 {key: deserialized_value}.

        始终返回所有已知 key，缺失的返回 None。
        """
        cursor = self._db.execute("SELECT key, value_json FROM persona_attributes")
        rows = cursor.fetchall()
        result: Dict[str, Any] = {}
        for row in rows:
            result[row["key"]] = self._deserialize(row["value_json"])

        # 确保所有已知 key 都有值
        for key in _KNOWN_KEYS:
            if key not in result:
                result[key] = None
        return result

    def get(self, key: str) -> Any:
        """读取单个属性值."""
        cursor = self._db.execute(
            "SELECT value_json FROM persona_attributes WHERE key = ?", (key,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._deserialize(row["value_json"])

    def set(self, key: str, value: Any) -> None:
        """写入单个属性值（UPSERT）."""
        value_json = self._serialize(value)
        self._db.execute(
            """INSERT INTO persona_attributes (key, value_json, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(key) DO UPDATE SET
                   value_json = excluded.value_json,
                   updated_at = excluded.updated_at""",
            (key, value_json),
        )
        self._db.commit()

    def set_batch(self, attrs: Dict[str, Any]) -> None:
        """批量写入属性（单个事务）."""
        for key, value in attrs.items():
            if key not in _KNOWN_KEYS:
                logger.warning(f"PersonaDAO: ignoring unknown key '{key}'")
                continue
            value_json = self._serialize(value)
            self._db.execute(
                """INSERT INTO persona_attributes (key, value_json, updated_at)
                   VALUES (?, ?, datetime('now'))
                   ON CONFLICT(key) DO UPDATE SET
                       value_json = excluded.value_json,
                       updated_at = excluded.updated_at""",
                (key, value_json),
            )
        self._db.commit()

    @staticmethod
    def is_known_key(key: str) -> bool:
        """检查 key 是否在白名单中."""
        return key in _KNOWN_KEYS

    @staticmethod
    def get_known_keys() -> set:
        """返回属性白名单."""
        return _KNOWN_KEYS.copy()
