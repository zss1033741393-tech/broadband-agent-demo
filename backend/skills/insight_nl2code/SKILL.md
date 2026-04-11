---
name: insight_nl2code
description: "NL2Code 沙箱：执行 InsightAgent 编写的 pandas 代码，用于 12 种洞察函数无法覆盖的自定义分析"
---

# NL2Code 沙箱

## Metadata
- **paradigm**: Tool Wrapper
- **when_to_use**: 当 12 种洞察函数无法满足分析需求时（如 Top N 查询、多列自定义比较）
- **inputs**: payload JSON（code + query_config + table_level）
- **outputs**: 结构化 JSON（result + description）

## When to Use
- ✅ Top N / Bottom N 查询（`df.nsmallest(3, col)`）
- ✅ 自定义多列比较、排序、组合计算
- ✅ 12 种洞察函数都无法表达的定制分析
- ❌ 能用 OutstandingMin/Max/Correlation 等洞察函数直接做的分析（优先用 `insight_query`）

## How to Use

```
get_skill_script(
    "insight_nl2code",
    "run_nl2code.py",
    execute=True,
    args=["<payload_json_string>"]
)
```
payload：
```json
{
  "code": "result = df.nsmallest(3, 'CEI_score')",
  "query_config": {
    "dimensions": [[]],
    "breakdown": {"name": "portUuid", "type": "UNORDERED"},
    "measures": [{"name": "CEI_score", "aggr": "AVG"}]
  },
  "table_level": "day",
  "code_prompt": "取 CEI 最低的前 3 个 PON 口"
}
```

### 返回格式
```json
{
  "status": "ok",
  "skill": "insight_nl2code",
  "op": "run_nl2code",
  "result": {"type": "dataframe", "shape": [3, 2], "columns": [...], "records": [...]},
  "description": "NL2Code 分析完成 — 取 CEI 最低的前 3 个 PON 口；结果 3 行 x 2 列",
  "code": "result = df.nsmallest(3, 'CEI_score')",
  "data_shape": [3857, 2]
}
```

### 代码约束
- 🔴 **禁止 `import` 语句**（`pd`、`np` 和所有 Python 内置函数已在沙箱中可用）
- 🔴 **`query_config.measures` 决定了 df 有哪些列**：想访问 `Stability_score` 就必须在 measures 里写
- 结果必须赋值给 `result` 变量
- 禁止 `open` / `exec` / `eval` / 魔术属性

## Scripts
- `scripts/run_nl2code.py` — 三元组查询 + 沙箱执行 pandas 代码

## References
- `references/nl2code_spec.md` — 沙箱规范、代码约束、正确/错误示例
