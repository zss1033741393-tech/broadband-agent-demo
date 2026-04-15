# 洞察函数目录（12 种 + NL2Code 兜底）

本目录列出 `ce_insight_core.run_insight(insight_type, df, value_columns, group_column)` 支持的全部洞察类型及其适用场景与 measures 约束。

InsightAgent 在 decompose 阶段必须严格遵守 measures 数量与 breakdown 类型要求，否则 runner 会在调用策略前直接返回 `significance=0` + 错误描述。

---

## 一、快速选择表

| 业务目标 | 首选函数 | 关键参数 |
|---|---|---|
| 找某指标得分**最低**的设备 | `OutstandingMin` | 1 measure + 1 group |
| 找某指标**最高/最异常**的设备 | `OutstandingMax` | 1 measure + 1 group |
| 找前两名最突出的设备 | `OutstandingTop2` | 1 measure + 1 group |
| **多设备 × 多维度对比**，每个设备各自最差/好的 measure | `OutstandingMin/Max`（**矩阵模式**） | 多 measure + 多 group |
| 多个候选指标横向对比，找整体最异常的维度 | `OutstandingMin/Max`（**measure_compare 模式**）| 多 measure + 0~1 group |
| 哪些 group 在拉低整体均值 | `Attribution`（**单 measure 模式**） | 1 measure + 1 group |
| 已定位某主体后，看哪个**指标**占主导 | `Attribution`（**多 measure 模式**） | ≥2 measures + 1 group ⚠️ 见语义陷阱 |
| 时序：是否上升/下降 | `Trend` | 1 measure + ORDERED |
| 时序：找异常起始的时间点 | `ChangePoint` | 1 measure + ORDERED |
| 时序：找周期性（日/周周期）| `Seasonality` | 1 measure + ORDERED |
| 单指标分布异常点 | `OutlierDetection` | 1 measure（group 可选）|
| 各分组分布是否均匀（基尼）| `Evenness` | 1 measure + 1 group |
| 验证两指标的相关性（A↔B）| `Correlation` | **正好 2 measures** |
| 多指标交叉相关矩阵 | `CrossMeasureCorrelation` | **≥ 3 measures** |
| 设备聚类成几个特征群 | `Clustering` | 多 measure |
| 占比/HighCnt 类字段（值多为 0）| `ChangePoint` 优于 `OutlierDetection` | — |
| 一步式 Top N / 自定义公式 / 复杂逻辑 | NL2Code 兜底 | LLM 自己写 pandas |

---

## 二、12 个函数详细目录

### A 类 · 排序对比 — Outstanding 系列（3 模式自动切换）

⚠️ **重要**：`OutstandingMin / OutstandingMax / OutstandingTop2` 三个函数都有 **3 种模式**，由 `value_columns` 数量 + `group_column` 实际唯一值数量自动决定，**LLM 必须根据想要的输出形态选对参数组合**：

| 模式 | 触发条件 | 输出形态 | 何时用 |
|---|---|---|---|
| **A1. 单值模式** | `len(value_columns) == 1` | 在 group 维度上找该指标的极值 | "找 CEI_score 最低的 PON 口" |
| **A2. measure_compare 模式** | `len(value_columns) ≥ 2` 且 group 唯一值 ≤ 1 | 横向对比哪个 measure 整体最高/低 | "8 个维度里哪个最差"（无下钻分组）|
| **A3. matrix 矩阵模式** | `len(value_columns) ≥ 2` 且 group 唯一值 ≥ 2 | 每个 group 各自最差/好的 measure | "5 个 PON 口各自最差的维度" |

#### `OutstandingMin`
- **算法**：分组求均值 → 排序 → 取最低
- **measures**：1 个或多个（决定模式）
- **group_column**：必须
- **最小数据要求**：≥ 2 个 group
- **显著性公式**：
  - 单值模式：`|z_score|/3`，z = (overall_mean - min_val) / std
  - measure_compare：同上但 z 是 measure 间的
  - matrix：`concentration`（最差 measure 的出现频率），clip 到 [0.3, 1.0]
- **description 关键字段**：
  - 单值：`min_group / min_value / second_value / gap / z_score / summary`
  - matrix：`mode="matrix" / per_group_worst / most_common_worst / most_common_count / n_groups / summary`
- **chart_type**：`bar`（最低值高亮红色）

