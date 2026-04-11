---
name: insight_plan
description: "数据洞察规划：根据用户问题设计 2-4 个分析 Phase（L1→L2→L3→L4 四层下钻模型）"
---

# 洞察规划

## Metadata
- **paradigm**: Instructional
- **when_to_use**: InsightAgent 收到数据洞察任务后，第一步设计分析阶段（MacroPlan）
- **inputs**: 用户问题
- **outputs**: MacroPlan JSON（goal + phases 数组）

## When to Use
- ✅ 收到数据洞察任务，需要制定分析计划
- ❌ 已经有了 MacroPlan，进入 Decompose/Execute 阶段（用其他 skill）

## How to Use

1. 加载本 Skill 指令：`get_skill_instructions("insight_plan")`
2. 按需加载参考文件：`get_skill_reference("insight_plan", "plan_fewshots.md")`
3. 根据用户问题类型，在 assistant 消息中直接输出 MacroPlan JSON

**不需要调用任何脚本**。Plan 阶段只用业务知识和 fewshot 来规划，不查数据。

## 业务背景

- CEI_score 是 8 个维度得分的加权总分（Stability + ODN + Rate + Service + OLT + Gateway + STA + Wifi）
- 天表是日粒度聚合数据（字段：`_score` / `HighCnt` / `Percent`），分钟表是原始分钟级数据
- 带扣分含义的指标越小越好（各种 HighCnt、Percent、Score 字段）

## 4 层下钻模型

- **L1** `CEI_score` → 找哪些设备总分低
- **L2** 8 个维度 `_score` → 找是哪个维度拖分
- **L3** 天表维度细化字段（`HighCnt` / `Percent` 等）→ 找该维度内哪个指标是根因
- **L4** 分钟表时序 → 验证根因指标的时序分布与相关性

⚠️ **L2 和 L3 必须拆成两个独立 Phase**：L2 结束后才知道是哪个维度有问题，L3 才能针对该维度分析细化字段。

## 任务分类 → Phase 数量

| 类型 | 触发词 | Phase 数 |
|---|---|---|
| **简单查询** | "只需输出"、"只要找出"、"列出 Top N" | 1 |
| **根因分析** | "分析原因"、"为什么"、"根因" | 4（L1→L2→L3→L4） |
| **指定维度** | "WiFi 差"、"光路问题"、"ODN" | 2（L3→L4） |
| **指定设备** | 用户给了 portUuid / gatewayMac | 3（L2→L3→L4） |

## 输出格式

在 assistant 消息中输出带事件标记的 MacroPlan JSON：

```json
<!--event:plan-->
{
  "goal": "用户意图的一句话摘要",
  "total_phases": 4,
  "phases": [
    {
      "phase_id": 1,
      "name": "L1-定位低分PON口",
      "milestone": "识别CEI_score均值最低的Top N个PON口设备",
      "table_level": "day",
      "description": "使用OutstandingMin函数，以portUuid为粒度，聚合CEI_score均值",
      "focus_dimensions": []
    }
  ]
}
```

`focus_dimensions` 一般留空，仅当用户明确指定维度时才填；值必须是 8 维度之一：
`Stability / ODN / Rate / Service / OLT / Gateway / STA / Wifi`

## References
- `references/plan_fewshots.md` — 4 类任务的典型故事线（根因分析 A/B/C + 多层点查 D）

## 禁止事项
- ❌ Plan 阶段不查数据、不调脚本、不看 Schema
- ❌ 不合并 L2+L3 到同一 Phase
- ❌ 简单查询类不要画蛇添足做根因分析
