# KONG CUBE 智能组态生成系统

基于 LangGraph 的多智能体工作流，用于把自然语言需求转换为 KONG CUBE 可导入的组态 JSON。

当前主链路已经接入 4 个节点：Analysis Agent、Retrieval Agent、Planning Agent、Coding Agent。Execution Tool、Validation Agent、Debugging Agent 仍保留代码骨架与状态字段，但尚未接入 workflow.py 的正式执行链路。

## 当前状态

| 组件 | 状态 | 当前职责 | 备注 |
|:---|:---:|:---|:---|
| Analysis Agent | ✅ | 解析用户需求，产出 retrieval_plan 和 scenario_analysis | 当前工作流入口节点 |
| Retrieval Agent | ✅ | 消费 retrieval_plan 并执行 ChromaDB 检索 | 已从“检索+分析”收敛为纯检索执行器 |
| Planning Agent | ✅ | 基于 analysis_result 和 retrieval_context 生成 execution_plan | 输出结构化 PlanIR |
| Coding Agent | ✅ | 将 execution_plan 落地为最终组态 JSON 字符串 | generated_code 当前实际存的是 JSON 文本 |
| Execution Tool | 🚧 | 代码执行沙箱 | 有实现，但未接入正式工作流 |
| Validation Agent | 🚧 | 形式化验证 + 语义验证 | 仍以占位逻辑为主 |
| Debugging Agent | 🚧 | 错误分析与修复 | 仍以占位逻辑为主 |

## 当前工作流

workflow.py 中当前启用的是线性四节点主链路：

```text
user_query
  -> Analysis Agent
  -> Retrieval Agent
  -> Planning Agent
  -> Coding Agent
  -> END
```

对应的共享状态字段为：

- user_query：原始用户需求
- analysis_result：分析结果，包含 retrieval_plan 和 scenario_analysis
- retrieval_context：检索得到的完整模块上下文
- execution_plan：规划阶段生成的 PlanIR
- generated_code：最终生成的组态 JSON 字符串
- execution_result、validation_result、debug_history、retry_count：已预留，暂未在主链路中使用

## 项目结构

```text
midea/
├── agents/
│   ├── analysis_agent.py
│   ├── retrieval_agent.py
│   ├── planning_agent.py
│   ├── coding_agent.py
│   ├── validation_agent.py
│   ├── debugging_agent.py
│   └── retrieval_agent_old.py
├── tools/
│   └── execution_tool.py
├── utils/
│   ├── context_formatter.py
│   ├── knowledge_base_manager.py
│   └── model_manager.py
├── schemas/                 # 模块 Schema 知识库
├── chroma_db/               # ChromaDB 持久化目录
├── generated_flow/          # 工作流生成的 JSON 输出
├── docs/                    # 各节点设计与实现文档
├── workflow.py              # 当前正式工作流入口
├── workflow_trace.py        # 带 trace 的实验编排文件
├── init_knowledge_base.py   # 首次初始化知识库
├── update_knowledge_base.py # 交互式知识库维护工具
├── auto_sync_schemas.py     # schemas 自动同步工具
├── config.py                # 模型与运行配置
└── README.md
```

## 核心能力

- 语义分析前置：Analysis Agent 将用户需求拆成 retrieval_plan 和 scenario_analysis，提升模糊需求理解能力。
- 纯检索执行：Retrieval Agent 只负责标准化检索计划、执行向量检索、返回完整模块定义。
- 受约束规划：Planning Agent 只能使用 retrieval_context 中的 module_type 白名单，避免虚构模块。
- 确定性落地：Coding Agent 基于 template_json、参数和连线关系生成最终平台 JSON，而不是自由生成代码。
- 知识库维护：支持初始化、增量更新、批量更新、重建和目录监听同步。
- 多模型支持：LLM 支持 DeepSeek、OpenAI、通义千问、智谱 GLM、Kimi；Embedding 支持 BGE、OpenAI、Sentence Transformers、Jina 等。

## 快速开始

### 1. 配置环境

推荐先激活本地 Conda 环境：

