# 反思（Reflect）决策规则

InsightAgent 在一个 Phase 执行完后，基于步骤结果决定后续 Phase 的去留 / 修改 /
补充。改写自 ce-insight-2.0 reflector.py 的 A/B/C/D 决策规则。

## 决策选项

| 选项 | 动作 | 触发条件 |
|---|---|---|
| **A** | 继续执行下一阶段，原计划不变 | 当前 Phase 的发现与预期一致，下一阶段目标仍然相关 |
| **B** | 修改下一阶段的 `milestone` / `description` | 发现了意料之外的方向，下一阶段目标需要调整 |
| **C** | 在下一阶段前插入新阶段 | 需要补充一步中间分析（如验证新发现的字段） |
| **D** | 跳过某个后续阶段 | 已通过当前结果直接得出结论，后续阶段已无必要 |

## 表字段边界（硬约束）

⚠️ 天表与分钟表字段完全不同，不能混用：
- **天表字段**：`CEI_score` / `Stability_score` / `ODN_score` / `Rate_score` / ... /
  `isXxxHighCnt` / `isXxxPercent` 等扣分项
- **分钟表字段**：`peakRxRate` / `avgNegotiationRxRate` / `RxPower` / `midCnt` /
  `highCnt` / `oltRxPowerHigh` 等原始采集指标

新增 / 修改阶段时，`table_level` 必须与字段匹配。天表阶段不能用分钟表字段，反之亦然。

## 反思输出 JSON 结构

```json
{
  "choice": "A",
  "reason": "选择原因",
  "modified_phase": null,
  "new_phase": null,
  "skip_phase_id": null
}
```

### 选 B（修改下一阶段）
```json
{
  "choice": "B",
  "reason": "发现 ODN 维度拖分，下一阶段应聚焦 ODN 细化字段",
  "modified_phase": {
    "milestone": "定位 ODN 维度内的根因指标",
    "description": "分析 bipHighCnt / fecHighCnt / oltRxPowerHighCnt 等 ODN 细化字段"
  },
  "new_phase": null,
  "skip_phase_id": null
}
```

### 选 C（插入新阶段）
```json
{
  "choice": "C",
  "reason": "需要先验证 WiFi 干扰是否波及全部低分网关",
  "modified_phase": null,
  "new_phase": {
    "name": "WiFi 干扰波及面扫描",
    "milestone": "确认干扰是否全网性",
    "description": "在全网范围内对 midInterferencePercent 做 OutlierDetection",
    "table_level": "day",
    "focus_dimensions": ["Wifi"]
  },
  "skip_phase_id": null
}
```

### 选 D（跳过阶段）
```json
{
  "choice": "D",
  "reason": "当前已直接定位到 fecHighCnt 为根因，无需再做分钟表时序下钻",
  "modified_phase": null,
  "new_phase": null,
  "skip_phase_id": 4
}
```

## 使用场景

- **每个 Phase 结束后调用一次**（InsightAgent 自驱）
- 如果没有剩余 Phase，跳过反思
- 反思失败 / LLM 无响应时，保持原计划继续
- 反思结果应在 `面向 Orchestrator 的摘要 JSON` 中留痕（新增 `reflection_log` 字段）

## 结果摘要喂给反思 LLM 的格式

```
- step1_output: 显著性=0.85, OutstandingMin: ODN_score 最低的 portUuid 为 p1/p2/p3
- step2_output: 显著性=0.72, CrossMeasureCorrelation: ODN_score 与 fecHighCnt 强负相关
- step3_output: 显著性=0.30, Trend: 下降趋势不显著
```

超过 200 字的 description 截断后加省略号。
