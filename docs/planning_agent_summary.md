# 规划智能体 (Planning Agent) 完整工作流程总结

## 1. 概述

**规划智能体 (Planning Agent)** 是 LangGraph 工作流中的第二个节点，位于检索智能体（Retrieval Agent）和编码智能体（Coding Agent）之间。它扮演**工业自动化控制系统逻辑规划专家**的角色，核心职责是：将用户的自然语言需求（如数学公式、控制逻辑描述）转化为**结构化的逻辑控制拓扑图**（中间表示 IR），供下游编码智能体将其翻译为最终的 JSON 组态文件。

### 在工作流中的位置

```
用户需求 → [检索智能体] → [规划智能体] → [编码智能体] → JSON 组态文件
                ↓                ↓                ↓
          retrieval_context   execution_plan   generated_code
```

工作流定义在 `workflow.py` 中，流程为：
```python
workflow.set_entry_point("retrieval")
workflow.add_edge("retrieval", "planning")    # 检索 → 规划
workflow.add_edge("planning", "coding")       # 规划 → 编码
workflow.add_edge("coding", END)              # 编码 → 结束
```

---

## 2. 源文件结构

| 文件 | 职责 |
|------|------|
| `agents/planning_agent.py` | 规划智能体主体实现，包含数据结构定义、LLM 调用、输出校验 |
| `utils/context_formatter.py` | `format_docs_for_planner()` 函数，负责将检索上下文清洗为 LLM 友好的精简文本 |
| `utils/model_manager.py` | `LLMManager` 类，统一管理多种 LLM 提供商的实例化 |
| `config.py` | 全局配置（LLM 提供商、温度、最大 token 数等） |
| `workflow.py` | LangGraph 工作流编排，定义规划智能体的节点注册和边连接 |

---

## 3. 数据结构定义（中间表示 IR）

规划智能体使用 Pydantic 模型定义了三层结构化数据模型，这是规划与编码之间的**协议契约**。

### 3.1 PlanNode（模块节点）

代表逻辑图中的一个模块实例：

| 字段 | 类型 | 说明 |
|------|------|------|
| `logic_id` | `str` | 唯一的逻辑标识符，使用有意义的名称（如 `temp_diff_calc`、`const_4_18`） |
| `module_type` | `str` | 对应知识库中的模块类型（如 `constInput`、`multiply`、`subtract`、`divide`） |
| `parameters` | `Dict[str, Any]` | 该模块实例的配置参数（如 `{"fixedValue": 4.18, "inputs": 3}`） |
| `reasoning` | `str` | LLM 选择此模块的理由说明 |

### 3.2 PlanConnection（连接关系）

代表两个模块之间的一条数据流连线：

| 字段 | 类型 | 说明 |
|------|------|------|
| `from_node` | `str` | 上游节点的 `logic_id` |
| `from_port_index` | `int` | 上游节点的输出端口索引（0-based），通常为 0 |
| `to_node` | `str` | 下游节点的 `logic_id` |
| `to_port_index` | `int` | 下游节点的输入端口索引（0-based） |

### 3.3 PlanIR（整体规划）

聚合所有节点和连接的顶层结构：

| 字段 | 类型 | 说明 |
|------|------|------|
| `goal` | `str` | 对当前计算任务的简述 |
| `nodes` | `List[PlanNode]` | 模块节点列表 |
| `connections` | `List[PlanConnection]` | 模块间的连接关系列表 |

---

## 4. 完整工作流程（详细步骤）

### 4.1 入口：`__call__(self, state)` — LangGraph 节点调用接口

当 LangGraph 执行到 `planning` 节点时，自动调用此方法。

