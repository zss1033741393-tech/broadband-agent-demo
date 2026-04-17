## sse流中新增的report事件



{
    "event": "report",
    "data": {
      "renderType": "insight",
      "renderData": {
        "charts": [
          {
            "chartId": "insight_insight_query_308226",
            "title": "bipHighCnt 最大值分析 (Top10)",
            "conclusion": "bipHighCnt 最大值出现在 000debc0-38b6-4c37-b66a-867989343fe7（0.00），高出第二名 0.00，z-score=0.00",
            "echartsOption": {
              "chart_type": "bar",
              "title": {
                "text": "bipHighCnt 最大值分析 (Top10)",
                "left": "center",
                "textStyle": {
                  "fontSize": 13,
                  "color": "#4a4a4a",
                  "fontWeight": 600
                }
              },
              "tooltip": {
                "trigger": "axis",
                "confine": true,
                "textStyle": {
                  "fontSize": 11
                }
              },
              "grid": {
                "left": "10%",
                "right": "6%",
                "bottom": "14%",
                "top": "16%",
                "containLabel": false
              },
              "xAxis": {
                "type": "category",
                "data": [
                  "000debc0-3...",
                  "001890f6-5...",
                  "001f9205-2...",
                  "00216504-6...",
                  "00352159-1...",
                  "003a610f-c...",
                  "00444d80-6...",
                  "0046519a-a...",
                  "004b2f57-7...",
                  "006ca84e-1..."
                ],
                "axisLabel": {
                  "fontSize": 10,
                  "rotate": 30
                }
              },
              "yAxis": {
                "type": "value",
                "name": "bipHighCnt",
                "nameTextStyle": {
                  "fontSize": 11
                }
              },
              "series": [
                {
                  "type": "bar",
                  "data": [
                    {
                      "value": 0,
                      "itemStyle": {
                        "color": "#e76f6f"
                      }
                    },
                    {
                      "value": 0,
                      "itemStyle": {
                        "color": "#7eb8da"
                      }
                    },
                    {
                      "value": 0,
                      "itemStyle": {
                        "color": "#7eb8da"
                      }
                    },
                    {
                      "value": 0,
                      "itemStyle": {
                        "color": "#7eb8da"
                      }
                    },
                    {
                      "value": 0,
                      "itemStyle": {
                        "color": "#7eb8da"
                      }
                    },
                    {
                      "value": 0,
                      "itemStyle": {
                        "color": "#7eb8da"
                      }
                    },
                    {
                      "value": 0,
                      "itemStyle": {
                        "color": "#7eb8da"
                      }
                    },
                    {
                      "value": 0,
                      "itemStyle": {
                        "color": "#7eb8da"
                      }
                    },
                    {
                      "value": 0,
                      "itemStyle": {
                        "color": "#7eb8da"
                      }
                    },
                    {
                      "value": 0,
                      "itemStyle": {
                        "color": "#7eb8da"
                      }
                    }
                  ],
                  "barMaxWidth": 40
                }
              ]
            },
            "phaseId": 3,
            "stepId": 2,
            "phaseName": "L3-细化根因指标",
            "stepName": "找出 bipHighCnt 最高的 PON 口"
          }
        ],
        "markdownReport": ""
      }
    }
  },


  {
    "event": "report",
    "data": {
      "renderType": "insight",
      "renderData": {
        "charts": [],
        "markdownReport": "\n# 网络质量数据洞察报告\n\n**生成时间**: 2026-04-14 18:59:59\n\n**分析目标**: 找出 CEI 分数较低的 PON 口并分析根因\n\n\n---\n\n\n## 摘要\n\n| 项目 | 值 |\n|---|---|\n| 问题 PON 口 | 288b6c71-c94e-4ac5-b3ed-c0d836f90b4f, 1c86d285-726d-47e5-a7cd-62d884e0c977, 5924e7b6-6a39-47da-8f7c-b4845f3d2143, 2862f00d-727b-4470-9876-1e0d1fb4c21a, d4789fba-bb9f-4c76-8cc8-9c92f8028680 |\n| 问题网关 | 无 |\n| 异常类型 | OLT 接收光功率异常 (oltRxPowerHighCnt 高达 94.5 次)、ODN 维度得分为 0（12 个 PON 口）、晚间 19:00-22:00 光功率异常加剧 |\n| 波及范围 | multi_pon |\n| 高峰时段 | 19:00-22:00 |\n| 是否含投诉 | 否 |\n| 根因字段 | oltRxPowerHighCnt, oltRxPowerHigh |\n| 建议远程闭环 | 无 |\n\n\n\n\n## 分析路径\n\n\n\n---\n\n### Phase 1 — L1-定位低分 PON 口\n\n**里程碑**: 识别 CEI_score 最低的 Top N 个 PON 口\n\n\n\n\n#### 执行步骤\n\n\n**Step 1 · OutstandingMin** (显著性: 1.00)\n\n\n\n- CEI_score 最小值出现在 288b6c71-c94e-4ac5-b3ed-c0d836f90b4f（54.08），低于第二名 1.34，z-score=5.36\n\n\n\n\n- *命中实体*: portUuid=[288b6c71-c94e-4ac5-b3ed-c0d836f90b4f, 1c86d285-726d-47e5-a7cd-62d884e0c977, 5924e7b6-6a39-47da-8f7c-b4845f3d2143, 2862f00d-727b-4470-9876-1e0d1fb4c21a, d4789fba-bb9f-4c76-8cc8-9c92f8028680, 5eb17fbc-2211-4190-a84a-c8e644020dcd, 30a759af-bab8-4521-b2bb-c4b5222d970d, 2dbb2abd-8b6c-40be-95ef-667ba38bd8b6, 1377e84d-7bb7-4d4b-9be0-f03b11aa2437, 52eee838-1914-49c9-9f0d-f9cb1b06bfa4]\n\n\n\n\n\n\n\n\n#### 反思\n**决策**: A — 成功识别 10 个低分 PON 口\n\n\n\n\n---\n\n### Phase 2 — L2-分维度归因\n\n**里程碑**: 确定哪个维度是主要拖分因素\n\n\n\n\n#### 执行步骤\n\n\n**Step 1 · OutstandingMin** (显著性: 1.00)\n\n\n\n- ODN_score 最小值出现在 ed1ffa4d-180f-4ae9-815d-93fea4b79a5b（0.00），发现 12 个 PON 口 ODN_score 为 0\n\n\n\n\n- *命中实体*: portUuid=[ed1ffa4d-180f-4ae9-815d-93fea4b79a5b, d6ed5949-9c5b-42fa-a481-5ff3cc5a0660, cd4af175-deae-4103-a901-9a070d9c1718, 8812629e-01e4-4766-a138-93d3762285c6, 9a22f060-77da-4cc5-a9ed-feaa90ed93c2]\n\n\n\n\n\n\n\n\n#### 反思\n**决策**: A — 确认 ODN 维度是主要拖分因素\n\n\n\n\n---\n\n### Phase 3 — L3-细化根因指标\n\n**里程碑**: 定位 ODN 维度内的具体根因字段\n\n\n\n\n#### 执行步骤\n\n\n**Step 1 · OutstandingMax** (显著性: 1.00)\n\n\n\n- oltRxPowerHighCnt 最大值出现在 72d69aa6-5f36-4e95-961f-501b29e49230（94.50），z-score=18.03\n\n\n\n\n- *命中实体*: portUuid=[72d69aa6-5f36-4e95-961f-501b29e49230, ed1ffa4d-180f-4ae9-815d-93fea4b79a5b, 8640b6fe-1050-4ce1-b4c2-605d41145a72, d6ed5949-9c5b-42fa-a481-5ff3cc5a0660, 9a22f060-77da-4cc5-a9ed-feaa90ed93c2]\n\n\n\n\n\n\n\n\n#### 反思\n**决策**: A — 确认 oltRxPowerHighCnt 是核心根因\n\n\n\n\n---\n\n### Phase 4 — L4-分钟表时序验证\n\n**里程碑**: 验证根因指标的时序分布\n\n\n\n\n#### 执行步骤\n\n\n**Step 1 · Trend** (显著性: 0.40)\n\n\n\n- oltRxPowerHigh 呈上升趋势，R?=0.3994，光功率异常在晚间时段开始增多\n\n\n\n\n- *命中实体*: time_id=[2025-04-10 16:00:00, 2025-04-10 17:15:00, 2025-04-10 17:30:00, 2025-04-10 17:45:00, 2025-04-10 18:00:00]\n\n\n\n\n\n\n\n\n#### 反思\n**决策**: A — 完成时序验证\n\n\n\n\n\n\n\n---\n\n*此报告由家宽网络调优智能助手自动生成*\n\n"
      }
    }
  },


新增了一个事件叫做report，是用于生成最终报告的，会顺序先生成n个chart图表配置，并且包含phraseId和stepId，最后会生成一个markdownReport不为空的报告markdown部分。
现在你需要实现这个功能-依据markdown中的占位符把图表插进去，最后生成一个图文并貌的报告！

之后的markdown中会插入这种格式的占位符：[CHART:p1s1] -- 这代表phraseId=1 stepId=1的图表，你需要从已有的report事件中找到对应图表并且做渲染。
当报告ready后，在首页的左侧qa框中跳出一个生成报告的气泡，点击后会将这个报告呈现在右侧的画布上。
