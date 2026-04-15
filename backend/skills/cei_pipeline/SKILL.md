---
name: cei_pipeline
description: "CEI 权重配置下发：调用 FAE 平台 config-threshold 接口，下发业务质量/Wi-Fi 网络/速率/稳定性等 8 维度 CEI 评分权重"
---

# CEI 权重配置

## Metadata
- **paradigm**: Tool Wrapper（封装 FAE 平台 config-threshold 接口）
- **when_to_use**: ProvisioningCeiChainAgent 需要调整 CEI 各维度评分权重时
- **inputs**: CLI 参数（`weights` / `config`）
- **outputs**: 脚本 stdout（执行过程日志）+ returncode（0=成功，非 0=失败）

## Parameter Schema（Provisioning 按此从方案段落提参）

| 字段 | 类型 | 必填 | 默认值 | 允许值 | 说明 |
|---|---|---|---|---|---|
| `weights` | string (CSV) | 否 | 见 §weights 字段表 | `参数名:数值` 逗号分隔 | 8 维度权重配置，格式 `Name1:V1,Name2:V2,...` |
| `config` | string | 否 | `fae_poc/config.ini` 绝对路径 | — | config.ini 路径 |

### weights 字段表（8 个维度，默认值加和为 100）

| 参数名 | 默认值 | 允许值 | 含义 |
|---|---|---|---|
| `ServiceQualityWeight` | `30` | 0-100 | 业务质量权重（直播/视频/游戏等感知） |
| `WiFiNetworkWeight` | `20` | 0-100 | Wi-Fi 网络权重（覆盖、干扰、连接） |
| `StabilityWeight` | `15` | 0-100 | 稳定性权重（抖动、掉线、重传） |
| `STAKPIWeight` | `10` | 0-100 | 终端 KPI 权重（STA 层指标） |
| `GatewayKPIWeight` | `10` | 0-100 | 网关 KPI 权重（家庭网关侧指标） |
| `RateWeight` | `5` | 0-100 | 速率权重（上下行速率） |
| `ODNWeight` | `5` | 0-100 | ODN 权重（光分配网） |
| `OLTKPIWeight` | `5` | 0-100 | OLT 权重（局端指标） |

**本 Skill 不做业务规则判断**：具体权重组合由 PlanningAgent 在方案段落里决定（见 `plan_design` SKILL.md 的套餐/场景权重预设速查），本 Skill 只做"参数 → CLI → 接口调用"的映射。业务上建议 8 维度权重加和为 100，但是否强制由 FAE 平台侧校验，本 Skill 不做本地加和检查。

## When to Use

- ✅ 场景 1（综合目标）"CEI 配置方案"段落启用时 → 完整保障链第一步
- ✅ 场景 3（单点指令）"调整 CEI 权重" / "提高业务质量权重" → 任务头 `[任务类型: 单点 CEI 配置]`
- ❌ 用户只是咨询 CEI 概念（直接回答即可）
- ❌ 用户要求 CEI 评分查询 / 低分用户拉取（应走 `cei_score_query`）
- ❌ 用户要求数据洞察 / 归因分析（应走 InsightAgent 的 `insight_*` skills）
- ❌ 需要调整故障诊断或远程闭环策略（分别走 `fault_diagnosis` / `remote_optimization`）

## How to Use

1. 从方案段落按 schema 提取参数（`weights` CSV 字符串 + 可选 `config`）
2. 组装 argparse CLI 参数列表，调用脚本：
   ```
   get_skill_script(
       "cei_pipeline",
       "cei_threshold_config.py",
       execute=True,
       args=["--weights", "ServiceQualityWeight:40,WiFiNetworkWeight:25,StabilityWeight:15,STAKPIWeight:5,GatewayKPIWeight:5,RateWeight:5,ODNWeight:3,OLTKPIWeight:2"],
       timeout=120
   )
   ```
3. 脚本内部流程：加载 `fae_poc/config.ini` → `NCELogin` 校验/获取 token → 调用 FAE config-threshold 接口
4. 把返回的 `stdout` / `stderr` / `returncode` **原样透传**给用户

**CLI 参数连接符统一为空格**（argparse 标准），不要使用 `--weights: ServiceQualityWeight:40` 这类带冒号的写法。`weights` 作为单个字符串传入（逗号分隔），例如 `"ServiceQualityWeight:40,WiFiNetworkWeight:25"`；内部每个子项用 `参数名:数值` 的冒号分隔。

`weights` 省略时脚本使用默认权重；可只传部分字段，脚本会在 FAE 侧以"只覆盖传入字段、其余维持现值"的语义处理（具体合并规则见 FAE 平台文档）。

## Scripts

- `scripts/cei_threshold_config.py` — FAE 平台 config-threshold 接口调用入口（依赖项目根 `fae_poc/` 包中的 `NCELogin` 和 `config.ini`）

## References

- `references/weight_parameters.md` — 8 维度权重参数说明表 + 套餐/场景常用预设速查

## Examples

**使用默认权重值**（全部字段取默认）：
```bash
python cei_threshold_config.py
```

