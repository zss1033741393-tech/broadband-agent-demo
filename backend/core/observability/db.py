"""SQLite schema 初始化与 DAO 层。

所有写操作均 try/except 包裹，失败不影响主流程。
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger


_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "sessions.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_hash TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    ended_at TEXT,
    user_agent TEXT,
    task_type TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT,
    created_at TEXT NOT NULL,
    parent_msg_id INTEGER,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    message_id INTEGER,
    skill_name TEXT,
    inputs_json TEXT,
    outputs_json TEXT,
    latency_ms INTEGER,
    status TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    session_hash TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL,
    agent_name TEXT NOT NULL DEFAULT '',
    payload_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_tool_calls_session ON tool_calls(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_traces_session ON traces(session_id, created_at);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """SQLite DAO — 线程安全（每次操作独立连接 or 使用 check_same_thread=False）。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or _DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        try:
            conn = self._get_conn()
            conn.executescript(_SCHEMA_SQL)
            # 兼容旧 schema：traces 表可能缺少新增列
            for col_sql in (
                "ALTER TABLE traces ADD COLUMN session_hash TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE traces ADD COLUMN agent_name TEXT NOT NULL DEFAULT ''",
            ):
                try:
                    conn.execute(col_sql)
                    conn.commit()
                except sqlite3.OperationalError:
                    pass  # 列已存在，忽略
            # agent_name 列确保存在后才能建索引（对旧 DB 做迁移时顺序不能提前）
            try:
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_traces_agent ON traces(agent_name, event_type)"
                )
                conn.commit()
            except sqlite3.OperationalError:
                pass
            # 自检：验证表存在且可写
            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
            # 写入验证：插入后立即删除，确认 DB 可写
            conn.execute(
                "INSERT INTO sessions (session_hash, created_at) VALUES ('__selftest__', ?)",
                (_now_iso(),),
            )
            conn.execute("DELETE FROM sessions WHERE session_hash='__selftest__'")
            conn.commit()
            conn.close()
            logger.info(f"SQLite schema 初始化完成 (可写验证通过): {self.db_path}, tables={tables}")
        except Exception:
            logger.exception(f"SQLite schema 初始化失败: {self.db_path}")

    # ---- sessions ----
    def create_session(self, session_hash: str, user_agent: str = "") -> Optional[int]:
        """创建会话记录（幂等）。

        使用 INSERT OR IGNORE 避免 UNIQUE 约束冲突（如应用重启后
        客户端用相同 session_hash 重连），冲突时回退到 SELECT 获取已有 ID。
        """
        conn = self._get_conn()
        try:
            cur = conn.execute(
                "INSERT OR IGNORE INTO sessions (session_hash, created_at, user_agent) VALUES (?, ?, ?)",
                (session_hash, _now_iso(), user_agent),
            )
            conn.commit()
            sid = cur.lastrowid
            if not sid:
                # UNIQUE 冲突时 lastrowid 为 0，回退查询已有记录
                row = conn.execute(
                    "SELECT id FROM sessions WHERE session_hash=?", (session_hash,)
                ).fetchone()
                sid = row["id"] if row else None
            if sid:
                logger.debug(f"create_session 成功: session_hash={session_hash[:8]}..., db_sid={sid}")
            else:
                logger.error(f"create_session 无法获取 sid: session_hash={session_hash[:8]}...")
            return sid
        except Exception:
            logger.exception(
                f"create_session 失败: session_hash={session_hash[:8]}..., db_path={self.db_path}"
            )
            return None
        finally:
            conn.close()

    def end_session(self, session_hash: str, task_type: str = "") -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE sessions SET ended_at=?, task_type=? WHERE session_hash=?",
                (_now_iso(), task_type, session_hash),
            )
            conn.commit()
        except Exception:
            logger.exception("end_session 失败")
        finally:
            conn.close()

    def get_session_id(self, session_hash: str) -> Optional[int]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT id FROM sessions WHERE session_hash=?", (session_hash,)
            ).fetchone()
            return row["id"] if row else None
        except Exception:
            logger.exception("get_session_id 失败")
            return None
        finally:
            conn.close()

    # ---- messages ----
    def insert_message(
        self, session_id: int, role: str, content: str, parent_msg_id: Optional[int] = None
    ) -> Optional[int]:
        conn = self._get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO messages (session_id, role, content, created_at, parent_msg_id) VALUES (?, ?, ?, ?, ?)",
                (session_id, role, content, _now_iso(), parent_msg_id),
            )
            conn.commit()
            mid = cur.lastrowid
            logger.debug(f"insert_message 成功: session_id={session_id}, role={role}, mid={mid}")
            return mid
        except Exception:
            logger.exception(f"insert_message 失败: session_id={session_id}, role={role}")
            return None
        finally:
            conn.close()

    # ---- tool_calls ----
    def insert_tool_call(
        self,
        session_id: int,
        skill_name: str,
        inputs_json: str,
        outputs_json: str = "",
        latency_ms: int = 0,
        status: str = "ok",
        message_id: Optional[int] = None,
    ) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO tool_calls (session_id, message_id, skill_name, inputs_json, outputs_json, latency_ms, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    message_id,
                    skill_name,
                    inputs_json,
                    outputs_json,
                    latency_ms,
                    status,
                    _now_iso(),
                ),
            )
            conn.commit()
        except Exception:
            logger.exception("insert_tool_call 失败")
        finally:
            conn.close()

    # ---- traces ----
    def insert_trace(
        self,
        session_id: int,
        session_hash: str,
        event_type: str,
        payload: Any = None,
        agent_name: str = "",
    ) -> None:
        conn = self._get_conn()
        try:
            payload_str = json.dumps(payload, ensure_ascii=False, default=str) if payload else "{}"
            conn.execute(
                "INSERT INTO traces (session_id, session_hash, event_type, agent_name, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, session_hash, event_type, agent_name, payload_str, _now_iso()),
            )
            conn.commit()
        except Exception:
            logger.exception("insert_trace 失败")
        finally:
            conn.close()


# 全局单例
db = Database()
