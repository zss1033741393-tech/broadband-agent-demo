# 故障诊断参数说明

本文件为 `fault_diagnosis` Skill 的 L3 参考：**只在脚本执行时按需加载**，不占用 Agent 常驻上下文。

Skill 调用前，Provisioning 根据这里的映射规则推导 `scenario` / `query-type` / `query-value` 三个必填参数。

## 1. `scenario` 枚举与推导规则

FAE 平台仅支持以下 4 个故障场景，枚举值使用**下划线写法**，大小写敏感：

| 值 | 含义 | 典型触发画像 / 关键词 |
|---|---|---|
| `NETWORK_ACCESS_SLOW` | 上网慢 | 普通套餐 + 投诉关键词含"网慢 / 慢 / 卡 / 速率低"；无具体业务场景时的默认 |
| `NETWORK_ACCESS_FAILURE` | 无法上网 | 投诉关键词含"断网 / 掉线 / 上不了网 / 无网络"；紧急恢复场景 |
| `LIVE_STUTTERING` | 直播卡顿 | 直播套餐 / 保障应用含"直播 / 抖音 / 快手 / B 站"；走播类场景 |
| `GAME_STUTTERING` | 游戏卡顿 | 游戏类用户 / 保障应用含"王者荣耀 / 吃鸡 / Steam / 原神"等 |

**PlanningAgent 推导路径**（写入 `## 故障诊断方案 - 故障场景` 字段）：
1. 先看"保障应用" → 直播类 → `LIVE_STUTTERING`；游戏类 → `GAME_STUTTERING`
2. 否则看"套餐" → 直播套餐 → `LIVE_STUTTERING`；游戏用户 → `GAME_STUTTERING`
3. 否则看"投诉历史关键词" → 含断网 → `NETWORK_ACCESS_FAILURE`；其余 → `NETWORK_ACCESS_SLOW`
4. 全部无法推导 → `NETWORK_ACCESS_SLOW`（兜底）

**Provisioning 场景 3 推导路径**（直接从用户原话识别）：
- "直播 / 抖音卡" → `LIVE_STUTTERING`
- "游戏卡 / 延迟高" → `GAME_STUTTERING`
- "断网 / 上不了网" → `NETWORK_ACCESS_FAILURE`
- "网慢 / 速率低" → `NETWORK_ACCESS_SLOW`
- 含糊不清 → 向用户追问"具体什么现象"，不要自己猜

## 2. `query-type` 选取优先级与取值含义

`query-type` 决定用哪种设备标识作为诊断范围。选取原则：**越细粒度越优**。

| 值 | 含义 | 粒度 | 示例值 | 选取优先级 |
|---|---|---|---|---|
| `ontResId` | ONT 资源 ID（终端设备级） | ★★★★★ 最细 | `10.25.81.249/0/1/0/7` | 1（最优先） |
| `uniUuid` | UNI UUID（接入单元级） | ★★★★ | `a1cffe38-4855-4d52-beb8-6c1ba6594ef1` | 2 |
| `ponResId` | PON 资源 ID（PON 口级） | ★★★ | `2604843250000002` | 3 |
| `gatewayId` | 网关 ID（家庭网关级） | ★★★ | `GATEWAY001` | 4 |
| `oltResId` | OLT 资源 ID（局端级） | ★ 最粗 | `10.25.81.249/0/1/0` | 5（仅整 OLT 排查） |

**FAE 平台建议优先使用 `ontResId`**：它能精准定位到具体接入终端，诊断结果最贴近单用户体验问题。只有在 `ontResId` 缺失或要求 OLT / PON 级粗筛时才退化到更粗粒度。

## 3. 从 `cei_score_query` 结果提取 `query-value` 的映射

保障链第 3 步的 `query-value` 来自上一步 `cei_score_query` 返回的 `rows[]`（第一行通常即低分 Top 1 目标用户）：

| Provisioning 选取的 query-type | 对应 `rows[0]` 的字段 | 字段示例 |
|---|---|---|
| `ontResId` | `ontResId` | `10.25.81.222/0/1/2/5` |
| `uniUuid` | `uniUuid` | `647e35d3-1da4-4a76-bc65-0dd82fd9a280` |
| `ponResId` | `ponSn` | `2604843250000066` |
| `gatewayId` | `gatewayMac` 或其他网关标识（按 FAE 平台定义对齐） | `AB:10:00:00:97:50` |
| `oltResId` | 从 `ontResId` 截取 OLT 前缀 | `ontResId=10.25.81.222/0/1/2/5` → `oltResId=10.25.81.222/0/1/2` |

**提取流程**：
1. 读 `rows[0]`（评分最低的目标用户）
2. 按 `query-type` 优先级从上到下找：`ontResId` 存在 → 用它；否则 `uniUuid` → `ponSn` → `gatewayMac`
3. 若 `rows[]` 为空（CEI 查询无低分用户）→ 整体体验达标，跳过本 Skill，在 Provisioning 状态行写明原因

## 4. 常用参数组合建议

以下为故事线 1（"直播套餐卖场走播保抖音，曾投诉卡顿"）在不同阶段的推荐组合：

| 阶段 | `scenario` | `query-type` | `query-value` 来源 |
|---|---|---|---|
| 保障链 · 直播场景低分用户定位 | `LIVE_STUTTERING` | `ontResId` | `cei_score_query.rows[0].ontResId` |
| 场景 3 · 用户直接报"抖音卡" | `LIVE_STUTTERING` | `ontResId` 或 `uniUuid` | 从用户原话或关键画像提取 |
| 场景 3 · 用户报"游戏延迟高" | `GAME_STUTTERING` | `ontResId` | 同上 |
| 场景 3 · 用户报"整 PON 范围慢" | `NETWORK_ACCESS_SLOW` | `ponResId` | 关键画像 `priority_pons` |
| 场景 3 · 运维侧 OLT 粗筛 | `NETWORK_ACCESS_SLOW` | `oltResId` | 关键画像中的 OLT 标识 |

## 5. FAE 返回结构

query 阶段返回体由脚本做字段白名单过滤后原样输出到 stdout。调用方可稳定依赖以下顶层字段（具体平台端字段清单以 FAE 文档为准，本 Skill 不扩展白名单）：

- `taskId` — 诊断任务 ID（与 start 阶段返回的一致，便于运维回溯）
- `status` — 任务终态（如 `success` / `failed` / `partial`）
- `scenario` — 回显请求场景
- `queryType` / `queryValue` — 回显请求目标
- `diagnoseResult` — 诊断结论主体（故障维度、根因、建议处置等，平台既定结构，不做二次解读）

## 6. 错误码与降级

| 场景 | stdout/returncode 形态 | Provisioning 处置建议 |
|---|---|---|
| 成功 | `returncode=0` + query 结果 JSON | 把诊断结论作为上下文进入远程闭环决策 |
| FAE 侧业务错误 | `returncode!=0` + `errorCode/errorMsg` | 在 assistant 状态行标 `❌`，摘要 `errorMsg` 指针，终止链路 |
| 轮询超时 | `status=failed, stage=poll_timeout` | 标 `⚠️`，告知用户"诊断超时未返回，建议人工介入" |
| 部署未完成 | `status=failed, stage=deployment_check` | 明示部署 NCELogin + config.ini，不要重试 |
