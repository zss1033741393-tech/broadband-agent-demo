# 宏观计划（MacroPlan）设计参考

InsightAgent 在 **阶段 1 — 规划（Plan）** 阶段，根据用户问题设计 2-4 个分析 Phase。
本文档给出 4 类任务的设计规则 + 3 条典型故事线（改写自 ce-insight-2.0 planner.py）。

## 4 层下钻模型（内部概念，禁止出现在 Phase 名字里）

> ⚠️ L1-L4 是内部分析逻辑，帮助你理解分析路径。**Phase 名字必须用业务语言**，
> 禁止写 "L1-xxx"、"L2-xxx" 这类标签——用户看到会以为前面缺了阶段。

- **L1** `CEI_score` → 找哪些设备总分低
- **L2** 8 个维度 `_score` → 找是哪个维度拖分
- **L3** 天表维度细化字段（`HighCnt` / `Percent` 等）→ 找该维度内哪个指标是根因
- **L4** 分钟表时序 → 验证根因指标的时序分布与相关性

⚠️ **L2 和 L3 必须拆成两个独立 Phase，绝不能合并**：
- L2 结束后才知道是哪个维度有问题
- L3 才能针对该维度去分析它的细化字段
- 合并后 decomposer 无从决定查哪些字段

## 业务术语映射

用户提到以下词语时，直接映射到对应维度，**触发"指定维度类"流程（3 个 Phase）**：

| 用户说的词 | 对应维度 | focus_dimensions 填写值 |
|---|---|---|
| 质差 / 用户质差率 / 业务质差 / 质差次数 | Service | `["Service"]` |
| WiFi 质量差 / WiFi 干扰 / 无线问题 | Wifi | `["Wifi"]` |
| 光路问题 / ODN / 光功率 / 光衰 / BIP / FEC | ODN | `["ODN"]` |
| 网关问题 / 网关异常 / 家庭网关 | Gateway | `["Gateway"]` |
| 稳定性差 / 频繁断线 / 告警多 | Stability | `["Stability"]` |
| 速率低 / 限速 / 带宽不足 | Rate | `["Rate"]` |
| OLT 问题 / PON 口异常 | OLT | `["OLT"]` |
| 终端问题 / STA / 接入设备多 | STA | `["STA"]` |

## 任务分类 → Phase 数量

> 🔴 **分类优先级（从高到低）**：
> 1. **指定设备类** — 用户提供了 portUuid / gatewayMac → 走类型 4
> 2. **指定维度类** — 命中上方"业务术语映射"表中的词（质差/WiFi差/光路问题等）→ 走类型 3，**即使用户同时说了"分析原因"也走 3 Phase，不走 4 Phase**
> 3. **简单查询类** — 用户明确说只需要列出/查出，不需要原因 → 走类型 1
> 4. **根因分析类** — 以上都不命中，且用户想知道"为什么/原因/根因" → 走类型 2（4 Phase）

### 1. 简单查询类（1 个 Phase）
触发词：明确说"只需输出"、"无需分析原因"、"只要找出"、"列出 Top N"
- **只设计 1 个 Phase**，用 `NL2Code` 或 `OutstandingMin/Max` 直出结果
- 不要画蛇添足做根因分析

### 2. 根因分析类（4 个 Phase，严格按 L1→L2→L3→L4 路径）
触发词：分析 / 为什么 / 原因 / 找出并分析 / 根因（且**未命中**业务术语映射表）
- 参考下方三条故事线
- 每层独立成一个 Phase，不可合并

### 3. 指定维度类（3 个 Phase）
触发词：见上方"业务术语映射"表，或用户明确说出某个维度名称

**⚠️ 优先级高于根因分析类**：用户说"分析质差原因"——"质差"命中映射表，直接走 3 Phase，
不走 4 Phase。"分析 WiFi 质量差的原因"——同理走 3 Phase。

分析路径（**不要跳过第一步**，先定位哪些设备在该维度最差）：
- Phase 1: 定位该维度得分最差的设备（`OutstandingMin` on `{维度}_score`，`breakdown` 按 `portUuid` 或 `gatewayMac`）
- Phase 2: 针对这些设备，分析该维度的天表细化字段，找根因指标
- Phase 3: 下钻分钟表，做时序验证

`focus_dimensions` 在 Phase 2 填写对应维度值（见业务术语映射表）；Phase 1 和 Phase 3 留空。

### 4. 指定设备类（3 个 Phase）
触发词：用户提供了 portUuid / gatewayMac

