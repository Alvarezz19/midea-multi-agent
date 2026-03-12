# 分析智能体 (Analysis Agent) 当前工作流总结

> 最后更新: 2026-03-09

## 1. 概述

当前版本的 Analysis Agent 是 LangGraph 工作流中的入口节点。

它的职责不是检索模块、规划连线或生成最终 JSON，而是先对用户需求做结构化语义分析，产出两类关键结果：

1. retrieval_plan：供 Retrieval Agent 执行向量检索。
2. scenario_analysis：供 Planning Agent 理解业务场景。

因此，Analysis Agent 本质上是当前工作流里的“语义编译前端”。它把自然语言需求先翻译成一个对后续节点可消费的结构化状态对象。

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

对应 workflow.py 中与 Analysis Agent 相关的关键编排是：

```python
workflow.set_entry_point("analysis")
workflow.add_edge("analysis", "retrieval")
```

这意味着当前工作流的第一步不是检索，而是先做结构化分析。

---

## 3. 相关文件

| 文件 | 作用 |
|:---|:---|
| agents/analysis_agent.py | Analysis Agent 主实现 |
| agents/retrieval_agent.py | 消费 retrieval_plan 的下游节点 |
| agents/planning_agent.py | 消费 scenario_analysis 的下游节点 |
| config.py | Analysis Agent 的模型与约束配置 |
| workflow.py | 工作流入口编排 |
| docs/analysis_agent_integration_plan.md | 该节点的设计与接入背景说明 |

---

## 4. 输出契约

Analysis Agent 的核心输出结构由三个 Pydantic 模型组成：

1. RetrievalPlan
2. ScenarioAnalysis
3. AnalysisMetadata

它们最终聚合成 AnalysisResult。

### 4.1 RetrievalPlan

供 Retrieval Agent 使用的检索计划：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| queries | List[str] | 检索查询变体列表 |
| category_l1 | str | 一级分类建议，可为空 |
| intent | str | 需求意图枚举值 |
| detected_operations | List[str] | 识别出的运算类型 |
| keywords | List[str] | 领域术语和关键词 |

### 4.2 ScenarioAnalysis

供 Planning Agent 使用的业务场景分析：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| summary | str | 面向规划阶段的简短摘要 |
| business_goal | str | 业务目标 |
| system_type | str | 系统类型 |
| equipment_object | str | 设备对象 |
| actuator | str | 执行器 |
| controlled_variable | str | 被控量 |
| feedback_variable | str | 反馈量 |
| setpoint_variable | str | 设定值 |
| output_signal | str | 目标输出 |
| control_strategy | str | 控制策略 |
| control_mode | str | 控制模式 |
| input_signals | List[str] | 输入信号 |
| output_signals | List[str] | 输出信号 |
| operating_conditions | List[str] | 运行条件 |
| interlocks_or_limits | List[str] | 联锁与限值 |
| calculation_logic | List[str] | 关键计算逻辑 |
| ambiguities | List[str] | 模糊点 |
| assumptions | List[str] | 保守假设 |
| confidence | float | 分析置信度，限制在 0 到 1 |

### 4.3 AnalysisMetadata

分析过程元数据：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| llm_used | bool | 是否成功使用了 LLM |
| cached | bool | 是否命中缓存 |
| fallback_used | bool | 是否使用本地兜底结果 |

### 4.4 最终输出结构

```json
{
  "retrieval_plan": {
    "queries": [],
    "category_l1": "",
    "intent": "general_query",
    "detected_operations": [],
    "keywords": []
  },
  "scenario_analysis": {
    "summary": "",
    "business_goal": "",
    "system_type": "",
    "equipment_object": "",
    "actuator": "",
    "controlled_variable": "",
    "feedback_variable": "",
    "setpoint_variable": "",
    "output_signal": "",
    "control_strategy": "",
    "control_mode": "",
    "input_signals": [],
    "output_signals": [],
    "operating_conditions": [],
    "interlocks_or_limits": [],
    "calculation_logic": [],
    "ambiguities": [],
    "assumptions": [],
    "confidence": 0.0
  },
  "metadata": {
    "llm_used": true,
    "cached": false,
    "fallback_used": false
  }
}
```

