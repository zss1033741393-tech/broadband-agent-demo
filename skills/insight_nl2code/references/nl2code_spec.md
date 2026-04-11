# NL2Code 沙箱规范

当现有 12 种洞察函数无法满足需求时，InsightAgent **直接写出** Python 代码，
通过 `run_nl2code.py` 脚本在受限沙箱中执行。

## 触发场景

- **Top N / Bottom N**：`df.nsmallest(3, "CEI_score")` / `df.nlargest(5, "bipHighCnt")`
- **自定义排序 / 多字段复合排序**
- **字段派生 / 分类逻辑**：`df["is_abnormal"] = df.CEI_score < 60`
- **简单聚合**：`result = df.groupby("olt").CEI_score.mean().sort_values()`
- **一步输出确定结果**的查询 — 不要拼凑多个洞察函数绕弯

## 代码约束

1. **结果必须赋值给 `result` 变量**（沙箱只读取 `result`）
2. **可用对象**：
   - `df` — 通过三元组查询得到的 DataFrame
   - `pd` — pandas
   - `np` — numpy
   - 受限 builtins（`len` / `max` / `min` / `sorted` / `sum` / `print` / `range` / `zip` / `enumerate` / `list` / `dict` / `set` / `tuple` / `str` / `int` / `float` / `bool` / `abs` / `round` / `map` / `filter` / ...）
3. **禁止**：
   - `import` / `from X import Y` 语句（AST 级阻断）
   - 直接调用 `open` / `exec` / `eval` / `compile` / `__import__` / `input` / `globals` / `locals` / `vars`（AST + builtins 双重阻断）
   - 访问魔术属性：`__class__` / `__bases__` / `__subclasses__` / `__globals__` / `__builtins__` / `__code__` / `__dict__` 等
   - 文件 IO、网络请求、子进程调用
4. **字符串引号**：
   - 🔴 **禁止三引号**（`"""..."""` / `'''...'''`）— LLM 经常少写引号导致 SyntaxError
   - 使用单行字符串 `'xxx'` / `"xxx"`，成对出现
5. **代码内嵌数据**：如果要在代码里放三元组 / JSON，直接用 Python dict 字面量，**不要**用字符串解析

## 结果类型

脚本会按以下规则序列化 `result`：
- **DataFrame** → `{"type": "dataframe", "shape": [N, M], "columns": [...], "records": [...前 20 行...]}`
- **dict** → `{"type": "dict", "value": {...}}`
- **list / tuple** → `{"type": "list", "value": [...前 50 项...]}`
- **标量 / None** → `{"type": "scalar", "text": "..."}`  / `{"type": "none"}`

## 正确示例

### Top 3 最低 CEI_score
```python
result = df.nsmallest(3, "CEI_score")[["portUuid", "CEI_score"]]
```

### 综合打分
```python
df["composite"] = df["CEI_score"] * 0.6 + df["Stability_score"] * 0.4
result = df.nsmallest(5, "composite")[["portUuid", "CEI_score", "Stability_score", "composite"]]
```

### 异常分组计数
```python
abnormal = df[df["CEI_score"] < 60]
result = {
    "total_abnormal": len(abnormal),
    "by_olt": abnormal.groupby("olt_name").size().to_dict(),
}
```

## 错误示例（禁止）

```python
# 🔴 禁止 import
import os
result = os.listdir(".")

# 🔴 禁止三引号
result = """多行字符串"""

# 🔴 禁止 open
result = open("/etc/passwd").read()

# 🔴 禁止魔术属性（逃逸尝试）
result = [].__class__.__bases__[0].__subclasses__()

# 🔴 未赋值 result
df.nsmallest(3, "CEI_score")  # result 未定义 → 返回 None
```

## 异常处理

脚本返回：
- **成功** → `{"status": "ok", "result": <serialized>, "description": "...", "row_count": N}`
- **失败** → `{"status": "error", "error": "NL2CodeError: 禁止 import 语句（line 1）", "code": "<原代码>"}`

InsightAgent 收到 `status=error` 时应重新生成代码，**最多重试 1 次**，避免死循环。
