# Analysis Agent 当前工作流总结

> 最后更新：2026-04-09

## 1. 当前定位

`AnalysisAgent` 仍然是正式主链入口节点，但它的职责已经不只是“给 Retrieval 写检索计划”。

在当前 Phase 3 主链里，它要同时产出两层结果：

1. `analysis_result`：保留给 Retrieval / compat 调用方使用的分析结果
2. `requirement_spec`：给 `ArchitecturePlanner` 使用的正式结构化需求契约

因此，`AnalysisAgent` 当前扮演的是“需求结构化前端”，而不是单纯的检索辅助节点。

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

`AnalysisAgent` 的直接下游有两个真实消费者：

- `RetrievalAgent`：消费 `analysis_result.retrieval_plan`
- `ArchitecturePlanner`：消费 `requirement_spec`

历史上的 `PlanningAgent` 只保留为 compat 路径，不再是正式主链下游。

## 3. 真实输入与输出

### 输入

- `user_query`

### 输出

- `analysis_result`
- `requirement_spec`
- `current_step = "analysis_completed"`

## 4. `analysis_result` 的当前意义

`analysis_result` 仍保持旧字段兼容，核心包括：

- `retrieval_plan`
- `scenario_analysis`
- `metadata`

它的主要作用是：

1. 给 `RetrievalAgent` 提供 query variants、intent、keywords 等检索线索
2. 为 compat 调用方保留历史语义入口
3. 给 `requirement_spec` 构建过程提供原始语义素材

## 5. `requirement_spec` 的当前意义

`requirement_spec` 是当前 Phase 3 主链里的正式需求契约，至少包含：

- `schema_version`
- `system_type`
- `scenario_summary`
- `subsystems`
- `signals`
- `required_pages`
- `global_modes`
- `ambiguities`
- `assumptions`
- `acceptance_criteria`
- `confidence`
- `warnings`

它不是 `analysis_result` 的简单拷贝，而是经过结构化归一后的规划入口。

## 6. 与 `ArchitecturePlanner` 的关系

`ArchitecturePlanner` 不再直接面向松散的 `scenario_analysis` 做系统规划，而是优先消费 `requirement_spec`。

这带来三个变化：

1. 规划入口从“Prompt 软参考”升级为显式结构化契约
2. 子系统、共享信号、必需页面等信息在进入架构层前就被标准化
3. `analysis_result` 可以继续保留 compat 价值，但不再承担正式系统规划契约

可以把两者关系理解为：

```text
user_query
  -> AnalysisAgent
       -> analysis_result      (给 Retrieval / compat)
       -> requirement_spec     (给 ArchitecturePlanner 正式规划)
```

## 7. 当前边界

`AnalysisAgent` 当前负责：

- 需求理解
- 检索计划生成
- 场景摘要抽取
- `requirement_spec` 构建

`AnalysisAgent` 当前不负责：

- 向量检索
- 系统级骨架规划
- 子系统局部 IR 生成
- 全局装配
- 编译与验收

## 8. 一句话结论

当前 `AnalysisAgent` 的真实职责是：把自然语言需求同时翻译成 Retrieval 可消费的 `analysis_result`，以及 ArchitecturePlanner 可消费的 `requirement_spec`，为 Phase 3 分层规划主链提供统一入口。
