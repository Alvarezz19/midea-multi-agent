# Retrieval Agent 当前工作流总结

> 最后更新：2026-04-09

## 1. 当前定位

`RetrievalAgent` 仍然是当前正式主链节点，但它的正式输出已经从单层 `retrieval_context` 升级为：

1. `retrieval_bundle`：Phase 2 / Phase 3 正式检索契约
2. `retrieval_context`：由 bundle 派生的兼容视图

因此，当前 Retrieval 节点的真实职责是“统一检索原子模块、AHU 子流程模板与 system pattern”，而不是只给旧 `PlanningAgent` 提供模块白名单。

## 2. 在工作流中的位置

当前正式主链为：

```text
user_query
  -> analysis
  -> retrieval
  -> architecture_planning
  -> subsystem_planning
  -> global_assembly
  -> coding
  -> verification
  -> END
```

`RetrievalAgent` 的上游是 `AnalysisAgent`，下游正式消费者是：

- `ArchitecturePlanner`
- `SubsystemPlanner`
- `GlobalAssembler`
- `CodingAgent`

历史上的 `PlanningAgent` / `AssemblyAgent` 只保留为 compat 消费方，不是正式主链节点。

## 3. 真实输入与输出

### 输入

- `user_query`
- `analysis_result`

### 输出

- `retrieval_bundle`
- `retrieval_context`
- `current_step = "retrieval_completed"`

## 4. `retrieval_bundle` 的结构

当前正式 bundle 包含：

- `atomic_modules`
- `subflow_templates`
- `system_patterns`
- `style_guides`
- `metadata`

其中 `metadata` 至少包含：

- `selected_case_pattern_id`
- `retrieved_atomic_count`
- `retrieved_subflow_count`
- `retrieved_pattern_count`
- `intent`
- `detected_operations`
- `query_bundle_version`

## 5. 当前检索边界

当前 Retrieval 节点负责：

1. 读取 `analysis_result.retrieval_plan`
2. 检索原子模块 collection
3. 检索 AHU `subflow_templates`
4. 检索 AHU `system_patterns`
5. 组合为正式 `retrieval_bundle`
6. 派生 compat `retrieval_context`

当前 Retrieval 节点不负责：

- 系统级规划
- 子系统局部 IR 生成
- 全局装配
- 编译
- 验收

## 6. 当前知识库边界

当前 Retrieval 链路依赖三类 Chroma collections：

- `kong_modules_v1`
- `ahu_subflow_templates_v1`
- `ahu_system_patterns_v1`

默认持久化目录是 `outputs/chroma_db`，配置见 `config.py`。

`AHU程序/pattern_library` 是规范化导出目录，不是 Retrieval 的唯一事实源；正式运行时优先读取 Chroma collections。

## 7. compat 说明

### `retrieval_context`

- 仍会继续写回
- 本质上是 `build_legacy_retrieval_context(retrieval_bundle)` 的兼容视图
- 主要服务旧 `PlanningAgent` / `AssemblyAgent` / 历史调用方

### `agents/retrieval_agent_old.py`

- 历史保留实现
- 不在当前正式主链中
- 不应继续扩展为新的正式检索入口

## 8. 一句话结论

当前 `RetrievalAgent` 的真实职责是：把 `AnalysisAgent` 给出的检索线索转成正式 `retrieval_bundle`，为 Phase 3 分层规划主链提供原子模块、AHU 模板和 system pattern 资产，同时保留 `retrieval_context` 兼容旧调用。
