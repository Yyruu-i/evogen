"""SQLite 数据库连接管理 - WAL模式 + 外键约束 + 线程安全."""

import sqlite3
import threading
from pathlib import Path
from typing import Optional

from backend.config import config


class ConnectionManager:
    """线程安全的 SQLite 连接管理器.

    特性：
    - 每线程一个连接（thread-local）
    - WAL 模式（读写并发）
    - 外键约束强制启用
    - 连接复用，自动关闭
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or config.db_path
        self._local = threading.local()

        # 确保父目录存在
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    def _get_conn(self) -> sqlite3.Connection:
        """获取当前线程的连接，如不存在则创建."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                self._db_path,
                timeout=config.db_timeout,
                check_same_thread=False,  # 允许跨线程使用，但我们用 thread-local
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
        return self._local.conn

    @property
    def conn(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接."""
        return self._get_conn()

    def close(self):
        """关闭当前线程的连接."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None

    def execute(self, sql: str, params=None):
        """执行 SQL 语句."""
        return self.conn.execute(sql, params or ())

    def executemany(self, sql: str, params_list):
        """批量执行 SQL 语句."""
        return self.conn.executemany(sql, params_list)

    def commit(self):
        """提交事务."""
        self.conn.commit()

    def rollback(self):
        """回滚事务."""
        self.conn.rollback()

    def table_exists(self, table_name: str) -> bool:
        """检查表是否存在."""
        cursor = self.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return cursor.fetchone() is not None


# 全局连接管理器
_db_manager: Optional[ConnectionManager] = None
_lock = threading.Lock()


def get_db(db_path: Optional[str] = None) -> ConnectionManager:
    """获取全局数据库连接管理器（线程安全单例）."""
    global _db_manager
    if _db_manager is None:
        with _lock:
            if _db_manager is None:
                _db_manager = ConnectionManager(db_path)
    return _db_manager


def init_db(db_path: Optional[str] = None):
    """初始化数据库：运行迁移并验证."""
    from backend.db.migrations import run_migrations

    mgr = get_db(db_path)
    run_migrations(mgr)
    return mgr