**执行逻辑：**
1. 从工作流状态 `state` 中提取 `user_query`（用户原始需求）和 `retrieval_context`（检索智能体产出的上下文）
2. 调用核心方法 `self.plan(user_query, retrieval_context)` 生成 `PlanIR`
3. 将 `PlanIR` 通过 `.model_dump()` 序列化为字典，写入 `state["execution_plan"]`
4. 更新 `state["current_step"]` 为 `"planning_completed"`
5. 返回更新后的 `state`

### 4.2 初始化：`__init__(self, llm_provider, model)`

在工作流创建时（`create_workflow()` 中 `PlanningAgent()` 被实例化），执行初始化：

1. **获取 LLM 实例**：通过 `LLMManager.get_llm()` 获取指定提供商（DeepSeek / OpenAI / Qwen / GLM / Kimi）的 ChatOpenAI 实例
2. **创建提示词模板**：调用 `_create_planning_prompt()` 预加载 System Prompt 和 User Prompt 模板

### 4.3 核心推理：`plan(self, user_query, retrieval_context)` → PlanIR

这是规划智能体最核心的方法，完整的执行流程如下：

```
┌─────────────────────────────────┐
│ 1. 提取模块白名单               │
│    从 retrieval_context 中提取   │
│    所有有效的 module_type 集合   │
└──────────────┬──────────────────┘
               ↓
┌─────────────────────────────────┐
│ 2. 上下文清洗                    │
│    调用 format_docs_for_planner │
│    生成 slim_context（精简文本） │
└──────────────┬──────────────────┘
               ↓
┌─────────────────────────────────┐
│ 3. 构建 Prompt                   │
│    将 slim_context 和 user_query │
│    注入提示词模板                │
└──────────────┬──────────────────┘
               ↓
┌─────────────────────────────────┐
│ 4. 调用 LLM 生成结构化输出       │
│    主路径: Structured Output     │
│    回退路径: 正则解析 JSON       │
└──────────────┬──────────────────┘
               ↓
┌─────────────────────────────────┐
│ 5. 校验阶段                      │
│    ① validate_ids(): 验证连接    │
│       中的节点ID是否存在         │
│    ② validate_module_types():    │
│       验证模块类型是否在白名单中 │
└──────────────┬──────────────────┘
               ↓
┌─────────────────────────────────┐
│ 6. 返回 PlanIR                   │
│    (校验失败则返回空规划)         │
└─────────────────────────────────┘
```

#### 步骤详解

**① 提取模块白名单**

从检索上下文的 `relevant_nodes` 中提取所有 `module_type`，构建一个 `Set[str]`，用于后续校验 LLM 生成的节点是否使用了合法的模块类型。

```python
self._available_module_types = {
    node.get('module_type')
    for node in retrieval_context.get('relevant_nodes', [])
    if node.get('module_type')
}
# 示例结果: {'constInput', 'multiply', 'subtract', 'divide', 'swInput', ...}
```

**② 上下文清洗（format_docs_for_planner）**

这是"减脂"关键步骤。该函数将检索智能体返回的包含完整 `template_json`、`keywords` 等冗余数据的上下文，精简为 LLM 易读的结构化文本。

清洗策略：
- **保留的信息**：模块名称、`module_type`、分类、功能描述、精简的参数定义（键名/类型/默认值/约束）、端口定义（索引/标签/类型）、使用场景指南
- **剔除的信息**：`template_json`（大块模板）、完整 `keywords` 列表、相似度分数细节
- **附加信息**：检索元数据（查询、匹配数量、平均相似度）、规划建议（基于相似度高低给出策略提示）

清洗后的文本格式示例：
```
知识库检索结果

检索查询: 设计夏季主机负荷模块...
检索统计:
   - 找到模块数: 10
   - 平均相似度: 0.720

相关模块清单:

[1] 常量(常量输入)
    类型: constInput
    分类: 变量模块/常量
    功能: 常数模块输出一个固定的数值...
    参数定义:
       • fixedValue (double, 默认=0): 常量的具体值
    输出端口:
       [0] 输出 (number): 输出参数配置中的数值
    适用场景:
       • 在公式中作为固定系数，如 4.18、3.6 等转换系数
...
```

