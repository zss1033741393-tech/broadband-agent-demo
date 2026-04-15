---
name: fault_diagnosis
description: "故障诊断：调用 FAE 平台 fault-diagnosis 接口，一次 tool call 内部完成 start → poll → query 全流程，返回当前场景的故障诊断结果"
---

# 故障诊断

## Metadata
- **paradigm**: Tool Wrapper（封装 FAE 平台 fault-diagnosis/action 接口，脚本内部编排 start + poll + query 三阶段）
- **when_to_use**: ProvisioningCeiChainAgent 在保障链第 3 步需要获取指定设备在指定故障场景下的诊断结论时，或场景 3 单点故障诊断查询时
- **inputs**: CLI 参数（argparse）
- **outputs**: 脚本 stdout（最终诊断结果 JSON）+ stderr（start / poll 进度日志）+ returncode（0=成功，非 0=失败）

## Parameter Schema（Provisioning 按此从方案段落 / 上一步上下文提参）

| 字段 | 类型 | 必填 | 默认值 | 允许值 / 推导提示 |
|---|---|---|---|---|
| `--scenario` | string | 是 | — | 4 个枚举值（**下划线分隔**）：`NETWORK_ACCESS_SLOW` / `NETWORK_ACCESS_FAILURE` / `LIVE_STUTTERING` / `GAME_STUTTERING`。来自方案段落 `故障场景` 字段（场景 1/2），或场景 3 从用户原话推导 |
| `--query-type` | string | 是 | — | `ontResId` / `uniUuid` / `gatewayId` / `oltResId` / `ponResId`。**选取优先级：`ontResId` > `uniUuid` > `ponResId` > `gatewayId` > `oltResId`**（越细粒度越优） |
| `--query-value` | string | 是 | — | 对应 `query-type` 的设备标识。保障链中**从上一步 `cei_score_query` 返回的 `rows[]` 提取**；场景 3 单点查询从用户原话或关键画像提取 |
| `--config` | string | 否 | `str(DEFAULT_CONFIG_PATH)` | `fae_poc/config.ini` 绝对路径 |

**三参（`scenario` + `query-type` + `query-value`）必须同时提供**，缺一无法调用 FAE 接口。scenario 推导规则、query-type 选取建议、从 `cei_score_query` 结果提取 query-value 的映射、常用参数组合建议详见 `references/diagnosis_parameters.md`（L3 加载）。

**本 Skill 不做业务规则判断**：`scenario` 由 PlanningAgent 在方案段落里指定，`query-type` / `query-value` 由 Provisioning 从上一步结果或画像推导后以 CLI 参数传入。Skill 只负责"参数 → CLI → FAE 接口编排 → stdout 透传"。

## 内部编排（一次 tool call 内部三阶段）

脚本内部按以下顺序自驱，Agent 侧**只感知为一次 `get_skill_script` 调用**：

1. **start** — 以 `scenario + query-type + query-value` 启动诊断任务，返回 `taskId`
2. **poll** — 按固定间隔轮询任务状态（脚本内部常量，不对外暴露），直至状态为终态或达到 `MAX_POLL_SECONDS`
3. **query** — 拉取诊断结果并输出到 stdout

start / poll 的进度信息走 stderr，不污染 stdout 主体。

## When to Use

- ✅ 场景 1（综合目标）完整保障链第 3 步：`cei_score_query` 返回低分 rows 后，对目标设备在 `scenario` 下做故障诊断
- ✅ 场景 3（单点指令）用户要求"诊断卡顿 / 故障定界 / 故障诊断" → 任务头 `[任务类型: 单点故障诊断]`
- ❌ 用户咨询故障诊断概念或字段含义（直接回答 + 引用 `references/diagnosis_parameters.md` 即可）
- ❌ CEI 评分尚未采集（保障链中应先走 `cei_score_query`，本 Skill 依赖其产出的设备标识）
- ❌ 需要远程修复动作（应走 `remote_optimization`，本 Skill 只做诊断、不做处置）

## How to Use

1. 从方案段落提取 `scenario`；从关键画像或上一步 `cei_score_query` 的 `rows[]` 推导 `query-type` + `query-value`
2. 按 argparse CLI 展开为 `List[str]`，调用脚本：
   ```
   get_skill_script(
       "fault_diagnosis",
       "fault_diagnosis.py",
       execute=True,
       args=["--scenario", "LIVE_STUTTERING", "--query-type", "ontResId", "--query-value", "10.25.81.249/0/1/0/7"],
       timeout=180,
   )
   ```
3. 脚本内部流程：加载 `fae_poc/config.ini` → `NCELogin` 校验/获取 token → start → poll → query → 原样输出结果 JSON
4. 把 `stdout` / `stderr` / `returncode` **原样透传**给调用方

**CLI 参数连接符统一为空格**（argparse 标准）。`scenario` 枚举值**必须使用下划线写法**（`NETWORK_ACCESS_SLOW`），不要用驼峰或去下划线形式。

**`timeout` 建议 ≥ 180s**：本 Skill 内部含 start → poll → query 三轮网络交互 + 轮询等待，比纯单次查询耗时长。Provisioning 调用时显式设置 `timeout=180` 更稳妥。

## Scripts

