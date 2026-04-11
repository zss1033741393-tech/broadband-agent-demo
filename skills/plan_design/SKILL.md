---
name: plan_design
description: "方案设计：根据用户画像或洞察摘要，生成 5 段式自然语言调优方案，启用段落必须对齐下游 Skill 参数 schema"
---

# 方案设计

## Metadata
- **paradigm**: Instructional (纯指令 + few-shot 样例，无脚本)
- **when_to_use**: PlanningAgent 收集齐画像（综合目标）或收到 Insight 摘要后，需要产出可执行方案
- **inputs**: 画像 JSON（场景 1）或 画像 + insight 摘要（场景 2）
- **outputs**: 分段 Markdown 方案，每段带 `启用: true/false` 头和对齐下游 Skill 参数 schema 的业务字段

## When to Use

- ✅ 综合目标任务的画像已齐全（7 槽填充完成）
- ✅ 数据洞察后用户要求生成优化方案，Insight 摘要已作为 hints 提供给 Planning
- ❌ 画像尚未齐全（应先调用 `goal_parsing`）
- ❌ 单点功能调用（场景 3 直达 Provisioning，不经过 Planning）

## 核心原则

1. **纯 LLM 生成**：本 Skill **无脚本、无模板**。PlanningAgent 通过 `get_skill_instructions("plan_design")` 加载本指令和 `get_skill_reference("plan_design", "examples.md")` 加载 few-shot 样例，然后**直接用 LLM 推理生成方案 Markdown**。
2. **业务规则由 LLM 决定**：如"直播套餐默认 ServiceQualityWeight 40"、"卖场走播场景远程闭环不含重启"等业务知识全部由本 Skill 的指令告知 LLM，**不能寄希望于下游 Skill 脚本补默认值**。
3. **字段对齐 schema**：每段启用时写出的业务字段，必须覆盖对应下游 Skill 的参数 schema（见 §输出结构契约）。这样 ProvisioningAgent 能直接按 schema 从方案段落提参。

## 输出结构契约（必须严格遵守）

方案必须产出 **5 段**，段落顺序与标题固定：

```markdown
## WIFI 仿真方案
**启用**: true | false
（启用时无需其他字段 — WIFI 仿真 Skill 内部自主驱动 4 步流程）
（禁用时写一行 _跳过原因: ..._）

## 差异化承载方案
**启用**: true | false
- 切片类型: <slice_type>
- 保障应用: <target_app>
- 白名单: <whitelist 列表或"无">
- 带宽保障 (Mbps): <bandwidth_guarantee_mbps>

## CEI 配置方案
**启用**: true | false
- 权重配置: <CSV 字符串>  # 8 维度权重，格式 ServiceQualityWeight:30,WiFiNetworkWeight:20,...（见§业务默认值速查）

## 故障诊断方案
**启用**: true | false
- 故障树: 开启 | 关闭
- 白名单规则: <whitelist_rules 列表>
- 严重性阈值: <severity_threshold>  # info | warning | major | critical

## 远程闭环处置方案
**启用**: true | false
- 执行策略: <strategy>  # immediate | idle | scheduled
- 整改方式: <rectification_method>  # [1,2,3,4] 的任意子集，或"全部"
- 执行时间: <operation_time>  # 仅 strategy=scheduled 时填写，格式 0-0-0-*-*-*
```

**整改方式编号**：`1`=设备重启、`2`=信道切换、`3`=2.4G 功率调整、`4`=5G 功率调整。写段落时可写数字列表 `[1,2,3,4]` 或中文简写组合（Provisioning 侧会统一归一化）。

每段**必须**包含 `**启用**: true/false` 这一行，字段名必须严格使用上面的中文标签，**便于 Orchestrator 按标题切分**。

## 字段 ↔ Skill Schema 对齐表

| 方案段落 | 对应 Skill | 必填参数（来自 Skill SKILL.md 声明的 schema） |
|---|---|---|
| WIFI 仿真方案 | `wifi_simulation` | 无（Skill 内部自驱 4 步） |
| 差异化承载方案 | `differentiated_delivery` | `slice_type, target_app, whitelist, bandwidth_guarantee_mbps` |
| CEI 配置方案 | `cei_pipeline` | `weights` (8 维度 CSV 字符串) |
| 故障诊断方案 | `fault_diagnosis` | `fault_tree_enabled, whitelist_rules, severity_threshold` |
| 远程闭环处置方案 | `remote_optimization` | `strategy, rectification_method, operation_time` |

## 启用决策规则（LLM 推理规则）

1. **单用户故障保障（场景 1）** — 画像含完整 7 槽、`guarantee_target` 为家庭网络或 STA 级：
   - 默认**全部 5 段启用**
   - 例外：用户已明确排除某方面时跳过对应段落
