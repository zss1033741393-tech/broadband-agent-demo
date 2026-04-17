---
name: plan_design
description: "方案设计：根据用户画像或洞察摘要，生成 5 段式调优方案，每段以中文冒号标题 + 缩进子字段形式输出，启用判断由子字段 True/False 驱动"
---

# 方案设计

## Metadata
- **paradigm**: Instructional + Knowledge Base（纯指令 + few-shot 样例 + 强制查阅的业务映射表，无脚本）
- **when_to_use**: PlanningAgent 收集齐画像（综合目标）或收到 Insight 摘要后，需要产出可执行方案
- **inputs**: 画像 JSON（场景 1）或 画像 + insight 摘要（场景 2）
- **outputs**: 5 段式方案，每段以中文冒号标题 + 4 空格缩进子字段输出，子字段 True/False 驱动下游 Skill 参数

## When to Use

- ✅ 综合目标任务的画像已齐全（7 槽填充完成）
- ✅ 数据洞察后用户要求生成优化方案，Insight 摘要已作为 hints 提供给 Planning
- ✅ 编辑方案：用户要求修改当前保障方案的某些字段（通过 plan_store 读取当前方案后局部修改）
- ❌ 画像尚未齐全（应先调用 `goal_parsing`）
- ❌ 单点功能调用（场景 3 直达 Provisioning，不经过 Planning）

## 核心原则

1. **纯 LLM 生成**：本 Skill **无脚本、无模板**。PlanningAgent 通过 `get_skill_instructions("plan_design")` 加载本指令和 `get_skill_reference("plan_design", "examples.md")` 加载 few-shot 样例，然后**直接用 LLM 推理生成方案**。
2. **业务规则由 LLM 决定**：如"直播模型对应 ServiceQualityWeight:40"、"卖场走播不含重启"等业务知识全部由本 Skill 的指令告知 LLM，**不能寄希望于下游 Skill 脚本补默认值**。
3. **字段对齐 schema**：每段输出的子字段，必须覆盖对应下游 Skill 的参数 schema（见 §输出结构契约）。ProvisioningAgent 能直接按 schema 从方案段落提参。

## 相关方案生成知识（基于目标任务的画像生成方案时参考）

1.**用户类型**：
    -直播用户：要求上行带宽的冗余、上行链路的低丢包 / 低抖动。组网上要求改桥接模式，由主路由器拨号关闭光猫自带 WiFi；优先有线直连，无线连接优先 5G WiFi；套餐上要求高上行和高QoS优先级，保障上行带宽足够；
    -游戏用户：对上下行的时延、抖动、丢包敏感，对带宽需求低；组网上要求改桥接模式，路由器拨号，关闭光猫自带 WiFi 和多余防火墙功能，路由器最好支持游戏QoS模式；优先有线直连路由器，无线必须用 5G 频段，避免wifi干扰；套餐上百兆带宽和千兆带宽区别不大。
    -视频用户：要求下行带宽足够，能稳定满足视频码率的吞吐量需求；组网上光猫路由 / 桥接模式均可；无线连接优先 5G WiFi； 套餐上百兆带宽和千兆带宽区别不大。
    -会议用户：要求上下行带宽的对称冗余，对时延、抖动、丢包实时性要求高；组网上优先桥接模式，路由器拨号；优先有线直连路由器，无线必须用 5G 频段； 套餐上优先办理商宽 / 对称带宽套餐，上行≥50Mbps    

2. **场景**：
    -走播直播场景：在较大空间内移动直播，手机通过wifi连接，可能因为WIFI覆盖弱，WIFI干扰大，多STA竞争等原因导致卡顿
    -楼宇直播场景：在写字楼中的固定直播间直播，使用的终端设备通过有线连接上网，可能因为上行带宽不足，NAT转发异常等原因导致卡顿 
    -家庭直播场景：在普通家庭内部进行直播间直播，手机通过wifi连接，可能因为上行带宽不足，WIFI覆盖弱等原因导致卡顿 

3. **套餐**：
    -普通家庭套餐：强非对称带宽，下行 1000M，上行带宽不足，普遍仅 30M-50M；家宽最低 QoS 优先级，PON 口带宽共享（1:64/1:128 分光比），城域网出口共享，晚高峰易拥塞
    -直播套餐： 高上行 / 对称带宽，主流配置：下行 1000M + 上行 500M；商宽 / 专线级最高 QoS 优先级，PON 口带宽预留，城域网专属出口。