**直播套餐卖场走播** — 提升业务质量 + Wi-Fi 权重：
```bash
python cei_threshold_config.py --weights ServiceQualityWeight:40,WiFiNetworkWeight:25,StabilityWeight:15,STAKPIWeight:5,GatewayKPIWeight:5,RateWeight:5,ODNWeight:3,OLTKPIWeight:2
```

**专线套餐 / VVIP** — 稳定性优先：
```bash
python cei_threshold_config.py --weights ServiceQualityWeight:25,WiFiNetworkWeight:15,StabilityWeight:25,STAKPIWeight:5,GatewayKPIWeight:5,RateWeight:15,ODNWeight:5,OLTKPIWeight:5
```

**游戏类用户** — 稳定性 + 网关 + 速率并重：
```bash
python cei_threshold_config.py --weights ServiceQualityWeight:20,WiFiNetworkWeight:20,StabilityWeight:25,STAKPIWeight:5,GatewayKPIWeight:15,RateWeight:15,ODNWeight:0,OLTKPIWeight:0
```

**指定配置文件（用 Windows 绝对路径覆盖默认）**：
```bash
python cei_threshold_config.py --weights ServiceQualityWeight:40 --config C:/path/to/fae_poc/config.ini
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
   例如 `session.put(..., timeout=(5, 15))`。这包含 `NCELogin` 内部和 `CEIThresholdConfigClient.config_threshold()`。否则一旦 FAE 网络不通就会挂到 agno 外层 timeout 被强杀。

Provisioning Agent 调用本 Skill 时 `get_skill_script` 建议显式传 `timeout=120`，为"NCELogin 登录 + 业务接口"两轮网络交互留足预算。

## 依赖与部署

`scripts/cei_threshold_config.py` 依赖项目根的 `fae_poc/` 包（见 `fae_poc/__init__.py` 的 docstring），与 `cei_score_query` / `fault_diagnosis` / `remote_optimization` / `experience_assurance` 共享同一套基础设施。初次部署：

1. 把本地 `NCELogin.py` 拷贝到 `fae_poc/NCELogin.py`（已 `.gitignore`）
2. 把 `fae_poc/config.ini.example` 复制为 `fae_poc/config.ini` 并填入真实 `base_url` / `csrf_token` / `cookie`（已 `.gitignore`）
3. config.ini 需包含 `[API]`（`ip` / `port`）和 `[AuthTokens]`（`x-uni-crsf-token` / `cookie`）两节

未完成部署时脚本应以结构化 JSON 返回 `status=failed, stage=deployment_check`，不要 crash（与同族 FAE / FAN Skill 的降级行为一致）。

## 方案字段映射（plan_design → CLI 参数）

Provisioning 从 `CEI体验感知：` 段落提取 `CEI模型` 字段，按此表查找预设权重 CSV 并翻译为 `--weights` 参数：

**CEI模型名 → `--weights` 预设速查表**

| CEI模型（方案字段值）| `--weights` CSV 值 |
|---|---|
| `直播模型` | `ServiceQualityWeight:40,WiFiNetworkWeight:25,StabilityWeight:15,STAKPIWeight:5,GatewayKPIWeight:5,RateWeight:5,ODNWeight:3,OLTKPIWeight:2` |
| `视频模型` | `ServiceQualityWeight:30,WiFiNetworkWeight:20,StabilityWeight:15,STAKPIWeight:10,GatewayKPIWeight:10,RateWeight:5,ODNWeight:5,OLTKPIWeight:5` |
| `游戏模型` | `ServiceQualityWeight:20,WiFiNetworkWeight:20,StabilityWeight:25,STAKPIWeight:5,GatewayKPIWeight:15,RateWeight:15,ODNWeight:0,OLTKPIWeight:0` |
| `VVIP模型` | `ServiceQualityWeight:25,WiFiNetworkWeight:15,StabilityWeight:25,STAKPIWeight:5,GatewayKPIWeight:5,RateWeight:15,ODNWeight:5,OLTKPIWeight:5` |

**CEI阈值**：`CEI阈值：70分` → 提取数字 `70` → `cei_score_query` 的 `--threshold 70`（本 Skill `cei_pipeline` 不使用阈值参数，阈值由 Provisioning 在后续 `cei_score_query` 步骤中使用）。

## 禁止事项

- ❌ 不做业务规则推断（权重组合由 PlanningAgent 在方案段落里决定）
- ❌ 不在 Skill 脚本里硬编码 `base_url` / `csrf_token` / `cookie`，一律从 `fae_poc/config.ini` 读取
- ❌ 不在 `weights` 里填 8 个字段之外的未知参数名（会被 FAE 平台拒绝）
- ❌ 不要在 Provisioning Agent 里自己拼装 FAE 接口 JSON，统一通过本 Skill 的 CLI 入口
- ❌ 不要改写脚本 stdout，原样透传给用户
- ❌ 不要在本 Skill 里尝试查询 CEI 评分 — 评分查询是 `cei_score_query` Skill 的职责，保障链里由 Provisioning 在本 Skill 下发完成后顺序调用
