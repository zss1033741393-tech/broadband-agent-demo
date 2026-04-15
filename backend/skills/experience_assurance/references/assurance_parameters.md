# 体验保障参数说明（业务字段 ↔ FAN CLI 参数映射）

本文件为 `experience_assurance` Skill 的 L3 参考：**只在 Provisioning 执行 `provisioning-delivery` 业务时按需加载**，不占用 Agent 常驻上下文。

Skill 调用前，Provisioning 根据这里的映射规则，把方案段落里的 4 个业务字段（`切片类型 / 保障应用 / 白名单 / 带宽保障`）映射到 5 个 CLI 参数（`ne-id / service-port-index / policy-profile / onu-res-id / app-id`）。

> **demo 阶段说明**：项目当前处于 POC 阶段，设备级 UUID（`ne-id` / `onu-res-id`）尚无设备发现 Skill 可查询，**统一使用 §3 的 mock 默认值**。接入真实设备发现后，本文件 §3 会被替换为运行时查询说明，届时 Provisioning / Skill 调用方不用改。

## 1. 业务字段 → CLI 参数 映射总表

| 方案段落业务字段 | CLI 参数 | 映射规则 |
|---|---|---|
| `切片类型` | `--policy-profile` | 见 §4 策略映射 |
| `保障应用` | `--app-id` | 查 §2 应用字典（demo 为 mock UUID） |
| `带宽保障 (Mbps)` | 影响 `--policy-profile` 的选择 | 非零且需特殊带宽保障时 → `customProfile`；否则 `defaultProfile` |
| `白名单` | 影响 `--policy-profile` 的选择 | 列表非空（有特定域名/IP 白名单）时 → `customProfile`；为"无"时 → `defaultProfile` |
| —（无业务字段） | `--ne-id` | 见 §3 demo mock |
| —（无业务字段） | `--onu-res-id` | 见 §3 demo mock |
| —（无业务字段） | `--service-port-index` | 见 §5 索引策略 |

## 2. 应用字典（`保障应用` → `--app-id` UUID）

demo 阶段使用以下 mock UUID。接入真实应用目录后，本表由上游数据同步。

| 保障应用 | `--app-id` (UUID) | 说明 |
|---|---|---|
| 抖音 | `12345678-1234-1234-1234-123456789001` | 直播类 |
| 快手 | `12345678-1234-1234-1234-123456789002` | 直播类 |
| B 站 | `12345678-1234-1234-1234-123456789003` | 视频类 |
| 王者荣耀 | `12345678-1234-1234-1234-123456789004` | 游戏类 |
| 和平精英 / 吃鸡 | `12345678-1234-1234-1234-123456789005` | 游戏类 |
| 原神 | `12345678-1234-1234-1234-123456789006` | 游戏类 |
| Steam | `12345678-1234-1234-1234-123456789007` | 游戏下载 / 游戏类 |
| 视频类流量（综合） | `12345678-1234-1234-1234-123456789010` | 聚合标签，场景 2 区域治理常用 |
| 兜底（未命中） | `12345678-1234-1234-1234-123456789000` | 未识别应用 → 使用兜底 UUID + 状态行标 `⚠️ 未命中应用字典，已使用兜底保障` |

**匹配规则**：
1. 精确匹配（字典 key 完全一致）
2. 别名/包含匹配（"抖音直播" → 抖音 / "吃鸡" → 和平精英）
3. 全部未命中 → 兜底 UUID + 状态行警告

## 3. 设备级 UUID（`--ne-id` / `--onu-res-id`）的 demo mock

demo 阶段没有设备发现 Skill，Provisioning 调用本 Skill 时**统一使用**：

```
--ne-id       12345678-1234-1234-1234-123456789999
--onu-res-id  12345678-1234-1234-1234-123456789999
```

**Provisioning 使用纪律**：
- 状态行必须显式标注 `【demo mock · 设备 UUID 为占位】`，告知用户当前不是真实绑定某台设备的操作
- 未来接入设备发现 Skill 后，本 §3 的 mock 值替换为"从关键画像或设备发现 Skill 获取"的说明，**调用方代码路径不变**

