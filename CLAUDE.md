# CLAUDE.md

## 项目概述

家宽网络调优智能助手。基于 agno 框架的 **Team (coordinate 模式) 多智能体系统**，包含 1 个 Orchestrator + 5 个 SubAgent + 14 个业务 Skills，覆盖从意图识别到配置下发的完整流程。

核心模式：**Orchestrator 路由/拆分 → 决策型 Agent (Planning/Insight) + 执行型 Agent (3 × Provisioning) → 参数 schema 驱动的 Skill 调用 → Mock 下游**

## 技术栈

Python 3.11+、agno ≥ 2.5.14、Gradio 4.x（Web UI）、SQLite（会话持久化 + 完整轨迹存储）、Jinja2（模板渲染）、loguru（日志）

## 架构拓扑

```
OrchestratorTeam (leader, coordinate 模式, prompts/orchestrator.md)
  ├─ PlanningAgent             (goal_parsing + plan_design + plan_review)
  ├─ InsightAgent              (insight_plan + insight_decompose + insight_query
  │                             + insight_nl2code + insight_reflect + insight_report)
  ├─ ProvisioningWifiAgent     (wifi_simulation)              ← 单 Skill 自驱 4 步
  ├─ ProvisioningDeliveryAgent (differentiated_delivery)
  └─ ProvisioningCeiChainAgent (cei_pipeline + fault_diagnosis + remote_optimization)
                                                              ← 条件串行 workflow
```

**关键边界**：
- 决策型 Agent (Planning / Insight) 产出方案或报告，**不执行**
- 执行型 Agent (Provisioning × 3) 接收任务载荷后按 Skill schema 从方案段落提参并调用，**不做业务规则判断**
- 3 个 Provisioning 实例**共享** `prompts/provisioning.md`，通过 `description` 字段注入各自的专业方向
- agno Team 不支持运行时动态添加 member，因此 3 个 Provisioning 实例**预声明**（非动态 spawn）

## 项目结构

```
├── configs/
│   ├── model.yaml          # 模型 provider / base_url / api_key / role_map
│   └── agents.yaml         # Team + 5 SubAgent (prompt + skills 子集 + description)
├── core/
│   ├── agent_factory.py    # create_team() — 装配 Team + 5 SubAgent
│   ├── model_loader.py     # 模型实例化 + prompt tracer 注入
│   ├── session_manager.py  # session_hash → Team + Tracer 隔离
│   └── observability/      # SQLite DAO + loguru sink + JSONL tracer
├── prompts/                # 4 份 SubAgent 作业手册
│   ├── orchestrator.md     # Team leader: 意图识别 + 路由 + 方案拆分 + 结果汇总
│   ├── planning.md         # 目标解析 + 方案设计 + 方案评审流程
│   ├── insight.md          # Plan→[Decompose→Execute→Reflect]×N→Report 洞察 + 输出路由协议
│   └── provisioning.md     # 3 个 Provisioning 实例共享，参数 schema 驱动
├── fae_poc/                # FAE 平台共享基础设施 (NCELogin + config.ini, .gitignore)
├── skills/                 # 14 个自包含 Skills (LocalSkills 自动扫描)
│   ├── goal_parsing/       # 槽位追问引擎 (Inversion + 脚本)
│   ├── plan_design/        # 方案设计 (Instructional, 无脚本, 仅 SKILL.md + few-shot)
│   ├── plan_review/        # 方案评审 (Reviewer, violations + recommendations)
│   ├── cei_pipeline/       # CEI 权重配置下发 (Tool Wrapper, scripts/ + 对接 FAE 真实接口)
│   ├── fault_diagnosis/    # 故障诊断配置 (参数 schema 驱动)
│   ├── remote_optimization/# 远程优化动作 (Tool Wrapper, 对接 FAE 真实接口)
│   ├── differentiated_delivery/ # 差异化承载 (切片/Appflow, 参数 schema 驱动)
│   ├── wifi_simulation/    # WIFI 3+1 步仿真 (户型图处理 → 信号仿真 → 网络仿真, 选点可选)
│   ├── insight_plan/       # 洞察规划 (Instructional, MacroPlan 生成)
│   ├── insight_decompose/  # Phase 分解 (Tool Wrapper, list_schema.py + 参考文件)
│   ├── insight_query/      # 洞察执行 (Tool Wrapper, run_insight.py + run_query.py)
│   ├── insight_nl2code/    # NL2Code 沙箱 (Tool Wrapper, run_nl2code.py)
│   ├── insight_reflect/    # Phase 反思 (Instructional, A/B/C/D 决策)
│   └── insight_report/     # 洞察报告渲染 (Generator, render_report.py)
├── ui/
│   ├── app.py              # Gradio 入口 (Team 流式事件处理 + SubAgent 徽章)
│   └── chat_renderer.py    # 思考/工具调用/SubAgent 标签的折叠渲染
├── vendor/
│   └── ce_insight_core/    # 洞察计算内核 (editable 安装)
└── tests/test_smoke.py     # 49 项冒烟测试
```

## 三类任务流程

