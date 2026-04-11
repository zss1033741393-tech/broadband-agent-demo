---
name: goal_parsing
description: "目标解析：通过决策树追问收集综合目标所需的 7 个核心槽位，产出结构化画像 JSON"
---

# 目标解析

## Metadata
- **paradigm**: Inversion + Pipeline
- **when_to_use**: PlanningAgent 接到综合目标类输入、需要先收集完整画像时
- **inputs**: 用户自然语言描述 + 当前槽位状态 JSON
- **outputs**: 更新后的槽位状态 JSON，含 `is_complete` 与 `next_questions`

## When to Use

- ✅ 用户描述综合性业务目标（如"直播套餐用户，保障直播"），需要收集完整画像
- ✅ 单用户故障保障场景（场景 1），需要 user_type/package_type/scenario/guarantee_target/time_window 等
- ❌ 数据洞察回流场景 — Orchestrator 已注入 insight 摘要作为 hints，PlanningAgent 可直接推断，**不必调用本 Skill**
- ❌ 具体功能单点调用 — 场景 3 由 Orchestrator 直达 Provisioning，不经过 Planning
- ❌ 用户只是问概念或澄清（直接回答即可）

## 必填槽位与依赖

| 槽位 | 类型 | 枚举/示例 | 依赖 |
|---|---|---|---|
| `user_type` | enum | 主播用户 / 游戏用户 / VVIP用户 | — |
| `package_type` | enum | 普通套餐 / 直播套餐 / 专线套餐 | — |
| `scenario` | enum | 家庭直播 / 卖场走播 / 楼宇直播 | depends_on `package_type`（分支枚举） |
| `guarantee_target` | enum | 家庭网络 / STA级 / 整网 | — |
| `time_window` | string | 18:00-22:00 / 全天 | — |
| `guarantee_app` | string | 抖音 / 王者荣耀 / … | 可选 |
| `complaint_history` | bool | 是 / 否 | 可选 |

槽位完整 schema 定义在 `references/slot_schema.yaml`。

## How to Use

1. **初始化状态**：首次调用时 `current_state_json = "{}"`；后续调用把上一轮返回的 `state` 字段作为新的 `current_state_json`。
2. **调用脚本**：
   ```
   get_skill_script(
       "goal_parsing",
       "slot_engine.py",
       execute=True,
       args=["<user_input>", "<current_state_json>"]
   )
   ```
3. **读取返回**：脚本返回 JSON，包含以下字段
   - `state`：已填充的槽位
   - `is_complete`：所有必填槽位是否齐全
   - `missing_slots`：仍缺失的槽位名列表
   - `next_questions`：一批（≤3 个）待追问的槽位说明
4. **追问策略**：
   - `is_complete=false` 时，把 `next_questions` 用自然语言一次性问给用户（2-3 个槽位合并一句问话，不要逐个问）
   - 用户回答后，带着用户原话和上一轮 `state` 再次调用脚本
5. **完成条件**：`is_complete=true` 时，把完整 `state` 作为画像传回 PlanningAgent 主流程，进入 `plan_design`
6. **约束**：本 Skill 只负责"槽位齐全性"判定，**不做业务规则判断**（如"直播套餐默认阈值多少"等业务知识由 `plan_design` LLM 决策）

## Scripts

- `scripts/slot_engine.py` — 读取 slot_schema.yaml，按状态机规则解析用户输入、产出追问列表

## References

- `references/slot_schema.yaml` — 槽位定义（字段、类型、枚举、依赖关系）

## Examples

**输入**: "直播套餐卖场走播用户，18:00-22:00 保障抖音直播"

**第一轮调用**: `args=["直播套餐卖场走播用户，18:00-22:00 保障抖音直播", "{}"]`

**返回**:
```json
{
  "state": {
    "package_type": "直播套餐",
    "scenario": "卖场走播",
    "time_window": "18:00-22:00",
    "guarantee_app": "抖音"
  },
  "is_complete": false,
  "missing_slots": ["user_type", "guarantee_target"],
  "next_questions": [
    {"slot_name": "user_type", "prompt": "请问您是哪类用户？（主播用户 / 游戏用户 / VVIP用户）"},
    {"slot_name": "guarantee_target", "prompt": "您希望保障的范围是？（家庭网络 / STA级 / 整网）"}
  ]
}
```

PlanningAgent 把两个追问合并一句问给用户，等回答后再次调用 `slot_engine.py`，直至 `is_complete=true`。