---

## 5. 输入与输出

### 5.1 输入

Analysis Agent 从共享状态中实际读取：

| 字段 | 类型 | 来源 | 说明 |
|:---|:---|:---|:---|
| user_query | str | 用户输入 | 用户自然语言需求 |

这是当前 Analysis Agent 唯一必需的业务输入。

### 5.2 输出

Analysis Agent 写回：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| analysis_result | dict | AnalysisResult 结构化结果 |
| current_step | str | analysis_completed |

Analysis Agent 不直接写 retrieval_context、execution_plan 或 generated_code。

---

## 6. 完整分析流程

### 6.1 LangGraph 节点入口

__call__(state) 的执行顺序是：

1. 从 state 读取 user_query。
2. 调用 analyze(user_query)。
3. 将结果写入 state["analysis_result"]。
4. 将 current_step 更新为 analysis_completed。

### 6.2 analyze() 总体流程

```text
user_query
    │
    ▼
analyze()
    │
    ├─ 1. 查询缓存
    ├─ 2. 构建 Prompt
    ├─ 3. 优先走 Structured Output
    ├─ 4. 失败则回退普通 JSON 解析
    ├─ 5. 再失败则使用本地兜底结果
    ├─ 6. 本地标准化 retrieval_plan
    ├─ 7. 本地标准化 scenario_analysis
    └─ 8. 写入缓存并返回 analysis_result
```

### 6.3 Prompt 目标

当前 Prompt 要求模型一次调用同时输出两部分：

1. retrieval_plan
2. scenario_analysis

这比把“检索计划生成”和“场景理解”拆成两次调用更稳定，因为：

1. 两部分共享同一份语义理解。
2. 可以避免前后结果漂移。
3. 更便于缓存。

### 6.4 retrieval_plan 的生成目标

Prompt 要求模型输出：

1. 多层级查询变体 queries。
2. 一级分类 category_l1。
3. intent 枚举值。
4. detected_operations 枚举值。
5. keywords 列表。

查询变体的设计是分层的：

1. 应用场景层
2. 核心功能拆解层
3. 基础组件关键词层

### 6.5 scenario_analysis 的生成目标

Prompt 要求模型尽量抽取 HVAC/BAS 相关的业务槽位，例如：

1. system_type
2. equipment_object
3. actuator
4. controlled_variable
5. feedback_variable
6. setpoint_variable
7. control_strategy
8. ambiguities
9. assumptions

并且明确要求：

1. 不得编造用户未给出的业务事实。
2. 不能确定时应留空，或进入 ambiguities / assumptions。
3. summary 必须简短，聚焦规划所需信息。

---

## 7. 标准化与约束逻辑

Analysis Agent 不直接信任模型原始输出，而是在本地做二次规范化。

### 7.1 _normalize_retrieval_plan()

主要规则：

1. queries 过滤空值并截断到 RETRIEVAL_LLM_MAX_QUERIES。
2. intent 必须属于合法枚举，否则降级为 general_query。
3. detected_operations 只保留合法枚举值。
4. category_l1 清洗为字符串。
5. keywords 过滤空值。
6. 如果最终 queries 为空，则退回原始 query。

允许的 intent：

```text
mathematical_computation
comparison
logic_operation
timing_control
statistical_analysis
variable_input
general_query
```

允许的 detected_operations：

```text
加法、减法、乘法、除法、模运算、幂运算
```

### 7.2 _normalize_scenario_analysis()

主要规则：

1. 非法或缺失的 payload 自动转为空对象。
2. summary 为空时回退为 query 截断摘要。
3. summary 最长 120 字。
4. confidence 强制转为 float，并限制在 0 到 1。
5. ambiguities 最多保留 ANALYSIS_MAX_AMBIGUITIES 条。
6. assumptions 最多保留 ANALYSIS_MAX_ASSUMPTIONS 条。

---

## 8. 容错与回退机制

Analysis Agent 当前采用三层容错：

### 8.1 缓存命中

