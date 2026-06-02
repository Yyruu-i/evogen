"""Pytest 配置文件."""

import sys
from pathlib import Path

# 将项目根目录加入 sys.path
sys.path.insert(0, str(Path(__file__).parent))

import pytest


def pytest_configure(config):
    """注册自定义 markers 并安装 sentence_transformers mock."""
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")

    # 如果 sentence_transformers 不可用，提前注入 mock
    _install_sentence_transformers_mock_if_needed()


def _install_sentence_transformers_mock_if_needed():
    """如果 sentence_transformers 不可用，注入 mock（在导入其他模块之前）."""
    if "sentence_transformers" in sys.modules:
        return
    try:
        import sentence_transformers  # noqa
        return
    except ImportError:
        pass

    import types
    import hashlib
    import numpy as np

    DIM = 1024

    class MockSentenceTransformer:
        def __init__(self, model_name_or_path, device="cpu", **kwargs):
            self.model_name = model_name_or_path
            self.device = device

        def encode(self, sentences, normalize_embeddings=True, show_progress_bar=False, batch_size=32):
            single = isinstance(sentences, str)
            if single:
                sentences = [sentences]
            results = []
            for s in sentences:
                h = hashlib.sha256(s.encode()).digest()
                seed = int.from_bytes(h[:4], "big")
                rng = np.random.RandomState(seed)
                vec = rng.randn(DIM).astype(np.float32)
                if normalize_embeddings:
                    norm = np.linalg.norm(vec)
                    if norm > 1e-8:
                        vec = vec / norm
                results.append(vec)
            if single:
                return results[0]
            return results

    mock_st = types.ModuleType("sentence_transformers")
    mock_st.SentenceTransformer = MockSentenceTransformer
    sys.modules["sentence_transformers"] = mock_st


@pytest.fixture(scope="session")
def project_root():
    """返回项目根目录路径."""
    return Path(__file__).parent


@pytest.fixture(scope="session")
def test_data_dir(tmp_path_factory):
    """创建临时测试数据目录."""
    return tmp_path_factory.mktemp("evogen_test_data")


@pytest.fixture(scope="function")
def temp_db_path(tmp_path):
    """为每个测试函数创建临时数据库路径."""
    db_path = tmp_path / "test_evogen.db"
    return str(db_path)