4. **保障对象**：   
    -家庭级：解决组网，连接优化，套餐需求等问题
    -应用级：在家庭保障的基础上，针对具体应用做切片，优先级等进阶优化

## 相关保障方案说明（方案生成时参考）

1.**AP补点推荐**：
    -功能说明：基于当前户型图和路由器位置，进行wifi信号强度仿真，确定室内不同点位的wifi信号强度。同时在当前wifi信号强度条件下进行应用卡顿率仿真。基于信号强度和应用卡顿率仿真结果，
    -解决问题：针对wifi连接场景，提升wifi覆盖率，解决wifi弱覆盖问题 

2.**CEI体验感知**：
    -功能说明：进行宽带用户用网体验的综合评估。可以设定不同模型，针对具体的用户类型进行体验感知；可以通过设定感知粒度来调节感知能力，粒度越细对于体验问题感知能力越强（分钟级>小时级>天级），但是消耗的系统资源也越多，所以默认是天级，仅针对高优先级或者高价值或者高投诉倾向用户设置细粒度；可以通过设定阈值来调节保障触发的敏感度，阈值设定分数越高代表对网络问题的容忍度约低（出现轻微问题也触发后续闭环流程），默认70分，针对高优先级或者高价值或者高投诉倾向用户提高阈值（不超过90分）。
    -解决问题：针对用户用网体验进行感知，触发后续的网络问题闭环流程

3.**故障诊断**：
    -功能说明：针对当前网络问题进行故障定界定位。其中包含两部分：1.故障树诊断，需要指定具体的故障场景（包括：上网慢 ，无法上网，游戏卡顿，直播卡顿等），当CEI分数低于阈值时默认触发故障树诊断功能；2. 偶发卡顿定界，实时监控偶发卡顿问题并给出定界定位结果，因为系统资源问题默认关闭，仅针对卡顿敏感场景（直播，游戏等）以及高优先级保障用户开启。 
    -解决问题：针对网络问题进行定界定位

4.**远程优化**：
    -功能说明：针对定界定位出的网络问题进行远程优化，其中包括远程WIFI信道切换，远程WIFI功率调优，远程网关重启。上述三种闭环方式针对不同的网络故障问题，可以选择性开启（比如，如果连接方式为有线连接，则关闭WIFI信道切换和WIFI功率调优）；触发时间可以配置为定时（固定时间执行），闲时（检测到无业务的时候执行），立即（手动立即触发），默认为定时，针对重点保障用户设定为闲时（远程闭环会造成网络短暂中断）
    -解决问题：针对网络问题远程修复闭环

5.**差异化承载**：
    -功能说明：可以配置三项不同的业务切片保障：体验保障-针对指定的应用类型和保障应用进行wifi时隙切片，确保受保障应用独占切片，避免因wifi干扰和应用转发竞争导致的卡顿问题; 限速: 用户所在的PON口进行大象流检测，针对流量过大的用户进行限处理；APP-flow：针对受保障用户进行PON口切片，保证独占 
    -解决问题：针对网络管道进行实时保障

## 输出结构契约（必须严格遵守）
方案必须产出 **5 段**，段落顺序与标题固定，格式为 **中文段落标题（后跟中文冒号"："） + 4 空格缩进子字段**：

```text
AP补点推荐：
    WIFI信号仿真：True | False
    应用卡顿仿真：True | False
    AP补点推荐：True | False

CEI体验感知：
    CEI模型：直播模型 | 视频模型 | 游戏模型 | 会议模型
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
    差异化承载：True | False
    应用类型：<app_type>
    保障应用：<app_name>
    业务类型：experience-assurance | app-flow | assurance-app-slice | limit-speed-1m | vip-assurance | 无
```

**启用 / 禁用规则**：

