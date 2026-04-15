---
name: wifi_simulation
description: "家宽 WIFI 仿真：内嵌户型预设 → AP 补点前后对比（RSSI 热力图 + 卡顿率栅格），输出 2 张对比 PNG + 4 份 JSON 矩阵"
---

# WIFI 仿真

## Metadata
- **paradigm**: Pipeline + Generator（脚本内部串行调用仿真引擎，对 Agent 表现为一次调用；脚本 stdout 为结构化 JSON 原样透传）
- **when_to_use**: `provisioning-wifi` 需要按方案段落执行 WIFI 信号仿真 / 卡顿率栅格 / AP 补点推荐
- **inputs**: 仿真参数 JSON（户型、AP 数、目标 AP 数、栅格）
- **outputs**: `image_paths`（2 张对比 PNG）+ `data_paths`（4 份 JSON 矩阵，补点前/后 × RSSI/卡顿率）+ `stats` 摘要 + `summary`

## Parameter Schema

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `preset` | string | 否 | `"大平层"` | 户型预设：`一居室` / `两居室` / `三居室` / `大平层` |
| `ap_count` | int | 否 | `1` | 当前 AP 数量（`>=1`） |
| `target_ap_count` | int | 否 | `3` | 补点后目标 AP 数，必须 `> ap_count` |
| `grid_size` | int | 否 | `40` | 栅格分辨率 NxN，推荐 `20` ~ `60`；越大越慢 |
| `show_doors` | bool | 否 | `true` | 是否渲染门洞（仅大平层有效；墙体替换为精细分段版，信号更真实） |

方案段落 → 参数映射（由 Plan 提供，Provisioning 按 schema 提参即可，本 Skill 不做业务判断）：

| 方案段落 | 参数 |
|---|---|
| `WIFI信号仿真: True` 或 `应用卡顿仿真: True` 或 `AP补点推荐: True` | 无需额外字段（使用默认值即可） |
| 指定目标 AP 数（如"补到 3 个 AP"） | `target_ap_count=3` |
| 栅格调整（如"用 20×20 栅格"） | `grid_size=20` |

## 产物说明

每次调用始终产出以下内容：

| 类型 | 数量 | 说明 |
|---|---|---|
| 对比 PNG | 2 张 | RSSI 对比图（补点前/后并排）、卡顿率对比图（补点前/后并排） |
| JSON 矩阵 | 4 份 | 补点前 RSSI、补点后 RSSI、补点前卡顿率、补点后卡顿率 |

每张图显式带 `kind`（`"rssi"` 或 `"stall"`），每份 JSON 显式带 `kind` + `phase`（`"before"` / `"after"`）。

## When to Use

- ✅ Provisioning 接收方案段落含 `WIFI信号仿真: True`、`应用卡顿仿真: True`、`AP补点推荐: True` 任一
- ✅ 场景 3 单点：用户明确要求"做 WIFI 仿真"、"看覆盖热力图"、"补点"、"换栅格分辨率"
- ❌ 用户只是问 WIFI 原理、PON 原理等概念
- ❌ 用户需要 FAN 切片 / 体验保障（走 `experience_assurance`）

## How to Use

1. 按方案段落构造参数 JSON（未出现的字段使用默认值）
2. 调用脚本：
   ```python
   get_skill_script(
       "wifi_simulation",
       "simulate.py",
       execute=True,
       args=["<params_json_string>"]
   )
   ```
3. `args` 必须是 `List[str]`，列表仅含一个 JSON 字符串元素
4. 脚本 stdout 为**单行** JSON；原样透传给用户，不得改写、截断、加注释

## Output Protocol

```json
{
  "skill": "wifi_simulation",
  "status": "ok",
  "preset": "大平层",
  "grid_size": 40,
  "ap_count": 1,
  "target_ap_count": 3,
  "image_paths": [
    {"label": "RSSI 对比图(补点前/后)", "path": "...rssi_comparison.png", "kind": "rssi"},
    {"label": "卡顿率对比图(补点前/后)", "path": "...stall_comparison.png", "kind": "stall"}
  ],
  "data_paths": [
    {"label": "补点前 RSSI 矩阵", "path": "...rssi_before.json", "kind": "rssi", "phase": "before"},
    {"label": "补点后 RSSI 矩阵", "path": "...rssi_after.json",  "kind": "rssi", "phase": "after"},
    {"label": "补点前 卡顿率矩阵", "path": "...stall_before.json", "kind": "stall", "phase": "before"},
    {"label": "补点后 卡顿率矩阵", "path": "...stall_after.json",  "kind": "stall", "phase": "after"}
  ],
  "stats": {
    "rssi_before": {"mean_rssi": -72.1, "worst_rssi": -90.0, "shape": [42, 42]},
    "rssi_after":  {"mean_rssi": -55.3, "worst_rssi": -78.5, "shape": [42, 42]},
    "stall_before": {"mean_stall_rate": 0.182, "max_stall_rate": 0.564, "shape": [42, 42]},
    "stall_after":  {"mean_stall_rate": 0.021, "max_stall_rate": 0.097, "shape": [42, 42]}
  },
  "summary": "大平层 1AP→3AP 补点优化完成；平均 RSSI 由 -72.1 dBm 提升至 -55.3 dBm；平均卡顿率由 18.20% 降至 2.10%"
}
```

错误路径：`{"skill":"wifi_simulation", "status":"error", "message":"..."}` 单行 JSON。

## Scripts

- `scripts/simulate.py` — 参数校验 + 引擎调用 + stdout 打包（薄外壳）
- `scripts/home_wifi_engine.py` — 自包含仿真引擎（户型预设 + FSPL+墙体衰减 + RTMP 卡顿仿真 + 贪心补点）

## References

- `references/default_wifi.yaml` — 参数默认值 / 可选值速查

## Examples

**输入（三居室，1AP 补到 3AP，栅格 20）**：

```python
get_skill_script(
    "wifi_simulation",
    "simulate.py",
    execute=True,
    args=['{"preset":"三居室","ap_count":1,"target_ap_count":3,"grid_size":20}']
)
```

**输入（大平层，默认参数）**：

```python
get_skill_script(
    "wifi_simulation",
    "simulate.py",
    execute=True,
    args=['{}']
)
```

## 禁止事项

- ❌ 不得多次 Skill 调用（一次 tool call 内完成所有能力）
- ❌ 不得改写或删除 `image_paths` / `data_paths` / `stats` 字段
- ❌ 不得在 stdout 里打印矩阵内容、进度、warning
- ❌ 不得依赖 `.npy` 文件（仅引擎内部副产物，用户只可见 `.json`）
- ❌ 业务规则（默认户型、AP 数）由 PlanningAgent 决定，Skill 不做推断
