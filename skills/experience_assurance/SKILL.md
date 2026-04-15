---
name: experience_assurance
description: "体验保障配置：调用 FAN 网络切片服务接口，创建体验保障配置任务，用于网络性能优化和保障"
---

# 体验保障配置

## Metadata
- **paradigm**: Tool Wrapper（封装 FAN 网络切片服务 app-flow/create-assure-config-task 接口）
- **when_to_use**: 创建体验保障配置任务，进行网络性能优化和保障
- **inputs**: CLI 参数（application-type / application / business-type）
- **outputs**: 脚本 stdout（执行过程日志 + 调用结果）+ returncode（0=成功，非 0=失败）

## Parameter Schema（Provisioning 按此从方案段落提参）

### 创建体验保障配置任务参数

| 字段                            | 类型 | 必填   | 默认值 | 允许值 | 说明            |
|-------------------------------|---|------|--|---|---------------|
| `application-type`            | string | 条件必填 | anchor-video | anchor-video/real-time-game/cloud-platform/online-office | 应用类型；仅 `business-type=experience-assurance` 时有效 |
| `application`                 | string | 条件必填 | TikTok | TikTok/Kwai/抖音/快手/王者荣耀/… | 保障应用名称；仅 `business-type=experience-assurance` 时有效 |
| `business-type`               | string | 是    | experience-assurance | experience-assurance / speed-limit / app-flow / assurance-app-slice / limit-speed-1m / 其他 FAN 策略名称 | 业务类型（直接映射 FAN 策略配置文件名称） |

注意: 只有业务类型为 `experience-assurance` 时需要指定 `application-type` 和 `application`；其他类型的 application 字段由脚本内部忽略

## When to Use

- ✅ 体验保障配置：需要创建体验保障配置任务进行网络优化
- ✅ 查询体验保障配置结果：根据设备IP、位置、ONU ID查询配置任务状态
- ❌ 只是想了解体验保障概念（直接回答即可）

## How to Use

1. 从方案段落按 schema 提取参数（`application-type` + `application` + `business-type`）
2. 组装 argparse CLI 参数列表，调用脚本：
   ```
   get_skill_script(
       "experience_assurance",
       "experience_assurance.py",
       execute=True,
       args=["--application-type", "anchor-video", "--application", "TikTok", "--business-type", "experience-assurance"],
       timeout=120
   )
   ```
   Provisioning Agent 调用本 Skill 时 `get_skill_script` 建议显式传 `timeout=120`，为"NCELogin 登录 + 业务接口"两轮网络交互留足预算。

3. 脚本内部流程：加载 `fae_poc/config.ini` → `NCELogin` 校验/获取 token → 调用 FAN 网络切片服务接口
4. 把返回的 `stdout` / `stderr` / `returncode` **原样透传**给用户

**CLI 参数连接符统一为空格**（argparse 标准），不要使用 `--ne-id: 12345678-1234-1234-1234-123456789999` 这类带冒号的写法。

## Scripts

- `scripts/experience_assurance.py` — FAN 网络切片服务体验保障配置接口调用入口（依赖项目根 `fae_poc/` 包中的 `NCELogin` 和 `config.ini`）


## Examples

**创建体验保障配置任务**：
```bash
python experience_assurance.py --application-type anchor-video --application TikTok --business-type experience-assurance
```

**创建限速配置任务**：
```bash
python experience_assurance.py --business-type speed-limit
```

**创建app-flow配置任务**：
```bash
python experience_assurance.py --business-type app-flow
```

## 脚本输出路径

```text
# 将结果输出为JSON文件
output_path = r'../output_dir'  # output_dir 和 script目录同级
output_file = os.path.join(output_path, "experience_assurance_output.json")
os.makedirs(output_path, exist_ok=True)
with open(output_file, 'w', encoding='utf-8') as f:
   json.dump(result, f, ensure_ascii=False, indent=2)
print(f"\n结果已保存到: {output_file}")
```


## 返回参数详情

### 查询体验保障配置任务返回参数

| 字段                   | 类型 | 说明 | 示例值 |
|----------------------|------|------|-------|
| `taskId`             | string | 任务ID | `b909cce2-7f68-4c89-9dd3-86017399d482` |
| `neName`             | string | 网络设备名称 | `200.30.33.63` |
| `neIp`               | string | 网络设备IP | `200.30.33.63` |
| `fsp`                | string | 设备位置（框/槽/端口）| `0/3/2` |
| `onuId`              | integer | ONU ID | `5` |
| `servicePortIndex`  | integer | 服务端口索引 | `3979` |
| `serviceName`        | string | 服务名称 | `103/0_3_2/5/1/多业务VLAN模式/1` |
| `configStatus`       | integer | 配置状态：0=已配置 | `0` |
| `runningStatus`      | integer | 运行状态：1=运行中 | `1` |
| `policyProfile`      | string | 策略配置 | `default-policy` |
| `limitProfile`       | string | 限速配置 | (空字符串) |
| `serviceType`        | string | 服务类型：assure=体验保障 | `assure` |
| `appCategory`        | string | 应用类别 | `anchor-video` |
| `appId`              | string | 应用ID | `0f5cb694-f20a-4baa-b692-f904b29989ad` |
| `appName`            | string | 应用名称 | `Tencent START Cloud Game` |
| `startTime`          | string | 开始时间 | `2025-12-15 19:46:35` |
| `timeLimit`          | integer | 时间限制：-1=无限制 | `-1` |


## 禁止事项

- ❌ 不做业务规则推断（参数由 PlanningAgent 在方案段落里决定）
- ❌ 不在 Skill 脚本里硬编码 `base_url` / `csrf_token` / `cookie`，一律从 `fae_poc/config.ini` 读取
- ❌ 不在参数里填无效的 UUID 格式（会被 FAN 网络切片服务平台拒绝）
- ❌ 不要在 Provisioning Agent 里自己拼装 FAN 网络切片服务接口 JSON，统一通过本 Skill 的 CLI 入口
- ❌ 不要改写脚本 stdout，原样透传给用户
- ❌ 不要修改接口返回的 JSON 格式，保持与 FAN 网络切片服务平台一致
