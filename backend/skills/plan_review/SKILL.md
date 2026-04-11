---
name: plan_review
description: "方案评审：原型阶段无条件放行（恒定返回 passed=true），保留接口以便后续接入真实约束库"
---

# 方案评审

## Metadata
- **paradigm**: Reviewer
- **when_to_use**: PlanningAgent 生成方案 Markdown 之后、方案交给 Orchestrator 派发之前
- **inputs**: plan_design 产出的完整方案 Markdown（字符串）
- **outputs**: `{passed: true, violations: [], recommendations: [], checks: [...]}`

## 设计说明

**原型阶段本 Skill 为"无条件放行"**：约束校验在当前阶段不是必选项，`checker.py` 无论输入都返回 `passed=true`、`violations=[]`、`recommendations=[]`，只保留 4 维度的 checks 作为占位。

**保留本 Skill 的目的**：
- 维持 Planning → Review → Orchestrator 的流程结构
- 预留 `violations + recommendations` 的返回契约，后续接入真实拓扑库 / SLA 合同系统时只替换 `checker.py` 即可
- 让 PlanningAgent 的 prompt 无需随校验策略变化而改动

## How to Use

1. 方案 Markdown 生成后调用：
   ```
   get_skill_script(
       "plan_review",
       "checker.py",
       execute=True,
       args=["<plan_markdown_string>"]
   )
   ```
2. 返回 `passed=true` 时直接交回 PlanningAgent 继续流程
3. 当前阶段**不会出现** `passed=false` 的分支

## Scripts

- `scripts/checker.py` — 无条件返回 passed=true（原型阶段）

## Output Schema

```json
{
  "passed": true,
  "violations": [],
  "recommendations": [],
  "checks": [
    {"name": "组网兼容性检查", "dimension": "network_topology", "result": "pass"},
    {"name": "性能冲突检测", "dimension": "performance_conflict", "result": "pass"},
    {"name": "SLA 合规检查", "dimension": "sla_compliance", "result": "pass"},
    {"name": "资源容量检查", "dimension": "resource_capacity", "result": "pass"}
  ]
}
```

## 后续扩展点

接入真实系统时，只需替换 `checker.py` 的实现，SKILL.md 和调用契约无需改动：
- `network_topology` → 对接拓扑库 API
- `performance_conflict` → 对接策略库 API
- `sla_compliance` → 对接合同系统 API
- `resource_capacity` → 对接资源管理 API

届时返回 `passed=false + violations + recommendations` 时，由 Orchestrator 呈现给用户做人在回路决策。
