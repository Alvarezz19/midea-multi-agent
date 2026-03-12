# 规划智能体 (Planning Agent) 当前工作流总结

> 最后更新: 2026-03-09

## 1. 概述

当前版本的 Planning Agent 是 LangGraph 工作流中的第三个节点，位于 Analysis Agent 和 Retrieval Agent 之后、Coding Agent 之前。

它的职责不是直接生成最终 JSON，而是把：

1. 用户原始需求 user_query
2. 检索智能体返回的模块白名单 retrieval_context
3. 分析智能体提供的业务场景参考 analysis_result

组合成一份结构化的中间表示 PlanIR，再写入 execution_plan，供 Coding Agent 使用。

Planning Agent 当前扮演的是“受检索结果约束的逻辑规划器”：

1. retrieval_context 决定可用模块范围。
2. analysis_result 决定规划理解方向。
3. execution_plan 决定下游如何实例化模块和连线。

---

## 2. 在工作流中的位置

当前主链路为：

```text
用户需求
  -> Analysis Agent
  -> Retrieval Agent
  -> Planning Agent
  -> Coding Agent
  -> END
```

对应的 workflow.py 节点关系是：

```python
workflow.set_entry_point("analysis")
workflow.add_edge("analysis", "retrieval")
workflow.add_edge("retrieval", "planning")
workflow.add_edge("planning", "coding")
workflow.add_edge("coding", END)
```

因此，Planning Agent 不再是“检索后的第二个节点”这种旧表述，而是当前线性工作流中的第三步。

---

## 3. 相关文件

| 文件 | 作用 |
|:---|:---|
| agents/planning_agent.py | Planning Agent 主实现，包含 IR 模型、Prompt、重试、校验逻辑 |
| utils/context_formatter.py | format_docs_for_planner()，将 retrieval_context 压缩为适合规划模型阅读的 slim_context |
| agents/analysis_agent.py | 上游语义分析节点，生成 scenario_analysis 供规划阶段软引用 |
| agents/retrieval_agent.py | 上游检索节点，提供 relevant_nodes 白名单与技术规格 |
| config.py | Planning Agent 的模型与上下文配置 |
| workflow.py | 工作流节点编排 |

---

## 4. 中间表示契约

Planning Agent 与 Coding Agent 之间通过 PlanIR 契约通信。

### 4.1 PlanNode

表示一个模块实例：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| logic_id | str | 逻辑层唯一标识符，如 temp_diff_calc、const_4_18 |
| module_type | str | 模块类型，必须来自 retrieval_context.relevant_nodes |
| parameters | Dict[str, Any] | 模块参数配置 |
| reasoning | str | 选择该模块的理由 |

注意：Prompt 示例中出现过 name 字段，但当前真正的 PlanNode 契约只有 logic_id、module_type、parameters、reasoning 四个字段。name 不属于最终 execution_plan 契约。

### 4.2 PlanConnection

表示两个节点之间的一条连接：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| from_node | str | 上游节点 logic_id |
| from_port_index | int | 上游输出端口索引，0-based |
| to_node | str | 下游节点 logic_id |
| to_port_index | int | 下游输入端口索引，0-based |

### 4.3 PlanIR

整体规划结果：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| goal | str | 对当前规划目标的简述 |
| nodes | List[PlanNode] | 节点列表 |
| connections | List[PlanConnection] | 连接关系列表 |

### 4.4 内建校验

PlanIR 当前内建两类校验：

1. validate_ids()：所有连接引用的 logic_id 必须存在。
2. validate_module_types()：所有 node.module_type 必须在检索结果白名单内。

---

## 5. 输入与输出

### 5.1 输入

Planning Agent 从共享状态中读取：

| 字段 | 类型 | 来源 | 说明 |
|:---|:---|:---|:---|
| user_query | str | 用户输入 | 用户原始需求 |
| retrieval_context | dict | Retrieval Agent | 检索到的模块定义、参数、端口、模板等完整信息 |
| analysis_result | dict | Analysis Agent | 业务场景分析结果，主要用于 prompt 软参考 |

其中 retrieval_context 是唯一的硬约束输入，analysis_result 是软参考输入。

### 5.2 analysis_result 在规划阶段的作用

Planning Agent 通过 _format_analysis_context() 从 analysis_result.scenario_analysis 中提取简洁的业务提示，包括：

1. summary
2. business_goal
3. system_type
4. equipment_object
5. actuator
6. controlled_variable
7. feedback_variable
8. setpoint_variable
9. output_signal
10. control_strategy
11. control_mode
12. input_signals
13. output_signals
14. ambiguities
15. assumptions

这些内容只作为 Prompt 中的“业务场景参考”，不会替代 retrieval_context 的模块白名单约束。

### 5.3 输出

