---
name: cei_score_query
description: "CEI 体验查询：调用 FAE 平台 cei-experience/userexperience/query 接口，拉取用户/业务/家庭三类体验的 CEI 评分列表与扣分详情"
---

# CEI 体验查询

## Metadata
- **paradigm**: Tool Wrapper（封装 FAE 平台 cei-experience/userexperience/query 接口）
- **when_to_use**: ProvisioningCeiChainAgent 需要读取当前 CEI 评分（保障链评分回采 / 场景 3 单点查询）时
- **inputs**: CLI 参数（argparse）
- **outputs**: 脚本 stdout（执行过程日志 + JSON 查询结果）+ returncode（0=成功，非 0=失败）

## Parameter Schema（Provisioning 按此从画像 / 场景推导）

| 字段 | 类型 | 必填 | 默认值 | 允许值 / 推导提示 |
|---|---|---|---|---|
| `--experience-type` / `-et` | int | 否 | `1` | `0`=用户体验 Top 低分 / `1`=业务体验 Top 低分 / `2`=家庭体验 Top 低分。直播、游戏、专线类业务保障 → `1`；整家体验巡检 → `2`；泛化低分排查 → `0` |
| `--period` / `-p` | string | 否 | `1DAY` | 统计周期。保障场景默认 `1DAY`；短时段突发定位可调小，由 FAE 平台允许值决定 |
| `--time-start` / `-ts` | int(ms) | 否 | *当日 00:00 时间戳* | 毫秒时间戳。保障时段（如 18:00-22:00）定位时，按当日该时段起始点计算 |
| `--time-end` / `-te` | int(ms) | 否 | *当日 24:00 时间戳* | 毫秒时间戳，必须 > `time-start` |
| `--sort` / `-s` | string | 否 | `avgCeiScore` | 排序字段，低分 Top 场景保持默认 |
| `--limit` / `-l` | int | 否 | `10` | 返回记录数。保障链评分回采一般 `10` 即可，场景 3 用户自定义时可放宽到 `50` |
| `--offset` / `-o` | int | 否 | `0` | 分页偏移 |
| `--cond-name` / `-cn` | string | 否 | `""` | 过滤字段名（与 `cond-value` / `cond-operator` **三者联动**，同时提供或同时省略） |
| `--cond-value` / `-cv` | string | 否 | `""` | 过滤字段值 |
| `--cond-operator` / `-cop` | string | 否 | `=` | 过滤操作符，遵循 FAE 平台允许值 |
| `--config` | string | 否 | `str(DEFAULT_CONFIG_PATH)` | `fae_poc/config.ini` 绝对路径 |

返回结果的字段含义 / `experience-type` 详细映射 / `cond-*` 联动用法见 `references/query_response_schema.md`（L3 加载）。

**本 Skill 不做业务规则判断**：查什么类型、看哪段时间、是否按用户名过滤，由 Provisioning 按关键画像 + 任务头推导后以 CLI 参数传入。Skill 只负责"参数 → CLI → FAE 接口 → stdout 透传"。

## When to Use

- ✅ 场景 1（综合目标）完整保障链第 2 步：`cei_pipeline` 权重下发完成后回采当前评分
- ✅ 场景 3（单点指令）用户要求"查 CEI 分数 / 查卡顿评分 / 查体验低分用户" → 任务头 `[任务类型: 单点 CEI 查询]`
- ❌ 用户想修改权重阈值（应走 `cei_pipeline`）
- ❌ 用户只是咨询 CEI 概念或扣分构成（直接回答 + 引用 `references/query_response_schema.md` 即可）
- ❌ 需要复杂多维归因分析（应走 `insight` SubAgent）

## How to Use

1. 从关键画像 / 任务头推导 Parameter Schema 每个字段的取值
2. 按 argparse CLI 展开为 `List[str]`，调用脚本：
   ```
   get_skill_script(
       "cei_score_query",
       "cei_score_query.py",
       execute=True,
       args=["--experience-type", "1", "--period", "1DAY", "--limit", "10", "--sort", "avgCeiScore"],
       timeout=120,
   )
   ```
