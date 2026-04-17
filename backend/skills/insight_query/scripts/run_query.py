#!/usr/bin/env python3
"""三元组数据查询脚本 — data_insight Skill 的执行单元之一。

输入（argv[1]）：JSON 字符串，形如
    {
        "query_config": {三元组},
        "table_level": "day" | "minute",
        "data_path": "mock"  // 可选，mock 模式下忽略
    }

输出（stdout）：JSON 字符串，形如
    {
        "status": "ok" | "error",
        "skill": "insight_query",
        "op": "run_query",
        "fixed_query_config": {...},
        "fix_warnings": [...],
        "data_shape": [row, col],
        "columns": [...],
        "records": [...最多 50 条...],
        "summary": "文字摘要"
    }

**禁止**：脚本内不做 LLM 调用、不做业务规则判断、不改写 fix_warnings。
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

# Windows 兼容：保留默认编码（Linux/Mac 是 UTF-8，Windows 是 GBK），
# 遇到不可编码字符（如 emoji）替换为 ? 而不是抛 UnicodeEncodeError 崩溃
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

try:
    import ce_insight_core as cic
except ImportError as exc:
    print(
        json.dumps(
            {
                "status": "error",
                "skill": "insight_query",
                "op": "run_query",
                "error": f"ce_insight_core 未安装: {exc}",
            },
            ensure_ascii=False,
        )
    )
    sys.exit(1)

_MAX_RECORDS = 15


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
    # 第 1.5 层：修复 LLM 将 args 列表结束符 ] 混入 JSON 对象末尾
    _candidate = raw.strip()
    if _candidate.startswith("{") and _candidate.endswith("]"):
        try:
            return json.loads(_candidate[:-1] + "}")
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


def _resolve_data_path(table_level: str) -> str:
    """从 configs/data_paths.yaml 读取天表/分钟表路径。找不到配置文件时回退到 'mock'。"""
    try:
        import yaml

        config_path = Path(__file__).resolve().parents[3] / "configs" / "data_paths.yaml"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            key = "minute_table_path" if table_level == "minute" else "day_table_path"
            return cfg.get(key, "mock") or "mock"
    except Exception:
        pass
    return "mock"


def run(payload_json: str) -> str:
    """主入口：解析 payload → 修复三元组 → 查询 → 序列化结果。"""
    try:
        payload: dict[str, Any] = _safe_parse_json(payload_json)
    except json.JSONDecodeError as exc:
        return _err(f"payload JSON 解析失败: {exc}")

    query_config = payload.get("query_config")
    if not isinstance(query_config, dict):
        return _err("payload 缺少 query_config 或类型非 dict")

    table_level = payload.get("table_level", "day")
    if table_level not in ("day", "minute"):
        return _err(f"table_level 必须是 day/minute，收到: {table_level}")

    data_path = payload.get("data_path") or _resolve_data_path(table_level)

    try:
        fixed_config, fix_warnings = cic.fix_query_config(query_config, table_level=table_level)
    except Exception as exc:
        return _err(f"fix_query_config 失败: {type(exc).__name__}: {exc}")

    # 兜底：fixer 意外清空 measures 时还原为原始值，确保 SQL 带聚合列
    if not fixed_config.get("measures"):
        fixed_config["measures"] = query_config.get("measures", [])

    try:
        dfs = cic.query_subject_pandas(fixed_config, data_path)
    except Exception as exc:
        return _err(f"查询失败: {type(exc).__name__}: {exc}")

    if not dfs:
        return _ok(
            fixed_config=fixed_config,
            fix_warnings=fix_warnings,
            shape=[0, 0],
            columns=[],
            records=[],
            summary="查询返回空 DataFrame 列表",
        )

    df = dfs[0]
    try:
        records = df.head(_MAX_RECORDS).to_dict(orient="records")
    except Exception:
        records = []
    try:
        summary = cic.summarize_dataframe(df, "查询结果")
    except Exception as exc:
        summary = f"summarize 失败: {exc}"

    return _ok(
        fixed_config=fixed_config,
        fix_warnings=fix_warnings,
        shape=list(df.shape),
        columns=list(df.columns),
        records=records,
        summary=summary,
    )


def _ok(**kwargs: Any) -> str:
    result: dict[str, Any] = {
        "status": "ok",
        "skill": "insight_query",
        "op": "run_query",
    }
    # 重命名内部 key → 对外 key，保持输出稳定
    if "fixed_config" in kwargs:
        result["fixed_query_config"] = kwargs.pop("fixed_config")
    if "shape" in kwargs:
        result["data_shape"] = kwargs.pop("shape")
    result.update(kwargs)
    return json.dumps(result, ensure_ascii=False, default=_json_default)


def _err(msg: str) -> str:
    return json.dumps(
        {
            "status": "error",
            "skill": "insight_query",
            "op": "run_query",
            "error": msg,
        },
        ensure_ascii=False,
    )


def _json_default(obj: Any) -> Any:
    """安全兜底：处理 pandas / numpy / datetime 等 json 默认不支持的类型。"""

    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "item"):  # numpy scalar
        try:
            return obj.item()
        except Exception:
            return str(obj)
    return str(obj)


if __name__ == "__main__":
    _payload = sys.argv[1] if len(sys.argv) > 1 else "{}"
    print(run(_payload))
