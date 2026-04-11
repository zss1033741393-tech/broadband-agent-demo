# ce_insight_core

从 `ce-insight-2.0` 抽取的无状态计算内核，供 `broadband-agent` 的 `skills/data_insight/`
作为轻量 Python 依赖引用。**不包含** LLM 编排层（planner / decomposer / reflector），
那些职责上移到 agno 的 `InsightAgent` + `prompts/insight.md`。

## 公共 API

```python
from ce_insight_core import (
    query_subject_pandas,     # 三元组查询 → list[DataFrame]
    summarize_dataframe,       # DataFrame → 文字摘要
    fix_query_config,          # 三元组修复 + 警告
    run_insight,               # 12 种洞察策略统一入口
    list_insight_types,        # 可用洞察类型
    get_day_schema,            # 天表 Schema
    get_pruned_schema,         # 天表剪枝 Schema (按 focus_dimensions)
    get_minute_schema,         # 分钟表 Schema
    get_minute_fields_for_dimension,
    run_nl2code,               # NL2Code 沙箱执行
    NL2CodeError,              # 沙箱异常
)
```

## 安装

```bash
pip install -e vendor/ce_insight_core
```

## 依赖

- pandas ≥ 2.0
- numpy ≥ 1.24
- scipy ≥ 1.10
- scikit-learn ≥ 1.3
- pydantic ≥ 2.0
