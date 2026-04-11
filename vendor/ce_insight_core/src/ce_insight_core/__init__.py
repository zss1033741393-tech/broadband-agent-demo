"""ce_insight_core — CE-Insight 2.0 抽取的无状态计算内核。

从 `ce-insight-2.0/services/` 和 `ce-insight-2.0/cei_query_mock/` 抽取而来，
不含 LLM 编排层。供 `broadband-agent` 的 `skills/data_insight/` 脚本引用。

公共 API 见下方 `__all__`。
"""

from ce_insight_core.sandbox import NL2CodeError, run_nl2code
from ce_insight_core.services.day_schema_manager import (
    get_all_day_fields,
    get_full_day_schema,
    get_pruned_day_schema,
    get_pruned_schema,
)
from ce_insight_core.services.insight_runner import (
    INSIGHT_MAP,
    list_insight_types,
    run_insight,
)
from ce_insight_core.services.minute_schema_manager import (
    get_all_minute_fields,
    get_minute_fields_for_dimension,
    get_minute_schema,
)
from ce_insight_core.services.query_fixer import fix_query_config
from ce_insight_core.services.subject_service import (
    query_subject_pandas,
    summarize_dataframe,
)

__all__ = [
    "query_subject_pandas",
    "summarize_dataframe",
    "fix_query_config",
    "run_insight",
    "list_insight_types",
    "INSIGHT_MAP",
    "get_full_day_schema",
    "get_pruned_schema",
    "get_pruned_day_schema",
    "get_all_day_fields",
    "get_minute_schema",
    "get_minute_fields_for_dimension",
    "get_all_minute_fields",
    "run_nl2code",
    "NL2CodeError",
]

__version__ = "0.1.0"