#### `OutstandingMax`
和 `OutstandingMin` **完全对称**，所有模式和规则相同，方向相反。**LLM 不要弄反**——找"最低分设备"用 Min，找"错误次数最多设备"用 Max。
- **description**：单值 `max_group / max_value / ...`；matrix `per_group_best / most_common_best / ...`

#### `OutstandingTop2`
- **算法**：找前两名 vs 其余的差距
- **measures**：1 个或多个（同样 3 模式）
- **group_column**：必须
- **最小数据要求**：≥ 2 个 group
- **显著性公式**：
  - 单值/measure_compare：`top2_share = top2.sum() / total.sum()`（前 2 名占总量比）
  - matrix：`concentration`
- **何时用**：用户问"前两个 / 一二名 / 最重要的两个"
- **chart_type**：`bar`，单值/measure_compare 模式 top2 红，matrix 模式 top1 深红 + top2 珊瑚粉

---

### B 类 · 时序 — Trend / Seasonality / ChangePoint

⚠️ **三个时序函数都只用 `value_columns[0]`**，多余的 measure 会被**静默忽略**。如果想分析多个指标的趋势，必须**拆成多个 step**，每个 step 一个 measure。

⚠️ `breakdown.type` 必须是 `ORDERED`，`group_column` 应为时间列（`date / time_id`），脚本会自动 `sort_values(group_column)`。

#### `Trend`
- **算法**：`np.polyfit` 最小二乘线性回归 + R²
- **measures**：仅用第一个
- **group_column**：必须，时间列
- **最小数据要求**：≥ 3 行
- **显著性公式**：`R²`（拟合度直接作为 significance）
- **description**：`direction("上升"|"下降") / slope / r_squared / summary`
- **chart_type**：`line`，含原始线 + 红色虚线趋势线 + 突变点橙色 pin markPoint
- **副作用**：会顺手做相邻差值检测，把超过 2σ 的点标 pin（最多 3 个）

#### `Seasonality`
- **算法**：去趋势（线性回归减掉）→ FFT → 找最大 power 频率 → 主周期 = 1/freq
  > ⚠️ **只有 FFT，没有自相关**（旧文档写错了）
- **measures**：仅用第一个
- **group_column**：必须，时间列
- **最小数据要求**：**≥ 6 行**（FFT 需要足够样本）
- **显著性公式**：`power_ratio = dominant_power / total_power`（主周期能量占比）
- **description**：`dominant_period / power_ratio / summary`
- **chart_type**：`line`，三条线（蓝原始 + 橙趋势虚线 + 绿去趋势带阴影）
- **何时用**：分钟表数据，想找日周期/周周期
- **何时不用**：< 6 个时间点；纯随机波动数据

#### `ChangePoint`
- **算法**：多窗口 t-test（窗口大小自适应 [2,3,5,7]）+ 邻点变化率检测，融合后过滤低置信度（< 0.5）+ 相邻点去重，找不到任何变点时 CUSUM 兜底取 1 个
  > ⚠️ **CUSUM 是兜底**，不是主算法（旧文档写成"t-test + CUSUM"是错的）
- **measures**：仅用第一个
- **group_column**：必须，时间列
- **最小数据要求**：≥ 3 行（**实际推荐 ≥ 9**，因为窗口最小 3 时需要 `n ≥ w*3`）
- **显著性公式**：`max(|前后差|/std) / 3`（最显著变点的前后差 / 整体 σ）
- **description**：`change_points[] / best{index,time,before_mean,after_mean,diff,direction} / count / summary`
- **特殊**：**自动近零值放大**（`max_abs < 0.01` 时 ×1000~10000）
- **chart_type**：`line`，红色 markLine + markArea + 橙/绿色前后均值水平段
- **何时用**：占比/HighCnt 类字段（值多为 0）的异常起始点检测——比 OutlierDetection 更适合

---

### C 类 · 分布与异常 — OutlierDetection / Evenness

#### `OutlierDetection`
- **算法**：IQR (`Q1 - 1.5×IQR, Q3 + 1.5×IQR`) **并集** Z-score (`|z| > 3`，近零值场景降到 2)
- **measures**：仅用第一个
- **group_column**：**可选**（不传时图表用序号做 x 轴；传了用作 x 轴标签）
- **最小数据要求**：≥ 3 行
- **显著性公式**：`max(outlier_ratio*5, max_z/6)`，clip [0,1]
- **description**：`outlier_count / outlier_ratio / iqr_outliers / zscore_outliers / lower_bound / upper_bound / zero_count / zero_ratio / is_near_zero / summary`
- **特殊**：**自动近零值放大**（同 ChangePoint，max_abs < 0.01 时 ×10000~100000）
- **chart_type**：`scatter`，正常点蓝半透 + 异常点红实心 + 上下限橙色虚线 markLine
- **何时用**：单指标找离群点
- **何时不用**：占比/HighCnt 字段值多为 0 的情况——会被 0 值拖偏，改用 `ChangePoint`

