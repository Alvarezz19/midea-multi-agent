# 规划智能体 (Planning Agent) 工作流总结

## 1. 智能体结构与职责

**Planning Agent** 扮演逻辑控制专家的角色，负责将用户的自然语言需求转化为精确的逻辑控制拓扑图。它位于检索智能体和编码智能体之间，是“大脑”核心。

### 核心组成
*   **LLM 核心**: 使用 LLM（如 DeepSeek, GPT-4）进行逻辑推理和结构化生成。
*   **Pydantic 数据模型**: 定义了严格的输出结构（节点、连接、整体规划），确保生成结果的规范性。
*   **Prompt 工程**: 内置专业的系统提示词，指导 LLM 选择模块、配置参数和建立连接。

---

## 2. 输入与输出

### 输入 (Input)
*   **用户需求 (`user_query`)**: 用户的自然语言描述（来自工作流状态）。
*   **检索上下文 (`retrieval_context`)**: 由检索智能体提供的可用模块列表、参数定义和相关知识。

### 输出 (Output)
*   **执行计划 (`execution_plan`)**: 一个符合 `PlanIR` 结构的字典，包含：
    *   `goal`: 规划目标的简述。
    *   `nodes`: 模块节点列表（ID、类型、参数、理由）。
    *   `connections`: 数据流连接列表（源节点端口 -> 目标节点端口）。

---

## 3. 主要参数

| 参数名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `llm_provider` | `Optional[str]` | 指定 LLM 提供商，默认使用配置文件中的全局设置。 |

---

## 4. 关键函数详解

### 4.1 `__init__(self, llm_provider=None)`
*   **作用**: 初始化智能体。
*   **逻辑**: 获取 LLM 实例，并调用 `_create_planning_prompt` 预加载提示词模板。

### 4.2 `__call__(self, state: Dict) -> Dict`
*   **作用**: LangGraph 的标准调用接口。
*   **输入**: 工作流状态字典 `state`。
*   **输出**: 更新后的 `state`，其中 `state["execution_plan"]` 包含生成的规划结果。
*   **逻辑**: 提取 `user_query` 和 `retrieval_context`，调用 `plan` 方法，并将结果序列化后存入状态。

### 4.3 `plan(self, user_query, retrieval_context) -> PlanIR`
*   **作用**: 核心推理函数，生成中间表示 (IR)。
*   **输入**: 用户文本需求，检索到的原始上下文。
*   **输出**: `PlanIR` 对象（结构化的规划图）。
*   **逻辑**:
    1.  调用 `format_docs_for_planner` 将复杂的检索结果清洗为 LLM 易读的精简列表 (`slim_context`)。
    2.  结合用户需求和 Prompt 模板生成 Prompt。
    3.  调用 LLM 获取 JSON 响应。
    4.  解析 JSON 并转换为 `PlanIR` 对象。
    5.  调用 `plan_ir.validate_ids()` 校验连接关系的合法性。
    6.  错误处理：如果解析失败，返回空的规划对象。

### 4.4 `_create_planning_prompt(self)`
*   **作用**: 构建 System Prompt 和 User Prompt。
*   **逻辑**: 定义了两部分提示词：
    *   **System Prompt**: 设定专家角色，规定输出必须为特定 JSON 格式，列出所有规则（如 0-based 索引、参数类型检查）。
    *   **User Prompt**: 注入用户需求和清洗后的模块列表。

### 4.5 `PlanIR.validate_ids(self)`
*   **作用**: 数据一致性校验。
*   **逻辑**: 遍历所有 `connections`，确保 `from_node` 和 `to_node` 引用的 ID 都在 `nodes` 列表中定义过，防止生成悬空连接。

---

## 5. 数据结构中间表示 (IR)

### `PlanNode`
代表一个模块实例：
*   `logic_id`: 逻辑唯一标识符（如 `avg_temp_calc`）。
*   `module_type`: 对应知识库中的模块类型。
*   `parameters`: 该实例的配置字典。
*   `reasoning`: AI 选择此模块的理由。

### `PlanConnection`
代表一条连线：
*   `from_node` / `from_port_index`: 源头。
*   `to_node` / `to_port_index`: 目标。

### `PlanIR`
整体规划对象，聚合了 Nodes 和 Connections。
