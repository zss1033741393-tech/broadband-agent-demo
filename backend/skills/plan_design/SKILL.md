---
name: plan_design
description: "方案设计：根据用户画像或洞察摘要，生成 5 段式调优方案，每段以中文冒号标题 + 缩进子字段形式输出，启用判断由子字段 True/False 驱动"
---

# 方案设计

## Metadata
- **paradigm**: Instructional (纯指令 + few-shot 样例，无脚本)
- **when_to_use**: PlanningAgent 收集齐画像（综合目标）或收到 Insight 摘要后，需要产出可执行方案
- **inputs**: 画像 JSON（场景 1）或 画像 + insight 摘要（场景 2）
- **outputs**: 5 段式方案，每段以中文冒号标题 + 4 空格缩进子字段输出，子字段 True/False 驱动下游 Skill 参数

## When to Use

- ✅ 综合目标任务的画像已齐全（7 槽填充完成）
- ✅ 数据洞察后用户要求生成优化方案，Insight 摘要已作为 hints 提供给 Planning
- ❌ 画像尚未齐全（应先调用 `goal_parsing`）
- ❌ 单点功能调用（场景 3 直达 Provisioning，不经过 Planning）

## 核心原则

1. **纯 LLM 生成**：本 Skill **无脚本、无模板**。PlanningAgent 通过 `get_skill_instructions("plan_design")` 加载本指令和 `get_skill_reference("plan_design", "examples.md")` 加载 few-shot 样例，然后**直接用 LLM 推理生成方案**。
2. **业务规则由 LLM 决定**：如"直播模型对应 ServiceQualityWeight:40"、"卖场走播不含重启"等业务知识全部由本 Skill 的指令告知 LLM，**不能寄希望于下游 Skill 脚本补默认值**。
3. **字段对齐 schema**：每段输出的子字段，必须覆盖对应下游 Skill 的参数 schema（见 §输出结构契约）。ProvisioningAgent 能直接按 schema 从方案段落提参。

## 输出结构契约（必须严格遵守）

方案必须产出 **5 段**，段落顺序与标题固定，格式为 **中文段落标题（后跟中文冒号"："） + 4 空格缩进子字段**：

```text
AP补点推荐：
    WIFI信号仿真：True | False
    应用卡顿仿真：True | False
    AP补点推荐：True | False

CEI体验感知：
    CEI模型：直播模型 | 视频模型 | 游戏模型 | VVIP模型
    CEI粒度：分钟级
    CEI阈值：<N>分

故障诊断：
    诊断场景：上网慢 | 无法上网 | 游戏卡顿 | 直播卡顿
    偶发卡顿定界：True | False

远程优化：
    远程优化触发时间：闲时 | 立即 | 定时
    远程WIFI信道切换：True | False
    远程网关重启：True | False
    远程WIFI功率调优：True | False

差异化承载：
    差异化wifi切片：True | False
    保障应用：<app_name>
    APP Flow：True | False
    应用策略：<policy_profile>
```

**启用 / 禁用规则**：

| 段落 | 跳过（不派发）条件 |
|---|---|
| `AP补点推荐` | `WIFI信号仿真`、`应用卡顿仿真`、`AP补点推荐` 三项全为 `False` |
| `CEI体验感知` | （CEI 段落无独立开关，若整体不需 CEI 配置，将 CEI模型 置空并在段落标题后注明"跳过原因"） |
| `故障诊断` | 无独立开关；若不适用，将 `诊断场景` 置为"无"并注明原因 |
| `远程优化` | `远程WIFI信道切换`、`远程网关重启`、`远程WIFI功率调优` 三项全为 `False` |
| `差异化承载` | `差异化wifi切片：False` |

禁用的段落须在段落标题下方用 `# 跳过原因: ...` 注释行说明原因，子字段一律写 `False` 或 `无`。

## 字段 ↔ Skill Schema 对齐表

