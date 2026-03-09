# 检索智能体 (Retrieval Agent) v2 完整工作流总结

> 最后更新: 2026-03-06

## 1. 概述

**Retrieval Agent v2** 是 KONG CUBE 智能组态生成系统工作流的**第一个节点**（入口节点）。相比 v1 版本，v2 将 **LLM 意图分析与查询生成**提升为主流程，完全移除了基于规则的 `QueryProcessor` 查询增强，由 LLM 统一完成意图推断、运算检测和查询变体生成。

### v1 → v2 核心变化

| 维度 | v1（旧版） | v2（新版） |
|:---|:---|:---|
| 查询增强 | `QueryProcessor` 规则（正则 + 关键词匹配） | LLM 意图分析（`_llm_analyze_query`） |
| 查询变体生成 | 规则拼接（运算符/变量/常量模式） | LLM 生成多层次查询策略 |
| 意图推断 | 规则优先级判断 | LLM 直接输出枚举值 |
| `detected_operations` | 正则扫描数学符号 | LLM 分析提取 |
| LLM 角色 | 可选（默认关闭） | 主流程（默认启用，失败自动兜底） |
| 兜底策略 | 规则增强 → 向量检索 | 原始查询 → 单次向量检索 |
| 外部依赖 | `QueryProcessor`（`utils/query_processor.py`） | 无规则依赖 |
| 输出结构 | `retrieval_context` | **完全一致，对下游零影响** |

### 核心组件

| 组件 | 说明 |
|:---|:---|
| **ChromaDB** | 持久化的向量数据库，存储所有模块的语义文本和元数据（集合名: `kong_modules_v1`） |
| **Embedding 模型** | 支持 BGE、OpenAI、SiliconFlow、Jina、Sentence-Transformers 等多种嵌入模型 |
| **LLM** | 用于意图推断和查询变体生成（主流程），支持 DeepSeek、OpenAI、Qwen、GLM、Kimi |

### 源码位置

- 主文件: `agents/retrieval_agent.py`（v2）
- 旧版备份: `agents/retrieval_agent_old.py`（v1）
- 模型管理器: `utils/model_manager.py`
- 配置文件: `config.py`

---

## 2. 在工作流中的位置

```
用户需求 → [Retrieval Agent] → Planning Agent → Coding Agent → END
                  ↑ 当前节点
```

检索智能体是 LangGraph 工作流 (`workflow.py`) 中的入口点 (`set_entry_point("retrieval")`)，通过 `__call__` 方法被调用。

---

## 3. 输入与输出

### 3.1 输入 (Input)

检索智能体从 `WorkflowState` 中读取以下字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| `user_query` | `str` | 用户的自然语言需求描述 |

其余 state 字段在此节点中不使用，原样透传。

**输入示例**：
```json
{
  "user_query": "设计计算模块，输入0时，公式为：4.18×(输入A-输入B-输入C-输入D)×输入E÷3.6。输入1时，公式为：4.18×(输入A-输入B-输入C+输入D)×输入E÷3.6",
  "retrieval_context": {},
  "execution_plan": {},
  "current_step": "start"
}
```

### 3.2 输出 (Output)

检索智能体更新 state 中的以下字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| `retrieval_context` | `dict` | 完整的检索结果（详见下方结构） |
| `current_step` | `str` | 更新为 `"retrieval_completed"` |

#### `retrieval_context` 结构

```json
{
  "query": "原始用户查询文本",
  "relevant_nodes": [
    {
      "module_type": "switch",
      "name": "通道选择 (Switch)",
      "description": "模块功能描述",
      "category": "逻辑模块/通道选择",
      "parameters_schema": { ... },
      "ports_definition": { "inputs": [...], "outputs": [...] },
      "template_json": { ... },
      "keywords": ["通道选择", "条件切换", ...],
      "usage_guides": ["根据条件选择不同的计算分支...", ...],
      "similarity_score": 0.759,
      "rank": 1,
      "matched_query": "通道选择 常量输入 变量输入"
    }
  ],
  "similar_cases": [],
  "metadata": {
    "retrieved_count": 10,
    "query_variants_used": 8,
    "detected_operations": ["加法", "减法", "乘法", "除法"],
    "intent": "mathematical_computation",
    "avg_confidence_score": 0.726,
    "rewrite_used": true,
    "llm_queries": ["条件选择公式计算", "减法运算 加法运算 乘法运算 除法运算", ...],
    "llm_category_l1": ""
  }
}
```