**③ 构建 Prompt**

提示词分为两部分：

- **System Prompt**：设定角色（工业自动化控制系统逻辑规划专家），明确任务规则：
  - 只能使用可用模块列表中的 `module_type`，严禁虚构
  - 逻辑 ID 需唯一且有意义
  - 端口索引使用 0-based
  - 常量需要检查模块是否支持 `fixedValue` 参数，不支持则实例化 `constInput`
  - 参数键名必须与模块定义完全一致
  - 注意参数类型（integer/number/boolean/string）
  - 指定严格的 JSON 输出格式

- **User Prompt**：注入用户需求文本

**④ 调用 LLM 生成结构化输出**

采用**双路径策略**，确保鲁棒性：

- **主路径 — Structured Output（Function Calling）**：
  ```python
  structured_llm = self.llm.with_structured_output(PlanIR)
  plan_ir = structured_llm.invoke(messages)
  ```
  利用 LLM 的 Function Calling / Tool Calling 能力，直接输出符合 `PlanIR` Pydantic 模型的结构化数据。这是首选方式，解析成功率最高。

- **回退路径 — 正则解析（_fallback_parse）**：
  当 Structured Output 失败时（如某些模型不支持 function calling），回退到普通文本生成 + 正则提取 JSON 的方式：
  ```python
  response = self.llm.invoke(messages)
  content = response.content
  json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
  plan_dict = json.loads(json_str)
  plan_ir = PlanIR(**plan_dict)
  ```

- **兜底处理**：如果两条路径都失败，返回一个空的 `PlanIR(goal="规划失败", nodes=[], connections=[])`。

**⑤ 校验阶段**

对 LLM 生成的 `PlanIR` 进行两层校验：

1. **节点 ID 一致性校验 (`validate_ids()`)**：
   遍历所有 `connections`，确保 `from_node` 和 `to_node` 引用的 `logic_id` 都在 `nodes` 列表中定义过。防止 LLM 生成悬空连接。

2. **模块类型白名单校验 (`validate_module_types()`)**：
   确保所有节点的 `module_type` 都在检索结果提供的合法类型集合中。防止 LLM 虚构不存在的模块类型。

校验失败时返回空的 `PlanIR`，附带错误信息在 `goal` 字段中。

---

## 5. 输入与输出规格

### 5.1 输入（从工作流状态中读取）

| 字段 | 类型 | 来源 | 说明 |
|------|------|------|------|
| `user_query` | `str` | 用户输入 | 用户的自然语言需求描述 |
| `retrieval_context` | `dict` | 检索智能体输出 | 包含检索到的模块列表及其详细定义 |

`retrieval_context` 的关键结构：
```json
{
  "query": "用户原始查询",
  "relevant_nodes": [
    {
      "module_type": "multiply",
      "name": "乘法运算",
      "description": "...",
      "category": "运算模块/数学运算",
      "parameters_schema": { ... },
      "ports_definition": { "inputs": [...], "outputs": [...] },
      "template_json": { ... },
      "keywords": [...],
      "usage_guides": [...],
      "similarity_score": 0.755,
      "rank": 2
    }
  ],
  "metadata": {
    "retrieved_count": 10,
    "avg_confidence_score": 0.720,
    "detected_operations": ["乘法", "减法", "除法"],
    "intent": "公式计算"
  }
}
```

### 5.2 输出（写入工作流状态）

| 字段 | 类型 | 说明 |
|------|------|------|
| `execution_plan` | `dict` | `PlanIR` 序列化后的字典，包含 `goal`、`nodes`、`connections` |
| `current_step` | `str` | 更新为 `"planning_completed"` |

