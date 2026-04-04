# 知识库构建与结构说明

> 最后核对时间：2026-04-02
> 核对范围：`init_knowledge_base.py`、`agents/retrieval_agent.py`、`utils/knowledge_base_manager.py`、`update_knowledge_base.py`、`auto_sync_schemas.py`、`config.py`、`schemas/`
> 适用对象：需要理解当前项目“知识库如何构建、库里存什么、检索结果如何进入工作流”的开发者

## 1. 这份知识库在当前工作流里的角色

当前项目的“知识库”本质上不是业务文档库，而是一个 **模块定义向量库**。  
它把 `schemas/` 下的模块 JSON 定义转成可检索的语义文本，并连同原始结构化信息一起写入 ChromaDB，供 `RetrievalAgent` 在主工作流中召回。

在当前 Phase 1 主链里，它的位置可以概括为：

```text
schemas/*.json
  -> RetrievalAgent.load_knowledge_base()
  -> ChromaDB(collection: kong_modules_v1)
  -> RetrievalAgent.retrieve()
  -> retrieval_context
  -> Planning / Assembly / Coding
```

也就是说：

1. `schemas/` 是知识库的数据源。
2. `chroma_db/` 是知识库的持久化载体。
3. `retrieval_context` 是知识库对工作流的直接输出接口。
4. 下游真正依赖的不是“摘要”，而是完整模块定义，尤其是 `parameters_schema`、`ports_definition`、`template_json`。

如果只想看日常增删改操作，优先看 [`docs/knowledge_base_update_guide.md`](./knowledge_base_update_guide.md)。  
本文更关注“构建原理”和“结构事实”。

---

## 2. 数据源：`schemas/` 目录到底存了什么

### 2.1 当前仓库里的模块规模

截至 2026-04-02，`schemas/` 下当前共有 **53 个**参与入库的 `.json` 模块文件。

按 JSON 内部 `category` 一级分类统计，当前分布为：

| 一级分类 | 数量 |
|:---|---:|
| `运算模块` | 15 |
| `变量模块` | 11 |
| `逻辑模块` | 10 |
| `应用` | 8 |
| `定时模块` | 4 |
| `累计模块` | 3 |
| `控制模块` | 1 |
| `其他` | 1 |

注意两点：

1. 检索和入库判断真实分类时，依据的是每个 JSON 里的 `category` 字段，不是目录名。
2. 例如 `schemas/logic/回差控制.json` 虽然放在 `logic/` 目录下，但其一级分类实际是 `控制模块`。

### 2.2 单个模块 JSON 的核心字段

当前知识库依赖的模块定义，至少围绕以下几组字段组织：

| 字段 | 用途 |
|:---|:---|
| `module_type` | 模块的稳定类型标识，也是向量库唯一 ID 的组成部分 |
| `category` | 分类路径，如 `逻辑模块/比较判断` |
| `name` | 模块展示名 |
| `description` | 面向自然语言检索的核心描述 |
| `keywords` | 补充召回词 |
| `usage_guides` | 使用场景、连线提示、工程约束 |
| `parameters_schema` | 参数约束，供规划和填参使用 |
| `ports_definition` | 端口结构，供连线和编译使用 |
| `template_json` | 最终平台节点模板，供编译器生成产物 |

这些字段可以理解成四层：

1. 检索与理解层：`description`、`keywords`、`usage_guides`
2. 参数约束层：`parameters_schema`
3. 拓扑定义层：`ports_definition`
4. 生成模板层：`template_json`

### 2.3 当前数据结构的几个真实特征

当前仓库里还有几个值得写明的结构事实：

1. `template_json` 两种写法都存在：当前 **27 个对象**、**26 个数组**，检索和下游都需要兼容。
2. 当前有 **15 个模块**在输入端口上使用了 `condition != "always"` 的动态端口表达。
3. 当前没有发现重复的 `doc_id`，说明现有 `category + module_type` 组合仍然唯一。

---

## 3. 知识库是怎样构建出来的

### 3.1 正式初始化入口

首次初始化或需要做一次完整装载时，当前入口是：

```powershell
conda activate midea
python init_knowledge_base.py
```

`init_knowledge_base.py` 的职责很轻，主要是：

1. 创建 `RetrievalAgent`
2. 调用 `load_knowledge_base("./schemas")`
3. 打印简单 smoke test 检索结果

真正的构建逻辑都在 `RetrievalAgent.load_knowledge_base()` 里。

### 3.2 `RetrievalAgent` 初始化时做了什么

`RetrievalAgent.__init__()` 会先准备向量库连接和 embedding：

1. 用 `chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)` 打开本地 ChromaDB
2. 通过 `EmbeddingManager.get_embedding()` 获取 embedding function
3. 获取已有集合 `kong_modules_v1`
4. 如果集合不存在，则自动创建新集合

