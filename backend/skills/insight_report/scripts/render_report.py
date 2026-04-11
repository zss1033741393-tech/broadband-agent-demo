#!/usr/bin/env python3
"""报告渲染脚本 — 将 InsightAgent 的执行产物渲染为 Markdown 报告。

作为 agno Skill 脚本被调用。stdout 即最终产物，Agent 必须原样输出。

自动识别两种上下文形态：
- **多阶段形态**（新）：含 `phases` 键 → 使用 `multi_phase_report.md.j2`
- **归因形态**（旧）：含 `analysis` 键 → 使用 `report.md.j2`（向后兼容）
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader

_REFERENCES_DIR = Path(__file__).resolve().parents[1] / "references"


def _safe_parse_json(raw: str) -> dict:
    """带修复的 JSON 解析：先直接解析，失败则尝试修复常见 shell 转义损坏后重试。"""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    stripped = raw.strip()
    if stripped.startswith("'") and stripped.endswith("'"):
        stripped = stripped[1:-1]
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    repaired = re.sub(r"(?<=[{,])\s*([a-zA-Z_]\w*)\s*:", r' "\1":', raw)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass
    try:
        from json_repair import repair_json

        return json.loads(repair_json(raw, return_objects=False))
    except (ImportError, Exception):
        pass
    if not sys.stdin.isatty():
        try:
            stdin_data = sys.stdin.read().strip()
            if stdin_data:
                return json.loads(stdin_data)
        except Exception:
            pass
    return json.loads(raw)


def render(context_json: str) -> str:
    """渲染 Markdown 报告。

    Args:
        context_json: 上下文 JSON 字符串，支持两种形态（见模块 docstring）。
    """
    try:
        ctx: Dict[str, Any] = (
            _safe_parse_json(context_json) if isinstance(context_json, str) else context_json
        )
    except json.JSONDecodeError as exc:
        return f"渲染失败: 无效的上下文 JSON — {exc}"

    ctx.setdefault("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    env = Environment(
        loader=FileSystemLoader(str(_REFERENCES_DIR)),
        keep_trailing_newline=True,
    )

    template_name = _pick_template(ctx)

    try:
        tmpl = env.get_template(template_name)
        return tmpl.render(**ctx)
    except Exception as exc:
        return f"渲染失败: {exc}"


def _pick_template(ctx: Dict[str, Any]) -> str:
    """选择模板。phases 优先（新多阶段），否则回退 report.md.j2（旧归因）。"""
    if ctx.get("phases"):
        return "multi_phase_report.md.j2"
    return "report.md.j2"


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(render(sys.argv[1]))
    else:
        print(render("{}"))
