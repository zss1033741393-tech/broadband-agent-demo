#!/usr/bin/env python3
"""故障诊断配置渲染 — 参数 schema 驱动。

作为 agno Skill 脚本被调用。不做业务规则判断。
"""

import json
import random
import sys
from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "references"

_SCHEMA_DEFAULTS: Dict[str, Any] = {
    "fault_tree_enabled": True,
    "whitelist_rules": [],
    "severity_threshold": "warning",
}

_ALLOWED_SEVERITY = {"info", "warning", "major", "critical"}


def _validate_and_fill(params: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {**_SCHEMA_DEFAULTS, **params}
    if not isinstance(merged.get("fault_tree_enabled"), bool):
        merged["fault_tree_enabled"] = bool(merged.get("fault_tree_enabled", True))
    if not isinstance(merged.get("whitelist_rules"), list):
        merged["whitelist_rules"] = []
    if merged.get("severity_threshold") not in _ALLOWED_SEVERITY:
        merged["severity_threshold"] = _SCHEMA_DEFAULTS["severity_threshold"]
    return merged


def _mock_dispatch(params: Dict[str, Any]) -> Dict[str, Any]:
    outcomes = [
        {
            "status": "success",
            "message": "故障配置 API 下发成功",
            "task_id": f"FAULT-{random.randint(10000, 99999)}",
            "diagnosis_summary": "故障树已加载，共 3 条检测规则生效",
        },
        {
            "status": "success",
            "message": "故障诊断完成：未发现持续性故障",
            "task_id": f"FAULT-{random.randint(10000, 99999)}",
            "diagnosis_summary": "命中白名单规则，问题判定为偶发性波动",
        },
    ]
    return random.choice(outcomes)


def render(params_json: str = "{}") -> str:
    try:
        params = json.loads(params_json) if params_json else {}
    except json.JSONDecodeError:
        return json.dumps({"error": "参数 JSON 解析失败"}, ensure_ascii=False)

    merged = _validate_and_fill(params)

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )
    try:
        tmpl = env.get_template("fault_config.json.j2")
        config_json = tmpl.render(**merged)
    except Exception as exc:
        return json.dumps({"error": f"渲染失败: {exc}"}, ensure_ascii=False)

    result = {
        "skill": "fault_diagnosis",
        "params": merged,
        "config_json": config_json,
        "dispatch_result": _mock_dispatch(merged),
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    _params = sys.argv[1] if len(sys.argv) > 1 else "{}"
    print(render(_params))
