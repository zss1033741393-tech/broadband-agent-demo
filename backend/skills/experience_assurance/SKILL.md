---
name: experience_assurance
description: "体验保障：调用 FAN 网络切片服务 app-flow/create-assure-config-task 接口，创建应用级体验保障配置任务（用户侧业务概念为『差异化承载』）"
---

# 体验保障（差异化承载 · FAN 侧实现）

## Metadata
- **paradigm**: Tool Wrapper（封装 FAN 网络切片服务 app-flow/create-assure-config-task 接口）
- **when_to_use**: 场景 1 综合目标方案里 `差异化承载方案` 启用时；场景 3 用户要求"开切片 / 应用保障 / 差异化承载"时
- **inputs**: CLI 参数（argparse）
- **outputs**: 脚本 stdout（执行过程日志 + FAN 接口返回 JSON）+ returncode（0=成功，非 0=失败）

## Parameter Schema（Provisioning 按此从"业务字段 → 技术参数"映射后提参）

| 字段 | 类型 | 必填 | 默认值 | 允许值 / 推导提示 |
|---|---|---|---|---|
| `--ne-id` | string (UUID) | 是 | — | 网元 ID。demo 阶段由 Provisioning 按 mock 规则提供（详见 `references/assurance_parameters.md` §3），未来接入设备发现 Skill 后来自真实查询 |
| `--service-port-index` | int | 是 | — | 0–65535。demo 阶段默认 `0`，可由方案段落"切片类型"隐式推导（详见 references §5） |
| `--policy-profile` | string | 是 | — | `defaultProfile` / `customProfile` / 平台允许的自定义名。由方案段落"切片类型 / 带宽保障"映射（详见 references §4） |
| `--onu-res-id` | string (UUID) | 是 | — | ONU 资源 ID。demo 阶段 mock，真实环境来自关键画像或设备发现 |
| `--app-id` | string (UUID) | 是 | — | 应用 ID（平台侧应用目录 UUID）。由方案段落"保障应用"通过**应用字典查找**得到（字典见 references §2） |
| `--config` | string | 否 | `str(DEFAULT_CONFIG_PATH)` | `fae_poc/config.ini` 绝对路径 |

**5 个必填 UUID / 枚举参数全部必须提供**，缺一无法调用 FAN 接口。业务字段到这些参数的映射规则、demo 阶段 mock 值表、应用字典统一收敛到 `references/assurance_parameters.md`（L3 加载）。

**本 Skill 不做业务规则判断**：业务字段（保障应用 / 切片类型 / 白名单 / 带宽保障）由 PlanningAgent 在方案段落写入；业务 → 技术参数的映射由 Provisioning 层参照 references 完成；Skill 只负责"CLI 参数 → FAN 接口 → stdout 透传"。

## When to Use

- ✅ 场景 1（综合目标）方案段落 `## 差异化承载方案 **启用**: true` 时 → 派发给 `provisioning-delivery` 实例执行
- ✅ 场景 3（单点指令）用户要求"开通切片 / 应用保障 / Appflow / 差异化承载 / 白名单" → 任务头 `[任务类型: 差异化承载开通]`
- ❌ 用户咨询切片 / 体验保障概念（直接回答 + 引用 `references/assurance_parameters.md` 即可）
- ❌ 用户要求调整权重 / 查 CEI / 故障诊断（走 `cei_pipeline` / `cei_score_query` / `fault_diagnosis`）
- ❌ 用户原话未指定保障应用 → 场景 3 **必须追问**"保障哪个应用"，不得猜测（见 `provisioning.md` §5 的 `provisioning-delivery` 特殊行为）

## How to Use

1. 按方案段落的业务字段（`切片类型 / 保障应用 / 白名单 / 带宽保障`）对照 `references/assurance_parameters.md` 做"业务 → 5 个技术参数"映射
2. 按 argparse CLI 展开为 `List[str]`，调用脚本：
   ```
   get_skill_script(
       "experience_assurance",
       "experience_assurance.py",
       execute=True,
       args=[
           "--ne-id", "12345678-1234-1234-1234-123456789999",
           "--service-port-index", "0",
           "--policy-profile", "defaultProfile",
           "--onu-res-id", "12345678-1234-1234-1234-123456789999",
           "--app-id", "12345678-1234-1234-1234-123456789999",
       ],
       timeout=120,
   )
   ```
3. 脚本内部流程：加载 `fae_poc/config.ini` → `NCELogin` 校验/获取 token → 调用 FAN `app-flow/create-assure-config-task` 接口
4. 把 `stdout` / `stderr` / `returncode` **原样透传**给调用方

**CLI 参数连接符统一为空格**（argparse 标准）。UUID 参数**必须符合标准 UUID 格式**（`8-4-4-4-12` 十六进制 + 连字符），否则会被 FAN 平台拒绝。

## Scripts

- `scripts/experience_assurance.py` — FAN 网络切片服务 `app-flow/create-assure-config-task` 接口调用入口（依赖项目根 `fae_poc/` 包中的 `NCELogin` 和 `config.ini`，与 `cei_pipeline` / `cei_score_query` / `fault_diagnosis` / `remote_optimization` 共享同一套基础设施）

## References

- `references/assurance_parameters.md` — 业务字段到 CLI 参数的完整映射表（切片类型 → policy-profile / 应用 → app-id 字典 / 带宽保障的处理 / demo 阶段 ne-id / onu-res-id / service-port-index 的 mock 规则 / FAN 返回白名单字段 / 错误码降级）

