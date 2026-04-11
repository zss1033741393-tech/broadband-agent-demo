#!/usr/bin/env python3
"""Schema 查询脚本 — data_insight Skill 的元信息工具。

供 InsightAgent 在规划 / 分解阶段查询天表或分钟表的合法字段和维度结构。
避免把庞大的 schema 常驻在 prompts/insight.md 中（Progressive Disclosure L3）。

输入（argv[1]）：JSON 字符串，形如
    {
        "table": "day" | "minute",
        "focus_dimensions": ["ODN", "Wifi"]   // 可选，不填返回全量 schema
    }

输出（stdout）：JSON 字符串，形如
    {
        "status": "ok",
        "skill": "insight_decompose",
        "op": "list_schema",
        "table": "day",
        "focus_dimensions": [...],
        "schema_markdown": "...文字 schema...",
        "all_fields": [...]
    }
"""

import json
import re
import sys
from typing import Any

try:
    import ce_insight_core as cic
except ImportError as exc:
    print(
        json.dumps(
            {
                "status": "error",
                "skill": "insight_decompose",
                "op": "list_schema",
                "error": f"ce_insight_core 未安装: {exc}",
            },
            ensure_ascii=False,
        )
    )
    sys.exit(1)


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


def run(payload_json: str) -> str:
    """主入口：解析 payload → 查询 schema → 返回。"""
    try:
        payload: dict[str, Any] = _safe_parse_json(payload_json) if payload_json else {}
    except json.JSONDecodeError as exc:
        return _err(f"payload JSON 解析失败: {exc}")

    table = payload.get("table", "day")
    if table not in ("day", "minute"):
        return _err(f"table 必须是 day/minute，收到: {table}")

    focus = payload.get("focus_dimensions") or []
    if not isinstance(focus, list):
        return _err("focus_dimensions 必须是 list[str]")

    try:
        if table == "day":
            schema_md = cic.get_pruned_schema(focus) if focus else cic.get_full_day_schema()
            all_fields = sorted(cic.get_all_day_fields())
        else:
            schema_md = cic.get_minute_schema(focus)
            all_fields = sorted(cic.get_all_minute_fields())
    except Exception as exc:
        return _err(f"获取 schema 失败: {type(exc).__name__}: {exc}")

    return json.dumps(
        {
            "status": "ok",
            "skill": "insight_decompose",
            "op": "list_schema",
            "table": table,
            "focus_dimensions": focus,
            "schema_markdown": schema_md,
            "all_fields": all_fields,
        },
        ensure_ascii=False,
    )


def _err(msg: str) -> str:
    return json.dumps(
        {
            "status": "error",
            "skill": "insight_decompose",
            "op": "list_schema",
            "error": msg,
        },
        ensure_ascii=False,
    )


if __name__ == "__main__":
    _payload = sys.argv[1] if len(sys.argv) > 1 else "{}"
    print(run(_payload))
