# 检索智能体 (Retrieval Agent) 当前工作流总结

> 最后更新: 2026-03-09

## 1. 概述

当前版本的 Retrieval Agent 已不再承担 LLM 意图分析、查询改写和业务语义理解职责。

这些职责已经前移到 Analysis Agent。Retrieval Agent 现在的定位是：

1. 读取 Analysis Agent 产出的 retrieval_plan。
2. 对 retrieval_plan 做本地标准化与校验。
3. 执行 ChromaDB 向量检索。
4. 将完整模块定义写回 retrieval_context，供 Planning Agent 和 Coding Agent 使用。

这意味着它已经从“检索 + LLM 分析混合节点”收敛为“纯检索执行器”。

### 当前职责边界

Retrieval Agent 负责：

1. 读取 analysis_result.retrieval_plan。
2. 校验 queries、intent、detected_operations、category_l1、keywords。
3. 基于多查询或单查询执行向量检索。
4. 保留完整模块定义，包括 parameters_schema、ports_definition、template_json。
5. 在 metadata 中补充少量分析引用信息，如 analysis_summary、analysis_confidence。

Retrieval Agent 不再负责：

1. 调用 LLM 生成查询变体。
2. 推断 intent。
3. 检测 detected_operations。
4. 抽取业务场景语义。
5. 生成规划或代码。

### 当前源码位置

1. 主实现: agents/retrieval_agent.py
2. 工作流入口: workflow.py
3. 规划上下文格式化: utils/context_formatter.py
4. 旧版备份: agents/retrieval_agent_old.py

---

## 2. 在工作流中的位置

当前主链路已经变为：

```text
用户需求
  -> Analysis Agent
  -> Retrieval Agent
  -> Planning Agent
  -> Coding Agent
  -> END
```

因此 Retrieval Agent 不再是工作流入口节点，而是第二个节点。

它在 workflow.py 中由 analysis 节点之后触发，并通过 __call__ 方法接收共享状态。

---

## 3. 输入与输出

### 3.1 输入

Retrieval Agent 从 WorkflowState 中实际读取以下字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| user_query | str | 用户原始需求 |
| analysis_result | dict | Analysis Agent 的结构化输出，重点使用其中的 retrieval_plan 和少量 scenario_analysis 元信息 |

其中 analysis_result 的核心结构为：

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
    "confidence": 0.0
  },
  "metadata": {
    "llm_used": true,
    "cached": false,
    "fallback_used": false
  }
}
```

### 3.2 输出

Retrieval Agent 更新 state 中的以下字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| retrieval_context | dict | 完整检索结果 |
| current_step | str | 更新为 retrieval_completed |

### 3.3 retrieval_context 结构

```json
{
  "query": "原始用户查询文本",
  "relevant_nodes": [
    {
      "module_type": "subtract",
      "name": "减法",
      "description": "模块功能描述",
      "category": "运算模块/数学运算",
      "parameters_schema": {},
      "ports_definition": {"inputs": [], "outputs": []},
      "template_json": {},
      "keywords": [],
      "usage_guides": [],
      "similarity_score": 0.73,
      "rank": 1,
      "matched_query": "减法运算"
    }
  ],
  "similar_cases": [],
  "metadata": {
    "retrieved_count": 10,
    "avg_confidence_score": 0.72,
    "rewrite_used": true,
    "analysis_used": true,
    "llm_queries": ["主机负荷计算", "减法运算", "乘法运算"],
    "llm_category_l1": "",
    "analysis_summary": "主机负荷计算场景，输入为温度与流量，输出为主机负荷。",
    "analysis_confidence": 0.84,
    "intent": "mathematical_computation",
    "detected_operations": ["减法", "乘法", "除法"]
  }
}
```

说明：

1. similar_cases 当前固定为空列表，检索主流程并不会填充示例代码。
2. relevant_nodes 中必须保留 template_json，因为 Coding Agent 直接依赖它生成最终 JSON。
3. matched_query 只在多查询路径下出现。

---

## 4. 初始化流程

__init__ 方法当前只做向量检索相关初始化：

```text
1. 创建 ChromaDB PersistentClient
2. 通过 EmbeddingManager 获取 embedding_function
3. 获取或创建集合 kong_modules_v1
```

### 构造函数参数

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| embedding_provider | Optional[str] | None | 嵌入模型提供商，不指定则使用 config.EMBEDDING_PROVIDER |
| llm_provider | Optional[str] | None | 为兼容旧调用保留，当前未使用 |
| llm_model | Optional[str] | None | 为兼容旧调用保留，当前未使用 |

其中 llm_provider 和 llm_model 只是兼容性残留参数，不参与当前检索主流程。

---

## 5. 完整检索流程

### 5.1 流程总览

```text
user_query + analysis_result
    │
    ▼