`execution_plan` 输出示例（来自实际运行记录）：
```json
{
  "goal": "设计夏季主机负荷计算模块，实现公式：4.18×(冷冻回水温度-冷冻供水温度)×冷冻水流量÷3.6",
  "nodes": [
    {
      "logic_id": "input_return_temp",
      "module_type": "swInput",
      "parameters": { "user_defined_name": "冷冻回水温度" },
      "reasoning": "用于接收冷冻回水温度的输入值"
    },
    {
      "logic_id": "input_supply_temp",
      "module_type": "swInput",
      "parameters": { "user_defined_name": "冷冻供水温度" },
      "reasoning": "用于接收冷冻供水温度的输入值"
    },
    {
      "logic_id": "input_flow",
      "module_type": "swInput",
      "parameters": { "user_defined_name": "冷冻水流量" },
      "reasoning": "用于接收冷冻水流量的输入值"
    },
    {
      "logic_id": "const_4_18",
      "module_type": "constInput",
      "parameters": { "user_defined_name": "系数4.18", "fixedValue": 4.18 },
      "reasoning": "提供公式中的常数系数4.18"
    },
    {
      "logic_id": "const_3_6",
      "module_type": "constInput",
      "parameters": { "user_defined_name": "系数3.6", "fixedValue": 3.6 },
      "reasoning": "提供公式中的除数常数3.6"
    },
    {
      "logic_id": "calc_temp_diff",
      "module_type": "subtract",
      "parameters": { "name": "温差计算", "inputs": 2 },
      "reasoning": "计算冷冻回水温度与冷冻供水温度的差值"
    },
    {
      "logic_id": "multiply_all",
      "module_type": "multiply",
      "parameters": { "name": "乘积计算", "inputs": 3 },
      "reasoning": "将4.18、温差和流量三个数值相乘"
    },
    {
      "logic_id": "divide_by_3_6",
      "module_type": "divide",
      "parameters": { "name": "除以3.6", "inputs": 2 },
      "reasoning": "将乘积结果除以3.6得到最终负荷值"
    }
  ],
  "connections": [
    { "from_node": "input_return_temp", "from_port_index": 0, "to_node": "calc_temp_diff", "to_port_index": 0 },
    { "from_node": "input_supply_temp", "from_port_index": 0, "to_node": "calc_temp_diff", "to_port_index": 1 },
    { "from_node": "calc_temp_diff", "from_port_index": 0, "to_node": "multiply_all", "to_port_index": 1 },
    { "from_node": "const_4_18", "from_port_index": 0, "to_node": "multiply_all", "to_port_index": 0 },
    { "from_node": "input_flow", "from_port_index": 0, "to_node": "multiply_all", "to_port_index": 2 },
    { "from_node": "multiply_all", "from_port_index": 0, "to_node": "divide_by_3_6", "to_port_index": 0 },
    { "from_node": "const_3_6", "from_port_index": 0, "to_node": "divide_by_3_6", "to_port_index": 1 }
  ]
}
```

对应的逻辑拓扑图：
```
冷冻回水温度(swInput) ──[0]──→ [0]温差计算(subtract)
冷冻供水温度(swInput) ──[0]──→ [1]温差计算(subtract)

系数4.18(constInput)  ──[0]──→ [0]乘积计算(multiply, inputs=3)
温差计算(subtract)    ──[0]──→ [1]乘积计算(multiply)
冷冻水流量(swInput)   ──[0]──→ [2]乘积计算(multiply)

乘积计算(multiply)    ──[0]──→ [0]除以3.6(divide, inputs=2)
系数3.6(constInput)   ──[0]──→ [1]除以3.6(divide)
                                    ↓
                               最终负荷值
```

---

## 6. 关键设计原则

### 6.1 视图分离（上下文清洗）

通过 `format_docs_for_planner()` 函数，将检索智能体返回的完整上下文（包含 `template_json`、完整 `keywords` 等噪音数据）清洗为 LLM 只需关注的核心信息：

