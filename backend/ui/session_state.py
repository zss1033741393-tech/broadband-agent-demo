"""Gradio session state 封装。"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class UISessionState:
    """Gradio 前端 session 状态。"""

    session_hash: str = field(default_factory=lambda: str(uuid.uuid4()))
    chat_history: List[Dict[str, Any]] = field(default_factory=list)
