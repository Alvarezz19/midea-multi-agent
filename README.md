# KONG CUBE 智能组态生成系统

基于 LangGraph 的多智能体工作流，用于把自然语言需求转换为 KONG CUBE 可导入的组态 JSON。

> 最后核对时间：2026-04-17  
> 当前真实主链、状态契约与测试事实以 [工作流总结文档](工作流总结文档.md) 为准；变更时间线见 [工作流演进记录](工作流演进记录.md)。

## 当前结论

- 当前系统已经完成 `Phase 6` 质量收口、`Phase 7` 工程准备冻结，以及 `Phase 8` 的前置澄清与架构评审主链接入。
- 当前正式主链为：

```text
user_query
  -> analysis
  -> ambiguity_router
  -> (clarification_review -> clarification_apply -> retrieval) | retrieval
  -> retrieval
  -> architecture_planning
  -> architecture_review
  -> (architecture_feedback_apply -> architecture_planning) | subsystem_planning
  -> subsystem_planning
  -> global_assembly
  -> coding
  -> verification
  -> repair_router
  -> (accept -> END) / (repair_agent -> subsystem_planning | global_assembly | coding)
```

- 当前真实主产物是 `compiled_artifact`；正式顶层状态已不再回填 `generated_code`。
- 当前真实编译输入是 `assembled_graph_ir`；正式顶层状态已不再回填 `execution_plan`。
- `assembled_graph_ir.source_execution_plan` 已从正式 IR 中移除。
- 当前未接入：`Send` 并行派发、reducer fan-in、`repair_review` 后置审核、完整 `internal_flow_objects` body 编译。
- `workflow_trace.py` 现在会把 review 暂停记为 `interrupted`，并在 trace 目录中补 `review_records.json`、`approval_record.json` 与 review 索引路径。

## 环境准备