#### `Evenness`
- **算法**：分组求均值 → **基尼系数 + 变异系数 CV**
  > ⚠️ **没有"熵"**（旧文档写成"熵 + Gini"是错的）
- **measures**：仅用第一个
- **group_column**：必须
- **最小数据要求**：≥ 2 个 group
- **显著性公式**：`gini`（基尼系数直接作为 significance）
- **分级**：`gini < 0.2` 均匀 / `< 0.4` 一定差异 / `≥ 0.4` 很不均匀
- **description**：`gini / cv / level / summary`
- **chart_type**：`bar`，含均值水平虚线 markLine
- **何时用**：判断"问题集中在少数设备 vs 全网普遍"

---

### D 类 · 关系发现 — Correlation / CrossMeasureCorrelation / Clustering

#### `Correlation`
- **算法**：`scipy.stats.pearsonr` 两列相关系数 + p-value
- **measures**：**正好 2 个**——多了**只用前两个**（其余静默丢弃 ⚠️），少于 2 直接报错
- **group_column**：不需要
- **最小数据要求**：≥ 3 行；任一列方差为 0 直接报错
- **显著性公式**：`|correlation|`
- **强度分级**：`|r|≥0.7 强 / ≥0.5 中等 / ≥0.3 弱 / 否则极弱`
- **description**：`correlation / p_value / strength / direction / summary`
- **chart_type**：`scatter` + 粉色虚线拟合
- **何时用**：明确想验证两个指标的关系（A↔B）

#### `CrossMeasureCorrelation`
- **算法**：所有 measure 两两 pearsonr，按 |r| 排序
- **measures**：**至少 3 个**（少于 3 报错并提示用 `Correlation`）
- **group_column**：不需要
- **最小数据要求**：≥ 3 行；零方差列**自动剔除**
- **显著性公式**：最强相关对的 `|r|`
- **三段兜底阈值**：先尝试 `|r|≥0.5 且 p<0.05` → 找不到放宽到 `|r|≥0.2` → 仍无则取全部并标 `is_fallback=true`
- **description**：`variable_count / significant_pairs / strong_pairs / medium_pairs / weak_pairs / very_weak_pairs / top_pairs[] / matched_columns / summary`（fallback 时多 `removed_low_variance / message / is_fallback`）
- **chart_type**：`heatmap`，强相关上色 + 弱相关灰底 + visualMap
- **何时用**：探索性分析，多个候选指标里找有关系的对

#### `Clustering`
- **算法**：StandardScaler 标准化 → KMeans，**k 在 2~5 自动选轮廓系数最高的**
- **measures**：1 个或多个；图表 x/y 轴分别用 `value_columns[0]` 和 `[1]`
- **group_column**：不需要
- **最小数据要求**：≥ 3 行（**实际推荐 ≥ 6**，因为 max_k=5）
- **依赖**：sklearn（**12 个里唯一依赖 sklearn**）
- **显著性公式**：`silhouette_score`（轮廓系数），clip [0,1]
- **description**：`n_clusters / silhouette_score / cluster_centers / summary`
- **chart_type**：`scatter`，每簇一个 series，颜色取自 PALETTE 轮换
- **何时用**：想把设备/分组按特征自动分群

---

### E 类 · 归因 — Attribution（**2 模式自动切换**）

⚠️ **重要**：`Attribution` 有 **2 种模式**，由 `value_columns` 数量自动决定。两种模式语义**完全不同**，不要混用：

| 模式 | 触发条件 | 问的问题 | 输出形态 |
|---|---|---|---|
| **E1. 单 measure 模式** | `len(value_columns) == 1` | "X 指标在哪些 group 上拉低/拉高了均值" | 按 group 排的偏差贡献 |
| **E2. 多 measure 模式** | `len(value_columns) ≥ 2` | "对一个主体，哪个 measure 占总和的主导" | 按 measure 排的份额贡献 |

