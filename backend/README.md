# 家宽网络调优智能助手

基于 [agno](https://github.com/agno-agi/agno) 框架构建的家宽网络调优场景多智能体系统，采用 **Team (coordinate 模式) + 14 个业务 Skills** 的分层架构。

## 功能特性

支持三类任务入口：

1. **综合目标** — 用户描述业务目标，PlanningAgent 追问画像 → 产出分段方案 → 并行派发多个 Provisioning 实例执行
2. **数据洞察** — InsightAgent 按 Plan → Decompose → Execute → Reflect → Report 五阶段产出数据 / 归因 / ECharts 图表 / Markdown 报告，结果可回流 Planning 生成优化方案
3. **单点功能** — Orchestrator 关键词路由直达对应 Provisioning 实例（WIFI 仿真 / 差异化承载 / 故障定界 / 远程操作 / CEI 权重配置）

## 架构

```
OrchestratorTeam (leader, coordinate 模式)
  ├─ PlanningAgent            (goal_parsing + plan_design + plan_review)
  ├─ InsightAgent             (insight_plan + insight_decompose + insight_query
  ���                            + insight_nl2code + insight_reflect + insight_report)
  ├─ ProvisioningWifiAgent    (wifi_simulation)              ← 单 Skill 内部 4 步
  ├─ ProvisioningDeliveryAgent (differentiated_delivery)
  └─ ProvisioningCeiChainAgent (cei_pipeline + fault_diagnosis + remote_optimization)
                                                             ← 条件串行 workflow
```

3 个 Provisioning 实例**共享** `prompts/provisioning.md`，通过 `description` 字段注入各自的功能目标。

### 业务 Skill 设计模式

- **`plan_design`**：Instructional 范式 — 纯 SKILL.md + few-shot 样例，**无脚本**，由 LLM 直接生成分段 Markdown 方案
- **`cei_pipeline / remote_optimization`**：Tool Wrapper 范式 — 封装 FAE 平台真实接口，CLI args 驱动，依赖 `fae_poc/` 共享的 NCELogin + config.ini
- **`fault_diagnosis / differentiated_delivery`**：Generator 范式 — SKILL.md 声明参数 schema，Jinja2 模板纯参数填空，**无业务规则分支**（业务规则已上移到 PlanningAgent）
- **`goal_parsing / plan_review`**：Inversion + Reviewer — 有状态/确定性任务保留脚本
- **`insight_*`**（6 个 Skill）：Pipeline — Plan → [Decompose → Execute → Reflect] × N Phase → Report 驱动，接入 `ce_insight_core` 真实计算内核（三元组查询 + 12 种洞察函数 + NL2Code 沙箱）
- **`wifi_simulation`**：Pipeline — 单脚本内部 3+1 步（户型图处理 → 信号强度仿真 → 网络性能仿真，选点可选）

## 技术栈

- Python 3.11 + [uv](https://docs.astral.sh/uv/) (包管理) + agno >= 2.5.14
- Gradio (Web UI，流式事件处理 + SubAgent 徽章)
- loguru (应用日志) + SQLite (会话持久化 + 完整轨迹存储) + JSONL (按天归档 trace)
- Jinja2 (配置模板渲染)
- pandas / numpy / scipy / scikit-learn (数据洞察科学计算栈)

## 快速开始

### 使用 uv（推荐）

```bash
# 安装全部依赖（含 vendor/ce_insight_core editable 安装）
uv sync

# 安装开发依赖（pytest + ruff）
uv sync --group dev

# 设置 API Key
export OPENAI_API_KEY="your-api-key"

# 启动应用
uv run python ui/app.py
```

### 使用 pip

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="your-api-key"
python ui/app.py
```

### 企业代理环境

如果启动时报 `Couldn't start the app because 'http://localhost:7860/gradio_api/startup-events' failed (code 504)`，说明公司代理拦截了 Gradio 的 localhost 自检请求。启动前设置：

```bash
# Linux / macOS
export NO_PROXY="localhost,127.0.0.1"

# Windows PowerShell
$env:NO_PROXY="localhost,127.0.0.1"
```

> 注意：当前 `server_name="0.0.0.0"` 会监听所有网卡，同网段的其他人可以通过你的 IP 访问。如果需要限制为仅本机访问，将 `ui/app.py` 中的 `server_name` 改为 `"127.0.0.1"`。

访问 http://localhost:7860 开始使用。

### vendor 子包更新

`vendor/ce_insight_core/` 以 **editable** 模式安装（`[tool.uv.sources]` 声明了 `editable = true`）。日常开发：

- **修改 Python 源码**（`vendor/ce_insight_core/src/` 下的 `.py` 文件）→ **无需重新安装**，改动自动生效
- **修改 `pyproject.toml`**（新增依赖 / 改版本号 / 改 entry points）→ 需要重新执行 `uv sync`
- **从上游同步新版本** → `uv sync` 会重新解析依赖关系

## 项目结构

```
├── pyproject.toml          # 项目依赖声明 (uv 规范源)
├── .python-version         # Python 版本锁定 (uv sync 使用)
├── requirements.txt        # pip 兼容依赖 (指向 pyproject.toml 为规范源)
├── configs/
│   ├── model.yaml          # 模型 provider/endpoint
│   └── agents.yaml         # Team + 5 个 SubAgent 配置
├── prompts/
│   ├── orchestrator.md     # Team leader 作业手册
│   ├── planning.md         # PlanningAgent 作业手册
│   ├── insight.md          # InsightAgent 作业手册
│   └── provisioning.md     # 3 个 Provisioning 实例共享的作业手册
├── skills/                 # 14 个业务 Skill (LocalSkills 自动扫描)
│   ├── goal_parsing/       # 槽位追问引擎
│   ├── plan_design/        # 方案设计 (Instructional, 无脚本)
│   ├── plan_review/        # 方案评审 (violations + recommendations)
│   ├── cei_pipeline/       # CEI 权重配置下发 (Tool Wrapper, 对接 FAE 真实接口)
│   ├── fault_diagnosis/    # 故障诊断配置
│   ├── remote_optimization/# 远程优化动作 (Tool Wrapper, 对接 FAE 真实接口)
│   ├── differentiated_delivery/ # 差异化承载 (切片/Appflow)
│   ├── wifi_simulation/    # WIFI 4 步仿真
│   ├── insight_plan/       # 洞察规划 (Instructional, MacroPlan 生成)
│   ├── insight_decompose/  # Phase 分解 (Tool Wrapper, list_schema.py + 参考文件)
│   ├── insight_query/      # 洞察执行 (Tool Wrapper, run_insight.py + run_query.py)
│   ├── insight_nl2code/    # NL2Code 沙箱 (Tool Wrapper, run_nl2code.py)
│   ├── insight_reflect/    # Phase 反思 (Instructional, A/B/C/D 决策)
│   └── insight_report/     # 洞察报告渲染 (Generator, render_report.py)
├── vendor/
│   └── ce_insight_core/    # 洞察计算内核 (editable 安装, 三元组查询 + 12 种洞察策略)
├── fae_poc/                # FAE 平台共享基础设施 (NCELogin + config.ini, .gitignore)
├── core/
│   ├── agent_factory.py    # create_team() — 装配 Team + 5 SubAgent
│   ├── session_manager.py  # session_hash → Team + Tracer 隔离
│   ├── model_loader.py     # 模型实例化 + prompt tracer 注入
│   └── observability/      # SQLite DAO + loguru sink + JSONL tracer
├── ui/
│   ├── app.py              # Gradio 入口 (Team 流式事件处理)
│   └── chat_renderer.py    # SubAgent 徽章 + 工具调用折叠/展开渲染
└── tests/test_smoke.py     # 冒烟测试
```

## 可观测性

完整的轨迹存储体系，覆盖 agent/subagent 交互全流程：

- **SQLite 数据库** (`data/sessions.db`)：4 张表 — `sessions`（会话生命周期）、`messages`（用户/assistant 消息，含 SubAgent 回复）、`tool_calls`（Skill 调用记录，含 latency_ms + message_id 关联 + 成功/失败状态）、`traces`（全量事件轨迹，含 agent_name 索引列）
- **JSONL 日志** (`data/logs/trace/YYYY-MM-DD.jsonl`)：按天归档，完整记录不截断，每条含 agent / is_leader 字段，并行 SubAgent 通过 agent 字段天然隔离
- **应用日志** (`data/logs/app/`)：loguru 按天轮转，7 天保留

DB 和 JSONL 双写：任一写入失败不影响主流程。Tracer 通过 monkey-patch 注入 Team leader 和所有 member 的 model，自动拦截 LLM 调用记录完整 prompt。

## 配置说明

- `pyproject.toml` — 项目依赖声明（uv 规范源），含 ruff / pytest 配置
- `configs/model.yaml` — 模型 provider / endpoint / role_map
- `configs/agents.yaml` — Team + 5 个 SubAgent 的 prompt + skills 子集 + description + memory
- `skills/goal_parsing/references/slot_schema.yaml` — 综合目标槽位定义
- `skills/plan_design/references/examples.md` — 方案设计 few-shot 样例

## 测试

```bash
# uv
uv run pytest tests/test_smoke.py -v

# pip
pytest tests/test_smoke.py -v
```

49 项冒烟测试，覆盖配置加载、14 个 Skill 脚本执行、UI 渲染（流式事件处理 + 思考隔离 + 工具调用折叠）、Team 装配（5 SubAgent + 正确 Skill 子集）、可观测性（SQLite schema + trace 双写）。
