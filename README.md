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

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的 API 密钥
```

### 2. 运行工作流

```python
from workflow import run_workflow

# 输入需求
user_query = "计算夏季主机初始开启数量，需要手自动切换功能"

# 运行
result = run_workflow(user_query)

# 输出 JSON 组态
print(result['final_output'])
```

### 3. 可视化工作流

```python
from workflow import visualize_workflow

# 生成 Mermaid 流程图
print(visualize_workflow())
```

## 6 个智能体说明

| 智能体 | 职责 | 输入 | 输出 |
|:---|:---|:---|:---|
| **Retrieval Agent** | 从向量库检索相关知识 | 用户需求 | 上下文（节点定义、案例） |
| **Planning Agent** | 拆解需求为逻辑步骤 | 需求 + 上下文 | 执行计划（YAML） |
| **Coding Agent** | 生成 Python 代码 | 执行计划 | Python 代码（基于 SDK） |
| **Execution Tool** | 代码沙箱执行 | Python 代码 | 执行结果 / 错误堆栈 |
| **Validation Agent** | 双重验证（形式+语义） | JSON 组态 + 原始需求 | 验证报告 |
| **Debugging Agent** | 错误修复 | 错误信息 + 原代码 | 修正后的代码 |

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

✅ **代码即组态**：生成 Python 中间代码，避免直接生成复杂 JSON  
✅ **自动闭环**：执行失败时自动调试，最多重试 3 次  
✅ **双重验证**：形式化检查 + LLM 语义检查  
✅ **可扩展**：基于 LangGraph，易于添加新智能体  

## TODO（未完成部分）

- [ ] LLM 实际调用（目前为硬编码示例）
- [ ] 向量数据库初始化脚本
- [ ] Kong SDK 的自动布局算法
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