Planning Agent 写回：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| execution_plan | dict | PlanIR 经 model_dump() 序列化后的结果 |
| current_step | str | planning_completed |

---

## 6. 完整规划流程

### 6.1 LangGraph 节点入口

__call__(state) 的执行顺序是：

1. 从 state 读取 user_query。
2. 从 state 读取 retrieval_context。
3. 从 state 读取 analysis_result。
4. 调用 plan(user_query, retrieval_context, analysis_result)。
5. 将返回的 PlanIR 序列化写入 state["execution_plan"]。
6. 将 current_step 更新为 planning_completed。

### 6.2 核心流程图

```text
user_query + retrieval_context + analysis_result
    │
    ▼
plan()
    │
    ├─ 1. 提取 module_type 白名单
    ├─ 2. format_docs_for_planner() 压缩检索上下文
    ├─ 3. _format_analysis_context() 压缩业务场景参考
    ├─ 4. 构建 Prompt
    ├─ 5. 先走 Structured Output
    ├─ 6. 失败则回退到 JSON 正则解析
    ├─ 7. 校验 IDs 与 module_type 白名单
    ├─ 8. 失败则带错误反馈重试
    └─ 9. 返回 PlanIR 或失败 PlanIR
```

### 6.3 步骤一：提取模块白名单

从 retrieval_context.relevant_nodes 中提取所有合法 module_type：

```python
self._available_module_types = {
    node.get('module_type')
    for node in retrieval_context.get('relevant_nodes', [])
    if node.get('module_type')
}
```

这一步的意义是把“规划自由度”限制在检索结果给出的模块集合里。

### 6.4 步骤二：压缩检索上下文

Planning Agent 不会把 retrieval_context 原样交给 LLM，而是调用 format_docs_for_planner() 做视图降维。

保留的信息主要有：

1. 模块名称
2. module_type
3. 分类
4. 功能描述
5. 参数键名、类型、默认值、约束
6. 端口索引、标签、类型、描述
7. 使用场景
8. 检索元数据摘要

被剔除或压缩的信息主要有：

1. template_json 原文
2. 大块无关结构
3. 过长的关键词与模板细节

上下文规模由以下配置控制：

1. PLANNING_CONTEXT_DETAIL_TOP_N
2. PLANNING_CONTEXT_MAX_MODULES

### 6.5 步骤三：压缩业务场景参考

_format_analysis_context() 会把上游的 scenario_analysis 转成一段简洁文本，作为 System Prompt 中的业务参考块。

它的设计原则是：

1. 提供业务理解方向。
2. 不把 analysis_result 变成新的硬约束源。
3. 模糊点和假设只保留少量关键内容，避免 Prompt 噪声膨胀。

### 6.6 步骤四：构建 Prompt

当前 Prompt 有三个关键组成部分：

1. analysis_context：来自 Analysis Agent 的业务场景参考。
2. slim_context：来自 Retrieval Agent 的模块清单和技术规格摘要。
3. user_query：用户原始需求。

Prompt 对模型施加的核心规则包括：

1. 只能使用可用模块列表中的 module_type。
2. logic_id 必须唯一且有意义。
3. 端口索引必须使用 0-based。
4. 参数键名必须与模块定义完全一致。
5. 常量优先检查是否能通过参数设置，否则需要显式实例化 constInput。
6. analysis_context 只能帮助理解场景，不能替代可用模块列表。

### 6.7 步骤五：Structured Output 主路径

Planning Agent 首选：

```python
structured_llm = self.llm.with_structured_output(
    PlanIR,
    method="function_calling",
)
```

也就是要求模型直接按 PlanIR 契约生成结构化输出。这是当前最稳定的主路径。

### 6.8 步骤六：回退解析路径

如果 Structured Output 失败，则调用 _fallback_parse()：

