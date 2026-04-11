---
name: insight_decompose
description: "Phase 分解：查询天表/分钟表 Schema，为当前 Phase 拆解 1-8 个执行步骤（Step）"
---

# Phase 分解

## Metadata
- **paradigm**: Tool Wrapper + Instructional
- **when_to_use**: InsightAgent 进入某个 Phase 后，需要查询可用字段并设计具体的执行步骤
- **inputs**: 当前 Phase 的 milestone + table_level + focus_dimensions + 前序 Phase 的 found_entities
- **outputs**: Step 数组 JSON（每步含 insight_type + query_config 三元组）

## When to Use
- ✅ 进入某个 Phase，需要查 Schema 确认可用字段
- ✅ 需要把 Phase 拆成具体的执行步骤
- ❌ 执行洞察分析（用 `insight_query`）
- ❌ 设计分析计划（用 `insight_plan`）

## How to Use

### Step 1 — 查询 Schema（确认当前 Phase 可用的字段）
```
get_skill_script(
    "insight_decompose",
    "list_schema.py",
    execute=True,
    args=["<payload_json_string>"]
)
```
payload：
```json
{"table": "day", "focus_dimensions": ["ODN"]}
```
`focus_dimensions` 可选；为 `[]` 时返回全量 schema。

### Step 2 — 加载分解规则
按需读取参考文件：
- `get_skill_reference("insight_decompose", "decompose_fewshots.md")` — 步骤数规则 + L3 根因 fewshot
- `get_skill_reference("insight_decompose", "insight_catalog.md")` — 12 种洞察函数的 measures 约束
- `get_skill_reference("insight_decompose", "triple_schema.md")` — 三元组格式契约

### Step 3 — 生成 Step 数组
在 assistant 消息中输出 Step 数组，带事件标记：

```json
<!--event:decompose-->
{
  "phase_id": 1,
  "steps": [
    {
      "step": 1,
      "insight_types": ["OutstandingMin"],
      "query_config": {
        "dimensions": [[]],
        "breakdown": {"name": "portUuid", "type": "UNORDERED"},
        "measures": [{"name": "CEI_score", "aggr": "AVG"}]
      },
      "output_ref": "step1_output",
      "rationale": "找出 CEI_score 最低的 PON 口"
    }
  ]
}
```

### 步骤数量规则
| 里程碑类型 | 步骤数 |
|---|---|
| 简单查询（"列出 Top N"） | 1-3 步 |
| 根因分析（"分析原因"） | 4-8 步 |
| 探索性分析（"全网扫描"） | 3-6 步 |

### 下钻筛选格式（重要！）
如果前序 Phase 产出了 `found_entities`，本 Phase 的步骤必须用正确的三元组 IN 过滤格式：

**正确**：
```json
"dimensions": [[{"dimension": {"name": "portUuid", "type": "DISCRETE"}, "conditions": [{"oper": "IN", "values": ["uuid-a", "uuid-b"]}]}]]
```

**错误**（会被清除为 `[[]]`，过滤失效）：
```json
"dimensions": [["portUuid", "IN", ["uuid-a"]]]
```

## Scripts
- `scripts/list_schema.py` — 查询天表/分钟表 Schema（按 focus_dimensions 剪枝）

## References
- `references/decompose_fewshots.md` — Phase 拆分步骤数规则 + Layer 3 根因 fewshot + 下钻筛选规则
- `references/insight_catalog.md` — 12 种洞察函数的触发规则与 measures 约束
- `references/triple_schema.md` — 三元组 dimensions/breakdown/measures 契约 + 硬约束