跳过 L1（定位设备），直接从 L2 开始：
- Phase 1: 扫描 8 个维度得分，找出拖分维度
- Phase 2: 针对问题维度，分析天表细化字段
- Phase 3: 下钻分钟表，时序验证

## Phase 命名规范

Phase 名字应该描述**这个阶段在做什么业务动作**，不要带 L1/L2/L3/L4 编号。

| ❌ 禁止 | ✅ 推荐 |
|---|---|
| L1-定位低分PON口 | 定位低分 PON 口 |
| L2-维度扫描 | 识别问题维度 |
| L3-ODN细化字段分析 | 定位 ODN 根因指标 |
| L4-分钟表时序下钻 | 时序验证与相关性分析 |
| L3-Service质差分析 | 定位业务质差根因 |

## 典型故事线 A — PON 口 CEI 低 → 光路问题

用户："找出 CEI 分数较低的 PON 口，并分析原因"

| Phase | 名称示例 | 动作 |
|---|---|---|
| 1 | 定位低分 PON 口 | `OutstandingMin` on `portUuid / CEI_score` |
| 2 | 识别问题维度 | 聚焦低分 PON 口，比较 8 个维度 `_score`，找拖分维度（如 ODN_score 最低） |
| 3 | 定位 ODN 根因指标 | 针对 ODN，分析细化字段：`bipHighCnt` / `fecHighCnt` / `oltRxPowerHighCnt` |
| 4 | 时序验证与相关性分析 | 下钻分钟表，分析质差次数与根因指标的时序相关性 |

**结论模板**：PON 光功率异常 → 业务质差次数上升

## 典型故事线 B — 网关 CEI 低 → WiFi 干扰

用户："找出 CEI 分数较低的网关，并分析原因"

| Phase | 名称示例 | 动作 |
|---|---|---|
| 1 | 定位低分网关 | `OutstandingMin` on `gatewayMac / CEI_score` |
| 2 | 识别问题维度 | 聚焦低分网关，确认 `Wifi_score` 或 `Gateway_score` 显著偏低 |
| 3 | 定位 WiFi 根因指标 | 针对问题维度，分析 `midInterferencePercent` / `highInterferencePercent` / `diagTimeDelayHighCnt` |
| 4 | 时序验证与相关性分析 | 下钻分钟表，分析 WiFi 干扰次数、质差、空口时延的时序相关性 |

**结论模板**：WiFi 干扰占空比高伴随 ping 时延越限 → 业务质差

## 典型故事线 C — 用户质差率升高 → 上行丢包

用户："PON 口下挂用户质差率升高，分析原因"

| Phase | 名称示例 | 动作 |
|---|---|---|
| 1 | 定位低分 PON 口 | `OutstandingMin` on `portUuid / CEI_score` |
| 2 | 识别问题维度 | 聚焦低分 PON 口，确认 `Rate_score` / `Service_score` 偏低 |
| 3 | 定位业务质差根因 | 分析业务质差率、`meanRxRate` 异常比例、`G10UpPlrHighCnt` / `portUpPlrHighCnt` |
| 4 | 时序验证与相关性分析 | 下钻分钟表，分析上行流量、质差次数、端口上行丢包的时序相关性 |

**结论模板**：上行流量和端口上行丢包升高 → 用户质差率上升

## 典型故事线 D — 指定维度：用户质差

用户："分析一下最近的用户质差问题" / "质差次数为什么这么高"

| Phase | 名称示例 | 动作 |
|---|---|---|
| 1 | 定位业务质差最严重的 PON 口 | `OutstandingMin` on `portUuid / Service_score` |
| 2 | 定位业务质差根因指标 | 针对问题 PON 口，分析 Service 维度细化字段（`focus_dimensions: ["Service"]`） |
| 3 | 时序验证与相关性分析 | 下钻分钟表，验证质差次数时序分布与根因指标相关性 |

**结论模板**：Service 维度 XX 指标异常 → 用户质差率上升

## MacroPlan JSON 结构

InsightAgent 产出的计划必须是以下结构（LLM 内部保留即可，不必发给用户）：

```json
{
  "goal": "用户意图的一句话摘要",
  "phases": [
    {
      "phase_id": 1,
      "name": "定位低分 PON 口",
      "milestone": "识别 CEI 得分最低的 PON 口列表",
      "table_level": "day",
      "description": "用 OutstandingMin 找出 CEI_score 最低的 portUuid",
      "focus_dimensions": []
    }
  ]
}
```

`focus_dimensions` 一般留空，仅当用户明确指定维度时才填；值必须是 8 维度之一：
`Stability / ODN / Rate / Service / OLT / Gateway / STA / Wifi`

