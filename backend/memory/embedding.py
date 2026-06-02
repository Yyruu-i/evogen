"""Embedding Provider - BGE-M3 抽象层.

提供统一的 embedding 接口，支持不同后端的切换。
"""

from abc import ABC, abstractmethod
from typing import List

import numpy as np


class EmbeddingProvider(ABC):
    """Embedding 抽象基类."""

    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """将单个文本编码为向量."""
        ...

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量编码文本为向量."""
        ...

    @abstractmethod
    def embed_query(self, query: str) -> List[float]:
        """编码查询文本（可用于不同的 prompt 前缀）."""
        ...

    @property
    @abstractmethod
    def dim(self) -> int:
        """向量维度."""
        ...


class BGEM3EmbeddingProvider(EmbeddingProvider):
    """BGE-M3 嵌入提供器.

    BAAI/bge-m3 是一个多语言（100+语言）、多功能（dense+sparse+colbert）嵌入模型。
    输出维度: 1024 (dense)
    """

    # Use local cache path (VPN required for first download only)
    MODEL_NAME = "BAAI/bge-m3"
    _LOCAL_PATH = "/root/.cache/huggingface/hub/models--BAAI--bge-m3/snapshots/5617a9f61b028005a4858fdac845db406aefb181"
    DIM = 1024
    QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

    def __init__(self, device: str = "cpu", normalize: bool = True):
        """初始化 BGE-M3 嵌入提供器.

        Args:
            device: 设备选择 ("cpu" 或 "cuda")
            normalize: 是否对向量做 L2 归一化（推荐 True，配合 cosine 距离）
        """
        self._device = device
        self._normalize = normalize
        self._model = None
        self._loaded = False

    def _ensure_loaded(self):
        """延迟加载模型."""
        if self._loaded:
            return
        from sentence_transformers import SentenceTransformer

        print(f"🔄 Loading BGE-M3 model: {self.MODEL_NAME} (device={self._device})")
        self._model = SentenceTransformer(
            self._LOCAL_PATH,  # use local cache, no network needed
            device=self._device,
            trust_remote_code=True,
        )
        # 验证输出维度
        test_vec = self._model.encode("test", normalize_embeddings=False)
        actual_dim = len(test_vec)
        if actual_dim != self.DIM:
            raise RuntimeError(
                f"BGE-M3 expected dim={self.DIM}, got dim={actual_dim}"
            )
        self._loaded = True
        print(f"✅ BGE-M3 loaded: dim={self.DIM}")

    @property
    def dim(self) -> int:
        return self.DIM

    def embed(self, text: str) -> List[float]:
        """编码单个文本."""
        self._ensure_loaded()
        vec = self._model.encode(
            text,
            normalize_embeddings=self._normalize,
            show_progress_bar=False,
        )
        return vec.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量编码文本."""
        self._ensure_loaded()
        vecs = self._model.encode(
            texts,
            normalize_embeddings=self._normalize,
            show_progress_bar=False,
            batch_size=32,
        )
        return vecs.tolist()

    def embed_query(self, query: str) -> List[float]:
        """编码查询文本，自动添加查询前缀."""
        self._ensure_loaded()
        prefixed = self.QUERY_PREFIX + query
        return self.embed(prefixed)


# ══════════════════════════════════════════════════
# 全局单例（延迟初始化）
# ══════════════════════════════════════════════════

_embedding_provider: BGEM3EmbeddingProvider | None = None


def get_embedding_provider(device: str = "cpu") -> BGEM3EmbeddingProvider:
    """获取全局 BGE-M3 嵌入提供器（延迟加载单例）."""
    global _embedding_provider
    if _embedding_provider is None:
        _embedding_provider = BGEM3EmbeddingProvider(device=device)
        _embedding_provider._ensure_loaded()
    return _embedding_provider


def embed_fn(text: str, device: str = "cpu") -> List[float]:
    """便捷函数：编码单个文本."""
    return get_embedding_provider(device).embed(text)


def embed_batch(texts: List[str], device: str = "cpu") -> List[List[float]]:
    """便捷函数：批量编码文本."""
    return get_embedding_provider(device).embed_batch(texts)


def embed_query(query: str, device: str = "cpu") -> List[float]:
    """便捷函数：编码查询文本."""
    return get_embedding_provider(device).embed_query(query)