**`relevant_nodes` 中每个节点的字段说明**：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| `module_type` | `str` | 模块类型标识符（如 `constInput`、`multiply`、`subtract`） |
| `name` | `str` | 模块的中文名称 |
| `description` | `str` | 模块功能的详细描述 |
| `category` | `str` | 模块分类路径（如 `运算模块/数学运算`） |
| `parameters_schema` | `dict` | 模块可配置参数的 JSON Schema |
| `ports_definition` | `dict` | 输入/输出端口定义（含端口名、类型、描述、条件） |
| `template_json` | `dict` | 模块的 JSON 模板（含占位符，用于后续代码生成） |
| `keywords` | `list[str]` | 关联关键词列表 |
| `usage_guides` | `list[str]` | 使用场景说明列表 |
| `similarity_score` | `float` | 与查询的相似度分数，范围 (0, 1] |
| `rank` | `int` | 按相似度排序后的排名 |
| `matched_query` | `str` | 匹配到该模块的查询变体，仅多查询主路径下存在 |

#### 关于 `similar_cases`

当前实现中，无论是 `_single_query_retrieve()` 还是 `_multi_query_retrieve()`，都固定返回空列表：

```json
"similar_cases": []
```

代码里虽然保留了 `_generate_example_code()` 方法，但当前检索主流程并没有调用它，因此 `similar_cases` 目前不是已填充的数据通道。

---

## 4. 初始化流程

`__init__` 方法执行以下初始化步骤：

```
┌─────────────────────────────────────────────┐
│ 1. 创建 ChromaDB PersistentClient           │
│    路径: config.CHROMA_PERSIST_DIR           │
│    (默认 ./chroma_db)                        │
├─────────────────────────────────────────────┤
│ 2. 获取 Embedding 函数                       │
│    通过 EmbeddingManager.get_embedding()     │
│    支持: bge / openai / siliconflow /        │
│          jina / sentence-transformers        │
│    失败时回退到 ChromaDB 默认 Embedding       │
├─────────────────────────────────────────────┤
│ 3. 加载 ChromaDB 集合                        │
│    集合名: "kong_modules_v1"                 │
│    存在 → 直接加载                            │
│    不存在 → 创建新集合                        │
├─────────────────────────────────────────────┤
│ 4. 配置 LLM（懒加载）                        │
│    读取 RETRIEVAL_LLM_PROVIDER/MODEL         │
│    首次调用 _ensure_llm() 时才真正初始化      │
│    仅尝试一次，失败后标记不再重试              │
├─────────────────────────────────────────────┤
│ 5. 创建 LLM 意图分析 Prompt 模板              │
│ 6. 初始化分析结果缓存字典                     │
└─────────────────────────────────────────────┘
```

### 构造函数参数

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `embedding_provider` | `Optional[str]` | `None` | 嵌入模型提供商，不指定则使用 `config.EMBEDDING_PROVIDER` |
| `llm_provider` | `Optional[str]` | `None` | LLM 提供商，不指定则优先使用 `config.RETRIEVAL_LLM_PROVIDER`，再回退到全局默认 |
| `llm_model` | `Optional[str]` | `None` | LLM 模型名，不指定则使用 `config.RETRIEVAL_LLM_MODEL` |

---

## 5. 完整检索流程

### 5.1 流程总览

```
用户需求 (user_query)
    │
    ▼
┌──────────────────────────────────────────────────────┐
│ retrieve() 方法                                       │
│                                                       │
│  ① LLM 意图分析 (_llm_analyze_query)                  │
│     - 调用 LLM 分析用户需求                            │
│     - 输出: queries / category_l1 / intent /           │
│             detected_operations / keywords             │
│     - 自带缓存（相同查询不重复调用 LLM）                │
│     - 失败时返回 None                                  │
│                                                       │
│  ② category_l1 过滤                                   │
│     - 仅当 LLM 推断的类别属于合法值时启用               │
│     - 复杂组合需求 LLM 会留空（不过滤）                 │
│                                                       │
│  ③ 检索路由                                            │
│     ┌─────────────────────────────────────────┐       │
│     │ LLM 成功 → _multi_query_retrieve        │       │
│     │ LLM 失败 → _single_query_retrieve (兜底) │       │
│     └─────────────────────────────────────────┘       │
│                                                       │
│  ④ 增强元数据（附加 rewrite_used 等可观测字段）         │
│     - 始终补写 rewrite_used                            │
│     - 仅 LLM 成功时补写 llm_queries / llm_category_l1  │
└──────────────────────────────────────────────────────┘
    │
    ▼
 retrieval_context (传递给 Planning Agent)
```