- **保留**：模块名称、类型、功能描述、参数定义（键名+类型+默认值+约束）、端口定义（索引+标签+类型）、使用场景指南
- **剔除**：`template_json` 模板、完整 `keywords`、相似度分数等

这确保 LLM 的注意力集中在逻辑推理上，而非被无关的模板细节干扰。

### 6.2 逻辑抽象（logic_id 解耦）

引入 `logic_id` 作为逻辑层面的唯一标识符，将"逻辑设计"与"物理生成"解耦：
- 规划智能体只关心逻辑拓扑（哪些模块、如何连接）
- 编码智能体负责将 `logic_id` 映射为实际的 UUID、坐标位置、wires 连接数组等物理属性

### 6.3 结构化输出 + 双路径容错

- **主路径**：利用 LLM 的 Function Calling 直接输出 Pydantic 模型，零解析开销
- **回退路径**：正则提取 JSON + 手动 Pydantic 校验，兼容不支持 function calling 的模型
- **兜底处理**：两条路径都失败时返回空规划，不会导致工作流崩溃

### 6.4 双重校验机制

1. **连接完整性**：确保所有连线的 `from_node`/`to_node` 都指向已定义的节点，防止悬空连接
2. **模块类型白名单**：确保 LLM 选择的 `module_type` 都在检索结果的可用范围内，防止虚构模块

---

## 7. 配置参数

| 配置项 | 来源 | 默认值 | 说明 |
|--------|------|--------|------|
| `LLM_PROVIDER` | `config.py` / `.env` | `"deepseek"` | LLM 提供商（deepseek/openai/qwen/glm/kimi） |
| `LLM_TEMPERATURE` | `config.py` / `.env` | `0.7` | 生成温度 |
| `LLM_MAX_TOKENS` | `config.py` / `.env` | `8192` | 最大输出 token 数 |
| `DEBUG` | `config.py` / `.env` | `True` | 是否输出调试信息 |

规划智能体支持在初始化时通过 `llm_provider` 和 `model` 参数覆盖全局配置。

---

## 8. 性能参考

根据实际运行记录（用户需求：`4.18×(冷冻回水温度-冷冻供水温度)×冷冻水流量÷3.6`）：

| 指标 | 值 |
|------|-----|
| 规划耗时 | 27.55 秒 |
| 生成节点数 | 8 个 |
| 生成连接数 | 7 条 |
| 使用模块类型 | `swInput`(3)、`constInput`(2)、`subtract`(1)、`multiply`(1)、`divide`(1) |

---

## 9. 错误处理策略

| 错误场景 | 处理方式 |
|----------|----------|
| Structured Output 失败 | 自动回退到正则解析 JSON |
| 正则解析也失败 | 返回空的 `PlanIR(goal="规划失败", nodes=[], connections=[])` |
| 连接引用了不存在的节点 ID | `validate_ids()` 抛出 `ValueError`，返回空规划 |
| 使用了不在白名单中的模块类型 | `validate_module_types()` 抛出 `ValueError`，返回空规划 |
| 检索上下文为空 | `format_docs_for_planner()` 返回警告文本 |

---

## 10. 与上下游智能体的协作关系

### 与检索智能体（上游）

- **依赖**：规划智能体完全依赖检索智能体提供的 `retrieval_context`，其中包含可用模块的定义和参数规格
- **约束**：规划时只能使用检索结果中已有的 `module_type`，通过白名单校验机制强制执行

### 与编码智能体（下游）

- **输出协议**：`PlanIR` 是两者之间的契约，编码智能体根据 `execution_plan` 中的节点列表和连接关系，结合模块的 `template_json` 模板，生成最终的 JSON 组态文件
- **职责边界**：
  - 规划智能体负责**逻辑正确性**（选什么模块、怎么连接、参数设多少）
  - 编码智能体负责**物理生成**（分配 UUID、计算坐标位置、填充 wires 数组、处理模板占位符）