1. 先调用普通 llm.invoke(messages)。
2. 优先提取 ```json 代码块。
3. 提取不到时尝试直接将全文作为 JSON 解析。
4. 再交给 PlanIR 做 Pydantic 校验。

因此当前规划阶段并不是“只有 Function Calling 一条路”，而是保留了兼容不同模型的回退链路。

### 6.9 步骤七：结果校验

当前统一由 _validate_plan() 执行：

1. 一定执行 plan_ir.validate_ids()。
2. 只有当 _available_module_types 非空时，才执行 module_type 白名单校验。

这意味着：

1. 正常情况下，Planning Agent 会受到检索结果的硬约束。
2. 当检索结果为空时，仍会尝试规划，但 module_type 白名单校验会被跳过。

### 6.10 步骤八：带错误反馈的重试

如果生成或校验失败，Planning Agent 不会立刻退出，而是进入带错误反馈的修正重试。

下一轮重试时，模型会看到：

1. 原始用户需求
2. slim_context
3. analysis_context
4. 上一轮错误原因
5. 上一轮生成内容

这样做的目的，是把失败原因显式反馈给模型，而不是盲目重试。

### 6.11 步骤九：最终兜底

当达到 max_attempts 仍失败时，返回失败 PlanIR：

```json
{
  "goal": "规划失败: <错误信息>",
  "nodes": [],
  "connections": []
}
```

这保证了工作流不会因为规划阶段异常而直接崩溃。

---

## 7. Prompt 设计要点

当前版本和旧版相比，最大的变化不是 JSON 结构，而是 Prompt 已显式接入 analysis_context。

也就是说，Planning Agent 现在同时受两类上游信息影响：

1. retrieval_context：技术白名单与模块规格。
2. analysis_result：业务场景理解与模糊点提示。

两者关系必须这样理解：

1. analysis_result 决定理解方向。
2. retrieval_context 决定可用积木。

如果 analysis_result 暗示“应该做 PID 控制”，但 retrieval_context 没有 PID 模块，Planning Agent 依然不能虚构 PID 模块。

---

## 8. 配置参数

当前实际相关配置如下：

| 配置项 | 默认值 | 说明 |
|:---|:---|:---|
| PLANNING_LLM_PROVIDER | "" | 规划节点专用 provider，为空时回退全局 LLM_PROVIDER |
| PLANNING_LLM_MODEL | "" | 规划节点专用模型，为空时使用 provider 默认模型 |
| PLANNING_LLM_TEMPERATURE | 0.7 | 规划阶段温度 |
| PLANNING_MAX_RETRIES | 2 | 总尝试次数上限，包含首次生成 |
| PLANNING_CONTEXT_DETAIL_TOP_N | 5 | 详细展开的模块数量 |
| PLANNING_CONTEXT_MAX_MODULES | 8 | 传给规划模型的最大模块数量 |

需要特别注意：PLANNING_MAX_RETRIES 当前实际语义是“总尝试次数”，不是“首次失败后的额外重试次数”。配置为 2 时，表示首次生成加最多 1 次修正。

---

## 9. 错误处理策略

| 场景 | 处理方式 |
|:---|:---|
| Structured Output 失败 | 回退到 _fallback_parse() |
| JSON 提取或解析失败 | 进入下一轮重试 |
| 连接引用了不存在的节点 ID | validate_ids() 抛错，进入下一轮重试 |
| 使用了不存在于检索白名单的 module_type | validate_module_types() 抛错，进入下一轮重试 |
| 超过最大尝试次数仍失败 | 返回失败 PlanIR |
| retrieval_context 为空 | 仍尝试规划，但 module_type 白名单校验可能跳过 |

---

## 10. 与上下游智能体的协作关系

### 10.1 与 Analysis Agent

Analysis Agent 为 Planning Agent 提供业务语义支撑。

Planning Agent 当前会消费的不是 analysis_result 全量对象，而是其中适合 Prompt 的场景摘要与关键槽位。

### 10.2 与 Retrieval Agent

Retrieval Agent 提供的是技术侧硬约束，包括：

1. 可用 module_type 白名单。
2. 参数定义。
3. 端口定义。
4. 使用场景。
5. 模板相关元信息。

Planning Agent 只依赖 retrieval_context 作为模块可用性的最终依据。

### 10.3 与 Coding Agent

Coding Agent 接收 execution_plan 后，会：

1. 把 logic_id 映射成真实 UUID。
2. 根据 connections 生成 wires。
3. 根据 retrieval_context 中对应模块的 template_json 生成最终平台 JSON。

因此 Planning Agent 只负责逻辑正确性，不负责物理生成细节。

---

## 11. 当前版本相对旧文档的主要变化

以下旧说法已经不适用于当前实现：

1. Planning Agent 只读取 user_query 和 retrieval_context。
2. 工作流入口是 Retrieval Agent。
3. Planning Agent 只依赖检索上下文，不利用分析结果。
4. 规划提示词里没有业务场景参考块。
5. PLANNING_LLM_TEMPERATURE 默认是 0.2。

当前正确描述应该是：

1. 工作流入口是 Analysis Agent。
2. Planning Agent 实际读取 user_query、retrieval_context、analysis_result 三个输入。
3. analysis_result 只做软参考，retrieval_context 才是硬约束来源。
4. Prompt 已显式包含业务场景参考。
5. 当前配置默认温度是 0.7。

---

## 12. 小结

当前版本的 Planning Agent 已经从“只看检索结果的规划器”升级成“结合分析语义、但仍受检索白名单约束的规划器”。

它的核心设计可以概括为：

1. 用 analysis_result 增强理解。
2. 用 retrieval_context 约束可用模块。
3. 用 PlanIR 解耦规划与编码。
4. 用 Structured Output + 回退解析 + 错误反馈重试保证鲁棒性。

这也是当前工作流里语义理解、模块检索、拓扑规划三层分工真正闭合的关键节点。