---
name: remote_optimization
description: "远程优化（远程闭环）：调用 FAE 平台批量优化接口，针对不同故障的用户下发设备重启/信道切换/功率调整等整改动作"
---

# 远程优化

## Metadata
- **paradigm**: Tool Wrapper（封装 FAE 平台 manual batch optimize 接口）
- **when_to_use**: 单用户故障保障，需要远程下发整改动作
- **inputs**: CLI 参数（strategy / rectification_method / operation_time / config）
- **outputs**: 脚本 stdout（执行过程日志）+ returncode（0=成功，非 0=失败）

## Parameter Schema（Provisioning 按此从方案段落提参）

| 字段 | 类型 | 必填 | 默认值 | 允许值 | 说明 |
|---|---|---|---|---|---|
| `strategy` | string | 是 | `immediate` | `immediate` / `idle` / `scheduled` | 执行策略 |
| `rectification_method` | list[int] | 否 | 空（代表"全部"） | `[1,2,3,4]` 的任意子集 | 整改方式编号列表 |
| `operation_time` | string | 条件必填 | `0-0-0-*-*-*` | 6 段 cron（用 `-` 分隔） | 仅 `strategy=scheduled` 时有效 |
| `config` | string | 否 | `fae_poc/config.ini` 绝对路径 | — | config.ini 路径 |

### strategy 语义

| 值 | 含义 | 内部编码 |
|---|---|---|
| `immediate` | 立即执行 | `1` |
| `idle` | 闲时执行 | `2` |
| `scheduled` | 定时执行（必须配 `operation_time`） | `3` |

### rectification_method 取值

| 值 | 含义 |
|---|---|
| `1` | 设备重启 |
| `2` | 信道切换 |
| `3` | 2.4G 功率调整 |
| `4` | 5G 功率调整 |
| 不传 / 空 | 全部整改方式 |

### operation_time 格式

6 段 cron，**用 `-` 分隔**（非空格），脚本内部会转换为空格分隔的 cron 表达式传给 FAE 接口：

```
秒-分-时-日-月-周
0-0-0-*-*-*   # 每天 00:00:00
0-30-2-*-*-*  # 每天 02:30:00
```

**本 Skill 不做业务规则判断**：整改方式组合 / 执行策略由 PlanningAgent 在方案段落里决定，本 Skill 只做"参数 → CLI → 接口调用"的映射。

## When to Use

- ✅ 单用户故障保障：需要对指定故障用户下发远程整改动作
- ✅ 场景 1（综合目标）"远程闭环处置方案"段落启用时 → 完整保障链第三步
- ✅ 场景 3（单点指令）"立即重启网关" / "闲时远程优化" → 任务头 `[任务类型: 单点远程操作]`
- ❌ 需要现场工程师处置的硬件故障
- ❌ 区域性拥塞问题（应走 `experience_assurance`）
- ❌ 用户只是咨询概念（直接回答即可）

## How to Use

1. 从方案段落按 schema 提取参数（`strategy` + `rectification_method` 列表 + 可选 `operation_time`）
2. 组装 argparse CLI 参数列表，调用脚本：
   ```
   get_skill_script(
       "remote_optimization",
       "manual_batch_optimize.py",
       execute=True,
       args=["--strategy", "idle", "--rectification-method", "1,2,3,4"],
       timeout=120
   )
   ```
3. 脚本内部流程：加载 `fae_poc/config.ini` → `NCELogin` 校验/获取 token → 调用 FAE 批量优化接口
4. 把返回的 `stdout` / `stderr` / `returncode` **原样透传**给用户

**CLI 参数连接符统一为空格**（argparse 标准），不要使用 `--strategy: immediate` 这类带冒号的写法。`rectification_method` 作为单个字符串传入（逗号分隔），例如 `"1,2,3,4"`。

## Scripts

- `scripts/manual_batch_optimize.py` — FAE 平台批量优化接口调用入口（依赖项目根 `fae_poc/` 包中的 `NCELogin` 和 `config.ini`）

## References

- `references/rectification_methods.md` — 整改方式编号对照表 + 常用组合建议

## Examples

**立即执行，仅设备重启**：
```bash
python manual_batch_optimize.py --strategy immediate --rectification-method 1
```

**闲时执行，信道 + 功率调整（卖场走播场景，不含重启避免打断业务）**：
```bash
python manual_batch_optimize.py --strategy idle --rectification-method 2,3,4
```

