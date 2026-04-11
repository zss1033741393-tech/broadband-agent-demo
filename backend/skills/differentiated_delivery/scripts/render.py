#!/usr/bin/env python3
"""差异化承载配置渲染 — 参数 schema 驱动。

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
    "slice_type": "application_slice",
    "target_app": "通用",
    "whitelist": [],
    "bandwidth_guarantee_mbps": 30,
}

_ALLOWED_SLICE_TYPES = {"application_slice", "appflow_traffic_shaping", "user_slice"}


def _validate_and_fill(params: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {**_SCHEMA_DEFAULTS, **params}
    if merged.get("slice_type") not in _ALLOWED_SLICE_TYPES:
        merged["slice_type"] = _SCHEMA_DEFAULTS["slice_type"]
    if not isinstance(merged.get("whitelist"), list):
        merged["whitelist"] = []
    try:
        merged["bandwidth_guarantee_mbps"] = int(merged["bandwidth_guarantee_mbps"])
    except (TypeError, ValueError):
        merged["bandwidth_guarantee_mbps"] = _SCHEMA_DEFAULTS["bandwidth_guarantee_mbps"]
    return merged


def _mock_dispatch(params: Dict[str, Any]) -> Dict[str, Any]:
    outcomes = [
        {
            "status": "success",
            "message": f"切片配置下发成功，{params.get('target_app', '通用')} 应用已纳入优先转发",
            "slice_id": f"SLICE-{random.randint(10000, 99999)}",
        },
        {
            "status": "success",
            "message": "Appflow 流量整形策略生效，优先级队列已更新",
            "slice_id": f"SLICE-{random.randint(10000, 99999)}",
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
        tmpl = env.get_template("slice_config.json.j2")
        config_json = tmpl.render(**merged)
    except Exception as exc:
        return json.dumps({"error": f"渲染失败: {exc}"}, ensure_ascii=False)

    result = {
        "skill": "differentiated_delivery",
        "params": merged,
        "config_json": config_json,
        "dispatch_result": _mock_dispatch(merged),
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    _params = sys.argv[1] if len(sys.argv) > 1 else "{}"
    print(render(_params))
