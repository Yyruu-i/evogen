"""Chroma 向量存储 - 持久化语义检索.

管理两个 Collection：
  - evo_memory_facts: 用户记忆事实
  - evo_experience_scenes: 经验场景记录
"""

import logging
from typing import Any, Optional

import chromadb
from chromadb.config import Settings

from backend.config import config

logger = logging.getLogger(__name__)


class VectorStore:
    """Chroma 向量存储管理器.

    特性：
    - PersistentClient 持久化存储
    - 两个 Collection: memory_facts + experience_scenes
    - Cosine 距离度量
    - 元数据自动管理
    """

    MEMORY_COLLECTION = config.chroma_collection_memory
    EXPERIENCE_COLLECTION = config.chroma_collection_experience

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        embedding_device: str = "cpu",
    ):
        """初始化 Chroma 向量存储.

        Args:
            persist_dir: Chroma 持久化目录，默认 ~/.evogen/data/chroma/
            embedding_device: embedding 设备
        """
        self._persist_dir = persist_dir or config.chroma_persist_dir
        self._device = embedding_device
        self._client: Optional[chromadb.PersistentClient] = None
        self._memory_collection = None
        self._experience_collection = None
        self._embedding_provider = None
        self._initialized = False

    def _ensure_initialized(self):
        """延迟初始化 Chroma 客户端和 Collection."""
        if self._initialized:
            return

        logger.info(f"Initializing Chroma: persist_dir={self._persist_dir}")

        # 初始化 Chroma PersistentClient
        self._client = chromadb.PersistentClient(
            path=self._persist_dir,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )

        # 获取或创建 Collection
        self._memory_collection = self._client.get_or_create_collection(
            name=self.MEMORY_COLLECTION,
            metadata={
                "description": "EvoGen 用户记忆事实",
                "hnsw:space": "cosine",
                "hnsw:construction_ef": 100,
                "hnsw:M": 16,
            },
        )

        self._experience_collection = self._client.get_or_create_collection(
            name=self.EXPERIENCE_COLLECTION,
            metadata={
                "description": "EvoGen 经验场景记录",
                "hnsw:space": "cosine",
                "hnsw:construction_ef": 100,
                "hnsw:M": 16,
            },
        )

        # 获取 embedding provider
        from backend.memory.embedding import get_embedding_provider
        self._embedding_provider = get_embedding_provider(device=self._device)

        self._initialized = True
        logger.info(
            f"Chroma initialized: "
            f"memory={self._memory_collection.count()}, "
            f"experience={self._experience_collection.count()}"
        )

    @property
    def client(self) -> chromadb.PersistentClient:
        self._ensure_initialized()
        return self._client

    @property
    def memory_collection(self):
        self._ensure_initialized()
        return self._memory_collection

    @property
    def experience_collection(self):
        self._ensure_initialized()
        return self._experience_collection

    # ══════════════════════════════════════════════════
    # Memory Facts CRUD
    # ══════════════════════════════════════════════════

    def add_memory(
        self,
        fact_id: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """向 evo_memory_facts 添加一条记忆.

        Args:
            fact_id: 事实 ID (对应 SQLite memory_facts.id)
            content: 记忆文本内容
            metadata: 附加元数据
        """
        self._ensure_initialized()
        embedding = self._embedding_provider.embed(content)

        meta = metadata or {}
        meta["fact_id"] = fact_id
        meta["content"] = content

        self._memory_collection.add(
            ids=[fact_id],
            embeddings=[embedding],
            metadatas=[meta],
            documents=[content],
        )
        logger.debug(f"Added memory fact: {fact_id}")

    def search_memories(
        self,
        query: str,
        n_results: int = 5,
        where: Optional[dict] = None,
        user_id: Optional[str] = None,
    ) -> list[dict]:
        """语义检索记忆.

        Args:
            query: 查询文本
            n_results: 返回结果数
            where: Chroma metadata 过滤条件
            user_id: 用户 ID 过滤（加入 where 条件）

        Returns:
            搜索结果列表，每项含 id, content, metadata, distance
        """
        self._ensure_initialized()
        query_embedding = self._embedding_provider.embed_query(query)

        # 合并 user_id 过滤（Chroma 多条件需用 $and）
        final_where = dict(where or {})
        if user_id:
            if final_where:
                final_where = {"$and": [{"user_id": user_id}, final_where]}
            else:
                final_where = {"user_id": user_id}

        results = self._memory_collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=final_where if final_where else None,
            include=["documents", "metadatas", "distances"],
        )

        # 转换成友好格式
        formatted = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                formatted.append({
                    "id": doc_id,
                    "content": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0.0,
                    "similarity": 1.0 - (results["distances"][0][i] if results["distances"] else 0.0),
                })

        return formatted

    def search_memories_doc_embedding(
        self,
        text: str,
        n_results: int = 5,
        where: Optional[dict] = None,
        user_id: Optional[str] = None,
    ) -> list[dict]:
        """用文档嵌入（无查询前缀）检索记忆，用于去重/合并场景.

        BGE-M3 的 embed_query 会添加前缀，导致查询与文档在不同子空间。
        此方法使用 embed()（与存储时一致），适合余弦相似度去重。

        Args:
            text: 文本（不添加查询前缀）
            n_results: 返回结果数
            where: Chroma metadata 过滤条件
            user_id: 用户 ID 过滤

        Returns:
            搜索结果列表，每项含 id, content, metadata, distance
        """
        self._ensure_initialized()
        doc_embedding = self._embedding_provider.embed(text)

        # 合并 user_id 过滤（Chroma 多条件需用 $and）
        final_where = dict(where or {})
        if user_id:
            if final_where:
                final_where = {"$and": [{"user_id": user_id}, final_where]}
            else:
                final_where = {"user_id": user_id}

        results = self._memory_collection.query(
            query_embeddings=[doc_embedding],
            n_results=n_results,
            where=final_where if final_where else None,
            include=["documents", "metadatas", "distances"],
        )

        formatted = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                formatted.append({
                    "id": doc_id,
                    "content": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0.0,
                    "similarity": 1.0 - (results["distances"][0][i] if results["distances"] else 0.0),
                })

        return formatted

    def delete_memory(self, fact_id: str) -> None:
        """删除一条记忆."""
        self._ensure_initialized()
        self._memory_collection.delete(ids=[fact_id])

    def memory_count(self) -> int:
        """返回记忆总数."""
        self._ensure_initialized()
        return self._memory_collection.count()

    # ══════════════════════════════════════════════════
    # Experience Scenes CRUD
    # ══════════════════════════════════════════════════

    def add_experience(
        self,
        trajectory_id: str,
        summary: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """向 evo_experience_scenes 添加一条经验.

        Args:
            trajectory_id: 轨迹 ID
            summary: 场景摘要文本
            metadata: 附加元数据
        """
        self._ensure_initialized()
        embedding = self._embedding_provider.embed(summary)

        meta = metadata or {}
        meta["trajectory_id"] = trajectory_id
        meta["summary"] = summary

        self._experience_collection.add(
            ids=[trajectory_id],
            embeddings=[embedding],
            metadatas=[meta],
            documents=[summary],
        )
        logger.debug(f"Added experience: {trajectory_id}")

    def search_experiences(
        self,
        query: str,
        n_results: int = 5,
    ) -> list[dict]:
        """语义检索经验."""
        self._ensure_initialized()
        query_embedding = self._embedding_provider.embed_query(query)

        results = self._experience_collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

        formatted = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                formatted.append({
                    "id": doc_id,
                    "content": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0.0,
                    "similarity": 1.0 - (results["distances"][0][i] if results["distances"] else 0.0),
                })

        return formatted

    def experience_count(self) -> int:
        """返回经验总数."""
        self._ensure_initialized()
        return self._experience_collection.count()

    # ══════════════════════════════════════════════════
    # 管理方法
    # ══════════════════════════════════════════════════

    def reset(self):
        """重置所有数据（仅开发/测试用）."""
        self._ensure_initialized()
        self._client.reset()
        self._initialized = False
        logger.warning("Chroma store reset!")


# 全局单例
_vector_store: Optional[VectorStore] = None


def get_vector_store(device: str = "cpu") -> VectorStore:
    """获取全局向量存储单例."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore(embedding_device=device)
    return _vector_store
