# 检索智能体 (Retrieval Agent) 工作流总结

## 1. 智能体结构与职责

**Retrieval Agent** 是 KONG CUBE 智能组态生成系统中的知识获取核心组件。其主要职责是基于用户的自然语言需求，从向量数据库（ChromaDB）中检索相关的领域知识（模块定义、使用规范等），为后续的规划和编码提供必要的上下文信息。

### 核心组成
*   **向量数据库接口**: 使用 `chromadb` 连接持久化存储的知识库。
*   **Embedding 模型**: 支持多种嵌入模型（如 BGE, OpenAI, SiliconFlow 等）将文本转换为向量。
*   **查询处理器**: 集成 `QueryProcessor` 用于查询增强和意图识别。
*   **LangGraph 节点**: 不仅作为独立工具，还作为 LangGraph 工作流的起始节点 (`__call__` 方法)。

---

## 2. 输入与输出

### 输入 (Input)
检索智能体主要接收包含用户需求的工作流状态对象。
*   **核心输入**: `user_query` (字符串) - 用户的自然语言指令，例如 "设计一个计算模块，计算公式是..."。
*   **上下文**: LangGraph 的 `WorkflowState` 字典。

### 输出 (Output)
智能体将检索结果注入到工作流状态中，不直接返回单一值，而是更新状态字典。
*   **核心输出**: `retrieval_context` (字典)，包含：
    *   `query`: 原始查询。
    *   `relevant_nodes`: 最相关的模块列表（包含模块名、类型、描述、相似度分数、参数定义等）。
    *   `similar_cases`: 相似案例代码（用于 Few-Shot Learning）。
    *   `metadata`: 检索元数据（检索数量、平均置信度、过滤条件等）。

---

## 3. 主要参数

在初始化和调用检索功能时涉及的关键参数：

| 参数名 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `embedding_provider` | `Optional[str]` | `None` | 指定 Embedding 模型提供商 (init参数)。 |
| `query` | `str` | - | 用户的查询文本 (retrieve参数)。 |
| `top_k` | `int` | `10` | 返回的最相关文档数量 (retrieve参数)。 |
| `category_filter` | `Optional[str]` | `None` | 按模块类别（如 "Logic"）进行过滤 (retrieve参数)。 |
| `similarity_threshold` | `float` | `0.3` | 相似度阈值，低于此值的结果将被过滤 (retrieve参数)。 |
| `use_query_enhancement` | `bool` | `True` | 是否启用多查询增强策略 (retrieve参数)。 |

---

## 4. 关键函数详解

### 4.1 `__init__(self, embedding_provider=None)`
*   **作用**: 初始化 ChromaDB 客户端和 Embedding 函数。
*   **逻辑**: 尝试从配置加载指定的 embedding provider，连接到 `kong_modules_v1` 集合。如果集合不存在则创建。

### 4.2 `__call__(self, state: Dict) -> Dict`
*   **作用**: LangGraph 的调用入口。
*   **输入**: 工作流状态 `state`。
*   **输出**: 更新后的 `state` (包含 `retrieval_context`)。
*   **逻辑**: 从 state 获取 `user_query`，调用 `retrieve` 方法，将结果存入 state。

### 4.3 `retrieve(self, query, ...)`
*   **作用**: 检索主入口，根据策略选择单查询或多查询模式。
*   **输入**: `query` 及配置参数。
*   **输出**: `retrieval_context` 字典。
*   **逻辑**:
    1.  调用 `QueryProcessor.enhance_query(query)` 分析用户意图和提取关键词。
    2.  如果检测到复杂查询（如涉及多种运算），调用 `_multi_query_retrieve`。
    3.  否则调用 `_single_query_retrieve`。

### 4.4 `_single_query_retrieve(self, query, ...)`
*   **作用**: 执行标准的向量相似度搜索。
*   **输入**: 单个查询字符串。
*   **输出**: 检索结果结构体。
*   **逻辑**:
    1.  使用 ChromaDB 的 `query` 方法搜索。
    2.  根据 `similarity_threshold` 过滤低分结果。
    3.  解析 JSON Schema，提取关键字段（name, description, parameters等）。
    4.  调用 `_generate_example_code` 生成参考案例。

### 4.5 `_multi_query_retrieve(self, enhanced, ...)`
*   **作用**: 处理复杂查询，通过多个变体查询提高召回率。
*   **输入**: 增强后的查询对象 `enhanced` (包含 `query_variants`)。
*   **输出**: 合并后的检索结果。
*   **逻辑**:
    1.  遍历所有查询变体，分别调用 `_single_query_retrieve`。
    2.  对所有结果进行去重（按 `module_type`），保留相似度最高的结果。
    3.  重新排序并裁剪 Top-K。

### 4.6 `_serialize_module_to_text(self, module_json)`
*   **作用**: 知识库构建时的辅助函数。
*   **输入**: 模块的 JSON 定义。
*   **输出**: 语义化的文本字符串。
*   **逻辑**: 将 JSON 字段转换为 "Title: ... \n Description: ..." 格式的文本，并增加核心字段（功能描述、使用场景）的权重，用于 Embedding 索引。

### 4.7 `load_knowledge_base(self, schemas_dir)`
*   **作用**: 扫描 schema 目录并重建向量数据库。
*   **输入**: schema 文件夹路径。
*   **作用**:
    1.  遍历 `.json` 文件。
    2.  调用 `_serialize_module_to_text` 生成索引文本。
    3.  调用 `_extract_metadata` 提取筛选元数据。
    4.  批量写入 ChromaDB (`upsert`)。

---

## 5. 工作流程总结

1.  **启动**: 通过 `__call__` 接收用户需求。
2.  **增强**: 分析需求，识别关键运算，生成多个查询变体（如将 "计算 A+B" 拆解为 "加法", "运算" 等）。
3.  **搜索**: 在向量数据库中并发或串行执行语义搜索。
4.  **过滤与处理**: 过滤低置信度结果，解析原始 JSON Schema 为结构化信息，生成 Few-Shot 示例代码。
5.  **输出**: 将清洗后的结构化上下文传递给下游的规划智能体 (Planning Agent)。
