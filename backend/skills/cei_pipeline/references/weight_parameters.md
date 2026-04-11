# CEI 权重参数说明

FAE 平台 CEI 评分采用 8 维度加权计算：`CEI_score = Σ(dimension_score × dimension_weight / 100)`。本文件列出 8 个权重参数的含义、允许值、默认值，以及 PlanningAgent 常用的套餐/场景预设速查。

> ⚠️ 本文件是 **L3 参考资料**（`get_skill_reference` 按需加载），**不会**默认进入 Agent 上下文。业务规则归属 `plan_design` SKILL.md 的"权重预设速查"章节；本文件只做权重定义与预设的详细展开，供脚本调试或运维查阅使用。

## 1. 8 维度权重参数表

| 参数名 | 默认值 | 允许值 | 含义 | 关注重点 |
|---|---|---|---|---|
| `ServiceQualityWeight` | 30 | 0-100 | 业务质量权重 | 直播、视频、游戏等应用感知质量 |
| `WiFiNetworkWeight` | 20 | 0-100 | Wi-Fi 网络权重 | 覆盖强度、信道干扰、终端连接 |
| `StabilityWeight` | 15 | 0-100 | 稳定性权重 | 抖动、重传、掉线、连接稳定性 |
| `STAKPIWeight` | 10 | 0-100 | 终端 KPI 权重 | STA 侧设备层指标 |
| `GatewayKPIWeight` | 10 | 0-100 | 网关 KPI 权重 | 家庭网关 CPU/内存/会话数等 |
| `RateWeight` | 5 | 0-100 | 速率权重 | 上下行实际速率与签约速率的达成率 |
| `ODNWeight` | 5 | 0-100 | ODN 权重 | 光分配网（光路）层指标 |
| `OLTKPIWeight` | 5 | 0-100 | OLT 权重 | 局端设备层指标 |

**默认值加和**：30 + 20 + 15 + 10 + 10 + 5 + 5 + 5 = **100**

业务上建议保持 8 维度加和为 100，便于不同权重组合之间的可比性。FAE 平台侧可能对加和做校验，本 Skill 脚本不做本地加和检查。

## 2. CSV 参数格式

Provisioning Agent 通过 argparse `--weights` 传入单个 CSV 字符串，格式：

```
ServiceQualityWeight:30,WiFiNetworkWeight:20,StabilityWeight:15,STAKPIWeight:10,GatewayKPIWeight:10,RateWeight:5,ODNWeight:5,OLTKPIWeight:5
```

- 分隔符：维度之间用 **逗号** `,`；参数名与数值之间用 **冒号** `:`
- 顺序：任意
- 省略：允许省略部分维度（脚本按 FAE 平台的"只覆盖传入字段"语义处理）
- 全量省略：等同于不传 `--weights`，使用 FAE 当前生效的权重

## 3. 套餐 / 场景预设速查

以下预设供 PlanningAgent 生成方案时使用。每组预设均为 8 维度完整加和 100 的组合，直接 CSV 化后填入 `## CEI 配置方案` 段落的 `权重配置` 字段。

### 3.1 普通套餐（默认基线）

```
ServiceQualityWeight:30,WiFiNetworkWeight:20,StabilityWeight:15,STAKPIWeight:10,GatewayKPIWeight:10,RateWeight:5,ODNWeight:5,OLTKPIWeight:5
```

**适用**：家庭常规用户、无特殊业务诉求。

### 3.2 直播套餐 + 卖场/楼宇走播

```
ServiceQualityWeight:40,WiFiNetworkWeight:25,StabilityWeight:15,STAKPIWeight:5,GatewayKPIWeight:5,RateWeight:5,ODNWeight:3,OLTKPIWeight:2
```

**设计思路**：走播场景强依赖业务感知（推流卡顿/花屏直接影响直播收益）和 Wi-Fi 覆盖（主播移动位置），因此大幅提升 `ServiceQualityWeight` 和 `WiFiNetworkWeight`。ODN/OLT/网关层问题通常不是走播场景的主要故障源，压缩权重。

**适用**：直播套餐 + 卖场 / 楼宇走播 / 户外走播场景。

### 3.3 专线套餐 / VVIP

```
ServiceQualityWeight:25,WiFiNetworkWeight:15,StabilityWeight:25,STAKPIWeight:5,GatewayKPIWeight:5,RateWeight:15,ODNWeight:5,OLTKPIWeight:5
```

**设计思路**：专线/VVIP 用户对带宽达成率和连接稳定性敏感（SLA 承诺），提升 `StabilityWeight` 和 `RateWeight`。业务质量权重保持中等，Wi-Fi 权重适度降低（专线通常有独立承载）。

**适用**：专线套餐、VVIP 用户、企业客户。

### 3.4 游戏类用户

```
ServiceQualityWeight:20,WiFiNetworkWeight:20,StabilityWeight:25,STAKPIWeight:5,GatewayKPIWeight:15,RateWeight:15,ODNWeight:0,OLTKPIWeight:0
```

**设计思路**：游戏场景对延迟抖动和网关转发质量极敏感，`StabilityWeight`、`GatewayKPIWeight`、`RateWeight` 并重；光路层对体验影响较小，可降至 0。

**适用**：明确自报游戏用户 / 电竞套餐。

### 3.5 投诉处置（在任一基础预设上叠加）

在任一预设基础上，**`ServiceQualityWeight` 加 5**（从其他低权重维度扣除），体现"优先恢复业务感知"的取向。例如直播套餐投诉处置：

```
ServiceQualityWeight:45,WiFiNetworkWeight:25,StabilityWeight:15,STAKPIWeight:5,GatewayKPIWeight:3,RateWeight:5,ODNWeight:1,OLTKPIWeight:1
```

## 4. 常见误区

- ❌ **加和不等于 100**：虽然 Skill 不做本地校验，但 FAE 平台通常要求加和为 100，否则评分归一化会出偏。建议 PlanningAgent 生成时严格加和到 100。
- ❌ **未知参数名**：`ServiceQuality` / `ServiceWeight` 等非精确拼写会被 FAE 拒绝。8 个参数名必须严格匹配本表大小写。
- ❌ **数值越界**：单个维度超过 100 无意义；FAE 平台会拒绝。
- ❌ **用权重表达"阈值"**：本接口仅配置评分各维度的权重组合，**不配置告警阈值**。告警阈值和评分查询是未来独立 Skill 的职责。