**定时执行（每天 00:00:00），全部整改方式**：
```bash
python manual_batch_optimize.py --strategy scheduled --operation-time 0-0-0-*-*-*
```

**组合使用**：
```bash
python manual_batch_optimize.py --strategy scheduled --operation-time 0-0-0-*-*-* --rectification-method 1,2,3,4
```

**指定配置文件（用 Windows 绝对路径覆盖默认）**：
```bash
python manual_batch_optimize.py --strategy immediate --config C:/path/to/fae_poc/config.ini
```

## 脚本实现约束（脚本作者必须遵守）

本 Skill 脚本封装真实 FAE 接口，有 4 条硬性约束。违反任何一条都会导致 agno 执行失败或挂起：

1. **首行必须是 shebang** `#!/usr/bin/env python3`  
   否则 Windows 下 agno 报 `[WinError 193] %1 不是有效的 Win32 应用程序`（agno 在 Win 下通过 shebang 解析解释器，没有就 fallback 到直接执行 `.py`）。

2. **顶部必须做 fae_poc sys.path 双路径注入**  
   从项目根 `broadband-agent/` 引入 `fae_poc` 包，同时让 `fae_poc/` 目录本身加入 `sys.path`，使 `from NCELogin import NCELogin` 这种 bare 导入可用：
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
   例如 `session.post(..., timeout=(5, 15))`。这包含 `NCELogin` 内部和 `ManualBatchOptimizeClient.optimize()`。否则一旦 FAE 网络不通就会挂到 agno 外层 timeout 被强杀。

Provisioning Agent 调用本 Skill 时 `get_skill_script` 建议显式传 `timeout=120`，为"NCELogin 登录 + 业务接口"两轮网络交互留足预算。

## 依赖与部署

`scripts/manual_batch_optimize.py` 依赖项目根的 `fae_poc/` 包（见 `fae_poc/__init__.py` 的 docstring）。初次部署：

1. 把本地 `NCELogin.py` 拷贝到 `fae_poc/NCELogin.py`（已 `.gitignore`）
2. 把 `fae_poc/config.ini.example` 复制为 `fae_poc/config.ini` 并填入真实 `base_url` / `csrf_token` / `cookie`（已 `.gitignore`）
3. config.ini 需包含 `[API]`（`ip` / `port`）和 `[AuthTokens]`（`x-uni-crsf-token` / `cookie`）两节

未完成部署时脚本会以结构化 JSON 返回 `status=failed, stage=deployment_check`，不会 crash。

## 方案字段映射（plan_design → CLI 参数）

Provisioning 从 `远程优化：` 段落提取以下字段并按此表翻译为 CLI 参数：

| 方案字段 | 值 | CLI 映射 |
|---|---|---|
| `远程优化触发时间` | `闲时` | `--strategy idle` |
| `远程优化触发时间` | `立即` | `--strategy immediate` |
| `远程优化触发时间` | `定时` | `--strategy scheduled`（须补 `--operation-time`） |
| `远程网关重启：True` | — | 整改方式编号 `1` |
| `远程WIFI信道切换：True` | — | 整改方式编号 `2` |
| `远程WIFI功率调优：True` | — | 整改方式编号 `3,4`（2.4G + 5G 合并） |

整改方式合并规则：将所有值为 `True` 的字段对应编号合并 → `--rectification-method "<编号逗号列表>"`。

例：`远程网关重启：False`，`远程WIFI信道切换：True`，`远程WIFI功率调优：True` → `--rectification-method "2,3,4"`

## 禁止事项

- ❌ 不做业务规则推断（整改方式组合 / 执行策略由 PlanningAgent 在方案段落里决定）
- ❌ 不在 Skill 脚本里硬编码 `base_url` / `csrf_token` / `cookie`，一律从 `fae_poc/config.ini` 读取
- ❌ 不在 `rectification_method` 里填 `1 / 2 / 3 / 4` 之外的值（会被 FAE 平台拒绝）
- ❌ `strategy=scheduled` 时不要省略 `operation_time`（会默认用 `0-0-0-*-*-*`，实际可能不是用户期望）
- ❌ 不要在 Provisioning Agent 里自己拼装 FAE 接口 JSON，统一通过本 Skill 的 CLI 入口
- ❌ 不要改写脚本 stdout，原样透传给用户
