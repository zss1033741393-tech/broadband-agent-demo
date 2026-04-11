# Skills 开发规范

> 遵循 [Google ADK Agent Skill Design Patterns](https://lavinigam.com/posts/adk-skill-design-patterns/)  
> 参考实现：[lavinigam-gcp/build-with-adk](https://github.com/lavinigam-gcp/build-with-adk/tree/main/adk-skill-design-patterns)

本文档定义 Skill 设计的通用规范，**不绑定**任何具体业务 Skill。开发新 Skill 或重构既有 Skill 时，应先匹配范式，再按本规范组织目录、撰写 SKILL.md。

## 1. 五大范式（ADK Skill Design Patterns）

每个 Skill 必须对应以下范式之一（或显式声明为多范式组合），并在 SKILL.md frontmatter 后的 Metadata 中声明 `paradigm` 字段。

### 1.1 Tool Wrapper（工具封装）

- **解决问题**：为 Agent 注入特定库/API 的最佳实践与调用约定，避免在系统提示中硬编码框架知识
- **典型结构**：`references/` 存放 API 速查、约定文档；`scripts/` 可选存放轻量调用脚本
- **指令风格**：以"何时应该使用 X 库的某个特性"、"调用 Y API 的正确顺序"为主
- **何时使用**：需要 Agent 一致性地解释或强制执行某个框架/库的专属规范时

### 1.2 Generator（结构化生成器）

- **解决问题**：保证生成内容的结构、字段、格式可复现，避免每次输出风格漂移
- **典型结构**：`references/` 存放模板（Jinja2/Markdown 等）和风格指南；`scripts/` 存放渲染脚本
- **指令风格**：项目经理式 — "加载模板 → 收集变量 → 渲染 → 原样输出"
- **何时使用**：输出需要稳定结构（报告、配置文件、规范文档、API 契约）

### 1.3 Reviewer（清单评审器）

- **解决问题**：将"检查什么"与"如何检查"分离，输出按严重性分级的评分报告
- **典型结构**：`references/` 存放评审清单（checklist）；`scripts/` 可选存放自动化检查脚本
- **指令风格**：清单驱动 — "对每一项，给出 PASS/WARN/FAIL + 证据 + 建议修复"
- **何时使用**：需要按既定标准系统性评估制品（代码评审、配置合规、SLA 校验）

### 1.4 Inversion（反向访谈器）

- **解决问题**：在用户描述模糊时，由 Agent 主导追问，先收集完整上下文再行动
- **典型结构**：`references/` 存放问题清单与决策树；`scripts/` 存放状态机/槽位引擎
- **指令风格**：强制门控 — "**所有必填项收集完成前，禁止开始执行**"
- **何时使用**：用户输入质量严重影响产出质量，且决策不能在缺少关键信息时做出

### 1.5 Pipeline（流水线）

- **解决问题**：编排多步骤工作流，每一步有明确的输入/输出和质量门控
- **典型结构**：`references/` 存放各阶段的契约/校验规则；`scripts/` 存放各阶段处理脚本；通常组合调用其他 Skill
- **指令风格**：阶段化 + 门控 — "完成步骤 N 并通过校验前，禁止进入步骤 N+1"
- **何时使用**：复杂任务需要顺序执行、中间校验、阶段间数据传递

### 1.6 范式组合

范式可以叠加：Pipeline 中可嵌入 Reviewer 步骤；Generator 可使用 Inversion 收集输入；Tool Wrapper 可作为 Pipeline 的一个引用文件。组合时需在 `paradigm` 字段中声明主范式 + 嵌入的次范式（如 `paradigm: Pipeline + Reviewer`）。

## 2. Agno LocalSkills 目录约定

agno 的 `LocalSkills` 加载器只扫描固定子目录，目录名必须严格匹配：

```
skill_name/
├── SKILL.md          # 必须：YAML frontmatter + Markdown 指令体
├── scripts/          # 可选：可执行脚本（agno 扫描 → available_scripts）
└── references/       # 可选：参考文件（模板、清单、Schema、示例等）
                      #         agno 扫描 → available_references
```

**关键约束**：

- `templates/` / `assets/` / `prompts/` 等目录名 **不被** agno 扫描 → 资源统一放入 `references/`
- Skill 顶层散落文件（如裸放的 `.yaml` / `.json`）**对 LLM 不可见** → 必须放入 `references/`
- `scripts/` 中的文件名通过 `available_scripts` 字段暴露给 LLM
- `references/` 中的文件名通过 `available_references` 字段暴露给 LLM
- 无 `SKILL.md` 的目录不被 LocalSkills 识别，属无效目录

## 3. SKILL.md 编写规范

### 3.1 标准模板

```markdown
---
name: skill_name
description: "一句话描述（L1 元数据，~100 token，Agent 启动时常驻加载）"
---

# Skill 标题

## Metadata
- **paradigm**: 范式名称（必填，如 Generator / Pipeline + Reviewer）
- **when_to_use**: 触发条件（一句话）
- **inputs**: 输入数据类型 / 来源
- **outputs**: 输出数据类型 / 形式

## When to Use
- ✅ 适用场景（具体可识别的特征）
- ❌ 不适用场景（避免误触发）

## How to Use
（具体调用步骤；LLM 在决定使用该 Skill 时通过 get_skill_instructions 加载，即 L2）

## Scripts
- `scripts/<file>` — 用途说明

## References
- `references/<file>` — 用途说明

## Examples
（输入/输出示例，至少一组）
```

### 3.2 调用 `get_skill_script` 的强制规范

凡 How to Use 中涉及脚本调用，**必须**：

1. 显式写出完整调用形式 `get_skill_script(skill_name, script_path, execute=True, args=[...])`
2. `args` 必须为 `List[str]` 字面量，每个元素对应一个 CLI 参数  
   - 正确：`args=["--insight", "<json_string>"]`、`args=["<json_string>"]`  
   - 错误：`args="--insight <json>"`（字符串）、`args="<json>"`（字符串）
3. 占位符需用清晰的语义命名（如 `<profile_json_string>`、`<user_input>`），避免 LLM 误解为字面量

### 3.3 范式特化要求

| 范式 | SKILL.md 必须包含 |
|---|---|
| **Tool Wrapper** | 列出所封装库/API 的版本范围；声明哪些 reference 文件在哪些情境下加载 |
| **Generator** | 明确声明"脚本 `stdout` 即最终产物，Agent 须原样输出，禁止二次改写"；列出模板字段与默认值 |
| **Reviewer** | 评分维度与严重性分级定义；输出 JSON Schema 或 Markdown 结构示例 |
| **Inversion** | 必填字段清单与依赖关系；门控规则（"未完成时禁止继续"） |
| **Pipeline** | 各阶段的输入/输出契约；阶段间的传递格式；门控点 |

## 4. 渐进式披露（Progressive Disclosure）

| 层级 | 加载时机 | 内容 | 估算开销 |
|---|---|---|---|
| **L1** | Agent 启动时常驻 | SKILL.md frontmatter（`name` + `description`） | ~100 token / Skill |
| **L2** | LLM 决定使用该 Skill 时 | SKILL.md 正文，通过 `get_skill_instructions` 加载 | 几百 ~ 数千 token |
| **L3** | 脚本运行时按需 | `references/` 文件内容，通过 `get_skill_reference` 加载 | 不计入对话上下文 |

**核心原则**：L1 决定是否触发，L2 决定如何调用，L3 仅在执行中按需展开。任何违反层级的写法（如把详细操作步骤塞进 frontmatter）都会浪费上下文 token。

## 5. 系统提示 vs SKILL.md 职责边界

| 放系统提示（项目级 prompt） | 放 SKILL.md（Skill 级） |
|---|---|
| 协议级通用规则（工具调用顺序、`args` 类型约束、stdout 处理） | Skill 专属的触发条件与调用步骤 |
| 任务类型识别与分流规则 | 当前 Skill 的禁止事项 |
| 跨 Skill 的流程状态机 / 编排约束 | 范式声明与资源列表 |
| 角色定位与输出风格 | 范式特定的输出格式契约 |

> ⚠️ 禁止将某个 Skill 的专属行为写入系统提示 — 违反 Progressive Disclosure 原则，会导致所有任务都付出该 Skill 的 token 开销。

## 6. Skill 开发禁止事项

- ❌ 不在 `skill_name/` 顶层放散落资源文件 → 必须放入 `references/`
- ❌ 不创建 `templates/` / `assets/` / `prompts/` 子目录 → 统一用 `references/`
- ❌ 不在 Skill 脚本中感知 `session_id` 或全局状态 → 持久化由 core 层处理
- ❌ SKILL.md frontmatter 缺少 `paradigm` 字段视为不合规
- ❌ Generator 范式脚本的 stdout 不得被 Agent 二次改写、摘要或重排版
- ❌ 不新增空 Skill 目录（无 SKILL.md 的目录不被 LocalSkills 识别）
- ❌ `args` 不得以字符串形式传递给 `get_skill_script`，必须为 `List[str]`
- ❌ 不在 SKILL.md 中描述其他 Skill 的专属行为（应通过系统提示的编排规则关联）
