# 洞察函数目录（12 种 + NL2Code 兜底）

本目录列出 `ce_insight_core.run_insight(insight_type, df, value_columns, group_column)`
支持的全部洞察类型及其适用场景与 measures 约束。InsightAgent 在 decompose 阶段必须
严格遵守 measures 数量要求。

## measures 数量约束

### 只接收 1 个 measure
- **Trend**（需 `breakdown.type=ORDERED`）— 线性回归趋势，看某指标的持续上升/下降
- **ChangePoint**（需 `ORDERED`）— 多尺度变点检测（t-test + CUSUM），找异常开始的时间节点。
  对占比/HighCnt 类字段（正常为 0）比 OutlierDetection 更合适
- **Seasonality**（需 `ORDERED`）— FFT + 自相关周期性检测，找固定周期的规律
- **OutlierDetection** — IQR + Z-score 双方法异常检测，找某指标中极端异常的设备
- **Evenness** — 熵 + Gini 系数，分析各设备间得分的均匀度

### 接收 1 个或多个 measure
- **OutstandingMin** — 找某指标**最低**的设备（适合定位得分最差的 PON 口）
- **OutstandingMax** — 找某指标**最高**的设备（适合定位 HighCnt 类最异常的设备）
- **OutstandingTop2** — 前两名最突出的设备对比
- **Attribution** — 贡献度归因，分析各主体对总体异常的贡献度
- **Clustering** — KMeans 聚类，把设备按相似度分组

### 精确数量要求
- **Correlation**（**恰好** 2 个 measure）— Pearson 相关系数，验证"A 高是否导致 B 低"
- **CrossMeasureCorrelation**（**≥ 3** 个 measure）— 多指标交叉相关矩阵

### 自定义兜底
- **NL2Code** — 灵活分析，用于：
  - Top N / Bottom N 查询（`df.nsmallest(3, col)` / `df.nlargest(5, col)`）
  - 自定义公式、多字段组合排序
  - 多步骤数据融合、复杂分类逻辑
  - 任何"一步输出确定结果"的简单查询优先用它，不要拼凑多个洞察函数
  - **只传代码字符串给 `run_nl2code.py`**，不自动生成；代码由 InsightAgent 写

## 业务选择建议

| 目标 | 首选函数 |
|---|---|
| 找得分最低的 PON 口 | OutstandingMin |
| 找异常次数最多的设备 | OutstandingMax |
| 找哪个维度贡献了低分 | Attribution |
| 看维度得分时间趋势 | Trend |
| 找异常开始的时间点 | ChangePoint |
| 验证两指标因果 | Correlation |
| 全维度交叉影响 | CrossMeasureCorrelation |
| 网关/WiFi 干扰问题 | 天表 OutstandingMax on midInterferencePercent/highInterferencePercent |
| 占比/HighCnt 类字段（正常 0） | ChangePoint（比 OutlierDetection 效果好） |

## 返回值结构

每次 `run_insight` 返回：
```json
{
  "insight_type": "OutstandingMin",
  "significance": 0.41,
  "description": {"min_group": "...", "summary": "..."},
  "filter_data": [{"portUuid": "...", "CEI_score": 45.0}, ...],
  "chart_configs": {"chart_type": "bar", "title": {...}, "series": [...]}
}
```

- **significance ∈ [0, 1]** — 结果显著性；< 0.3 可在报告中折叠
- **description** — 文字描述（可能是 str 或 dict，含 `summary` 键时优先取 summary）
- **filter_data** — 供后续步骤筛选的原始记录（InsightAgent 可据此提取 `found_entities`）
- **chart_configs** — ECharts option JSON（`chart_type` + 标准 ECharts 字段）；**禁止改写**，原样透传

## 指标方向判断

- `*_score` 字段越大越好（满分 100）
- `*HighCnt` / `*Percent` / `count_*` 字段正常为 0；有数值即异常
- 网关问题通常伴随干扰占空比：`midInterferencePercent` / `highInterferencePercent` / `lowInterferencePercent`