相关默认配置在 `config.py` 中：

| 配置项 | 默认值 | 作用 |
|:---|:---|:---|
| `CHROMA_PERSIST_DIR` | `./chroma_db` | ChromaDB 持久化目录 |
| `EMBEDDING_PROVIDER` | `bge` | 默认 embedding 提供商 |
| `BGE_MODEL_NAME` | `BAAI/bge-m3` | 本地 BGE 模型 |
| `BGE_DEVICE` | `cpu` | 本地 embedding 推理设备 |

如果指定 embedding 初始化失败，代码会退回到 ChromaDB 的默认 embedding function。

### 3.3 入库扫描范围

`load_knowledge_base()` 会递归扫描 `schemas/` 下的所有 `.json` 文件，并批量写入向量库。

当前扫描规则是：

1. 只处理扩展名为 `.json` 的文件
2. 显式跳过名为 `扩展描述文件.json` 的文件
3. `README.md`、`模块特点总结.md`、`扩展描述文件.jsonc` 这类文件不会被写入

因此，当前知识库的数据源范围非常清晰：  
**真正入库的是模块定义 JSON，而不是说明文档本身。**

### 3.4 从 JSON 到向量库记录的转换流程

每个模块 JSON 在入库时会经历三步：

#### 第一步：生成语义文本 `document`

`_serialize_module_to_text()` 会把 JSON 拼成一个更适合 embedding 的文本块，主要包含：

1. 模块名称、类型、类别
2. 功能描述
3. 关键词
4. 使用场景
5. 参数功能摘要
6. 输入输出端口说明

这一步的目的不是保留原始 JSON 格式，而是把“适合语义匹配的信息”集中到一段文本里。

#### 第二步：提取结构化元数据 `metadata`

`_extract_metadata()` 会写入以下元数据：

| 元数据字段 | 说明 |
|:---|:---|
| `module_id` | JSON 内部的 `id` 字段 |
| `module_type` | 模块类型 |
| `category` | 完整分类路径 |
| `category_l1` | 一级分类 |
| `category_l2` | 二级分类 |
| `has_dynamic_ports` | 是否存在条件输入端口 |
| `keywords` | 关键词字符串 |
| `json_schema` | 原始模块 JSON 的字符串化副本 |

这里最关键的是 `json_schema`。  
它让检索阶段可以直接从向量库结果中还原完整模块定义，而不用再回头重新读 `schemas/` 文件。

#### 第三步：生成唯一 ID 并 `upsert`

当前唯一 ID 规则是：

```python
doc_id = f"{category.replace('/', '_')}_{module_type}"
```

例如：

```text
category    = 逻辑模块/比较判断
module_type = compare
doc_id      = 逻辑模块_比较判断_compare
```

最终通过：

```python
self.collection.upsert(
    documents=documents,
    metadatas=metadatas,
    ids=ids,
)
```

批量写入集合 `kong_modules_v1`。

---

## 4. 知识库存储成什么样

### 4.1 逻辑存储单元

从 ChromaDB 的视角看，当前每条知识库记录由三部分组成：

1. `id`：`category + module_type` 派生的唯一键
2. `document`：语义文本块
3. `metadata`：分类、动态端口信息和完整 `json_schema`

因此，这个知识库并不是“只存向量，不存原文”。  
它实际上把“检索文本”和“原始结构化定义”一起存了进去。

### 4.2 本地落盘目录

默认持久化目录是：

```text
./chroma_db/
```

当前仓库里的实际落盘形态已经能看到典型的 ChromaDB 结构：

1. `chroma.sqlite3`
2. 某个 UUID 命名的向量索引目录

这说明知识库是 **本地持久化** 的，而不是每次启动都重新构建。

---

## 5. 检索时，知识库怎样进入工作流

### 5.1 上游输入：`analysis_result.retrieval_plan`

当前检索节点已经不是“自己理解需求”，而是消费 `AnalysisAgent` 给出的 `retrieval_plan`。

`retrieve()` 主要会使用这些信息：

1. `queries`
2. `category_l1`
3. `intent`
4. `detected_operations`
5. `keywords`

随后 RetrievalAgent 会先做一轮本地标准化和清洗，避免直接信任上游输出。

### 5.2 两条检索路径

当前实际存在两种路径：

#### 路径 A：多查询批量检索

当 `retrieval_plan.queries` 非空时：

1. 使用所有 query variants 一次性调用 `collection.query()`
2. 每个变体取最多 `min(top_k, 5)` 条结果
3. 把 Chroma 的 L2 distance 转成 similarity score
4. 过滤低于阈值的结果
5. 按 `module_type` 去重，保留高分版本

#### 路径 B：单查询兜底检索

当 `analysis_result` 缺失、`retrieval_plan` 非法或 `queries` 为空时：