- `scripts/fault_diagnosis.py` — FAE 平台 fault-diagnosis 接口调用入口（内部编排 start + poll + query；依赖项目根 `fae_poc/` 包中的 `NCELogin` 和 `config.ini`，与 `cei_pipeline` / `cei_score_query` / `remote_optimization` 共享同一套基础设施）

## References

- `references/diagnosis_parameters.md` — 诊断参数说明表（`scenario` 枚举含义与推导规则 / `query-type` 选取优先级与从 `cei_score_query` `rows[]` 的字段映射 / 常用参数组合建议 / FAE 返回结构白名单字段）

## Examples

**保障链第 3 步 · 直播卡顿场景 + ontResId 定位**：
```bash
python fault_diagnosis.py --scenario LIVE_STUTTERING --query-type ontResId --query-value 10.25.81.249/0/1/0/7
```

**保障链第 3 步 · 上网慢场景 + uniUuid 定位（投诉用户）**：
```bash
python fault_diagnosis.py --scenario NETWORK_ACCESS_SLOW --query-type uniUuid --query-value a1cffe38-4855-4d52-beb8-6c1ba6594ef1
```

**场景 3 · 游戏卡顿单点诊断 + PON 粒度**：
```bash
python fault_diagnosis.py --scenario GAME_STUTTERING --query-type ponResId --query-value 2604843250000002
```

**场景 3 · 无法上网故障 + 网关定位**：
```bash
python fault_diagnosis.py --scenario NETWORK_ACCESS_FAILURE --query-type gatewayId --query-value GATEWAY001
```

**指定配置文件（Windows 绝对路径覆盖默认）**：
```bash
python fault_diagnosis.py --scenario LIVE_STUTTERING --query-type ontResId --query-value 10.25.81.249/0/1/0/7 --config C:/path/to/fae_poc/config.ini
```

## 脚本实现约束（脚本作者必须遵守）

本 Skill 脚本封装真实 FAE 接口，与 `cei_pipeline` / `cei_score_query` / `remote_optimization` 共享以下 4 条硬性约束。违反任一条都会导致 agno 执行失败或挂起：

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
   包含 `NCELogin` 内部、start / poll / query 三个阶段的每一次 HTTP 调用。例如 `session.post(..., timeout=(5, 15))`。否则一旦 FAE 网络不通就会挂到 agno 外层 timeout 被强杀。

**额外约束（内部编排专属）**：

5. **poll 阶段必须有最大轮询时长与退出条件**
   脚本内部定义 `MAX_POLL_SECONDS` 和 `POLL_INTERVAL_SECONDS` 常量，超时后以结构化 JSON 返回 `status=failed, stage=poll_timeout`，不要死循环。

6. **start / poll 的中间日志输出到 stderr**
   query 阶段的最终结果 JSON 是 stdout 唯一主体，便于调用方解析；进度日志走 stderr。

## 依赖与部署

`scripts/fault_diagnosis.py` 与 `cei_pipeline` / `cei_score_query` / `remote_optimization` 共享 `fae_poc/` 包。初次部署：

1. 把本地 `NCELogin.py` 拷贝到 `fae_poc/NCELogin.py`（已 `.gitignore`）
2. 把 `fae_poc/config.ini.example` 复制为 `fae_poc/config.ini` 并填入真实 `base_url` / `csrf_token` / `cookie`（已 `.gitignore`）
3. config.ini 需包含 `[API]`（`ip` / `port`）和 `[AuthTokens]`（`x-uni-crsf-token` / `cookie`）两节

未完成部署时脚本应以结构化 JSON 返回 `status=failed, stage=deployment_check`，不要 crash（与同族 FAE Skill 的降级行为一致）。

## 方案字段映射（plan_design → CLI 参数）

Provisioning 从 `故障诊断：` 段落提取以下字段并按此表翻译为 CLI 参数：

**诊断场景 → `--scenario` 枚举值**

| 方案字段值（中文）| CLI 枚举值 |
|---|---|
| `直播卡顿` | `LIVE_STUTTERING` |
| `游戏卡顿` | `GAME_STUTTERING` |
| `无法上网` | `NETWORK_ACCESS_FAILURE` |
| `上网慢` | `NETWORK_ACCESS_SLOW` |

**偶发卡顿定界字段**

| 方案字段 | 值 | 处理方式 |
|---|---|---|
| `偶发卡顿定界` | `True` | 若脚本支持 `--intermittent-diagnosis` flag 则传入；否则记录在状态行供工程师参考 |
| `偶发卡顿定界` | `False` | 不传该 flag |

## 禁止事项

- ❌ 不做业务规则推断（`scenario` 由方案段落决定，`query-type/query-value` 由 Provisioning 从上一步推导）
- ❌ 不在脚本里硬编码 `base_url` / `csrf_token` / `cookie`，一律从 `fae_poc/config.ini` 读取
- ❌ 不扩展 / 修改 FAE 返回字段白名单，保持与平台一致
- ❌ 不改写 start / poll / query 任一阶段的 FAE 返回体，query 结果原样透传
- ❌ 不把 start / poll 的中间日志混入 stdout（应走 stderr）
- ❌ 不要在 Provisioning Agent 里自己拆分 start / poll / query 调用，统一通过本 Skill CLI 入口
- ❌ 不承担远程修复动作（那是 `remote_optimization` 的职责）
