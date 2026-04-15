# 体验保障参数说明（业务字段 ↔ CLI 参数映射）

本文件为 `experience_assurance` Skill 的 L3 参考：**只在 Provisioning 执行 `provisioning-delivery` 任务时按需加载**，不占用 Agent 常驻上下文。

Provisioning 根据这里的映射规则，把方案段落的 3 个业务字段（`应用类型 / 保障应用 / 业务类型`）映射到 3 个 CLI 参数（`--application-type / --application / --business-type`）后调用脚本。

> **设备级参数说明**：`--ne-id`/`--onu-res-id`/`--service-port-index` 已由脚本内部统一处理（demo 阶段使用 mock UUID），**Provisioning 无需传入这三个参数**。

---

## 1. 业务字段 → CLI 参数 映射总表

| 方案段落字段（差异化承载段） | CLI 参数 | 有效条件 |
|---|---|---|
| `应用类型` | `--application-type` | `业务类型=experience-assurance` 时有效；其它业务类型忽略此字段 |
| `保障应用` | `--application` | `业务类型=experience-assurance` 时有效；其它业务类型忽略此字段 |
| `业务类型` | `--business-type` | 必传 |

---

## 2. `应用类型`（`--application-type`）允许值

| 方案字段值 | CLI 值 | 对应场景 |
|---|---|---|
| 直播 / anchor-video | `anchor-video` | 直播类应用保障（抖音/快手等） |
| 游戏 / real-time-game | `real-time-game` | 实时游戏保障（王者荣耀/和平精英等） |
| 云 / cloud-platform | `cloud-platform` | 云平台类 |
| 会议 / online-office | `online-office` | 在线会议/办公类 |

**推导规则**（Provisioning 按此从方案段落 `保障应用` 字段推导 `--application-type`）：

| 保障应用 | 推荐 application-type |
|---|---|
| 抖音 / TikTok / 快手 / Kwai / B 站 / 虎牙 | `anchor-video` |
| 王者荣耀 / 和平精英 / 原神 / Steam / 游戏类 | `real-time-game` |
| 腾讯会议 / 钉钉 / Teams / Zoom | `online-office` |
| 无法推导（兜底） | `anchor-video` + 状态行标 `⚠️ 应用类型默认 anchor-video` |

---

## 3. `保障应用`（`--application`）值约定

直接从方案段落的 `保障应用：` 字段提取，透传到 `--application`。
脚本内部维护应用名 → mock app_id 的字典；未命中时使用兜底 UUID + stderr 警告，不影响调用。

常见值：`TikTok` / `Kwai` / `抖音` / `快手` / `B站` / `王者荣耀` / `和平精英`

---

## 4. `业务类型`（`--business-type`）允许值

`--business-type` 的值直接透传为 FAN 平台的策略配置文件名称，**不做枚举校验**，任何 FAN 侧已存在的策略名均可传入。

常用值：

| 方案字段值 | CLI 值 | 需要 application 参数 | 说明 |
|---|---|---|---|
| experience-assurance | `experience-assurance` | ✅ 需要 | WiFi 时隙切片（针对指定应用） |
| assurance-app-slice | `assurance-app-slice` | ❌ 脚本忽略 | 单用户应用切片保障（wifi 连接场景） |
| app-flow | `app-flow` | ❌ 脚本忽略 | APP Flow / PON 口切片（有线连接场景） |
| speed-limit | `speed-limit` | ❌ 脚本忽略 | PON 口大象流检测 + 限速 |
| limit-speed-1m | `limit-speed-1m` | ❌ 脚本忽略 | PON 口拥塞整形（1Mbps 限速） |
| vip-assurance | `vip-assurance` | ❌ 脚本忽略 | 高保障 VIP 套餐 |

**场景 → 业务类型选择**（plan_design SKILL.md §差异化承载已含完整规则，仅作备查）：

| plan_design 方案场景描述 | 推荐 business-type |
|---|---|
| 单用户 WiFi 体验保障（指定应用类型 + 保障应用） | `experience-assurance` |
| 单用户应用切片（wifi 连接，无需指定应用参数） | `assurance-app-slice` |
| 楼宇直播有线连接 / PON 口独占（无 wifi 参数） | `app-flow` |
| 区域性 PON 拥塞流量整形 | `limit-speed-1m` |
| 高保障 VIP 套餐 | `vip-assurance` |

---

## 5. 完整调用示例

### 示例 1 — 差异化承载保抖音（experience-assurance）

方案段落：
```text
差异化承载：
    差异化承载：True
    应用类型：直播
    保障应用：抖音
    业务类型：experience-assurance
```

CLI 调用：
```python
get_skill_script(
    "experience_assurance",
    "experience_assurance.py",
    execute=True,
    args=[
        "--application-type", "anchor-video",
        "--application", "抖音",
        "--business-type", "experience-assurance",
    ],
    timeout=120,
)
```

Provisioning 状态行：
```
✅ 已下发抖音体验保障配置（experience-assurance），taskId=<...>
【demo mock · 设备 UUID 为占位】
```

### 示例 2 — PON 口大象流限速（speed-limit）

方案段落：
```text
差异化承载：
    差异化承载：True
    应用类型：直播
    保障应用：抖音
    业务类型：speed-limit
```

CLI 调用：
```python
get_skill_script(
    "experience_assurance",
    "experience_assurance.py",
    execute=True,
    args=["--business-type", "speed-limit"],
    timeout=120,
)
```

---

## 6. 脚本输出协议

脚本向 stdout 输出**单行** JSON（其余进度信息写 stderr）：

```json
{
  "skill": "experience_assurance",
  "status": "ok",
  "business_type": "experience-assurance",
  "application_type": "anchor-video",
  "application": "抖音",
  "is_mock": true,
  "result": {
    "taskId": "b909cce2-7f68-4c89-9dd3-86017399d482",
    "neName": "200.30.33.63",
    "neIp": "200.30.33.63",
    "fsp": "0/3/2",
    "onuId": 5,
    "servicePortIndex": 0,
    "serviceName": "103/0_3_2/5/1/多业务VLAN模式/1",
    "configStatus": 0,
    "runningStatus": 1,
    "policyProfile": "defaultProfile",
    "limitProfile": "",
    "serviceType": "assure",
    "appCategory": "anchor-video",
    "appId": "12345678-1234-1234-1234-123456789001",
    "appName": "抖音",
    "startTime": "2025-12-15 19:46:35",
    "timeLimit": -1
  },
  "output_file": "skills/experience_assurance/output_dir/experience_assurance_output.json"
}
```

错误路径：`{"skill": "experience_assurance", "status": "error", "message": "..."}`

---

## 7. 错误码与降级

| 场景 | stdout / returncode 形态 | Provisioning 处置建议 |
|---|---|---|
| 成功（真实或 mock） | `status=ok` + result JSON | 状态行标 `✅`；若 `is_mock=true` 追加 `【demo mock · 设备 UUID 为占位】` |
| FAE 侧业务错误 | `status=error` + `message` | 状态行标 `❌`，摘要 message，不自动重试 |
| 参数解析失败 | `status=error` + `message` | 状态行标 `❌`，检查方案段落 `业务类型`/`应用类型`/`保障应用` 字段 |
| 应用字典未命中 | `status=ok`（使用兜底 UUID）| 脚本 stderr 有警告；状态行标 `⚠️ 未命中应用字典，已使用兜底 UUID` |