### 5.2 步骤一：LLM 意图分析 (`_llm_analyze_query`)

这是 v2 版本的**核心变化**，用一次 LLM 调用替代了旧版的全部规则增强逻辑。

#### Prompt 设计

Prompt 引导 LLM 作为**"工业楼控/自动化模块检索专家"**，输出包含 5 个字段的结构化 JSON：

```json
{
  "queries": ["应用场景查询", "核心功能查询", "基础组件查询1", "基础组件查询2"],
  "category_l1": "一级分类或空字符串",
  "intent": "mathematical_computation",
  "detected_operations": ["乘法", "减法", "除法"],
  "keywords": ["领域术语1", "运算名称1"]
}
```

**查询生成的三层策略**：

| 层级 | 说明 | 示例 |
|:---|:---|:---|
| 第1层 · 应用场景（1条） | 保留完整需求语义 | "条件选择公式计算" |
| 第2层 · 核心功能拆解（1-2条） | 提取计算逻辑 | "基于输入选择执行不同公式" |
| 第3层 · 基础组件关键词（2-4条） | 直接使用模块名称 | "减法运算 加法运算 乘法运算 除法运算" |

查询总数上限由 `config.RETRIEVAL_LLM_MAX_QUERIES`（默认 8）控制。

#### intent 枚举值

LLM 输出的 `intent` 必须是以下枚举值之一，非法值自动降级为 `general_query`：

| 枚举值 | 含义 |
|:---|:---|
| `mathematical_computation` | 包含数学公式或运算 |
| `comparison` | 包含比较/判断逻辑 |
| `logic_operation` | 包含逻辑运算（与或非） |
| `timing_control` | 包含定时/延时控制 |
| `statistical_analysis` | 包含统计计算（平均/最大/最小） |
| `variable_input` | 主要涉及数据输入/输出 |
| `general_query` | 无法归类的通用查询 |

#### detected_operations 枚举值

LLM 输出的运算类型必须从以下枚举值中选取：

```
加法、减法、乘法、除法、模运算、幂运算
```

#### 输出标准化

LLM 返回的 JSON 经过严格标准化处理：

1. **queries**：过滤非字符串/空值，截断至 `RETRIEVAL_LLM_MAX_QUERIES`
2. **intent**：校验是否属于合法枚举值，否则降级为 `general_query`
3. **detected_operations**：仅保留属于合法枚举值的项
4. **category_l1**：保留原样（后续在 `retrieve()` 中二次校验）
5. **keywords**：过滤非字符串/空值

#### 缓存与容错

| 机制 | 说明 |
|:---|:---|
| **缓存** | `_analyze_cache` 字典按 query 文本缓存结果，相同查询不重复调用 LLM |
| **懒加载** | LLM 在首次调用 `_ensure_llm()` 时才初始化，且仅尝试一次 |
| **超时** | 由 `config.RETRIEVAL_LLM_TIMEOUT_S`（默认 8 秒）控制 |
| **失败回退** | LLM 初始化失败或调用失败时返回 `None`，主方法自动走兜底路径 |
| **JSON 提取** | 支持 ` ```json ``` ` 代码块、裸 JSON，以及通过正则提取首个对象/数组 |

### 5.3 步骤二：category_l1 过滤

LLM 推断出的 `category_l1` 仅在属于以下合法值时才用于过滤：

```
应用、逻辑模块、运算模块、变量模块、定时模块、累计模块、基础组件、高级组件、备注组件、其他
```

对于复杂组合需求，LLM 会输出空字符串（不过滤），确保跨类别的模块都能被检索到。

### 5.4 步骤三：向量检索

根据 LLM 分析结果自动选择检索策略。