| 新方案字段 | 对应 Skill | Provisioning 侧映射逻辑 |
|---|---|---|
| `WIFI信号仿真 / 应用卡顿仿真 / AP补点推荐` | `wifi_simulation` | 透传给 Provisioning 作为执行范围约束；wifi_simulation 内部 4 步流程自驱 |
| `CEI模型` | `cei_pipeline` | 模型名 → 权重预设 CSV → `--weights`（见§业务默认值速查） |
| `CEI粒度` | `cei_score_query` | 前端展示标注，当前 API 固定分钟级，Provisioning 可忽略 |
| `CEI阈值` | `cei_score_query` | 查询低分用户的阈值过滤；透传为 `--threshold` 或 Provisioning 层过滤 |
| `诊断场景` | `fault_diagnosis` | 中文标签 → 枚举值（见§业务默认值速查）→ `--scenario` |
| `偶发卡顿定界` | `fault_diagnosis` | `True` 时传 `--intermittent-diagnosis`；否则不传 |
| `远程优化触发时间` | `remote_optimization` | `闲时→idle / 立即→immediate / 定时→scheduled` → `--strategy` |
| `远程网关重启：True` | `remote_optimization` | 整改方式编号 `1` |
| `远程WIFI信道切换：True` | `remote_optimization` | 整改方式编号 `2` |
| `远程WIFI功率调优：True` | `remote_optimization` | 整改方式编号 `3,4`（2.4G + 5G） |
| `差异化wifi切片` | `experience_assurance` | `False` 时整段跳过不派发 |
| `APP Flow` | `experience_assurance` | `True→slice_type=appflow_traffic_shaping`，`False→slice_type=application_slice` |
| `保障应用` | `experience_assurance` | → `--target-app` |
| `应用策略` | `experience_assurance` | → `--policy-profile`（如 `limit-speed-1m`） |

## 启用决策规则（LLM 推理规则）

1. **单用户故障保障（场景 1）** — 画像含完整 7 槽、`guarantee_target` 为家庭网络或 STA 级：
   - 默认**全部 5 段启用**（AP补点推荐 / CEI体验感知 / 故障诊断 / 远程优化 / 差异化承载）
   - 例外：用户已明确排除某方面时，对应段落全部子字段置 `False`
2. **区域性问题（场景 2，Insight 回流）** — 画像含 `scope_indicator=regional/multi_pon` 或 `hints.priority_pons`：
   - 根据问题类型决定启用段落，**通常只启用 1-2 段**
   - `PON 拥塞 / 应用流量集中` → 仅 `差异化承载`（差异化wifi切片:True + APP Flow:True）
   - `光路异常 / 丢包率高` → `差异化承载` + `故障诊断`
   - `WIFI 覆盖弱` → 仅 `AP补点推荐`（三子项均 True）
   - 禁用的段落必须注明跳过原因
3. **用户显式要求** — 用户提了特殊需求时，即使默认规则不启用也要启用对应段

## 业务默认值速查（LLM 生成时使用）

### CEI模型 → 权重预设 `--weights`（Provisioning 按此表映射）

| CEI模型（方案字段值） | 对应权重 CSV |
|---|---|
| 直播模型 | `ServiceQualityWeight:40,WiFiNetworkWeight:25,StabilityWeight:15,STAKPIWeight:5,GatewayKPIWeight:5,RateWeight:5,ODNWeight:3,OLTKPIWeight:2` |
| 视频模型 | `ServiceQualityWeight:30,WiFiNetworkWeight:20,StabilityWeight:15,STAKPIWeight:10,GatewayKPIWeight:10,RateWeight:5,ODNWeight:5,OLTKPIWeight:5` |
| 游戏模型 | `ServiceQualityWeight:20,WiFiNetworkWeight:20,StabilityWeight:25,STAKPIWeight:5,GatewayKPIWeight:15,RateWeight:15,ODNWeight:0,OLTKPIWeight:0` |
| VVIP模型 | `ServiceQualityWeight:25,WiFiNetworkWeight:15,StabilityWeight:25,STAKPIWeight:5,GatewayKPIWeight:5,RateWeight:15,ODNWeight:5,OLTKPIWeight:5` |