相同 query 优先从 _analyze_cache 直接返回，不重复调用模型。

### 8.2 Structured Output 主路径

优先使用：

```python
self.llm.with_structured_output(
    AnalysisResult,
    method="function_calling",
)
```

这要求模型按 AnalysisResult 契约直接输出结构化对象。

### 8.3 普通 JSON 解析回退

如果 Structured Output 失败，则退回普通 llm.invoke()，并通过 _extract_json_text() 从：

1. ```json 代码块
2. 裸 JSON 对象
3. 首个可匹配对象/数组

中提取 JSON 再解析。

### 8.4 本地兜底结果

如果连普通 JSON 解析也失败，则返回 _fallback_result(query)。

该兜底结果的特点是：

1. retrieval_plan.queries 至少退回原始 query。
2. intent 退回 general_query。
3. scenario_analysis.summary 退回 query 截断。
4. ambiguities 中写入“分析智能体未能完成结构化场景解析”。
5. metadata.fallback_used = true。

这保证了整个工作流不会因为分析阶段失败而完全不可用。

---

## 9. 配置参数

当前与 Analysis Agent 直接相关的配置为：

| 配置项 | 默认值 | 说明 |
|:---|:---|:---|
| ANALYSIS_LLM_PROVIDER | "" | 分析节点专用 provider，为空时回退全局 LLM_PROVIDER |
| ANALYSIS_LLM_MODEL | "" | 分析节点专用模型 |
| ANALYSIS_LLM_TEMPERATURE | 0.2 | 分析阶段温度 |
| ANALYSIS_LLM_TIMEOUT_S | 30 | 模型调用超时秒数 |
| ANALYSIS_MAX_AMBIGUITIES | 5 | ambiguities 最多保留条数 |
| ANALYSIS_MAX_ASSUMPTIONS | 5 | assumptions 最多保留条数 |
| RETRIEVAL_LLM_MAX_QUERIES | 8 | retrieval_plan.queries 最大条数 |

当前 Analysis Agent 的温度配置明显低于 Planning Agent，说明它被设计成“高约束结构化分析节点”，而不是开放式生成节点。

---

## 10. 与上下游智能体的协作关系

### 10.1 与 Retrieval Agent

Analysis Agent 为 Retrieval Agent 提供 retrieval_plan：

1. queries 决定多查询检索内容。
2. category_l1 决定是否启用一级分类过滤。
3. intent 与 detected_operations 被传递进 retrieval_context.metadata。

### 10.2 与 Planning Agent

Analysis Agent 为 Planning Agent 提供 scenario_analysis：

1. summary 提供整体业务摘要。
2. 控制对象、被控量、执行器等字段提供规划方向。
3. ambiguities 和 assumptions 提醒规划阶段的风险与不确定性。

### 10.3 与 Coding Agent

Coding Agent 不直接读取 analysis_result。Analysis Agent 的影响会在 Retrieval Agent 和 Planning Agent 两层中被吸收，最终体现在 execution_plan 与 generated_code 里。

---

## 11. 当前版本相对旧认知的几个要点

以下理解在当前版本里更准确：

1. Analysis Agent 是工作流入口节点，而不是一个可选增强器。
2. Retrieval Agent 不再自己调用 LLM 生成查询变体。
3. Analysis Agent 一次调用同时产出 retrieval_plan 和 scenario_analysis。
4. Analysis Agent 的职责边界是“语义理解和结构化分析”，不是检索执行。
5. 即使分析阶段失败，也会通过 fallback_result 让工作流降级运行。

---

## 12. 小结

当前版本的 Analysis Agent 是整个工作流的语义起点。

它的核心设计可以概括为：

1. 用一次 LLM 调用同时生成检索计划和业务场景分析。
2. 用本地标准化约束模型输出格式。
3. 用缓存、Structured Output、JSON 回退、本地兜底保证稳定性。
4. 将自然语言需求转换成 Retrieval Agent 和 Planning Agent 都能稳定消费的状态对象。

这也是当前系统能够实现“理解前置、检索受约束、规划有业务语义参考”的关键基础。