2. **区域性问题（场景 2，Insight 回流）** — 画像含 `scope_indicator=regional/multi_pon` 或 `hints.priority_pons`：
   - 根据问题类型决定启用段落，**通常只启用 1-2 段**
   - `PON 拥塞 / 应用流量集中` → 仅 `差异化承载方案` (Appflow)
   - `光路异常 / 丢包率高` → `差异化承载方案` + `故障诊断方案`
   - `WIFI 覆盖弱` → 仅 `WIFI 仿真方案`
   - 禁用的段落必须写明 `_跳过原因: ..._`
3. **用户显式要求** — 用户提了特殊需求（如"也帮我看下 WIFI"）时，即使默认规则不启用也要启用对应段

## 业务默认值速查（LLM 生成时使用）

**套餐/场景 → CEI 权重预设 `weights`**

> 8 维度权重，默认加和为 100。字段顺序不限，生成时以 CSV 字符串填入 `## CEI 配置方案` 段落的 `权重配置` 字段。详细维度含义见 `cei_pipeline/references/weight_parameters.md`。

| 套餐 / 场景 | 推荐权重配置 | 设计思路 |
|---|---|---|
| 普通套餐（默认基线） | `ServiceQualityWeight:30,WiFiNetworkWeight:20,StabilityWeight:15,STAKPIWeight:10,GatewayKPIWeight:10,RateWeight:5,ODNWeight:5,OLTKPIWeight:5` | 均衡分布，常规家宽 |
| 直播套餐 + 卖场/楼宇走播 | `ServiceQualityWeight:40,WiFiNetworkWeight:25,StabilityWeight:15,STAKPIWeight:5,GatewayKPIWeight:5,RateWeight:5,ODNWeight:3,OLTKPIWeight:2` | 业务感知 + Wi-Fi 覆盖并重，压缩 ODN/OLT |
| 专线套餐 / VVIP | `ServiceQualityWeight:25,WiFiNetworkWeight:15,StabilityWeight:25,STAKPIWeight:5,GatewayKPIWeight:5,RateWeight:15,ODNWeight:5,OLTKPIWeight:5` | 稳定性 + 速率达成率优先 |
| 游戏类用户 | `ServiceQualityWeight:20,WiFiNetworkWeight:20,StabilityWeight:25,STAKPIWeight:5,GatewayKPIWeight:15,RateWeight:15,ODNWeight:0,OLTKPIWeight:0` | 稳定性 + 网关 + 速率并重 |
| 投诉处置叠加 | 在任一基础预设上 `ServiceQualityWeight` 再 +5（从低权重维度扣除） | 体现"优先恢复业务感知" |

**场景 → 远程闭环执行策略 `strategy`**
- 直播套餐（有业务时段保障）→ `idle`（闲时执行，避开直播时段）
- 专线套餐 / VVIP → `immediate`（优先级最高）
- 投诉处置 / 紧急恢复 → `immediate`
- 常规维护 → `scheduled`，搭配 `operation_time` (如 `0-0-3-*-*-*` 凌晨 3 点)

**场景 → 远程闭环整改方式 `rectification_method`**
- 卖场走播（走动覆盖弱，忌重启打断业务）→ `[2, 3, 4]`（信道切换 + 2.4G/5G 功率调整，**不含重启**）
- 楼宇直播（相对静态）→ `[1, 2, 3, 4]`（全部整改）
- 家庭直播 → `[1, 2]`（重启 + 信道切换，最小影响）
- 常规维护 / 意图不明 → 不填（代表"全部整改方式"）

**场景 → 故障诊断白名单**
- 直播场景 → 加入"偶发卡顿"白名单（避免误判持续故障）
- 其他 → 空

**投诉历史 = true** → 故障诊断 `severity_threshold` 提升为 `warning`

## How to Use

1. PlanningAgent 调用 `get_skill_instructions("plan_design")` 获取本指令
2. 可选地加载 `get_skill_reference("plan_design", "examples.md")` 查看 few-shot 样例
3. **不调用任何脚本**，直接用 LLM 根据画像推理生成分段 Markdown
4. 把生成的 Markdown 交给 `plan_review` 校验
5. 校验通过后交回 PlanningAgent 主流程，由 Orchestrator 拆分派发

## References

- `references/examples.md` — 3 个典型场景的 few-shot 样例（场景 1 完整方案 / 场景 2 稀疏方案 / 场景 3 禁用示例）

## 禁止事项

- ❌ 不要凭空编造下游 Skill 之外的段落（必须严格 5 段）
- ❌ 不要省略 `**启用**: true/false` 头（Orchestrator 拆分依赖这一行）
- ❌ 不要把业务字段写成自由散文（字段名必须严格对齐 §输出结构契约 的中文标签）
- ❌ 不要猜测 schema 之外的参数
