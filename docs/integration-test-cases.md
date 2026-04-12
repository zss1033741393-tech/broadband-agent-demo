# 前后端联调测试用例

覆盖 5 条路径：基础文本流、数据洞察（render）、单点执行、综合方案、历史恢复。

---

## T1 · 基础文本流（无步骤卡）

**目的**：验证 `text` / `done` SSE 事件，Orchestrator 直接回复不调用 SubAgent。

**输入：**
```
你好，你是什么系统？有什么能力？
```

**预期 UI：**
- 对话气泡：打字机效果逐字出现，无卡顿
- 步骤卡：**无**
- 右侧面板：**空**（无 render 事件）
- 无 thinking 折叠块

**关键 SSE 事件序列：** `text` × N → `done`

---

## T2 · 数据洞察（核心路径，验证 render 事件）

**目的**：验证 InsightAgent 完整链路，含步骤卡、sub_step 计时、右侧图表+报告渲染。

**输入：**
```
查询当前网络中 CEI 评分最低的 PON 口，并分析原因，生成报告
```

**预期 UI：**
- 步骤卡：`InsightAgent` 出现，展开后有多个 sub_step
  - sub_step 名称含 `insight_query`、`insight_report` 等
  - 每个 sub_step 显示耗时（durationMs）
- 右侧面板：自动弹出 **图表 + Markdown 报告**（render 事件触发）
- 对话气泡：Orchestrator 汇总回复

**关键 SSE 事件序列：** `step_start(insight)` → `sub_step` × N → `step_end(insight)` → `render` → `text` × N → `done`

---

## T3 · 单点执行（WIFI 仿真）

**目的**：验证单个 ProvisioningAgent 步骤卡，无 render。

**输入：**
```
帮我做 WIFI 信号仿真，查看当前覆盖情况
```

**预期 UI：**
- 步骤卡：`ProvisioningAgent (WIFI 仿真)` 出现，sub_step 含 `wifi_simulation`
- 右侧面板：**空**（或出现 image render，取决于后端是否生成图片）
- 对话气泡：仿真结果描述

**关键 SSE 事件序列：** `step_start(provisioning-wifi)` → `sub_step` × N → `step_end(provisioning-wifi)` → `text` × N → `done`

---

## T4 · 综合方案（多步骤卡）

**目的**：验证 Planning + 多 Provisioning 并发/串行，步骤卡依次渲染。

**输入：**
```
我的网络质量较差，请帮我制定完整优化方案并执行所有配置
```

**预期 UI：**
- 步骤卡依次出现：
  - `PlanningAgent`（含 sub_step：`goal_parsing`、`plan_design`、`plan_review`）
  - `ProvisioningAgent` × 1~3（视方案内容，可能含 WIFI 仿真、差异化承载、体验保障链）
- 每张步骤卡可独立展开/收起
- 对话气泡：Orchestrator 汇总所有执行结果

**关键 SSE 事件序列：** `step_start(planning)` → ... → `step_end(planning)` → `step_start(provisioning-*)` × N → ... → `text` × N → `done`

---

## T5 · 历史恢复（刷新不丢状态）

**目的**：验证 `GET /messages` 历史接口，render 块可从 DB 恢复到右侧面板。

**操作：** 完成 T2 后，**刷新浏览器**，重新打开同一会话

**预期 UI：**
- 对话历史完整恢复（用户消息 + assistant 回复文字）
- 步骤卡恢复（InsightAgent + sub_steps，含耗时）
- 右侧面板**自动恢复**最后一条 render 块（图表 + Markdown 报告）
- 无需重新发送消息

**关键接口：** `GET /api/conversations/:id/messages` → 返回含 `steps`、`renderBlocks` 的完整 Message

---

## 验证顺序

```
T1 → T2 → T5 → T3 → T4
```

先验证基础流（T1），再验证最复杂的 render 路径（T2），立即接 T5 验证持久化，最后验证其他执行路径。

---

## 排错速查

| 现象 | 可能原因 |
|------|----------|
| 步骤卡不出现 | `delegate_task_to_member` 的 `member_id` 未命中 `_MEMBER_DISPLAY_NAMES` |
| render 不触发 | `insight_query` 返回无 `chart_configs`，或 `insight_report` skill 未被调用 |
| 右侧面板刷新后消失 | `renderBlocks` 未落库，或 `loadMessages` 未恢复 `currentRender` |
| durationMs 全为 0 | `ToolCallStarted` 事件未被捕获，FIFO 队列为空 |
| SSE 流中断 | 后端异常，检查 FastAPI 日志（`/tmp/api.log`） |