## 4. `policy-profile` 策略映射

由方案段落的 `切片类型` + `带宽保障` + `白名单` 三字段联合决定：

| 方案段落业务组合 | `--policy-profile` |
|---|---|
| `切片类型: application_slice` + 白名单为"无" + 带宽 ≤ 50 Mbps | `defaultProfile` |
| `切片类型: application_slice` + 白名单非空 或 带宽 > 50 Mbps | `customProfile` |
| `切片类型: appflow_traffic_shaping` + 白名单为"无" | `defaultProfile` |
| `切片类型: appflow_traffic_shaping` + 白名单非空 | `customProfile` |
| 用户/方案显式指定其他 profile 名（demo 阶段可自定义，FAN 侧已存在该 profile） | 直接透传该名 |

**兜底**：方案段落缺失 `切片类型` 字段时 → `defaultProfile` + 状态行警告"切片类型缺失，使用默认策略"。

## 5. `service-port-index` 索引策略

- demo 阶段：统一取 `0`
- 未来实际部署时：由设备发现 Skill 或关键画像里的"业务端口"字段确定，允许 0–65535

Provisioning 调用时 `--service-port-index 0` 即可覆盖故事线 1 的所有场景。

## 6. FAN 返回结构

脚本按接口既定字段白名单过滤返回体后原样输出到 stdout。调用方可稳定依赖以下顶层字段（具体以 FAN 平台文档为准，本 Skill 不扩展白名单）：

- `taskId` — 创建的保障配置任务 ID
- `status` — 创建结果（如 `success` / `failed` / `partial`）
- `errorCode` / `errorMsg` — 错误码 / 错误文案（成功时为空）
- `createdAt` — 任务创建时间戳

## 7. 错误码与降级

| 场景 | stdout / returncode 形态 | Provisioning 处置建议 |
|---|---|---|
| 成功 | `returncode=0` + 创建结果 JSON（含 `taskId`） | 状态行标 `✅ 已下发保障配置，taskId=<...>` |
| FAN 侧业务错误（如 UUID 不存在 / 策略不支持） | `returncode!=0` + `errorCode/errorMsg` | 状态行标 `❌`，摘要 `errorMsg` 作为指针，不自动重试；提示用户确认 `保障应用` / `策略配置` 是否正确 |
| 部署未完成 | `status=failed, stage=deployment_check` | 明示部署 NCELogin + config.ini，不要重试 |
| 应用字典未命中 | 脚本正常调用（用兜底 UUID） | 状态行标 `⚠️ 未命中应用字典，已使用兜底 UUID，建议上游补齐字典` |

## 8. 映射示例（故事线 1 · 直播套餐卖场走播保抖音）

方案段落：
```markdown
## 差异化承载方案
**启用**: true
- 切片类型: application_slice
- 保障应用: 抖音
- 白名单: 抖音域名/IP, douyin.com, *.douyinstatic.com
- 带宽保障 (Mbps): 50
```

映射结果：

| CLI 参数 | 值 | 来源 |
|---|---|---|
| `--policy-profile` | `customProfile` | 白名单非空 → §4 customProfile |
| `--app-id` | `12345678-1234-1234-1234-123456789001` | 查 §2 抖音条目 |
| `--ne-id` | `12345678-1234-1234-1234-123456789999` | §3 demo mock |
| `--onu-res-id` | `12345678-1234-1234-1234-123456789999` | §3 demo mock |
| `--service-port-index` | `0` | §5 demo 默认 |

调用：
```
get_skill_script(
    "experience_assurance",
    "experience_assurance.py",
    execute=True,
    args=[
        "--ne-id", "12345678-1234-1234-1234-123456789999",
        "--service-port-index", "0",
        "--policy-profile", "customProfile",
        "--onu-res-id", "12345678-1234-1234-1234-123456789999",
        "--app-id", "12345678-1234-1234-1234-123456789001",
    ],
    timeout=120,
)
```

Provisioning 状态行：
```
✅ 已下发抖音差异化承载配置（customProfile），taskId=<...>
【demo mock · 设备 UUID 为占位，真实绑定待接入设备发现 Skill】
```
