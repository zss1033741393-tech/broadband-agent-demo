"""会话与消息的持久化读写。

使用独立的 SQLite 文件（data/api.db），与 agno 的 agent_sessions.db 互不干扰。
所有字段按前端 Message 模型存储，不暴露 Gradio 结构。
"""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, List, Optional

import aiosqlite
from loguru import logger

from api.models import (
    Conversation,
    ExperienceAssuranceRenderBlock,
    ImageRenderBlock,
    InsightRenderBlock,
    Message,
    RenderBlock,
    Step,
)

_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "api.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@asynccontextmanager
async def _get_conn() -> AsyncGenerator[aiosqlite.Connection, None]:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(_DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        yield conn


async def init_db() -> None:
    """建表（幂等）。"""
    async with _get_conn() as conn:
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id                   TEXT PRIMARY KEY,
                title                TEXT NOT NULL,
                created_at           TEXT NOT NULL,
                updated_at           TEXT NOT NULL,
                message_count        INTEGER DEFAULT 0,
                last_message_preview TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS messages (
                id                    TEXT PRIMARY KEY,
                conversation_id       TEXT NOT NULL,
                role                  TEXT NOT NULL,
                content               TEXT DEFAULT '',
                thinking_content      TEXT DEFAULT '',
                thinking_duration_sec INTEGER DEFAULT 0,
                steps                 TEXT DEFAULT '[]',
                render_blocks         TEXT DEFAULT '[]',
                created_at            TEXT NOT NULL,
                status                TEXT DEFAULT 'done',
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
        """)
        await conn.commit()
    logger.info(f"API DB 初始化完成: {_DB_PATH}")


# ─── Conversation CRUD ────────────────────────────────────────────────────────

async def list_conversations(page: int = 1, page_size: int = 20) -> tuple[List[Conversation], int]:
    offset = (page - 1) * page_size
    async with _get_conn() as conn:
        async with conn.execute(
            "SELECT COUNT(*) FROM conversations"
        ) as cur:
            row = await cur.fetchone()
            total = row[0]

        async with conn.execute(
            "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (page_size, offset),
        ) as cur:
            rows = await cur.fetchall()

    convs = [_row_to_conversation(r) for r in rows]
    return convs, total


async def create_conversation(title: str = "新对话") -> Conversation:
    now = _now_iso()
    conv = Conversation(
        id=str(uuid.uuid4()),
        title=title,
        createdAt=now,
        updatedAt=now,
        messageCount=0,
        lastMessagePreview="",
    )
    async with _get_conn() as conn:
        await conn.execute(
            "INSERT INTO conversations VALUES (?, ?, ?, ?, ?, ?)",
            (conv.id, conv.title, conv.createdAt, conv.updatedAt, 0, ""),
        )
        await conn.commit()
    return conv


async def get_conversation(conv_id: str) -> Optional[Conversation]:
    async with _get_conn() as conn:
        async with conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv_id,)
        ) as cur:
            row = await cur.fetchone()
    return _row_to_conversation(row) if row else None


async def delete_conversation(conv_id: str) -> bool:
    async with _get_conn() as conn:
        cur = await conn.execute(
            "DELETE FROM conversations WHERE id = ?", (conv_id,)
        )
        await conn.commit()
    return cur.rowcount > 0


async def update_conversation_title(conv_id: str, title: str) -> bool:
    """更新会话标题。"""
    async with aiosqlite.connect(_DB_PATH) as conn:
        cur = await conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title[:100], _now_iso(), conv_id),
        )
        await conn.commit()
    return cur.rowcount > 0


async def _update_conversation_meta(conn: aiosqlite.Connection, conv_id: str, preview: str) -> None:
    now = _now_iso()
    await conn.execute(
        """UPDATE conversations
           SET updated_at = ?, message_count = message_count + 1, last_message_preview = ?
           WHERE id = ?""",
        (now, preview[:100], conv_id),
    )


# ─── Message CRUD ─────────────────────────────────────────────────────────────

async def list_messages(conv_id: str) -> List[Message]:
    async with _get_conn() as conn:
        async with conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conv_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [_row_to_message(r) for r in rows]


async def insert_user_message(conv_id: str, content: str) -> Message:
    now = _now_iso()
    msg = Message(
        id=str(uuid.uuid4()),
        conversationId=conv_id,
        role="user",
        content=content,
        createdAt=now,
    )
    async with _get_conn() as conn:
        await conn.execute(
            "INSERT INTO messages (id, conversation_id, role, content, thinking_content, "
            "thinking_duration_sec, steps, render_blocks, created_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (msg.id, conv_id, "user", content, "", 0, "[]", "[]", now, "done"),
        )
        await _update_conversation_meta(conn, conv_id, content)
        await conn.commit()
    return msg


async def insert_assistant_message(
    conv_id: str,
    content: str,
    thinking_content: str = "",
    thinking_duration_sec: int = 0,
    steps: list = None,
    render_blocks: list = None,
    status: str = "done",
) -> Message:
    now = _now_iso()
    msg_id = str(uuid.uuid4())
    steps_json = json.dumps(steps or [], ensure_ascii=False)
    render_json = json.dumps(render_blocks or [], ensure_ascii=False)
    preview = content[:100] if content else ""

    async with _get_conn() as conn:
        await conn.execute(
            "INSERT INTO messages (id, conversation_id, role, content, thinking_content, "
            "thinking_duration_sec, steps, render_blocks, created_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (msg_id, conv_id, "assistant", content, thinking_content,
             thinking_duration_sec, steps_json, render_json, now, status),
        )
        await _update_conversation_meta(conn, conv_id, preview)
        await conn.commit()

    return Message(
        id=msg_id,
        conversationId=conv_id,
        role="assistant",
        content=content,
        thinkingContent=thinking_content or None,
        thinkingDurationSec=thinking_duration_sec or None,
        steps=[],
        renderBlocks=[],
        createdAt=now,
    )


# ─── 行转模型 ─────────────────────────────────────────────────────────────────

def _row_to_conversation(row: aiosqlite.Row) -> Conversation:
    return Conversation(
        id=row["id"],
        title=row["title"],
        createdAt=row["created_at"],
        updatedAt=row["updated_at"],
        messageCount=row["message_count"],
        lastMessagePreview=row["last_message_preview"],
    )


def _row_to_message(row: aiosqlite.Row) -> Message:
    steps_raw = json.loads(row["steps"] or "[]")
    render_raw = json.loads(row["render_blocks"] or "[]")

    # 老数据兼容：早期 SubStep 契约与现行不同（曾有 result 字段、缺 scriptPath 等）。
    # 逐条过 Step.model_validate 时对缺失字段做宽容处理，单条失败不影响整条消息。
    steps: List[Step] = []
    for s in steps_raw:
        try:
            steps.append(Step(**s))
        except Exception:
            logger.warning(
                f"Step 校验失败，降级展示（step_id={s.get('stepId')}）"
            )
            # 降级：保留 stepId/title/textContent，subSteps 过滤掉无法解析的条目
            safe_subs = []
            for sub in s.get("subSteps") or []:
                try:
                    safe_subs.append(sub if isinstance(sub, dict) else {})
                except Exception:
                    pass
            steps.append(Step(
                stepId=s.get("stepId", ""),
                title=s.get("title", ""),
                subSteps=[],  # 无法还原时留空，UI 自会降级显示"暂无内容"
                textContent=s.get("textContent", ""),
            ))
            # safe_subs 仅保留原始 dict 供调试日志，未接入 Message 结构
            _ = safe_subs
    render_blocks: List[RenderBlock] = []
    for rb in render_raw:
        if rb.get("renderType") == "insight":
            render_blocks.append(InsightRenderBlock(**rb))
        elif rb.get("renderType") == "image":
            render_blocks.append(ImageRenderBlock(**rb))
        elif rb.get("renderType") == "experience_assurance":
            render_blocks.append(ExperienceAssuranceRenderBlock(**rb))

    return Message(
        id=row["id"],
        conversationId=row["conversation_id"],
        role=row["role"],
        content=row["content"],
        thinkingContent=row["thinking_content"] or None,
        thinkingDurationSec=row["thinking_duration_sec"] or None,
        steps=steps,
        renderBlocks=render_blocks,
        createdAt=row["created_at"],
    )