| 段落 | 跳过（不派发）条件 |
|---|---|
| `AP补点推荐` | `WIFI信号仿真`、`应用卡顿仿真`、`AP补点推荐` 三项全为 `False` |
| `CEI体验感知` | （CEI 段落无独立开关，若整体不需 CEI 配置，将 CEI模型 置空并在段落标题后注明"跳过原因"） |
| `故障诊断` | 无独立开关；若不适用，将 `诊断场景` 置为"无"并注明原因 |
| `远程优化` | `远程WIFI信道切换`、`远程网关重启`、`远程WIFI功率调优` 三项全为 `False` |
| `差异化承载` | `差异化承载：False` |

禁用的段落须在段落标题下方用 `# 跳过原因: ...` 注释行说明原因，子字段一律写 `False` 或 `无`。

> ⚠️ **禁用段子字段强制规范**：凡主开关为 `False`（或段落整体跳过）的段落，其所有子字段均须写 `False` 或 `无`，**禁止在禁用段填写真实业务值**（如 `差异化承载：False` 时，下方 `应用类型 / 保障应用 / 业务类型` 必须全写 `无`）。

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
| `差异化承载` | `experience_assurance` | `False` 时整段跳过不派发 |


## 启用决策规则（LLM 推理规则）

1. **单用户故障保障（场景 1）** — 画像含完整 7 槽、`guarantee_target` 为家庭级或应用级：
   - 默认**3 段启用**（CEI体验感知 / 故障诊断 / 远程优化）
   - 默认**其它 2 段不启用**（AP补点推荐 / 差异化承载）
   - **WIFI 覆盖弱特判**（优先级高于默认规则）：`issue_type=wifi_coverage` 或投诉关键词含"信号弱/盲区/覆盖差" → 覆盖默认 3 段规则，**仅启用 AP补点推荐**（三子项全 True），其余 4 段全部禁用并注明跳过原因
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
| 直播模型 | `ServiceQualityWeight:40,WiFiNetworkWeight:10,StabilityWeight:25,STAKPIWeight:5,GatewayKPIWeight:10,RateWeight:5,ODNWeight:3,OLTKPIWeight:2` |
| 视频模型 | `ServiceQualityWeight:30,WiFiNetworkWeight:20,StabilityWeight:15,STAKPIWeight:10,GatewayKPIWeight:10,RateWeight:5,ODNWeight:5,OLTKPIWeight:5` |
| 游戏模型 | `ServiceQualityWeight:20,WiFiNetworkWeight:20,StabilityWeight:25,STAKPIWeight:5,GatewayKPIWeight:15,RateWeight:15,ODNWeight:0,OLTKPIWeight:0` |
| 会议模型 | `ServiceQualityWeight:25,WiFiNetworkWeight:15,StabilityWeight:25,STAKPIWeight:5,GatewayKPIWeight:5,RateWeight:15,ODNWeight:5,OLTKPIWeight:5` |

**套餐/场景 → CEI模型选择**

| 套餐 / 场景 | 推荐 CEI模型 |
|---|---|
| 直播套餐 + 卖场走播/楼宇直播 | 直播模型 |
| 普通套餐 + 家庭直播 | 直播模型 |
| 直播类用户 | 直播模型 |
| 普通套餐 / 视频类 | 视频模型 |
| 视频类用户 | 视频模型 |
| 游戏类用户 | 游戏模型 |
| 专线套餐 / 会议类 | 会议模型 |
| 会议类用户 | 会议模型 |

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
| 专线套餐  | 闲时 |
| 投诉处置 / 紧急恢复 | 立即 |
| 常规维护 | 定时 |

**整改动作组合**：

| 场景 | 网关重启 | 信道切换 | 功率调优 |
|---|---|---|---|
| 卖场走播（忌重启打断业务） | False | True | True |
| 楼宇直播（有线连接，无wifi连接） | True | False | False |
| 家庭直播 | True | True | True |
| 常规维护 / 意图不明 | True | True | True |

### 差异化承载 → 业务类型选择

| 场景 | 差异化承载（主开关） | 业务类型 |
|---|---|---|
| 区域性 PON 拥塞整形（流量成型） | True | `limit-speed-1m` |
| 有线连接·PON 管道保障（如楼宇直播） | True | `app-flow` |
| 单用户 WIFI 应用切片保障（仅对 WiFi 连接生效） | True | `assurance-app-slice` |
| 高保障 VIP 套餐 | True | `vip-assurance` |
| 不需要差异化承载 | False | 无 |

