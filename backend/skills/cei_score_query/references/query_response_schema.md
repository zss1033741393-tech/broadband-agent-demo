# CEI 体验查询返回体字段定义

本文件为 `cei_score_query` Skill 的 L3 参考：**只在脚本执行时按需加载**，不占用 Agent 常驻上下文。

## 1. 返回体顶层结构

FAE 平台 `cei-experience/userexperience/query` 接口返回 JSON，脚本只保留以下 7 个顶层字段（其余字段被白名单过滤丢弃）：

| 字段名 | 含义 | 说明 |
|---|---|---|
| `errorCode` | 错误码 | 接口调用错误码，`0` / `"0"` / `null` 代表成功 |
| `errorMsg` | 错误信息 | 失败时的错误文案，成功通常为空 |
| `rowStart` | 起始行号 | 本次查询返回的起始行号，与 `offset` 对应 |
| `rowEnd` | 结束行号 | 本次查询返回的结束行号 |
| `rowSize` | 总记录数 | 符合查询条件的总记录数（用于分页） |
| `headers` | 表头信息 | `rows[]` 的列顺序声明 |
| `rows` | 数据行 | 实际的 CEI 评分记录列表，每行字段定义见 §2 |

## 2. `rows[]` 行字段定义

每行代表一个 CEI 体验记录，字段集合如下：

| 字段名 | 含义 | 示例值 |
|---|---|---|
| `timePoint` | 时间点（毫秒时间戳） | `null` / `1775923200000` |
| `uniUuid` | UNI UUID（接入单元唯一标识） | `647e35d3-1da4-4a76-bc65-0dd82fd9a280` |
| `userName` | 用户名（PON 路径 + 端口） | `pk-lbc/0/1/2/5` |
| `pppoeAccount` | PPPoE 账号 | `pppoe74_0000108` |
| `gatewayMac` | 家庭网关 MAC | `AB:10:00:00:97:50` |
| `ceiScore` | 当前 CEI 分数 | `45` |
| `avgCeiScore` | 平均 CEI 分数（周期内） | `43` |
| `deductionDetails` | 扣分详情（按维度分解） | `业务质量: -30分 稳定性: -15分 ODN: -5分 OLT: -5分` |
| `experienceType` | 体验类型（与请求入参一致） | `0` / `1` / `2` |
| `ontResId` | ONT 资源 ID | `10.25.81.222/0/1/2/5` |
| `ponSn` | PON 序列号 | `2604843250000066` |
| `customizedId` | 自定义 ID（平台侧可选标识） | `null` |
| `ceiUserType` | CEI 用户类型（平台侧分类） | `null` |

调用方读取时：
- 低分 Top 场景通常看 `ceiScore` + `avgCeiScore` + `deductionDetails`
- 定位到具体设备时使用 `uniUuid` / `ontResId` / `ponSn` / `userName`
- `deductionDetails` 是文本结构，字段之间用空格分隔，每段形如 `<维度中文名>: -<扣分值>分`

## 3. `experience-type` 取值映射

| 值 | 含义 | 典型触发场景 |
|---|---|---|
| `0` | 用户体验 Top 低分用户 | 泛化"体验差的用户"排查；没有明确业务目标的巡检 |
| `1` | 业务体验 Top 低分用户 | 直播保障 / 游戏保障 / 专线保障 / 投诉"卡顿"溯源；**保障链评分回采默认值** |
| `2` | 家庭体验 Top 低分用户 | 整户网络体验巡检；家庭级别投诉（"家里网很卡"） |

Provisioning 推导规则：
- 任务头 `[任务类型: 完整保障链]` + 画像含"保障应用" → `1`
- 任务头 `[任务类型: 单点 CEI 查询]` + 用户原话含"家里 / 整家" → `2`
- 其余 → `1`（默认业务体验）

## 4. `cond-*` 三参联动

FAE 平台要求过滤条件三元组**同时提供或同时省略**：

```
--cond-name <字段名> --cond-value <字段值> --cond-operator <操作符>
```

| `cond-name` 取值 | 配合 `cond-value` 示例 | 用途 |
|---|---|---|
| `userName` | `pk-lbc/0/1/2/5` | 按 PON 路径定位用户（投诉用户处置常用） |
| `pppoeAccount` | `pppoe74_0000108` | 按 PPPoE 账号定位 |
| `gatewayMac` | `AB:10:00:00:97:50` | 按网关 MAC 定位 |
| `ponSn` | `2604843250000066` | 按 PON 序列号定位（整 PON 巡检） |

`cond-operator` 默认 `=`；FAE 平台允许的其他操作符（如 `like` / `in`）遵循平台文档，本 Skill 原样透传。

**典型推导场景**：
- 关键画像含具体投诉用户标识 → 填 `userName` / `pppoeAccount`
- 关键画像只有 PON 口范围（如"PON-2/0/5"）→ 填 `ponSn` 或留空让平台返回该区域的 Top 低分列表

## 5. 错误码与降级

| `errorCode` | 含义 | Provisioning 处置建议 |
|---|---|---|
| `0` / `"0"` / `null` | 成功 | 继续保障链下一步 |
| 非 0 | FAE 平台业务错误 | 在 assistant 状态行标注 `❌`，把 `errorMsg` 作为指针呈现，终止保障链 |
| 脚本返回 `status=failed, stage=deployment_check` | `fae_poc/` 未完成部署 | 明示用户部署 NCELogin + config.ini，不要重试 |
