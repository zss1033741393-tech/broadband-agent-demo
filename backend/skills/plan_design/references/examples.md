# Plan Design Few-Shot 样例

以下样例覆盖场景 1（完整方案）× 2、场景 2（区域稀疏方案）、场景 2 变体（WIFI 覆盖弱）。  
每个样例均附 **决策链路**，标注每个方案字段的推导来源，LLM 生成时须按相同路径推导，不得跳过。

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
# 跳过原因: 楼宇直播为固定有线场地，无 WIFI 覆盖问题
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

**决策链路**:
- `scenario=楼宇直播（固定有线场地）` → 无 WIFI 覆盖问题 → `AP补点推荐全 False`（写跳过原因）
- `package_type=直播套餐` → §套餐/场景→CEI模型选择 → `CEI模型: 直播模型`
- `complaint_history=false ∧ 直播场景` → §CEI阈值参考"直播/专线场景 80 分" → `CEI阈值: 80分`
- `guarantee_app=快手 ∧ 直播套餐` → §套餐/关键词→诊断场景"保障应用含直播类" → `诊断场景: 直播卡顿`
- `scenario=楼宇直播（有线连接，忌干扰）` → §整改动作组合"楼宇直播" → `远程网关重启: True, 信道切换: False, 功率调优: False`
- `package_type=直播套餐` → §触发时间选择"直播套餐→闲时" → `远程优化触发时间: 闲时`
- `guarantee_target=应用级 ∧ scenario=楼宇直播（有线连接）` → §差异化承载→业务类型"有线连接·PON 管道保障" → `差异化承载: True, 业务类型: app-flow`

---

## 样例 2 — 场景 1：直播套餐卖场走播保抖音

**输入画像**:
```json
{
  "user_type": "主播用户",
  "package_type": "直播套餐",
  "scenario": "卖场走播",
  "guarantee_target": "应用级",
  "time_window": "全天",
  "guarantee_app": "抖音",
  "complaint_history": true
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

**决策链路**:
- `scenario=卖场走播（无线移动，WIFI 覆盖不均）` → §启用决策规则-1"默认 AP补点按需" → 走动场景需全场覆盖 → `AP补点推荐三项全 True`
- `package_type=直播套餐` → §套餐/场景→CEI模型选择 → `CEI模型: 直播模型`
- `complaint_history=true ∧ 直播场景` → §CEI阈值参考"投诉处置建议 85 分" → `CEI阈值: 85分`
- `guarantee_app=抖音 ∧ 直播套餐` → §套餐/关键词→诊断场景"保障应用含直播类" → `诊断场景: 直播卡顿`
- `scenario=卖场走播（走动业务，忌重启）` → §整改动作组合"卖场走播" → `远程网关重启: False, 信道切换: True, 功率调优: True`
- `package_type=直播套餐` → §触发时间选择"直播套餐→闲时" → `远程优化触发时间: 闲时`
- `scenario=卖场走播（WiFi 连接移动场景）` → §差异化承载→业务类型"单用户 WIFI 应用切片" → `差异化承载: True, 业务类型: assurance-app-slice`

---

## 样例 3 — 场景 2：区域性 PON 拥塞（Insight 回流）

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
    CEI粒度：无
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
    应用类型：无
    保障应用：无
    业务类型：limit-speed-1m
```

**决策链路**:
- `scope_indicator=regional` → §启用决策规则-2 → 进入区域性稀疏方案逻辑
- `distinct_issues=[带宽利用率过高, 丢包率超标]` → §启用决策规则-2"PON 拥塞/应用流量集中" → `仅启用差异化承载`，其余 4 段全部跳过
- `regional PON 拥塞（无单一保障应用）` → 无 `guarantee_app` 字段 → `应用类型: 无, 保障应用: 无`
- `PON 拥塞整形场景` → §差异化承载→业务类型"区域性 PON 拥塞整形" → `差异化承载: True, 业务类型: limit-speed-1m`
- 禁用的 4 段各写 `# 跳过原因:` 注释，子字段全部写 `False` 或 `无`

---

## 样例 4 — 场景 2 变体：WIFI 覆盖弱（单用户，Insight 回流）

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
# 跳过原因: issue_type=wifi_coverage 触发特判，用户仅关注 WIFI 覆盖问题
    CEI模型：无
    CEI粒度：无
    CEI阈值：无

故障诊断：
# 跳过原因: issue_type=wifi_coverage 触发特判，WIFI 覆盖问题无需故障树诊断
    诊断场景：无
    偶发卡顿定界：False

远程优化：
# 跳过原因: issue_type=wifi_coverage 触发特判，覆盖弱靠 AP 补点解决，远程闭环无法改善
    远程优化触发时间：无
    远程WIFI信道切换：False
    远程网关重启：False
    远程WIFI功率调优：False

差异化承载：
# 跳过原因: issue_type=wifi_coverage 触发特判，无需差异化管道保障
    差异化承载：False
    应用类型：无
    保障应用：无
    业务类型：无
```

**决策链路**:
- `scope_indicator=single_user ∧ issue_type=wifi_coverage` → §启用决策规则-1"WIFI 覆盖弱特判（优先级高于默认规则）" → **覆盖默认 3 段启用规则**
- `issue_type=wifi_coverage` → 仅启用 AP补点推荐 → `WIFI信号仿真/应用卡顿仿真/AP补点推荐 全 True`
- 其余 4 段全部触发特判跳过，各写 `# 跳过原因:` + 子字段全写 `False` 或 `无`
- `差异化承载：False` → 禁用段规范 → `应用类型: 无, 保障应用: 无, 业务类型: 无`（**禁止填真实业务值**）

---

## 场景 → 段落启用速查矩阵

生成方案前对照此矩阵做快速自检，所有字段推导完成后再写输出。

| 场景标签 | AP补点 | CEI体验感知 | 故障诊断 | 远程优化组合 | 差异化承载 / 业务类型 |
|---|---|---|---|---|---|
| 直播套餐·楼宇直播（有线固定） | ✗ 全 False | ✓ 直播模型·80分 | ✓ 直播卡顿·偶发 True | 仅网关重启·闲时 | ✓ `app-flow` |
| 直播套餐·卖场走播（WiFi 移动） | ✓ 三项全 True | ✓ 直播模型·80/85分 | ✓ 直播卡顿·偶发 True | 信道+功率·闲时 | ✓ `assurance-app-slice` |
| 普通套餐·家庭直播（WiFi 固定） | 按信号强度判断 | ✓ 直播模型·70分 | ✓ 直播卡顿 | 全开·定时 | 按保障应用判断 |
| 游戏用户（有线/WiFi） | ✗ | ✓ 游戏模型·70分 | ✓ 游戏卡顿 | 全开·定时 | 按需 |
| 区域·PON 拥塞（regional） | ✗ | ✗ | ✗ | ✗ | ✓ `limit-speed-1m` |
| 单用户·WIFI 覆盖弱（特判） | ✓ 三项全 True | ✗ 特判覆盖 | ✗ 特判覆盖 | ✗ 特判覆盖 | ✗ 特判覆盖 |

> 矩阵只列典型场景；具体字段值（CEI阈值、诊断场景枚举、触发时间）以 SKILL.md §业务默认值速查 为准。