**套餐/场景 → CEI模型选择**

| 套餐 / 场景 | 推荐 CEI模型 |
|---|---|
| 直播套餐 + 卖场/楼宇走播 | 直播模型 |
| 普通套餐（默认基线）/ 视频类 | 视频模型 |
| 游戏类用户 | 游戏模型 |
| 专线套餐 / VVIP | VVIP模型 |

### 诊断场景 → `--scenario` 枚举值

| 诊断场景（方案字段值） | CLI 枚举值 |
|---|---|
| 直播卡顿 | `LIVE_STUTTERING` |
| 游戏卡顿 | `GAME_STUTTERING` |
| 无法上网 | `NETWORK_ACCESS_FAILURE` |
| 上网慢 | `NETWORK_ACCESS_SLOW` |

**套餐 / 关键词 → 诊断场景选择**

| 套餐 / 保障应用 / 投诉关键词 | 推荐诊断场景 |
|---|---|
| 保障应用含直播类（抖音 / 快手 / B 站）或直播套餐 | 直播卡顿 |
| 保障应用含游戏类或游戏用户 | 游戏卡顿 |
| 投诉含"断网 / 掉线 / 上不了网" | 无法上网 |
| 投诉含"网慢 / 速率低 / 卡顿（非业务场景）" | 上网慢 |
| 无法推导（兜底） | 上网慢 |

### 远程优化 → 触发时间 / 整改动作

**触发时间选择**：

| 场景 | 远程优化触发时间 |
|---|---|
| 直播套餐（有业务时段保障） | 闲时 |
| 专线套餐 / VVIP | 立即 |
| 投诉处置 / 紧急恢复 | 立即 |
| 常规维护 | 定时 |

**整改动作组合**：

| 场景 | 网关重启 | 信道切换 | 功率调优 |
|---|---|---|---|
| 卖场走播（忌重启打断业务） | False | True | True |
| 楼宇直播（相对静态） | True | True | True |
| 家庭直播 | True | True | False |
| 常规维护 / 意图不明 | True | True | True |

### 差异化承载 → APP Flow / 应用策略

| 场景 | APP Flow | 应用策略参考值 |
|---|---|---|
| 区域性 PON 拥塞整形（流量成型） | True | `limit-speed-1m` |
| 单用户应用切片保障 | False | `assurance-app-slice` |
| 高保障 VIP 套餐 | False | `vip-assurance` |

**CEI阈值参考**：常规场景默认 `70分`；VVIP/专线场景建议 `80分`；投诉处置建议 `65分`。

## How to Use

1. PlanningAgent 调用 `get_skill_instructions("plan_design")` 获取本指令
2. 可选地加载 `get_skill_reference("plan_design", "examples.md")` 查看 few-shot 样例
3. **不调用任何脚本**，直接用 LLM 根据画像推理生成 5 段方案
4. 把生成的方案交给 `plan_review` 校验
5. 校验通过后交回 PlanningAgent 主流程，由 Orchestrator 拆分派发

## References

- `references/examples.md` — 3 个典型场景的 few-shot 样例（场景 1 完整方案 / 场景 2 稀疏方案 / 场景 2 变体）

## 禁止事项

- ❌ 不要凭空编造段落外的字段
- ❌ 不要使用 Markdown `##` 标题，段落标题必须是"中文名称 + 中文冒号"格式
- ❌ 不要写 `**启用**: true/false` 行（旧格式，已废弃）
- ❌ 不要把业务字段写成自由散文，子字段必须严格按 `字段名：值` 格式
- ❌ 不要猜测 schema 之外的参数
