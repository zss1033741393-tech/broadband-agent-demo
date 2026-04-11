# 宏观计划（MacroPlan）设计参考

InsightAgent 在 **阶段 1 — 规划（Plan）** 阶段，根据用户问题设计 2-4 个分析 Phase。
本文档给出 4 类任务的设计规则 + 3 条典型故事线（改写自 ce-insight-2.0 planner.py）。

## 4 层下钻模型（L1→L4）

- **L1** `CEI_score` → 找哪些设备总分低
- **L2** 8 个维度 `_score` → 找是哪个维度拖分
- **L3** 天表维度细化字段（`HighCnt` / `Percent` 等）→ 找该维度内哪个指标是根因
- **L4** 分钟表时序 → 验证根因指标的时序分布与相关性

⚠️ **L2 和 L3 必须拆成两个独立 Phase，绝不能合并**：
- L2 结束后才知道是哪个维度有问题
- L3 才能针对该维度去分析它的细化字段
- 合并后 decomposer 无从决定查哪些字段

## 任务分类 → Phase 数量

### 1. 简单查询类（1 个 Phase）
触发词：明确说"只需输出"、"无需分析原因"、"只要找出"、"列出 Top N"
- **只设计 1 个 Phase**，用 `NL2Code` 或 `OutstandingMin/Max` 直出结果
- 不要画蛇添足做根因分析

### 2. 根因分析类（4 个 Phase，严格 L1→L2→L3→L4）
触发词：分析 / 为什么 / 原因 / 找出并分析 / 根因
- 参考下方三条故事线
- 每层独立成一个 Phase，不可合并

### 3. 指定维度类（2 个 Phase）
触发词：Wifi 质量差 / 光路问题 / ODN / 网关问题
- **跳过 L1 / L2**，直接从 L3 开始
- Phase 1: L3 天表维度细化字段分析，`focus_dimensions` 填该维度
- Phase 2: L4 分钟表时序下钻

### 4. 指定设备类（3 个 Phase）
触发词：用户提供了 portUuid / gatewayMac
- 跳过 L1 (定位设备)，直接从 L2 开始
- Phase 1: L2 维度扫描（已知设备）
- Phase 2: L3 天表维度细化
- Phase 3: L4 分钟表时序

## 典型故事线 A — PON 口 CEI 低 → 光路问题

用户："找出 CEI 分数较低的 PON 口，并分析原因"

| Phase | 层级 | 动作 |
|---|---|---|
| 1 | L1 | `OutstandingMin` on `portUuid / CEI_score`：定位低分 PON 口 |
| 2 | L2 | 聚焦低分 PON 口，比较 8 个维度 `_score`，找拖分维度（如 ODN_score 最低） |
| 3 | L3 | 针对 ODN，分析细化字段：`bipHighCnt` / `fecHighCnt` / `oltRxPowerHighCnt` / `gamePoorQualityCount`，定位根因指标 |
| 4 | L4 | 下钻分钟表，分析质差次数与根因指标（`bipHigh` / `fecHigh` / `oltRxPowerHigh`）的时序相关性 |

**结论模板**：PON 光功率异常 → 业务质差次数上升

## 典型故事线 B — 网关 CEI 低 → WiFi 干扰

用户："找出 CEI 分数较低的网关，并分析原因"

| Phase | 层级 | 动作 |
|---|---|---|
| 1 | L1 | `OutstandingMin` on `gatewayMac / CEI_score` |
| 2 | L2 | 聚焦低分网关，确认 `Wifi_score` 或 `Gateway_score` 显著偏低 |
| 3 | L3 | 针对问题维度，分析 `midInterferencePercent` / `highInterferencePercent` / `diagTimeDelayHighCnt` |
| 4 | L4 | 下钻分钟表，分析 WiFi 干扰次数（`midCnt` / `highCnt`）、质差、空口时延（`avgDiagAvgTime`）的时序相关性 |

**结论模板**：WiFi 干扰占空比高伴随 ping 时延越限 → 业务质差

## 典型故事线 C — 用户质差率升高 → 上行丢包

用户："PON 口下挂用户质差率升高，分析原因"

| Phase | 层级 | 动作 |
|---|---|---|
| 1 | L1 | `OutstandingMin` on `portUuid / CEI_score` |
| 2 | L2 | 聚焦低分 PON 口，确认 `Rate_score` / `Service_score` 偏低 |
| 3 | L3 | 分析业务质差率、`meanRxRate` 异常比例、`G10UpPlrHighCnt` / `portUpPlrHighCnt` |
| 4 | L4 | 下钻分钟表，分析 ONT→PON 上行流量（`meanRxTraffic`）、质差次数、端口上行丢包（`portUpPlr` / `G10UpPlr`）的时序相关性 |

**结论模板**：上行流量和端口上行丢包升高 → 用户质差率上升

## MacroPlan JSON 结构

InsightAgent 产出的计划必须是以下结构（LLM 内部保留即可，不必发给用户）：

```json
{
  "goal": "用户意图的一句话摘要",
  "phases": [
    {
      "phase_id": 1,
      "name": "阶段名",
      "milestone": "里程碑目标",
      "table_level": "day",
      "description": "要做什么分析（对应哪一层 L1/L2/L3/L4）",
      "focus_dimensions": []
    }
  ]
}
```

`focus_dimensions` 一般留空，仅当用户明确指定维度时才填；值必须是 8 维度之一：
`Stability / ODN / Rate / Service / OLT / Gateway / STA / Wifi`