```powershell
conda activate midea
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

然后根据需要在 `.env` 中配置：

- `LLM_PROVIDER` 及对应 API Key
- `EMBEDDING_PROVIDER` 及对应模型配置
- `ANALYSIS_LLM_PROVIDER`、`PLANNING_LLM_PROVIDER` 等可选覆盖项

## 正式入口

### Python

```python
from workflow import run_workflow
result = run_workflow("为 AHU 生成送风机与电加热联动控制")
```

```python
from workflow_trace import run_workflow
result = run_workflow("为 AHU 生成送风机与电加热联动控制")
```

### 命令行

```powershell
conda activate midea
python workflow.py
```

```powershell
conda activate midea
python workflow_trace.py
```

`workflow_trace.py` 与 `workflow.py` 使用同一套正式主链拓扑，只额外落盘 trace 文件，并在 `final_output.workflow_trace` 回写产物路径；当存在 review 历史时，还会补充 `review_records_json`、`approval_record_json` 与 thread/attempt 级 review 索引。

## 关键状态字段

### 正式字段

- `analysis_result`
- `requirement_spec`
- `retrieval_bundle`
- `decomposition_result`
- `architecture_plan`
- `subsystem_plan_map`
- `assembled_graph_ir`
- `compiled_artifact`
- `verification_report`
- `final_output`

### 已降级为 legacy / compat 的对象

- `build_legacy_retrieval_context(...)`
- `utils/legacy_execution_plan.py` 中的 `build_legacy_execution_plan(...)`

### 历史预留字段

- `debug_history`
- `retry_count`
- `current_step`

## 各节点职责

| 节点 | 当前职责 | 关键输出 |
|:---|:---|:---|
| `analysis` | 结构化需求理解 | `analysis_result`、`requirement_spec` |
| `retrieval` | 检索原子模块与 Phase 2 AHU 资产 | `retrieval_bundle` |
| `architecture_planning` | 生成系统骨架、页签和共享信号约束 | `decomposition_result`、`architecture_plan` |
| `subsystem_planning` | 逐个子系统生成局部 IR | `subsystem_plan_map` |
| `global_assembly` | 组装全局 Graph IR | `assembled_graph_ir` |
| `coding` | 确定性编译平台 JSON | `compiled_artifact` |
| `verification` | 结构验收 | `verification_report`、`final_output` |

## Phase 2 资产链与知识库

当前检索链已经分成两层资产：

1. `schemas/*.json`：原子模块定义，写入 `kong_modules_v1`
2. `AHU程序/flows_*.json`：AHU 子流程模板与 system pattern 源数据，经构建后写入：
   - `ahu_subflow_templates_v1`
   - `ahu_system_patterns_v1`

默认配置见 [config.py](config.py)：

- `CHROMA_PERSIST_DIR = ./outputs/chroma_db`
- `AHU_PATTERN_LIBRARY_DIR = AHU程序/pattern_library`
- `PHASE2_CHROMA_COLLECTION_OWNER = phase2_ahu_assets`

### 构建命令

只生成规范化产物：

```powershell
conda activate midea
python scripts/build_phase2_retrieval_indexes.py --output-dir AHU程序/pattern_library
```

生成规范化产物并写入正式 Chroma collections：

```powershell
conda activate midea
python scripts/build_phase2_retrieval_indexes.py --output-dir AHU程序/pattern_library --write-chroma --persist-dir outputs/chroma_db
```

### 当前口径

- `pattern_library` 是可重建缓存，不是唯一事实源。
- 当前正式检索主输出是 `retrieval_bundle`；`retrieval_context` 只是兼容视图。
- `manifest.json` 会记录 `build_command`、`persist_dir`、`collection_names`、`collection_owner` 和源 `flows_*.json` 的摘要。
- 回滚采用“重建式”策略：保留 manifest / build_command，切换或重建目标 `persist_dir`，不要手工改 collections 内容。

## 遗留模块状态

| 模块 | 当前状态 | 说明 |
|:---|:---|:---|
| `agents/legacy/planning_agent.py` | legacy 实现 | 仍有 Phase 2 legacy 回归测试覆盖，但不在 Phase 3 正式主链中 |
| `agents/legacy/assembly_agent.py` | legacy 实现 | 正式共享 helper 已抽到 `agents/assembly_shared.py`；formal 代码不再复用该类 |

其中 root wrapper `planning_agent.py`、`assembly_agent.py`、`validation_agent.py`、`debugging_agent.py`、`retrieval_agent_old.py` 已删除；另外仓内 `0` 调用的 `agents/legacy/validation_agent.py`、`agents/legacy/debugging_agent.py`、`agents/legacy/retrieval_agent_old.py` 也已清退。`GlobalAssembler` 已不再继承 legacy `AssemblyAgent`，而是复用 `agents/assembly_shared.py` 中的共享 helper。

兼容测试也开始分层：`tests/test_legacy_execution_plan.py`、`tests/test_phase2_planning_bundle.py`、`tests/test_phase2_retrieval_bundle.py`、`tests/test_phase2_retrieval_agent.py`、`tests/test_phase6_retrieval_eval_contract.py` 目前仍保留兼容入口或混合入口，真实测试实现已下沉到 `tests/legacy/` / `tests/contracts/`，以便在不破坏现有命令的前提下逐步剥离 legacy 回归集。`tests/test_legacy_agent_imports.py` 已随 root wrapper 删除一并清退。

## 已验证环境基线

当前仓库在 `midea` Conda 环境下完成验证，版本基线如下：

| 组件 | 已验证版本 |
|:---|:---|
| Python | `3.12.12` |
| `langgraph` | `1.0.6` |
| `langchain` | `1.2.6` |
| `chromadb` | `1.4.1` |
| `langchain-openai` | `1.1.7` |
| `openai` | `2.15.0` |
| `pydantic` | `2.12.4` |
| `sentence-transformers` | `5.2.0` |
| `torch` | `2.10.0` |
| `transformers` | `4.57.6` |
| `python-dotenv` | `1.2.1` |
| `langsmith` | `0.6.0` |
| `colorama` | `0.4.6` |

`requirements.txt` 已按这组基线收紧下界，不再保留 `langgraph>=0.0.40` 这类失真的旧声明。

### 后续阶段说明

- 若后续进入 HITL / `interrupt` / persistence，需要按目标 API 重新验证 LangGraph 版本，并补 checkpointer 相关依赖。
- 若后续进入 `Send` / `Command` 路由升级，应从当前已验证版本出发，不再按旧下界假设兼容。
- 当前 `1.0.6` 只代表本仓库现有 Phase 1/2/3 主链的验证基线，不代表未来所有 LangGraph 新能力都已验过。

## 验收与回归命令

基础回归：

```powershell
conda activate midea
python -m unittest discover -s tests -p "test_phase3*.py"
python -m unittest discover -s tests -p "test_phase2*.py"
python -m unittest discover -s tests -p "test_phase1_workflow.py"
```

环境与依赖一致性：

```powershell
conda activate midea
python -m unittest tests.test_runtime_versions
python -m pip check
```

Phase 2 正式落库烟测：

```powershell
conda activate midea
python scripts/build_phase2_retrieval_indexes.py --output-dir outputs/test_tmp/pattern_library_phase123_rectify
python scripts/build_phase2_retrieval_indexes.py --output-dir outputs/test_tmp/pattern_library_phase123_rectify_write --write-chroma --persist-dir outputs/test_tmp/chroma_phase123_rectify
```

## 文档索引

- [工作流总结文档](工作流总结文档.md)：当前系统真实画像、状态字段、测试事实
- [工作流演进记录](工作流演进记录.md)：改动时间线、决策与验收记录
- [AHU程序/LangGraph工作流V2架构设计.md](AHU程序/LangGraph工作流V2架构设计.md)：V2 架构设计稿
- [docs/analysis_agent_summary.md](docs/analysis_agent_summary.md)：Analysis Agent 当前边界
- [docs/new_retrieval_agent_summary.md](docs/new_retrieval_agent_summary.md)：Retrieval Agent 当前正式契约与兼容接口
- [docs/planning_agent_summary.md](docs/planning_agent_summary.md)：旧 `PlanningAgent` compat 说明
- [docs/coding_agent_summary.md](docs/coding_agent_summary.md)：CodingAgent 编译边界
- [docs/knowledge_base_architecture.md](docs/knowledge_base_architecture.md)：知识库与 Phase 2 资产链说明

## 当前限制

- 结构验收已稳定，但系统级 AHU 规划质量仍需继续迭代。
- 真实在线 LLM 质量、真实项目上的召回质量与 Repair 闭环仍未完成验收。
- 若 `AHU程序/flows_*.json` 未纳入版本管理，则“干净克隆即可复现正式资产链”不成立。

## 许可证

内部项目，仅供美的楼宇科技使用。
