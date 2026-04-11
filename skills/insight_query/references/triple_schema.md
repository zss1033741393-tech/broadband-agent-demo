# 三元组查询契约

`ce_insight_core.query_subject_pandas(query_config, data_path)` 的输入结构。
所有数据查询必须走三元组。

## 基本结构

```json
{
  "dimensions": [[]],
  "breakdown": {"name": "portUuid", "type": "UNORDERED"},
  "measures": [{"name": "CEI_score", "aggr": "AVG"}]
}
```

### `dimensions` — 双层列表的维度筛选

- **不筛选时必须写 `[[]]`**，不能保留空的 `dim_cond` 结构
- 有筛选时写 `[[{...}]]`（注意双层方括号）
- 多组条件用 `AND` 组合

筛选条件格式：
```json
[[
  {
    "dimension": {"name": "portUuid", "type": "DISCRETE"},
    "conditions": [{"oper": "IN", "values": ["uuid-1", "uuid-2"]}]
  }
]]
```

**禁止**：
- `conditions: []`（空条件数组）
- `conditions: [{"oper": "IN", "values": []}]`（空 values）
- 在 values 中使用 placeholder / 虚构值 / 前序步骤变量引用 — 要么用真实值，要么写 `dimensions: [[]]`

### `breakdown` — 分组维度

- **`type`**：
  - `ORDERED` — 时间序列（`date` / `time_id`），用于 Trend / ChangePoint / Seasonality
  - `UNORDERED` — 分组对比（`portUuid` / `gatewayMac`），用于 OutstandingMin/Max 等
- **必须是离散字段**，不能用 CEI_score 等连续数值字段做 breakdown
- 天表可用：`portUuid` / `date` / `gatewayMac`
- 分钟表可用：`portUuid` / `time_id` / `gatewayMac`

### `measures` — 度量指标

```json
[{"name": "CEI_score", "aggr": "AVG"}]
```

- **`aggr`**：`SUM` / `AVG` / `COUNT` / `MIN` / `MAX`
- **`name`** 必须是所查表（day / minute）的合法字段名
- 天表字段示例：`CEI_score` / `ODN_score` / `bipHighCnt` / `midInterferencePercent`
- 分钟表字段完全不同，使用前务必通过 `list_schema.py table=minute` 查看合法字段

## 天表 vs 分钟表

⚠️ **天表字段和分钟表字段完全不兼容**。`ce_insight_core.fix_query_config(config, table_level=...)`
会做字段合法性校验 + 模糊匹配修复；修复警告会透传到脚本 stdout。

- 天表 `table_level="day"`：聚合到日粒度，字段多是 `_score` / `HighCnt` / `Percent`
- 分钟表 `table_level="minute"`：原始采集数据，字段多是 `Rate` / `RxPower` / 标记类 `*High` (0/1)

## 运算符

`oper` 字段取值：`IN` / `NOT_IN` / `BETWEEN` / `GREATER` / `LESS` / `EQUAL` / `NOT_EQUAL`

## 完整示例

### 示例 1：全网查询 PON 口 CEI 均值
```json
{
  "dimensions": [[]],
  "breakdown": {"name": "portUuid", "type": "UNORDERED"},
  "measures": [{"name": "CEI_score", "aggr": "AVG"}]
}
```

### 示例 2：下钻异常设备的 8 维度得分
```json
{
  "dimensions": [[{
    "dimension": {"name": "portUuid", "type": "DISCRETE"},
    "conditions": [{"oper": "IN", "values": ["uuid-a", "uuid-b", "uuid-c"]}]
  }]],
  "breakdown": {"name": "date", "type": "ORDERED"},
  "measures": [
    {"name": "Stability_score", "aggr": "AVG"},
    {"name": "ODN_score", "aggr": "AVG"},
    {"name": "Rate_score", "aggr": "AVG"}
  ]
}
```

### 示例 3：分钟表时序下钻
```json
{
  "dimensions": [[{
    "dimension": {"name": "portUuid", "type": "DISCRETE"},
    "conditions": [{"oper": "IN", "values": ["uuid-a"]}]
  }]],
  "breakdown": {"name": "time_id", "type": "ORDERED"},
  "measures": [{"name": "oltRxPowerHigh", "aggr": "AVG"}]
}
```
