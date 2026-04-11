---
name: fault_diagnosis
description: "故障诊断配置：根据传入参数渲染故障树与白名单策略 JSON，完成故障诊断配置下发"
---

# 故障诊断

## Metadata
- **paradigm**: Generator (参数 schema 驱动)
- **when_to_use**: ProvisioningCeiChainAgent 需要配置故障诊断规则，或单点故障定界调用
- **inputs**: JSON 参数（schema 见下）
- **outputs**: 故障配置 JSON + mock 下发/定界结果

## Parameter Schema

| 字段 | 类型 | 必填 | 默认值 | 允许值 | 说明 |
|---|---|---|---|---|---|
| `fault_tree_enabled` | bool | 是 | `true` | — | 是否启用故障树推理 |
| `whitelist_rules` | list[string] | 否 | `[]` | 字符串列表 | 白名单规则（如"偶发卡顿"），加入白名单的症状不判定为持续故障 |
| `severity_threshold` | string | 是 | `warning` | `info` / `warning` / `major` / `critical` | 告警严重性阈值 |

## When to Use

- ✅ Provisioning 接收方案段落含"故障诊断方案: **启用**: true"
- ✅ 场景 3 单点指令：用户投诉卡顿，需要定界 — 任务头 `[任务类型: 单点故障诊断]`
- ✅ 完整保障链的第二步（CEI 低分时触发）
- ❌ 用户上报实际故障需要人工处理（应转人工）

## How to Use

1. ProvisioningAgent 按 schema 组装参数 JSON
2. 调用脚本：
   ```
   get_skill_script(
       "fault_diagnosis",
       "render.py",
       execute=True,
       args=["<params_json_string>"]
   )
   ```
3. 脚本读取模板生成故障配置 JSON，并附加 mock 下发或定界结果
4. 透传给用户展示

## Scripts

- `scripts/render.py` — 模板渲染 + mock 下发/定界

## References

- `references/fault_config.json.j2` — 故障配置 Jinja2 模板

## Examples

**输入**:
```json
{
  "fault_tree_enabled": true,
  "whitelist_rules": ["偶发卡顿"],
  "severity_threshold": "warning"
}
```

**输出**:
```json
{
  "skill": "fault_diagnosis",
  "params": {...},
  "config_json": "{ ... 故障规则 ... }",
  "dispatch_result": {"status": "success", "task_id": "FAULT-..."}
}
```

## 禁止事项

- ❌ 不做业务规则推断（是否开启故障树、白名单列表由 PlanningAgent 在方案段落中决定）
- ❌ 不得改写用户展示的 stdout
