"""NL2Code 沙箱执行模块。

从 `ce-insight-2.0/pipeline/executor.py::_execute_nl2code` 抽出的纯执行部分，
**不含** LLM 代码生成调用 — 代码由上游（InsightAgent）生成后传入本模块执行。

安全措施（相比 ce-insight-2.0 原版有所收紧）：
- 禁用 `open` / `__import__` / `exec` / `eval` / `compile` / `input` / `exit` / `quit`
- 禁止 `import` 语句（通过预编译 AST 检查）
- 禁止 `from X import Y`（同上）
- 禁止访问 `__builtins__` / `__globals__` / `__subclasses__` 等魔术属性（AST 检查）
- 执行环境仅注入 `df` / `pd` / `np` / 受限 builtins
- 结果必须赋值给 `result` 变量，否则返回 None
"""

from __future__ import annotations

import ast
import builtins as _builtins_module
from typing import Any

import numpy as np
import pandas as pd

# 禁用的 builtins 名称（即便走 AST 检查也做第二道防线）
_FORBIDDEN_BUILTINS: set[str] = {
    "open",
    "exec",
    "eval",
    "compile",
    "__import__",
    "input",
    "exit",
    "quit",
    "help",
    "globals",
    "locals",
    "vars",
    "breakpoint",
}

# 禁用的属性名（AST 检查时阻断）
_FORBIDDEN_ATTRS: set[str] = {
    "__class__",
    "__bases__",
    "__subclasses__",
    "__mro__",
    "__globals__",
    "__builtins__",
    "__import__",
    "__loader__",
    "__code__",
    "__closure__",
    "__dict__",
}


class NL2CodeError(Exception):
    """NL2Code 沙箱执行或校验失败。"""


def _build_safe_builtins() -> dict[str, Any]:
    """构造白名单 builtins：移除危险符号后的 builtins 字典。"""
    safe: dict[str, Any] = {}
    for name in dir(_builtins_module):
        if name.startswith("_"):
            continue
        if name in _FORBIDDEN_BUILTINS:
            continue
        safe[name] = getattr(_builtins_module, name)
    return safe


def _validate_ast(code: str) -> None:
    """AST 级静态检查：禁止 import / 禁止访问魔术属性 / 禁止调用危险 builtins。

    失败时抛 NL2CodeError。
    """
    try:
        tree = ast.parse(code, filename="<nl2code>", mode="exec")
    except SyntaxError as exc:
        raise NL2CodeError(f"SyntaxError: {exc}") from exc

    for node in ast.walk(tree):
        # 1. 禁止 import / from import
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise NL2CodeError(f"禁止 import 语句（line {getattr(node, 'lineno', '?')}）")
        # 2. 禁止访问魔术属性
        if isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_ATTRS:
            raise NL2CodeError(
                f"禁止访问魔术属性 `{node.attr}`（line {getattr(node, 'lineno', '?')}）"
            )
        # 3. 禁止直接调用危险 builtins（即使被重命名也会被下面 exec 时的 __builtins__ 拦截）
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_BUILTINS:
            raise NL2CodeError(f"禁止使用 `{node.id}`（line {getattr(node, 'lineno', '?')}）")


def run_nl2code(
    code: str,
    df: pd.DataFrame,
    *,
    extra_context: dict[str, Any] | None = None,
) -> Any:
    """在受限沙箱中执行 NL2Code 片段，返回 `result` 变量的值。

    Args:
        code: 待执行的 Python 代码字符串；必须把输出赋值给 `result`。
        df: 已通过三元组查询得到的 DataFrame，作为 `df` 注入沙箱。
        extra_context: 额外注入的只读对象（如 `found_entities` 等），不建议滥用。

    Returns:
        沙箱中 `result` 变量的最终值。若未赋值返回 None。

    Raises:
        NL2CodeError: AST 校验失败、语法错误或运行时异常。
    """
    _validate_ast(code)

    safe_builtins = _build_safe_builtins()
    exec_env: dict[str, Any] = {
        "__builtins__": safe_builtins,
        "df": df,
        "pd": pd,
        "np": np,
    }
    if extra_context:
        for k, v in extra_context.items():
            if k in {"df", "pd", "np", "__builtins__"}:
                continue
            exec_env[k] = v

    try:
        exec(code, exec_env, exec_env)  # noqa: S102 — 已通过 AST 校验
    except Exception as exc:
        raise NL2CodeError(f"{type(exc).__name__}: {exc}") from exc

    return exec_env.get("result")


def summarize_nl2code_result(result: Any, max_len: int = 500) -> dict[str, Any]:
    """把 NL2Code 的返回值转成可 JSON 序列化的摘要。

    - DataFrame → {"type": "dataframe", "shape": ..., "records": [...]}
    - dict → {"type": "dict", "value": ...}
    - 其他 → {"type": "scalar", "text": str(result)[:max_len]}
    """
    if isinstance(result, pd.DataFrame):
        try:
            records = result.head(20).to_dict(orient="records")
        except Exception:
            records = []
        return {
            "type": "dataframe",
            "shape": list(result.shape),
            "columns": list(result.columns),
            "records": records,
        }
    if isinstance(result, dict):
        return {"type": "dict", "value": result}
    if isinstance(result, (list, tuple)):
        return {"type": "list", "value": list(result)[:50]}
    if result is None:
        return {"type": "none"}
    return {"type": "scalar", "text": str(result)[:max_len]}
