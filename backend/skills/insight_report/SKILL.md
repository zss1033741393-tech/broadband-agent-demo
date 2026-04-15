---
name: insight_report
description: "洞察报告生成：汇总所有 Phase 的分析结果，渲染 Markdown 报告 + 结构化交接契约"
---

# 洞察报告

## Metadata
- **paradigm**: Generator
- **when_to_use**: InsightAgent 完成所有 Phase 后，汇总生成最终报告
- **inputs**: 所有 Phase 的 step_results + reflection_log
- **outputs**: Markdown 报告（stdout）+ 结构化交接契约 JSON（assistant 代码块）

## When to Use
- ✅ 所有 Phase 执行完毕，需要生成最终报告
- ❌ 还有未完成的 Phase（先完成再出报告）

## How to Use

### 方式 1 — 调用渲染脚本
```
get_skill_script(
    "insight_report",
    "render_report.py",
    execute=True,
    args=["<context_json_string>"]
)
```
context JSON 格式见 `references/output_schema.md`。
脚本 stdout 是渲染好的 Markdown，**必须原样输出，禁止改写**。

### 方式 2 — 兜底（脚本调用失败时）
直接在 assistant 消息中用 Markdown 输出报告，包含：
- 各 Phase 的步骤结果表格
- 关键发现总结
- 结构化交接契约 JSON

手写时遵循以下格式约定：
- 每个 Phase 前加 `---` 横线分界
- 每个有图的 step，在 `description` 末尾追加 `\n\n[CHART:p{phase_id}s{step_id}]`
  例：Phase 1 Step 2 的 description → `"...分析结论\n\n[CHART:p1s2]"`
  占位符由 InsightAgent 根据工具调用结果中 chart_configs 是否非空自行决定是否插入

### Report 阶段输出清单（3 样，不多不少）

1. **`render_report.py` stdout**（Markdown 报告，通过 ToolCallCompleted 自动展示）
2. **`<!--event:done-->`**（流程结束信号）：
   ```
   <!--event:done-->
   {"total_phases": 4, "total_steps": 12, "total_charts": 8}
   ```
3. **summary JSON 代码块**（结构化交接契约，供 Orchestrator 消费）

> `<!--event:report-->` 已移除 — 其数据与 stdout + step_result 重复，改由上述 3 项替代。

## Scripts
- `scripts/render_report.py` — Jinja2 模板渲染 Markdown 报告

## References
- `references/output_schema.md` — context JSON 契约 + 各脚本 stdout 字段说明（Agent 用）
- `references/multi_phase_report.md.j2` — 多阶段报告 Jinja2 模板
- `references/report.md.j2` — 归因报告 Jinja2 模板（旧版兼容）

## 禁止事项
- ❌ 不得改写 render_report.py 的 stdout
- ❌ 报告完成后禁止自动进入 Planning（必须等用户确认）
- ❌ context JSON 各字段（包括 key_findings、direct_answer、root_cause_narrative 等）禁止使用 emoji 字符，只能使用纯文本