```
场景 1 · 综合目标:
  Orchestrator → PlanningAgent (goal_parsing → plan_design → plan_review)
               → 按方案段落拆分并行派发
               → [provisioning_wifi] + [provisioning_delivery] + [provisioning_cei_chain]
               → 汇总结果

场景 2 · 数据洞察:
  Orchestrator → InsightAgent (4 阶段: intent → query → attribution → report_rendering)
               → 停下等待用户确认 (D10)
               → (用户要方案时) PlanningAgent (注入 insight summary 作为 hints)
                 → 稀疏方案 → Provisioning 派发

场景 3 · 单点功能:
  Orchestrator → 关键词直接匹配 → 对应 Provisioning 实例
               → 从用户原话推导 Skill 参数 → 执行 → 透传产出
  (跳过 Planning,不做参数提取)
```

## 架构要点

1. **Skills 自包含**：模板、脚本、参考配置全在 Skill 目录内，通过 `LocalSkills` 自动扫描
2. **会话隔离**：`SessionManager` 为每个 Gradio session_hash 创建独立 Team (含 5 SubAgent) + Tracer
3. **参数 schema 驱动**：业务 Skill 的 SKILL.md 显式声明参数 schema，Provisioning 按 schema 从方案段落提参。业务规则（如"直播套餐默认 ServiceQualityWeight 40"）全部上移到 PlanningAgent 的 LLM 决策，**Skill 不做业务判断**
4. **plan_design Instructional 范式**：无脚本，纯 SKILL.md + few-shot 样例，由 LLM 直接生成分段 Markdown 方案
5. **可观测性双写（完整存储）**：SQLite + JSONL，写入失败不影响主流程。Tracer 向 Team leader 和所有 member 的 model 注入 prompt 回调。DB 和日志完整存储所有轨迹数据，不做截断
6. **轨迹关联**：tool_calls 表通过 message_id 关联到触发它的用户消息，traces 表通过 agent_name 列支持按 agent 过滤查询，tool_calls 记录真实 latency_ms
7. **会话生命周期**：`SessionManager` 在 Gradio `app.unload()` 时销毁会话，写入 `ended_at` 到 DB
8. **派发载荷 4 块结构**：Orchestrator 给 Provisioning 的载荷必须含"任务头 + 原始用户目标 + 关键画像 + 方案段落"，缺一不可

## Skills 开发规范

遵循 Google ADK Agent Skills Design Patterns，详见 @.claude/rules/skills_rules.md。

**本项目使用的范式**：
- `plan_design` / `insight_plan` / `insight_reflect` — Instructional（无脚本，纯指令）
- `goal_parsing` — Inversion（槽位追问引擎）
- `plan_review` — Reviewer（违规清单 + 建议）
- `cei_pipeline` / `remote_optimization` — Tool Wrapper（封装 FAE 平台真实接口，CLI args 驱动）
- `insight_decompose` / `insight_query` / `insight_nl2code` — Tool Wrapper（脚本执行型）
- `fault_diagnosis` / `differentiated_delivery` — Generator（参数 schema 驱动，纯模板填空）
- `wifi_simulation` — Pipeline（内部 3+1 步串行）
- `insight_report` — Generator（Markdown/ECharts 报告渲染）

## Python 代码规范

- **类型注解**：所有函数必须有完整类型注解（参数 + 返回值），使用内置泛型（`list[str]`、`Dict[str, Any]`）
- **Docstring**：公开函数和类必须有 docstring
- **私有符号**：模块内部函数/变量以 `_` 开头
- **常量**：模块级常量全大写，放在 import 之后、函数之前
- **异常处理**：core 层 try/except 包裹所有 DB 和 IO 操作，失败写日志不抛异常
- **格式化**：`ruff format .`；**Lint**：`ruff check --fix .`

## Git 提交规范

类型：`feat` | `fix` | `refactor` | `docs` | `skill`（SKILL.md/scripts/references）| `test` | `config`

- 禁止 `--force` 推送到 main/master
- 使用 git push -u origin <branch> 通过 PAT URL 直接推送
- 严禁使用 GitHub MCP Server 工具（mcp__github__push_files 等）提交或推送代码
- 新增/删除模块、架构或目录结构变更时必须同步更新 README.md

## 开发命令

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="your-key"
python ui/app.py                          # 启动 Gradio UI (localhost:7860)
pytest tests/test_smoke.py -v             # 冒烟测试 (49 项)
```

## 禁止事项

- ❌ 不要在业务 Skill 里做业务规则判断（业务规则归属 PlanningAgent 的 LLM）
- ❌ 不要在 Provisioning 里跳过 `get_skill_instructions` 直接猜参数（Step 1 是强制的）
- ❌ 不要改写 Skill stdout（包括 YAML/JSON 配置、ECharts 数据、Markdown 报告）
- ❌ 不要让某个 SubAgent 调用子集之外的 Skill
- ❌ 不要在 Skill 脚本中感知 `session_id`，持久化由 core 层处理
- ❌ observability 写入失败必须静默，禁止抛异常阻断主流程
- ❌ 不要让 Orchestrator 推导 Skill 参数，参数提取是 Provisioning 的职责
- ❌ 不要让 PlanningAgent 自行派发 Provisioning，那是 Orchestrator 的职责
- ❌ plan_review 校验失败必须呈现给用户，禁止自动修正重试