#### E1. 单 measure 模式
- **算法**：每组贡献度 = `(组均值 - 总均值) × 组样本占比`，归一化为百分比
- **group_column**：必须
- **显著性公式**：`max(|contribution_pct|) / 100`
- **description**：`mode="single_measure" / top_neg_groups / top_neg_pcts / max_neg_contribution_pct / summary`
- **chart_type**：横向 `bar`，红=负贡献（拉低）/ 绿=正贡献（拉高）
- **何时用**：定位"哪些设备拉低了整体均值"

#### E2. 多 measure 模式（新功能）
- **算法**：把数据聚合（多行取均值，单行直接用）成"一个主体" → 每个 measure 贡献度 = `value / total` → 按 |contribution| 降序
- **group_column**：必须（用作 `group_label` 显示，不强制要求实际筛选）
- **显著性公式**：`norm.cdf(max_contribution)`（**注意输出范围 [0.5, 0.84]，不会到 1**）
- **主导阈值**：`|max_contribution| ≥ 0.5` 时标 `is_significant=True`
- **description**：`mode="multi_measure" / group_label / n_measures / total / top_measure / top_value / top_contribution_pct / is_significant / summary`
- **filter_data 字段**：`measure / value / contribution / contribution_pct`（**注意：没有 group_column 列**，所以不会产出可下钻的 `found_entities`）
- **chart_type**：横向 `bar`，主导贡献者红色 / 其他蓝色

#### ⚠️ Attribution 多 measure 模式的语义陷阱

多 measure 模式计算的是**份额**（`value / total`），它的语义在不同字段类型上**完全相反**：

| 字段类型 | 例子 | "贡献最大"含义 | 是否符合直觉 |
|---|---|---|---|
| **HighCnt 类**（值越大越异常）| `bipHighCnt / fecHighCnt / oltRxPowerHighCnt` | 错误源占总错误数 80% → **就是问题根源** | ✅ 符合 |
| **Score 类**（值越大越好）| `ODN_score / Wifi_score / CEI_score` | Wifi_score 占总分 30% → **是分数最高的维度，不是问题** | ❌ 完全相反 |

**LLM 决策指南**：

| 你想找什么 | 字段类型 | 该用什么 |
|---|---|---|
| "对某 PON 口，8 个维度里哪个**错误最多**" | HighCnt | ✅ Attribution 多 measure |
| "对某 PON 口，8 个维度里哪个**得分最低**" | Score | ❌ **不要用 Attribution 多 measure**！应该用 `OutstandingMin` measure_compare 模式（多 measure + 1 group） |
| "全网 5 个 PON 口各自最差的维度" | Score | 用 `OutstandingMin` 矩阵模式 |
| "哪些 PON 口拉低了全网 CEI 均值" | Score | 用 Attribution 单 measure 模式（这是它的正典场景）|

---

## 三、Correlation vs CrossMeasureCorrelation 互斥规则

LLM 经常搞混这两个，记住下面这张表：

| 你想分析几个指标 | 用哪个 | 错误用法的后果 |
|---|---|---|
| **正好 2 个** | `Correlation` | 用 `CrossMeasureCorrelation` 会被报"需至少 3 个指标列" |
| **3 个或更多** | `CrossMeasureCorrelation` | 用 `Correlation` 会**只取前 2 个**（静默丢掉其他 measure），你以为分析了 5 个其实只算了 2 个 |
| **只有 1 个** | 都不能用 | 改用 `Trend / Seasonality / OutlierDetection` 等单指标函数 |

---

## 四、最小数据量速查表

| 函数 | 最小要求 | 备注 |
|---|---|---|
| `Trend` | ≥ 3 行 | 数据点太少回归不可信 |
| `Seasonality` | **≥ 6 行** | FFT 需要足够样本 |
| `ChangePoint` | ≥ 3 行（推荐 ≥ 9） | 窗口最小 3 时需 `n ≥ 9` 才能跑多窗口 |
| `OutlierDetection` | ≥ 3 行 | IQR 需四分位 |
| `Correlation` | ≥ 3 行 | 且两列方差不为 0 |
| `CrossMeasureCorrelation` | ≥ 3 行 + ≥ 3 measures | 零方差列自动剔除 |
| `Clustering` | ≥ 3 行（推荐 ≥ 6） | KMeans max_k=5 |
| Outstanding 系列 | ≥ 2 个 group | 单值模式；matrix 模式同样 ≥ 2 |
| `Evenness` | ≥ 2 个 group | 至少要有差异可比 |
| `Attribution` 单 measure | ≥ 2 个 group | 单一分组无可归因 |
| `Attribution` 多 measure | ≥ 1 行 + ≥ 2 measures | 单行直接用，多行取均值 |

