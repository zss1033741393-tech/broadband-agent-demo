# Report 阶段 context JSON 契约

> 本文档定义 `render_report.py` 的输入格式（context JSON）及各脚本的 stdout JSON Schema。
> Agent 在 Report 阶段需要把所有 Phase 的执行结果组装为此格式。
> 前端渲染相关文档见 `docs/frontend_data_contract.md`。

---

## context JSON（render_report.py 的输入）

```json
{
  "title": "网络质量数据洞察报告",
  "goal": "<MacroPlan.goal>",
  "phases": [
    {
      "phase_id": 1,
      "name": "L1-定位低分PON口",
      "milestone": "识别CEI最低的PON口列表",
      "table_level": "day",
      "steps": [
        {
          "step_id": 1,
          "insight_type": "OutstandingMin",
          "significance": 0.73,
          "description": "CEI_score 最小值出现在 288b6c71-...",
          "found_entities": {"portUuid": ["288b6c71-...", "1c86d285-..."]},
          "chart_configs": { ... }
        }
      ],
      "reflection": {"choice": "A", "reason": "..."}
    }
  ],
  "summary": {
    "goal": "...",
    "priority_pons": ["uuid-a", "uuid-b"],
    "priority_gateways": ["mac-a"],
    "distinct_issues": ["ODN 光功率异常", "WiFi 干扰高"],
    "scope_indicator": "single_pon | multi_pon | regional",
    "peak_time_window": "19:00-22:00",
    "has_complaints": true,
    "remote_loop_candidates": ["uuid-a"],
    "root_cause_fields": ["oltRxPowerHighCnt", "bipHighCnt"],
    "reflection_log": [{"phase": 1, "choice": "A", "reason": "..."}]
  }
}
```

---

## 各脚本 stdout JSON 字段说明（Agent 需关注的字段）

### run_insight.py stdout 核心字段

| 字段 | 类型 | Agent 用途 |
|---|---|---|
| `status` | `"ok"` / `"error"` | 判断步骤是否成功 |
| `insight_type` | string | 填入 step_result 事件和 context JSON |
| `significance` | float [0, 1] | 填入 step_result；>= 0.5 为高显著性 |
| `description` | string / dict | dict 时取 `.summary`；填入 step_result |
| `filter_data` | array[dict] | 原样保留供 Report 阶段使用 |
| `chart_configs` | dict | 原样保留，禁止改写 |
| `found_entities` | dict | 供后续 step 下钻 + summary JSON 推导 |
| `phase_id` / `step_id` | int / null | 透传，用于通道关联 |
| `fix_warnings` | array[string] | 非空时需在 step description 末尾附加警告 |

### run_nl2code.py stdout 核心字段

| 字段 | 类型 | Agent 用途 |
|---|---|---|
| `status` | `"ok"` / `"error"` | 判断步骤是否成功 |
| `result` | dict | `type` 字段区分 dataframe/dict/list/scalar/none |
| `description` | string | 填入 step_result 事件 |
| `phase_id` / `step_id` | int / null | 透传 |

### 12 种 insight_type

| insight_type | 说明 |
|---|---|
| OutstandingMin | 找最低值 |
| OutstandingMax | 找最高值 |
| OutstandingTop2 | 找前两名 |
| Trend | 线性回归趋势 |
| ChangePoint | 时序变点检测 |
| Seasonality | 周期性检测 |
| OutlierDetection | 异常点检测 |
| Correlation | 两指标相关性 |
| CrossMeasureCorrelation | 多指标交叉相关 |
| Clustering | KMeans 聚类 |
| Attribution | 贡献度归因 |
| Evenness | 均匀度分析 |

---

## 错误格式（所有脚本通用）

```json
{
  "status": "error",
  "skill": "<对应 skill 名>",
  "op": "<对应 op>",
  "error": "错误描述信息"
}
```

Agent 遇到 `status: "error"` 时应在 step_result 事件中标记 `"status": "error"` 并写入 `summary` 描述。
