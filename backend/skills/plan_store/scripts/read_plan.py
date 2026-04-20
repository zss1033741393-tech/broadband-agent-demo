#!/usr/bin/env python3
"""读取当前保障方案。

从 data/api.db 的 protection_plans 表读取方案文本，
无记录时返回默认方案。输出 JSON 到 stdout。
"""

import json
import sqlite3
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "api.db"

_DEFAULT_PLAN_TEXT = (
    "AP补点推荐：\n"
    "    WIFI信号仿真：False\n"
    "    应用卡顿仿真：False\n"
    "    AP补点推荐：False\n"
    "\n"
    "CEI体验感知：\n"
    "    CEI模型：普通\n"
    "    CEI粒度：天级\n"
    "    CEI阈值：70分\n"
    "\n"
    "故障诊断：\n"
    "    诊断场景：上网慢 | 无法上网 | 游戏卡顿 | 直播卡顿\n"
    "    偶发卡顿定界：False\n"
    "\n"
    "远程优化：\n"
    "    远程优化触发时间：定时\n"
    "    远程WIFI信道切换：True\n"
    "    远程网关重启：True\n"
    "    远程WIFI功率调优：True\n"
    "\n"
    "差异化承载：\n"
    "    差异化承载：False\n"
)


def main() -> None:
    if not _DB_PATH.exists():
        print(json.dumps({"exists": False, "plan_text": _DEFAULT_PLAN_TEXT}, ensure_ascii=False))
        return

    conn = sqlite3.connect(str(_DB_PATH))
    try:
        cur = conn.execute("SELECT plan_text FROM protection_plans WHERE id = 1")
        row = cur.fetchone()
    finally:
        conn.close()

    if row and row[0]:
        print(json.dumps({"exists": True, "plan_text": row[0]}, ensure_ascii=False))
    else:
        print(json.dumps({"exists": False, "plan_text": _DEFAULT_PLAN_TEXT}, ensure_ascii=False))


if __name__ == "__main__":
    main()
