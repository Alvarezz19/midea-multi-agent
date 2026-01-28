# 知识库更新指南

## 概述

当你修改 `schemas` 目录下的模块 JSON 文件后，需要同步更新向量数据库。本文档介绍了多种更新方法。

## 核心组件

- **RetrievalAgent** ([retrieval_agent.py](../agents/retrieval_agent.py)): 负责检索和加载知识库
- **KnowledgeBaseManager** ([knowledge_base_manager.py](../utils/knowledge_base_manager.py)): 负责知识库的维护操作（更新、删除、重建等）

## 方法一：增量更新（推荐）

使用 `load_knowledge_base` 方法会自动处理更新：

```python
from agents.retrieval_agent import RetrievalAgent

agent = RetrievalAgent()
agent.load_knowledge_base("./schemas")
```

**优点**：
- 自动识别新增、修改的模块
- 使用 `upsert` 操作，已存在的会更新，不存在的会新增
- 不会删除未在文件中的模块

**使用场景**：日常维护，添加或修改少量模块

---

## 方法二：更新单个模块

当你只修改了一个 JSON 文件时：

```python
from utils.knowledge_base_manager import KnowledgeBaseManager

manager = KnowledgeBaseManager()
manager.update_single_module("./schemas/logic/比较判断.json")
```

**优点**：
- 快速，只更新一个模块
- 适合调试单个模块

**使用场景**：修改单个模块后快速验证

---

## 方法三：批量更新多个模块

当你修改了多个特定的 JSON 文件时：

```python
from utils.knowledge_base_manager import KnowledgeBaseManager

manager = KnowledgeBaseManager()

files = [
    "./schemas/logic/比较判断.json",
    "./schemas/logic/逻辑运算.json",
    "./schemas/math/加.json"
]

result = manager.update_multiple_modules(files)
print(f"成功: {result['success']}, 失败: {result['failed']}")
```

**优点**：
- 精确控制更新哪些模块
- 返回详细的统计信息

**使用场景**：批量修改一组相关模块

---

## 方法四：重建整个知识库

当你需要完全重建知识库时（删除所有旧数据）：

```python
from utils.knowledge_base_manager import KnowledgeBaseManager

manager = KnowledgeBaseManager()
manager.rebuild_knowledge_base("./schemas")
```

**优点**：
- 清理所有历史数据
- 确保数据库完全同步

**使用场景**：
- 修改了模块的 ID 生成规则
- 数据库损坏需要重建
- 大规模重构后

⚠️ **警告**：此操作会删除所有现有数据！

---

## 方法五：使用交互式工具

运行 `update_knowledge_base.py` 交互式更新：

```bash
python update_knowledge_base.py
```

提供菜单选项：
1. 更新单个模块
2. 批量更新多个模块
3. 删除指定模块
4. 重建整个知识库
5. 查看模块信息
6. 重新加载所有模块（增量更新）

**优点**：
- 用户友好的交互界面
- 适合不熟悉代码的用户

---

## 方法六：自动监控同步

### 持续监控模式

监控 schemas 目录的变化，自动同步：

```bash
python auto_sync_schemas.py --mode watch --interval 5
```

参数说明：
- `--mode watch`: 持续监控模式
- `--interval 5`: 每5秒检查一次

**优点**：
- 修改文件后自动同步，无需手动操作
- 实时监控文件变化

**使用场景**：开发阶段，频繁修改模块定义

### 一次性同步模式

一次性同步所有文件：

```bash
python auto_sync_schemas.py --mode sync --dir ./schemas
```

**优点**：
- 适合在脚本或 CI/CD 中使用
- 可以指定不同的目录

---

## 删除模块

删除向量数据库中的特定模块：

```python
from utils.knowledge_base_manager import KnowledgeBaseManager

manager = KnowledgeBaseManager()
manager.delete_module(
    module_type="compare",
    category="逻辑模块/比较判断"
)
```

**注意**：删除操作不会删除 JSON 文件，只删除向量数据库中的记录

---

## 查看模块信息

检查模块是否在向量数据库中：

```python
from utils.knowledge_base_manager import KnowledgeBaseManager

manager = KnowledgeBaseManager()
info = manager.get_module_info(
    module_type="compare",
    category="逻辑模块/比较判断"
)

if info:
    print(f"模块名称: {info['name']}")
    print(f"描述: {info['description']}")
else:
    print("模块不存在")
```