3. 脚本内部流程：加载 `fae_poc/config.ini` → `NCELogin` 校验/获取 token → 调用 FAE `cei-experience/userexperience/query` 接口 → 按接口既定字段白名单过滤返回体
4. 把 `stdout` / `stderr` / `returncode` **原样透传**给调用方

**CLI 参数连接符统一为空格**（argparse 标准）。所有参数都是可选，省略即用默认值。投诉用户定位场景下，`cond-name` / `cond-value` / `cond-operator` 三者必须同时给出，例如：

```
args=["--cond-name", "userName", "--cond-value", "pk-lbc/0/1/2/5", "--cond-operator", "="]
```

## Scripts

- `scripts/cei_score_query.py` — FAE 平台 CEI 体验查询接口调用入口（依赖项目根 `fae_poc/` 包中的 `NCELogin` 和 `config.ini`，与 `cei_pipeline` / `remote_optimization` 共享同一套基础设施）

## References

- `references/query_response_schema.md` — 返回体字段定义（`rows[]` / `headers` 等）+ `experience-type` 取值含义 + `cond-*` 三参联动用法

## Examples

**保障链评分回采（默认业务体验 Top10，当日全天）**：
```bash
python cei_score_query.py --experience-type 1 --period 1DAY --limit 10 --sort avgCeiScore
```

**整家体验巡检（家庭体验 Top50）**：
```bash
python cei_score_query.py --experience-type 2 --period 1DAY --limit 50
```

**投诉用户定位**：
```bash
python cei_score_query.py --experience-type 1 --cond-name userName --cond-value pk-lbc/0/1/2/5 --cond-operator =
```

**指定配置文件（Windows 绝对路径覆盖默认）**：
```bash
python cei_score_query.py --config C:/path/to/fae_poc/config.ini
```

## 脚本实现约束（脚本作者必须遵守）

本 Skill 脚本封装真实 FAE 接口，与 `cei_pipeline` 共享以下 4 条硬性约束。违反任一条都会导致 agno 执行失败或挂起：

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
   例如 `session.post(..., timeout=(5, 15))`。包含 `NCELogin` 内部和本 Skill 的查询调用。否则一旦 FAE 网络不通就会挂到 agno 外层 timeout 被强杀。

Provisioning Agent 调用本 Skill 时 `get_skill_script` 建议显式传 `timeout=120`，为"NCELogin 登录 + 业务接口"两轮网络交互留足预算。

## 依赖与部署

`scripts/cei_score_query.py` 与 `cei_pipeline / remote_optimization` 共享 `fae_poc/` 包。初次部署：

1. 把本地 `NCELogin.py` 拷贝到 `fae_poc/NCELogin.py`（已 `.gitignore`）
2. 把 `fae_poc/config.ini.example` 复制为 `fae_poc/config.ini` 并填入真实 `base_url` / `csrf_token` / `cookie`（已 `.gitignore`）
3. config.ini 需包含 `[API]`（`ip` / `port`）和 `[AuthTokens]`（`x-uni-crsf-token` / `cookie`）两节

未完成部署时脚本应以结构化 JSON 返回 `status=failed, stage=deployment_check`，不要 crash（与 `cei_pipeline` / `remote_optimization` 的降级行为一致）。

## 禁止事项

- ❌ 不做业务规则推断（查什么 / 查谁由调用方通过 CLI 传入）
- ❌ 不在脚本里硬编码 `base_url` / `csrf_token` / `cookie`，一律从 `fae_poc/config.ini` 读取
- ❌ 不扩展 / 修改 FAE 返回字段白名单，保持与平台一致
- ❌ 不改写脚本 stdout（包括 JSON 结构、日志行序），原样透传
- ❌ 不要在 Provisioning Agent 里自己拼装 FAE 接口 JSON，统一通过本 Skill CLI 入口
- ❌ 不承担扣分归因或趋势分析（那是 `insight` SubAgent 的职责）
