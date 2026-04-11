# 前后端对接方案

目标：在 agno Team 事件和前端 SSE 协议之间新增一个适配层。不改 Agent 逻辑，不动 Gradio 文件。

```
agno Team event → Event Adapter → SSE event → frontend
```

---

## 1. agno 原始事件分类

通过实际运行（`backend/scripts/dump_events.py`）确认，agno Team 在 coordinate 模式下的事件分两类：

**Team leader（Orchestrator）**，事件名带 `Team` 前缀，携带 `team_id / team_name`：

- `TeamRunStarted` / `TeamRunCompleted`
- `TeamToolCallStarted` / `TeamToolCallCompleted`
- `TeamRunContent`（Orchestrator 流式最终回复）

**SubAgent member**，无前缀，携带 `agent_id / agent_name`：

- `RunStarted` / `RunCompleted`
- `ToolCallStarted` / `ToolCallCompleted`
- `RunContent`（SubAgent 内部摘要，**不透给前端**）

---

## 2. agno 事件 → 前端 SSE 事件映射

| agno 事件 | 条件 | → 前端 SSE 事件 |
|----------|------|----------------|
| `ReasoningContentDelta` / `TeamRunContent.reasoning_content` | 任意 | `thinking { delta }` |
| `TeamRunContent` | 有 content，leader | `text { delta }` |
| `TeamToolCallStarted` | `tool_name == "delegate_task_to_member"` | `step_start { stepId, title }` |
| `ToolCallCompleted` | `tool_name == "get_skill_script"` | `sub_step { stepId, subStepId, name, result, durationMs }` |
| `TeamToolCallCompleted` | `tool_name == "delegate_task_to_member"` | `step_end { stepId }` |
| `TeamRunCompleted` | — | `done { messageId, thinkingDurationSec }` |
| 任何 Error 事件 | — | `error { message }` |
| `ToolCallStarted/Completed` | `tool_name == "get_skill_instructions"` | **忽略**（内部加载 SKILL.md） |
| `RunContent` | member 事件 | **忽略**（SubAgent 内部摘要） |

### 流式粒度说明

**thinking / text**：token 级流式。`TeamRunContent` 每次只携带几个字，Event Adapter 收到即推，前端打字机效果天然实现。

**step / sub_step**：事件级流式，实时推送，不等全部结束。

```
TeamToolCallStarted (delegate)        → step_start    步骤卡立刻出现，进入转圈状态
  ToolCallStarted (get_skill_script)  → 记录 t0（不发事件）
  ToolCallCompleted (get_skill_script)→ sub_step      skill 完成，携带真实 durationMs = now - t0
  （多个 skill 依次出现 sub_step）
TeamToolCallCompleted (delegate)      → step_end      步骤卡打勾
```

skill 执行期间步骤卡内无 sub_step，前端在 `step_start` 到第一个 `sub_step` 之间显示 loading 占位，`sub_step` 到来时替换。

### step / sub_step 字段说明

- **step** = SubAgent 被激活（`delegate_task_to_member` 一次调用）
- **sub_step** = SubAgent 内执行的单个 Skill 脚本（`get_skill_script` 一次调用）
- `stepId` 使用 `tool_args.member_id`（如 `provisioning-wifi`）
- `subStepId` 使用 `{stepId}_{skill_name}`
- `durationMs` = `ToolCallCompleted` 时间 − `ToolCallStarted` 时间（真实脚本耗时）
- `sub_step` 在 `ToolCallCompleted` 时发出（执行完成才有 result）

### SubAgent 中文名映射

| member_id | step title |
|-----------|-----------|
| `planning` | PlanningAgent |
| `insight` | InsightAgent |
| `provisioning-wifi` | ProvisioningAgent (WIFI 仿真) |
| `provisioning-delivery` | ProvisioningAgent (差异化承载) |
| `provisioning-cei-chain` | ProvisioningAgent (体验保障链) |

### render 事件

