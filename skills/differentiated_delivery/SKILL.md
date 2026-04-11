---
name: differentiated_delivery
description: "差异化承载：根据传入参数渲染切片配置与应用白名单策略，完成差异化承载开通"
---

# 差异化承载

## Metadata
- **paradigm**: Generator (参数 schema 驱动)
- **when_to_use**: ProvisioningDeliveryAgent 需要配置切片或应用白名单时
- **inputs**: JSON 参数（schema 见下）
- **outputs**: 切片配置 JSON + mock 下发结果

## Parameter Schema

| 字段 | 类型 | 必填 | 默认值 | 允许值 | 说明 |
|---|---|---|---|---|---|
| `slice_type` | string | 是 | `application_slice` | `application_slice` / `appflow_traffic_shaping` / `user_slice` | 切片类型 |
| `target_app` | string | 是 | `通用` | — | 保障应用名（如"抖音"、"王者荣耀"、"视频类流量(综合)"） |
| `whitelist` | list[string] | 否 | `[]` | — | 域名/IP 白名单（加入优先转发） |
| `bandwidth_guarantee_mbps` | int | 否 | `30` | 0-10000 | 保障带宽 Mbps |

## When to Use

- ✅ Provisioning 接收方案段落含"差异化承载方案: **启用**: true"
- ✅ 场景 3 单点指令：用户要求"开通抖音切片"或"Appflow 流量整形" — 任务头 `[任务类型: 差异化承载开通]`
- ❌ 用户只是问切片概念（直接回答）

## How to Use

1. ProvisioningAgent 按 schema 组装参数 JSON
2. 调用脚本：
   ```
   get_skill_script(
       "differentiated_delivery",
       "render.py",
       execute=True,
       args=["<params_json_string>"]
   )
   ```
3. 脚本渲染配置 + mock 下发，返回 `{params, config_json, dispatch_result}` JSON
4. 透传给用户展示

## Scripts

- `scripts/render.py` — 模板渲染 + mock 下发

## References

- `references/slice_config.json.j2` — 切片配置 Jinja2 模板

## Examples

**输入**:
```json
{
  "slice_type": "application_slice",
  "target_app": "抖音",
  "whitelist": ["douyin.com", "*.douyinstatic.com"],
  "bandwidth_guarantee_mbps": 50
}
```

**输出**:
```json
{
  "skill": "differentiated_delivery",
  "params": {...},
  "config_json": "{ ... 切片配置 ... }",
  "dispatch_result": {"status": "success", "slice_id": "SLICE-..."}
}
```

## 禁止事项

- ❌ 不推断应用白名单（白名单列表由 PlanningAgent 或用户显式指定）
- ❌ 不得在用户未指定应用时自动选择（应向用户追问）