#### 5.4.1 多查询检索 (`_multi_query_retrieve`) — 主路径

**触发条件**: LLM 分析成功且 `queries` 非空（绝大多数情况）

```
多个查询变体 [v1, v2, v3, ...]（来自 LLM）
         │
         ▼
  ChromaDB collection.query(
    query_texts=[v1, v2, v3, ...],   ← 单次批量调用
    n_results=min(top_k, 5)          ← 每变体最多5条
  )
         │
         ▼
  ┌─────────────────────────────┐
  │ 遍历所有变体的结果:           │
  │   - L2距离→相似度分数         │
  │   - 阈值过滤                  │
  │   - 按 module_type 去重       │
  │   - 保留最高相似度分数         │
  └─────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────┐
  │ 后处理:                      │
  │   - 按相似度降序排序          │
  │   - 截取 Top-K               │
  │   - 重新计算排名              │
  └─────────────────────────────┘
```

**关键优化**: 利用 ChromaDB 的 `query_texts` 批量查询能力，将所有变体合并为**一次** I/O 调用。

#### 5.4.2 单查询检索 (`_single_query_retrieve`) — 兜底路径

**触发条件**: LLM 不可用或返回的 `queries` 为空

```
原始查询文本 → ChromaDB collection.query(query_texts=[query], n_results=top_k)
                                       │
                                       ▼
                               原始检索结果 (documents, metadatas, distances)
                                       │
                                       ▼
                               ┌───────────────────┐
                               │ 遍历每条结果:       │
                               │  1. L2距离→相似度分数│
                               │  2. 阈值过滤        │
                               │  3. 解析JSON Schema │
                               │  4. 提取节点信息     │
                               └───────────────────┘
                                       │
                                       ▼
                               检索结果字典
```

#### 单查询与多查询元数据差异

当前实现中，两条检索路径的 `metadata` 并不完全对称：

| 字段 | 单查询兜底路径 | 多查询主路径 |
|:---|:---|:---|
| `retrieved_count` | 有 | 有 |
| `avg_confidence_score` | 有 | 有 |
| `total_candidates` | 有 | 无 |
| `category_filter` | 有 | 无 |
| `query_variants_used` | 无 | 有 |
| `detected_operations` | 无 | 有 |
| `intent` | 无 | 有 |
| `rewrite_used` | 外层统一补写 | 外层统一补写 |
| `llm_queries` | 无 | 外层统一补写 |
| `llm_category_l1` | 无 | 外层统一补写 |

因此，`metadata.intent`、`metadata.detected_operations` 等字段只在 LLM 成功并进入多查询主路径时稳定出现；兜底路径不会自行补齐这些字段。

### 5.5 相似度计算

使用 L2 距离到相似度的归一化公式：

$$similarity = \frac{1}{1 + distance}$$

- 距离 = 0 → 相似度 = 1.0（完全匹配）
- 距离越大 → 相似度趋近于 0
- 结果范围: $(0, 1]$

默认阈值 `similarity_threshold = 0.3`，低于此值的结果被过滤。

### 5.6 排序与去重细节

- 多查询路径使用 `module_type` 作为去重键，同一模块被多个查询变体命中时，只保留相似度最高的一条。
- 多查询路径会在最终排序后重新计算 `rank`。
- 单查询路径不做二次去重，`rank` 直接沿用原始结果顺序。

---

## 6. 知识库管理

### 6.1 知识库加载 (`load_knowledge_base`)

扫描 `schemas/` 目录下的所有 `.json` 文件（排除 `扩展描述文件.json`），执行以下流程：

```
schemas/
├── application/   ← 应用模块
├── logic/         ← 逻辑模块
├── math/          ← 运算模块
├── variable/      ← 变量模块
├── timing/        ← 定时模块
├── accumulation/  ← 累计模块
└── others/        ← 其他

对每个 .json 文件:
  1. 读取并解析 JSON
  2. _serialize_module_to_text() → 生成语义文本块（用于向量索引）
  3. _extract_metadata()         → 提取元数据（用于条件过滤）
  4. 生成唯一 ID: "{category}_{module_type}"

最后: collection.upsert() 批量写入 ChromaDB
```

### 6.2 文本序列化 (`_serialize_module_to_text`)