**CEI阈值参考**：常规场景默认 `70分`；直播/专线场景建议 `80分`；投诉处置建议 `85分`。

## How to Use

### 场景 1/2：从画像生成新方案

1. PlanningAgent 调用 `get_skill_instructions("plan_design")` 获取本指令
2. **强制**加载 `get_skill_reference("plan_design", "examples.md")` 查看 few-shot 样例（非可选；Instructional 范式 few-shot 是推理锚点）
3. **判据自检**：确认画像中以下字段是否齐全：`user_type / package_type / scenario / guarantee_target / guarantee_app / complaint_history`；字段缺失 → 回到 `goal_parsing`，**禁止补默认值**
4. 对照 §启用决策规则 确定各段落启用状态（注意 WIFI 覆盖弱特判优先级）
5. 对照 §业务默认值速查 逐字段推导 CEI模型 / CEI阈值 / 诊断场景 / 远程优化触发时间 / 业务类型等关键值
6. **格式自检**：每段字段名与 §输出结构契约 对齐；禁用段子字段是否全部为 `False` 或 `无`（不得留有真实业务值）
7. **不调用任何脚本**，直接用 LLM 推理生成 5 段方案
8. 把生成的方案交给 `plan_review` 校验
9. 校验完成后交回 PlanningAgent 主流程，由 Orchestrator 拆分派发

### 场景 4：编辑现有方案

当 PlanningAgent 收到 `[任务类型: 编辑方案]` 时：

1. PlanningAgent 已通过 `plan_store/read_plan.py` 获取当前方案文本
2. 加载本指令 `get_skill_instructions("plan_design")` 和 `get_skill_reference("plan_design", "examples.md")`
3. 解析用户的编辑指令，对照当前方案进行**局部修改**：
   - "将XX开启" → 对应字段改为 `True`
   - "将XX关闭" → 对应字段改为 `False`
   - "把XX改为YY" → 对应字段值修改为 `YY`
   - "编辑方案"（无具体指令）→ 展示当前方案，询问用户想修改哪些内容
4. 修改后的方案必须仍然符合 §输出结构契约 和 §禁用段子字段强制规范
5. **跳过 goal_parsing**（不需要槽位追问）
6. 仍需调用 `plan_review` 校验修改后的方案
7. 修改后的方案返回给 Orchestrator，走 §4.6 确认流程（含 save_plan 持久化）

**编辑操作示例**：

| 用户指令 | 修改动作 |
|---|---|
| "将偶发卡顿定界开启" | `故障诊断` 段 → `偶发卡顿定界：True` |
| "把CEI模型改为游戏模型" | `CEI体验感知` 段 → `CEI模型：游戏模型` |
| "开启差异化承载" | `差异化承载` 段 → `差异化承载：True`，并追问应用类型/保障应用/业务类型 |
| "关闭远程网关重启" | `远程优化` 段 → `远程网关重启：False` |
| "将CEI阈值调高到85分" | `CEI体验感知` 段 → `CEI阈值：85分` |

**注意**：当用户开启一个被禁用的段落（如差异化承载从 False → True），需要检查该段的必填子字段是否有值，若缺失则追问用户（例如：差异化承载开启后需要确认应用类型、保障应用和业务类型）。

## References

- `references/examples.md` — 4 个典型场景的 few-shot 样例（场景 1 直播完整方案 × 2 / 场景 2 区域稀疏方案 / 场景 2 变体 WIFI 覆盖弱）；每个样例含显式"决策链路"标注推导路径

## 禁止事项

- ❌ 不要凭空编造段落外的字段
- ❌ 不要使用 Markdown `##` 标题，段落标题必须是"中文名称 + 中文冒号"格式
- ❌ 不要写 `**启用**: true/false` 行（旧格式，已废弃）
- ❌ 不要把业务字段写成自由散文，子字段必须严格按 `字段名：值` 格式
- ❌ 不要猜测 schema 之外的参数
- ❌ 禁用段（主开关为 `False` 或整段跳过）的子字段禁止填真实业务值，一律写 `False` 或 `无`
- ❌ 不要把 `How to Use` 中的步骤 3 判据自检跳过，缺字段必须回到 `goal_parsing`
