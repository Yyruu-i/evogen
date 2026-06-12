"""幂等数据库迁移管理.

使用 migration_versions 表追踪已应用的迁移版本。
所有迁移操作通过 IF NOT EXISTS / OR IGNORE 保证幂等。
"""

import hashlib
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# 迁移版本表 DDL
MIGRATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS _migration_versions (
    version     TEXT PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now')),
    checksum    TEXT NOT NULL
);
"""

# 迁移名称 → SQL 文件映射
MIGRATIONS = {
    "v0.1.0_initial_schema": str(SCHEMA_PATH),
    "v0.1.1_sessions": str(Path(__file__).parent / "migration_v0.1.1_sessions.sql"),
    "v0.2.0_auth_isolation": str(Path(__file__).parent / "migration_v0.2.0_auth.sql"),
    "v0.2.1_artifacts": str(Path(__file__).parent / "migration_v0.2.1_artifacts.sql"),
}


def _compute_checksum(sql: str) -> str:
    """计算 SQL 内容的 SHA256 校验和."""
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _load_schema_sql() -> str:
    """加载 schema.sql 内容."""
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema file not found: {SCHEMA_PATH}")
    return SCHEMA_PATH.read_text(encoding="utf-8")


def _execute_statements_safe(db, sql_text: str) -> list[str]:
    """逐条执行 SQL，单条失败不阻断后续语句（用于 schema 演进时的安全回退）."""
    import sqlite3

    errors = []
    for stmt in sql_text.split(";"):
        # 去掉前导注释行后再判断是否为空
        stmt = "\n".join(
            line for line in stmt.split("\n")
            if line.strip() and not line.strip().startswith("--")
        ).strip()
        if not stmt:
            continue
        try:
            # 单条语句用 execute()，不会像 executescript 一样在错误时中断后续
            db.execute(stmt)
        except sqlite3.OperationalError as e:
            # IF NOT EXISTS 语句在旧表结构不匹配时可能失败（如索引引用已删除的列）
            errors.append(f"[skipped] {str(e)[:80]}: {stmt[:60]}...")
            continue
        except Exception:
            errors.append(f"[skipped] unexpected error: {stmt[:60]}...")
            continue
    db.commit()
    return errors


def run_migrations(db) -> list[str]:
    """运行所有未应用的迁移，返回已应用的版本列表.

    幂等保证：
    - 创建 _migration_versions 表（IF NOT EXISTS）
    - 检查每个迁移的 checksum
    - 只执行未应用或 checksum 变化的迁移
    - 所有 DDL 使用 IF NOT EXISTS
    - 所有 DML INSERT 使用 OR IGNORE

    Args:
        db: ConnectionManager 实例

    Returns:
        已应用的版本号列表
    """
    applied = []

    # 1. 创建迁移追踪表
    db.execute(MIGRATION_TABLE_SQL)
    db.commit()

    # 2. 逐个检查并应用迁移
    for version, sql_file_path in MIGRATIONS.items():
        try:
            sql_content = Path(sql_file_path).read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning(f"Migration file not found: {sql_file_path}, skipping")
            continue

        current_checksum = _compute_checksum(sql_content)

        # 检查是否已应用
        row = db.execute(
            "SELECT version, checksum FROM _migration_versions WHERE version=?",
            (version,),
        ).fetchone()

        if row is None:
            # 未应用 → 执行
            logger.info(f"Applying migration: {version}")
            db.conn.executescript(sql_content)
            db.execute(
                "INSERT INTO _migration_versions (version, checksum) VALUES (?, ?)",
                (version, current_checksum),
            )
            db.commit()
            applied.append(version)
            logger.info(f"Migration applied: {version}")

        elif row["checksum"] != current_checksum:
            # checksum 变化 → 重新执行（所有 DDL 使用 IF NOT EXISTS，DML 使用 OR IGNORE，安全）
            logger.warning(
                f"Migration {version} checksum changed! "
                f"Stored: {row['checksum'][:12]}..., Current: {current_checksum[:12]}..."
            )
            logger.info(f"Re-applying migration: {version}")
            try:
                db.conn.executescript(sql_content)
            except Exception as exec_err:
                # 旧表结构可能不兼容新 DDL（如缺少列导致 CREATE INDEX 失败），
                # 逐条重试执行，单条失败不影响后续
                logger.warning(
                    f"Re-execution of {version} encountered error: {exec_err}"
                )
                logger.info(f"Falling back to per-statement execution for {version}")
                stmt_errors = _execute_statements_safe(db, sql_content)
                if stmt_errors:
                    for err in stmt_errors:
                        logger.warning(f"  {err}")
            db.execute(
                "UPDATE _migration_versions SET checksum=?, applied_at=datetime('now') WHERE version=?",
                (current_checksum, version),
            )
            db.commit()
            applied.append(version)
            logger.info(f"Migration re-applied: {version}")

        else:
            # 已应用且 checksum 匹配 → 跳过
            logger.debug(f"Migration already applied: {version}")
            applied.append(f"{version} (already applied)")

    # 3. 验证关键表
    _verify_tables(db)

    return applied


def _verify_tables(db):
    """验证所有必需的表都已创建."""
    required_tables = [
        "sessions",
        "messages",
        "memory_facts",
        "experience_trajectories",
        "experience_feedback",
        "persona_attributes",
        "memory_snapshots",
        "users",
        "artifacts",
    ]

    for table in required_tables:
        if not db.table_exists(table):
            raise RuntimeError(f"Required table '{table}' was not created after migration!")

    # 验证 persona_attributes 预置值
    count = db.execute("SELECT COUNT(*) as cnt FROM persona_attributes").fetchone()
    logger.info(f"persona_attributes: {count['cnt']} rows (expected 12)")


def reset_migrations(db) -> None:
    """重置所有迁移（仅用于开发/测试）."""
    logger.warning("Resetting all migrations...")
    db.execute("DROP TABLE IF EXISTS _migration_versions")
    db.commit()
    logger.info("Migrations reset complete.")
