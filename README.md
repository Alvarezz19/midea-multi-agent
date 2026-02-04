# KONG CUBE 智能组态生成系统
基于 LangGraph 的多智能体系统，自动将自然语言需求转换为楼宇自控组态文件。

## 项目结构

```
midea/
├── agents/                 # 智能体模块
│   ├── retrieval_agent.py  # 检索智能体
│   ├── planning_agent.py   # 规划智能体
│   ├── coding_agent.py     # 编码智能体
│   ├── validation_agent.py # 验证智能体
│   └── debugging_agent.py  # 调试智能体
├── tools/                  # 工具模块
│   └── execution_tool.py   # 代码执行沙箱
├── json/                   # JSON 组态文件样本
├── kong_sdk.py             # Kong CUBE SDK
├── workflow.py             # LangGraph 工作流编排
├── config.py               # 配置文件
├── requirements.txt        # 依赖列表
├── .env.example            # 环境变量模板
└── README.md               # 本文件
```

## 快速开始

### 1. 环境配置

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量（可选）
cp .env.example .env
# 编辑 .env 文件，填入你的 OpenAI API Key
# 如果不配置，将使用默认的 embedding 函数
```

### 2. 初始化知识库

首次使用前，需要加载模块定义到向量数据库：

```bash
python init_knowledge_base.py
```

这将扫描 `schemas/` 目录下的所有模块定义，并存储到 ChromaDB。

### 3. 测试检索功能

```bash
python workflow.py
```

示例输出：
```
🔍 开始检索: 比较温度是否大于25度
   ✅ 匹配 #1: compare (比较判断) - 分数: 0.856
   📊 检索完成: 找到 2 个相关模块
```

### 4. 在代码中使用

```python
from agents.retrieval_agent import RetrievalAgent

# 创建检索智能体
agent = RetrievalAgent()

# 检索相关模块
result = agent.retrieve("我需要比较两个温度值")

# 查看检索结果
for node in result['relevant_nodes']:
    print(f"{node['name']}: {node['similarity_score']:.3f}")
```

## 6 个智能体说明

| 智能体 | 状态 | 职责 | 输入 | 输出 |
|:---|:---:|:---|:---|:---|
| **Retrieval Agent** | ✅ | 从向量库检索相关知识 | 用户需求 | 上下文（节点定义、案例） |
| **Planning Agent** | 🚧 | 拆解需求为逻辑步骤 | 需求 + 上下文 | 执行计划（YAML） |
| **Coding Agent** | 🚧 | 生成 Python 代码 | 执行计划 | Python 代码（基于 SDK） |
| **Execution Tool** | 🚧 | 代码沙箱执行 | Python 代码 | 执行结果 / 错误堆栈 |
| **Validation Agent** | 🚧 | 双重验证（形式+语义） | JSON 组态 + 原始需求 | 验证报告 |
| **Debugging Agent** | 🚧 | 错误修复 | 错误信息 + 原代码 | 修正后的代码 |

**图例**: ✅ 已完成 | 🚧 开发中

## 工作流程（DAG）

```
开始 → 检索 → 规划 → 编码 → 执行 
                              ↓
                      成功 → 验证 → 通过 → 结束
                      ↓            ↓
                    调试 ←──────── 未通过
                      ↓
                   重试（最多3次）
```

## 核心特性

✅ **智能语义检索**：基于向量数据库的模块检索，支持自然语言查询  
✅ **分层知识表示**：将 JSON Schema 转换为富含语义的文本块  
✅ **元数据索引**：支持类别过滤和相似度阈值控制  
✅ **多模型支持**：支持 DeepSeek、OpenAI、通义千问等多种 LLM 和 Embedding 模型  
✅ **可扩展架构**：基于 LangGraph，易于添加新智能体  
🚧 **代码即组态**：生成 Python 中间代码，避免直接生成复杂 JSON  
🚧 **自动闭环**：执行失败时自动调试，最多重试 3 次  
🚧 **双重验证**：形式化检查 + LLM 语义检查  

**图例**: ✅ 已实现 | 🚧 开发中

## 🔧 技术栈

- **LangGraph**: 工作流编排
- **ChromaDB**: 向量数据库
- **Python 3.8+**: 开发语言

### 支持的模型

#### 大语言模型（LLM）
- ⭐ **DeepSeek**: 高性价比，中文友好（推荐）
- **OpenAI**: GPT-4, GPT-3.5-turbo
- **通义千问**: 阿里云，中文优秀
- **智谱 GLM**: 清华技术，中文优化

#### 嵌入模型（Embedding）
- ⭐ **BGE-M3**: 免费本地模型，多语言支持（推荐）
- **OpenAI**: text-embedding-ada-002
- **Sentence Transformers**: 轻量级多语言模型
- **Jina**: 中文优化

详见 [多模型配置指南](docs/model_configuration_guide.md)

## 当前进度

- ✅ 项目架构设计
- ✅ 多模型支持架构
  - ✅ 统一模型管理器
  - ✅ DeepSeek、OpenAI、通义千问、智谱GLM
  - ✅ BGE、OpenAI Embedding、Sentence Transformers
- ✅ 检索智能体完整实现
  - ✅ JSON Schema 智能序列化
  - ✅ 向量数据库集成（ChromaDB）
  - ✅ 语义检索功能
  - ✅ 知识库加载机制
  - ✅ 单元测试覆盖
- 🚧 规划智能体开发中
- 🚧 编码智能体开发中
- 🚧 其他智能体待开发

## 📖 详细文档

- [多模型配置指南](docs/model_configuration_guide.md) ⭐ 必读
- [检索智能体使用指南](docs/retrieval_agent_guide.md)
- [检索智能体实现总结](docs/retrieval_agent_implementation.md)
- [工作安排](工作安排.md) - 知识库构建方案
- [开发进度](开发进度.md)
- [团队开发规范](团队开发规范.md)

## TODO（下一步）

### 优先级 1（核心功能）
- [ ] 实现规划智能体（Planning Agent）
- [ ] 集成 LLM 进行需求分析
- [ ] 实现参数推理功能

### 优先级 2（增强功能）  
- [ ] 数据增强：生成假设性查询
- [ ] 案例检索：从历史 JSON 学习
- [ ] Kong SDK 的自动布局算法

### 优先级 3（工程化）
- [ ] 代码沙箱安全限制（禁用危险模块）
- [ ] Streamlit 前端界面
- [ ] 人工审核（Human-in-the-Loop）

## 开发指南

### 添加新的节点类型

编辑 `kong_sdk.py` 中的 `NODE_TYPES` 字典：

```python
NODE_TYPES = {
    "new_type": "新节点类型描述"
}
```

### 调试单个智能体

```python
from agents.coding_agent import CodingAgent

agent = CodingAgent()
result = agent.generate_code({"title": "测试计划"})
print(result)
```

## 许可证

内部项目 - 仅供美的楼宇科技使用
