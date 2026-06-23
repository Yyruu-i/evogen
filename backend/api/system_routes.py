"""系统状态 REST API — Gateway 心跳 / Agent 在线状态 / 数据库状态."""

import json
import logging
import os
import re
import subprocess
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"])

_APP_START_TIME = time.time()


# ─────────────────────────────────────────────────────
# Gateway 心跳检测
# ─────────────────────────────────────────────────────


def _check_gateway() -> dict:
    """检查 Hermes Gateway 运行状态.

    策略：
    1. 运行 `hermes gateway status` 检查进程
    2. 回退：pgrep 检查 gateway 进程
    """
    profiles: list[dict] = []
    running = False
    error = None

    try:
        result = subprocess.run(
            ["hermes", "gateway", "status"],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "HOME": os.path.expanduser("~")},
        )
        stdout = result.stdout.strip()

        if "not running" in stdout.lower():
            running = False
        elif result.returncode == 0 or "running" in stdout.lower():
            running = True
            # 解析两种格式:
            #   "✓ Gateway is running (PID: 110)"
            #   "  ✓ architect        — PID 106"
            for line in stdout.split("\n"):
                line = line.strip()
                pid = None
                profile = ""

                if "— PID" in line or "-- PID" in line:
                    # 格式: ✓ architect        — PID 106
                    try:
                        clean = line.lstrip("✓✗").strip()
                        parts = clean.replace("—", " -- ").replace("--", " -- ").split(" -- ")
                        profile = parts[0].strip()
                        pid_part = parts[1].strip() if len(parts) > 1 else ""
                        pid = int(pid_part.replace("PID", "").strip()) if pid_part else None
                    except (ValueError, IndexError):
                        pass
                elif "(PID:" in line:
                    # 格式: ✓ Gateway is running (PID: 110)
                    m = re.search(r"\(PID:\s*(\d+)\)", line)
                    if m:
                        pid = int(m.group(1))
                        profile = "gateway"

                if profile:
                    profiles.append({"profile": profile, "pid": pid})
        else:
            error = stdout or "Unknown gateway status"
    except FileNotFoundError:
        # hermes CLI 不可用，用 pgrep 回退
        try:
            pg = subprocess.run(
                ["pgrep", "-f", "hermes gateway run"],
                capture_output=True, text=True, timeout=5,
            )
            pids = [int(p) for p in pg.stdout.strip().split("\n") if p]
            if pids:
                running = True
                for pid in pids:
                    profiles.append({"profile": "unknown", "pid": pid})
        except Exception as e:
            error = str(e)
    except subprocess.TimeoutExpired:
        error = "Gateway status check timed out"
    except Exception as e:
        error = str(e)

    return {
        "running": running,
        "profiles": profiles,
        "error": error,
    }


def _check_db() -> dict:
    """检查数据库状态."""
    try:
        from backend.db.connection import get_db
        db = get_db()
        row = db.execute("SELECT COUNT(*) FROM memory_facts").fetchone()
        fact_count = row[0] if row else 0
        return {"connected": True, "memory_facts": fact_count}
    except Exception as e:
        return {"connected": False, "error": str(e)}


# ─────────────────────────────────────────────────────
# GET /api/v1/system/status
# ─────────────────────────────────────────────────────


@router.get("/status")
async def system_status():
    """获取系统完整状态 — Gateway 心跳 + Agent 在线 + 数据库 + 容量概览.

    返回格式：
    {
      "ok": true,
      "data": {
        "agent": {"status": "online", "uptime_seconds": 1234, ...},
        "gateway": {"running": true, "profiles": [...]},
        "database": {"connected": true, "memory_facts": 11},
        "memory_capacity": {...},
        "server_time": "2026-06-02T..."
      }
    }
    """
    uptime = int(time.time() - _APP_START_TIME)

    # Gateway 心跳
    gateway = _check_gateway()

    # 数据库
    database = _check_db()

    # 记忆容量概览（不抛异常，优雅降级）
    capacity = {}
    try:
        from backend.db.connection import get_db
        db = get_db()
        total = db.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
        archive = db.execute(
            "SELECT COUNT(*) FROM memory_facts WHERE layer = 'archive'"
        ).fetchone()[0]
        layer_rows = db.execute(
            "SELECT layer, COUNT(*) as cnt FROM memory_facts GROUP BY layer"
        ).fetchall()
        by_layer = {r["layer"]: r["cnt"] for r in layer_rows}

        # 读容量上限
        limit_row = db.execute(
            "SELECT value_json FROM persona_attributes WHERE key = 'memory_capacity_limit'"
        ).fetchone()
        limit = 10000
        if limit_row:
            try:
                limit = int(json.loads(limit_row["value_json"]))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

        # 存储估算
        storage_row = db.execute(
            "SELECT COALESCE(SUM(LENGTH(content)), 0) FROM memory_facts"
        ).fetchone()
        text_bytes = int((storage_row[0] if storage_row else 0) * 1.5)
        vector_bytes = total * 1024 * 4

        capacity = {
            "total_facts": total,
            "archive_count": archive,
            "capacity_limit": limit,
            "usage_percent": round(total / limit * 100, 2) if limit > 0 else 0.0,
            "storage_estimate_bytes": text_bytes + vector_bytes,
            "by_layer": by_layer,
        }
    except Exception as e:
        capacity = {"error": str(e)}

    return {
        "ok": True,
        "data": {
            "agent": {
                "status": "online",
                "version": "0.1.1",
                "uptime_seconds": uptime,
                "uptime_human": _format_uptime(uptime),
                "python_version": os.environ.get("PYTHON_VERSION", "3.12"),
                "started_at": datetime.fromtimestamp(
                    _APP_START_TIME, tz=timezone.utc
                ).isoformat(),
            },
            "gateway": gateway,
            "database": database,
            "memory_capacity": capacity,
            "server_time": datetime.now(timezone.utc).isoformat(),
        },
    }