retrieve()
    │
    ├─ 1. 读取 analysis_result.retrieval_plan
    ├─ 2. 本地标准化 retrieval_plan
    ├─ 3. 根据 category_l1 决定是否启用一级分类过滤
    ├─ 4. queries 非空 -> 多查询批量检索
    ├─ 5. queries 为空 -> 原始 query 单查询兜底检索
    └─ 6. 增强 metadata，写入 retrieval_context
```

### 5.2 retrieval_plan 标准化

Retrieval Agent 不信任上游原始输出，而是会在本地再次清洗：

1. queries：过滤空字符串并截断到 config.RETRIEVAL_LLM_MAX_QUERIES。
2. intent：只允许以下枚举值，否则降级为 general_query。
3. detected_operations：仅保留合法枚举值。
4. category_l1：清洗为字符串。
5. keywords：过滤空字符串。

允许的 intent 为：

```text
mathematical_computation
comparison
logic_operation
timing_control
statistical_analysis
variable_input
general_query
```

允许的 detected_operations 为：

```text
加法、减法、乘法、除法、模运算、幂运算
```

### 5.3 category_l1 过滤

如果 analysis_result 中给出的 category_l1 属于以下允许前缀，则 Retrieval Agent 会把它转成 ChromaDB 的 where 过滤条件：

```text
逻辑模块、运算模块、变量模块、定时模块、累计模块、应用、基础组件、高级组件、备注组件、其他
```

如果 category_l1 为空或不在允许集合中，则不做类别过滤。

### 5.4 多查询检索

触发条件：retrieval_plan.queries 非空。

流程：

1. 使用 query_texts 一次性提交全部查询变体。
2. 每个变体最多取 min(top_k, 5) 条结果。
3. 将 L2 distance 转换为 similarity_score。
4. 过滤低于 similarity_threshold 的结果。
5. 按 module_type 去重，只保留更高分数的候选。
6. 最终按相似度降序排序，截取 top_k，并重排 rank。

多查询路径会在 metadata 中稳定提供：

1. query_variants_used
2. detected_operations
3. intent
4. avg_confidence_score

### 5.5 单查询兜底检索

触发条件：

1. analysis_result 不存在。
2. retrieval_plan 无效。
3. retrieval_plan.queries 为空。

流程：

1. 直接用原始 user_query 调用 collection.query。
2. 逐条解析结果并计算相似度。
3. 过滤低分结果。
4. 保留完整模块定义。

这条兜底路径不再调用任何 LLM。

### 5.6 元数据增强

retrieve() 在检索完成后，会统一补强 metadata：

1. rewrite_used：是否使用了 analysis_result 中的查询变体。
2. analysis_used：本次是否收到 analysis_result。
3. llm_queries：仅在多查询路径下写入，上游实际来自 Analysis Agent。
4. llm_category_l1：仅在多查询路径下写入，上游实际来自 Analysis Agent。
5. analysis_summary：从 scenario_analysis.summary 引用。
6. analysis_confidence：从 scenario_analysis.confidence 引用。

注意：字段名里虽然仍保留 llm_queries、llm_category_l1、rewrite_used 这些历史命名，但它们现在表达的是“上游分析结果被使用”，而不是 Retrieval Agent 自己在调用 LLM。

---

## 6. 知识库管理能力

除了检索主流程，Retrieval Agent 仍保留知识库装载相关能力，这部分不是旧分析残留，而是项目其他脚本仍在使用的基础设施。

### 6.1 load_knowledge_base

该方法会扫描 schemas 目录下的模块 JSON，序列化为语义文本并批量 upsert 到 ChromaDB。

主要步骤：

1. 扫描 schemas 目录中的 .json 文件。
2. 跳过 扩展描述文件.json。
3. 调用 _serialize_module_to_text() 生成语义文本。
4. 调用 _extract_metadata() 生成过滤元数据。
5. 生成唯一 ID 并写入 collection.upsert()。

### 6.2 _serialize_module_to_text

将模块 JSON 转成用于向量检索的语义文本，包含：

1. 模块名称、模块类型、模块类别。
2. 功能描述。
3. 关键词。
4. 使用场景。
5. 参数功能。
6. 输入输出端口描述。

### 6.3 _extract_metadata

提取以下元数据字段：

1. module_id
2. module_type
3. category
4. category_l1
5. category_l2
6. has_dynamic_ports
7. keywords
8. json_schema

---

## 7. 关键配置参数

### 7.1 Retrieval Agent 实际使用的配置

| 环境变量 | 默认值 | 说明 |
|:---|:---|:---|
| EMBEDDING_PROVIDER | bge | 嵌入模型提供商 |
| BGE_MODEL_NAME | BAAI/bge-m3 | BGE 模型名称 |
| BGE_DEVICE | cpu | 本地推理设备 |
| CHROMA_PERSIST_DIR | ./chroma_db | ChromaDB 持久化目录 |
| RETRIEVAL_LLM_MAX_QUERIES | 8 | retrieval_plan 允许的最大 queries 数量 |

### 7.2 已不再由 Retrieval Agent 使用的旧配置

以下配置项仍可能保留在 config.py 中，但当前 Retrieval Agent 主流程并不会读取它们来调用 LLM：

1. RETRIEVAL_USE_LLM_REWRITE
2. RETRIEVAL_LLM_PROVIDER
3. RETRIEVAL_LLM_MODEL
4. RETRIEVAL_LLM_TIMEOUT_S

这些配置属于旧检索阶段 LLM 设计的历史遗留，不应再被理解为当前检索主流程的一部分。

---

## 8. retrieve() 方法参数速查

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| query | str | 必填 | 用户查询文本 |
| top_k | int | 10 | 返回的最相关文档数量 |
| category_filter | Optional[str] | None | 可选的一级分类过滤 |
| similarity_threshold | float | 0.3 | 相似度阈值 |
| analysis_result | Optional[dict] | None | Analysis Agent 的结构化输出 |

---

## 9. 容错与兜底机制

| 场景 | 处理方式 |
|:---|:---|
| Embedding 模型加载失败 | 回退到 ChromaDB 默认 Embedding 函数 |
| ChromaDB 集合不存在 | 自动创建新集合 |
| analysis_result 缺失 | 直接退回原始 query 单次检索 |
| retrieval_plan 非法或 queries 为空 | 退回原始 query 单次检索 |
| 向量检索异常 | 返回空结果和 error 信息 |
| 某条 json_schema 解析失败 | 跳过该条候选，继续处理后续结果 |

当前兜底机制的关键点是：

1. 工作流允许 Analysis Agent 失败后降级运行。
2. Retrieval Agent 的兜底完全不依赖重新调用 LLM。

---

## 10. 与上下游智能体的协作关系

### 10.1 与 Analysis Agent

Analysis Agent 是 Retrieval Agent 的上游语义提供者：

1. retrieval_plan 决定检索变体和检索方向。
2. scenario_analysis.summary 和 confidence 以轻量元数据形式透传给 retrieval_context.metadata。

### 10.2 与 Planning Agent

Planning Agent 的硬约束输入仍然是 retrieval_context.relevant_nodes。

它会：

1. 从 retrieval_context 中提取模块白名单。
2. 使用 parameters_schema 和 ports_definition 构造规划上下文。
3. 间接利用 metadata 中的 intent、detected_operations、analysis_summary 等辅助信息。

### 10.3 与 Coding Agent

Coding Agent 直接依赖 retrieval_context.relevant_nodes 中的 template_json 生成最终平台 JSON。因此 Retrieval Agent 不能把 relevant_nodes 简化成纯摘要。

---

## 11. 当前版本与旧版文档的差异

如果你看到历史描述中出现以下说法，都已经不再适用于当前实现：

1. Retrieval Agent 是工作流入口节点。
2. Retrieval Agent 会调用 LLM 生成 queries。
3. Retrieval Agent 内部仍有 _llm_analyze_query 主流程。
4. RETRIEVAL_LLM_PROVIDER 和 RETRIEVAL_LLM_MODEL 控制当前检索主流程。
5. 检索主路径是“LLM rewrite -> multi query retrieve”。

当前正确理解应为：

```text
Analysis Agent 负责理解和生成 retrieval_plan
Retrieval Agent 负责消费 retrieval_plan 并执行向量检索
Planning Agent 负责在检索结果白名单内生成 execution_plan
```

---

## 12. 小结

当前版本的 Retrieval Agent 已经完成角色收缩：

1. 从“检索 + LLM 语义分析”变成“纯检索执行器”。
2. 上游由 Analysis Agent 提供结构化语义输入。
3. 下游继续保持 retrieval_context -> execution_plan -> generated_code 的主协议不变。
4. 保留了单查询兜底和知识库装载能力，保证稳定性和可维护性。

这也是当前工作流能够做到“语义理解前置、模块检索受约束、规划阶段保留白名单硬约束”的基础。