#!/usr/bin/env python3
"""目标解析 — 槽位状态机。

读取 slot_schema.yaml 驱动追问逻辑。作为 agno Skill 脚本被调用。
接受 (user_input, current_state_json) 输入，返回槽位状态 + 追问列表 JSON。
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "references" / "slot_schema.yaml"


def _load_schema() -> Dict[str, Any]:
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _get_missing_slots(schema: Dict[str, Any], state: Dict[str, Any]) -> List[str]:
    """按 schema 顺序返回缺失的必填槽位。"""
    missing: List[str] = []
    for name, cfg in schema.get("slots", {}).items():
        if cfg.get("required", False) and state.get(name) in (None, ""):
            missing.append(name)
    return missing


def _get_next_questions(
    schema: Dict[str, Any],
    state: Dict[str, Any],
    max_questions: int = 3,
) -> List[Dict[str, Any]]:
    """返回下一批待追问的槽位。"""
    slots_def = schema.get("slots", {})
    missing = _get_missing_slots(schema, state)
    questions: List[Dict[str, Any]] = []

    for slot_name in missing[:max_questions]:
        cfg = slots_def[slot_name]
        prompt = cfg.get("prompt", f"请提供 {slot_name}")

        if "depends_on" in cfg and "branches" in cfg:
            dep_value = state.get(cfg["depends_on"])
            if dep_value and dep_value in cfg["branches"]:
                options = cfg["branches"][dep_value]
                prompt = f"{prompt}（可选: {' / '.join(options)}）"
        elif "enum" in cfg:
            options = cfg["enum"]
            prompt = f"{prompt}（{' / '.join(options)}）"

        questions.append(
            {
                "slot_name": slot_name,
                "prompt": prompt,
                "required": cfg.get("required", False),
                "type": cfg.get("type", "enum"),
            }
        )
    return questions


_APP_PATTERNS = [
    ("抖音", r"抖音|Douyin|tiktok"),
    ("快手", r"快手|kuaishou"),
    ("微信", r"微信|wechat"),
    ("王者荣耀", r"王者荣耀|王者"),
    ("和平精英", r"和平精英|吃鸡"),
    ("原神", r"原神|genshin"),
    ("哔哩哔哩", r"B站|bilibili|哔哩哔哩"),
]


def _parse_user_input(
    user_text: str, schema: Dict[str, Any], state: Dict[str, Any]
) -> Dict[str, Any]:
    """从用户文本中尽可能提取槽位值。"""
    slots_def = schema.get("slots", {})
    merged = {**state}
    extracted: Dict[str, Any] = {}

    for name, cfg in slots_def.items():
        if merged.get(name) not in (None, ""):
            continue

        # enum 直接匹配
        if "enum" in cfg:
            for option in cfg["enum"]:
                if option in user_text:
                    extracted[name] = option
                    merged[name] = option
                    break

        # branches 匹配（依赖项已知时）
        if "branches" in cfg:
            dep_value = merged.get(cfg.get("depends_on", ""))
            if dep_value and dep_value in cfg["branches"]:
                for option in cfg["branches"][dep_value]:
                    if option in user_text:
                        extracted[name] = option
                        merged[name] = option
                        break

        # 时间窗口
        if name == "time_window" and cfg.get("type") == "string":
            match = re.search(r"\d{1,2}:\d{2}\s*[-–~]\s*\d{1,2}:\d{2}", user_text)
            if match:
                extracted[name] = re.sub(r"[–~]", "-", match.group()).replace(" ", "")
            elif "全天" in user_text or "24小时" in user_text:
                extracted[name] = "全天"

        # 保障应用
        if name == "guarantee_app":
            for app, pattern in _APP_PATTERNS:
                if re.search(pattern, user_text, re.IGNORECASE):
                    extracted[name] = app
                    break

        # 投诉历史
        if name == "complaint_history" and cfg.get("type") == "bool":
            if re.search(r"有投诉|曾投诉|投诉过|投诉历史", user_text):
                extracted[name] = True
            elif re.search(r"无投诉|没有投诉|没投诉", user_text):
                extracted[name] = False

    return extracted


def process(user_input: str = "", current_state_json: str = "{}") -> str:
    """主处理函数。

    Args:
        user_input: 用户本轮输入文本
        current_state_json: 上一轮已填充的槽位状态 JSON

    Returns:
        JSON 字符串：{state, is_complete, missing_slots, next_questions}
    """
    schema = _load_schema()
    try:
        state = json.loads(current_state_json) if current_state_json else {}
    except json.JSONDecodeError:
        state = {}

    if user_input:
        extracted = _parse_user_input(user_input, schema, state)
        state.update(extracted)

    missing = _get_missing_slots(schema, state)
    is_complete = len(missing) == 0
    questions = _get_next_questions(schema, state) if not is_complete else []

    result = {
        "state": state,
        "is_complete": is_complete,
        "missing_slots": missing,
        "next_questions": questions,
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # Usage: slot_engine.py <user_input> [current_state_json]
    _user_input = sys.argv[1] if len(sys.argv) > 1 else ""
    _state = sys.argv[2] if len(sys.argv) > 2 else "{}"
    print(process(_user_input, _state))