将模块 JSON 转换为结构化的自然语言文本，包含以下语义层次：

1. **核心身份**: 模块名称、类型、类别
2. **功能描述**: 模块的核心功能说明（检索权重最高）
3. **关键词**: 关联的领域术语
4. **适用场景**: 使用场景列表（匹配用户意图的关键）
5. **参数功能**: 可配置参数及其含义（跳过纯技术字段 x/y/wires/id/z）
6. **输入输出端口**: 端口名称、类型、描述、显示条件

### 6.3 元数据提取 (`_extract_metadata`)

提取的元数据用于 ChromaDB 的 `where` 条件过滤：

| 元数据字段 | 说明 |
|:---|:---|
| `module_id` | 模块唯一标识 |
| `module_type` | 模块类型标识符 |
| `category` | 完整分类路径（如 `运算模块/数学运算`） |
| `category_l1` | 一级分类（如 `运算模块`），用于快速过滤 |
| `category_l2` | 二级分类（如 `数学运算`） |
| `has_dynamic_ports` | 是否有动态端口 |
| `keywords` | 关键词列表（逗号分隔字符串） |
| `json_schema` | 原始 JSON 的完整序列化（检索时用于还原完整信息） |

---

## 7. 关键配置参数

以下配置项定义在 `config.py` 中，可通过环境变量覆盖：

### 7.1 Embedding 配置

| 环境变量 | 默认值 | 说明 |
|:---|:---|:---|
| `EMBEDDING_PROVIDER` | `bge` | 嵌入模型提供商 |
| `BGE_MODEL_NAME` | `BAAI/bge-m3` | BGE 模型名称 |
| `BGE_DEVICE` | `cpu` | 运算设备 (cpu/cuda) |
| `SILICONFLOW_API_KEY` | - | 硅基流动 API Key |
| `SILICONFLOW_EMBEDDING_MODEL` | `BAAI/bge-m3` | 硅基流动嵌入模型 |

### 7.2 LLM 配置

| 环境变量 | 默认值 | 说明 |
|:---|:---|:---|
| `RETRIEVAL_LLM_PROVIDER` | `""` | LLM 提供商（空则复用全局 `LLM_PROVIDER`） |
| `RETRIEVAL_LLM_MODEL` | `""` | LLM 模型（空则复用对应 provider 默认模型） |
| `RETRIEVAL_LLM_MAX_QUERIES` | `8` | LLM 生成的最大查询数量 |
| `RETRIEVAL_LLM_TIMEOUT_S` | `8` | LLM 调用超时时间（秒） |

> 注：`config.py` 中仍保留 `RETRIEVAL_USE_LLM_REWRITE` 配置项，但当前 `agents/retrieval_agent.py` 实现并未读取该开关；现行逻辑是默认尝试 LLM 分析，失败后自动回退到单查询检索。

### 7.3 向量数据库配置

| 环境变量 | 默认值 | 说明 |
|:---|:---|:---|
| `CHROMA_PERSIST_DIR` | `./chroma_db` | ChromaDB 持久化目录 |

---

## 8. `retrieve()` 方法参数速查

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `query` | `str` | (必填) | 用户查询/需求文本 |
| `top_k` | `int` | `10` | 返回的最相关文档数量 |
| `category_filter` | `Optional[str]` | `None` | 按一级分类过滤 |
| `similarity_threshold` | `float` | `0.3` | 相似度阈值 |

> 注：v1 中的 `use_query_enhancement` 和 `use_llm_rewrite` 参数已移除。

---

## 9. 端到端执行示例

以查询 `"设计计算模块，输入0时，公式为：4.18×(输入A-输入B-输入C-输入D)×输入E÷3.6。输入1时，公式为：4.18×(输入A-输入B-输入C+输入D)×输入E÷3.6"` 为例：

### 第1步：LLM 意图分析

```
LLM 输出:
{
  "queries": [
    "条件选择公式计算",
    "基于输入选择执行不同公式",
    "减法运算 加法运算 乘法运算 除法运算",
    "通道选择 常量输入 变量输入",
    "4.18×(A-B-C-D)×E÷3.6",
    "4.18×(A-B-C+D)×E÷3.6",
    "逻辑判断 条件分支",
    "比较判断 线性变换"
  ],
  "category_l1": "",
  "intent": "mathematical_computation",
  "detected_operations": ["加法", "减法", "乘法", "除法"],
  "keywords": ["公式计算", "条件选择", "输入切换"]
}

→ category_l1 为空 → 不过滤类别
→ 8 个查询变体 → 走多查询检索
```

