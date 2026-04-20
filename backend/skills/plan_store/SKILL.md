---
name: plan_store
description: "方案持久化：读取或保存当前用户保障方案到业务数据库，供编辑方案场景和方案确认后持久化使用"
---

# 方案持久化

## Metadata
- **paradigm**: Tool Wrapper（封装 api.db 的保障方案读写操作）
- **when_to_use**: 编辑方案场景需读取当前方案；场景 1/2 方案确认后需保存到 DB
- **inputs**: 读取：无参数 | 保存：完整 5 段式方案文本
- **outputs**: 读取：当前方案文本 JSON | 保存：成功状态 + 更新时间

## When to Use
- ✅ 场景 4 编辑方案：PlanningAgent 先 `read_plan` 获取当前方案，再应用用户编辑指令
- ✅ 场景 1/2 方案确认后：PlanningAgent 调用 `save_plan` 持久化新方案
- ❌ 场景 3 单点功能直达（不经过 Planning）

## How to Use

### 读取当前方案

```
get_skill_script(
    "plan_store",
    "read_plan.py",
    execute=True,
    args=[]
)
```

返回 JSON：
```json
{
  "exists": true,
  "plan_text": "<5 段式方案文本>"
}
```

`exists=false` 时 `plan_text` 为默认方案。

### 保存方案

```
get_skill_script(
    "plan_store",
    "save_plan.py",
    execute=True,
    args=["<plan_text_string>"]
)
```

参数为完整 5 段式方案文本（单个字符串参数）。

返回 JSON：
```json
{
  "status": "ok",
  "updated_at": "2026-04-17T12:00:00Z"
}
```

## Scripts
- `scripts/read_plan.py` — 从 data/api.db 读取当前保障方案
- `scripts/save_plan.py` — 解析 5 段式方案文本并保存到 data/api.db

## 禁止事项
- ❌ 不要在非 Planning 流程中调用（持久化由 Planning 统一管理）
- ❌ 保存时不得传入部分方案（必须是完整 5 段文本）
