"""业务追踪层 — 订阅 agno 事件流，落到 SQLite + JSONL。

写入失败绝不影响主流程。

每条 JSONL 记录结构:
    {"ts": "...", "session": "...", "agent": "insight|orchestrator|...",
     "is_leader": true/false, "event": "...", "payload": {...}}
并行 SubAgent 通过 agent 字段隔离，主 agent 通过 is_leader=true 区分。
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from core.observability.db import db

_TRACE_DIR = Path(__file__).resolve().parents[2] / "data" / "logs" / "trace"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_serialize(obj: Any) -> Any:
    """将 payload 安全降级为 JSON 可序列化形式。

    处理 agno 内部对象（ToolExecution、dataclass、Pydantic BaseModel 等），
    避免 json.dumps 在 default=str 之前因嵌套容器中的不可序列化对象而失败。

    对 JSON 字符串（如 agno agent_skills 返回值）做 parse → 返回 dict/list，
    使外层 json.dumps(ensure_ascii=False) 能正确保留中文字符，消除 \\uXXXX 转义。
    """
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        # agno skill 工具返回 JSON 字符串（ensure_ascii=True），
        # 解析为 dict/list 后由外层 json.dumps(ensure_ascii=False) 重新序列化，
        # 消除内层 \uXXXX 转义。
        try:
            parsed = json.loads(obj)
            if isinstance(parsed, (dict, list)):
                return _safe_serialize(parsed)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return obj
    if isinstance(obj, dict):
        return {k: _safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(v) for v in obj]
    # Pydantic BaseModel
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump(mode="json")
        except Exception:
            pass
    # dataclass
    if hasattr(obj, "__dataclass_fields__"):
        try:
            from dataclasses import asdict
            return asdict(obj)
        except Exception:
            pass
    # 其他对象 → 降级为字符串
    return str(obj)


def _write_jsonl(
    event_type: str,
    session_hash: str,
    payload: Any,
    *,
    agent: str = "",
    is_leader: bool = False,
) -> None:
    """追加一行到当天的 JSONL 文件。

    Args:
        event_type: 事件类型
        session_hash: 会话标识
        payload: 事件载荷
        agent: 产生该事件的 agent 名称（如 "insight"、"orchestrator"）
        is_leader: 是否来自 Team leader
    """
    try:
        _TRACE_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filepath = _TRACE_DIR / f"{today}.jsonl"
        safe_payload = _safe_serialize(payload)
        line = json.dumps(
            {
                "ts": _now_iso(),
                "session": session_hash,
                "agent": agent,
                "is_leader": is_leader,
                "event": event_type,
                "payload": safe_payload,
            },
            ensure_ascii=False,
            default=str,
        )
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        logger.warning(f"JSONL write failed: {event_type}")


class Tracer:
    """会话级 Tracer — 绑定到一个 session_hash。

    所有 trace 方法接受 agent / is_leader 参数，用于区分事件来源。
    并行 SubAgent 通过 agent 字段天然隔离。
    """

    def __init__(self, session_hash: str, db_session_id: Optional[int] = None):
        self.session_hash = session_hash
        self.db_session_id = db_session_id

    def trace(
        self,
        event_type: str,
        payload: Any = None,
        *,
        agent: str = "",
        is_leader: bool = False,
    ) -> None:
        """写入一条 trace 事件（SQLite + JSONL 双写）。"""
        try:
            safe_payload = _safe_serialize(payload)
            if self.db_session_id is not None:
                # agent 信息同时存入独立列（可索引）和 payload（兼容旧查询）
                enriched = safe_payload if isinstance(safe_payload, dict) else {"data": safe_payload}
                enriched = {**enriched, "_agent": agent, "_is_leader": is_leader}
                db.insert_trace(
                    self.db_session_id,
                    self.session_hash,
                    event_type,
                    enriched,
                    agent_name=agent,
                )
            _write_jsonl(event_type, self.session_hash, safe_payload, agent=agent, is_leader=is_leader)
        except Exception:
            logger.warning(f"trace write failed: {event_type}")

    # ─── 用户请求/最终回复 ────────────────────────────────────────────

    def request(self, user_input: str) -> None:
        self.trace("request", {"input": user_input})

    def response(self, content: str) -> None:
        self.trace("response", {"content": content}, agent="orchestrator", is_leader=True)

    # ─── LLM 调用 (由 inject_prompt_tracer 触发) ─────────────────────

    def llm_prompt(
        self,
        messages: list,
        *,
        tools: Optional[list] = None,
        tool_choice: Any = None,
        agent_name: str = "",
    ) -> None:
        """记录发送给 LLM 的完整请求（messages + tools 定义 + tool_choice）。

        Args:
            messages: 发送给 LLM 的消息列表
            tools: 可用工具定义
            tool_choice: 工具选择策略
            agent_name: 发出该 LLM 调用的 agent 名称
        """
        serialized = []
        for m in messages:
            try:
                role = getattr(m, "role", "unknown")
                content = getattr(m, "content", "")
                if isinstance(content, str):
                    try:
                        parsed = json.loads(content)
                        content = json.dumps(parsed, ensure_ascii=False)
                    except (json.JSONDecodeError, TypeError):
                        pass
                elif isinstance(content, list):
                    content = json.dumps(content, ensure_ascii=False, default=str)
                serialized.append({"role": str(role), "content": content})
            except Exception:
                serialized.append({"role": "unknown", "content": str(m)[:512]})

        payload: dict[str, Any] = {"messages": serialized, "count": len(serialized)}

        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        # agent_name 为空时说明是 orchestrator (leader)
        is_leader = not agent_name or agent_name in ("orchestrator", "home-broadband-team")
        self.trace(
            "llm_prompt",
            payload,
            agent=agent_name or "orchestrator",
            is_leader=is_leader,
        )

    # ─── 思考 ────────────────────────────────────────────────────────

    def thinking(self, content: str, *, agent: str = "", is_leader: bool = False) -> None:
        self.trace("thinking", {"content": content}, agent=agent, is_leader=is_leader)

    # ─── 工具调用 ────────────────────────────────────────────────────

    def tool_invoke(
        self, skill_name: str, inputs: Any, *, agent: str = "", is_leader: bool = False
    ) -> None:
        self.trace(
            "tool_invoke", {"skill": skill_name, "inputs": inputs}, agent=agent, is_leader=is_leader
        )

    def tool_result(
        self,
        skill_name: str,
        outputs: Any,
        latency_ms: int = 0,
        *,
        agent: str = "",
        is_leader: bool = False,
    ) -> None:
        self.trace(
            "tool_result",
            {"skill": skill_name, "outputs": outputs, "latency_ms": latency_ms},
            agent=agent,
            is_leader=is_leader,
        )

    # ─── SubAgent 交互 ──────────────────────────────────────────────

    def member_content(self, member_name: str, content: str) -> None:
        """记录 SubAgent 的文本回复内容。"""
        self.trace("member_content", {"content": content}, agent=member_name, is_leader=False)

    def member_completed(self, member_name: str, content: str = "") -> None:
        """记录 SubAgent 运行完成。"""
        self.trace("member_completed", {"content": content}, agent=member_name, is_leader=False)

    # ─── 错误 / 未处理事件 ──────────────────────────────────────────

    def unhandled_event(
        self, event_type: str, source_id: str = "", is_leader: bool = False
    ) -> None:
        """记录未处理的事件类型（用于调试缺失事件）。"""
        self.trace(
            "unhandled_event",
            {"event_type": event_type},
            agent=source_id,
            is_leader=is_leader,
        )

    def error(self, error_msg: str) -> None:
        self.trace("error", {"error": error_msg})
