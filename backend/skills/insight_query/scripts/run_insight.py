#!/usr/bin/env python3
"""洞察函数执行脚本 — data_insight Skill 的执行单元之二。

先按三元组查询数据，再对结果调用 ce_insight_core.run_insight()。

输入（argv[1]）：JSON 字符串，形如
    {
        "insight_type": "OutstandingMin",
        "query_config": {三元组},
        "table_level": "day" | "minute",
        "value_columns": ["CEI_score", ...],   // 可选；不传则从 measures 推导
        "group_column": "portUuid",            // 可选；不传则从 breakdown 推导
        "data_path": "mock",
        "phase_id": 1,                         // 可选；由 InsightAgent 传入，用于前端关联
        "step_id": 1,                          // 可选；由 InsightAgent 传入，用于前端关联
        "phase_name": "L1-定位低分PON口",      // 可选；MacroPlan phases[i].name
        "step_name": "找出 CEI_score 最低的 PON 口"  // 可选；Step 数组的 rationale
    }

输出（stdout）：JSON 字符串，形如
    {
        "status": "ok" | "error",
        "skill": "insight_query",
        "op": "run_insight",
        "insight_type": "...",
        "significance": 0.0-1.0,
        "description": str | dict,
        "filter_data": [...最多 50 条...],
        "chart_configs": {ECharts option},
        "fix_warnings": [...],
        "found_entities": {"portUuid": [...]},
        "data_shape": [row, col],
        "phase_id": int | null,
        "step_id": int | null,
        "phase_name": str | null,
        "step_name": str | null
    }

`chart_configs` 原样透传 ce_insight_core 的 ECharts option，**禁止改写**。
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
                "op": "run_insight",
                "error": f"ce_insight_core 未安装: {exc}",
            },
            ensure_ascii=False,
        )
    )
    sys.exit(1)

_MAX_RECORDS = 15


def _safe_parse_json(raw: str) -> dict:
    """带修复的 JSON 解析：先直接解析，失败则尝试修复常见 shell 转义损坏后重试。

    agno 的 get_skill_script 在 Windows 上把 JSON 作为命令行参数传递时，
    嵌套引号可能被 shell 吃掉或替换。本函数尝试以下修复：
    1. 去除首尾可能残留的单引号包裹
    2. 把被 shell 替换成单引号的双引号恢复
    3. 修复 Windows cmd 吃掉双引号后的裸键值（key: value → "key": "value"）
    4. 用 json_repair 库兜底（如果可用）
    """
    # 第 0 层：直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 第 1 层：去除首尾单引号包裹
    stripped = raw.strip()
    if stripped.startswith("'") and stripped.endswith("'"):
        stripped = stripped[1:-1]
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

    # 第 2 层：Windows cmd 有时会吃掉 \" 变成空，尝试修复常见模式
    # 例如 {insight_type: OutstandingMin} → {"insight_type": "OutstandingMin"}
    repaired = raw
    # 修复未加引号的键名
    repaired = re.sub(r"(?<=[{,])\s*([a-zA-Z_]\w*)\s*:", r' "\1":', repaired)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # 第 3 层：尝试 json_repair 库（pip install json-repair）
    try:
        from json_repair import repair_json

        repaired_str = repair_json(raw, return_objects=False)
        return json.loads(repaired_str)
    except (ImportError, Exception):
        pass

    # 第 4 层：尝试读取 stdin（如果 argv 解析失败，agno 可能通过 stdin 传数据）
    if not sys.stdin.isatty():
        try:
            stdin_data = sys.stdin.read().strip()
            if stdin_data:
                return json.loads(stdin_data)
        except Exception:
            pass

    # 全部失败，抛出原始错误
    return json.loads(raw)  # 会抛 JSONDecodeError


def _resolve_data_path(table_level: str) -> str:
    """从 configs/data_paths.yaml 读取天表/分钟表路径。找不到配置文件时回退到 'mock'。"""
    try:
        import yaml

        config_path = Path(__file__).resolve().parents[3] / "configs" / "data_paths.yaml"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            key = "minute_table_path" if table_level == "minute" else "day_table_path"
            path = cfg.get(key, "mock") or "mock"
            return path
    except Exception:
        pass
    return "mock"


def run(payload_json: str) -> str:
    """主入口：解析 payload → 查询 → 执行洞察 → 序列化。"""
    try:
        payload: dict[str, Any] = _safe_parse_json(payload_json)
    except json.JSONDecodeError as exc:
        return _err(f"payload JSON 解析失败: {exc}")

    insight_type = payload.get("insight_type")
    if not insight_type:
        return _err("payload 缺少 insight_type")

    query_config = payload.get("query_config")
    if not isinstance(query_config, dict):
        return _err("payload 缺少 query_config 或类型非 dict")

    table_level = payload.get("table_level", "day")
    if table_level not in ("day", "minute"):
        return _err(f"table_level 必须是 day/minute，收到: {table_level}")

    data_path = payload.get("data_path") or _resolve_data_path(table_level)

    # 1. 修复三元组（query_fixer 可能替换字段名 / breakdown 名 / measures 名）
    try:
        fixed_config, fix_warnings = cic.fix_query_config(query_config, table_level=table_level)
    except Exception as exc:
        return _err(f"fix_query_config 失败: {type(exc).__name__}: {exc}")

    # 兜底：fixer 意外清空 measures 时还原为原始值，确保 SQL 带聚合列
    if not fixed_config.get("measures"):
        fixed_config["measures"] = query_config.get("measures", [])

    # 2. 从**修复后**的 config 推导默认的 value_columns / group_column
    #    （用 fixed_config 而非 query_config，确保 query_fixer 的字段替换被同步，
    #    避免后续 NEEDS_GROUP 检查时拿到原始字段名而 df 列名是修复后的，导致误报）
    default_value_cols = [m.get("name") for m in fixed_config.get("measures", []) if m.get("name")]
    # 兜底：fixer 清空 measures 时，回退到原始 query_config 的 measures
    if not default_value_cols:
        default_value_cols = [m.get("name") for m in query_config.get("measures", []) if m.get("name")]
    default_group_col = fixed_config.get("breakdown", {}).get("name", "")

    value_columns = payload.get("value_columns") or default_value_cols
    group_column = payload.get("group_column") or default_group_col

    if not value_columns:
        return _err("无法从 payload 或 fixed_config.measures 推导 value_columns")

    # 3. 查询
    try:
        dfs = cic.query_subject_pandas(fixed_config, data_path)
    except Exception as exc:
        return _err(f"查询失败: {type(exc).__name__}: {exc}")

    if not dfs or dfs[0].empty:
        return _err("查询返回空 DataFrame")

    df = dfs[0]

    # 4. 列名兜底：修复后的字段名可能与 fixed_config 里的还有细微差异（如聚合后缀），
    #    做最后一层模糊匹配（startswith 前缀匹配）
    value_columns = _resolve_columns(df, value_columns)

    # 2. 执行洞察
    try:
        result = cic.run_insight(
            insight_type=insight_type,
            df=df,
            value_columns=value_columns,
            group_column=group_column,
        )
    except ValueError as exc:
        return _err(f"未知 insight_type: {exc}")
    except Exception as exc:
        return _err(f"run_insight 失败: {type(exc).__name__}: {exc}")

    # 3. 提取 found_entities（供后续 step 下钻使用）
    found_entities = _extract_entities(df, group_column, result.get("filter_data", []))

    # 4. 组装输出
    filter_data = result.get("filter_data", [])[:_MAX_RECORDS]
    output: dict[str, Any] = {
        "status": "ok",
        "skill": "insight_query",
        "op": "run_insight",
        "insight_type": result.get("insight_type", insight_type),
        "significance": result.get("significance", 0.0),
        "description": result.get("description", ""),
        "filter_data": filter_data,
        "chart_configs": result.get("chart_configs", {}),
        "fix_warnings": fix_warnings,
        "found_entities": found_entities,
        "data_shape": list(df.shape),
        "value_columns_used": value_columns,
        "group_column_used": group_column,
        "phase_id": payload.get("phase_id"),
        "step_id": payload.get("step_id"),
        "phase_name": payload.get("phase_name"),
        "step_name": payload.get("step_name"),
    }
    return json.dumps(output, ensure_ascii=False, default=_json_default)


def _resolve_columns(df: Any, cols: list[str]) -> list[str]:
    """若 df 中不存在 col，尝试前缀匹配（如 'CEI_score' → 'CEI_score_avg'）。"""
    resolved: list[str] = []
    available = list(df.columns)
    for col in cols:
        if col in available:
            resolved.append(col)
            continue
        candidates = [c for c in available if c.startswith(col + "_") or c == col]
        if candidates:
            resolved.append(candidates[0])
        else:
            resolved.append(col)  # 保留原名，让 run_insight 返回结构化错误
    return resolved


def _extract_entities(df: Any, group_column: str, filter_data: list[dict]) -> dict[str, list[str]]:
    """从 filter_data 提取分组字段的前 N 个值，供后续 step 下钻筛选使用。"""
    if not group_column or not filter_data:
        return {}
    values: list[str] = []
    for row in filter_data[:10]:
        v = row.get(group_column)
        if v is not None and v not in values:
            values.append(str(v))
    return {group_column: values} if values else {}


def _err(msg: str) -> str:
    return json.dumps(
        {
            "status": "error",
            "skill": "insight_query",
            "op": "run_insight",
            "error": msg,
        },
        ensure_ascii=False,
    )


def _json_default(obj: Any) -> Any:

    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "item"):
        try:
            return obj.item()
        except Exception:
            return str(obj)
    return str(obj)


if __name__ == "__main__":
    _payload = sys.argv[1] if len(sys.argv) > 1 else "{}"
    print(run(_payload))