1. 直接使用原始 `user_query`
2. 做一次单查询检索
3. 返回同样结构的 `retrieval_context`

这条兜底路径不依赖重新调用 LLM。

### 5.3 下游拿到的 `retrieval_context`

检索结果最终写入 `WorkflowState.retrieval_context`。  
其核心字段是 `relevant_nodes`，每个候选节点当前都会带回：

1. `module_type`
2. `name`
3. `description`
4. `category`
5. `parameters_schema`
6. `ports_definition`
7. `template_json`
8. `keywords`
9. `usage_guides`
10. `similarity_score`
11. `rank`
12. `matched_query`（仅多查询路径下可能出现）

这也是为什么知识库设计里必须保留完整 `json_schema`：  
因为下游不是只要“哪个模块相关”，而是要继续拿这些定义做规划、组装和编译。

---

## 6. 维护入口和适用场景

当前知识库维护能力主要分成四类：

### 6.1 全量初始化

```powershell
conda activate midea
python init_knowledge_base.py
```

适合首次建库或本地快速验证。

### 6.2 增量更新

最底层入口仍然是：

```python
RetrievalAgent().load_knowledge_base("./schemas")
```

它基于 `upsert`，因此：

1. 已存在的记录会更新
2. 不存在的记录会新增
3. 不会自动删除已经从文件系统中消失的旧记录

### 6.3 精确维护

`KnowledgeBaseManager` 提供了更细粒度的能力：

1. `update_single_module()`
2. `update_multiple_modules()`
3. `delete_module()`
4. `rebuild_knowledge_base()`
5. `get_module_info()`
6. `get_statistics()`

交互式入口是：

```powershell
conda activate midea
python update_knowledge_base.py
```

### 6.4 自动监控同步

开发时可以用：

```powershell
conda activate midea
python auto_sync_schemas.py --mode watch --interval 5
```

或者做一次性同步：

```powershell
conda activate midea
python auto_sync_schemas.py --mode sync --dir ./schemas
```

---

## 7. 当前实现里最容易踩坑的点

### 7.1 增量更新不会自动删除旧模块

`load_knowledge_base()` 和 `update_multiple_modules()` 都是 `upsert` 语义。  
如果你删除了某个 JSON 文件，旧记录不会自己消失。

正确做法是：

1. 明确调用 `delete_module()` 删除
2. 或直接 `rebuild_knowledge_base()` 重建整个集合

### 7.2 改 `category` 或 `module_type` 会生成新 ID

因为 `doc_id` 依赖这两个字段：

```python
category.replace('/', '_') + "_" + module_type
```

所以一旦改了分类或模块类型：

1. 新记录会被当作一个新模块写入
2. 旧 ID 对应的记录不会自动清理

这类变更建议直接重建知识库。

### 7.3 `auto_sync_schemas.py` 对“删除文件”还没有闭环

当前 watch 脚本已经能检测到文件被删除，但删除逻辑仍是 TODO。  
所以它适合“新增/修改自动同步”，不适合“删除后自动清库”。

### 7.4 分类过滤白名单和实际分类并不完全一致

`RetrievalAgent.retrieve()` 在应用 `category_l1` 过滤时，使用了一组硬编码白名单。  
这组白名单当前包含：

```text
逻辑模块、运算模块、变量模块、定时模块、累计模块、应用、
基础组件、高级组件、备注组件、其他
```

但当前 `schemas/` 的真实一级分类里还存在 `控制模块`。  
这意味着：

1. `控制模块` 里的模块仍然可以被检索到
2. 但如果上游分析明确给出 `category_l1 = 控制模块`，当前代码不会启用分类过滤，而是退回“无过滤检索”

后续如果继续扩展分类体系，应该同步修改这里的 allowed prefixes。

### 7.5 目录名不是唯一真相，JSON 内部字段才是契约

当前项目里已经出现“文件放在 `logic/` 目录里，但真实分类是 `控制模块/...`”的情况。  
所以：

1. 文档归类可以参考目录
2. 程序契约必须以 JSON 内容为准

---

## 8. 建议的阅读顺序

如果后续要继续改知识库，建议按这个顺序读：

1. `docs/knowledge_base_architecture.md`
2. `docs/knowledge_base_update_guide.md`
3. `init_knowledge_base.py`
4. `agents/retrieval_agent.py`
5. `utils/knowledge_base_manager.py`
6. `auto_sync_schemas.py`
7. `schemas/模块特点总结.md`
8. `schemas/` 下的具体模块 JSON

---

## 9. 一句话总结

当前项目的知识库可以准确理解为：

**一个以 `schemas/*.json` 为源、以 ChromaDB 为载体、以完整模块定义回传为目标的模块知识向量库。它既负责“语义召回”，也负责把规划和编译所需的结构化模块信息稳定交给下游工作流。**