---

## 工作流程建议

### 日常开发流程

1. **修改 JSON 文件**
   ```
   编辑 schemas/logic/比较判断.json
   ```

2. **更新向量数据库**（选择以下任一方式）
   
   方式A - 使用自动监控（开发阶段）：
   ```bash
   python auto_sync_schemas.py --mode watch
   ```
   
   方式B - 手动更新单个文件：
   ```bash
   python -c "from utils.knowledge_base_manager import KnowledgeBaseManager; \
              manager = KnowledgeBaseManager(); \
              manager.update_single_module('./schemas/logic/比较判断.json')"
   ```
   
   方式C - 使用交互工具：
   ```bash
   python update_knowledge_base.py
   # 选择选项 1，输入文件路径
   ```

3. **验证更新**
   ```python
   from agents.retrieval_agent import RetrievalAgent
   
   agent = RetrievalAgent()
   result = agent.retrieve("比较两个数值", top_k=3)
   print(result['relevant_nodes'][0]['name'])  # 应该显示最新版本
   ```

### 生产部署流程

1. **完成所有修改**
2. **测试本地知识库**
3. **重建知识库**（确保一致性）
   ```python
   from utils.knowledge_base_manager import KnowledgeBaseManager
   manager = KnowledgeBaseManager()
   manager.rebuild_knowledge_base("./schemas")
   ```
4. **验证检索功能**
5. **部署到生产环境**

---

## 注意事项

### 模块 ID 规则

模块的唯一 ID 由以下规则生成：
```python
doc_id = f"{category.replace('/', '_')}_{module_type}"
```

例如：
- 类别：`逻辑模块/比较判断`
- 类型：`compare`
- ID：`逻辑模块_比较判断_compare`

⚠️ **重要**：如果修改了 `category` 或 `module_type`，会被视为新模块

### 数据持久化

向量数据库保存在：
```
./chroma_db/
```

此目录应该加入版本控制或定期备份。

### 性能考虑

- **单个模块更新**：最快（约1-2秒）
- **批量更新10个模块**：约5-10秒
- **全量重建（53个模块）**：约30-60秒（取决于 embedding 模型）

---

## 常见问题

### Q1: 修改 JSON 后检索结果没变化？

**原因**：向量数据库未更新

**解决**：运行增量更新
```bash
python -c "from agents.retrieval_agent import RetrievalAgent; \
           RetrievalAgent().load_knowledge_base('./schemas')"
```

### Q2: 删除了 JSON 文件，但检索还能找到？

**原因**：向量数据库中的记录未删除

**解决**：使用 `delete_module` 或重建知识库

### Q3: 更新后向量数据库没反应？

**检查**：
1. JSON 文件格式是否正确
2. `module_type` 和 `category` 是否正确
3. 查看控制台是否有错误信息（设置 `config.DEBUG = True`）

### Q4: 如何批量删除某个类别的所有模块？

目前需要手动逐个删除，或者使用重建功能（删除对应的 JSON 文件后重建）

---

## 快速参考

| 场景 | 推荐方法 | 命令 |
|------|---------|------|
| 修改单个文件 | 单个更新 | `manager.update_single_module(path)` |
| 修改多个文件 | 批量更新 | `manager.update_multiple_modules(paths)` |
| 添加新模块 | 增量更新 | `agent.load_knowledge_base()` |
| 大规模修改 | 重建知识库 | `manager.rebuild_knowledge_base()` |
| 开发阶段 | 自动监控 | `python auto_sync_schemas.py --mode watch` |
| 脚本/CI | 一次性同步 | `python auto_sync_schemas.py --mode sync` |
| 交互操作 | 交互工具 | `python update_knowledge_base.py` |

---

## 总结

选择合适的更新方法：

- 🚀 **快速迭代**：使用自动监控 (`auto_sync_schemas.py --mode watch`)
- 🎯 **精确更新**：使用单个或批量更新方法
- 🔄 **全面同步**：使用增量更新 (`load_knowledge_base()`)
- 🛠️ **彻底重建**：使用重建方法 (`rebuild_knowledge_base()`)
- 💬 **用户友好**：使用交互工具 (`update_knowledge_base.py`)