### 第2步：批量向量检索

```
调用 ChromaDB:
  query_texts = [8个查询变体]
  n_results = 5 (每变体)

检索结果去重 + 排序：
  ✅ 匹配: switch (通道选择) - 分数: 0.759
  ✅ 匹配: divide (除法运算) - 分数: 0.739
  ✅ 匹配: subtract (减法运算) - 分数: 0.734
  ✅ 匹配: multiply (乘法运算) - 分数: 0.732
  ✅ 匹配: constInput (常量) - 分数: 0.730
  ✅ 匹配: swInput (变量) - 分数: 0.723
  ✅ 匹配: add (加法运算) - 分数: 0.722
  ✅ 匹配: compare (比较判断) - 分数: 0.720
  ✅ 匹配: linear (线性变换) - 分数: 0.704
  ✅ 匹配: logic (逻辑运算) - 分数: 0.699
  ...（共 10 个模块）
```

### 第3步：输出

检索结果写入 `state["retrieval_context"]`，传递给 Planning Agent。

```
metadata:
  retrieved_count: 10
  query_variants_used: 8
  detected_operations: ["加法", "减法", "乘法", "除法"]
  intent: "mathematical_computation"
  avg_confidence_score: 0.726
  rewrite_used: true
  llm_queries: [8个查询变体]
  llm_category_l1: ""
```

---

## 10. 容错与兜底机制

| 场景 | 处理方式 |
|:---|:---|
| Embedding 模型加载失败 | 回退到 ChromaDB 默认 Embedding 函数 |
| ChromaDB 集合不存在 | 自动创建新集合 |
| LLM 初始化失败 | 标记 `_llm = None`，走兜底路径（原始查询单次检索） |
| LLM 调用超时 / 异常 | 捕获异常，返回 `None`，走兜底路径 |
| LLM 返回非法 JSON | 解析失败返回 `None`，走兜底路径 |
| LLM 返回非法 intent | 自动降级为 `general_query` |
| LLM 返回非法 detected_operations | 仅保留合法枚举值 |
| LLM 返回空 queries | 视为失败，走兜底路径 |
| 向量检索异常 | 返回空结果 `{"relevant_nodes": [], "error": "..."}` |
| JSON Schema 解析失败 | 跳过该条结果，继续处理下一条 |

### 兜底流程图

```
_llm_analyze_query(query)
         │
    ┌────┴────┐
    │ 成功?    │
    └────┬────┘
     Yes │  No
         │    │
         ▼    ▼
   多查询检索  单查询检索
   (8变体)    (原始query)
         │    │
         └──┬─┘
            ▼
    retrieval_context
    (结构完全一致)
```

---

## 11. 与上下游智能体的协作关系

### 与规划智能体（下游）

- **输出协议**: `retrieval_context` 结构与 v1 完全一致，规划智能体无需任何修改
- **关键字段**: `relevant_nodes` 提供可用模块列表，规划智能体从中构建白名单
- **元数据**: `metadata.detected_operations` 和 `metadata.intent` 被 `context_formatter.py` 格式化后传递给规划智能体的 LLM Prompt

### 输出兼容性

v2 保证以下字段与 v1 完全一致，对下游零影响：

| 字段路径 | 说明 |
|:---|:---|
| `retrieval_context.query` | 原始查询 |
| `retrieval_context.relevant_nodes[]` | 节点列表（11个字段） |
| `retrieval_context.similar_cases[]` | 示例代码 |
| `retrieval_context.metadata.retrieved_count` | 检索数量 |
| `retrieval_context.metadata.avg_confidence_score` | 平均置信度 |
| `retrieval_context.metadata.detected_operations` | 运算类型 |
| `retrieval_context.metadata.intent` | 意图分类 |
| `retrieval_context.metadata.rewrite_used` | 是否使用了 LLM |
| `retrieval_context.metadata.llm_queries` | LLM 生成的查询 |
| `retrieval_context.metadata.llm_category_l1` | LLM 推断类别 |
