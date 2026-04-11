# 阶段分解（Decompose）参考

InsightAgent 在 **阶段 2 — 分解（Decompose）** 把一个 Phase 拆成若干 Step，
每步有 `insight_type` + `query_config` 三元组。本文档给出步骤数量规则 + 典型
分解示例（改写自 ce-insight-2.0 decomposer.py）。

## 步骤数量要求（根据里程碑自适应）

| 里程碑类型 | 步骤数 | 说明 |
|---|---|---|
| **简单查询** | 1-3 步 | 里程碑是具体数据输出（"列出 Top 3"、"找出最差 N 个"）— 优先 NL2Code 一步搞定 |
| **根因分析** | 4-8 步 | 里程碑含"分析原因"、"定位根因"、"验证因果" — 至少 1 次 Correlation / CrossMeasureCorrelation |
| **探索性分析** | 3-6 步 | 里程碑是"全网扫描"、"异常模式识别"、"整体评估" — 包含分布 + 异常 + 基础相关 |

**判断原则**：
- 里程碑含"无需分析原因"、"只需输出"、"只要找出" → 简单查询类
- 里程碑含"分析"、"定位"、"验证"、"为什么" → 根因/探索类
- **宁可少而精准，不要多而冗余**。每步都必须为里程碑服务

## Layer 3 根因分析 fewshot（关键！）

**已知**：前序 Phase 发现 `ODN_score` 在某些 portUuid 上最低。

**正确做法**（本 Phase 进入 L3，用细化字段）：
```
Step 1: OutstandingMax  measures=[bipHighCnt, fecHighCnt, oltRxPowerHighCnt]
          → 看哪个 HighCnt 最高
Step 2: OutlierDetection  measures=[oltRxPowerPercent]
          → 光功率越限占比的异常分布
Step 3: OutlierDetection  measures=[bipPercent]
          → BIP 误码占比的异常分布
Step 4: CrossMeasureCorrelation  measures=[bipHighCnt, fecHighCnt, oltRxPowerHighCnt]
          → 看这几个字段是否联动
Step 5: ChangePoint  breakdown=date  measures=[最异常的那个字段]
          → 看时间突变点
```

**错误做法**（禁止）：
```
measures 继续用 ODN_score 或 CEI_score —— 那是 Layer 2 已经做完的事
```

### Layer 3 步骤分配建议

- **60%** OutstandingMax / OutlierDetection 在细化字段上找异常
- **20%** CrossMeasureCorrelation / Correlation 分析字段间关系
- **20%** Trend / ChangePoint 看最异常字段的时间演化

## 下钻实体使用

如果前序 Phase 产出了 `found_entities`（如 `portUuid: ["uuid-a", "uuid-b"]`），
本 Phase 的步骤应用 `IN` 过滤这些真实值而不是写 `dimensions: [[]]`：

```json
"dimensions": [[{
  "dimension": {"name": "portUuid", "type": "DISCRETE"},
  "conditions": [{"oper": "IN", "values": ["uuid-a", "uuid-b"]}]
}]]
```

**判断筛选字段**：
- 光路 / ODN / 速率问题 → 用 `portUuid`
- 网关 / Wifi / CPU 问题 → 用 `gatewayMac`

**例外**：只有当步骤目的是"找新的异常"或"对比全网基线"时才用 `dimensions: [[]]`。

## 步骤 JSON 结构

InsightAgent 生成的 Step 数组格式：

```json
[
  {
    "step": 1,
    "insight_types": ["Trend"],
    "query_config": {
      "dimensions": [[]],
      "breakdown": {"name": "date", "type": "ORDERED"},
      "measures": [{"name": "CEI_score", "aggr": "AVG"}]
    },
    "output_ref": "step1_output",
    "rationale": "分析 CEI 得分随时间的变化趋势"
  },
  {
    "step": 2,
    "insight_types": ["OutstandingMin"],
    "query_config": {
      "dimensions": [[]],
      "breakdown": {"name": "portUuid", "type": "UNORDERED"},
      "measures": [{"name": "CEI_score", "aggr": "AVG"}]
    },
    "output_ref": "step2_output",
    "rationale": "找出 CEI 得分最低的 PON 口"
  }
]
```

### NL2Code 步骤格式
```json
{
  "step": 1,
  "insight_types": ["NL2Code"],
  "code_prompt": "从 df 中取 CEI_score 最低的前 3 个 portUuid",
  "generated_code": "result = df.nsmallest(3, 'CEI_score')",
  "query_config": {
    "dimensions": [[]],
    "breakdown": {"name": "portUuid", "type": "UNORDERED"},
    "measures": [{"name": "CEI_score", "aggr": "AVG"}]
  },
  "output_ref": "step1_output",
  "rationale": "OutstandingMin 只返回最小值一个，用 NL2Code 直接取 Top 3"
}
```

- `generated_code` 由 InsightAgent **直接写出**（而非委托给另一个 LLM）
- 代码必须把结果赋给 `result` 变量
- `query_config` 必须独立查询原始数据，**不能**在 `dimensions.conditions.values` 里引用 `stepN_output` 变量

## 格式硬约束

- `dimensions` 不筛选时 **必须** 写 `[[]]`（空的双层方括号）
- `dimensions` 有筛选时 **必须** 写 `[[{...}]]`（双层方括号内含 dim_cond）
- 🔴 **禁止** `[[{"dimension":..., "conditions":[]}]]`（空 conditions 非法）
- 🔴 **禁止** `values: []`（等于无效过滤）
- `breakdown.type`：`ORDERED` 或 `UNORDERED`
- `measures.aggr`：`SUM` / `AVG` / `COUNT` / `MIN` / `MAX`
- `output_ref` 格式：`stepN_output`
- `insight_types` 数组里只放一种方法
- 不使用 placeholder / 占位符，未知具体值时 `dimensions: [[]]`