def _format_uptime(seconds: int) -> str:
    """格式化 uptime."""
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


# ─────────────────────────────────────────────────────
# 日志读取
# ─────────────────────────────────────────────────────

_LOG_PATH = os.environ.get("EVOGEN_LOG_PATH", "/tmp/evogen-backend.log")


def _parse_log_line(line: str) -> dict:
    """将单行日志解析为结构化字段.

    支持三种格式：
    1. 2026-06-02 22:27:22,059 [INFO] backend.main: message
    2. INFO:     message (uvicorn)
    3. WARNING/ERROR: message
    """
    entry = {"raw": line, "level": "INFO", "timestamp": None, "source": "", "message": line}

    # 格式1: 时间戳 [LEVEL] module: message
    m = re.match(
        r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+\[(\w+)\]\s+([\w.]+):\s*(.*)",
        line,
    )
    if m:
        entry["timestamp"] = m.group(1)
        entry["level"] = m.group(2)
        entry["source"] = m.group(3)
        entry["message"] = m.group(4)
        return entry

    # 格式2: LEVEL:     message
    m = re.match(r"(\w+):\s{2,}(.*)", line)
    if m:
        entry["level"] = m.group(1)
        entry["message"] = m.group(2)
        entry["source"] = "uvicorn"
        return entry

    return entry


def _read_recent_logs(
    path: str = _LOG_PATH, limit: int = 50,
    level: str = "", keyword: str = "",
) -> list[dict]:
    """读取最近的日志行并解析.

    Args:
        path: 日志文件路径
        limit: 返回最大行数
        level: 按级别过滤 (INFO/WARNING/ERROR)
        keyword: 按关键词过滤
    """
    if not os.path.exists(path):
        return []

    entries: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            # 从尾部读 limit 行
            lines = f.readlines()
            lines = lines[-limit:]  # 取最近 N 行

        for line in lines:
            line = line.rstrip("\n\r")
            if not line.strip():
                continue
            entry = _parse_log_line(line)

            # 过滤
            if level and entry["level"].upper() != level.upper():
                continue
            if keyword and keyword.lower() not in entry["message"].lower():
                continue

            entries.append(entry)
    except Exception as e:
        logger.error(f"Failed to read log file {path}: {e}")
        entries = [{"raw": f"Error reading log: {e}", "level": "ERROR"}]

    return entries


# ─────────────────────────────────────────────────────
# 系统配置（可运行时修改）
# ─────────────────────────────────────────────────────

# 运行时配置（内存中，重启后重置，可由前端设置页修改）
_runtime_config: dict = {
    "max_agent_rounds": 90,
    "llm_model": os.getenv("LLM_MODEL", "deepseek-chat"),
}

# 持久化配置文件路径
_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "runtime_config.json"
)


def _save_runtime_config():
    """持久化运行时配置到 JSON 文件."""
    try:
        with open(_CONFIG_FILE, "w") as f:
            json.dump(_runtime_config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save runtime config: {e}")


def _load_runtime_config():
    """启动时从 JSON 文件加载运行时配置."""
    try:
        if os.path.exists(_CONFIG_FILE):
            with open(_CONFIG_FILE, "r") as f:
                data = json.load(f)
                _runtime_config.update(data)
    except Exception as e:
        logger.warning(f"Failed to load runtime config: {e}")


# 启动时加载持久化配置
_load_runtime_config()


@router.get("/config")
async def get_config():
    """获取系统运行时配置."""
    return {"ok": True, "data": {**_runtime_config}}


@router.put("/config")
async def update_config(config: dict):
    """更新系统运行时配置."""
    allowed_keys = {"max_agent_rounds", "llm_model"}
    for key, value in config.items():
        if key in allowed_keys:
            if key == "max_agent_rounds":
                value = max(1, min(int(value), 500))
            _runtime_config[key] = value
    _save_runtime_config()
    return {"ok": True, "data": {**_runtime_config}}


# 提供一个同步读取配置的函数，供其他模块使用
def get_config_value(key: str, default=None):
    return _runtime_config.get(key, default)


# ════════════════════════════════════════════════════════
# GET /api/v1/system/logs
# ════════════════════════════════════════════════════════


@router.get("/logs")


@router.get("/logs")
async def system_logs(
    limit: int = 50,
    level: str = "",
    keyword: str = "",
):
    """返回最近的系统日志.

    Query params:
        limit:  返回条目数 (默认 50, 最大 200)
        level:  按级别过滤 (INFO/WARNING/ERROR)
        keyword: 按关键词搜索

    返回格式：
    {
      "ok": true,
      "data": {
        "total": 50,
        "entries": [
          {"timestamp": "...", "level": "INFO", "source": "backend.main", "message": "..."},
          ...
        ],
        "log_file": "/tmp/evogen-backend.log"
      }
    }
    """
    limit = min(max(1, limit), 200)
    level = level.strip().upper()
    keyword = keyword.strip()

    if level and level not in ("INFO", "WARNING", "ERROR", "DEBUG", "CRITICAL"):
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "error": f"Invalid level: {level}. Use INFO/WARNING/ERROR/DEBUG/CRITICAL",
            },
        )

    entries = _read_recent_logs(path=_LOG_PATH, limit=limit, level=level, keyword=keyword)
    return {
        "ok": True,
        "data": {
            "total": len(entries),
            "entries": entries,
            "log_file": _LOG_PATH,
        },
    }