## Examples

**场景 1 保障抖音直播（默认策略）**：
```bash
python experience_assurance.py --ne-id 12345678-1234-1234-1234-123456789999 --service-port-index 0 --policy-profile defaultProfile --onu-res-id 12345678-1234-1234-1234-123456789999 --app-id 12345678-1234-1234-1234-123456789999
```

**自定义策略（方案段落声明了带宽保障或特殊白名单时）**：
```bash
python experience_assurance.py --ne-id 12345678-1234-1234-1234-123456789999 --service-port-index 1 --policy-profile customProfile --onu-res-id 12345678-1234-1234-1234-123456789999 --app-id 22345678-1234-1234-1234-123456789999
```

**指定配置文件（Windows 绝对路径覆盖默认）**：
```bash
python experience_assurance.py --ne-id 12345678-1234-1234-1234-123456789999 --service-port-index 0 --policy-profile defaultProfile --onu-res-id 12345678-1234-1234-1234-123456789999 --app-id 12345678-1234-1234-1234-123456789999 --config C:/path/to/fae_poc/config.ini
```

## 脚本实现约束（脚本作者必须遵守）

本 Skill 脚本封装真实 FAN 接口，与 `cei_pipeline` / `cei_score_query` / `fault_diagnosis` / `remote_optimization` 共享以下 4 条硬性约束。违反任一条都会导致 agno 执行失败或挂起：

1. **首行必须是 shebang** `#!/usr/bin/env python3`
   否则 Windows 下 agno 报 `[WinError 193] %1 不是有效的 Win32 应用程序`。

2. **顶部必须做 `fae_poc` sys.path 双路径注入**
   ```python
   _PROJECT_ROOT = Path(__file__).resolve().parents[3]
   _FAE_POC_DIR = _PROJECT_ROOT / "fae_poc"
   for _p in (str(_PROJECT_ROOT), str(_FAE_POC_DIR)):
       if _p not in sys.path:
           sys.path.insert(0, _p)
   from fae_poc import DEFAULT_CONFIG_PATH, require_config
   ```

3. **argparse `--config` 默认值必须用 `str(DEFAULT_CONFIG_PATH)`**（绝对路径）
   禁止 `default='../../config.ini'` 这类相对路径 —— agno 运行脚本时 `cwd` 由框架决定，相对路径会解析错位。

4. **所有 `requests` 调用必须显式传 `timeout=(connect, read)`**
   包含 `NCELogin` 内部和 FAN 接口调用。例如 `session.post(..., timeout=(5, 15))`。否则一旦网络不通就会挂到 agno 外层 timeout 被强杀。

Provisioning Agent 调用本 Skill 时 `get_skill_script` 建议显式传 `timeout=120`，为"NCELogin 登录 + FAN 接口"两轮网络交互留足预算。

## 依赖与部署

`scripts/experience_assurance.py` 与 `cei_pipeline` / `cei_score_query` / `fault_diagnosis` / `remote_optimization` 共享 `fae_poc/` 包。初次部署：

1. 把本地 `NCELogin.py` 拷贝到 `fae_poc/NCELogin.py`（已 `.gitignore`）
2. 把 `fae_poc/config.ini.example` 复制为 `fae_poc/config.ini` 并填入真实 `base_url` / `csrf_token` / `cookie`（已 `.gitignore`）
3. config.ini 需包含 `[API]`（`ip` / `port`）和 `[AuthTokens]`（`x-uni-crsf-token` / `cookie`）两节

未完成部署时脚本应以结构化 JSON 返回 `status=failed, stage=deployment_check`，不要 crash（与同族 FAE Skill 的降级行为一致）。

## 方案字段映射（plan_design → CLI 参数）

Provisioning 从 `差异化承载：` 段落提取以下字段并按此表翻译为 CLI 参数：

| 方案字段 | 值 | CLI 映射 |
|---|---|---|
| `差异化wifi切片` | `False` | 整段跳过，不派发本 Skill |
| `差异化wifi切片` | `True` | 继续提取其余字段 |
| `APP Flow` | `True` | `slice_type=appflow_traffic_shaping` → `--policy-profile` 选流量成型策略 |
| `APP Flow` | `False` | `slice_type=application_slice` → `--policy-profile` 选应用切片策略 |
| `保障应用` | `<app_name>` | → `--target-app <app_name>` |
| `应用策略` | `<profile>` | → `--policy-profile <profile>`（如 `limit-speed-1m` / `assurance-app-slice`） |

注：`ne-id` / `service-port-index` / `onu-res-id` / `app-id` 等设备级 UUID 参数仍从 `references/assurance_parameters.md` 按设备 mock 表或真实画像查找，方案字段不包含此类参数。

## 禁止事项

- ❌ 不做业务规则推断（`保障应用 / 策略选择` 由 PlanningAgent 在方案段落决定，业务 → UUID 映射由 Provisioning 按 references 执行）
- ❌ 不在脚本里硬编码 `base_url` / `csrf_token` / `cookie`，一律从 `fae_poc/config.ini` 读取
- ❌ 不在脚本里实现"业务字段 → UUID"映射（那是 Provisioning 层的职责，映射表见 references）
- ❌ 不扩展 / 修改 FAN 返回字段白名单，保持与平台一致
- ❌ 不改写脚本 stdout，原样透传
- ❌ 不在 Provisioning Agent 里自己拼装 FAN 接口 JSON，统一通过本 Skill CLI 入口
