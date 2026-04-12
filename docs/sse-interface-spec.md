# SSE 流式接口规范

## 概览

**接口**：`POST /api/conversations/{conv_id}/messages`

**响应格式**：`Content-Type: text/event-stream`（Server-Sent Events）

前端通过该接口发送用户消息，后端返回 SSE 流，实时推送 Agent 执行过程和结果。流结束后，后端自动将完整消息持久化到数据库。

---

## SSE 帧格式

每个 SSE 事件由两行组成，以空行分隔：

```
event: <事件类型>
data: <JSON 字符串>

```

`data` 字段始终为合法的 JSON 对象（`ensure_ascii=False`，中文不转义）。

---

## 请求体

```json
{
  "content": "用户消息文本",
  "deepThinking": false
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `content` | `string` | 用户输入内容，必填 |
| `deepThinking` | `boolean` | 是否启用深度思考模式，默认 `false` |

---

## 事件类型一览

| 事件 | 触发时机 | 数量 |
|---|---|---|
| `thinking` | Agent 产生推理内容时（流式，多次） | 0~N 次 |
| `text` | Orchestrator 产生最终回答时（流式，多次） | 0~N 次 |
| `step_start` | 某个 SubAgent 开始执行 | 0~N 次 |
| `sub_step` | SubAgent 内部某个 Skill 执行完成 | 0~N 次 |
| `step_end` | 某个 SubAgent 执行完成 | 0~N 次 |
| `render` | 产生可视化内容（图表 / 报告）时 | 0~1 次 |
| `done` | 整个流程正常结束 | 必须 1 次 |
| `error` | 任意阶段发生错误 | 0~1 次 |

`done` 和 `error` 互斥，流中必须以其中一个结尾。

---

## 事件数据结构

### `thinking`

Agent 推理过程的增量文本片段。

```json
{
  "delta": "正在分析用户意图...",
  "stepId": "planning"
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `delta` | `string` | 本次推理内容增量，非空 |
| `stepId` | `string?` | 存在时表示该 thinking 属于某个 SubAgent（值为 `member_id`）；不存在时属于 Orchestrator |

> **前端处理**：有 `stepId` → 追加到对应 StepCard 的 thinking 块；无 `stepId` → 追加到顶层 ThinkingBlock。

---

### `text`

Orchestrator 最终回答的增量文本片段。

```json
{
  "delta": "根据分析结果，"
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `delta` | `string` | 本次回答内容增量，非空 |

> **注意**：`text` 事件仅由 Team leader（Orchestrator）产生。SubAgent 的输出通过 `sub_step` 传递。

---

### `step_start`

某个 SubAgent 开始执行。

```json
{
  "stepId": "planning",
  "title": "PlanningAgent"
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `stepId` | `string` | SubAgent 标识，取值见下方 member_id 表 |
| `title` | `string` | SubAgent 显示名称 |

**`stepId` 取值表**：

| stepId | title |
|---|---|
| `planning` | `PlanningAgent` |
| `insight` | `InsightAgent` |
| `provisioning-wifi` | `ProvisioningAgent (WIFI 仿真)` |
| `provisioning-delivery` | `ProvisioningAgent (差异化承载)` |
| `provisioning-cei-chain` | `ProvisioningAgent (体验保障链)` |

---

### `sub_step`

SubAgent 内部某个 Skill 脚本执行完成。

```json
{
  "stepId": "planning",
  "subStepId": "planning_goal_parsing",
  "name": "goal_parsing",
  "scriptPath": "scripts/slot_engine.py",
  "callArgs": ["--input", "{\"user_query\": \"直播套餐保障\"}"],
  "stdout": "{\"slots\": {\"scenario\": \"直播\", \"app\": \"抖音\"}}",
  "stderr": "",
  "completedAt": "2026-04-12T07:30:00Z",
  "durationMs": 1234
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `stepId` | `string` | 所属 SubAgent 的 `stepId` |
| `subStepId` | `string` | 唯一标识，格式 `{stepId}_{skillName}` |
| `name` | `string` | Skill 名称（对应 `skills/` 目录名） |
| `scriptPath` | `string?` | 被调用的脚本路径（相对于 Skill 目录），可为空 |
| `callArgs` | `string[]?` | 传入脚本的 CLI 参数列表 |
| `stdout` | `string?` | 脚本 stdout 输出，截断至 500 字符 |
| `stderr` | `string?` | 脚本 stderr 输出，截断至 500 字符 |
| `completedAt` | `string` | 完成时间，ISO 8601 格式（UTC） |
| `durationMs` | `number` | 执行耗时（毫秒） |

---

### `step_end`

某个 SubAgent 执行完成。

```json
{
  "stepId": "planning"
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `stepId` | `string` | 对应 `step_start` 中的 `stepId` |

> **前端处理**：收到后将对应 StepCard 的 loading 状态切换为完成图标，关闭末尾未结束的 thinking 块。

---

### `render`

产生可视化内容，目前支持 `insight`（数据洞察图表 + 报告）和 `image` 两种类型。

#### `renderType: "insight"`

```json
{
  "renderType": "insight",
  "renderData": {
    "charts": [
      {
        "chartId": "insight_query_1",
        "title": "PON 口 CEI 分布",
        "conclusion": "共 12 个 PON 口 CEI 低于阈值；显著性 0.87",
        "echartsOption": { ... }
      }
    ],
    "markdownReport": "## 洞察总结\n\n..."
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `renderType` | `"insight"` | 固定值 |
| `renderData.charts` | `ChartItem[]` | ECharts 图表列表，可为空数组 |
| `renderData.markdownReport` | `string` | Markdown 格式的洞察报告，可为空字符串 |

**`ChartItem` 结构**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `chartId` | `string` | 图表唯一 ID |
| `title` | `string` | 图表标题 |
| `conclusion` | `string` | 图表结论文字 |
| `echartsOption` | `object` | 完整的 ECharts `option` 对象 |

#### `renderType: "image"`

```json
{
  "renderType": "image",
  "renderData": {
    "imageId": "wifi_heatmap_001",
    "imageUrl": "/api/images/wifi_heatmap_001.png",
    "title": "WIFI 信号热力图",
    "conclusion": "客厅区域信号强度良好，卧室角落存在弱覆盖"
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `renderType` | `"image"` | 固定值 |
| `renderData.imageId` | `string` | 图片唯一 ID |
| `renderData.imageUrl` | `string` | 图片访问路径（相对 URL） |
| `renderData.title` | `string` | 图片标题 |
| `renderData.conclusion` | `string` | 图片描述结论 |

---

### `done`

流式响应正常结束。

```json
{
  "messageId": "550e8400-e29b-41d4-a716-446655440000",
  "thinkingDurationSec": 12
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `messageId` | `string` | 本次 assistant 消息的 UUID（已持久化到数据库） |
| `thinkingDurationSec` | `number` | Orchestrator 推理总耗时（秒），无推理时为 0 |

---

### `error`

任意阶段发生错误时推送，推送后流立即结束。

```json
{
  "message": "Agent 执行失败：连接超时"
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `message` | `string` | 错误描述文字，用于前端展示 |

---

## 典型事件序列

### 场景 1：综合目标规划（Orchestrator → Planning → Provisioning）

```
thinking          # Orchestrator 分析意图
step_start        # stepId: "planning"
thinking          # stepId: "planning"，PlanningAgent 推理
sub_step          # name: "goal_parsing"
thinking          # stepId: "planning"
sub_step          # name: "plan_design"
sub_step          # name: "plan_review"
step_end          # stepId: "planning"
step_start        # stepId: "provisioning-wifi"
sub_step          # name: "wifi_simulation"
step_end          # stepId: "provisioning-wifi"
step_start        # stepId: "provisioning-delivery"
sub_step          # name: "differentiated_delivery"
step_end          # stepId: "provisioning-delivery"
thinking          # Orchestrator 汇总推理
text              # Orchestrator 输出结论（多次）
done
```

### 场景 2：数据洞察

```
thinking          # Orchestrator 分析意图
step_start        # stepId: "insight"
thinking          # stepId: "insight"
sub_step          # name: "insight_plan"
sub_step          # name: "insight_decompose"
sub_step          # name: "insight_query"（多次）
sub_step          # name: "insight_report"
step_end          # stepId: "insight"
render            # renderType: "insight"，包含图表和报告
thinking          # Orchestrator 汇总推理
text              # Orchestrator 输出结论（多次）
done
```

---

## 响应头

```
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
```

`X-Accel-Buffering: no` 用于禁用 Nginx 等反向代理的缓冲，确保事件实时到达客户端。

---

## 错误处理约定

1. **Agent 内部错误**：发送 `error` 事件后结束流，消息**不会**持久化
2. **数据库持久化失败**：静默处理，不影响流式响应，前端不感知
3. **连接中断（客户端 abort）**：后端 SSE 生成器自然终止，无需额外清理
