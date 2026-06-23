"""EvoGen 配置类 - 集中管理所有配置项."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EvoGenConfig:
    """EvoGen 全局配置，支持环境变量覆盖."""

    # ── 路径配置 ──
    evogen_home: str = field(default_factory=lambda: os.path.expanduser("~/.evogen"))
    data_dir: str = field(default_factory=lambda: os.path.join(
        os.path.expanduser("~/.evogen"), "data"
    ))

    # ── 数据库配置 ──
    db_path: str = field(default_factory=lambda: os.path.join(
        os.path.expanduser("~/.evogen"), "data", "evogen.db"
    ))
    db_wal_mode: bool = True
    db_foreign_keys: bool = True
    db_timeout: int = 30

    # ── Chroma 配置 ──
    chroma_persist_dir: str = field(default_factory=lambda: os.path.join(
        os.path.expanduser("~/.evogen"), "data", "chroma"
    ))
    chroma_collection_memory: str = "evo_memory_facts"
    chroma_collection_experience: str = "evo_experience_scenes"

    # ── Embedding 配置 ──
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    embedding_device: str = "cpu"

    # ── LLM 配置 ──
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "deepseek"))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "deepseek-chat"))
    llm_api_key: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    llm_base_url: str = field(default_factory=lambda: os.getenv(
        "LLM_BASE_URL", "https://api.deepseek.com"
    ))

    # ── Agent 配置 ──
    max_agent_rounds: int = field(default_factory=lambda: int(os.getenv("MAX_AGENT_ROUNDS", "90")))
    """Agent 最大执行轮次（工具调用 + 对话轮次总和），防止死循环。默认 90。"""

    # ── FastAPI 配置 ──
    api_host: str = "0.0.0.0"
    api_port: int = 8100
    api_reload: bool = False

    # ── 日志配置 ──
    log_level: str = "INFO"

    def __post_init__(self):
        """确保目录存在."""
        Path(self.evogen_home).mkdir(parents=True, exist_ok=True)
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        Path(self.chroma_persist_dir).mkdir(parents=True, exist_ok=True)

    @property
    def project_root(self) -> str:
        """返回项目根目录."""
        return str(Path(__file__).parent.parent)


# 全局单例
config = EvoGenConfig()