```powershell
conda activate midea
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

然后根据需要在 .env 中配置：

- LLM_PROVIDER 及对应 API Key
- EMBEDDING_PROVIDER 及对应模型配置
- ANALYSIS_LLM_PROVIDER、PLANNING_LLM_PROVIDER 等可选覆盖项

默认配置下：

- LLM_PROVIDER 为 deepseek
- EMBEDDING_PROVIDER 为 bge
- Analysis Agent 温度为 0.2
- Planning Agent 温度为 0.7

### 2. 初始化知识库

首次运行前，需要将 schemas 目录中的模块定义加载到 ChromaDB：

```powershell
conda activate midea
python init_knowledge_base.py
```

该脚本会：

- 初始化 RetrievalAgent
- 扫描 schemas 目录
- 生成语义文本块与元数据
- 写入 chroma_db 持久化目录

### 3. 运行当前工作流

```powershell
conda activate midea
python workflow.py
```

当前脚本会：

- 调用 run_workflow(user_query)
- 依次输出 analysis、retrieval、planning、coding 的摘要
- 将最终生成的 JSON 保存到 generated_flow 目录

### 4. 在代码中调用

运行完整工作流：

```python
from workflow import run_workflow

result = run_workflow("生成一个程序，接收一个输入，输入5v的时候，输出1，输入3v的时候输出2，输入10v的时候输出0")

print(result["current_step"])
print(result["execution_plan"])
print(result["generated_code"][:300])
```

单独调用检索智能体：

```python
from agents.analysis_agent import AnalysisAgent
from agents.retrieval_agent import RetrievalAgent

query = "我需要比较两个温度值"

analysis_agent = AnalysisAgent()
analysis_result = analysis_agent.analyze(query)

retrieval_agent = RetrievalAgent()
result = retrieval_agent.retrieve(query, analysis_result=analysis_result)

for node in result["relevant_nodes"]:
    print(f"{node['name']}: {node['similarity_score']:.3f}")
```

## 各节点输入输出契约

### Analysis Agent

- 输入：user_query
- 输出：analysis_result
- 关键字段：retrieval_plan、scenario_analysis、metadata

### Retrieval Agent

- 输入：user_query、analysis_result
- 输出：retrieval_context
- 关键字段：relevant_nodes、metadata、similar_cases

说明：similar_cases 当前保持兼容字段，默认返回空列表。

### Planning Agent

- 输入：user_query、retrieval_context、analysis_result
- 输出：execution_plan
- 关键结构：goal、nodes、connections

### Coding Agent

- 输入：execution_plan、retrieval_context
- 输出：generated_code
- 当前输出格式：平台可导入的 JSON 字符串

## 知识库维护

### 交互式更新

```powershell
conda activate midea
python update_knowledge_base.py
```

支持：

- 更新单个模块
- 批量更新多个模块
- 删除指定模块
- 重建整个知识库
- 查看模块信息
- 重新加载所有模块
- 查看统计信息

### 自动监听同步

```powershell
conda activate midea
python auto_sync_schemas.py --mode watch --interval 5
```

### 一次性同步

```powershell
conda activate midea
python auto_sync_schemas.py --mode sync --dir ./schemas
```

## 文档索引

docs 目录当前包含的节点与协作文档如下：

- docs/analysis_agent_integration_plan.md：Analysis Agent 接入方案与设计背景
- docs/analysis_agent_summary.md：Analysis Agent 当前职责、输出契约与流程总结
- docs/new_retrieval_agent_summary.md：Retrieval Agent 当前工作流位置、输入输出与检索策略总结
- docs/planning_agent_summary.md：Planning Agent 的 PlanIR 契约、重试与上下文压缩逻辑总结
- docs/coding_agent_summary.md：Coding Agent 的模板落地、布局和连线生成逻辑总结
- docs/optimization_plan_retrieval_planning.md：Retrieval -> Planning 协作优化方案
- docs/knowledge_base_update_guide.md：知识库增量更新、重建与同步指南


## 当前限制

- workflow.py 只接入了 analysis、retrieval、planning、coding 四个节点，尚未实现执行-验证-调试闭环。
- Validation Agent 和 Debugging Agent 仍包含较多 TODO 与示例逻辑，不能视为正式完成。
- generated_code 这一字段名保留了历史命名，但当前实际内容是 JSON，不是 Python 代码。
- 部分实验输出和 generated_flow 示例文件用于验证生成效果，不代表统一的最终接口规范。

## 下一步方向

- 将 Execution Tool、Validation Agent、Debugging Agent 接入正式工作流
- 完善验证与错误修复闭环
- 继续收敛 Planning Agent 的参数推理与模块选择稳定性
- 增强 Coding Agent 对动态端口和复杂模板的适配能力
- 引入更完整的测试覆盖和评估样本集

## 许可证

内部项目，仅供美的楼宇科技使用。
