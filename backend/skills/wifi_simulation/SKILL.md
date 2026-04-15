---
name: wifi_simulation
description: "WIFI 仿真：户型图处理→信号覆盖仿真→网络性能仿真 3 阶段流水线，产出热力图/网络仪表盘 PNG 可视化与选点建议"
---

# WIFI 仿真

## Metadata
- **paradigm**: Pipeline (3 阶段串行：户型图→信号→网络，对 Agent 表现为一次调用)
- **when_to_use**: ProvisioningWifiAgent 需要执行 WIFI 信号覆盖仿真、AP 选点优化或查看网络性能
- **inputs**: 仿真参数 JSON（户型图路径、AP 数量、WiFi 标准等，均可选）
- **outputs**: PNG 可视化图片路径 + JSON 统计指标

## Parameter Schema

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `floor_plan_image` | string | 否 | (内置样例) | 户型图图片路径（jpg/png） |
| `ap_count` | int | 否 | `2` | AP 数量（启用自动优化选点） |
| `ap_positions` | list[string] | 否 | null | 手动 AP 坐标，如 `["5.0,5.0", "15.0,15.0"]`，与 `ap_count` 互斥 |
| `tx_power` | int | 否 | `20` | AP 发射功率 dBm |
| `frequency` | float | 否 | `5.0` | WiFi 频率 GHz |
| `wifi_standard` | string | 否 | `wifi6` | WiFi 标准：wifi4/wifi5/wifi6/wifi6e/wifi7 |
| `grid_size` | int | 否 | `400` | 栅格分辨率 |

## 内部 3 阶段流水线（由 `simulate.py` 编排）

| 阶段 | 脚本 | 功能 | 产出 |
|---|---|---|---|
| 1. 户型图处理 | `floorplan_process.py` | YOLO+RFDETR 或轮廓检测 → 400×400 grid_map | `simplified_floorplan.png` + `grid_map.npy` |
| 2. 信号仿真 | `signal_simulation.py` | COST231 传播模型 + AP 自动优化 | `rssi_heatmap.png` + `rssi_matrix.npy` |
| 3. 网络仿真 | `network_simulation.py` | SNR→MCS→吞吐量/延迟/丢包 | `network_dashboard.png` + `network_metrics.json` |

模型文件（可选）放置于 `models/` 目录：
- `models/65s.pt` — YOLO 分割模型
- `models/911checkpoint_best_ema.pth` — RFDETR 检测模型

模型文件不存在时自动使用轮廓检测备用方案。

## When to Use

- ✅ Provisioning 接收方案段落含"WIFI 仿真方案: **启用**: true"
- ✅ 场景 3 单点指令：用户要求"查看 WIFI 覆盖"或"做个仿真" — 任务头 `[任务类型: WIFI 仿真执行]`
- ❌ 用户只是问 WIFI 概念
- ❌ 用户要求 Appflow 或切片（应走 `experience_assurance`）

## How to Use

1. ProvisioningAgent 按 schema 组装参数 JSON（或传 `{}` 使用全部默认值）
2. 调用脚本：
   ```
   get_skill_script(
       "wifi_simulation",
       "simulate.py",
       execute=True,
       args=["<params_json_string>"]
   )
   ```
3. 脚本串行执行 3 阶段，产出可视化 PNG + 指标 JSON
4. 最终返回包含 `image_paths` 的完整 JSON，**Agent 透传给用户**（不得改写图片路径或指标数据）

## Output Protocol — 图片路径模式

stdout 为 JSON，包含 `image_paths` 数组，前端自动转 base64 渲染：

```json
{
  "skill": "wifi_simulation",
  "status": "ok",
  "steps": [
    {"step": 1, "name": "户型图处理", "status": "success", "result": {...}},
    {"step": 2, "name": "信号强度仿真", "status": "success", "result": {...}},
    {"step": 3, "name": "网络性能仿真", "status": "success", "result": {...}}
  ],
  "image_paths": [
    {"label": "户型识别", "path": "/abs/path/simplified_floorplan.png"},
    {"label": "信号热力图", "path": "/abs/path/rssi_heatmap.png"},
    {"label": "网络仪表盘", "path": "/abs/path/network_dashboard.png"}
  ],
  "metrics": {
    "signal": {"mean_rssi": -52.3, "min_rssi": -78.1, ...},
    "network": {"throughput": {"mean_mbps": 450.5}, "latency": {"mean_ms": 8.5}, ...}
  },
  "summary": "户型识别完成；2 AP 自动选点，平均 RSSI -52 dBm；平均吞吐量 450 Mbps, 延迟 8.5 ms"
}
```

## Scripts

- `scripts/simulate.py` — 单入口编排器，串行驱动 3 阶段
- `scripts/floorplan_process.py` — 户型图处理（YOLO+RFDETR / 轮廓检测 fallback）
- `scripts/signal_simulation.py` — COST231 信号强度仿真 + AP 自动优化
- `scripts/network_simulation.py` — WiFi 网络性能仿真（吞吐量/延迟/丢包）

## References

- `references/default_wifi.yaml` — 默认仿真参数配置
- `references/sample_floorplan.jpg` — 内置样例户型图

## Examples

**输入**：
```json
{"ap_count": 3, "wifi_standard": "wifi6", "frequency": 5.0}
```

**调用**：
```python
get_skill_script("wifi_simulation", "simulate.py", execute=True, args=['{"ap_count":3,"wifi_standard":"wifi6"}'])
```

## 禁止事项

- ❌ 不得拆成多次 Skill 调用（3 阶段在脚本内部完成）
- ❌ 不得改写或删除 `image_paths` 中的图片路径
- ❌ 不得改写 `metrics` 统计数据