如果数据量不够，函数会返回 `significance=0` + 描述性错误，LLM 应在 reflect 阶段考虑换函数或缩小过滤条件。

---

## 五、显著性阈值参考（reflect 阶段判断用）

⚠️ **各函数的 significance 公式完全不同**，不要拿 Trend 的 0.5 和 OutstandingMin 的 0.5 直接比。下表给出"高显著（≥0.7）"实际意味着什么：

| 函数 | 公式 | 0.7+ 意味着 |
|---|---|---|
| OutstandingMin/Max（单值）| `|z|/3` | 极值偏离均值 ≥ 2σ |
| OutstandingTop2（单值）| `top2_share` | 前 2 名占总量 > 70% |
| Outstanding（matrix）| `concentration` | 多数 group 共同短板 |
| Trend | `R²` | 趋势拟合度极高 |
| Seasonality | `power_ratio` | 主周期占总能量 > 70% |
| ChangePoint | `max\|diff\|/std/3` | 变点前后差距 ≥ 2σ |
| OutlierDetection | `max(ratio*5, maxz/6)` | 异常率 > 14% 或最大 z > 4 |
| Evenness | `gini` | 分布极不均匀 |
| Correlation | `\|r\|` | 强相关 |
| CrossMeasureCorrelation | 最强对的 `\|r\|` | 强相关 |
| Clustering | `silhouette_score` | 聚类清晰可分 |
| Attribution 单 measure | `max\|pct\|/100` | 单一 group 拉走过半贡献 |
| Attribution 多 measure | `norm.cdf(max_contribution)` | ⚠️ 输出范围 [0.5, 0.84]，**0.7 已经是相对高分**，不要套用其他函数的阈值 |

---

## 六、NL2Code 兜底

适用场景：12 个洞察函数都不能精准表达需求，需要 LLM 自己写 pandas 代码：

- Top N / Bottom N 查询（`df.nsmallest(3, col)` / `df.nlargest(5, col)`）
- 自定义公式、加权打分、多字段组合排序
- 多步骤数据融合、复杂 groupby 逻辑
- 任何"一步输出确定结果"的简单查询优先用它，**不要拼凑多个洞察函数**

调用方式：用 `insight_nl2code` skill 的 `run_nl2code.py`，代码字符串由 InsightAgent 自己写并传入。

---

## 七、返回值结构

每次 `run_insight` 返回：
```json
{
  "insight_type": "OutstandingMin",
  "significance": 0.41,
  "description": {"mode": "...", "summary": "..."},
  "filter_data": [{"portUuid": "...", "CEI_score": 45.0}, ...],
  "chart_configs": {"chart_type": "bar", "title": {...}, "series": [...]}
}
```

- **`significance` ∈ [0, 1]** — 结果显著性；< 0.3 可在报告中折叠。**注意各函数公式不同**，详见上面"显著性阈值参考"节
- **`description`** — **永远是 dict**，所有 12 个函数均含 `summary` 字段，LLM 取摘要直接 `description.get("summary")`。多模式函数（Outstanding / Attribution）会有 `mode` 字段区分子模式
- **`filter_data`** — 供后续步骤筛选的原始记录。InsightAgent 据此提取 `found_entities` 用于下钻——**注意 Attribution 多 measure 模式的 filter_data 不含 group_column 列**，无法产出可下钻的实体
- **`chart_configs`** — 100% 标准 ECharts option JSON。`chart_type` 字段是给前端做路由用的元信息（值都是标准 ECharts 类型：bar / line / scatter / heatmap）；其余字段直接喂 `echarts.setOption()` 即可。**禁止改写**，原样透传

---

## 八、指标方向判断

- `*_score` 字段越大越好（满分 100）
- `*HighCnt` / `*Percent` / `count_*` 字段正常为 0；有数值即异常
- 网关问题通常伴随干扰占空比：`midInterferencePercent` / `highInterferencePercent` / `lowInterferencePercent`
- **占比/HighCnt 字段值多为 0 时，优先用 `ChangePoint` 而非 `OutlierDetection`**（后者会被零值拖偏）
- **Score 字段做"找最差"分析时，优先用 `OutstandingMin` 而非 `Attribution` 多 measure**（语义相反）