**insight 场景**：`data_insight` 和 `report_rendering` 的产物分散在多次 `ToolCallCompleted` 中，Event Adapter 需在服务端缓存聚合，待 `InsightAgent` 的 `step_end` 触发后一次性发出：

```
event: render
data: { "renderType": "insight", "renderData": { "charts": [...], "markdownReport": "..." } }
```

**image 场景**：Skill 生成图片文件后，后端存储并生成 `imageId`，通过 `/api/images/:imageId` 提供访问，随即发出：

```
event: render
data: { "renderType": "image", "renderData": { "imageId": "...", "imageUrl": "/api/images/...", "title": "...", "conclusion": "..." } }
```

---

## 3. 服务端消息聚合模型

每次回答过程中维护一个聚合对象，`done` 时落库：

```python
@dataclass
class MessageAggregate:
    message_id: str
    conversation_id: str
    role: str = "assistant"
    content: str = ""                 # 累积 text delta
    thinking_content: str = ""        # 累积 thinking delta
    thinking_duration_sec: int = 0
    steps: list[Step] = field(default_factory=list)
    render_blocks: list[RenderBlock] = field(default_factory=list)
    created_at: str = ""
    status: str = "streaming"         # streaming | done | error
```

历史消息查询直接返回此结构，与流式模型保持一致。

---

## 4. 新增模块结构

所有新增代码放入 `backend/api/`，**不触碰任何现有文件**：

```
backend/api/
├── __init__.py
├── main.py              # FastAPI 入口，端口 8080
├── models.py            # 前端协议数据模型（Conversation / Message / Step / RenderBlock）
├── event_adapter.py     # 核心：agno 事件 → 前端 SSE 事件 + MessageAggregate 维护
├── sse.py               # SSE 格式化编码
├── repository.py        # 会话 / 消息持久化读写（按前端模型，不暴露 Gradio 结构）
└── routes/
    ├── conversations.py  # GET/POST/DELETE /api/conversations
    ├── messages.py       # GET/POST /api/conversations/:id/messages（POST 走 SSE）
    └── images.py         # GET /api/images/:imageId
```

可 import 但不修改的现有模块：

| 模块 | 用途 |
|------|------|
| `core/agent_factory.py` | `create_team()` |
| `core/session_manager.py` | 会话隔离 |
| `core/observability/` | 日志 / DB（可选） |

---

## 5. 实施里程碑

| 阶段 | 目标 | 完成标志 |
|------|------|---------|
| **M1** API 外壳 | FastAPI 服务跑通，REST 接口可调 | `GET /conversations` 返回空列表，前端能连上 |
| **M2** 基础流 | SSE 跑通最简事件 | `thinking` / `text` / `done` / `error` 前端可渲染 |
| **M3** 步骤卡 | 步骤面板真实联动 | `step_start` / `sub_step` / `step_end` 前端步骤卡正常展开 |
| **M4** 右侧面板 | render 事件联动 | `insight` / `image` 右侧面板真实展示 |
| **M5** 历史恢复 | 刷新不丢状态 | `GET /messages` 返回完整 Message，右侧渲染块可恢复 |

---

## 6. 协作约束

### 禁止修改的文件

| 文件 | 原因 |
|------|------|
| `backend/ui/app.py` | 后端团队持续迭代的 Gradio 入口 |
| `backend/ui/chat_renderer.py` | Gradio 渲染逻辑 |
| `backend/ui/session_state.py` | Gradio session 管理 |

### event_adapter.py 是重写，不是迁移

`ui/app.py` 中的 `chat_handler()` 是为 Gradio 输出设计的，**不复制其代码**。`api/event_adapter.py` 依据本文档第 2 节的映射规则从头实现，输出目标是前端 SSE 事件，不是 Gradio ChatMessage。

### 运行时共存

| 服务 | 端口 | 用途 |
|------|------|------|
| Gradio UI | 7860 | 后端团队调试 |
| FastAPI API | 8080 | 前后端正式对接 |
