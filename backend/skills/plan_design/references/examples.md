# Plan Design Few-Shot 样例

以下样例覆盖场景 1（完整方案）、场景 2（稀疏方案）、场景 2 变体（仅 AP补点启用）。

---

## 样例 1 — 场景 1：直播套餐楼宇直播保快手

**输入画像**:
```json
{
  "user_type": "主播用户",
  "package_type": "直播套餐",
  "scenario": "楼宇直播",
  "guarantee_target": "应用级",
  "time_window": "全天",
  "guarantee_app": "快手",
  "complaint_history": false
}
```

**产出方案**:

```text
AP补点推荐：
    WIFI信号仿真：False 
    应用卡顿仿真：False 
    AP补点推荐：False 

CEI体验感知：
    CEI模型：直播模型 
    CEI粒度：分钟级
    CEI阈值：80分

故障诊断：
    诊断场景：直播卡顿
    偶发卡顿定界：True 

远程优化：
    远程优化触发时间：闲时 
    远程WIFI信道切换：False 
    远程网关重启：True
    远程WIFI功率调优：False

差异化承载：
    差异化承载：True
    应用类型：直播
    保障应用：快手
    业务类型：app-flow

```

**关键业务规则体现**:
- 直播套餐 + 楼宇直播 → CEI 模型选"直播模型"（Provisioning 按预设表翻译为 ServiceQualityWeight:40 权重 CSV）
- 保障应用快手 + 直播套餐 → 诊断场景：直播卡顿
- 楼宇直播（有线连接，无wifi连接）→ `远程网关重启：True`，不做wifi信道切换 + 功率调优
- 直播套餐（有保障时段）→ 触发时间：闲时
- 差异化承载 → `差异化承载：True`，`应用策略：app-flow`，有线连接场景只保障PON管道

---

## 样例 2 — 场景 1：直播套餐卖场走播保抖音

**输入画像**:
```json
{
  "user_type": "主播用户",
  "package_type": "直播套餐",
  "scenario": "卖场走播",
  "guarantee_target": "应用级",
  "time_window": 全天,
  "guarantee_app": "抖音",
  "complaint_history": True
}
```

**产出方案**:

```text
AP补点推荐：
    WIFI信号仿真：True 
    应用卡顿仿真：True 
    AP补点推荐：True  

CEI体验感知：
    CEI模型：直播模型 
    CEI粒度：分钟级
    CEI阈值：85分

故障诊断：
    诊断场景：直播卡顿
    偶发卡顿定界：True 

远程优化：
    远程优化触发时间：闲时 
    远程WIFI信道切换：True 
    远程网关重启：False
    远程WIFI功率调优：True

差异化承载：
    差异化承载：True
    应用类型：直播
    保障应用：抖音
    业务类型：assurance-app-slice

```

**关键业务规则体现**:
- 直播套餐 + 卖场走播 → CEI 模型选"直播模型"（Provisioning 按预设表翻译为 ServiceQualityWeight:40 权重 CSV）
- 保障应用抖音 + 直播套餐 → 诊断场景：直播卡顿
- 卖场走播（走动业务，忌重启）→ `远程网关重启：False`，仅做信道切换 + 功率调优
- 直播套餐（有保障时段）→ 触发时间：闲时
- 单用户应用切片 → `差异化承载：True`，`应用策略：assurance-app-slice`

---

## 样例 3 — 场景 3：区域性 PON 拥塞（Insight 回流）

**输入画像（含 insight 摘要）**:
```json
{
  "scope_indicator": "regional",
  "peak_time_window": "19:00-22:00",
  "priority_pons": ["PON-2/0/5", "PON-1/0/3"],
  "distinct_issues": ["带宽利用率过高", "丢包率超标"],
  "has_complaints": true
}
```

**产出方案**（稀疏方案，只启用差异化承载）:

```text
AP补点推荐：
# 跳过原因: 区域性 PON 拥塞，与单用户 WIFI 覆盖无关
    WIFI信号仿真：False
    应用卡顿仿真：False
    AP补点推荐：False

CEI体验感知：
# 跳过原因: 已通过区域性数据洞察定位，无需单用户 CEI 采集
    CEI模型：无
    CEI粒度：分钟级
    CEI阈值：无

故障诊断：
# 跳过原因: 已确认为拥塞问题，非设备故障
    诊断场景：无
    偶发卡顿定界：False

远程优化：
# 跳过原因: 区域性拥塞需容量扩展，远程闭环无法解决
    远程优化触发时间：无
    远程WIFI信道切换：False
    远程网关重启：False
    远程WIFI功率调优：False

差异化承载：
    差异化承载：True
    应用类型：直播
    保障应用：抖音
    业务类型：limit-speed-1m
```

**关键业务规则体现**:
- 区域性 PON 拥塞 → 仅启用差异化承载段（`差异化承载：True`），其余四段全部 False
- PON 拥塞整形场景 → `APP Flow：True`（流量成型），`应用策略：limit-speed-1m`
- 其余三段均写 `# 跳过原因:` 注释说明

---

## 样例 4 — 场景 2 变体：WIFI 覆盖弱（Insight 回流）

**输入画像（含 insight 摘要）**:
```json
{
  "scope_indicator": "single_user",
  "issue_type": "wifi_coverage",
  "complaint_keyword": "信号弱",
  "guarantee_target": "家庭级"
}
```

**产出方案**（仅 AP补点推荐启用）:

```text
AP补点推荐：
    WIFI信号仿真：True
    应用卡顿仿真：True
    AP补点推荐：True

CEI体验感知：
# 跳过原因: 用户仅关注 WIFI 覆盖问题
    CEI模型：无
    CEI粒度：分钟级
    CEI阈值：无

故障诊断：
# 跳过原因: 用户仅关注 WIFI 覆盖问题
    诊断场景：无
    偶发卡顿定界：False

远程优化：
# 跳过原因: 用户仅关注 WIFI 覆盖问题
    远程优化触发时间：无
    远程WIFI信道切换：False
    远程网关重启：False
    远程WIFI功率调优：False

差异化承载：
# 跳过原因: 用户仅关注 WIFI 覆盖问题
    差异化承载：False
    应用类型：直播
    保障应用：抖音
    业务类型：limit-speed-1m
```

---

## 常见错误避免

1. **使用旧的 `## 段落标题` + `**启用**: true/false` 格式** → 已废弃，Orchestrator 无法识别
2. **子字段缩进不正确**（未用 4 空格）→ Orchestrator 段落切分异常
3. **禁用段不写 `# 跳过原因`** → 用户体验差，可追溯性差
4. **区域性问题也全部启用**（如 PON 拥塞还做 CEI 单点采集）→ 违反稀疏方案原则
5. **CEI模型字段直接写 CSV 权重**（如 `ServiceQualityWeight:40,...`）→ 应写模型名（如 `直播模型`），由 Provisioning 层查预设表翻译
