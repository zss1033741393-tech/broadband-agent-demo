#!/usr/bin/env python3
"""保存保障方案到 data/api.db。

接收完整 5 段式方案文本作为 CLI 参数，解析为结构化 JSON 后写入
protection_plans 表（单行表，id=1）。
"""

import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Union

_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "api.db"

_TITLE_RE = re.compile(r"^(.+?)\s*[：:]$")
_FIELD_RE = re.compile(r"^\s{4}(.+?)\s*[：:]\s*(.+)$")


def _parse_value(raw: str) -> Union[str, bool]:
    stripped = raw.strip()
    if stripped == "True":
        return True
    if stripped == "False":
        return False
    return stripped


def _parse_plan_text(text: str) -> List[Dict[str, Any]]:
    """解析 5 段式方案文本为 Group 列表。"""
    groups: List[Dict[str, Any]] = []
    current_title: str | None = None
    current_items: List[Dict[str, Any]] = []

    for line in text.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        title_m = _TITLE_RE.match(line)
        if title_m:
            if current_title is not None:
                groups.append({"title": current_title, "items": current_items})
            current_title = title_m.group(1)
            current_items = []
            continue
        field_m = _FIELD_RE.match(line)
        if field_m and current_title is not None:
            current_items.append({
                "label": field_m.group(1),
                "value": _parse_value(field_m.group(2)),
            })

    if current_title is not None:
        groups.append({"title": current_title, "items": current_items})

    return groups


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "缺少方案文本参数"}, ensure_ascii=False))
        sys.exit(1)

    plan_text = sys.argv[1]
    groups = _parse_plan_text(plan_text)

    if not groups:
        print(json.dumps({"status": "error", "message": "方案文本解析失败，未识别到任何段落"}, ensure_ascii=False))
        sys.exit(1)

    plan_json = json.dumps({"groups": groups}, ensure_ascii=False)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS protection_plans ("
            "id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1), "
            "plan_text TEXT NOT NULL DEFAULT '', "
            "plan_json TEXT NOT NULL DEFAULT '{}', "
            "updated_at TEXT NOT NULL"
            ")"
        )
        conn.execute(
            "INSERT INTO protection_plans (id, plan_text, plan_json, updated_at) "
            "VALUES (1, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET plan_text = excluded.plan_text, "
            "plan_json = excluded.plan_json, updated_at = excluded.updated_at",
            (plan_text, plan_json, now),
        )
        conn.commit()
    finally:
        conn.close()

    print(json.dumps({"status": "ok", "updated_at": now}, ensure_ascii=False))


if __name__ == "__main__":
    main()
