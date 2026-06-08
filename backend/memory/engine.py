"""EvoMemoryEngine - 进化记忆引擎门面类.

对齐 03-产品详细设计-v2.0.md 第352-449行.
上层（API/AgentLoop）只通过此引擎访问记忆.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from backend.config import config
from backend.db.connection import ConnectionManager, get_db
from backend.db.vector_store import VectorStore, get_vector_store
from backend.memory.embedding import BGEM3EmbeddingProvider, get_embedding_provider
from backend.memory.extractor import FactExtractor, get_extractor

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════
# 数据结构
# ══════════════════════════════════════════════════


@dataclass
class MemoryFact:
    """记忆事实（对齐设计文档第413-427行）."""

    id: str  # UUID
    type: str  # preference | fact | procedure | relationship
    content: str  # 可读的记忆内容
    embedding: Optional[List[float]] = None  # 向量嵌入（仅在检索时填充）
    importance: float = 0.5  # 0-1 重要性评分
    weight: float = 1.0  # 当前权重（M1 衰减用，MVP 固定 1.0）
    layer: str = "working"  # transient | working | core
    source_session_id: Optional[str] = None
    source_interaction_id: Optional[str] = None
    privacy_level: str = "private"  # public | private | sensitive
    tags: List[str] = field(default_factory=list)
    user_id: str = "default"  # 用户隔离
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_accessed_at: Optional[str] = None
    similarity: Optional[float] = None  # 仅搜索结果中填充


@dataclass
class MemorySnapshot:
    """记忆快照（对齐设计文档第429-434行）."""

    core_facts: List[MemoryFact] = field(default_factory=list)
    working_facts: List[MemoryFact] = field(default_factory=list)
    transient_facts: List[MemoryFact] = field(default_factory=list)
    generated_at: Optional[str] = None
    snapshot_id: Optional[str] = None


@dataclass
class MemoryStats:
    """记忆统计（对齐设计文档第443-448行）."""

    total_facts: int = 0
    by_layer: Dict[str, int] = field(default_factory=dict)
    by_type: Dict[str, int] = field(default_factory=dict)
    last_extraction_at: Optional[str] = None
    total_vector_bytes: int = 0

    # ── 容量管理字段 ──
    archive_count: int = 0
    capacity_limit: int = 10000
    storage_estimate_bytes: int = 0
    usage_percent: float = 0.0
    archived_by_age_count: int = 0
    archived_by_importance_count: int = 0


# ══════════════════════════════════════════════════
# 事件类型（延迟导入避免循环依赖，但 MemoryFact 已就绪）
# ══════════════════════════════════════════════════

from backend.memory.events import MemoryEvent  # noqa: E402


# ══════════════════════════════════════════════════
# 类型映射（FactExtractor → Schema）
# ══════════════════════════════════════════════════

_EXTRACTOR_TYPE_MAP: Dict[str, str] = {
    "preference": "preference",
    "relationship": "relationship",
    "plan": "procedure",
    "personal_info": "fact",
    "experience": "fact",
    "knowledge": "fact",
    "health": "fact",
    "location": "fact",
    "habit": "fact",
    "other": "fact",
}

_PRIVACY_MAP: Dict[str, str] = {
    "public": "public",
    "internal": "private",
    "sensitive": "sensitive",
    "secret": "sensitive",
}


# ══════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════


def _utcnow_iso() -> str:
    """返回 UTC 时间的 ISO 格式字符串."""
    return datetime.now(timezone.utc).isoformat()


def _estimate_storage(db) -> int:
    """估算记忆总存储占用（SQLite + Chroma 向量）."""
    row = db.execute(
        "SELECT COUNT(*), COALESCE(SUM(LENGTH(content)), 0) FROM memory_facts"
    ).fetchone()
    if not row:
        return 0
    count, total_text_len = row[0], row[1]
    text_bytes = int(total_text_len * 1.5)
    vector_bytes = count * 1024 * 4
    return text_bytes + vector_bytes


# ══════════════════════════════════════════════════
# EvoMemoryEngine
# ══════════════════════════════════════════════════


class EvoMemoryEngine:
    """进化记忆引擎 — 记忆管理的统一门面.

    上层（API/AgentLoop）只通过此引擎访问记忆，
    所有底层操作（SQLite + Chroma）在此封装.
    """

    def __init__(
        self,
        db: Optional[ConnectionManager] = None,
        vector_store: Optional[VectorStore] = None,
        embedding_provider: Optional[BGEM3EmbeddingProvider] = None,
        extractor: Optional[FactExtractor] = None,
        db_path: Optional[str] = None,
        chroma_dir: Optional[str] = None,
    ):
        """初始化引擎.

        Args:
            db: SQLite 连接管理器. None 则使用全局单例.
            vector_store: Chroma 向量存储. None 则使用全局单例.
            embedding_provider: Embedding 提供器. None 则使用全局单例.
            extractor: LLM 事实提取器. None 则使用全局单例.
            db_path: 覆盖默认数据库路径（测试用）.
            chroma_dir: 覆盖默认 Chroma 持久化目录（测试用）.
        """
        self._db = db or get_db(db_path)
        self._vs = vector_store or get_vector_store()
        if chroma_dir:
            # 重新创建 VectorStore 以使用自定义目录
            self._vs = VectorStore(persist_dir=chroma_dir)
        self._embedding = embedding_provider or get_embedding_provider()
        self._extractor = extractor  # None → get_extractor() on demand
        self._last_extraction_at: Optional[str] = None

        # 观察者模式：WebSocket 事件订阅者（Phase 5 集成时挂载 Hermes HookRegistry）
        self._subscribers: List[Callable[['MemoryEvent'], None]] = []

    # ══════════════════════════════════════════════════
    # 观察者模式（事件钩子）
    # ══════════════════════════════════════════════════

    def subscribe(self, callback: Callable[['MemoryEvent'], None]) -> None:
        """订阅记忆变更事件.

        Args:
            callback: 接收 MemoryEvent 的回调函数.
        """
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[['MemoryEvent'], None]) -> None:
        """取消订阅.

        Args:
            callback: 要移除的回调函数.
        """
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def _emit(self, event: 'MemoryEvent') -> None:
        """向所有订阅者发送事件.

        Args:
            event: MemoryEvent 对象.
        """
        for subscriber in self._subscribers:
            try:
                subscriber(event)
            except Exception as e:
                logger.error(f"Event subscriber error: {e}", exc_info=True)

    # ══════════════════════════════════════════════════
    # CRUD
    # ══════════════════════════════════════════════════

    def add_manual_fact(
        self,
        content: str,
        type: str,
        importance: float = 0.5,
        layer: str = "working",
        tags: Optional[List[str]] = None,
        privacy_level: str = "private",
        user_id: str = "default",
    ) -> MemoryFact:
        """手动添加记忆事实.

        Args:
            content: 事实内容
            type: 事实类型 (preference|fact|procedure|relationship)
            importance: 重要性 0-1
            layer: 记忆层级 (transient|working|core)
            tags: 用户自定义标签
            privacy_level: 隐私级别 (public|private|sensitive)

        Returns:
            创建的 MemoryFact 对象.
        """
        fact_id = str(uuid.uuid4())
        tags = tags or []
        now = _utcnow_iso()

        # 0. Chroma 去重检查 (cosine > 0.85 提示用户)
        dup_warning = self._check_duplicate(content)

        # 1. 写入 Chroma（自动生成 embedding）
        chroma_meta = {
            "type": type,
            "importance": importance,
            "layer": layer,
            "privacy_level": privacy_level,
            "user_id": user_id,
        }
        self._vs.add_memory(fact_id, content, metadata=chroma_meta)

        # 2. 写入 SQLite
        try:
            self._db.execute(
                """INSERT INTO memory_facts
                   (id, type, content, chroma_id, importance, weight, layer,
                    privacy_level, tags_json, user_id, created_at, updated_at, last_accessed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    fact_id,
                    type,
                    content,
                    fact_id,
                    importance,
                    1.0,
                    layer,
                    privacy_level,
                    json.dumps(tags, ensure_ascii=False),
                    user_id,
                    now,
                    now,
                    now,
                ),
            )
            self._db.commit()
        except Exception:
            # 回滚：从 Chroma 删除
            self._vs.delete_memory(fact_id)
            raise

        fact = MemoryFact(
            id=fact_id,
            type=type,
            content=content,
            importance=importance,
            weight=1.0,
            layer=layer,
            privacy_level=privacy_level,
            tags=tags,
            created_at=now,
            updated_at=now,
            last_accessed_at=now,
        )

        # 3. 发布事件
        self._emit(MemoryEvent(
            action="created",
            fact=fact,
            metadata={"dup_warning": dup_warning} if dup_warning else {},
        ))

        return fact

    def update_fact(self, fact_id: str, **updates) -> MemoryFact:
        """更新记忆事实，支持部分字段更新.

        Args:
            fact_id: 事实 ID
            **updates: 要更新的字段 (type, content, importance, layer,
                       privacy_level, tags)

        Returns:
            更新后的 MemoryFact 对象.

        Raises:
            ValueError: 事实不存在.
        """
        existing = self._get_fact_by_id(fact_id)
        if existing is None:
            raise ValueError(f"Fact not found: {fact_id}")

        now = _utcnow_iso()
        content_changed = "content" in updates and updates["content"] != existing.content

        # 构建 SET 子句
        allowed_fields = {
            "type",
            "content",
            "importance",
            "layer",
            "privacy_level",
            "tags",
        }
        set_clauses: List[str] = []
        params: List[Any] = []

        for field in allowed_fields:
            if field in updates:
                value = updates[field]
                if field == "tags":
                    value = json.dumps(value, ensure_ascii=False)
                    set_clauses.append("tags_json = ?")
                else:
                    set_clauses.append(f"{field} = ?")
                params.append(value)

        if not set_clauses:
            return existing

        set_clauses.append("updated_at = ?")
        params.append(now)
        params.append(fact_id)

        # 更新 SQLite
        sql = f"UPDATE memory_facts SET {', '.join(set_clauses)} WHERE id = ?"
        self._db.execute(sql, params)
        self._db.commit()

        # 若 content 变化，更新 Chroma
        if content_changed:
            self._vs.delete_memory(fact_id)
            new_content = updates["content"]
            new_type = updates.get("type", existing.type)
            new_importance = updates.get("importance", existing.importance)
            new_layer = updates.get("layer", existing.layer)
            new_privacy = updates.get("privacy_level", existing.privacy_level)
            self._vs.add_memory(
                fact_id,
                new_content,
                metadata={
                    "type": new_type,
                    "importance": new_importance,
                    "layer": new_layer,
                    "privacy_level": new_privacy,
                    "user_id": existing.user_id,
                },
            )

        updated_fact = self._get_fact_by_id(fact_id)

        # 发布事件
        self._emit(MemoryEvent(action="updated", fact=updated_fact))

        return updated_fact

    def delete_fact(self, fact_id: str) -> None:
        """删除记忆事实.

        先删 Chroma，再删 SQLite.

        Args:
            fact_id: 事实 ID.
        """
        # 先获取事实用于事件发布
        existing = self._get_fact_by_id(fact_id)

        self._vs.delete_memory(fact_id)
        self._db.execute("DELETE FROM memory_facts WHERE id = ?", (fact_id,))
        self._db.commit()

        # 发布事件（即使 fact 已删除）
        if existing:
            self._emit(MemoryEvent(action="deleted", fact=existing))

    def reinforce(self, fact_id: str, amount: float = 0.1) -> MemoryFact:
        """强化记忆（增加权重和重要性）.

        Args:
            fact_id: 事实 ID
            amount: 强化幅度

        Returns:
            更新后的 MemoryFact 对象.

        Raises:
            ValueError: 事实不存在.
        """
        existing = self._get_fact_by_id(fact_id)
        if existing is None:
            raise ValueError(f"Fact not found: {fact_id}")

        new_weight = existing.weight + amount
        new_importance = min(1.0, existing.importance + amount)
        now = _utcnow_iso()

        self._db.execute(
            """UPDATE memory_facts
               SET weight = ?, importance = ?, last_accessed_at = ?, updated_at = ?
               WHERE id = ?""",
            (new_weight, new_importance, now, now, fact_id),
        )
        self._db.commit()

        reinforced_fact = self._get_fact_by_id(fact_id)

        # 发布事件
        self._emit(MemoryEvent(action="reinforced", fact=reinforced_fact))

        return reinforced_fact

    def list_facts(
        self,
        layer: Optional[str] = None,
        type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        user_id: str = "default",
    ) -> List[MemoryFact]:
        """分页列出记忆事实.

        Args:
            layer: 按层级筛选 (transient|working|core|all). None 表示全部.
            type: 按类型筛选. None 表示全部.
            limit: 每页数量.
            offset: 偏移量.
            user_id: 用户 ID（数据隔离）.

        Returns:
            MemoryFact 列表.
        """
        where_clauses: List[str] = ["user_id = ?"]
        params: List[Any] = [user_id]

        if layer and layer != "all":
            where_clauses.append("layer = ?")
            params.append(layer)
        if type:
            where_clauses.append("type = ?")
            params.append(type)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        sql = (
            f"SELECT * FROM memory_facts {where_sql} "
            f"ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])

        rows = self._db.execute(sql, params).fetchall()
        return [self._row_to_fact(row) for row in rows]

    def search_memories(self, query: str, top_k: int = 10, user_id: str = "default") -> List[MemoryFact]:
        """向量语义搜索记忆.

        Args:
            query: 查询文本.
            top_k: 返回结果数.
            user_id: 用户 ID（数据隔离）.

        Returns:
            按相似度降序排列的 MemoryFact 列表.
        """
        results = self._vs.search_memories(query, n_results=top_k, user_id=user_id)

        facts: List[MemoryFact] = []
        for r in results:
            fact_id = r["id"]
            row = self._db.execute(
                "SELECT * FROM memory_facts WHERE id = ?", (fact_id,)
            ).fetchone()
            if row:
                fact = self._row_to_fact(row)
                fact.similarity = r.get("similarity", 0.0)
                facts.append(fact)

        # 访问时自动微量强化：每次被检索到 weight += 0.01
        if facts:
            self._auto_reinforce([f.id for f in facts], amount=0.01)

        return facts

    def get_stats(self, user_id: str = "default") -> MemoryStats:
        """获取记忆统计.

        Returns:
            MemoryStats 对象.
        """
        total = self._db.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE user_id = ?", (user_id,)
        ).fetchone()[0]

        # by_layer
        layer_rows = self._db.execute(
            "SELECT layer, COUNT(*) as cnt FROM memory_facts WHERE user_id = ? GROUP BY layer",
            (user_id,),
        ).fetchall()
        by_layer: Dict[str, int] = {r["layer"]: r["cnt"] for r in layer_rows}

        # by_type
        type_rows = self._db.execute(
            "SELECT type, COUNT(*) as cnt FROM memory_facts WHERE user_id = ? GROUP BY type",
            (user_id,),
        ).fetchall()
        by_type: Dict[str, int] = {r["type"]: r["cnt"] for r in type_rows}

        # 近似向量存储字节数: dim * count * 4 bytes/float32
        total_vector_bytes = total * self._embedding.dim * 4

        # ── 容量字段 ──
        archive_count = self._db.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE layer = 'archive'"
        ).fetchone()[0]
        limit = self._get_capacity_limit()
        storage_est = _estimate_storage(self._db)

        return MemoryStats(
            total_facts=total,
            by_layer=by_layer,
            by_type=by_type,
            last_extraction_at=self._last_extraction_at,
            total_vector_bytes=total_vector_bytes,
            archive_count=archive_count,
            capacity_limit=limit,
            storage_estimate_bytes=storage_est,
            usage_percent=round((total / limit * 100), 2) if limit > 0 else 0.0,
        )

    # ══════════════════════════════════════════════════
    # Capacity Management
    # ══════════════════════════════════════════════════

    _DEFAULT_CAPACITY_LIMIT = 10000

    def _get_capacity_limit(self) -> int:
        row = self._db.execute(
            "SELECT value_json FROM persona_attributes WHERE key = 'memory_capacity_limit'"
        ).fetchone()
        if row:
            try:
                return int(json.loads(row["value_json"]))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        return self._DEFAULT_CAPACITY_LIMIT

    def _set_capacity_limit_db(self, limit: int) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO persona_attributes (key, value_json, updated_at) VALUES ('memory_capacity_limit', ?, ?)",
            (json.dumps(limit), _utcnow_iso()),
        )
        self._db.commit()

    def get_capacity_info(self) -> MemoryStats:
        stats = self.get_stats()
        row = self._db.execute(
            "SELECT COALESCE(SUM(CASE WHEN tags_json LIKE '%auto_archived_by_age%' THEN 1 ELSE 0 END), 0), "
            "COALESCE(SUM(CASE WHEN tags_json LIKE '%auto_archived_by_importance%' THEN 1 ELSE 0 END), 0) "
            "FROM memory_facts WHERE layer = 'archive'"
        ).fetchone()
        stats.archived_by_age_count = row[0] if row else 0
        stats.archived_by_importance_count = row[1] if row else 0
        return stats

    def set_capacity_limit(self, limit: int) -> int:
        if limit < 100:
            raise ValueError("Capacity limit must be at least 100")
        self._set_capacity_limit_db(limit)
        return limit

    def cleanup_by_age(self, days: int, dry_run: bool = False) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = self._db.execute(
            "SELECT id FROM memory_facts WHERE layer IN ('transient', 'working') AND created_at < ? ORDER BY importance ASC",
            (cutoff,),
        ).fetchall()
        if dry_run:
            return len(rows)
        count = 0
        for r in rows:
            self._archive_fact(r["id"], reason="auto_archived_by_age")
            count += 1
        if count:
            self._db.commit()
        return count

    def cleanup_by_importance(self, threshold: float, dry_run: bool = False) -> int:
        rows = self._db.execute(
            "SELECT id FROM memory_facts WHERE layer IN ('transient', 'working') AND importance <= ? ORDER BY importance ASC",
            (threshold,),
        ).fetchall()
        if dry_run:
            return len(rows)
        count = 0
        for r in rows:
            self._archive_fact(r["id"], reason="auto_archived_by_importance")
            count += 1
        if count:
            self._db.commit()
        return count

    def auto_archive_if_over_limit(self) -> int:
        limit = self._get_capacity_limit()
        total_active = self._db.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE layer != 'archive'"
        ).fetchone()[0]
        if total_active <= limit:
            return 0
        max_archive = max(int(total_active * 0.1), 1)
        archived = 0
        if archived < max_archive:
            rows = self._db.execute(
                "SELECT id FROM memory_facts WHERE layer = 'transient' AND importance <= 0.15 ORDER BY importance ASC LIMIT ?",
                (max_archive - archived,),
            ).fetchall()
            for r in rows:
                self._archive_fact(r["id"], reason="auto_archived_by_importance")
                archived += 1
        if archived < max_archive:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
            rows = self._db.execute(
                "SELECT id FROM memory_facts WHERE layer IN ('transient', 'working') AND created_at < ? ORDER BY importance ASC LIMIT ?",
                (cutoff, max_archive - archived),
            ).fetchall()
            for r in rows:
                self._archive_fact(r["id"], reason="auto_archived_by_age")
                archived += 1
        if archived > 0:
            self._db.commit()
        return archived

    def _archive_fact(self, fact_id: str, reason: str = "") -> None:
        self._db.execute(
            "UPDATE memory_facts SET layer = 'archive', tags_json = json_insert(COALESCE(tags_json, '[]'), '$[#]', ?), updated_at = ? WHERE id = ?",
            (reason, _utcnow_iso(), fact_id),
        )

    # ══════════════════════════════════════════════════
    # get_snapshot + format_snapshot
    # ══════════════════════════════════════════════════

    def get_snapshot(
        self,
        session_id: str,
        current_message: str,
        user_id: str = "default",
    ) -> MemorySnapshot:
        """获取当前会话的完整记忆快照（对齐设计文档第369-375行、872-902行）.

        流程：
        1. 对 current_message 生成 embedding
        2. Chroma 检索 top-20（where layer in [core, working]）
        3. 核心记忆（layer=core）：全量从 SQLite 获取
        4. 工作记忆（layer=working）：cosine > 0.35 过滤
        5. 瞬态记忆：从 SQLite 获取 session_id 对应的会话内新增记忆

        Args:
            session_id: 当前会话 ID
            current_message: 当前用户消息文本

        Returns:
            MemorySnapshot 对象.
        """
        from uuid import uuid4

        snapshot_id = str(uuid4())
        now = _utcnow_iso()

        # 1-2. Chroma 向量检索 top-20（core + working + user_id 过滤）
        where_filter = {"layer": {"$in": ["core", "working"]}}
        chroma_results = self._vs.search_memories(
            current_message,
            n_results=20,
            where=where_filter,
            user_id=user_id,
        )

        # 分离 core / working 结果
        working_facts: List[MemoryFact] = []
        for r in chroma_results:
            fact_id = r["id"]
            meta = r.get("metadata", {})
            fact_layer = meta.get("layer", "working")
            similarity = r.get("similarity", 0.0)

            if fact_layer == "working" and similarity <= 0.35:
                # 工作记忆：cosine > 0.35 过滤
                continue

            # 从 SQLite 获取完整信息
            row = self._db.execute(
                "SELECT * FROM memory_facts WHERE id = ?", (fact_id,)
            ).fetchone()
            if row:
                fact = self._row_to_fact(row)
                fact.embedding = None  # 不在快照中返回向量
                fact.similarity = similarity
                if fact_layer == "working":
                    working_facts.append(fact)

        # 3. 核心记忆（layer=core）：全量从 SQLite 获取（该用户）
        core_rows = self._db.execute(
            "SELECT * FROM memory_facts WHERE layer = 'core' AND user_id = ? ORDER BY importance DESC",
            (user_id,),
        ).fetchall()
        core_facts = [self._row_to_fact(row) for row in core_rows]
        for f in core_facts:
            f.embedding = None

        # 4. 瞬态记忆：从 SQLite 获取 session_id 对应的会话内新增记忆
        transient_rows = self._db.execute(
            "SELECT * FROM memory_facts WHERE source_session_id = ? ORDER BY created_at DESC",
            (session_id,),
        ).fetchall()
        transient_facts = [self._row_to_fact(row) for row in transient_rows]
        for f in transient_facts:
            f.embedding = None

        # 记录快照到 SQLite（用于调试）
        fact_ids = [
            f.id for f in core_facts + working_facts + transient_facts
        ]
        try:
            self._db.execute(
                "INSERT INTO memory_snapshots (id, session_id, fact_ids_json, generated_at) "
                "VALUES (?, ?, ?, ?)",
                (snapshot_id, session_id, json.dumps(fact_ids, ensure_ascii=False), now),
            )
            self._db.commit()
        except Exception as e:
            logger.warning(f"Failed to persist snapshot: {e}")

        # 访问时自动微量强化：被纳入快照的 working + core 记忆 weight += 0.01
        reinforced_ids = [f.id for f in working_facts] + [f.id for f in core_facts]
        if reinforced_ids:
            self._auto_reinforce(reinforced_ids, amount=0.01)

        return MemorySnapshot(
            core_facts=core_facts,
            working_facts=working_facts,
            transient_facts=transient_facts,
            generated_at=now,
            snapshot_id=snapshot_id,
        )

    @staticmethod
    def format_snapshot(snapshot: MemorySnapshot) -> str:
        """将 MemorySnapshot 格式化为自然语言中文（对齐设计文档第904-909行）.

        按 type 分组，importance 降序排列。

        Args:
            snapshot: MemorySnapshot 对象.

        Returns:
            格式化的中文自然语言字符串.
        """
        # type 中文标签映射
        TYPE_LABELS: Dict[str, str] = {
            "preference": "偏好",
            "fact": "事实",
            "procedure": "流程",
            "relationship": "关系",
        }

        lines: List[str] = []

        # 合并所有事实并去重（按 id）
        seen: set = set()
        all_facts: List[MemoryFact] = []
        for fact in snapshot.core_facts + snapshot.working_facts + snapshot.transient_facts:
            if fact.id not in seen:
                seen.add(fact.id)
                all_facts.append(fact)

        # 按 type 分组
        by_type: Dict[str, List[MemoryFact]] = {}
        for fact in all_facts:
            by_type.setdefault(fact.type, []).append(fact)

        # 每组内按 importance 降序排列
        for facts in by_type.values():
            facts.sort(key=lambda f: f.importance, reverse=True)

        # 按 type 优先级排序：preference > fact > procedure > relationship
        type_order = ["preference", "fact", "procedure", "relationship"]
        sorted_types = [t for t in type_order if t in by_type]

        if not sorted_types:
            return "## 关于你的记忆\n（暂无记忆）\n"

        lines.append("## 关于你的记忆")

        for t in sorted_types:
            label = TYPE_LABELS.get(t, t)
            for fact in by_type[t]:
                lines.append(f"- ({label}) {fact.content}")

        return "\n".join(lines) + "\n"

    # ══════════════════════════════════════════════════
    # extract_and_store
    # ══════════════════════════════════════════════════

    def extract_and_store(
        self,
        session_id: str,
        user_message: str,
        assistant_response: str,
        user_id: str = "default",
    ) -> List[MemoryFact]:
        """从对话中提取事实并存储（对齐设计文档第916-948行）.

        流程：
        1. 调用 FactExtractor 提取事实
        2. 对每条事实：Chroma 查 top-1 → cosine > 0.75 则强化，否则新增
        3. 写入 SQLite + Chroma
        4. 返回新增/更新的 MemoryFact 列表

        Args:
            session_id: 会话 ID
            user_message: 用户消息文本
            assistant_response: 助手回复文本

        Returns:
            新增或更新的 MemoryFact 列表.
            异常不抛到调用方（内部捕获并记录日志）.
        """
        facts: List[MemoryFact] = []

        try:
            # 1. 调用 FactExtractor
            extractor = self._extractor or get_extractor()
            messages = [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_response},
            ]
            extracted = extractor.extract(messages)

            if not extracted:
                return facts

            now = _utcnow_iso()

            # 2. 逐条处理
            for item in extracted:
                try:
                    content = item["content"]
                    item_type = _EXTRACTOR_TYPE_MAP.get(
                        item.get("type", "other"), "fact"
                    )
                    importance = float(item.get("importance", 0.5))
                    privacy = _PRIVACY_MAP.get(
                        item.get("privacy_level", "internal"), "private"
                    )

                    # 根据 importance 分配 layer
                    if importance >= 0.8:
                        layer = "core"
                    elif importance >= 0.5:
                        layer = "working"
                    else:
                        layer = "transient"

                    # 3. Chroma 去重查询 (cosine similarity, 使用 doc embedding 确保同空间比较)
                    search_results = self._vs.search_memories_doc_embedding(content, n_results=1, user_id=user_id)

                    if (
                        search_results
                        and search_results[0].get("similarity", 0.0) > 0.75
                    ):
                        # 相似 → 合并更新已有记忆
                        existing_id = search_results[0]["id"]
                        try:
                            existing = self._get_fact_by_id(existing_id)
                            if existing:
                                fact = self._merge_and_update(
                                    existing=existing,
                                    new_content=content,
                                    new_importance=importance,
                                    new_layer=layer,
                                    new_privacy=privacy,
                                    new_type=item_type,
                                )
                            else:
                                raise ValueError("Fact not found")
                            facts.append(fact)
                        except ValueError:
                            # 可能已被删除，当作新增
                            fact = self._add_extracted_fact(
                                fact_id=str(uuid.uuid4()),
                                content=content,
                                type=item_type,
                                importance=importance,
                                layer=layer,
                                privacy_level=privacy,
                                session_id=session_id,
                                now=now,
                                user_id=user_id,
                            )
                            facts.append(fact)
                    else:
                        # 不相似 → 新增
                        fact = self._add_extracted_fact(
                            fact_id=str(uuid.uuid4()),
                            content=content,
                            type=item_type,
                            importance=importance,
                            layer=layer,
                            privacy_level=privacy,
                            session_id=session_id,
                            now=now,
                            user_id=user_id,
                        )
                        facts.append(fact)

                except Exception as e:
                    logger.warning(
                        f"Failed to process extracted fact '{item.get('content', '')[:50]}': {e}"
                    )
                    continue

            self._last_extraction_at = now

            # ── 容量检查：超过上限则自动归档 ──
            self.auto_archive_if_over_limit()

        except Exception as e:
            logger.error(f"extract_and_store failed: {e}", exc_info=True)

        return facts

    # ══════════════════════════════════════════════════
    # Internal Helpers
    # ══════════════════════════════════════════════════

    def _get_fact_by_id(self, fact_id: str) -> Optional[MemoryFact]:
        """按 ID 查询单条事实."""
        row = self._db.execute(
            "SELECT * FROM memory_facts WHERE id = ?", (fact_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_fact(row)

    @staticmethod
    def _row_to_fact(row) -> MemoryFact:
        """将 SQLite Row 转换为 MemoryFact."""
        tags: List[str] = []
        if row["tags_json"]:
            try:
                tags = json.loads(row["tags_json"])
            except (json.JSONDecodeError, TypeError):
                pass

        return MemoryFact(
            id=row["id"],
            type=row["type"],
            content=row["content"],
            importance=float(row["importance"]),
            weight=float(row["weight"]),
            layer=row["layer"],
            source_session_id=row["source_session_id"],
            source_interaction_id=row["source_interaction_id"],
            privacy_level=row["privacy_level"],
            tags=tags,
            user_id=row["user_id"] if "user_id" in row.keys() else "default",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_accessed_at=row["last_accessed_at"],
        )

    def _add_extracted_fact(
        self,
        fact_id: str,
        content: str,
        type: str,
        importance: float,
        layer: str,
        privacy_level: str,
        session_id: str,
        now: str,
        user_id: str = "default",
    ) -> MemoryFact:
        """内部方法：将从 LLM 提取的事实写入存储."""
        # Chroma
        chroma_meta = {
            "type": type,
            "importance": importance,
            "layer": layer,
            "privacy_level": privacy_level,
            "user_id": user_id,
        }
        self._vs.add_memory(fact_id, content, metadata=chroma_meta)

        # SQLite
        self._db.execute(
            """INSERT INTO memory_facts
               (id, type, content, chroma_id, importance, weight, layer,
                source_session_id, privacy_level, tags_json, user_id,
                created_at, updated_at, last_accessed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fact_id,
                type,
                content,
                fact_id,
                importance,
                1.0,
                layer,
                session_id,
                privacy_level,
                json.dumps([], ensure_ascii=False),
                user_id,
                now,
                now,
                now,
            ),
        )
        self._db.commit()

        return MemoryFact(
            id=fact_id,
            type=type,
            content=content,
            importance=importance,
            weight=1.0,
            layer=layer,
            source_session_id=session_id,
            privacy_level=privacy_level,
            tags=[],
            created_at=now,
            updated_at=now,
            last_accessed_at=now,
        )

    # ══════════════════════════════════════════════════
    # T-01-07: 去重 / 合并 / 冲突检测 / 自动强化
    # ══════════════════════════════════════════════════

    def _check_duplicate(self, content: str) -> Optional[Dict[str, Any]]:
        """检查 content 是否与已有记忆高度相似（cosine > 0.85）.

        Args:
            content: 待添加的内容文本.

        Returns:
            如存在重复，返回 {"fact_id": str, "content": str, "similarity": float}
            否则返回 None.
        """
        search_results = self._vs.search_memories_doc_embedding(content, n_results=1)
        if search_results and search_results[0].get("similarity", 0.0) > 0.85:
            existing_id = search_results[0]["id"]
            existing = self._get_fact_by_id(existing_id)
            if existing:
                return {
                    "fact_id": existing.id,
                    "content": existing.content,
                    "similarity": search_results[0]["similarity"],
                }
        return None

    def _merge_and_update(
        self,
        existing: MemoryFact,
        new_content: str,
        new_importance: float,
        new_layer: str,
        new_privacy: str,
        new_type: str,
    ) -> MemoryFact:
        """合并 extracted fact 与已有记忆.

        合并策略：
        - content: 取较长的
        - importance: 取 max
        - tags: 合并去重
        - weight: 微量强化 +0.05
        - layer: 保留层级较高的 (core > working > transient)

        Args:
            existing: 已有 MemoryFact
            new_content: 新提取的内容
            new_importance: 新提取的重要性
            new_layer: 新提取的层级
            new_privacy: 新提取的隐私级别
            new_type: 新提取的类型

        Returns:
            合并更新后的 MemoryFact.
        """
        LAYER_ORDER = {"core": 3, "working": 2, "transient": 1}

        # content: 取较长的
        merged_content = (
            new_content if len(new_content) > len(existing.content) else existing.content
        )

        # importance: 取 max
        merged_importance = max(existing.importance, new_importance)

        # layer: 保留层级较高的
        merged_layer = (
            new_layer
            if LAYER_ORDER.get(new_layer, 0) > LAYER_ORDER.get(existing.layer, 0)
            else existing.layer
        )

        # tags: 合并去重
        existing_tags = existing.tags or []
        merged_tags = list(set(existing_tags))

        # privacy: 保留更严格的 (sensitive > private > public)
        PRIVACY_ORDER = {"sensitive": 3, "private": 2, "public": 1}
        merged_privacy = (
            new_privacy
            if PRIVACY_ORDER.get(new_privacy, 0) > PRIVACY_ORDER.get(existing.privacy_level, 0)
            else existing.privacy_level
        )

        # 更新
        now = _utcnow_iso()
        new_weight = existing.weight + 0.05

        # 如果 content 变化，需要更新 Chroma
        if merged_content != existing.content:
            self._vs.delete_memory(existing.id)
            self._vs.add_memory(
                existing.id,
                merged_content,
                metadata={
                    "type": new_type,
                    "importance": merged_importance,
                    "layer": merged_layer,
                    "privacy_level": merged_privacy,
                },
            )

        self._db.execute(
            """UPDATE memory_facts
               SET content = ?, type = ?, importance = ?, weight = ?,
                   layer = ?, privacy_level = ?, tags_json = ?,
                   updated_at = ?, last_accessed_at = ?
               WHERE id = ?""",
            (
                merged_content,
                new_type,
                merged_importance,
                new_weight,
                merged_layer,
                merged_privacy,
                json.dumps(merged_tags, ensure_ascii=False),
                now,
                now,
                existing.id,
            ),
        )
        self._db.commit()

        updated = self._get_fact_by_id(existing.id)
        return updated

    def _auto_reinforce(self, fact_ids: List[str], amount: float = 0.01) -> None:
        """批量微量强化：对检索到的记忆 weight += amount.

        不触发事件（避免搜索时的事件风暴）.

        Args:
            fact_ids: 要强化的 fact ID 列表
            amount: 强化幅度（默认 0.01）
        """
        if not fact_ids:
            return

        now = _utcnow_iso()
        placeholders = ",".join(["?"] * len(fact_ids))

        try:
            self._db.execute(
                f"""UPDATE memory_facts
                    SET weight = weight + ?,
                        last_accessed_at = ?
                    WHERE id IN ({placeholders})""",
                [amount, now] + fact_ids,
            )
            self._db.commit()
        except Exception as e:
            logger.warning(f"Auto-reinforce failed: {e}")

    # ══════════════════════════════════════════════════
    # detect_contradiction
    # ══════════════════════════════════════════════════

    # 矛盾检测关键词：否定词 + 反义对
    _NEGATION_WORDS = {
        "不", "没有", "没", "非", "无", "否", "别", "勿", "未",
        "not", "no", "never", "don't", "doesn't", "isn't", "aren't",
        "wasn't", "weren't", "won't", "can't", "cannot",
    }

    _OPPOSITE_PAIRS = [
        ({"喜欢", "爱", "偏好", "like", "love", "enjoy", "prefer"},
         {"讨厌", "恨", "厌恶", "不喜欢", "hate", "dislike", "detest"}),
        ({"可以", "能", "会", "can", "able", "will"},
         {"不能", "不会", "无法", "cannot", "unable", "won't"}),
        ({"是", "有", "is", "are", "has", "have"},
         {"不是", "没有", "isn't", "aren't", "hasn't", "haven't"}),
        ({"好", "good", "great", "excellent"},
         {"差", "坏", "糟糕", "bad", "poor", "terrible"}),
        ({"快", "fast", "quick", "rapid"},
         {"慢", "slow", "sluggish"}),
        ({"多", "many", "much", "a lot"},
         {"少", "few", "little", "rarely"}),
    ]

    def detect_contradiction(self, fact_id: str) -> List[MemoryFact]:
        """检测与指定事实矛盾的已有记忆.

        MVP 级别：使用关键词 + embedding 对比检测。
        同一 type+layer 下语义相似但包含相反关键词 → 标记为冲突。

        Args:
            fact_id: 要检测冲突的事实 ID.

        Returns:
            疑似冲突的已有 MemoryFact 列表.

        Raises:
            ValueError: fact_id 不存在.
        """
        target = self._get_fact_by_id(fact_id)
        if target is None:
            raise ValueError(f"Fact not found: {fact_id}")

        # 1. 获取同一 type+layer 的其他事实
        rows = self._db.execute(
            """SELECT * FROM memory_facts
               WHERE type = ? AND layer = ? AND id != ?
               ORDER BY updated_at DESC""",
            (target.type, target.layer, fact_id),
        ).fetchall()

        if not rows:
            return []

        candidates = [self._row_to_fact(row) for row in rows]

        # 2. 用 Chroma 检索与 target 语义最相近的 candidates (doc embedding)
        search_results = self._vs.search_memories_doc_embedding(
            target.content, n_results=min(len(candidates), 10)
        )

        # 3. 对高相似度 (>0.65) 的候选进行关键词矛盾检测
        contradictions: List[MemoryFact] = []
        seen_ids: set = set()

        for r in search_results:
            candidate_id = r["id"]
            similarity = r.get("similarity", 0.0)

            if candidate_id == fact_id or candidate_id in seen_ids:
                continue
            if similarity < 0.65:
                continue

            candidate = self._get_fact_by_id(candidate_id)
            if candidate is None:
                continue

            # 关键词矛盾检测
            if self._has_opposite_keywords(target.content, candidate.content):
                seen_ids.add(candidate_id)
                candidate.similarity = similarity
                contradictions.append(candidate)

        return contradictions

    def _has_opposite_keywords(self, text_a: str, text_b: str) -> bool:
        """检测两段文本是否包含矛盾关键词.

        策略：
        1. 如果一方含否定词而另一方不含 → 可能矛盾
        2. 如果两方分别包含反义对中的正/负项 → 矛盾

        Args:
            text_a: 文本 A
            text_b: 文本 B

        Returns:
            True 如果检测到矛盾关键词.
        """
        a_lower = text_a.lower()
        b_lower = text_b.lower()

        # 检查1：否定词不对称（一方含否定词，另一方不含）
        a_has_neg = any(neg in a_lower for neg in self._NEGATION_WORDS)
        b_has_neg = any(neg in b_lower for neg in self._NEGATION_WORDS)
        if a_has_neg != b_has_neg:
            return True

        # 检查2：反义对检测
        for pos_set, neg_set in self._OPPOSITE_PAIRS:
            a_pos = any(w in a_lower for w in pos_set)
            a_neg = any(w in a_lower for w in neg_set)
            b_pos = any(w in b_lower for w in pos_set)
            b_neg = any(w in b_lower for w in neg_set)

            # 一方为正，另一方为负 → 矛盾
            if (a_pos and b_neg) or (a_neg and b_pos):
                return True

        return False


# ══════════════════════════════════════════════════
# 便捷函数
# ══════════════════════════════════════════════════

_engine: Optional[EvoMemoryEngine] = None


def get_engine(
    db_path: Optional[str] = None,
    chroma_dir: Optional[str] = None,
) -> EvoMemoryEngine:
    """获取全局 EvoMemoryEngine 单例（延迟初始化）."""
    global _engine
    if _engine is None:
        _engine = EvoMemoryEngine(db_path=db_path, chroma_dir=chroma_dir)
    return _engine
