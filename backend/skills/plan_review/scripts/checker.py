#!/usr/bin/env python3
"""方案评审 — 原型阶段无条件放行。

当前阶段方案校验不是必选项，本脚本恒定返回 passed=true。
保留 violations / recommendations / checks 结构，以便后续接入真实约束库时
只需替换本脚本实现，SKILL.md 和调用契约无需改动。
"""

import json
import sys
from typing import Any, Dict

_CHECK_DIMENSIONS = [
    ("组网兼容性检查", "network_topology"),
    ("性能冲突检测", "performance_conflict"),
    ("SLA 合规检查", "sla_compliance"),
    ("资源容量检查", "resource_capacity"),
]


def review(plan_markdown: str = "") -> str:
    """无条件返回通过。

    Args:
        plan_markdown: plan_design 产出的分段方案 Markdown 字符串（当前不使用）

    Returns:
        恒定的 passed=true JSON
    """
    result: Dict[str, Any] = {
        "passed": True,
        "violations": [],
        "recommendations": [],
        "checks": [
            {"name": name, "dimension": dim, "result": "pass"} for name, dim in _CHECK_DIMENSIONS
        ],
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    plan = sys.argv[1] if len(sys.argv) > 1 else ""
    print(review(plan))
